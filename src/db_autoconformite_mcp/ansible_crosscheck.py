"""Cross-check two independent tools: what Ansible would change vs what fleetctl reports.

    ANSIBLE_STDOUT_CALLBACK=ansible.builtin.json ansible-playbook ... --check > ansible.json
    uv run fleetctl check --format json > fleet.json
    uv run python -m db_autoconformite_mcp.ansible_crosscheck ansible.json fleet.json

Ansible derives its changes from the exported baseline and its own reading of the roles;
fleetctl from its collectors. If they disagree on which rules an instance breaks, one of
them is wrong, and the job fails. R05 (backups) is not a configuration parameter, so
Ansible cannot fix it and it is left out of the comparison.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from db_autoconformite_mcp.ansible_export import PARAMETER_RULE

STANDARD_TASK = "Paramètres standard du référentiel"
REVOKE_TASK = "Retirer SUPERUSER aux rôles que la CMDB n'autorise pas"
NOT_CONFIG = {"R05"}


def ansible_rules(report: dict) -> dict[str, set[str]]:
    """Per host, the baseline rules Ansible would change something for."""
    out: dict[str, set[str]] = {}
    for play in report["plays"]:
        for task in play["tasks"]:
            name = task["task"]["name"]
            if name not in (STANDARD_TASK, REVOKE_TASK):
                continue
            for host, result in task["hosts"].items():
                rules = out.setdefault(host, set())
                for item in result.get("results", []):
                    if item.get("changed"):
                        rules.add(PARAMETER_RULE[item["item"]["key"]] if name == STANDARD_TASK
                                  else "R04")
                if result.get("failed") or any(i.get("failed") for i in result.get("results", [])):
                    raise RuntimeError(f"ansible task failed on {host}: {name}")
    return out


def fleet_rules(report: dict) -> dict[str, set[str]]:
    """Per instance, the failing rules fleetctl reports, configuration rules only."""
    return {inst: {f["rule_id"] for f in findings
                   if f["status"] == "fail" and f["rule_id"] not in NOT_CONFIG}
            for inst, findings in report.items()}


def compare(ansible: dict[str, set[str]], fleet: dict[str, set[str]]) -> list[str]:
    problems = []
    for host in sorted(set(ansible) | set(fleet)):
        a, f = ansible.get(host, set()), fleet.get(host, set())
        if a != f:
            problems.append(f"{host}: ansible would change {sorted(a)}, "
                            f"fleetctl reports {sorted(f)}")
    return problems


def main(argv: list[str]) -> int:
    ansible = ansible_rules(json.loads(Path(argv[0]).read_text(encoding="utf-8")))
    fleet = fleet_rules(json.loads(Path(argv[1]).read_text(encoding="utf-8")))
    for host in sorted(ansible):
        print(f"{host}: {sorted(ansible[host]) or 'nothing to change'}")
    problems = compare(ansible, fleet)
    for p in problems:
        print("MISMATCH", p)
    print("agreement" if not problems else f"{len(problems)} mismatch(es)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
