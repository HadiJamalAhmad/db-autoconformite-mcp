"""fleetctl: the same checks as the MCP server, from a terminal or a CI job.

    uv run fleetctl inventory
    uv run fleetctl discover
    uv run fleetctl check [--instance ID] [--format text|json|markdown] [--fail-on high]
    uv run fleetctl correlate [--fail-on high]
    uv run fleetctl plan ID

Exit code 1 when a failing finding reaches --fail-on: that is what makes the CI job a
compliance gate (auto-conformité) rather than a report nobody reads.
"""

from __future__ import annotations

import argparse
import json
import sys

from db_autoconformite_mcp.models import Finding, Severity, Status
from db_autoconformite_mcp.service import Fleet, summary

MARK = {Status.PASS: "OK  ", Status.FAIL: "FAIL", Status.UNKNOWN: "??  "}


def _text(results: dict[str, list[Finding]]) -> str:
    lines = []
    for inst, findings in results.items():
        s = summary(findings)
        lines.append(f"== {inst}: {s['pass']} ok, {s['fail']} en écart, {s['unknown']} inconnu"
                     + (f" (pire : {s['worst']})" if s["worst"] else ""))
        for f in findings:
            lines.append(f"  {MARK[f.status]} {f.rule_id} [{f.severity.value}] {f.title}: "
                         f"observé {f.observed} | attendu {f.expected}")
    return "\n".join(lines)


def _markdown(results: dict[str, list[Finding]]) -> str:
    lines = ["| Instance | Règle | Statut | Gravité | Observé | Attendu |",
             "|---|---|---|---|---|---|"]
    for inst, findings in results.items():
        for f in findings:
            lines.append(f"| {inst} | {f.rule_id} {f.title} | {f.status.value} | "
                         f"{f.severity.value} | {f.observed} | {f.expected} |")
    return "\n".join(lines)


def _gate(findings: list[Finding], fail_on: str | None) -> int:
    if not fail_on:
        return 0
    threshold = Severity(fail_on).rank
    bad = [f for f in findings if f.status == Status.FAIL and f.severity.rank >= threshold]
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fleetctl", description="Database fleet compliance")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inventory", help="list the inventory (CMDB)")
    sub.add_parser("discover", help="which databases answer on the network")
    c = sub.add_parser("check", help="check the baseline")
    c.add_argument("--instance", default="all")
    c.add_argument("--format", choices=["text", "json", "markdown"], default="text")
    c.add_argument("--fail-on", choices=[s.value for s in Severity])
    k = sub.add_parser("correlate", help="cross inventory, discovery and facts")
    k.add_argument("--fail-on", choices=[s.value for s in Severity])
    r = sub.add_parser("plan", help="proposed remediation plan for one instance")
    r.add_argument("instance")
    args = p.parse_args(argv)

    fleet = Fleet()
    if args.cmd == "inventory":
        for i in fleet.list_instances():
            print(f"{i['id']:16} {i['engine']:10} {i['environment']:11} {i['hosting']:8} "
                  f"{'in scope' if i['in_scope'] else 'OUT OF SCOPE':12} owner={i['owner']}")
        return 0
    if args.cmd == "discover":
        for name in sorted(fleet.discover()):
            print(name, "" if name in fleet.inventory else "  <- not in the inventory")
        return 0
    if args.cmd == "check":
        results = (fleet.check_all() if args.instance == "all"
                   else {args.instance: fleet.check(args.instance)})
        if args.format == "json":
            print(json.dumps({i: [f.as_dict() for f in fs] for i, fs in results.items()},
                             ensure_ascii=False, indent=1))
        else:
            print(_markdown(results) if args.format == "markdown" else _text(results))
        return _gate([f for fs in results.values() for f in fs], args.fail_on)
    if args.cmd == "correlate":
        findings = fleet.correlate()
        print(_text({"corrélation": findings}))
        return _gate(findings, args.fail_on)
    if args.cmd == "plan":
        print(fleet.remediation_plan(args.instance))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
