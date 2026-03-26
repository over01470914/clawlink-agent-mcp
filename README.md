# CLAWLINK-AGENT

CLAWLINK-AGENT is the deployable runtime for each AI agent node. It can run on a PC (VS Code AI agent host) or a cloud host (OpenClaw MCP endpoint).

## Deployment Role

Use this component when you need a standalone agent service that can:

1. host local memory (triadic memory + replay + conflict detection)
2. expose agent HTTP endpoints
3. register to a ClawLink Router
4. provide MCP-compatible tools for IDE integrations

## Independent Runtime Contract

This service is designed to run independently with only one external dependency: Router URL.

- Input dependency: `--router-url` (or empty when running local-only)
- Local state: `--memory-dir` directory owned by this node
- Network direction: outbound connection to Router
- No hardcoded peer IP is required in code

## Install

From PyPI:

```bash
pip install clawlink-agent
```

From source:

```bash
cd clawlink-agent
pip install -e .
```

## Quick Start

1. Create memory directory

```bash
mkdir -p ./clawlink_memories
```

1. Start the service

```bash
clawlink-agent serve \
  --port 8430 \
  --agent-id agent-local-01 \
  --display-name "Local Agent 01" \
  --memory-dir ./clawlink_memories \
  --router-url http://ROUTER_HOST:8420
```

1. Check health

```bash
curl http://localhost:8430/ping
```

1. Use CLI diagnostics

```bash
clawlink-agent stats --port 8430
clawlink-agent list --port 8430
clawlink-agent search "your query" --port 8430
```

## CLI Commands

| Command | Purpose |
| --- | --- |
| `serve` | Start agent HTTP runtime |
| `set-memory-dir PATH` | Switch memory storage directory |
| `search QUERY` | Search memory entries |
| `list` | List memory entries |
| `stats` | Show runtime and memory info |
| `replay-queue` | Show replay queue |
| `pair --router-url URL` | Pair/register with Router |
| `bootstrap-deps` | Verify and auto-install runtime Python dependencies |

## Dependency Bootstrap

If the runtime environment is incomplete, the CLI can self-heal missing Python dependencies.

Check only:

```bash
clawlink-agent bootstrap-deps --check-only
```

Auto-install missing dependencies:

```bash
clawlink-agent bootstrap-deps
```

`serve`, `search`, `list`, `stats`, `replay-queue`, and `pair` also run dependency bootstrap automatically before importing their runtime modules.

## Router Compatibility Notes

For direct Router integration testing:

1. start the agent with `--public-endpoint`
2. run `clawlink-agent pair --router-url http://HOST:8420 --port <agent-port>`
3. Router will register the agent through `/agents/register`

`/message` also returns `response` and `content` fields containing recalled memory context so generic HTTP Router clients receive non-empty text.

## Standalone Memory Automation Test

Use this before integrating Router when you want to validate long-task memory continuity for a single agent.

Run:

```bash
py scripts/standalone_memory_automation_test.py
```

Optional thresholds:

```bash
py scripts/standalone_memory_automation_test.py --phases 10 --recall-threshold 0.8 --latency-threshold-ms 500
```

Output JSON includes:

- `recall_rate`: phase recall hit rate
- `consistency`: top recall consistency across checkpoints
- `avg_search_latency_ms`: average search latency
- `passed`: final pass/fail verdict

## Auto Capture and Noise Filtering

`/message` now supports optional memory auto-capture with an importance filter.

Default behavior is safe: auto-capture is disabled unless configured.

Enable at runtime:

```bash
curl -X PUT http://localhost:8430/memory/config \
  -H "Content-Type: application/json" \
  -d '{"auto_memory_capture": true, "min_importance": 0.55}'
```

When enabled, each message can be evaluated for:

- keyword extraction (`keywords` field)
- importance scoring (decision/fix/policy signals)
- duplicate suppression (avoid near-identical memory entries)

Draft memories can also receive TTL so low-confidence short-lived notes naturally fall out of retrieval.

Use the quality test:

```bash
py scripts/auto_capture_quality_test.py
```

## Merge and Decay Stabilization

To keep retrieval quality stable when memory volume grows:

- similar memories are automatically merged instead of growing one fragment per near-duplicate event
- draft memories can expire through `ttl_days`
- retrieval ranking applies recency decay with access-count bonus to keep useful memories near the top

Run the regression test:

```bash
py scripts/memory_merge_decay_test.py
```

### `serve` Options

| Flag | Default | Description |
| --- | --- | --- |
| `--port` | `8430` | Local listen port |
| `--agent-id` | `agent-default` | Unique identifier |
| `--display-name` | `CLAWLINK Agent` | UI display name |
| `--memory-dir` | `./memories` | Local memory path |
| `--router-url` | empty | Router endpoint |
| `--public-endpoint` | `http://127.0.0.1:<port>` | Callback endpoint Router should call |

