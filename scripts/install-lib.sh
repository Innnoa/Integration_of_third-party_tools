#!/usr/bin/env bash
set -euo pipefail

INSTALL_SKIP_PANEL=0
INSTALL_SKIP_HARBOR=1
INSTALL_REPAIR=0
INSTALL_BASE_DOMAIN="${INSTALL_BASE_DOMAIN:-}"
INSTALL_PUBLIC_IP="${INSTALL_PUBLIC_IP:-}"
INSTALL_HOSTS_FILE="${INSTALL_HOSTS_FILE:-}"
INSTALL_HELPER="${INSTALL_HELPER:-}"
INSTALL_VERIFICATION_SUMMARY="${INSTALL_VERIFICATION_SUMMARY:-}"
INSTALL_REQUIRED_COMMANDS="${INSTALL_REQUIRED_COMMANDS:-python3 docker docker-compose-plugin}"
INSTALL_PACKAGE_MANAGER="${INSTALL_PACKAGE_MANAGER:-}"
INSTALL_RETRY_DELAY_SECONDS="${INSTALL_RETRY_DELAY_SECONDS:-0}"
INSTALL_MAIN_STACK_RETRIES="${INSTALL_MAIN_STACK_RETRIES:-3}"
INSTALL_BOOTSTRAP_RETRIES="${INSTALL_BOOTSTRAP_RETRIES:-2}"
INSTALL_CONFIGURE_RETRIES="${INSTALL_CONFIGURE_RETRIES:-2}"
INSTALL_VERIFY_RETRIES="${INSTALL_VERIFY_RETRIES:-2}"

declare -ag INSTALL_STAGE_RESULTS=()
INSTALL_OVERALL_STATUS="success"

