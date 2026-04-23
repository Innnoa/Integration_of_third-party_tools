import importlib.util
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


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

    def test_configure_portainer_oauth_initializes_admin_when_login_fails(self) -> None:
        helper = load_install_helper()
        requests: list[tuple[str, str, bytes | None]] = []

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

        def fake_urlopen(request, timeout=10):
            requests.append((request.method, request.full_url, request.data))
            auth_calls = [entry for entry in requests if entry[1].endswith("/api/auth")]
            if request.full_url.endswith("/api/auth") and len(auth_calls) == 1:
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
        put_payload = requests[-1][2].decode("utf-8") if requests[-1][2] else ""
        self.assertIn('"AuthenticationMethod": 3', put_payload)
        self.assertIn('"ClientID": "portainer"', put_payload)

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

    def test_configure_portainer_cli_includes_required_oidc_defaults(self) -> None:
        helper = load_install_helper()

        argv = [
            "install_helper.py",
            "configure-portainer",
            "--base-url",
            "http://127.0.0.1",
            "--host-header",
            "portainer.dev.example",
            "--admin-user",
            "admin",
            "--admin-password",
            "StrongPassword_123",
            "--client-id",
            "portainer",
            "--client-secret",
            "portainer-secret",
            "--auth-url",
            "http://auth.dev.example/realms/infra/protocol/openid-connect/auth",
            "--token-url",
            "http://auth.dev.example/realms/infra/protocol/openid-connect/token",
            "--resource-url",
            "http://auth.dev.example/realms/infra/protocol/openid-connect/userinfo",
            "--logout-url",
            "http://auth.dev.example/realms/infra/protocol/openid-connect/logout",
            "--redirect-url",
            "http://portainer.dev.example/",
        ]

        with (
            patch.object(sys, "argv", argv),
            patch.object(helper, "configure_portainer_oauth") as configure_mock,
        ):
            helper.main()

        oauth_settings = configure_mock.call_args.kwargs["oauth_settings"]
        self.assertEqual(oauth_settings["UserIdentifier"], "preferred_username")
        self.assertEqual(oauth_settings["Scopes"], "openid profile email groups")
        self.assertIs(oauth_settings["OAuthAutoCreateUsers"], True)

    def test_render_nightingale_config_uses_env_values(self) -> None:
        helper = load_install_helper()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_path = root / ".env"
            output_path = root / "config.toml"
            env_path.write_text(
                "PUBLIC_SCHEME=https\n"
                "KEYCLOAK_PUBLIC_HOST=auth.dev.example\n"
                "KEYCLOAK_REALM=infra\n"
                "NIGHTINGALE_PUBLIC_HOST=nightingale.dev.example\n"
                "NIGHTINGALE_DB_PASSWORD=db-secret\n"
                "NIGHTINGALE_REDIS_PASSWORD=redis-secret\n"
                "NIGHTINGALE_CLIENT_SECRET=oidc-secret\n",
                encoding="utf-8",
            )

            helper.render_nightingale_config(env_path, output_path)

            config = output_path.read_text(encoding="utf-8")

        self.assertIn(
            'DSN = "nightingale:db-secret@tcp(nightingale-mysql:3306)/nightingale?charset=utf8mb4&parseTime=True&loc=Local"',
            config,
        )
        self.assertIn('Password = "redis-secret"', config)
        self.assertIn('RedirectURL = "https://nightingale.dev.example/callback"', config)
        self.assertIn(
            'SsoAddr = "https://auth.dev.example/realms/infra/protocol/openid-connect/auth"',
            config,
        )
        self.assertIn('ClientSecret = "oidc-secret"', config)
