#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/install-lib.sh"

CHECK_PREREQS_OS_RELEASE_FILE="${CHECK_PREREQS_OS_RELEASE_FILE:-/etc/os-release}"

read_os_release_value() {
  local key="$1"
  local prefix="${key}="
  local raw_line=""

  [[ -f "${CHECK_PREREQS_OS_RELEASE_FILE}" ]] || return 0

  while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
    if [[ "${raw_line}" == "${prefix}"* ]]; then
      raw_line="${raw_line#${prefix}}"
      raw_line="${raw_line%\"}"
      raw_line="${raw_line#\"}"
      printf '%s\n' "${raw_line}"
      return 0
    fi
  done < "${CHECK_PREREQS_OS_RELEASE_FILE}"
}

first_package_candidate() {
  local manager="$1"
  local dependency="$2"
  local candidate=""
  while IFS= read -r candidate; do
    printf '%s\n' "${candidate}"
    return 0
  done < <(package_candidates_for_dependency "${manager}" "${dependency}")
  return 1
}

join_package_candidates() {
  local manager="$1"
  local dependency="$2"
  local output=""
  local candidate=""

  while IFS= read -r candidate; do
    output="$(append_unique_word "${output}" "${candidate}")"
  done < <(package_candidates_for_dependency "${manager}" "${dependency}")

  printf '%s\n' "${output}"
}

classify_support_tier() {
  local distro_id="$1"
  local version_id="$2"
  local manager="$3"

  case "${distro_id}:${version_id}" in
    debian:13|debian:13.*)
      printf 'validated\n'
      ;;
    ubuntu:22.04|ubuntu:24.04)
      printf 'apt-compatible\n'
      ;;
    fedora:*|rhel:*|rocky:*|almalinux:*|centos:*|arch:*|opensuse*:*|sles:*)
      if [[ "${manager}" == "unsupported" ]]; then
        printf 'unverified\n'
      else
        printf 'package-manager-mapped\n'
      fi
      ;;
    *)
      if [[ "${manager}" == "unsupported" ]]; then
        printf 'unverified\n'
      else
        printf 'package-manager-mapped\n'
      fi
      ;;
  esac
}

support_note_for_tier() {
  local tier="$1"
  case "${tier}" in
    validated)
      printf '当前脚本路径已对 Debian 13 做过专项修复并有自动化测试覆盖。\n'
      ;;
    apt-compatible)
      printf 'apt 路径已适配 docker-compose-plugin -> docker-compose-v2 -> docker-compose 回退，但仍建议先自检。\n'
      ;;
    package-manager-mapped)
      printf '当前仅确认包管理器映射存在，未声明整套环境已完整验证。\n'
      ;;
    *)
      printf '当前发行版不在已验证列表内，请先人工确认依赖安装方式。\n'
      ;;
  esac
}

support_tier_label() {
  local tier="$1"
  case "${tier}" in
    validated) printf '已验证\n' ;;
    apt-compatible) printf 'APT 兼容路径\n' ;;
    package-manager-mapped) printf '已映射包管理器\n' ;;
    *) printf '未验证\n' ;;
  esac
}

state_label() {
  local state="$1"
  case "${state}" in
    ok) printf '正常\n' ;;
    present) printf '已存在\n' ;;
    missing) printf '缺失\n' ;;
    unsupported) printf '不受支持\n' ;;
    *) printf '%s\n' "${state}" ;;
  esac
}

overall_label() {
  local overall="$1"
  case "${overall}" in
    ready) printf '已就绪\n' ;;
    installable) printf '可安装\n' ;;
    blocked) printf '已阻塞\n' ;;
    *) printf '%s\n' "${overall}" ;;
  esac
}

