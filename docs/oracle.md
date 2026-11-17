# Oracle : collecteur, droits minimaux et notions utiles

Le collecteur Oracle (`src/db_autoconformite_mcp/collectors/oracle.py`) lit le dictionnaire de
données avec `python-oracledb` en mode léger (thin) : aucun client Oracle à installer. Il est
testé à chaque push contre **Oracle Database Free 23** dans la CI (job `oracle`).

## Le compte de supervision

```sql
CREATE USER autoconformite_ro IDENTIFIED BY "<secret>";
GRANT CREATE SESSION, SELECT_CATALOG_ROLE TO autoconformite_ro;
GRANT AUDIT_VIEWER TO autoconformite_ro;
```

| Droit | Pourquoi |
|---|---|
| `CREATE SESSION` | se connecter |
| `SELECT_CATALOG_ROLE` | lire les vues `DBA_` et `V$` (paramètres, comptes, sauvegardes) |
| `AUDIT_VIEWER` | lire les politiques d'audit unifié (règle R01) |

Rien d'autre : pas de `SELECT ANY DICTIONARY`, aucun droit d'écriture. La CI vérifie que
chaque fait est lisible avec ces seuls droits (`test_oracle_every_fact_is_readable_with_the_minimum_grants`).

## Ce que lit chaque règle

| Règle | Vue | Valeur conforme |
|---|---|---|
| R01 | `AUDIT_UNIFIED_ENABLED_POLICIES` jointe à `AUDIT_UNIFIED_POLICIES` | au moins une politique activée qui audite `LOGON` |
| R02 | `V$DATABASE.LOG_MODE` | `ARCHIVELOG` |
| R03 | `DBA_USERS.PASSWORD_VERSIONS` (comptes non maintenus par Oracle) | aucun vérificateur `10G` |
| R04 | `DBA_ROLE_PRIVS` (rôle `DBA`), hors `DBA_USERS.ORACLE_MAINTAINED = 'Y'` | uniquement les comptes autorisés dans la CMDB |
| R05 | `V$RMAN_BACKUP_JOB_DETAILS` (`STATUS = 'COMPLETED'`) | dernière sauvegarde de moins de 24 h en production |
| R06 | `DBA_PROFILES`, profil `DEFAULT`, ressource `IDLE_TIME` | différente de `UNLIMITED` |

## Résultat sur une base Oracle Database Free neuve (CI)

| Règle | Statut | Observé |
|---|---|---|
| R01 | écart (moyen) | aucune politique d'audit sur LOGON activée |
| R02 | écart (élevé) | NOARCHIVELOG |
| R03 | conforme | pas de vérificateur 10G |
| R04 | écart (critique) | `LEGACY_ADMIN` détient le rôle DBA (dérive créée par `fleet/oracle/setup_ci.py`) |
| R05 | écart (critique) | aucune sauvegarde RMAN |
| R06 | écart (faible) | `IDLE_TIME` illimité |

Aucun fait inconnu : les droits minimaux suffisent.

## Notions Oracle derrière les règles

- **Instance et base.** L'instance, ce sont les processus et la mémoire (SGA partagée, PGA
  par session) ; la base, ce sont les fichiers (données, journaux de reprise, fichiers de
  contrôle). Une instance ouvre une base.
- **CDB et PDB.** Depuis la 12c, une base conteneur (CDB) héberge des bases enfichables (PDB).
  Ici, le collecteur se connecte à la PDB `FREEPDB1`. Les vues `CDB_` couvrent tout le
  conteneur, les vues `DBA_` la PDB courante.
- **Paramètres.** Stockés dans le fichier de paramètres serveur (spfile) ; `ALTER SYSTEM SET
  ... SCOPE = MEMORY | SPFILE | BOTH` choisit si le changement est immédiat, au prochain
  démarrage, ou les deux. Lus dans `V$PARAMETER`.
- **Vues `V$` et `DBA_`.** `V$` : l'état dynamique de l'instance (mémoire, sessions,
  sauvegardes) ; `DBA_` : le dictionnaire de données (comptes, droits, profils).
- **Profils.** Limites de ressources et politique de mots de passe d'un compte : durée de vie,
  tentatives, `IDLE_TIME` (R06).
- **Audit unifié.** Depuis la 12c, un seul journal d'audit, piloté par des politiques
  (`CREATE AUDIT POLICY`, `AUDIT POLICY`). R01 vérifie qu'une politique audite les connexions.
- **ARCHIVELOG.** Les journaux de reprise sont archivés avant d'être réécrits : indispensable
  pour restaurer à un instant précis. Le passage en ARCHIVELOG se fait base montée et non
  ouverte, d'où la fenêtre de maintenance signalée par le plan de remédiation (R02).
- **RMAN.** L'outil de sauvegarde et de restauration d'Oracle ; son historique se lit dans
  `V$RMAN_BACKUP_JOB_DETAILS` (R05).
- **Vérificateurs de mots de passe.** `PASSWORD_VERSIONS` liste les formats d'empreinte
  stockés pour un compte : `10G` est ancien et faible, `11G` et `12C` sont plus robustes (R03).
