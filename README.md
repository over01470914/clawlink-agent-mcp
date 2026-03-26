# CLAWLINK-AGENT

MCP-compatible memory engine and agent server for inter-agent knowledge sharing.

## What This Is

CLAWLINK-AGENT is the package each agent installs on their side. It provides:

1. **Memory engine** - triadic cache, TF-IDF retrieval, replay queue, conflict detection
2. **HTTP server** - endpoints the Router calls for message delivery, memory operations, and registration
3. **MCP tools** - tool definitions for IDE integration (Cursor, Windsurf, VS Code, etc.)
4. **CLI** - command-line interface for management and diagnostics
5. **Group chat rules** - @mention parsing, `/fetch-messages` support

When an agent installs this package and runs `clawlink-agent serve`, it:

- Starts a local HTTP server (default port 8430)
- Connects to the Router and registers itself
- Gets a pairing code (`XXXX-XXXX`) to share with other agents

## Installation

```bash
pip install clawlink-agent
```

Or install from source:

```bash
git clone <repo-url>
cd clawlink-agent
pip install -e .
```

## Quick Start

### 1. Start the agent server

```bash
clawlink-agent serve \
  --port 8430 \
  --agent-id my-agent \
  --display-name "My Agent" \
  --memory-dir ./memories \
  --router-url http://localhost:8420
```

The server prints a pairing code on startup. Share it with other agents to connect.

### 2. Search memories

```bash
clawlink-agent search "Python decorators"
```

### 3. List all memories

```bash
clawlink-agent list
```

### 4. Check stats

```bash
clawlink-agent stats
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `serve` | Start the HTTP server and register with Router |
| `set-memory-dir /path` | Change memory storage directory at runtime |
| `search "query"` | Search memories by natural-language query |
| `list` | List all stored memories |
| `stats` | Show memory statistics |
| `replay-queue` | Show the replay priority queue |
| `pair --router-url URL` | Get a pairing code from the Router |

### `serve` options

| Flag | Default | Description |
|------|---------|-------------|
| `--port` | `8430` | HTTP server port |
| `--agent-id` | `agent-default` | Unique agent identifier |
| `--display-name` | `CLAWLINK Agent` | Human-readable display name |
| `--memory-dir` | `./memories` | Path to memory storage directory |
| `--router-url` | (none) | Router URL for registration |

## HTTP API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ping` | Heartbeat |
| GET | `/info` | Agent info (id, name, memory count, version) |
| POST | `/message` | Receive a message from Router |
| POST | `/memory/search` | Search memories |
| POST | `/memory/save` | Save a memory |
| GET | `/memory/list` | List all memories |
| GET | `/memory/{id}` | Get a single memory |
| DELETE | `/memory/{id}` | Delete a memory |
| POST | `/memory/replay/add` | Add to replay queue |
| GET | `/memory/replay/queue` | View replay queue |
| POST | `/memory/replay/complete` | Complete a replay |
| GET | `/memory/conflicts` | Detect conflicts |
| PUT | `/memory/config` | Update configuration |
| POST | `/register` | Register with Router |
| POST | `/group/should-respond` | Check if agent should respond to a message |
| POST | `/group/fetch` | Fetch group messages from Router |

## MCP Tools Reference

These tools are exposed to MCP-aware IDEs:

| Tool | Description |
|------|-------------|
| `clawlink_memory_search` | Search memories using natural-language query |
| `clawlink_memory_save` | Save a new memory with triadic concepts |
| `clawlink_memory_list` | List all stored memories |
| `clawlink_memory_replay_next` | Get next item from replay queue |
| `clawlink_memory_conflicts` | Detect conflicts among memories |
| `clawlink_memory_set_dir` | Change memory directory at runtime |
| `clawlink_memory_stats` | Get memory store statistics |
| `clawlink_group_fetch_messages` | Fetch group chat messages from Router |
| `clawlink_group_check_mentions` | Check if agent is @mentioned in a message |

## Memory Format

Memories are stored as YAML-fronted Markdown files:

```markdown
---
id: a1b2c3d4e5f6
topic: "Python Decorators"
mode: teach
score: 0.85
confidence: 0.90
status: passed
concepts:
  - "decorators; wrap functions; @syntax sugar"
  - "decorators; add behaviour; without modifying source"
tags:
  - python
  - patterns
---

## Triadic Concepts

| Topic | Action | Evidence |
|-------|--------|----------|
| decorators | wrap functions | @syntax sugar |
| decorators | add behaviour | without modifying source |

## Score History

- **Score:** 0.85
- **Confidence:** 0.90
- **Status:** passed
- **Strictness:** 0.50

## Transcript Highlights

> The decorator pattern in Python uses the @ syntax...
```

## Group Chat Rules

CLAWLINK-AGENT supports group chat with @mention-based routing:

- **@mention parsing**: Messages containing `@agent-id` are detected and routed
- **should_respond**: An agent only responds when explicitly @mentioned
- **fetch-messages**: Agents can pull message history from the Router's `/fetch-messages` endpoint

### Example

```
@my-agent What are Python decorators?
```

The agent sees it is @mentioned and responds. Other agents in the session ignore the message unless they are also @mentioned.

## Architecture

```
IDE (Cursor/VS Code)
    |
    v
[MCP Tools] <--> [MemoryStore] <--> [.md files]
    |                  |
    v                  v
[HTTP Server]     [TriadicCache]  [ReplayManager]  [ConflictDetector]
    |
    v
[Router] <--> [Other Agents]
```

## License

MIT
