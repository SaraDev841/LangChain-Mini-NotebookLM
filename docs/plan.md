

## Plan: Complete NotebookLM project (Stages 1–3 + bonus)

The project is OpenAI chat + Cohere embeddings, built in the assignment's stage order. Stage 1 is written but never verified. The temporary `core/store.py` has no vector search, and `core/sources.py` doesn't exist yet.

**Current state**
- chat.py has `create_agent`, a system prompt, `InMemorySaver` and an `Answer` dataclass, but no tools.
- app.py is the local test runner.
- store.py is a plain dict store with no embeddings.
- `OPENAI_API_KEY` in .env is empty, which is the likely cause of the "Internal Server Error".

**Phase 0 – Verify Stage 1 (blocks everything else)**
1. Put a real `OPENAI_API_KEY` in .env.
2. Run `uv run notebooklm` and confirm it prints a reply from the model.
3. Check that the agent keeps memory: ask something, then ask a follow-up with the same `thread_id`.
4. Run `uv run notebooklm-serve` and send one message in the UI. With no sources the API answers "No active sources", which is expected until Stage 2.

**Phase 1 – Stage 2A: Store and sources** *(depends on 0)*
5. Create src/core/sources.py with `chunk_source(source_id, name, content)`. It uses `RecursiveCharacterTextSplitter` (size 800, overlap 120, `add_start_index=True`) and sets `source` and `source_id` in each chunk's metadata.
6. Add `format_docs(docs)` in the same file. It outputs `[i] (source: name)` followed by the chunk text, with blocks separated by blank lines.
7. Rewrite store.py as the assignment's `SourceStore`:
   - Keep `Source` and the existing methods `list`, `get`, `active_ids`, `set_active`, because services.py already calls them.
   - Add `CohereEmbeddings` (`embed-multilingual-v3.0`, key from `COHERE_API_KEY`) and an `InMemoryVectorStore`.
   - `add` chunks the text, embeds it, stores it, and records the vector ids per source.
   - `remove` deletes the vectors using `pop` (the starter code would raise `KeyError` here).
   - `search` filters to active sources and uses a default `k` of 4. The starter passes `k=None`, which would break.
   - Create the embeddings lazily so .env is loaded before it reads the key.

**Phase 2 – Stage 2B: Tools** *(depends on 1)*
8. In chat.py, add `_make_tools(store)` with three `@tool` functions and docstrings that say when to use each:
   - `search_sources(query)` calls `store.search` and `format_docs`.
   - `list_sources()` returns the available sources.
   - `get_source(source_id)` returns one source's content.
9. Update `SYSTEM_PROMPT` to say when to use each tool, to answer only from sources, and to say so when nothing is found.
10. Build the agent once with `tools=_make_tools(store)`, keeping the single shared checkpointer so memory works. The starter rebuilds the checkpointer on every call, which loses history.
11. Fill `Answer.sources` from the `ToolMessage`s in the result, so the UI citations work (the starter leaves this as a TODO). One approach is to have `search_sources` return its documents as a tool artifact and collect the unique `source` names.
12. Test: upload a source in the UI, ask about it, and check for a grounded answer with citations. Then toggle the source off and confirm it isn't used, and delete it and confirm the vectors are gone.

**Phase 3 – Stage 3: Web sources with Firecrawl** *(depends on 2; you need a Firecrawl account first)*
13. Add the `firecrawl-py` dependency and `FIRECRAWL_API_KEY` to pyproject.toml and .env.example.
14. Create `src/agents/research.py` with three tools: `web_search`, `web_scrape` and `web_crawl`.
15. Give the research agent a prompt that tells it to write several different search queries, pick the best URLs, scrape them, and index the content with `store.add`.
16. Add an API route and schema in app.py, schemas.py and services.py, for example `POST /api/sources/web {query}`. Return the added sources. Schemas should only be extended, not changed.
17. Update the UI in index.html and app.js: add a "Search web" field next to the existing text and upload options, plus a loading state.

**Phase 4 – Bonus: Human-in-the-loop** *(depends on 3, optional)*
18. Wrap the "choose URLs to scrape" step with `HumanInTheLoopMiddleware`. It needs the checkpointer and a `thread_id`.
19. Add API calls to start a search and return the candidate URLs, and to resume with the user's selection.
20. Add a checklist of candidate URLs in the UI. The selected ones are scraped and indexed.

**Phase 5 – Submission**
21. Rewrite README.md. It still references `src/notebooklm/...` paths and a chat.py layout that no longer match the project. It should cover the purpose, setup (`uv sync`, .env, the OpenAI, Cohere and Firecrawl keys), how to run, and the structure.
22. Check that .env is in `.gitignore`. It contains a real Cohere key, so rotate it if it was ever pushed.

**Verification**
1. `uv run notebooklm` returns a model answer.
2. The UI chat answers from an uploaded `.txt` source, and citations show the right source name.
3. Toggling or removing a source changes the search results.
4. Web search adds sources and the chat can answer from them.
5. In the bonus flow, only the URLs you select are indexed.

**Decisions**
- Chat model is OpenAI `gpt-4o`, not the Anthropic model the PDF names.
- Tool names follow the starter code: `search_sources`, `list_sources`, `get_source`.
- Phase 4 (bonus) is included, but it's last and doesn't block Phases 0–3 or 5.
- Out of scope: persistence beyond memory, authentication, and the Studio artifacts (they stay "coming soon").

The plan is saved in session memory. Say if you want changes, or approve it and start with Phase 0.