---
name: analyse-ecart
description: Analyser un écart de conformité précis sur une instance (pourquoi la règle existe, ce qui est observé, le risque, la correction). Utiliser quand on demande d'expliquer un écart ou une règle R01 à R06, C01 à C04.
---

# Analyse d'un écart

1. `explain_rule` avec l'identifiant de la règle : justification, source du fait pour chaque
   moteur (PostgreSQL et Oracle), correction proposée.
2. `get_config` sur l'instance concernée : la valeur réellement observée, et les faits
   manquants éventuels (`missing`).
3. `check_compliance` sur cette instance pour confirmer le statut et la gravité.

## Réponse attendue

- **Constat** : valeur observée et valeur attendue, avec l'outil qui les a fournies.
- **Risque** : en une ou deux phrases, à partir de la justification de la règle.
- **Équivalence** : où le même contrôle se lit sur l'autre moteur.
- **Correction** : la proposition, avec ses conditions (redémarrage, fenêtre de maintenance).

Si le fait figure dans `missing`, l'écart ne peut pas être conclu : le dire, et indiquer
qu'il faut vérifier les droits du compte de supervision.
