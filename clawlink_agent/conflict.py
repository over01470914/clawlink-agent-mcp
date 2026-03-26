"""Conflict detection between memories on the same topic."""

from __future__ import annotations

import logging
from typing import List

from .models import ConflictReport, MemoryEntry

logger = logging.getLogger(__name__)


class ConflictDetector:
    """Detects potential conflicts between MemoryEntry objects.

    Two memories conflict when they share the same topic but have
    materially different scores or contradictory concepts.
    """

    SCORE_THRESHOLD: float = 0.3
    """Minimum score difference to flag a conflict."""

    def __init__(self) -> None:
        self._reports: List[ConflictReport] = []

    # -- public API ----------------------------------------------------------

    def detect(self, entries: List[MemoryEntry]) -> List[ConflictReport]:
        """Scan a list of memories and return new conflict reports.

        Conflicts are detected when:
        1. Two memories share the same topic (case-insensitive).
        2. Their scores differ by more than ``SCORE_THRESHOLD``.
        3. OR they have contradictory statuses (one passed, one failed).
        """
        self._reports = []
        by_topic: dict[str, List[MemoryEntry]] = {}
        for entry in entries:
            key = entry.topic.strip().lower()
            by_topic.setdefault(key, []).append(entry)

        for topic_key, group in by_topic.items():
            if len(group) < 2:
                continue
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    reasons: List[str] = []

                    # Score divergence
                    if abs(a.score - b.score) >= self.SCORE_THRESHOLD:
                        reasons.append(
                            f"Score divergence: {a.score:.2f} vs {b.score:.2f}"
                        )

                    # Status contradiction
                    if {a.status, b.status} == {"passed", "failed"}:
                        reasons.append(
                            f"Status contradiction: {a.status} vs {b.status}"
                        )

                    # Concept contradiction (simple: same topic+action, different evidence)
                    a_concepts = self._parse_concepts(a.concepts)
                    b_concepts = self._parse_concepts(b.concepts)
                    for key_pair, a_ev in a_concepts.items():
                        if key_pair in b_concepts and a_ev != b_concepts[key_pair]:
                            reasons.append(
                                f"Concept contradiction on '{key_pair[0]}; {key_pair[1]}': "
                                f"'{a_ev}' vs '{b_concepts[key_pair]}'"
                            )

                    if reasons:
                        report = ConflictReport(
                            memory_a_id=a.id,
                            memory_b_id=b.id,
                            topic=a.topic,
                            description="; ".join(reasons),
                            resolved=False,
                        )
                        self._reports.append(report)
                        logger.info(
                            "Conflict detected: %s <-> %s: %s",
                            a.id,
                            b.id,
                            report.description,
                        )

                        # Cross-link on the entries
                        if b.id not in a.conflicts_with:
                            a.conflicts_with.append(b.id)
                        if a.id not in b.conflicts_with:
                            b.conflicts_with.append(a.id)

        return self._reports

    def get_reports(self) -> List[ConflictReport]:
        """Return the most recently computed conflict reports."""
        return list(self._reports)

    def resolve(self, memory_a_id: str, memory_b_id: str) -> bool:
        """Mark a specific conflict as resolved. Returns True if found."""
        for report in self._reports:
            if (
                report.memory_a_id == memory_a_id
                and report.memory_b_id == memory_b_id
            ) or (
                report.memory_a_id == memory_b_id
                and report.memory_b_id == memory_a_id
            ):
                report.resolved = True
                logger.info("Resolved conflict between %s and %s", memory_a_id, memory_b_id)
                return True
        return False

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _parse_concepts(concepts: List[str]) -> dict[tuple[str, str], str]:
        """Parse triadic concept strings into a dict keyed by (topic, action) -> evidence."""
        result: dict[tuple[str, str], str] = {}
        for c in concepts:
            parts = [p.strip().lower() for p in c.split(";")]
            if len(parts) >= 3:
                result[(parts[0], parts[1])] = parts[2]
        return result
