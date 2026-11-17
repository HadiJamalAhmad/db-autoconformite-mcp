"""The fleet service: what both the CLI (fleetctl) and the MCP server call.

Everything external is injected (collectors, discovery, clock, sources), so the tests run
the real logic against fake databases, and the CLI and the server stay thin.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from db_autoconformite_mcp import correlate as corr
from db_autoconformite_mcp import remediation, rules, sources
from db_autoconformite_mcp.collectors import Collector, default_collectors
from db_autoconformite_mcp.guard import Guard, GuardError
from db_autoconformite_mcp.models import Facts, Finding, Instance, Rule, Status

Discover = Callable[[dict[str, Instance]], set[str]]


class Fleet:
    def __init__(self, inventory: dict[str, Instance] | None = None,
                 baseline: list[Rule] | None = None,
                 backup_log: dict[str, datetime] | None = None,
                 collectors: dict[str, Collector] | None = None,
                 discover: Discover | None = None,
                 clock: Callable[[], datetime] | None = None,
                 audit_path: Path | None = None):
        self.inventory = inventory if inventory is not None else sources.load_inventory()
        self.rules = baseline if baseline is not None else rules.load_rules()
        self.backup_log = backup_log if backup_log is not None else sources.load_backup_log()
        self.collectors = collectors if collectors is not None else default_collectors()
        self._discover = discover
        self.clock = clock or (lambda: datetime.now(UTC))
        self.guard = Guard(self.inventory, audit_path)

    # ------------------------------------------------------------------ reading
    def list_instances(self) -> list[dict]:
        return [{"id": i.id, "engine": i.engine, "environment": i.environment,
                 "hosting": i.hosting, "in_scope": i.in_scope, "owner": i.owner or None,
                 "criticality": i.criticality}
                for i in sorted(self.inventory.values(), key=lambda i: i.id)]

    def facts(self, instance_id: str) -> Facts:
        inst = self.guard.instance(instance_id)
        facts = self.collectors[inst.engine](inst, self.clock())
        # PostgreSQL has no backup catalogue of its own: the backup tool's log is the source.
        if inst.engine == "postgresql":
            facts.last_backup_at = self.backup_log.get(inst.id)
        return facts

    def check(self, instance_id: str) -> list[Finding]:
        inst = self.guard.instance(instance_id)
        return rules.evaluate_all(self.rules, self.facts(inst.id), inst, self.clock())

    def check_all(self) -> dict[str, list[Finding]]:
        return {i.id: self.check(i.id) for i in self.inventory.values() if i.in_scope}

    def discover(self) -> set[str]:
        if self._discover is None:
            from db_autoconformite_mcp.discovery import discover

            self._discover = discover
        return self._discover(self.inventory)

    def correlate(self) -> list[Finding]:
        found = self.discover()
        facts = {i: self.facts(i) for i in found
                 if i in self.inventory and self.inventory[i].in_scope}
        return corr.correlate(self.inventory, found, facts)

    def explain_rule(self, rule_id: str) -> dict:
        rule_id = self.guard.rule_id(rule_id)
        for r in self.rules:
            if r.id == rule_id:
                d = asdict(r)
                d["severity"] = r.severity.value
                return d
        raise GuardError(f"unknown rule {rule_id}")

    def remediation_plan(self, instance_id: str) -> str:
        inst = self.guard.instance(instance_id)
        return remediation.plan(inst, self.check(inst.id))


def summary(findings: list[Finding]) -> dict:
    out = {"pass": 0, "fail": 0, "unknown": 0, "worst": None}
    worst = None
    for f in findings:
        out[f.status.value] += 1
        if f.status == Status.FAIL and (worst is None or f.severity.rank > worst.rank):
            worst = f.severity
    out["worst"] = worst.value if worst else None
    return out
