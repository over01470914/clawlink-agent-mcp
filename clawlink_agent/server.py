"""FastAPI HTTP server for CLAWLINK-AGENT.

Exposes endpoints that the Router calls, plus memory management APIs.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
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
    "openclaw_enabled": True,
    "openclaw_required": True,
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


def _normalise_fact_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n\"'，。:：")


def _append_fact(facts: Dict[str, List[str]], key: str, value: str) -> None:
    cleaned = _normalise_fact_value(value)
    if not cleaned:
        return
    bucket = facts.setdefault(key, [])
    if cleaned not in bucket:
        bucket.append(cleaned)


def _merge_facts(*fact_sets: Dict[str, List[str]]) -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = {}
    for fact_set in fact_sets:
        for key, values in fact_set.items():
            bucket = merged.setdefault(key, [])
            for value in values:
                cleaned = _normalise_fact_value(value)
                if cleaned and cleaned not in bucket:
                    bucket.append(cleaned)
    return merged


def _has_new_fact_values(base: Dict[str, List[str]], candidate: Dict[str, List[str]]) -> bool:
    for key, values in candidate.items():
        existing = set(base.get(key, []))
        for value in values:
            if value not in existing:
                return True
    return False


def _collect_pattern_facts(text: str, facts: Dict[str, List[str]]) -> None:
    lowered = text.lower()
    fact_patterns = {
        "backend": [("fastapi", "FastAPI"), ("django", "Django"), ("flask", "Flask")],
        "frontend": [("react", "React"), ("vue", "Vue"), ("next.js", "Next.js"), ("nextjs", "Next.js")],
        "database": [("postgresql", "PostgreSQL"), ("postgres", "PostgreSQL"), ("mysql", "MySQL"), ("mongodb", "MongoDB")],
        "orm": [("sqlalchemy", "SQLAlchemy"), ("typeorm", "TypeORM"), ("orm", "ORM")],
        "api_style": [("restful", "RESTful"), ("rest api", "RESTful")],
        "validation": [("pydantic", "Pydantic")],
        "auth": [("jwt", "JWT")],
        "auth_storage": [("redis", "Redis")],
        "async_jobs": [("celery", "Celery")],
        "frontend_ui": [("dnd-kit", "dnd-kit"), ("component library", "component library"), ("组件库", "组件库")],
        "migration": [("alembic", "Alembic")],
    }
    for key, patterns in fact_patterns.items():
        for needle, value in patterns:
            if needle in lowered:
                _append_fact(facts, key, value)

    principle_markers = {
        "architecture": [
            ("解耦", "模块解耦"),
            ("模块之间要解耦", "模块解耦"),
            ("清晰", "架构清晰"),
            ("维护", "易维护"),
            ("decoupled", "模块解耦"),
            ("clear architecture", "架构清晰"),
            ("maintainable", "易维护"),
        ],
        "configuration": [
            ("环境变量", "环境变量配置"),
            ("配置文件", "配置文件管理"),
            ("不要硬编码", "避免硬编码"),
            ("environment variable", "环境变量配置"),
            ("config file", "配置文件管理"),
            ("hardcode", "避免硬编码"),
        ],
        "testing": [
            ("单元测试", "单元测试"),
            ("可测试", "可测试设计"),
            ("测试覆盖", "测试覆盖"),
            ("unit test", "单元测试"),
            ("testable", "可测试设计"),
            ("tested", "测试覆盖"),
        ],
    }
    for key, patterns in principle_markers.items():
        for needle, value in patterns:
            if needle in text:
                _append_fact(facts, key, value)


def _extract_message_facts(
    content: str,
    keywords: List[str],
    *,
    allow_project_name_fallback: bool = True,
) -> Dict[str, List[str]]:
    facts: Dict[str, List[str]] = {}

    project_match = re.search(
        r"(?:项目名|项目叫|叫|名称是|project name is|project name|called)\s*[:：]?\s*([A-Za-z][A-Za-z0-9_\- ]{1,40})",
        content,
        re.IGNORECASE,
    )
    if project_match:
        _append_fact(facts, "project_name", project_match.group(1))

    quoted_name_match = re.search(r"App叫([A-Za-z][A-Za-z0-9_\- ]{1,40})", content, re.IGNORECASE)
    if quoted_name_match:
        _append_fact(facts, "project_name", quoted_name_match.group(1))

    app_name_match = re.search(r"\bapp\s+([A-Za-z][A-Za-z0-9_\-]{2,40})\b", content, re.IGNORECASE)
    if app_name_match:
        _append_fact(facts, "project_name", app_name_match.group(1))

    _collect_pattern_facts(content, facts)

    project_name_context = (
        "项目" in content
        or "名字" in content
        or "名称" in content
        or "project" in content.lower()
        or "app" in content.lower()
    )
    if allow_project_name_fallback and project_name_context and not facts.get("project_name"):
        for keyword in keywords:
            if keyword in {
                "app", "api", "orm", "react", "fastapi", "postgresql", "sqlalchemy",
                "called", "building", "build", "must", "use", "backend", "frontend", "todo",
                "restful", "jwt", "redis", "celery", "alembic", "pydantic", "schema",
            }:
                continue
            if re.fullmatch(r"[a-z][a-z0-9_\-]{2,40}", keyword):
                _append_fact(facts, "project_name", keyword)
                break

    if not facts and keywords:
        for keyword in keywords[:4]:
            _append_fact(facts, "keywords", keyword)
    return facts


def _compact_facts(facts: Dict[str, List[str]]) -> Dict[str, List[str]]:
    compact: Dict[str, List[str]] = {}
    for key, values in facts.items():
        unique_values: List[str] = []
        for value in values:
            cleaned = _normalise_fact_value(value)
            if cleaned and cleaned not in unique_values:
                unique_values.append(cleaned)
        if unique_values:
            compact[key] = unique_values[:6]
    return compact


def _format_fact_lines(facts: Dict[str, List[str]]) -> List[str]:
    labels = {
        "project_name": "项目名",
        "backend": "后端",
        "frontend": "前端",
        "database": "数据库",
        "orm": "ORM",
        "api_style": "API 规范",
        "validation": "输入验证",
        "auth": "认证",
        "auth_storage": "认证存储",
        "async_jobs": "异步任务",
        "frontend_ui": "前端 UI",
        "migration": "数据库迁移",
        "architecture": "架构原则",
        "configuration": "配置原则",
        "testing": "测试要求",
    }
    lines: List[str] = []
    for key in [
        "project_name", "backend", "frontend", "database", "orm", "api_style", "validation",
        "auth", "auth_storage", "async_jobs", "frontend_ui", "migration",
        "architecture", "configuration", "testing",
    ]:
        values = facts.get(key)
        if values:
            lines.append(f"- {labels.get(key, key)}: {', '.join(values[:4])}")
    return lines


def _build_brief_from_entries(query: str, entries: List[MemoryEntry]) -> Dict[str, Any]:
    facts: Dict[str, List[str]] = {}
    highlights: List[str] = []
    topics: List[str] = []
    for entry in entries:
        topics.append(entry.topic)
        for key, values in entry.facts.items():
            bucket = facts.setdefault(key, [])
            for value in values:
                if value not in bucket:
                    bucket.append(value)
        for highlight in entry.transcript_highlights:
            cleaned = re.sub(r"\s+", " ", highlight).strip()
            if cleaned and cleaned not in highlights:
                highlights.append(cleaned[:220])
            if len(highlights) >= 3:
                break

    lines: List[str] = []
    if facts:
        lines.append("Recalled facts:")
        for key, values in facts.items():
            lines.append(f"- {key}: {', '.join(values[:4])}")
    elif topics:
        lines.append("Recalled topics:")
        for topic in topics[:3]:
            lines.append(f"- {topic}")

    return {
        "query": query,
        "count": len(entries),
        "topics": topics,
        "facts": facts,
        "highlights": highlights,
        "brief_text": "\n".join(lines) if lines else "No relevant memories recalled.",
    }


def _extract_question_text(content: str) -> str:
    marker = "现在请回答:"
    if marker in content:
        return content.split(marker, 1)[1].strip()
    return content.strip()


def _build_task_guidance(question: str, facts: Dict[str, List[str]]) -> List[str]:
    guidance: List[str] = []
    lowered = question.lower()
    if ("认证" in question or "auth" in lowered) and facts.get("auth"):
        auth_parts = facts.get("auth", []) + facts.get("auth_storage", [])
        guidance.append(f"认证链路沿用 {', '.join(auth_parts[:3])}，避免自实现状态管理。")
    if ("api" in lowered or "接口" in question) and (facts.get("api_style") or facts.get("validation")):
        parts = facts.get("api_style", []) + facts.get("validation", [])
        if not facts.get("validation") and "fastapi" in " ".join(facts.get("backend", [])).lower():
            parts.append("Pydantic")
        guidance.append(f"接口层保持 {', '.join(parts[:3])}，把校验放在 schema 层。")
    elif ("api" in lowered or "接口" in question) and ("fastapi" in lowered or "fastapi" in " ".join(facts.get("backend", [])).lower()):
        guidance.append("接口层保持 RESTful，并使用 Pydantic schema 承担输入校验。")
    if ("前端" in question or "界面" in question or "ui" in lowered) and (facts.get("frontend") or facts.get("frontend_ui")):
        parts = facts.get("frontend", []) + facts.get("frontend_ui", [])
        guidance.append(f"前端实现沿用 {', '.join(parts[:3])}，不要回退到手写散乱样式。")
    if ("异步" in question or "提醒" in question or "任务" in question) and facts.get("async_jobs"):
        guidance.append(f"后台任务继续使用 {', '.join(facts['async_jobs'][:2])}。")
    elif ("提醒" in question or "异步" in question or "定时" in question):
        guidance.append("这类后台提醒任务建议放到 Celery，避免把调度逻辑塞进同步请求链路。")
    if ("迁移" in question or "索引" in question or "数据库" in question) and facts.get("migration"):
        guidance.append(f"数据库变更通过 {', '.join(facts['migration'][:2])} 管理，不直接改库。")
    if not guidance:
        stack_parts: List[str] = []
        for key in ["backend", "frontend", "database", "orm"]:
            stack_parts.extend(facts.get(key, []))
        if stack_parts:
            guidance.append(f"实现时保持既有技术主线: {', '.join(stack_parts[:4])}。")
    return guidance


def _generate_teaching_response(content: str, brief: Dict[str, Any]) -> str:
    """Generate a student response to teaching content.

    Echo/summarise the received teaching content and include any recalled
    memories so the response demonstrates that the student captured and
    understood the material.
    """
    lines: List[str] = []

    # Summarise the teaching content that was just received
    snippet = content.strip()
    if len(snippet) > 300:
        snippet = snippet[:300] + "…"
    lines.append(f"收到教學內容: {snippet}")

    # Include recalled memory highlights to show understanding
    highlights = brief.get("highlights", [])
    if highlights:
        lines.append("已回憶起相關記憶:")
        for h in highlights[:5]:
            lines.append(f"- {h}")

    # Echo key facts if available
    facts = brief.get("facts", {})
    if facts:
        lines.append("已記錄的關鍵事實:")
        for key, values in list(facts.items())[:5]:
            lines.append(f"- {key}: {', '.join(str(v) for v in values[:3])}")

    if not highlights and not facts:
        lines.append("已將此內容存入記憶。")

    return "\n".join(lines)


def _filter_brief_for_prompt(content: str, brief: Dict[str, Any]) -> Dict[str, Any]:
    query_keywords = set(_extract_keywords(content, limit=12))
    if not query_keywords:
        return brief

    def _is_related(text: str) -> bool:
        return bool(query_keywords.intersection(_extract_keywords(text, limit=12)))

    highlights = [str(h) for h in (brief.get("highlights") or []) if _is_related(str(h))]
    facts: Dict[str, List[str]] = {}
    for key, values in (brief.get("facts") or {}).items():
        key_text = str(key)
        value_list = [str(v) for v in (values or [])]
        kept_values = [v for v in value_list if _is_related(f"{key_text} {v}")]
        if kept_values:
            facts[key_text] = kept_values

    if not highlights and not facts:
        return brief

    filtered = dict(brief)
    filtered["highlights"] = highlights[:5]
    filtered["facts"] = facts
    filtered["count"] = len(highlights)
    return filtered


def _build_openclaw_prompt(content: str, brief: Dict[str, Any], *, teaching_mode: bool) -> str:
    lines: List[str] = []
    lowered = (content or "").lower()
    concept_transfer_mode = teaching_mode or any(
        marker in lowered
        for marker in ["教学", "教學", "teach", "challenge", "quiz", "暗號", "暗号", "secret code"]
    )

    if concept_transfer_mode:
        lines.append("你现在只做一件事：围绕当前概念进行教学或复述，确保回答紧扣主题。")
        lines.append("禁止讨论你的身份、背景真实性、是否在扮演角色，也不要输出拒绝扮演类声明。")
        lines.append("若信息不足，只允许提出一个与当前概念直接相关的澄清问题。")
    else:
        lines.append("请基于用户问题与已召回记忆，给出聚焦、可执行、不跑题的回答。")

    lines.append("输出要求：")
    lines.append("1) 先给结论，再给2-5条关键点。")
    lines.append("2) 仅使用与当前问题直接相关的信息。")
    lines.append("3) 不要引入无关话题，不要扩展到其他历史任务。")
    lines.append(f"原始消息:\n{content}")

    highlights = brief.get("highlights", []) or []
    facts = brief.get("facts", {}) or {}
    if highlights:
        lines.append("召回记忆片段:")
        for item in highlights[:5]:
            lines.append(f"- {item}")
    if facts:
        lines.append("召回事实:")
        for key, values in list(facts.items())[:8]:
            values_text = ", ".join(str(v) for v in values[:4])
            lines.append(f"- {key}: {values_text}")

    lines.append("请仅输出最终答案正文，不要输出分析过程。")
    return "\n".join(lines)


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    text = (raw_text or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no_json_object")
    return json.loads(text[start:end + 1])


def _generate_openclaw_response(content: str, brief: Dict[str, Any], *, session_id: str, teaching_mode: bool) -> tuple[str, Dict[str, Any]]:
    prompt = _build_openclaw_prompt(content, brief, teaching_mode=teaching_mode)
    session_key = session_id.strip() or f"clawlink-{_state['agent_id']}-{uuid.uuid4().hex[:8]}"
    timeout_seconds = int(os.getenv("CLAWLINK_OPENCLAW_TIMEOUT", "90"))
    command = [
        "openclaw",
        "agent",
        "--local",
        "--session-id",
        session_key,
        "--json",
        "--timeout",
        str(timeout_seconds),
        "-m",
        prompt,
    ]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds + 10,
        check=False,
    )

    if proc.returncode != 0:
        raise RuntimeError(f"openclaw_exit_{proc.returncode}: {(proc.stderr or proc.stdout).strip()[:500]}")

    payload_obj: Dict[str, Any] | None = None
    for stream_text in (proc.stdout, proc.stderr):
        if not stream_text:
            continue
        try:
            payload_obj = _extract_json_object(stream_text)
            if isinstance(payload_obj, dict) and isinstance(payload_obj.get("payloads"), list):
                break
        except Exception:
            continue

    if not payload_obj or not payload_obj.get("payloads"):
        raise RuntimeError("openclaw_invalid_json_payload")

    payloads = payload_obj.get("payloads", [])
    response_text = ""
    for item in payloads:
        text = (item or {}).get("text")
        if text:
            response_text = str(text).strip()
            if response_text:
                break

    if not response_text:
        raise RuntimeError("openclaw_empty_response")

    meta = payload_obj.get("meta", {}) if isinstance(payload_obj, dict) else {}
    return response_text, meta


def _generate_response_text(content: str, facts: Dict[str, List[str]], brief_text: str) -> str:
    question = _extract_question_text(content)
    if not facts:
        return brief_text or f"针对问题“{question or '当前任务'}”，建议先明确目标、约束和交付物，再按步骤执行并验证结果。"

    lowered = question.lower()
    lines: List[str] = []

    if any(marker in question for marker in ["最终内存测试", "请回答以下问题", "最初的架构要求", "符合最初"]) or any(
        marker in lowered for marker in ["what is the project name", "tech stack", "restful", "pydantic"]
    ):
        lines.append("基于已召回记忆，当前项目约束如下:")
        lines.extend(_format_fact_lines(facts))
        return "\n".join(lines)

    lines.append("基于已召回记忆，当前任务建议如下:")
    lines.extend(_build_task_guidance(question, facts))

    supporting_lines = _format_fact_lines(facts)
    if supporting_lines:
        lines.append("关键约束:")
        lines.extend(supporting_lines[:6])
    return "\n".join(lines)


def _build_response_memory(
    *,
    original_msg: MessageIn,
    response_text: str,
    response_facts: Dict[str, List[str]],
) -> MemoryEntry:
    response_keywords = _extract_keywords(response_text)
    merged_keywords = list(dict.fromkeys([*_extract_keywords(original_msg.content), *response_keywords]))[:8]
    synthetic = MessageIn(
        sender_id=_state["agent_id"],
        session_id=original_msg.session_id,
        content=f"问题: {_extract_question_text(original_msg.content)}\n回答决策: {response_text}",
        metadata={"capture_memory": True},
    )
    importance = max(0.7, _estimate_importance(synthetic.content, merged_keywords, response_facts))
    return _build_memory_from_message(
        synthetic,
        keywords=merged_keywords,
        importance=importance,
        facts=response_facts,
    )


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


def _estimate_importance(content: str, keywords: List[str], facts: Optional[Dict[str, List[str]]] = None) -> float:
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
    technical_terms = [
        "api", "endpoint", "function", "class", "module", "bug", "phase", "测试", "部署",
        "jwt", "redis", "celery", "alembic", "pydantic", "fastapi", "react", "postgresql",
    ]
    if any(term in text for term in technical_terms):
        score += 0.20

    if facts:
        score += min(len(facts), 4) * 0.08
        critical_keys = {"auth", "auth_storage", "async_jobs", "migration", "validation", "frontend_ui"}
        if critical_keys & set(facts):
            score += 0.15

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


def _build_memory_from_message(
    msg: MessageIn,
    keywords: List[str],
    importance: float,
    facts: Optional[Dict[str, List[str]]] = None,
) -> MemoryEntry:
    facts = facts or _extract_message_facts(msg.content, keywords)
    primary = keywords[0] if keywords else "conversation"
    secondary = keywords[1] if len(keywords) > 1 else "note"
    project_name = facts.get("project_name", [""])[0] if facts.get("project_name") else ""
    topic = f"project-{project_name}-memory" if project_name else f"{primary}-{secondary}-memory"

    concepts = []
    if keywords:
        concepts.append(f"{primary}; capture decision context; {secondary}")

    tags = list(dict.fromkeys([*keywords[:4], *(value for values in facts.values() for value in values)]))[:8]
    return MemoryEntry(
        topic=topic,
        mode="chat",
        teacher_id=msg.sender_id or "user",
        student_id=_state["agent_id"],
        strictness=0.5,
        rubric="importance-filtered-memory",
        score=importance,
        confidence=max(0.50, importance),
        access_count=0,
        version=1,
        concepts=concepts,
        transcript_highlights=[msg.content[:800]],
        status="passed" if importance >= 0.70 else "draft",
        tags=tags,
        keywords=keywords,
        facts=_compact_facts(facts),
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

    # Determine if this is a teaching-loop message (always capture)
    meta_msg_type = str(msg.metadata.get("message_type", "")).lower()
    meta_role = str(msg.metadata.get("role", "")).lower()
    is_teaching_content = meta_msg_type in ("teaching", "challenge") and meta_role == "student"

    # Memory capture: always for teaching content, otherwise respect config
    capture_requested = bool(msg.metadata.get("capture_memory", False))
    capture_enabled = is_teaching_content or bool(_state.get("auto_memory_capture", False)) or capture_requested
    memory_id = ""
    memory_captured = False
    importance = 0.0
    keywords: List[str] = []
    message_facts: Dict[str, List[str]] = {}
    recalled_memories: List[MemoryEntry] = []
    brief: Dict[str, Any] = {"query": "", "count": 0, "topics": [], "facts": {}, "highlights": [], "brief_text": "No relevant memories recalled."}
    recall_enabled = bool(msg.metadata.get("use_memory_recall", True))

    if msg.content.strip():
        keywords = _extract_keywords(msg.content)
        message_facts = _extract_message_facts(msg.content, keywords)

    if capture_enabled and msg.content.strip():
        store = _get_store()
        importance = _estimate_importance(msg.content, keywords, message_facts)
        # For teaching content, lower the threshold to ensure capture
        min_importance = 0.0 if is_teaching_content else float(_state.get("min_importance", 0.55))
        if importance >= min_importance and keywords:
            query = " ".join(keywords[:4])
            if not _is_duplicate_memory(store, query=query, content=msg.content):
                entry = _build_memory_from_message(
                    msg,
                    keywords=keywords,
                    importance=max(importance, 0.7) if is_teaching_content else importance,
                    facts=message_facts,
                )
                memory_id = store.save(entry)
                memory_captured = True
                triadic = _get_triadic()
                for concept in entry.concepts:
                    triadic.add_from_concept_string(concept, memory_id)

    if recall_enabled and msg.content.strip():
        store = _get_store()
        query_candidates: List[str] = []
        if keywords:
            query_candidates.append(" ".join(keywords[:4]))
            if len(keywords) > 4:
                query_candidates.append(" ".join(keywords[:8]))
        query_candidates.append(msg.content[:240])
        query_candidates = [candidate for index, candidate in enumerate(query_candidates) if candidate and candidate not in query_candidates[:index]]

        seen_ids: set[str] = set()
        for candidate in query_candidates:
            for entry in store.search(candidate, top_k=5):
                if entry.id in seen_ids:
                    continue
                seen_ids.add(entry.id)
                recalled_memories.append(entry)
                if len(recalled_memories) >= 5:
                    break
            if len(recalled_memories) >= 5:
                break

        recall_query = query_candidates[0] if query_candidates else msg.content[:120]
        brief = _build_brief_from_entries(recall_query, recalled_memories)

    response_source = "template"
    response_text = ""
    openclaw_meta: Dict[str, Any] = {}
    openclaw_error = ""

    use_openclaw = bool(msg.metadata.get("use_openclaw", _state.get("openclaw_enabled", True)))
    require_openclaw = bool(msg.metadata.get("require_openclaw", _state.get("openclaw_required", True)))

    if use_openclaw:
        try:
            brief_for_prompt = _filter_brief_for_prompt(msg.content, brief)
            response_text, openclaw_meta = _generate_openclaw_response(
                msg.content,
                brief_for_prompt,
                session_id=msg.session_id,
                teaching_mode=is_teaching_content,
            )
            response_source = "openclaw"
        except Exception as exc:
            openclaw_error = str(exc)
            logger.error("OpenClaw response failed: %s", openclaw_error)
            if require_openclaw:
                raise HTTPException(status_code=500, detail=f"openclaw_failed: {openclaw_error}")

    if response_source != "openclaw":
        # Fallback path (disabled when require_openclaw=True)
        if is_teaching_content:
            response_text = _generate_teaching_response(msg.content, brief)
        else:
            response_text = _generate_response_text(msg.content, brief.get("facts", {}), brief.get("brief_text", ""))

    response_facts = _extract_message_facts(
        response_text,
        _extract_keywords(response_text),
        allow_project_name_fallback=False,
    ) if response_text else {}

    if capture_enabled and response_text and response_facts:
        known_facts = _merge_facts(message_facts, brief.get("facts", {}))
        if _has_new_fact_values(known_facts, response_facts):
            store = _get_store()
            response_entry = _build_response_memory(
                original_msg=msg,
                response_text=response_text,
                response_facts=response_facts,
            )
            if not _is_duplicate_memory(store, query=" ".join(response_entry.keywords[:4]), content=response_entry.transcript_highlights[0]):
                response_memory_id = store.save(response_entry)
                triadic = _get_triadic()
                for concept in response_entry.concepts:
                    triadic.add_from_concept_string(concept, response_memory_id)

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
        "memory_summary": _summarise_recalled_memories(recalled_memories),
        "memory_brief": brief,
        "response": response_text,
        "content": response_text,
        "response_source": response_source,
        "openclaw_meta": openclaw_meta,
        "openclaw_error": openclaw_error,
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
    """Return a concise recall packet for reasoning."""
    store = _get_store()
    return store.build_brief(req.query, top_k=req.top_k)


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
