# Business Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为当前第三方业务集成栈补一个独立的统一业务面板，支持业务直达、三层状态展示和受控启停。

**Architecture:** 面板以本地 Python Web 服务形式运行，不并入现有 compose。后端负责读取 `.env`、构建业务单元、探测容器/入口/认证三层状态，并通过白名单动作调用现有 `scripts/services.sh` 与固定 `docker compose` 命令；前端使用静态 HTML/CSS/JS 单页渲染总览与业务卡片。

**Tech Stack:** Python 3.14 stdlib (`http.server`, `urllib`, `subprocess`, `threading`, `dataclasses`, `unittest`), Bash, Docker Compose, static HTML/CSS/JavaScript

---

**Execution Note:** 当前目录不是 git 仓库。执行本计划时，用“验证通过后勾选步骤”替代 git commit 检查点，不增加伪提交步骤。

## File Map

- Create: `business_panel/__init__.py`
  - 作用：包初始化，暴露版本常量
- Create: `business_panel/config.py`
  - 作用：读取项目根目录 `.env`，生成 `PanelSettings`
- Create: `business_panel/catalog.py`
  - 作用：定义业务单元、入口 URL、控制服务列表、认证模式和依赖保护策略
- Create: `business_panel/models.py`
  - 作用：定义面板使用的 dataclass 与状态枚举
- Create: `business_panel/probes.py`
  - 作用：实现容器探测、入口探测、认证探测
- Create: `business_panel/control.py`
  - 作用：白名单控制动作、共享依赖保护、单任务锁
- Create: `business_panel/status_service.py`
  - 作用：协调 catalog、probes、control，输出页面所需总览 JSON
- Create: `business_panel/server.py`
  - 作用：提供 `/`、`/api/status`、`/api/control` 路由
- Create: `business_panel/main.py`
  - 作用：启动本地 HTTP 服务
- Create: `business_panel/static/index.html`
  - 作用：统一业务面板页面骨架
- Create: `business_panel/static/app.css`
  - 作用：页面样式、状态色、卡片布局
- Create: `business_panel/static/app.js`
  - 作用：拉取状态、渲染卡片、发送控制动作
- Create: `tests/test_config_catalog.py`
  - 作用：验证设置读取和业务单元构建
- Create: `tests/test_status_service.py`
  - 作用：验证状态汇总规则
- Create: `tests/test_probes.py`
  - 作用：验证认证/入口探测分类
- Create: `tests/test_control.py`
  - 作用：验证白名单动作、共享依赖保护和锁
- Create: `tests/test_server.py`
  - 作用：验证 HTTP API 与静态页面返回
- Create: `scripts/panel.sh`
  - 作用：本地启动、停止、重启、查看业务面板服务状态
- Modify: `.env.example`
  - 作用：增加业务面板端口和刷新间隔配置
- Modify: `README.md`
  - 作用：增加业务面板启动、访问、限制与验收说明

### Task 1: 初始化 Python 面板骨架与业务单元定义

**Files:**
- Create: `business_panel/__init__.py`
- Create: `business_panel/config.py`
- Create: `business_panel/catalog.py`
- Create: `tests/test_config_catalog.py`
- Modify: `.env.example`

- [ ] **Step 1: 写失败测试，固定设置读取与业务单元结构**

```python
import tempfile
import unittest
from pathlib import Path

from business_panel.catalog import build_units
from business_panel.config import load_settings


class ConfigCatalogTest(unittest.TestCase):
    def test_load_settings_and_build_units(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                "\n".join(
                    [
                        "PUBLIC_SCHEME=http",
                        "PUBLIC_HOST=127.0.0.1",
                        "BROWSER_HOST=localhost",
                        "KEYCLOAK_PUBLIC_HOST=auth.localhost",
                        "KEYCLOAK_REALM=infra",
                        "KEYCLOAK_PORT=8080",
                        "PORTAINER_PORT=19000",
                        "KAFKA_UI_PORT=8082",
                        "REDISINSIGHT_PROXY_PORT=4180",
                        "PHPMYADMIN_PROXY_PORT=4181",
                        "MONGO_EXPRESS_PROXY_PORT=4182",
                        "HARBOR_PORT=8088",
                        "BUSINESS_PANEL_HOST=127.0.0.1",
                        "BUSINESS_PANEL_PORT=8090",
                        "BUSINESS_PANEL_REFRESH_INTERVAL=15",
                    ]
                ),
                encoding="utf-8",
            )

            settings = load_settings(root)
            units = {unit.unit_id: unit for unit in build_units(settings)}

        self.assertEqual(settings.panel_port, 8090)
        self.assertEqual(units["keycloak"].entry_url, "http://127.0.0.1:8080")
        self.assertEqual(
            units["redisinsight"].shared_dependencies,
            ("redis",),
        )
        self.assertEqual(
            units["redisinsight"].start_services,
            ("redis", "redisinsight", "oauth2-proxy-redisinsight"),
        )
        self.assertEqual(
            units["redisinsight"].stop_services,
            ("redisinsight", "oauth2-proxy-redisinsight"),
        )
        self.assertEqual(units["harbor"].compose_scope, "harbor")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests/test_config_catalog.py -v`  
Expected: `ModuleNotFoundError: No module named 'business_panel'`

- [ ] **Step 3: 实现设置读取、基础包和业务单元构建**

