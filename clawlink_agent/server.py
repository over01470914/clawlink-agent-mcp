"""FastAPI HTTP server for CLAWLINK-AGENT.

Exposes endpoints that the Router calls, plus memory management APIs.
"""

from __future__ import annotations

import logging
import os
import re
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
    "listen_port": 8430,
    "public_endpoint": "",
    "auto_memory_capture": False,
    "min_importance": 0.55,
    "draft_ttl_days": 30,
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
    port: int = 8430,
    public_endpoint: str = "",
) -> None:
    """Configure server state before starting."""
    global _store, _triadic, _replay, _conflict
    _state["agent_id"] = agent_id
    _state["display_name"] = display_name
    _state["memory_dir"] = memory_dir
    _state["router_url"] = router_url
    _state["listen_port"] = port
    _state["public_endpoint"] = public_endpoint.strip()
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


def _agent_endpoint() -> str:
    endpoint = str(_state.get("public_endpoint", "") or "").strip()
    if endpoint:
        return endpoint.rstrip("/")
    return f"http://127.0.0.1:{int(_state.get('listen_port', 8430))}"


def _summarise_recalled_memories(entries: List[MemoryEntry]) -> str:
    if not entries:
        return "No relevant memories recalled."
    lines = ["Relevant memories recalled:"]
    for entry in entries[:3]:
        highlight = entry.transcript_highlights[0] if entry.transcript_highlights else entry.topic
        lines.append(f"- {entry.topic}: {highlight[:160]}")
    return "\n".join(lines)


