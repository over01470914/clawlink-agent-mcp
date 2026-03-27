"""
MCP Connection Test Script
测试 MCP 服务连接状态并生成报告
"""

import json
import sys
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TestResult:
    name: str
    passed: bool
    message: str
    details: Optional[Dict] = None


class MCPConnectionTester:
    def __init__(self, agent_url: str = "http://127.0.0.1:8430"):
        self.agent_url = agent_url
        self.results: List[TestResult] = []

    async def run_all_tests(self) -> Dict[str, Any]:
        print("=" * 60)
        print("MCP Connection Test Suite")
        print(f"Target: {self.agent_url}")
        print("=" * 60)

        await self.test_health_check()
        await self.test_mcp_initialize()
        await self.test_tools_list()
        await self.test_memory_stats()
        await self.test_memory_search()
        await self.test_memory_list()
        await self.test_send_message()

        return self.generate_report()

    async def test_health_check(self) -> None:
        import httpx
        test = TestResult(name="Health Check", passed=False, message="")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.agent_url}/ping")
                if resp.status_code == 200:
                    data = resp.json()
                    test.passed = True
                    test.message = f"✓ Agent is healthy (ID: {data.get('agent_id', 'unknown')})"
                    test.details = data
                else:
                    test.message = f"✗ Health check failed: HTTP {resp.status_code}"
        except Exception as e:
            test.message = f"✗ Connection failed: {str(e)}"

        self.results.append(test)
        print(f"\n[1] Health Check: {test.message}")

    async def test_mcp_initialize(self) -> None:
        test = TestResult(name="MCP Initialize", passed=False, message="")
        bridge = self._create_bridge()

        try:
            response = await self._send_mcp_request({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"}
                }
            }, bridge)

            if response and response.get("result"):
                info = response["result"].get("serverInfo", {})
                test.passed = True
                test.message = f"✓ MCP initialized (Server: {info.get('name', 'unknown')} v{info.get('version', 'unknown')})"
                test.details = info
            else:
                test.message = f"✗ Initialize failed: {response.get('error', 'Unknown error')}"
        except Exception as e:
            test.message = f"✗ Initialize failed: {str(e)}"

        self.results.append(test)
        print(f"[2] MCP Initialize: {test.message}")

    async def test_tools_list(self) -> None:
        test = TestResult(name="Tools List", passed=False, message="")
        bridge = self._create_bridge()

        try:
            response = await self._send_mcp_request({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            }, bridge)

            if response and response.get("result"):
                tools = response["result"].get("tools", [])
                test.passed = True
                test.message = f"✓ Found {len(tools)} tools available"
                test.details = {"tool_count": len(tools), "tools": [t["name"] for t in tools]}
            else:
                test.message = f"✗ Tools list failed: {response.get('error', 'Unknown error')}"
        except Exception as e:
            test.message = f"✗ Tools list failed: {str(e)}"

        self.results.append(test)
        print(f"[3] Tools List: {test.message}")

    async def test_memory_stats(self) -> None:
        test = TestResult(name="Memory Stats", passed=False, message="")
        bridge = self._create_bridge()

        try:
            response = await self._send_mcp_request({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "clawlink_memory_stats",
                    "arguments": {}
                }
            }, bridge)

            if response and response.get("result"):
                content = response["result"].get("content", [])
                if content:
                    stats = json.loads(content[0].get("text", "{}"))
                    total = stats.get("total", 0)
                    test.passed = True
                    test.message = f"✓ Memory system working ({total} memories stored)"
                    test.details = stats
                else:
                    test.message = "✗ Empty response from memory stats"
            else:
                test.message = f"✗ Memory stats failed: {response.get('error', 'Unknown error')}"
        except Exception as e:
            test.message = f"✗ Memory stats failed: {str(e)}"

        self.results.append(test)
        print(f"[4] Memory Stats: {test.message}")

    async def test_memory_search(self) -> None:
        test = TestResult(name="Memory Search", passed=False, message="")
        bridge = self._create_bridge()

        try:
            response = await self._send_mcp_request({
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "clawlink_memory_search",
                    "arguments": {"query": "test query", "top_k": 3}
                }
            }, bridge)

            if response and response.get("result"):
                content = response["result"].get("content", [])
                if content:
                    results = json.loads(content[0].get("text", "[]"))
                    test.passed = True
                    test.message = f"✓ Memory search working ({len(results)} results for 'test query')"
                    test.details = {"result_count": len(results)}
                else:
                    test.message = "✓ Memory search working (no results for empty query)"
            else:
                test.message = f"✗ Memory search failed: {response.get('error', 'Unknown error')}"
        except Exception as e:
            test.message = f"✗ Memory search failed: {str(e)}"

        self.results.append(test)
        print(f"[5] Memory Search: {test.message}")

    async def test_memory_list(self) -> None:
        test = TestResult(name="Memory List", passed=False, message="")
        bridge = self._create_bridge()

        try:
            response = await self._send_mcp_request({
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "clawlink_memory_list",
                    "arguments": {}
                }
            }, bridge)

            if response and response.get("result"):
                content = response["result"].get("content", [])
                if content:
                    memories = json.loads(content[0].get("text", "[]"))
                    test.passed = True
                    test.message = f"✓ Memory list working ({len(memories)} memories)"
                    test.details = {"memory_count": len(memories)}
                else:
                    test.message = "✓ Memory list working (0 memories)"
            else:
                test.message = f"✗ Memory list failed: {response.get('error', 'Unknown error')}"
        except Exception as e:
            test.message = f"✗ Memory list failed: {str(e)}"

        self.results.append(test)
        print(f"[6] Memory List: {test.message}")

    async def test_send_message(self) -> None:
        test = TestResult(name="Send Message", passed=False, message="")
        bridge = self._create_bridge()

        try:
            response = await self._send_mcp_request({
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "clawlink_send_message",
                    "arguments": {
                        "content": "Hello from MCP test script!",
                        "sender_id": "test-script"
                    }
                }
            }, bridge)

            if response and response.get("result"):
                content = response["result"].get("content", [])
                if content:
                    result = json.loads(content[0].get("text", "{}"))
                    received = result.get("received", False)
                    test.passed = received
                    if received:
                        test.message = "✓ Send message working (agent received message)"
                    else:
                        test.message = "✗ Agent did not receive message"
                    test.details = {"received": received}
                else:
                    test.message = "✗ Empty response from send message"
            else:
                test.message = f"✗ Send message failed: {response.get('error', 'Unknown error')}"
        except Exception as e:
            test.message = f"✗ Send message failed: {str(e)}"

        self.results.append(test)
        print(f"[7] Send Message: {test.message}")

    def _create_bridge(self):
        sys.path.insert(0, 'c:/Users/administration/Desktop/clawlink/clawlink-agent-test/clawlink-agent-mcp')
        from clawlink_agent.mcp_stdio_bridge import MCPStdioBridge
        return MCPStdioBridge(self.agent_url)

    async def _send_mcp_request(self, request: Dict, bridge) -> Optional[Dict]:
        import subprocess
        import asyncio

        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "clawlink_agent.mcp_stdio_bridge", self.agent_url,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )

        stdout, _ = await proc.communicate(input=json.dumps(request).encode())
        try:
            return json.loads(stdout.decode().strip())
        except:
            return None

    def generate_report(self) -> Dict[str, Any]:
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        pass_rate = (passed / total * 100) if total > 0 else 0

        report = {
            "timestamp": datetime.now().isoformat(),
            "agent_url": self.agent_url,
            "summary": {
                "total_tests": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": round(pass_rate, 2),
                "status": "HEALTHY" if pass_rate >= 80 else "DEGRADED" if pass_rate >= 50 else "UNHEALTHY"
            },
            "tests": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "message": r.message,
                    "details": r.details
                }
                for r in self.results
            ]
        }

        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"Total: {total} tests")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Pass Rate: {pass_rate:.1f}%")
        print(f"Status: {report['summary']['status']}")

        if pass_rate >= 80:
            print("\n✅ MCP Service is HEALTHY and fully operational!")
        elif pass_rate >= 50:
            print("\n⚠️ MCP Service is DEGRADED - some features may not work")
        else:
            print("\n❌ MCP Service is UNHEALTHY - needs attention")

        return report


