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
        self.harbor_unit = UnitDefinition(
            unit_id="harbor",
            display_name="Harbor",
            description="镜像仓库",
            entry_url="http://127.0.0.1:8088",
            compose_scope="harbor",
            start_services=(),
            stop_services=(),
            shared_dependencies=(),
            auth_mode="harbor_oidc",
            auth_path="/c/oidc/login",
            auth_expectation="best_effort",
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
        self.assertEqual(command.cwd, self.settings.root_dir)

    def test_all_restart_uses_services_script(self) -> None:
        service = ControlService(self.settings, {"redisinsight": self.unit})
        command = service.build_command("all", "restart")
        self.assertEqual(
            command.argv,
            [str(self.settings.root_dir / "scripts" / "services.sh"), "restart"],
        )
        self.assertEqual(command.cwd, self.settings.root_dir)

    def test_harbor_start_uses_harbor_compose_in_installer_cwd(self) -> None:
        service = ControlService(self.settings, {"harbor": self.harbor_unit})
        command = service.build_command("harbor", "start")
        self.assertEqual(command.argv, ["docker", "compose", "up", "-d"])
        self.assertEqual(command.cwd, self.settings.root_dir / "harbor" / "installer")

    def test_invalid_action_is_rejected(self) -> None:
        service = ControlService(self.settings, {"redisinsight": self.unit})
        with self.assertRaisesRegex(ValueError, "unsupported action"):
            service.build_command("redisinsight", "status")

    def test_invalid_unit_id_is_rejected(self) -> None:
        service = ControlService(self.settings, {"redisinsight": self.unit})
        with self.assertRaisesRegex(ValueError, "unknown unit_id"):
            service.build_command("missing", "start")

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
