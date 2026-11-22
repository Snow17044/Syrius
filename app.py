"""Point d'entrée pour Vercel (il cherche une variable `app` dans app.py, écrite directement à la racine du fichier).

Avec la variable UCHRONIE_SEUL=1, ce projet sert le jeu Uchronie seul (site à part, sans compte) au lieu de Syrius.
"""
import logging
import os

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)


def build() -> FastAPI:
    if os.environ.get("UCHRONIE_SEUL", "").strip().lower() in ("1", "true", "oui", "yes"):
        from server.uchronie_site import create_site
        return create_site()
    from server.app import create_app
    return create_app()


app: FastAPI = build()
