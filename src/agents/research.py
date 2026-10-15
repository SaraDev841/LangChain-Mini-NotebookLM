"""Research agent (stage 3): searches the web with Firecrawl and indexes pages as sources.

The agent plans several search queries, picks the most credible URLs, scrapes them, and
every scraped page is added to the SourceStore (chunked + embedded), so the chat agent can
answer from it like any uploaded file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from firecrawl import Firecrawl
from langchain.agents import create_agent
from langchain_core.tools import tool

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
    return Firecrawl(api_key=api_key) if api_key else Firecrawl()


def _add_page(store: SourceStore, added: list[Source], url: str, doc) -> str:
    markdown = (_field(doc, "markdown") or "").strip()
    if not markdown:
        return f"No readable content found at {url}."
    title = _field(_field(doc, "metadata"), "title") or url
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
        result = _client().search(query, limit=limit)
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
    def web_scrape(url: str) -> str:
        """Scrape one web page and add its main content to the notebook as a source."""
        doc = _client().scrape(url, formats=["markdown"], only_main_content=True)
        return _add_page(store, added, url, doc)

    @tool
    def web_crawl(url: str, limit: int = 3) -> str:
        """Crawl a site starting at url (up to `limit` pages) and add each page as a source."""
        limit = max(1, min(limit, MAX_PAGES_PER_CRAWL))
        job = _client().crawl(
            url,
            limit=limit,
            scrape_options={"formats": ["markdown"], "only_main_content": True},
            poll_interval=2,
            timeout=120,
        )
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
