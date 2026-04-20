#!/usr/bin/env bash
set -euo pipefail

INSTALL_SKIP_PANEL=0
INSTALL_SKIP_HARBOR=0
INSTALL_REPAIR=0

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --skip-panel) INSTALL_SKIP_PANEL=1 ;;
      --skip-harbor) INSTALL_SKIP_HARBOR=1 ;;
      --repair) INSTALL_REPAIR=1 ;;
      *) echo "未知参数: $1" >&2; return 1 ;;
    esac
    shift
  done
}

log_phase() {
  local index="$1"
  local total="$2"
  local name="$3"
  printf '[%s/%s] %s\n' "${index}" "${total}" "${name}"
}

run_step() {
  local label="$1"
  local status=0
  shift

  "$@" || status=$?

  if [[ "${status}" == "0" ]]; then
    printf 'OK: %s\n' "${label}"
    return 0
  fi

  printf 'FAIL: %s\n' "${label}" >&2
  return "${status}"
}

run_harbor_install() (
  cd "${ROOT_DIR}/harbor/installer"
  ./install.sh --with-trivy
)

run_install() {
  local total=8

  log_phase 1 "${total}" "preflight"
  run_step "preflight" preflight

  log_phase 2 "${total}" "env"
  run_step "env" ensure_env

  log_phase 3 "${total}" "network"
  run_step "network" "${ROOT_DIR}/scripts/init-network.sh"

  log_phase 4 "${total}" "main_stack"
  run_step "main_stack" "${ROOT_DIR}/scripts/up-main.sh"

  log_phase 5 "${total}" "harbor_prepare"
  if [[ "${INSTALL_SKIP_HARBOR}" == "1" ]]; then
    printf 'SKIP: harbor_prepare\n'
  else
    run_step "harbor_prepare" "${ROOT_DIR}/scripts/prepare-harbor.sh"
  fi

  log_phase 6 "${total}" "harbor_install"
  if [[ "${INSTALL_SKIP_HARBOR}" == "1" ]]; then
    printf 'SKIP: harbor_install\n'
  else
    run_step "harbor_install" run_harbor_install
  fi

  log_phase 7 "${total}" "bootstrap"
  run_step "bootstrap" "${ROOT_DIR}/scripts/bootstrap-keycloak.sh"

  log_phase 8 "${total}" "panel"
  if [[ "${INSTALL_SKIP_PANEL}" == "1" ]]; then
    printf 'SKIP: panel\n'
  else
    run_step "panel" "${ROOT_DIR}/scripts/panel.sh" start
  fi
}

preflight() {
  [[ -f "${ROOT_DIR}/.env.example" ]] || { echo "缺少 .env.example" >&2; return 1; }
  if [[ "${INSTALL_SKIP_HARBOR}" == "1" ]]; then
    return 0
  fi
  [[ -f "${ROOT_DIR}/harbor/installer/install.sh" ]] || {
    echo "缺少 harbor/installer/install.sh" >&2
    return 1
  }
}

ensure_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "缺少命令: $1" >&2
    return 1
  }
}

random_secret() {
  ensure_command python3
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
}

set_env_if_missing() {
  local file="$1"
  local key="$2"
  local value="$3"
  if grep -q "^${key}=" "${file}"; then
    return 0
  fi
  if [[ -s "${file}" ]] && [[ -n "$(tail -c 1 "${file}")" ]]; then
    printf "\n" >>"${file}"
  fi
  printf "%s=%s\n" "${key}" "${value}" >>"${file}"
}

replace_placeholder_if_present() {
  local file="$1"
  local key="$2"
  local placeholder="$3"
  local value="$4"
  python3 - "${file}" "${key}" "${placeholder}" "${value}" <<'PY'
import pathlib
import sys

file_path = pathlib.Path(sys.argv[1])
key = sys.argv[2]
placeholder = sys.argv[3]
value = sys.argv[4]
target = f"{key}={placeholder}"
replacement = f"{key}={value}"

lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
changed = False
for index, line in enumerate(lines):
    normalized = line[:-1] if line.endswith("\n") else line
    if normalized == target:
        suffix = "\n" if line.endswith("\n") else ""
        lines[index] = replacement + suffix
        changed = True

if changed:
    file_path.write_text("".join(lines), encoding="utf-8")
PY
}

ensure_env() {
  local env_file="${ROOT_DIR}/.env"
  [[ -f "${env_file}" ]] || cp "${ROOT_DIR}/.env.example" "${env_file}"

  set_env_if_missing "${env_file}" "KEYCLOAK_PUBLIC_HOST" "auth.localhost"
  set_env_if_missing "${env_file}" "PORTAINER_PUBLIC_HOST" "portainer.localhost"
  set_env_if_missing "${env_file}" "KAFKA_UI_PUBLIC_HOST" "kafka.localhost"
  set_env_if_missing "${env_file}" "REDISINSIGHT_PUBLIC_HOST" "redis.localhost"
  set_env_if_missing "${env_file}" "PHPMYADMIN_PUBLIC_HOST" "pma.localhost"
  set_env_if_missing "${env_file}" "MONGO_EXPRESS_PUBLIC_HOST" "mongo.localhost"
  set_env_if_missing "${env_file}" "HARBOR_PUBLIC_HOST" "harbor.localhost"
  set_env_if_missing "${env_file}" "BUSINESS_PANEL_HOST" "127.0.0.1"
  set_env_if_missing "${env_file}" "BUSINESS_PANEL_PORT" "8090"

  if grep -q "^KEYCLOAK_ADMIN_PASSWORD=ChangeMe_Keycloak_Admin_123!$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "KEYCLOAK_ADMIN_PASSWORD" "ChangeMe_Keycloak_Admin_123!" "$(random_secret)"
  fi
  if grep -q "^KEYCLOAK_DB_PASSWORD=ChangeMe_Keycloak_Db_123!$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "KEYCLOAK_DB_PASSWORD" "ChangeMe_Keycloak_Db_123!" "$(random_secret)"
  fi
  if grep -q "^PORTAINER_CLIENT_SECRET=ChangeMe_Portainer_Secret_123!$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "PORTAINER_CLIENT_SECRET" "ChangeMe_Portainer_Secret_123!" "$(random_secret)"
  fi
  if grep -q "^OAUTH2_PROXY_CLIENT_SECRET=ChangeMe_OAuth2Proxy_Secret_123!$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "OAUTH2_PROXY_CLIENT_SECRET" "ChangeMe_OAuth2Proxy_Secret_123!" "$(random_secret)"
  fi
  if grep -q "^OAUTH2_PROXY_COOKIE_SECRET=REPLACE_WITH_32_BYTE_SECRET$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "OAUTH2_PROXY_COOKIE_SECRET" "REPLACE_WITH_32_BYTE_SECRET" "$(python3 - <<'PY'
import secrets
print(secrets.token_hex(16))
PY
)"
  fi
}
