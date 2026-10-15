"""Research agent (stage 3): searches the web with Firecrawl and indexes pages as sources.

The agent plans several search queries, picks the most credible URLs, scrapes them, and
every scraped page is added to the SourceStore (chunked + embedded), so the chat agent can
answer from it like any uploaded file.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlparse

from firecrawl import Firecrawl
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from core.store import Source, SourceStore, store

MODEL = os.getenv("NOTEBOOKLM_CHAT_MODEL", "openai:gpt-4o")
MAX_SOURCE_CHARS = 30_000  # keep each indexed page bounded (embedding cost / latency)
MAX_PAGES_PER_CRAWL = 5

SYSTEM_PROMPT = """You are a deep web-research assistant for a notebook of sources.

Given a topic, do this:
1. Write 3-4 DIFFERENT search queries that cover the topic from different angles, and call
   web_search for each one.
2. From all results, choose the 3-6 most relevant and credible, distinct pages. Skip
   duplicates, ads, social media, forums and paywalled pages.
3. Call web_scrape on each chosen URL. Use web_crawl only when several pages of one
   documentation site are needed.
4. Finish with a short paragraph summarizing which pages you added and why.

Scraped pages are indexed automatically; you never need to copy their content."""

REVIEW_SYSTEM_PROMPT = """You are a deep web-research assistant for a notebook of sources.
A human will choose which pages are actually scraped.

Given a topic, do this:
1. Write 3-4 DIFFERENT search queries that cover the topic from different angles, and call
   web_search for each one.
2. From all results, propose the 5-8 most relevant and credible, distinct pages by calling
   web_scrape once per page (pass the result's title as `title`), all in the same turn.
   Skip duplicates, ads, social media, forums and paywalled pages.
3. The human approves or rejects each proposed page. Do NOT re-propose rejected pages and
   do NOT propose more pages afterwards.
4. Finish with a short paragraph summarizing which pages were added.

Scraped pages are indexed automatically; you never need to copy their content."""


@dataclass
class ResearchResult:
    summary: str
    sources: list[Source]


def _field(obj, name: str, default=None):
    """Read a field from an SDK object or a plain dict."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _client() -> Firecrawl:
    # Without a key Firecrawl's free, rate-limited tier is used for scrape/search.
    api_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    if not api_key or api_key.endswith("..."):  # unset or the .env.example placeholder
        return Firecrawl()
    return Firecrawl(api_key=api_key)


def _error(action: str, exc: Exception) -> str:
    """Report a failed web call to the agent so it can skip it and try something else."""
    return f"{action} failed: {exc}. Skip this one and try a different URL or query."


def _add_page(store: SourceStore, added: list[Source], url: str, doc, fallback_title: str = "") -> str:
    markdown = (_field(doc, "markdown") or "").strip()
    if not markdown:
        return f"No readable content found at {url}."
    title = _field(_field(doc, "metadata"), "title") or fallback_title or url
    name = f"{title[:60]} [{urlparse(url).netloc}]"
    if any(s.name == name for s in store.list()):
        return f"Already added: {name}"
    source = store.add(name=name, content=markdown[:MAX_SOURCE_CHARS])
    added.append(source)
    return f"Added source '{name}' ({len(source.content)} chars)."


def _make_tools(store: SourceStore, added: list[Source]):
    @tool
    def web_search(query: str, limit: int = 5) -> str:
        """Search the web. Returns numbered results with title, url and a short description."""
        try:
            result = _client().search(query, limit=limit)
        except Exception as exc:
            return _error(f"Search for '{query}'", exc)
        items = _field(result, "web") or []
        if not items:
            return "No results."
        lines = []
        for i, item in enumerate(items, start=1):
            lines.append(
                f"[{i}] {_field(item, 'title', '')}\n{_field(item, 'url', '')}\n"
                f"{_field(item, 'description', '')}"
            )
        return "\n\n".join(lines)

    @tool
    def web_scrape(url: str, title: str = "") -> str:
        """Scrape one web page and add its main content to the notebook as a source.

        Pass the page title from the search results as `title`.
        """
        try:
            doc = _client().scrape(url, formats=["markdown"], only_main_content=True)
        except Exception as exc:
            return _error(f"Scraping {url}", exc)
        return _add_page(store, added, url, doc, title)

    @tool
    def web_crawl(url: str, limit: int = 3) -> str:
        """Crawl a site starting at url (up to `limit` pages) and add each page as a source."""
        limit = max(1, min(limit, MAX_PAGES_PER_CRAWL))
        try:
            job = _client().crawl(
                url,
                limit=limit,
                scrape_options={"formats": ["markdown"], "only_main_content": True},
                poll_interval=2,
                timeout=120,
            )
        except Exception as exc:
            return _error(f"Crawling {url}", exc)
        messages = []
        for doc in _field(job, "data") or []:
            page_url = _field(_field(doc, "metadata"), "source_url") or url
            messages.append(_add_page(store, added, page_url, doc))
        return "\n".join(messages) or "Crawl returned no pages."

    return [web_search, web_scrape, web_crawl]


def research(topic: str) -> ResearchResult:
    """Run a deep web search on `topic` and index the chosen pages as sources."""
    added: list[Source] = []
    agent = create_agent(
        model=MODEL,
        system_prompt=SYSTEM_PROMPT,
        tools=_make_tools(store, added),
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"Research topic: {topic}"}]},
        config={"recursion_limit": 40},
    )
    return ResearchResult(summary=result["messages"][-1].text, sources=added)


