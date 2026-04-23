import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from business_panel.catalog import UnitDefinition
from business_panel.config import PanelSettings
from business_panel.control import PanelBusyError
from business_panel.models import ProbeResult
from business_panel.server import dispatch_request
from business_panel.status_service import PanelApplication, _run_compose_ps


class FakeApp:
    def __init__(self) -> None:
        self.actions = []
        self.status_error: Exception | None = None
        self.action_error: Exception | None = None

    def get_status_payload(self) -> dict:
        if self.status_error is not None:
            raise self.status_error
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
        if self.action_error is not None:
            raise self.action_error
        self.actions.append((unit_id, action))
        return {"ok": True, "unit_id": unit_id, "action": action}


class ServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FakeApp()

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], str]:
        response = dispatch_request(
            self.app,
            method=method,
            path=path,
            headers=headers or {},
            body=(body or "").encode("utf-8"),
        )
        payload = response.body.decode("utf-8")
        return response.status, dict(response.headers), payload

    def test_status_endpoint_returns_json(self) -> None:
        status, _, body = self._request("GET", "/api/status")
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["totals"]["healthy"], 1)

    def test_control_endpoint_passes_action(self) -> None:
        status, _, body = self._request(
            "POST",
            "/api/control",
            body=json.dumps({"unit_id": "all", "action": "restart"}),
            headers={"Content-Type": "application/json"},
        )
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["action"], "restart")
        self.assertEqual(self.app.actions, [("all", "restart")])

    def test_root_serves_panel_html(self) -> None:
        status, _, body = self._request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("统一业务面板", body)

    def test_root_head_returns_ok(self) -> None:
        status, headers, body = self._request("HEAD", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertEqual(body, "")

    def test_static_assets_are_served(self) -> None:
        css_status, css_headers, css_body = self._request("GET", "/app.css")
        js_status, js_headers, js_body = self._request("GET", "/app.js")

        self.assertEqual(css_status, 200)
        self.assertIn("text/css", css_headers["Content-Type"])
        self.assertIn("--bg", css_body)
        self.assertEqual(js_status, 200)
        self.assertIn("application/javascript", js_headers["Content-Type"])
        self.assertIn("loadStatus", js_body)

    def test_unknown_route_returns_404(self) -> None:
        status, _, _ = self._request("GET", "/missing")
        self.assertEqual(status, 404)

    def test_control_endpoint_rejects_invalid_json(self) -> None:
        status, headers, body = self._request(
            "POST",
            "/api/control",
            body="{bad json",
            headers={"Content-Type": "application/json"},
        )

        payload = json.loads(body)
        self.assertEqual(status, 400)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(payload["ok"], False)
        self.assertIn("JSON", payload["error"])

    def test_control_endpoint_rejects_missing_keys(self) -> None:
        status, _, body = self._request(
            "POST",
            "/api/control",
            body=json.dumps({"unit_id": "all"}),
            headers={"Content-Type": "application/json"},
        )

        payload = json.loads(body)
        self.assertEqual(status, 400)
        self.assertEqual(payload["ok"], False)
        self.assertIn("action", payload["error"])

    def test_control_endpoint_maps_panel_busy_error(self) -> None:
        self.app.action_error = PanelBusyError("已有控制任务在执行")

        status, _, body = self._request(
            "POST",
            "/api/control",
            body=json.dumps({"unit_id": "all", "action": "restart"}),
            headers={"Content-Type": "application/json"},
        )

        payload = json.loads(body)
        self.assertEqual(status, 409)
        self.assertEqual(payload["ok"], False)
        self.assertIn("已有控制任务", payload["error"])

    def test_control_endpoint_maps_value_error(self) -> None:
        self.app.action_error = ValueError("unknown unit_id: missing")

        status, _, body = self._request(
            "POST",
            "/api/control",
            body=json.dumps({"unit_id": "missing", "action": "restart"}),
            headers={"Content-Type": "application/json"},
        )

        payload = json.loads(body)
        self.assertEqual(status, 400)
        self.assertEqual(payload["ok"], False)
        self.assertIn("unknown unit_id", payload["error"])

    def test_control_endpoint_maps_unexpected_error(self) -> None:
        self.app.action_error = RuntimeError("boom")

        status, _, body = self._request(
            "POST",
            "/api/control",
            body=json.dumps({"unit_id": "all", "action": "restart"}),
            headers={"Content-Type": "application/json"},
        )

        payload = json.loads(body)
        self.assertEqual(status, 500)
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["error"], "服务器内部错误")


class FakeLock:
    def __init__(self) -> None:
        self.released = False

    def release(self) -> None:
        self.released = True


class FakeControl:
    def __init__(self, lock: FakeLock) -> None:
        self.lock = lock

    def acquire_lock(self) -> FakeLock:
        return self.lock

    def build_command(self, unit_id: str, action: str):
        class _Command:
            argv = ["docker", "compose", "restart", unit_id]
            cwd = Path("/tmp")

        return _Command()