parse_args() {
  INSTALL_HOSTS_FILE="${INSTALL_HOSTS_FILE:-/etc/hosts}"
  INSTALL_HELPER="${ROOT_DIR}/scripts/install_helper.py"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --skip-panel) INSTALL_SKIP_PANEL=1 ;;
      --with-harbor) INSTALL_SKIP_HARBOR=0 ;;
      --skip-harbor) INSTALL_SKIP_HARBOR=1 ;;
      --repair) INSTALL_REPAIR=1 ;;
      --base-domain)
        shift
        [[ $# -gt 0 ]] || { echo "缺少参数值: --base-domain" >&2; return 1; }
        INSTALL_BASE_DOMAIN="$1"
        ;;
      --public-ip)
        shift
        [[ $# -gt 0 ]] || { echo "缺少参数值: --public-ip" >&2; return 1; }
        INSTALL_PUBLIC_IP="$1"
        ;;
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

set_overall_status() {
  local next_status="$1"
  if [[ "${INSTALL_OVERALL_STATUS}" == "failed" ]]; then
    return 0
  fi
  case "${next_status}" in
    failed) INSTALL_OVERALL_STATUS="failed" ;;
    degraded)
      if [[ "${INSTALL_OVERALL_STATUS}" == "success" ]]; then
        INSTALL_OVERALL_STATUS="degraded"
      fi
      ;;
  esac
}

record_stage_result() {
  local label="$1"
  local status="$2"
  INSTALL_STAGE_RESULTS+=("${label}=${status}")
}

sleep_for_retry() {
  if [[ "${INSTALL_RETRY_DELAY_SECONDS}" != "0" ]]; then
    sleep "${INSTALL_RETRY_DELAY_SECONDS}"
  fi
}

run_step() {
  local label="$1"
  local attempts="$2"
  shift 2

  local attempt=1
  local status=0

  while (( attempt <= attempts )); do
    "$@" && {
      record_stage_result "${label}" "ok"
      printf 'OK: %s\n' "${label}"
      return 0
    }
    status=$?
    if (( attempt < attempts )); then
      printf 'RETRY: %s (%s/%s)\n' "${label}" "${attempt}" "${attempts}" >&2
      sleep_for_retry
    fi
    attempt=$((attempt + 1))
  done

  record_stage_result "${label}" "failed"
  set_overall_status "failed"
  printf 'FAIL: %s\n' "${label}" >&2
  return "${status}"
}

run_optional_step() {
  local label="$1"
  local attempts="$2"
  shift 2

  local attempt=1
  local status=0

  while (( attempt <= attempts )); do
    "$@" && {
      record_stage_result "${label}" "ok"
      printf 'OK: %s\n' "${label}"
      return 0
    }
    status=$?
    if (( attempt < attempts )); then
      printf 'RETRY: %s (%s/%s)\n' "${label}" "${attempt}" "${attempts}" >&2
      sleep_for_retry
    fi
    attempt=$((attempt + 1))
  done

  record_stage_result "${label}" "degraded"
  set_overall_status "degraded"
  printf 'WARN: %s\n' "${label}" >&2
  return 0
}

run_harbor_install() (
  cd "${ROOT_DIR}/harbor/installer"
  ./install.sh --with-trivy
)

configure_portainer_stage() {
  local env_file="${ROOT_DIR}/.env"
  local install_http_base_url="${INSTALL_HTTP_BASE_URL:-http://127.0.0.1}"

  set -a
  # shellcheck disable=SC1090
  source "${env_file}"
  set +a

  python3 "${INSTALL_HELPER}" configure-portainer \
    --base-url "${install_http_base_url}" \
    --host-header "${PORTAINER_PUBLIC_HOST}" \
    --admin-user "${PORTAINER_ADMIN_USER}" \
    --admin-password "${PORTAINER_ADMIN_PASSWORD}" \
    --client-id "${PORTAINER_CLIENT_ID}" \
    --client-secret "${PORTAINER_CLIENT_SECRET}" \
    --auth-url "${PUBLIC_SCHEME}://${KEYCLOAK_PUBLIC_HOST}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/auth" \
    --token-url "${PUBLIC_SCHEME}://${KEYCLOAK_PUBLIC_HOST}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token" \
    --resource-url "${PUBLIC_SCHEME}://${KEYCLOAK_PUBLIC_HOST}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/userinfo" \
    --logout-url "${PUBLIC_SCHEME}://${KEYCLOAK_PUBLIC_HOST}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/logout" \
    --redirect-url "${PUBLIC_SCHEME}://${PORTAINER_PUBLIC_HOST}/"
}

verify_install_stage() {
  local env_file="${ROOT_DIR}/.env"
  local install_http_base_url="${INSTALL_HTTP_BASE_URL:-http://127.0.0.1}"
  local verify_output
  local verify_status

  set -a
  # shellcheck disable=SC1090
  source "${env_file}"
  set +a

  verify_output="$(
    python3 "${INSTALL_HELPER}" verify-install \
      --base-url "${install_http_base_url}" \
      --host "${KEYCLOAK_PUBLIC_HOST}" \
      --host "${PORTAINER_PUBLIC_HOST}" \
      --host "${KAFKA_UI_PUBLIC_HOST}" \
      --host "${REDISINSIGHT_PUBLIC_HOST}" \
      --host "${PHPMYADMIN_PUBLIC_HOST}" \
      --host "${MONGO_EXPRESS_PUBLIC_HOST}" \
      --host "${NACOS_PUBLIC_HOST}" \
      --host "${NIGHTINGALE_PUBLIC_HOST}"
  )" || return 1

  if [[ "${INSTALL_SKIP_HARBOR}" != "1" ]]; then
    verify_output="$(
      python3 "${INSTALL_HELPER}" verify-install \
        --base-url "${install_http_base_url}" \
        --host "${KEYCLOAK_PUBLIC_HOST}" \
        --host "${PORTAINER_PUBLIC_HOST}" \
        --host "${KAFKA_UI_PUBLIC_HOST}" \
        --host "${REDISINSIGHT_PUBLIC_HOST}" \
        --host "${PHPMYADMIN_PUBLIC_HOST}" \
        --host "${MONGO_EXPRESS_PUBLIC_HOST}" \
        --host "${NACOS_PUBLIC_HOST}" \
        --host "${NIGHTINGALE_PUBLIC_HOST}" \
        --host "${HARBOR_PUBLIC_HOST}"
    )" || return 1
  fi

  verify_status="$(python3 - "${verify_output}" <<'PY'