# -- human-in-the-loop: the user picks which pages get scraped ------------------


@dataclass
class Candidate:
    url: str
    title: str


@dataclass
class _Session:
    agent: object
    added: list[Source]
    config: dict
    requests: list[dict] = field(default_factory=list)


_sessions: dict[str, _Session] = {}


def _pending(result) -> list[dict]:
    """The scrape calls waiting for human review (empty when the run finished)."""
    interrupts = getattr(result, "interrupts", None)
    if interrupts is None and isinstance(result, dict):
        interrupts = result.get("__interrupt__")
    requests: list[dict] = []
    for item in interrupts or []:
        requests.extend(item.value.get("action_requests", []))
    return requests


def _final_text(result) -> str:
    state = result if isinstance(result, dict) else getattr(result, "value", {})
    messages = state.get("messages") or []
    return messages[-1].text if messages else ""


def start_review(topic: str) -> tuple[str, list[Candidate]]:
    """Search, then pause so the user can choose pages. Returns (session_id, candidates)."""
    added: list[Source] = []
    tools = [t for t in _make_tools(store, added) if t.name != "web_crawl"]
    agent = create_agent(
        model=MODEL,
        system_prompt=REVIEW_SYSTEM_PROMPT,
        tools=tools,
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={"web_scrape": {"allowed_decisions": ["approve", "reject"]}},
                description_prefix="Page proposed for scraping",
            )
        ],
        checkpointer=InMemorySaver(),
    )
    session_id = uuid.uuid4().hex[:8]
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": 40}
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"Research topic: {topic}"}]},
        config=config,
    )
    requests = _pending(result)
    if not requests:
        return session_id, []
    _sessions[session_id] = _Session(agent, added, config, requests)
    candidates = [
        Candidate(
            url=r["args"].get("url", ""),
            title=r["args"].get("title") or r["args"].get("url", ""),
        )
        for r in requests
    ]
    return session_id, candidates


def finish_review(session_id: str, approved_urls: list[str]) -> ResearchResult:
    """Resume the paused run: scrape the approved pages, reject the rest."""
    session = _sessions.pop(session_id, None)
    if session is None:
        raise KeyError("Unknown or expired review session.")
    approved = set(approved_urls)
    requests = session.requests
    summary = ""
    for round_no in range(3):
        reject_msg = (
            "The user did not select this page. Do not retry it."
            if round_no == 0
            else "The selection is complete. Do not propose more pages; write the final summary."
        )
        decisions = [
            {"type": "approve"}
            if round_no == 0 and r["args"].get("url") in approved
            else {"type": "reject", "message": reject_msg}
            for r in requests
        ]
        result = session.agent.invoke(
            Command(resume={"decisions": decisions}), config=session.config
        )
        requests = _pending(result)
        if not requests:
            summary = _final_text(result)
            break
    return ResearchResult(summary=summary, sources=session.added)
