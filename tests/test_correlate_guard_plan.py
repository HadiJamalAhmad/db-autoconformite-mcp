"""Correlation across sources, the guard, and remediation plans."""

import json

import pytest

from db_autoconformite_mcp.guard import GuardError
from db_autoconformite_mcp.models import Status


# ---------------------------------------------------------------- correlation
def test_correlation_finds_what_no_single_source_shows(fleet):
    by_rule = {}
    for f in fleet.correlate():
        by_rule.setdefault(f.rule_id, []).append(f.instance)
    assert by_rule["C01"] == ["pg-shadow"]  # answers, not in the CMDB
    assert by_rule["C03"] == ["pg-recette"]  # no owner
    assert by_rule["C04"] == ["pg-cloud"]  # cloud-native: out of scope
    assert "C02" not in by_rule  # every inventoried in-scope instance answered


def test_an_inventoried_instance_that_does_not_answer_is_reported(fleet):
    fleet._discover = lambda inv: {"pg-ok", "pg-drift", "pg-recette"}  # ora-01 silent
    c02 = [f for f in fleet.correlate() if f.rule_id == "C02"]
    assert [f.instance for f in c02] == ["ora-01"]


def test_out_of_scope_is_informational_not_a_failure(fleet):
    c04 = next(f for f in fleet.correlate() if f.rule_id == "C04")
    assert c04.status == Status.PASS


# ---------------------------------------------------------------- guard
@pytest.mark.parametrize("bad", ["", "PG-PROD", "pg; DROP TABLE x", "../etc", "a" * 60, 42])
def test_malformed_instance_ids_are_refused(fleet, bad):
    with pytest.raises(GuardError, match="invalid instance id"):
        fleet.guard.instance(bad)


def test_unknown_and_out_of_scope_instances_are_refused(fleet):
    with pytest.raises(GuardError, match="not in the inventory"):
        fleet.check("pg-shadow")
    with pytest.raises(GuardError, match="out of scope"):
        fleet.check("pg-cloud")


def test_rule_ids_are_validated(fleet):
    with pytest.raises(GuardError, match="invalid rule id"):
        fleet.explain_rule("R1; rm -rf")
    with pytest.raises(GuardError, match="unknown rule"):
        fleet.explain_rule("R99")


def test_audit_log_records_each_call(fleet, tmp_path):
    fleet.guard.audit("check_compliance", {"instance": "pg-ok"}, "ok")
    fleet.guard.audit("check_compliance", {"instance": "pg-cloud"}, "refused", "out of scope")
    lines = [json.loads(x) for x in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert [x["outcome"] for x in lines] == ["ok", "refused"]
    assert lines[1]["args"] == {"instance": "pg-cloud"}


# ---------------------------------------------------------------- remediation
def test_plan_orders_by_severity_warns_about_restarts_and_executes_nothing(fleet):
    text = fleet.remediation_plan("pg-drift")
    assert "rien n'a été exécuté" in text
    order = [line.split("]")[0] for line in text.splitlines() if line.startswith("-- [")]
    assert order[0] == "-- [CRITICAL"  # R04 extra superuser, or R05 backup
    assert "redémarrage ou fenêtre de maintenance" in text  # R02
    assert "ALTER ROLE legacy_admin NOSUPERUSER;" in text


def test_plan_for_a_compliant_instance_has_nothing_to_fix(fleet):
    assert "Aucun écart corrigeable" in fleet.remediation_plan("pg-ok")
