# Backlog

Chaque incrément est livrable seul et a sa « definition of done » : code, tests au vert,
lint propre, documentation à jour, CI verte.

## Fait

| # | User story | Preuve |
|---|---|---|
| 1 | En tant qu'exploitant, je veux un référentiel unique PostgreSQL et Oracle, pour homogénéiser le parc | `baseline/rules.yaml`, `tests/test_rules.py` |
| 2 | En tant qu'exploitant, je veux que les bases soient lues en lecture seule, pour ne jamais risquer la production | collecteurs, `test_the_monitoring_session_cannot_write` |
| 3 | En tant que responsable conformité, je veux qu'un fait illisible ne soit jamais déclaré conforme | `test_an_unreachable_database_yields_only_unknowns` |
| 4 | En tant qu'exploitant, je veux croiser CMDB, découverte réseau et sauvegardes, pour trouver ce qu'aucune source ne montre | `correlate.py`, tests de corrélation |
| 5 | En tant qu'utilisateur de Claude, je veux des outils MCP sûrs et audités | `server.py`, `guard.py`, `tests/test_server.py` |
| 6 | En tant qu'utilisateur de Claude, je veux des skills réutilisables pour l'audit, l'analyse et la remédiation | `.claude/skills/`, `tests/test_skills.py` |
| 7 | En tant que responsable conformité, je veux que la CI bloque une dérive, chaque push et chaque nuit | job `fleet` |
| 8 | En tant qu'exploitant Oracle, je veux les mêmes contrôles sur Oracle | `collectors/oracle.py`, job `oracle` |

## À faire

| # | User story |
|---|---|
| 9 | Playbooks Ansible de configuration standard en mode `--check` dans la CI |
| 10 | Scénarios d'évaluation de l'agent (outils attendus pour chaque tâche) |
| 11 | Règles supplémentaires : chiffrement des connexions, comptes par défaut verrouillés |
