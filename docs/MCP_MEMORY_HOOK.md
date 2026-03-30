# MCP Memory Hook — Agent 記憶掛鉤機制

本文件說明 ClawLink Agent 如何在每次 Q&A 互動中自動產生記憶條目（Memory Entry）並進行召回（Recall），以及如何透過 Router 的教學迴圈（Teaching Loop）確保學生 Agent 能正確捕獲教師教授的內容。

---

## 1. 記憶掛鉤概覽

Agent 收到 Router 轉發的訊息時（`POST /message`），會依序執行以下步驟：

```
收到訊息 → 提取關鍵字 → 判斷是否捕獲 → 估計重要性 → 儲存記憶 → 召回相關記憶 → 生成回應
```

### 1.1 觸發條件

記憶捕獲在以下任一條件成立時啟動：

| 條件                             | 說明                                                                                  |
| -------------------------------- | ------------------------------------------------------------------------------------- |
| `auto_memory_capture = True`     | 全域設定，透過 `POST /memory/config` 啟用                                             |
| `metadata.capture_memory = True` | 單次訊息層級，由 Router 在 metadata 中指定                                            |
| 教學內容（Teaching Content）     | `metadata.message_type` 為 `teaching` 或 `challenge`，且 `metadata.role` 為 `student` |

### 1.2 教學內容的特殊處理

當 Agent 作為學生角色接收教學內容時：

- **重要性門檻降為 0**：確保所有教學內容都能被捕獲
- **重要性下限提升至 0.7**：教學內容的記憶重要性至少為 0.7
- **回應包含教學摘要**：學生 Agent 會在回應中回顯收到的教學內容

---

## 2. 記憶條目產生流程

### 2.1 關鍵字提取 (`_extract_keywords`)

從訊息內容中提取關鍵字，用於：

- 建立記憶的 `keywords` 欄位
- 產生事實摘要（`_extract_message_facts`）
- 構建搜尋查詢

### 2.2 重要性估計 (`_estimate_importance`)

根據以下因素計算 0.0–1.0 的重要性分數：

- 技術關鍵字出現次數
- 專案相關事實的豐富度
- 訊息長度與結構

**一般訊息**：需達到 `min_importance`（預設 0.55）才會儲存。
**教學訊息**：門檻降為 0，確保捕獲。

### 2.3 去重檢查 (`_is_duplicate_memory`)

在儲存前檢查是否已存在高度相似的記憶，避免重複。

### 2.4 記憶建構 (`_build_memory_from_message`)

將訊息轉換為 `MemoryEntry`，包含：

- `keywords`: 提取的關鍵字
- `concepts`: 三元概念（Triadic Concepts）
- `importance`: 重要性分數
- `transcript_highlights`: 訊息摘要
- `facts`: 結構化事實

### 2.5 三元網路索引 (`TriadicMemory`)

每個記憶條目的概念會被加入三元概念網路，支援關聯式召回。

---

## 3. 記憶召回流程

### 3.1 查詢構建

從訊息中生成多組查詢候選：

1. 前 4 個關鍵字組合
2. 前 8 個關鍵字組合（如果有的話）
3. 訊息內容前 240 字元

### 3.2 搜尋與排序 (`MemoryStore.search`)

使用 TF-IDF 向量搜尋，返回最相關的 top-k 條記憶（預設 5 條）。

### 3.3 摘要建構 (`_build_brief_from_entries`)

將召回的記憶整合為結構化摘要：

```json
{
  "query": "搜尋查詢",
  "count": 3,
  "topics": ["topic_a", "topic_b"],
  "facts": { "project_name": ["ClawLink"] },
  "highlights": ["記憶片段1", "記憶片段2"],
  "brief_text": "基於 3 筆記憶的摘要文字"
}
```

---

## 4. Router 教學迴圈中的記憶掛鉤

Router 的 7 步驟教學迴圈如何觸發記憶掛鉤：

| 步驟               | 角色              | message_type  | role      | capture_memory |
| ------------------ | ----------------- | ------------- | --------- | -------------- |
| 1. 教師教學        | Teacher → Student | `teaching`    | `student` | `True`         |
| 2. 學生回應        | Student → Teacher | `response`    | `teacher` | `False`        |
| 3. 教師挑戰        | Teacher → Student | `challenge`   | `student` | `True`         |
| 4. 學生回答        | Student → Teacher | `response`    | `teacher` | `False`        |
| 5. 學生自評        | Student           | `self_assess` | `student` | `True`         |
| 6. 教師評分        | Teacher           | `score`       | `teacher` | `False`        |
| 7. Router 混合評分 | -                 | -             | -         | -              |

### 4.1 metadata 結構

Router 發送給 Agent 的訊息會包含以下 metadata：

```json
{
  "capture_memory": true,
  "role": "student",
  "message_type": "teaching",
  "sender_id": "agent-a"
}
```

---

## 5. API 參考

### 5.1 接收訊息

```
POST /message
```

**Request Body:**

```json
{
  "sender_id": "agent-a",
  "session_id": "session-123",
  "content": "今晚的暗號是「今晚打老虎」",
  "metadata": {
    "capture_memory": true,
    "message_type": "teaching",
    "role": "student"
  }
}
```

**Response:**

```json
{
  "received": true,
  "agent_id": "agent-b",
  "memory_captured": true,
  "memory_id": "mem-abc123",
  "importance": 0.7,
  "keywords": ["暗號", "今晚打老虎"],
  "recalled_memories": [...],
  "memory_brief": {...},
  "response": "收到教學內容: 今晚的暗號是「今晚打老虎」\n已將此內容存入記憶。",
  "content": "..."
}
```

### 5.2 記憶配置

```
POST /memory/config
```

**Request Body:**

```json
{
  "auto_memory_capture": true,
  "min_importance": 0.55
}
```

### 5.3 記憶搜尋

```
POST /memory/recall
```

**Request Body:**

```json
{
  "query": "暗號",
  "top_k": 5
}
```

### 5.4 手動種子記憶

```
POST /memory/seed
```

**Request Body:**

```json
{
  "content": "今晚的暗號是「今晚打老虎」",
  "keywords": ["暗號", "今晚打老虎"],
  "importance": 0.9
}
```

---

## 6. 常見問題排除

### 學生 Agent 無法記住教學內容

1. **檢查 metadata**：確認 Router 發送的訊息包含 `capture_memory: true`
2. **檢查記憶儲存路徑**：Docker 容器中記憶儲存在 `/app/memories/`
3. **檢查重要性門檻**：教學內容應自動降低門檻，但一般訊息需達到 0.55
4. **檢查去重**：如果相同內容已存在，不會重複儲存

### Agent 回應中看不到召回的記憶

1. **檢查 `use_memory_recall`**：metadata 中預設為 `true`
2. **確認記憶已儲存**：呼叫 `GET /memory/search?q=關鍵字` 確認
3. **檢查關鍵字匹配**：TF-IDF 搜尋需要關鍵字有足夠重疊
