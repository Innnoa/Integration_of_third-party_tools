from __future__ import annotations

import fcntl
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .catalog import UnitDefinition
from .config import PanelSettings


class PanelBusyError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandSpec:
    argv: list[str]
    cwd: Path


class LockHandle:
    def __init__(self, file_obj: TextIO) -> None:
        self._file_obj = file_obj

    def release(self) -> None:
        fcntl.flock(self._file_obj.fileno(), fcntl.LOCK_UN)
        self._file_obj.close()


class ControlService:
    def __init__(self, settings: PanelSettings, units: dict[str, UnitDefinition]) -> None:
        self.settings = settings
        self.units = units
        self.lock_file = settings.root_dir / "outputs" / "runtime" / "panel" / "control.lock"

    def acquire_lock(self) -> LockHandle:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        file_obj = self.lock_file.open("a+", encoding="utf-8")
        try:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            file_obj.close()
            raise PanelBusyError("已有控制任务在执行") from exc
        return LockHandle(file_obj)

    def build_command(self, unit_id: str, action: str) -> CommandSpec:
        if action not in {"start", "stop", "restart"}:
            raise ValueError(f"unsupported action: {action}")

        if unit_id == "all":
            return CommandSpec(
                argv=[str(self.settings.root_dir / "scripts" / "services.sh"), action],
                cwd=self.settings.root_dir,
            )

        unit = self.units.get(unit_id)
        if unit is None:
            raise ValueError(f"unknown unit_id: {unit_id}")
        if unit.compose_scope == "harbor":
            if action == "start":
                argv = ["docker", "compose", "up", "-d"]
            elif action == "stop":
                argv = ["docker", "compose", "stop"]
            else:
                argv = ["docker", "compose", "restart"]
            return CommandSpec(
                argv=argv,
                cwd=self.settings.root_dir / "harbor" / "installer",
            )

        argv = [
            "docker",
            "compose",
            "--env-file",
            str(self.settings.root_dir / ".env"),
            "-f",
            str(self.settings.root_dir / "compose.yml"),
        ]
        if action == "start":
            argv.extend(["up", "-d", *unit.start_services])
        elif action == "stop":
            argv.extend(["stop", *unit.stop_services])
        else:
            argv.extend(["restart", *unit.stop_services])
        return CommandSpec(argv=argv, cwd=self.settings.root_dir)