```python
# business_panel/config.py
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PanelSettings:
    root_dir: Path
    public_scheme: str
    public_host: str
    browser_host: str
    keycloak_public_host: str
    keycloak_realm: str
    keycloak_port: int
    portainer_port: int
    kafka_ui_port: int
    redisinsight_port: int
    phpmyadmin_port: int
    mongo_express_port: int
    harbor_port: int
    panel_host: str
    panel_port: int
    refresh_interval: int


def load_settings(root_dir: Path) -> PanelSettings:
    values = {}
    for raw_line in (root_dir / ".env").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return PanelSettings(
        root_dir=root_dir,
        public_scheme=values["PUBLIC_SCHEME"],
        public_host=values["PUBLIC_HOST"],
        browser_host=values["BROWSER_HOST"],
        keycloak_public_host=values["KEYCLOAK_PUBLIC_HOST"],
        keycloak_realm=values["KEYCLOAK_REALM"],
        keycloak_port=int(values["KEYCLOAK_PORT"]),
        portainer_port=int(values["PORTAINER_PORT"]),
        kafka_ui_port=int(values["KAFKA_UI_PORT"]),
        redisinsight_port=int(values["REDISINSIGHT_PROXY_PORT"]),
        phpmyadmin_port=int(values["PHPMYADMIN_PROXY_PORT"]),
        mongo_express_port=int(values["MONGO_EXPRESS_PROXY_PORT"]),
        harbor_port=int(values["HARBOR_PORT"]),
        panel_host=values.get("BUSINESS_PANEL_HOST", "127.0.0.1"),
        panel_port=int(values.get("BUSINESS_PANEL_PORT", "8090")),
        refresh_interval=int(values.get("BUSINESS_PANEL_REFRESH_INTERVAL", "15")),
    )
```

```python
# business_panel/catalog.py
from dataclasses import dataclass

from business_panel.config import PanelSettings


@dataclass(frozen=True)
class UnitDefinition:
    unit_id: str
    display_name: str
    description: str
    entry_url: str
    compose_scope: str
    start_services: tuple[str, ...]
    stop_services: tuple[str, ...]
    shared_dependencies: tuple[str, ...]
    auth_mode: str
    auth_path: str
    auth_expectation: str


def build_units(settings: PanelSettings) -> list[UnitDefinition]:
    base = f"{settings.public_scheme}://{settings.public_host}"
    return [
        UnitDefinition(
            unit_id="keycloak",
            display_name="Keycloak",
            description="统一认证中心",
            entry_url=f"{base}:{settings.keycloak_port}",
            compose_scope="main",
            start_services=("keycloak-postgres", "keycloak"),
            stop_services=("keycloak", "keycloak-postgres"),
            shared_dependencies=(),
            auth_mode="metadata",
            auth_path=f"/realms/{settings.keycloak_realm}/.well-known/openid-configuration",
            auth_expectation="required",
        ),
        UnitDefinition(
            unit_id="portainer",
            display_name="Portainer",
            description="容器管理面板",
            entry_url=f"{base}:{settings.portainer_port}",
            compose_scope="main",
            start_services=("portainer",),
            stop_services=("portainer",),
            shared_dependencies=(),
            auth_mode="not_checked",
            auth_path="",
            auth_expectation="not_checked",
        ),
        UnitDefinition(
            unit_id="kafka_ui",
            display_name="KafkaUI",
            description="Kafka 可视化管理",
            entry_url=f"{base}:{settings.kafka_ui_port}",
            compose_scope="main",
            start_services=("kafka", "kafka-ui"),
            stop_services=("kafka-ui", "kafka"),
            shared_dependencies=(),
            auth_mode="oidc_redirect",
            auth_path="openid-connect/auth",
            auth_expectation="required",
        ),
        UnitDefinition(
            unit_id="redisinsight",
            display_name="RedisInsight",
            description="Redis 可视化管理",
            entry_url=f"{base}:{settings.redisinsight_port}",
            compose_scope="main",
            start_services=("redis", "redisinsight", "oauth2-proxy-redisinsight"),
            stop_services=("redisinsight", "oauth2-proxy-redisinsight"),
            shared_dependencies=("redis",),
            auth_mode="oauth2_proxy_redirect",
            auth_path="/oauth2/",
            auth_expectation="required",
        ),
        UnitDefinition(
            unit_id="phpmyadmin",
            display_name="phpMyAdmin",
            description="MariaDB 管理面板",
            entry_url=f"{base}:{settings.phpmyadmin_port}",
            compose_scope="main",
            start_services=("mariadb", "phpmyadmin", "oauth2-proxy-phpmyadmin"),
            stop_services=("phpmyadmin", "oauth2-proxy-phpmyadmin"),
            shared_dependencies=("mariadb",),
            auth_mode="oauth2_proxy_redirect",
            auth_path="/oauth2/",
            auth_expectation="required",
        ),
        UnitDefinition(
            unit_id="mongo_express",
            display_name="mongo-express",
            description="MongoDB 管理面板",
            entry_url=f"{base}:{settings.mongo_express_port}",
            compose_scope="main",
            start_services=("mongodb", "mongo-express", "oauth2-proxy-mongo-express"),
            stop_services=("mongo-express", "oauth2-proxy-mongo-express"),
            shared_dependencies=("mongodb",),
            auth_mode="oauth2_proxy_redirect",
            auth_path="/oauth2/",
            auth_expectation="required",
        ),
        UnitDefinition(
            unit_id="harbor",
            display_name="Harbor",
            description="镜像仓库与安全扫描",
            entry_url=f"{base}:{settings.harbor_port}",
            compose_scope="harbor",
            start_services=(),
            stop_services=(),
            shared_dependencies=(),
            auth_mode="harbor_oidc",
            auth_path="/c/oidc/login",
            auth_expectation="best_effort",
        ),
    ]
```

```dotenv
# .env.example
BUSINESS_PANEL_HOST=127.0.0.1
BUSINESS_PANEL_PORT=8090
BUSINESS_PANEL_REFRESH_INTERVAL=15
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `python3 -m unittest tests/test_config_catalog.py -v`  
Expected: `OK`

- [ ] **Step 5: 记录任务检查点**

Run: `python3 -m unittest tests/test_config_catalog.py -v && rg -n "BUSINESS_PANEL_" .env.example`  
Expected: 单测通过，且 `.env.example` 输出三行 `BUSINESS_PANEL_*` 配置

### Task 2: 固化状态模型与总览汇总规则

**Files:**
- Create: `business_panel/models.py`
- Create: `business_panel/status_service.py`
- Create: `tests/test_status_service.py`

- [ ] **Step 1: 写失败测试，固定总状态与摘要规则**

```python
import unittest

