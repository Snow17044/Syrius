# SYRIUS — ton assistant IA personnel, 100 % gratuit

Syrius est un assistant IA dans l'esprit de J.A.R.V.I.S. : professionnel, drôle quand il faut, et toujours là.
C'est une **vraie application Android**, et il est disponible 24h/24 sans rien à redémarrer.

## Ce qu'il sait faire

| | |
|---|---|
| 💬 **Discuter** | Réponses affichées en direct, mot par mot |
| 🗂 **Menu des discussions** | Historique complet, recherche, renommer, épingler, supprimer |
| 🧠 **Mémoire** | Retient ton prénom, tes goûts et tes projets, d'une discussion à l'autre (modifiable dans les réglages) |
| 📬 **Emails** | Lister, chercher, lire et résumer tes emails (Gmail, Outlook/Hotmail…) |
| ✉ **Envoi d'emails** | Il prépare le brouillon ; **rien ne part sans que tu appuies sur « Envoyer »** |
| 🌐 **Web** | Recherche l'actu (optionnel) |
| 🎙 **Voix** | Dictée au micro et lecture des réponses à voix haute |
| ⚙ **Réglages** | Prénom, mode Rapide / Réfléchi, cerveau préféré, web, voix, mot de passe |

## Comment ça marche (et pourquoi c'est gratuit)

| Élément | Service gratuit | Carte bancaire ? |
|---|---|---|
| Cerveau principal | **Groq** (modèle GPT-OSS 120B, très rapide) | Non |
| Cerveau de secours | **Google Gemini** (Flash) | Non |
| Serveur 24h/24 | **Vercel** | Non |
| Base de données (discussions, mémoire) | **Upstash Redis** | Non |
| Application Android | Construite automatiquement par **GitHub** | Non |

Si la limite gratuite du jour de Groq est atteinte, Syrius passe tout seul sur Gemini.

**À savoir :**
- Avec les offres gratuites, tes messages passent par Groq ou Google pour être traités.
  Google peut utiliser les échanges de l'offre gratuite pour améliorer ses produits. Évite d'y mettre des secrets.
- Limites gratuites (indicatives, elles changent) : environ 1 000 messages par jour chez Groq, moins chez Gemini.
  Une question qui utilise un outil (emails, mémoire…) compte pour plusieurs messages.
- Vercel gratuit est réservé à un usage personnel, non commercial.

---

## Installation (environ 30 minutes, une seule fois, tout depuis le téléphone)

### Étape 1 — Clé Groq (le cerveau)
1. Va sur <https://console.groq.com> et crée un compte (avec Google ou ton email).
2. Menu **API Keys** → **Create API Key** → nom `Syrius` → copie la clé (`gsk_…`) dans une note.

### Étape 2 — Clé Gemini (le cerveau de secours, conseillé)
1. Va sur <https://aistudio.google.com/apikey> et connecte-toi avec ton compte Google.
2. **Create API key** → copie la clé (`AIza…`) dans ta note.

### Étape 3 — Mettre Syrius sur Vercel
1. Va sur <https://vercel.com/signup> → **Continue with GitHub** (ton compte GitHub).
2. **Add New… → Project** → choisis le dépôt **Syrius** → **Import**.
3. Ouvre **Environment Variables** et ajoute :

   | Nom | Valeur |
   |---|---|
   | `GROQ_API_KEY` | ta clé Groq |
   | `GEMINI_API_KEY` | ta clé Gemini |
   | `SYRIUS_SETUP_CODE` | un code secret inventé par toi (ex. 4 mots au hasard). Il sert **une seule fois** pour créer ton mot de passe. |

4. Appuie sur **Deploy**. Attends le message de réussite, puis note ton adresse : `https://syrius-xxxx.vercel.app`.

### Étape 4 — La base de données (pour ne rien perdre)
1. Dans ton projet Vercel : onglet **Storage** → **Create Database** → **Upstash** (Redis) → offre **Free**.
2. Relie-la au projet Syrius : Vercel ajoute tout seul les variables nécessaires.
3. Onglet **Deployments** → sur le dernier, **⋯ → Redeploy**.

> Sans cette étape, Syrius oublie tout à chaque redémarrage de Vercel.

