"""Run the long-horizon app-development scenario against a live agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.memory_test_scenarios import AppDevelopmentScenario


async def _send_message(
    client: httpx.AsyncClient,
    *,
    agent_url: str,
    content: str,
    capture_memory: bool,
) -> Dict[str, Any]:
    payload = {
        "sender_id": "scenario-regression",
        "session_id": "app-scenario-regression",
        "content": content,
        "metadata": {"capture_memory": capture_memory},
    }
    response = await client.post(f"{agent_url}/message", json=payload)
    response.raise_for_status()
    return response.json()


async def run_regression(agent_url: str) -> Dict[str, Any]:
    scenario = AppDevelopmentScenario()
    round_responses = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        await _send_message(
            client,
            agent_url=agent_url,
            content=scenario.initial_requirements["initial_demand"],
            capture_memory=True,
        )

        for round_task in scenario.get_rounds():
            content = round_task.user_request
            if round_task.user_request_emphasis:
                content = f"{content}\n补充要求: {round_task.user_request_emphasis}"

            result = await _send_message(
                client,
                agent_url=agent_url,
                content=content,
                capture_memory=True,
            )
            round_responses.append(
                {
                    "round": round_task.round_num,
                    "title": round_task.title,
                    "response": result.get("response", "") or result.get("content", ""),
                    "memory_brief": result.get("memory_brief", {}),
                }
            )

        final_result = await _send_message(
            client,
            agent_url=agent_url,
            content=scenario.get_memory_test_question(),
            capture_memory=False,
        )

    final_response = final_result.get("response", "") or final_result.get("content", "")
    evaluation = scenario.evaluate_memory_recall(final_response)
    return {
        "agent_url": agent_url,
        "round_responses": round_responses,
        "final_response": final_response,
        "final_memory_brief": final_result.get("memory_brief", {}),
        "evaluation": evaluation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run app-development memory regression")
    parser.add_argument("--agent-url", default="http://127.0.0.1:8430")
    parser.add_argument("--output", help="Optional path to write the JSON result")
    args = parser.parse_args()

    result = asyncio.run(run_regression(args.agent_url.rstrip("/")))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())