class PanelApplicationTest(unittest.TestCase):
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
            unit_id="keycloak",
            display_name="Keycloak",
            description="统一认证中心",
            entry_url="http://127.0.0.1:8080",
            compose_scope="main",
            start_services=("keycloak-postgres", "keycloak"),
            stop_services=("keycloak", "keycloak-postgres"),
            shared_dependencies=(),
            auth_mode="metadata",
            auth_path="/realms/infra/.well-known/openid-configuration",
            auth_expectation="required",
        )

    def test_run_compose_ps_timeout_returns_empty_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("", encoding="utf-8")
            (root / "compose.yml").write_text("services: {}", encoding="utf-8")
            settings = self.settings.__class__(**{**self.settings.__dict__, "root_dir": root})
            with patch(
                "business_panel.status_service.subprocess.run",
                side_effect=subprocess.TimeoutExpired(["docker", "compose"], timeout=5),
            ):
                result = _run_compose_ps(settings, "main")

        self.assertEqual(result, set())

    def test_run_compose_ps_parses_line_delimited_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("", encoding="utf-8")
            (root / "compose.yml").write_text("services: {}", encoding="utf-8")
            settings = self.settings.__class__(**{**self.settings.__dict__, "root_dir": root})
            stdout = "\n".join(
                [
                    json.dumps({"Service": "keycloak", "State": "running"}),
                    json.dumps({"Service": "redis", "State": "running"}),
                    json.dumps({"Service": "mariadb", "State": "exited"}),
                ]
            )
            with patch(
                "business_panel.status_service.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    args=["docker", "compose", "ps", "--format", "json"],
                    returncode=0,
                    stdout=stdout,
                    stderr="",
                ),
            ):
                result = _run_compose_ps(settings, "main")

        self.assertEqual(result, {"keycloak", "redis"})

    def test_status_payload_treats_compose_unavailable_as_failed_container(self) -> None:
        with patch("business_panel.status_service.build_units", return_value=(self.unit,)):
            app = PanelApplication(self.settings)

        with (
            patch(
                "business_panel.status_service._run_compose_ps",
                side_effect=[set(), set()],
            ),
            patch("business_panel.status_service.probe_endpoint", return_value=ProbeResult.ok("入口可达")),
            patch("business_panel.status_service.probe_auth", return_value=ProbeResult.ok("认证正常")),
        ):
            payload = app.get_status_payload()

        unit = payload["units"][0]
        self.assertEqual(unit["container"]["level"], "fail")
        self.assertEqual(unit["container"]["summary"], "存在未运行服务")

    def test_run_action_timeout_returns_ok_false_and_releases_lock(self) -> None:
        with patch("business_panel.status_service.build_units", return_value=(self.unit,)):
            app = PanelApplication(self.settings)

        lock = FakeLock()
        app.control = FakeControl(lock)

        with patch(
            "business_panel.status_service.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["docker", "compose"], timeout=5, output="partial", stderr="slow"),
        ):
            result = app.run_action("keycloak", "restart")

        self.assertEqual(result["ok"], False)
        self.assertIn("超时", result["stderr"])
        self.assertTrue(lock.released)

    def test_status_payload_skips_probes_when_container_is_already_failed(self) -> None:
        with patch("business_panel.status_service.build_units", return_value=(self.unit,)):
            app = PanelApplication(self.settings)

        with (
            patch("business_panel.status_service._run_compose_ps", side_effect=[set(), set()]),
            patch(
                "business_panel.status_service.probe_endpoint",
                return_value=ProbeResult.ok("不应调用"),
            ) as endpoint_probe,
            patch(
                "business_panel.status_service.probe_auth",
                return_value=ProbeResult.ok("不应调用"),
            ) as auth_probe,
        ):
            payload = app.get_status_payload()

        unit = payload["units"][0]
        self.assertEqual(unit["container"]["level"], "fail")
        self.assertEqual(unit["endpoint"]["level"], "warn")
        self.assertEqual(unit["endpoint"]["summary"], "存在未运行服务，跳过入口探测")
        self.assertEqual(unit["auth"]["level"], "warn")
        self.assertEqual(unit["auth"]["summary"], "存在未运行服务，跳过认证探测")
        endpoint_probe.assert_not_called()
        auth_probe.assert_not_called()

    def test_harbor_requires_proxy_service_to_count_as_running(self) -> None:
        harbor_unit = UnitDefinition(
            unit_id="harbor",
            display_name="Harbor",
            description="registry",
            entry_url="http://localhost:8088",
            compose_scope="harbor",
            start_services=(),
            stop_services=(),
            shared_dependencies=(),
            auth_mode="harbor_oidc",
            auth_path="/c/oidc/login",
            auth_expectation="best_effort",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "harbor" / "installer").mkdir(parents=True)
            settings = self.settings.__class__(**{**self.settings.__dict__, "root_dir": root})
            with patch("business_panel.status_service.build_units", return_value=(harbor_unit,)):
                app = PanelApplication(settings)

            with (
                patch("business_panel.status_service._run_compose_ps", side_effect=[set(), {"log"}]),
                patch(
                    "business_panel.status_service.probe_endpoint",
                    return_value=ProbeResult.ok("不应调用"),
                ) as endpoint_probe,
                patch(
                    "business_panel.status_service.probe_auth",
                    return_value=ProbeResult.ok("不应调用"),
                ) as auth_probe,
            ):
                payload = app.get_status_payload()

        unit = payload["units"][0]
        self.assertEqual(unit["container"]["level"], "fail")
        self.assertEqual(unit["container"]["summary"], "Harbor compose 未运行")
        self.assertEqual(unit["endpoint"]["summary"], "Harbor compose 未运行，跳过入口探测")
        self.assertEqual(unit["auth"]["summary"], "Harbor compose 未运行，跳过认证探测")
        endpoint_probe.assert_not_called()
        auth_probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
