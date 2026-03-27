"""
MCP STDIO Bridge for CLAWLINK-AGENT
将 HTTP REST API 桥接到 MCP STDIO 协议，供 IDE MCP 客户端使用
"""

import sys
import json
import asyncio
import httpx
from typing import Any, Dict, List, Optional


class MCPStdioBridge:
    def __init__(self, agent_url: str = "http://127.0.0.1:8430"):
        self.agent_url = agent_url.rstrip('/')
        self.tools = self._get_tools()

    def _get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "clawlink_memory_search",
                "description": "Search agent memories using a natural-language query (TF-IDF + keyword fallback).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "top_k": {"type": "integer", "description": "Max results", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "clawlink_memory_save",
                "description": "Save a new memory entry with triadic concepts, score, and evidence.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "Memory topic"},
                        "mode": {"type": "string", "description": "Interaction mode", "default": "teach"},
                        "teacher_id": {"type": "string", "default": ""},
                        "student_id": {"type": "string", "default": ""},
                        "strictness": {"type": "number", "default": 0.5},
                        "rubric": {"type": "string", "default": ""},
                        "score": {"type": "number", "default": 0.0},
                        "confidence": {"type": "number", "default": 0.0},
                        "concepts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Triadic concepts in 'topic; action; evidence' format",
                        },
                        "transcript_highlights": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "status": {"type": "string", "default": "draft"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "keywords": {"type": "array", "items": {"type": "string"}},
                        "ttl_days": {"type": "integer", "minimum": 1},
                    },
                    "required": ["topic"],
                },
            },
            {
                "name": "clawlink_memory_list",
                "description": "List all stored memories (id, topic, status, score).",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "clawlink_memory_stats",
                "description": "Return statistics about stored memories (count, topics, statuses).",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "clawlink_memory_get",
                "description": "Get a single memory by ID.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "memory_id": {"type": "string", "description": "Memory ID to retrieve"},
                    },
                    "required": ["memory_id"],
                },
            },
            {
                "name": "clawlink_send_message",
                "description": "Send a message to the agent and receive a response. Captures memories automatically.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Message content to send"},
                        "sender_id": {"type": "string", "description": "Sender identifier", "default": "user"},
                        "session_id": {"type": "string", "description": "Session ID", "default": "default"},
                        "capture_memory": {"type": "boolean", "description": "Auto-capture memory", "default": True},
                    },
                    "required": ["content"],
                },
            },
            {
                "name": "clawlink_diagnose",
                "description": "Run a comprehensive diagnostic test on the MCP connection and return a status report.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "verbose": {"type": "boolean", "description": "Include detailed output", "default": False},
                    },
                },
            },
        ]

    async def _call_http_api(self, endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{self.agent_url}{endpoint}"
            if method == "GET":
                resp = await client.get(url)
            else:
                resp = await client.post(url, json=data)
            return resp.json()

    async def _run_diagnostics(self, verbose: bool = False) -> Dict[str, Any]:
        from datetime import datetime

        tests = []
        all_passed = True

        try:
            health = await self._call_http_api("/ping")
            tests.append({
                "name": "Health Check",
                "passed": health.get("status") == "ok",
                "message": f"Agent ID: {health.get('agent_id', 'unknown')}"
            })
        except Exception as e:
            tests.append({"name": "Health Check", "passed": False, "message": str(e)})
            all_passed = False

        try:
            info = await self._call_http_api("/info")
            tests.append({
                "name": "Agent Info",
                "passed": True,
                "message": f"Version: {info.get('version', 'unknown')}, Memories: {info.get('memory_count', 0)}"
            })
        except Exception as e:
            tests.append({"name": "Agent Info", "passed": False, "message": str(e)})

        try:
            memories = await self._call_http_api("/memory/list")
            tests.append({
                "name": "Memory List",
                "passed": True,
                "message": f"Found {len(memories)} memories"
            })
        except Exception as e:
            tests.append({"name": "Memory List", "passed": False, "message": str(e)})
            all_passed = False

        try:
            msg_result = await self._call_http_api(
                "/message",
                method="POST",
                data={"content": "MCP diagnostic test", "sender_id": "diagnostic"}
            )
            tests.append({
                "name": "Send Message",
                "passed": msg_result.get("received", False),
                "message": "Message sent successfully" if msg_result.get("received") else "Failed"
            })
        except Exception as e:
            tests.append({"name": "Send Message", "passed": False, "message": str(e)})
            all_passed = False

        passed_count = sum(1 for t in tests if t["passed"])
        total_count = len(tests)

        result = {
            "timestamp": datetime.now().isoformat(),
            "agent_url": self.agent_url,
            "status": "HEALTHY" if all_passed else "DEGRADED",
            "summary": {
                "total_tests": total_count,
                "passed": passed_count,
                "failed": total_count - passed_count,
                "pass_rate": round(passed_count / total_count * 100, 1) if total_count > 0 else 0
            },
            "tests": tests,
            "user_notification": self._generate_notification(all_passed, passed_count, total_count)
        }

        return result

    def _generate_notification(self, all_passed: bool, passed: int, total: int) -> str:
        if all_passed:
            return f"""
✅ **CLAWLINK-AGENT MCP 服务状态报告**

🎉 **MCP 服务运行正常！**

**测试结果**: {passed}/{total} 项通过 (100%)

Agent 已准备好接收任务。你可以：
- 使用 `clawlink_memory_search` 搜索记忆
- 使用 `clawlink_send_message` 发送消息
- 使用 `clawlink_memory_list` 查看所有记忆
"""
        else:
            return f"""
⚠️ **CLAWLINK-AGENT MCP 服务状态报告**

**测试结果**: {passed}/{total} 项通过

部分功能可能无法正常工作，请检查服务状态。
"""

    async def execute_tool(self, tool_name: str, arguments: Dict) -> str:
        if tool_name == "clawlink_memory_search":
            result = await self._call_http_api(
                "/memory/search",
                method="POST",
                data={"query": arguments.get("query", ""), "top_k": arguments.get("top_k", 5)}
            )
            return json.dumps(result, indent=2, ensure_ascii=False)

        elif tool_name == "clawlink_memory_save":
            result = await self._call_http_api(
                "/memory/save",
                method="POST",
                data=arguments
            )
            return json.dumps(result, indent=2, ensure_ascii=False)

        elif tool_name == "clawlink_memory_list":
            result = await self._call_http_api("/memory/list")
            return json.dumps(result, indent=2, ensure_ascii=False)

        elif tool_name == "clawlink_memory_stats":
            result = await self._call_http_api("/memory/list")
            entries = result if isinstance(result, list) else []
            stats = {
                "total": len(entries),
                "topics": {},
                "statuses": {}
            }
            for e in entries:
                topic = e.get("topic", "unknown")
                stats["topics"][topic] = stats["topics"].get(topic, 0) + 1
                status = e.get("status", "unknown")
                stats["statuses"][status] = stats["statuses"].get(status, 0) + 1
            return json.dumps(stats, indent=2, ensure_ascii=False)

        elif tool_name == "clawlink_memory_get":
            memory_id = arguments.get("memory_id", "")
            result = await self._call_http_api(f"/memory/{memory_id}")
            return json.dumps(result, indent=2, ensure_ascii=False)

        elif tool_name == "clawlink_send_message":
            result = await self._call_http_api(
                "/message",
                method="POST",
                data={
                    "content": arguments.get("content", ""),
                    "sender_id": arguments.get("sender_id", "user"),
                    "session_id": arguments.get("session_id", "default"),
                    "metadata": {"capture_memory": arguments.get("capture_memory", True)}
                }
            )
            return json.dumps(result, indent=2, ensure_ascii=False)

        elif tool_name == "clawlink_diagnose":
            return json.dumps(await self._run_diagnostics(arguments.get("verbose", False)), indent=2, ensure_ascii=False)

        return json.dumps({"error": f"Unknown tool: {tool_name}"})


def send_response(request_id: Optional[str], result: Any, error: Optional[str] = None) -> None:
    response = {
        "jsonrpc": "2.0",
        "id": request_id,
    }
    if error:
        response["error"] = error
    else:
        response["result"] = result
    print(json.dumps(response), flush=True)


async def main():
    agent_url = "http://127.0.0.1:8430"
    if len(sys.argv) > 1:
        agent_url = sys.argv[1]

    bridge = MCPStdioBridge(agent_url)

    print("MCP STDIO Bridge for CLAWLINK-AGENT", file=sys.stderr)
    print(f"Connecting to: {agent_url}", file=sys.stderr)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)

            method = request.get("method", "")
            request_id = request.get("id")

            if method == "initialize":
                send_response(request_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "clawlink-agent",
                        "version": "1.0.0"
                    }
                })

            elif method == "tools/list":
                send_response(request_id, {
                    "tools": bridge.tools
                })

            elif method == "tools/call":
                tool_name = request.get("params", {}).get("name", "")
                arguments = request.get("params", {}).get("arguments", {})
                try:
                    result = await bridge.execute_tool(tool_name, arguments)
                    send_response(request_id, {
                        "content": [
                            {
                                "type": "text",
                                "text": result
                            }
                        ]
                    })
                except Exception as e:
                    send_response(request_id, None, {
                        "code": -32603,
                        "message": str(e)
                    })

            elif method == "ping":
                send_response(request_id, None)

        except json.JSONDecodeError:
            continue
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
