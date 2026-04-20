#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${ROOT_DIR}/outputs/runtime/panel"
PID_FILE="${RUNTIME_DIR}/panel.pid"
LOG_FILE="${RUNTIME_DIR}/panel.log"
PANEL_HOST="127.0.0.1"
PANEL_PORT="8090"

load_env() {
  PANEL_HOST="127.0.0.1"
  PANEL_PORT="8090"
  [[ -f "${ROOT_DIR}/.env" ]] || return 0

  while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
    line="${raw_line#"${raw_line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    case "${line}" in
      BUSINESS_PANEL_HOST=*)
        PANEL_HOST="${line#BUSINESS_PANEL_HOST=}"
        ;;
      BUSINESS_PANEL_PORT=*)
        PANEL_PORT="${line#BUSINESS_PANEL_PORT=}"
        ;;
    esac
  done < "${ROOT_DIR}/.env"
}

is_panel_process() {
  local pid="$1"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  kill -0 "${pid}" 2>/dev/null || return 1
  [[ -r "/proc/${pid}/cmdline" ]] || return 1

  local cmdline
  cmdline="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)"
  [[ "${cmdline}" == *"python"* && "${cmdline}" == *"business_panel.main"* ]]
}

current_panel_pid() {
  [[ -f "${PID_FILE}" ]] || return 1

  local pid
  pid="$(tr -d '[:space:]' < "${PID_FILE}" 2>/dev/null || true)"
  if is_panel_process "${pid}"; then
    echo "${pid}"
    return 0
  fi

  rm -f "${PID_FILE}"
  return 1
}

start_panel() {
  load_env
  mkdir -p "${RUNTIME_DIR}"
  if current_pid="$(current_panel_pid)"; then
    echo "panel 已在运行"
    return 0
  fi

  local pid
  pid="$(
    cd "${ROOT_DIR}"
    nohup python3 -m business_panel.main >"${LOG_FILE}" 2>&1 &
    echo "$!"
  )"
  echo "${pid}" > "${PID_FILE}"

  sleep 0.2
  if ! is_panel_process "${pid}"; then
    rm -f "${PID_FILE}"
    echo "panel 启动失败，请查看 ${LOG_FILE}"
    return 1
  fi

  echo "panel 已启动: http://${PANEL_HOST}:${PANEL_PORT}"
}

stop_panel() {
  local pid
  if pid="$(current_panel_pid)"; then
    kill "${pid}"
    for _ in {1..10}; do
      if ! kill -0 "${pid}" 2>/dev/null; then
        break
      fi
      sleep 0.1
    done
    if kill -0 "${pid}" 2>/dev/null; then
      echo "panel 停止超时"
      return 1
    fi
    rm -f "${PID_FILE}"
    echo "panel 已停止"
    return 0
  fi
  echo "panel 未运行"
}

status_panel() {
  local pid
  if pid="$(current_panel_pid)"; then
    echo "panel 运行中 (pid: ${pid})"
  else
    echo "panel 未运行"
  fi
}

case "${1:-}" in
  start)
    start_panel
    ;;
  stop)
    stop_panel
    ;;
  restart)
    stop_panel
    start_panel
    ;;
  status)
    status_panel
    ;;
  *)
    echo "用法: ./scripts/panel.sh {start|stop|restart|status}"
    exit 1
    ;;
esac
