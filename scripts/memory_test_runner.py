"""
CLAWLINK-AGENT Memory Test Runner
主测试运行器 - 执行测试、收集结果、生成报告
"""

import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import asyncio
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.memory_test_framework import (
    TestDataGenerator,
    BenchmarkScorer,
    TestCase,
    TestResult,
    TestCategory
)
from scripts.memory_test_scenarios import (
    AppDevelopmentScenario,
    UserHabitScenario
)


class MemoryTestRunner:
    """测试运行器 - 与MCP交互执行测试"""

    def __init__(self, agent_url: str = "http://127.0.0.1:8430", memory_dir: str = None):
        self.agent_url = agent_url.rstrip('/')
        self.memory_dir = memory_dir or "./test_memories"
        self.generator = TestDataGenerator(seed=42)
        self.scorer = BenchmarkScorer()
        self.results: List[TestResult] = []

    async def check_agent_health(self) -> bool:
        """检查agent是否在线"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.agent_url}/ping")
                return response.status_code == 200
        except Exception as e:
            print(f"Agent health check failed: {e}")
            return False

    async def send_message(self, content: str, capture_memory: bool = True) -> Dict[str, Any]:
        """发送消息到agent并获取响应"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "sender_id": "test-runner",
                    "session_id": "test-session",
                    "content": content,
                    "metadata": {"capture_memory": capture_memory}
                }
                response = await client.post(f"{self.agent_url}/message", json=payload)
                return response.json()
        except Exception as e:
            print(f"Failed to send message: {e}")
            return {"response": "", "error": str(e)}

    async def save_memory(self, entry: Dict[str, Any]) -> str:
        """手动保存记忆"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(f"{self.agent_url}/memory/save", json=entry)
                data = response.json()
                return data.get("memory_id", "")
        except Exception as e:
            print(f"Failed to save memory: {e}")
            return ""

    async def search_memories(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """搜索记忆"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.agent_url}/memory/search",
                    json={"query": query, "top_k": top_k}
                )
                return response.json()
        except Exception as e:
            print(f"Failed to search memories: {e}")
            return []

    async def run_management_test(self, test_case: TestCase) -> TestResult:
        """运行管理驱动测试"""
        context_msg = f"{test_case.context}\n\n现在请回答: {test_case.question}"
        response_data = await self.send_message(context_msg)
        response = response_data.get("response", "") or response_data.get("content", "")

        recalled = await self.search_memories(" ".join(test_case.memory_keywords[:3]))
        recalled_topics = [m.get("topic", "") for m in recalled[:3]]

        evaluation = self.scorer.score_management_test(response, test_case)

        return TestResult(
            case_id=test_case.case_id,
            category=test_case.category,
            passed=evaluation["passed"],
            score=evaluation["total_score"],
            agent_response=response,
            evaluation_details=evaluation,
            memory_recalled=recalled_topics,
            timestamp=datetime.now().isoformat()
        )

    async def run_logic_test(self, test_case: TestCase) -> TestResult:
        """运行逻辑执行测试"""
        context_msg = f"{test_case.context}\n\n现在请回答: {test_case.question}"
        response_data = await self.send_message(context_msg)
        response = response_data.get("response", "") or response_data.get("content", "")

        recalled = await self.search_memories(" ".join(test_case.memory_keywords[:3]))
        recalled_topics = [m.get("topic", "") for m in recalled[:3]]

        evaluation = self.scorer.score_logic_test(response, test_case)

        return TestResult(
            case_id=test_case.case_id,
            category=test_case.category,
            passed=evaluation["passed"],
            score=evaluation["total_score"],
            agent_response=response,
            evaluation_details=evaluation,
            memory_recalled=recalled_topics,
            timestamp=datetime.now().isoformat()
        )

    async def run_user_habit_test(self, test_case: TestCase) -> TestResult:
        """运行用户习惯测试"""
        context_msg = f"{test_case.context}\n\n现在请回答: {test_case.question}"
        response_data = await self.send_message(context_msg)
        response = response_data.get("response", "") or response_data.get("content", "")

        recalled = await self.search_memories(" ".join(test_case.memory_keywords[:3]))
        recalled_topics = [m.get("topic", "") for m in recalled[:3]]

        evaluation = self.scorer.score_user_habit_test(response, test_case, recalled_topics)

        return TestResult(
            case_id=test_case.case_id,
            category=test_case.category,
            passed=evaluation["passed"],
            score=evaluation["total_score"],
            agent_response=response,
            evaluation_details=evaluation,
            memory_recalled=recalled_topics,
            timestamp=datetime.now().isoformat()
        )

    async def run_all_tests(self, verbose: bool = False) -> Dict[str, Any]:
        """运行所有测试"""
        print("\n" + "="*70)
        print("CLAWLINK-AGENT Memory Test Suite")
        print("="*70)

        is_healthy = await self.check_agent_health()
        if not is_healthy:
            print(f"Warning: Agent at {self.agent_url} is not responding.")
            print("Running in simulation mode...")

        all_results = []

        print("\n" + "-"*70)
        print("TEST 1: Management-Driven Memory Tests")
        print("-"*70)
        mgmt_cases = self.generator.generate_management_test_cases(15)
        for i, case in enumerate(mgmt_cases):
            print(f"\n[{i+1}/15] {case.case_id}: {case.title}")
            print(f"    Context: {case.context[:80]}...")
            print(f"    Question: {case.question[:80]}...")

            result = await self.run_management_test(case)
            self.results.append(result)
            all_results.append(result)

            status = "✓ PASS" if result.passed else "✗ FAIL"
            print(f"    Score: {result.score:.1f}/100 {status}")

        print("\n" + "-"*70)
        print("TEST 2: Logic Execution Memory Tests")
        print("-"*70)
        logic_cases = self.generator.generate_logic_execution_test_cases(15)
        for i, case in enumerate(logic_cases):
            print(f"\n[{i+1}/15] {case.case_id}: {case.title}")
            print(f"    Context: {case.context[:80]}...")
            print(f"    Question: {case.question[:80]}...")

            result = await self.run_logic_test(case)
            self.results.append(result)
            all_results.append(result)

            status = "✓ PASS" if result.passed else "✗ FAIL"
            print(f"    Score: {result.score:.1f}/100 {status}")

        print("\n" + "-"*70)
        print("TEST 3: User Habit Memory Tests")
        print("-"*70)
        habit_cases = self.generator.generate_user_habit_test_cases(15)
        for i, case in enumerate(habit_cases):
            print(f"\n[{i+1}/15] {case.case_id}: {case.title}")
            print(f"    Context: {case.context[:80]}...")
            print(f"    Question: {case.question[:80]}...")

            result = await self.run_user_habit_test(case)
            self.results.append(result)
            all_results.append(result)

            status = "✓ PASS" if result.passed else "✗ FAIL"
            print(f"    Score: {result.score:.1f}/100 {status}")

        report = self.generate_final_report(all_results)
        return report

    def generate_final_report(self, results: List[TestResult]) -> Dict[str, Any]:
        """生成最终测试报告"""
        report = {
            "test_run_timestamp": datetime.now().isoformat(),
            "total_tests": len(results),
            "overall_pass_rate": 0,
            "category_reports": {},
            "weakest_category": "",
            "recommendations": []
        }

        categories = [TestCategory.MANAGEMENT.value, TestCategory.LOGIC_EXECUTION.value, TestCategory.USER_HABIT.value]

        for category in categories:
            category_results = [r for r in results if r.category == category]
            if category_results:
                passed = sum(1 for r in category_results if r.passed)
                avg_score = sum(r.score for r in category_results) / len(category_results)
                pass_rate = passed / len(category_results) * 100

                category_report = self.scorer.generate_benchmark_report(category_results, category)
                report["category_reports"][category] = {
                    "total_cases": len(category_results),
                    "passed": passed,
                    "failed": len(category_results) - passed,
                    "pass_rate": round(pass_rate, 2),
                    "average_score": round(avg_score, 2),
                    "weak_areas": category_report.weak_areas,
                    "suggestions": category_report.improvement_suggestions
                }

        total_passed = sum(1 for r in results if r.passed)
        report["overall_pass_rate"] = round(total_passed / len(results) * 100, 2) if results else 0

        weakest = min(
            report["category_reports"].items(),
            key=lambda x: x[1]["pass_rate"]
        )
        report["weakest_category"] = weakest[0]

        if report["weakest_category"] == TestCategory.MANAGEMENT.value:
            report["recommendations"].append("建议强化任务委派记忆训练")
        elif report["weakest_category"] == TestCategory.LOGIC_EXECUTION.value:
            report["recommendations"].append("建议强化架构规范记忆训练")
        elif report["weakest_category"] == TestCategory.USER_HABIT.value:
            report["recommendations"].append("建议强化用户偏好记忆训练")

        print("\n" + "="*70)
        print("FINAL TEST REPORT")
        print("="*70)
        print(f"\nTotal Tests: {report['total_tests']}")
        print(f"Overall Pass Rate: {report['overall_pass_rate']}%")
        print(f"\nWeakest Category: {report['weakest_category']}")

        for category, data in report["category_reports"].items():
            print(f"\n{category.upper()}:")
            print(f"  Pass Rate: {data['pass_rate']}%")
            print(f"  Average Score: {data['average_score']}/100")
            if data['weak_areas']:
                print(f"  Weak Areas: {', '.join(data['weak_areas'][:3])}")

        if report["recommendations"]:
            print(f"\nRecommendations:")
            for rec in report["recommendations"]:
                print(f"  - {rec}")

        return report

    def save_results(self, report: Dict[str, Any], output_file: str = None):
        """保存测试结果"""
        if output_file is None:
            output_file = f"memory_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "report": report,
                "results": [vars(r) for r in self.results]
            }, f, ensure_ascii=False, indent=2)

        print(f"\nResults saved to: {output_file}")