import json
import sys

summary = json.loads(sys.argv[1])
print(summary.get("overall", "error"))
PY
)"
  INSTALL_VERIFICATION_SUMMARY="${verify_output}"
  [[ "${verify_status}" == "ready" ]]
}

preflight() {
  [[ -f "${ROOT_DIR}/.env.example" ]] || { echo "缺少 .env.example" >&2; return 1; }
  [[ -f "${INSTALL_HELPER}" ]] || { echo "缺少 ${INSTALL_HELPER}" >&2; return 1; }
  require_base_domain_if_needed || return 1
  if [[ "${INSTALL_SKIP_HARBOR}" == "1" ]]; then
    return 0
  fi
  [[ -f "${ROOT_DIR}/harbor/installer/install.sh" ]] || {
    echo "缺少 harbor/installer/install.sh" >&2
    return 1
  }
}

read_env_value() {
  local file="$1"
  local key="$2"
  python3 - "$file" "$key" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
prefix = f"{key}="
if not path.exists():
    raise SystemExit(0)
for raw in path.read_text(encoding="utf-8").splitlines():
    if raw.startswith(prefix):
        print(raw[len(prefix):])
        break
PY
}

needs_base_domain() {
  local file="${ROOT_DIR}/.env"
  if [[ ! -f "${file}" ]]; then
    file="${ROOT_DIR}/.env.example"
  fi

  local public_host
  public_host="$(read_env_value "${file}" "PUBLIC_HOST")"
  [[ "${public_host}" == "REPLACE_ME_PUBLIC_HOST" ]]
}

