"""Collectors: engine-specific values -> neutral facts, and failures -> UNKNOWN, never PASS."""

import oracledb
import psycopg
import pytest
from conftest import NOW, inst

from db_autoconformite_mcp.collectors import oracle, postgres
from db_autoconformite_mcp.models import Status
from db_autoconformite_mcp.rules import evaluate_all, load_rules


# ---------------------------------------------------------------- PostgreSQL mapping
def test_postgres_settings_map_to_neutral_facts():
    assert postgres.normalize({
        "log_connections": "on", "archive_mode": "always", "password_encryption": "scram-sha-256",
        "idle_in_transaction_session_timeout": "600000"}) == {
        "log_connections": "on", "archiving": "on", "password_hashing": "strong",
        "idle_timeout": "enabled"}
    assert postgres.normalize({
        "log_connections": "off", "archive_mode": "off", "password_encryption": "md5",
        "idle_in_transaction_session_timeout": "0"}) == {
        "log_connections": "off", "archiving": "off", "password_hashing": "weak",
        "idle_timeout": "disabled"}


def test_postgres_sessions_are_read_only_and_time_limited(monkeypatch):
    seen = {}

    def fake_connect(**kw):
        seen.update(kw)
        raise psycopg.OperationalError("stop here")

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    postgres.collect(inst("x"), NOW)
    assert "default_transaction_read_only=on" in seen["options"]
    assert "statement_timeout=" in seen["options"]
    assert seen["connect_timeout"] == 5


# ---------------------------------------------------------------- Oracle mapping
@pytest.mark.parametrize("fact,raw,neutral", [
    ("log_connections", 1, "on"), ("log_connections", 0, "off"),
    ("archiving", "ARCHIVELOG", "on"), ("archiving", "NOARCHIVELOG", "off"),
    ("password_hashing", 0, "strong"), ("password_hashing", 3, "weak"),
    ("idle_timeout", "UNLIMITED", "disabled"), ("idle_timeout", "30", "enabled"),
])
def test_oracle_answers_map_to_neutral_facts(fact, raw, neutral):
    assert oracle.normalize(fact, raw) == neutral


def test_oracle_queries_only_read_the_catalogue():
    for sql in [*oracle.QUERIES.values(), oracle.PRIVILEGED, oracle.LAST_BACKUP, oracle.VERSION]:
        assert sql.strip().upper().startswith("SELECT"), sql


# ---------------------------------------------------------------- the safety property
def test_an_unreachable_database_yields_only_unknowns(monkeypatch):
    """No connection, no compliance: every checked fact is UNKNOWN, none PASS."""
    def refuse(**kw):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(psycopg, "connect", refuse)
    i = inst("down", criticality="standard")
    f = postgres.collect(i, NOW)
    f.last_backup_at = NOW  # the backup log is a separate source
    found = {x.rule_id: x.status for x in evaluate_all(load_rules(), f, i, NOW)}
    assert Status.PASS not in {found[r] for r in ("R01", "R02", "R03", "R04", "R06")}
    assert {found[r] for r in ("R01", "R02", "R03", "R04", "R06")} == {Status.UNKNOWN}


def test_an_unreachable_oracle_yields_only_unknowns(monkeypatch):
    def refuse(**kw):
        raise oracledb.OperationalError("DPY-6005: cannot connect")

    monkeypatch.setattr(oracledb, "connect", refuse)
    i = inst("ora", engine="oracle")
    f = oracle.collect(i, NOW)
    assert {x.status for x in evaluate_all(load_rules(), f, i, NOW)} == {Status.UNKNOWN}
