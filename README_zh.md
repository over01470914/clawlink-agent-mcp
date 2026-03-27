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

### Windows 一鍵啟動

如果是 clone 專案後希望零參數啟動，可直接執行：

```bash
start_clawlink_agent.bat
```

此腳本會在 8430 埠啟動本機服務，並自動寫入 `.mcp.json`。
若埠已被佔用，會先確認是否為 CLAWLINK-AGENT：

- 若是同一服務：詢問是否重啟（`y/n`）
- 若是其他服務：中止啟動，避免誤停他人程序

啟動後會依序執行健康檢查：`/ping` -> `/health` -> `/info`。
最後會停留在結尾畫面，按鍵後只關閉啟動腳本本身，服務會持續在背景執行。

### Linux 一鍵啟動

```bash
chmod +x ./start_clawlink_agent.sh
./start_clawlink_agent.sh
```

Linux 腳本同樣會先檢查埠佔用，確認服務身份後再詢問是否重啟。
同時也會依序做健康檢查，最後等待 Enter 後只關閉啟動腳本。

### 1. 啟動代理伺服器

```bash
clawlink-agent serve \
  --port 8430 \
  --agent-id my-agent \
  --display-name "我的代理" \
  --memory-dir ./memories \
  --router-url http://localhost:8420
```

`serve` 啟動時預設會自動在本機產生 `.mcp.json`。
產生的設定會使用目前執行環境的 Python 解譯器路徑（`sys.executable`），因此使用者 clone 專案後通常不需要手動修改絕對路徑。

可選參數：

```bash
clawlink-agent serve \
  --mcp-config-path ./.mcp.json \
  --mcp-server-name clawlink-agent \
  --overwrite-mcp-config
```

若要停用自動產生：

```bash
clawlink-agent serve --no-write-mcp-config
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

`/message` 會在 `response` 與 `content` 欄位返回可直接閱讀的回答文本，
並在 `memory_summary` 欄位返回記憶召回摘要，方便測試腳本將「回答品質」與「記憶召回」分開評估。

## MCP 工具參考

這些工具會暴露給支援 MCP 的 IDE（Cursor、VS Code、TRAE 等）：

| 工具 | 說明 |
|------|------|
| `clawlink_memory_search` | 使用自然語言查詢搜尋記憶 |
| `clawlink_memory_brief` | 產生聚合結構化 facts 的精簡 recall brief |
| `clawlink_memory_save` | 儲存帶有三元概念的新記憶 |
| `clawlink_memory_list` | 列出所有儲存的記憶 |
| `clawlink_memory_get` | 根據 ID 獲取單一記憶 |
| `clawlink_memory_stats` | 取得記憶存儲統計資訊 |
| `clawlink_send_message` | 發送訊息給代理並自動擷取記憶 |
| `clawlink_diagnose` | 執行全面的 MCP 連接診斷 ⭐ |

## 記憶回歸驗證

目前倉庫內建兩個回歸腳本，用來驗證 MCP 記憶是否真的能提升回答品質，同時不會帶來明顯推理延遲。

### 長程記憶回歸

這個腳本會跑完整的 10 輪 TaskMaster 開發場景，最後檢查 agent 是否能回憶完整專案約束。

```bash
python scripts/app_scenario_regression.py \
  --agent-url http://127.0.0.1:8430 \
  --output ./regression.json
```

目前在本工作區驗證過的 fresh baseline：

- `fresh_facts_scenario_v7/regression.json`
- 最終分數：`100.0`
- 命中項目：`9/9`

### Memory-on vs Memory-off A/B 回歸

這個腳本會先灌入同一組場景記憶，然後對同一批 probe 分別以開啟與關閉 recall 的方式測試。

```bash
python scripts/app_scenario_ab_regression.py \
  --agent-url http://127.0.0.1:8430 \
  --output ./ab_regression.json
