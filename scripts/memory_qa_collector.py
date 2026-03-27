"""
CLAWLINK-AGENT Memory Q&A Collector
问答收集器 - 向 Agent 发送问题并记录所有回答，不自行评分
结果可交给另一个 AI 进行客观评分
"""

import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field
import asyncio
import time
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.memory_test_framework import (
    TestDataGenerator,
    TestCase,
    TestCategory,
    BenchmarkScorer,
)
from scripts.memory_test_scenarios import AppDevelopmentScenario


@dataclass
class QARecord:
    """问答记录 - 包含问题、上下文和回答"""
    case_id: str
    category: str
    difficulty: int
    title: str

    question: str
    context: str
    correct_answer: str
    evaluation_criteria: List[str]

    agent_response: str = ""
    memory_keywords: List[str] = field(default_factory=list)
    response_valid: bool = False
    response_attempts: int = 0
    raw_response: Dict[str, Any] = field(default_factory=dict)
    recall_enabled: bool = True
    capture_memory: bool = True
    variant: str = "default"
    response_latency_ms: float = 0.0
    recalled_memory_topics: List[str] = field(default_factory=list)
    recall_relevance_score: float = 0.0
    recall_relevance_reason: str = ""
    response_uses_recall: bool = False
    heuristic_score: Optional[float] = None
    heuristic_passed: Optional[bool] = None

    timestamp: str = ""
    notes: str = ""


