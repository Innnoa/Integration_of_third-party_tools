#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

[[ -f "${ENV_FILE}" ]] || { echo "缺少 ${ENV_FILE}" >&2; exit 1; }

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

require_env() {
  local key="$1"
  [[ -n "${!key:-}" ]] || { echo "缺少环境变量: ${key}" >&2; exit 1; }
}

sql_escape_literal() {
  python3 - "$1" <<'PY'
import sys

print(sys.argv[1].replace("\\", "\\\\").replace("'", "''"))
PY
}

sql_escape_identifier() {
  python3 - "$1" <<'PY'
import sys

print(sys.argv[1].replace("`", "``"))
PY
}

require_env MARIADB_DATABASE
require_env MARIADB_ROOT_PASSWORD
require_env PHPMYADMIN_AUTOLOGIN_USER
require_env PHPMYADMIN_AUTOLOGIN_PASSWORD

db_name="$(sql_escape_identifier "${MARIADB_DATABASE}")"
db_user="$(sql_escape_literal "${PHPMYADMIN_AUTOLOGIN_USER}")"
db_password="$(sql_escape_literal "${PHPMYADMIN_AUTOLOGIN_PASSWORD}")"

docker exec -i mariadb mariadb -uroot "-p${MARIADB_ROOT_PASSWORD}" <<SQL
CREATE USER IF NOT EXISTS '${db_user}'@'%' IDENTIFIED BY '${db_password}';
ALTER USER '${db_user}'@'%' IDENTIFIED BY '${db_password}';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER, CREATE VIEW, SHOW VIEW, REFERENCES, TRIGGER, LOCK TABLES, CREATE TEMPORARY TABLES
  ON \`${db_name}\`.* TO '${db_user}'@'%';
FLUSH PRIVILEGES;
SQL
