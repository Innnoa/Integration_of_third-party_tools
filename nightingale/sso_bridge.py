from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen


UPSTREAM = os.environ.get("NIGHTINGALE_UPSTREAM", "http://nightingale:17000")
LISTEN_HOST = os.environ.get("NIGHTINGALE_SSO_BRIDGE_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("NIGHTINGALE_SSO_BRIDGE_PORT", "18100"))


def _json_request(url: str, *, method: str = "GET", body: bytes | None = None) -> tuple[int, dict[str, object]]:
    request = Request(url=url, method=method, data=body)
    request.add_header("Content-Type", "application/json")
    with urlopen(request, timeout=15) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        if parsed.path == "/callback":
            self._handle_callback(parsed)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        if parsed.path in {"/api/n9e/auth/login", "/api/n9e/auth/refresh"}:
            self._handle_auth_post(parsed)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "not found")

    def _handle_callback(self, parsed) -> None:
        params = parse_qs(parsed.query, keep_blank_values=True)
        flat = {key: values[-1] if values else "" for key, values in params.items()}
        flat.setdefault("redirect", "/")

        try:
            _, payload = _json_request(f"{UPSTREAM}/api/n9e/auth/callback?{urlencode(flat)}")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            self._render_error(f"callback 请求失败: {exc}")
            return

        self._finish_auth(payload, redirect_default="/")

    def _handle_auth_post(self, parsed) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            status, payload = _json_request(f"{UPSTREAM}{parsed.path}", method="POST", body=body)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            self._render_json({"err": str(exc)}, HTTPStatus.BAD_GATEWAY)
            return

        self._render_json(payload, status)

    def _finish_auth(self, payload: dict[str, object], *, redirect_default: str) -> None:
        if payload.get("err"):
            self._render_error(str(payload["err"]))
            return

        dat = payload.get("dat")
        if not isinstance(dat, dict):
            self._render_error("callback 未返回 dat")
            return

        access_token = dat.get("access_token")
        refresh_token = dat.get("refresh_token")
        redirect = dat.get("redirect") or redirect_default
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            self._render_error("callback 未返回 access_token / refresh_token")
            return

        self.send_response(HTTPStatus.FOUND)
        self.send_header("Set-Cookie", f"n9e_access_token={access_token}; Path=/; SameSite=Lax")
        self.send_header("Set-Cookie", f"n9e_refresh_token={refresh_token}; Path=/; SameSite=Lax")
        self.send_header("Location", redirect if isinstance(redirect, str) else "/")
        self.end_headers()

    def _render_json(self, payload: dict[str, object], status: int) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        dat = payload.get("dat")
        if isinstance(dat, dict):
            access_token = dat.get("access_token")
            refresh_token = dat.get("refresh_token")
            if isinstance(access_token, str) and isinstance(refresh_token, str):
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Set-Cookie", f"n9e_access_token={access_token}; Path=/; SameSite=Lax")
                self.send_header("Set-Cookie", f"n9e_refresh_token={refresh_token}; Path=/; SameSite=Lax")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(fmt % args)

    def _render_error(self, message: str) -> None:
        body = f"""<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <title>Nightingale 登录失败</title>
  </head>
  <body>
    <h1>登录失败</h1>
    <p>{message}</p>
    <p><a href="/login?redirect=%2F">返回登录页</a></p>
  </body>
</html>
""".encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    print(f"Nightingale SSO bridge listening on http://{LISTEN_HOST}:{LISTEN_PORT}")
    server.serve_forever()
