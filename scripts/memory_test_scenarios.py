"""
Test 2-1: 10-Round App Development Memory Test
模拟一个完整的App开发项目，测试agent在多轮迭代后是否能记住初始诉求
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class RoundTask:
    round_num: int
    title: str
    user_request: str
    expected_behavior: str
    architecture_compliance: bool
    code_quality_requirements: List[str]
    user_request_emphasis: str = ""
    hints: List[str] = field(default_factory=list)


class AppDevelopmentScenario:
    """
    模拟一个待办事项App的完整开发周期
    初始诉求：使用FastAPI + React，技术债务最小化，架构清晰
    """

    def __init__(self):
        self.initial_requirements = {
            "project_name": "TaskMaster",
            "tech_stack": {
                "backend": "FastAPI",
                "frontend": "React",
                "database": "PostgreSQL + SQLAlchemy"
            },
            "key_principles": [
                "使用成熟框架，不重复造轮子",
                "模块解耦，层次分明",
                "避免硬编码，使用配置管理",
                "代码必须可测试",
                "API遵循RESTful规范"
            ],
            "initial_demand": """
用户初始诉求：
"我需要开发一个待办事项管理App叫TaskMaster。
后端必须用FastAPI，前端用React。
数据库用PostgreSQL，用ORM操作数据库。
整个架构要清晰，模块之间要解耦。
不要硬编码，所有配置都要通过环境变量或配置文件管理。
代码要能测试，每个函数最好都有单元测试。
API设计要遵循RESTful规范。
这是长期项目，后续会持续迭代，所以架构要好维护。"
            """
        }

    def get_rounds(self) -> List[RoundTask]:
        """返回10轮任务"""

        return [
            RoundTask(
                round_num=1,
                title="项目初始化",
                user_request="初始化项目结构，创建基本的FastAPI后端和React前端项目",
                expected_behavior="使用cookiecutter或官方模板创建项目，包含清晰的目录结构",
                architecture_compliance=True,
                code_quality_requirements=["目录结构清晰", "配置管理", "依赖隔离"]
            ),

            RoundTask(
                round_num=2,
                title="数据库模型设计",
                user_request="设计任务和用户的数据库模型",
                expected_behavior="使用SQLAlchemy定义User和Task模型，包含正确的关联关系",
                architecture_compliance=True,
                code_quality_requirements=["ORM模型", "关系定义", "类型提示"]
            ),

            RoundTask(
                round_num=3,
                title="API接口实现",
                user_request="实现创建、读取、更新、删除任务的API",
                expected_behavior="使用FastAPI的Router和Pydantic模型，RESTful风格",
                architecture_compliance=True,
                code_quality_requirements=["RESTful", "Pydantic验证", "错误处理"]
            ),

            RoundTask(
                round_num=4,
                title="用户认证系统",
                user_request="实现JWT用户认证",
                expected_behavior="使用python-jose生成JWT，Redis存储token，完整的登录注册流程",
                architecture_compliance=True,
                code_quality_requirements=["JWT认证", "密码哈希", "Token管理"]
            ),

            RoundTask(
                round_num=5,
                title="任务列表功能",
                user_request="实现任务列表的展示和筛选功能",
                expected_behavior="支持分页、筛选、排序，API设计合理",
                architecture_compliance=True,
                code_quality_requirements=["分页", "查询参数", "响应格式"]
            ),

            RoundTask(
                round_num=6,
                title="任务提醒功能",
                user_request="添加任务到期提醒功能",
                expected_behavior="使用Celery异步任务发送提醒",
                architecture_compliance=True,
                code_quality_requirements=["异步任务", "Celery", "定时任务"]
            ),

            RoundTask(
                round_num=7,
                title="数据分析功能",
                user_request="添加任务统计功能，显示完成率等",
                expected_behavior="使用聚合查询，不直接写SQL字符串",
                architecture_compliance=True,
                code_quality_requirements=["ORM聚合", "统计接口", "数据可视化"]
            ),

            RoundTask(
                round_num=8,
                title="前端界面优化",
                user_request="优化任务管理界面，添加拖拽排序",
                user_request_emphasis="记得用React组件库，不要自己写样式",
                expected_behavior="使用dnd-kit或react-beautiful-dnd实现拖拽",
                architecture_compliance=True,
                code_quality_requirements=["组件库", "拖拽交互", "状态管理"]
            ),

            RoundTask(
                round_num=9,
                title="性能优化",
                user_request="优化数据库查询性能，添加索引",
                user_request_emphasis="用Alembic迁移，不要直接改数据库",
                expected_behavior="使用Alembic添加索引，分析查询性能",
                architecture_compliance=True,
                code_quality_requirements=["索引优化", "Alembic迁移", "查询分析"]
            ),

            RoundTask(
                round_num=10,
                title="最终验收测试",
                user_request="检查整个项目，确认是否符合最初的架构要求",
                expected_behavior="回顾初始需求，检查架构、配置、测试覆盖",
                architecture_compliance=True,
                code_quality_requirements=["架构检查", "配置审计", "测试覆盖"]
            )
        ]

    def get_memory_prompts(self) -> Dict[int, str]:
        """返回每轮应该记住的关键记忆点"""
        return {
            1: "项目名TaskMaster，FastAPI+React架构",
            3: "API必须RESTful，用Pydantic验证",
            4: "认证用JWT+Redis，不用自己实现",
            6: "异步任务用Celery",
            8: "React用组件库，不用手写样式",
            9: "数据库用Alembic迁移"
        }

    def get_memory_test_question(self) -> str:
        """返回最终的内存测试问题"""
        return """
