# Nightingale Nacos SSO Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前统一入口与 Keycloak 体系下，为项目新增 `夜莺` 与 `Nacos` 两个服务，实现统一主机名入口、统一登录和业务面板接入。

**Architecture:** 两个服务都并入主 `compose.yml`。`Nacos` 采用 `nacos + nacos-mysql`，`夜莺` 采用 `nightingale + nightingale-mysql + nightingale-redis`。统一入口继续走现有 `gateway`，认证都使用原生 OIDC 直连 `Keycloak`，首版只打通登录不做角色映射，业务面板新增两个业务单元和基础状态探测。

**Tech Stack:** Docker Compose, Keycloak OIDC, Nginx gateway, Python business panel, Bash bootstrap scripts, Python 3.14 `unittest`

---

**Execution Note:** 当前目录不是 git 仓库。执行本计划时，不要求 commit 检查点；以测试、配置校验和真实请求验证作为完成依据。

## File Map

- Modify: `.env.example`
  - 作用：新增 `NACOS_PUBLIC_HOST`、`NIGHTINGALE_PUBLIC_HOST` 及相关配置项
- Modify: `.env`
  - 作用：同步当前运行环境的默认值
- Modify: `compose.yml`
  - 作用：新增 `nacos`、`nacos-mysql`、`nightingale`、`nightingale-mysql`、`nightingale-redis`
- Modify: `gateway/nginx.conf`
  - 作用：新增 `nacos.localhost` 与 `nightingale.localhost` 两条路由
- Create: `nacos/application.properties`
  - 作用：集中保存 Nacos OIDC 与数据库配置
- Create: `nightingale/config.toml`
  - 作用：保存夜莺数据库、Redis、OIDC 基础配置
- Modify: `scripts/bootstrap-keycloak.sh`
  - 作用：新增 `nacos` 与 `nightingale` client 的刷新逻辑
- Modify: `business_panel/config.py`
  - 作用：新增 `NACOS_PUBLIC_HOST`、`NIGHTINGALE_PUBLIC_HOST` 读取
- Modify: `business_panel/catalog.py`
  - 作用：新增 `nacos`、`nightingale` 业务单元
- Modify: `business_panel/probes.py`
  - 作用：增加两个新服务的入口/认证判定
- Modify: `README.md`
  - 作用：补统一入口、登录、配置与验证说明
- Create: `tests/test_nacos_nightingale_compose.py`
  - 作用：验证 compose、gateway 与面板目录定义
- Modify: `tests/test_config_catalog.py`
  - 作用：验证新 host 变量与业务单元
- Modify: `tests/test_probes.py`
  - 作用：验证新服务认证跳转判定

### Task 1: 扩展环境变量与业务面板目录定义

**Files:**
- Modify: `.env.example`
- Modify: `.env`
- Modify: `business_panel/config.py`
- Modify: `business_panel/catalog.py`
- Modify: `tests/test_config_catalog.py`

- [ ] **Step 1: 先写失败测试，固定新增 host 与业务单元**

```python
    def test_build_units_includes_nacos_and_nightingale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_env(
                root,
                self._base_env_lines()
                + [
                    "NACOS_PUBLIC_HOST=nacos.localhost",
                    "NIGHTINGALE_PUBLIC_HOST=nightingale.localhost",
                ],
            )
            settings = load_settings(root)
            units = {unit.unit_id: unit for unit in build_units(settings)}

        self.assertEqual(units["nacos"].entry_url, "http://nacos.localhost")
        self.assertEqual(units["nightingale"].entry_url, "http://nightingale.localhost")
        self.assertEqual(units["nacos"].auth_mode, "oidc_redirect")
        self.assertEqual(units["nightingale"].auth_mode, "oidc_redirect")
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests/test_config_catalog.py -v`  
Expected: 至少 1 个关于 `nacos` / `nightingale` 缺失的失败

- [ ] **Step 3: 实现最小配置与目录扩展**

```python
# business_panel/config.py
    nacos_public_host: str = "nacos.localhost"
    nightingale_public_host: str = "nightingale.localhost"
```

```python
# load_settings(...)
        nacos_public_host=_optional_str(env_values, "NACOS_PUBLIC_HOST", "nacos.localhost"),
        nightingale_public_host=_optional_str(env_values, "NIGHTINGALE_PUBLIC_HOST", "nightingale.localhost"),
```

```python
# business_panel/catalog.py
        UnitDefinition(
            unit_id="nacos",
            display_name="Nacos",
            description="Service registry and config center.",
            entry_url=f"{settings.public_scheme}://{settings.nacos_public_host}",
            compose_scope="main",
            start_services=("nacos", "nacos-mysql"),
            stop_services=("nacos", "nacos-mysql"),
            shared_dependencies=(),
            auth_mode="oidc_redirect",
            auth_path="openid-connect/auth",
            auth_expectation="required",
        ),
        UnitDefinition(
            unit_id="nightingale",
            display_name="Nightingale",
            description="Observability and alerting platform.",
            entry_url=f"{settings.public_scheme}://{settings.nightingale_public_host}",
            compose_scope="main",
            start_services=("nightingale", "nightingale-mysql", "nightingale-redis"),
            stop_services=("nightingale", "nightingale-mysql", "nightingale-redis"),
            shared_dependencies=(),
            auth_mode="oidc_redirect",
            auth_path="openid-connect/auth",
            auth_expectation="required",
        ),
```

