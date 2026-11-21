# StrategyLab — analyse en Python, page web reliée à distance

Simulateur de stratégies sur le **pétrole (WTI)** et l'**or (XAU/USD)**, avec données réelles.
Aucun ordre réel, aucune connexion à un courtier. Un backtest ne garantit jamais la performance future.

## Version à livrer (recommandée) : un fichier, un lien
`python -m tools.bundle --out deliver` produit **`deliver/app.py`** (toute l'application, 23 modules embarqués tels quels,
intégrité vérifiée à la construction) + `requirements.txt` + `.streamlit/config.toml`. Ces 3 fichiers sur GitHub, puis
Streamlit Community Cloud (gratuit) : un lien à envoyer au client. Python fait tout : données réelles, analyse, interface.
Pas de serveur à relier, pas d'adresse à saisir, pas de Firebase. Voir `LISEZMOI-DEPLOIEMENT.md`.
Le reste de ce document décrit la **variante** « page HTML + API Python sur Cloud Run ».

## Architecture
```
Navigateur ── index.html (Netlify / Vercel / n'importe où) ── graphiques TradingView Lightweight Charts
                  │  appels HTTPS (JSON)
                  ▼
        API Python (Google Cloud Run)  ── tout le calcul : indicateurs, backtest, risque, projection
                  │
                  ▼
        FRED (pétrole, gratuit)   ·   Twelve Data (or, clé gratuite)
```
- **`index.html`** : page unique, sans dépendance à installer. Elle ne calcule rien : elle envoie la configuration
  à l'API et affiche la réponse.
- **API** (`api/server.py`) : bibliothèque standard + pandas/numpy. Les données sont rechargées au plus toutes les
  heures (cache partagé). Si la source tombe, la dernière copie est servie avec un avertissement.
- Le dossier contient aussi une interface Streamlit (`ui/streamlit_app.py`), facultative.

## Mise en ligne — 2 gestes

L'`index.html` fourni est **déjà configuré** pour l'adresse prévue de ton serveur
(`https://strategylab-api-311803000887.europe-west1.run.app`, déduite du numéro de ton projet Google
`tradermaker-67ddf`, selon le format d'adresse documenté par Google Cloud Run). Il ne demande rien à l'utilisateur.

### 1. Déployer le serveur Python (une seule fois)
Prérequis : facturation activée sur le projet Google (Cloud Run a un quota gratuit ; mets une alerte de budget).
Dans **Cloud Shell** (https://shell.cloud.google.com) :
```bash
# Menu ⋮ → Upload → strategylab_python_tradingview.zip
unzip strategylab_python_tradingview.zip && cd strategylab_v1
TWELVEDATA_API_KEY=ta_clé ./deploy.sh        # clé gratuite sur twelvedata.com ; sans clé, seul le pétrole marche
```
Si gcloud propose de créer un dépôt Artifact Registry, réponds `y`. À la fin, le script vérifie l'adresse et affiche
« OK : l'index.html déjà fourni est configuré pour cette adresse ». S'il affiche « ATTENTION », il fabrique un
`dist/index.html` avec la bonne adresse (`cloudshell download dist/index.html`).

### 2. Donner le lien au client
- **Le plus simple** : le lien du serveur lui-même (`https://strategylab-api-311803000887.europe-west1.run.app`) affiche
  déjà la page. Rien d'autre à héberger.
- **Ou** héberger `index.html` sur Netlify (app.netlify.com/drop) ; Vercel demande, à ma connaissance, un dépôt Git
  ou son terminal. Aucune configuration supplémentaire : tous les sites sont autorisés par défaut.

### Facultatif : restreindre l'API à ton site
```bash
gcloud run services update strategylab-api --region europe-west1 \
  --update-env-vars ALLOWED_ORIGINS="https://ton-site.netlify.app"
```
(plusieurs sites séparés par `;`). Cela empêche d'autres pages web d'utiliser ton API via le navigateur de leurs
visiteurs ; la protection contre l'abus repose sur `--max-instances 2`, la limite de 4 calculs simultanés et la taille
de requête plafonnée à 20 Ko.

## Données réelles
- **Pétrole** : EIA via FRED, sans clé. Une seule clôture par jour → bougies reconstruites (pas de vraies mèches),
  indicateurs de volume désactivés. Jours à prix ≤ 0 (ex. avril 2020) écartés.
- **Or** : Twelve Data, **clé gratuite obligatoire** (aucune source d'or fiable sans clé n'a été trouvée) (variable `TWELVEDATA_API_KEY`, jamais dans le code). Sans clé, l'or est
  indiqué indisponible : rien n'est inventé. Selon la source, l'or peut ne pas avoir de volume.
- Les indicateurs sont calculés sur tout l'historique puis la période est découpée (une SMA 200 reste définie sur
  « 3 jours »). Aucun look-ahead : exécution à l'ouverture suivante.
- **Projection** : Monte Carlo (2000 trajectoires, graine fixe), tendance nulle : une plage de probabilité, **pas une
  prédiction de direction**.

## Sécurité
- Aucune clé dans le code ni dans les logs ; elle est masquée dans les messages d'erreur (testé).
- L'API valide chaque champ (bornes, types, 5 conditions maximum, dates), refuse les corps > 20 Ko, ne renvoie jamais
  de trace d'erreur, coupe les connexions lentes, et n'accepte que les origines autorisées (CORS).
- La page n'insère jamais de données dans le HTML (aucun `innerHTML`, vérifié par un test) : pas d'injection possible.
- Le conteneur tourne sans droits root. Variables sensibles : préfère Secret Manager à `--set-env-vars` pour la clé
  (visible sinon par les éditeurs du projet).
- **Non fait** (non testable sans navigateur réel) : Content-Security-Policy, authentification des utilisateurs.

## Tests
```bash
pip install pytest pandas numpy && pytest tests/ -v          # 120 tests
node tests/e2e/page_e2e.js …                                  # page ↔ API, voir tests/e2e/README.md
```
Ils couvrent le moteur, l'API (entrées invalides, CORS, limites, erreurs), la construction de la page et le
parcours complet page ↔ serveur avec un faux navigateur. **Ils ne remplacent pas un premier essai dans un vrai
navigateur et un vrai déploiement Cloud Run.**

## Limites connues
- Séries journalières, long uniquement, une position à la fois. Pas de minute par minute avec ces sources gratuites.
- Pas de comptes utilisateurs, pas de sauvegarde de stratégies ni d'historique des tests (menu de la maquette non
  reproduit).
- Le cache est en mémoire : une instance qui se réveille recharge les données (1 à 2 s).
- Exemples et aperçu autonome : `python -m ui.preview_page apercu.html` (données simulées).
