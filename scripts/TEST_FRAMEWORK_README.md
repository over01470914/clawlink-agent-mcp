# CLAWLINK-AGENT 记忆测试框架

本测试框架用于评估 CLAWLINK-AGENT MCP 的记忆能力和行为修正能力。

## 测试概览

### 测试一：管理驱动测试 (Management-Driven Tests)
**目的**: 测试 agent 在被明确告知不能直接执行任务的情况下，是否能记住委派原则并正确分配任务。

**测试数量**: 15 个测试用例
**难度分布**:
- 简单 (6个): 单一任务委派
- 中等 (6个): 多任务协调
- 复杂 (3个): 跨部门/跨系统协调

**评分维度**:
- 任务拆解能力 (40%)
- 委派执行者识别 (30%)
- 约束遵循度 (30%)

---

### 测试二：逻辑执行测试 (Logic Execution Tests)
**目的**: 测试 agent 在被要求使用成熟框架和最佳实践时，是否能记住并应用这些要求。

**测试数量**: 15 个测试用例
**覆盖框架**:
- FastAPI + Pydantic
- SQLAlchemy + Alembic
- Celery + Redis
- Docker + docker-compose
- pytest + pytest-asyncio
- JWT认证方案

**评分维度**:
- 框架使用正确性 (35%)
- 反模式避免度 (35%)
- 架构质量 (30%)

---

### 测试二-一：10轮App开发测试 (10-Round App Development)
**目的**: 模拟一个完整的项目开发周期，测试 agent 在多轮迭代后是否仍能记住初始诉求。

**场景**: TaskMaster 待办事项 App
**技术栈**: FastAPI + React + PostgreSQL

**10轮任务**:
1. 项目初始化
2. 数据库模型设计
3. API接口实现
4. 用户认证系统
5. 任务列表功能
6. 任务提醒功能
7. 数据分析功能
8. 前端界面优化
9. 性能优化
10. 最终验收测试

**最终测试问题**:
```
1. 这个项目叫什么名字？使用什么技术栈？
2. API设计遵循什么规范？输入验证用什么？
3. 用户认证使用什么方案？
4. 异步任务用什么工具？
5. 前端UI组件用什么库？
6. 数据库迁移用什么工具？
7. 整个项目的核心架构原则是什么？
```

---

### 测试三：用户习惯测试 (User Habit Tests)
**目的**: 测试 agent 是否能记住用户的多维度偏好，并在后续交互中一致地应用。

**测试数量**: 15 个测试用例
**用户画像类型**:
- 技术直男型 (偏好直接技术方案)
- 简洁至上型 (偏好最小代码)
- 文档狂人型 (偏好完整文档)
- 测试驱动型 (偏好TDD)
- Markdown爱好者 (偏好格式化输出)
- 等等...

**评分维度**:
- 记忆召回率 (40%)
- 偏好应用度 (35%)
- 一致性 (25%)

---

## 运行测试

### 模拟模式（离线）
```bash
python scripts/memory_test_runner.py --simulate
```

### 在线模式（需要运行中的Agent）
```bash
# 启动Agent
clawlink-agent serve --port 8430 --agent-id test-agent --memory-dir ./test_memories

# 运行测试
python scripts/memory_test_runner.py --agent-url http://127.0.0.1:8430 --output results.json
```

### 运行特定场景测试
```bash
python scripts/memory_test_scenarios.py
```

---

## 评分系统

### 评分标准
- **A (90-100)**: 优秀 - 完全理解并正确应用
- **B (80-89)**: 良好 - 基本理解，有小瑕疵
- **C (70-79)**: 及格 - 部分理解，需要改进
- **D (60-69)**: 不及格 - 理解不足
- **F (<60)**: 失败 - 完全未理解

### 通过标准
- 单项测试: ≥70分
- 整体通过率: ≥70%
- 薄弱环节: <60分的维度

---

## 测试结果解读

### 薄弱环节识别
框架会自动识别以下薄弱环节:
- **Management**: 委派意识不足、任务拆解不当
- **Logic Execution**: 硬编码、框架选择不当
- **User Habit**: 记忆召回失败、偏好应用不一致

### 改进建议
基于测试结果，框架会生成具体的改进建议，例如:
- "建议强化任务委派记忆训练"
- "建议强化架构规范记忆训练"
- "建议强化用户偏好记忆训练"

---

## 自定义测试

### 添加新的测试用例
在 `memory_test_framework.py` 中的相应生成方法中添加:

```python
def _get_management_tasks(self) -> List[Dict[str, Any]]:
    # 在列表末尾添加
    new_task = {
        'id': 18,
        'difficulty': 2,
        'task_type': 'medium',
        'title': '新任务类型',
        'context': '场景描述',
        'question': '测试问题',
        'answer': '期望答案',
        'expected_delegations': 2
    }
    return tasks + [new_task]
```

### 调整评分权重
修改 `BenchmarkScorer` 类中的权重配置:

```python
self.weights = {
    'management': {
        'delegation': 0.40,      # 调整委派权重
        'task_breakdown': 0.30,  # 调整拆解权重
        'constraint_following': 0.30
    },
    # ...
}
```

---

## 测试文件结构

```
clawlink-agent-mcp/
├── scripts/
│   ├── memory_test_framework.py    # 核心框架（生成器、评分器）
│   ├── memory_test_scenarios.py   # 场景测试（10轮开发、用户画像）
│   └── memory_test_runner.py      # 测试运行器
└── test_memories/                  # 测试记忆存储目录
```

---

## 最佳实践

1. **定期测试**: 建议每周运行一次完整测试
2. **关注薄弱环节**: 优先改进得分最低的类别
3. **渐进式提升**: 不要期望一次达到90%通过率
4. **记录趋势**: 保存历史测试结果，观察改进轨迹
5. **反馈循环**: 根据测试结果调整 Agent 的记忆训练策略
