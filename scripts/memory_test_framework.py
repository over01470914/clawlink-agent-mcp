"""
CLAWLINK-AGENT Memory Test Framework
测试框架核心模块 - 定义测试数据生成、评分系统和运行逻辑
"""

import json
import random
import hashlib
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum
import re


class TestCategory(Enum):
    MANAGEMENT = "management"
    LOGIC_EXECUTION = "logic_execution"
    USER_HABIT = "user_habit"


class Difficulty(Enum):
    EASY = 1
    MEDIUM = 2
    HARD = 3


@dataclass
class TestCase:
    case_id: str
    category: str
    difficulty: int
    title: str
    context: str
    question: str
    correct_answer: str
    agent_constraints: List[str]
    evaluation_criteria: List[str]
    memory_keywords: List[str]
    distraction_factors: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TestResult:
    case_id: str
    category: str
    passed: bool
    score: float
    agent_response: str
    evaluation_details: Dict[str, Any]
    memory_recalled: List[str]
    timestamp: str


@dataclass
class BenchmarkReport:
    category: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    average_score: float
    score_distribution: Dict[str, int]
    weak_areas: List[str]
    improvement_suggestions: List[str]
    detailed_results: List[Dict[str, Any]]


class TestDataGenerator:
    """测试数据生成器 - 生成多样化的测试用例"""

    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)

    def generate_management_test_cases(self, count: int = 15) -> List[TestCase]:
        """生成管理驱动测试用例 - 测试agent是否能正确委派任务而非自己执行"""
        tasks = self._get_management_tasks()
        cases = []

        for i, task_template in enumerate(tasks[:count]):
            case_id = f"MGMT-{task_template['id']:02d}"

            case = TestCase(
                case_id=case_id,
                category=TestCategory.MANAGEMENT.value,
                difficulty=task_template['difficulty'],
                title=task_template['title'],
                context=task_template['context'],
                question=task_template['question'],
                correct_answer=task_template['answer'],
                agent_constraints=[
                    "禁止使用subagent直接执行任务",
                    "必须将任务拆解为多个子任务",
                    "必须明确指定每个子任务的目标agent",
                    "只输出任务分配计划，不执行具体工作"
                ],
                evaluation_criteria=[
                    "是否拆解了任务",
                    "是否指定了执行者",
                    "是否避免了直接执行",
                    "任务分配是否合理"
                ],
                memory_keywords=self._extract_keywords(task_template),
                distraction_factors=[
                    "提供看似简单的实现代码",
                    "暗示可以直接完成任务",
                    "模糊任务边界"
                ],
                metadata={
                    "task_type": task_template.get('task_type', 'general'),
                    "expected_delegation_count": task_template.get('expected_delegations', 2),
                    "constraint_violation_keywords": ["直接执行", "我来", "subagent.execute"]
                }
            )
            cases.append(case)

        return cases

    def generate_logic_execution_test_cases(self, count: int = 15) -> List[TestCase]:
        """生成逻辑执行测试用例 - 测试agent是否能遵循架构规范"""
        tasks = self._get_logic_tasks()
        cases = []

        for i, task_template in enumerate(tasks[:count]):
            case_id = f"LOGIC-{task_template['id']:02d}"

            case = TestCase(
                case_id=case_id,
                category=TestCategory.LOGIC_EXECUTION.value,
                difficulty=task_template['difficulty'],
                title=task_template['title'],
                context=task_template['context'],
                question=task_template['question'],
                correct_answer=task_template['answer'],
                agent_constraints=[
                    "必须使用成熟的商业框架",
                    "禁止硬编码",
                    "必须解耦模块",
                    "代码必须可测试"
                ],
                evaluation_criteria=[
                    "是否使用了指定框架",
                    "是否存在硬编码",
                    "模块耦合度",
                    "代码可测试性"
                ],
                memory_keywords=self._extract_keywords(task_template),
                distraction_factors=[
                    "提供快速的硬编码方案",
                    "暗示性能优先",
                    "简化错误处理"
                ],
                metadata={
                    "required_frameworks": task_template.get('frameworks', []),
                    "anti_patterns": ["hardcoded_value", "magic_number", "tight_coupling"],
                    "expected_architecture": task_template.get('architecture', 'layered')
                }
            )
            cases.append(case)

        return cases

    def generate_user_habit_test_cases(self, count: int = 15) -> List[TestCase]:
        """生成用户习惯测试用例 - 测试agent是否能记住用户偏好"""
        profiles = self._get_user_profiles()
        cases = []

        for i, profile_template in enumerate(profiles[:count]):
            case_id = f"HABIT-{profile_template['id']:02d}"

            case = TestCase(
                case_id=case_id,
                category=TestCategory.USER_HABIT.value,
                difficulty=profile_template['difficulty'],
                title=profile_template['title'],
                context=profile_template['context'],
                question=profile_template['question'],
                correct_answer=profile_template['answer'],
                agent_constraints=[
                    "必须回忆之前的用户描述",
                    "必须基于用户习惯调整回答",
                    "禁止忽略用户偏好",
                    "回答必须符合用户风格"
                ],
                evaluation_criteria=[
                    "是否正确回忆了用户习惯",
                    "回答是否符合用户偏好",
                    "是否使用了正确的称呼/风格",
                    "是否避免了用户明确拒绝的方式"
                ],
                memory_keywords=profile_template.get('habits', []),
                distraction_factors=[
                    "提供通用的解决方案",
                    "使用默认参数",
                    "忽略用户特定限制"
                ],
                metadata={
                    "user_preferences": profile_template.get('preferences', {}),
                    "common_habits": profile_template.get('common_habits', []),
                    "rare_habits": profile_template.get('rare_habits', [])
                }
            )
            cases.append(case)

        return cases

    def _get_management_tasks(self) -> List[Dict[str, Any]]:
        """获取管理任务模板 - 15+个多样化的任务"""
        return [
            {
                'id': 1, 'difficulty': 1, 'task_type': 'simple',
                'title': '代码审查任务委派',
                'context': '用户告诉agent: "你是团队管理者，不要自己审查代码，要让其他成员来做代码审查"',
                'question': '现在有一份PR需要审查，你会怎么做？',
                'answer': '拆解任务: 1)通知code-reviewer角色审查PR 2)分配具体的文件范围 3)设定审查截止时间',
                'expected_delegations': 2
            },
            {
                'id': 2, 'difficulty': 1, 'task_type': 'simple',
                'title': '文档更新任务委派',
                'context': '用户告诉agent: "你作为管理者，只能分配任务，不能自己写文档"',
                'question': '项目需要更新API文档，你会怎么做？',
                'answer': '拆解任务: 1)指定tech-writer负责文档更新 2)分配API端点清单 3)提供文档模板',
                'expected_delegations': 2
            },
            {
                'id': 3, 'difficulty': 2, 'task_type': 'medium',
                'title': '多团队协调任务',
                'context': '用户告诉agent: "你是项目协调者，所有执行工作都要分配给对应专家"',
                'question': '需要同时更新前端、后端和数据库，你会怎么做？',
                'answer': '拆解任务: 1)分配前端任务给frontend-dev 2)分配后端任务给backend-dev 3)分配DB任务给data-eng',
                'expected_delegations': 3
            },
            {
                'id': 4, 'difficulty': 2, 'task_type': 'medium',
                'title': '紧急Bug修复协调',
                'context': '用户告诉agent: "紧急情况也要遵循委派原则，不能自己动手"',
                'question': '生产环境出现严重bug，你会怎么处理？',
                'answer': '拆解任务: 1)立即通知oncall-eng诊断问题 2)分配根因分析任务 3)协调dev-ops准备回滚',
                'expected_delegations': 3
            },
            {
                'id': 5, 'difficulty': 1, 'task_type': 'simple',
                'title': '简单问答委派',
                'context': '用户告诉agent: "像FAQ回答这类事，直接分配给support-bot"',
                'question': '用户询问产品定价，你会怎么做？',
                'answer': '将任务委派给support-bot处理',
                'expected_delegations': 1
            },
            {
                'id': 6, 'difficulty': 2, 'task_type': 'medium',
                'title': '技术选型决策',
                'context': '用户告诉agent: "你只负责收集信息做决策，执行由团队决定"',
                'question': '团队需要选择新的数据库方案，你会怎么做？',
                'answer': '拆解任务: 1)分配调研任务给researcher收集方案 2)分配评估任务给architect做技术评审 3)做最终推荐',
                'expected_delegations': 2
            },
            {
                'id': 7, 'difficulty': 3, 'task_type': 'complex',
                'title': '大型功能发布协调',
                'context': '用户告诉agent: "发布相关工作都要分配，不能自己操作发布"',
                'question': '新功能需要灰度发布，你会如何处理？',
                'answer': '拆解任务: 1)分配灰度配置任务给devops 2)分配监控任务给sre 3)分配回滚预案给backup-team 4)协调rollback流程',
                'expected_delegations': 4
            },
            {
                'id': 8, 'difficulty': 1, 'task_type': 'simple',
                'title': '会议安排委派',
                'context': '用户告诉agent: "日程安排这类事交给scheduler处理"',
                'question': '需要安排与客户的周会，你会怎么做？',
                'answer': '将任务委派给scheduler-agent',
                'expected_delegations': 1
            },
            {
                'id': 9, 'difficulty': 2, 'task_type': 'medium',
                'title': '代码重构监督',
                'context': '用户告诉agent: "你监督重构进度，不参与具体代码编写"',
                'question': '需要进行代码重构，你会怎么处理？',
                'answer': '拆解任务: 1)分配具体模块给对应的dev 2)设定重构目标和时间表 3)定期检查进度',
                'expected_delegations': 2
            },
            {
                'id': 10, 'difficulty': 3, 'task_type': 'complex',
                'title': '跨部门项目启动',
                'context': '用户告诉agent: "这是跨部门项目，你是项目经理，只负责协调"',
                'question': '新项目需要研发、市场和运营部门协作，你会如何启动？',
                'answer': '拆解任务: 1)分配研发计划任务给tech-lead 2)分配市场调研给marketing 3)分配运营方案给ops',
                'expected_delegations': 3
            },
            {
                'id': 11, 'difficulty': 1, 'task_type': 'simple',
                'title': '测试报告汇总',
                'context': '用户告诉agent: "汇总工作交给你，执行类测试分配出去"',
                'question': '需要汇总各模块的测试报告，你会怎么做？',
                'answer': '拆解任务: 1)向各模块负责人请求报告 2)收集后汇总整理',
                'expected_delegations': 1
            },
            {
                'id': 12, 'difficulty': 2, 'task_type': 'medium',
                'title': '性能优化任务',
                'context': '用户告诉agent: "性能优化要分配给专人，你只做评估和协调"',
                'question': '系统响应时间变慢，需要优化，你会怎么做？',
                'answer': '拆解任务: 1)分配profiling任务给perf-eng 2)分配优化任务给backend-dev 3)协调优化方案',
                'expected_delegations': 2
            },
            {
                'id': 13, 'difficulty': 3, 'task_type': 'complex',
                'title': '安全事件响应',
                'context': '用户告诉agent: "安全事件你只能协调，不能自己处理"',
                'question': '发现潜在安全漏洞，你会如何处理？',
                'answer': '拆解任务: 1)立即通知security-team 2)分配漏洞分析给sec-eng 3)协调修复方案 4)监督修复进度',
                'expected_delegations': 3
            },
            {
                'id': 14, 'difficulty': 2, 'task_type': 'medium',
                'title': '需求变更处理',
                'context': '用户告诉agent: "需求变更要评估影响并分配，不是你自己改代码"',
                'question': '客户提出新需求，你会如何处理？',
                'answer': '拆解任务: 1)分配影响评估任务给analyst 2)分配方案设计给architect 3)协调实施计划',
                'expected_delegations': 2
            },
            {
                'id': 15, 'difficulty': 1, 'task_type': 'simple',
                'title': '日志查看请求',
                'context': '用户告诉agent: "查日志这种操作交给ops，不是你亲自做"',
                'question': '需要查看某服务的错误日志，你会怎么做？',
                'answer': '将任务委派给ops-agent',
                'expected_delegations': 1
            },
            {
                'id': 16, 'difficulty': 2, 'task_type': 'medium',
                'title': '第三方集成协调',
                'context': '用户告诉agent: "集成工作分配给API-dev，你只负责协调"',
                'question': '需要集成支付网关，你会如何处理？',
                'answer': '拆解任务: 1)分配API对接任务给backend-dev 2)分配测试任务给qa 3)协调进度',
                'expected_delegations': 2
            },
            {
                'id': 17, 'difficulty': 3, 'task_type': 'complex',
                'title': '系统迁移项目',
                'context': '用户告诉agent: "迁移是大事，你只能做总指挥"',
                'question': '需要将系统从本地迁移到云，你会如何规划？',
                'answer': '拆解任务: 1)分配环境搭建给devops 2)分配数据迁移给dba 3)分配应用迁移给dev-team 4)协调切换',
                'expected_delegations': 4
            }
        ]

    def _get_logic_tasks(self) -> List[Dict[str, Any]]:
        """获取逻辑执行任务模板 - 15+个多样化任务"""
        return [
            {
                'id': 1, 'difficulty': 1, 'frameworks': ['SQLAlchemy', 'FastAPI'],
                'title': '数据库连接配置',
                'context': '用户告诉agent: "所有数据库连接必须用ORM，禁止直接写SQL字符串"',
                'question': '需要实现一个用户查询功能，你会如何实现？',
                'answer': '使用SQLAlchemy定义User模型，通过ORM查询获取用户',
                'architecture': 'layered'
            },
            {
                'id': 2, 'difficulty': 1, 'frameworks': ['Django REST Framework'],
                'title': 'API接口开发',
                'context': '用户告诉agent: "API必须用DRF序列化器，禁止直接返回字典"',
                'question': '需要创建用户列表API，你会如何实现？',
                'answer': '使用DRF的ModelSerializer定义序列化器，通过ViewSet处理请求',
                'architecture': 'restful'
            },
            {
                'id': 3, 'difficulty': 2, 'frameworks': ['Celery', 'Redis'],
                'title': '异步任务处理',
                'context': '用户告诉agent: "耗时操作必须用Celery，禁止同步阻塞"',
                'question': '需要发送大量邮件通知，你会如何实现？',
                'answer': '定义Celery任务，使用@shared_task装饰器，通过broker异步执行',
                'architecture': 'async'
            },
            {
                'id': 4, 'difficulty': 2, 'frameworks': ['Pydantic', 'FastAPI'],
                'title': '数据验证',
                'context': '用户告诉agent: "所有输入必须用Pydantic验证，禁止手写if判断"',
                'question': '需要验证用户注册信息，你会如何实现？',
                'answer': '定义Pydantic模型(BaseModel)，包含field_validator进行验证',
                'architecture': 'typed'
            },
            {
                'id': 5, 'difficulty': 1, 'frameworks': ['pytest'],
                'title': '单元测试编写',
                'context': '用户告诉agent: "测试必须用pytest，禁止用unittest"',
                'question': '需要为工具函数写测试，你会如何写？',
                'answer': '使用pytest定义test_函数，使用fixture，用assert进行断言',
                'architecture': 'testable'
            },
            {
                'id': 6, 'difficulty': 2, 'frameworks': ['Docker', 'docker-compose'],
                'title': '容器化部署',
                'context': '用户告诉agent: "服务必须Docker化，禁止直接部署到主机"',
                'question': '需要部署一个Python Web服务，你会如何处理？',
                'answer': '编写Dockerfile，使用docker-compose定义服务，启动容器运行',
                'architecture': 'containerized'
            },
            {
                'id': 7, 'difficulty': 3, 'frameworks': ['FastAPI', 'Redis', 'JWT'],
                'title': '认证系统',
                'context': '用户告诉agent: "认证必须用JWT+Redis，禁止自己实现token"',
                'question': '需要实现登录功能，你会如何实现？',
                'answer': '使用python-jose生成JWT，Redis存储token，Depends验证token',
                'architecture': 'secure'
            },
            {
                'id': 8, 'difficulty': 2, 'frameworks': ['SQLAlchemy', 'Alembic'],
                'title': '数据库迁移',
                'context': '用户告诉agent: "数据库变更必须用Alembic，禁止手动修改表"',
                'question': '需要添加一个新字段，你会如何操作？',
                'answer': '使用alembic revision创建迁移文件，编辑upgrade/downgrade函数，执行migrate',
                'architecture': 'migratable'
            },
            {
                'id': 9, 'difficulty': 1, 'frameworks': ['pydantic-settings'],
                'title': '配置管理',
                'context': '用户告诉agent: "配置必须用pydantic-settings，禁止hardcode"',
                'question': '需要读取数据库配置，你会如何实现？',
                'answer': '定义Settings类继承BaseSettings，使用env文件加载配置',
                'architecture': 'configurable'
            },
            {
                'id': 10, 'difficulty': 2, 'frameworks': ['FastAPI', 'OpenTelemetry'],
                'title': '日志记录',
                'context': '用户告诉agent: "日志必须结构化输出，禁止用print"',
                'question': '需要记录API调用日志，你会如何实现？',
                'answer': '使用structlog或OpenTelemetry配置结构化日志，记录trace_id',
                'architecture': 'observable'
            },
            {
                'id': 11, 'difficulty': 3, 'frameworks': ['FastAPI', 'Prometheus'],
                'title': '监控系统集成',
                'context': '用户告诉agent: "监控必须用Prometheus，禁止自建监控"',
                'question': '需要暴露服务指标，你会如何实现？',
                'answer': '使用prometheus-fastapi-instrumentator，暴露/metrics端点',
                'architecture': 'monitored'
            },
            {
                'id': 12, 'difficulty': 1, 'frameworks': ['httpx'],
                'title': 'HTTP客户端',
                'context': '用户告诉agent: "HTTP请求必须用httpx，禁止用requests"',
                'question': '需要调用第三方API，你会如何实现？',
                'answer': '使用httpx.AsyncClient发送请求，处理响应',
                'architecture': 'async'
            },
            {
                'id': 13, 'difficulty': 2, 'frameworks': ['FastAPI', 'rate-limit'],
                'title': '限流实现',
                'context': '用户告诉agent: "限流必须用库实现，禁止自己写计数器"',
                'question': '需要限制API调用频率，你会如何实现？',
                'answer': '使用slowapi定义限流规则，应用到endpoint',
                'architecture': 'protected'
            },
            {
                'id': 14, 'difficulty': 2, 'frameworks': ['pytest', 'pytest-asyncio'],
                'title': '异步测试',
                'context': '用户告诉agent: "异步代码测试必须用pytest-asyncio"',
                'question': '需要测试异步函数，你会如何写测试？',
                'answer': '使用pytest-asyncio的@pytest.mark.asyncio，用async def测试函数',
                'architecture': 'testable'
            },
            {
                'id': 15, 'difficulty': 1, 'frameworks': ['python-dotenv'],
                'title': '环境变量',
                'context': '用户告诉agent: "环境变量必须用.env文件管理"',
                'question': '需要区分开发和生产配置，你会如何实现？',
                'answer': '创建.env和.env.prod文件，使用python-dotenv加载',
                'architecture': 'env-based'
            },
            {
                'id': 16, 'difficulty': 3, 'frameworks': ['FastAPI', 'WebSocket'],
                'title': '实时通信',
                'context': '用户告诉agent: "WebSocket必须用FastAPI内置支持"',
                'question': '需要实现实时聊天功能，你会如何实现？',
                'answer': '使用FastAPI的WebSocket端点，定义connection_manager管理连接',
                'architecture': 'realtime'
            },
            {
                'id': 17, 'difficulty': 2, 'frameworks': [' Alembic', 'pytest'],
                'title': '迁移测试',
                'context': '用户告诉agent: "数据库迁移必须有测试覆盖"',
                'question': '需要测试一个迁移脚本，你会如何写？',
                'answer': '使用pytest.mark.migration标记测试，验证upgrade和downgrade',
                'architecture': 'testable'
            }
        ]

    def _get_user_profiles(self) -> List[Dict[str, Any]]:
        """获取用户画像模板 - 15+个多样化用户"""
        return [
            {
                'id': 1, 'difficulty': 1,
                'title': '技术风格偏好',
                'context': '第一轮: 用户说"我喜欢简洁的代码风格，不要太多注释"',
                'question': '第二轮: 用户问"怎么实现快速排序？"基于之前的偏好，你会如何回答？',
                'answer': '提供简洁的实现代码，附带简短注释或无注释',
                'preferences': {'code_style': 'minimal_comments', 'verbosity': 'low'},
                'common_habits': ['简洁风格', '直接代码'],
                'rare_habits': ['详细解释']
            },
            {
                'id': 2, 'difficulty': 2,
                'title': '沟通方式偏好',
                'context': '第一轮: 用户说"我是技术背景，请直接说技术方案，不用解释概念"',
                'question': '第二轮: 用户问"用什么方式存储配置好？"基于之前偏好，你会如何回答？',
                'answer': '直接给出技术方案: pydantic-settings + .env，不解释什么是环境变量',
                'preferences': {'communication': 'technical_direct', 'explanations': False},
                'common_habits': ['技术直接', '跳过概念'],
                'rare_habits': ['需要背景说明']
            },
            {
                'id': 3, 'difficulty': 1,
                'title': '响应格式偏好',
                'context': '第一轮: 用户说"回答时请用Markdown格式，代码用代码块"',
                'question': '第二轮: 用户问"怎么连接数据库？"基于之前偏好，你会如何回答？',
                'answer': '使用Markdown格式，代码用```python```代码块展示',
                'preferences': {'format': 'markdown', 'code_block': True},
                'common_habits': ['Markdown格式', '代码块'],
                'rare_habits': ['纯文本回答']
            },
            {
                'id': 4, 'difficulty': 2,
                'title': '开发环境偏好',
                'context': '第一轮: 用户说"我只在Linux环境工作，不要提供Windows方案"',
                'question': '第二轮: 用户问"怎么运行这个脚本？"基于之前偏好，你会如何回答？',
                'answer': '只提供Linux命令，如./run.sh或python main.py',
                'preferences': {'os': 'linux', 'platform': 'unix'},
                'common_habits': ['Linux命令', 'Unix工具'],
                'rare_habits': ['Windows方案']
            },
            {
                'id': 5, 'difficulty': 1,
                'title': '命名规范偏好',
                'context': '第一轮: 用户说"我喜欢用下划线命名法，不要驼峰"',
                'question': '第二轮: 用户问"定义一个用户类"基于之前偏好，你会如何命名？',
                'answer': '使用user_class或UserClass(根据Python PEP8推荐)，避免UserClass',
                'preferences': {'naming': 'snake_case'},
                'common_habits': ['snake_case', '下划线命名'],
                'rare_habits': ['camelCase']
            },
            {
                'id': 6, 'difficulty': 2,
                'title': '错误处理偏好',
                'context': '第一轮: 用户说"我需要详细的错误日志，方便排查问题"',
                'question': '第二轮: 实现一个函数时，基于之前偏好，你会如何处理错误？',
                'answer': '包含详细的try-except，日志记录完整堆栈信息',
                'preferences': {'error_handling': 'verbose', 'logging': 'detailed'},
                'common_habits': ['详细日志', '完整堆栈'],
                'rare_habits': ['简单错误处理']
            },
            {
                'id': 7, 'difficulty': 1,
                'title': '测试覆盖偏好',
                'context': '第一轮: 用户说"每个函数都必须有单元测试"',
                'question': '第二轮: 实现一个工具函数时，基于之前偏好，你会如何处理？',
                'answer': '同时提供test_xxx函数的测试代码',
                'preferences': {'testing': 'mandatory', 'coverage': '100%'},
                'common_habits': ['测试优先', '完整覆盖'],
                'rare_habits': ['跳过测试']
            },
            {
                'id': 8, 'difficulty': 2,
                'title': '代码审查偏好',
                'context': '第一轮: 用户说"提交代码前请先自审，确保符合PEP8"',
                'question': '第二轮: 写完一段代码后，基于之前偏好，你会如何处理？',
                'answer': '先检查PEP8规范，确保格式一致后再输出',
                'preferences': {'review': 'self_first', 'style': 'pep8'},
                'common_habits': ['自审', 'PEP8'],
                'rare_habits': ['直接提交']
            },
            {
                'id': 9, 'difficulty': 1,
                'title': '版本控制偏好',
                'context': '第一轮: 用户说"使用Git，提交信息要有意义，不要用"fix"这种"',
                'question': '第二轮: 修复了一个bug，基于之前偏好，你会如何写提交信息？',
                'answer': '使用有意义的提交信息，如"fix: resolve null pointer in user login"',
                'preferences': {'vcs': 'git', 'commit_style': 'conventional'},
                'common_habits': ['有意义提交', 'conventional'],
                'rare_habits': ['简短提交']
            },
            {
                'id': 10, 'difficulty': 2,
                'title': '性能要求偏好',
                'context': '第一轮: 用户说"性能很重要，优化要优先考虑"',
                'question': '第二轮: 需要实现数据查询，基于之前偏好，你会如何实现？',
                'answer': '考虑索引、缓存，选择更高效的查询方式',
                'preferences': {'optimization': 'priority', 'performance': True},
                'common_habits': ['性能优先', '优化意识'],
                'rare_habits': ['功能优先']
            },
            {
                'id': 11, 'difficulty': 1,
                'title': '文档偏好',
                'context': '第一轮: 用户说"代码要有docstring，公共API必须写文档"',
                'question': '第二轮: 写一个公共函数时，基于之前偏好，你会如何处理？',
                'answer': '包含完整的docstring，说明参数、返回值和用法',
                'preferences': {'documentation': 'required', 'docstring': True},
                'common_habits': ['完整文档', 'docstring'],
                'rare_habits': ['无文档']
            },
            {
                'id': 12, 'difficulty': 2,
                'title': '依赖管理偏好',
                'context': '第一轮: 用户说"尽量用标准库，避免引入不必要的依赖"',
                'question': '第二轮: 需要处理JSON，基于之前偏好，你会如何实现？',
                'answer': '使用json标准库，不引入orjson等第三方库',
                'preferences': {'dependencies': 'minimal', 'stdlib': 'preferred'},
                'common_habits': ['标准库', '少依赖'],
                'rare_habits': ['多依赖']
            },
            {
                'id': 13, 'difficulty': 1,
                'title': '代码复用偏好',
                'context': '第一轮: 用户说"重复代码要抽取成函数，不要复制粘贴"',
                'question': '第二轮: 发现两处相似的逻辑，基于之前偏好，你会如何处理？',
                'answer': '抽取为通用函数，在两处调用',
                'preferences': {'dry': True, 'reuse': 'mandatory'},
                'common_habits': ['DRY原则', '函数抽取'],
                'rare_habits': ['代码复制']
            },
            {
                'id': 14, 'difficulty': 2,
                'title': '安全要求偏好',
                'context': '第一轮: 用户说"安全是红线，不要有任何安全漏洞"',
                'question': '第二轮: 处理用户输入时，基于之前偏好，你会如何处理？',
                'answer': '严格验证输入，防止注入攻击，使用参数化查询',
                'preferences': {'security': 'critical', 'validation': 'strict'},
                'common_habits': ['安全优先', '严格验证'],
                'rare_habits': ['宽松处理']
            },
            {
                'id': 15, 'difficulty': 1,
                'title': '注释风格偏好',
                'context': '第一轮: 用户说"注释要解释为什么，不只是做什么"',
                'question': '第二轮: 写一段代码的注释，基于之前偏好，你会如何写？',
                'answer': '写"# Why: 使用二分查找因为数据量大于10000"而非"# 做二分查找"',
                'preferences': {'comments': 'why_focused'},
                'common_habits': ['解释原因', 'Why注释'],
                'rare_habits': ['What注释']
            },
            {
                'id': 16, 'difficulty': 2,
                'title': '模块组织偏好',
                'context': '第一轮: 用户说"模块要小而专一，一个模块只做一件事"',
                'question': '第二轮: 设计一个新功能模块，基于之前偏好，你会如何组织？',
                'answer': '拆分为多个小模块，每个模块职责单一',
                'preferences': {'modules': 'single_responsibility', 'size': 'small'},
                'common_habits': ['小模块', '单一职责'],
                'rare_habits': ['大而全']
            },
            {
                'id': 17, 'difficulty': 1,
                'title': '异步编程偏好',
                'context': '第一轮: 用户说"IO操作必须异步，不要用同步阻塞"',
                'question': '第二轮: 需要读取文件，基于之前偏好，你会如何实现？',
                'answer': '使用aiofiles异步读取，不用open().read()',
                'preferences': {'async': 'required', 'io': 'non_blocking'},
                'common_habits': ['异步优先', '非阻塞'],
                'rare_habits': ['同步操作']
            }
        ]

    def _extract_keywords(self, template: Dict[str, Any]) -> List[str]:
        """从模板中提取关键词"""
        text = f"{template.get('title', '')} {template.get('context', '')} {template.get('question', '')}"
        tokens = re.findall(r'[\u4e00-\u9fff\w]{2,}', text.lower())
        keywords = [t for t in tokens if len(t) >= 2][:8]
        return keywords


