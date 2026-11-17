"""Oracle collector: V$ and DBA_ views, through a monitoring account with read-only grants.

The account needs CREATE SESSION, SELECT_CATALOG_ROLE and AUDIT_VIEWER, nothing else
(docs/oracle.md). python-oracledb in thin mode: no Oracle client to install.
"""

from __future__ import annotations

from datetime import datetime

import oracledb

from db_autoconformite_mcp.collectors import credentials
from db_autoconformite_mcp.models import Facts, Instance

# Each fact comes from one fixed query; a failing query leaves its fact unknown.
QUERIES = {
    "log_connections": """
        SELECT COUNT(*) FROM AUDIT_UNIFIED_ENABLED_POLICIES e
        JOIN AUDIT_UNIFIED_POLICIES p ON p.POLICY_NAME = e.POLICY_NAME
        WHERE p.AUDIT_OPTION = 'LOGON'""",
    "archiving": "SELECT LOG_MODE FROM V$DATABASE",
    "password_hashing": """
        SELECT COUNT(*) FROM DBA_USERS
        WHERE ORACLE_MAINTAINED = 'N' AND PASSWORD_VERSIONS LIKE '%10G%'""",
    "idle_timeout": """
        SELECT LIMIT FROM DBA_PROFILES
        WHERE PROFILE = 'DEFAULT' AND RESOURCE_NAME = 'IDLE_TIME'""",
}
PRIVILEGED = """
    SELECT p.GRANTEE FROM DBA_ROLE_PRIVS p
    LEFT JOIN DBA_USERS u ON u.USERNAME = p.GRANTEE
    WHERE p.GRANTED_ROLE = 'DBA' AND NVL(u.ORACLE_MAINTAINED, 'N') = 'N'
    ORDER BY p.GRANTEE"""
LAST_BACKUP = "SELECT MAX(END_TIME) FROM V$RMAN_BACKUP_JOB_DETAILS WHERE STATUS = 'COMPLETED'"
VERSION = "SELECT VERSION_FULL FROM V$INSTANCE"


def normalize(fact: str, value) -> str:
    """One raw Oracle answer -> the engine-neutral value the baseline checks."""
    if fact == "log_connections":
        return "on" if int(value) > 0 else "off"
    if fact == "archiving":
        return "on" if value == "ARCHIVELOG" else "off"
    if fact == "password_hashing":
        return "strong" if int(value) == 0 else "weak"
    if fact == "idle_timeout":
        return "disabled" if value in (None, "UNLIMITED") else "enabled"
    raise ValueError(fact)


def collect(instance: Instance, now: datetime) -> Facts:
    facts = Facts(instance=instance.id, engine="oracle", collected_at=now)
    user, password = credentials("oracle")
    try:
        conn = oracledb.connect(user=user, password=password,
                                dsn=f"{instance.host}:{instance.port}/{instance.service}",
                                tcp_connect_timeout=5)
    except oracledb.Error as exc:
        error = f"connect: {str(exc).splitlines()[0]}"
        for fact in (*QUERIES, "privileged_accounts", "last_backup_at"):
            facts.lose(fact, error)
        return facts
    with conn:
        conn.call_timeout = 5000  # ms, per round trip
        cur = conn.cursor()

        def one(sql: str, fact: str):
            try:
                row = cur.execute(sql).fetchone()
                return row[0] if row else None
            except oracledb.Error as exc:
                facts.lose(fact, str(exc).splitlines()[0])
                return _MISSING

        for fact, sql in QUERIES.items():
            value = one(sql, fact)
            if value is not _MISSING:
                facts.settings[fact] = normalize(fact, value)
        version = one(VERSION, "version")
        facts.version = "" if version is _MISSING else str(version)
        facts.missing.discard("version")  # the version is informative, not a checked fact
        last = one(LAST_BACKUP, "last_backup_at")
        facts.last_backup_at = None if last is _MISSING else last
        try:
            facts.privileged_accounts = [r[0] for r in cur.execute(PRIVILEGED).fetchall()]
        except oracledb.Error as exc:
            facts.lose("privileged_accounts", str(exc).splitlines()[0])
    return facts


_MISSING = object()
