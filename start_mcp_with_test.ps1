# CLAWLINK-AGENT MCP 启动脚本 (PowerShell)
# 使用方法: 右键 -> 用 PowerShell 运行

param(
    [string]$AgentUrl = "http://127.0.0.1:8430",
    [string]$AgentId = "test-agent",
    [string]$MemoryDir = "..\..\test_memories"
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$TestScript = Join-Path $PSScriptRoot "scripts\test_mcp_connection.py"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "CLAWLINK-AGENT MCP 启动脚本" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/3] 正在启动 CLAWLINK-AGENT 服务..." -ForegroundColor Yellow

$AgentProcess = Start-Process -FilePath $VenvPython `
    -ArgumentList "-m", "clawlink_agent.cli", "serve", "--port", "8430", "--agent-id", $AgentId, "--memory-dir", $MemoryDir `
    -PassThru -WindowStyle Normal

Write-Host "    Agent PID: $($AgentProcess.Id)" -ForegroundColor Gray

Write-Host "[2/3] 等待服务启动 (3秒)..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

Write-Host "[3/3] 运行 MCP 连接测试..." -ForegroundColor Yellow
Write-Host ""

$env:PYTHONPATH = $ProjectRoot

try {
    $result = & $VenvPython $TestScript $AgentUrl --json 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "✅ MCP 服务已成功启动并通过测试！" -ForegroundColor Green
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "Agent 地址: $AgentUrl" -ForegroundColor White
        Write-Host "Agent ID: $AgentId" -ForegroundColor White
        Write-Host ""
        Write-Host "现在可以在 TRAE IDE 中连接此 MCP 服务了。" -ForegroundColor Cyan
    } else {
        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Red
        Write-Host "❌ MCP 连接测试失败" -ForegroundColor Red
        Write-Host "============================================================" -ForegroundColor Red
    }
} catch {
    Write-Host "错误: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "按 Enter 键退出..."
Read-Host
