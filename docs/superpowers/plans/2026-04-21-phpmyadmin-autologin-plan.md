# phpMyAdmin Autologin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 phpMyAdmin 增加“仅 `/platform-admins` 可访问、进入后自动使用固定 MariaDB 账号登录、账号权限仅覆盖 `appdb`”的完整实现，并把数据库账号补偿逻辑纳入安装 / repair 流程。

**Architecture:** 继续复用现有 `oauth2-proxy-phpmyadmin` 作为外层 SSO 入口，在该实例上增加 `--allowed-group=${PHPMYADMIN_ALLOWED_GROUP}` 做准入控制。phpMyAdmin 本体改为挂载 `phpmyadmin/config.user.inc.php` 并切到 `auth_type = config`，从环境变量读取固定数据库账号。MariaDB 专用账号通过新的 `scripts/repair-mariadb-phpmyadmin-user.sh` 幂等创建，并在 `scripts/install-lib.sh` 的 `up-main.sh` 之后自动执行，覆盖新环境与老数据卷场景。

**Tech Stack:** Docker Compose, Bash, phpMyAdmin, oauth2-proxy, MariaDB, Python 3 `unittest`

---

**Execution Note:** `scripts/bootstrap-keycloak.sh` 已经创建 `platform-admins` 组，本计划不修改 Keycloak bootstrap，只复用现有组。

## File Map

- Modify: `.env.example`
  - 作用：新增 phpMyAdmin 自动登录账号、密码和允许组变量
- Modify: `scripts/install-lib.sh`
  - 作用：补齐默认值、替换自动登录密码占位符、把 MariaDB repair 脚本纳入安装顺序
- Create: `scripts/repair-mariadb-phpmyadmin-user.sh`
  - 作用：幂等创建 / 更新 `pma_appdb_admin` 并授予 `appdb.*` 范围内最小权限
- Modify: `tests/test_install_script.py`
  - 作用：锁定 `.env` 默认值、密码占位符替换与新阶段执行顺序
- Create: `phpmyadmin/config.user.inc.php`
  - 作用：把 phpMyAdmin 改为 `config` 认证并固定到 `appdb`
- Modify: `compose.yml`
  - 作用：给 phpMyAdmin 注入自动登录环境变量与配置挂载，并给 `oauth2-proxy-phpmyadmin` 增加组限制
- Create: `tests/test_phpmyadmin_autologin_contract.py`
  - 作用：锁定 compose、phpMyAdmin 配置与 README 中的自动登录合同
- Modify: `README.md`
  - 作用：说明 `/platform-admins` 准入、自动登录行为、`403` 行为与 repair 用法

### Task 1: 安装流与 MariaDB repair 合同

**Files:**
- Modify: `.env.example`
- Modify: `scripts/install-lib.sh`
- Create: `scripts/repair-mariadb-phpmyadmin-user.sh`
- Modify: `tests/test_install_script.py`

- [ ] **Step 1: 先写失败测试，锁定新的 env 默认值与阶段顺序**

```python
def stage_successful_runtime_scripts(root: Path, panel_content: str = "#!/usr/bin/env bash\nexit 0\n") -> None:
    stage_contents = {
        "init-network.sh": "#!/usr/bin/env bash\nexit 0\n",
        "up-main.sh": "#!/usr/bin/env bash\nexit 0\n",
        "repair-mariadb-phpmyadmin-user.sh": "#!/usr/bin/env bash\nexit 0\n",
        "prepare-harbor.sh": "#!/usr/bin/env bash\nexit 0\n",
        "bootstrap-keycloak.sh": "#!/usr/bin/env bash\nexit 0\n",
        "panel.sh": panel_content,
    }
    for name, content in stage_contents.items():
        write_executable(root / "scripts" / name, content)
```

```python
    def test_install_adds_phpmyadmin_autologin_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\nexit 0\n")
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\n", encoding="utf-8")

            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel", "--skip-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
            )
            env_map = parse_env((root / ".env").read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(env_map["PHPMYADMIN_ALLOWED_GROUP"], "/platform-admins")
        self.assertEqual(env_map["PHPMYADMIN_AUTOLOGIN_USER"], "pma_appdb_admin")
```