【最终内存测试】
请回答以下问题（基于第1轮到第9轮的开发过程）：

1. 这个项目叫什么名字？使用什么技术栈？
2. API设计遵循什么规范？输入验证用什么？
3. 用户认证使用什么方案？
4. 异步任务用什么工具？
5. 前端UI组件用什么库？
6. 数据库迁移用什么工具？
7. 整个项目的核心架构原则是什么？
"""

    def evaluate_memory_recall(self, response: str) -> Dict[str, Any]:
        """评估记忆召回情况"""
        correct_answers = {
            "project_name": ["taskmaster", "task master"],
            "tech_stack": ["fastapi", "react", "postgresql"],
            "api_style": ["restful", "rest"],
            "validation": ["pydantic"],
            "auth": ["jwt", "redis"],
            "async": ["celery"],
            "frontend": ["组件库", "component library", "dnd-kit"],
            "migration": ["alembic"],
            "principles": ["框架", "解耦", "配置", "测试"]
        }

        results = {}
        total_score = 0
        max_score = len(correct_answers)

        response_lower = response.lower()

        for key, keywords in correct_answers.items():
            found = any(kw in response_lower for kw in keywords)
            results[key] = {"correct": found, "keywords": keywords}
            if found:
                total_score += 1

        return {
            "score": round(total_score / max_score * 100, 2),
            "correct_count": total_score,
            "total_items": max_score,
            "details": results,
            "passed": total_score / max_score >= 0.7
        }


class UserHabitScenario:
    """
    Test 3: 用户画像测试
    模拟用户在不同场景下的偏好，测试agent是否能记住并应用
    """

    def __init__(self):
        self.user_profiles = []

    def get_scenarios(self) -> List[Dict[str, Any]]:
        """返回用户习惯测试场景"""
        return [
            {
                "scenario_id": "HABIT-2-1",
                "category": "communication_style",
                "title": "技术直男型",
                "rounds": [
                    {
                        "round": 1,
                        "user_says": "我是技术背景出身，说话直接，不喜欢废话，代码直接给我",
                        "agent_should_remember": "用户偏好技术直接风格"
                    },
                    {
                        "round": 2,
                        "context_reminder": "之前用户说过喜欢直接风格",
                        "test_question": "怎么实现用户登录？",
                        "expected_response_style": "直接给代码实现，跳过概念解释"
                    }
                ]
            },
            {
                "scenario_id": "HABIT-2-2",
                "category": "code_style",
                "title": "简洁至上型",
                "rounds": [
                    {
                        "round": 1,
                        "user_says": "代码要简洁，能三行解决的问题不要写三十行，少用注释",
                        "agent_should_remember": "用户偏好简洁代码"
                    },
                    {
                        "round": 2,
                        "context_reminder": "之前用户说过要简洁",
                        "test_question": "写一个字符串反转函数",
                        "expected_response_style": "最简实现，少注释"
                    }
                ]
            },
            {
                "scenario_id": "HABIT-2-3",
                "category": "documentation",
                "title": "文档狂人型",
                "rounds": [
                    {
                        "round": 1,
                        "user_says": "每个函数必须有docstring，公共API必须写完整文档",
                        "agent_should_remember": "用户要求完整文档"
                    },
                    {
                        "round": 2,
                        "context_reminder": "之前用户说过要完整文档",
                        "test_question": "实现一个工具函数",
                        "expected_response_style": "带完整docstring和用法示例"
                    }
                ]
            },
            {
                "scenario_id": "HABIT-2-4",
                "category": "testing",
                "title": "测试驱动型",
                "rounds": [
                    {
                        "round": 1,
                        "user_says": "TDD开发，先写测试再写实现",
                        "agent_should_remember": "用户要求TDD"
                    },
                    {
                        "round": 2,
                        "context_reminder": "之前用户说过TDD",
                        "test_question": "需要计算器功能",
                        "expected_response_style": "先给测试用例，再给实现"
                    }
                ]
            },
            {
                "scenario_id": "HABIT-2-5",
                "category": "format",
                "title": "Markdown爱好者",
                "rounds": [
                    {
                        "round": 1,
                        "user_says": "回答用Markdown格式，代码用代码块，中文说明",
                        "agent_should_remember": "用户要求Markdown格式"
                    },
                    {
                        "round": 2,
                        "context_reminder": "之前用户说过Markdown格式",
                        "test_question": "解释一下闭包",
                        "expected_response_style": "Markdown格式，中文，代码块"
                    }
                ]
            }
        ]

    def evaluate_habit_recall(self, response: str, scenario: Dict) -> Dict[str, Any]:
        """评估用户习惯召回"""
        first_round = scenario["rounds"][0]
        user_says = first_round["user_says"]
        expected_style = scenario["rounds"][1]["expected_response_style"]

        score = 0
        checks = []

        if "直接" in user_says or "废话" in user_says:
            if "解释" not in response[:50]:
                score += 25
                checks.append("简洁直接风格✓")
            else:
                checks.append("简洁直接风格✗")

        if "简洁" in user_says:
            lines = response.split('\n')
            if len(lines) < 15:
                score += 25
                checks.append("代码简洁✓")
            else:
                checks.append("代码简洁✗")

        if "docstring" in user_says or "文档" in user_says:
            if '"""' in response or "'''" in response:
                score += 25
                checks.append("完整文档✓")
            else:
                checks.append("完整文档✗")

        if "Markdown" in user_says or "markdown" in user_says:
            if '```' in response:
                score += 25
                checks.append("Markdown格式✓")
            else:
                checks.append("Markdown格式✗")

        return {
            "score": score,
            "checks": checks,
            "passed": score >= 75
        }


