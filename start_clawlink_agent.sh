#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PORT="8430"
AGENT_ID="agent-local-01"
DISPLAY_NAME="Local Agent 01"
MEMORY_DIR="./memories"

find_listen_pid() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null | head -n 1
    return 0
  fi

  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "sport = :${port}" 2>/dev/null | awk -F'pid=' 'NR>1 && NF>1 {split($2, a, ","); print a[1]; exit}'
    return 0
  fi

  echo ""
}

http_ok() {
  local url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS "$url" >/dev/null 2>&1
    return $?
  fi

  if command -v python3 >/dev/null 2>&1; then
    python3 - "$url" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

url = sys.argv[1]
with urllib.request.urlopen(url, timeout=2):
    pass
PY
    return $?
  fi

  if command -v python >/dev/null 2>&1; then
    python - "$url" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

url = sys.argv[1]
with urllib.request.urlopen(url, timeout=2):
    pass
PY
    return $?
  fi

  return 1
}

EXISTING_PID="$(find_listen_pid "$PORT" || true)"
if [[ -n "${EXISTING_PID}" ]]; then
  EXISTING_CMD="$(ps -p "$EXISTING_PID" -o command= 2>/dev/null || true)"
  if [[ "$EXISTING_CMD" == *"clawlink_agent.cli serve"* ]]; then
    echo "Detected CLAWLINK-AGENT already listening on port ${PORT} (pid=${EXISTING_PID})."
    read -r -p "Restart service? (y/n): " RESTART_CHOICE
    if [[ "${RESTART_CHOICE,,}" == "y" ]]; then
      kill "$EXISTING_PID" || { echo "Failed to stop existing process."; exit 1; }
      sleep 1
    else
      echo "Startup cancelled."
      exit 0
    fi
  else
    echo "Port ${PORT} is occupied by another service (pid=${EXISTING_PID}). Startup aborted."
    exit 1
  fi
fi

mkdir -p "$MEMORY_DIR"

PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "Python is not found in PATH."
  exit 1
fi

echo "Starting CLAWLINK-AGENT..."
echo "Port       : ${PORT}"
echo "Agent ID   : ${AGENT_ID}"
echo "Memory Dir : ${MEMORY_DIR}"
echo

LOG_FILE="./start_clawlink_agent.log"
"$PYTHON_CMD" -m clawlink_agent.cli serve \
  --port "$PORT" \
  --agent-id "$AGENT_ID" \
  --display-name "$DISPLAY_NAME" \
  --memory-dir "$MEMORY_DIR" \
  --overwrite-mcp-config \
  >"$LOG_FILE" 2>&1 &

SERVICE_PID=$!
echo "Service process started in background. pid=${SERVICE_PID}"
echo "Logs: ${LOG_FILE}"
echo "Running health checks..."

READY=0
for _ in $(seq 1 20); do
  if http_ok "http://127.0.0.1:${PORT}/ping"; then
    READY=1
    break
  fi
  sleep 1
done

if [[ "$READY" == "1" ]]; then
  if http_ok "http://127.0.0.1:${PORT}/ping"; then
    echo "[OK] /ping"
  else
    echo "[FAIL] /ping"
  fi

  if http_ok "http://127.0.0.1:${PORT}/health"; then
    echo "[OK] /health"
  else
    echo "[FAIL] /health"
  fi

  if http_ok "http://127.0.0.1:${PORT}/info"; then
    echo "[OK] /info"
  else
    echo "[FAIL] /info"
  fi
else
  echo "[WARN] Service did not respond on /ping within timeout."
  echo "[WARN] Skip endpoint checks."
fi

echo
echo "Launcher completed."
echo "Press Enter to close this launcher script only."
echo "The CLAWLINK-AGENT service will keep running in background."
read -r _