```python
    def test_install_generates_phpmyadmin_autologin_password_when_placeholder_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\nexit 0\n")
            (root / ".env.example").write_text(
                "PUBLIC_SCHEME=http\nPHPMYADMIN_AUTOLOGIN_PASSWORD=ChangeMe_PhpMyAdmin_Autologin_123!\n",
                encoding="utf-8",
            )

            subprocess.run(
                ["bash", "install.sh", "--skip-panel", "--skip-harbor"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            env_map = parse_env((root / ".env").read_text(encoding="utf-8"))

        self.assertIn("PHPMYADMIN_AUTOLOGIN_PASSWORD", env_map)
        self.assertNotEqual(env_map["PHPMYADMIN_AUTOLOGIN_PASSWORD"], "ChangeMe_PhpMyAdmin_Autologin_123!")
        self.assertGreaterEqual(len(env_map["PHPMYADMIN_AUTOLOGIN_PASSWORD"]), 24)
```

```python
    def test_install_runs_phpmyadmin_user_repair_after_main_stack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            log_file = root / "run.log"
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\necho harbor-install >> \"$INSTALL_LOG\"\n")
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")
            for name in (
                "init-network.sh",
                "up-main.sh",
                "repair-mariadb-phpmyadmin-user.sh",
                "prepare-harbor.sh",
                "bootstrap-keycloak.sh",
                "panel.sh",
            ):
                write_executable(root / "scripts" / name, f"#!/usr/bin/env bash\necho {name} >> \"$INSTALL_LOG\"\n")

            result = subprocess.run(
                ["bash", "install.sh"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "INSTALL_LOG": str(log_file)},
            )
            lines = log_file.read_text(encoding="utf-8").splitlines()
            output_lines = [line for line in result.stdout.splitlines() if line.startswith("[") or line.startswith("OK:")]

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            output_lines,
            [
                "[1/9] preflight",
                "OK: preflight",
                "[2/9] env",
                "OK: env",
                "[3/9] network",
                "OK: network",
                "[4/9] main_stack",
                "OK: main_stack",
                "[5/9] phpmyadmin_user_repair",
                "OK: phpmyadmin_user_repair",
                "[6/9] harbor_prepare",
                "OK: harbor_prepare",
                "[7/9] harbor_install",
                "OK: harbor_install",
                "[8/9] bootstrap",
                "OK: bootstrap",
                "[9/9] panel",
                "OK: panel",
            ],
        )
        self.assertEqual(
            lines,
            [
                "init-network.sh",
                "up-main.sh",
                "repair-mariadb-phpmyadmin-user.sh",
                "prepare-harbor.sh",
                "harbor-install",
                "bootstrap-keycloak.sh",
                "panel.sh",
            ],
        )
```

```python
        self.assertEqual(lines, ["init-network.sh", "up-main.sh", "repair-mariadb-phpmyadmin-user.sh", "bootstrap-keycloak.sh", "panel.sh"])
        self.assertIn("[5/9] phpmyadmin_user_repair", result.stdout)
        self.assertIn("OK: phpmyadmin_user_repair", result.stdout)
        self.assertIn("[6/9] harbor_prepare", result.stdout)
        self.assertIn("[7/9] harbor_install", result.stdout)
```

```python
        self.assertEqual(
            relevant_lines,
            [
                "[1/9] preflight",
                "OK: preflight",
                "[2/9] env",
                "OK: env",
                "[3/9] network",
                "OK: network",
                "[4/9] main_stack",
                "OK: main_stack",
                "[5/9] phpmyadmin_user_repair",
                "OK: phpmyadmin_user_repair",
                "[6/9] harbor_prepare",
                "SKIP: harbor_prepare",
                "[7/9] harbor_install",
                "SKIP: harbor_install",
                "[8/9] bootstrap",
                "OK: bootstrap",
                "[9/9] panel",
                "SKIP: panel",
            ],
        )
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests/test_install_script.py -v`  
Expected: `KeyError: 'PHPMYADMIN_AUTOLOGIN_USER'`、`PHPMYADMIN_ALLOWED_GROUP` 缺失，或阶段顺序仍停留在 `8` 段

- [ ] **Step 3: 补 .env.example 与 install-lib 默认值**

```dotenv
MARIADB_DATABASE=appdb
MARIADB_USER=appuser
MARIADB_PASSWORD=ChangeMe_MariaDB_User_123!
MARIADB_ROOT_PASSWORD=ChangeMe_MariaDB_Root_123!
PHPMYADMIN_ALLOWED_GROUP=/platform-admins
PHPMYADMIN_AUTOLOGIN_USER=pma_appdb_admin
PHPMYADMIN_AUTOLOGIN_PASSWORD=ChangeMe_PhpMyAdmin_Autologin_123!
```

