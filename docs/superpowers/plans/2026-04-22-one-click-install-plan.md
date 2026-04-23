# One-Click Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前安装流程补成 `sudo ./install.sh --base-domain example.internal` 级别的一键安装，在任意 Linux 主机上自动完成域名派生、`.env` 对齐、本机 `/etc/hosts` 维护、主栈启动、Keycloak bootstrap、Portainer OAuth 自动化和安装后验收。

**Architecture:** 继续以 `install.sh + scripts/install-lib.sh` 作为总控，保留现有阶段化 Bash 编排与幂等 secret 逻辑。新增一个 Python 辅助脚本集中处理 Bash 不擅长的工作：公网 IP 探测、`/etc/hosts` 标记块维护、Portainer API 自动化与 HTTP 验收；安装脚本只负责参数、阶段控制和结果汇总。

**Tech Stack:** Bash, Python 3 `unittest`, `urllib.request`, `json`, `ipaddress`, existing Docker Compose scripts, Portainer HTTP API

---

## File Map

- Modify: `install.sh`
  - 作用：接收 `--base-domain` / `--public-ip`，在安装完成后打印新的单命令摘要。
- Modify: `scripts/install-lib.sh`
  - 作用：增加必填参数校验、域名派生、helper 调用、hosts 更新、Portainer 自动化和安装后验收。
- Create: `scripts/install_helper.py`
  - 作用：集中实现 IP 探测、`/etc/hosts` 标记块维护、Portainer API 操作和 HTTP 验收。
- Modify: `.env.example`
  - 作用：明确一键安装仍依赖的基础键，保留脚本会自动管理的键。
- Modify: `README.md`
  - 作用：更新一键安装命令、参数、运行边界和安装后验证说明。
- Modify: `tests/test_install_script.py`
  - 作用：验证新参数合同、`.env` 派生、hosts 文件调用、阶段顺序和 helper 编排。
- Create: `tests/test_install_helper.py`
  - 作用：验证 helper 的 IP、hosts、Portainer API、验收逻辑，避免真实网络依赖。

## Task 1: 固定一键安装 CLI 合同与 `.env` 派生规则

**Files:**
- Modify: `install.sh`
- Modify: `scripts/install-lib.sh`
- Modify: `tests/test_install_script.py`

- [ ] **Step 1: 先写失败测试，固定 `--base-domain` 和域名派生合同**

```python
class InstallScriptTest(unittest.TestCase):
    def test_install_requires_base_domain_for_default_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            write_executable(
                root / "scripts" / "install_helper.py",
                "#!/usr/bin/env python3\nprint('127.0.0.1')\n",
            )
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=REPLACE_ME_PUBLIC_HOST\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", "install.sh"],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--base-domain", result.stderr + result.stdout)

    def test_install_base_domain_derives_public_hosts_and_public_ip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            hosts_file = root / "hosts"
            write_executable(
                root / "scripts" / "install_helper.py",
                """#!/usr/bin/env python3
import pathlib, sys

argv = sys.argv[1:]
if argv[0] == "detect-public-ip":
    print("192.168.50.10")
elif argv[0] == "sync-hosts":
    target = pathlib.Path(argv[argv.index("--hosts-file") + 1])
    target.write_text("managed-hosts\\n", encoding="utf-8")
elif argv[0] in {"configure-portainer", "verify-install"}:
    print(argv[0] + ":ok")
else:
    raise SystemExit(f"unexpected args: {argv}")
""",
            )
            (root / ".env.example").write_text(
                "PUBLIC_SCHEME=http\n"
                "PUBLIC_HOST=REPLACE_ME_PUBLIC_HOST\n"
                "BROWSER_HOST=localhost\n"
                "KAFKA_HOST_BOOTSTRAP_SERVER=REPLACE_ME_PUBLIC_HOST:9092\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["bash", "install.sh", "--base-domain", "dev.example", "--skip-panel"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "INSTALL_HOSTS_FILE": str(hosts_file)},
            )

            env_map = parse_env((root / ".env").read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(env_map["PUBLIC_HOST"], "192.168.50.10")
        self.assertEqual(env_map["KAFKA_HOST_BOOTSTRAP_SERVER"], "192.168.50.10:9092")
        self.assertEqual(env_map["KEYCLOAK_PUBLIC_HOST"], "auth.dev.example")
        self.assertEqual(env_map["PORTAINER_PUBLIC_HOST"], "portainer.dev.example")
        self.assertEqual(env_map["NACOS_PUBLIC_HOST"], "nacos.dev.example")
        self.assertEqual(env_map["NIGHTINGALE_PUBLIC_HOST"], "nightingale.dev.example")
        self.assertEqual(env_map["BROWSER_HOST"], "localhost")
        self.assertEqual(hosts_file.read_text(encoding="utf-8"), "managed-hosts\n")
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests.test_install_script.InstallScriptTest.test_install_requires_base_domain_for_default_flow tests.test_install_script.InstallScriptTest.test_install_base_domain_derives_public_hosts_and_public_ip -v`  
Expected: 失败，报 `--base-domain` 未实现或 `.env` 仍保留占位值。

