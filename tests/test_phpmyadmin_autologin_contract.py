import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class PhpMyAdminAutologinContractTest(unittest.TestCase):
    def test_compose_mounts_phpmyadmin_autologin_config_and_group_gate(self) -> None:
        text = (REPO_ROOT / "compose.yml").read_text(encoding="utf-8")
        for needle in (
            "MARIADB_DATABASE: ${MARIADB_DATABASE}",
            "PHPMYADMIN_AUTOLOGIN_USER: ${PHPMYADMIN_AUTOLOGIN_USER}",
            "PHPMYADMIN_AUTOLOGIN_PASSWORD: ${PHPMYADMIN_AUTOLOGIN_PASSWORD}",
            "- ./phpmyadmin/config.user.inc.php:/etc/phpmyadmin/config.user.inc.php:ro",
            "- --allowed-group=${PHPMYADMIN_ALLOWED_GROUP}",
        ):
            self.assertIn(needle, text)

    def test_phpmyadmin_config_uses_config_auth_and_only_db(self) -> None:
        text = (REPO_ROOT / "phpmyadmin" / "config.user.inc.php").read_text(encoding="utf-8")
        for needle in (
            "$cfg['Servers'][$i]['auth_type'] = 'config';",
            "$cfg['Servers'][$i]['host'] = getenv('PMA_HOST') ?: 'mariadb';",
            "$cfg['Servers'][$i]['user'] = getenv('PHPMYADMIN_AUTOLOGIN_USER') ?: '';",
            "$cfg['Servers'][$i]['password'] = getenv('PHPMYADMIN_AUTOLOGIN_PASSWORD') ?: '';",
            "$cfg['Servers'][$i]['only_db'] = [getenv('MARIADB_DATABASE') ?: 'appdb'];",
        ):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