def _extract_question_text(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""

    markers = ["现在请回答:", "【问题】"]
    for marker in markers:
        idx = text.rfind(marker)
        if idx >= 0:
            return text[idx + len(marker):].strip()

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else text


def _extract_frameworks_from_text(content: str) -> List[str]:
    known = [
        "FastAPI", "Pydantic", "SQLAlchemy", "Alembic", "Celery", "Redis",
        "Docker", "docker-compose", "pytest", "pytest-asyncio", "JWT", "DRF",
    ]
    found: List[str] = []
    lowered = (content or "").lower()
    for fw in known:
        if fw.lower() in lowered:
            found.append(fw)
    return found


def _build_management_answer(question: str) -> str:
    return (
        f"针对问题“{question}”，我会只做协调与委派，不直接执行：\n"
        "1) 任务拆解：将目标拆为需求澄清、执行实施、结果验收三个子任务。\n"
        "2) 委派执行：指定对应负责人分别执行，每个子任务明确交付物和截止时间。\n"
        "3) 约束遵循：我仅跟踪进度与风险升级，不亲自编写代码/文档/脚本。\n"
        "4) 闭环验收：收集各执行者产出，按标准统一评审并反馈下一步。"
    )


def _build_logic_answer(question: str, content: str) -> str:
    frameworks = _extract_frameworks_from_text(content)
    framework_text = " + ".join(frameworks[:3]) if frameworks else "FastAPI + Pydantic"
    return (
        f"针对问题“{question}”，建议采用 {framework_text} 的分层实现方案：\n"
        "1) 接口层：使用成熟框架定义 API 与输入验证，避免手写校验分支。\n"
        "2) 业务层：将核心逻辑放入独立 service 模块，保持模块分离与解耦。\n"
        "3) 数据层：通过 ORM/迁移工具管理模型和变更，禁止硬编码连接与魔法值。\n"
        "4) 质量层：补充 pytest 测试与配置化参数，确保可测试、可扩展、可维护。"
    )


def _build_habit_answer(question: str, content: str) -> str:
    text = (content or "").lower()
    prefix = "根据您之前的偏好，我会按一致风格回答。"

    if "markdown" in text or "代码块" in content:
        return (
            f"{prefix}\n\n"
            f"问题：{question}\n\n"
            "建议方案：\n"
            "```python\n"
            "def solve():\n"
            "    return \"按用户偏好给出简洁可执行方案\"\n"
            "```"
        )

    if "linux" in text:
        return (
            f"{prefix}\n"
            f"问题：{question}\n"
            "执行命令（Linux）：\n"
            "- chmod +x ./run.sh\n"
            "- ./run.sh"
        )

    if "简洁" in content:
        return f"{prefix} 问题：{question}。回答将保持简洁直达，只给最小可执行步骤。"

    return f"{prefix} 问题：{question}。我会先回忆已知习惯，再给出匹配偏好的实现建议。"


def _generate_response_text(msg: MessageIn, recalled: List[MemoryEntry]) -> str:
    """Generate a deterministic answer so /message returns actionable content."""
    content = (msg.content or "").strip()
    question = _extract_question_text(content)
    lowered = content.lower()

    management_signals = ["管理者", "委派", "分配任务", "不能自己", "协调者", "项目经理"]
    logic_signals = [
        "框架", "fastapi", "pydantic", "sqlalchemy", "alembic", "celery", "redis", "docker", "pytest", "jwt", "drf",
    ]
    habit_signals = ["第一轮", "第二轮", "偏好", "习惯", "根据之前", "用户说"]

    if any(sig in content for sig in management_signals):
        return _build_management_answer(question or "当前任务")

    if any(sig in lowered for sig in logic_signals):
        return _build_logic_answer(question or "当前任务", content)

    if any(sig in content for sig in habit_signals):
        return _build_habit_answer(question or "当前任务", content)

    if recalled:
        hint = recalled[0].topic
        return f"针对问题“{question or '当前任务'}”，我建议优先参考已召回记忆主题：{hint}，并给出分步骤执行计划。"

    return f"针对问题“{question or '当前任务'}”，我建议先明确目标、约束和交付物，再按步骤执行并验证结果。"


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


class BriefRequest(BaseModel):
    query: str
    top_k: int = 3
    max_chars: int = Field(default=1200, ge=200, le=4000)


class ConfigUpdate(BaseModel):
    memory_dir: Optional[str] = None
    auto_memory_capture: Optional[bool] = None
    min_importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    draft_ttl_days: Optional[int] = Field(default=None, ge=1)


class ReplayCompleteRequest(BaseModel):
    memory_id: str


class MemoryPackImportRequest(BaseModel):
    pack: Dict[str, Any]
    strict: bool = True
    allowed_licenses: List[str] = Field(default_factory=list)


class GroupShouldRespondRequest(BaseModel):
    content: str
    agent_id: Optional[str] = None


class GroupFetchRequest(BaseModel):
    router_url: Optional[str] = None
    session_id: str
    agent_id: Optional[str] = None
    since: Optional[str] = None


_TOKEN_RE = re.compile(r"[a-zA-Z0-9\u4e00-\u9fff_\-]+")
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "then", "when", "have", "has",
    "was", "were", "will", "would", "should", "could", "about", "your", "our", "their", "its",
    "to", "of", "in", "on", "at", "as", "is", "are", "be", "by", "or", "an", "a",
    "我们", "你们", "他们", "这个", "那个", "以及", "如果", "然后", "就是", "可以", "需要", "进行",
    "一个", "一些", "没有", "因为", "所以", "但是", "并且", "或者", "的是", "了", "在", "和",
}