- [ ] **Step 3: 在安装脚本中加入新的参数与 Bash 侧派生逻辑**

```bash
INSTALL_SKIP_PANEL=0
INSTALL_SKIP_HARBOR=1
INSTALL_REPAIR=0
INSTALL_BASE_DOMAIN=""
INSTALL_PUBLIC_IP=""
INSTALL_HOSTS_FILE="${INSTALL_HOSTS_FILE:-/etc/hosts}"
INSTALL_HELPER="${ROOT_DIR}/scripts/install_helper.py"

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --skip-panel) INSTALL_SKIP_PANEL=1 ;;
      --with-harbor) INSTALL_SKIP_HARBOR=0 ;;
      --skip-harbor) INSTALL_SKIP_HARBOR=1 ;;
      --repair) INSTALL_REPAIR=1 ;;
      --base-domain)
        shift
        INSTALL_BASE_DOMAIN="${1:-}"
        ;;
      --public-ip)
        shift
        INSTALL_PUBLIC_IP="${1:-}"
        ;;
      *)
        echo "未知参数: $1" >&2
        return 1
        ;;
    esac
    shift
  done
}

require_base_domain() {
  [[ -n "${INSTALL_BASE_DOMAIN}" ]] || {
    echo "缺少必填参数: --base-domain" >&2
    return 1
  }
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
  if [[ "${INSTALL_SKIP_HARBOR}" != "1" ]]; then
    HARBOR_PUBLIC_HOST="harbor.${INSTALL_BASE_DOMAIN}"
  fi
}

resolve_public_ip() {
  if [[ -n "${INSTALL_PUBLIC_IP}" ]]; then
    printf '%s\n' "${INSTALL_PUBLIC_IP}"
    return 0
  fi
  python3 "${INSTALL_HELPER}" detect-public-ip
}

upsert_env_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  python3 - "$file" "$key" "$value" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text(encoding="utf-8").splitlines()
prefix = f"{key}="
for index, line in enumerate(lines):
    if line.startswith(prefix):
        lines[index] = prefix + value
        break
else:
    lines.append(prefix + value)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}
```

```bash
ensure_managed_env_values() {
  local env_file="${ROOT_DIR}/.env"
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
  upsert_env_value "${env_file}" "BROWSER_HOST" "${BROWSER_HOST:-localhost}"
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
}
```

- [ ] **Step 4: 运行测试并确认转绿**

Run: `python3 -m unittest tests.test_install_script.InstallScriptTest.test_install_requires_base_domain_for_default_flow tests.test_install_script.InstallScriptTest.test_install_base_domain_derives_public_hosts_and_public_ip -v`  
Expected: `OK`

- [ ] **Step 5: 提交这一组 CLI / `.env` 合同修改**

```bash
git add install.sh scripts/install-lib.sh tests/test_install_script.py
git commit -m "feat: require base domain for one-click install"
```

## Task 2: 实现 Python helper 的 IP 探测与 `/etc/hosts` 标记块维护

**Files:**
- Create: `scripts/install_helper.py`
- Create: `tests/test_install_helper.py`
- Modify: `tests/test_install_script.py`

