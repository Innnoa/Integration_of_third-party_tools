#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/install-lib.sh"

load_install_env() {
  local env_file="${ROOT_DIR}/.env"
  [[ -f "${env_file}" ]] || return 1

  # shellcheck disable=SC1090
  source "${env_file}"
}

print_windows_hosts_guidance() {
  local keycloak_host="$1"
  local portainer_host="$2"
  local kafka_host="$3"
  local redis_host="$4"
  local pma_host="$5"
  local mongo_host="$6"
  local harbor_host="$7"
  local nacos_host="$8"
  local nightingale_host="$9"

  printf -- '- Add the current .env hostnames to your Windows hosts file: %s, %s, %s, %s, %s, %s, %s, %s' \
    "${keycloak_host}" "${portainer_host}" "${kafka_host}" "${redis_host}" "${pma_host}" "${mongo_host}" "${nacos_host}" "${nightingale_host}"
  if [[ "${INSTALL_SKIP_HARBOR}" != "1" ]]; then
    printf ', %s' "${harbor_host}"
  fi
  printf '.\n'
}

print_result_summary() {
  printf '\nResult:\n'
  printf -- '- overall=%s\n' "${INSTALL_OVERALL_STATUS:-unknown}"
  if ((${#INSTALL_STAGE_RESULTS[@]} > 0)); then
    printf 'Stage Results:\n'
    local entry
    for entry in "${INSTALL_STAGE_RESULTS[@]}"; do
      printf -- '- %s\n' "${entry}"
    done
  fi
}

print_access_summary() {
  load_install_env

  local keycloak_host="${KEYCLOAK_PUBLIC_HOST:-auth.localhost}"
  local portainer_host="${PORTAINER_PUBLIC_HOST:-portainer.localhost}"
  local kafka_host="${KAFKA_UI_PUBLIC_HOST:-kafka.localhost}"
  local redis_host="${REDISINSIGHT_PUBLIC_HOST:-redis.localhost}"
  local pma_host="${PHPMYADMIN_PUBLIC_HOST:-pma.localhost}"
  local mongo_host="${MONGO_EXPRESS_PUBLIC_HOST:-mongo.localhost}"
  local harbor_host="${HARBOR_PUBLIC_HOST:-harbor.localhost}"
  local nacos_host="${NACOS_PUBLIC_HOST:-nacos.localhost}"
  local nightingale_host="${NIGHTINGALE_PUBLIC_HOST:-nightingale.localhost}"
  local panel_host="${BUSINESS_PANEL_HOST:-127.0.0.1}"
  local panel_port="${BUSINESS_PANEL_PORT:-8090}"
  local public_host="${PUBLIC_HOST:-localhost}"

  printf '\nInstall complete. Access:\n'
  printf -- '- http://%s\n' "${keycloak_host}"
  printf -- '- http://%s\n' "${portainer_host}"
  printf -- '- http://%s\n' "${kafka_host}"
  printf -- '- http://%s\n' "${redis_host}"
  printf -- '- http://%s\n' "${pma_host}"
  printf -- '- http://%s\n' "${mongo_host}"
  printf -- '- http://%s\n' "${nacos_host}"
  printf -- '- http://%s\n' "${nightingale_host}"
  if [[ "${INSTALL_SKIP_HARBOR}" != "1" ]]; then
    printf -- '- http://%s\n' "${harbor_host}"
  fi
  if [[ "${INSTALL_SKIP_PANEL}" != "1" ]]; then
    printf -- '- http://%s:%s\n' "${panel_host}" "${panel_port}"
  fi
  printf -- '- PUBLIC_HOST:9092 (current: %s:9092)\n' "${public_host}"
  if [[ -n "${INSTALL_VERIFICATION_SUMMARY:-}" ]]; then
    printf '\nVerification:\n'
    python3 - "${INSTALL_VERIFICATION_SUMMARY}" <<'PY'
import json
import sys

summary = json.loads(sys.argv[1])
print(f"- overall={summary.get('overall', 'unknown')}")
for item in summary.get("checks", []):
    host = item.get("host", "unknown")
    result = item.get("result", "unknown")
    print(f"- {host}: {result}")
PY
  fi
  printf '\nNext:\n'
  print_windows_hosts_guidance \
    "${keycloak_host}" \
    "${portainer_host}" \
    "${kafka_host}" \
    "${redis_host}" \
    "${pma_host}" \
    "${mongo_host}" \
    "${harbor_host}" \
    "${nacos_host}" \
    "${nightingale_host}"
  if [[ "${INSTALL_SKIP_HARBOR}" != "1" ]]; then
    printf -- '- Open http://%s, http://%s, http://%s, and http://%s in your browser.\n' \
      "${keycloak_host}" "${portainer_host}" "${nacos_host}" "${harbor_host}"
  else
    printf -- '- Open http://%s, http://%s, and http://%s in your browser.\n' \
      "${keycloak_host}" "${portainer_host}" "${nacos_host}"
  fi
  if [[ "${INSTALL_SKIP_PANEL}" != "1" ]]; then
    printf -- '- Open http://%s:%s and verify the panel plus Kafka bootstrap at %s:9092.\n' \
      "${panel_host}" "${panel_port}" "${public_host}"
  else
    printf -- '- Verify Kafka bootstrap at %s:9092.\n' "${public_host}"
  fi
}

main() {
  parse_args "$@"
  run_install
  print_result_summary
  print_access_summary
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