from business_panel.models import ProbeResult, UnitSnapshot
from business_panel.status_service import summarize_panel, summarize_unit


class StatusServiceTest(unittest.TestCase):
    def test_required_auth_failure_marks_unit_failed(self) -> None:
        snapshot = UnitSnapshot(
            unit_id="kafka_ui",
            display_name="KafkaUI",
            description="Kafka 可视化管理",
            entry_url="http://127.0.0.1:8082",
            auth_expectation="required",
            container=ProbeResult.ok("容器运行"),
            endpoint=ProbeResult.ok("入口可达"),
            auth=ProbeResult.fail("未跳转到 Keycloak"),
            available_actions=("start", "stop", "restart"),
        )

        summary = summarize_unit(snapshot)

        self.assertEqual(summary.overall_state, "failed")
        self.assertIn("认证", summary.failure_summary)

    def test_best_effort_auth_failure_marks_unit_degraded(self) -> None:
        snapshot = UnitSnapshot(
            unit_id="harbor",
            display_name="Harbor",
            description="镜像仓库与安全扫描",
            entry_url="http://127.0.0.1:8088",
            auth_expectation="best_effort",
            container=ProbeResult.ok("容器运行"),
            endpoint=ProbeResult.ok("入口可达"),
            auth=ProbeResult.fail("未发现 OIDC 入口"),
            available_actions=("start", "stop", "restart"),
        )

        summary = summarize_unit(snapshot)

        self.assertEqual(summary.overall_state, "degraded")

    def test_panel_totals_count_all_statuses(self) -> None:
        payload = summarize_panel(
            [
                UnitSnapshot(
                    unit_id="keycloak",
                    display_name="Keycloak",
                    description="统一认证中心",
                    entry_url="http://127.0.0.1:8080",
                    auth_expectation="required",
                    container=ProbeResult.ok("容器运行"),
                    endpoint=ProbeResult.ok("入口可达"),
                    auth=ProbeResult.ok("OIDC 元数据正常"),
                    available_actions=("start", "stop", "restart"),
                ),
                UnitSnapshot(
                    unit_id="harbor",
                    display_name="Harbor",
                    description="镜像仓库与安全扫描",
                    entry_url="http://127.0.0.1:8088",
                    auth_expectation="best_effort",
                    container=ProbeResult.not_installed("Harbor installer 缺失"),
                    endpoint=ProbeResult.not_installed("Harbor installer 缺失"),
                    auth=ProbeResult.not_installed("Harbor installer 缺失"),
                    available_actions=("start", "stop", "restart"),
                ),
            ]
        )

        self.assertEqual(payload["totals"]["healthy"], 1)
        self.assertEqual(payload["totals"]["not_installed"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests/test_status_service.py -v`  
Expected: `ModuleNotFoundError` 或 `ImportError`

- [ ] **Step 3: 实现 dataclass、ProbeResult 工厂和汇总逻辑**

```python
# business_panel/models.py
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProbeResult:
    level: str
    summary: str

    @classmethod
    def ok(cls, summary: str) -> "ProbeResult":
        return cls(level="ok", summary=summary)

    @classmethod
    def fail(cls, summary: str) -> "ProbeResult":
        return cls(level="fail", summary=summary)

    @classmethod
    def warn(cls, summary: str) -> "ProbeResult":
        return cls(level="warn", summary=summary)

    @classmethod
    def not_installed(cls, summary: str) -> "ProbeResult":
        return cls(level="not_installed", summary=summary)


@dataclass(frozen=True)
class UnitSnapshot:
    unit_id: str
    display_name: str
    description: str
    entry_url: str
    auth_expectation: str
    container: ProbeResult
    endpoint: ProbeResult
    auth: ProbeResult
    available_actions: tuple[str, ...]


@dataclass(frozen=True)
class UnitSummary:
    unit_id: str
    display_name: str
    description: str
    entry_url: str
    overall_state: str
    failure_summary: str
    container: ProbeResult
    endpoint: ProbeResult
    auth: ProbeResult
    available_actions: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "display_name": self.display_name,
            "description": self.description,
            "entry_url": self.entry_url,
            "overall_state": self.overall_state,
            "failure_summary": self.failure_summary,
            "container": asdict(self.container),
            "endpoint": asdict(self.endpoint),
            "auth": asdict(self.auth),
            "available_actions": list(self.available_actions),
        }
```

```python
# business_panel/status_service.py
from collections import Counter
from datetime import datetime, timezone

from business_panel.models import UnitSnapshot, UnitSummary


def summarize_unit(snapshot: UnitSnapshot) -> UnitSummary:
    probes = (snapshot.container, snapshot.endpoint, snapshot.auth)
    if any(probe.level == "not_installed" for probe in probes):
        overall_state = "not_installed"
    elif snapshot.container.level == "fail" or snapshot.endpoint.level == "fail":
        overall_state = "failed"
    elif snapshot.auth.level == "fail" and snapshot.auth_expectation == "required":
        overall_state = "failed"
    elif any(probe.level in {"fail", "warn"} for probe in probes):
        overall_state = "degraded"
    else:
        overall_state = "healthy"

    failure_parts = [
        f"容器：{snapshot.container.summary}" if snapshot.container.level != "ok" else "",
        f"入口：{snapshot.endpoint.summary}" if snapshot.endpoint.level != "ok" else "",
        f"认证：{snapshot.auth.summary}" if snapshot.auth.level != "ok" else "",
    ]
    failure_summary = "；".join(part for part in failure_parts if part) or "状态正常"
    return UnitSummary(
        unit_id=snapshot.unit_id,
        display_name=snapshot.display_name,
        description=snapshot.description,
        entry_url=snapshot.entry_url,
        overall_state=overall_state,
        failure_summary=failure_summary,
        container=snapshot.container,
        endpoint=snapshot.endpoint,
        auth=snapshot.auth,
        available_actions=snapshot.available_actions,
    )


def summarize_panel(snapshots: list[UnitSnapshot]) -> dict:
    unit_summaries = [summarize_unit(snapshot) for snapshot in snapshots]
    totals = Counter(summary.overall_state for summary in unit_summaries)
    return {
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "healthy": totals["healthy"],
            "degraded": totals["degraded"],
            "failed": totals["failed"],
            "not_installed": totals["not_installed"],
            "total": len(unit_summaries),
        },
        "units": [summary.to_dict() for summary in unit_summaries],
    }
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `python3 -m unittest tests/test_status_service.py -v`  
Expected: `OK`