class SimulatedTestRunner:
    """模拟测试运行器 - 用于离线测试"""

    def __init__(self):
        self.generator = TestDataGenerator(seed=42)
        self.scorer = BenchmarkScorer()

    def run_simulation(self) -> Dict[str, Any]:
        """运行模拟测试"""
        print("\n" + "="*70)
        print("CLAWLINK-AGENT Memory Test Simulation (Offline Mode)")
        print("="*70)

        results = []

        print("\n" + "-"*70)
        print("TEST 1: Management-Driven Memory Tests (15 cases)")
        print("-"*70)
        mgmt_cases = self.generator.generate_management_test_cases(15)
        for i, case in enumerate(mgmt_cases):
            print(f"\n[{i+1}/15] {case.case_id}: {case.title}")
            print(f"    Context: {case.context[:60]}...")

            score = self._simulate_score(case.category, case.difficulty)
            passed = score >= 70

            result = TestResult(
                case_id=case.case_id,
                category=case.category,
                passed=passed,
                score=score,
                agent_response=f"Simulated response for {case.case_id}",
                evaluation_details={"simulated": True},
                memory_recalled=case.memory_keywords[:3],
                timestamp=datetime.now().isoformat()
            )
            results.append(result)

            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"    Score: {score:.1f}/100 {status}")

        print("\n" + "-"*70)
        print("TEST 2: Logic Execution Memory Tests (15 cases)")
        print("-"*70)
        logic_cases = self.generator.generate_logic_execution_test_cases(15)
        for i, case in enumerate(logic_cases):
            print(f"\n[{i+1}/15] {case.case_id}: {case.title}")
            print(f"    Context: {case.context[:60]}...")

            score = self._simulate_score(case.category, case.difficulty)
            passed = score >= 70

            result = TestResult(
                case_id=case.case_id,
                category=case.category,
                passed=passed,
                score=score,
                agent_response=f"Simulated response for {case.case_id}",
                evaluation_details={"simulated": True},
                memory_recalled=case.memory_keywords[:3],
                timestamp=datetime.now().isoformat()
            )
            results.append(result)

            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"    Score: {score:.1f}/100 {status}")

        print("\n" + "-"*70)
        print("TEST 3: User Habit Memory Tests (15 cases)")
        print("-"*70)
        habit_cases = self.generator.generate_user_habit_test_cases(15)
        for i, case in enumerate(habit_cases):
            print(f"\n[{i+1}/15] {case.case_id}: {case.title}")
            print(f"    Context: {case.context[:60]}...")

            score = self._simulate_score(case.category, case.difficulty)
            passed = score >= 70

            result = TestResult(
                case_id=case.case_id,
                category=case.category,
                passed=passed,
                score=score,
                agent_response=f"Simulated response for {case.case_id}",
                evaluation_details={"simulated": True},
                memory_recalled=case.memory_keywords[:3],
                timestamp=datetime.now().isoformat()
            )
            results.append(result)

            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"    Score: {score:.1f}/100 {status}")

        report = self._generate_report(results)
        return report

    def _simulate_score(self, category: str, difficulty: int) -> float:
        """模拟评分 - 基于难度和类别生成随机分数"""
        import random
        random.seed()

        base_scores = {
            TestCategory.MANAGEMENT.value: (55, 85),
            TestCategory.LOGIC_EXECUTION.value: (50, 80),
            TestCategory.USER_HABIT.value: (60, 90)
        }

        low, high = base_scores.get(category, (50, 80))
        difficulty_modifier = (3 - difficulty) * 5

        score = random.uniform(low + difficulty_modifier, high + difficulty_modifier)
        return min(max(score, 0), 100)

    def _generate_report(self, results: List[TestResult]) -> Dict[str, Any]:
        """生成测试报告"""
        passed = sum(1 for r in results if r.passed)
        avg_score = sum(r.score for r in results) / len(results) if results else 0

        category_stats = {}
        for cat in [TestCategory.MANAGEMENT.value, TestCategory.LOGIC_EXECUTION.value, TestCategory.USER_HABIT.value]:
            cat_results = [r for r in results if r.category == cat]
            if cat_results:
                cat_passed = sum(1 for r in cat_results if r.passed)
                category_stats[cat] = {
                    "total": len(cat_results),
                    "passed": cat_passed,
                    "pass_rate": round(cat_passed / len(cat_results) * 100, 2),
                    "avg_score": round(sum(r.score for r in cat_results) / len(cat_results), 2)
                }

        report = {
            "test_run_timestamp": datetime.now().isoformat(),
            "mode": "simulation",
            "total_tests": len(results),
            "overall_pass_rate": round(passed / len(results) * 100, 2) if results else 0,
            "average_score": round(avg_score, 2),
            "category_stats": category_stats,
            "weakest_category": min(category_stats.items(), key=lambda x: x[1]["pass_rate"])[0] if category_stats else None
        }

        print("\n" + "="*70)
        print("SIMULATION RESULTS")
        print("="*70)
        print(f"\nTotal: {len(results)} tests")
        print(f"Passed: {passed}")
        print(f"Pass Rate: {report['overall_pass_rate']}%")
        print(f"Average Score: {report['average_score']}/100")

        for cat, stats in category_stats.items():
            print(f"\n{cat.upper()}:")
            print(f"  Pass Rate: {stats['pass_rate']}%")
            print(f"  Avg Score: {stats['avg_score']}/100")

        return report


async def main():
    parser = argparse.ArgumentParser(description="CLAWLINK-AGENT Memory Test Runner")
    parser.add_argument("--agent-url", default="http://127.0.0.1:8430", help="Agent URL")
    parser.add_argument("--memory-dir", help="Memory directory")
    parser.add_argument("--output", help="Output file for results")
    parser.add_argument("--simulate", action="store_true", help="Run simulation mode")

    args = parser.parse_args()

    if args.simulate:
        runner = SimulatedTestRunner()
        report = runner.run_simulation()
    else:
        runner = MemoryTestRunner(agent_url=args.agent_url, memory_dir=args.memory_dir)
        report = await runner.run_all_tests()
        runner.save_results(report, args.output)

    return report


if __name__ == "__main__":
    asyncio.run(main())