- [ ] **Step 1: 先写失败测试，固定 helper 的纯函数合同**

```python
import importlib.util
import tempfile
import unittest
from pathlib import Path


def load_install_helper():
    path = Path("scripts/install_helper.py")
    spec = importlib.util.spec_from_file_location("install_helper", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class InstallHelperTest(unittest.TestCase):
    def test_detect_public_ip_returns_explicit_override(self) -> None:
        helper = load_install_helper()
        self.assertEqual(helper.detect_public_ip("192.168.9.10"), "192.168.9.10")

    def test_render_hosts_block_includes_managed_markers(self) -> None:
        helper = load_install_helper()
        block = helper.render_hosts_block("192.168.9.10", ["auth.dev.example", "portainer.dev.example"])
        self.assertIn("# BEGIN integration_of_third-party_tools", block)
        self.assertIn("192.168.9.10 auth.dev.example", block)
        self.assertIn("# END integration_of_third-party_tools", block)

    def test_sync_hosts_replaces_existing_managed_block(self) -> None:
        helper = load_install_helper()
        with tempfile.TemporaryDirectory() as tmp:
            hosts_path = Path(tmp) / "hosts"
            hosts_path.write_text(
                "127.0.0.1 localhost\n"
                "# BEGIN integration_of_third-party_tools\n"
                "10.0.0.1 old.example\n"
                "# END integration_of_third-party_tools\n",
                encoding="utf-8",
            )
            helper.sync_hosts_file(hosts_path, "192.168.9.10", ["auth.dev.example"])
            text = hosts_path.read_text(encoding="utf-8")

        self.assertIn("127.0.0.1 localhost", text)
        self.assertIn("192.168.9.10 auth.dev.example", text)
        self.assertNotIn("old.example", text)
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests.test_install_helper -v`  
Expected: `FileNotFoundError` 或 `ImportError`

- [ ] **Step 3: 写最小 helper，实现 detect / hosts 子命令和可测试的纯函数**

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import socket
from pathlib import Path

MANAGED_BEGIN = "# BEGIN integration_of_third-party_tools"
MANAGED_END = "# END integration_of_third-party_tools"


def detect_public_ip(explicit: str | None = None) -> str:
    if explicit:
        ipaddress.ip_address(explicit)
        return explicit
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(("8.8.8.8", 80))
        detected = sock.getsockname()[0]
    ipaddress.ip_address(detected)
    if detected.startswith("127."):
        raise RuntimeError(f"detected loopback ip is invalid: {detected}")
    return detected


def render_hosts_block(public_ip: str, hostnames: list[str]) -> str:
    entries = [f"{public_ip} {host}" for host in hostnames]
    return "\n".join([MANAGED_BEGIN, *entries, MANAGED_END, ""])


