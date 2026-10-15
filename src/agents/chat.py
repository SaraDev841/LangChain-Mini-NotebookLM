"""Chat agent: grounded Q&A over the notebook's active sources (tools + short-term memory)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from core.sources import format_docs
from core.store import SourceStore, store


@dataclass
class Answer:
    text: str
    sources: list[str]


MODEL = os.getenv("NOTEBOOKLM_CHAT_MODEL", "openai:gpt-4o")

SYSTEM_PROMPT = """You are the assistant for a notebook of source documents.

Answer the user's questions using ONLY the notebook's active sources. Tools:
- search_sources(query): semantic search over the active sources. Use it for any question
  about the content of the documents. Rephrase or search several times if needed.
- list_sources(): list the available sources (id and name). Use it when the user asks what
  sources/documents exist, or when you need a source id.
- get_source(source_id): return the full text of one source. Use it when the user asks about
  a whole document (e.g. "summarize intro.md") rather than a specific detail.

If the sources do not contain the answer, say so clearly instead of guessing.
Mention the source names you relied on."""


def _make_tools(store: SourceStore):
    @tool(response_format="content_and_artifact")
    def search_sources(query: str) -> tuple[str, list[str]]:
        """Find passages in the active sources that are relevant to a query."""
        docs = store.search(query=query)
        if not docs:
            return "No relevant documents found in the active sources.", []
        names = list(dict.fromkeys(d.metadata.get("source", "unknown") for d in docs))
        return format_docs(docs), names

    @tool
    def list_sources() -> str:
        """List the available (active) sources with their ids and names."""
        active = store.active()
        if not active:
            return "There are no active sources."
        return "\n".join(f"- id: {s.id} | name: {s.name} | chars: {len(s.content)}" for s in active)

    @tool
    def get_source(source_id: str) -> str:
        """Return the full text of a source, given its id (see list_sources)."""
        source = store.get(source_id)
        if source is None:
            return f"No source found with id '{source_id}'."
        return f"(source: {source.name})\n{source.content}"

    return [search_sources, list_sources, get_source]

# Created once so the conversation history (per thread_id) survives between calls.
_checkpointer = InMemorySaver()
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent(
            model=MODEL,
            system_prompt=SYSTEM_PROMPT,
            tools=_make_tools(store),
            checkpointer=_checkpointer,
        )
    return _agent


def _sources_used(messages: list) -> list[str]:
    """Source names returned by search_sources during the latest turn only."""
    last_human = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=-1)
    names: list[str] = []
    for m in messages[last_human + 1 :]:
        if isinstance(m, ToolMessage) and m.name == "search_sources" and isinstance(m.artifact, list):
            names.extend(m.artifact)
    return list(dict.fromkeys(names))


def answer(question: str, thread_id: str = "default") -> Answer:
    config = {"configurable": {"thread_id": thread_id}}
    result = _get_agent().invoke(
        {"messages": [{"role": "user", "content": question}]}, config=config
    )
    messages = result["messages"]
    return Answer(text=messages[-1].text, sources=_sources_used(messages))
