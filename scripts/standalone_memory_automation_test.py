"""Standalone memory reliability test for CLAWLINK-AGENT.

This script validates that clawlink-agent can be used without a Router
and still provide useful persistent memory across a long multi-phase task.

Run from the clawlink-agent repository root:
    py scripts/standalone_memory_automation_test.py
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from statistics import mean
from typing import Any

from fastapi.testclient import TestClient

from clawlink_agent.server import app, configure


def _save_memory(client: TestClient, payload: dict[str, Any]) -> str:
    response = client.post("/memory/save", json=payload)
    response.raise_for_status()
    body = response.json()
    return body["memory_id"]


def _search(client: TestClient, query: str, top_k: int = 5) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    response = client.post("/memory/search", json={"query": query, "top_k": top_k})
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.raise_for_status()
    return response.json(), elapsed_ms


def _joined_text(entries: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for e in entries:
        parts.append(str(e.get("topic", "")))
        parts.append(str(e.get("rubric", "")))
        parts.extend(str(x) for x in e.get("concepts", []))
        parts.extend(str(x) for x in e.get("transcript_highlights", []))
        parts.extend(str(x) for x in e.get("tags", []))
    return " ".join(parts).lower()


def build_phase_payload(phase: int) -> dict[str, Any]:
    base_constraints = [
        "architecture; enforce layered design; avoid cross module coupling",
        "naming; use snake_case for python symbols; keep consistency",
    ]
    testing_constraints = [
        "testing; add unit tests before refactor; prevent regression",
        "git; use feat slash ticket branch naming; improve traceability",
    ]

    concepts = [
        f"phase_{phase}; implement milestone; complete planned scope",
        f"phase_{phase}; track decision log; keep engineering context",
    ]

    highlights = [
        f"Phase {phase} completed with explicit decision summary.",
    ]

    tags = ["project_x", f"phase{phase}"]

    if phase == 1:
        concepts.extend(base_constraints)
        highlights.append("Established layered architecture and snake_case naming.")
        tags.extend(["architecture", "naming"])

    if phase == 2:
        concepts.extend(testing_constraints)
        highlights.append("Established testing-first refactor rule and branch naming policy.")
        tags.extend(["testing", "git"])

    if phase in {4, 6, 8, 10}:
        # Reinforcement memories to reduce forgetting in long tasks.
        concepts.append("architecture; reinforce layered boundary; preserve initial constraints")
        highlights.append("Reinforced phase1 and phase2 constraints before implementation.")

    return {
        "topic": f"project_x_phase_{phase}_summary",
        "mode": "chat",
        "teacher_id": "user",
        "student_id": "single-agent",
        "strictness": 0.6,
        "rubric": "consistency, correctness, continuity",
        "score": 0.82,
        "confidence": 0.84,
        "concepts": concepts,
        "transcript_highlights": highlights,
        "status": "passed",
        "tags": tags,
    }


def run_test(total_phases: int, recall_threshold: float, latency_threshold_ms: float) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="clawlink_memtest_") as memory_dir:
        configure(
            agent_id="memory-test-agent",
            display_name="Memory Test Agent",
            memory_dir=memory_dir,
            router_url="",
        )

        latency_samples: list[float] = []
        recall_checks = 0
        recall_hits = 0

        checkpoint_queries = [
            (
                "What was decided in phase1 about architecture boundaries?",
                ["layered", "architecture"],
            ),
            (
                "What naming convention was fixed early in the project?",
                ["snake_case", "naming"],
            ),
            (
                "What testing policy was defined in phase2?",
                ["unit tests", "testing"],
            ),
            (
                "What branch naming policy was defined?",
                ["feat", "ticket", "branch"],
            ),
        ]

        top1_ids_by_checkpoint: dict[str, list[str]] = {q: [] for q, _ in checkpoint_queries}

        with TestClient(app) as client:
            for phase in range(1, total_phases + 1):
                payload = build_phase_payload(phase)
                _save_memory(client, payload)

                # Simulate a phase transition recall request.
                entries, elapsed_ms = _search(
                    client,
                    query="phase1 architecture constraints and phase2 testing policy",
                    top_k=5,
                )
                latency_samples.append(elapsed_ms)

                # Evaluate checkpoints on key milestones where forgetting usually appears.
                if phase in {6, 8, 10}:
                    for query, expected_tokens in checkpoint_queries:
                        results, elapsed_ms = _search(client, query=query, top_k=5)
                        latency_samples.append(elapsed_ms)
                        recall_checks += 1
                        text = _joined_text(results)
                        if all(token.lower() in text for token in expected_tokens):
                            recall_hits += 1
                        if results:
                            top1_ids_by_checkpoint[query].append(results[0].get("id", ""))

            list_resp = client.get("/memory/list")
            list_resp.raise_for_status()
            all_memories = list_resp.json()

        files = sorted(Path(memory_dir).glob("*.md"))

    recall_rate = (recall_hits / recall_checks) if recall_checks else 0.0
    avg_latency = mean(latency_samples) if latency_samples else 0.0

    consistency_scores: list[float] = []
    for _query, top_ids in top1_ids_by_checkpoint.items():
        if not top_ids:
            continue
        dominant = max(set(top_ids), key=top_ids.count)
        consistency_scores.append(top_ids.count(dominant) / len(top_ids))
    consistency = mean(consistency_scores) if consistency_scores else 0.0

    passed = (
        len(files) == total_phases
        and len(all_memories) == total_phases
        and recall_rate >= recall_threshold
        and avg_latency <= latency_threshold_ms
        and consistency >= 0.60
    )

    return {
        "passed": passed,
        "total_phases": total_phases,
        "memory_file_count": len(files),
        "memory_api_count": len(all_memories),
        "recall_rate": round(recall_rate, 4),
        "consistency": round(consistency, 4),
        "avg_search_latency_ms": round(avg_latency, 2),
        "thresholds": {
            "recall_rate": recall_threshold,
            "avg_search_latency_ms": latency_threshold_ms,
            "consistency": 0.60,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone memory automation test")
    parser.add_argument("--phases", type=int, default=10, help="Total simulated phases")
    parser.add_argument(
        "--recall-threshold",
        type=float,
        default=0.80,
        help="Minimum acceptable recall hit rate",
    )
    parser.add_argument(
        "--latency-threshold-ms",
        type=float,
        default=500.0,
        help="Maximum acceptable average search latency in milliseconds",
    )
    args = parser.parse_args()

    report = run_test(
        total_phases=args.phases,
        recall_threshold=args.recall_threshold,
        latency_threshold_ms=args.latency_threshold_ms,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
