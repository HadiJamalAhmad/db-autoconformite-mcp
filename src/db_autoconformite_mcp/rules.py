"""The compliance baseline and its evaluation.

Evaluation is pure: facts in, findings out, no I/O. A fact that could not be collected
gives UNKNOWN, never PASS: an unreadable setting is not a compliant one.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from db_autoconformite_mcp.models import Facts, Finding, Instance, Rule, Severity, Status

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = ROOT / "baseline" / "rules.yaml"


def load_rules(path: Path = DEFAULT_BASELINE) -> list[Rule]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = []
    for r in data["rules"]:
        rules.append(Rule(
            id=r["id"], title=r["title"], severity=Severity(r["severity"]), check=r["check"],
            fact=r["fact"], expected=str(r.get("expected", "")),
            max_age_hours=dict(r.get("max_age_hours", {})),
            rationale=r.get("rationale", "").strip(),
            source=dict(r.get("source", {})), remediation=dict(r.get("remediation", {}))))
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate rule ids in {path}")
    return rules


def evaluate(rule: Rule, facts: Facts, instance: Instance, now: datetime) -> Finding:
    """One rule on one instance."""

    def finding(status: Status, observed: str, expected: str, fix: str = "",
                severity: Severity | None = None) -> Finding:
        return Finding(rule.id, instance.id, status, severity or rule.severity, rule.title,
                       observed, expected, fix if status == Status.FAIL else "")

    fix = rule.remediation.get(instance.engine, "")

    if rule.fact in facts.missing:
        return finding(Status.UNKNOWN, "not collected", rule.expected or "collected")

    if rule.check == "equals":
        value = facts.settings.get(rule.fact)
        if value is None:
            return finding(Status.UNKNOWN, "not collected", rule.expected)
        ok = value == rule.expected
        return finding(Status.PASS if ok else Status.FAIL, value, rule.expected, fix)

    if rule.check == "subset_of_allowed":
        allowed = set(instance.allowed_admins)
        extra = sorted(set(facts.privileged_accounts) - allowed)
        observed = ", ".join(sorted(facts.privileged_accounts)) or "none"
        expected = "only: " + (", ".join(sorted(allowed)) or "none")
        if extra:
            fixes = "\n".join(fix.format(account=a) for a in extra)
            return finding(Status.FAIL, observed, expected, fixes)
        return finding(Status.PASS, observed, expected)

    if rule.check == "max_age_hours":
        limit = rule.max_age_hours.get(instance.environment)
        if limit is None:
            return finding(Status.PASS, "no limit for this environment", "n/a")
        expected = f"at most {limit} h old"
        if facts.last_backup_at is None:
            return finding(Status.FAIL, "no backup found", expected, fix, _escalate(rule, instance))
        age = (now - facts.last_backup_at).total_seconds() / 3600
        ok = age <= limit
        return finding(Status.PASS if ok else Status.FAIL, f"{age:.0f} h old", expected, fix,
                       None if ok else _escalate(rule, instance))

    raise ValueError(f"unknown check {rule.check!r} in rule {rule.id}")


def _escalate(rule: Rule, instance: Instance) -> Severity:
    """A missing backup on a production database the inventory marks critical is critical."""
    if instance.environment == "production" and instance.criticality == "critical":
        return Severity.CRITICAL
    return rule.severity


def evaluate_all(rules: list[Rule], facts: Facts, instance: Instance,
                 now: datetime) -> list[Finding]:
    return [evaluate(r, facts, instance, now) for r in rules]
