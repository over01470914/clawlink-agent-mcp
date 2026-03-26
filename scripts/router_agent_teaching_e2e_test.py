"""End-to-end Router -> Agent teaching loop test.

This script starts one Router and two Agent runtimes, registers the agents,
creates a SOLO session, runs the teaching loop, and validates memory writeback.

Run:
    py scripts/router_agent_teaching_e2e_test.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_ok(url: str, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            code, _ = _http_request_json("GET", url, timeout=2.0)
            if code == 200:
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.4)
    return False


def _http_request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int, Any]:
    body: bytes | None = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(url=url, data=body, method=method.upper(), headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {raw[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


def _start_router(router_dir: Path, port: int) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["CLAWLINK_ROUTER_HOST"] = "127.0.0.1"
    env["CLAWLINK_ROUTER_PORT"] = str(port)
    return subprocess.Popen(
        ["py", "run.py"],
        cwd=str(router_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _start_agent(
    agent_dir: Path,
    *,
    port: int,
    agent_id: str,
    display_name: str,
    memory_dir: Path,
    router_url: str,
) -> subprocess.Popen[str]:
    cmd = [
        "py",
        "-m",
        "clawlink_agent.cli",
        "serve",
        "--port",
        str(port),
        "--agent-id",
        agent_id,
        "--display-name",
        display_name,
        "--memory-dir",
        str(memory_dir),
        "--router-url",
        router_url,
        "--public-endpoint",
        f"http://127.0.0.1:{port}",
    ]
    return subprocess.Popen(
        cmd,
        cwd=str(agent_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _stop_processes(processes: list[subprocess.Popen[str]]) -> None:
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    deadline = time.time() + 8
    for proc in processes:
        if proc.poll() is not None:
            continue
        while time.time() < deadline and proc.poll() is None:
            time.sleep(0.2)
        if proc.poll() is None:
            proc.kill()


def _register_agent(agent_url: str, router_url: str) -> dict[str, Any]:
    _, data = _http_request_json("POST", f"{agent_url}/register", {"router_url": router_url}, timeout=10.0)
    return data


def _set_auto_capture(agent_url: str) -> None:
    _http_request_json(
        "PUT",
        f"{agent_url}/memory/config",
        {"auto_memory_capture": True, "min_importance": 0.0, "draft_ttl_days": 30},
        timeout=10.0,
    )


def _wait_for_agents(router_url: str, expected: list[str], timeout: float = 25.0) -> list[dict[str, Any]]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        _, agents = _http_request_json("GET", f"{router_url}/agents", timeout=4.0)
        ids = {a.get("agent_id") for a in agents}
        if all(e in ids for e in expected):
            return agents
        time.sleep(0.4)
    return []


def _run() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    agent_dir = root / "clawlink-agent"
    router_dir = root / "clawlink-router"

    router_port = _free_port()
    agent_a_port = _free_port()
    agent_b_port = _free_port()

    router_url = f"http://127.0.0.1:{router_port}"
    agent_a_url = f"http://127.0.0.1:{agent_a_port}"
    agent_b_url = f"http://127.0.0.1:{agent_b_port}"

    report: dict[str, Any] = {
        "router_url": router_url,
        "agents": [
            {"agent_id": "agent-teacher", "endpoint": agent_a_url},
            {"agent_id": "agent-student", "endpoint": agent_b_url},
        ],
    }

    processes: list[subprocess.Popen[str]] = []
    started_at = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory(prefix="clawlink_e2e_router_agent_") as tmp:
            tmp_dir = Path(tmp)
            mem_a = tmp_dir / "mem_a"
            mem_b = tmp_dir / "mem_b"
            mem_a.mkdir(parents=True, exist_ok=True)
            mem_b.mkdir(parents=True, exist_ok=True)

            router_proc = _start_router(router_dir=router_dir, port=router_port)
            processes.append(router_proc)
            if not _wait_ok(f"{router_url}/health", timeout=30.0):
                raise RuntimeError("Router failed to start")

            agent_a_proc = _start_agent(
                agent_dir,
                port=agent_a_port,
                agent_id="agent-teacher",
                display_name="Teacher Agent",
                memory_dir=mem_a,
                router_url=router_url,
            )
            agent_b_proc = _start_agent(
                agent_dir,
                port=agent_b_port,
                agent_id="agent-student",
                display_name="Student Agent",
                memory_dir=mem_b,
                router_url=router_url,
            )
            processes.extend([agent_a_proc, agent_b_proc])

            if not _wait_ok(f"{agent_a_url}/health", timeout=30.0):
                raise RuntimeError("Teacher agent failed to start")
            if not _wait_ok(f"{agent_b_url}/health", timeout=30.0):
                raise RuntimeError("Student agent failed to start")

            _set_auto_capture(agent_a_url)
            _set_auto_capture(agent_b_url)

            reg_t0 = time.perf_counter()
            reg_a = _register_agent(agent_a_url, router_url)
            reg_b = _register_agent(agent_b_url, router_url)
            reg_ms = (time.perf_counter() - reg_t0) * 1000.0

            router_agents = _wait_for_agents(router_url, ["agent-teacher", "agent-student"], timeout=25.0)
            if not router_agents:
                raise RuntimeError("Router did not register expected agents")

            _, session = _http_request_json(
                "POST",
                f"{router_url}/sessions",
                {
                    "chat_type": "solo",
                    "mode": "|",
                    "agents": ["agent-teacher", "agent-student"],
                    "strictness": 45,
                    "pass_threshold": 60,
                    "max_iterations": 3,
                },
                timeout=20.0,
            )
            session_id = session["session_id"]

            teach_t0 = time.perf_counter()
            _http_request_json("POST", f"{router_url}/sessions/{session_id}/teach", {}, timeout=20.0)

            final_session = None
            deadline = time.time() + 70
            while time.time() < deadline:
                _, state = _http_request_json("GET", f"{router_url}/sessions/{session_id}", timeout=20.0)
                if state.get("status") in {"completed", "failed"} and state.get("current_iteration", 0) > 0:
                    final_session = state
                    break
                time.sleep(0.6)
            if final_session is None:
                raise RuntimeError("Teaching loop did not complete within timeout")
            teach_ms = (time.perf_counter() - teach_t0) * 1000.0

            _, memories_a = _http_request_json("GET", f"{agent_a_url}/memory/list", timeout=10.0)
            _, memories_b = _http_request_json("GET", f"{agent_b_url}/memory/list", timeout=10.0)
            _, search_a_data = _http_request_json(
                "POST",
                f"{agent_a_url}/memory/search",
                {"query": "teaching challenge feedback confidence", "top_k": 3},
                timeout=10.0,
            )
            _, search_b_data = _http_request_json(
                "POST",
                f"{agent_b_url}/memory/search",
                {"query": "teaching challenge feedback confidence", "top_k": 3},
                timeout=10.0,
            )

            total_ms = (time.perf_counter() - started_at) * 1000.0

            score_count = len(final_session.get("scores", []))
            final_score = final_session.get("scores", [{}])[-1].get("score") if score_count else None
            message_count = len(final_session.get("messages", []))

            report.update(
                {
                    "registration": {
                        "teacher": reg_a.get("status", "unknown"),
                        "student": reg_b.get("status", "unknown"),
                        "latency_ms": round(reg_ms, 2),
                    },
                    "session": {
                        "session_id": final_session.get("session_id"),
                        "status": final_session.get("status"),
                        "iterations": final_session.get("current_iteration", 0),
                        "score_count": score_count,
                        "final_score": final_score,
                        "message_count": message_count,
                        "teach_latency_ms": round(teach_ms, 2),
                    },
                    "memory": {
                        "teacher_count": len(memories_a),
                        "student_count": len(memories_b),
                        "teacher_search_hits": len(search_a_data),
                        "student_search_hits": len(search_b_data),
                    },
                    "timing": {"total_ms": round(total_ms, 2)},
                }
            )
    finally:
        _stop_processes(processes)

    report["passed"] = (
        report["registration"]["teacher"] in {"registered", "updated"}
        and report["registration"]["student"] in {"registered", "updated"}
        and report["session"]["status"] == "completed"
        and report["session"]["score_count"] >= 1
        and report["session"]["message_count"] >= 4
        and report["memory"]["teacher_count"] >= 1
        and report["memory"]["student_count"] >= 1
    )
    return report


def main() -> int:
    report: dict[str, Any]
    try:
        report = _run()
    except Exception as exc:  # noqa: BLE001
        report = {
            "passed": False,
            "error": str(exc),
        }

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