```bash
run_install() {
  local total=9

  log_phase 1 "${total}" "preflight"
  run_step "preflight" preflight

  log_phase 2 "${total}" "env"
  run_step "env" ensure_env

  log_phase 3 "${total}" "network"
  run_step "network" "${ROOT_DIR}/scripts/init-network.sh"

  log_phase 4 "${total}" "main_stack"
  run_step "main_stack" "${ROOT_DIR}/scripts/up-main.sh"

  log_phase 5 "${total}" "phpmyadmin_user_repair"
  run_step "phpmyadmin_user_repair" "${ROOT_DIR}/scripts/repair-mariadb-phpmyadmin-user.sh"

  log_phase 6 "${total}" "harbor_prepare"
  if [[ "${INSTALL_SKIP_HARBOR}" == "1" ]]; then
    printf 'SKIP: harbor_prepare\n'
  else
    run_step "harbor_prepare" "${ROOT_DIR}/scripts/prepare-harbor.sh"
  fi

  log_phase 7 "${total}" "harbor_install"
  if [[ "${INSTALL_SKIP_HARBOR}" == "1" ]]; then
    printf 'SKIP: harbor_install\n'
  else
    run_step "harbor_install" run_harbor_install
  fi

  log_phase 8 "${total}" "bootstrap"
  run_step "bootstrap" "${ROOT_DIR}/scripts/bootstrap-keycloak.sh"

  log_phase 9 "${total}" "panel"
  if [[ "${INSTALL_SKIP_PANEL}" == "1" ]]; then
    printf 'SKIP: panel\n'
  else
    run_step "panel" "${ROOT_DIR}/scripts/panel.sh" start
  fi
}
```

```bash
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
  set_env_if_missing "${env_file}" "PHPMYADMIN_ALLOWED_GROUP" "/platform-admins"
  set_env_if_missing "${env_file}" "PHPMYADMIN_AUTOLOGIN_USER" "pma_appdb_admin"

  if grep -q "^PHPMYADMIN_AUTOLOGIN_PASSWORD=ChangeMe_PhpMyAdmin_Autologin_123!$" "${env_file}"; then
    replace_placeholder_if_present "${env_file}" "PHPMYADMIN_AUTOLOGIN_PASSWORD" "ChangeMe_PhpMyAdmin_Autologin_123!" "$(random_secret)"
  fi
}
```

- [ ] **Step 4: 新建幂等的 MariaDB repair 脚本**

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

[[ -f "${ENV_FILE}" ]] || { echo "缺少 ${ENV_FILE}" >&2; exit 1; }

set -a
source "${ENV_FILE}"
set +a

require_env() {
  local key="$1"
  [[ -n "${!key:-}" ]] || { echo "缺少环境变量: ${key}" >&2; exit 1; }
}

sql_escape_literal() {
  python3 - "$1" <<'PY'
import sys
print(sys.argv[1].replace("\\", "\\\\").replace("'", "''"))
PY
}

sql_escape_identifier() {
  python3 - "$1" <<'PY'
import sys
print(sys.argv[1].replace("`", "``"))
PY
}

require_env MARIADB_DATABASE
require_env MARIADB_ROOT_PASSWORD
require_env PHPMYADMIN_AUTOLOGIN_USER
require_env PHPMYADMIN_AUTOLOGIN_PASSWORD

db_name="$(sql_escape_identifier "${MARIADB_DATABASE}")"
db_user="$(sql_escape_literal "${PHPMYADMIN_AUTOLOGIN_USER}")"
db_password="$(sql_escape_literal "${PHPMYADMIN_AUTOLOGIN_PASSWORD}")"

docker exec -i mariadb mariadb -uroot "-p${MARIADB_ROOT_PASSWORD}" <<SQL
CREATE USER IF NOT EXISTS '${db_user}'@'%' IDENTIFIED BY '${db_password}';
ALTER USER '${db_user}'@'%' IDENTIFIED BY '${db_password}';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER, CREATE VIEW, SHOW VIEW, REFERENCES, TRIGGER, LOCK TABLES, CREATE TEMPORARY TABLES
  ON \`${db_name}\`.* TO '${db_user}'@'%';
FLUSH PRIVILEGES;
SQL
```

- [ ] **Step 5: 运行测试并确认安装流转绿**

