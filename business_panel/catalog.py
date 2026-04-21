from __future__ import annotations

from dataclasses import dataclass

from .config import PanelSettings


@dataclass(frozen=True)
class UnitDefinition:
    unit_id: str
    display_name: str
    description: str
    entry_url: str
    compose_scope: str
    start_services: tuple[str, ...]
    stop_services: tuple[str, ...]
    shared_dependencies: tuple[str, ...]
    auth_mode: str
    auth_path: str
    auth_expectation: str


def _public_url(scheme: str, host: str, port: int) -> str:
    return f"{scheme}://{host}:{port}"


def build_units(settings: PanelSettings) -> tuple[UnitDefinition, ...]:
    return (
        UnitDefinition(
            unit_id="keycloak",
            display_name="Keycloak",
            description="Identity provider and SSO realm management.",
            entry_url=f"{settings.public_scheme}://{settings.keycloak_public_host}",
            compose_scope="main",
            start_services=("keycloak-postgres", "keycloak"),
            stop_services=("keycloak", "keycloak-postgres"),
            shared_dependencies=(),
            auth_mode="metadata",
            auth_path=f"/realms/{settings.keycloak_realm}/.well-known/openid-configuration",
            auth_expectation="required",
        ),
        UnitDefinition(
            unit_id="portainer",
            display_name="Portainer",
            description="Container management UI.",
            entry_url=f"{settings.public_scheme}://{settings.portainer_public_host}",
            compose_scope="main",
            start_services=("portainer",),
            stop_services=("portainer",),
            shared_dependencies=(),
            auth_mode="not_checked",
            auth_path="",
            auth_expectation="not_checked",
        ),
        UnitDefinition(
            unit_id="kafka_ui",
            display_name="Kafka UI",
            description="Kafka cluster browser.",
            entry_url=f"{settings.public_scheme}://{settings.kafka_ui_public_host}",
            compose_scope="main",
            start_services=("kafka", "kafka-ui"),
            stop_services=("kafka-ui", "kafka"),
            shared_dependencies=(),
            auth_mode="oidc_redirect",
            auth_path="openid-connect/auth",
            auth_expectation="required",
        ),
        UnitDefinition(
            unit_id="redisinsight",
            display_name="RedisInsight",
            description="Redis management dashboard.",
            entry_url=f"{settings.public_scheme}://{settings.redisinsight_public_host}",
            compose_scope="main",
            start_services=("redis", "redisinsight", "oauth2-proxy-redisinsight"),
            stop_services=("redisinsight", "oauth2-proxy-redisinsight"),
            shared_dependencies=("redis",),
            auth_mode="oauth2_proxy_redirect",
            auth_path="/oauth2/",
            auth_expectation="required",
        ),
        UnitDefinition(
            unit_id="phpmyadmin",
            display_name="phpMyAdmin",
            description="MariaDB administration panel.",
            entry_url=f"{settings.public_scheme}://{settings.phpmyadmin_public_host}",
            compose_scope="main",
            start_services=("mariadb", "phpmyadmin", "oauth2-proxy-phpmyadmin"),
            stop_services=("phpmyadmin", "oauth2-proxy-phpmyadmin"),
            shared_dependencies=("mariadb",),
            auth_mode="oauth2_proxy_redirect",
            auth_path="/oauth2/",
            auth_expectation="required",
        ),
        UnitDefinition(
            unit_id="mongo_express",
            display_name="Mongo Express",
            description="MongoDB administration panel.",
            entry_url=f"{settings.public_scheme}://{settings.mongo_express_public_host}",
            compose_scope="main",
            start_services=("mongodb", "mongo-express", "oauth2-proxy-mongo-express"),
            stop_services=("mongo-express", "oauth2-proxy-mongo-express"),
            shared_dependencies=("mongodb",),
            auth_mode="oauth2_proxy_redirect",
            auth_path="/oauth2/",
            auth_expectation="required",
        ),
        UnitDefinition(
            unit_id="nacos",
            display_name="Nacos",
            description="Configuration and service discovery platform.",
            entry_url=f"{settings.public_scheme}://{settings.nacos_public_host}",
            compose_scope="main",
            start_services=("nacos", "nacos-mysql"),
            stop_services=("nacos", "nacos-mysql"),
            shared_dependencies=(),
            auth_mode="oidc_redirect",
            auth_path="openid-connect/auth",
            auth_expectation="required",
        ),
        UnitDefinition(
            unit_id="nightingale",
            display_name="Nightingale",
            description="Observability and alerting platform.",
            entry_url=f"{settings.public_scheme}://{settings.nightingale_public_host}",
            compose_scope="main",
            start_services=("nightingale", "nightingale-mysql", "nightingale-redis"),
            stop_services=("nightingale", "nightingale-mysql", "nightingale-redis"),
            shared_dependencies=(),
            auth_mode="oidc_redirect",
            auth_path="openid-connect/auth",
            auth_expectation="required",
        ),
        UnitDefinition(
            unit_id="harbor",
            display_name="Harbor",
            description="Container registry and artifact management.",
            entry_url=f"{settings.public_scheme}://{settings.harbor_public_host}",
            compose_scope="harbor",
            start_services=(),
            stop_services=(),
            shared_dependencies=(),
            auth_mode="harbor_oidc",
            auth_path="/c/oidc/login",
            auth_expectation="best_effort",
        ),
    )
