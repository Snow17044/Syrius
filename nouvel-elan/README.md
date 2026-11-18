# Nouvel Élan — l'application de l'association

Une application pour téléphone (Android et iPhone) qui s'installe depuis un simple lien.
Elle ne dépend d'aucun site existant, et il n'y a ni boutique d'applications ni mise à jour à faire.

## Ce qu'elle fait

| Écran | Contenu |
|---|---|
| 🏠 **Accueil** | Le slogan, « Découvrir notre programme », « Nous rejoindre », les grands axes, puis l'actualité |
| 🚩 **Programme** | L'introduction et les grands axes, chacun avec sa présentation et ses propositions |
| 📰 **Articles** | Tous les articles, avec recherche et filtre par thème |
| ➕ **Ajouter** | (équipe seulement) On colle un lien → titre et image se remplissent tout seuls → « Publier » |
| 👥 **Association** | Présentation, réseaux sociaux, installer et partager l'appli |

- **Ajouter un article en 2 secondes** : sur n'importe quel site, appuie sur **Partager → Nouvel Élan**
  (Android, une fois l'appli installée). Sinon, copie le lien et appuie sur **Coller** dans l'onglet Ajouter.
- **Rédiger le programme** : onglet Association → **Mode éditeur** → onglet Programme → **Modifier le programme**.
  On y écrit le slogan, l'introduction, le lien d'adhésion et les axes (une proposition par ligne).
- **Code éditeur** : seules les personnes qui ont le code peuvent publier, épingler à la une ou supprimer.
  Tout le monde peut lire et partager.
- **Hors connexion** : l'appli s'ouvre et affiche les derniers articles même sans réseau.

---

## Mise en ligne (gratuit, environ 10 minutes, une seule fois)

### 1. Créer le projet sur Vercel
1. Va sur <https://vercel.com/new> et choisis le dépôt GitHub **Syrius**.
2. Dans **Root Directory**, choisis le dossier **`nouvel-elan`** (important).
3. Nom du projet : `nouvel-elan`. Clique sur **Deploy**.

### 2. Brancher la base de données (où sont rangés les articles)
1. Dans le projet Vercel : onglet **Storage** → **Create Database** → **Neon (Postgres)** (offre gratuite).
   Upstash for Redis fonctionne aussi.
2. Relie-la au projet. Les variables (`DATABASE_URL`…) sont ajoutées toutes seules,
   et l'application crée sa table au premier lancement.

> Déjà fait : l'application est en ligne sur **https://nouvelles-elan.vercel.app**
> (projet Vercel `nouvelles-elan`, base Neon branchée, code éditeur enregistré).

### 3. Choisir le code éditeur
1. **Settings → Environment Variables** → ajoute `NE_CODE_EDITEUR` avec un code solide
   (par ex. 3 ou 4 mots au hasard). Donne-le seulement aux personnes qui publient.
2. Onglet **Deployments** → sur le dernier, **⋯ → Redeploy** (pour prendre en compte le code).

### 4. Partager l'application
Envoie le lien `https://nouvel-elan.vercel.app` (ou ton adresse Vercel) dans le groupe de l'association.
- **Android (Chrome)** : ouvrir le lien → menu ⋮ → **Installer l'application** (ou le bouton dans l'onglet Association).
- **iPhone (Safari)** : ouvrir le lien → **Partager** → **Sur l'écran d'accueil**.

L'icône Nouvel Élan apparaît alors comme une vraie application.

---

## Personnaliser

- **Présentation et réseaux sociaux** : en haut du fichier `public/app.js` (bloc `ASSOCIATION`).
  Mets les vrais liens Instagram, TikTok, etc.
- **Thèmes des articles** : liste `CATEGORIES` dans `api/articles.js`.
- **Couleurs** : en haut de `public/app.css` (bleu `#00246A` et rouge `#D60616`, ceux du logo).

## Essayer sur un ordinateur

```bash
cd nouvel-elan
npm run dev        # http://localhost:3000 — code éditeur : « elan », articles en mémoire
```