require_base_domain_if_needed() {
  if [[ -n "${INSTALL_BASE_DOMAIN}" ]]; then
    return 0
  fi
  if needs_base_domain; then
    echo "缺少必填参数: --base-domain" >&2
    return 1
  fi
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

upsert_env_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  python3 - "$file" "$key" "$value" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
prefix = f"{key}="
lines = path.read_text(encoding="utf-8").splitlines()
for index, line in enumerate(lines):
    if line.startswith(prefix):
        lines[index] = prefix + value
        break
else:
    lines.append(prefix + value)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

derive_public_hosts() {
  KEYCLOAK_PUBLIC_HOST="auth.${INSTALL_BASE_DOMAIN}"
  PORTAINER_PUBLIC_HOST="portainer.${INSTALL_BASE_DOMAIN}"
  KAFKA_UI_PUBLIC_HOST="kafka.${INSTALL_BASE_DOMAIN}"
  REDISINSIGHT_PUBLIC_HOST="redis.${INSTALL_BASE_DOMAIN}"
  PHPMYADMIN_PUBLIC_HOST="pma.${INSTALL_BASE_DOMAIN}"
  MONGO_EXPRESS_PUBLIC_HOST="mongo.${INSTALL_BASE_DOMAIN}"
  NACOS_PUBLIC_HOST="nacos.${INSTALL_BASE_DOMAIN}"
  NIGHTINGALE_PUBLIC_HOST="nightingale.${INSTALL_BASE_DOMAIN}"
  HARBOR_PUBLIC_HOST="harbor.${INSTALL_BASE_DOMAIN}"
}

resolve_public_ip() {
  if [[ -n "${INSTALL_PUBLIC_IP}" ]]; then
    printf '%s\n' "${INSTALL_PUBLIC_IP}"
    return 0
  fi
  python3 "${INSTALL_HELPER}" detect-public-ip
}

ensure_managed_env_values() {
  local env_file="$1"
  local public_ip
  public_ip="$(resolve_public_ip)"
  derive_public_hosts

  upsert_env_value "${env_file}" "PUBLIC_HOST" "${public_ip}"
  upsert_env_value "${env_file}" "KAFKA_HOST_BOOTSTRAP_SERVER" "${public_ip}:9092"
  upsert_env_value "${env_file}" "KEYCLOAK_PUBLIC_HOST" "${KEYCLOAK_PUBLIC_HOST}"
  upsert_env_value "${env_file}" "PORTAINER_PUBLIC_HOST" "${PORTAINER_PUBLIC_HOST}"
  upsert_env_value "${env_file}" "KAFKA_UI_PUBLIC_HOST" "${KAFKA_UI_PUBLIC_HOST}"
  upsert_env_value "${env_file}" "REDISINSIGHT_PUBLIC_HOST" "${REDISINSIGHT_PUBLIC_HOST}"
  upsert_env_value "${env_file}" "PHPMYADMIN_PUBLIC_HOST" "${PHPMYADMIN_PUBLIC_HOST}"
  upsert_env_value "${env_file}" "MONGO_EXPRESS_PUBLIC_HOST" "${MONGO_EXPRESS_PUBLIC_HOST}"
  upsert_env_value "${env_file}" "NACOS_PUBLIC_HOST" "${NACOS_PUBLIC_HOST}"
  upsert_env_value "${env_file}" "NIGHTINGALE_PUBLIC_HOST" "${NIGHTINGALE_PUBLIC_HOST}"
  if [[ "${INSTALL_SKIP_HARBOR}" != "1" ]]; then
    upsert_env_value "${env_file}" "HARBOR_PUBLIC_HOST" "${HARBOR_PUBLIC_HOST}"
  fi

  python3 "${INSTALL_HELPER}" sync-hosts \
    --hosts-file "${INSTALL_HOSTS_FILE}" \
    --public-ip "${public_ip}" \
    --host "${KEYCLOAK_PUBLIC_HOST}" \
    --host "${PORTAINER_PUBLIC_HOST}" \
    --host "${KAFKA_UI_PUBLIC_HOST}" \
    --host "${REDISINSIGHT_PUBLIC_HOST}" \
    --host "${PHPMYADMIN_PUBLIC_HOST}" \
    --host "${MONGO_EXPRESS_PUBLIC_HOST}" \
    --host "${NACOS_PUBLIC_HOST}" \
    --host "${NIGHTINGALE_PUBLIC_HOST}"
  if [[ "${INSTALL_SKIP_HARBOR}" != "1" ]]; then
    python3 "${INSTALL_HELPER}" sync-hosts \
      --hosts-file "${INSTALL_HOSTS_FILE}" \
      --public-ip "${public_ip}" \
      --host "${KEYCLOAK_PUBLIC_HOST}" \
      --host "${PORTAINER_PUBLIC_HOST}" \
      --host "${KAFKA_UI_PUBLIC_HOST}" \
      --host "${REDISINSIGHT_PUBLIC_HOST}" \
      --host "${PHPMYADMIN_PUBLIC_HOST}" \
      --host "${MONGO_EXPRESS_PUBLIC_HOST}" \
      --host "${NACOS_PUBLIC_HOST}" \
      --host "${NIGHTINGALE_PUBLIC_HOST}" \
      --host "${HARBOR_PUBLIC_HOST}"
  fi
}

ensure_env() {
  local env_file="${ROOT_DIR}/.env"
  [[ -f "${env_file}" ]] || cp "${ROOT_DIR}/.env.example" "${env_file}"

  set_env_if_missing "${env_file}" "PUBLIC_SCHEME" "http"
  set_env_if_missing "${env_file}" "PUBLIC_HOST" "localhost"
  set_env_if_missing "${env_file}" "BROWSER_HOST" "localhost"
  set_env_if_missing "${env_file}" "KEYCLOAK_PUBLIC_HOST" "auth.localhost"
  set_env_if_missing "${env_file}" "KEYCLOAK_REALM" "infra"
  set_env_if_missing "${env_file}" "PORTAINER_PUBLIC_HOST" "portainer.localhost"
  set_env_if_missing "${env_file}" "PORTAINER_CLIENT_ID" "portainer"
  set_env_if_missing "${env_file}" "PORTAINER_CLIENT_SECRET" "ChangeMe_Portainer_Secret_123!"
  set_env_if_missing "${env_file}" "PORTAINER_ADMIN_USER" "admin"
  set_env_if_missing "${env_file}" "PORTAINER_ADMIN_PASSWORD" "ChangeMe_Portainer_Admin_123!"
  set_env_if_missing "${env_file}" "KAFKA_UI_PUBLIC_HOST" "kafka.localhost"
  set_env_if_missing "${env_file}" "REDISINSIGHT_PUBLIC_HOST" "redis.localhost"
  set_env_if_missing "${env_file}" "PHPMYADMIN_PUBLIC_HOST" "pma.localhost"
  set_env_if_missing "${env_file}" "MONGO_EXPRESS_PUBLIC_HOST" "mongo.localhost"
  set_env_if_missing "${env_file}" "HARBOR_PUBLIC_HOST" "harbor.localhost"
  set_env_if_missing "${env_file}" "NACOS_PUBLIC_HOST" "nacos.localhost"
  set_env_if_missing "${env_file}" "NIGHTINGALE_PUBLIC_HOST" "nightingale.localhost"
  set_env_if_missing "${env_file}" "BUSINESS_PANEL_HOST" "127.0.0.1"
  set_env_if_missing "${env_file}" "BUSINESS_PANEL_PORT" "8090"
  set_env_if_missing "${env_file}" "PHPMYADMIN_ALLOWED_GROUP" "/platform-admins"
  set_env_if_missing "${env_file}" "PHPMYADMIN_AUTOLOGIN_USER" "pma_appdb_admin"
  set_env_if_missing "${env_file}" "PHPMYADMIN_AUTOLOGIN_PASSWORD" "ChangeMe_PhpMyAdmin_Autologin_123!"
  set_env_if_missing "${env_file}" "NIGHTINGALE_DB_PASSWORD" "ChangeMe_Nightingale_Db_123!"
  set_env_if_missing "${env_file}" "NIGHTINGALE_DB_ROOT_PASSWORD" "ChangeMe_Nightingale_DbRoot_123!"
  set_env_if_missing "${env_file}" "NIGHTINGALE_REDIS_PASSWORD" "ChangeMe_Nightingale_Redis_123!"
  set_env_if_missing "${env_file}" "NIGHTINGALE_CLIENT_SECRET" "ChangeMe_Nightingale_Client_123!"

  if grep -q "^KEYCLOAK_ADMIN_PASSWORD=ChangeMe_Keycloak_Admin_123!$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "KEYCLOAK_ADMIN_PASSWORD" "ChangeMe_Keycloak_Admin_123!" "$(random_secret)"
  fi
  if grep -q "^KEYCLOAK_DB_PASSWORD=ChangeMe_Keycloak_Db_123!$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "KEYCLOAK_DB_PASSWORD" "ChangeMe_Keycloak_Db_123!" "$(random_secret)"
  fi
  if grep -q "^PORTAINER_CLIENT_SECRET=ChangeMe_Portainer_Secret_123!$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "PORTAINER_CLIENT_SECRET" "ChangeMe_Portainer_Secret_123!" "$(random_secret)"
  fi
  if grep -q "^PORTAINER_ADMIN_PASSWORD=ChangeMe_Portainer_Admin_123!$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "PORTAINER_ADMIN_PASSWORD" "ChangeMe_Portainer_Admin_123!" "$(random_secret)"
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
  if grep -q "^PHPMYADMIN_AUTOLOGIN_PASSWORD=ChangeMe_PhpMyAdmin_Autologin_123!$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "PHPMYADMIN_AUTOLOGIN_PASSWORD" "ChangeMe_PhpMyAdmin_Autologin_123!" "$(random_secret)"
  fi
  if grep -q "^NIGHTINGALE_DB_PASSWORD=ChangeMe_Nightingale_Db_123!$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "NIGHTINGALE_DB_PASSWORD" "ChangeMe_Nightingale_Db_123!" "$(random_secret)"
  fi
  if grep -q "^NIGHTINGALE_DB_ROOT_PASSWORD=ChangeMe_Nightingale_DbRoot_123!$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "NIGHTINGALE_DB_ROOT_PASSWORD" "ChangeMe_Nightingale_DbRoot_123!" "$(random_secret)"
  fi
  if grep -q "^NIGHTINGALE_REDIS_PASSWORD=ChangeMe_Nightingale_Redis_123!$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "NIGHTINGALE_REDIS_PASSWORD" "ChangeMe_Nightingale_Redis_123!" "$(random_secret)"
  fi
  if grep -q "^NIGHTINGALE_CLIENT_SECRET=ChangeMe_Nightingale_Client_123!$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "NIGHTINGALE_CLIENT_SECRET" "ChangeMe_Nightingale_Client_123!" "$(random_secret)"
  fi

  if [[ -n "${INSTALL_BASE_DOMAIN}" ]]; then
    ensure_managed_env_values "${env_file}"
  fi
}

command_missing() {
  local name="$1"
  case "${name}" in
    docker-compose-plugin)
      ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1
      ;;
    *)
      ! command -v "${name}" >/dev/null 2>&1
      ;;
  esac
}

