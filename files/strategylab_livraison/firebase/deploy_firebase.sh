#!/usr/bin/env bash
# Met en place la base de données Firebase alimentée automatiquement toutes les heures.
# À lancer dans Google Cloud Shell (https://shell.cloud.google.com), depuis ce dossier :
#     firebase login --no-localhost        # une seule fois : suis le lien, colle le code affiché
#     ./deploy_firebase.sh                 # pétrole seul
#     TWELVEDATA_API_KEY=ta_clé ./deploy_firebase.sh     # pétrole + or (clé gratuite sur twelvedata.com)
# Prérequis : Firestore créé en mode PRODUCTION et plan Blaze activé (voir LISEZMOI-FIREBASE.md).
set -euo pipefail
cd "$(dirname "$0")"
PROJECT="${PROJECT:-tradermaker-67ddf}"

command -v firebase >/dev/null || npm install -g firebase-tools
(cd functions && npm install --no-audit --no-fund)
if [ -n "${TWELVEDATA_API_KEY:-}" ]; then
  printf 'TWELVEDATA_API_KEY=%s\n' "$TWELVEDATA_API_KEY" > functions/.env      # lu par la fonction, jamais envoyé sur GitHub
fi

# Publie les règles Firestore (lecture seule, aucune écriture depuis l'extérieur) et la fonction horaire.
firebase deploy --project "$PROJECT" --only functions,firestore:rules

# Premier remplissage immédiat (sinon il faudrait attendre l'heure pile).
JOB="$(gcloud scheduler jobs list --project "$PROJECT" --location us-central1 --format='value(name)' 2>/dev/null | grep -i updateMarketData | head -1 || true)"
if [ -n "$JOB" ]; then
  gcloud scheduler jobs run "${JOB##*/}" --project "$PROJECT" --location us-central1 && echo "Premier remplissage lancé."
else
  echo "Lance le premier remplissage à la main : console Google Cloud → Cloud Scheduler → la tâche updateMarketData → Force run."
fi
echo "Terminé. Dans 1 à 2 minutes, la console Firebase → Firestore doit contenir markets/OIL."
