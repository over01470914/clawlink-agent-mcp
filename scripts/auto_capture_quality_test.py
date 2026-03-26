"""Quality test for automatic memory capture in /message endpoint.

Run:
    py scripts/auto_capture_quality_test.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from clawlink_agent.server import app, configure


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="clawlink_autocap_") as memory_dir:
        configure(
            agent_id="autocap-agent",
            display_name="Auto Capture Test Agent",
            memory_dir=memory_dir,
            router_url="",
        )

        with TestClient(app) as client:
            # Enable auto-capture with a moderate threshold.
            cfg = client.put(
                "/memory/config",
                json={"auto_memory_capture": True, "min_importance": 0.55},
            )
            cfg.raise_for_status()

            # High-value messages should be captured.
            high_value = [
                "Phase1 decision: enforce layered architecture and avoid cross module coupling for API and service boundaries.",
                "Fix policy: before refactor we must add unit tests and keep snake_case naming for Python functions.",
                "Deployment rule: for phase6 we standardize release checklist and bug rollback workflow.",
            ]

            # Low-value chatter should be filtered out.
            low_value = [
                "ok",
                "thanks",
                "done",
                "hello there",
                "nice",
            ]

            captured_count = 0
            for text in high_value:
                resp = client.post(
                    "/message",
                    json={"sender_id": "user", "session_id": "s1", "content": text, "metadata": {}},
                )
                resp.raise_for_status()
                body = resp.json()
                if body.get("memory_captured"):
                    captured_count += 1

            filtered_count = 0
            for text in low_value:
                resp = client.post(
                    "/message",
                    json={"sender_id": "user", "session_id": "s1", "content": text, "metadata": {}},
                )
                resp.raise_for_status()
                body = resp.json()
                if not body.get("memory_captured"):
                    filtered_count += 1

            memories_resp = client.get("/memory/list")
            memories_resp.raise_for_status()
            memories = memories_resp.json()

        files = list(Path(memory_dir).glob("*.md"))

    report = {
        "captured_high_value": captured_count,
        "total_high_value": len(high_value),
        "filtered_low_value": filtered_count,
        "total_low_value": len(low_value),
        "memory_api_count": len(memories),
        "memory_file_count": len(files),
    }

    report["passed"] = (
        captured_count >= 2
        and filtered_count >= 4
        and len(memories) == len(files)
    )

    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