def run_app_development_test() -> Dict[str, Any]:
    """运行10轮App开发测试"""
    scenario = AppDevelopmentScenario()

    print("\n" + "="*60)
    print("Test 2-1: 10-Round App Development Memory Test")
    print("="*60)
    print("\n【初始诉求】")
    print(scenario.initial_requirements["initial_demand"])

    results = {
        "initial_requirements": scenario.initial_requirements["initial_demand"],
        "rounds": [],
        "memory_test": None
    }

    for round_task in scenario.get_rounds():
        print(f"\n--- Round {round_task.round_num}: {round_task.title} ---")
        print(f"User: {round_task.user_request}")
        print(f"Expected: {round_task.expected_behavior}")
        print(f"Architecture Compliance: {round_task.architecture_compliance}")

        results["rounds"].append({
            "round": round_task.round_num,
            "title": round_task.title,
            "request": round_task.user_request,
            "expected": round_task.expected_behavior,
            "compliant": round_task.architecture_compliance
        })

    print("\n" + "="*60)
    print("MEMORY RECALL TEST")
    print("="*60)
    print(scenario.get_memory_test_question())

    return results


def run_user_habit_test() -> Dict[str, Any]:
    """运行用户习惯测试"""
    scenario = UserHabitScenario()

    print("\n" + "="*60)
    print("Test 3: User Habit Memory Test")
    print("="*60)

    results = {
        "scenarios": [],
        "overall_score": 0
    }

    for scenario_data in scenario.get_scenarios():
        print(f"\nScenario: {scenario_data['scenario_id']} - {scenario_data['title']}")

        for round_info in scenario_data["rounds"]:
            if "user_says" in round_info:
                print(f"  Round {round_info['round']}: User: {round_info['user_says']}")
            else:
                print(f"  Test: {round_info['test_question']}")
                print(f"  Expected Style: {round_info['expected_response_style']}")

        results["scenarios"].append({
            "id": scenario_data["scenario_id"],
            "title": scenario_data["title"],
            "category": scenario_data["category"]
        })

    return results


if __name__ == "__main__":
    print("CLAWLINK-AGENT Memory Test Suite")
    print("="*60)

    app_results = run_app_development_test()
    habit_results = run_user_habit_test()

    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"App Development Test: {len(app_results['rounds'])} rounds completed")
    print(f"User Habit Test: {len(habit_results['scenarios'])} scenarios")
