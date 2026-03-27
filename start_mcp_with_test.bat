@echo off
chcp 65001 >nul
echo ============================================================
echo CLAWLINK-AGENT MCP 启动脚本
echo ============================================================
echo.

REM 配置
set AGENT_PORT=8430
set AGENT_ID=test-agent
set MEMORY_DIR=..\..\test_memories
set VENV_PYTHON=..\..\venv\Scripts\python.exe
set MCP_SCRIPT=scripts\test_mcp_connection.py

echo [1/3] 正在启动 CLAWLINK-AGENT 服务...
start "CLAWLINK-AGENT" cmd /k "%VENV_PYTHON% -m clawlink_agent.cli serve --port %AGENT_PORT% --agent-id %AGENT_ID% --memory-dir %MEMORY_DIR%"

REM 等待服务启动
echo [2/3] 等待服务启动...
timeout /t 3 /nobreak >nul

REM 运行 MCP 连接测试
echo [3/3] 运行 MCP 连接测试...
echo.
echo ============================================================
call %VENV_PYTHON% %MCP_SCRIPT%

echo.
echo ============================================================
echo 按任意键关闭此窗口...
pause >nul
