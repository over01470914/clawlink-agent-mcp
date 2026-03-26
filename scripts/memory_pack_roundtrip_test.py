"""Round-trip test for memory pack export/import.

Run:
    py scripts/memory_pack_roundtrip_test.py
"""

from __future__ import annotations

import json
import tempfile
from copy import deepcopy

from fastapi.testclient import TestClient

from clawlink_agent.server import app, configure


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="clawlink_pack_src_") as src_dir:
        configure(
            agent_id="pack-export-agent",
            display_name="Pack Export Agent",
            memory_dir=src_dir,
            router_url="",
        )

        with TestClient(app) as client:
            memory_a = {
                "id": "pack-mem-1",
                "topic": "python-retry-policy-memory",
                "mode": "chat",
                "score": 0.88,
                "confidence": 0.86,
                "concepts": ["python; define retry policy; avoid silent failures"],
                "transcript_highlights": ["Use exponential backoff for transient HTTP failures."],
                "status": "passed",
                "tags": ["python", "retry"],
                "keywords": ["python", "retry", "backoff"],
            }
            memory_b = {
                "id": "pack-mem-2",
                "topic": "temporary-brainstorm-note",
                "mode": "chat",
                "score": 0.35,
                "confidence": 0.45,
                "concepts": ["draft-note; retain temporary idea; naming exploration"],
                "transcript_highlights": ["Explore alternate naming for onboarding flow."],
                "status": "draft",
                "tags": ["draft"],
                "keywords": ["brainstorm"],
                "ttl_days": 30,
            }

            for payload in (memory_a, memory_b):
                save_resp = client.post("/memory/save", json=payload)
                save_resp.raise_for_status()

            export_resp = client.get("/memory/pack/export", params={"include_drafts": True, "min_score": 0.0})
            export_resp.raise_for_status()
            exported_pack = export_resp.json()

            tampered_pack = deepcopy(exported_pack)
            tampered_pack["memories"][0]["topic"] = "tampered-topic-without-signature-update"

    with tempfile.TemporaryDirectory(prefix="clawlink_pack_dst_") as dst_dir:
        configure(
            agent_id="pack-import-agent",
            display_name="Pack Import Agent",
            memory_dir=dst_dir,
            router_url="",
        )

        with TestClient(app) as client:
            import_resp = client.post("/memory/pack/import", json={"pack": exported_pack})
            import_resp.raise_for_status()
            import_result = import_resp.json()

            strict_fail_resp = client.post(
                "/memory/pack/import",
                json={"pack": tampered_pack, "strict": True},
            )

            list_resp = client.get("/memory/list")
            list_resp.raise_for_status()
            imported_memories = list_resp.json()

            non_strict_resp = client.post(
                "/memory/pack/import",
                json={"pack": tampered_pack, "strict": False},
            )
            non_strict_resp.raise_for_status()
            non_strict_result = non_strict_resp.json()

    imported_ids = sorted([m["id"] for m in imported_memories])
    report = {
        "export_count": exported_pack.get("memory_count", 0),
        "imported": import_result.get("imported", 0),
        "failed": import_result.get("failed", 0),
        "imported_ids": imported_ids,
        "metadata_keys": sorted(list(exported_pack.get("metadata", {}).keys())),
        "signature_present": bool(exported_pack.get("signature")),
        "strict_tamper_rejected": strict_fail_resp.status_code == 400,
        "non_strict_tamper_imported": non_strict_result.get("imported", 0) >= 1,
        "non_strict_has_validation_errors": bool(non_strict_result.get("validation_errors", [])),
    }
    report["passed"] = (
        report["export_count"] == 2
        and report["imported"] == 2
        and report["failed"] == 0
        and imported_ids == ["pack-mem-1", "pack-mem-2"]
        and report["signature_present"]
        and report["strict_tamper_rejected"]
        and report["non_strict_tamper_imported"]
        and report["non_strict_has_validation_errors"]
    )

    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
