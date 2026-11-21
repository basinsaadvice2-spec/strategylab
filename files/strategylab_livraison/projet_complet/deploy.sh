#!/usr/bin/env bash
# Déploie l'API Python sur Google Cloud Run, puis fabrique dist/index.html relié à cette API.
# À lancer dans Google Cloud Shell (https://shell.cloud.google.com), depuis ce dossier :
#     ./deploy.sh
# Options (variables d'environnement) :
#     TWELVEDATA_API_KEY=ta_clé   pour activer l'or
#     ALLOWED_ORIGINS="https://mon-site.netlify.app"   sites autorisés à appeler l'API ("*" par défaut)
#     PROJECT, REGION, SERVICE    (défauts ci-dessous)
set -euo pipefail

PROJECT="${PROJECT:-tradermaker-67ddf}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-strategylab-api}"

gcloud config set project "$PROJECT"
# Adresse prévisible du service (format documenté par Google) : sert à vérifier l'index.html préconfiguré.
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
EXPECTED_URL="https://${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

ENV_VARS="ALLOWED_ORIGINS=${ALLOWED_ORIGINS:-*}"
if [ -n "${TWELVEDATA_API_KEY:-}" ]; then
  ENV_VARS="${ENV_VARS},TWELVEDATA_API_KEY=${TWELVEDATA_API_KEY}"
fi

# Si gcloud propose de créer un dépôt Artifact Registry : répondre y.
gcloud run deploy "$SERVICE" --source . --region "$REGION" --allow-unauthenticated \
  --max-instances 2 --memory 512Mi --cpu 1 --concurrency 20 --timeout 60 \
  --set-env-vars "$ENV_VARS"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
mkdir -p dist
python3 -m web.build --api-url "$URL" --out dist/index.html

echo
if [ "$URL" = "$EXPECTED_URL" ]; then
  echo "OK : l'index.html déjà fourni est configuré pour cette adresse, rien à changer."
else
  echo "ATTENTION : adresse différente de celle prévue ($EXPECTED_URL)."
  echo "Utilise le dist/index.html généré maintenant : il contient la bonne adresse."
fi
echo "API en ligne  : $URL"
echo "La page est aussi servie directement sur cette adresse."
echo "Fichier à héberger sur Netlify / Vercel : dist/index.html"
echo "Pour le télécharger :  cloudshell download dist/index.html"
