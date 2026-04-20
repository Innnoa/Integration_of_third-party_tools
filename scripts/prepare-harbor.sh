#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
INSTALLER_DIR="${ROOT_DIR}/harbor/installer"
EXAMPLE_FILE="${ROOT_DIR}/harbor/harbor.yml.example"
TARGET_FILE="${INSTALLER_DIR}/harbor.yml"
OVERRIDE_SOURCE="${ROOT_DIR}/harbor/docker-compose.override.yml"
OVERRIDE_TARGET="${INSTALLER_DIR}/docker-compose.override.yml"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "缺少 ${ENV_FILE}，请先准备环境变量。"
  exit 1
fi

if [[ ! -d "${INSTALLER_DIR}" ]]; then
  echo "缺少 Harbor installer 目录: ${INSTALLER_DIR}"
  echo "请先下载并解压 Harbor online installer 到 harbor/installer/"
  exit 1
fi

if [[ ! -f "${INSTALLER_DIR}/install.sh" ]]; then
  echo "未找到 ${INSTALLER_DIR}/install.sh"
  echo "请确认 Harbor installer 已正确解压。"
  exit 1
fi

cp "${EXAMPLE_FILE}" "${TARGET_FILE}"
cp "${OVERRIDE_SOURCE}" "${OVERRIDE_TARGET}"

set -a
source "${ENV_FILE}"
set +a

sed -i "s/REPLACE_ME_PUBLIC_HOST/${PUBLIC_HOST}/g" "${TARGET_FILE}"
sed -i "s#external_url: http://${PUBLIC_HOST}#external_url: ${PUBLIC_SCHEME}://${HARBOR_PUBLIC_HOST}#g" "${TARGET_FILE}"
sed -i "s#hostname: ${PUBLIC_HOST}#hostname: ${HARBOR_PUBLIC_HOST}#g" "${TARGET_FILE}"
sed -i "s/ChangeMe_Harbor_Admin_123!/${HARBOR_ADMIN_PASSWORD//\//\\/}/g" "${TARGET_FILE}"
sed -i "s/REPLACE_ME_TOOLS_NETWORK/${TOOLS_NETWORK}/g" "${OVERRIDE_TARGET}"

echo "Harbor 模板已准备："
echo "  ${TARGET_FILE}"
echo "  ${OVERRIDE_TARGET}"
echo
echo "下一步："
echo "1. 检查 harbor.yml 是否还需要调整 data_volume、database password 等内容"
echo "2. 进入 harbor/installer/"
echo "3. 执行 ./install.sh --with-trivy"
