"""Run an A/B memory-on vs memory-off regression against a live agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.memory_test_scenarios import AppDevelopmentScenario


PROBES: List[Dict[str, Any]] = [
    {
        "id": "final_memory",
        "prompt": AppDevelopmentScenario().get_memory_test_question(),
        "kind": "full",
    },
    {
        "id": "validation_auth",
        "prompt": "请基于当前项目记忆，说明 API 规范、输入验证、认证方案和 token 存储。",
        "kind": "keywords",
        "keywords": ["restful", "pydantic", "jwt", "redis"],
    },
    {
        "id": "async_frontend_migration",
        "prompt": "请基于当前项目记忆，说明异步任务工具、前端 UI 组件策略、数据库迁移工具。",
        "kind": "keywords",
        "keywords": ["celery", "组件库", "alembic"],
    },
]


async def _send_message(
    client: httpx.AsyncClient,
    *,
    agent_url: str,
    content: str,
    capture_memory: bool,
    use_memory_recall: bool,
) -> Dict[str, Any]:
    payload = {
        "sender_id": "ab-regression",
        "session_id": "app-scenario-ab-regression",
        "content": content,
        "metadata": {
            "capture_memory": capture_memory,
            "use_memory_recall": use_memory_recall,
        },
    }
    started = time.perf_counter()
    response = await client.post(f"{agent_url}/message", json=payload)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    response.raise_for_status()
    data = response.json()
    data["latency_ms"] = elapsed_ms
    return data


def _keyword_score(response_text: str, keywords: List[str]) -> Dict[str, Any]:
    lowered = response_text.lower()
    hits = [keyword for keyword in keywords if keyword.lower() in lowered]
    score = round(len(hits) / len(keywords) * 100, 2) if keywords else 0.0
    return {
        "score": score,
        "matched": hits,
        "missing": [keyword for keyword in keywords if keyword not in hits],
        "passed": len(hits) == len(keywords),
    }


def _score_probe(probe: Dict[str, Any], response_text: str, scenario: AppDevelopmentScenario) -> Dict[str, Any]:
    if probe["kind"] == "full":
        return scenario.evaluate_memory_recall(response_text)
    return _keyword_score(response_text, probe["keywords"])


async def run_ab_regression(agent_url: str) -> Dict[str, Any]:
    scenario = AppDevelopmentScenario()

    async with httpx.AsyncClient(timeout=30.0) as client:
        await _send_message(
            client,
            agent_url=agent_url,
            content=scenario.initial_requirements["initial_demand"],
            capture_memory=True,
            use_memory_recall=True,
        )

        for round_task in scenario.get_rounds():
            content = round_task.user_request
            if round_task.user_request_emphasis:
                content = f"{content}\n补充要求: {round_task.user_request_emphasis}"
            await _send_message(
                client,
                agent_url=agent_url,
                content=content,
                capture_memory=True,
                use_memory_recall=True,
            )

        probe_results: List[Dict[str, Any]] = []
        for probe in PROBES:
            with_memory = await _send_message(
                client,
                agent_url=agent_url,
                content=probe["prompt"],
                capture_memory=False,
                use_memory_recall=True,
            )
            without_memory = await _send_message(
                client,
                agent_url=agent_url,
                content=probe["prompt"],
                capture_memory=False,
                use_memory_recall=False,
            )

            with_text = with_memory.get("response", "") or with_memory.get("content", "")
            without_text = without_memory.get("response", "") or without_memory.get("content", "")

            with_score = _score_probe(probe, with_text, scenario)
            without_score = _score_probe(probe, without_text, scenario)

            probe_results.append(
                {
                    "probe_id": probe["id"],
                    "prompt": probe["prompt"],
                    "with_memory": {
                        "latency_ms": with_memory["latency_ms"],
                        "response": with_text,
                        "memory_brief": with_memory.get("memory_brief", {}),
                        "score": with_score,
                    },
                    "without_memory": {
                        "latency_ms": without_memory["latency_ms"],
                        "response": without_text,
                        "memory_brief": without_memory.get("memory_brief", {}),
                        "score": without_score,
                    },
                }
            )

    avg_score_with = round(sum(item["with_memory"]["score"]["score"] for item in probe_results) / len(probe_results), 2)
    avg_score_without = round(sum(item["without_memory"]["score"]["score"] for item in probe_results) / len(probe_results), 2)
    avg_latency_with = round(sum(item["with_memory"]["latency_ms"] for item in probe_results) / len(probe_results), 2)
    avg_latency_without = round(sum(item["without_memory"]["latency_ms"] for item in probe_results) / len(probe_results), 2)

    return {
        "agent_url": agent_url,
        "probe_results": probe_results,
        "summary": {
            "avg_score_with_memory": avg_score_with,
            "avg_score_without_memory": avg_score_without,
            "avg_score_delta": round(avg_score_with - avg_score_without, 2),
            "avg_latency_with_memory_ms": avg_latency_with,
            "avg_latency_without_memory_ms": avg_latency_without,
            "avg_latency_delta_ms": round(avg_latency_with - avg_latency_without, 2),
            "memory_helped_probes": sum(
                1
                for item in probe_results
                if item["with_memory"]["score"]["score"] > item["without_memory"]["score"]["score"]
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run app-development A/B memory regression")
    parser.add_argument("--agent-url", default="http://127.0.0.1:8430")
    parser.add_argument("--output", help="Optional path to write the JSON result")
    args = parser.parse_args()

    result = asyncio.run(run_ab_regression(args.agent_url.rstrip("/")))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())