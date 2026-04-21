from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import ClassVar, Literal


ProbeLevel = Literal["ok", "fail", "warn", "not_installed"]
AuthExpectation = Literal["required", "best_effort", "not_checked"]
OverallState = Literal["healthy", "degraded", "failed", "not_installed"]


@dataclass(frozen=True)
class ProbeResult:
    level: ProbeLevel
    summary: str
    _VALID_LEVELS: ClassVar[frozenset[str]] = frozenset({"ok", "fail", "warn", "not_installed"})

    def __post_init__(self) -> None:
        if self.level not in self._VALID_LEVELS:
            raise ValueError(f"invalid probe level: {self.level}")

    @classmethod
    def ok(cls, summary: str) -> "ProbeResult":
        return cls(level="ok", summary=summary)

    @classmethod
    def fail(cls, summary: str) -> "ProbeResult":
        return cls(level="fail", summary=summary)

    @classmethod
    def warn(cls, summary: str) -> "ProbeResult":
        return cls(level="warn", summary=summary)

    @classmethod
    def not_installed(cls, summary: str) -> "ProbeResult":
        return cls(level="not_installed", summary=summary)


@dataclass(frozen=True)
class UnitSnapshot:
    unit_id: str
    display_name: str
    description: str
    entry_url: str
    auth_expectation: AuthExpectation
    container: ProbeResult
    endpoint: ProbeResult
    auth: ProbeResult
    available_actions: tuple[str, ...]
    open_url: str | None = None
    _VALID_AUTH_EXPECTATIONS: ClassVar[frozenset[str]] = frozenset({"required", "best_effort", "not_checked"})

    def __post_init__(self) -> None:
        if self.auth_expectation not in self._VALID_AUTH_EXPECTATIONS:
            raise ValueError(f"invalid auth_expectation: {self.auth_expectation}")


@dataclass(frozen=True)
class UnitSummary:
    unit_id: str
    display_name: str
    description: str
    entry_url: str
    open_url: str
    auth_expectation: AuthExpectation
    container: ProbeResult
    endpoint: ProbeResult
    auth: ProbeResult
    overall_state: OverallState
    failure_summary: str
    available_actions: tuple[str, ...]
    _VALID_OVERALL_STATES: ClassVar[frozenset[str]] = frozenset({"healthy", "degraded", "failed", "not_installed"})

    def __post_init__(self) -> None:
        if self.overall_state not in self._VALID_OVERALL_STATES:
            raise ValueError(f"invalid overall_state: {self.overall_state}")

    def to_dict(self) -> dict[str, object]:
        return {
            "unit_id": self.unit_id,
            "display_name": self.display_name,
            "description": self.description,
            "entry_url": self.entry_url,
            "open_url": self.open_url,
            "auth_expectation": self.auth_expectation,
            "container": asdict(self.container),
            "endpoint": asdict(self.endpoint),
            "auth": asdict(self.auth),
            "overall_state": self.overall_state,
            "failure_summary": self.failure_summary,
            "available_actions": list(self.available_actions),
        }
