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
| 9 | En tant qu'exploitant, je veux corriger avec Ansible à partir du même référentiel, et vérifier | `ansible/`, job `ansible` |
| 10 | En tant que responsable, je veux mesurer que l'agent se comporte correctement, injection comprise | `evals/`, `agent_eval.py` |

## À faire

| # | User story |
|---|---|
| 11 | Règles supplémentaires : chiffrement des connexions, comptes par défaut verrouillés |
| 12 | Règle : paramètre imposé hors de portée d'`ALTER SYSTEM` (`pg_settings.source = 'command line'`). Trouvé par la CI : une correction appliquée par `ALTER SYSTEM` était masquée à chaque redémarrage par la ligne de commande |
| 13 | Évaluation de l'agent planifiée en CI (clé d'API en secret GitHub) |