main() {
  local distro_pretty distro_id version_id
  local manager support_tier support_note
  local python3_state docker_state compose_v2_state compose_v1_state root_access_state
  local docker_package compose_packages overall
  local support_tier_cn manager_cn overall_cn
  local -a errors=()
  local -a suggestions=()
  local entry=""

  distro_pretty="$(read_os_release_value "PRETTY_NAME")"
  distro_id="$(read_os_release_value "ID")"
  version_id="$(read_os_release_value "VERSION_ID")"

  distro_pretty="${distro_pretty:-unknown}"
  distro_id="${distro_id:-unknown}"
  version_id="${version_id:-unknown}"

  manager="$(detect_package_manager 2>/dev/null || true)"
  manager="${manager:-unsupported}"

  support_tier="$(classify_support_tier "${distro_id}" "${version_id}" "${manager}")"
  support_note="$(support_note_for_tier "${support_tier}")"
  support_tier_cn="$(support_tier_label "${support_tier}")"

  if command_missing python3; then
    python3_state="missing"
  else
    python3_state="ok"
  fi

  if command_missing docker; then
    docker_state="missing"
  else
    docker_state="ok"
  fi

  if command_missing docker-compose-plugin; then
    compose_v2_state="missing"
  else
    compose_v2_state="ok"
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    compose_v1_state="present"
  else
    compose_v1_state="missing"
  fi

  if [[ "${EUID}" -eq 0 ]] || command -v sudo >/dev/null 2>&1; then
    root_access_state="ok"
  else
    root_access_state="missing"
  fi

  if [[ "${manager}" == "unsupported" ]]; then
    docker_package="unknown"
    compose_packages="unknown"
    manager_cn="不受支持"
  else
    docker_package="$(first_package_candidate "${manager}" "docker")"
    compose_packages="$(join_package_candidates "${manager}" "docker-compose-plugin")"
    manager_cn="${manager}"
  fi

  overall="ready"
  if [[ "${manager}" == "unsupported" ]] || [[ "${root_access_state}" == "missing" ]]; then
    overall="blocked"
  elif [[ "${python3_state}" != "ok" ]] || [[ "${docker_state}" != "ok" ]] || [[ "${compose_v2_state}" != "ok" ]]; then
    overall="installable"
  fi
  overall_cn="$(overall_label "${overall}")"

  if [[ "${manager}" == "unsupported" ]]; then
    errors+=("当前主机缺少受支持的包管理器。")
    suggestions+=("请先手工安装 Python 3、Docker 与 Docker Compose v2，再重新执行安装。")
  fi
  if [[ "${python3_state}" != "ok" ]]; then
    errors+=("缺少 Python 3。")
    suggestions+=("请先安装 Python 3。")
  fi
  if [[ "${docker_state}" != "ok" ]]; then
    errors+=("缺少 Docker。")
    suggestions+=("请先安装 Docker。")
  fi
  if [[ "${compose_v2_state}" != "ok" ]]; then
    errors+=("缺少 Docker Compose v2（\`docker compose\`）。")
    suggestions+=("先安装 Compose 候选包，或直接执行安装脚本让它自动补齐。")
  fi
  if [[ "${root_access_state}" != "ok" ]]; then
    errors+=("当前用户既不是 root，也没有 sudo。")
    suggestions+=("请切换到具备 sudo 权限的用户，或使用 root 执行安装。")
  fi

  printf '安装前提检查\n'
  printf '系统：%s\n' "${distro_pretty}"
  printf '发行版 ID：%s\n' "${distro_id}"
  printf '发行版版本：%s\n' "${version_id}"
  printf '包管理器：%s\n' "${manager_cn}"
  printf '支持等级：%s\n' "${support_tier_cn}"
  printf '提示：%s\n' "${support_note}"
  printf 'Python 3：%s\n' "$(state_label "${python3_state}")"
  printf 'Docker：%s\n' "$(state_label "${docker_state}")"
  printf 'Docker Compose v2：%s\n' "$(state_label "${compose_v2_state}")"
  printf 'Docker Compose v1：%s\n' "$(state_label "${compose_v1_state}")"
  printf '提权能力：%s\n' "$(state_label "${root_access_state}")"
  printf 'Docker 包：%s\n' "${docker_package}"
  printf 'Compose 候选包：%s\n' "${compose_packages}"
  printf '结论：%s\n' "${overall_cn}"

  if (( ${#errors[@]} > 0 )); then
    for entry in "${errors[@]}"; do
      printf '错误：%s\n' "${entry}"
    done
  fi

  if (( ${#suggestions[@]} > 0 )); then
    for entry in "${suggestions[@]}"; do
      printf '建议：%s\n' "${entry}"
    done
  fi

  if [[ "${overall}" == "blocked" ]]; then
    return 1
  fi
}

main "$@"
