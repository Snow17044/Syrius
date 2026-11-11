"""Commandes d'administration.

    python -m server.manage set-password     # définir / changer le mot de passe
    python -m server.manage outlook-login    # connecter une boîte Outlook / Hotmail
"""
import getpass
import sys

from . import auth
from .config import config
from .app import open_database
from .tools.email_tool import EmailError, outlook_device_login


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in {"set-password", "outlook-login"}:
        print(__doc__)
        return 1
    db = open_database(config)
    if argv[0] == "set-password":
        pw = getpass.getpass("Nouveau mot de passe Syrius (10 caractères min.) : ")
        if pw != getpass.getpass("Confirme : "):
            print("Les mots de passe ne correspondent pas.")
            return 1
        try:
            auth.set_password(db, pw)
        except ValueError as e:
            print(e)
            return 1
        print("Mot de passe enregistré ✅ (tous les appareils ont été déconnectés)")
        return 0
    try:
        outlook_device_login(config, db)
    except EmailError as e:
        print(f"Erreur : {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
