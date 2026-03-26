"""Persistent memory store backed by YAML-fronted Markdown files."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .models import MemoryEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_md(path: Path) -> Optional[MemoryEntry]:
    """Parse a YAML-fronted .md file into a MemoryEntry."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return None

    match = _FRONT_MATTER_RE.match(text)
    if not match:
        logger.warning("No YAML front-matter in %s", path)
        return None

    try:
        meta: dict = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        logger.warning("Bad YAML in %s: %s", path, exc)
        return None

    # Attach body text as the first transcript highlight if not already present
    body = text[match.end():].strip()
    if body and body not in meta.get("transcript_highlights", []):
        meta.setdefault("transcript_highlights", []).append(body)

    try:
        return MemoryEntry(**meta)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cannot hydrate MemoryEntry from %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------


class MemoryStore:
    """File-backed memory store using YAML-fronted Markdown."""

    def __init__(self, memory_dir: str) -> None:
        self._dir = Path(memory_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        logger.info("MemoryStore initialised at %s", self._dir)

    # -- persistence ---------------------------------------------------------

    def save(self, entry: MemoryEntry) -> str:
        """Persist a MemoryEntry to disk and return its ID."""
        from .generator import MemoryFileGenerator  # late import to avoid circular

        content = MemoryFileGenerator.generate(entry)
        path = self._dir / f"{entry.id}.md"
        path.write_text(content, encoding="utf-8")
        logger.info("Saved memory %s to %s", entry.id, path)
        return entry.id

    def get(self, memory_id: str) -> Optional[MemoryEntry]:
        """Load a single memory by ID."""
        path = self._dir / f"{memory_id}.md"
        if not path.exists():
            logger.warning("Memory %s not found", memory_id)
            return None
        return _parse_md(path)

    def list_all(self) -> List[MemoryEntry]:
        """Return every memory in the store."""
        entries: List[MemoryEntry] = []
        for path in sorted(self._dir.glob("*.md")):
            entry = _parse_md(path)
            if entry is not None:
                entries.append(entry)
        return entries

    def delete(self, memory_id: str) -> bool:
        """Delete a memory file. Returns True if it existed."""
        path = self._dir / f"{memory_id}.md"
        if path.exists():
            path.unlink()
            logger.info("Deleted memory %s", memory_id)
            return True
        logger.warning("Memory %s not found for deletion", memory_id)
        return False

    # -- search --------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        """Search memories by query string using TF-IDF with keyword fallback."""
        from .retriever import TFIDFRetriever  # late import

        all_entries = self.list_all()
        if not all_entries:
            return []
        retriever = TFIDFRetriever(all_entries)
        return retriever.search(query, top_k=top_k)

    def search_by_topic(self, topic: str) -> List[MemoryEntry]:
        """Return memories whose topic matches (case-insensitive substring)."""
        topic_lower = topic.lower()
        return [e for e in self.list_all() if topic_lower in e.topic.lower()]

    # -- configuration -------------------------------------------------------

    def update_memory_dir(self, new_dir: str) -> None:
        """Change the backing directory (does NOT move existing files)."""
        self._dir = Path(new_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        logger.info("Memory directory updated to %s", self._dir)

    # -- stats ---------------------------------------------------------------

    def get_stats(self) -> Dict[str, object]:
        """Return aggregate statistics about stored memories."""
        entries = self.list_all()
        topics: Dict[str, int] = {}
        statuses: Dict[str, int] = {}
        for e in entries:
            topics[e.topic] = topics.get(e.topic, 0) + 1
            statuses[e.status] = statuses.get(e.status, 0) + 1

        return {
            "total": len(entries),
            "memory_dir": str(self._dir),
            "topics": topics,
            "statuses": statuses,
        }
