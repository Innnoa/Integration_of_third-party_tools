# Installer Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为当前项目补一个可重复执行的 `install.sh`，在完整项目目录交付的前提下完成环境检查、配置生成、主栈启动、Harbor 安装、Keycloak bootstrap、面板启动和统一入口提示。

**Architecture:** 根目录 `install.sh` 作为总控入口，内部调用 `scripts/install-lib.sh` 中的可复用函数完成 preflight、`.env` 补齐、自动生成 secrets、阶段日志和幂等判断。安装流程优先复用现有 `scripts/*.sh`，Harbor 继续走官方 installer 路线，测试使用 Python `unittest` 通过临时目录和 fake executables 校验阶段编排、幂等逻辑和参数分支。

**Tech Stack:** Bash, Python 3.14 `unittest`, existing project scripts, Docker Compose, Harbor installer

---

**Execution Note:** 当前目录不是 git 仓库。执行本计划时，不要求 commit 检查点；以测试和命令验证结果作为阶段完成依据。

## File Map

- Create: `install.sh`
  - 作用：统一安装入口，解析参数并串行执行各阶段
- Create: `scripts/install-lib.sh`
  - 作用：封装环境检查、`.env` 更新、secret 生成、阶段输出和命令调度
- Create: `tests/test_install_script.py`
  - 作用：验证安装脚本的幂等行为、参数分支、阶段顺序和错误处理
- Modify: `README.md`
  - 作用：补充 `install.sh` 用法、Windows hosts 提示、安装后访问清单

### Task 1: 建立安装脚本测试骨架与可 source 的函数库

**Files:**
- Create: `install.sh`
- Create: `scripts/install-lib.sh`
- Create: `tests/test_install_script.py`

- [ ] **Step 1: 先写失败测试，固定 install 脚本的最小合同**

```python
import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


def write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class InstallScriptTest(unittest.TestCase):
    def test_install_fails_when_harbor_installer_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", "install.sh"],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("harbor/installer", result.stderr + result.stdout)

    def test_install_sources_library_and_creates_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "harbor" / "installer").mkdir(parents=True)
            (root / "harbor" / "installer" / "install.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            (root / ".env.example").write_text(
                textwrap.dedent(
                    \"\"\"\
                    PUBLIC_SCHEME=http
                    PUBLIC_HOST=REPLACE_ME_PUBLIC_HOST
                    BROWSER_HOST=localhost
                    KEYCLOAK_PUBLIC_HOST=auth.localhost
                    PORTAINER_PUBLIC_HOST=portainer.localhost
                    KAFKA_UI_PUBLIC_HOST=kafka.localhost
                    REDISINSIGHT_PUBLIC_HOST=redis.localhost
                    PHPMYADMIN_PUBLIC_HOST=pma.localhost
                    MONGO_EXPRESS_PUBLIC_HOST=mongo.localhost
                    HARBOR_PUBLIC_HOST=harbor.localhost
                    TOOLS_NETWORK=tools_net
                    \"\"\"
                ),
                encoding="utf-8",
            )
            write_executable(root / "scripts" / "init-network.sh", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(root / "scripts" / "prepare-harbor.sh", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(root / "scripts" / "bootstrap-keycloak.sh", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(root / "scripts" / "panel.sh", "#!/usr/bin/env bash\nexit 0\n")
            fakebin = root / "fakebin"
            fakebin.mkdir()
            write_executable(fakebin / "docker", "#!/usr/bin/env bash\nexit 0\n")
            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}"},
            )

            env_text = (root / ".env").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0)
        self.assertIn("PUBLIC_HOST=", env_text)
        self.assertIn("KEYCLOAK_PUBLIC_HOST=auth.localhost", env_text)
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests/test_install_script.py -v`  
Expected: `No such file or directory: install.sh` 或 `ModuleNotFoundError`

- [ ] **Step 3: 写最小入口和函数库骨架**

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck disable=SC1091
source "${ROOT_DIR}/scripts/install-lib.sh"