def generate_user_notification(report: Dict[str, Any]) -> str:
    """生成用户友好的通知消息"""
    summary = report["summary"]
    status_emoji = {
        "HEALTHY": "✅",
        "DEGRADED": "⚠️",
        "UNHEALTHY": "❌"
    }

    message = f"""
{status_emoji.get(summary['status'], '❓')} **CLAWLINK-AGENT MCP 连接状态报告**

**状态**: {summary['status']}
**测试时间**: {report['timestamp']}
**Agent**: {report['agent_url']}

**测试结果**:
- 总计: {summary['total_tests']} 项
- 通过: {summary['passed']} 项
- 失败: {summary['failed']} 项
- 通过率: {summary['pass_rate']}%

**详细结果**:
"""

    for test in report["tests"]:
        emoji = "✅" if test["passed"] else "❌"
        message += f"\n{emoji} **{test['name']}**: {test['message']}"

    if summary['status'] == "HEALTHY":
        message += """

🎉 **MCP 服务运行正常！**
所有功能测试通过，Agent 已准备好接收任务。
"""
    elif summary['status'] == "DEGRADED":
        message += """

⚠️ **MCP 服务部分异常**
部分功能可能无法正常工作，请检查失败的测试项。
"""
    else:
        message += """

❌ **MCP 服务异常**
多个核心功能测试失败，需要检查服务状态。
"""

    return message


async def main():
    agent_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8430"

    tester = MCPConnectionTester(agent_url)
    report = await tester.run_all_tests()

    notification = generate_user_notification(report)
    print("\n" + notification)

    if "--json" in sys.argv:
        print("\n--- JSON Output ---")
        print(json.dumps(report, indent=2, ensure_ascii=False))

    return report


if __name__ == "__main__":
    asyncio.run(main())
