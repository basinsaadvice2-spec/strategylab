# StrategyLab — tout ce qu'il faut pour publier

## Comment l'application est reliée au marché (rien à saisir, aucun lien à donner)
```
Marché réel (FRED / Twelve Data)
      │  toutes les heures, automatiquement
      ▼
Fonction Firebase  ──►  Base Firestore (tradermaker-67ddf)
                              │  lue automatiquement
                              ▼
                     Application Python (Streamlit)  ──►  le client voit les graphiques
        (si la base est vide ou injoignable : l'application lit directement les sources du marché)
```
Le client ouvre l'adresse `….streamlit.app` et c'est tout. **Personne n'a d'adresse ni de clé à saisir.** Le « lien » dont
on parlait, c'est seulement l'adresse de l'application terminée, que tu lui envoies. Pas de fichier `.app` : un lien suffit.

## Étape 1 — L'application (GitHub + Streamlit)
Dans ton dépôt GitHub : **Add file → Upload files** → dépose `app.py` (il remplace l'ancien), puis **Commit changes**.
Vérifie que `requirements.txt` est à la racine et `config.toml` dans un dossier `.streamlit/`. Sur share.streamlit.io :
fichier principal `app.py`. L'application se met à jour toute seule à chaque modification (sinon : **Reboot**).

## Étape 2 — La base Firebase qui se remplit toute seule (une seule fois)
Tout est dans `strategylab_firebase_donnees.zip` (guide : `LISEZMOI-FIREBASE.md` dedans). En résumé :
1. Console Firebase : créer **Firestore en mode Production** et passer au **plan Blaze** (carte bancaire ; ce volume reste
   normalement dans les quotas gratuits ; mets une alerte de budget).
2. Google Cloud Shell : envoyer le zip, puis :
```bash
unzip strategylab_firebase_donnees.zip && cd firebase
firebase login --no-localhost
TWELVEDATA_API_KEY=ta_clé ./deploy_firebase.sh        # clé gratuite sur twelvedata.com ; sans clé : pétrole seul
```
3. Dans la console Firebase, Firestore doit contenir `markets/OIL` (et `markets/GOLD`). L'application les lit seule.
La clé de l'or n'est plus à mettre dans Streamlit : elle reste côté Firebase.

## Avant d'envoyer le lien au client
- Ouvre-le sur ton téléphone **et** sur un ordinateur : prix du pétrole à gauche, graphique, onglets du bas ; change la
  période et une condition d'achat.
- Une application gratuite s'endort après un moment sans visite : ouvre le lien toi-même juste avant de l'envoyer.
- Vérifie que l'or apparaît à gauche (si tu as mis la clé).
- Vérifie que l'offre gratuite Twelve Data autorise l'usage prévu avec ton client.

## Si l'écran dit « Aucune donnée de marché disponible »
La raison exacte s'affiche dans un encadré gris sous le message rouge (et dans Manage app → Logs) : **fais-en une capture**.
Elle liste chaque source essayée (Firebase, puis lecture directe) et pourquoi elle a échoué.

## À dire au client
- Simulateur : aucun ordre réel ; les résultats passés ne garantissent pas les performances futures.
- Les données sont **réelles** et rafraîchies automatiquement toutes les heures. Le pétrole n'est publié qu'**une fois par
  jour** par sa source ; un flux « à la seconde » du marché mondial exige un fournisseur de données payant (seule la
  fonction `firebase/functions/index.js` serait à adapter).
- Pétrole : une clôture par jour → bougies reconstruites (pas de vraies mèches), pas d'indicateurs de volume.
- La projection est une plage de probabilité, pas une prédiction. Pas de comptes ni de sauvegarde de stratégies.

## Honnêteté sur les tests
138 tests automatiques passent, et l'application a été exécutée en entier dans un environnement isolé avec un faux
Streamlit et de fausses données (Firebase et sources simulées). **Elle n'a pas pu être lancée sur le vrai Streamlit, la vraie
base Firebase ni les vraies sources depuis mon environnement.** Le premier essai réel est le vrai test : fais-le avant
d'envoyer le lien et montre-moi ce que tu vois s'il y a un souci.

## Pour les développeurs
`projet_complet/` : code modulaire, tests, variante « page HTML + API Cloud Run ». `python -m tools.bundle --out deliver`
régénère `app.py`.
