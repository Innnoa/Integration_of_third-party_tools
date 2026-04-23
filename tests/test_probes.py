import io
import pathlib
import re
import tomllib
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import Mock, patch

from business_panel.catalog import UnitDefinition
from business_panel.models import ProbeResult
from business_panel.probes import HttpResponse, ProbeClient, probe_auth, probe_endpoint


def _parse_properties(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _parse_env(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _load_toml(path: str) -> dict:
    return tomllib.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _strip_shell_arg(raw_line: str) -> str:
    value = raw_line.strip()
    if value.endswith("\\"):
        value = value[:-1].rstrip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return value


def _parse_bootstrap_client_calls(script: str) -> dict[str, dict[str, str]]:
    lines = script.splitlines()
    calls: dict[str, dict[str, str]] = {}
    for index, line in enumerate(lines):
        if line.strip() != "create_or_update_client \\":
            continue
        client_id = _strip_shell_arg(lines[index + 1])
        calls[client_id] = {
            "secret": _strip_shell_arg(lines[index + 2]),
            "redirect_uris": _strip_shell_arg(lines[index + 3]),
            "web_origins": _strip_shell_arg(lines[index + 4]),
        }
    return calls


def _extract_shell_function(script: str, function_name: str) -> str:
    match = re.search(rf"{function_name}\(\) \{{\n(.*?)\n\}}", script, re.DOTALL)
    if match is None:
        raise AssertionError(f"missing shell function: {function_name}")
    return match.group(1)


class FakeProbeClient(ProbeClient):
    def __init__(self, responses: dict[str, HttpResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, bool]] = []

    def fetch(self, url: str, *, follow_redirects: bool = False) -> HttpResponse:
        self.calls.append((url, follow_redirects))
        return self.responses[url]


def _unit(
    *,
    unit_id: str,
    entry_url: str,
    auth_mode: str,
    auth_path: str,
    auth_expectation: str = "required",
    compose_scope: str = "main",
) -> UnitDefinition:
    return UnitDefinition(
        unit_id=unit_id,
        display_name=unit_id,
        description="desc",
        entry_url=entry_url,
        compose_scope=compose_scope,
        start_services=(),
        stop_services=(),
        shared_dependencies=(),
        auth_mode=auth_mode,
        auth_path=auth_path,
        auth_expectation=auth_expectation,
    )


class ProbeClientTest(unittest.TestCase):
    def test_fetch_no_redirect_returns_302_http_error_response(self) -> None:
        client = ProbeClient()
        opener = Mock()
        opener.open.side_effect = HTTPError(
            "http://example.local/",
            302,
            "Found",
            {"Location": "/login"},
            io.BytesIO(b""),
        )

        with patch("business_panel.probes.build_opener", return_value=opener):
            response = client.fetch("http://example.local/", follow_redirects=False)

        self.assertEqual(response.status, 302)
        self.assertEqual(response.headers.get("Location"), "/login")
        self.assertEqual(response.body, "")

    def test_fetch_http_error_preserves_headers_and_body(self) -> None:
        client = ProbeClient()
        opener = Mock()
        opener.open.side_effect = HTTPError(
            "http://example.local/protected",
            401,
            "Unauthorized",
            {"WWW-Authenticate": "Basic realm=test"},
            io.BytesIO("access denied".encode("utf-8")),
        )

        with patch("business_panel.probes.build_opener", return_value=opener):
            response = client.fetch("http://example.local/protected", follow_redirects=False)

        self.assertEqual(response.status, 401)
        self.assertEqual(response.headers.get("WWW-Authenticate"), "Basic realm=test")
        self.assertEqual(response.body, "access denied")

    def test_fetch_network_failure_returns_fallback_http_response(self) -> None:
        client = ProbeClient()
        with patch("business_panel.probes.urlopen", side_effect=URLError("dns failed")):
            response = client.fetch("http://missing.local", follow_redirects=True)

        self.assertEqual(response.status, 503)
        self.assertEqual(response.headers, {})
        self.assertIn("dns failed", response.body)


class ProbeEndpointTest(unittest.TestCase):
    def test_probe_endpoint_warns_on_4xx(self) -> None:
        unit = _unit(
            unit_id="redisinsight",
            entry_url="http://127.0.0.1:4180",
            auth_mode="oauth2_proxy_redirect",
            auth_path="/oauth2/",
        )
        client = FakeProbeClient({"http://127.0.0.1:4180": HttpResponse(status=404, headers={}, body="")})

        result = probe_endpoint(unit, client, harbor_installed=True)

        self.assertEqual(result, ProbeResult.warn("入口返回 404"))

    def test_probe_endpoint_fails_on_5xx(self) -> None:
        unit = _unit(
            unit_id="kafka_ui",
            entry_url="http://127.0.0.1:8082",
            auth_mode="oidc_redirect",
            auth_path="openid-connect/auth",
        )
        client = FakeProbeClient({"http://127.0.0.1:8082": HttpResponse(status=503, headers={}, body="")})

        result = probe_endpoint(unit, client, harbor_installed=True)

        self.assertEqual(result, ProbeResult.fail("入口返回 503"))

    def test_probe_endpoint_uses_harbor_ping_target(self) -> None:
        unit = _unit(
            unit_id="harbor",
            entry_url="http://127.0.0.1:8088",
            auth_mode="harbor_oidc",
            auth_path="/c/oidc/login",
            auth_expectation="best_effort",
            compose_scope="harbor",
        )
        client = FakeProbeClient(
            {"http://127.0.0.1:8088/api/v2.0/ping": HttpResponse(status=200, headers={}, body="pong")}
        )

        result = probe_endpoint(unit, client, harbor_installed=True)

        self.assertEqual(result, ProbeResult.ok("入口可达"))
        self.assertEqual(client.calls, [("http://127.0.0.1:8088/api/v2.0/ping", False)])


class ProbeAuthTest(unittest.TestCase):
    def test_kafka_ui_auth_accepts_keycloak_redirect(self) -> None:
        unit = _unit(
            unit_id="kafka_ui",
            entry_url="http://127.0.0.1:8082",
            auth_mode="oidc_redirect",
            auth_path="openid-connect/auth",
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
        unit = _unit(
            unit_id="redisinsight",
            entry_url="http://127.0.0.1:4180",
            auth_mode="oauth2_proxy_redirect",
            auth_path="/oauth2/",
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
        unit = _unit(
            unit_id="harbor",
            entry_url="http://127.0.0.1:8088",
            auth_mode="harbor_oidc",
            auth_path="/c/oidc/login",
            auth_expectation="best_effort",
            compose_scope="harbor",
        )
        client = FakeProbeClient({})

        result = probe_auth(unit, client, harbor_installed=False)

        self.assertEqual(result, ProbeResult.not_installed("Harbor installer 缺失"))

    def test_probe_auth_metadata_failure(self) -> None:
        unit = _unit(
            unit_id="keycloak",
            entry_url="http://127.0.0.1:8080",
            auth_mode="metadata",
            auth_path="/realms/infra/.well-known/openid-configuration",
        )
        client = FakeProbeClient(
            {
                "http://127.0.0.1:8080/realms/infra/.well-known/openid-configuration": HttpResponse(
                    status=200, headers={}, body='{"issuer":"x"}'
                )
            }
        )

        result = probe_auth(unit, client, harbor_installed=True)

        self.assertEqual(result, ProbeResult.fail("认证元数据异常"))

    def test_probe_auth_oidc_redirect_missing_location_fails(self) -> None:
        unit = _unit(
            unit_id="kafka_ui",
            entry_url="http://127.0.0.1:8082",
            auth_mode="oidc_redirect",
            auth_path="openid-connect/auth",
        )
        client = FakeProbeClient({"http://127.0.0.1:8082": HttpResponse(status=200, headers={}, body="")})

        result = probe_auth(unit, client, harbor_installed=True)

        self.assertEqual(result, ProbeResult.fail("未检测到 OIDC 跳转"))

    def test_probe_auth_oidc_redirect_accepts_spring_oauth2_authorization_redirect(self) -> None:
        unit = _unit(
            unit_id="kafka_ui",
            entry_url="http://127.0.0.1:8082",
            auth_mode="oidc_redirect",
            auth_path="openid-connect/auth",
        )
        client = FakeProbeClient(
            {
                "http://127.0.0.1:8082": HttpResponse(
                    status=302,
                    headers={"Location": "/oauth2/authorization/keycloak"},
                    body="",
                )
            }
        )

        result = probe_auth(unit, client, harbor_installed=True)

        self.assertEqual(result, ProbeResult.ok("检测到 OIDC 跳转"))

    def test_probe_auth_nacos_accepts_oauth2_proxy_redirect(self) -> None:
        unit = _unit(
            unit_id="nacos",
            entry_url="http://nacos.localhost",
            auth_mode="oauth2_proxy_redirect",
            auth_path="/oauth2/",
        )
        client = FakeProbeClient(
            {
                "http://nacos.localhost": HttpResponse(
                    status=302,
                    headers={"Location": "/oauth2/start?rd=%2F"},
                    body="",
                )
            }
        )

        result = probe_auth(unit, client, harbor_installed=True)

        self.assertEqual(result.level, "ok")

    def test_probe_auth_nacos_accepts_direct_keycloak_redirect_from_proxy(self) -> None:
        unit = _unit(
            unit_id="nacos",
            entry_url="http://nacos.localhost",
            auth_mode="oauth2_proxy_redirect",
            auth_path="/oauth2/",
        )
        client = FakeProbeClient(
            {
                "http://nacos.localhost": HttpResponse(
                    status=302,
                    headers={
                        "Location": (
                            "http://auth.localhost/realms/infra/protocol/openid-connect/auth"
                            "?client_id=oauth2-proxy"
                            "&redirect_uri=http%3A%2F%2Fnacos.localhost%2Foauth2%2Fcallback"
                        )
                    },
                    body="",
                ),
            }
        )

        result = probe_auth(unit, client, harbor_installed=True)

        self.assertEqual(client.calls, [("http://nacos.localhost", False)])
        self.assertEqual(result.level, "ok")
        location = client.responses["http://nacos.localhost"].headers.get("Location", "")
        self.assertIn("client_id=oauth2-proxy", location)
        self.assertIn(
            "redirect_uri=http%3A%2F%2Fnacos.localhost%2Foauth2%2Fcallback",
            location,
        )

    def test_probe_auth_nightingale_accepts_oidc_redirect(self) -> None:
        unit = _unit(
            unit_id="nightingale",
            entry_url="http://nightingale.localhost",
            auth_mode="oidc_redirect",
            auth_path="openid-connect/auth",
        )
        client = FakeProbeClient(
            {
                "http://nightingale.localhost/api/n9e/auth/redirect?redirect=%2F": HttpResponse(
                    status=200,
                    headers={},
                    body='{"dat":"http://auth.localhost/realms/infra/protocol/openid-connect/auth?client_id=nightingale&redirect_uri=http%3A%2F%2Fnightingale.localhost%2Fcallback","err":""}',
                )
            }
        )

        result = probe_auth(unit, client, harbor_installed=True)

        self.assertEqual(result.level, "ok")

    def test_probe_auth_harbor_oidc_warn_when_missing_keyword(self) -> None:
        unit = _unit(
            unit_id="harbor",
            entry_url="http://127.0.0.1:8088",
            auth_mode="harbor_oidc",
            auth_path="/c/oidc/login",
            auth_expectation="best_effort",
            compose_scope="harbor",
        )
        client = FakeProbeClient({"http://127.0.0.1:8088": HttpResponse(status=200, headers={}, body="<html>login</html>")})

        result = probe_auth(unit, client, harbor_installed=True)

        self.assertEqual(result, ProbeResult.warn("未发现 Harbor OIDC 入口"))
        self.assertEqual(client.calls, [("http://127.0.0.1:8088", True)])

    def test_probe_auth_harbor_oidc_ok_when_oidc_present(self) -> None:
        unit = _unit(
            unit_id="harbor",
            entry_url="http://127.0.0.1:8088",
            auth_mode="harbor_oidc",
            auth_path="/c/oidc/login",
            auth_expectation="best_effort",
            compose_scope="harbor",
        )
        client = FakeProbeClient(
            {"http://127.0.0.1:8088": HttpResponse(status=200, headers={}, body="<a href='/c/oidc/login'>OIDC</a>")}
        )

        result = probe_auth(unit, client, harbor_installed=True)

        self.assertEqual(result, ProbeResult.ok("检测到 Harbor OIDC 入口"))

    def test_probe_auth_unknown_mode_returns_warn(self) -> None:
        unit = _unit(
            unit_id="portainer",
            entry_url="http://127.0.0.1:9000",
            auth_mode="custom_future_mode",
            auth_path="",
            auth_expectation="required",
        )
        client = FakeProbeClient({})

        result = probe_auth(unit, client, harbor_installed=True)

        self.assertEqual(result, ProbeResult.warn("未定义认证检查"))


class Task3OidcConfigContractTest(unittest.TestCase):
    def test_nacos_console_config_is_local_dev_ready(self) -> None:
        nacos_config = _parse_properties("nacos/application.properties")

        self.assertEqual(nacos_config["nacos.core.auth.enabled"], "false")
        self.assertEqual(nacos_config["nacos.core.auth.console.enabled"], "false")
        self.assertEqual(nacos_config["nacos.console.ui.enabled"], "true")
        self.assertNotIn("nacos.core.auth.system.type", nacos_config)
        self.assertEqual(nacos_config["nacos.core.auth.server.identity.key"], "serverIdentity")
        self.assertEqual(nacos_config["nacos.core.auth.server.identity.value"], "security")
        self.assertEqual(
            nacos_config["nacos.core.auth.plugin.nacos.token.secret.key"],
            "VGhpc0lzTXlDdXN0b21TZWNyZXRLZXkwMTIzNDU2Nzg=",
        )
        self.assertNotIn("nacos.core.auth.plugin.oidc.client-id", nacos_config)
        self.assertNotIn("nacos.core.auth.plugin.oidc.client-secret", nacos_config)
        self.assertNotIn("nacos.core.auth.plugin.oidc.issuer-uri", nacos_config)

    def test_nightingale_oidc_config_is_local_dev_ready(self) -> None:
        config = _load_toml("nightingale/config.toml")
        auth = config["Auth"]["OIDC"]

        self.assertEqual(config["DB"]["DBType"], "mysql")
        self.assertIn("nightingale:nightingale-dev-password@", config["DB"]["DSN"])
        self.assertIn("tcp(nightingale-mysql:3306)", config["DB"]["DSN"])
        self.assertIn("/nightingale?", config["DB"]["DSN"])
        self.assertIn("parseTime=True", config["DB"]["DSN"])
        self.assertEqual(config["Redis"]["Address"], "nightingale-redis:6379")
        self.assertEqual(config["Redis"]["RedisType"], "standalone")
        self.assertEqual(config["Redis"]["Password"], "nightingale-redis-dev-password")
        self.assertIs(auth["Enable"], True)
        self.assertEqual(auth["DisplayName"], "OIDC")
        self.assertEqual(auth["RedirectURL"], "http://nightingale.localhost/callback")
        self.assertEqual(auth["SsoAddr"], "http://auth.localhost/realms/infra/protocol/openid-connect/auth")
        self.assertEqual(auth["SsoLogoutAddr"], "http://auth.localhost/realms/infra/protocol/openid-connect/logout")
        self.assertEqual(auth["ClientId"], "nightingale")
        self.assertEqual(auth["ClientSecret"], "nightingale-client-secret")
        self.assertIs(auth["CoverAttributes"], True)
        self.assertEqual(auth["DefaultRoles"], ["Standard"])
        self.assertEqual(auth["Scopes"], ["openid", "profile", "email"])
        self.assertEqual(auth["Attributes"]["Username"], "preferred_username")
        self.assertEqual(auth["Attributes"]["Nickname"], "preferred_username")
        self.assertEqual(auth["Attributes"]["Email"], "email")

    def test_task3_auth_surfaces_share_public_issuer_and_client_contract(self) -> None:
        env_values = _parse_env(".env.example")
        nacos_config = _parse_properties("nacos/application.properties")
        nightingale_config = _load_toml("nightingale/config.toml")
        bootstrap = pathlib.Path("scripts/bootstrap-keycloak.sh").read_text(encoding="utf-8")
        bootstrap_clients = _parse_bootstrap_client_calls(bootstrap)

        expected_issuer = (
            f'{env_values["PUBLIC_SCHEME"]}://{env_values["KEYCLOAK_PUBLIC_HOST"]}/realms/{env_values["KEYCLOAK_REALM"]}'
        )
        expected_auth_endpoint = f"{expected_issuer}/protocol/openid-connect/auth"
        self.assertEqual(nacos_config["nacos.core.auth.enabled"], "false")
        self.assertEqual(nightingale_config["Auth"]["OIDC"]["SsoAddr"], expected_auth_endpoint)
        self.assertEqual(
            nightingale_config["Auth"]["OIDC"]["SsoLogoutAddr"],
            f"{expected_issuer}/protocol/openid-connect/logout",
        )
        self.assertIn(
            'KEYCLOAK_PUBLIC_ISSUER="${PUBLIC_SCHEME}://${KEYCLOAK_PUBLIC_HOST}/realms/${KEYCLOAK_REALM}"',
            bootstrap,
        )
        self.assertEqual(nightingale_config["Auth"]["OIDC"]["ClientId"], "nightingale")
        self.assertIn("${OAUTH2_PROXY_CLIENT_ID}", bootstrap_clients)
        self.assertIn("nightingale", bootstrap_clients)

    def test_keycloak_bootstrap_refreshes_oauth2_proxy_and_nightingale_clients(self) -> None:
        bootstrap = pathlib.Path("scripts/bootstrap-keycloak.sh").read_text(encoding="utf-8")
        bootstrap_clients = _parse_bootstrap_client_calls(bootstrap)
        function_body = _extract_shell_function(bootstrap, "create_or_update_client")

        self.assertEqual(
            bootstrap_clients["${OAUTH2_PROXY_CLIENT_ID}"],
            {
                "secret": "${OAUTH2_PROXY_CLIENT_SECRET}",
                "redirect_uris": "[\\\"${PUBLIC_SCHEME}://${REDISINSIGHT_PUBLIC_HOST}/oauth2/callback\\\",\\\"${PUBLIC_SCHEME}://${PHPMYADMIN_PUBLIC_HOST}/oauth2/callback\\\",\\\"${PUBLIC_SCHEME}://${MONGO_EXPRESS_PUBLIC_HOST}/oauth2/callback\\\",\\\"${PUBLIC_SCHEME}://${NACOS_PUBLIC_HOST}/oauth2/callback\\\"]",
                "web_origins": "[\\\"${PUBLIC_SCHEME}://${REDISINSIGHT_PUBLIC_HOST}\\\",\\\"${PUBLIC_SCHEME}://${PHPMYADMIN_PUBLIC_HOST}\\\",\\\"${PUBLIC_SCHEME}://${MONGO_EXPRESS_PUBLIC_HOST}\\\",\\\"${PUBLIC_SCHEME}://${NACOS_PUBLIC_HOST}\\\"]",
            },
        )
        self.assertEqual(
            bootstrap_clients["nightingale"],
            {
                "secret": "${NIGHTINGALE_CLIENT_SECRET}",
                "redirect_uris": "[\\\"${PUBLIC_SCHEME}://${NIGHTINGALE_PUBLIC_HOST}/callback\\\"]",
                "web_origins": "[\\\"${PUBLIC_SCHEME}://${NIGHTINGALE_PUBLIC_HOST}\\\"]",
            },
        )
        self.assertNotIn("nacos", bootstrap_clients)
        self.assertRegex(
            function_body,
            r'(?s)update "clients/\$\{client_uuid\}".*?[\'"]attributes\."post\.logout\.redirect\.uris"="\+"[\'"].*?secret="\$\{secret\}"',
        )


if __name__ == "__main__":
    unittest.main()
