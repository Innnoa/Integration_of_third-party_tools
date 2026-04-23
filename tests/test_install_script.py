import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("INSTALL_REQUIRED_COMMANDS", "python3")


def stage_install_scripts(root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    shutil.copy2(repo_root / "install.sh", root / "install.sh")
    shutil.copy2(repo_root / "scripts" / "install-lib.sh", root / "scripts" / "install-lib.sh")
    write_executable(
        root / "scripts" / "install_helper.py",
        """#!/usr/bin/env python3
import pathlib
import sys

argv = sys.argv[1:]
if argv[0] == "detect-public-ip":
    print("127.0.0.1")
elif argv[0] == "sync-hosts":
    pathlib.Path(argv[argv.index("--hosts-file") + 1]).write_text("managed-hosts\\n", encoding="utf-8")
elif argv[0] == "configure-portainer":
    print("configured")
elif argv[0] == "verify-install":
    print('{"overall":"ready","checks":[]}')
elif argv[0] == "render-nightingale-config":
    pathlib.Path(argv[argv.index("--output") + 1]).write_text("[generated]\\n", encoding="utf-8")
else:
    raise SystemExit(argv)
""",
    )


def stage_successful_runtime_scripts(root: Path, panel_content: str = "#!/usr/bin/env bash\nexit 0\n") -> None:
    stage_contents = {
        "init-network.sh": "#!/usr/bin/env bash\nexit 0\n",
        "up-main.sh": "#!/usr/bin/env bash\nexit 0\n",
        "repair-mariadb-phpmyadmin-user.sh": "#!/usr/bin/env bash\nexit 0\n",
        "prepare-harbor.sh": "#!/usr/bin/env bash\nexit 0\n",
        "bootstrap-keycloak.sh": "#!/usr/bin/env bash\nexit 0\n",
        "panel.sh": panel_content,
    }
    for name, content in stage_contents.items():
        write_executable(root / "scripts" / name, content)


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def parse_env(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


class InstallScriptTest(unittest.TestCase):
    def test_install_apt_prefers_docker_compose_plugin_package_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")

            fakebin = root / "fakebin"
            fakebin.mkdir()
            install_log = root / "deps.log"
            write_executable(
                fakebin / "docker",
                "#!/usr/bin/env bash\n"
                "if [ \"$1\" = \"compose\" ] && [ \"$2\" = \"version\" ]; then\n"
                "  exit 1\n"
                "fi\n"
                "exit 0\n",
            )
            write_executable(
                fakebin / "sudo",
                "#!/usr/bin/env bash\n"
                "\"$@\"\n",
            )
            write_executable(
                fakebin / "apt-get",
                "#!/usr/bin/env bash\n"
                "echo apt-get:$* >> \"$INSTALL_LOG\"\n"
                "if [ \"$1\" = \"install\" ]; then\n"
                "  shift 2\n"
                "  if [ \"$1\" = \"docker-compose-plugin\" ]; then\n"
                "    cat > \"$INSTALL_FAKEBIN/docker\" <<'EOF'\n"
                "#!/usr/bin/env bash\n"
                "if [ \"$1\" = \"compose\" ] && [ \"$2\" = \"version\" ]; then\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n"
                "EOF\n"
                "    chmod +x \"$INSTALL_FAKEBIN/docker\"\n"
                "    exit 0\n"
                "  fi\n"
                "fi\n"
                "exit 1\n",
            )
            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel", "--skip-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "PATH": f"{fakebin}:{os.environ['PATH']}",
                    "INSTALL_LOG": str(install_log),
                    "INSTALL_FAKEBIN": str(fakebin),
                    "INSTALL_REQUIRED_COMMANDS": "docker-compose-plugin",
                    "INSTALL_PACKAGE_MANAGER": "apt-get",
                },
            )
            log_text = install_log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0)
        self.assertIn("apt-get:install -y docker-compose-plugin", log_text)

    def test_install_apt_falls_back_to_docker_compose_v2_when_plugin_package_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")

            fakebin = root / "fakebin"
            fakebin.mkdir()
            install_log = root / "deps.log"
            write_executable(
                fakebin / "docker",
                "#!/usr/bin/env bash\n"
                "if [ \"$1\" = \"compose\" ] && [ \"$2\" = \"version\" ]; then\n"
                "  exit 1\n"
                "fi\n"
                "exit 0\n",
            )
            write_executable(
                fakebin / "sudo",
                "#!/usr/bin/env bash\n"
                "\"$@\"\n",
            )
            write_executable(
                fakebin / "apt-get",
                "#!/usr/bin/env bash\n"
                "echo apt-get:$* >> \"$INSTALL_LOG\"\n"
                "if [ \"$1\" = \"install\" ]; then\n"
                "  shift 2\n"
                "  if [ \"$1\" = \"docker-compose-plugin\" ]; then\n"
                "    exit 100\n"
                "  fi\n"
                "  if [ \"$1\" = \"docker-compose-v2\" ]; then\n"
                "    cat > \"$INSTALL_FAKEBIN/docker\" <<'EOF'\n"
                "#!/usr/bin/env bash\n"
                "if [ \"$1\" = \"compose\" ] && [ \"$2\" = \"version\" ]; then\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n"
                "EOF\n"
                "    chmod +x \"$INSTALL_FAKEBIN/docker\"\n"
                "    exit 0\n"
                "  fi\n"
                "fi\n"
                "exit 1\n",
            )
            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel", "--skip-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "PATH": f"{fakebin}:{os.environ['PATH']}",
                    "INSTALL_LOG": str(install_log),
                    "INSTALL_FAKEBIN": str(fakebin),
                    "INSTALL_REQUIRED_COMMANDS": "docker-compose-plugin",
                    "INSTALL_PACKAGE_MANAGER": "apt-get",
                },
            )
            log_text = install_log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0)
        self.assertIn("apt-get:install -y docker-compose-plugin", log_text)
        self.assertIn("apt-get:install -y docker-compose-v2", log_text)

    def test_install_apt_falls_back_to_docker_compose_package_when_v2_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")

            fakebin = root / "fakebin"
            fakebin.mkdir()
            install_log = root / "deps.log"
            write_executable(
                fakebin / "docker",
                "#!/usr/bin/env bash\n"
                "if [ \"$1\" = \"compose\" ] && [ \"$2\" = \"version\" ]; then\n"
                "  exit 1\n"
                "fi\n"
                "exit 0\n",
            )
            write_executable(
                fakebin / "sudo",
                "#!/usr/bin/env bash\n"
                "\"$@\"\n",
            )
            write_executable(
                fakebin / "apt-get",
                "#!/usr/bin/env bash\n"
                "echo apt-get:$* >> \"$INSTALL_LOG\"\n"
                "if [ \"$1\" = \"install\" ]; then\n"
                "  shift 2\n"
                "  if [ \"$1\" = \"docker-compose-plugin\" ] || [ \"$1\" = \"docker-compose-v2\" ]; then\n"
                "    exit 100\n"
                "  fi\n"
                "  if [ \"$1\" = \"docker-compose\" ]; then\n"
                "    cat > \"$INSTALL_FAKEBIN/docker\" <<'EOF'\n"
                "#!/usr/bin/env bash\n"
                "if [ \"$1\" = \"compose\" ] && [ \"$2\" = \"version\" ]; then\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n"
                "EOF\n"
                "    chmod +x \"$INSTALL_FAKEBIN/docker\"\n"
                "    exit 0\n"
                "  fi\n"
                "fi\n"
                "exit 1\n",
            )
            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel", "--skip-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "PATH": f"{fakebin}:{os.environ['PATH']}",
                    "INSTALL_LOG": str(install_log),
                    "INSTALL_FAKEBIN": str(fakebin),
                    "INSTALL_REQUIRED_COMMANDS": "docker-compose-plugin",
                    "INSTALL_PACKAGE_MANAGER": "apt-get",
                },
            )
            log_text = install_log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0)
        self.assertIn("apt-get:install -y docker-compose-plugin", log_text)
        self.assertIn("apt-get:install -y docker-compose-v2", log_text)
        self.assertIn("apt-get:install -y docker-compose", log_text)

    def test_install_auto_installs_missing_dependencies_with_supported_package_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")

            fakebin = root / "fakebin"
            fakebin.mkdir()
            install_log = root / "deps.log"
            write_executable(
                fakebin / "sudo",
                "#!/usr/bin/env bash\n"
                "echo sudo:$* >> \"$INSTALL_LOG\"\n"
                "\"$@\"\n",
            )
            write_executable(
                fakebin / "apt-get",
                "#!/usr/bin/env bash\n"
                "echo apt-get:$* >> \"$INSTALL_LOG\"\n"
                "if [ \"$1\" = \"install\" ]; then\n"
                "  : > \"$INSTALL_FAKEBIN/fakecmd\"\n"
                "  chmod +x \"$INSTALL_FAKEBIN/fakecmd\"\n"
                "fi\n",
            )
            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel", "--skip-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "PATH": f"{fakebin}:{os.environ['PATH']}",
                    "INSTALL_LOG": str(install_log),
                    "INSTALL_FAKEBIN": str(fakebin),
                    "INSTALL_REQUIRED_COMMANDS": "fakecmd",
                    "INSTALL_PACKAGE_MANAGER": "apt-get",
                },
            )
            log_text = install_log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0)
        self.assertIn("apt-get:update", log_text)
        self.assertIn("apt-get:install -y", log_text)

    def test_install_retries_main_stack_before_failing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")
            log_file = root / "up-main.log"
            write_executable(root / "scripts" / "init-network.sh", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(
                root / "scripts" / "up-main.sh",
                "#!/usr/bin/env bash\n"
                "count=0\n"
                "if [ -f \"$INSTALL_LOG\" ]; then count=$(wc -l < \"$INSTALL_LOG\"); fi\n"
                "count=$((count+1))\n"
                "printf 'up-main\\n' >> \"$INSTALL_LOG\"\n"
                "if [ \"$count\" -lt 2 ]; then exit 23; fi\n"
                "exit 0\n",
            )
            for name in ("repair-mariadb-phpmyadmin-user.sh", "bootstrap-keycloak.sh"):
                write_executable(root / "scripts" / name, "#!/usr/bin/env bash\nexit 0\n")
            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel", "--skip-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "INSTALL_LOG": str(log_file)},
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("RETRY: main_stack", result.stdout + result.stderr)

    def test_install_prints_overall_and_stage_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel", "--skip-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Result:", result.stdout)
        self.assertIn("overall=success", result.stdout)
        self.assertIn("preflight=ok", result.stdout)
        self.assertIn("verify=ok", result.stdout)

    def test_install_requires_base_domain_for_default_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            write_executable(
                root / "scripts" / "install_helper.py",
                "#!/usr/bin/env python3\nprint('127.0.0.1')\n",
            )
            (root / ".env.example").write_text(
                "PUBLIC_SCHEME=http\nPUBLIC_HOST=REPLACE_ME_PUBLIC_HOST\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["bash", "install.sh"],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--base-domain", result.stderr + result.stdout)

    def test_install_base_domain_derives_public_hosts_and_public_ip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            hosts_file = root / "hosts"
            write_executable(
                root / "scripts" / "install_helper.py",
                """#!/usr/bin/env python3
import pathlib
import sys

argv = sys.argv[1:]
if argv[0] == "detect-public-ip":
    print("192.168.50.10")
elif argv[0] == "sync-hosts":
    target = pathlib.Path(argv[argv.index("--hosts-file") + 1])
    target.write_text("managed-hosts\\n", encoding="utf-8")
elif argv[0] == "configure-portainer":
    print("configure-portainer:ok")
elif argv[0] == "verify-install":
    print('{"overall":"ready","checks":[]}')
else:
    raise SystemExit(f"unexpected args: {argv}")
""",
            )
            (root / ".env.example").write_text(
                "PUBLIC_SCHEME=http\n"
                "PUBLIC_HOST=REPLACE_ME_PUBLIC_HOST\n"
                "BROWSER_HOST=localhost\n"
                "KAFKA_HOST_BOOTSTRAP_SERVER=REPLACE_ME_PUBLIC_HOST:9092\n"
                "KEYCLOAK_REALM=infra\n"
                "PORTAINER_CLIENT_ID=portainer\n"
                "PORTAINER_CLIENT_SECRET=portainer-secret\n"
                "PORTAINER_ADMIN_USER=admin\n"
                "PORTAINER_ADMIN_PASSWORD=StrongPassword_123\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["bash", "install.sh", "--base-domain", "dev.example", "--skip-panel"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "INSTALL_HOSTS_FILE": str(hosts_file)},
            )

            env_map = parse_env((root / ".env").read_text(encoding="utf-8"))
            hosts_text = hosts_file.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(env_map["PUBLIC_HOST"], "192.168.50.10")
        self.assertEqual(env_map["KAFKA_HOST_BOOTSTRAP_SERVER"], "192.168.50.10:9092")
        self.assertEqual(env_map["KEYCLOAK_PUBLIC_HOST"], "auth.dev.example")
        self.assertEqual(env_map["PORTAINER_PUBLIC_HOST"], "portainer.dev.example")
        self.assertEqual(env_map["NACOS_PUBLIC_HOST"], "nacos.dev.example")
        self.assertEqual(env_map["NIGHTINGALE_PUBLIC_HOST"], "nightingale.dev.example")
        self.assertEqual(env_map["BROWSER_HOST"], "localhost")
        self.assertEqual(hosts_text, "managed-hosts\n")

    def test_install_summary_uses_current_env_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\nexit 0\n")
            (root / ".env.example").write_text(
                "\n".join(
                    [
                        "PUBLIC_HOST=public.example",
                        "KEYCLOAK_PUBLIC_HOST=auth.dev.local",
                        "PORTAINER_PUBLIC_HOST=portainer.dev.local",
                        "KAFKA_UI_PUBLIC_HOST=kafka.dev.local",
                        "REDISINSIGHT_PUBLIC_HOST=redis.dev.local",
                        "PHPMYADMIN_PUBLIC_HOST=pma.dev.local",
                        "MONGO_EXPRESS_PUBLIC_HOST=mongo.dev.local",
                        "HARBOR_PUBLIC_HOST=harbor.dev.local",
                        "BUSINESS_PANEL_HOST=panel.dev.local",
                        "BUSINESS_PANEL_PORT=18090",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["bash", "install.sh", "--with-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0)
        for expected in (
            "http://auth.dev.local",
            "http://portainer.dev.local",
            "http://kafka.dev.local",
            "http://redis.dev.local",
            "http://pma.dev.local",
            "http://mongo.dev.local",
            "http://harbor.dev.local",
            "http://panel.dev.local:18090",
            "auth.dev.local",
            "harbor.dev.local",
        ):
            self.assertIn(expected, result.stdout)
        for unexpected in ("http://auth.localhost", "http://harbor.localhost", "http://127.0.0.1:8090"):
            self.assertNotIn(unexpected, result.stdout)

    def test_install_prints_final_access_summary_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / ".env.example").write_text("PUBLIC_HOST=public.example\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", "install.sh"],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0)
        for expected in (
            "http://auth.localhost",
            "http://portainer.localhost",
            "http://kafka.localhost",
            "http://redis.localhost",
            "http://pma.localhost",
            "http://mongo.localhost",
            "http://127.0.0.1:8090",
            "PUBLIC_HOST:9092",
            "public.example:9092",
            "Next:",
            "Windows hosts",
            "auth.localhost",
            "portainer.localhost",
        ):
            self.assertIn(expected, result.stdout)
        self.assertNotIn("http://harbor.localhost", result.stdout)
        self.assertNotIn("harbor.localhost", result.stdout)

    def test_install_summary_omits_panel_when_skip_panel_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / ".env.example").write_text("PUBLIC_HOST=public.example\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel"],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0)
        self.assertNotIn("http://127.0.0.1:8090", result.stdout)
        self.assertNotIn("verify the panel", result.stdout)
        self.assertNotIn("panel plus Kafka", result.stdout)
        self.assertNotIn("http://harbor.localhost", result.stdout)
        self.assertIn("PUBLIC_HOST:9092", result.stdout)

    def test_install_summary_omits_harbor_when_skip_harbor_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / ".env.example").write_text("PUBLIC_HOST=public.example\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", "install.sh", "--skip-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0)
        self.assertNotIn("http://harbor.localhost", result.stdout)
        self.assertNotIn("harbor.localhost", result.stdout)
        self.assertIn("http://127.0.0.1:8090", result.stdout)
        self.assertIn("PUBLIC_HOST:9092", result.stdout)

    def test_install_with_harbor_fails_when_harbor_installer_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", "install.sh", "--with-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("harbor/installer", result.stderr + result.stdout)

    def test_install_creates_env_from_example_when_preflight_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / ".env.example").write_text("PUBLIC_HOST=example.local\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", "install.sh"],
                cwd=root,
                capture_output=True,
                text=True,
            )

            env_text = (root / ".env").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0)
        self.assertIn("PUBLIC_HOST=example.local", env_text)

    def test_install_skip_harbor_allows_env_creation_without_harbor_installer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", "install.sh", "--skip-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
            )

            env_text = (root / ".env").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0)
        self.assertIn("PUBLIC_SCHEME=http", env_text)

    def test_install_skip_harbor_skips_prepare_and_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            log_file = root / "run.log"
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")
            for name in ("init-network.sh", "up-main.sh", "repair-mariadb-phpmyadmin-user.sh", "bootstrap-keycloak.sh", "panel.sh"):
                write_executable(root / "scripts" / name, f"#!/usr/bin/env bash\necho {name} >> \"$INSTALL_LOG\"\n")
            write_executable(root / "scripts" / "prepare-harbor.sh", "#!/usr/bin/env bash\necho harbor-prepare-ran >> \"$INSTALL_LOG\"\n")
            result = subprocess.run(
                ["bash", "install.sh", "--skip-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "INSTALL_LOG": str(log_file)},
            )
            lines = log_file.read_text(encoding="utf-8").splitlines() if log_file.exists() else []

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            lines,
            ["init-network.sh", "up-main.sh", "repair-mariadb-phpmyadmin-user.sh", "bootstrap-keycloak.sh", "panel.sh"],
        )
        self.assertIn("[6/12] repair", result.stdout)
        self.assertIn("OK: repair", result.stdout)
        self.assertIn("[7/12] harbor_prepare", result.stdout)
        self.assertIn("SKIP: harbor_prepare", result.stdout)
        self.assertIn("[8/12] harbor_install", result.stdout)
        self.assertIn("SKIP: harbor_install", result.stdout)

    def test_install_preserves_existing_secrets_on_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\nexit 0\n")
            (root / ".env.example").write_text(
                "PUBLIC_SCHEME=http\nPUBLIC_HOST=REPLACE_ME_PUBLIC_HOST\nKEYCLOAK_ADMIN_PASSWORD=ChangeMe\n",
                encoding="utf-8",
            )
            (root / ".env").write_text(
                "PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\nKEYCLOAK_ADMIN_PASSWORD=keep-me\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel", "--skip-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
            )

            env_text = (root / ".env").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0)
        self.assertIn("KEYCLOAK_ADMIN_PASSWORD=keep-me", env_text)

    def test_install_generates_secret_values_for_missing_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\nexit 0\n")
            (root / ".env.example").write_text(
                "PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\nKEYCLOAK_ADMIN_PASSWORD=ChangeMe_Keycloak_Admin_123!\nOAUTH2_PROXY_COOKIE_SECRET=REPLACE_WITH_32_BYTE_SECRET\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel", "--skip-harbor"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            env_text = (root / ".env").read_text(encoding="utf-8")
            env_map = parse_env(env_text)

        self.assertNotIn("ChangeMe_Keycloak_Admin_123!", env_text)
        self.assertNotIn("REPLACE_WITH_32_BYTE_SECRET", env_text)
        self.assertIn("KEYCLOAK_ADMIN_PASSWORD", env_map)
        self.assertIn("OAUTH2_PROXY_COOKIE_SECRET", env_map)
        self.assertGreaterEqual(len(env_map["KEYCLOAK_ADMIN_PASSWORD"]), 24)
        self.assertRegex(env_map["OAUTH2_PROXY_COOKIE_SECRET"], r"^[0-9a-f]{32}$")

    def test_install_adds_phpmyadmin_autologin_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\nexit 0\n")
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\n", encoding="utf-8")

            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel", "--skip-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
            )
            env_map = parse_env((root / ".env").read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(env_map["PHPMYADMIN_ALLOWED_GROUP"], "/platform-admins")
        self.assertEqual(env_map["PHPMYADMIN_AUTOLOGIN_USER"], "pma_appdb_admin")

    def test_install_generates_phpmyadmin_autologin_password_when_placeholder_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\nexit 0\n")
            (root / ".env.example").write_text(
                "PUBLIC_SCHEME=http\nPHPMYADMIN_AUTOLOGIN_PASSWORD=ChangeMe_PhpMyAdmin_Autologin_123!\n",
                encoding="utf-8",
            )

            subprocess.run(
                ["bash", "install.sh", "--skip-panel", "--skip-harbor"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            env_map = parse_env((root / ".env").read_text(encoding="utf-8"))

        self.assertIn("PHPMYADMIN_AUTOLOGIN_PASSWORD", env_map)
        self.assertNotEqual(env_map["PHPMYADMIN_AUTOLOGIN_PASSWORD"], "ChangeMe_PhpMyAdmin_Autologin_123!")
        self.assertGreaterEqual(len(env_map["PHPMYADMIN_AUTOLOGIN_PASSWORD"]), 24)

    def test_install_adds_default_hosts_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\nexit 0\n")
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel", "--skip-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
            )

            env_map = parse_env((root / ".env").read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0)
        self.assertEqual(env_map["KEYCLOAK_PUBLIC_HOST"], "auth.localhost")
        self.assertEqual(env_map["PORTAINER_PUBLIC_HOST"], "portainer.localhost")
        self.assertEqual(env_map["BUSINESS_PANEL_HOST"], "127.0.0.1")
        self.assertEqual(env_map["BUSINESS_PANEL_PORT"], "8090")

    def test_install_appends_missing_key_when_env_has_no_trailing_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\n", encoding="utf-8")
            (root / ".env").write_text("PUBLIC_SCHEME=http", encoding="utf-8")
            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel", "--skip-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
            )

            env_text = (root / ".env").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0)
        self.assertIn("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\nBROWSER_HOST=localhost\nKEYCLOAK_PUBLIC_HOST=auth.localhost\n", env_text)

    def test_install_runs_portainer_configuration_after_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            log_file = root / "run.log"
            hosts_file = root / "hosts"
            write_executable(
                root / "scripts" / "install_helper.py",
                """#!/usr/bin/env python3
import os
import pathlib
import sys

log = pathlib.Path(os.environ["INSTALL_LOG"]) if os.environ.get("INSTALL_LOG") else None
cmd = sys.argv[1]
if cmd == "detect-public-ip":
    print("192.168.50.10")
elif cmd == "sync-hosts":
    pathlib.Path(sys.argv[sys.argv.index("--hosts-file") + 1]).write_text("managed-hosts\\n", encoding="utf-8")
elif cmd == "configure-portainer":
    if log:
        previous = log.read_text(encoding="utf-8") if log.exists() else ""
        log.write_text(previous + "configure-portainer\\n", encoding="utf-8")
elif cmd == "verify-install":
    print('{"overall":"ready"}')
else:
    raise SystemExit(cmd)
""",
            )
            for name in ("init-network.sh", "up-main.sh", "repair-mariadb-phpmyadmin-user.sh", "bootstrap-keycloak.sh"):
                write_executable(root / "scripts" / name, f"#!/usr/bin/env bash\necho {name} >> \"$INSTALL_LOG\"\n")
            write_executable(root / "scripts" / "panel.sh", "#!/usr/bin/env bash\necho panel.sh >> \"$INSTALL_LOG\"\n")
            (root / ".env.example").write_text(
                "PUBLIC_SCHEME=http\n"
                "PUBLIC_HOST=REPLACE_ME_PUBLIC_HOST\n"
                "BROWSER_HOST=localhost\n"
                "KEYCLOAK_REALM=infra\n"
                "PORTAINER_CLIENT_ID=portainer\n"
                "PORTAINER_CLIENT_SECRET=portainer-secret\n"
                "PORTAINER_ADMIN_USER=admin\n"
                "PORTAINER_ADMIN_PASSWORD=StrongPassword_123\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["bash", "install.sh", "--base-domain", "dev.example", "--skip-panel"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "INSTALL_LOG": str(log_file), "INSTALL_HOSTS_FILE": str(hosts_file)},
            )

            lines = log_file.read_text(encoding="utf-8").splitlines()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(lines[-2:], ["bootstrap-keycloak.sh", "configure-portainer"])

    def test_install_prints_verification_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            stage_successful_runtime_scripts(root)
            hosts_file = root / "hosts"
            write_executable(
                root / "scripts" / "install_helper.py",
                """#!/usr/bin/env python3
import pathlib
import sys

argv = sys.argv[1:]
if argv[0] == "detect-public-ip":
    print("192.168.50.10")
elif argv[0] == "sync-hosts":
    pathlib.Path(argv[argv.index("--hosts-file") + 1]).write_text("managed-hosts\\n", encoding="utf-8")
elif argv[0] == "configure-portainer":
    print("configured")
elif argv[0] == "verify-install":
    print('{"overall":"ready","checks":[{"host":"kafka.dev.example","result":"ready"}]}')
else:
    raise SystemExit(argv)
""",
            )
            (root / ".env.example").write_text(
                "PUBLIC_SCHEME=http\n"
                "PUBLIC_HOST=REPLACE_ME_PUBLIC_HOST\n"
                "BROWSER_HOST=localhost\n"
                "KEYCLOAK_REALM=infra\n"
                "PORTAINER_CLIENT_ID=portainer\n"
                "PORTAINER_CLIENT_SECRET=portainer-secret\n"
                "PORTAINER_ADMIN_USER=admin\n"
                "PORTAINER_ADMIN_PASSWORD=StrongPassword_123\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["bash", "install.sh", "--base-domain", "dev.example", "--skip-panel"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "INSTALL_HOSTS_FILE": str(hosts_file)},
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Verification:", result.stdout)
        self.assertIn("overall=ready", result.stdout)
        self.assertIn("kafka.dev.example", result.stdout)

    def test_install_runs_existing_scripts_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(
                root / "harbor" / "installer" / "install.sh",
                "#!/usr/bin/env bash\necho harbor-install >> \"$INSTALL_LOG\"\n",
            )
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")
            log_file = root / "run.log"
            for name in (
                "init-network.sh",
                "up-main.sh",
                "repair-mariadb-phpmyadmin-user.sh",
                "prepare-harbor.sh",
                "bootstrap-keycloak.sh",
                "panel.sh",
            ):
                write_executable(root / "scripts" / name, f"#!/usr/bin/env bash\necho {name} >> \"$INSTALL_LOG\"\n")
            result = subprocess.run(
                ["bash", "install.sh", "--with-harbor"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "INSTALL_LOG": str(log_file)},
            )
            lines = log_file.read_text(encoding="utf-8").splitlines() if log_file.exists() else []
            output_lines = [line for line in result.stdout.splitlines() if line.startswith("[") or line.startswith("OK:")]

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            output_lines,
            [
                "[1/12] preflight",
                "OK: preflight",
                "[2/12] deps",
                "OK: deps",
                "[3/12] env",
                "OK: env",
                "[4/12] network",
                "OK: network",
                "[5/12] main_stack",
                "OK: main_stack",
                "[6/12] repair",
                "OK: repair",
                "[7/12] harbor_prepare",
                "OK: harbor_prepare",
                "[8/12] harbor_install",
                "OK: harbor_install",
                "[9/12] bootstrap",
                "OK: bootstrap",
                "[10/12] configure",
                "OK: configure",
                "[11/12] panel",
                "OK: panel",
                "[12/12] verify",
                "OK: verify",
            ],
        )
        self.assertEqual(
            lines,
            [
                "init-network.sh",
                "up-main.sh",
                "repair-mariadb-phpmyadmin-user.sh",
                "prepare-harbor.sh",
                "harbor-install",
                "bootstrap-keycloak.sh",
                "panel.sh",
            ],
        )

    def test_install_skips_panel_when_flag_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\nexit 0\n")
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")
            panel_script = root / "scripts" / "panel.sh"
            write_executable(panel_script, "#!/usr/bin/env bash\necho panel-stage-ran\n")
            write_executable(root / "scripts" / "up-main.sh", "#!/usr/bin/env bash\nexit 0\n")
            for name in ("init-network.sh", "repair-mariadb-phpmyadmin-user.sh", "prepare-harbor.sh", "bootstrap-keycloak.sh"):
                write_executable(root / "scripts" / name, "#!/usr/bin/env bash\nexit 0\n")
            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel"],
                cwd=root,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0)
        self.assertNotIn("panel-stage-ran", result.stdout)

    def test_install_logs_phase_markers_and_status_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")
            for name in ("init-network.sh", "up-main.sh", "repair-mariadb-phpmyadmin-user.sh", "prepare-harbor.sh", "bootstrap-keycloak.sh"):
                write_executable(root / "scripts" / name, "#!/usr/bin/env bash\nexit 0\n")
            result = subprocess.run(
                ["bash", "install.sh", "--skip-panel"],
                cwd=root,
                capture_output=True,
                text=True,
            )
            relevant_lines = [
                line
                for line in result.stdout.splitlines()
                if line.startswith("[") or line.startswith("OK:") or line.startswith("SKIP:")
            ]

        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            relevant_lines,
            [
                "[1/12] preflight",
                "OK: preflight",
                "[2/12] deps",
                "OK: deps",
                "[3/12] env",
                "OK: env",
                "[4/12] network",
                "OK: network",
                "[5/12] main_stack",
                "OK: main_stack",
                "[6/12] repair",
                "OK: repair",
                "[7/12] harbor_prepare",
                "SKIP: harbor_prepare",
                "[8/12] harbor_install",
                "SKIP: harbor_install",
                "[9/12] bootstrap",
                "OK: bootstrap",
                "[10/12] configure",
                "OK: configure",
                "[11/12] panel",
                "SKIP: panel",
                "[12/12] verify",
                "OK: verify",
            ],
        )

    def test_install_stops_after_failed_phase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_install_scripts(root)
            log_file = root / "run.log"
            (root / "harbor" / "installer").mkdir(parents=True)
            write_executable(root / "harbor" / "installer" / "install.sh", "#!/usr/bin/env bash\necho harbor-install >> \"$INSTALL_LOG\"\n")
            (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")
            write_executable(root / "scripts" / "init-network.sh", "#!/usr/bin/env bash\necho init-network.sh >> \"$INSTALL_LOG\"\n")
            write_executable(root / "scripts" / "up-main.sh", "#!/usr/bin/env bash\necho up-main.sh >> \"$INSTALL_LOG\"\nexit 23\n")
            for name in ("prepare-harbor.sh", "bootstrap-keycloak.sh", "panel.sh"):
                write_executable(root / "scripts" / name, f"#!/usr/bin/env bash\necho {name} >> \"$INSTALL_LOG\"\n")
            result = subprocess.run(
                ["bash", "install.sh"],
                cwd=root,
                capture_output=True,
                text=True,
                env={**os.environ, "INSTALL_LOG": str(log_file)},
            )
            lines = log_file.read_text(encoding="utf-8").splitlines() if log_file.exists() else []

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL: main_stack", result.stderr)
        self.assertEqual(lines, ["init-network.sh", "up-main.sh", "up-main.sh", "up-main.sh"])
        self.assertNotIn("prepare-harbor.sh", lines)
        self.assertNotIn("bootstrap-keycloak.sh", lines)
        self.assertNotIn("panel.sh", lines)