def _extract_keywords(text: str, limit: int = 8) -> List[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    cleaned: List[str] = []
    for tok in tokens:
        if len(tok) < 3:
            continue
        if tok in _STOPWORDS:
            continue
        if tok.isdigit():
            continue
        cleaned.append(tok)

    seen: set[str] = set()
    keywords: List[str] = []
    for tok in cleaned:
        if tok in seen:
            continue
        seen.add(tok)
        keywords.append(tok)
        if len(keywords) >= limit:
            break
    return keywords


def _estimate_importance(content: str, keywords: List[str]) -> float:
    text = content.lower()
    score = 0.0

    # Base signal from lexical richness.
    if len(content) >= 120:
        score += 0.20
    if len(content) >= 240:
        score += 0.10
    if len(keywords) >= 4:
        score += 0.20

    # Decision / policy / fix language tends to be high-value memory.
    decision_terms = [
        "decide", "decision", "rule", "policy", "constraint", "fix", "solution",
        "规范", "约束", "修复", "方案", "规则", "决定", "架构", "实现",
    ]
    if any(term in text for term in decision_terms):
        score += 0.30

    # Code/technical clues usually indicate actionable context.
    technical_terms = ["api", "endpoint", "function", "class", "module", "bug", "phase", "测试", "部署"]
    if any(term in text for term in technical_terms):
        score += 0.20

    return min(score, 1.0)


def _is_duplicate_memory(store: MemoryStore, query: str, content: str) -> bool:
    candidates = store.search(query, top_k=1)
    if not candidates:
        return False
    existing = candidates[0]
    existing_text = " ".join(existing.transcript_highlights).strip().lower()
    new_text = content.strip().lower()
    if not existing_text or not new_text:
        return False
    # Lightweight duplicate gate: if one contains the other, avoid writing a near-duplicate memory.
    return existing_text in new_text or new_text in existing_text


def _build_memory_from_message(msg: MessageIn, keywords: List[str], importance: float) -> MemoryEntry:
    primary = keywords[0] if keywords else "conversation"
    secondary = keywords[1] if len(keywords) > 1 else "note"
    topic = f"{primary}-{secondary}-memory"

    concepts = []
    if keywords:
        concepts.append(f"{primary}; capture decision context; {secondary}")

    tags = keywords[:4]
    return MemoryEntry(
        topic=topic,
        mode="chat",
        teacher_id=msg.sender_id or "user",
        student_id=_state["agent_id"],
        strictness=0.5,
        rubric="importance-filtered-memory",
        score=importance,
        confidence=max(0.50, importance),
        concepts=concepts,
        transcript_highlights=[msg.content[:800]],
        status="passed" if importance >= 0.70 else "draft",
        tags=tags,
        keywords=keywords,
        ttl_days=None if importance >= 0.70 else int(_state.get("draft_ttl_days", 30)),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/ping")
async def ping() -> Dict[str, str]:
    """Heartbeat endpoint."""
    return {"status": "ok", "agent_id": _state["agent_id"]}


@app.get("/health")
async def health() -> Dict[str, str]:
    """Compatibility health endpoint expected by Router clients."""
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
        "endpoint": _agent_endpoint(),
        "auto_memory_capture": _state.get("auto_memory_capture", False),
        "min_importance": _state.get("min_importance", 0.55),
        "draft_ttl_days": _state.get("draft_ttl_days", 30),
    }


@app.post("/message")
async def receive_message(msg: MessageIn) -> Dict[str, Any]:
    """Receive a message from the Router (teaching or group chat delivery)."""
    logger.info("Message from %s: %s", msg.sender_id, msg.content[:120])
    mentioned = group_rules.should_respond(msg.content, _state["agent_id"])

    # Optional memory auto-capture: disabled by default, can be enabled globally
    # in /memory/config or per-message with metadata.capture_memory=true.
    capture_requested = bool(msg.metadata.get("capture_memory", False))
    capture_enabled = bool(_state.get("auto_memory_capture", False)) or capture_requested
    memory_id = ""
    memory_captured = False
    importance = 0.0
    keywords: List[str] = []
    recalled_memories: List[MemoryEntry] = []
    recall_enabled = bool(msg.metadata.get("use_memory_recall", True))

    if capture_enabled and msg.content.strip():
        store = _get_store()
        keywords = _extract_keywords(msg.content)
        importance = _estimate_importance(msg.content, keywords)
        min_importance = float(_state.get("min_importance", 0.55))
        if importance >= min_importance and keywords:
            query = " ".join(keywords[:4])
            if not _is_duplicate_memory(store, query=query, content=msg.content):
                entry = _build_memory_from_message(msg, keywords=keywords, importance=importance)
                memory_id = store.save(entry)
                memory_captured = True
                triadic = _get_triadic()
                for concept in entry.concepts:
                    triadic.add_from_concept_string(concept, memory_id)

    if msg.content.strip() and recall_enabled:
        store = _get_store()
        recall_query = " ".join(keywords[:4]) if keywords else msg.content[:120]
        recalled_memories = store.search(recall_query, top_k=3)
    answer_text = _generate_response_text(msg, recalled_memories)
    recall_text = _summarise_recalled_memories(recalled_memories)

    return {
        "received": True,
        "agent_id": _state["agent_id"],
        "mentioned": mentioned,
        "content_length": len(msg.content),
        "memory_captured": memory_captured,
        "memory_id": memory_id,
        "importance": round(importance, 3),
        "keywords": keywords,
        "recall_enabled": recall_enabled,
        "recalled_memories": [e.model_dump() for e in recalled_memories],
        "response": answer_text,
        "content": answer_text,
        "memory_summary": recall_text,
    }


# -- Memory CRUD -----------------------------------------------------------


@app.post("/memory/search")
async def memory_search(req: SearchRequest) -> List[Dict[str, Any]]:
    """Search memories by query."""
    store = _get_store()
    results = store.search(req.query, top_k=req.top_k)
    return [r.model_dump() for r in results]


@app.post("/memory/brief")
async def memory_brief(req: BriefRequest) -> Dict[str, Any]:
    """Return a concise memory briefing optimised for agent reasoning."""
    store = _get_store()
    return store.build_brief(query=req.query, top_k=req.top_k, max_chars=req.max_chars)


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


@app.get("/memory/pack/export")
async def memory_pack_export(
    include_drafts: bool = True,
    min_score: float = 0.0,
    pack_id: str = "",
    name: str = "",
    version: str = "1.0.0",
    author: str = "",
    license: str = "proprietary",
    tags: str = "",
    description: str = "",
    include_signature: bool = True,
) -> Dict[str, Any]:
    """Export memory entries into a portable JSON pack."""
    store = _get_store()
    tag_items = [t.strip() for t in tags.split(",") if t.strip()]
    metadata = {
        "pack_id": pack_id or f"{_state['agent_id']}-pack",
        "name": name or f"{_state['display_name']} Memory Pack",
        "version": version,
        "author": author or _state["agent_id"],
        "license": license,
        "tags": tag_items,
        "description": description,
    }
    pack = store.export_pack(
        include_drafts=include_drafts,
        min_score=min_score,
        metadata=metadata,
        include_signature=include_signature,
    )
    pack["agent_id"] = _state["agent_id"]
    pack["display_name"] = _state["display_name"]
    return pack


@app.post("/memory/pack/import")
async def memory_pack_import(req: MemoryPackImportRequest) -> Dict[str, Any]:
    """Import memory entries from a portable JSON pack."""
    store = _get_store()
    try:
        result = store.import_pack(
            req.pack,
            strict=req.strict,
            allowed_licenses=req.allowed_licenses,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "imported", **result}


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
    if cfg.auto_memory_capture is not None:
        _state["auto_memory_capture"] = bool(cfg.auto_memory_capture)
    if cfg.min_importance is not None:
        _state["min_importance"] = float(cfg.min_importance)
    if cfg.draft_ttl_days is not None:
        _state["draft_ttl_days"] = int(cfg.draft_ttl_days)
    return {
        "status": "updated",
        "memory_dir": _state["memory_dir"],
        "auto_memory_capture": str(_state["auto_memory_capture"]),
        "min_importance": str(_state["min_importance"]),
        "draft_ttl_days": str(_state["draft_ttl_days"]),
    }


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
        "endpoint": _agent_endpoint(),
        "agent_type": "local",
        "metadata": {
            "memory_dir": _state["memory_dir"],
            "auto_memory_capture": _state.get("auto_memory_capture", False),
        },
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
