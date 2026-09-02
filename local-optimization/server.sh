#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$PROJECT_ROOT/tmp/local-optimization"
PID_FILE="$STATE_DIR/qwen-server.pid"
LOG_FILE="$STATE_DIR/qwen-server.log"

LLAMA_ROOT="${QWEN_LLAMA_ROOT:-/home/christina/.local/opt/llama.cpp}"
LLAMA_SERVER="${QWEN_LLAMA_SERVER:-$LLAMA_ROOT/bin/llama-server}"
MODEL_FILE="${QWEN_MODEL_FILE:-/home/christina/hf/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf}"
MODEL_ALIAS="${QWEN_MODEL_ALIAS:-qwen3.8-27b}"
HOST="${QWEN_HOST:-127.0.0.1}"
PORT="${QWEN_PORT:-8080}"

is_managed_running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(<"$PID_FILE")"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  [[ "$(ps -p "$pid" -o args= 2>/dev/null)" == *"llama-server"* ]]
}

start_server() {
  mkdir -p "$STATE_DIR"
  if is_managed_running; then
    echo "Managed Qwen server already running (PID $(<"$PID_FILE"))."
    exit 0
  fi
  if [[ ! -x "$LLAMA_SERVER" ]]; then
    echo "llama-server not executable: $LLAMA_SERVER" >&2
    exit 1
  fi
  if [[ ! -f "$MODEL_FILE" ]]; then
    echo "Model not found: $MODEL_FILE" >&2
    exit 1
  fi
  if ss -ltn | awk '{print $4}' | grep -Eq "(^|:)$PORT$"; then
    echo "Port $PORT is already occupied; refusing to start a second server." >&2
    exit 1
  fi

  local extra=()
  if [[ -n "${QWEN_EXTRA_ARGS:-}" ]]; then
    read -r -a extra <<<"$QWEN_EXTRA_ARGS"
  fi

  nohup env LD_LIBRARY_PATH="$LLAMA_ROOT/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    "$LLAMA_SERVER" \
    --model "$MODEL_FILE" \
    --alias "$MODEL_ALIAS" \
    --host "$HOST" --port "$PORT" \
    -ngl 99 -c 262144 \
    --cache-type-k q8_0 --cache-type-v q8_0 \
    --flash-attn on --jinja \
    --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0 \
    "${extra[@]}" >"$LOG_FILE" 2>&1 &
  local pid=$!
  printf '%s\n' "$pid" >"$PID_FILE"

  for _ in $(seq 1 180); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "Server exited during startup. See $LOG_FILE" >&2
      exit 1
    fi
    if curl -fsS --max-time 2 "http://$HOST:$PORT/v1/models" >/dev/null 2>&1; then
      echo "Qwen server ready: http://$HOST:$PORT (PID $pid)"
      exit 0
    fi
    sleep 1
  done
  echo "Server did not become ready within 180 seconds. See $LOG_FILE" >&2
  exit 1
}

stop_server() {
  if ! is_managed_running; then
    echo "No managed Qwen server is running."
    exit 0
  fi
  local pid
  pid="$(<"$PID_FILE")"
  kill "$pid"
  for _ in $(seq 1 60); do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$PID_FILE"
      echo "Stopped managed Qwen server (PID $pid)."
      exit 0
    fi
    sleep 1
  done
  echo "Server did not stop cleanly within 60 seconds; PID $pid remains." >&2
  exit 1
}

status_server() {
  if is_managed_running; then
    echo "Managed Qwen server running (PID $(<"$PID_FILE")) at http://$HOST:$PORT."
  elif curl -fsS --max-time 2 "http://$HOST:$PORT/v1/models" >/dev/null 2>&1; then
    echo "An unmanaged model server is reachable at http://$HOST:$PORT."
  else
    echo "No Qwen server is reachable at http://$HOST:$PORT."
    return 1
  fi
}

adopt_server() {
  mkdir -p "$STATE_DIR"
  if is_managed_running; then
    echo "Server is already managed (PID $(<"$PID_FILE"))."
    exit 0
  fi
  local pid
  pid="$(ss -ltnp 2>/dev/null | sed -nE "s/.*:${PORT}[[:space:]].*pid=([0-9]+).*/\1/p" | head -n 1)"
  if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
    echo "Could not resolve a process listening on port $PORT." >&2
    exit 1
  fi
  if [[ "$(ps -p "$pid" -o args= 2>/dev/null)" != *"llama-server"* ]]; then
    echo "PID $pid is not llama-server; refusing to adopt it." >&2
    exit 1
  fi
  printf '%s\n' "$pid" >"$PID_FILE"
  echo "Adopted existing Qwen server (PID $pid)."
}

case "${1:-status}" in
  start) start_server ;;
  stop) stop_server ;;
  restart) stop_server; start_server ;;
  status) status_server ;;
  adopt) adopt_server ;;
  *) echo "Usage: $0 {start|stop|restart|status|adopt}" >&2; exit 2 ;;
esac
