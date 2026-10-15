# langchain-notebooklm

A NotebookLM-style **grounded research assistant**, built as a project for learning
**LangChain v1**. The code is organized as a finished product, by feature — not by
development stage.


## Stack
- **Chat model:** OpenAI (`openai:gpt-4o` by default, override with `NOTEBOOKLM_CHAT_MODEL`)
- **Embeddings:** Cohere (`embed-multilingual-v3.0` by default)
- **Web sources:** Firecrawl (search / scrape / crawl)
- **Framework:** LangChain v1 (`create_agent`, tools, checkpointer, human-in-the-loop middleware)
- Keys and overrides are set via env vars — see [`.env.example`](.env.example).

## The app

A NotebookLM-style 3-panel workspace, with a real client/server split:

```
┌ Sources ────┬ Chat ───────────────┬ Studio ──────┐
│ add / upload│ grounded answers    │ artifacts    │
│ select      │ with citations      │ + saved notes│
│ view / del  │                     │              │
└─────────────┴─────────────────────┴──────────────┘
```

- **Sources** — add by pasting text, uploading `.md`/`.txt`, or **searching the web**; toggle
  which sources are active (retrieval is scoped to them), view or remove a source.
  Web search can run fully automatically, or pause so **you choose which pages** are scraped
  (human-in-the-loop).
- **Chat** — the main product: a single conversational agent for grounded Q&A with
  citations and short-term memory; save any answer to a note.
- **Studio** — generate artifacts: **Infographic · PowerPoint · Summary · FAQ**
  (each will be its own standalone agent; PowerPoint uses a `.pptx` generation skill).

## Structure

```
client/                 web client — single-page HTML/JS/CSS, no build step
src/
  app.py                local script to try the chat agent without the server
  agents/
    chat.py             chat agent: tools (search/list/get sources) + short-term memory
    research.py         web research agent: Firecrawl tools + human-in-the-loop review
  core/
    sources.py          chunking and formatting of documents
    store.py            SourceStore: sources + in-memory vector store (Cohere embeddings)
  api/                  FastAPI backend: schemas (contract), services, routes
```

The chat is one agent with three tools over the active sources: `search_sources` (semantic
search), `list_sources` and `get_source`. Conversation history is kept per `thread_id` with an
in-memory checkpointer. The Studio artifact generators are not built yet: they return `501`
and the UI shows a "coming soon" notice.

## Quick start

```bash
uv sync
cp .env.example .env         # fill in OPENAI_API_KEY and COHERE_API_KEY (FIRECRAWL_API_KEY optional)
uv run notebooklm-serve      # then open http://127.0.0.1:4040
```

On Windows PowerShell use `Copy-Item .env.example .env`. The port can be changed with
`NOTEBOOKLM_PORT`.

Try the chat agent without the server:

```bash
uv run notebooklm
```

## How to use

1. Click **+ Add** and paste text, upload a file, or search the web for a topic.
2. For web search, keep **Let me choose the pages** ticked to review the proposed pages and
   add only the ones you want, or untick it to let the agent choose.
3. Ask questions in the chat. Answers are grounded in the active sources and cite them.
4. Untick a source to exclude it from answers, or delete it to remove it completely.

## Feature roadmap

| Feature | Status |
|---------|--------|
| Basic chat agent + memory | ✅ done — `agents/chat.py` |
| Retrieval (grounded Q&A, RAG) | ✅ done — `core/store.py`, `core/sources.py` |
| Agent tools | ✅ done — `search_sources`, `list_sources`, `get_source` |
| Web sources (Firecrawl search / scrape / crawl) | ✅ done — `agents/research.py` |
| Human in the loop (choose pages to scrape) | ✅ done — `HumanInTheLoopMiddleware` |
| Structured output (Studio artifacts) | ⏳ planned |
| Event streaming | ⏳ planned |
| Guardrails | ⏳ planned |
| MCP | ⏳ planned |
