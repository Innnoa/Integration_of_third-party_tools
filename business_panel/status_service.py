from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

from .catalog import build_units
from .config import PanelSettings
from .control import ControlService
from .models import ProbeResult, UnitSnapshot, UnitSummary
from .probes import ProbeClient, probe_auth, probe_endpoint


ACTIONS = ("start", "stop", "restart")
STATUS_COMMAND_TIMEOUT = 8
ACTION_COMMAND_TIMEOUT = 300


def _failure_summary(snapshot: UnitSnapshot) -> str:
    labels: tuple[tuple[str, ProbeResult], ...] = (
        ("容器", snapshot.container),
        ("入口", snapshot.endpoint),
        ("认证", snapshot.auth),
    )
    failures = [f"{label}: {probe.summary}" for label, probe in labels if probe.level != "ok"]
    if not failures:
        return "状态正常"
    return "；".join(failures)


def summarize_unit(snapshot: UnitSnapshot) -> UnitSummary:
    probes = (snapshot.container, snapshot.endpoint, snapshot.auth)
    if any(probe.level == "not_installed" for probe in probes):
        overall_state = "not_installed"
    elif snapshot.container.level == "fail" or snapshot.endpoint.level == "fail":
        overall_state = "failed"
    elif snapshot.auth.level == "fail" and snapshot.auth_expectation == "required":
        overall_state = "failed"
    elif any(probe.level in {"fail", "warn"} for probe in probes):
        overall_state = "degraded"
    else:
        overall_state = "healthy"

    return UnitSummary(
        unit_id=snapshot.unit_id,
        display_name=snapshot.display_name,
        description=snapshot.description,
        entry_url=snapshot.entry_url,
        open_url=snapshot.open_url or snapshot.entry_url,
        auth_expectation=snapshot.auth_expectation,
        container=snapshot.container,
        endpoint=snapshot.endpoint,
        auth=snapshot.auth,
        overall_state=overall_state,
        failure_summary=_failure_summary(snapshot),
        available_actions=snapshot.available_actions,
    )


def summarize_panel(snapshots: list[UnitSnapshot]) -> dict[str, object]:
    totals = {
        "healthy": 0,
        "degraded": 0,
        "failed": 0,
        "not_installed": 0,
        "total": 0,
    }
    units: list[dict[str, object]] = []

    for snapshot in snapshots:
        summary = summarize_unit(snapshot)
        totals[summary.overall_state] += 1
        totals["total"] += 1
        units.append(summary.to_dict())

    return {
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "totals": totals,
        "units": units,
    }


def _run_compose_ps(settings: PanelSettings, scope: str) -> set[str]:
    if scope == "harbor":
        installer_dir = settings.root_dir / "harbor" / "installer"
        if not installer_dir.exists():
            return set()
        command = ["docker", "compose", "ps", "--format", "json"]
        cwd = installer_dir
    else:
        command = [
            "docker",
            "compose",
            "--env-file",
            str(settings.root_dir / ".env"),
            "-f",
            str(settings.root_dir / "compose.yml"),
            "ps",
            "--format",
            "json",
        ]
        cwd = settings.root_dir

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=STATUS_COMMAND_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return set()
    except OSError:
        return set()

    if completed.returncode != 0:
        return set()

    stdout = completed.stdout or ""
    try:
        payload = json.loads(stdout)
        if isinstance(payload, dict):
            payload = [payload]
        elif not isinstance(payload, list):
            return set()
    except json.JSONDecodeError:
        payload = []
        for line in stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                item = json.loads(stripped)
            except json.JSONDecodeError:
                return set()
            payload.append(item)

    running_services: set[str] = set()
    for item in payload:
        if not isinstance(item, dict) or item.get("State") != "running":
            continue
        service = item.get("Service")
        if isinstance(service, str):
            running_services.add(service)
    return running_services


def _tail_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[-600:]


class PanelApplication:
    def __init__(self, settings: PanelSettings) -> None:
        self.settings = settings
        self.units = {unit.unit_id: unit for unit in build_units(settings)}
        self.control = ControlService(settings, self.units)
        self.client = ProbeClient()

    def get_status_payload(self) -> dict[str, object]:
        harbor_installed = (self.settings.root_dir / "harbor" / "installer").exists()
        running_main = _run_compose_ps(self.settings, "main")
        running_harbor = _run_compose_ps(self.settings, "harbor") if harbor_installed else set()
        snapshots: list[UnitSnapshot] = []

        for unit in self.units.values():
            if unit.compose_scope == "harbor" and not harbor_installed:
                missing = ProbeResult.not_installed("Harbor installer 缺失")
                snapshots.append(
                    UnitSnapshot(
                        unit_id=unit.unit_id,
                        display_name=unit.display_name,
                        description=unit.description,
                        entry_url=unit.entry_url,
                        open_url=unit.open_url,
                        auth_expectation=unit.auth_expectation,
                        container=missing,
                        endpoint=missing,
                        auth=missing,
                        available_actions=ACTIONS,
                    )
                )
                continue

            if unit.compose_scope == "harbor":
                container = (
                    ProbeResult.ok("Harbor compose 已启动")
                    if "proxy" in running_harbor
                    else ProbeResult.fail("Harbor compose 未运行")
                )
            else:
                probe_services = unit.start_services or unit.stop_services
                container = (
                    ProbeResult.ok("容器运行")
                    if all(service in running_main for service in probe_services)
                    else ProbeResult.fail("存在未运行服务")
                )

            if container.level == "fail":
                endpoint = ProbeResult.warn(f"{container.summary}，跳过入口探测")
                auth = ProbeResult.warn(f"{container.summary}，跳过认证探测")
            else:
                endpoint = probe_endpoint(unit, self.client, harbor_installed=harbor_installed)
                auth = probe_auth(unit, self.client, harbor_installed=harbor_installed)

            snapshots.append(
                UnitSnapshot(
                    unit_id=unit.unit_id,
                    display_name=unit.display_name,
                    description=unit.description,
                    entry_url=unit.entry_url,
                    open_url=unit.open_url,
                    auth_expectation=unit.auth_expectation,
                    container=container,
                    endpoint=endpoint,
                    auth=auth,
                    available_actions=ACTIONS,
                )
            )

        return summarize_panel(snapshots)

    def run_action(self, unit_id: str, action: str) -> dict[str, object]:
        lock = self.control.acquire_lock()
        try:
            command = self.control.build_command(unit_id, action)
            try:
                completed = subprocess.run(
                    command.argv,
                    cwd=command.cwd,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=ACTION_COMMAND_TIMEOUT,
                )
            except subprocess.TimeoutExpired as exc:
                return {
                    "ok": False,
                    "unit_id": unit_id,
                    "action": action,
                    "stdout": _tail_text(getattr(exc, "stdout", None) or getattr(exc, "output", None)),
                    "stderr": _tail_text(f"{_tail_text(exc.stderr)}\n控制命令执行超时".strip()),
                }
            except OSError as exc:
                return {
                    "ok": False,
                    "unit_id": unit_id,
                    "action": action,
                    "stdout": "",
                    "stderr": _tail_text(str(exc)),
                }
        finally:
            lock.release()

        return {
            "ok": completed.returncode == 0,
            "unit_id": unit_id,
            "action": action,
            "stdout": _tail_text(completed.stdout),
            "stderr": _tail_text(completed.stderr),
        }
