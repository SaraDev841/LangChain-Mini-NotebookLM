"""Chat agent (stage 1): plain conversation with an OpenAI model + short-term memory."""

from __future__ import annotations

import os
from dataclasses import dataclass

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver


@dataclass
class Answer:
    text: str
    sources: list[str]


MODEL = os.getenv("NOTEBOOKLM_CHAT_MODEL", "openai:gpt-4o")
SYSTEM_PROMPT = "You are the assistant for a notebook of source documents."

# Created once so the conversation history (per thread_id) survives between calls.
_checkpointer = InMemorySaver()
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent(
            model=MODEL,
            system_prompt=SYSTEM_PROMPT,
            checkpointer=_checkpointer,
        )
    return _agent


def answer(question: str, thread_id: str = "default") -> Answer:
    config = {"configurable": {"thread_id": thread_id}}
    result = _get_agent().invoke(
        {"messages": [{"role": "user", "content": question}]}, config=config
    )
    text = result["messages"][-1].text
    return Answer(text=text, sources=[])