def sync_hosts_file(path: Path, public_ip: str, hostnames: list[str]) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    managed = render_hosts_block(public_ip, hostnames)
    if MANAGED_BEGIN in existing and MANAGED_END in existing:
        prefix, rest = existing.split(MANAGED_BEGIN, 1)
        _, suffix = rest.split(MANAGED_END, 1)
        new_text = prefix.rstrip("\n") + "\n" + managed + suffix.lstrip("\n")
    else:
        base = existing.rstrip("\n")
        new_text = (base + "\n" if base else "") + managed
    path.write_text(new_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    detect_cmd = sub.add_parser("detect-public-ip")
    detect_cmd.add_argument("--public-ip")

    sync_cmd = sub.add_parser("sync-hosts")
    sync_cmd.add_argument("--hosts-file", required=True)
    sync_cmd.add_argument("--public-ip", required=True)
    sync_cmd.add_argument("--host", action="append", default=[])

    args = parser.parse_args()
    if args.command == "detect-public-ip":
        print(detect_public_ip(args.public_ip))
        return
    if args.command == "sync-hosts":
        sync_hosts_file(Path(args.hosts_file), args.public_ip, args.host)
        return
    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行 helper 测试与现有安装测试**

Run: `python3 -m unittest tests.test_install_helper tests.test_install_script -v`  
Expected: `OK`

- [ ] **Step 5: 提交 helper 的 IP / hosts 基础能力**

```bash
git add scripts/install_helper.py tests/test_install_helper.py tests/test_install_script.py
git commit -m "feat: add install helper for ip and hosts management"
```

## Task 3: 通过 Portainer API 自动初始化管理员并写入 OAuth 配置

**Files:**
- Modify: `scripts/install_helper.py`
- Modify: `scripts/install-lib.sh`
- Modify: `tests/test_install_helper.py`
- Modify: `tests/test_install_script.py`

- [ ] **Step 1: 先写失败测试，固定 Portainer API 调用顺序和配置载荷**

```python
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError


class FakeHTTPResponse:
    def __init__(self, payload: str, status: int = 200):
        self.payload = payload.encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class InstallHelperTest(unittest.TestCase):
    def test_configure_portainer_oauth_initializes_admin_when_login_fails(self) -> None:
        helper = load_install_helper()
        requests = []

        def fake_urlopen(request, timeout=10):
            requests.append((request.method, request.full_url, request.data))
            if request.full_url.endswith("/api/auth") and len([r for r in requests if r[1].endswith("/api/auth")]) == 1:
                raise HTTPError(request.full_url, 401, "Unauthorized", hdrs=None, fp=BytesIO(b'{"message":"Unauthorized"}'))
            if request.full_url.endswith("/api/users/admin/init"):
                return FakeHTTPResponse("{}")
            if request.full_url.endswith("/api/auth"):
                return FakeHTTPResponse('{"jwt":"token"}')
            if request.full_url.endswith("/api/settings") and request.method == "GET":
                return FakeHTTPResponse('{"AuthenticationMethod":1,"OAuthSettings":{"ClientID":""}}')
            if request.full_url.endswith("/api/settings") and request.method == "PUT":
                return FakeHTTPResponse("{}")
            raise AssertionError(f"unexpected request: {request.method} {request.full_url}")

        with patch.object(helper.urllib.request, "urlopen", side_effect=fake_urlopen):
            helper.configure_portainer_oauth(
                base_url="http://127.0.0.1",
                host_header="portainer.dev.example",
                admin_user="admin",
                admin_password="StrongPassword_123",
                oauth_settings={
                    "ClientID": "portainer",
                    "AuthorizationURI": "http://auth.dev.example/realms/infra/protocol/openid-connect/auth",
                },
            )

        self.assertEqual(
            [url.rsplit("/", 1)[-1] for _, url, _ in requests],
            ["auth", "init", "auth", "settings", "settings"],
        )
        put_payload = requests[-1][2].decode("utf-8")
        self.assertIn('"AuthenticationMethod": 3', put_payload)
        self.assertIn('"ClientID": "portainer"', put_payload)
```

```python
class InstallScriptTest(unittest.TestCase):
    def test_install_runs_portainer_configuration_after_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            log_file = root / "run.log"
            hosts_file = root / "hosts"
            write_executable(
                root / "scripts" / "install_helper.py",
                """#!/usr/bin/env python3
import os, pathlib, sys
log = pathlib.Path(os.environ['INSTALL_LOG']) if os.environ.get('INSTALL_LOG') else None
cmd = sys.argv[1]
if cmd == 'detect-public-ip':
    print('192.168.50.10')
elif cmd == 'sync-hosts':
    pathlib.Path(sys.argv[sys.argv.index('--hosts-file') + 1]).write_text('managed-hosts\\n', encoding='utf-8')
elif cmd == 'configure-portainer':
    if log:
        previous = log.read_text(encoding='utf-8') if log.exists() else ''
        log.write_text(previous + 'configure-portainer\\n', encoding='utf-8')
elif cmd == 'verify-install':
    print('{\"overall\":\"ready\"}')
else:
    raise SystemExit(cmd)
""",
            )
            for name in ("init-network.sh", "up-main.sh", "repair-mariadb-phpmyadmin-user.sh", "bootstrap-keycloak.sh"):
                write_executable(root / "scripts" / name, f"#!/usr/bin/env bash\necho {name} >> \"$INSTALL_LOG\"\n")
            write_executable(root / "scripts" / "panel.sh", "#!/usr/bin/env bash\necho panel.sh >> \"$INSTALL_LOG\"\n")
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=REPLACE_ME_PUBLIC_HOST\nBROWSER_HOST=localhost\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", "install.sh", "--base-domain", "dev.example"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "INSTALL_LOG": str(log_file), "INSTALL_HOSTS_FILE": str(hosts_file)},
            )

            lines = log_file.read_text(encoding="utf-8").splitlines()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(lines[-2:], ["bootstrap-keycloak.sh", "configure-portainer"])
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests.test_install_helper.InstallHelperTest.test_configure_portainer_oauth_initializes_admin_when_login_fails tests.test_install_script.InstallScriptTest.test_install_runs_portainer_configuration_after_bootstrap -v`  
Expected: 失败，helper 中尚无 `configure_portainer_oauth`，安装编排也尚未调用 Portainer 配置。

- [ ] **Step 3: 在 helper 中实现 Portainer API 自动化，并在安装流程中接入**

```python
import json
import urllib.request
from urllib.error import HTTPError


def _request_json(method: str, url: str, *, headers: dict[str, str], payload: dict[str, object] | None = None) -> dict[str, object]:
    raw = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=raw, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def _portainer_login(base_url: str, host_header: str, admin_user: str, admin_password: str) -> str | None:
    try:
        payload = _request_json(
            "POST",
            f"{base_url}/api/auth",
            headers={"Host": host_header, "Content-Type": "application/json"},
            payload={"Username": admin_user, "Password": admin_password},
        )
    except HTTPError as exc:
        if exc.code in {401, 404, 422}:
            return None
        raise
    token = payload.get("jwt")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Portainer login did not return jwt")
    return token


def configure_portainer_oauth(
    *,
    base_url: str,
    host_header: str,
    admin_user: str,
    admin_password: str,
    oauth_settings: dict[str, object],
) -> None:
    token = _portainer_login(base_url, host_header, admin_user, admin_password)
    if token is None:
        _request_json(
            "POST",
            f"{base_url}/api/users/admin/init",
            headers={"Host": host_header, "Content-Type": "application/json"},
            payload={"Username": admin_user, "Password": admin_password},
        )
        token = _portainer_login(base_url, host_header, admin_user, admin_password)
    assert token is not None

    auth_headers = {
        "Host": host_header,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    settings = _request_json("GET", f"{base_url}/api/settings", headers=auth_headers)
    merged = dict(settings)
    merged["AuthenticationMethod"] = 3
    merged["OAuthSettings"] = {**settings.get("OAuthSettings", {}), **oauth_settings}
    _request_json("PUT", f"{base_url}/api/settings", headers=auth_headers, payload=merged)
```

```bash
configure_portainer_stage() {
  local env_file="${ROOT_DIR}/.env"
  set -a
  source "${env_file}"
  set +a

  python3 "${INSTALL_HELPER}" configure-portainer \
    --base-url "${INSTALL_HTTP_BASE_URL:-http://127.0.0.1}" \
    --host-header "${PORTAINER_PUBLIC_HOST}" \
    --admin-user "${PORTAINER_ADMIN_USER}" \
    --admin-password "${PORTAINER_ADMIN_PASSWORD}" \
    --client-id "portainer" \
    --client-secret "${PORTAINER_CLIENT_SECRET}" \
    --auth-url "${PUBLIC_SCHEME}://${KEYCLOAK_PUBLIC_HOST}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/auth" \
    --token-url "${PUBLIC_SCHEME}://${KEYCLOAK_PUBLIC_HOST}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token" \
    --resource-url "${PUBLIC_SCHEME}://${KEYCLOAK_PUBLIC_HOST}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/userinfo" \
    --logout-url "${PUBLIC_SCHEME}://${KEYCLOAK_PUBLIC_HOST}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/logout" \
    --redirect-url "${PUBLIC_SCHEME}://${PORTAINER_PUBLIC_HOST}/"
}
```

```bash
log_phase 8 "${total}" "bootstrap"
run_step "bootstrap" "${ROOT_DIR}/scripts/bootstrap-keycloak.sh"

log_phase 9 "${total}" "portainer_oauth"
run_step "portainer_oauth" configure_portainer_stage

log_phase 10 "${total}" "panel"
if [[ "${INSTALL_SKIP_PANEL}" == "1" ]]; then
  printf 'SKIP: panel\n'
else
  run_step "panel" "${ROOT_DIR}/scripts/panel.sh" start
fi
```

- [ ] **Step 4: 运行 Portainer 自动化测试**

Run: `python3 -m unittest tests.test_install_helper.InstallHelperTest.test_configure_portainer_oauth_initializes_admin_when_login_fails tests.test_install_script.InstallScriptTest.test_install_runs_portainer_configuration_after_bootstrap -v`  
Expected: `OK`

- [ ] **Step 5: 提交 Portainer 自动化**

```bash
git add scripts/install_helper.py scripts/install-lib.sh tests/test_install_helper.py tests/test_install_script.py
git commit -m "feat: automate portainer oauth during install"
```

## Task 4: 增加安装后验收摘要，并更新文档与全量测试

**Files:**
- Modify: `scripts/install_helper.py`
- Modify: `scripts/install-lib.sh`
- Modify: `install.sh`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `tests/test_install_helper.py`
- Modify: `tests/test_install_script.py`

- [ ] **Step 1: 先写失败测试，固定安装后验收与最终摘要**

```python
class InstallHelperTest(unittest.TestCase):
    def test_verify_install_accepts_keycloak_or_oauth_proxy_redirects(self) -> None:
        helper = load_install_helper()

        def fake_urlopen(request, timeout=10):
            raise HTTPError(
                request.full_url,
                302,
                "Found",
                hdrs={"Location": "http://auth.dev.example/realms/infra/protocol/openid-connect/auth?client_id=kafka-ui"},
                fp=BytesIO(b""),
            )

        with patch.object(helper.urllib.request, "urlopen", side_effect=fake_urlopen):
            summary = helper.verify_install(
                base_url="http://127.0.0.1",
                hostnames=["kafka.dev.example"],
            )

        self.assertEqual(summary["overall"], "ready")
        self.assertEqual(summary["checks"][0]["host"], "kafka.dev.example")
        self.assertEqual(summary["checks"][0]["result"], "ready")
```

```python
class InstallScriptTest(unittest.TestCase):
    def test_install_prints_verification_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            hosts_file = root / "hosts"
            write_executable(
                root / "scripts" / "install_helper.py",
                """#!/usr/bin/env python3
import pathlib, sys
argv = sys.argv[1:]
if argv[0] == 'detect-public-ip':
    print('192.168.50.10')
elif argv[0] == 'sync-hosts':
    pathlib.Path(argv[argv.index('--hosts-file') + 1]).write_text('managed-hosts\\n', encoding='utf-8')
elif argv[0] == 'configure-portainer':
    print('configured')
elif argv[0] == 'verify-install':
    print('{"overall":"ready","checks":[{"host":"kafka.dev.example","result":"ready"}]}')
else:
    raise SystemExit(argv)
""",
            )
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=REPLACE_ME_PUBLIC_HOST\nBROWSER_HOST=localhost\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", "install.sh", "--base-domain", "dev.example", "--skip-panel"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "INSTALL_HOSTS_FILE": str(hosts_file)},
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Verification:", result.stdout)
        self.assertIn("overall=ready", result.stdout)
        self.assertIn("kafka.dev.example", result.stdout)
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests.test_install_helper.InstallHelperTest.test_verify_install_accepts_keycloak_or_oauth_proxy_redirects tests.test_install_script.InstallScriptTest.test_install_prints_verification_summary -v`  
Expected: 失败，helper 中尚无 `verify_install` 或安装脚本尚未打印验证摘要。

- [ ] **Step 3: 实现验收逻辑并更新 README**

```python
def verify_install(
    *,
    base_url: str,
    hostnames: list[str],
) -> dict[str, object]:
    checks: list[dict[str, str]] = []
    for host in hostnames:
        request = urllib.request.Request(f"{base_url}/", headers={"Host": host})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read().decode("utf-8", "replace")
                ok = "OIDC" in body or "/oauth2/" in body
        except HTTPError as exc:
            location = exc.headers.get("Location", "")
            ok = "/oauth2/" in location or "openid-connect/auth" in location
        checks.append({"host": host, "result": "ready" if ok else "degraded"})
    overall = "ready" if all(item["result"] == "ready" for item in checks) else "degraded"
    return {"overall": overall, "checks": checks}
```

```bash
print_verification_summary() {
  local summary_json="$1"
  python3 - "$summary_json" <<'PY'
import json
import sys

summary = json.loads(sys.argv[1])
print("Verification:")
print(f"- overall={summary['overall']}")
for item in summary["checks"]:
    print(f"- {item['host']}: {item['result']}")
PY
}

run_install() {
  local total=10
  # ... existing phases ...
  local verification_json
  verification_json="$(
    python3 "${INSTALL_HELPER}" verify-install \
      --base-url "${INSTALL_HTTP_BASE_URL:-http://127.0.0.1}" \
      --host "${KAFKA_UI_PUBLIC_HOST}" \
      --host "${REDISINSIGHT_PUBLIC_HOST}" \
      --host "${PHPMYADMIN_PUBLIC_HOST}" \
      --host "${MONGO_EXPRESS_PUBLIC_HOST}" \
      --host "${NACOS_PUBLIC_HOST}" \
      --host "${NIGHTINGALE_PUBLIC_HOST}"
  )"
  print_verification_summary "${verification_json}"
}
```

`.env.example` 需要保留清晰的“脚本管理字段”提示：

```dotenv
PUBLIC_SCHEME=http
PUBLIC_HOST=REPLACE_ME_PUBLIC_HOST
BROWSER_HOST=localhost
KEYCLOAK_PUBLIC_HOST=auth.localhost
PORTAINER_PUBLIC_HOST=portainer.localhost
KAFKA_HOST_BOOTSTRAP_SERVER=REPLACE_ME_PUBLIC_HOST:9092
# install.sh --base-domain 会覆盖 PUBLIC_HOST、KAFKA_HOST_BOOTSTRAP_SERVER 和各 *_PUBLIC_HOST
```

README 需要新增的一键安装段落可直接写成：

```text
## 真正一键安装

sudo ./install.sh --base-domain example.internal

- `--base-domain` 为必填
- 默认自动探测 `PUBLIC_HOST`
- 自动维护本机 `/etc/hosts`
- 默认自动配置 Portainer OAuth
- 默认不安装 Harbor；只有显式 `--with-harbor` 才启用
```

- [ ] **Step 4: 运行全量回归**

Run: `python3 -m unittest discover -s tests -v`  
Expected: `OK`

Run: `bash -n install.sh scripts/install-lib.sh && python3 -m py_compile scripts/install_helper.py`  
Expected: 无输出

- [ ] **Step 5: 提交验收与文档收尾**

```bash
git add install.sh scripts/install-lib.sh scripts/install_helper.py .env.example README.md tests/test_install_script.py tests/test_install_helper.py
git commit -m "feat: add one-click install verification flow"
```

## Self-Review

- Spec coverage:
  - `--base-domain` / `--public-ip`：Task 1
  - `.env` 域名派生与 `PUBLIC_HOST` / `KAFKA_HOST_BOOTSTRAP_SERVER`：Task 1
  - `/etc/hosts` 自动维护：Task 2
  - Portainer API 初始化与 OAuth：Task 3
  - 安装后验收与最终摘要：Task 4
  - README 一键安装说明：Task 4
- Placeholder scan:
  - 无 `TODO` / `TBD`
  - 每个任务都给了明确文件、代码和命令
- Type consistency:
  - helper 统一使用 `detect_public_ip`、`sync_hosts_file`、`configure_portainer_oauth`、`verify_install`
  - Bash 统一通过 `INSTALL_HELPER` 调用 `detect-public-ip`、`sync-hosts`、`configure-portainer`、`verify-install`
