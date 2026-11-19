# Simulateur de drone (Syrius)

**Simulation seulement.** Rien ici ne parle à un vrai drone, et ce dossier n'est pas relié à l'application Syrius.

## Ce que c'est
- `sim.py` : la physique d'un quadricoptère (poids, poussée, inclinaison, vent, rafales, moteurs qui répondent avec un retard, batterie, sol).
- `control.py` : le **pilote automatique**, qui fait le travail difficile tout seul : stabiliser le drone, tenir sa position et sa hauteur, se poser doucement. Il ne voit que des mesures bruitées, comme un vrai drone.
- `commander.py` : les **ordres simples** (`takeoff`, `goto`, `hover`, `land`, `status`), tous vérifiés, et les **sécurités** (batterie faible, liaison perdue, sortie de zone) qui déclenchent l'atterrissage automatique.
- `render.py` : dessine un vol en SVG.

## Qui fait quoi
Syrius (une IA qui parle) ne devrait JAMAIS piloter les moteurs : il met plusieurs secondes à répondre et peut se tromper. Il donne seulement des ordres de haut niveau en JSON, par exemple `{"cmd": "takeoff", "altitude": 10}` ; le pilote automatique, qui réagit 200 fois par seconde, s'occupe du reste.

## Essayer
```
python -m drone --vent 6 --rafales 2 --sortie vol.svg
```
Un vol complet : décollage, déplacement, atterrissage automatique, avec un résumé et un dessin.

## Limites mesurées (10 à 20 essais par cas, simulation)
- Vent jusqu'à 12 m/s avec rafales de 3 m/s : le drone se pose doucement (moins de 0,4 m/s).
- Vers 16 m/s de vent constant, il ne peut plus tenir sa position : il dérive de dizaines de mètres, mais se pose quand même sans casse. Les sécurités de zone le font atterrir plus tôt.
- Le monde simulé est simplifié : pas d'effet de sol, pas de capteurs qui tombent en panne, pas de vraie mécanique des moteurs. Ce qui marche ici n'est PAS une preuve que ça marcherait sur un vrai drone.

## Avant tout vrai drone (à lire)
En France, les drones sont réglementés : enregistrement, zones interdites, hauteur maximale, pas de vol au-dessus de personnes. Les règles dépendent de l'âge du pilote et du poids du drone. Un vrai drone doit garder son propre contrôleur de vol certifié (PX4, ArduPilot ou celui du constructeur), un retour automatique à la maison et une télécommande pour reprendre la main à tout moment.
