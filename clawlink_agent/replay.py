"""Replay manager: priority-queue of memories to revisit, JSON-backed."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .models import ReplayItem

logger = logging.getLogger(__name__)


class ReplayManager:
    """Manages a persistent priority queue of replay items.

    Lower ``priority`` numbers are replayed first (1 = highest priority).
    The queue is stored as a JSON array on disk.
    """

    def __init__(self, queue_path: str) -> None:
        self._path = Path(queue_path)
        self._items: List[ReplayItem] = []
        self._load()

    # -- persistence ---------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._items = [ReplayItem(**item) for item in raw]
            logger.info("Loaded %d replay items from %s", len(self._items), self._path)
        except (json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
            logger.warning("Failed to load replay queue: %s", exc)
            self._items = []

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [item.model_dump() for item in self._items]
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # -- public API ----------------------------------------------------------

    def add(self, item: ReplayItem) -> None:
        """Add (or update) a replay item and persist."""
        # Replace existing entry for same memory_id
        self._items = [i for i in self._items if i.memory_id != item.memory_id]
        self._items.append(item)
        self._sort()
        self._flush()
        logger.info("Replay item added/updated for memory %s (priority %d)", item.memory_id, item.priority)

    def next(self) -> Optional[ReplayItem]:
        """Peek at the highest-priority item without removing it."""
        self._sort()
        return self._items[0] if self._items else None

    def complete(self, memory_id: str) -> bool:
        """Mark a replay as completed (removes from queue). Returns True if found."""
        before = len(self._items)
        self._items = [i for i in self._items if i.memory_id != memory_id]
        removed = before - len(self._items)
        if removed:
            self._flush()
            logger.info("Completed replay for memory %s", memory_id)
        return removed > 0

    def record_attempt(self, memory_id: str) -> bool:
        """Increment the attempt counter for a replay item. Returns True if found."""
        for item in self._items:
            if item.memory_id == memory_id:
                item.attempts += 1
                item.last_attempt = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                self._flush()
                return True
        return False

    def get_queue(self) -> List[ReplayItem]:
        """Return the full sorted queue."""
        self._sort()
        return list(self._items)

    def remove(self, memory_id: str) -> bool:
        """Remove a replay item by memory ID. Returns True if found."""
        return self.complete(memory_id)

    def clear(self) -> None:
        """Clear the entire queue."""
        self._items.clear()
        self._flush()

    def __len__(self) -> int:
        return len(self._items)

    # -- internal ------------------------------------------------------------

    def _sort(self) -> None:
        self._items.sort(key=lambda i: (i.priority, i.attempts))
