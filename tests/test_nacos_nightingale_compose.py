import pathlib
import unittest


class ComposeExtensionTest(unittest.TestCase):
    def _service_block(self, compose: str, service_name: str) -> str:
        start = compose.index(f"\n  {service_name}:\n")
        next_marker = compose.find("\n  ", start + 1)
        while next_marker != -1 and compose[next_marker + 3] == " ":
            next_marker = compose.find("\n  ", next_marker + 1)
        return compose[start: next_marker if next_marker != -1 else len(compose)]

    def test_compose_includes_nacos_and_nightingale_services(self) -> None:
        compose = pathlib.Path("compose.yml").read_text(encoding="utf-8")
        self.assertIn("  nacos:", compose)
        self.assertIn("  nacos-mysql:", compose)
        self.assertIn("  oauth2-proxy-nacos:", compose)
        self.assertIn("  nightingale:", compose)
        self.assertIn("  nightingale-mysql:", compose)
        self.assertIn("  nightingale-redis:", compose)
        self.assertIn("  nightingale-sso-bridge:", compose)

        nacos_mysql = self._service_block(compose, "nacos-mysql")
        self.assertIn("image: ${NACOS_MYSQL_IMAGE:-mysql:8.4}", nacos_mysql)
        self.assertIn("MYSQL_PASSWORD: ${NACOS_DB_PASSWORD:-nacos-dev-password}", nacos_mysql)
        self.assertIn("MYSQL_ROOT_PASSWORD: ${NACOS_DB_ROOT_PASSWORD:-nacos-root-dev-password}", nacos_mysql)
        self.assertIn("./nacos/mysql-schema.sql:/docker-entrypoint-initdb.d/01-nacos-schema.sql:ro", nacos_mysql)
        self.assertIn("healthcheck:", nacos_mysql)
        self.assertIn("mysqladmin ping", nacos_mysql)

        nacos = self._service_block(compose, "nacos")
        self.assertIn("image: ${NACOS_IMAGE:-nacos/nacos-server:latest}", nacos)
        self.assertIn("NACOS_DEPLOYMENT_TYPE: ${NACOS_DEPLOYMENT_TYPE:-merged}", nacos)
        self.assertIn("./nacos/application.properties:/home/nacos/conf/application.properties:ro", nacos)
        self.assertIn("condition: service_healthy", nacos)
        self.assertIn(
            "NACOS_AUTH_TOKEN: ${NACOS_AUTH_TOKEN:-VGhpc0lzTXlDdXN0b21TZWNyZXRLZXkwMTIzNDU2Nzg=}",
            nacos,
        )
        self.assertIn(
            "NACOS_AUTH_IDENTITY_KEY: ${NACOS_AUTH_IDENTITY_KEY:-serverIdentity}",
            nacos,
        )
        self.assertIn(
            "NACOS_AUTH_IDENTITY_VALUE: ${NACOS_AUTH_IDENTITY_VALUE:-security}",
            nacos,
        )

        nacos_proxy = self._service_block(compose, "oauth2-proxy-nacos")
        self.assertIn("container_name: oauth2-proxy-nacos", nacos_proxy)
        self.assertIn("--http-address=0.0.0.0:4183", nacos_proxy)
        self.assertIn("--redirect-url=${PUBLIC_SCHEME}://${NACOS_PUBLIC_HOST}/oauth2/callback", nacos_proxy)
        self.assertIn("--upstream=http://nacos:8080/", nacos_proxy)
        self.assertIn("--cookie-name=_oauth2_proxy_nacos", nacos_proxy)

        nightingale_mysql = self._service_block(compose, "nightingale-mysql")
        self.assertIn("image: ${NIGHTINGALE_MYSQL_IMAGE:-mysql:8.4}", nightingale_mysql)
        self.assertIn(
            "MYSQL_PASSWORD: ${NIGHTINGALE_DB_PASSWORD:-nightingale-dev-password}",
            nightingale_mysql,
        )
        self.assertIn(
            "MYSQL_ROOT_PASSWORD: ${NIGHTINGALE_DB_ROOT_PASSWORD:-nightingale-root-dev-password}",
            nightingale_mysql,
        )
        self.assertIn("healthcheck:", nightingale_mysql)
        self.assertIn("mysqladmin ping", nightingale_mysql)

        nightingale_redis = self._service_block(compose, "nightingale-redis")
        self.assertIn("image: ${NIGHTINGALE_REDIS_IMAGE:-redis:7.2-alpine}", nightingale_redis)
        self.assertIn(
            '"redis-server", "--appendonly", "yes", "--requirepass", "${NIGHTINGALE_REDIS_PASSWORD:-nightingale-redis-dev-password}"',
            nightingale_redis,
        )
        self.assertIn("healthcheck:", nightingale_redis)
        self.assertIn("redis-cli", nightingale_redis)

        nightingale = self._service_block(compose, "nightingale")
        self.assertIn("image: ${NIGHTINGALE_IMAGE:-flashcatcloud/nightingale:latest}", nightingale)
        self.assertIn('command: ["sh", "-c", "/app/n9e"]', nightingale)
        self.assertIn('extra_hosts:', nightingale)
        self.assertIn('- "auth.localhost:host-gateway"', nightingale)
        self.assertIn("./nightingale/config.toml:/app/etc/config.toml:ro", nightingale)
        self.assertIn("condition: service_healthy", nightingale)

        bridge = self._service_block(compose, "nightingale-sso-bridge")
        self.assertIn("image: python:3.12-slim", bridge)
        self.assertIn('command: ["python", "/app/nightingale/sso_bridge.py"]', bridge)
        self.assertIn("./nightingale/sso_bridge.py:/app/nightingale/sso_bridge.py:ro", bridge)

        self.assertIn("  nacos_mysql_data:", compose)
        self.assertIn("  nightingale_mysql_data:", compose)
        self.assertIn("  nightingale_redis_data:", compose)

        up_main = pathlib.Path("scripts/up-main.sh").read_text(encoding="utf-8")
        self.assertIn("render-nightingale-config", up_main)
        self.assertIn('--env-file "${ROOT_DIR}/.env"', up_main)
        self.assertIn('--output "${ROOT_DIR}/nightingale/config.toml"', up_main)

    def test_gateway_routes_include_new_hostnames(self) -> None:
        gateway = pathlib.Path("gateway/nginx.conf").read_text(encoding="utf-8")
        self.assertIn("server_name nacos.localhost;", gateway)
        self.assertIn("server_name nightingale.localhost;", gateway)
        self.assertNotIn("return 302 /nacos/;", gateway)
        self.assertIn("map $cookie_n9e_access_token $nightingale_cookie_auth {", gateway)
        self.assertIn('default "Bearer $cookie_n9e_access_token";', gateway)
        self.assertIn("map $nightingale_cookie_auth $nightingale_upstream_auth {", gateway)
        self.assertIn("set $upstream http://oauth2-proxy-nacos:4183;", gateway)
        self.assertIn("location = /callback {", gateway)
        self.assertIn("set $upstream http://nightingale-sso-bridge:18100/callback$is_args$args;", gateway)
        self.assertIn("proxy_set_header Authorization $nightingale_upstream_auth;", gateway)
        self.assertIn("location = /api/n9e/auth/login {", gateway)
        self.assertIn("proxy_pass http://nightingale-sso-bridge:18100/api/n9e/auth/login;", gateway)
        self.assertIn("location = /api/n9e/auth/refresh {", gateway)
        self.assertIn("proxy_pass http://nightingale-sso-bridge:18100/api/n9e/auth/refresh;", gateway)
        self.assertIn("set $upstream http://nightingale:17000;", gateway)

    def test_placeholder_config_files_match_task2_compose_defaults(self) -> None:
        nacos_config = pathlib.Path("nacos/application.properties").read_text(encoding="utf-8")
        self.assertIn("nacos.server.main.port=8848", nacos_config)
        self.assertIn("nacos.console.port=8080", nacos_config)
        self.assertIn("nacos.console.ui.enabled=true", nacos_config)
        self.assertIn("nacos.core.auth.enabled=false", nacos_config)
        self.assertIn("nacos.core.auth.console.enabled=false", nacos_config)
        self.assertIn("nacos.core.auth.server.identity.key=serverIdentity", nacos_config)
        self.assertIn("nacos.core.auth.server.identity.value=security", nacos_config)
        self.assertIn(
            "nacos.core.auth.plugin.nacos.token.secret.key=VGhpc0lzTXlDdXN0b21TZWNyZXRLZXkwMTIzNDU2Nzg=",
            nacos_config,
        )
        self.assertIn("db.user=nacos", nacos_config)
        self.assertIn("db.password=nacos-dev-password", nacos_config)
        self.assertIn("allowPublicKeyRetrieval=true", nacos_config)
        self.assertNotIn("${NACOS_DB_PASSWORD}", nacos_config)
        self.assertNotIn("nacos.core.auth.plugin.oidc.client-secret=nacos-client-secret", nacos_config)

        nacos_schema = pathlib.Path("nacos/mysql-schema.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE `config_info`", nacos_schema)

        nightingale_config = pathlib.Path("nightingale/config.toml").read_text(encoding="utf-8")
        self.assertIn('DBType = "mysql"', nightingale_config)
        self.assertIn(
            'DSN = "nightingale:nightingale-dev-password@tcp(nightingale-mysql:3306)/nightingale?charset=utf8mb4&parseTime=True&loc=Local"',
            nightingale_config,
        )
        self.assertIn('RedisType = "standalone"', nightingale_config)
        self.assertIn('Password = "nightingale-redis-dev-password"', nightingale_config)
        self.assertIn('[HTTP.JWTAuth]', nightingale_config)
        self.assertIn('AccessExpired = 1500', nightingale_config)
        self.assertIn('RefreshExpired = 10080', nightingale_config)
        self.assertIn('RedisKeyPrefix = "/jwt/"', nightingale_config)
        self.assertNotIn("${NIGHTINGALE_DB_PASSWORD}", nightingale_config)
        self.assertNotIn("${NIGHTINGALE_REDIS_PASSWORD}", nightingale_config)
        self.assertNotIn("${NIGHTINGALE_CLIENT_SECRET}", nightingale_config)

        bridge_code = pathlib.Path("nightingale/sso_bridge.py").read_text(encoding="utf-8")
        self.assertIn('UPSTREAM = os.environ.get("NIGHTINGALE_UPSTREAM", "http://nightingale:17000")', bridge_code)
        self.assertIn('Set-Cookie", f"n9e_access_token={access_token}; Path=/; SameSite=Lax"', bridge_code)
        self.assertIn('Set-Cookie", f"n9e_refresh_token={refresh_token}; Path=/; SameSite=Lax"', bridge_code)
        self.assertIn('Location", redirect if isinstance(redirect, str) else "/"', bridge_code)
        self.assertIn('if parsed.path in {"/api/n9e/auth/login", "/api/n9e/auth/refresh"}:', bridge_code)

    def test_nightingale_env_and_bootstrap_contract_use_explicit_secret(self) -> None:
        env_example = pathlib.Path(".env.example").read_text(encoding="utf-8")
        bootstrap = pathlib.Path("scripts/bootstrap-keycloak.sh").read_text(encoding="utf-8")

        self.assertIn("NIGHTINGALE_DB_PASSWORD=ChangeMe_Nightingale_Db_123!", env_example)
        self.assertIn("NIGHTINGALE_DB_ROOT_PASSWORD=ChangeMe_Nightingale_DbRoot_123!", env_example)
        self.assertIn("NIGHTINGALE_REDIS_PASSWORD=ChangeMe_Nightingale_Redis_123!", env_example)
        self.assertIn("NIGHTINGALE_CLIENT_SECRET=ChangeMe_Nightingale_Client_123!", env_example)
        self.assertIn('"${NIGHTINGALE_CLIENT_SECRET}" \\', bootstrap)