- [ ] **Step 5: 回归 Task 1 与当前任务**

Run: `python3 -m unittest tests/test_config_catalog.py tests/test_status_service.py -v`  
Expected: `OK`

### Task 3: 实现控制动作白名单与共享依赖保护

**Files:**
- Create: `business_panel/control.py`
- Create: `tests/test_control.py`
- Create: `scripts/panel.sh`

- [ ] **Step 1: 写失败测试，固定动作映射与并发保护**

```python
import tempfile
import unittest
from pathlib import Path

from business_panel.catalog import UnitDefinition
from business_panel.control import ControlService, PanelBusyError
from business_panel.config import PanelSettings


class ControlServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = PanelSettings(
            root_dir=Path("/tmp/project"),
            public_scheme="http",
            public_host="127.0.0.1",
            browser_host="localhost",
            keycloak_public_host="auth.localhost",
            keycloak_realm="infra",
            keycloak_port=8080,
            portainer_port=19000,
            kafka_ui_port=8082,
            redisinsight_port=4180,
            phpmyadmin_port=4181,
            mongo_express_port=4182,
            harbor_port=8088,
            panel_host="127.0.0.1",
            panel_port=8090,
            refresh_interval=15,
        )
        self.unit = UnitDefinition(
            unit_id="redisinsight",
            display_name="RedisInsight",
            description="Redis 可视化管理",
            entry_url="http://127.0.0.1:4180",
            compose_scope="main",
            start_services=("redis", "redisinsight", "oauth2-proxy-redisinsight"),
            stop_services=("redisinsight", "oauth2-proxy-redisinsight"),
            shared_dependencies=("redis",),
            auth_mode="oauth2_proxy_redirect",
            auth_path="/oauth2/",
            auth_expectation="required",
        )

    def test_stop_skips_shared_dependencies(self) -> None:
        service = ControlService(self.settings, {"redisinsight": self.unit})
        command = service.build_command("redisinsight", "stop")
        self.assertEqual(
            command.argv,
            [
                "docker",
                "compose",
                "--env-file",
                str(self.settings.root_dir / ".env"),
                "-f",
                str(self.settings.root_dir / "compose.yml"),
                "stop",
                "redisinsight",
                "oauth2-proxy-redisinsight",
            ],
        )

    def test_all_restart_uses_services_script(self) -> None:
        service = ControlService(self.settings, {"redisinsight": self.unit})
        command = service.build_command("all", "restart")
        self.assertEqual(
            command.argv,
            [str(self.settings.root_dir / "scripts" / "services.sh"), "restart"],
        )

    def test_second_lock_raises_busy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = self.settings.__class__(**{**self.settings.__dict__, "root_dir": Path(tmp)})
            service = ControlService(settings, {"redisinsight": self.unit})
            lock = service.acquire_lock()
            try:
                with self.assertRaises(PanelBusyError):
                    service.acquire_lock()
            finally:
                lock.release()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests/test_control.py -v`  
Expected: `ImportError: cannot import name 'ControlService'`

- [ ] **Step 3: 实现命令构建、锁和控制脚本**

```python
# business_panel/control.py
from dataclasses import dataclass
from pathlib import Path
import fcntl

from business_panel.catalog import UnitDefinition
from business_panel.config import PanelSettings


class PanelBusyError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandSpec:
    argv: list[str]
    cwd: Path


class LockHandle:
    def __init__(self, file_obj) -> None:
        self._file_obj = file_obj

    def release(self) -> None:
        fcntl.flock(self._file_obj.fileno(), fcntl.LOCK_UN)
        self._file_obj.close()


class ControlService:
    def __init__(self, settings: PanelSettings, units: dict[str, UnitDefinition]) -> None:
        self.settings = settings
        self.units = units
        self.lock_file = settings.root_dir / "outputs" / "runtime" / "panel" / "control.lock"

    def acquire_lock(self) -> LockHandle:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        file_obj = self.lock_file.open("a+", encoding="utf-8")
        try:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            file_obj.close()
            raise PanelBusyError("已有控制任务在执行") from exc
        return LockHandle(file_obj)

    def build_command(self, unit_id: str, action: str) -> CommandSpec:
        if action not in {"start", "stop", "restart"}:
            raise ValueError(f"unsupported action: {action}")
        if unit_id == "all":
            return CommandSpec(
                argv=[str(self.settings.root_dir / "scripts" / "services.sh"), action],
                cwd=self.settings.root_dir,
            )
        unit = self.units[unit_id]
        if unit.compose_scope == "harbor":
            if action == "start":
                argv = ["docker", "compose", "up", "-d"]
            elif action == "stop":
                argv = ["docker", "compose", "stop"]
            else:
                argv = ["docker", "compose", "restart"]
            return CommandSpec(
                argv=argv,
                cwd=self.settings.root_dir / "harbor" / "installer",
            )

        argv = [
            "docker",
            "compose",
            "--env-file",
            str(self.settings.root_dir / ".env"),
            "-f",
            str(self.settings.root_dir / "compose.yml"),
        ]
        if action == "start":
            argv.extend(["up", "-d", *unit.start_services])
        elif action == "stop":
            argv.extend(["stop", *unit.stop_services])
        else:
            argv.extend(["restart", *unit.stop_services])
        return CommandSpec(argv=argv, cwd=self.settings.root_dir)
```

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${ROOT_DIR}/outputs/runtime/panel"
PID_FILE="${RUNTIME_DIR}/panel.pid"
LOG_FILE="${RUNTIME_DIR}/panel.log"