main() {
  parse_args "$@"
  run_install
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
```

```bash
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

run_install() {
  preflight
  ensure_env
}

preflight() {
  [[ -f "${ROOT_DIR}/.env.example" ]] || { echo "缺少 .env.example" >&2; return 1; }
  [[ -f "${ROOT_DIR}/harbor/installer/install.sh" ]] || {
    echo "缺少 harbor/installer/install.sh" >&2
    return 1
  }
}

ensure_env() {
  [[ -f "${ROOT_DIR}/.env" ]] || cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
}
```

- [ ] **Step 4: 运行测试并确认转绿**

Run: `python3 -m unittest tests/test_install_script.py -v`  
Expected: `OK`

- [ ] **Step 5: 记录当前检查点**

Run: `python3 -m unittest tests/test_install_script.py -v && bash -n install.sh scripts/install-lib.sh`  
Expected: 测试通过，shell 语法检查无输出

### Task 2: 实现 preflight、环境补齐与自动生成 secrets

**Files:**
- Modify: `install.sh`
- Modify: `scripts/install-lib.sh`
- Modify: `tests/test_install_script.py`

- [ ] **Step 1: 写失败测试，固定幂等 env 规则**

```python
    def test_install_preserves_existing_secrets_on_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\nexit 0\n")
            (root / ".env.example").write_text(
                "PUBLIC_SCHEME=http\nPUBLIC_HOST=REPLACE_ME_PUBLIC_HOST\nKEYCLOAK_ADMIN_PASSWORD=ChangeMe\n",
                encoding="utf-8",
            )
            (root / ".env").write_text(
                "PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\nKEYCLOAK_ADMIN_PASSWORD=keep-me\n",
                encoding="utf-8",
            )
            write_executable(root / "scripts" / "init-network.sh", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(root / "scripts" / "prepare-harbor.sh", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(root / "scripts" / "bootstrap-keycloak.sh", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(root / "scripts" / "panel.sh", "#!/usr/bin/env bash\nexit 0\n")
            fakebin = root / "fakebin"
            fakebin.mkdir()
            write_executable(fakebin / "docker", "#!/usr/bin/env bash\nexit 0\n")

            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}"},
            )

            env_text = (root / ".env").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0)
        self.assertIn("KEYCLOAK_ADMIN_PASSWORD=keep-me", env_text)
```

```python
    def test_install_generates_secret_values_for_missing_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\nexit 0\n")
            (root / ".env.example").write_text(
                "PUBLIC_SCHEME=http\nPUBLIC_HOST=REPLACE_ME_PUBLIC_HOST\nKEYCLOAK_ADMIN_PASSWORD=ChangeMe\nOAUTH2_PROXY_COOKIE_SECRET=REPLACE_WITH_32_BYTE_SECRET\n",
                encoding="utf-8",
            )
            write_executable(root / "scripts" / "init-network.sh", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(root / "scripts" / "prepare-harbor.sh", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(root / "scripts" / "bootstrap-keycloak.sh", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(root / "scripts" / "panel.sh", "#!/usr/bin/env bash\nexit 0\n")
            fakebin = root / "fakebin"
            fakebin.mkdir()
            write_executable(fakebin / "docker", "#!/usr/bin/env bash\nexit 0\n")

            subprocess.run(
                ["bash", "install.sh", "--skip-panel"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}"},
            )

            env_text = (root / ".env").read_text(encoding="utf-8")

        self.assertNotIn("ChangeMe", env_text)
        self.assertNotIn("REPLACE_WITH_32_BYTE_SECRET", env_text)
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests/test_install_script.py -v`  
Expected: 至少 1 个关于 env 幂等或 secret 生成的失败

- [ ] **Step 3: 实现 env 补齐和 secret 生成函数**

```bash
ensure_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "缺少命令: $1" >&2
    return 1
  }
}

random_secret() {
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
}

set_env_if_missing() {
  local file="$1" key="$2" value="$3"
  if grep -q "^${key}=" "$file"; then
    return 0
  fi
  printf '%s=%s\n' "$key" "$value" >> "$file"
}

replace_placeholder_if_present() {
  local file="$1" key="$2" placeholder="$3" value="$4"
  if grep -q "^${key}=${placeholder}$" "$file"; then
    python3 - "$file" "$key" "$value" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = []
for raw in path.read_text(encoding="utf-8").splitlines():
    if raw.startswith(f"{key}="):
        lines.append(f"{key}={value}")
    else:
        lines.append(raw)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
  fi
}

ensure_env() {
  local env_file="${ROOT_DIR}/.env"
  [[ -f "$env_file" ]] || cp "${ROOT_DIR}/.env.example" "$env_file"

  set_env_if_missing "$env_file" "KEYCLOAK_PUBLIC_HOST" "auth.localhost"
  set_env_if_missing "$env_file" "PORTAINER_PUBLIC_HOST" "portainer.localhost"
  set_env_if_missing "$env_file" "KAFKA_UI_PUBLIC_HOST" "kafka.localhost"
  set_env_if_missing "$env_file" "REDISINSIGHT_PUBLIC_HOST" "redis.localhost"
  set_env_if_missing "$env_file" "PHPMYADMIN_PUBLIC_HOST" "pma.localhost"
  set_env_if_missing "$env_file" "MONGO_EXPRESS_PUBLIC_HOST" "mongo.localhost"
  set_env_if_missing "$env_file" "HARBOR_PUBLIC_HOST" "harbor.localhost"
  set_env_if_missing "$env_file" "BUSINESS_PANEL_HOST" "127.0.0.1"
  set_env_if_missing "$env_file" "BUSINESS_PANEL_PORT" "8090"

  replace_placeholder_if_present "$env_file" "KEYCLOAK_ADMIN_PASSWORD" "ChangeMe_Keycloak_Admin_123!" "$(random_secret)"
  replace_placeholder_if_present "$env_file" "KEYCLOAK_DB_PASSWORD" "ChangeMe_Keycloak_Db_123!" "$(random_secret)"
  replace_placeholder_if_present "$env_file" "PORTAINER_CLIENT_SECRET" "ChangeMe_Portainer_Secret_123!" "$(random_secret)"
  replace_placeholder_if_present "$env_file" "OAUTH2_PROXY_CLIENT_SECRET" "ChangeMe_OAuth2Proxy_Secret_123!" "$(random_secret)"
  replace_placeholder_if_present "$env_file" "OAUTH2_PROXY_COOKIE_SECRET" "REPLACE_WITH_32_BYTE_SECRET" "$(python3 - <<'PY'\nimport secrets\nprint(secrets.token_hex(16))\nPY)"
}
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `python3 -m unittest tests/test_install_script.py -v`  
Expected: `OK`

- [ ] **Step 5: 回归当前脚本语法**

Run: `python3 -m unittest tests/test_install_script.py -v && bash -n install.sh scripts/install-lib.sh scripts/prepare-env.sh`  
Expected: 测试通过，shell 语法检查无输出

### Task 3: 实现阶段编排、幂等跳过与修复模式

**Files:**
- Modify: `install.sh`
- Modify: `scripts/install-lib.sh`
- Modify: `tests/test_install_script.py`

- [ ] **Step 1: 写失败测试，固定阶段顺序与 `--repair` 行为**

```python
    def test_install_runs_existing_scripts_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\necho harbor-install >> \"$INSTALL_LOG\"\n")
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")
            log_file = root / "run.log"
            for name in ("init-network.sh", "prepare-harbor.sh", "bootstrap-keycloak.sh", "panel.sh"):
                write_executable(root / "scripts" / name, f\"#!/usr/bin/env bash\\necho {name} >> \\\"$INSTALL_LOG\\\"\\n\")
            fakebin = root / "fakebin"
            fakebin.mkdir()
            write_executable(fakebin / "docker", "#!/usr/bin/env bash\nexit 0\n")

            result = subprocess.run(
                ["bash", "install.sh"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}", "INSTALL_LOG": str(log_file)},
            )

            lines = log_file.read_text(encoding="utf-8").splitlines()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            lines,
            ["init-network.sh", "prepare-harbor.sh", "harbor-install", "bootstrap-keycloak.sh", "panel.sh"],
        )
```

```python
    def test_install_skips_panel_when_flag_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\nexit 0\n")
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")
            panel_script = root / "scripts" / "panel.sh"
            write_executable(panel_script, "#!/usr/bin/env bash\necho panel\n")
            for name in ("init-network.sh", "prepare-harbor.sh", "bootstrap-keycloak.sh"):
                write_executable(root / "scripts" / name, "#!/usr/bin/env bash\nexit 0\n")
            fakebin = root / "fakebin"
            fakebin.mkdir()
            write_executable(fakebin / "docker", "#!/usr/bin/env bash\nexit 0\n")

            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}"},
            )

        self.assertEqual(result.returncode, 0)
        self.assertNotIn("panel", result.stdout)
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests/test_install_script.py -v`  
Expected: 至少 1 个关于阶段顺序或参数分支的失败

- [ ] **Step 3: 实现阶段调度与结果输出**

```bash
log_phase() {
  local index="$1" total="$2" name="$3"
  printf '[%s/%s] %s\n' "$index" "$total" "$name"
}

run_step() {
  local label="$1"; shift
  if "$@"; then
    echo "OK: ${label}"
  else
    echo "FAIL: ${label}" >&2
    return 1
  fi
}

run_install() {
  log_phase 1 8 preflight
  run_step "preflight" preflight

  log_phase 2 8 env
  run_step "env" ensure_env

  log_phase 3 8 network
  run_step "network" "${ROOT_DIR}/scripts/init-network.sh"

  log_phase 4 8 main_stack
  run_step "main_stack" "${ROOT_DIR}/scripts/up-main.sh"

  log_phase 5 8 harbor_prepare
  run_step "harbor_prepare" "${ROOT_DIR}/scripts/prepare-harbor.sh"

  if [[ "${INSTALL_SKIP_HARBOR}" -eq 1 ]]; then
    echo "SKIP: harbor_install"
  else
    log_phase 6 8 harbor_install
    run_step "harbor_install" bash -lc "cd '${ROOT_DIR}/harbor/installer' && ./install.sh --with-trivy"
  fi

  log_phase 7 8 bootstrap
  run_step "bootstrap" "${ROOT_DIR}/scripts/bootstrap-keycloak.sh"

  log_phase 8 8 panel
  if [[ "${INSTALL_SKIP_PANEL}" -eq 1 ]]; then
    echo "SKIP: panel"
  else
    run_step "panel" "${ROOT_DIR}/scripts/panel.sh" start
  fi
}
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `python3 -m unittest tests/test_install_script.py -v`  
Expected: `OK`

- [ ] **Step 5: 记录当前脚本检查点**

Run: `python3 -m unittest tests/test_install_script.py -v && bash -n install.sh scripts/install-lib.sh`  
Expected: 测试通过，shell 语法检查无输出

### Task 4: 更新 README 并补最终验证

**Files:**
- Modify: `README.md`
- Modify: `install.sh`
- Modify: `tests/test_install_script.py`

- [ ] **Step 1: 在 README 增加安装脚本章节**

````md
## 一键安装

完整项目目录交付后，可直接执行：

```bash
./install.sh
```

常用参数：

```bash
./install.sh --repair
./install.sh --skip-panel
```

说明：

- 脚本会自动生成缺失的密码和 secret
- 不会自动改 Windows hosts
- Harbor 为必装项，installer 目录必须存在
````

- [ ] **Step 2: 补一条 README 提示，要求手动添加 `hosts`**

```md
Windows hosts 至少应包含：

```text
127.0.0.1 auth.localhost
127.0.0.1 portainer.localhost
127.0.0.1 kafka.localhost
127.0.0.1 redis.localhost
127.0.0.1 pma.localhost
127.0.0.1 mongo.localhost
127.0.0.1 harbor.localhost
```
```

- [ ] **Step 3: 运行最终自动验证**

Run: `python3 -m unittest tests/test_install_script.py -v && bash -n install.sh scripts/install-lib.sh scripts/*.sh`  
Expected: 测试通过，shell 语法检查无输出

- [ ] **Step 4: 运行一次最小人工验收**

Run:

```bash
./install.sh --skip-panel
./scripts/panel.sh start
./scripts/check-main.sh
```

Expected:

- 输出 8 个阶段日志
- 看到 `OK` / `SKIP` / `FAIL` 风格结果
- 输出统一入口地址清单
- `check-main.sh` 能打印当前统一入口主机名

## Self-Review

- 设计稿第 5 节阶段结构：由 Task 3 的阶段编排覆盖
- 设计稿第 6 节可重复执行策略：由 Task 2 和 Task 3 的幂等逻辑覆盖
- 设计稿第 7-8 节输入输出约定：由 Task 3 和 Task 4 的脚本输出与 README 覆盖
- 设计稿第 9 节交付方式：由 Task 4 的 README 说明覆盖
- 设计稿第 10-11 节风险与冻结决策：计划中未偏离 Harbor 必装、自动生成 secret、手动 hosts、可重复执行这些边界
