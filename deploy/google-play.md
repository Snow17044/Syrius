# Publier Syrius sur Google Play

Ce guide sert à ce que l'application ne soit plus signalée comme « dangereuse » et soit installée depuis le
Play Store, par toi et ta famille.

## Ce qui est déjà prêt dans l'application

- Elle cible Android 16, comme Google Play l'exige.
- Elle est compatible avec la mémoire 16 Ko d'Android 15 et plus.
- Elle est fournie au format AAB (`Syrius.aab`, dans les Releases GitHub).
- Les autorisations refusées par Google Play sont retirées : « afficher par-dessus les autres applis »,
  « ignorer l'optimisation de la batterie » et « alarme exacte réservée aux réveils ».
- Avant d'accéder aux contacts, l'appli explique clairement pourquoi.
- La politique de confidentialité est en ligne : `https://TON-SYRIUS/confidentialite`.
- On peut supprimer son compte dans l'appli : Réglages → Sécurité.
- Un bouton « Signaler » apparaît sous chaque réponse de l'IA (règle sur l'IA générative).
- Les liens d'invitation ouvrent directement l'application.

## Étape 1 : la clé de signature (une seule fois)

1. Va sur GitHub, dans ton dépôt Syrius : **Settings → Secrets and variables → Actions → New repository secret**.
2. Dans **Name**, écris `SYRIUS_KEYSTORE_PASSWORD`.
3. Dans **Secret**, mets un long mot de passe que tu inventes (au moins 16 caractères).
   Note-le en lieu sûr : il te servira pour toutes les mises à jour.
4. Dis à Claude « c'est bon ». Il lance la création de la clé, puis une nouvelle construction de l'appli.

## Étape 2 : le compte développeur Google Play

1. Crée ton compte sur <https://play.google.com/console/signup>. Choisis un compte **personnel**.
2. Tu paies 25 $ une seule fois, et Google vérifie ton identité (pièce d'identité).

## Étape 3 : créer l'application

Dans la Play Console, clique sur **Créer une application** et remplis ainsi :

| Champ | Ce qu'il faut mettre |
|---|---|
| Nom | Syrius |
| Langue | Français |
| Application ou jeu | Application |
| Gratuite ou payante | Gratuite |

## Étape 4 : le test interne, idéal pour la famille

1. Va dans **Tester → Tests internes → Créer une version**, puis importe `Syrius.aab`.
2. Ajoute les adresses Gmail de ta famille dans la liste des testeurs (100 personnes au maximum).
3. Envoie-leur le lien d'inscription. Ils installent ensuite Syrius depuis le Play Store, sans aucun
   avertissement.

Pour une publication publique (production), Google demande que 12 testeurs aient l'appli pendant
14 jours d'affilée en « test fermé ».

## Étape 5 : les formulaires

**Politique de confidentialité**

`https://TON-SYRIUS/confidentialite`

**Accès à l'application**

L'application demande une connexion. Crée un compte famille pour l'examinateur, avec le prénom
« Google » et un mot de passe. Ensuite, donne dans la Console :
- l'adresse de connexion,
- le prénom « Google »,
- ce mot de passe.

**Publicités** : Non.

**Classification du contenu** : catégorie « Utilitaire / productivité ». Pour l'IA générative, coche
oui : l'utilisateur peut générer du texte et des images.

**Public cible** : 13 ans et plus.

**Sécurité des données**

Questions générales :
- Données collectées : Oui.
- Données chiffrées en transit : Oui.
- Suppression possible : Oui, avec l'adresse `https://TON-SYRIUS/confidentialite#suppression`.

| Type de données | Utilisation | Partage |
|---|---|---|
| Nom (prénom du compte) | Gestion du compte | Non partagé |
| Messages | Fonctionnalité de l'appli | Envoyés aux services d'IA pour répondre |
| Photos | Fonctionnalité de l'appli, non conservées | Envoyées aux services d'IA |
| Audio (messages vocaux) | Fonctionnalité de l'appli, non conservé | Transcription par Groq |
| Position approximative | Facultative : météo, lieux proches | Non partagée |
| Contacts | Lus sur le téléphone uniquement, jamais envoyés | « Non collectés » |

**Service de premier plan « micro »** (pour « Hey Syrius »)
- Explication : « Détection du mot-clé “Hey Syrius” activée par l'utilisateur, avec une notification
  permanente ».
- Joins une courte vidéo de l'activation.

## Étape 6 : les liens qui ouvrent l'application

1. Dans la Play Console, va dans **Configuration → Intégrité de l'application → Signature d'application**.
2. Copie l'empreinte **SHA-256** de la clé de signature d'application.
3. Dans Vercel, ajoute la variable `SYRIUS_ANDROID_CERT_SHA256` avec cette empreinte, puis redéploie.

L'empreinte de ta propre clé (étape 1) est déjà prise en compte par Claude.
