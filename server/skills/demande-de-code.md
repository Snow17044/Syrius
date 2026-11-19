---
name: demande-de-code
description: Préparer une demande de changement du code de Syrius ou de Syrius Code, à envoyer à l'IA programmeuse.
---
Avant d'appeler `propose_code_change`, assure-toi que la demande est précise, petite et testable.
1. Une seule modification par demande (petite). Si c'est gros, découpe en étapes et propose-les une par une.
2. Dis OÙ : application « Syrius » (web/index.html, web/app.js, web/style.css, server/…) ou « Syrius Code »
   (web/code.html, web/code.js, web/code.css, server/aurore.md, server/skills/…).
3. Dis QUOI exactement (comportement attendu, texte affiché, cas limites) et COMMENT vérifier (test à écrire).
4. Parties INTERDITES à l'IA programmeuse : connexion et mots de passe, comptes de la famille, filtres de contenu,
   base de données, configuration, automatisations GitHub, signature Android, entraînement, scanner de sites.
   Si la demande les touche, dis que le propriétaire devra le faire avec un développeur.
5. Résultat : une proposition (pull request) que le propriétaire relit et publie lui-même. Tu ne publies jamais.
6. Pas de nouvelle dépendance, pas de secret dans le code.
