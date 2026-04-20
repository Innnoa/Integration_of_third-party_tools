from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PanelSettings:
    root_dir: Path
    public_scheme: str
    public_host: str
    browser_host: str
    keycloak_public_host: str
    keycloak_realm: str
    keycloak_port: int
    portainer_port: int
    kafka_ui_port: int
    redisinsight_port: int
    phpmyadmin_port: int
    mongo_express_port: int
    harbor_port: int
    panel_host: str
    panel_port: int
    refresh_interval: int
    portainer_public_host: str = "portainer.localhost"
    kafka_ui_public_host: str = "kafka.localhost"
    redisinsight_public_host: str = "redis.localhost"
    phpmyadmin_public_host: str = "pma.localhost"
    mongo_express_public_host: str = "mongo.localhost"
    harbor_public_host: str = "harbor.localhost"


def _load_env(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ValueError(f"Invalid .env malformed line {line_number}: {stripped!r}")
        key, value = stripped.split("=", 1)
        values[key] = value
    return values


def _require(env_values: dict[str, str], key: str) -> str:
    value = env_values.get(key)
    if value is None or value == "":
        raise ValueError(f"Missing required setting: {key}")
    return value


def _require_int(env_values: dict[str, str], key: str) -> int:
    raw = _require(env_values, key)
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for {key}: {raw!r}") from exc


def _optional_int(env_values: dict[str, str], key: str, default: int) -> int:
    raw = env_values.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for {key}: {raw!r}") from exc


def _optional_str(env_values: dict[str, str], key: str, default: str) -> str:
    raw = env_values.get(key)
    if raw is None or raw == "":
        return default
    return raw


def load_settings(root_dir: Path) -> PanelSettings:
    env_values = _load_env(root_dir / ".env")
    return PanelSettings(
        root_dir=root_dir,
        public_scheme=_require(env_values, "PUBLIC_SCHEME"),
        public_host=_require(env_values, "PUBLIC_HOST"),
        browser_host=_require(env_values, "BROWSER_HOST"),
        keycloak_public_host=_require(env_values, "KEYCLOAK_PUBLIC_HOST"),
        keycloak_realm=_require(env_values, "KEYCLOAK_REALM"),
        keycloak_port=_require_int(env_values, "KEYCLOAK_PORT"),
        portainer_port=_require_int(env_values, "PORTAINER_PORT"),
        kafka_ui_port=_require_int(env_values, "KAFKA_UI_PORT"),
        redisinsight_port=_require_int(env_values, "REDISINSIGHT_PROXY_PORT"),
        phpmyadmin_port=_require_int(env_values, "PHPMYADMIN_PROXY_PORT"),
        mongo_express_port=_require_int(env_values, "MONGO_EXPRESS_PROXY_PORT"),
        harbor_port=_require_int(env_values, "HARBOR_PORT"),
        panel_host=_optional_str(env_values, "BUSINESS_PANEL_HOST", "127.0.0.1"),
        panel_port=_optional_int(env_values, "BUSINESS_PANEL_PORT", 8090),
        refresh_interval=_optional_int(env_values, "BUSINESS_PANEL_REFRESH_INTERVAL", 15),
        portainer_public_host=_optional_str(env_values, "PORTAINER_PUBLIC_HOST", "portainer.localhost"),
        kafka_ui_public_host=_optional_str(env_values, "KAFKA_UI_PUBLIC_HOST", "kafka.localhost"),
        redisinsight_public_host=_optional_str(env_values, "REDISINSIGHT_PUBLIC_HOST", "redis.localhost"),
        phpmyadmin_public_host=_optional_str(env_values, "PHPMYADMIN_PUBLIC_HOST", "pma.localhost"),
        mongo_express_public_host=_optional_str(env_values, "MONGO_EXPRESS_PUBLIC_HOST", "mongo.localhost"),
        harbor_public_host=_optional_str(env_values, "HARBOR_PUBLIC_HOST", "harbor.localhost"),
    )
