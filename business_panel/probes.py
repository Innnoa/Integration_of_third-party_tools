from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from .catalog import UnitDefinition
from .models import ProbeResult


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: str


class ProbeClient:
    def fetch(self, url: str, *, follow_redirects: bool = False) -> HttpResponse:
        request = Request(url=url, method="GET")
        try:
            if follow_redirects:
                with urlopen(request, timeout=5) as resp:
                    return HttpResponse(
                        status=getattr(resp, "status", resp.getcode()),
                        headers=dict(resp.headers.items()),
                        body=resp.read().decode("utf-8", errors="replace"),
                    )
            opener = build_opener(_NoRedirectHandler())
            with opener.open(request, timeout=5) as resp:
                return HttpResponse(
                    status=getattr(resp, "status", resp.getcode()),
                    headers=dict(resp.headers.items()),
                    body=resp.read().decode("utf-8", errors="replace"),
                )
        except HTTPError as exc:
            body = ""
            if exc.fp is not None:
                body = exc.read().decode("utf-8", errors="replace")
            return HttpResponse(status=exc.code, headers=dict(exc.headers.items()), body=body)
        except (URLError, TimeoutError, OSError) as exc:
            return HttpResponse(status=503, headers={}, body=str(exc))


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def probe_endpoint(
    unit: UnitDefinition,
    client: ProbeClient,
    *,
    harbor_installed: bool,
) -> ProbeResult:
    if unit.unit_id == "harbor" and not harbor_installed:
        return ProbeResult.not_installed("Harbor installer 缺失")

    target = unit.entry_url
    if unit.unit_id == "harbor":
        target = f"{unit.entry_url}/api/v2.0/ping"

    response = client.fetch(target)
    if response.status >= 500:
        return ProbeResult.fail(f"入口返回 {response.status}")
    if response.status >= 400:
        return ProbeResult.warn(f"入口返回 {response.status}")
    return ProbeResult.ok("入口可达")


def probe_auth(
    unit: UnitDefinition,
    client: ProbeClient,
    *,
    harbor_installed: bool,
) -> ProbeResult:
    if unit.auth_expectation == "not_checked":
        return ProbeResult.warn("首版未做端到端认证检查")
    if unit.unit_id == "harbor" and not harbor_installed:
        return ProbeResult.not_installed("Harbor installer 缺失")

    if unit.auth_mode == "metadata":
        response = client.fetch(f"{unit.entry_url}{unit.auth_path}")
        if response.status == 200 and "authorization_endpoint" in response.body:
            return ProbeResult.ok("认证元数据正常")
        return ProbeResult.fail("认证元数据异常")

    if unit.auth_mode == "oidc_redirect":
        if unit.unit_id == "nightingale":
            response = client.fetch(f"{unit.entry_url}/api/n9e/auth/redirect?redirect={quote('/', safe='')}")
            if "openid-connect/auth" in response.body and "client_id=nightingale" in response.body:
                return ProbeResult.ok("检测到 OIDC 跳转")
            return ProbeResult.fail("未检测到 OIDC 跳转")
        response = client.fetch(unit.entry_url)
        location = _header_value(response.headers, "Location")
        if unit.auth_path in location or "/oauth2/authorization/" in location:
            return ProbeResult.ok("检测到 OIDC 跳转")
        return ProbeResult.fail("未检测到 OIDC 跳转")

    if unit.auth_mode == "oauth2_proxy_redirect":
        response = client.fetch(unit.entry_url)
        location = _header_value(response.headers, "Location")
        if unit.auth_path in location or "openid-connect/auth" in location:
            return ProbeResult.ok("检测到 OAuth2 Proxy 跳转")
        return ProbeResult.fail("未检测到 OAuth2 Proxy 跳转")

    if unit.auth_mode == "harbor_oidc":
        response = client.fetch(unit.entry_url, follow_redirects=True)
        if unit.auth_path in response.body or "OIDC" in response.body:
            return ProbeResult.ok("检测到 Harbor OIDC 入口")
        return ProbeResult.warn("未发现 Harbor OIDC 入口")

    return ProbeResult.warn("未定义认证检查")

def _header_value(headers: dict[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""
