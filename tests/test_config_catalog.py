import tempfile
import unittest
from pathlib import Path

from business_panel.catalog import build_units
from business_panel.config import load_settings


class ConfigCatalogTest(unittest.TestCase):
    def _write_env(self, root: Path, lines: list[str]) -> None:
        (root / ".env").write_text("\n".join(lines), encoding="utf-8")

    def _base_env_lines(self) -> list[str]:
        return [
            "PUBLIC_SCHEME=http",
            "PUBLIC_HOST=127.0.0.1",
            "BROWSER_HOST=localhost",
            "KEYCLOAK_PUBLIC_HOST=auth.localhost",
            "PORTAINER_PUBLIC_HOST=portainer.localhost",
            "KAFKA_UI_PUBLIC_HOST=kafka.localhost",
            "REDISINSIGHT_PUBLIC_HOST=redis.localhost",
            "PHPMYADMIN_PUBLIC_HOST=pma.localhost",
            "MONGO_EXPRESS_PUBLIC_HOST=mongo.localhost",
            "HARBOR_PUBLIC_HOST=harbor.localhost",
            "KEYCLOAK_REALM=infra",
            "KEYCLOAK_PORT=8080",
            "PORTAINER_PORT=19000",
            "KAFKA_UI_PORT=8082",
            "REDISINSIGHT_PROXY_PORT=4180",
            "PHPMYADMIN_PROXY_PORT=4181",
            "MONGO_EXPRESS_PROXY_PORT=4182",
            "HARBOR_PORT=8088",
        ]

    def test_load_settings_maps_required_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_env(
                root,
                self._base_env_lines()
                + [
                    "BUSINESS_PANEL_HOST=127.0.0.1",
                    "BUSINESS_PANEL_PORT=8090",
                    "BUSINESS_PANEL_REFRESH_INTERVAL=15",
                ],
            )

            settings = load_settings(root)

        self.assertEqual(settings.root_dir, root)
        self.assertEqual(settings.keycloak_public_host, "auth.localhost")
        self.assertEqual(settings.panel_port, 8090)
        self.assertEqual(settings.refresh_interval, 15)
        self.assertEqual(settings.redisinsight_port, 4180)
        self.assertEqual(settings.phpmyadmin_port, 4181)
        self.assertEqual(settings.mongo_express_port, 4182)

    def test_build_units_keycloak_definition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_env(root, self._base_env_lines())
            settings = load_settings(root)
            units = {unit.unit_id: unit for unit in build_units(settings)}

        self.assertEqual(units["keycloak"].entry_url, "http://auth.localhost")
        self.assertEqual(
            units["keycloak"].open_url,
            "http://auth.localhost/realms/infra/account/",
        )
        self.assertEqual(
            units["keycloak"].start_services,
            ("keycloak-postgres", "keycloak"),
        )
        self.assertEqual(
            units["keycloak"].stop_services,
            ("keycloak", "keycloak-postgres"),
        )
        self.assertEqual(units["keycloak"].shared_dependencies, ())
        self.assertEqual(units["keycloak"].auth_mode, "metadata")
        self.assertEqual(
            units["keycloak"].auth_path,
            "/realms/infra/.well-known/openid-configuration",
        )
        self.assertEqual(units["keycloak"].auth_expectation, "required")

    def test_build_units_auth_modes_and_harbor_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_env(root, self._base_env_lines())
            settings = load_settings(root)
            units = {unit.unit_id: unit for unit in build_units(settings)}

        self.assertEqual(units["portainer"].entry_url, "http://portainer.localhost")
        self.assertIsNone(units["portainer"].open_url)
        self.assertEqual(units["kafka_ui"].entry_url, "http://kafka.localhost")
        self.assertEqual(units["redisinsight"].entry_url, "http://redis.localhost")
        self.assertEqual(units["phpmyadmin"].entry_url, "http://pma.localhost")
        self.assertEqual(units["mongo_express"].entry_url, "http://mongo.localhost")
        self.assertEqual(units["harbor"].entry_url, "http://harbor.localhost")
        self.assertEqual(units["portainer"].auth_mode, "not_checked")
        self.assertEqual(units["portainer"].auth_path, "")
        self.assertEqual(units["portainer"].auth_expectation, "not_checked")
        self.assertEqual(
            units["kafka_ui"].stop_services,
            ("kafka-ui", "kafka"),
        )
        self.assertEqual(units["kafka_ui"].shared_dependencies, ())
        self.assertEqual(units["kafka_ui"].auth_mode, "oidc_redirect")
        self.assertEqual(units["kafka_ui"].auth_path, "openid-connect/auth")
        self.assertEqual(units["kafka_ui"].auth_expectation, "required")
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
        self.assertEqual(units["redisinsight"].auth_mode, "oauth2_proxy_redirect")
        self.assertEqual(units["redisinsight"].auth_path, "/oauth2/")
        self.assertEqual(units["redisinsight"].auth_expectation, "required")
        self.assertEqual(units["phpmyadmin"].auth_mode, "oauth2_proxy_redirect")
        self.assertEqual(units["phpmyadmin"].auth_path, "/oauth2/")
        self.assertEqual(units["phpmyadmin"].auth_expectation, "required")
        self.assertEqual(
            units["mongo_express"].start_services,
            ("mongodb", "mongo-express", "oauth2-proxy-mongo-express"),
        )
        self.assertEqual(units["mongo_express"].auth_mode, "oauth2_proxy_redirect")
        self.assertEqual(units["mongo_express"].auth_path, "/oauth2/")
        self.assertEqual(units["mongo_express"].auth_expectation, "required")
        self.assertEqual(units["harbor"].compose_scope, "harbor")
        self.assertEqual(units["harbor"].start_services, ())
        self.assertEqual(units["harbor"].stop_services, ())
        self.assertEqual(units["harbor"].auth_mode, "harbor_oidc")
        self.assertEqual(units["harbor"].auth_path, "/c/oidc/login")
        self.assertEqual(units["harbor"].auth_expectation, "best_effort")

    def test_build_units_includes_nacos_and_nightingale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_env(
                root,
                self._base_env_lines()
                + [
                    "NACOS_PUBLIC_HOST=nacos.custom.local",
                    "NIGHTINGALE_PUBLIC_HOST=nightingale.custom.local",
                ],
            )
            settings = load_settings(root)
            units = {unit.unit_id: unit for unit in build_units(settings)}

        self.assertEqual(settings.nacos_public_host, "nacos.custom.local")
        self.assertEqual(settings.nightingale_public_host, "nightingale.custom.local")
        self.assertEqual(units["nacos"].entry_url, "http://nacos.custom.local")
        self.assertEqual(units["nightingale"].entry_url, "http://nightingale.custom.local")
        self.assertIsNone(units["nacos"].open_url)
        self.assertEqual(
            units["nightingale"].open_url,
            "http://nightingale.custom.local/login?redirect=%2F",
        )
        self.assertEqual(units["nacos"].compose_scope, "main")
        self.assertEqual(units["nightingale"].compose_scope, "main")
        self.assertEqual(units["nacos"].start_services, ("nacos", "nacos-mysql", "oauth2-proxy-nacos"))
        self.assertEqual(units["nacos"].stop_services, ("nacos", "nacos-mysql", "oauth2-proxy-nacos"))
        self.assertEqual(
            units["nightingale"].start_services,
            ("nightingale", "nightingale-mysql", "nightingale-redis"),
        )
        self.assertEqual(
            units["nightingale"].stop_services,
            ("nightingale", "nightingale-mysql", "nightingale-redis"),
        )
        self.assertEqual(units["nacos"].auth_mode, "oauth2_proxy_redirect")
        self.assertEqual(units["nightingale"].auth_mode, "oidc_redirect")
        self.assertEqual(units["nacos"].auth_path, "/oauth2/")
        self.assertEqual(units["nightingale"].auth_path, "openid-connect/auth")
        self.assertEqual(units["nacos"].auth_expectation, "required")
        self.assertEqual(units["nightingale"].auth_expectation, "required")

    def test_load_settings_uses_business_panel_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_env(root, self._base_env_lines())

            settings = load_settings(root)

        self.assertEqual(settings.panel_host, "127.0.0.1")
        self.assertEqual(settings.panel_port, 8090)
        self.assertEqual(settings.refresh_interval, 15)

    def test_load_settings_empty_business_panel_host_uses_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_env(
                root,
                self._base_env_lines()
                + [
                    "BUSINESS_PANEL_HOST=",
                    "BUSINESS_PANEL_PORT=8090",
                    "BUSINESS_PANEL_REFRESH_INTERVAL=15",
                ],
            )

            settings = load_settings(root)

        self.assertEqual(settings.panel_host, "127.0.0.1")

    def test_load_settings_rejects_malformed_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_env(root, self._base_env_lines() + ["MALFORMED_LINE"])

            with self.assertRaisesRegex(ValueError, "malformed"):
                load_settings(root)

    def test_load_settings_reports_missing_required_setting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lines = [line for line in self._base_env_lines() if not line.startswith("PUBLIC_HOST=")]
            self._write_env(root, lines)

            with self.assertRaisesRegex(ValueError, "PUBLIC_HOST"):
                load_settings(root)

    def test_load_settings_rejects_invalid_optional_int_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_env(
                root,
                self._base_env_lines()
                + [
                    "BUSINESS_PANEL_PORT=abc",
                    "BUSINESS_PANEL_REFRESH_INTERVAL=15",
                ],
            )
            with self.assertRaisesRegex(ValueError, "BUSINESS_PANEL_PORT"):
                load_settings(root)

            self._write_env(
                root,
                self._base_env_lines()
                + [
                    "BUSINESS_PANEL_PORT=8090",
                    "BUSINESS_PANEL_REFRESH_INTERVAL=abc",
                ],
            )
            with self.assertRaisesRegex(ValueError, "BUSINESS_PANEL_REFRESH_INTERVAL"):
                load_settings(root)


if __name__ == "__main__":
    unittest.main()
