"""Point d'entrée pour Vercel (il cherche une variable `app` dans app.py)."""
import logging

from server.app import create_app

logging.basicConfig(level=logging.INFO)
app = create_app()