Run: `python3 -m unittest tests/test_install_script.py -v`  
Expected: `OK`

Run: `bash -n install.sh scripts/install-lib.sh scripts/repair-mariadb-phpmyadmin-user.sh`  
Expected: 无输出

- [ ] **Step 6: 提交这一阶段**

```bash
git add .env.example scripts/install-lib.sh scripts/repair-mariadb-phpmyadmin-user.sh tests/test_install_script.py
git commit -m "feat: add phpmyadmin repair stage"
```

### Task 2: phpMyAdmin 自动登录合同与编排

**Files:**
- Modify: `compose.yml`
- Create: `phpmyadmin/config.user.inc.php`
- Create: `tests/test_phpmyadmin_autologin_contract.py`

- [ ] **Step 1: 先写失败合同测试，锁定 compose 与配置文件**

```python
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class PhpMyAdminAutologinContractTest(unittest.TestCase):
    def test_compose_mounts_phpmyadmin_autologin_config_and_group_gate(self) -> None:
        text = (REPO_ROOT / "compose.yml").read_text(encoding="utf-8")
        for needle in (
            "MARIADB_DATABASE: ${MARIADB_DATABASE}",
            "PHPMYADMIN_AUTOLOGIN_USER: ${PHPMYADMIN_AUTOLOGIN_USER}",
            "PHPMYADMIN_AUTOLOGIN_PASSWORD: ${PHPMYADMIN_AUTOLOGIN_PASSWORD}",
            "- ./phpmyadmin/config.user.inc.php:/etc/phpmyadmin/config.user.inc.php:ro",
            "- --allowed-group=${PHPMYADMIN_ALLOWED_GROUP}",
        ):
            self.assertIn(needle, text)

    def test_phpmyadmin_config_uses_config_auth_and_only_db(self) -> None:
        text = (REPO_ROOT / "phpmyadmin" / "config.user.inc.php").read_text(encoding="utf-8")
        for needle in (
            "$cfg['Servers'][$i]['auth_type'] = 'config';",
            "$cfg['Servers'][$i]['host'] = getenv('PMA_HOST') ?: 'mariadb';",
            "$cfg['Servers'][$i]['user'] = getenv('PHPMYADMIN_AUTOLOGIN_USER') ?: '';",
            "$cfg['Servers'][$i]['password'] = getenv('PHPMYADMIN_AUTOLOGIN_PASSWORD') ?: '';",
            "$cfg['Servers'][$i]['only_db'] = [getenv('MARIADB_DATABASE') ?: 'appdb'];",
        ):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行合同测试并确认当前失败**

Run: `python3 -m unittest tests/test_phpmyadmin_autologin_contract.py -v`  
Expected: `FileNotFoundError: phpmyadmin/config.user.inc.php` 或 `AssertionError` 提示 compose 缺少挂载 / 组限制

- [ ] **Step 3: 新建 phpMyAdmin config 模式配置文件**

```php
<?php

declare(strict_types=1);

$i = 1;
$cfg['Servers'][$i]['auth_type'] = 'config';
$cfg['Servers'][$i]['host'] = getenv('PMA_HOST') ?: 'mariadb';
$cfg['Servers'][$i]['port'] = (int) (getenv('PMA_PORT') ?: 3306);
$cfg['Servers'][$i]['AllowNoPassword'] = false;
$cfg['Servers'][$i]['user'] = getenv('PHPMYADMIN_AUTOLOGIN_USER') ?: '';
$cfg['Servers'][$i]['password'] = getenv('PHPMYADMIN_AUTOLOGIN_PASSWORD') ?: '';
$cfg['Servers'][$i]['only_db'] = [getenv('MARIADB_DATABASE') ?: 'appdb'];
```

- [ ] **Step 4: 更新 compose.yml，把准入与自动登录接起来**

```yaml
  phpmyadmin:
    image: ${PHPMYADMIN_IMAGE}
    container_name: phpmyadmin
    restart: unless-stopped
    environment:
      PMA_HOST: mariadb
      PMA_PORT: 3306
      PMA_ABSOLUTE_URI: ${PUBLIC_SCHEME}://${PHPMYADMIN_PUBLIC_HOST}/
      MARIADB_DATABASE: ${MARIADB_DATABASE}
      PHPMYADMIN_AUTOLOGIN_USER: ${PHPMYADMIN_AUTOLOGIN_USER}
      PHPMYADMIN_AUTOLOGIN_PASSWORD: ${PHPMYADMIN_AUTOLOGIN_PASSWORD}
      UPLOAD_LIMIT: 256M
    volumes:
      - ./phpmyadmin/config.user.inc.php:/etc/phpmyadmin/config.user.inc.php:ro
    depends_on:
      - mariadb
    networks:
      - tools_net
