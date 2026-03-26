"""Regression test for memory merge and TTL/decay behavior.

Run:
    py scripts/memory_merge_decay_test.py
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from clawlink_agent.server import app, configure


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="clawlink_merge_decay_") as memory_dir:
        configure(
            agent_id="merge-decay-agent",
            display_name="Merge Decay Test Agent",
            memory_dir=memory_dir,
            router_url="",
        )

        with TestClient(app) as client:
            first = {
                "id": "mem-alpha",
                "topic": "architecture-boundaries-memory",
                "timestamp": _iso_days_ago(20),
                "last_accessed": _iso_days_ago(20),
                "mode": "chat",
                "score": 0.72,
                "confidence": 0.74,
                "concepts": ["architecture; enforce layered design; avoid cross module coupling"],
                "transcript_highlights": ["Initial decision about architecture boundaries."],
                "status": "passed",
                "tags": ["architecture", "layered"],
                "keywords": ["architecture", "boundaries", "layered"],
            }
            second = {
                "id": "mem-beta",
                "topic": "architecture-boundary-rule",
                "timestamp": _iso_days_ago(2),
                "last_accessed": _iso_days_ago(2),
                "mode": "chat",
                "score": 0.90,
                "confidence": 0.92,
                "concepts": ["architecture; preserve service boundary; reduce coupling"],
                "transcript_highlights": ["Reinforced architecture boundary rule."],
                "status": "passed",
                "tags": ["architecture", "service"],
                "keywords": ["architecture", "boundary", "coupling"],
            }
            expired = {
                "id": "mem-expired",
                "topic": "temporary-draft-memory",
                "timestamp": _iso_days_ago(40),
                "last_accessed": _iso_days_ago(40),
                "mode": "chat",
                "score": 0.55,
                "confidence": 0.56,
                "concepts": ["temporary; keep draft note; cleanup later"],
                "transcript_highlights": ["Short-lived draft memory."],
                "status": "draft",
                "tags": ["draft"],
                "keywords": ["temporary", "draft"],
                "ttl_days": 7,
            }

            for payload in (first, second, expired):
                resp = client.post("/memory/save", json=payload)
                resp.raise_for_status()

            list_resp = client.get("/memory/list")
            list_resp.raise_for_status()
            memories = list_resp.json()

            search_resp = client.post(
                "/memory/search",
                json={"query": "architecture layered boundary coupling", "top_k": 5},
            )
            search_resp.raise_for_status()
            results = search_resp.json()

        files = sorted(Path(memory_dir).glob("*.md"))

    memory_ids = [m["id"] for m in memories]
    result_ids = [r["id"] for r in results]
    merged_entry = next((m for m in memories if m["id"] == "mem-alpha"), None)

    report = {
        "memory_api_count": len(memories),
        "memory_file_count": len(files),
        "memory_ids": memory_ids,
        "search_result_ids": result_ids,
        "merged_from": merged_entry.get("merged_from", []) if merged_entry else [],
        "expired_hidden": "mem-expired" not in memory_ids,
        "merge_happened": "mem-alpha" in memory_ids and "mem-beta" not in memory_ids,
        "ranked_merged_first": bool(result_ids and result_ids[0] == "mem-alpha"),
    }
    report["passed"] = (
        report["expired_hidden"]
        and report["merge_happened"]
        and report["ranked_merged_first"]
        and len(memories) == 1
        and len(files) == 2
    )

    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
