"""Data models for CLAWLINK-AGENT memory system."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


def _new_id() -> str:
    """Generate a new unique memory ID."""
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class EvidenceRef(BaseModel):
    """Reference to an evidence source."""

    source: str = Field(..., description="Evidence source path or URI")
    vec_id: Optional[str] = Field(None, description="Optional vector-store ID")


class MemoryEntry(BaseModel):
    """A single memory record with triadic structure."""

    id: str = Field(default_factory=_new_id, description="Unique memory ID")
    timestamp: str = Field(default_factory=_now_iso, description="ISO-8601 creation time")
    last_accessed: str = Field(default_factory=_now_iso, description="Last access time")
    access_count: int = Field(0, ge=0, description="Number of successful recalls")
    topic: str = Field(..., description="Memory topic")
    mode: str = Field("teach", description="Interaction mode (teach, review, quiz, chat)")
    teacher_id: str = Field("", description="ID of the teaching agent")
    student_id: str = Field("", description="ID of the learning agent")
    strictness: float = Field(0.5, ge=0.0, le=1.0, description="Grading strictness 0-1")
    rubric: str = Field("", description="Evaluation rubric text")
    score: float = Field(0.0, ge=0.0, le=1.0, description="Score 0-1")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Confidence 0-1")
    evidence_refs: List[EvidenceRef] = Field(default_factory=list, description="Evidence references")
    concepts: List[str] = Field(
        default_factory=list,
        description='Triadic concepts in "topic; action; evidence" format',
    )
    transcript_highlights: List[str] = Field(
        default_factory=list, description="Key transcript excerpts"
    )
    status: str = Field(
        "draft",
        description="Memory status: passed, failed, conflict, draft, archived",
    )
    version: int = Field(1, ge=1, description="Version number")
    tags: List[str] = Field(default_factory=list, description="Free-form tags")
    keywords: List[str] = Field(
        default_factory=list,
        description="Normalized keywords used for retrieval and trigger matching",
    )
    ttl_days: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional time-to-live in days for low-value memories",
    )
    merged_from: List[str] = Field(
        default_factory=list,
        description="IDs of memory entries merged into this record",
    )
    conflicts_with: List[str] = Field(
        default_factory=list, description="IDs of conflicting memories"
    )


class ReplayItem(BaseModel):
    """An item in the replay queue."""

    memory_id: str = Field(..., description="ID of the memory to replay")
    priority: int = Field(1, ge=1, description="Priority (1=highest)")
    reason: str = Field("", description="Reason for replay")
    attempts: int = Field(0, ge=0, description="Number of replay attempts so far")
    last_attempt: Optional[str] = Field(None, description="ISO-8601 timestamp of last attempt")


class TriadicEntry(BaseModel):
    """A single triadic cache entry: topic -> action -> evidence."""

    topic: str = Field(..., description="Topic noun/phrase")
    action: str = Field(..., description="Action verb/phrase")
    evidence: str = Field(..., description="Evidence / supporting detail")
    memory_id: str = Field(..., description="Owning memory ID")


class ConflictReport(BaseModel):
    """Report of a detected conflict between two memories."""

    memory_a_id: str = Field(..., description="First memory ID")
    memory_b_id: str = Field(..., description="Second memory ID")
    topic: str = Field(..., description="Topic where the conflict was detected")
    description: str = Field("", description="Human-readable description of the conflict")
    resolved: bool = Field(False, description="Whether the conflict has been resolved")


class GroupChatRule(BaseModel):
    """Rules governing group-chat behaviour for an agent."""

    agent_id: str = Field(..., description="Agent identifier")
    mention_prefix: str = Field("@", description="Prefix used for mentions")
    auto_fetch_interval: int = Field(
        0,
        ge=0,
        description="Auto-fetch interval in seconds (0 = disabled)",
    )
