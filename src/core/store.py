"""In-memory source store used by the API services layer."""

from __future__ import annotations

from dataclasses import dataclass
import uuid


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

    def list(self) -> list[Source]:
        return list(self._items.values())

    def get(self, source_id: str) -> Source | None:
        return self._items.get(source_id)

    def add(self, name: str, content: str) -> Source:
        source = Source(id=uuid.uuid4().hex[:8], name=name, content=content, active=True)
        self._items[source.id] = source
        return source

    def set_active(self, source_id: str, active: bool) -> Source | None:
        source = self._items.get(source_id)
        if source is None:
            return None
        source.active = active
        return source

    def remove(self, source_id: str) -> bool:
        return self._items.pop(source_id, None) is not None

    def active(self) -> list[Source]:
        return [s for s in self._items.values() if s.active]

    def active_ids(self) -> set[str]:
        return {s.id for s in self._items.values() if s.active}


store = SourceStore()
