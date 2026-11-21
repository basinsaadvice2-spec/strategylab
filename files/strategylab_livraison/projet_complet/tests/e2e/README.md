# Test de bout en bout (page ↔ API), sans navigateur

Nécessite Node.js. Lance l'API avec de fausses données FRED, puis exécute le vrai script de la page contre
elle avec un faux DOM (le graphique TradingView est simulé).

    python3 tests/e2e/fake_server.py 18765 &
    python3 -m web.build --api-url http://localhost:18765 --out /tmp/e2e_page.html
    node tests/e2e/page_e2e.js /tmp/e2e_page.html        # parcours complet
    python3 -m web.build --api-url http://localhost:1 --out /tmp/e2e_offline.html
    node tests/e2e/page_e2e.js /tmp/e2e_offline.html offline

Ce test ne remplace pas un essai dans un vrai navigateur.
