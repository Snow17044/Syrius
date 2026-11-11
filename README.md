# SYRIUS — ton assistant IA personnel

Syrius est un assistant IA dans l'esprit de J.A.R.V.I.S. : professionnel, drôle quand il faut, et toujours là.
Il tourne **24h/24 sur un petit serveur**, et tu lui parles depuis ton téléphone comme avec une app.

## Ce qu'il sait faire

| | |
|---|---|
| 💬 **Discuter** | Réponses affichées en direct, mot par mot, au format téléphone |
| 🗂 **Menu des discussions** | Historique complet, recherche, renommer, épingler, supprimer |
| 🧠 **Mémoire** | Retient ton prénom, tes goûts et tes projets, d'une discussion à l'autre (modifiable dans les réglages) |
| 📬 **Emails** | Lister, chercher, lire et résumer tes emails (Gmail, Outlook/Hotmail…) |
| ✉ **Envoi d'emails** | Il prépare le brouillon ; **rien ne part sans que tu appuies sur « Envoyer »** |
| 🌐 **Web** | Recherche l'actu et les infos récentes |
| 🎙 **Voix** | Dictée au micro et lecture des réponses à voix haute |
| ⚙ **Réglages** | Prénom, style de réponse (rapide / équilibré / approfondi), mode turbo, web, voix, mot de passe |

Le cerveau est **Claude Opus 5.5** (Anthropic), réglé par défaut en mode « rapide ».

## Pourquoi « toujours là » sans le redémarrer

- Syrius vit sur un **serveur allumé en permanence**, pas dans ton téléphone. Si le serveur redémarre, Syrius redémarre tout seul.
- Sur ton téléphone, c'est une **app installée sur l'écran d'accueil** (PWA). Tu restes connecté·e 30 jours, et l'app rouvre ta dernière discussion.
- Tes discussions et sa mémoire sont stockées sur **ton** serveur.

---

## Installation (environ 30 minutes, une seule fois)

### Ce qu'il te faut

1. **Une clé API Anthropic** : crée un compte sur <https://console.anthropic.com>, ajoute un moyen de paiement, puis *API Keys → Create Key*. C'est payé à l'usage (quelques centimes par discussion en mode rapide ; tu peux fixer une limite de dépense dans la console).
2. **Un petit serveur Linux allumé 24h/24**, par exemple :
   - un VPS à ~4–6 €/mois (Hetzner, OVH, Scaleway…), **ou**
   - un vieux PC / Raspberry Pi à la maison.
3. **Une adresse web** pour le HTTPS, gratuite avec <https://www.duckdns.org> (ex. `monsyrius.duckdns.org`), pointée vers l'IP du serveur.

### Étapes

Sur le serveur (connecté en SSH) :

```bash
# 1. Installer Docker (méthode officielle)
curl -fsSL https://get.docker.com -o get-docker.sh
less get-docker.sh          # (facultatif) relire le script avant de l'exécuter
sudo sh get-docker.sh

# 2. Récupérer Syrius
git clone https://github.com/snow17044/syrius.git
cd syrius

# 3. Configurer
cp .env.example .env
nano .env                   # colle ta clé ANTHROPIC_API_KEY et ton SYRIUS_DOMAIN
chmod 600 .env

# 4. Lancer (24h/24, redémarrage automatique)
sudo docker compose up -d --build

# 5. Choisir ton mot de passe Syrius (10 caractères minimum)
sudo docker compose exec syrius python -m server.manage set-password
```

### Sur ton téléphone

1. Ouvre `https://ton-adresse.duckdns.org` et connecte-toi.
2. **Android (Chrome)** : menu ⋮ → *Ajouter à l'écran d'accueil* / *Installer l'application*.
   **iPhone (Safari)** : bouton Partager → *Sur l'écran d'accueil*.
3. C'est tout : l'icône Syrius s'ouvre comme une vraie app.

---

## Emails

Syrius ouvre ta boîte **en lecture seule** : il ne peut ni supprimer, ni déplacer, ni marquer comme lu.

### Gmail
1. Active la **validation en 2 étapes** sur ton compte Google.
2. Crée un **mot de passe d'application** : <https://myaccount.google.com/apppasswords>.
3. Dans `.env`, décommente le bloc *Gmail* et remplis ton adresse + ce mot de passe d'application.
4. `sudo docker compose up -d` pour appliquer.

### Outlook / Hotmail / Live
Microsoft n'accepte plus les mots de passe simples : il faut une connexion sécurisée (OAuth2).
1. Va sur <https://entra.microsoft.com> → *Inscriptions d'applications* → *Nouvelle inscription*.
   Nom : `Syrius` ; type de compte : *Comptes Microsoft personnels uniquement*.
2. Dans l'application créée : *Authentification* → active **« Autoriser les flux de clients publics »**.
3. *Autorisations d'API* → *Ajouter* → *API utilisées par mon organisation* → cherche **Office 365 Exchange Online** →
   *Autorisations déléguées* → coche `IMAP.AccessAsUser.All` et `SMTP.Send`.
4. Copie l'**ID d'application (client)** dans `SYRIUS_MS_CLIENT_ID` (bloc *Outlook* du `.env`), puis :
   ```bash
   sudo docker compose up -d
   sudo docker compose exec syrius python -m server.manage outlook-login
   ```
   Suis le lien affiché et entre le code : c'est fait, une fois pour toutes.

---

## Sécurité

Voir [SECURITY.md](SECURITY.md) pour le détail. En résumé :

- Mot de passe obligatoire, stocké chiffré (scrypt) ; blocage après 5 essais ratés.
- Connexion uniquement en **HTTPS**, cookie de session protégé.
- Les emails et pages web sont traités comme des **données non fiables** : un email piégé ne peut pas donner d'ordres à Syrius.
- **Aucun email n'est envoyé sans ton clic de confirmation.**
- Dépendances vérifiées : éditeurs officiels uniquement, versions publiées depuis plus de 2 semaines, empreintes SHA-256 contrôlées à chaque installation, scan des failles connues.

Lancer tous les contrôles (tests + analyse du code + failles connues) :

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install --require-hashes --only-binary :all: -r requirements.txt
pip install --only-binary :all: -r requirements-dev.txt
./scripts/security_check.sh
```

## Mettre à jour Syrius

```bash
cd syrius && git pull && sudo docker compose up -d --build
```

## Sauvegarder

Tes données sont dans le volume Docker `syrius-data`. Sauvegarde :

```bash
sudo docker compose exec syrius python -c "import sqlite3; s=sqlite3.connect('/data/syrius.db'); s.backup(sqlite3.connect('/tmp/backup.db'))"
sudo docker compose cp syrius:/tmp/backup.db ./syrius-backup.db
```

## Pour les développeurs

```
server/            API (FastAPI) + cerveau
  agent.py         dialogue avec Claude, outils, réponses en direct
  app.py           routes, connexion, en-têtes de sécurité
  db.py            stockage SQLite
  tools/           mémoire, emails, heure
web/               app téléphone (PWA, sans dépendance externe)
tests/             tests fonctionnels et de sécurité
```

Lancer en local : `SYRIUS_COOKIE_SECURE=false SYRIUS_DATA_DIR=./data uvicorn server.app:main --factory --reload`
