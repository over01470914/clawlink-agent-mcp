"""CLI entry-point for CLAWLINK-AGENT."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from .bootstrap import ensure_runtime_dependencies

logger = logging.getLogger("clawlink_agent")


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------


def _cmd_serve(args: argparse.Namespace) -> None:
    """Start the agent HTTP server and register with Router."""
    missing = ensure_runtime_dependencies(auto_install=True)
    if missing:
        print(f"Error: missing dependencies after bootstrap: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    import uvicorn

    from .server import app, configure, generate_pairing_code

    configure(
        agent_id=args.agent_id,
        display_name=args.display_name,
        memory_dir=args.memory_dir,
        router_url=args.router_url,
        port=args.port,
        public_endpoint=args.public_endpoint,
    )

    code = generate_pairing_code()
    print(f"\n  CLAWLINK-AGENT starting")
    print(f"  Agent ID    : {args.agent_id}")
    print(f"  Display Name: {args.display_name}")
    print(f"  Memory Dir  : {os.path.abspath(args.memory_dir)}")
    print(f"  Router URL  : {args.router_url or '(none)'}")
    print(f"  Endpoint    : {args.public_endpoint or f'http://127.0.0.1:{args.port}'}")
    print(f"  Pairing Code: {code}")
    print(f"  Listening on: http://0.0.0.0:{args.port}")
    print()

    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")


def _cmd_set_memory_dir(args: argparse.Namespace) -> None:
    """Update the memory directory via the running server."""
    missing = ensure_runtime_dependencies(auto_install=True)
    if missing:
        print(f"Error: missing dependencies after bootstrap: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    import httpx

    url = f"http://localhost:{args.port}/memory/config"
    try:
        resp = httpx.put(url, json={"memory_dir": args.path}, timeout=5.0)
        resp.raise_for_status()
        print(json.dumps(resp.json(), indent=2))
    except httpx.RequestError as exc:
        print(f"Error: cannot reach agent server on port {args.port}: {exc}", file=sys.stderr)
        sys.exit(1)


def _cmd_search(args: argparse.Namespace) -> None:
    """Search memories via the running server."""
    missing = ensure_runtime_dependencies(auto_install=True)
    if missing:
        print(f"Error: missing dependencies after bootstrap: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    import httpx

    url = f"http://localhost:{args.port}/memory/search"
    try:
        resp = httpx.post(url, json={"query": args.query, "top_k": args.top_k}, timeout=10.0)
        resp.raise_for_status()
        results = resp.json()
        if not results:
            print("No results found.")
            return
        for entry in results:
            print(f"  [{entry.get('id', '?')}] {entry.get('topic', '')} "
                  f"(score={entry.get('score', 0):.2f}, status={entry.get('status', '')})")
    except httpx.RequestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _cmd_list(args: argparse.Namespace) -> None:
    """List all memories via the running server."""
    missing = ensure_runtime_dependencies(auto_install=True)
    if missing:
        print(f"Error: missing dependencies after bootstrap: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    import httpx

    url = f"http://localhost:{args.port}/memory/list"
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        entries = resp.json()
        if not entries:
            print("No memories stored.")
            return
        print(f"  Total memories: {len(entries)}\n")
        for entry in entries:
            print(f"  [{entry.get('id', '?')}] {entry.get('topic', '')} "
                  f"(score={entry.get('score', 0):.2f}, status={entry.get('status', '')})")
    except httpx.RequestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _cmd_stats(args: argparse.Namespace) -> None:
    """Show memory statistics via the running server."""
    missing = ensure_runtime_dependencies(auto_install=True)
    if missing:
        print(f"Error: missing dependencies after bootstrap: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    import httpx

    url = f"http://localhost:{args.port}/info"
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        print(json.dumps(resp.json(), indent=2))
    except httpx.RequestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _cmd_replay_queue(args: argparse.Namespace) -> None:
    """Show the replay queue via the running server."""
    missing = ensure_runtime_dependencies(auto_install=True)
    if missing:
        print(f"Error: missing dependencies after bootstrap: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    import httpx

    url = f"http://localhost:{args.port}/memory/replay/queue"
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        queue = resp.json()
        if not queue:
            print("Replay queue is empty.")
            return
        for item in queue:
            print(f"  [{item.get('memory_id', '?')}] priority={item.get('priority', '?')} "
                  f"attempts={item.get('attempts', 0)} reason={item.get('reason', '')}")
    except httpx.RequestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _cmd_pair(args: argparse.Namespace) -> None:
    """Register with Router and get a pairing code."""
    missing = ensure_runtime_dependencies(auto_install=True)
    if missing:
        print(f"Error: missing dependencies after bootstrap: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    import httpx

    if not args.router_url:
        print("Error: --router-url is required for pairing", file=sys.stderr)
        sys.exit(1)

    # If a local server is running, ask it to register
    url = f"http://localhost:{args.port}/register"
    try:
        resp = httpx.post(url, json={"router_url": args.router_url}, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        print(f"  Pairing Code: {data.get('pairing_code', '?')}")
        print(f"  Status      : {data.get('status', '?')}")
    except httpx.RequestError:
        # No local server running - do a direct registration
        import uuid
        raw = uuid.uuid4().hex[:8].upper()
        code = f"{raw[:4]}-{raw[4:]}"
        print(f"  Generated Pairing Code: {code}")
        print("  (Note: agent server is not running; start with 'clawlink-agent serve' first)")


def _cmd_bootstrap_deps(args: argparse.Namespace) -> None:
    """Check and install missing runtime dependencies."""
    missing = ensure_runtime_dependencies(auto_install=not args.check_only)
    if missing:
        print(json.dumps({"status": "missing", "modules": missing}, indent=2))
        sys.exit(1)
    print(json.dumps({"status": "ok", "message": "runtime dependencies are ready"}, indent=2))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawlink-agent",
        description="CLAWLINK-AGENT: MCP-compatible memory engine and agent server",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # serve
    serve_p = sub.add_parser("serve", help="Start the agent HTTP server")
    serve_p.add_argument("--port", type=int, default=8430, help="Port to listen on (default: 8430)")
    serve_p.add_argument("--agent-id", default="agent-default", help="Unique agent identifier")
    serve_p.add_argument("--display-name", default="CLAWLINK Agent", help="Human-readable name")
    serve_p.add_argument("--memory-dir", default="./memories", help="Path to memory storage directory")
    serve_p.add_argument("--router-url", default="", help="Router URL (e.g. http://localhost:8420)")
    serve_p.add_argument(
        "--public-endpoint",
        default="",
        help="Endpoint Router should call back (default: http://127.0.0.1:<port>)",
    )

    # set-memory-dir
    smd_p = sub.add_parser("set-memory-dir", help="Change the memory directory")
    smd_p.add_argument("path", help="New memory directory path")
    smd_p.add_argument("--port", type=int, default=8430, help="Agent server port")

    # search
    search_p = sub.add_parser("search", help="Search memories")
    search_p.add_argument("query", help="Search query string")
    search_p.add_argument("--top-k", type=int, default=5, help="Max results")
    search_p.add_argument("--port", type=int, default=8430, help="Agent server port")

    # list
    list_p = sub.add_parser("list", help="List all memories")
    list_p.add_argument("--port", type=int, default=8430, help="Agent server port")

    # stats
    stats_p = sub.add_parser("stats", help="Show memory statistics")
    stats_p.add_argument("--port", type=int, default=8430, help="Agent server port")

    # replay-queue
    rq_p = sub.add_parser("replay-queue", help="Show the replay queue")
    rq_p.add_argument("--port", type=int, default=8430, help="Agent server port")

    # pair
    pair_p = sub.add_parser("pair", help="Get a pairing code from the Router")
    pair_p.add_argument("--router-url", default="", help="Router URL")
    pair_p.add_argument("--port", type=int, default=8430, help="Agent server port")

    # bootstrap-deps
    bootstrap_p = sub.add_parser("bootstrap-deps", help="Install or verify runtime dependencies")
    bootstrap_p.add_argument(
        "--check-only",
        action="store_true",
        help="Only check dependency availability without installing",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

_DISPATCH = {
    "serve": _cmd_serve,
    "set-memory-dir": _cmd_set_memory_dir,
    "search": _cmd_search,
    "list": _cmd_list,
    "stats": _cmd_stats,
    "replay-queue": _cmd_replay_queue,
    "pair": _cmd_pair,
    "bootstrap-deps": _cmd_bootstrap_deps,
}


def main() -> None:
    """CLI entry-point."""
    parser = _build_parser()
    args = parser.parse_args()
    _setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    handler = _DISPATCH.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler(args)


if __name__ == "__main__":
    main()
