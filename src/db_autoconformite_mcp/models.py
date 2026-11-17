"""Data model shared by collectors, rules, correlation and the MCP server.

Collectors turn each engine's own catalogue (PostgreSQL settings, Oracle V$ and DBA_ views)
into the same engine-neutral `Facts`, so one rule set checks both engines.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return ["info", "low", "medium", "high", "critical"].index(self.value)


class Status(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"  # the fact could not be collected: never reported as compliant


@dataclass(frozen=True)
class Instance:
    """One database as the inventory (CMDB) describes it."""

    id: str
    engine: str  # "postgresql" | "oracle"
    host: str
    port: int
    service: str  # PostgreSQL database name or Oracle service name
    environment: str  # "production" | "recette" | ...
    hosting: str  # "on-prem" | "cloud"
    owner: str = ""
    criticality: str = "standard"  # "standard" | "critical"
    allowed_admins: tuple[str, ...] = ()

    @property
    def in_scope(self) -> bool:
        """The mission's perimeter: databases that are not native to the public cloud."""
        return self.hosting != "cloud"


@dataclass
class Facts:
    """What a collector observed on one instance, in engine-neutral keys."""

    instance: str
    engine: str
    collected_at: datetime
    version: str = ""
    settings: dict[str, str] = field(default_factory=dict)
    privileged_accounts: list[str] = field(default_factory=list)
    last_backup_at: datetime | None = None
    errors: list[str] = field(default_factory=list)
    # Facts that could not be read. A rule on a missing fact reports UNKNOWN: an empty list of
    # privileged accounts because the query failed must never read as "no privileged account".
    missing: set[str] = field(default_factory=set)

    def lose(self, fact: str, error: str) -> None:
        self.missing.add(fact)
        self.errors.append(f"{fact}: {error}")


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: Severity
    check: str  # "equals" | "subset_of_allowed" | "max_age_hours"
    fact: str
    expected: str = ""
    max_age_hours: dict[str, int] = field(default_factory=dict)  # per environment
    rationale: str = ""
    source: dict[str, str] = field(default_factory=dict)  # engine -> where the fact comes from
    remediation: dict[str, str] = field(default_factory=dict)  # engine -> proposed fix


@dataclass
class Finding:
    rule_id: str
    instance: str
    status: Status
    severity: Severity
    title: str
    observed: str
    expected: str
    remediation: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["severity"] = self.severity.value
        return d