```dotenv
# .env.example / .env
NACOS_PUBLIC_HOST=nacos.localhost
NIGHTINGALE_PUBLIC_HOST=nightingale.localhost
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `python3 -m unittest tests/test_config_catalog.py -v`  
Expected: `OK`

- [ ] **Step 5: 记录当前检查点**

Run: `python3 -m unittest tests/test_config_catalog.py -v && rg -n 'NACOS_PUBLIC_HOST|NIGHTINGALE_PUBLIC_HOST' .env.example business_panel/config.py`  
Expected: 测试通过，能看到两个新增 host 配置

### Task 2: 把 Nacos 与 Nightingale 并入主 compose 与统一入口

**Files:**
- Modify: `compose.yml`
- Modify: `gateway/nginx.conf`
- Create: `nacos/application.properties`
- Create: `nightingale/config.toml`
- Create: `tests/test_nacos_nightingale_compose.py`

- [ ] **Step 1: 写失败测试，固定 compose 与 gateway 入口**

```python
import pathlib
import unittest


class ComposeExtensionTest(unittest.TestCase):
    def test_compose_includes_nacos_and_nightingale_services(self) -> None:
        compose = pathlib.Path("compose.yml").read_text(encoding="utf-8")
        self.assertIn("  nacos:", compose)
        self.assertIn("  nacos-mysql:", compose)
        self.assertIn("  nightingale:", compose)
        self.assertIn("  nightingale-mysql:", compose)
        self.assertIn("  nightingale-redis:", compose)

    def test_gateway_routes_include_new_hostnames(self) -> None:
        gateway = pathlib.Path("gateway/nginx.conf").read_text(encoding="utf-8")
        self.assertIn("server_name nacos.localhost;", gateway)
        self.assertIn("server_name nightingale.localhost;", gateway)
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests/test_nacos_nightingale_compose.py -v`  
Expected: `FAIL`，缺少新服务或新路由

- [ ] **Step 3: 实现 compose 与 gateway 最小接入**

```yaml
  nacos-mysql:
    image: mysql:8.4
    restart: unless-stopped
    environment:
      MYSQL_DATABASE: nacos
      MYSQL_USER: nacos
      MYSQL_PASSWORD: ${NACOS_DB_PASSWORD}
      MYSQL_ROOT_PASSWORD: ${NACOS_DB_ROOT_PASSWORD}
    volumes:
      - nacos_mysql_data:/var/lib/mysql
    networks:
      - tools_net

  nacos:
    image: nacos/nacos-server:latest
    restart: unless-stopped
    env_file:
      - ./nacos/application.properties
    depends_on:
      - nacos-mysql
    networks:
      - tools_net
```

```yaml
  nightingale-mysql:
    image: mysql:8.4
    restart: unless-stopped
    environment:
      MYSQL_DATABASE: nightingale
      MYSQL_USER: nightingale
      MYSQL_PASSWORD: ${NIGHTINGALE_DB_PASSWORD}
      MYSQL_ROOT_PASSWORD: ${NIGHTINGALE_DB_ROOT_PASSWORD}
    volumes:
      - nightingale_mysql_data:/var/lib/mysql
    networks:
      - tools_net

  nightingale-redis:
    image: redis:7.2-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes", "--requirepass", "${NIGHTINGALE_REDIS_PASSWORD}"]
    volumes:
      - nightingale_redis_data:/data
    networks:
      - tools_net

  nightingale:
    image: flashcatcloud/nightingale:latest
    restart: unless-stopped
    volumes:
      - ./nightingale/config.toml:/app/etc/config.toml:ro
    depends_on:
      - nightingale-mysql
      - nightingale-redis
    networks:
      - tools_net
```

```nginx
  server {
    listen 80;
    server_name nacos.localhost;

    location / {
      set $upstream http://nacos:8848;
      proxy_pass $upstream;
    }
  }

  server {
    listen 80;
    server_name nightingale.localhost;

    location / {
      set $upstream http://nightingale:17000;
      proxy_pass $upstream;
    }
  }
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `python3 -m unittest tests/test_nacos_nightingale_compose.py -v`  
Expected: `OK`

- [ ] **Step 5: 验证 compose 语法**

Run: `docker compose --env-file .env -f compose.yml config >/tmp/nacos-n9e.compose.rendered.yml`  
Expected: exit code 0

### Task 3: 配置原生 OIDC 与 Keycloak bootstrap

**Files:**
- Create: `nacos/application.properties`
- Create: `nightingale/config.toml`
- Modify: `scripts/bootstrap-keycloak.sh`
- Modify: `tests/test_probes.py`

