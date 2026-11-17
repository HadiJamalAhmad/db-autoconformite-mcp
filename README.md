# db-autoconformite-mcp

**Automatisation des opérations et de la conformité d'un parc de bases de données hors cloud
(PostgreSQL, Oracle), pilotée par un agent IA (Claude) à travers un serveur MCP.**

L'agent lit la configuration de chaque base, la compare à un référentiel unique, croise
plusieurs sources (bases, inventaire CMDB, sauvegardes, découverte réseau) et propose des
corrections priorisées. Il ne modifie jamais rien : chaque correction est une proposition à
valider par un humain.

[![ci](https://github.com/HadiJamalAhmad/db-autoconformite-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/HadiJamalAhmad/db-autoconformite-mcp/actions/workflows/ci.yml)

---

## 1. Matrice de traçabilité

Chaque exigence de la mission, le module qui y répond, et la preuve vérifiable.

### Industrialisation et automatisation des infrastructures

| Exigence | Réponse dans le dépôt | Preuve |
|---|---|---|
| Développer des outils et scripts pour automatiser les opérations d'infrastructure | `fleetctl` : inventaire, découverte réseau, contrôle, corrélation, plan de remédiation (`src/.../cli.py`, `discovery.py`) | Job CI `fleet` |
| Mettre en place et améliorer les mécanismes d'industrialisation | Parc reproductible (`fleet/compose.yaml`), dépendances verrouillées (`uv.lock`), CI à chaque push et chaque nuit | `.github/workflows/ci.yml` |
| Standardiser les configurations, homogénéiser la plateforme | Un référentiel unique pour les deux moteurs (`baseline/rules.yaml`) : chaque règle donne la source et la correction pour PostgreSQL **et** Oracle | `tests/test_rules.py` |

### Intelligence artificielle et agents

| Exigence | Réponse dans le dépôt | Preuve |
|---|---|---|
| Utiliser des solutions d'IA générative, notamment Claude | Serveur déclaré pour Claude Code (`.mcp.json`) ; utilisable aussi depuis Claude Desktop | Section 4 |
| Développer et améliorer des agents IA pour automatiser des tâches techniques | 6 outils MCP + prompt système de l'agent (`prompts/agent-conformite.md`) | `tests/test_server.py` |
| Concevoir des prompts et développer des skills réutilisables | 3 skills : `audit-parc`, `analyse-ecart`, `plan-remediation` (`.claude/skills/`) | `tests/test_skills.py` (les skills ne citent que des outils existants) |

### Intégration MCP et corrélation de données

| Exigence | Réponse dans le dépôt | Preuve |
|---|---|---|
| Développer ou intégrer des serveurs MCP | `src/.../server.py`, SDK MCP officiel (v2), outils annotés en lecture seule | Tests à travers le vrai protocole MCP (client en mémoire) |
| Connecter les agents à plusieurs sources de données et outils | 4 sources : les bases (PostgreSQL, Oracle), l'inventaire CMDB, le journal des sauvegardes, la découverte réseau | `tests/test_correlate_guard_plan.py` |
| Collecter, croiser et corréler des informations de plusieurs systèmes | `correlate.py` : instance qui répond mais absente de la CMDB, instance inventoriée injoignable, propriétaire manquant, hors périmètre | Tests de corrélation, unitaires et sur le parc réel |

### Automatisation de la conformité

| Exigence | Réponse dans le dépôt | Preuve |
|---|---|---|
| Mettre en place des mécanismes d'auto-conformité | `fleetctl check --fail-on high` bloque la CI ; contrôle planifié chaque nuit | Job `fleet` : étape « the compliance gate blocks the deliberate drifts » |
| Automatiser les contrôles, faciliter la détection des écarts | Évaluation pure des règles : observé, attendu, gravité, correction | `tests/test_rules.py` |
| Fiabilité, standardisation, amélioration continue | Un fait illisible donne « inconnu », **jamais** « conforme » ; journal d'audit de chaque appel | `tests/test_collectors.py` (base injoignable : aucun « conforme ») |

### Outils

| Outil | Usage |
|---|---|
| Python | Tout le code (3.12, `uv`, `ruff`, `pytest`) |
| Claude | L'agent : serveur MCP, skills, prompt système |
| Serveurs MCP | `db-autoconformite-mcp` (stdio) |
| Cloud | Filtrage du périmètre (les bases natives du cloud public sont exclues, comme dans la mission) ; conteneurs ; CI GitHub |
| Bases de données Oracle | Collecteur Oracle (`V$` et `DBA_`) testé contre **Oracle Database Free** dans la CI |

---

## 2. Contexte

Le parc de démonstration reproduit le périmètre de la mission : des bases **non natives du
cloud public**, avec des écarts réalistes.

| Instance | Moteur | Environnement | Situation |
|---|---|---|---|
| `pg-prod-01` | PostgreSQL 17 | production | conforme |
| `pg-prod-02` | PostgreSQL 17 | production | dérives : connexions non journalisées, archivage désactivé, hachage MD5, superutilisateur oublié, délai d'inactivité absent ; dernière sauvegarde réussie il y a 50 h (celle d'il y a 2 h a échoué) |
| `pg-recette-01` | PostgreSQL 17 | recette | sans propriétaire dans la CMDB, sans sauvegarde, délai d'inactivité absent |
| `pg-shadow-01` | PostgreSQL 17 | ? | répond sur le réseau mais **absente de l'inventaire** |
| `pg-cloud-01` | PostgreSQL | production | native du cloud public : **hors périmètre** |
| `ora-ci-01` | Oracle 23 Free | production | dans la CI : un compte `LEGACY_ADMIN` avec le rôle DBA, NOARCHIVELOG, aucune sauvegarde RMAN |

---

## 3. Le référentiel de conformité

| Règle | Contrôle | PostgreSQL | Oracle |
|---|---|---|---|
| R01 | Journalisation des connexions | `log_connections` | politique d'audit unifié sur `LOGON` |
| R02 | Archivage des journaux | `archive_mode` | `V$DATABASE.LOG_MODE` |
| R03 | Hachage robuste des mots de passe | `password_encryption` | `DBA_USERS.PASSWORD_VERSIONS` |
| R04 | Comptes à privilèges maîtrisés | `pg_roles.rolsuper` | `DBA_ROLE_PRIVS` (rôle DBA) |
| R05 | Sauvegarde récente (24 h en production) | journal de l'outil de sauvegarde | `V$RMAN_BACKUP_JOB_DETAILS` |
| R06 | Délai d'inactivité des sessions | `idle_in_transaction_session_timeout` | `DBA_PROFILES.IDLE_TIME` |

Corrélation : **C01** instance non inventoriée, **C02** instance inventoriée injoignable ou
illisible, **C03** propriétaire manquant, **C04** hors périmètre.

Une sauvegarde manquante sur une base de production marquée critique dans la CMDB passe en
gravité **critique** : la gravité dépend du contexte, pas seulement de la règle.

---

## 4. Utilisation

```bash
uv sync
cp .env.example .env                                   # choisir des mots de passe locaux
docker compose -f fleet/compose.yaml --env-file .env up -d --wait
uv run python fleet/seed_backups.py

uv run fleetctl inventory
uv run fleetctl check                                  # tout le périmètre
uv run fleetctl check --instance pg-prod-02 --fail-on high
uv run fleetctl correlate
uv run fleetctl plan pg-prod-02                        # plan proposé, rien n'est exécuté
```

**Avec Claude Code** : le serveur est déclaré dans `.mcp.json`. Ouvrir le dépôt et demander,
par exemple, « Audite le parc » : le skill `audit-parc` déroule les outils et rédige le rapport.

**Avec Claude Desktop** : ajouter le serveur dans la configuration MCP :

```json
{ "mcpServers": { "db-autoconformite": {
    "command": "uv",
    "args": ["--directory", "/chemin/vers/db-autoconformite-mcp", "run", "db-autoconformite-mcp"] } } }
```

### Les outils MCP

| Outil | Rôle |
|---|---|
| `list_instances` | le parc et son périmètre, depuis la CMDB |
| `get_config` | la configuration d'une instance, faits manquants compris |
| `check_compliance` | le contrôle d'une instance ou de tout le périmètre |
| `correlate_sources` | le croisement des sources |
| `explain_rule` | la justification d'une règle et son équivalent sur chaque moteur |
| `propose_remediation` | le plan de correction priorisé, à valider |

La ressource `baseline://rules` expose le référentiel.

---

## 5. Sécurité

- **Lecture seule à trois niveaux** : outils annotés en lecture seule, session PostgreSQL en
  `default_transaction_read_only` (testé : une écriture est refusée par le serveur), compte
  Oracle limité à `CREATE SESSION`, `SELECT_CATALOG_ROLE` et `AUDIT_VIEWER`.
- **Aucune requête venue de l'agent** : les collecteurs n'exécutent que des requêtes fixes.
- **Liste blanche** : seules les instances inventoriées et dans le périmètre sont accessibles ;
  les identifiants sont validés avant tout traitement.
- **Délais maximum** sur chaque connexion et chaque requête.
- **Journal d'audit** : chaque appel d'outil (accepté ou refusé) est tracé.
- **Secrets** : uniquement par variables d'environnement ; scan `gitleaks` de tout
  l'historique et audit des dépendances (`pip-audit`) en CI.

---

## 6. Qualité et intégration continue

| Job | Contenu |
|---|---|
| `test` | lint et 50 tests sans base de données, dont le protocole MCP |
| `security` | scan de secrets et audit des dépendances |
| `fleet` | les 4 PostgreSQL réels : tests d'intégration, rapport de conformité publié, preuve que le contrôle bloque les dérives |
| `oracle` | Oracle Database Free : chaque fait lisible avec les droits minimaux, dérives détectées |

---

## 7. Méthode et suite

Le travail est découpé en incréments livrables, chacun avec ses tests ; le détail est dans
[`docs/backlog.md`](docs/backlog.md).

**Prochaines étapes** :
- playbooks Ansible de configuration standard, exécutés en mode vérification (`--check`) dans la CI ;
- scénarios d'évaluation de l'agent (enchaînement des outils attendu par tâche) ;
- règles supplémentaires (chiffrement des connexions, comptes par défaut verrouillés).

---

Licence MIT. Le parc est une démonstration : il ne contient aucune donnée réelle.
