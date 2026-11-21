# RAPPORT_AUDIT — StrategyLab V1

## 8. Audit — comment la fiabilité du backtest est garantie

### Anti-look-ahead bias
- Les signaux ACHAT/VENTE sont calculés à la clôture de la barre T à partir
  de données connues à T (`strategy/builder.py`).
- **L'exécution a toujours lieu à l'ouverture de la barre T+1**
  (`backtest/engine.py`), jamais sur la clôture de T. C'est la garantie
  structurelle principale contre le look-ahead — testée explicitement par
  `tests/test_backtest.py::test_no_lookahead_price_spike_on_signal_bar_does_not_affect_entry_price`
  et par `tests/test_no_lookahead.py` (modifier le futur ne doit jamais
  changer un signal passé).
- Les indicateurs eux-mêmes (`indicators/`) n'utilisent que `rolling`/`ewm`
  avec `min_periods` strict : ils renvoient `NaN` pendant le préchauffage
  plutôt qu'une estimation biaisée sur fenêtre incomplète.

### Ambiguïté SL/TP intra-bougie
Avec des données OHLC (pas de tick-by-tick), impossible de savoir avec
certitude si le stop-loss ou le take-profit a été touché en premier quand
les deux sont dans le `[low, high]` de la même bougie. Le moteur ne devine
pas silencieusement : il applique une politique **configurable**
(`SLTP_AMBIGUITY_POLICY`, par défaut `stop_first` — l'hypothèse la plus
prudente) et **marque chaque trade concerné** (`sltp_ambiguous=True`) pour
que ce soit visible dans le rapport, pas caché.

### Frais et slippage
Commission et slippage sont appliqués à l'entrée ET à la sortie, jamais
ignorés. `tests/test_backtest.py::test_commission_and_slippage_reduce_pnl`
vérifie qu'ils réduisent bien le P&L.

### Risque et position sizing
Le sizing suit exactement la formule du cahier des charges
(`risk/position_sizing.py`, testé contre l'exemple donné : 10 000 $ × 2 % =
200 $ de risque théorique). La quantité est ensuite plafonnée par le cash
réellement disponible — jamais de position à crédit
(`test_position_cost_never_exceeds_available_cash`).

### Données
`data/loader.py` reprend et généralise les corrections faites sur le
premier projet (trading bot V0) : valeurs manquantes détectées
explicitement (une cellule vide ne devient plus un NaN silencieux),
cohérence OHLC vérifiée, timestamps dupliqués ou désordonnés **signalés**
(pas juste corrigés en silence), valeurs infinies rejetées.

### Validation / data leakage
`data/periods.py::chronological_split` découpe développement / validation /
hors-échantillon **dans l'ordre chronologique strict** (jamais un mélange
aléatoire qui laisserait filtrer de l'information future dans le passé).
Le rapport signale explicitement (`reliable_sample`) quand le nombre de
trades est trop faible (< `MIN_TRADES_FOR_RELIABLE_STATS` = 20) pour une
interprétation solide — conformément à la consigne de ne jamais présenter
un résultat comme fiable s'il ne l'est pas statistiquement.

### Reproductibilité
Le moteur ne contient aucun aléatoire : `test_reproducibility_same_inputs_same_outputs`
vérifie que deux runs identiques produisent des résultats bit-à-bit
identiques.

### Sécurité
Aucune clé API, aucun accès courtage, aucun stockage de mot de passe.
Vérifié par lecture complète du code : le projet ne contient aucun client
d'échange/courtier, aucune fonction d'envoi d'ordre.

## Tests — couverture

