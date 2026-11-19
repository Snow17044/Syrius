---
name: audit-securite-site
description: Lire un résultat de scan de sécurité d'un site, le prioriser et expliquer quoi corriger en premier.
---
1. Lance `scan_site` seulement sur un site que le propriétaire a ajouté et prouvé. Jamais un autre.
2. Classe les problèmes en trois groupes : à corriger aujourd'hui (graves : fichiers secrets exposés, clés visibles,
   HTTPS cassé), cette semaine (moyens : en-têtes, cookies), plus tard (légers et informations).
3. Pour chaque problème : une phrase sur le risque réel (pas de jargon), puis le correctif concret. Si le site est
   fait avec un assistant de code, écris la consigne exacte à lui donner.
4. Rappelle que le scan est passif : il ne teste ni injections, ni connexions, ni formulaires, et ne remplace pas un
   test d'intrusion complet.
5. Si une clé secrète est visible : dis de la RÉVOQUER tout de suite chez le service concerné, avant même de corriger le site.
