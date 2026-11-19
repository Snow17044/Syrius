---
name: revue-de-code
description: Relire du code (le tien ou celui du propriétaire) : bugs, failles de sécurité, lisibilité, tests manquants.
---
1. Lis tout le code avant de répondre. Si une partie manque pour juger (fichier, version, erreur exacte), demande-la.
2. Cherche dans cet ordre : bugs qui cassent le résultat, failles de sécurité (injection, secrets écrits dans le code,
   entrées non vérifiées, droits trop larges), cas limites (vide, très grand, erreur réseau), puis lisibilité.
3. Réponds en liste courte classée par gravité : [Grave] [Moyen] [Léger]. Pour chaque point : où (ligne ou fonction),
   pourquoi c'est un problème, et le correctif en code.
4. Termine par la version corrigée complète seulement si le code est court (moins de 60 lignes) ; sinon, donne les
   morceaux à changer.
5. Propose 2 à 3 tests utiles. Ne félicite pas pour du code moyen : sois juste et précis.
