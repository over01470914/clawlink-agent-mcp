"""MCP tool definitions for CLAWLINK-AGENT.

Each tool is a plain dict describing name, description, and parameters,
plus an ``execute`` async function.  The list ``TOOLS`` is the public API
consumed by MCP-aware hosts.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from .conflict import ConflictDetector
from .memory_store import MemoryStore
from .models import MemoryEntry
from .replay import ReplayManager
from .triadic import TriadicCache
from . import group_rules

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared state (set by the server / CLI before tools are invoked)
# ---------------------------------------------------------------------------

_store: MemoryStore | None = None
_triadic: TriadicCache | None = None
_replay: ReplayManager | None = None
_conflict: ConflictDetector | None = None

_config: Dict[str, str] = {
    "router_url": "",
    "agent_id": "",
}


def init(
    store: MemoryStore,
    triadic: TriadicCache,
    replay: ReplayManager,
    conflict: ConflictDetector,
    router_url: str = "",
    agent_id: str = "",
) -> None:
    """Inject shared components into the MCP tool layer."""
    global _store, _triadic, _replay, _conflict
    _store = store
    _triadic = triadic
    _replay = replay
    _conflict = conflict
    _config["router_url"] = router_url
    _config["agent_id"] = agent_id


def _require_store() -> MemoryStore:
    if _store is None:
        raise RuntimeError("MCP tools not initialised. Call mcp_tools.init() first.")
    return _store


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def _memory_search(arguments: Dict[str, Any]) -> str:
    """Search memories by query."""
    store = _require_store()
    query: str = arguments.get("query", "")
    top_k: int = int(arguments.get("top_k", 5))
    results = store.search(query, top_k=top_k)
    return json.dumps([r.model_dump() for r in results], indent=2, ensure_ascii=False)


async def _memory_save(arguments: Dict[str, Any]) -> str:
    """Save a memory entry."""
    store = _require_store()
    entry = MemoryEntry(**arguments)
    mid = store.save(entry)
    if _triadic:
        for concept in entry.concepts:
            _triadic.add_from_concept_string(concept, mid)
    return json.dumps({"memory_id": mid, "status": "saved"})


async def _memory_list(arguments: Dict[str, Any]) -> str:
    """List all memories."""
    store = _require_store()
    entries = store.list_all()
    return json.dumps(
        [{"id": e.id, "topic": e.topic, "status": e.status, "score": e.score} for e in entries],
        indent=2,
        ensure_ascii=False,
    )


async def _memory_replay_next(arguments: Dict[str, Any]) -> str:
    """Get the next item from the replay queue."""
    if _replay is None:
        return json.dumps({"error": "Replay manager not initialised"})
    item = _replay.next()
    if item is None:
        return json.dumps({"message": "Replay queue is empty"})
    _replay.record_attempt(item.memory_id)
    return json.dumps(item.model_dump(), indent=2)


async def _memory_conflicts(arguments: Dict[str, Any]) -> str:
    """Detect conflicts among stored memories."""
    store = _require_store()
    detector = _conflict or ConflictDetector()
    entries = store.list_all()
    reports = detector.detect(entries)
    return json.dumps([r.model_dump() for r in reports], indent=2, ensure_ascii=False)


async def _memory_set_dir(arguments: Dict[str, Any]) -> str:
    """Change the memory directory at runtime."""
    store = _require_store()
    new_dir: str = arguments.get("path", "")
    if not new_dir:
        return json.dumps({"error": "No path provided"})
    store.update_memory_dir(new_dir)
    return json.dumps({"status": "updated", "memory_dir": new_dir})


async def _memory_stats(arguments: Dict[str, Any]) -> str:
    """Return memory store statistics."""
    store = _require_store()
    stats = store.get_stats()
    return json.dumps(stats, indent=2, ensure_ascii=False)


async def _group_fetch_messages(arguments: Dict[str, Any]) -> str:
    """Fetch all group chat messages from the Router."""
    router_url: str = arguments.get("router_url", _config.get("router_url", ""))
    session_id: str = arguments.get("session_id", "")
    agent_id: str = arguments.get("agent_id", _config.get("agent_id", ""))
    if not router_url:
        return json.dumps({"error": "No router_url provided"})
    if not session_id:
        return json.dumps({"error": "No session_id provided"})

    messages = await group_rules.fetch_messages(
        router_url=router_url, session_id=session_id, agent_id=agent_id
    )
    return json.dumps({"messages": messages, "count": len(messages)}, indent=2, ensure_ascii=False)


async def _group_check_mentions(arguments: Dict[str, Any]) -> str:
    """Check if the agent is mentioned in a message."""
    content: str = arguments.get("content", "")
    agent_id: str = arguments.get("agent_id", _config.get("agent_id", ""))
    mentions = group_rules.parse_mentions(content)
    mentioned = group_rules.should_respond(content, agent_id) if agent_id else False
    return json.dumps(
        {"mentions": mentions, "should_respond": mentioned, "agent_id": agent_id},
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "clawlink_memory_search",
        "description": "Search agent memories using a natural-language query (TF-IDF + keyword fallback).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "description": "Max results", "default": 5},
            },
            "required": ["query"],
        },
        "execute": _memory_search,
    },
    {
        "name": "clawlink_memory_save",
        "description": "Save a new memory entry with triadic concepts, score, and evidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Memory topic"},
                "mode": {"type": "string", "description": "Interaction mode", "default": "teach"},
                "teacher_id": {"type": "string", "default": ""},
                "student_id": {"type": "string", "default": ""},
                "strictness": {"type": "number", "default": 0.5},
                "rubric": {"type": "string", "default": ""},
                "score": {"type": "number", "default": 0.0},
                "confidence": {"type": "number", "default": 0.0},
                "concepts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Triadic concepts in 'topic; action; evidence' format",
                },
                "transcript_highlights": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "status": {"type": "string", "default": "draft"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "ttl_days": {"type": "integer", "minimum": 1},
            },
            "required": ["topic"],
        },
        "execute": _memory_save,
    },
    {
        "name": "clawlink_memory_list",
        "description": "List all stored memories (id, topic, status, score).",
        "inputSchema": {"type": "object", "properties": {}},
        "execute": _memory_list,
    },
    {
        "name": "clawlink_memory_replay_next",
        "description": "Get the next highest-priority memory from the replay queue.",
        "inputSchema": {"type": "object", "properties": {}},
        "execute": _memory_replay_next,
    },
    {
        "name": "clawlink_memory_conflicts",
        "description": "Detect conflicts among stored memories (score divergence, status contradiction).",
        "inputSchema": {"type": "object", "properties": {}},
        "execute": _memory_conflicts,
    },
    {
        "name": "clawlink_memory_set_dir",
        "description": "Change the memory storage directory at runtime.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "New memory directory path"},
            },
            "required": ["path"],
        },
        "execute": _memory_set_dir,
    },
    {
        "name": "clawlink_memory_stats",
        "description": "Return statistics about stored memories (count, topics, statuses).",
        "inputSchema": {"type": "object", "properties": {}},
        "execute": _memory_stats,
    },
    {
        "name": "clawlink_group_fetch_messages",
        "description": "Fetch all group chat messages from the Router for a given session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "router_url": {"type": "string", "description": "Router base URL"},
                "session_id": {"type": "string", "description": "Chat session ID"},
                "agent_id": {"type": "string", "description": "Agent ID (defaults to self)"},
            },
            "required": ["session_id"],
        },
        "execute": _group_fetch_messages,
    },
    {
        "name": "clawlink_group_check_mentions",
        "description": "Check if this agent is @mentioned in a message and list all mentions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Message text to check"},
                "agent_id": {"type": "string", "description": "Agent ID to check for"},
            },
            "required": ["content"],
        },
        "execute": _group_check_mentions,
    },
]
