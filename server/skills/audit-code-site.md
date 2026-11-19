---
name: audit-code-site
description: Lire tout le code d'un site (pages, scripts, styles) et en faire un audit : sécurité, bugs, qualité, performance.
---
1. Commence par `list_site_files` : regarde la structure (nombre de pages, scripts, styles, sourcemaps, secrets masqués).
2. Lis dans cet ordre : la page d'accueil, puis les scripts qui font appel à un serveur ou stockent des données, puis
   les formulaires, puis les styles. Utilise `part` pour la suite d'un gros fichier. Si un sourcemap existe, lis les
   sources originales : elles sont plus claires que le code compressé.
3. Cherche : secrets ou adresses d'API en dur ; `innerHTML`, `eval`, `document.write` avec des données venant de
   l'extérieur ; jetons ou mots de passe gardés dans `localStorage` ; scripts de sites tiers sans contrôle d'intégrité ;
   formulaires sans protection ; requêtes en http ; appels qui échouent sans gestion d'erreur ; code mort ou dupliqué.
4. Puis qualité : performance (gros fichiers, images non optimisées), accessibilité (texte alternatif, étiquettes de
   champs, contrastes), référencement (titre, description, structure des titres).
5. Rapport : un résumé en 3 lignes, puis les points classés [Grave] [Moyen] [Léger] avec le fichier et l'extrait
   concerné (court), la raison et le correctif en code. Ne recopie jamais un secret : s'il est masqué, dis seulement
   où il se trouve et de le révoquer.
6. Si tu n'as pas pu tout lire (limite de fichiers par réponse), dis précisément ce qui reste et propose de continuer
   dans un nouveau message. N'invente jamais le contenu d'un fichier que tu n'as pas lu.
7. Pour corriger : propose le code corrigé ; si c'est un site du propriétaire hébergé dans ce dépôt, applique la
   compétence `demande-de-code` plutôt que de modifier toi-même.
