import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


class PanelScriptTest(unittest.TestCase):
    def test_status_and_stop_recover_running_panel_without_pid_file(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "business_panel").mkdir()
            shutil.copy2(repo_root / "scripts" / "panel.sh", root / "scripts" / "panel.sh")
            (root / "business_panel" / "__init__.py").write_text("", encoding="utf-8")
            (root / "business_panel" / "main.py").write_text(
                "import signal\n"
                "import sys\n"
                "import time\n"
                "\n"
                "def _exit(*_args):\n"
                "    sys.exit(0)\n"
                "\n"
                "signal.signal(signal.SIGTERM, _exit)\n"
                "while True:\n"
                "    time.sleep(0.2)\n",
                encoding="utf-8",
            )

            proc = subprocess.Popen(["python3", "-m", "business_panel.main"], cwd=root)
            try:
                time.sleep(0.3)
                self.assertIsNone(proc.poll())

                status = subprocess.run(
                    ["bash", "scripts/panel.sh", "status"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(status.returncode, 0)
                self.assertIn(f"panel 运行中 (pid: {proc.pid})", status.stdout)

                pid_file = root / "outputs" / "runtime" / "panel" / "panel.pid"
                self.assertEqual(pid_file.read_text(encoding="utf-8").strip(), str(proc.pid))
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
