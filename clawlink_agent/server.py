"""FastAPI HTTP server for CLAWLINK-AGENT.

Exposes endpoints that the Router calls, plus memory management APIs.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import __version__
from .conflict import ConflictDetector
from .memory_store import MemoryStore
from .models import ConflictReport, MemoryEntry, ReplayItem
from .replay import ReplayManager
from .triadic import TriadicCache
from . import group_rules

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application state (module-level singletons, configured at startup)
# ---------------------------------------------------------------------------

_state: Dict[str, Any] = {
    "agent_id": "agent-default",
    "display_name": "CLAWLINK Agent",
    "memory_dir": "./memories",
    "router_url": "",
    "pairing_code": "",
}

app = FastAPI(title="CLAWLINK-AGENT", version=__version__)

# Lazy-initialised components
_store: Optional[MemoryStore] = None
_triadic: Optional[TriadicCache] = None
_replay: Optional[ReplayManager] = None
_conflict: Optional[ConflictDetector] = None


def _get_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore(_state["memory_dir"])
    return _store


def _get_triadic() -> TriadicCache:
    global _triadic
    if _triadic is None:
        cache_path = os.path.join(_state["memory_dir"], ".triadic_cache.json")
        _triadic = TriadicCache(cache_path)
    return _triadic


def _get_replay() -> ReplayManager:
    global _replay
    if _replay is None:
        queue_path = os.path.join(_state["memory_dir"], ".replay_queue.json")
        _replay = ReplayManager(queue_path)
    return _replay


def _get_conflict() -> ConflictDetector:
    global _conflict
    if _conflict is None:
        _conflict = ConflictDetector()
    return _conflict


def configure(
    agent_id: str,
    display_name: str,
    memory_dir: str,
    router_url: str = "",
) -> None:
    """Configure server state before starting."""
    global _store, _triadic, _replay, _conflict
    _state["agent_id"] = agent_id
    _state["display_name"] = display_name
    _state["memory_dir"] = memory_dir
    _state["router_url"] = router_url
    # Reset lazy singletons so they pick up new paths
    _store = None
    _triadic = None
    _replay = None
    _conflict = None


def generate_pairing_code() -> str:
    """Generate an XXXX-XXXX pairing code."""
    raw = uuid.uuid4().hex[:8].upper()
    code = f"{raw[:4]}-{raw[4:]}"
    _state["pairing_code"] = code
    return code


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class MessageIn(BaseModel):
    sender_id: str = ""
    session_id: str = ""
    content: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class ConfigUpdate(BaseModel):
    memory_dir: Optional[str] = None


class ReplayCompleteRequest(BaseModel):
    memory_id: str


class GroupShouldRespondRequest(BaseModel):
    content: str
    agent_id: Optional[str] = None


class GroupFetchRequest(BaseModel):
    router_url: Optional[str] = None
    session_id: str
    agent_id: Optional[str] = None
    since: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/ping")
async def ping() -> Dict[str, str]:
    """Heartbeat endpoint."""
    return {"status": "ok", "agent_id": _state["agent_id"]}


@app.get("/info")
async def info() -> Dict[str, Any]:
    """Agent information."""
    store = _get_store()
    return {
        "agent_id": _state["agent_id"],
        "display_name": _state["display_name"],
        "memory_dir": _state["memory_dir"],
        "memory_count": len(store.list_all()),
        "version": __version__,
        "pairing_code": _state.get("pairing_code", ""),
    }


@app.post("/message")
async def receive_message(msg: MessageIn) -> Dict[str, Any]:
    """Receive a message from the Router (teaching or group chat delivery)."""
    logger.info("Message from %s: %s", msg.sender_id, msg.content[:120])
    mentioned = group_rules.should_respond(msg.content, _state["agent_id"])
    return {
        "received": True,
        "agent_id": _state["agent_id"],
        "mentioned": mentioned,
        "content_length": len(msg.content),
    }


# -- Memory CRUD -----------------------------------------------------------


@app.post("/memory/search")
async def memory_search(req: SearchRequest) -> List[Dict[str, Any]]:
    """Search memories by query."""
    store = _get_store()
    results = store.search(req.query, top_k=req.top_k)
    return [r.model_dump() for r in results]


@app.post("/memory/save")
async def memory_save(entry: MemoryEntry) -> Dict[str, str]:
    """Save a new or updated memory."""
    store = _get_store()
    triadic = _get_triadic()

    mid = store.save(entry)

    # Index triadic concepts
    for concept in entry.concepts:
        triadic.add_from_concept_string(concept, mid)

    return {"memory_id": mid, "status": "saved"}


@app.get("/memory/list")
async def memory_list() -> List[Dict[str, Any]]:
    """List all memories."""
    store = _get_store()
    return [e.model_dump() for e in store.list_all()]


@app.get("/memory/{memory_id}")
async def memory_get(memory_id: str) -> Dict[str, Any]:
    """Get a single memory by ID."""
    store = _get_store()
    entry = store.get(memory_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found")
    return entry.model_dump()


@app.delete("/memory/{memory_id}")
async def memory_delete(memory_id: str) -> Dict[str, Any]:
    """Delete a memory by ID."""
    store = _get_store()
    triadic = _get_triadic()

    deleted = store.delete(memory_id)
    triadic.remove_by_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found")
    return {"memory_id": memory_id, "status": "deleted"}


# -- Replay ----------------------------------------------------------------


@app.post("/memory/replay/add")
async def replay_add(item: ReplayItem) -> Dict[str, str]:
    """Add an item to the replay queue."""
    replay = _get_replay()
    replay.add(item)
    return {"memory_id": item.memory_id, "status": "queued"}


@app.get("/memory/replay/queue")
async def replay_queue() -> List[Dict[str, Any]]:
    """Return the current replay queue."""
    replay = _get_replay()
    return [i.model_dump() for i in replay.get_queue()]


@app.post("/memory/replay/complete")
async def replay_complete(req: ReplayCompleteRequest) -> Dict[str, Any]:
    """Mark a replay as completed."""
    replay = _get_replay()
    found = replay.complete(req.memory_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"Replay item {req.memory_id} not found")
    return {"memory_id": req.memory_id, "status": "completed"}


# -- Conflicts -------------------------------------------------------------


@app.get("/memory/conflicts")
async def memory_conflicts() -> List[Dict[str, Any]]:
    """Detect and return conflicts among stored memories."""
    store = _get_store()
    detector = _get_conflict()
    entries = store.list_all()
    reports = detector.detect(entries)
    return [r.model_dump() for r in reports]


# -- Config ----------------------------------------------------------------


@app.put("/memory/config")
async def memory_config(cfg: ConfigUpdate) -> Dict[str, str]:
    """Update runtime configuration."""
    if cfg.memory_dir:
        _state["memory_dir"] = cfg.memory_dir
        _get_store().update_memory_dir(cfg.memory_dir)
    return {"status": "updated", "memory_dir": _state["memory_dir"]}


# -- Registration ----------------------------------------------------------


@app.post("/register")
async def register_with_router(body: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Register this agent with the Router.

    The body may contain ``router_url``; otherwise the configured URL is used.
    """
    router_url = (body or {}).get("router_url", _state["router_url"])
    if not router_url:
        raise HTTPException(status_code=400, detail="No router_url configured or provided")

    code = generate_pairing_code()
    payload = {
        "agent_id": _state["agent_id"],
        "display_name": _state["display_name"],
        "version": __version__,
        "pairing_code": code,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{router_url.rstrip('/')}/agents/register", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.RequestError as exc:
        logger.error("Cannot reach Router at %s: %s", router_url, exc)
        # Still return the pairing code even if Router is unreachable
        return {"status": "pending", "pairing_code": code, "error": str(exc)}
    except httpx.HTTPStatusError as exc:
        logger.error("Router returned %s", exc.response.status_code)
        return {
            "status": "error",
            "pairing_code": code,
            "error": f"HTTP {exc.response.status_code}",
        }

    logger.info("Registered with Router. Pairing code: %s", code)
    return {"status": "registered", "pairing_code": code, "router_response": data}


# -- Group chat ------------------------------------------------------------


@app.post("/group/should-respond")
async def group_should_respond(req: GroupShouldRespondRequest) -> Dict[str, Any]:
    """Check if this agent should respond to a message."""
    agent_id = req.agent_id or _state["agent_id"]
    mentioned = group_rules.should_respond(req.content, agent_id)
    mentions = group_rules.parse_mentions(req.content)
    return {
        "should_respond": mentioned,
        "mentions": mentions,
        "agent_id": agent_id,
    }


@app.post("/group/fetch")
async def group_fetch(req: GroupFetchRequest) -> Dict[str, Any]:
    """Fetch group messages from the Router."""
    router_url = req.router_url or _state["router_url"]
    if not router_url:
        raise HTTPException(status_code=400, detail="No router_url configured or provided")

    agent_id = req.agent_id or _state["agent_id"]
    since_dt = None
    if req.since:
        try:
            since_dt = datetime.fromisoformat(req.since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid 'since' datetime: {req.since}")

    messages = await group_rules.fetch_messages(
        router_url=router_url,
        session_id=req.session_id,
        agent_id=agent_id,
        since=since_dt,
    )
    return {"messages": messages, "count": len(messages)}
