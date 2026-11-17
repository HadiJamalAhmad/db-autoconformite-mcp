"""Shared fixtures: a small fleet, a fixed clock, and fake collectors (no database needed)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from db_autoconformite_mcp.models import Facts, Instance
from db_autoconformite_mcp.rules import load_rules
from db_autoconformite_mcp.service import Fleet

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)

COMPLIANT = {"log_connections": "on", "archiving": "on", "password_hashing": "strong",
             "idle_timeout": "enabled"}
DRIFTED = {"log_connections": "off", "archiving": "off", "password_hashing": "weak",
           "idle_timeout": "disabled"}


def inst(id_, env="production", hosting="on-prem", owner="team", engine="postgresql",
         criticality="critical") -> Instance:
    return Instance(id=id_, engine=engine, host="127.0.0.1", port=5432, service="postgres",
                    environment=env, hosting=hosting, owner=owner, criticality=criticality,
                    allowed_admins=("postgres",))


@pytest.fixture
def inventory() -> dict[str, Instance]:
    items = [inst("pg-ok"), inst("pg-drift"), inst("pg-recette", env="recette", owner="",
                                                 criticality="standard"),
             inst("pg-cloud", hosting="cloud"), inst("ora-01", engine="oracle")]
    return {i.id: i for i in items}


@pytest.fixture
def facts_by_instance() -> dict[str, Facts]:
    return {
        "pg-ok": Facts("pg-ok", "postgresql", NOW, "17.6", dict(COMPLIANT), ["postgres"]),
        "pg-drift": Facts("pg-drift", "postgresql", NOW, "17.6", dict(DRIFTED),
                          ["legacy_admin", "postgres"]),
        "pg-recette": Facts("pg-recette", "postgresql", NOW, "17.6",
                            {**COMPLIANT, "idle_timeout": "disabled"}, ["postgres"]),
        "ora-01": Facts("ora-01", "oracle", NOW, "23.6", dict(COMPLIANT), [],
                        last_backup_at=NOW - timedelta(hours=5)),
    }


@pytest.fixture
def fleet(inventory, facts_by_instance, tmp_path) -> Fleet:
    def fake(instance, now):
        f = facts_by_instance[instance.id]
        return Facts(f.instance, f.engine, now, f.version, dict(f.settings),
                     list(f.privileged_accounts), f.last_backup_at, list(f.errors),
                     set(f.missing))

    backups = {"pg-ok": NOW - timedelta(hours=3), "pg-drift": NOW - timedelta(hours=50)}
    return Fleet(inventory=inventory, baseline=load_rules(), backup_log=backups,
                 collectors={"postgresql": fake, "oracle": fake},
                 discover=lambda inv: {"pg-ok", "pg-drift", "pg-recette", "ora-01",
                                       "pg-shadow"},
                 clock=lambda: NOW, audit_path=tmp_path / "audit.jsonl")
