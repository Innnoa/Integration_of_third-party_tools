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
        self.assertIn("  nightingale:", compose)
        self.assertIn("  nightingale-mysql:", compose)
        self.assertIn("  nightingale-redis:", compose)

        nacos_mysql = self._service_block(compose, "nacos-mysql")
        self.assertIn("image: ${NACOS_MYSQL_IMAGE:-mysql:8.4}", nacos_mysql)
        self.assertIn("MYSQL_PASSWORD: ${NACOS_DB_PASSWORD:-nacos-dev-password}", nacos_mysql)
        self.assertIn("MYSQL_ROOT_PASSWORD: ${NACOS_DB_ROOT_PASSWORD:-nacos-root-dev-password}", nacos_mysql)
        self.assertIn("./nacos/mysql-schema.sql:/docker-entrypoint-initdb.d/01-nacos-schema.sql:ro", nacos_mysql)
        self.assertIn("healthcheck:", nacos_mysql)
        self.assertIn("mysqladmin ping", nacos_mysql)

        nacos = self._service_block(compose, "nacos")
        self.assertIn("image: ${NACOS_IMAGE:-nacos/nacos-server:latest}", nacos)
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
        self.assertIn("./nightingale/config.toml:/app/etc/config.toml:ro", nightingale)
        self.assertIn("condition: service_healthy", nightingale)

        self.assertIn("  nacos_mysql_data:", compose)
        self.assertIn("  nightingale_mysql_data:", compose)
        self.assertIn("  nightingale_redis_data:", compose)

    def test_gateway_routes_include_new_hostnames(self) -> None:
        gateway = pathlib.Path("gateway/nginx.conf").read_text(encoding="utf-8")
        self.assertIn("server_name nacos.localhost;", gateway)
        self.assertIn("server_name nightingale.localhost;", gateway)
        self.assertIn("set $upstream http://nacos:8080;", gateway)
        self.assertIn("set $upstream http://nightingale:17000;", gateway)

    def test_placeholder_config_files_match_task2_compose_defaults(self) -> None:
        nacos_config = pathlib.Path("nacos/application.properties").read_text(encoding="utf-8")
        self.assertIn("server.port=8080", nacos_config)
        self.assertIn("db.user=nacos", nacos_config)
        self.assertIn("db.password=nacos-dev-password", nacos_config)
        self.assertIn("allowPublicKeyRetrieval=true", nacos_config)
        self.assertNotIn("${NACOS_DB_PASSWORD}", nacos_config)
        self.assertNotIn("${NACOS_CLIENT_SECRET}", nacos_config)

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
        self.assertNotIn("${NIGHTINGALE_DB_PASSWORD}", nightingale_config)
        self.assertNotIn("${NIGHTINGALE_REDIS_PASSWORD}", nightingale_config)
        self.assertNotIn("${NIGHTINGALE_CLIENT_SECRET}", nightingale_config)
