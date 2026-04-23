#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

MANAGED_BEGIN = "# BEGIN integration_of_third-party_tools"
MANAGED_END = "# END integration_of_third-party_tools"
NIGHTINGALE_DEFAULTS = {
    "PUBLIC_SCHEME": "http",
    "KEYCLOAK_PUBLIC_HOST": "auth.localhost",
    "KEYCLOAK_REALM": "infra",
    "NIGHTINGALE_PUBLIC_HOST": "nightingale.localhost",
    "NIGHTINGALE_DB_PASSWORD": "nightingale-dev-password",
    "NIGHTINGALE_REDIS_PASSWORD": "nightingale-redis-dev-password",
    "NIGHTINGALE_CLIENT_SECRET": "nightingale-client-secret",
}


def detect_public_ip(explicit: str | None = None) -> str:
    if explicit:
        ipaddress.ip_address(explicit)
        return explicit

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(("8.8.8.8", 80))
        detected = sock.getsockname()[0]

    ipaddress.ip_address(detected)
    if detected.startswith("127."):
        raise RuntimeError(f"detected loopback ip is invalid: {detected}")
    return detected


def render_hosts_block(public_ip: str, hostnames: list[str]) -> str:
    entries = [f"{public_ip} {hostname}" for hostname in hostnames]
    return "\n".join([MANAGED_BEGIN, *entries, MANAGED_END, ""])


def sync_hosts_file(path: Path, public_ip: str, hostnames: list[str]) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    managed = render_hosts_block(public_ip, hostnames)

    if MANAGED_BEGIN in existing and MANAGED_END in existing:
        prefix, rest = existing.split(MANAGED_BEGIN, 1)
        _, suffix = rest.split(MANAGED_END, 1)
        new_text = prefix.rstrip("\n") + "\n" + managed + suffix.lstrip("\n")
    else:
        base = existing.rstrip("\n")
        new_text = (base + "\n" if base else "") + managed

    path.write_text(new_text, encoding="utf-8")


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    raw = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=raw, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"malformed env line: {raw_line}")
        key, value = line.split("=", 1)
        values[key] = value
    return values


def render_nightingale_config(env_file: Path, output_file: Path) -> None:
    env_values = dict(NIGHTINGALE_DEFAULTS)
    env_values.update(parse_env_file(env_file))

    public_scheme = env_values["PUBLIC_SCHEME"]
    keycloak_host = env_values["KEYCLOAK_PUBLIC_HOST"]
    keycloak_realm = env_values["KEYCLOAK_REALM"]
    nightingale_host = env_values["NIGHTINGALE_PUBLIC_HOST"]
    db_password = env_values["NIGHTINGALE_DB_PASSWORD"]
    redis_password = env_values["NIGHTINGALE_REDIS_PASSWORD"]
    client_secret = env_values["NIGHTINGALE_CLIENT_SECRET"]
    issuer = f"{public_scheme}://{keycloak_host}/realms/{keycloak_realm}"

    config = f"""[HTTP]
Host = "0.0.0.0"
Port = 17000

[HTTP.JWTAuth]
AccessExpired = 1500
RefreshExpired = 10080
RedisKeyPrefix = "/jwt/"

[DB]
DBType = "mysql"
DSN = "nightingale:{db_password}@tcp(nightingale-mysql:3306)/nightingale?charset=utf8mb4&parseTime=True&loc=Local"

[Redis]
RedisType = "standalone"
Address = "nightingale-redis:6379"
Password = "{redis_password}"
DB = 0

[Auth.OIDC]
Enable = true
DisplayName = "OIDC"
RedirectURL = "{public_scheme}://{nightingale_host}/callback"
SsoAddr = "{issuer}/protocol/openid-connect/auth"
SsoLogoutAddr = "{issuer}/protocol/openid-connect/logout"
ClientId = "nightingale"
ClientSecret = "{client_secret}"
CoverAttributes = true
DefaultRoles = ["Standard"]
Scopes = ["openid", "profile", "email"]

[Auth.OIDC.Attributes]
Username = "preferred_username"
Nickname = "preferred_username"
Email = "email"
"""
    output_file.write_text(config, encoding="utf-8")


def portainer_login(base_url: str, host_header: str, admin_user: str, admin_password: str) -> str | None:
    try:
        payload = request_json(
            "POST",
            f"{base_url}/api/auth",
            headers={"Host": host_header, "Content-Type": "application/json"},
            payload={"Username": admin_user, "Password": admin_password},
        )
    except HTTPError as exc:
        if exc.code in {401, 404, 422}:
            return None
        raise

    token = payload.get("jwt")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Portainer login did not return jwt")
    return token