load_env() {
  if [[ -f "${ROOT_DIR}/.env" ]]; then
    set -a
    source "${ROOT_DIR}/.env"
    set +a
  fi
}

start_panel() {
  load_env
  mkdir -p "${RUNTIME_DIR}"
  if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "panel 已在运行"
    return 0
  fi
  nohup python3 -m business_panel.main >"${LOG_FILE}" 2>&1 &
  echo $! > "${PID_FILE}"
  echo "panel 已启动: http://${BUSINESS_PANEL_HOST:-127.0.0.1}:${BUSINESS_PANEL_PORT:-8090}"
}

stop_panel() {
  if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    kill "$(cat "${PID_FILE}")"
    rm -f "${PID_FILE}"
    echo "panel 已停止"
    return 0
  fi
  echo "panel 未运行"
}

status_panel() {
  if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    echo "panel 运行中"
  else
    echo "panel 未运行"
  fi
}

case "${1:-}" in
  start) start_panel ;;
  stop) stop_panel ;;
  restart) stop_panel; start_panel ;;
  status) status_panel ;;
  *) echo "用法: ./scripts/panel.sh {start|stop|restart|status}"; exit 1 ;;
esac
```

- [ ] **Step 4: 运行测试和脚本语法检查**

Run: `python3 -m unittest tests/test_control.py -v && bash -n scripts/panel.sh`  
Expected: 单测 `OK`，shell 语法检查无输出

- [ ] **Step 5: 回归前两任务**

Run: `python3 -m unittest tests/test_config_catalog.py tests/test_status_service.py tests/test_control.py -v`  
Expected: `OK`

### Task 4: 实现入口探测与认证探测

**Files:**
- Create: `business_panel/probes.py`
- Create: `tests/test_probes.py`

- [ ] **Step 1: 写失败测试，固定三类认证检查**

```python
import unittest

from business_panel.catalog import UnitDefinition
from business_panel.models import ProbeResult
from business_panel.probes import HttpResponse, ProbeClient, probe_auth


class FakeProbeClient(ProbeClient):
    def __init__(self, responses: dict[str, HttpResponse]) -> None:
        self.responses = responses

    def fetch(self, url: str, *, follow_redirects: bool = False) -> HttpResponse:
        return self.responses[url]


