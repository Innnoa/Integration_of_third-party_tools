import unittest
from datetime import datetime, timezone

from business_panel.models import ProbeResult, UnitSnapshot, UnitSummary
from business_panel.status_service import summarize_panel, summarize_unit


class StatusServiceTest(unittest.TestCase):
    def test_required_auth_failure_marks_unit_failed(self) -> None:
        snapshot = UnitSnapshot(
            unit_id="kafka_ui",
            display_name="KafkaUI",
            description="Kafka 可视化管理",
            entry_url="http://127.0.0.1:8082",
            auth_expectation="required",
            container=ProbeResult.ok("容器运行"),
            endpoint=ProbeResult.ok("入口可达"),
            auth=ProbeResult.fail("未跳转到 Keycloak"),
            available_actions=("start", "stop", "restart"),
        )

        summary = summarize_unit(snapshot)

        self.assertEqual(summary.overall_state, "failed")
        self.assertIn("认证", summary.failure_summary)

    def test_best_effort_auth_failure_marks_unit_degraded(self) -> None:
        snapshot = UnitSnapshot(
            unit_id="harbor",
            display_name="Harbor",
            description="镜像仓库与安全扫描",
            entry_url="http://127.0.0.1:8088",
            auth_expectation="best_effort",
            container=ProbeResult.ok("容器运行"),
            endpoint=ProbeResult.ok("入口可达"),
            auth=ProbeResult.fail("未发现 OIDC 入口"),
            available_actions=("start", "stop", "restart"),
        )

        summary = summarize_unit(snapshot)

        self.assertEqual(summary.overall_state, "degraded")

    def test_panel_totals_count_all_statuses(self) -> None:
        payload = summarize_panel(
            [
                UnitSnapshot(
                    unit_id="keycloak",
                    display_name="Keycloak",
                    description="统一认证中心",
                    entry_url="http://127.0.0.1:8080",
                    auth_expectation="required",
                    container=ProbeResult.ok("容器运行"),
                    endpoint=ProbeResult.ok("入口可达"),
                    auth=ProbeResult.ok("OIDC 元数据正常"),
                    available_actions=("start", "stop", "restart"),
                ),
                UnitSnapshot(
                    unit_id="harbor",
                    display_name="Harbor",
                    description="镜像仓库与安全扫描",
                    entry_url="http://127.0.0.1:8088",
                    auth_expectation="best_effort",
                    container=ProbeResult.not_installed("Harbor installer 缺失"),
                    endpoint=ProbeResult.not_installed("Harbor installer 缺失"),
                    auth=ProbeResult.not_installed("Harbor installer 缺失"),
                    available_actions=("start", "stop", "restart"),
                ),
            ]
        )

        self.assertEqual(payload["totals"]["healthy"], 1)
        self.assertEqual(payload["totals"]["not_installed"], 1)

    def test_not_installed_has_highest_priority(self) -> None:
        snapshot = UnitSnapshot(
            unit_id="harbor",
            display_name="Harbor",
            description="镜像仓库与安全扫描",
            entry_url="http://127.0.0.1:8088",
            auth_expectation="required",
            container=ProbeResult.not_installed("Harbor installer 缺失"),
            endpoint=ProbeResult.fail("入口不可达"),
            auth=ProbeResult.fail("认证失败"),
            available_actions=("start", "stop", "restart"),
        )

        summary = summarize_unit(snapshot)

        self.assertEqual(summary.overall_state, "not_installed")

    def test_failed_container_or_endpoint_marks_unit_failed(self) -> None:
        container_failed = UnitSnapshot(
            unit_id="mongo_express",
            display_name="Mongo Express",
            description="MongoDB 管理面板",
            entry_url="http://127.0.0.1:8089",
            auth_expectation="best_effort",
            container=ProbeResult.fail("容器未运行"),
            endpoint=ProbeResult.ok("入口可达"),
            auth=ProbeResult.ok("认证正常"),
            available_actions=("start", "stop", "restart"),
        )
        endpoint_failed = UnitSnapshot(
            unit_id="redisinsight",
            display_name="RedisInsight",
            description="Redis 管理面板",
            entry_url="http://127.0.0.1:8091",
            auth_expectation="best_effort",
            container=ProbeResult.ok("容器运行"),
            endpoint=ProbeResult.fail("入口不可达"),
            auth=ProbeResult.ok("认证正常"),
            available_actions=("start", "stop", "restart"),
        )

        self.assertEqual(summarize_unit(container_failed).overall_state, "failed")
        self.assertEqual(summarize_unit(endpoint_failed).overall_state, "failed")

    def test_warn_marks_unit_degraded(self) -> None:
        snapshot = UnitSnapshot(
            unit_id="portainer",
            display_name="Portainer",
            description="容器管理面板",
            entry_url="http://127.0.0.1:9000",
            auth_expectation="not_checked",
            container=ProbeResult.ok("容器运行"),
            endpoint=ProbeResult.warn("入口响应较慢"),
            auth=ProbeResult.ok("认证正常"),
            available_actions=("start", "stop", "restart"),
        )

        summary = summarize_unit(snapshot)

        self.assertEqual(summary.overall_state, "degraded")

    def test_failure_summary_defaults_to_normal(self) -> None:
        snapshot = UnitSnapshot(
            unit_id="keycloak",
            display_name="Keycloak",
            description="统一认证中心",
            entry_url="http://127.0.0.1:8080",
            auth_expectation="required",
            container=ProbeResult.ok("容器运行"),
            endpoint=ProbeResult.ok("入口可达"),
            auth=ProbeResult.ok("OIDC 元数据正常"),
            available_actions=("start", "stop", "restart"),
        )

        summary = summarize_unit(snapshot)

        self.assertEqual(summary.failure_summary, "状态正常")

    def test_panel_payload_has_required_shape(self) -> None:
        payload = summarize_panel(
            [
                UnitSnapshot(
                    unit_id="keycloak",
                    display_name="Keycloak",
                    description="统一认证中心",
                    entry_url="http://127.0.0.1:8080",
                    auth_expectation="required",
                    container=ProbeResult.ok("容器运行"),
                    endpoint=ProbeResult.ok("入口可达"),
                    auth=ProbeResult.ok("OIDC 元数据正常"),
                    available_actions=("start", "stop", "restart"),
                ),
            ]
        )

        self.assertIn("refreshed_at", payload)
        self.assertSetEqual(
            set(payload["totals"].keys()),
            {"healthy", "degraded", "failed", "not_installed", "total"},
        )
        self.assertEqual(len(payload["units"]), 1)
        unit = payload["units"][0]
        self.assertIn("container", unit)
        self.assertIn("endpoint", unit)
        self.assertIn("auth", unit)
        self.assertEqual(unit["open_url"], "http://127.0.0.1:8080")
        self.assertSetEqual(set(unit["container"].keys()), {"level", "summary"})
        self.assertSetEqual(set(unit["endpoint"].keys()), {"level", "summary"})
        self.assertSetEqual(set(unit["auth"].keys()), {"level", "summary"})

    def test_unit_summary_prefers_open_url_when_present(self) -> None:
        summary = summarize_unit(
            UnitSnapshot(
                unit_id="keycloak",
                display_name="Keycloak",
                description="统一认证中心",
                entry_url="http://auth.localhost",
                auth_expectation="required",
                container=ProbeResult.ok("容器运行"),
                endpoint=ProbeResult.ok("入口可达"),
                auth=ProbeResult.ok("OIDC 元数据正常"),
                available_actions=("start", "stop", "restart"),
                open_url="http://auth.localhost/realms/infra/account/",
            )
        )

        self.assertEqual(summary.open_url, "http://auth.localhost/realms/infra/account/")
        self.assertEqual(summary.to_dict()["open_url"], "http://auth.localhost/realms/infra/account/")

    def test_refreshed_at_is_parseable_utc_iso_timestamp(self) -> None:
        payload = summarize_panel(
            [
                UnitSnapshot(
                    unit_id="keycloak",
                    display_name="Keycloak",
                    description="统一认证中心",
                    entry_url="http://127.0.0.1:8080",
                    auth_expectation="required",
                    container=ProbeResult.ok("容器运行"),
                    endpoint=ProbeResult.ok("入口可达"),
                    auth=ProbeResult.ok("OIDC 元数据正常"),
                    available_actions=("start", "stop", "restart"),
                ),
            ]
        )

        refreshed_at = payload["refreshed_at"]
        self.assertIsInstance(refreshed_at, str)
        parsed = datetime.fromisoformat(refreshed_at)
        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.utcoffset(), timezone.utc.utcoffset(parsed))

    def test_panel_units_equal_summarize_unit_to_dict_results(self) -> None:
        snapshots = [
            UnitSnapshot(
                unit_id="keycloak",
                display_name="Keycloak",
                description="统一认证中心",
                entry_url="http://127.0.0.1:8080",
                auth_expectation="required",
                container=ProbeResult.ok("容器运行"),
                endpoint=ProbeResult.ok("入口可达"),
                auth=ProbeResult.ok("OIDC 元数据正常"),
                available_actions=("start", "stop", "restart"),
            ),
            UnitSnapshot(
                unit_id="harbor",
                display_name="Harbor",
                description="镜像仓库与安全扫描",
                entry_url="http://127.0.0.1:8088",
                auth_expectation="best_effort",
                container=ProbeResult.warn("容器状态不稳定"),
                endpoint=ProbeResult.ok("入口可达"),
                auth=ProbeResult.fail("未发现 OIDC 入口"),
                available_actions=("start", "stop", "restart"),
            ),
        ]
        expected_units = [summarize_unit(snapshot).to_dict() for snapshot in snapshots]

        payload = summarize_panel(snapshots)

        self.assertEqual(payload["units"], expected_units)

    def test_invalid_probe_level_or_auth_expectation_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "level"):
            ProbeResult(level="broken", summary="非法状态")

        with self.assertRaisesRegex(ValueError, "auth_expectation"):
            UnitSnapshot(
                unit_id="bad_unit",
                display_name="Bad Unit",
                description="非法认证期望",
                entry_url="http://127.0.0.1:9999",
                auth_expectation="optional",
                container=ProbeResult.ok("容器运行"),
                endpoint=ProbeResult.ok("入口可达"),
                auth=ProbeResult.ok("认证正常"),
                available_actions=("start", "stop", "restart"),
            )

    def test_failure_summary_concatenates_multiple_non_ok_in_fixed_order(self) -> None:
        snapshot = UnitSnapshot(
            unit_id="kafka_ui",
            display_name="KafkaUI",
            description="Kafka 可视化管理",
            entry_url="http://127.0.0.1:8082",
            auth_expectation="required",
            container=ProbeResult.fail("容器未启动"),
            endpoint=ProbeResult.warn("入口响应较慢"),
            auth=ProbeResult.fail("未跳转到 Keycloak"),
            available_actions=("start", "stop", "restart"),
        )

        summary = summarize_unit(snapshot)

        self.assertEqual(
            summary.failure_summary,
            "容器: 容器未启动；入口: 入口响应较慢；认证: 未跳转到 Keycloak",
        )

    def test_invalid_unit_summary_overall_state_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "overall_state"):
            UnitSummary(
                unit_id="keycloak",
                display_name="Keycloak",
                description="统一认证中心",
                entry_url="http://127.0.0.1:8080",
                open_url="http://127.0.0.1:8080",
                auth_expectation="required",
                container=ProbeResult.ok("容器运行"),
                endpoint=ProbeResult.ok("入口可达"),
                auth=ProbeResult.ok("OIDC 元数据正常"),
                overall_state="unknown",  # type: ignore[arg-type]
                failure_summary="状态正常",
                available_actions=("start", "stop", "restart"),
            )


if __name__ == "__main__":
    unittest.main()
