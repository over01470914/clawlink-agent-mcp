@echo off
setlocal

chcp 65001 >nul
set "PYTHONUTF8=1"

cd /d "%~dp0"

set "PORT=8430"
set "AGENT_ID=agent-local-01"
set "DISPLAY_NAME=Local Agent 01"
set "MEMORY_DIR=./memories"

set "EXISTING_PID="
for /f %%P in ('powershell -NoProfile -Command "$p = Get-NetTCPConnection -State Listen -LocalPort %PORT% -ErrorAction SilentlyContinue ^| Select-Object -First 1 -ExpandProperty OwningProcess; if ($p) { $p }"') do set "EXISTING_PID=%%P"

if defined EXISTING_PID (
  set "IS_CLAWLINK="
  powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter 'ProcessId=%EXISTING_PID%'; if ($p -and $p.CommandLine -match 'clawlink_agent\.cli\s+serve') { exit 0 } else { exit 1 }"
  if not errorlevel 1 set "IS_CLAWLINK=1"

  if defined IS_CLAWLINK (
    echo Detected CLAWLINK-AGENT already listening on port %PORT% (PID=%EXISTING_PID%).
    set /p "RESTART_CHOICE=Restart service? (y/n): "
    if /I "%RESTART_CHOICE%"=="y" (
      taskkill /PID %EXISTING_PID% /F >nul 2>nul
      if errorlevel 1 (
        echo Failed to stop existing service. Please check permissions and retry.
        pause
        exit /b 1
      )
      timeout /t 1 >nul
    ) else (
      echo Startup cancelled.
      exit /b 0
    )
  ) else (
    echo Port %PORT% is occupied by another service (PID=%EXISTING_PID%). Startup aborted.
    pause
    exit /b 1
  )
)

if not exist "%MEMORY_DIR%" mkdir "%MEMORY_DIR%"

set "PYTHON_CMD=py"
where %PYTHON_CMD% >nul 2>nul
if errorlevel 1 (
  set "PYTHON_CMD=python"
)

echo Starting CLAWLINK-AGENT...
echo Port       : %PORT%
echo Agent ID   : %AGENT_ID%
echo Memory Dir : %MEMORY_DIR%
echo.

%PYTHON_CMD% -m clawlink_agent.cli serve ^
  --port %PORT% ^
  --agent-id %AGENT_ID% ^
  --display-name "%DISPLAY_NAME%" ^
  --memory-dir "%MEMORY_DIR%" ^
  --overwrite-mcp-config

if errorlevel 1 (
  echo.
  echo Service exited with an error.
  pause
)