```

```yaml
  oauth2-proxy-phpmyadmin:
    <<: *oauth2-proxy-common
    container_name: oauth2-proxy-phpmyadmin
    command:
      - --config=/etc/oauth2-proxy/oauth2-proxy.cfg
      - --http-address=0.0.0.0:4181
      - --redirect-url=${PUBLIC_SCHEME}://${PHPMYADMIN_PUBLIC_HOST}/oauth2/callback
      - --upstream=http://phpmyadmin:80/
      - --cookie-name=_oauth2_proxy_pma
      - --allowed-group=${PHPMYADMIN_ALLOWED_GROUP}
    depends_on:
      - keycloak
      - redis
      - phpmyadmin
```

- [ ] **Step 5: 运行合同测试并验证 compose 可渲染**

Run: `python3 -m unittest tests/test_phpmyadmin_autologin_contract.py -v`  
Expected: `OK`

Run: `docker compose --env-file .env.example config >/tmp/phpmyadmin-autologin.compose.yml`  
Expected: 命令退出码为 `0`

- [ ] **Step 6: 提交这一阶段**

```bash
git add compose.yml phpmyadmin/config.user.inc.php tests/test_phpmyadmin_autologin_contract.py
git commit -m "feat: enable phpmyadmin config autologin"
```

### Task 3: README 说明与最终验证

**Files:**
- Modify: `README.md`
- Modify: `tests/test_phpmyadmin_autologin_contract.py`

- [ ] **Step 1: 先扩合同测试，锁定 README 的对外说明**

```python
    def test_readme_documents_group_gate_autologin_and_repair(self) -> None:
        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for needle in (
            "只有 `platform-admins` 组成员可以进入 phpMyAdmin",
            "进入后会自动使用固定 MariaDB 账号登录",
            "该账号只授权 `appdb`",
            "非 `platform-admins` 成员会收到 `403`",
            "./install.sh --repair",
            "./scripts/repair-mariadb-phpmyadmin-user.sh",
        ):
            self.assertIn(needle, text)
```

- [ ] **Step 2: 运行 README 合同测试并确认当前失败**

Run: `python3 -m unittest tests/test_phpmyadmin_autologin_contract.py -v`  
Expected: `AssertionError`，提示 README 中尚未出现自动登录 / `403` / repair 说明

- [ ] **Step 3: 更新 README 的 phpMyAdmin 段落**

```md
### oauth2-proxy 前置保护

以下入口都经过 Keycloak 认证：

- RedisInsight: `http://PUBLIC_HOST:4180`
- phpMyAdmin: `http://PUBLIC_HOST:4181`
- mongo-express: `http://PUBLIC_HOST:4182`

第一次访问会跳转到 Keycloak。  
后续因为已经有 Keycloak 会话，一般不需要重复输密码。

#### phpMyAdmin 自动登录说明

- 只有 `platform-admins` 组成员可以进入 phpMyAdmin
- 通过 SSO 后，进入后会自动使用固定 MariaDB 账号登录
- 该账号只授权 `appdb`
- 非 `platform-admins` 成员会收到 `403`
- 如果你修改了 `PHPMYADMIN_AUTOLOGIN_PASSWORD`、`PHPMYADMIN_AUTOLOGIN_USER` 或数据库权限，重跑 `./install.sh --repair`
- 只需要补数据库账号权限时，也可以单独执行 `./scripts/repair-mariadb-phpmyadmin-user.sh`
```

- [ ] **Step 4: 做最终验证**

Run: `python3 -m unittest discover -s tests`  
Expected: `OK`

Run: `bash -n install.sh scripts/install-lib.sh scripts/repair-mariadb-phpmyadmin-user.sh`  
Expected: 无输出

Run: `docker compose --env-file .env.example config >/tmp/phpmyadmin-autologin.compose.yml`  
Expected: 命令退出码为 `0`

- [ ] **Step 5: 提交最终文档与验证完成状态**

```bash
git add README.md tests/test_phpmyadmin_autologin_contract.py
git commit -m "docs: describe phpmyadmin autologin flow"
```
