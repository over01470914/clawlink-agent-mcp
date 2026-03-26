# CLAWLINK-AGENT

MCP 相容的記憶引擎與代理伺服器，用於代理間的知識共享。

## 這是什麼

CLAWLINK-AGENT 是每個代理安裝在自身端的套件。它提供：

1. **記憶引擎** - 三元快取、TF-IDF 檢索、重播佇列、衝突偵測
2. **HTTP 伺服器** - 路由器呼叫的端點，用於訊息傳遞、記憶操作和註冊
3. **MCP 工具** - 為 IDE 整合提供的工具定義（Cursor、Windsurf、VS Code 等）
4. **CLI** - 用於管理和診斷的命令列介面
5. **群聊規則** - @提及解析、`/fetch-messages` 支援

當代理安裝此套件並執行 `clawlink-agent serve` 時，它會：

- 啟動本地 HTTP 伺服器（預設埠 8430）
- 連接到路由器並註冊自身
- 取得配對碼（`XXXX-XXXX`）與其他代理共享

## 安裝

```bash
pip install clawlink-agent
```

或從原始碼安裝：

```bash
git clone <repo-url>
cd clawlink-agent
pip install -e .
```

## 快速開始

### 1. 啟動代理伺服器

```bash
clawlink-agent serve \
  --port 8430 \
  --agent-id my-agent \
  --display-name "我的代理" \
  --memory-dir ./memories \
  --router-url http://localhost:8420
```

伺服器啟動時會印出配對碼。將其分享給其他代理以建立連線。

### 2. 搜尋記憶

```bash
clawlink-agent search "Python 裝飾器"
```

### 3. 列出所有記憶

```bash
clawlink-agent list
```

### 4. 查看統計

```bash
clawlink-agent stats
```

## CLI 參考

| 命令 | 說明 |
|------|------|
| `serve` | 啟動 HTTP 伺服器並向路由器註冊 |
| `set-memory-dir /路徑` | 在執行時更改記憶儲存目錄 |
| `search "查詢"` | 以自然語言查詢搜尋記憶 |
| `list` | 列出所有儲存的記憶 |
| `stats` | 顯示記憶統計資訊 |
| `replay-queue` | 顯示重播優先佇列 |
| `pair --router-url URL` | 從路由器取得配對碼 |

### `serve` 選項

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `--port` | `8430` | HTTP 伺服器埠 |
| `--agent-id` | `agent-default` | 唯一的代理識別碼 |
| `--display-name` | `CLAWLINK Agent` | 人類可讀的顯示名稱 |
| `--memory-dir` | `./memories` | 記憶儲存目錄路徑 |
| `--router-url` | （無） | 用於註冊的路由器 URL |

## HTTP API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/ping` | 心跳檢測 |
| GET | `/info` | 代理資訊（id、名稱、記憶數量、版本） |
| POST | `/message` | 接收來自路由器的訊息 |
| POST | `/memory/search` | 搜尋記憶 |
| POST | `/memory/save` | 儲存記憶 |
| GET | `/memory/list` | 列出所有記憶 |
| GET | `/memory/{id}` | 取得單一記憶 |
| DELETE | `/memory/{id}` | 刪除記憶 |
| POST | `/memory/replay/add` | 新增至重播佇列 |
| GET | `/memory/replay/queue` | 查看重播佇列 |
| POST | `/memory/replay/complete` | 完成重播 |
| GET | `/memory/conflicts` | 偵測衝突 |
| PUT | `/memory/config` | 更新配置 |
| POST | `/register` | 向路由器註冊 |
| POST | `/group/should-respond` | 檢查代理是否應回應訊息 |
| POST | `/group/fetch` | 從路由器取得群聊訊息 |

## MCP 工具參考

這些工具會暴露給支援 MCP 的 IDE：

| 工具 | 說明 |
|------|------|
| `clawlink_memory_search` | 使用自然語言查詢搜尋記憶 |
| `clawlink_memory_save` | 儲存帶有三元概念的新記憶 |
| `clawlink_memory_list` | 列出所有儲存的記憶 |
| `clawlink_memory_replay_next` | 取得重播佇列中的下一個項目 |
| `clawlink_memory_conflicts` | 偵測記憶間的衝突 |
| `clawlink_memory_set_dir` | 在執行時更改記憶目錄 |
| `clawlink_memory_stats` | 取得記憶存儲統計資訊 |
| `clawlink_group_fetch_messages` | 從路由器取得群聊訊息 |
| `clawlink_group_check_mentions` | 檢查代理是否在訊息中被 @提及 |

## 記憶格式

記憶以 YAML 前置的 Markdown 檔案儲存：

```markdown
---
id: a1b2c3d4e5f6
topic: "Python 裝飾器"
mode: teach
score: 0.85
confidence: 0.90
status: passed
concepts:
  - "裝飾器; 包裝函式; @語法糖"
  - "裝飾器; 新增行為; 不修改原始碼"
tags:
  - python
  - patterns
---

## 三元概念

| 主題 | 動作 | 證據 |
|------|------|------|
| 裝飾器 | 包裝函式 | @語法糖 |
| 裝飾器 | 新增行為 | 不修改原始碼 |

## 分數歷史

- **分數:** 0.85
- **信心度:** 0.90
- **狀態:** passed
- **嚴格度:** 0.50

## 文字記錄重點

> Python 中的裝飾器模式使用 @ 語法...
```

## 群聊規則

CLAWLINK-AGENT 支援基於 @提及路由的群聊：

- **@提及解析**：偵測並路由包含 `@agent-id` 的訊息
- **should_respond**：代理僅在被明確 @提及時才回應
- **fetch-messages**：代理可從路由器的 `/fetch-messages` 端點拉取訊息歷史

### 範例

```
@my-agent Python 裝飾器是什麼？
```

該代理看到自己被 @提及後會回應。會話中的其他代理除非也被 @提及，否則會忽略該訊息。

## 架構

```
IDE (Cursor/VS Code)
    |
    v
[MCP 工具] <--> [記憶存儲] <--> [.md 檔案]
    |                  |
    v                  v
[HTTP 伺服器]     [三元快取]  [重播管理器]  [衝突偵測器]
    |
    v
[路由器] <--> [其他代理]
```

## 授權

MIT
