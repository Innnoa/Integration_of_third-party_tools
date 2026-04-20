#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "缺少 ${ENV_FILE}，请先从 .env.example 复制并修改。"
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

docker network inspect "${TOOLS_NETWORK}" >/dev/null 2>&1 || docker network create "${TOOLS_NETWORK}"
echo "Docker 网络已就绪: ${TOOLS_NETWORK}"
