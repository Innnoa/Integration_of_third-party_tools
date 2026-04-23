from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from .control import PanelBusyError

STATIC_DIR = Path(__file__).resolve().parent / "static"


@dataclass(frozen=True)
class ResponseSpec:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes = b""


def _json_response(payload: dict[str, object], status: int = HTTPStatus.OK, *, send_body: bool = True) -> ResponseSpec:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return ResponseSpec(
        status=status,
        headers=(
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ),
        body=body if send_body else b"",
    )


def _empty_response(status: int) -> ResponseSpec:
    return ResponseSpec(status=status, headers=(("Content-Length", "0"),))


def _file_response(path: Path, content_type: str, *, send_body: bool = True) -> ResponseSpec:
    if not path.exists():
        return _empty_response(HTTPStatus.NOT_FOUND)
    body = path.read_bytes()
    return ResponseSpec(
        status=HTTPStatus.OK,
        headers=(
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
        ),
        body=body if send_body else b"",
    )


def _read_json_body(raw_body: bytes) -> dict[str, object]:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, JSONDecodeError) as exc:
        raise ValueError("请求体不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是 JSON 对象")
    return payload


def dispatch_request(
    app,
    *,
    method: str,
    path: str,
    headers: Mapping[str, str] | None = None,
    body: bytes = b"",
) -> ResponseSpec:
    route = urlsplit(path).path
    send_body = method != "HEAD"

    if method in {"GET", "HEAD"}:
        if route == "/api/status":
            try:
                return _json_response(app.get_status_payload(), send_body=send_body)
            except Exception:
                return _json_response({"ok": False, "error": "服务器内部错误"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
        if route in {"/", "/index.html"}:
            return _file_response(STATIC_DIR / "index.html", "text/html; charset=utf-8", send_body=send_body)
        if route == "/app.css":
            return _file_response(STATIC_DIR / "app.css", "text/css; charset=utf-8", send_body=send_body)
        if route == "/app.js":
            return _file_response(STATIC_DIR / "app.js", "application/javascript; charset=utf-8", send_body=send_body)
        return _empty_response(HTTPStatus.NOT_FOUND)

    if method == "POST":
        if route != "/api/control":
            return _empty_response(HTTPStatus.NOT_FOUND)
        try:
            payload = _read_json_body(body)
            unit_id = payload.get("unit_id")
            action = payload.get("action")
            if not isinstance(unit_id, str) or not isinstance(action, str) or not unit_id or not action:
                raise ValueError("请求体必须包含 unit_id 和 action")
            return _json_response(app.run_action(unit_id, action))
        except PanelBusyError as exc:
            return _json_response({"ok": False, "error": str(exc) or "已有控制任务在执行"}, status=HTTPStatus.CONFLICT)
        except ValueError as exc:
            return _json_response({"ok": False, "error": str(exc) or "请求参数无效"}, status=HTTPStatus.BAD_REQUEST)
        except Exception:
            return _json_response({"ok": False, "error": "服务器内部错误"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    return _empty_response(HTTPStatus.NOT_FOUND)


def make_server(host: str, port: int, app) -> ThreadingHTTPServer:
    class PanelHandler(BaseHTTPRequestHandler):
        def _send_response(self, response: ResponseSpec) -> None:
            self.send_response(response.status)
            for key, value in response.headers:
                self.send_header(key, value)
            self.end_headers()
            if response.body:
                self.wfile.write(response.body)

        def do_GET(self) -> None:
            self._send_response(dispatch_request(app, method="GET", path=self.path, headers=self.headers))

        def do_HEAD(self) -> None:
            self._send_response(dispatch_request(app, method="HEAD", path=self.path, headers=self.headers))

        def do_POST(self) -> None:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            self._send_response(dispatch_request(app, method="POST", path=self.path, headers=self.headers, body=body))

        def log_message(self, format: str, *args) -> None:
            return

    return ThreadingHTTPServer((host, port), PanelHandler)
