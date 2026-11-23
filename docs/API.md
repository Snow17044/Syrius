# API de Syrius : un assistant IA sur ton site

Syrius peut répondre aux visiteurs d'un autre site. Le plus simple : le propriétaire de Syrius t'envoie un
**lien** (*Réglages → Services → API → Créer le lien*). Tu l'ouvres, tu décris ton site, et la page te donne le code
à coller. Le lien ne sert qu'une fois et reste valable 7 jours. Le propriétaire peut aussi créer la clé lui-même et
te l'envoyer. Le domaine du serveur Syrius est noté `SYRIUS` ci-dessous
(par exemple `https://syriusprojet1.vercel.app`).

L'assistant de l'API ne voit rien de privé : pas de souvenirs, pas d'emails, pas d'outils. Il connaît seulement
les informations sur ton site que le propriétaire a écrites dans la clé (horaires, services, ton à employer…).

## 1. Le plus simple : la bulle de discussion

Colle cette ligne juste avant `</body>` :

```html
<script src="SYRIUS/widget.js" data-key="sk_syr_…" defer></script>
```

Une bulle apparaît en bas à droite. Elle est isolée (Shadow DOM) : elle ne modifie pas ton CSS, et ton CSS ne la
modifie pas.

| Option | Exemple | Effet |
|---|---|---|
| `data-color` | `"#f2a65a"` | Couleur principale |
| `data-position` | `"left"` | Bulle en bas à gauche |
| `data-theme` | `"light"` | Fenêtre claire (sombre par défaut) |
| `data-welcome` | `"Bonjour ! Une question ?"` | Premier message affiché |

Une clé « site » ne marche **que depuis les adresses enregistrées** avec la clé (par exemple
`https://garage-leo.fr`). Pour une autre adresse (un sous-domaine, `www.`, ou `http://localhost:3000` pour tester),
demande au propriétaire de l'ajouter.

## 2. Pour les développeurs : l'API HTTP

### `POST SYRIUS/api/v1/chat`

En-têtes :

```
Authorization: Bearer sk_syr_…
Content-Type: application/json
```

Le corps peut prendre deux formes.

- Un seul message :

  ```json
  { "message": "Vous êtes ouverts le samedi ?" }
  ```

- Toute la discussion, 20 messages au plus, chacun de 4000 caractères au plus. Le dernier vient de l'utilisateur :

  ```json
  { "messages": [
      { "role": "user", "content": "Bonjour" },
      { "role": "assistant", "content": "Bonjour ! Comment puis-je t'aider ?" },
      { "role": "user", "content": "Vous êtes ouverts le samedi ?" }
  ] }
  ```

Réponse `200` :

```json
{ "reply": "Oui, le samedi de 8h à 18h.", "name": "Nova", "usage": { "used_today": 12, "limit": 300 } }
```

L'API ne garde pas l'historique. Renvoie la discussion à chaque appel avec `messages` si l'assistant doit se
souvenir de ce qui a été dit.

### `GET SYRIUS/api/v1/info`

Renvoie `{"name": "Nova", "site": "Garage de Léo"}` et sert à vérifier que la clé marche.

### Erreurs

Le corps d'une erreur est `{"error": "message lisible"}`.

| Code | Sens |
|---|---|
| 400 | Corps invalide (pas de message, mauvais rôle…) |
| 401 | Clé manquante, fausse ou supprimée |
| 403 | Le site qui appelle n'est pas autorisé pour cette clé, ou une clé « serveur » est utilisée dans un navigateur |
| 429 | Limite du jour atteinte, pour la clé ou pour un même visiteur |
| 503 | IA momentanément indisponible : réessaie |

### Les deux sortes de clés

- **Clé « site »** : elle est liée à une ou plusieurs adresses. Le navigateur envoie l'en-tête `Origin`, que
  Syrius vérifie. La clé est visible dans la page, ce qui est normal : elle ne marche pas ailleurs et elle a une
  limite par jour.
- **Clé « serveur »** : elle n'a pas d'adresse. Elle s'utilise depuis ton serveur, en PHP, Node, Python…, et doit
  rester **secrète**. Elle est refusée si un navigateur l'utilise.

Exemple avec une clé serveur :

```bash
curl -X POST SYRIUS/api/v1/chat \
  -H "Authorization: Bearer sk_syr_…" -H "Content-Type: application/json" \
  -d '{"message": "Bonjour"}'
```

```js
// Node 18+
const r = await fetch("SYRIUS/api/v1/chat", {
  method: "POST",
  headers: { Authorization: `Bearer ${process.env.SYRIUS_KEY}`, "Content-Type": "application/json" },
  body: JSON.stringify({ message: "Bonjour" }),
});
console.log((await r.json()).reply);
```

## Limites

- Chaque clé a un nombre de messages par jour, fixé par le propriétaire : 300 par défaut, 3000 au plus.
- Un même visiteur peut envoyer 60 messages par jour au plus.
- Les compteurs repartent à zéro chaque jour à minuit, heure UTC.
- Les réponses sont générées par des IA gratuites. Elles peuvent parfois mettre quelques secondes à arriver.
