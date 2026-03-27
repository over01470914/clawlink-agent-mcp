@echo off
setlocal EnableExtensions EnableDelayedExpansion

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
    echo Detected CLAWLINK-AGENT already listening on port %PORT% ^(PID=%EXISTING_PID%^).
    set /p "RESTART_CHOICE=Restart service? ^(y/n^): "
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
    echo Port %PORT% is occupied by another service ^(PID=%EXISTING_PID%^). Startup aborted.
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

set "LOG_FILE=start_clawlink_agent.log"

echo Starting CLAWLINK-AGENT...
echo Port       : %PORT%
echo Agent ID   : %AGENT_ID%
echo Memory Dir : %MEMORY_DIR%
echo Logs       : %LOG_FILE%
echo.

start "" /b %PYTHON_CMD% -m clawlink_agent.cli serve --port %PORT% --agent-id %AGENT_ID% --display-name "%DISPLAY_NAME%" --memory-dir "%MEMORY_DIR%" --overwrite-mcp-config > "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo Failed to start service process.
  echo Check %LOG_FILE% for details.
  pause
  exit /b 1
)
echo Service process started in background.
echo Running health checks...

set "READY=0"
for /L %%I in (1,1,20) do (
  powershell -NoProfile -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:%PORT%/ping' -TimeoutSec 2 ^| Out-Null; exit 0 } catch { exit 1 }"
  if not errorlevel 1 (
    set "READY=1"
    goto :ready
  )
  timeout /t 1 >nul
)

:ready
if "%READY%"=="1" (
  powershell -NoProfile -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:%PORT%/ping' -TimeoutSec 2 ^| Out-Null; Write-Host '[OK] /ping' } catch { Write-Host '[FAIL] /ping' }"
  powershell -NoProfile -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:%PORT%/health' -TimeoutSec 2 ^| Out-Null; Write-Host '[OK] /health' } catch { Write-Host '[FAIL] /health' }"
  powershell -NoProfile -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:%PORT%/info' -TimeoutSec 2 ^| Out-Null; Write-Host '[OK] /info' } catch { Write-Host '[FAIL] /info' }"
) else (
  echo [WARN] Service did not respond on /ping within timeout.
  echo [WARN] Skip endpoint checks.
)

echo.
echo Launcher completed.
echo Press any key to close this launcher script only.
echo The CLAWLINK-AGENT service will keep running in background.
pause >nul
exit /b 0
