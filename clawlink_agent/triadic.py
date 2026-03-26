"""Triadic cache: topic -> action -> evidence, backed by a JSON file."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .models import TriadicEntry

logger = logging.getLogger(__name__)


class TriadicCache:
    """In-memory + JSON-persisted triadic concept cache.

    Structure on disk (JSON):
    [
      {"topic": "...", "action": "...", "evidence": "...", "memory_id": "..."},
      ...
    ]
    """

    def __init__(self, cache_path: str) -> None:
        self._path = Path(cache_path)
        self._entries: List[TriadicEntry] = []
        self._load()

    # -- persistence ---------------------------------------------------------

    def _load(self) -> None:
        """Load cache from disk if the file exists."""
        if not self._path.exists():
            logger.debug("No triadic cache file at %s; starting empty", self._path)
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._entries = [TriadicEntry(**item) for item in raw]
            logger.info("Loaded %d triadic entries from %s", len(self._entries), self._path)
        except (json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
            logger.warning("Failed to load triadic cache: %s", exc)
            self._entries = []

    def _flush(self) -> None:
        """Write current entries to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [e.model_dump() for e in self._entries]
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # -- public API ----------------------------------------------------------

    def add(self, entry: TriadicEntry) -> None:
        """Add a triadic entry and persist."""
        self._entries.append(entry)
        self._flush()
        logger.debug("Added triadic entry: %s; %s; %s", entry.topic, entry.action, entry.evidence)

    def add_from_concept_string(self, concept: str, memory_id: str) -> None:
        """Parse a 'topic; action; evidence' string and add it.

        Args:
            concept: Semicolon-separated triadic concept.
            memory_id: Owning memory ID.
        """
        parts = [p.strip() for p in concept.split(";")]
        if len(parts) < 3:
            logger.warning("Malformed concept string (need 3 parts): %r", concept)
            return
        self.add(
            TriadicEntry(
                topic=parts[0],
                action=parts[1],
                evidence=parts[2],
                memory_id=memory_id,
            )
        )

    def search_by_topic(self, topic: str) -> List[TriadicEntry]:
        """Return entries whose topic matches (case-insensitive substring)."""
        t = topic.lower()
        return [e for e in self._entries if t in e.topic.lower()]

    def search_by_memory(self, memory_id: str) -> List[TriadicEntry]:
        """Return all entries belonging to a given memory."""
        return [e for e in self._entries if e.memory_id == memory_id]

    def get_all(self) -> List[TriadicEntry]:
        """Return all cached entries."""
        return list(self._entries)

    def remove_by_memory(self, memory_id: str) -> int:
        """Remove all entries for a memory and return the count removed."""
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.memory_id != memory_id]
        removed = before - len(self._entries)
        if removed:
            self._flush()
        return removed

    def clear(self) -> None:
        """Remove all entries."""
        self._entries.clear()
        self._flush()

    def __len__(self) -> int:
        return len(self._entries)
