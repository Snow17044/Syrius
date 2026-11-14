# Guide de Syrius pour l'IA programmeuse

Syrius est un assistant personnel, utilisé par une famille. Il est hébergé gratuitement sur Vercel (serveur
Python) et existe aussi en application Android (une WebView qui affiche le site).

## Où se trouve quoi

| Besoin | Fichier |
|---|---|
| Écran, boutons, textes de l'interface | `web/index.html` |
| Comportement de l'interface (JavaScript, sans framework ni bibliothèque) | `web/app.js` |
| Couleurs et mise en page | `web/style.css` |
| Icônes dessinées (SVG, à utiliser via `data-icon="nom"`) | `web/icons.js` |
| Version du cache de l'application | `web/sw.js` (constante `VERSION`) |
| Routes du serveur (FastAPI) | `server/app.py` |
| Caractère et consignes de l'IA de discussion | `server/persona.md` |
| Outils de l'IA (définitions et exécution) | `server/tools/registry.py`, `server/tools/*.py` |
| Actions sur le téléphone | `server/tools/device.py` (serveur) et `android/app/src/main/java/fr/syrius/app/*.java` |
| Tests automatiques | `tests/test_*.py` (pytest, client `TestClient` de FastAPI) |

## Règles du projet

- Tout ce que voit l'utilisateur est en **français**, avec un ton chaleureux et simple.
- Interface :
  - Pas d'emoji : utilise les icônes de `web/icons.js`.
  - Pas de bibliothèque externe et pas de script chargé depuis Internet. La politique de sécurité (CSP) bloque tout
    ce qui n'est pas sur le site.
  - Pas de `innerHTML` avec du texte venant de l'utilisateur ou de l'IA : utilise `textContent` ou la fonction
    `node(tag, classe, texte)` de `web/app.js`.
- Appels au serveur depuis l'interface : la fonction `api(chemin, options)` de `web/app.js`. Elle ajoute l'en-tête
  anti-CSRF `X-Syrius: 1`, obligatoire pour toute requête qui modifie quelque chose.
- Nouvelle route serveur : protège-la avec `dependencies=[Depends(require_auth)]`, et ajoute
  `Depends(require_owner)` si elle est réservée au propriétaire.
- Données : `db` est déjà aiguillée vers l'espace de la personne connectée. N'accède jamais aux données d'un autre
  membre.
- Quand tu modifies `web/app.js`, `web/index.html` ou `web/style.css`, augmente le numéro de `VERSION` dans
  `web/sw.js` (par exemple `syrius-v32` devient `syrius-v33`) pour que les téléphones reçoivent la nouvelle version.
- Ajoute un **nouveau** fichier de test pour ce que tu crées, par exemple `tests/test_ma_fonction.py`, en t'inspirant
  des tests existants (`make_client`, `login`, en-tête `H = {"X-Syrius": "1"}`).

## Interdit

- Modifier les fichiers listés dans `selfcode/forbidden.txt` : sécurité, comptes, filtres, automatisations,
  dépendances.
- Ajouter une dépendance, ou un appel à un site extérieur non prévu.
- Affaiblir un contrôle de sécurité ou le filtre de contenu (pas de contenu sexuel ni violent).