collect_missing_dependencies() {
  local dep
  for dep in ${INSTALL_REQUIRED_COMMANDS}; do
    if command_missing "${dep}"; then
      printf '%s\n' "${dep}"
    fi
  done
}

detect_package_manager() {
  if [[ -n "${INSTALL_PACKAGE_MANAGER}" ]]; then
    printf '%s\n' "${INSTALL_PACKAGE_MANAGER}"
    return 0
  fi

  if command -v apt-get >/dev/null 2>&1; then
    printf 'apt-get\n'
  elif command -v dnf >/dev/null 2>&1; then
    printf 'dnf\n'
  elif command -v yum >/dev/null 2>&1; then
    printf 'yum\n'
  elif command -v pacman >/dev/null 2>&1; then
    printf 'pacman\n'
  elif command -v zypper >/dev/null 2>&1; then
    printf 'zypper\n'
  else
    return 1
  fi
}

package_name_for_dependency() {
  local manager="$1"
  local dependency="$2"

  case "${dependency}" in
    python3)
      case "${manager}" in
        pacman) printf 'python\n' ;;
        *) printf 'python3\n' ;;
      esac
      ;;
    docker)
      case "${manager}" in
        apt-get) printf 'docker.io\n' ;;
        *) printf 'docker\n' ;;
      esac
      ;;
    docker-compose-plugin)
      case "${manager}" in
        pacman|zypper) printf 'docker-compose\n' ;;
        *) printf 'docker-compose-plugin\n' ;;
      esac
      ;;
    *)
      printf '%s\n' "${dependency}"
      ;;
  esac
}

