"""Remediation plans: proposed, ordered, never executed.

A plan lists the failing rules of one instance, most severe first, with the engine's fix and
a warning when the fix needs a restart or a maintenance window.
"""

from __future__ import annotations

from db_autoconformite_mcp.models import Finding, Instance, Status

NEEDS_RESTART = {"R02"}  # archiving: PostgreSQL restart / Oracle MOUNT state


def plan(instance: Instance, findings: list[Finding]) -> str:
    failing = sorted((f for f in findings if f.status == Status.FAIL and f.remediation),
                     key=lambda f: (-f.severity.rank, f.rule_id))
    unknown = [f for f in findings if f.status == Status.UNKNOWN]
    lines = [f"-- Plan de remédiation proposé pour {instance.id} ({instance.engine}, "
             f"{instance.environment})",
             "-- PROPOSITION À VALIDER : rien n'a été exécuté.", ""]
    if not failing:
        lines.append("-- Aucun écart corrigeable.")
    for f in failing:
        lines.append(f"-- [{f.severity.value.upper()}] {f.rule_id} {f.title}: "
                     f"observé {f.observed}, attendu {f.expected}")
        if f.rule_id in NEEDS_RESTART:
            lines.append("-- ATTENTION : redémarrage ou fenêtre de maintenance requis.")
        lines += [f.remediation, ""]
    if unknown:
        lines.append("-- Faits non collectés (à vérifier avant toute conclusion) : "
                     + ", ".join(f.rule_id for f in unknown))
    return "\n".join(lines).rstrip() + "\n"
