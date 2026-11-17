"""MCP server: the fleet's compliance tools, for an AI agent such as Claude.

Every tool is read-only (annotated as such) and goes through the guard: allowlisted instances,
validated arguments, one audit-log line per call. No tool accepts SQL or changes anything;
remediation comes back as a proposal for a human to validate.

    uv run db-autoconformite-mcp          # stdio, for Claude Desktop / Claude Code
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from db_autoconformite_mcp.guard import GuardError
from db_autoconformite_mcp.rules import DEFAULT_BASELINE
from db_autoconformite_mcp.service import Fleet, summary

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True,
                            openWorldHint=False)


def build_server(fleet: Fleet) -> MCPServer:
    server = MCPServer("db-autoconformite")

    def guarded(tool: str, args: dict, fn):
        """Run one tool behind the guard and record the call in the audit log."""
        try:
            result = fn()
        except GuardError as exc:
            fleet.guard.audit(tool, args, "refused", str(exc))
            raise ToolError(str(exc)) from None
        fleet.guard.audit(tool, args, "ok")
        return result

    @server.tool(annotations=READ_ONLY)
    def list_instances() -> dict:
        """List the database fleet from the inventory (CMDB): engine, environment, hosting,
        owner, and whether the instance is in the compliance perimeter (not cloud-native)."""
        return guarded("list_instances", {}, lambda: {"instances": fleet.list_instances()})

    @server.tool(annotations=READ_ONLY)
    def get_config(instance: str) -> dict:
        """Read the compliance-relevant configuration of one instance, in engine-neutral
        terms, with any fact that could not be collected listed under `missing`."""

        def run():
            f = fleet.facts(instance)
            d = asdict(f)
            d["collected_at"] = f.collected_at.isoformat()
            d["last_backup_at"] = f.last_backup_at.isoformat() if f.last_backup_at else None
            d["missing"] = sorted(f.missing)
            return d

        return guarded("get_config", {"instance": instance}, run)

    @server.tool(annotations=READ_ONLY)
    def check_compliance(instance: str = "all") -> dict:
        """Check one instance, or every in-scope instance ("all"), against the baseline.
        Returns each rule's status (pass / fail / unknown), severity, observed and expected
        values. UNKNOWN means the fact could not be read: it is never treated as compliant."""

        def run():
            results = (fleet.check_all() if instance == "all"
                       else {instance: fleet.check(instance)})
            return {"instances": {i: {"summary": summary(fs),
                                      "findings": [f.as_dict() for f in fs]}
                                  for i, fs in results.items()}}

        return guarded("check_compliance", {"instance": instance}, run)

    @server.tool(annotations=READ_ONLY)
    def correlate_sources() -> dict:
        """Cross the inventory (CMDB), network discovery and the collected facts: instances
        that answer but are not inventoried, inventoried ones that do not answer or cannot
        be read, missing owners, and what is out of scope."""
        return guarded("correlate_sources", {},
                       lambda: {"findings": [f.as_dict() for f in fleet.correlate()]})

    @server.tool(annotations=READ_ONLY)
    def explain_rule(rule_id: str) -> dict:
        """Explain a baseline rule: why it exists, where each engine (PostgreSQL, Oracle)
        exposes the fact, and the proposed fix."""
        return guarded("explain_rule", {"rule_id": rule_id},
                       lambda: fleet.explain_rule(rule_id))

    @server.tool(annotations=READ_ONLY)
    def propose_remediation(instance: str) -> str:
        """Propose a remediation plan for one instance: failing rules most severe first,
        the engine's fix, and maintenance-window warnings. Nothing is executed."""
        return guarded("propose_remediation", {"instance": instance},
                       lambda: fleet.remediation_plan(instance))

    @server.resource("baseline://rules", mime_type="application/yaml")
    def baseline() -> str:
        """The compliance baseline (YAML)."""
        return Path(DEFAULT_BASELINE).read_text(encoding="utf-8")

    return server


def main() -> None:
    audit = Path(os.environ.get("AUTOCONF_AUDIT_LOG", "audit/mcp-audit.jsonl"))
    build_server(Fleet(audit_path=audit)).run()


if __name__ == "__main__":
    main()
