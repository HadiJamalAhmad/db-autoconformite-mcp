"""Correlation across sources: what no single source can show on its own.

Inputs: the inventory (CMDB), what discovery found answering on the network, and what the
collectors could read. Each finding names the sources that disagree.
"""

from __future__ import annotations

from db_autoconformite_mcp.models import Facts, Finding, Instance, Severity, Status


def correlate(inventory: dict[str, Instance], discovered: set[str],
              facts: dict[str, Facts]) -> list[Finding]:
    out: list[Finding] = []

    def add(rule_id: str, instance: str, severity: Severity, title: str, observed: str,
            expected: str, fix: str = "", status: Status = Status.FAIL) -> None:
        out.append(Finding(rule_id, instance, status, severity, title, observed, expected, fix))

    for name in sorted(discovered - set(inventory)):
        add("C01", name, Severity.HIGH, "Instance découverte absente de l'inventaire",
            "answers on the network", "declared in the CMDB",
            "Déclarer l'instance dans la CMDB (propriétaire, environnement) ou l'arrêter.")

    for inst in sorted(inventory.values(), key=lambda i: i.id):
        if not inst.in_scope:
            add("C04", inst.id, Severity.INFO, "Hors périmètre (cloud public)",
                f"hosting: {inst.hosting}", "on-prem", status=Status.PASS)
            continue
        if inst.id not in discovered:
            add("C02", inst.id, Severity.HIGH, "Instance inventoriée injoignable",
                "not found by discovery", "reachable",
                "Vérifier si l'instance a été décommissionnée ; mettre la CMDB à jour.")
        elif inst.id in facts and facts[inst.id].errors:
            add("C02", inst.id, Severity.MEDIUM, "Instance joignable mais illisible",
                "; ".join(facts[inst.id].errors), "readable by the monitoring account",
                "Vérifier les droits du compte de supervision en lecture seule.")
        if not inst.owner:
            add("C03", inst.id, Severity.MEDIUM, "Instance sans propriétaire",
                "owner: empty", "an accountable team",
                "Renseigner l'équipe propriétaire dans la CMDB.")
    return out
