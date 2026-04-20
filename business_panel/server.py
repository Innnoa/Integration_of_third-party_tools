from __future__ import annotations

import json
from json import JSONDecodeError
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .control import PanelBusyError

STATIC_DIR = Path(__file__).resolve().parent / "static"


def make_server(host: str, port: int, app) -> ThreadingHTTPServer:
    class PanelHandler(BaseHTTPRequestHandler):
        def _send_json(self, payload: dict[str, object], status: int = HTTPStatus.OK, *, send_body: bool = True) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        def _send_error_json(self, status: int, message: str) -> None:
            self._send_json({"ok": False, "error": message}, status=status)

        def _send_file(self, path: Path, content_type: str, *, send_body: bool = True) -> None:
            if not path.exists():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        def _read_json_body(self) -> dict[str, object]:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except (UnicodeDecodeError, JSONDecodeError) as exc:
                raise ValueError("请求体不是有效 JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError("请求体必须是 JSON 对象")
            return payload

        def do_GET(self) -> None:
            route = urlsplit(self.path).path
            if route == "/api/status":
                try:
                    self._send_json(app.get_status_payload())
                except Exception:
                    self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "服务器内部错误")
                return
            if route in {"/", "/index.html"}:
                self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
                return
            if route == "/app.css":
                self._send_file(STATIC_DIR / "app.css", "text/css; charset=utf-8")
                return
            if route == "/app.js":
                self._send_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_HEAD(self) -> None:
            route = urlsplit(self.path).path
            if route == "/api/status":
                try:
                    self._send_json(app.get_status_payload(), send_body=False)
                except Exception:
                    self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "服务器内部错误")
                return
            if route in {"/", "/index.html"}:
                self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8", send_body=False)
                return
            if route == "/app.css":
                self._send_file(STATIC_DIR / "app.css", "text/css; charset=utf-8", send_body=False)
                return
            if route == "/app.js":
                self._send_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8", send_body=False)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            route = urlsplit(self.path).path
            if route != "/api/control":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                payload = self._read_json_body()
                unit_id = payload.get("unit_id")
                action = payload.get("action")
                if not isinstance(unit_id, str) or not isinstance(action, str) or not unit_id or not action:
                    raise ValueError("请求体必须包含 unit_id 和 action")
                self._send_json(app.run_action(unit_id, action))
            except PanelBusyError as exc:
                self._send_error_json(HTTPStatus.CONFLICT, str(exc) or "已有控制任务在执行")
            except ValueError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc) or "请求参数无效")
            except Exception:
                self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "服务器内部错误")

        def log_message(self, format: str, *args) -> None:
            return

    return ThreadingHTTPServer((host, port), PanelHandler)