## HTTP Endpoints (Agent)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/ping` | Health check |
| GET | `/health` | Router-compatible health check |
| GET | `/info` | Runtime info |
| POST | `/message` | Receive router message |
| POST | `/memory/search` | Memory search |
| POST | `/memory/save` | Save memory |
| GET | `/memory/list` | List memory |
| GET | `/memory/{memory_id}` | Read memory |
| DELETE | `/memory/{memory_id}` | Delete memory |
| POST | `/memory/replay/add` | Add replay task |
| GET | `/memory/replay/queue` | View replay queue |
| POST | `/memory/replay/complete` | Complete replay task |
| GET | `/memory/conflicts` | Detect conflicts |
| PUT | `/memory/config` | Update memory settings |
| POST | `/register` | Register to Router |
| POST | `/group/should-respond` | Mention routing decision |
| POST | `/group/fetch` | Pull group messages |

## Extracted Essentials From Global Docs

### Memory Schema Essentials

Agent memory entries should keep these key fields consistent:

- `id`: unique memory id
- `topic`: knowledge title
- `category`: patterns / corrections / observations / facts / procedures
- `confidence`: score in range 0.0 to 1.0
- `source`: taught / learned / corrected / observed
- `sessionContext`: session id, mode, iteration, score

### Confidence Update Rule

Suggested blend rule for reinforcement:

```text
confidence_new = (confidence_old * 0.6) + (new_score * 0.4)
```

### Conflict Handling

When new memory conflicts with existing memory on the same topic:

1. compare confidence and score
2. keep higher-confidence outcome as active knowledge
3. keep correction record for traceability

### Replay Queue Intent

Replay queue is used for low-confidence or failed items and should be reviewed periodically.

## Device-Specific Notes

- VS Code host PC: run with local memory path and keep service near IDE.
- Cloud MCP host: run under process manager (systemd, supervisor, or container).
- Multi-agent scenario: each node must use a unique `--agent-id` and its own `--memory-dir`.

## Anti-Hardcoding Checklist

- Do not hardcode Router IP in source code.
- Pass Router endpoint through CLI/env/config.
- Keep memory path configurable per machine.
- Keep port configurable to avoid conflicts.

## License

MIT

---

## 中文说明

CLAWLINK-AGENT 是每个 AI Agent 节点的可部署运行时，可运行在本地 PC（VS Code AI Agent 宿主）或云端主机（OpenClaw MCP 端点）。

### 组件职责

当你需要一个可独立运行的 Agent 服务时使用本模块，它可以：

1. 承载本地记忆（triadic memory + replay + 冲突检测）
2. 提供 Agent HTTP 接口
3. 注册到 ClawLink Router
4. 向 IDE 提供 MCP 兼容工具

### 独立运行契约

本服务只依赖一个外部输入：Router URL。

- 外部依赖：`--router-url`（为空时可本地模式运行）
- 本地状态：`--memory-dir`（每个节点独立目录）
- 网络方向：主动连接 Router
- 代码中不需要写死对端 IP

### 安装

PyPI 安装：

```bash
pip install clawlink-agent
```

源码安装：

```bash
cd clawlink-agent
pip install -e .
```

### 快速启动

1. 创建记忆目录

```bash
mkdir -p ./clawlink_memories
```

1. 启动服务

```bash
clawlink-agent serve \
  --port 8430 \
  --agent-id agent-local-01 \
  --display-name "Local Agent 01" \
  --memory-dir ./clawlink_memories \
  --router-url http://ROUTER_HOST:8420
```

1. 健康检查

```bash
curl http://localhost:8430/ping
```

1. 运行诊断命令

```bash
clawlink-agent stats --port 8430
clawlink-agent list --port 8430
clawlink-agent search "your query" --port 8430
```

### 从全局 docs 提炼的记忆与教学关键点

#### 记忆字段基线

建议保持以下核心字段：

- `id`：唯一记忆标识
- `topic`：知识主题
- `category`：patterns / corrections / observations / facts / procedures
- `confidence`：0.0 到 1.0
- `source`：taught / learned / corrected / observed
- `sessionContext`：记录 session、mode、iteration、score

#### 置信度更新建议

```text
confidence_new = (confidence_old * 0.6) + (new_score * 0.4)
```

#### 冲突处理原则

同 topic 冲突时：

1. 对比新旧 confidence/score
2. 保留高置信内容为当前知识
3. 保留 correction 记录以便追踪

#### Replay 队列用途

Replay 队列用于低置信度或失败项的复习与再学习。

### 防硬编码清单

- 不要在源码中写死 Router IP。
- Router 地址通过 CLI / 环境变量 / 配置传入。
- 记忆目录按机器配置。
- 端口保持可配置，避免冲突。
