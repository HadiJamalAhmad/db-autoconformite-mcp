# Agent ADK sur Vertex AI : mise en place

L'évaluation ADK appelle Gemini sur Vertex AI. Deux façons de la lancer.

## En local

```bash
gcloud services enable aiplatform.googleapis.com --project <projet>
gcloud auth application-default login          # identifiants locaux, jamais dans le dépôt
uv sync --extra adk
GOOGLE_GENAI_USE_VERTEXAI=TRUE GOOGLE_CLOUD_PROJECT=<projet> GOOGLE_CLOUD_LOCATION=global \
  uv run python -m db_autoconformite_mcp.adk_eval --only injection-cmdb
```

Le coût s'affiche si l'on donne les prix lus sur la page de tarifs Vertex AI du modèle choisi :
`--usd-per-mtok <entrée> <sortie>` (en dollars par million de jetons). Sans eux, le rapport
donne les jetons, pas de montant inventé.

## En CI (workflow `adk-eval`), sans clé stockée

GitHub Actions échange son jeton OIDC contre des identifiants Google de courte durée
(Workload Identity Federation). Aucune clé de compte de service n'existe, donc aucune ne peut
fuir. Une seule fois, par le propriétaire du projet :

```bash
PROJECT=<projet>
NUM=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
REPO=HadiJamalAhmad/db-autoconformite-mcp
SA=adk-eval@$PROJECT.iam.gserviceaccount.com

gcloud services enable aiplatform.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  --project $PROJECT
gcloud iam service-accounts create adk-eval --project $PROJECT \
  --display-name "adk-eval (GitHub Actions)"
gcloud projects add-iam-policy-binding $PROJECT \
  --member "serviceAccount:$SA" --role roles/aiplatform.user     # appeler les modèles, rien d'autre

gcloud iam workload-identity-pools create github --project $PROJECT --location global
gcloud iam workload-identity-pools providers create-oidc github-repo --project $PROJECT \
  --location global --workload-identity-pool github \
  --issuer-uri https://token.actions.githubusercontent.com \
  --attribute-mapping google.subject=assertion.sub,attribute.repository=assertion.repository \
  --attribute-condition "assertion.repository=='$REPO'"          # ce dépôt seulement
gcloud iam service-accounts add-iam-policy-binding $SA --project $PROJECT \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/$NUM/locations/global/workloadIdentityPools/github/attribute.repository/$REPO"

gh variable set GCP_PROJECT --body $PROJECT --repo $REPO
gh variable set GCP_WIF_PROVIDER --repo $REPO \
  --body projects/$NUM/locations/global/workloadIdentityPools/github/providers/github-repo
gh variable set GCP_SERVICE_ACCOUNT --body $SA --repo $REPO
```

Ce ne sont pas des secrets : sans le jeton OIDC de CE dépôt, ces identifiants ne donnent rien.
Le compte de service n'a que le rôle `aiplatform.user`. Conseillé : une alerte de budget sur
le projet.

Puis : onglet Actions > adk-eval > Run workflow.
