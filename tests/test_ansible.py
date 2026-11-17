"""The Ansible export (one source of truth) and the cross-check between Ansible and fleetctl."""

import yaml
from conftest import inst

from db_autoconformite_mcp import ansible_crosscheck as cc
from db_autoconformite_mcp.ansible_export import PARAMETER_RULE, inventory, standard_settings
from db_autoconformite_mcp.rules import load_rules

RULES = load_rules()


def test_standard_settings_come_from_the_baseline_and_cover_the_configuration_rules():
    settings = standard_settings(RULES)
    assert settings == {"log_connections": "on", "archive_mode": "on",
                        "password_encryption": "scram-sha-256",
                        "idle_in_transaction_session_timeout": "600000"}
    by_rule = {r.id: r for r in RULES}
    for param, rule_id in PARAMETER_RULE.items():
        assert param in by_rule[rule_id].standard["postgresql"]


def test_the_exported_inventory_keeps_only_in_scope_postgresql():
    instances = {i.id: i for i in [inst("pg-a"), inst("pg-cloud", hosting="cloud"),
                                   inst("ora-a", engine="oracle")]}
    hosts = inventory(instances, RULES)["all"]["children"]["postgresql"]["hosts"]
    assert list(hosts) == ["pg-a"]
    assert hosts["pg-a"]["pg_allowed_admins"] == ["postgres"]


def test_the_export_is_valid_yaml(tmp_path):
    from db_autoconformite_mcp.ansible_export import write

    path = write({"pg-a": inst("pg-a")}, RULES, tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["all"]["children"]["postgresql"]["vars"]["pg_standard_settings"]


# ---------------------------------------------------------------- cross-check
def task(name, hosts):
    return {"task": {"name": name}, "hosts": hosts}


def item(key, changed):
    return {"item": {"key": key}, "changed": changed}


ANSIBLE = {"plays": [{"tasks": [
    task(cc.STANDARD_TASK, {
        "pg-prod-01": {"results": [item("log_connections", False), item("archive_mode", False)]},
        "pg-prod-02": {"results": [item("log_connections", True), item("archive_mode", True)]},
    }),
    task("Lire les rôles existants", {"pg-prod-02": {}}),
    task(cc.REVOKE_TASK, {
        "pg-prod-01": {"results": []},
        "pg-prod-02": {"results": [item("legacy_admin", True)]},
    }),
]}]}


def finding(rule, status):
    return {"rule_id": rule, "status": status}


def test_agreement_when_both_tools_see_the_same_drifts():
    fleet = {"pg-prod-01": [finding("R01", "pass")],
             "pg-prod-02": [finding("R01", "fail"), finding("R02", "fail"),
                            finding("R04", "fail"), finding("R05", "fail")]}  # R05 ignored
    assert cc.compare(cc.ansible_rules(ANSIBLE), cc.fleet_rules(fleet)) == []


def test_a_disagreement_is_reported():
    fleet = {"pg-prod-01": [finding("R01", "fail")],
             "pg-prod-02": [finding("R01", "fail"), finding("R02", "fail"),
                            finding("R04", "fail")]}
    problems = cc.compare(cc.ansible_rules(ANSIBLE), cc.fleet_rules(fleet))
    assert problems == ["pg-prod-01: ansible would change [], fleetctl reports ['R01']"]