`pytest tests/ -v` → 50 tests (à rejouer avec un vrai pytest ; ils ont été
exécutés manuellement pendant cet audit via un harnais compatible
`pytest.raises`/`pytest.approx`, faute d'accès réseau pour installer
pytest dans cet environnement — **à revalider avec le vrai pytest avant
mise en prod interne**). Couvrent : données manquantes/dupliquées/désordonnées,
chaque indicateur (valeurs connues), logique AND/OR, sizing, achat/vente,
SL/TP (y compris l'ambiguïté et ses deux politiques), frais/slippage,
capital insuffisant, absence de look-ahead, rendement/drawdown,
reproductibilité, découpage dev/validation/OOS.

## 9. Problèmes connus / limites de la V1

- **Données synthétiques uniquement.** Aucune vraie donnée Gold/Oil n'est
  fournie ni récupérée automatiquement (le cahier des charges exclut le
  cloud/API payante obligatoire) — il faut fournir un CSV réel au même
  format pour un backtest exploitable en pratique.
- **Long uniquement.** Pas de vente à découvert en V1 (non demandée
  explicitement, mais à clarifier si le client en a besoin).
- **Une seule position à la fois.** Pas de pyramidage ni de plusieurs
  positions simultanées sur le même actif.
- **Rendements journaliers non annualisés dans le rapport de base** — à
  ajouter si le client veut comparer des périodes de durées différentes
  sur une base commune (ex. rendement annualisé, Sharpe annualisé).
- **La politique SL/TP "stop_first" par défaut est une hypothèse, pas un
  fait** — sur des données réelles avec granularité plus fine (H1, M15),
  l'ambiguïté diminue mais ne disparaît jamais totalement en OHLC pur.
- **Le Strategy Builder ne supporte que AND ou OR "plat"** (pas de
  parenthèses imbriquées type `(A ET B) OU C`) — suffisant pour l'exemple
  du cahier des charges, à étendre si le client a besoin de logique plus
  riche.
- **Interface Streamlit non testée en conditions réelles** dans cet
  environnement (pas de serveur exposé ici) — le code est complet et
  suit l'API Streamlit standard, mais un test manuel `streamlit run` est
  recommandé avant démonstration client.
- **Frais de change/financement overnight non modélisés** (pertinent pour
  Gold/Oil tradés en CFD/futures avec frais de portage) — à ajouter en V2
  si le produit réel du client en comporte.

## 10. Plan V2 (proposition)

1. **Connecter une vraie source de données** Gold/Oil (fichier fourni par
   le client, ou un `DataProvider` supplémentaire) — aucun changement
   requis dans `indicators/`, `strategy/`, `backtest/` grâce à l'abstraction
   déjà en place.
2. **Rendements et Sharpe annualisés**, comparables entre périodes de
   durées différentes.
3. **Logique de règles imbriquée** (parenthèses, groupes AND/OR combinés).
4. **Walk-forward / optimisation de paramètres** sur le bloc développement
   uniquement, avec validation stricte sur le bloc hors-échantillon jamais
   touché pendant l'optimisation.
5. **Support du short** si le client en a l'usage.
6. **Rapport exportable** (PDF/Excel) en plus du JSON/CSV actuel.
7. **CI automatisée** (GitHub Actions) pour exécuter `pytest` à chaque
   modification.
8. **Test manuel de l'interface Streamlit** en conditions réelles avec le
   client, puis itération sur l'ergonomie du Strategy Builder.

## Rappel — ce que cette V1 n'est PAS

Ce n'est pas un outil de trading réel. Il n'y a aucun ordre envoyé, aucune
connexion à un compte, aucune clé API stockée. C'est un simulateur destiné
à tester des hypothèses de stratégie sur historique, avec des résultats
strictement descriptifs — jamais une promesse de performance future.

## Addendum V1.1 — indicateurs étendus + architecture temps réel

- **28 nouveaux indicateurs** ajoutés au registre (`indicators/base.py`),
  couvrant tendance (ADX, Aroon), momentum (Stochastique, Williams %R,
  CCI, ROC, Momentum, TRIX, Ultimate Oscillator), volatilité (Bollinger,
  Donchian, Keltner, écart-type) et volume (OBV, VWAP, MFI, CMF). Tous
  testés (`tests/test_new_indicators.py`) : bornes vérifiées quand
  l'indicateur en a (ex. Stochastique ∈ [0,100], CMF ∈ [-1,1]), calcul
  sans erreur sur données réalistes, cohérence des canaux (bande haute ≥
  bande basse).
- **Aucun changement de comportement des indicateurs existants** — les 8
  indicateurs V1 gardent exactement le même calcul, testé par la suite
  V1 déjà en place (aucun test existant modifié).
- **Architecture temps réel** (`data/realtime.py`) : `import_new_bars()`
  pour un rafraîchissement par CSV sans API, et `RealtimeDataProvider`
  pour un vrai flux live une fois une `fetch_fn` fournie. Ce module ne
  se connecte à aucune source réelle par lui-même — brancher un vrai
  fournisseur de données (clé API, format de réponse) reste à faire
  ensemble, mais aucune autre partie du logiciel n'aura besoin de
  changer quand ce sera fait.

