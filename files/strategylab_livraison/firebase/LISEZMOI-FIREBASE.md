# Firebase — la base qui se remplit toute seule

Ce que ça fait : une fonction **se déclenche toute seule toutes les heures**, va chercher les prix réels (pétrole : EIA via
FRED ; or : Twelve Data), les contrôle et les écrit dans ta base Firestore (`tradermaker-67ddf`). L'application les lit
automatiquement : **personne n'a de lien ni d'adresse à saisir**. Si la base est vide ou injoignable, l'application passe
toute seule en lecture directe des sources.

## À faire une seule fois
1. **Console Firebase** (console.firebase.google.com → projet tradermaker-67ddf) :
   - *Firestore Database → Create database* → mode **Production** (jamais « mode test »).
   - *Passer au plan Blaze* (« Upgrade », en bas à gauche) : indispensable pour les fonctions planifiées. Paiement à
     l'usage avec carte bancaire ; ce volume (une petite fonction par heure) reste normalement dans les quotas
     gratuits. Mets une alerte de budget dans Google Cloud.
2. **Google Cloud Shell** (shell.cloud.google.com) : menu ⋮ → Upload → `strategylab_firebase_donnees.zip`, puis :
```bash
unzip strategylab_firebase_donnees.zip && cd firebase
firebase login --no-localhost                      # suis le lien, colle le code affiché
TWELVEDATA_API_KEY=ta_clé ./deploy_firebase.sh     # sans clé : pétrole seul
```
3. Vérifie : console Firebase → Firestore → tu dois voir `markets/OIL` (et `markets/GOLD` avec la clé).

## Sécurité
- Règles Firestore : lecture seule, limitée à `GOLD` et `OIL`. **Aucune écriture possible depuis l'extérieur** ; seule la
  fonction écrit. La clé web Firebase placée dans l'application n'est pas un secret.
- La clé de l'or (Twelve Data) reste dans `functions/.env`, jamais sur GitHub.
- Si tu restreins plus tard la clé API web à des sites (referrers), la lecture par l'application sera refusée : ne le
  fais pas, ou autorise aussi les appels serveur.

## À savoir
- Le pétrole n'est publié qu'**une fois par jour** par sa source : « toutes les heures » veut dire « dès que la source
  publie », pas seconde par seconde. Un vrai flux à la seconde exige un fournisseur payant ; seule `functions/index.js`
  serait à adapter.
- Pétrole : une clôture par jour → bougies reconstruites, indicateurs de volume désactivés.
