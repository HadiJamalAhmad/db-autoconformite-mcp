"""The guard between the AI agent and the database fleet.

- Only inventoried, in-scope instances can be named by a tool (allowlist).
- Arguments are validated before anything else runs.
- Every tool call is appended to an audit log (JSON lines): who asked what, and the outcome.
- No tool takes SQL or writes anything: collectors run fixed read-only queries, and
  remediation is returned as text for a human to review.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from db_autoconformite_mcp.models import Instance

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
RULE_RE = re.compile(r"^[RC]\d{2}$")


class GuardError(ValueError):
    """A refused tool call. The message is safe to show to the agent."""


class Guard:
    def __init__(self, inventory: dict[str, Instance], audit_path: Path | None = None):
        self.inventory = inventory
        self.audit_path = audit_path

    def instance(self, instance_id: str) -> Instance:
        if not isinstance(instance_id, str) or not ID_RE.fullmatch(instance_id):
            raise GuardError("invalid instance id")
        inst = self.inventory.get(instance_id)
        if inst is None:
            raise GuardError(f"{instance_id} is not in the inventory")
        if not inst.in_scope:
            raise GuardError(f"{instance_id} is out of scope (hosting: {inst.hosting})")
        return inst

    def rule_id(self, rule_id: str) -> str:
        if not isinstance(rule_id, str) or not RULE_RE.fullmatch(rule_id):
            raise GuardError("invalid rule id (expected R01..R99 or C01..C99)")
        return rule_id

    def audit(self, tool: str, args: dict, outcome: str, detail: str = "") -> None:
        if self.audit_path is None:
            return
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"at": datetime.now(UTC).isoformat(timespec="seconds"), "tool": tool,
                 "args": args, "outcome": outcome, "detail": detail}
        with self.audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
