"""Prepare the CI's Oracle Database Free container (run as SYSTEM, once).

- The monitoring account with the minimum read-only grants the collector needs
  (docs/oracle.md): CREATE SESSION, SELECT_CATALOG_ROLE, AUDIT_VIEWER.
- A deliberate drift for the checks to find: LEGACY_ADMIN holding the DBA role (rule R04).

    ORACLE_PASSWORD=... AUTOCONF_ORA_PASSWORD=... uv run python fleet/oracle/setup_ci.py
"""

from __future__ import annotations

import os
import time

import oracledb

DSN = os.environ.get("ORACLE_DSN", "127.0.0.1:1521/FREEPDB1")


def connect_with_retry(attempts: int = 60) -> oracledb.Connection:
    for i in range(attempts):
        try:
            return oracledb.connect(user="system", password=os.environ["ORACLE_PASSWORD"],
                                    dsn=DSN)
        except oracledb.Error:
            if i == attempts - 1:
                raise
            time.sleep(5)
    raise RuntimeError("unreachable")


def main() -> None:
    monitor_password = os.environ["AUTOCONF_ORA_PASSWORD"]
    with connect_with_retry() as conn:
        cur = conn.cursor()
        statements = [
            f'CREATE USER autoconformite_ro IDENTIFIED BY "{monitor_password}"',
            "GRANT CREATE SESSION, SELECT_CATALOG_ROLE TO autoconformite_ro",
            "GRANT AUDIT_VIEWER TO autoconformite_ro",
            "CREATE USER legacy_admin NO AUTHENTICATION",
            "GRANT DBA TO legacy_admin",
        ]
        for sql in statements:
            cur.execute(sql)
            print("ok:", sql.split(" IDENTIFIED")[0])


if __name__ == "__main__":
    main()