append_unique_word() {
  local current="$1"
  local candidate="$2"
  case " ${current} " in
    *" ${candidate} "*) printf '%s\n' "${current}" ;;
    *)
      if [[ -n "${current}" ]]; then
        printf '%s %s\n' "${current}" "${candidate}"
      else
        printf '%s\n' "${candidate}"
      fi
      ;;
  esac
}

run_privileged() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  else
    if ! command -v sudo >/dev/null 2>&1; then
      echo "缺少命令: sudo" >&2
      return 1
    fi
    sudo "$@"
  fi
}

install_dependencies() {
  local manager="$1"
  shift
  local packages=("$@")

  case "${manager}" in
    apt-get)
      run_privileged apt-get update
      run_privileged apt-get install -y "${packages[@]}"
      ;;
    dnf)
      run_privileged dnf install -y "${packages[@]}"
      ;;
    yum)
      run_privileged yum install -y "${packages[@]}"
      ;;
    pacman)
      run_privileged pacman -Sy --noconfirm "${packages[@]}"
      ;;
    zypper)
      run_privileged zypper --non-interactive install "${packages[@]}"
      ;;
    *)
      echo "不支持的包管理器: ${manager}" >&2
      return 1
      ;;
  esac
}

deps_stage() {
  local -a missing=()
  local manager=""
  local packages_text=""
  local dependency package

  mapfile -t missing < <(collect_missing_dependencies)
  if (( ${#missing[@]} == 0 )); then
    return 0
  fi

  manager="$(detect_package_manager)" || {
    echo "无法识别受支持的包管理器。" >&2
    return 1
  }

  for dependency in "${missing[@]}"; do
    package="$(package_name_for_dependency "${manager}" "${dependency}")"
    packages_text="$(append_unique_word "${packages_text}" "${package}")"
  done

  # shellcheck disable=SC2206
  local packages=(${packages_text})
  install_dependencies "${manager}" "${packages[@]}"

  mapfile -t missing < <(collect_missing_dependencies)
  if (( ${#missing[@]} > 0 )); then
    echo "依赖安装后仍缺少: ${missing[*]}" >&2
    return 1
  fi
}

run_install() {
  local total=12

  log_phase 1 "${total}" "preflight"
  run_step "preflight" 1 preflight

  log_phase 2 "${total}" "deps"
  run_step "deps" 1 deps_stage

  log_phase 3 "${total}" "env"
  run_step "env" 1 ensure_env

  log_phase 4 "${total}" "network"
  run_step "network" 1 "${ROOT_DIR}/scripts/init-network.sh"

  log_phase 5 "${total}" "main_stack"
  run_step "main_stack" "${INSTALL_MAIN_STACK_RETRIES}" "${ROOT_DIR}/scripts/up-main.sh"

  log_phase 6 "${total}" "repair"
  run_step "repair" 1 "${ROOT_DIR}/scripts/repair-mariadb-phpmyadmin-user.sh"

  log_phase 7 "${total}" "harbor_prepare"
  if [[ "${INSTALL_SKIP_HARBOR}" == "1" ]]; then
    record_stage_result "harbor_prepare" "skipped"
    printf 'SKIP: harbor_prepare\n'
  else
    run_step "harbor_prepare" 1 "${ROOT_DIR}/scripts/prepare-harbor.sh"
  fi

  log_phase 8 "${total}" "harbor_install"
  if [[ "${INSTALL_SKIP_HARBOR}" == "1" ]]; then
    record_stage_result "harbor_install" "skipped"
    printf 'SKIP: harbor_install\n'
  else
    run_step "harbor_install" 1 run_harbor_install
  fi

  log_phase 9 "${total}" "bootstrap"
  run_step "bootstrap" "${INSTALL_BOOTSTRAP_RETRIES}" "${ROOT_DIR}/scripts/bootstrap-keycloak.sh"

  log_phase 10 "${total}" "configure"
  run_step "configure" "${INSTALL_CONFIGURE_RETRIES}" configure_portainer_stage

  log_phase 11 "${total}" "panel"
  if [[ "${INSTALL_SKIP_PANEL}" == "1" ]]; then
    record_stage_result "panel" "skipped"
    printf 'SKIP: panel\n'
  else
    run_optional_step "panel" 1 "${ROOT_DIR}/scripts/panel.sh" start
  fi

  log_phase 12 "${total}" "verify"
  run_step "verify" "${INSTALL_VERIFY_RETRIES}" verify_install_stage
}
