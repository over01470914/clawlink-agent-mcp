"""Persistent memory store backed by YAML-fronted Markdown files."""

from __future__ import annotations

import json
import logging
import re
import hashlib
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .models import MemoryEntry, MemoryPack, MemoryPackMetadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_TRANSCRIPT_SECTION_RE = re.compile(
    r"^##\s+Transcript Highlights\s*$\n?(.*?)(?=^##\s+|\Z)",
    re.DOTALL | re.MULTILINE,
)


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_dumps(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _clean_brief_text(text: str) -> str:
    cleaned = str(text or "")
    cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.replace("|", " ")
    cleaned = cleaned.replace(">", " ")
    cleaned = re.sub(r"- \*\*[^*]+\*\*:\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _clean_transcript_highlight(text: str) -> str:
    """Normalize stored transcript content and strip generator markdown noise."""
    cleaned_lines: List[str] = []
    for raw_line in str(text or "").splitlines():
        line = re.sub(r"^\s*(>\s*)+", "", raw_line).rstrip()
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        if line.startswith("## "):
            continue
        if line.startswith("|"):
            continue
        if line.startswith("- **"):
            continue
        if line.startswith("---"):
            continue
        cleaned_lines.append(line)

    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()
    while cleaned_lines and cleaned_lines[0] == "":
        cleaned_lines.pop(0)

    return "\n".join(cleaned_lines).strip()


def _extract_transcript_highlights(body: str) -> List[str]:
    """Extract only the Transcript Highlights section instead of ingesting the whole markdown body."""
    match = _TRANSCRIPT_SECTION_RE.search(body or "")
    if not match:
        return []

    section = match.group(1)
    highlights: List[str] = []
    current_lines: List[str] = []

    for line in section.splitlines():
        if re.match(r"^\s*>", line):
            current_lines.append(line)
            continue

        if current_lines:
            cleaned = _clean_transcript_highlight("\n".join(current_lines))
            if cleaned:
                highlights.append(cleaned)
            current_lines = []

    if current_lines:
        cleaned = _clean_transcript_highlight("\n".join(current_lines))
        if cleaned:
            highlights.append(cleaned)

    deduped: List[str] = []
    for item in highlights:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _pack_signature(pack_version: str, metadata: Dict[str, Any], memories: List[Dict[str, Any]]) -> str:
    payload = {
        "pack_version": pack_version,
        "metadata": metadata,
        "memories": memories,
    }
    return hashlib.sha256(_canonical_dumps(payload).encode("utf-8")).hexdigest()


def _normalise_tokens(parts: List[str]) -> set[str]:
    token_re = re.compile(r"[a-zA-Z0-9\u4e00-\u9fff_\-]+")
    tokens: set[str] = set()
    for part in parts:
        for token in token_re.findall(part.lower()):
            if len(token) >= 3:
                tokens.add(token)
    return tokens


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _phase_marker(entry: MemoryEntry) -> Optional[str]:
    combined = " ".join([entry.topic, *entry.tags, *entry.keywords]).lower()
    match = re.search(r"phase[_\-]?(\d+)", combined)
    if match:
        return match.group(1)
    return None


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

    body = text[match.end():].strip()
    parsed_highlights = _extract_transcript_highlights(body)
    if parsed_highlights:
        meta["transcript_highlights"] = parsed_highlights
    else:
        meta.setdefault("transcript_highlights", [])

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
        self._merge_similarity_threshold = 0.55
        self._decay_half_life_days = 45.0
        self._search_cache: Dict[tuple[str, int], List[str]] = {}
        logger.info("MemoryStore initialised at %s", self._dir)

    def _invalidate_cache(self) -> None:
        self._search_cache.clear()

    # -- persistence ---------------------------------------------------------

    def save(self, entry: MemoryEntry) -> str:
        """Persist a MemoryEntry to disk and return its ID."""
        from .generator import MemoryFileGenerator  # late import to avoid circular

        existing = self._find_merge_candidate(entry)
        if existing is not None:
            entry = self._merge_entries(existing, entry)

        content = MemoryFileGenerator.generate(entry)
        path = self._dir / f"{entry.id}.md"
        path.write_text(content, encoding="utf-8")
        self._invalidate_cache()
        logger.info("Saved memory %s to %s", entry.id, path)
        return entry.id

    def get(self, memory_id: str) -> Optional[MemoryEntry]:
        """Load a single memory by ID."""
        path = self._dir / f"{memory_id}.md"
        if not path.exists():
            logger.warning("Memory %s not found", memory_id)
            return None
        entry = _parse_md(path)
        if entry is None:
            return None
        if self._is_expired(entry):
            logger.info("Memory %s expired and will be ignored", memory_id)
            return None
        self._touch(entry)
        return entry

    def list_all(self) -> List[MemoryEntry]:
        """Return every memory in the store."""
        entries: List[MemoryEntry] = []
        for path in sorted(self._dir.glob("*.md")):
            entry = _parse_md(path)
            if entry is not None and not self._is_expired(entry):
                entries.append(entry)
        return entries

    def delete(self, memory_id: str) -> bool:
        """Delete a memory file. Returns True if it existed."""
        path = self._dir / f"{memory_id}.md"
        if path.exists():
            path.unlink()
            self._invalidate_cache()
            logger.info("Deleted memory %s", memory_id)
            return True
        logger.warning("Memory %s not found for deletion", memory_id)
        return False

    # -- search --------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        """Search memories by query string using TF-IDF with keyword fallback."""
        from .retriever import TFIDFRetriever  # late import

        cache_key = (query.strip().lower(), int(top_k))
        cached_ids = self._search_cache.get(cache_key)
        if cached_ids:
            id_map = {entry.id: entry for entry in self.list_all()}
            cached_results = [id_map[mid] for mid in cached_ids if mid in id_map]
            if cached_results:
                for entry in cached_results:
                    self._touch(entry)
                return cached_results[:top_k]

        all_entries = self.list_all()
        if not all_entries:
            return []
        retriever = TFIDFRetriever(all_entries)
        ranked = retriever.search(query, top_k=max(top_k * 3, top_k))
        ranked = sorted(
            ranked,
            key=lambda entry: self._effective_weight(entry),
            reverse=True,
        )
        results = ranked[:top_k]
        self._search_cache[cache_key] = [entry.id for entry in results]
        for entry in results:
            self._touch(entry)
        return results

    def build_brief(self, query: str, top_k: int = 3, max_chars: int = 1200) -> Dict[str, Any]:
        """Return a concise memory briefing optimised for LLM reasoning, not raw storage inspection."""
        results = self.search(query, top_k=top_k)
        items: List[Dict[str, Any]] = []
        lines: List[str] = []

        for entry in results:
            concepts = []
            for concept in entry.concepts[:2]:
                parts = [part.strip() for part in concept.split(";")]
                if len(parts) >= 3:
                    concepts.append({
                        "topic": parts[0],
                        "action": parts[1],
                        "evidence": parts[2],
                    })

            fact_parts: List[str] = []
            for concept in concepts:
                fact_parts.append(f"{concept['topic']} -> {concept['action']} -> {concept['evidence']}")

            if not fact_parts and entry.transcript_highlights:
                fact_parts.append(_clean_brief_text(entry.transcript_highlights[0]))

            highlight = " ; ".join(part for part in fact_parts if part).strip()
            if len(highlight) > 220:
                highlight = highlight[:220].rstrip() + "..."

            items.append({
                "id": entry.id,
                "topic": entry.topic,
                "confidence": entry.confidence,
                "score": entry.score,
                "keywords": entry.keywords[:6],
                "concepts": concepts,
                "facts": fact_parts[:3],
                "highlight": highlight,
            })

            summary_line = f"- {entry.topic} | confidence={entry.confidence:.2f} | {highlight or 'no-highlight'}"
            lines.append(summary_line)

        brief_text = "\n".join(lines)
        if len(brief_text) > max_chars:
            brief_text = brief_text[:max_chars].rstrip() + "..."

        return {
            "query": query,
            "count": len(items),
            "items": items,
            "brief_text": brief_text,
        }

    def search_by_topic(self, topic: str) -> List[MemoryEntry]:
        """Return memories whose topic matches (case-insensitive substring)."""
        topic_lower = topic.lower()
        return [e for e in self.list_all() if topic_lower in e.topic.lower()]

    # -- configuration -------------------------------------------------------

    def update_memory_dir(self, new_dir: str) -> None:
        """Change the backing directory (does NOT move existing files)."""
        self._dir = Path(new_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._invalidate_cache()
        logger.info("Memory directory updated to %s", self._dir)

    def touch(self, memory_id: str) -> bool:
        """Update access metadata for a memory."""
        path = self._dir / f"{memory_id}.md"
        if not path.exists():
            return False
        entry = _parse_md(path)
        if entry is None or self._is_expired(entry):
            return False
        self._touch(entry)
        return entry is not None

    def purge_expired(self) -> int:
        """Delete expired memory files and return count."""
        removed = 0
        for path in sorted(self._dir.glob("*.md")):
            entry = _parse_md(path)
            if entry is None:
                continue
            if self._is_expired(entry):
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    def export_pack(
        self,
        include_drafts: bool = True,
        min_score: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
        include_signature: bool = True,
    ) -> Dict[str, object]:
        """Export memories into a portable JSON-compatible pack payload."""
        memories: List[Dict[str, object]] = []
        for entry in self.list_all():
            if not include_drafts and entry.status == "draft":
                continue
            if entry.score < min_score:
                continue
            memories.append(entry.model_dump())

        default_meta = {
            "pack_id": f"pack-{_now_utc().strftime('%Y%m%d%H%M%S')}",
            "name": "CLAWLINK Memory Pack",
            "version": "1.0.0",
            "author": "unknown",
            "license": "proprietary",
            "tags": ["memory"],
        }
        merged_meta = {**default_meta, **(metadata or {})}
        meta = MemoryPackMetadata(**merged_meta).model_dump()
        signature = _pack_signature("1.0", meta, memories) if include_signature else ""
        pack = MemoryPack(
            pack_version="1.0",
            exported_at=_now_utc().isoformat(timespec="seconds").replace("+00:00", "Z"),
            memory_count=len(memories),
            metadata=MemoryPackMetadata(**meta),
            memories=[MemoryEntry(**m) for m in memories],
            signature=signature,
        )
        return pack.model_dump()

    def import_pack(
        self,
        payload: Dict[str, object],
        strict: bool = True,
        allowed_licenses: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Import a portable memory pack payload."""
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")

        validation_errors: List[str] = []
        pack_version = str(payload.get("pack_version", ""))
        if pack_version != "1.0":
            validation_errors.append("unsupported pack_version; expected '1.0'")

        metadata = payload.get("metadata")
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        if not metadata_dict:
            validation_errors.append("missing metadata object")
        else:
            required_meta = ["pack_id", "name", "version", "author", "license", "created_at"]
            for key in required_meta:
                if not str(metadata_dict.get(key, "")).strip():
                    validation_errors.append(f"metadata.{key} is required")

        if allowed_licenses and metadata_dict:
            license_name = str(metadata_dict.get("license", "")).strip()
            if license_name and license_name not in set(allowed_licenses):
                validation_errors.append(f"license '{license_name}' is not in allowed_licenses")

        raw_memories = payload.get("memories", [])
        if not isinstance(raw_memories, list):
            raise ValueError("payload.memories must be a list")

        signature = str(payload.get("signature", "") or "").strip()
        if metadata_dict and signature:
            expected = _pack_signature(pack_version or "1.0", metadata_dict, raw_memories)
            if signature != expected:
                validation_errors.append("pack signature verification failed")
        elif strict:
            validation_errors.append("missing signature in strict mode")

        if strict and validation_errors:
            raise ValueError("; ".join(validation_errors))

        imported = 0
        failed = 0
        merged = 0
        for item in raw_memories:
            try:
                if isinstance(item, str):
                    item = json.loads(item)
                if not isinstance(item, dict):
                    failed += 1
                    continue

                before_ids = {e.id for e in self.list_all()}
                entry = MemoryEntry(**item)
                saved_id = self.save(entry)
                after_ids = {e.id for e in self.list_all()}

                imported += 1
                if saved_id in before_ids or len(after_ids) == len(before_ids):
                    merged += 1
            except Exception:  # noqa: BLE001
                failed += 1

        return {
            "imported": imported,
            "failed": failed,
            "merged_or_updated": merged,
            "strict": strict,
            "validation_errors": validation_errors,
        }

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

    # -- merge / lifecycle --------------------------------------------------

    def _find_merge_candidate(self, entry: MemoryEntry) -> Optional[MemoryEntry]:
        new_tokens = _normalise_tokens(
            [entry.topic, " ".join(entry.tags), " ".join(entry.keywords), " ".join(entry.concepts)]
        )
        best_match: Optional[MemoryEntry] = None
        best_score = 0.0
        for existing in self.list_all():
            phase_a = _phase_marker(existing)
            phase_b = _phase_marker(entry)
            if phase_a and phase_b and phase_a != phase_b:
                continue

            existing_tokens = _normalise_tokens(
                [
                    existing.topic,
                    " ".join(existing.tags),
                    " ".join(existing.keywords),
                    " ".join(existing.concepts),
                ]
            )
            token_similarity = _jaccard(new_tokens, existing_tokens)
            topic_similarity = SequenceMatcher(None, existing.topic.lower(), entry.topic.lower()).ratio()
            shared_markers = len(set(existing.tags + existing.keywords) & set(entry.tags + entry.keywords))

            similarity = max(token_similarity, topic_similarity)
            if shared_markers > 0:
                similarity += 0.10

            if similarity > best_score:
                best_score = similarity
                best_match = existing
        if best_match is not None and best_score >= self._merge_similarity_threshold:
            return best_match
        return None

    def _merge_entries(self, existing: MemoryEntry, new_entry: MemoryEntry) -> MemoryEntry:
        merged_ids = list(dict.fromkeys([*existing.merged_from, new_entry.id]))
        merged_tags = list(dict.fromkeys([*existing.tags, *new_entry.tags]))
        merged_keywords = list(dict.fromkeys([*existing.keywords, *new_entry.keywords]))
        merged_concepts = list(dict.fromkeys([*existing.concepts, *new_entry.concepts]))
        merged_highlights = list(
            dict.fromkeys([*existing.transcript_highlights, *new_entry.transcript_highlights])
        )[-8:]
        merged_conflicts = list(dict.fromkeys([*existing.conflicts_with, *new_entry.conflicts_with]))

        existing.score = max(existing.score, new_entry.score)
        existing.confidence = min(1.0, (existing.confidence * 0.7) + (new_entry.confidence * 0.3))
        existing.tags = merged_tags
        existing.keywords = merged_keywords
        existing.concepts = merged_concepts
        existing.transcript_highlights = merged_highlights
        existing.conflicts_with = merged_conflicts
        existing.merged_from = merged_ids
        existing.last_accessed = new_entry.last_accessed
        existing.status = "passed" if existing.confidence >= 0.70 else existing.status
        if existing.ttl_days is None:
            existing.ttl_days = new_entry.ttl_days
        elif new_entry.ttl_days is not None:
            existing.ttl_days = max(existing.ttl_days, new_entry.ttl_days)
        return existing

    def _is_expired(self, entry: MemoryEntry) -> bool:
        if entry.ttl_days is None:
            return False
        created = _parse_iso(entry.timestamp)
        expires_at = created + timedelta(days=entry.ttl_days)
        return _now_utc() >= expires_at.astimezone(timezone.utc)

    def _effective_weight(self, entry: MemoryEntry) -> float:
        age_days = max((_now_utc() - _parse_iso(entry.timestamp)).total_seconds() / 86400.0, 0.0)
        decay = 0.5 ** (age_days / self._decay_half_life_days) if self._decay_half_life_days > 0 else 1.0
        access_bonus = min(entry.access_count, 10) * 0.03
        return (entry.confidence * decay) + access_bonus

    def _touch(self, entry: MemoryEntry) -> None:
        entry.access_count += 1
        entry.last_accessed = _now_utc().isoformat(timespec="seconds").replace("+00:00", "Z")
        from .generator import MemoryFileGenerator  # late import to avoid circular

        path = self._dir / f"{entry.id}.md"
        path.write_text(MemoryFileGenerator.generate(entry), encoding="utf-8")
