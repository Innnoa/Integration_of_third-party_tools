#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "缺少 ${ENV_FILE}"
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

echo "== kafka container =="
docker compose --env-file "${ENV_FILE}" -f "${ROOT_DIR}/compose.yml" ps kafka

echo
echo "== topic list =="
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list || true

echo
echo "== bootstrap endpoints =="
echo "internal: ${KAFKA_BOOTSTRAP_SERVERS}"
echo "external: ${KAFKA_HOST_BOOTSTRAP_SERVER}"