class ProbesTest(unittest.TestCase):
    def test_kafka_ui_auth_accepts_keycloak_redirect(self) -> None:
        unit = UnitDefinition(
            unit_id="kafka_ui",
            display_name="KafkaUI",
            description="Kafka 可视化管理",
            entry_url="http://127.0.0.1:8082",
            compose_scope="main",
            start_services=("kafka", "kafka-ui"),
            stop_services=("kafka-ui", "kafka"),
            shared_dependencies=(),
            auth_mode="oidc_redirect",
            auth_path="openid-connect/auth",
            auth_expectation="required",
        )
        client = FakeProbeClient(
            {
                "http://127.0.0.1:8082": HttpResponse(
                    status=302,
                    headers={
                        "Location": "http://auth.localhost:8080/realms/infra/protocol/openid-connect/auth?client_id=kafka-ui"
                    },
                    body="",
                )
            }
        )

        result = probe_auth(unit, client, harbor_installed=True)

        self.assertEqual(result.level, "ok")

    def test_oauth2_proxy_auth_accepts_proxy_redirect(self) -> None:
        unit = UnitDefinition(
            unit_id="redisinsight",
            display_name="RedisInsight",
            description="Redis 可视化管理",
            entry_url="http://127.0.0.1:4180",
            compose_scope="main",
            start_services=("redis", "redisinsight", "oauth2-proxy-redisinsight"),
            stop_services=("redisinsight", "oauth2-proxy-redisinsight"),
            shared_dependencies=("redis",),
            auth_mode="oauth2_proxy_redirect",
            auth_path="/oauth2/",
            auth_expectation="required",
        )
        client = FakeProbeClient(
            {
                "http://127.0.0.1:4180": HttpResponse(
                    status=302,
                    headers={"Location": "/oauth2/start?rd=%2F"},
                    body="",
                )
            }
        )

        result = probe_auth(unit, client, harbor_installed=True)

        self.assertEqual(result.level, "ok")

    def test_harbor_auth_returns_not_installed_when_installer_missing(self) -> None:
        unit = UnitDefinition(
            unit_id="harbor",
            display_name="Harbor",
            description="镜像仓库与安全扫描",
            entry_url="http://127.0.0.1:8088",
            compose_scope="harbor",
            start_services=(),
            stop_services=(),
            shared_dependencies=(),
            auth_mode="harbor_oidc",
            auth_path="/c/oidc/login",
            auth_expectation="best_effort",
        )
        client = FakeProbeClient({})

        result = probe_auth(unit, client, harbor_installed=False)

        self.assertEqual(result, ProbeResult.not_installed("Harbor installer 缺失"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests/test_probes.py -v`  
Expected: `ImportError: cannot import name 'HttpResponse'`

- [ ] **Step 3: 实现 HTTP 响应模型与认证探测函数**

```python
# business_panel/probes.py
from dataclasses import dataclass
from urllib import error, request

from business_panel.catalog import UnitDefinition
from business_panel.models import ProbeResult


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: str


class ProbeClient:
    def fetch(self, url: str, *, follow_redirects: bool = False) -> HttpResponse:
        if follow_redirects:
            opener = request.build_opener()
        else:
            class NoRedirectHandler(request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None

            opener = request.build_opener(NoRedirectHandler)
        req = request.Request(url, method="GET")
        try:
            with opener.open(req, timeout=5) as response:
                return HttpResponse(
                    status=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read().decode("utf-8", errors="ignore"),
                )
        except error.HTTPError as exc:
            return HttpResponse(
                status=exc.code,
                headers=dict(exc.headers.items()),
                body=exc.read().decode("utf-8", errors="ignore"),
            )


def probe_endpoint(unit: UnitDefinition, client: ProbeClient, *, harbor_installed: bool) -> ProbeResult:
    if unit.unit_id == "harbor" and not harbor_installed:
        return ProbeResult.not_installed("Harbor installer 缺失")
    target = f"{unit.entry_url}/api/v2.0/ping" if unit.unit_id == "harbor" else unit.entry_url
    response = client.fetch(target, follow_redirects=True)
    if response.status >= 500:
        return ProbeResult.fail(f"入口返回 {response.status}")
    if response.status >= 400:
        return ProbeResult.warn(f"入口返回 {response.status}")
    return ProbeResult.ok("入口可达")


def probe_auth(unit: UnitDefinition, client: ProbeClient, *, harbor_installed: bool) -> ProbeResult:
    if unit.auth_expectation == "not_checked":
        return ProbeResult.warn("首版未做端到端认证检查")
    if unit.unit_id == "harbor" and not harbor_installed:
        return ProbeResult.not_installed("Harbor installer 缺失")

    response = client.fetch(unit.entry_url, follow_redirects=False)
    location = response.headers.get("Location", "")

    if unit.auth_mode == "metadata":
        metadata_url = f"{unit.entry_url}{unit.auth_path}"
        metadata = client.fetch(metadata_url, follow_redirects=True)
        return (
            ProbeResult.ok("OIDC 元数据正常")
            if metadata.status == 200 and "authorization_endpoint" in metadata.body
            else ProbeResult.fail("OIDC 元数据不可用")
        )

    if unit.auth_mode == "oidc_redirect":
        return (
            ProbeResult.ok("已跳转到 Keycloak")
            if unit.auth_path in location
            else ProbeResult.fail("未跳转到 Keycloak")
        )

    if unit.auth_mode == "oauth2_proxy_redirect":
        return (
            ProbeResult.ok("已进入 oauth2-proxy 登录流程")
            if unit.auth_path in location or "openid-connect/auth" in location
            else ProbeResult.fail("未进入 oauth2-proxy 登录流程")
        )

    if unit.auth_mode == "harbor_oidc":
        full = client.fetch(unit.entry_url, follow_redirects=True)
        return (
            ProbeResult.ok("检测到 Harbor OIDC 入口")
            if unit.auth_path in full.body or "OIDC" in full.body
            else ProbeResult.warn("未发现 Harbor OIDC 入口")
        )

    return ProbeResult.warn("未定义认证检查")
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `python3 -m unittest tests/test_probes.py -v`  
Expected: `OK`

- [ ] **Step 5: 回归已完成任务**

Run: `python3 -m unittest tests/test_config_catalog.py tests/test_status_service.py tests/test_control.py tests/test_probes.py -v`  
Expected: `OK`

### Task 5: 组装状态服务、HTTP API 与静态页面

**Files:**
- Modify: `business_panel/probes.py`
- Modify: `business_panel/status_service.py`
- Create: `business_panel/server.py`
- Create: `business_panel/main.py`
- Create: `business_panel/static/index.html`
- Create: `business_panel/static/app.css`
- Create: `business_panel/static/app.js`
- Create: `tests/test_server.py`

- [ ] **Step 1: 写失败测试，固定 `/api/status`、`/api/control` 和首页输出**

```python
import json
import threading
import unittest
from http.client import HTTPConnection

from business_panel.server import make_server


class FakeApp:
    def __init__(self) -> None:
        self.actions = []

    def get_status_payload(self) -> dict:
        return {
            "refreshed_at": "2026-04-16T00:00:00+00:00",
            "totals": {"healthy": 1, "degraded": 0, "failed": 0, "not_installed": 0, "total": 1},
            "units": [
                {
                    "unit_id": "keycloak",
                    "display_name": "Keycloak",
                    "description": "统一认证中心",
                    "entry_url": "http://127.0.0.1:8080",
                    "overall_state": "healthy",
                    "failure_summary": "状态正常",
                    "container": {"level": "ok", "summary": "容器运行"},
                    "endpoint": {"level": "ok", "summary": "入口可达"},
                    "auth": {"level": "ok", "summary": "OIDC 元数据正常"},
                    "available_actions": ["start", "stop", "restart"],
                }
            ],
        }

    def run_action(self, unit_id: str, action: str) -> dict:
        self.actions.append((unit_id, action))
        return {"ok": True, "unit_id": unit_id, "action": action}


class ServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FakeApp()
        self.server = make_server("127.0.0.1", 0, self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)

    def test_status_endpoint_returns_json(self) -> None:
        conn = HTTPConnection("127.0.0.1", self.port)
        conn.request("GET", "/api/status")
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["totals"]["healthy"], 1)

    def test_control_endpoint_passes_action(self) -> None:
        conn = HTTPConnection("127.0.0.1", self.port)
        conn.request(
            "POST",
            "/api/control",
            body=json.dumps({"unit_id": "all", "action": "restart"}),
            headers={"Content-Type": "application/json"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["action"], "restart")
        self.assertEqual(self.app.actions, [("all", "restart")])

    def test_root_serves_panel_html(self) -> None:
        conn = HTTPConnection("127.0.0.1", self.port)
        conn.request("GET", "/")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("统一业务面板", body)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试并确认当前失败**

Run: `python3 -m unittest tests/test_server.py -v`  
Expected: `ImportError: cannot import name 'make_server'`

- [ ] **Step 3: 在状态服务里接入真实探测与控制调度**

```python
# business_panel/status_service.py
from pathlib import Path
import subprocess

from business_panel.catalog import build_units
from business_panel.config import PanelSettings
from business_panel.control import ControlService
from business_panel.models import ProbeResult, UnitSnapshot
from business_panel.probes import ProbeClient, probe_auth, probe_endpoint

# 保留 Task 2 中已实现的 summarize_panel / summarize_unit 定义


def _run_compose_ps(settings: PanelSettings, scope: str) -> set[str]:
    if scope == "harbor":
        installer_dir = settings.root_dir / "harbor" / "installer"
        if not installer_dir.exists():
            return set()
        command = ["docker", "compose", "ps", "--format", "json"]
        cwd = installer_dir
    else:
        command = [
            "docker",
            "compose",
            "--env-file",
            str(settings.root_dir / ".env"),
            "-f",
            str(settings.root_dir / "compose.yml"),
            "ps",
            "--format",
            "json",
        ]
        cwd = settings.root_dir
    completed = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return set()
    return {
        item["Service"]
        for item in __import__("json").loads(completed.stdout or "[]")
        if item.get("State") == "running"
    }


class PanelApplication:
    def __init__(self, settings: PanelSettings) -> None:
        self.settings = settings
        self.units = {unit.unit_id: unit for unit in build_units(settings)}
        self.control = ControlService(settings, self.units)
        self.client = ProbeClient()

    def get_status_payload(self) -> dict:
        harbor_installed = (self.settings.root_dir / "harbor" / "installer").exists()
        running_main = _run_compose_ps(self.settings, "main")
        running_harbor = _run_compose_ps(self.settings, "harbor")
        snapshots = []
        for unit in self.units.values():
            if unit.compose_scope == "harbor" and not harbor_installed:
                snapshots.append(
                    UnitSnapshot(
                        unit_id=unit.unit_id,
                        display_name=unit.display_name,
                        description=unit.description,
                        entry_url=unit.entry_url,
                        auth_expectation=unit.auth_expectation,
                        container=ProbeResult.not_installed("Harbor installer 缺失"),
                        endpoint=ProbeResult.not_installed("Harbor installer 缺失"),
                        auth=ProbeResult.not_installed("Harbor installer 缺失"),
                        available_actions=("start", "stop", "restart"),
                    )
                )
                continue
            running = running_harbor if unit.compose_scope == "harbor" else running_main
            probe_services = unit.start_services or unit.stop_services
            if unit.compose_scope == "harbor":
                container = (
                    ProbeResult.ok("Harbor compose 已启动")
                    if running_harbor
                    else ProbeResult.fail("Harbor compose 未运行")
                )
            else:
                container = (
                    ProbeResult.ok("容器运行")
                    if all(service in running for service in probe_services)
                    else ProbeResult.fail("存在未运行服务")
                )
            snapshots.append(
                UnitSnapshot(
                    unit_id=unit.unit_id,
                    display_name=unit.display_name,
                    description=unit.description,
                    entry_url=unit.entry_url,
                    auth_expectation=unit.auth_expectation,
                    container=container,
                    endpoint=probe_endpoint(unit, self.client, harbor_installed=harbor_installed),
                    auth=probe_auth(unit, self.client, harbor_installed=harbor_installed),
                    available_actions=("start", "stop", "restart"),
                )
            )
        return summarize_panel(snapshots)

    def run_action(self, unit_id: str, action: str) -> dict:
        lock = self.control.acquire_lock()
        try:
            command = self.control.build_command(unit_id, action)
            completed = subprocess.run(
                command.argv,
                cwd=command.cwd,
                check=False,
                capture_output=True,
                text=True,
            )
        finally:
            lock.release()
        return {
            "ok": completed.returncode == 0,
            "unit_id": unit_id,
            "action": action,
            "stdout": completed.stdout[-600:],
            "stderr": completed.stderr[-600:],
        }
```

- [ ] **Step 4: 实现 HTTP 路由和前端静态页面**

```python
# business_panel/server.py
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


STATIC_DIR = Path(__file__).resolve().parent / "static"


def make_server(host: str, port: int, app):
    class PanelHandler(BaseHTTPRequestHandler):
        def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path: Path, content_type: str) -> None:
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/api/status":
                self._send_json(app.get_status_payload())
                return
            if self.path in {"/", "/index.html"}:
                self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
                return
            if self.path == "/app.css":
                self._send_file(STATIC_DIR / "app.css", "text/css; charset=utf-8")
                return
            if self.path == "/app.js":
                self._send_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if self.path != "/api/control":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            self._send_json(app.run_action(payload["unit_id"], payload["action"]))

        def log_message(self, format: str, *args) -> None:
            return

    return ThreadingHTTPServer((host, port), PanelHandler)
```

```python
# business_panel/main.py
from pathlib import Path

from business_panel.config import load_settings
from business_panel.server import make_server
from business_panel.status_service import PanelApplication


def main() -> None:
    root_dir = Path(__file__).resolve().parent.parent
    settings = load_settings(root_dir)
    app = PanelApplication(settings)
    server = make_server(settings.panel_host, settings.panel_port, app)
    print(f"Business panel listening on http://{settings.panel_host}:{settings.panel_port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
```

```html
<!-- business_panel/static/index.html -->
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>统一业务面板</title>
    <link rel="stylesheet" href="/app.css" />
  </head>
  <body>
    <main class="shell">
      <section class="hero">
        <div>
          <p class="eyebrow">Integration Console</p>
          <h1>统一业务面板</h1>
          <p class="summary">直达各业务页，集中看状态，并在同一页做受控启停。</p>
        </div>
        <div class="global-actions">
          <button data-action="start" data-unit="all">Start All</button>
          <button data-action="restart" data-unit="all">Restart All</button>
          <button data-action="stop" data-unit="all" class="danger">Stop All</button>
        </div>
      </section>
      <section id="totals" class="totals"></section>
      <section id="cards" class="cards"></section>
    </main>
    <script src="/app.js"></script>
  </body>
</html>
```

```css
/* business_panel/static/app.css */
:root {
  --bg: #f4efe6;
  --panel: rgba(255, 252, 246, 0.94);
  --ink: #1f2a2b;
  --muted: #5f6b67;
  --healthy: #2f855a;
  --degraded: #c67b1d;
  --failed: #c53030;
  --not-installed: #6b7280;
}

body {
  margin: 0;
  font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
  color: var(--ink);
  background:
    radial-gradient(circle at top left, rgba(210, 181, 142, 0.22), transparent 32%),
    linear-gradient(135deg, #f4efe6, #e3e9df);
}

.shell {
  max-width: 1180px;
  margin: 0 auto;
  padding: 32px 20px 56px;
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}

.card {
  background: var(--panel);
  border: 1px solid rgba(31, 42, 43, 0.08);
  border-radius: 20px;
  padding: 18px;
  box-shadow: 0 12px 32px rgba(31, 42, 43, 0.08);
}

.status-healthy { color: var(--healthy); }
.status-degraded { color: var(--degraded); }
.status-failed { color: var(--failed); }
.status-not_installed { color: var(--not-installed); }
```

```javascript
// business_panel/static/app.js
const totalsEl = document.querySelector("#totals");
const cardsEl = document.querySelector("#cards");

async function loadStatus() {
  const response = await fetch("/api/status");
  const payload = await response.json();
  renderTotals(payload);
  renderCards(payload.units);
}

function renderTotals(payload) {
  totalsEl.innerHTML = `
    <article class="card">
      <strong>${payload.totals.total}</strong>
      <span>业务总数</span>
    </article>
    <article class="card">
      <strong>${payload.totals.healthy}</strong>
      <span>正常</span>
    </article>
    <article class="card">
      <strong>${payload.totals.degraded}</strong>
      <span>部分异常</span>
    </article>
    <article class="card">
      <strong>${payload.totals.failed}</strong>
      <span>异常</span>
    </article>
  `;
}

function renderCards(units) {
  cardsEl.innerHTML = units
    .map(
      (unit) => `
        <article class="card">
          <div class="card-top">
            <div>
              <h2>${unit.display_name}</h2>
              <p>${unit.description}</p>
            </div>
            <span class="status-${unit.overall_state}">${unit.overall_state}</span>
          </div>
          <p>${unit.failure_summary}</p>
          <ul>
            <li>容器：${unit.container.summary}</li>
            <li>入口：${unit.endpoint.summary}</li>
            <li>认证：${unit.auth.summary}</li>
          </ul>
          <div class="actions">
            <a href="${unit.entry_url}" target="_blank" rel="noreferrer">打开</a>
            ${unit.available_actions
              .map(
                (action) => `<button data-unit="${unit.unit_id}" data-action="${action}">${action}</button>`
              )
              .join("")}
          </div>
        </article>
      `
    )
    .join("");
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const { unit, action } = button.dataset;
  const ok = window.confirm(`确认执行 ${unit} / ${action} ?`);
  if (!ok) return;
  button.disabled = true;
  try {
    await fetch("/api/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ unit_id: unit, action }),
    });
    await loadStatus();
  } finally {
    button.disabled = false;
  }
});

loadStatus();
window.setInterval(loadStatus, 15000);
```

- [ ] **Step 5: 运行 API/页面测试与核心回归**

Run: `python3 -m unittest tests/test_server.py -v && python3 -m unittest discover -s tests -v`  
Expected: `OK`

### Task 6: 补齐文档与人工验收路径

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `scripts/panel.sh`

- [ ] **Step 1: 在 README 增加业务面板章节**

````md
## 统一业务面板

启动：

```bash
./scripts/panel.sh start
```

访问：

```text
http://BUSINESS_PANEL_HOST:BUSINESS_PANEL_PORT
```

首版能力：

- 直达 Keycloak、Portainer、KafkaUI、RedisInsight、phpMyAdmin、mongo-express、Harbor
- 展示容器、入口、认证三层状态
- 支持全栈和业务单元级 `start / stop / restart`

限制：

- Portainer 首版不做稳定端到端认证检查
- Harbor OIDC 仅做页面级证据检查，不读取后台配置
````

- [ ] **Step 2: 跑全量单测与脚本语法检查**

Run: `python3 -m unittest discover -s tests -v && bash -n scripts/*.sh`  
Expected: 所有单测 `OK`，shell 语法检查无输出

- [ ] **Step 3: 启动面板并验证 `/api/status`**

Run: `./scripts/panel.sh start && curl -s http://127.0.0.1:8090/api/status | python3 -m json.tool | sed -n '1,40p'`  
Expected: 返回包含 `totals`、`units`、`refreshed_at` 的 JSON

- [ ] **Step 4: 验证页面可访问并停止面板**

Run: `curl -I http://127.0.0.1:8090/ && ./scripts/panel.sh stop && ./scripts/panel.sh status`  
Expected: 首页返回 `HTTP/1.0 200 OK` 或 `HTTP/1.1 200 OK`；停止后输出 `panel 未运行`

- [ ] **Step 5: 人工验收**

Run:

```bash
./scripts/services.sh status
./scripts/panel.sh start
```

Expected:

- 浏览器打开 `http://127.0.0.1:8090`
- 首页能看到全部业务卡片
- 点击 `打开` 能直达业务页
- 点击业务卡片或顶部按钮时，会弹确认框
- 某服务停掉后，卡片状态会在下一轮刷新里变成 `部分异常` 或 `异常`

## Self-Review

- 设计稿第 5 节页面结构：由 Task 5 的静态页面和 API 返回覆盖
- 设计稿第 6 节业务单元定义：由 Task 1 的 `build_units` 和 Task 3 的控制映射覆盖
- 设计稿第 7 节状态模型：由 Task 2 和 Task 4 覆盖
- 设计稿第 8 节控制模型：由 Task 3 和 Task 5 的 `/api/control` 覆盖
- 设计稿第 9-12 节技术路线、数据流、错误处理、验收：由 Task 5 和 Task 6 覆盖
- 占位词扫描要求已满足；计划中没有未完成占位词描述
