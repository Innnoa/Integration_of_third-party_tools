#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
MAIN_COMPOSE_FILE="${ROOT_DIR}/compose.yml"
HARBOR_DIR="${ROOT_DIR}/harbor/installer"
HARBOR_COMPOSE_FILE="${HARBOR_DIR}/docker-compose.yml"

usage() {
  cat <<'EOF'
用法:
  ./scripts/services.sh start
  ./scripts/services.sh stop
  ./scripts/services.sh restart
  ./scripts/services.sh status

说明:
  start   启动主栈，并在 Harbor compose 存在时一并启动 Harbor
  stop    停止 Harbor 与主栈，但不删除容器和卷
  restart 先 stop 再 start
  status  查看主栈和 Harbor 当前状态
EOF
}

require_main_files() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "缺少 ${ENV_FILE}"
    exit 1
  fi

  if [[ ! -f "${MAIN_COMPOSE_FILE}" ]]; then
    echo "缺少 ${MAIN_COMPOSE_FILE}"
    exit 1
  fi
}

harbor_available() {
  [[ -f "${HARBOR_COMPOSE_FILE}" ]]
}

run_main_compose() {
  docker compose --env-file "${ENV_FILE}" -f "${MAIN_COMPOSE_FILE}" "$@"
}

run_harbor_compose() {
  (
    cd "${HARBOR_DIR}"
    docker compose "$@"
  )
}

start_all() {
  "${ROOT_DIR}/scripts/init-network.sh"
  echo "== 启动主栈 =="
  run_main_compose up -d

  if harbor_available; then
    echo
    echo "== 启动 Harbor =="
    run_harbor_compose up -d
  else
    echo
    echo "== 跳过 Harbor =="
    echo "未发现 ${HARBOR_COMPOSE_FILE}"
  fi
}

stop_all() {
  if harbor_available; then
    echo "== 停止 Harbor =="
    run_harbor_compose stop
    echo
  fi

  echo "== 停止主栈 =="
  run_main_compose stop
}

status_all() {
  echo "== 主栈状态 =="
  run_main_compose ps

  echo
  if harbor_available; then
    echo "== Harbor 状态 =="
    run_harbor_compose ps
  else
    echo "== Harbor 状态 =="
    echo "未发现 ${HARBOR_COMPOSE_FILE}"
  fi
}

main() {
  require_main_files

  if [[ $# -ne 1 ]]; then
    usage
    exit 1
  fi

  case "$1" in
    start)
      start_all
      ;;
    stop)
      stop_all
      ;;
    restart)
      stop_all
      echo
      start_all
      ;;
    status)
      status_all
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