```

目前在本工作區驗證過的 fresh baseline：

- `ab_facts_scenario_v2/ab_regression.json`
- memory-on 平均分：`91.67`
- memory-off 平均分：`0.0`
- 平均分差：`+91.67`
- memory-on 平均延遲：`3.76ms`
- memory-off 平均延遲：`3.01ms`
- 平均延遲差：`+0.75ms`

解讀方式：

- 記憶已被證明可以顯著提升回答完整度
- recall 快取已把延遲壓到接近無記憶路徑

### 為什麼延遲下降了

目前 runtime 主要靠以下幾點減少 recall 成本：

- 將已載入的 memory entries 保留在程序內快取
- retriever index 不再每次 search 重建
- 重複查詢會命中 search cache
- search hit 不再每次都同步落盤更新 access metadata

## AI Agent 自動診斷指南

當 AI Agent 透過 MCP 連接到 CLAWLINK-AGENT 時，**應自動執行診斷檢查**以驗證連接是否正常運作。

### 連接後自動檢查（AI Agent 應執行的操作）

連接到 MCP 伺服器後，Agent 應該執行以下檢查：

```
使用 clawlink_diagnose 工具驗證 MCP 連接是否正常。
```

這會自動執行以下測試並返回使用者友好的報告：

1. **健康檢查** - 驗證代理是否正常回應
2. **代理資訊** - 確認版本和記憶數量
3. **記憶列表** - 驗證記憶系統可存取
4. **發送訊息** - 測試雙向通訊

## 建議的 MCP 推理流程

若希望記憶功能真正提升 Agent 的思考品質，同時避免額外延遲與上下文噪聲，建議按以下方式使用：

1. 先用 `clawlink_memory_brief` 針對當前任務取回精簡記憶摘要
2. 將 `brief_text` 注入 Agent 的思考上下文
3. 僅在確實需要原始記憶內容時，再呼叫 `clawlink_memory_search`
4. 任務完成後，再用 `clawlink_memory_save` 寫回穩定事實

這個流程比每輪都把完整記憶 JSON 餵給模型更適合「記憶增強 + 加速」。

### 獨立診斷腳本

也可以執行完整的診斷腳本：

```bash
python scripts/test_mcp_connection.py
```

這提供更詳細的輸出，包括所有 7 個測試案例：

- 健康檢查 (Health Check)
- MCP 初始化 (MCP Initialize)
- 工具列表 (Tools List)
- 記憶統計 (Memory Stats)
- 記憶搜尋 (Memory Search)
- 記憶列表 (Memory List)
- 發送訊息 (Send Message)

### 一鍵啟動並測試

Windows：
```bash
start_mcp_with_test.bat
```

PowerShell：
```powershell
.\start_mcp_with_test.ps1
```

這會自動：
1. 啟動 CLAWLINK-AGENT 服務
2. 執行完整的 MCP 連接測試
3. 顯示使用者友好的狀態報告
4. 通知使用者連接成功/失敗

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

## AI Agent 行為指南

當 AI Agent 連接到 CLAWLINK-AGENT MCP 服務時，應遵循以下行為規範：

### 連接後自動檢查流程

1. **連接到 MCP** → 讀取 `.mcp.json` 配置
2. **初始化 MCP 連接** → 發送 `initialize` 請求
3. **獲取工具列表** → 呼叫 `tools/list` 確認可用工具
4. **執行診斷檢查** → 呼叫 `clawlink_diagnose` 驗證連接狀態
5. **向用戶報告** → 根據診斷結果生成友好提示

### AI Agent 應執行的 MCP 診斷代碼

```python
# 當連接到 CLAWLINK-AGENT MCP 後，Agent 應自動執行：
result = await mcp_client.call_tool("clawlink_diagnose", {})

# 解析診斷結果
if result.status == "HEALTHY":
    print("✅ MCP 服務運行正常！所有功能測試通過。")
else:
    print("⚠️ MCP 服務部分異常，需要檢查。")
```

### Agent 應記憶的關鍵工具

| 工具名稱 | 用途 |
|----------|------|
| `clawlink_memory_search` | 搜尋歷史記憶 |
| `clawlink_memory_save` | 儲存新記憶 |
| `clawlink_send_message` | 發送訊息並自動擷取記憶 |
| `clawlink_diagnose` | 診斷連接狀態 |

### 診斷結果解讀

當收到 `clawlink_diagnose` 的結果時：

- **status: HEALTHY** → MCP 服務完全正常，可以開始工作
- **status: DEGRADED** → 部分功能異常，應通知用戶
- **測試失敗** → 詳細檢查失敗的測試項目並報告

## 授權

MIT
