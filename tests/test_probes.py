import io
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import Mock, patch

from business_panel.catalog import UnitDefinition
from business_panel.models import ProbeResult
from business_panel.probes import HttpResponse, ProbeClient, probe_auth, probe_endpoint


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


if __name__ == "__main__":
    unittest.main()
