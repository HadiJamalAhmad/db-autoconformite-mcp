"""Against real databases: the PostgreSQL fleet (docker compose) and Oracle Database Free (CI).

Skipped when the databases are not running, so the unit suite stays offline:
    docker compose -f fleet/compose.yaml --env-file .env up -d --wait
    uv run python fleet/seed_backups.py
    uv run pytest -m integration
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from db_autoconformite_mcp.discovery import open_port
from db_autoconformite_mcp.models import Status
from db_autoconformite_mcp.rules import load_rules
from db_autoconformite_mcp.service import Fleet
from db_autoconformite_mcp.sources import load_backup_log, load_inventory

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[1]

needs_pg = pytest.mark.skipif(not open_port("127.0.0.1", 5433),
                              reason="PostgreSQL fleet not running")
needs_oracle = pytest.mark.skipif(not open_port("127.0.0.1", 1521) or
                                  not os.environ.get("AUTOCONF_ORA_PASSWORD"),
                                  reason="Oracle Database Free not running")


def statuses(findings):
    return {f.rule_id: f.status for f in findings}


@needs_pg
def test_the_compliant_production_database_passes_everything():
    found = Fleet().check("pg-prod-01")
    assert set(statuses(found).values()) == {Status.PASS}, [f.as_dict() for f in found]


@needs_pg
def test_the_drifted_production_database_fails_on_every_drift():
    found = {f.rule_id: f for f in Fleet().check("pg-prod-02")}
    assert {r for r, f in found.items() if f.status == Status.FAIL} == \
        {"R01", "R02", "R03", "R04", "R05", "R06"}
    assert "legacy_admin" in found["R04"].observed
    # The backup run 2 h ago FAILED: the last success is 50 h old, critical in production.
    assert found["R05"].severity.value == "critical"


@needs_pg
def test_recette_only_misses_the_idle_timeout_and_a_backup():
    found = statuses(Fleet().check("pg-recette-01"))
    assert {r for r, s in found.items() if s == Status.FAIL} == {"R05", "R06"}


@needs_pg
def test_correlation_on_the_live_fleet():
    by_rule = {}
    for f in Fleet().correlate():
        by_rule.setdefault(f.rule_id, []).append(f.instance)
    assert by_rule["C01"] == ["pg-shadow-01"]
    assert by_rule["C03"] == ["pg-recette-01"]
    assert by_rule["C04"] == ["pg-cloud-01"]
    assert "C02" not in by_rule


@needs_pg
def test_the_monitoring_session_cannot_write():
    import psycopg

    from db_autoconformite_mcp.collectors.postgres import connect
    with connect("127.0.0.1", 5433, "postgres") as conn, \
            pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        conn.execute("CREATE TABLE should_not_exist (x int)")


@needs_oracle
def test_oracle_every_fact_is_readable_with_the_minimum_grants():
    inventory = load_inventory(ROOT / "fleet" / "oracle" / "inventory.yaml")
    fleet = Fleet(inventory=inventory, baseline=load_rules(), backup_log={})
    facts = fleet.facts("ora-ci-01")
    assert facts.missing == set(), facts.errors
    assert facts.version.startswith("23")


@needs_oracle
def test_oracle_drifts_are_found():
    inventory = load_inventory(ROOT / "fleet" / "oracle" / "inventory.yaml")
    fleet = Fleet(inventory=inventory, baseline=load_rules(), backup_log={})
    found = {f.rule_id: f for f in fleet.check("ora-ci-01")}
    assert found["R04"].status == Status.FAIL and "LEGACY_ADMIN" in found["R04"].observed
    assert found["R02"].status == Status.FAIL  # a fresh Free database runs NOARCHIVELOG
    assert found["R05"].status == Status.FAIL  # no RMAN backup yet
    assert found["R06"].status == Status.FAIL  # DEFAULT profile: IDLE_TIME UNLIMITED
    assert all(f.status != Status.UNKNOWN for f in found.values())


def test_the_backup_log_ignores_failed_runs(tmp_path):
    log = tmp_path / "b.jsonl"
    log.write_text(
        '{"instance": "x", "finished_at": "2026-11-15T10:00:00+00:00", "status": "success"}\n'
        '{"instance": "x", "finished_at": "2026-11-17T10:00:00+00:00", "status": "failed"}\n',
        encoding="utf-8")
    assert load_backup_log(log)["x"].day == 15
