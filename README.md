# SYRIUS — ton assistant IA personnel, 100 % gratuit

Syrius est un assistant IA dans l'esprit de J.A.R.V.I.S. : professionnel, drôle quand il faut, et toujours là.
Son cerveau est une **IA locale qui tourne sur ton propre serveur** : aucun abonnement, aucune facture,
aucune limite de messages, et tes discussions ne partent chez personne.

## Ce qu'il sait faire

| | |
|---|---|
| 💬 **Discuter** | Réponses affichées en direct, mot par mot, au format téléphone |
| 🗂 **Menu des discussions** | Historique complet, recherche, renommer, épingler, supprimer |
| 🧠 **Mémoire** | Retient ton prénom, tes goûts et tes projets, d'une discussion à l'autre (modifiable dans les réglages) |
| 📬 **Emails** | Lister, chercher, lire et résumer tes emails (Gmail, Outlook/Hotmail…) |
| ✉ **Envoi d'emails** | Il prépare le brouillon ; **rien ne part sans que tu appuies sur « Envoyer »** |
| 🌐 **Web** | Recherche l'actu (optionnel, clé gratuite) |
| 🎙 **Voix** | Dictée au micro et lecture des réponses à voix haute |
| ⚙ **Réglages** | Prénom, mode Rapide / Réfléchi, choix du modèle d'IA, web, voix, mot de passe |

## Ce que ça coûte : 0 €

