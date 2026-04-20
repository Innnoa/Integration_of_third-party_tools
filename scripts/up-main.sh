#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${ROOT_DIR}/scripts/init-network.sh"
docker compose --env-file "${ROOT_DIR}/.env" -f "${ROOT_DIR}/compose.yml" up -d
echo "主栈已启动。建议继续执行 scripts/check-main.sh"
