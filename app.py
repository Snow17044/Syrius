"""Point d'entrée pour Vercel (il cherche une variable `app` dans app.py).

Avec la variable UCHRONIE_SEUL=1, ce projet sert le jeu Uchronie seul (site à part, sans compte) au lieu de Syrius.
"""
import logging
import os

logging.basicConfig(level=logging.INFO)

if os.environ.get("UCHRONIE_SEUL", "").strip().lower() in ("1", "true", "oui", "yes"):
    from server.uchronie_site import create_site
    app = create_site()
else:
    from server.app import create_app
    app = create_app()