| Élément | Solution gratuite |
|---|---|
| Cerveau | **Ollama** + un modèle libre (par défaut **Qwen3 8B**), qui tourne sur ton serveur |
| Serveur 24h/24 | **Oracle Cloud « Always Free »** (gratuit à vie) ou un vieux PC chez toi |
| Adresse web + HTTPS | **DuckDNS** + Caddy (certificat Let's Encrypt gratuit) |
| Recherche web | Clé gratuite Ollama (optionnelle) |

### Soyons honnêtes sur la vitesse et l'intelligence

- **Intelligence** : Qwen3 8B est un bon modèle libre pour la conversation, les résumés et les emails,
  mais il est nettement en dessous des meilleures IA payantes (Claude, ChatGPT) sur les questions pointues.
  Avec plus de mémoire (un PC à 24 Go ou plus), `qwen3:30b` est bien plus intelligent **et** plus rapide.
- **Vitesse** : sur le serveur Oracle gratuit (2 cœurs, sans carte graphique), il écrit **plus lentement
  que la vitesse de lecture** : compte quelques secondes à une minute selon la longueur de la réponse.
  Le mode **Rapide** (par défaut) répond directement ; le mode **Réfléchi** réfléchit d'abord (plus lent, plus juste).
  - Le tout premier message après le démarrage du serveur prend plus de temps (chargement du modèle).
    Ensuite le modèle reste en mémoire en permanence.
  - Avec un PC équipé d'une carte graphique NVIDIA (12 Go ou plus), c'est quasi instantané.

## Pourquoi « toujours là » sans le redémarrer

- Syrius vit sur un **serveur allumé en permanence**, pas dans ton téléphone. Si le serveur redémarre, tout repart tout seul.
- Sur ton téléphone, c'est une **app installée sur l'écran d'accueil** (PWA). Tu restes connecté·e 30 jours, et l'app rouvre ta dernière discussion.

---

## Installation (environ 45 minutes, une seule fois)

### 1. Créer le serveur gratuit (Oracle Cloud)

1. Crée un compte sur <https://www.oracle.com/cloud/free/>. Une carte bancaire est demandée
   **pour vérifier ton identité** ; l'offre « Always Free » ne prélève rien.
2. *Compute → Instances → Create instance* :
   - Image : **Ubuntu**
   - Shape : **Ampere (VM.Standard.A1.Flex)**, mets **2 OCPU et 12 Go de mémoire** (le maximum gratuit depuis juin 2026)
   - Ajoute ta clé SSH (ou laisse Oracle en générer une et télécharge-la)
3. Dans le *réseau* de l'instance (Security List), autorise les ports **80** et **443** en entrée.
   Sur le serveur, ouvre-les aussi : `sudo iptables -I INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT && sudo netfilter-persistent save`

> Si Oracle affiche « Out of capacity », réessaie un peu plus tard ou choisis une autre zone.
> Alternative : un vieux PC à la maison sous Linux (16 Go de RAM ou plus), avec les ports 80/443 redirigés par ta box.

### 2. Créer ton adresse gratuite

Sur <https://www.duckdns.org>, connecte-toi, crée un nom (ex. `monsyrius`) et mets l'IP publique de ton serveur.
Ton adresse sera `monsyrius.duckdns.org`.

### 3. Installer Syrius

Sur le serveur (connecté en SSH) :

```bash
# Installer Docker (méthode officielle)
curl -fsSL https://get.docker.com -o get-docker.sh
less get-docker.sh          # (facultatif) relire le script avant de l'exécuter
sudo sh get-docker.sh

# Récupérer Syrius
git clone https://github.com/snow17044/syrius.git
cd syrius

# Configurer
cp .env.example .env
nano .env                   # mets ton SYRIUS_DOMAIN (et choisis le modèle selon ta RAM)
chmod 600 .env

# Lancer (24h/24, redémarrage automatique)
sudo docker compose up -d --build

# Suivre le téléchargement du modèle (~5 Go, une seule fois, quelques minutes)
sudo docker compose logs -f ollama-pull

# Choisir ton mot de passe Syrius (10 caractères minimum)
sudo docker compose exec syrius python -m server.manage set-password
```

### 4. Sur ton téléphone

1. Ouvre `https://monsyrius.duckdns.org` et connecte-toi.
2. **Android (Chrome)** : menu ⋮ → *Ajouter à l'écran d'accueil* / *Installer l'application*.
   **iPhone (Safari)** : bouton Partager → *Sur l'écran d'accueil*.

---

## Choisir / changer de modèle d'IA

Le modèle se choisit selon la mémoire (RAM) du serveur :

| RAM du serveur | Modèle conseillé | |
|---|---|---|
| 24 Go et plus (PC perso) | `qwen3:30b` | le meilleur : intelligent et rapide |
| 16 Go | `qwen3:14b` | bon, un peu plus lent |
| 12 Go (Oracle gratuit) | `qwen3:8b` | correct (par défaut) |
| 8 Go | `qwen3:4b` | basique, pour les petites machines |

Pour en essayer un autre (par exemple `gemma4`, catalogue sur <https://ollama.com/library>) :

```bash
sudo docker compose exec ollama ollama pull gemma4
```

Il apparaît ensuite dans **Réglages → Modèle d'IA** sur ton téléphone. Choisis un modèle qui gère les
« tools » (outils), sinon la mémoire et les emails ne marcheront pas.

**Avec une carte graphique NVIDIA** : installe le *NVIDIA Container Toolkit*, puis décommente le bloc `deploy:` du service `ollama` dans `docker-compose.yml`.

## Modifier Syrius

Tout le code est à toi et modifiable.

- **Sa personnalité** : le fichier [`server/persona.md`](server/persona.md), en français, sans programmation.
  Change son ton, ajoute des règles… puis `sudo docker compose up -d --build`.
- **Tes préférences** sans toucher au code : *Réglages → Ce que Syrius doit savoir*.
- **Ses outils** (ce qu'il sait faire) : `server/tools/registry.py`.
- **L'apparence** de l'app : `web/style.css`.

Après une modification, relance les tests : `./scripts/security_check.sh` (voir plus bas).

---

## Recherche web (optionnelle, gratuite)

1. Crée un compte gratuit sur <https://ollama.com>, puis une clé sur <https://ollama.com/settings/keys>.
2. Mets-la dans `.env` : `OLLAMA_API_KEY=...`, puis `sudo docker compose up -d`.

Seule la recherche (quelques mots) est envoyée à ollama.com ; tes discussions restent sur ton serveur.

## Emails

Syrius ouvre ta boîte **en lecture seule** : il ne peut ni supprimer, ni déplacer, ni marquer comme lu.

### Gmail
1. Active la **validation en 2 étapes** sur ton compte Google.
2. Crée un **mot de passe d'application** : <https://myaccount.google.com/apppasswords>.
3. Dans `.env`, décommente le bloc *Gmail* et remplis ton adresse + ce mot de passe d'application.
4. `sudo docker compose up -d` pour appliquer.

### Outlook / Hotmail / Live
Microsoft n'accepte plus les mots de passe simples : il faut une connexion sécurisée (OAuth2), gratuite.
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

Voir [SECURITY.md](SECURITY.md). En résumé :

- Mot de passe obligatoire, stocké haché (scrypt) ; blocage après 5 essais ratés ; HTTPS uniquement.
- L'IA tourne chez toi : aucune discussion n'est envoyée à une entreprise d'IA.
- Les emails et pages web sont traités comme des **données non fiables** : un email piégé ne peut pas donner d'ordres à Syrius.
- **Aucun email n'est envoyé sans ton clic de confirmation.**
- Dépendances vérifiées : éditeurs officiels, versions de plus de 2 semaines, empreintes SHA-256, scan des failles connues.

Lancer tous les contrôles :

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

```bash
sudo docker compose exec syrius python -c "import sqlite3; s=sqlite3.connect('/data/syrius.db'); s.backup(sqlite3.connect('/tmp/backup.db'))"
sudo docker compose cp syrius:/tmp/backup.db ./syrius-backup.db
```

## Pour les développeurs

```
server/            API (FastAPI) + cerveau
  persona.md       personnalité de Syrius (modifiable)
  agent.py         dialogue avec l'IA, outils, réponses en direct
  llm.py           connexion à Ollama (bibliothèque standard uniquement)
  app.py           routes, connexion, en-têtes de sécurité
  db.py            stockage SQLite
  tools/           mémoire, emails, web, heure
web/               app téléphone (PWA, sans dépendance externe)
tests/             tests fonctionnels et de sécurité
```

Lancer en local (avec Ollama installé sur ta machine) :
`SYRIUS_OLLAMA_URL=http://localhost:11434 SYRIUS_COOKIE_SECURE=false SYRIUS_DATA_DIR=./data uvicorn server.app:main --factory --reload`
