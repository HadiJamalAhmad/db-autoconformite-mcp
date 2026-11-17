---
name: plan-remediation
description: Préparer un plan de remédiation à faire valider pour une instance ou tout le parc, priorisé par gravité, avec les fenêtres de maintenance nécessaires. Utiliser quand on demande comment corriger les écarts.
---

# Plan de remédiation

1. `check_compliance` (l'instance demandée, ou `all`) pour lister les écarts.
2. `propose_remediation` pour chaque instance en écart.
3. Regrouper les actions :
   - **sans interruption** (paramètres rechargeables, révocation de droits) ;
   - **avec fenêtre de maintenance** (signalées par l'outil : redémarrage requis).
4. Ordonner par gravité, en commençant par `critical`.

## Format

Un plan par instance : action, commande proposée, gravité, impact (interruption ou non),
et une ligne « Validation requise : propriétaire de l'instance ».

Ne jamais présenter le plan comme exécuté : les outils proposent, un humain valide et
applique. Après application, relancer `check_compliance` pour vérifier le retour à la
conformité.
