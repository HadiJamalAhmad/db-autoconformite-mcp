"""PostgreSQL collector: pg_settings and pg_roles, through a read-only monitoring role."""

from __future__ import annotations

from datetime import datetime

import psycopg

from db_autoconformite_mcp.collectors import credentials
from db_autoconformite_mcp.models import Facts, Instance

SETTINGS = ("log_connections", "archive_mode", "password_encryption",
            "idle_in_transaction_session_timeout", "cluster_name")


def connect(host: str, port: int, dbname: str) -> psycopg.Connection:
    user, password = credentials("postgresql")
    return psycopg.connect(
        host=host, port=port, dbname=dbname, user=user, password=password, connect_timeout=5,
        # Enforced by the server for this session: any write is rejected, any query capped.
        options="-c default_transaction_read_only=on -c statement_timeout=5000",
        autocommit=True)


def normalize(raw: dict[str, str]) -> dict[str, str]:
    """PostgreSQL settings -> the engine-neutral facts the baseline checks."""
    out: dict[str, str] = {}
    if "log_connections" in raw:
        out["log_connections"] = "on" if raw["log_connections"] == "on" else "off"
    if "archive_mode" in raw:
        out["archiving"] = "on" if raw["archive_mode"] in ("on", "always") else "off"
    if "password_encryption" in raw:
        out["password_hashing"] = "strong" if raw["password_encryption"] == "scram-sha-256" \
            else "weak"
    if "idle_in_transaction_session_timeout" in raw:
        out["idle_timeout"] = "enabled" if int(raw["idle_in_transaction_session_timeout"]) > 0 \
            else "disabled"
    return out


def collect(instance: Instance, now: datetime) -> Facts:
    facts = Facts(instance=instance.id, engine="postgresql", collected_at=now)
    try:
        with connect(instance.host, instance.port, instance.service) as conn:
            raw = dict(conn.execute("SELECT name, setting FROM pg_settings WHERE name = ANY(%s)",
                                    [list(SETTINGS)]).fetchall())
            facts.settings = normalize(raw)
            facts.version = conn.execute("SHOW server_version").fetchone()[0]
            facts.privileged_accounts = [r[0] for r in conn.execute(
                "SELECT rolname FROM pg_roles WHERE rolsuper ORDER BY rolname").fetchall()]
    except psycopg.Error as exc:
        error = f"{type(exc).__name__}: {str(exc).strip().splitlines()[0]}"
        for fact in ("log_connections", "archiving", "password_hashing", "idle_timeout",
                     "privileged_accounts"):
            if fact not in facts.settings:
                facts.lose(fact, error)
    return facts


def identify(host: str, port: int) -> str | None:
    """The instance's own name (cluster_name), used by discovery to match the inventory."""
    try:
        with connect(host, port, "postgres") as conn:
            return conn.execute("SHOW cluster_name").fetchone()[0] or None
    except psycopg.Error:
        return None