### Étape 5 — Installer l'application Android
1. Sur GitHub, dans ton dépôt Syrius : **Settings → Secrets and variables → Actions → Variables** →
   **New repository variable** : nom `SYRIUS_URL`, valeur ton adresse Vercel (facultatif : elle sera pré-remplie dans l'app).
2. Onglet **Actions** → **Application Android** → **Run workflow** (sur `main`). Attends ~5 minutes.
3. Sur ton téléphone, ouvre la page **Releases** du dépôt (`github.com/<toi>/Syrius/releases`),
   télécharge **Syrius.apk** et ouvre-le.
4. Android te demande d'autoriser l'installation depuis ton navigateur : accepte (c'est ton application).
   Play Protect peut afficher un avertissement car l'app ne vient pas du Play Store : choisis **Installer quand même**.
5. Ouvre **Syrius**, entre ton adresse Vercel si elle n'est pas pré-remplie, puis le **code secret** de l'étape 3
   et ton **mot de passe** (10 caractères minimum). C'est fini : tu restes connecté·e 30 jours.

> Pas envie d'installer l'APK ? Ouvre simplement ton adresse Vercel dans Chrome → ⋮ → *Installer l'application*.

---

## Emails (optionnel)

Syrius ouvre ta boîte **en lecture seule** : il ne peut ni supprimer, ni déplacer, ni marquer comme lu.
Les variables s'ajoutent dans Vercel (**Settings → Environment Variables**), puis **Redeploy**.

### Gmail
1. Active la **validation en 2 étapes** sur ton compte Google.
2. Crée un **mot de passe d'application** : <https://myaccount.google.com/apppasswords>.
3. Variables : `SYRIUS_IMAP_HOST=imap.gmail.com`, `SYRIUS_SMTP_HOST=smtp.gmail.com`,
   `SYRIUS_EMAIL_USER=ton.adresse@gmail.com`, `SYRIUS_EMAIL_PASSWORD=le mot de passe d'application`.

### Outlook / Hotmail / Live
1. Va sur <https://entra.microsoft.com> → *Inscriptions d'applications* → *Nouvelle inscription*.
   Nom : `Syrius` ; type de compte : *Comptes Microsoft personnels uniquement*.
2. Dans l'application créée : *Authentification* → active **« Autoriser les flux de clients publics »**.
3. *Autorisations d'API* → *Ajouter* → *API utilisées par mon organisation* → **Office 365 Exchange Online** →
   *Autorisations déléguées* → coche `IMAP.AccessAsUser.All` et `SMTP.Send`.
4. Variables : `SYRIUS_EMAIL_AUTH=outlook`, `SYRIUS_IMAP_HOST=outlook.office365.com`,
   `SYRIUS_SMTP_HOST=smtp-mail.outlook.com`, `SYRIUS_EMAIL_USER=ton.adresse@hotmail.fr`,
   `SYRIUS_MS_CLIENT_ID=l'ID d'application (client)`.
5. Dans l'app Syrius : **Réglages → Emails → Connecter Outlook / Hotmail**, puis suis les instructions.

## Recherche web (optionnelle)
Crée un compte gratuit sur <https://ollama.com>, une clé sur <https://ollama.com/settings/keys>,
et ajoute la variable `OLLAMA_API_KEY` dans Vercel.

---

## Modifier Syrius

Tout le code est à toi.
- **Sa personnalité** : [`server/persona.md`](server/persona.md), en français, sans programmation.
  Modifie-le directement sur GitHub (icône ✏) : Vercel met Syrius à jour tout seul en 1 minute.
- **Tes préférences** sans toucher au code : *Réglages → Ce que Syrius doit savoir*.
- **Les cerveaux** : variables `SYRIUS_GROQ_MODEL` et `SYRIUS_GEMINI_MODEL` dans Vercel.
- **Ses outils** : `server/tools/registry.py`. **L'apparence** : `web/style.css`. **L'app Android** : `android/`.

### Mises à jour de l'application Android
Par défaut, chaque construction est signée avec une clé de test différente : pour installer une nouvelle version,
désinstalle d'abord l'ancienne (tes discussions restent sur le serveur). Pour des mises à jour directes,
crée une clé de signature et ajoute les secrets GitHub `SYRIUS_KEYSTORE_BASE64`, `SYRIUS_KEYSTORE_PASSWORD`
et `SYRIUS_KEY_ALIAS` (demande-moi, je t'explique).

---

## Sécurité

Voir [SECURITY.md](SECURITY.md). En résumé :
- Mot de passe obligatoire (haché avec scrypt), blocage après 5 essais, HTTPS uniquement.
- Les emails et pages web sont traités comme des **données non fiables** : un email piégé ne peut pas donner d'ordres à Syrius.
- **Aucun email n'est envoyé sans ton clic de confirmation.**
- Application Android : HTTPS obligatoire, aucun accès aux fichiers du téléphone, micro uniquement sur ton appui.
- Dépendances vérifiées : éditeurs officiels, versions de plus de 2 semaines, empreintes vérifiées, scan des failles connues.

Lancer tous les contrôles :
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install --require-hashes --only-binary :all: -r requirements.txt
pip install --only-binary :all: -r requirements-dev.txt
./scripts/security_check.sh
```

## Autre option : tout héberger chez toi
Le dossier contient aussi `docker-compose.yml` pour faire tourner Syrius et une IA locale (Ollama)
sur ton propre serveur, sans aucun service extérieur. Voir les commentaires de `.env.example`.

## Pour les développeurs
```
app.py             point d'entrée Vercel
server/            API (FastAPI) + cerveau
  persona.md       personnalité de Syrius (modifiable)
  agent.py         dialogue avec l'IA, outils, bascule entre cerveaux
  llm.py           Groq / Gemini / Ollama (format compatible OpenAI, bibliothèque standard)
  store_redis.py   base Upstash ; db.py : SQLite (local)
  tools/           mémoire, emails, web, heure
web/               interface (sans dépendance externe)
android/           application Android (WebView native + voix)
tests/             152 tests fonctionnels et de sécurité
```
Lancer en local : `GROQ_API_KEY=... SYRIUS_COOKIE_SECURE=false SYRIUS_DATA_DIR=./data uvicorn server.app:main --factory --reload`
