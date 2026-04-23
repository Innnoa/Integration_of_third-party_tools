import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def stage_prereqs_scripts(root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    shutil.copy2(repo_root / "scripts" / "install-lib.sh", root / "scripts" / "install-lib.sh")
    shutil.copy2(repo_root / "scripts" / "check-install-prereqs.sh", root / "scripts" / "check-install-prereqs.sh")
    (root / ".env.example").write_text("PUBLIC_SCHEME=http\nPUBLIC_HOST=localhost\n", encoding="utf-8")


class InstallPrereqsScriptTest(unittest.TestCase):
    def test_check_install_prereqs_reports_ready_for_debian_13_with_compose_v2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_prereqs_scripts(root)

            fakebin = root / "fakebin"
            fakebin.mkdir()
            os_release = root / "os-release"
            os_release.write_text(
                'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nID=debian\nVERSION_ID="13"\n',
                encoding="utf-8",
            )
            write_executable(fakebin / "python3", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(fakebin / "sudo", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(fakebin / "apt-get", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(
                fakebin / "docker",
                "#!/usr/bin/env bash\n"
                "if [ \"$1\" = \"compose\" ] && [ \"$2\" = \"version\" ]; then\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n",
            )

            result = subprocess.run(
                ["/bin/bash", "scripts/check-install-prereqs.sh"],
                cwd=root,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "PATH": f"{fakebin}:{os.environ['PATH']}",
                    "CHECK_PREREQS_OS_RELEASE_FILE": str(os_release),
                },
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("安装前提检查", result.stdout)
        self.assertIn("支持等级：已验证", result.stdout)
        self.assertIn("结论：已就绪", result.stdout)
        self.assertIn("Compose 候选包：docker-compose-plugin docker-compose-v2 docker-compose", result.stdout)
        self.assertIn("提示：当前脚本路径已对 Debian 13 做过专项修复并有自动化测试覆盖。", result.stdout)

    def test_check_install_prereqs_reports_installable_for_ubuntu_when_compose_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_prereqs_scripts(root)

            fakebin = root / "fakebin"
            fakebin.mkdir()
            os_release = root / "os-release"
            os_release.write_text(
                'PRETTY_NAME="Ubuntu 24.04.2 LTS"\nID=ubuntu\nVERSION_ID="24.04"\n',
                encoding="utf-8",
            )
            write_executable(fakebin / "python3", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(fakebin / "sudo", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(fakebin / "apt-get", "#!/usr/bin/env bash\nexit 0\n")
            write_executable(
                fakebin / "docker",
                "#!/usr/bin/env bash\n"
                "if [ \"$1\" = \"compose\" ] && [ \"$2\" = \"version\" ]; then\n"
                "  exit 1\n"
                "fi\n"
                "exit 0\n",
            )

            result = subprocess.run(
                ["/bin/bash", "scripts/check-install-prereqs.sh"],
                cwd=root,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "PATH": f"{fakebin}:{os.environ['PATH']}",
                    "CHECK_PREREQS_OS_RELEASE_FILE": str(os_release),
                },
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("支持等级：APT 兼容路径", result.stdout)
        self.assertIn("Docker Compose v2：缺失", result.stdout)
        self.assertIn("结论：可安装", result.stdout)
        self.assertIn("Compose 候选包：docker-compose-plugin docker-compose-v2 docker-compose", result.stdout)
        self.assertIn("错误：缺少 Docker Compose v2（`docker compose`）。", result.stdout)
        self.assertIn("建议：先安装 Compose 候选包，或直接执行安装脚本让它自动补齐。", result.stdout)

    def test_check_install_prereqs_reports_blocked_without_supported_package_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            stage_prereqs_scripts(root)

            fakebin = root / "fakebin"
            fakebin.mkdir()
            os_release = root / "os-release"
            os_release.write_text(
                'PRETTY_NAME="Gentoo"\nID=gentoo\nVERSION_ID="2.15"\n',
                encoding="utf-8",
            )
            write_executable(fakebin / "python3", "#!/usr/bin/env bash\nexit 0\n")

            result = subprocess.run(
                ["/bin/bash", "scripts/check-install-prereqs.sh"],
                cwd=root,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "PATH": f"{fakebin}:{os.environ['PATH']}",
                    "CHECK_PREREQS_OS_RELEASE_FILE": str(os_release),
                    "INSTALL_PACKAGE_MANAGER": "unsupported",
                },
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("包管理器：不受支持", result.stdout)
        self.assertIn("支持等级：未验证", result.stdout)
        self.assertIn("结论：已阻塞", result.stdout)
        self.assertIn("错误：当前主机缺少受支持的包管理器。", result.stdout)
        self.assertIn("建议：请先手工安装 Python 3、Docker 与 Docker Compose v2，再重新执行安装。", result.stdout)
