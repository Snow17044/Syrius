# Syrius sur Discord (salon vocal, même sur Xbox)

Avec ce bot, tu parles à Syrius dans un salon vocal Discord. Ça marche aussi pendant que tu joues sur ta
console. Commence ta phrase par « **Syrius** », par exemple « Syrius, quel temps fera-t-il demain ? » : il te
répond à voix haute dans le salon.

Il te faut un petit serveur toujours allumé, gratuit chez Google Cloud. Compte environ 15 minutes en tout.

## 1. Créer le bot Discord (5 min)

1. Ouvre <https://discord.com/developers/applications>, puis **New Application**. Nom : `Syrius`.
2. Dans le menu de gauche, **Bot** :
   - touche **Reset Token**, puis **Copy** ;
   - garde ce jeton pour l'étape 4, sans l'envoyer à personne.
3. Toujours dans **Bot**, désactive **Public Bot** : comme ça, toi seul peux l'inviter.
4. Menu **OAuth2**, puis **URL Generator** :
   - coche `bot` ;
   - dans les permissions, coche `Connect` et `Speak` ;
   - ouvre le lien généré tout en bas et invite Syrius sur ton serveur Discord.

## 2. Dans ton Syrius (2 min)

**Réglages → Syrius sur Discord** :

1. Récupère ton identifiant Discord :
   - Discord → Paramètres → Avancés → active **Mode développeur** ;
   - appui long sur ton pseudo, puis **Copier l'identifiant**.
2. Colle-le dans Syrius, puis touche **Enregistrer**.
3. Touche **Copier la clé du bot**. Tu en auras besoin à l'étape 4.

## 3. Le serveur gratuit Google Cloud (5 min)

1. Ouvre <https://console.cloud.google.com> et connecte-toi avec ton compte Google.
   - Il faut activer la facturation. La carte sert seulement à vérifier ton identité : rien n'est prélevé
     tant qu'on reste dans l'offre gratuite.
2. Va dans **Compute Engine → Instances de VM**, puis **Créer une instance**, et règle :

   | Réglage | Valeur |
   |---|---|
   | Nom | `syrius` |
   | Région | `us-central1` (Iowa), `us-east1` ou `us-west1`. Ce sont les seules gratuites. |
   | Type de machine | **e2-micro** |
   | Disque de démarrage | **Debian 12**, 30 Go, **Disque persistant standard** |

3. Touche **Créer**.

## 4. Installer Syrius sur le serveur (3 min)

1. Sur la ligne de ta VM, touche **SSH**. Une fenêtre noire s'ouvre.
2. Colle cette ligne, puis appuie sur Entrée :

   ```
   curl -fsSL https://raw.githubusercontent.com/Snow17044/Syrius/main/discord-bot/install.sh | sudo bash
   ```

3. Quand le script le demande, colle tes deux clés :
   - le jeton Discord ;
   - la clé du bot Syrius.

   Rien ne s'affiche quand tu colles, c'est normal. Appuie sur Entrée pour l'adresse proposée.

## 5. Essayer

1. Entre dans un salon vocal de ton serveur Discord : Syrius te rejoint et dit « Syrius est là ».
2. Dis : « **Syrius**, raconte-moi une blague ».

Sur Xbox : ouvre Discord sur ton téléphone, rejoins le salon, puis touche **Rejoindre sur Xbox**.

## Bon à savoir

- Syrius n'écoute **que toi** (ton identifiant), et seulement les phrases qui commencent par « Syrius ».
- Le son n'est jamais enregistré. Les conversations vont dans une discussion « Syrius sur Discord » de ton
  application.
- Le bot se met à jour tout seul chaque nuit.
- Journal en direct : `sudo journalctl -fu syrius-discord`
