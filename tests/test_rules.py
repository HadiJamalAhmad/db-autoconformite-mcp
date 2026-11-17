"""The baseline and its evaluation: pass, fail, unknown, and severity escalation."""

from datetime import timedelta

from conftest import NOW, inst

from db_autoconformite_mcp.models import Facts, Severity, Status
from db_autoconformite_mcp.rules import evaluate, evaluate_all, load_rules

RULES = {r.id: r for r in load_rules()}


def statuses(findings):
    return {f.rule_id: f.status for f in findings}


# ---------------------------------------------------------------- the baseline itself
def test_every_rule_says_where_each_engine_exposes_its_fact_and_how_to_fix_it():
    """PostgreSQL and Oracle side by side: the baseline is engine-neutral by construction."""
    for r in RULES.values():
        assert set(r.source) == {"postgresql", "oracle"}, r.id
        assert set(r.remediation) == {"postgresql", "oracle"}, r.id
        assert r.rationale, r.id


def test_rule_ids_are_unique_and_ordered():
    assert list(RULES) == ["R01", "R02", "R03", "R04", "R05", "R06"]


# ---------------------------------------------------------------- outcomes
def test_a_compliant_instance_passes_every_rule(facts_by_instance, inventory):
    f = facts_by_instance["pg-ok"]
    f.last_backup_at = NOW - timedelta(hours=3)
    assert set(statuses(evaluate_all(list(RULES.values()), f, inventory["pg-ok"], NOW))
               .values()) == {Status.PASS}


def test_a_drifted_instance_fails_with_observed_and_expected_values(facts_by_instance,
                                                                    inventory):
    f = facts_by_instance["pg-drift"]
    results = {x.rule_id: x for x in evaluate_all(list(RULES.values()), f,
                                                  inventory["pg-drift"], NOW)}
    assert {k for k, v in results.items() if v.status == Status.FAIL} == \
        {"R01", "R02", "R03", "R04", "R05", "R06"}
    assert (results["R01"].observed, results["R01"].expected) == ("off", "on")
    assert "legacy_admin" in results["R04"].remediation
    assert "postgres" not in results["R04"].remediation.split()  # allowed admin left alone


def test_a_fact_that_could_not_be_read_is_unknown_never_compliant():
    """An empty privileged-account list because the query failed is not 'no superuser'."""
    f = Facts("x", "oracle", NOW)
    for fact in ("privileged_accounts", "log_connections", "last_backup_at"):
        f.lose(fact, "ORA-00942: table or view does not exist")
    i = inst("x", engine="oracle")
    for rid in ("R04", "R01", "R05"):
        assert evaluate(RULES[rid], f, i, NOW).status == Status.UNKNOWN


def test_a_missing_backup_on_a_critical_production_database_is_critical():
    f = Facts("p", "postgresql", NOW)
    finding = evaluate(RULES["R05"], f, inst("p"), NOW)
    assert (finding.status, finding.severity) == (Status.FAIL, Severity.CRITICAL)


def test_backup_age_limits_depend_on_the_environment():
    f = Facts("r", "postgresql", NOW, last_backup_at=NOW - timedelta(hours=100))
    assert evaluate(RULES["R05"], f, inst("r", env="recette", criticality="standard"),
                    NOW).status == Status.PASS  # recette: 168 h
    assert evaluate(RULES["R05"], f, inst("p"), NOW).status == Status.FAIL  # production: 24 h


def test_remediation_is_given_only_for_failures_and_per_engine():
    ok = Facts("o", "oracle", NOW, settings={"archiving": "on"})
    bad = Facts("o", "oracle", NOW, settings={"archiving": "off"})
    i = inst("o", engine="oracle")
    assert evaluate(RULES["R02"], ok, i, NOW).remediation == ""
    assert "ALTER DATABASE ARCHIVELOG" in evaluate(RULES["R02"], bad, i, NOW).remediation