def configure_portainer_oauth(
    *,
    base_url: str,
    host_header: str,
    admin_user: str,
    admin_password: str,
    oauth_settings: dict[str, object],
) -> None:
    token = portainer_login(base_url, host_header, admin_user, admin_password)
    if token is None:
        request_json(
            "POST",
            f"{base_url}/api/users/admin/init",
            headers={"Host": host_header, "Content-Type": "application/json"},
            payload={"Username": admin_user, "Password": admin_password},
        )
        token = portainer_login(base_url, host_header, admin_user, admin_password)

    if token is None:
        raise RuntimeError("Portainer admin login failed after init")

    auth_headers = {
        "Host": host_header,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    settings = request_json("GET", f"{base_url}/api/settings", headers=auth_headers)
    oauth_base = settings.get("OAuthSettings", {})
    merged_oauth = dict(oauth_base) if isinstance(oauth_base, dict) else {}
    merged_oauth.update(oauth_settings)
    merged_settings = dict(settings)
    merged_settings["AuthenticationMethod"] = 3
    merged_settings["OAuthSettings"] = merged_oauth
    request_json("PUT", f"{base_url}/api/settings", headers=auth_headers, payload=merged_settings)


def is_ready_redirect(location: str) -> bool:
    return any(
        marker in location
        for marker in (
            "/protocol/openid-connect/auth",
            "/oauth2/",
            "/oauth2/sign_in",
        )
    )


def verify_install(base_url: str, hostnames: list[str]) -> dict[str, object]:
    checks: list[dict[str, str]] = []
    overall = "ready"

    for hostname in hostnames:
        request = urllib.request.Request(base_url, headers={"Host": hostname}, method="GET")
        result = "ready"
        detail = "http_200"
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                detail = f"http_{getattr(response, 'status', 200)}"
        except HTTPError as exc:
            location = exc.headers.get("Location", "") if exc.headers else ""
            if exc.code in {301, 302, 303, 307, 308} and is_ready_redirect(location):
                result = "ready"
                detail = f"redirect:{location}"
            else:
                result = "error"
                detail = f"http_{exc.code}"
        except Exception as exc:  # pragma: no cover - defensive fallback
            result = "error"
            detail = str(exc)

        if result != "ready":
            overall = "error"
        checks.append({"host": hostname, "result": result, "detail": detail})

    return {"overall": overall, "checks": checks}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)

    detect_cmd = subcommands.add_parser("detect-public-ip")
    detect_cmd.add_argument("--public-ip")

    sync_cmd = subcommands.add_parser("sync-hosts")
    sync_cmd.add_argument("--hosts-file", required=True)
    sync_cmd.add_argument("--public-ip", required=True)
    sync_cmd.add_argument("--host", action="append", default=[])

    portainer_cmd = subcommands.add_parser("configure-portainer")
    portainer_cmd.add_argument("--base-url", required=True)
    portainer_cmd.add_argument("--host-header", required=True)
    portainer_cmd.add_argument("--admin-user", required=True)
    portainer_cmd.add_argument("--admin-password", required=True)
    portainer_cmd.add_argument("--client-id", required=True)
    portainer_cmd.add_argument("--client-secret", required=True)
    portainer_cmd.add_argument("--auth-url", required=True)
    portainer_cmd.add_argument("--token-url", required=True)
    portainer_cmd.add_argument("--resource-url", required=True)
    portainer_cmd.add_argument("--logout-url", required=True)
    portainer_cmd.add_argument("--redirect-url", required=True)

    render_nightingale_cmd = subcommands.add_parser("render-nightingale-config")
    render_nightingale_cmd.add_argument("--env-file", required=True)
    render_nightingale_cmd.add_argument("--output", required=True)

    verify_cmd = subcommands.add_parser("verify-install")
    verify_cmd.add_argument("--base-url", required=True)
    verify_cmd.add_argument("--host", action="append", default=[])

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "detect-public-ip":
        print(detect_public_ip(args.public_ip))
        return

    if args.command == "sync-hosts":
        sync_hosts_file(Path(args.hosts_file), args.public_ip, args.host)
        return

    if args.command == "configure-portainer":
        configure_portainer_oauth(
            base_url=args.base_url,
            host_header=args.host_header,
            admin_user=args.admin_user,
            admin_password=args.admin_password,
            oauth_settings={
                "ClientID": args.client_id,
                "ClientSecret": args.client_secret,
                "AuthorizationURI": args.auth_url,
                "AccessTokenURI": args.token_url,
                "ResourceURI": args.resource_url,
                "LogoutURI": args.logout_url,
                "RedirectURI": args.redirect_url,
                "UserIdentifier": "preferred_username",
                "Scopes": "openid profile email groups",
                "OAuthAutoCreateUsers": True,
            },
        )
        return

    if args.command == "render-nightingale-config":
        render_nightingale_config(Path(args.env_file), Path(args.output))
        return

    if args.command == "verify-install":
        print(json.dumps(verify_install(args.base_url, args.host)))
        return

    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