class MemoryQACollector:
    """问答收集器 - 与 Agent 一问一答，记录所有回答"""

    def __init__(self, agent_url: str = "http://127.0.0.1:8430", session_id: str = None):
        self.agent_url = agent_url.rstrip('/')
        self.session_id = session_id or f"qa-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.generator = TestDataGenerator(seed=42)
        self.scorer = BenchmarkScorer()
        self.app_scenario = AppDevelopmentScenario()
        self.qa_records: List[QARecord] = []
        self.max_reasks = 2
        self.retry_interval_seconds = 2

    async def check_agent_health(self) -> bool:
        """检查 Agent 是否在线"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.agent_url}/ping")
                return response.status_code == 200
        except Exception as e:
            print(f"❌ Agent 健康检查失败: {e}")
            return False

    async def send_message(
        self,
        content: str,
        *,
        capture_memory: bool = True,
        recall_enabled: bool = True,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """发送消息到 Agent 并获取响应"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "sender_id": "qa-collector",
                    "session_id": session_id or self.session_id,
                    "content": content,
                    "metadata": {
                        "capture_memory": capture_memory,
                        "use_memory_recall": recall_enabled,
                    }
                }
                response = await client.post(f"{self.agent_url}/message", json=payload)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict):
                    return data
                return {"response": "", "error": "invalid_response_payload"}
        except Exception as e:
            print(f"❌ 发送消息失败: {e}")
            return {"response": "", "error": str(e)}

    def _extract_response_text(self, payload: Dict[str, Any]) -> str:
        if not isinstance(payload, dict):
            return ""

        candidate_fields = ["response", "content", "answer", "message", "text"]
        for field in candidate_fields:
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()

        nested = payload.get("data")
        if isinstance(nested, dict):
            for field in candidate_fields:
                value = nested.get(field)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ""

    def _is_placeholder_response(self, text: str) -> bool:
        lowered = (text or "").strip().lower()
        if not lowered:
            return True
        placeholders = [
            "no relevant memories recalled",
            "relevant memories recalled:",
        ]
        return any(token in lowered for token in placeholders)

    def _tokenize_text(self, text: str) -> List[str]:
        import re

        return re.findall(r"[a-zA-Z0-9\u4e00-\u9fff_\-]{2,}", (text or "").lower())

    def _analyze_recall_usage(self, test_case: TestCase, payload: Dict[str, Any], response_text: str) -> Dict[str, Any]:
        recalled = payload.get("recalled_memories", []) if isinstance(payload, dict) else []
        if not isinstance(recalled, list):
            recalled = []

        recalled_topics: List[str] = []
        recalled_tokens: set[str] = set()
        for item in recalled[:3]:
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic", "")).strip()
            if topic:
                recalled_topics.append(topic)
                recalled_tokens.update(self._tokenize_text(topic))
            for highlight in item.get("transcript_highlights", [])[:1]:
                recalled_tokens.update(self._tokenize_text(str(highlight)))

        expected_tokens = set(self._tokenize_text(" ".join(test_case.memory_keywords + [test_case.question, test_case.context])))
        if recalled_tokens and expected_tokens:
            overlap = recalled_tokens & expected_tokens
            score = round(len(overlap) / max(len(expected_tokens), 1) * 100, 2)
        else:
            overlap = set()
            score = 0.0

        response_tokens = set(self._tokenize_text(response_text))
        used_overlap = recalled_tokens & response_tokens
        uses_recall = bool(used_overlap)

        if not recalled_topics:
            reason = "no_recall"
        elif score >= 35:
            reason = "recalled_topics_overlap_with_expected_context"
        elif score > 0:
            reason = "recalled_topics_partially_related"
        else:
            reason = "recalled_topics_not_related_to_expected_context"

        return {
            "recalled_memory_topics": recalled_topics,
            "recall_relevance_score": score,
            "recall_relevance_reason": reason,
            "response_uses_recall": uses_recall,
            "recall_overlap_tokens": sorted(list(overlap))[:12],
            "response_recall_overlap_tokens": sorted(list(used_overlap))[:12],
        }

    def _score_case(self, test_case: TestCase, response_text: str, recalled_topics: List[str]) -> Dict[str, Any]:
        if test_case.category == TestCategory.MANAGEMENT.value:
            return self.scorer.score_management_test(response_text, test_case)
        if test_case.category == TestCategory.LOGIC_EXECUTION.value:
            return self.scorer.score_logic_test(response_text, test_case)
        return self.scorer.score_user_habit_test(response_text, test_case, recalled_topics)

    async def ask_with_retry(
        self,
        full_question: str,
        *,
        capture_memory: bool = True,
        recall_enabled: bool = True,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        attempts = 0
        last_payload: Dict[str, Any] = {}
        last_text = ""
        started = time.perf_counter()

        max_attempts = 1 + self.max_reasks
        while attempts < max_attempts:
            attempts += 1
            if attempts == 1:
                prompt = full_question
            else:
                prompt = "请直接回答上一条问题，不要只返回记忆召回摘要。"

            last_payload = await self.send_message(
                prompt,
                capture_memory=capture_memory,
                recall_enabled=recall_enabled,
                session_id=session_id,
            )
            last_text = self._extract_response_text(last_payload)

            if last_text and not self._is_placeholder_response(last_text):
                break

            if attempts < max_attempts:
                print(f"⚠️ 未拿到有效回答，{self.retry_interval_seconds}s 后重试 ({attempts}/{max_attempts})...")
                await asyncio.sleep(self.retry_interval_seconds)

        return {
            "payload": last_payload,
            "text": last_text,
            "attempts": attempts,
            "valid": bool(last_text and not self._is_placeholder_response(last_text)),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    async def ask_question(
        self,
        test_case: TestCase,
        *,
        recall_enabled: bool = True,
        capture_memory: bool = True,
        variant: str = "default",
        session_id: Optional[str] = None,
    ) -> QARecord:
        """向 Agent 发送问题并记录回答"""
        full_question = f"{test_case.context}\n\n【问题】{test_case.question}"

        print(f"\n{'='*70}")
        print(f"📤 发送问题 [{test_case.case_id}]: {test_case.title}")
        print(f"{'='*70}")
        print(f"📋 上下文: {test_case.context[:100]}...")
        print(f"❓ 问题: {test_case.question[:100]}...")
        print(f"\n⏳ 等待 Agent 回答...")

        asked = await self.ask_with_retry(
            full_question,
            capture_memory=capture_memory,
            recall_enabled=recall_enabled,
            session_id=session_id,
        )
        agent_response = asked["text"]
        recall_analysis = self._analyze_recall_usage(test_case, asked["payload"], agent_response)
        heuristic = self._score_case(test_case, agent_response, recall_analysis["recalled_memory_topics"])

        print(f"\n📥 Agent 回答:")
        print(f"{'-'*50}")
        print(agent_response[:500] + "..." if len(agent_response) > 500 else agent_response)
        print(
            f"\n有效回答: {'是' if asked['valid'] else '否'} | 尝试次数: {asked['attempts']} | "
            f"召回相关性: {recall_analysis['recall_relevance_score']:.1f}"
        )
        print(f"{'-'*50}")

        return QARecord(
            case_id=test_case.case_id,
            category=test_case.category,
            difficulty=test_case.difficulty,
            title=test_case.title,
            question=test_case.question,
            context=test_case.context,
            correct_answer=test_case.correct_answer,
            evaluation_criteria=test_case.evaluation_criteria,
            agent_response=agent_response,
            memory_keywords=test_case.memory_keywords,
            response_valid=asked["valid"],
            response_attempts=asked["attempts"],
            raw_response=asked["payload"],
            recall_enabled=recall_enabled,
            capture_memory=capture_memory,
            variant=variant,
            response_latency_ms=asked["latency_ms"],
            recalled_memory_topics=recall_analysis["recalled_memory_topics"],
            recall_relevance_score=recall_analysis["recall_relevance_score"],
            recall_relevance_reason=recall_analysis["recall_relevance_reason"],
            response_uses_recall=recall_analysis["response_uses_recall"],
            heuristic_score=heuristic.get("total_score"),
            heuristic_passed=heuristic.get("passed"),
            timestamp=datetime.now().isoformat()
        )

    async def run_ab_comparison_for_cases(self, cases: List[TestCase], category: str) -> Dict[str, Any]:
        """Run per-case comparison with memory recall on vs off."""
        print("\n" + "#"*70)
        print(f"#  A/B Memory Comparison: {category}")
        print("#  A = recall enabled, B = recall disabled")
        print("#"*70)

        comparisons: List[Dict[str, Any]] = []
        summary = {
            "cases": 0,
            "avg_score_with_memory": 0.0,
            "avg_score_without_memory": 0.0,
            "avg_score_delta": 0.0,
            "avg_recall_relevance_with_memory": 0.0,
            "memory_helped_cases": 0,
        }

        for index, case in enumerate(cases, start=1):
            print(f"\n[{index}/{len(cases)}] A/B {case.case_id}: {case.title}")
            record_on = await self.ask_question(
                case,
                recall_enabled=True,
                capture_memory=False,
                variant="memory_on",
                session_id=f"{self.session_id}-ab-on-{case.case_id}",
            )
            record_off = await self.ask_question(
                case,
                recall_enabled=False,
                capture_memory=False,
                variant="memory_off",
                session_id=f"{self.session_id}-ab-off-{case.case_id}",
            )

            self.qa_records.extend([record_on, record_off])
            comparisons.append({
                "case_id": case.case_id,
                "category": case.category,
                "title": case.title,
                "with_memory": asdict(record_on),
                "without_memory": asdict(record_off),
                "score_delta": round((record_on.heuristic_score or 0.0) - (record_off.heuristic_score or 0.0), 2),
                "latency_delta_ms": round(record_on.response_latency_ms - record_off.response_latency_ms, 2),
            })

        if comparisons:
            summary["cases"] = len(comparisons)
            summary["avg_score_with_memory"] = round(sum(c["with_memory"]["heuristic_score"] or 0.0 for c in comparisons) / len(comparisons), 2)
            summary["avg_score_without_memory"] = round(sum(c["without_memory"]["heuristic_score"] or 0.0 for c in comparisons) / len(comparisons), 2)
            summary["avg_score_delta"] = round(sum(c["score_delta"] for c in comparisons) / len(comparisons), 2)
            summary["avg_recall_relevance_with_memory"] = round(sum(c["with_memory"]["recall_relevance_score"] for c in comparisons) / len(comparisons), 2)
            summary["memory_helped_cases"] = sum(1 for c in comparisons if c["score_delta"] > 0)

        return {
            "session_id": self.session_id,
            "mode": "ab_comparison",
            "category": category,
            "summary": summary,
            "comparisons": comparisons,
        }

    async def run_app_development_scenario(self) -> Dict[str, Any]:
        """Run the 10-round app-development memory scenario and final recall check."""
        print("\n" + "#"*70)
        print("#  10-Round App Development Scenario")
        print("#"*70)

        rounds_output: List[Dict[str, Any]] = []
        scenario_session = f"{self.session_id}-app-scenario"

        for round_task in self.app_scenario.get_rounds():
            prompt = self.app_scenario.initial_requirements["initial_demand"].strip() if round_task.round_num == 1 else ""
            if prompt:
                prompt += "\n\n"
            prompt += f"第{round_task.round_num}轮任务：{round_task.user_request}"
            if round_task.user_request_emphasis:
                prompt += f"\n补充要求：{round_task.user_request_emphasis}"

            synthetic_case = TestCase(
                case_id=f"APP-{round_task.round_num:02d}",
                category="app_development",
                difficulty=round_task.round_num,
                title=round_task.title,
                context=prompt,
                question=round_task.user_request,
                correct_answer=round_task.expected_behavior,
                agent_constraints=round_task.code_quality_requirements,
                evaluation_criteria=round_task.code_quality_requirements,
                memory_keywords=self._tokenize_text(round_task.user_request + " " + round_task.expected_behavior)[:8],
                distraction_factors=[],
                metadata={"round": round_task.round_num},
            )
            record = await self.ask_question(
                synthetic_case,
                recall_enabled=True,
                capture_memory=True,
                variant="scenario_round",
                session_id=scenario_session,
            )
            self.qa_records.append(record)
            rounds_output.append(asdict(record))
            await asyncio.sleep(1)

        final_question = self.app_scenario.get_memory_test_question().strip()
        final_case = TestCase(
            case_id="APP-MEMORY-FINAL",
            category="app_development",
            difficulty=3,
            title="10轮最终记忆测试",
            context="请仅基于前9轮开发过程回答。",
            question=final_question,
            correct_answer="TaskMaster / FastAPI / React / PostgreSQL / RESTful / Pydantic / JWT / Redis / Celery / Alembic",
            agent_constraints=[],
            evaluation_criteria=[],
            memory_keywords=["TaskMaster", "FastAPI", "React", "PostgreSQL", "Pydantic", "JWT", "Redis", "Celery", "Alembic"],
            distraction_factors=[],
            metadata={},
        )
        final_record = await self.ask_question(
            final_case,
            recall_enabled=True,
            capture_memory=False,
            variant="scenario_final_memory_check",
            session_id=scenario_session,
        )
        self.qa_records.append(final_record)
        memory_eval = self.app_scenario.evaluate_memory_recall(final_record.agent_response)

        return {
            "session_id": self.session_id,
            "mode": "app_development_scenario",
            "initial_requirements": self.app_scenario.initial_requirements,
            "round_records": rounds_output,
            "final_memory_record": asdict(final_record),
            "memory_recall_evaluation": memory_eval,
        }

    async def run_management_tests(self, count: int = 15) -> List[QARecord]:
        """运行管理驱动测试"""
        print("\n" + "="*70)
        print("📋 TEST 1: 管理驱动测试 (Management-Driven Tests)")
        print("="*70)
        print(f"测试目标: 验证 Agent 是否能记住委派原则")
        print(f"测试数量: {count} 个问题")
        print("="*70)

        mgmt_cases = self.generator.generate_management_test_cases(count)
        records = []

        for i, case in enumerate(mgmt_cases):
            print(f"\n[{i+1}/{count}] 进度: {i+1}/{count}")
            record = await self.ask_question(case)
            records.append(record)
            self.qa_records.append(record)

            await asyncio.sleep(1)

        return records

    async def run_logic_tests(self, count: int = 15) -> List[QARecord]:
        """运行逻辑执行测试"""
        print("\n" + "="*70)
        print("📋 TEST 2: 逻辑执行测试 (Logic Execution Tests)")
        print("="*70)
        print(f"测试目标: 验证 Agent 是否能记住使用成熟框架")
        print(f"测试数量: {count} 个问题")
        print("="*70)

        logic_cases = self.generator.generate_logic_execution_test_cases(count)
        records = []

        for i, case in enumerate(logic_cases):
            print(f"\n[{i+1}/{count}] 进度: {i+1}/{count}")
            record = await self.ask_question(case)
            records.append(record)
            self.qa_records.append(record)

            await asyncio.sleep(1)

        return records

    async def run_user_habit_tests(self, count: int = 15) -> List[QARecord]:
        """运行用户习惯测试"""
        print("\n" + "="*70)
        print("📋 TEST 3: 用户习惯测试 (User Habit Tests)")
        print("="*70)
        print(f"测试目标: 验证 Agent 是否能记住用户偏好")
        print(f"测试数量: {count} 个问题")
        print("="*70)

        habit_cases = self.generator.generate_user_habit_test_cases(count)
        records = []

        for i, case in enumerate(habit_cases):
            print(f"\n[{i+1}/{count}] 进度: {i+1}/{count}")
            record = await self.ask_question(case)
            records.append(record)
            self.qa_records.append(record)

            await asyncio.sleep(1)

        return records

    async def run_all_tests(self) -> Dict[str, Any]:
        """运行所有测试"""
        print("\n" + "#"*70)
        print("#  CLAWLINK-AGENT Memory Q&A 收集器")
        print("#  目标: 收集 Agent 的回答，交给另一个 AI 评分")
        print("#"*70)

        is_healthy = await self.check_agent_health()
        if not is_healthy:
            print(f"\n❌ Agent ({self.agent_url}) 未响应或离线")
            print("请确保 Agent 服务正在运行:")
            print(f"   clawlink-agent serve --port 8430")
            return {"error": "Agent not responding"}

        print(f"\n✅ Agent 连接成功: {self.agent_url}")
        print(f"📝 Session ID: {self.session_id}")
        print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        all_records = []

        management_records = await self.run_management_tests(15)
        all_records.extend(management_records)

        logic_records = await self.run_logic_tests(15)
        all_records.extend(logic_records)

        habit_records = await self.run_user_habit_tests(15)
        all_records.extend(habit_records)

        print("\n" + "#"*70)
        print(f"#  测试完成！共收集 {len(all_records)} 个问答")
        print(f"#  结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("#"*70)

        return {
            "session_id": self.session_id,
            "start_time": datetime.now().isoformat(),
            "end_time": datetime.now().isoformat(),
            "total_records": len(all_records),
            "categories": {
                "management": len(management_records),
                "logic_execution": len(logic_records),
                "user_habit": len(habit_records)
            },
            "qa_records": [asdict(r) for r in all_records]
        }

    def _build_prompt_sections(self) -> str:
        return """

## 额外字段解释（用于判断记忆是否真的产生价值）

- `recall_enabled`: 本轮是否开启记忆召回
- `recalled_memory_topics`: 实际召回的记忆主题
- `recall_relevance_score`: 召回内容与当前问题/预期上下文的相关性启发式分数
- `response_uses_recall`: 回答文本是否明显使用了召回内容
- `heuristic_score`: 本地启发式评分，仅用于 A/B 对照参考，不替代客观 AI 评分

## 记忆价值判断要求

- 不只判断回答是否正确，还要判断开启记忆后，回答是否比关闭记忆时更准确、更一致或更贴近历史约束。
- 如果 `recall_enabled=true` 但 `recall_relevance_score` 很低，或 `response_uses_recall=false`，说明记忆系统可能没有真正帮助回答。
- 在 A/B 结果中，若 `score_delta <= 0`，则不能声称“记忆增强有效”。
"""

    def save_results(self, results: Dict[str, Any], output_file: str = None) -> str:
        """保存测试结果到 JSON 文件"""
        if output_file is None:
            output_file = f"qa_results_{self.session_id}.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 结果已保存到: {output_file}")
        return output_file

    def generate_evaluation_prompt(self, output_file: str = None) -> str:
        """生成可交给另一个 AI 的评分提示"""
        prompt = """# CLAWLINK-AGENT Memory Test 评分任务

你是评分专家。请根据以下评分标准，对收集到的 Q&A 结果进行客观评分。

## 评分标准

### 1. 管理驱动测试 (Management Tests)
权重: 40% 委派意识 + 30% 任务拆解 + 30% 约束遵循

- **委派意识 (40%)**: Agent 是否正确将任务分配给其他 Agent，而非自己执行
- **任务拆解 (30%)**: Agent 是否将复杂任务拆解为多个子任务
- **约束遵循 (30%)**: Agent 是否遵循"不能使用 subagent 执行"的约束

### 2. 逻辑执行测试 (Logic Execution Tests)
权重: 35% 框架使用 + 35% 反模式避免 + 30% 架构质量

- **框架使用 (35%)**: Agent 是否正确使用指定的成熟框架
- **反模式避免 (35%)**: Agent 是否避免硬编码、magic number 等反模式
- **架构质量 (30%)**: Agent 是否遵循分层、解耦等架构原则

### 3. 用户习惯测试 (User Habit Tests)
权重: 40% 记忆召回 + 35% 偏好应用 + 25% 一致性

- **记忆召回 (40%)**: Agent 是否正确回忆用户的偏好
- **偏好应用 (35%)**: Agent 是否将用户偏好应用到回答中
- **一致性 (25%)**: Agent 的回答是否与用户之前表达的一致

## 评分等级

| 等级 | 分数 | 说明 |
|------|------|------|
| A | 90-100 | 完全正确，优秀 |
| B | 80-89 | 基本正确，有小瑕疵 |
| C | 70-79 | 部分正确，需改进 |
| D | 60-69 | 较差，需要大幅改进 |
| F | <60 | 完全不正确 |

## 输出格式

请对每个 Q&A 记录进行评分，并输出：

```json
{
  "case_id": "MGMT-01",
  "category": "management",
  "score": 85,
  "grade": "B",
  "strengths": ["...", "..."],
  "weaknesses": ["...", "..."],
  "reasoning": "评分理由..."
}
```

## 强制判定规则（避免空回答误判）

- 若 `agent_response` 为空、仅空白、或仅包含记忆召回占位语（如 `No relevant memories recalled` / `Relevant memories recalled`），该条 **总分必须为 0，等级 F**。
- 若回答与问题无关，只复述历史片段而未回答当前问题，最高不超过 20 分。
- 评分时优先参考 `agent_response`，`correct_answer` 仅作为目标对照，不可反向推断给高分。

## 需要评分的 Q&A 结果

请读取以下 JSON 文件获取 Q&A 数据:
"""
        if output_file:
            prompt += self._build_prompt_sections()
            prompt += f"\n```\n{output_file}\n```"
        return prompt


async def main():
    parser = argparse.ArgumentParser(
        description="CLAWLINK-AGENT Q&A 收集器 - 向 Agent 发送问题并记录回答"
    )
    parser.add_argument("--agent-url", default="http://127.0.0.1:8430", help="Agent URL")
    parser.add_argument("--session-id", help="Session ID (可选)")
    parser.add_argument("--output", help="输出文件路径")
    parser.add_argument("--management-only", action="store_true", help="只运行管理测试")
    parser.add_argument("--logic-only", action="store_true", help="只运行逻辑测试")
    parser.add_argument("--habit-only", action="store_true", help="只运行习惯测试")
    parser.add_argument("--ab-category", choices=["management", "logic_execution", "user_habit"], help="运行记忆开关A/B对照测试")
    parser.add_argument("--app-scenario", action="store_true", help="运行10轮App开发记忆场景")
    parser.add_argument("--count", type=int, default=15, help="每个类别的问题数量")

    args = parser.parse_args()

    collector = MemoryQACollector(
        agent_url=args.agent_url,
        session_id=args.session_id
    )

    is_healthy = await collector.check_agent_health()
    if not is_healthy:
        print(f"\n❌ 错误: Agent ({args.agent_url}) 未响应")
        print("请先启动 Agent 服务:")
        print(f"   clawlink-agent serve --port 8430")
        sys.exit(1)

    results = {}

    if args.ab_category:
        if args.ab_category == "management":
            cases = collector.generator.generate_management_test_cases(args.count)
        elif args.ab_category == "logic_execution":
            cases = collector.generator.generate_logic_execution_test_cases(args.count)
        else:
            cases = collector.generator.generate_user_habit_test_cases(args.count)
        results = await collector.run_ab_comparison_for_cases(cases, args.ab_category)
    elif args.app_scenario:
        results = await collector.run_app_development_scenario()
    elif args.management_only:
        records = await collector.run_management_tests(args.count)
        results = {
            "session_id": collector.session_id,
            "total_records": len(records),
            "category": "management",
            "qa_records": [asdict(r) for r in records]
        }
    elif args.logic_only:
        records = await collector.run_logic_tests(args.count)
        results = {
            "session_id": collector.session_id,
            "total_records": len(records),
            "category": "logic_execution",
            "qa_records": [asdict(r) for r in records]
        }
    elif args.habit_only:
        records = await collector.run_user_habit_tests(args.count)
        results = {
            "session_id": collector.session_id,
            "total_records": len(records),
            "category": "user_habit",
            "qa_records": [asdict(r) for r in records]
        }
    else:
        results = await collector.run_all_tests()

    output_file = args.output
    if output_file:
        collector.save_results(results, output_file)

        prompt = collector.generate_evaluation_prompt(output_file)
        prompt_file = output_file.replace('.json', '_evaluation_prompt.md')
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)
        print(f"✅ 评分提示已保存到: {prompt_file}")

    return results


if __name__ == "__main__":
    asyncio.run(main())
