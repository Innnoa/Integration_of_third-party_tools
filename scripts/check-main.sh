#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "缺少 ${ENV_FILE}。"
  exit 1
fi

echo "== docker compose ps =="
docker compose --env-file "${ENV_FILE}" -f "${ROOT_DIR}/compose.yml" ps

echo
echo "== docker compose config check =="
docker compose --env-file "${ENV_FILE}" -f "${ROOT_DIR}/compose.yml" config >/dev/null
echo "compose 解析通过"

echo
echo "== unified urls =="
set -a
source "${ENV_FILE}"
set +a
echo "Keycloak:      ${PUBLIC_SCHEME}://${KEYCLOAK_PUBLIC_HOST}"
echo "Portainer:     ${PUBLIC_SCHEME}://${PORTAINER_PUBLIC_HOST}"
echo "KafkaUI:       ${PUBLIC_SCHEME}://${KAFKA_UI_PUBLIC_HOST}"
echo "Kafka broker:  ${KAFKA_HOST_BOOTSTRAP_SERVER}"
echo "RedisInsight:  ${PUBLIC_SCHEME}://${REDISINSIGHT_PUBLIC_HOST}"
echo "phpMyAdmin:    ${PUBLIC_SCHEME}://${PHPMYADMIN_PUBLIC_HOST}"
echo "mongo-express: ${PUBLIC_SCHEME}://${MONGO_EXPRESS_PUBLIC_HOST}"
echo "Harbor:        ${PUBLIC_SCHEME}://${HARBOR_PUBLIC_HOST}"
echo
echo "旧的 Web 宿主机端口入口已关闭，统一通过 80 端口 + Host 头访问。"
