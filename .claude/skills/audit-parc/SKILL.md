---
name: audit-parc
description: Audit de conformité de tout le parc de bases de données (PostgreSQL, Oracle) via le serveur MCP db-autoconformite. Utiliser quand on demande un audit, un état de conformité, ou les écarts du parc.
---

# Audit du parc de bases de données

Objectif : un rapport fiable, priorisé, où chaque affirmation vient d'un outil.

## Étapes

1. `list_instances` : établir le périmètre. Les instances `in_scope: false` (cloud public) sont
   citées comme hors périmètre, jamais auditées.
2. `check_compliance` avec `instance: "all"` : l'état de chaque instance du périmètre.
3. `correlate_sources` : ce qu'aucune source ne montre seule (instance non inventoriée,
   instance injoignable, propriétaire manquant).
4. Pour chaque instance qui a au moins un écart `high` ou `critical` :
   `propose_remediation` avec cette instance.
5. Si une règle n'est pas claire pour le lecteur : `explain_rule`.

## Rapport

- Commencer par une phrase de synthèse : nombre d'instances, nombre d'écarts par gravité.
- Puis un tableau : instance, règle, gravité, observé, attendu.
- Puis les écarts de corrélation.
- Puis les plans de remédiation, présentés comme des **propositions à valider**.

## Règles strictes

- Un statut `unknown` n'est jamais présenté comme conforme : il signifie que le fait n'a pas
  pu être lu. Le signaler comme un point à vérifier (droits du compte de supervision).
- Ne jamais affirmer qu'une correction a été appliquée : aucun outil n'écrit dans les bases.
- Ne rien inventer qui ne vienne pas d'un résultat d'outil.