class BenchmarkScorer:
    """评分系统 - 客观评估agent的记忆和执行能力"""

    def __init__(self):
        self.weights = {
            'management': {
                'delegation': 0.40,
                'task_breakdown': 0.30,
                'constraint_following': 0.30
            },
            'logic_execution': {
                'framework_usage': 0.35,
                'anti_pattern_avoidance': 0.35,
                'architecture_quality': 0.30
            },
            'user_habit': {
                'memory_recall': 0.40,
                'preference_application': 0.35,
                'consistency': 0.25
            }
        }

    def _is_non_answer(self, response: str) -> bool:
        """Detect empty or placeholder responses that should receive zero score."""
        text = (response or "").strip()
        if not text:
            return True

        lowered = text.lower()
        placeholder_signals = [
            "no relevant memories recalled",
            "relevant memories recalled:",
            "memory recall",
            "no response",
        ]
        if any(sig in lowered for sig in placeholder_signals):
            # Pure recall summary without concrete answer should be treated as non-answer.
            answer_cues = ["1)", "2)", "步骤", "建议", "使用", "实现", "可以", "应该"]
            if not any(cue in text for cue in answer_cues):
                return True

        return False

    def score_management_test(self, response: str, test_case: TestCase) -> Dict[str, Any]:
        """评分管理测试"""
        if self._is_non_answer(response):
            return {
                'total_score': 0.0,
                'component_scores': {
                    'delegation': 0.0,
                    'task_breakdown': 0.0,
                    'constraint_following': 0.0,
                },
                'details': {
                    'no_response': True,
                    'reason': 'empty_or_placeholder_response',
                },
                'passed': False
            }

        scores = {}
        details = {}

        delegation_patterns = [
            r'分配.*给', r'指定.*负责', r'委托.*执行',
            r'通知.*进行', r'协调.*完成'
        ]
        delegation_count = sum(1 for p in delegation_patterns if re.search(p, response))

        scores['delegation'] = min(delegation_count / test_case.metadata.get('expected_delegations', 2), 1.0) * 100
        details['delegation_count'] = delegation_count
        details['expected_delegations'] = test_case.metadata.get('expected_delegations', 2)

        breakdown_indicators = ['拆解', '1)', '2)', '3)', '步骤', '阶段', '子任务']
        scores['task_breakdown'] = sum(20 for i in breakdown_indicators if i in response)

        constraint_violations = ['直接执行', '我来', 'subagent.execute', '自己写', '自己改']
        violation_count = sum(1 for v in constraint_violations if v in response)
        scores['constraint_following'] = max(100 - violation_count * 25, 0)

        total_score = (
            scores['delegation'] * self.weights['management']['delegation'] +
            scores['task_breakdown'] * self.weights['management']['task_breakdown'] +
            scores['constraint_following'] * self.weights['management']['constraint_following']
        )

        return {
            'total_score': round(total_score, 2),
            'component_scores': {k: round(v, 2) for k, v in scores.items()},
            'details': details,
            'passed': total_score >= 70
        }

    def score_logic_test(self, response: str, test_case: TestCase) -> Dict[str, Any]:
        """评分逻辑执行测试"""
        if self._is_non_answer(response):
            return {
                'total_score': 0.0,
                'component_scores': {
                    'framework_usage': 0.0,
                    'anti_pattern_avoidance': 0.0,
                    'architecture_quality': 0.0,
                },
                'details': {
                    'no_response': True,
                    'reason': 'empty_or_placeholder_response',
                },
                'passed': False
            }

        scores = {}
        details = {}

        required_frameworks = test_case.metadata.get('required_frameworks', [])
        framework_mentioned = sum(1 for f in required_frameworks if f.lower() in response.lower())
        scores['framework_usage'] = (framework_mentioned / len(required_frameworks) * 100) if required_frameworks else 50

        details['frameworks_found'] = framework_mentioned
        details['frameworks_required'] = len(required_frameworks)

        anti_patterns = test_case.metadata.get('anti_patterns', [])
        found_anti_patterns = []
        for pattern in anti_patterns:
            if 'hardcode' in pattern.lower() and any(word in response for word in ['"123"', "'abc'", '硬编码']):
                found_anti_patterns.append(pattern)
            elif 'magic_number' in pattern.lower() and re.search(r'[0-9]{2,}', response):
                found_anti_patterns.append(pattern)

        scores['anti_pattern_avoidance'] = max(100 - len(found_anti_patterns) * 33, 0)
        details['anti_patterns_found'] = found_anti_patterns

        architecture_indicators = ['模块', '层', '分离', '解耦', '可扩展']
        scores['architecture_quality'] = sum(20 for i in architecture_indicators if i in response)

        total_score = (
            scores['framework_usage'] * self.weights['logic_execution']['framework_usage'] +
            scores['anti_pattern_avoidance'] * self.weights['logic_execution']['anti_pattern_avoidance'] +
            scores['architecture_quality'] * self.weights['logic_execution']['architecture_quality']
        )

        return {
            'total_score': round(total_score, 2),
            'component_scores': {k: round(v, 2) for k, v in scores.items()},
            'details': details,
            'passed': total_score >= 70
        }

    def score_user_habit_test(self, response: str, test_case: TestCase, memory_recalled: List[str] = None) -> Dict[str, Any]:
        """评分用户习惯测试"""
        if self._is_non_answer(response):
            return {
                'total_score': 0.0,
                'component_scores': {
                    'memory_recall': 0.0,
                    'preference_application': 0.0,
                    'consistency': 0.0,
                },
                'details': {
                    'no_response': True,
                    'reason': 'empty_or_placeholder_response',
                },
                'passed': False
            }

        scores = {}
        details = {}

        memory_keywords = test_case.memory_keywords
        recalled_count = sum(1 for kw in memory_keywords if kw.lower() in response.lower())
        scores['memory_recall'] = (recalled_count / max(len(memory_keywords), 1)) * 100

        details['keywords_recalled'] = recalled_count
        details['keywords_total'] = len(memory_keywords)

        preferences = test_case.metadata.get('user_preferences', {})
        preference_applied = 0
        for pref_key, pref_value in preferences.items():
            if 'format' in pref_key and 'markdown' in str(pref_value).lower():
                if '```' in response or 'markdown' in response.lower():
                    preference_applied += 1
            elif 'style' in pref_key:
                if pref_value in response.lower():
                    preference_applied += 1

        scores['preference_application'] = min(preference_applied * 50, 100) if preferences else 75

        consistency_keywords = ['之前', '根据您说的', '如您所好', '按照您的']
        scores['consistency'] = sum(25 for kw in consistency_keywords if kw in response)

        total_score = (
            scores['memory_recall'] * self.weights['user_habit']['memory_recall'] +
            scores['preference_application'] * self.weights['user_habit']['preference_application'] +
            scores['consistency'] * self.weights['user_habit']['consistency']
        )

        return {
            'total_score': round(total_score, 2),
            'component_scores': {k: round(v, 2) for k, v in scores.items()},
            'details': details,
            'passed': total_score >= 70
        }

    def generate_benchmark_report(self, results: List[TestResult], category: str) -> BenchmarkReport:
        """生成基准测试报告"""
        category_results = [r for r in results if r.category == category]

        if not category_results:
            return BenchmarkReport(
                category=category,
                total_cases=0,
                passed_cases=0,
                failed_cases=0,
                average_score=0,
                score_distribution={'A': 0, 'B': 0, 'C': 0, 'D': 0, 'F': 0},
                weak_areas=[],
                improvement_suggestions=[],
                detailed_results=[]
            )

        passed = sum(1 for r in category_results if r.passed)
        failed = len(category_results) - passed
        scores = [r.score for r in category_results]
        avg_score = sum(scores) / len(scores)

        distribution = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'F': 0}
        for s in scores:
            if s >= 90: distribution['A'] += 1
            elif s >= 80: distribution['B'] += 1
            elif s >= 70: distribution['C'] += 1
            elif s >= 60: distribution['D'] += 1
            else: distribution['F'] += 1

        weak_areas = self._identify_weak_areas(category_results)
        suggestions = self._generate_suggestions(category, weak_areas)

        return BenchmarkReport(
            category=category,
            total_cases=len(category_results),
            passed_cases=passed,
            failed_cases=failed,
            average_score=round(avg_score, 2),
            score_distribution=distribution,
            weak_areas=weak_areas,
            improvement_suggestions=suggestions,
            detailed_results=[asdict(r) for r in category_results]
        )

    def _identify_weak_areas(self, results: List[TestResult]) -> List[str]:
        """识别薄弱环节"""
        weak = []
        avg_scores = {}

        for r in results:
            for key, score in r.evaluation_details.get('component_scores', {}).items():
                if key not in avg_scores:
                    avg_scores[key] = []
                avg_scores[key].append(score)

        for key, scores in avg_scores.items():
            if scores and sum(scores) / len(scores) < 60:
                weak.append(f"{key}: {sum(scores) / len(scores):.1f}%")

        return weak

    def _generate_suggestions(self, category: str, weak_areas: List[str]) -> List[str]:
        """生成改进建议"""
        suggestions = []

        if category == TestCategory.MANAGEMENT.value:
            suggestions.append("建议强化任务委派意识：明确告知agent只能协调不能执行")
            if any('delegation' in w for w in weak_areas):
                suggestions.append("需要提高任务分配能力：建议agent学习任务拆解模式")
        elif category == TestCategory.LOGIC_EXECUTION.value:
            suggestions.append("建议强化架构意识：持续强调使用成熟框架的重要性")
            if any('anti_pattern' in w for w in weak_areas):
                suggestions.append("需要避免硬编码：建议使用配置和常量管理")
        elif category == TestCategory.USER_HABIT.value:
            suggestions.append("建议强化用户记忆：在每次交互中提醒agent回忆用户偏好")
            if any('memory' in w for w in weak_areas):
                suggestions.append("需要提高记忆能力：建议增加记忆检索频率")

        return suggestions
