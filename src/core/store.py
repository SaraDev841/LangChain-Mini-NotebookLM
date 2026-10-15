"""In-memory source store with semantic (vector) search over the active sources."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from langchain_cohere import CohereEmbeddings
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore

from core.sources import chunk_source

DEFAULT_K = 4


def _make_embeddings() -> CohereEmbeddings:
    # Created lazily so .env has already been loaded when the key is read.
    return CohereEmbeddings(
        cohere_api_key=os.getenv("COHERE_API_KEY"),
        model=os.getenv("NOTEBOOKLM_EMBEDDING_MODEL", "embed-multilingual-v3.0"),
    )


@dataclass(slots=True)
class Source:
    id: str
    name: str
    content: str
    active: bool = True


class SourceStore:
    """Small in-memory store for notebook sources."""

    def __init__(self) -> None:
        self._items: dict[str, Source] = {}
        self._vector_store: InMemoryVectorStore | None = None
        self._vector_ids_by_source: dict[str, list[str]] = {}

    def list(self) -> list[Source]:
        return list(self._items.values())

    def get(self, source_id: str) -> Source | None:
        return self._items.get(source_id)

    def add(self, name: str, content: str) -> Source:
        source = Source(id=uuid.uuid4().hex[:8], name=name, content=content, active=True)
        chunks = chunk_source(source.id, source.name, source.content)
        if self._vector_store is None:
            self._vector_store = InMemoryVectorStore(_make_embeddings())
        self._vector_ids_by_source[source.id] = self._vector_store.add_documents(chunks)
        self._items[source.id] = source
        return source

    def set_active(self, source_id: str, active: bool) -> Source | None:
        source = self._items.get(source_id)
        if source is None:
            return None
        source.active = active
        return source

    def remove(self, source_id: str) -> bool:
        if self._items.pop(source_id, None) is None:
            return False
        ids = self._vector_ids_by_source.pop(source_id, [])
        if ids and self._vector_store is not None:
            self._vector_store.delete(ids=ids)
        return True

    def search(self, query: str, k: int = DEFAULT_K) -> list[Document]:
        """Semantic search restricted to the active sources."""
        active = self.active_ids()
        if not active or self._vector_store is None:
            return []
        return self._vector_store.similarity_search(
            query,
            k=k,
            filter=lambda doc: doc.metadata.get("source_id") in active,
        )

    def active(self) -> list[Source]:
        return [s for s in self._items.values() if s.active]

    def active_ids(self) -> set[str]:
        return {s.id for s in self._items.values() if s.active}


store = SourceStore()
