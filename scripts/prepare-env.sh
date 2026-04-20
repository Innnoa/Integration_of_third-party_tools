#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE_ENV="${ROOT_DIR}/.env.example"
TARGET_ENV="${ROOT_DIR}/.env"

if [[ -f "${TARGET_ENV}" ]]; then
  echo ".env 已存在，不覆盖。"
  exit 0
fi

cp "${EXAMPLE_ENV}" "${TARGET_ENV}"
echo "已生成 ${TARGET_ENV}。"
echo "请至少修改 PUBLIC_HOST、各 *_PUBLIC_HOST 以及所有密码、secret，再执行其他脚本。"
