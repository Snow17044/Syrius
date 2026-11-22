"""Crée et lance le bot Discord sur un Space Hugging Face gratuit, avec la clé HF_TOKEN de ton Syrius.

Un bouton dans les réglages du propriétaire fait tout :
1. crée le Space public « syrius-discord » (Docker, CPU basic gratuit) sur ton compte Hugging Face ;
2. y dépose le Dockerfile (qui récupère le code du bot depuis ton dépôt GitHub) ;
3. y range les deux secrets : le jeton Discord (collé par toi, transmis directement, jamais gardé par Syrius) et
   la clé du bot (créée par ton Syrius).
Les secrets d'un Space ne sont jamais visibles, même si le Space est public.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request

API = "https://huggingface.co"
SPACE_NAME = "syrius-discord"
# Copie exacte de discord-bot/Dockerfile (Vercel n'envoie pas les fichiers « Dockerfile » ; un test vérifie l'égalité).
DOCKERFILE = '# Syrius sur Discord dans un conteneur (Hugging Face Space, offre gratuite « CPU basic »).\n# Le Space n\'a besoin QUE de ce fichier : il récupère le code du bot depuis le dépôt GitHub de Syrius.\nFROM node:22.23.4-bookworm-slim\n\nRUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates python3-venv wget \\\n    && rm -rf /var/lib/apt/lists/*\n\n# Voix française Piper (open source), servie uniquement à l\'intérieur du conteneur\nRUN python3 -m venv /opt/piper && /opt/piper/bin/pip install --no-cache-dir "piper-tts[http]==1.8.0" \\\n    && mkdir -p /opt/voices && /opt/piper/bin/python -m piper.download_voices fr_FR-siwis-medium --data-dir /opt/voices\n\n# Code du bot (dépendances figées, aucun script d\'installation exécuté)\nARG SYRIUS_REPO=Snow17044/Syrius\nARG SYRIUS_REF=main\nRUN git clone --depth 1 --branch "$SYRIUS_REF" "https://github.com/${SYRIUS_REPO}.git" /opt/syrius \\\n    && cd /opt/syrius/discord-bot && npm ci --omit=dev --ignore-scripts --no-audit --no-fund\n\nWORKDIR /opt/syrius/discord-bot\nENV PORT=7860 PIPER_URL=http://127.0.0.1:5000 SYRIUS_URL=https://syriusprojet1.vercel.app\nUSER node\nEXPOSE 7860\nCMD ["./start.sh"]\n'
README = """---
title: Syrius Discord
emoji: 🎙️
colorFrom: indigo
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
---

Syrius dans un salon vocal Discord (bot personnel). Code : https://github.com/{repo}/tree/main/discord-bot
"""
_DISCORD_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{20,}$")


class SpaceError(Exception):
    pass


def _call(token: str, method: str, path: str, body: bytes | None = None, ctype: str = "application/json",
          timeout: float = 30) -> tuple[int, dict | list | str]:
    req = urllib.request.Request(API + path, data=body, method=method, headers={
        "Authorization": f"Bearer {token}", "User-Agent": "Syrius/1.0", **({"Content-Type": ctype} if body else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310 (adresse fixe de Hugging Face)
            status, raw = r.status, r.read(500_000)
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read(20_000)
    except (urllib.error.URLError, OSError):
        raise SpaceError("Hugging Face ne répond pas, réessaie dans un moment.") from None
    try:
        return status, json.loads(raw or b"{}")
    except ValueError:
        return status, raw.decode("utf-8", "replace")[:300]


def valid_discord_token(t: str) -> bool:
    return bool(_DISCORD_TOKEN.match(t or ""))


def owner(hf_token: str) -> str:
    status, data = _call(hf_token, "GET", "/api/whoami-v2")
    if status != 200 or not isinstance(data, dict) or not data.get("name"):
        raise SpaceError("Clé Hugging Face (HF_TOKEN) refusée.")
    return data["name"]


def setup(hf_token: str, discord_token: str, bot_key: str, syrius_url: str, repo: str) -> dict:
    if not hf_token:
        raise SpaceError("Clé HF_TOKEN absente de ton Syrius (Vercel).")
    if not valid_discord_token(discord_token):
        raise SpaceError("Ce n'est pas un jeton de bot Discord (portail développeur → Bot → Reset Token).")
    user = owner(hf_token)
    space = f"{user}/{SPACE_NAME}"
    status, data = _call(hf_token, "POST", "/api/repos/create", json.dumps(
        {"name": SPACE_NAME, "type": "space", "sdk": "docker", "private": False}).encode())
    if status == 403:
        raise SpaceError("Ta clé Hugging Face ne permet pas de créer un Space : il faut une clé avec le droit "
                         "« Write » (huggingface.co/settings/tokens), à mettre dans HF_TOKEN sur Vercel.")
    if status not in (200, 201, 409):
        raise SpaceError(f"Création du Space impossible ({status}).")
    files = {"Dockerfile": DOCKERFILE.encode(), "README.md": README.format(repo=repo).encode()}
    lines = [{"key": "header", "value": {"summary": "Syrius sur Discord", "description": ""}}]
    lines += [{"key": "file", "value": {"path": p, "encoding": "base64", "content": base64.b64encode(c).decode()}}
              for p, c in files.items()]
    status, _ = _call(hf_token, "POST", f"/api/spaces/{space}/commit/main",
                      "\n".join(json.dumps(x) for x in lines).encode(), "application/x-ndjson", timeout=60)
    if status not in (200, 201):
        raise SpaceError(f"Envoi des fichiers impossible ({status}).")
    for key, value in (("DISCORD_TOKEN", discord_token), ("SYRIUS_BOT_KEY", bot_key)):
        status, _ = _call(hf_token, "POST", f"/api/spaces/{space}/secrets",
                          json.dumps({"key": key, "value": value}).encode())
        if status not in (200, 201):
            raise SpaceError(f"Enregistrement du secret {key} impossible ({status}).")
    status, _ = _call(hf_token, "POST", f"/api/spaces/{space}/variables",
                      json.dumps({"key": "SYRIUS_URL", "value": syrius_url}).encode())
    _call(hf_token, "POST", f"/api/spaces/{space}/restart", b"{}")
    return {"space": space, "url": f"https://huggingface.co/spaces/{space}"}


def status(hf_token: str) -> dict:
    """État du Space : BUILDING, RUNNING, RUNTIME_ERROR, etc."""
    if not hf_token:
        return {"exists": False}
    user = owner(hf_token)
    space = f"{user}/{SPACE_NAME}"
    code, data = _call(hf_token, "GET", f"/api/spaces/{space}/runtime")
    if code == 404:
        return {"exists": False}
    if code != 200 or not isinstance(data, dict):
        return {"exists": True, "stage": "UNKNOWN", "url": f"https://huggingface.co/spaces/{space}"}
    return {"exists": True, "stage": str(data.get("stage", "")), "hardware": str((data.get("hardware") or {}).get(
        "current") or ""), "url": f"https://huggingface.co/spaces/{space}"}


# ------------------------------------------------------------------ atelier rapide d'Aurora
ATELIER_SPACE = "syrius-atelier"
# Image Playwright : Node, Chromium et Python déjà dedans. Le code de l'atelier vient du dépôt GitHub de Syrius
# (au moment de la construction seulement). Copie exacte de selfcode/Dockerfile.atelier (un test vérifie l'égalité).
ATELIER_DOCKERFILE = '''# Atelier rapide d'Aurora (Hugging Face Space, offre gratuite « CPU basic ») : Python, Node.js et un vrai navigateur.
FROM mcr.microsoft.com/playwright:v1.49.1-noble

RUN apt-get update && apt-get install -y --no-install-recommends git python3-venv python3-pip ca-certificates \\
    && rm -rf /var/lib/apt/lists/*
# Python : un environnement à part (pip y installe ce que les projets demandent), pytest déjà là
RUN python3 -m venv /opt/py && /opt/py/bin/pip install --no-cache-dir pytest==9.1.1 && ln -sf /opt/py/bin/python /usr/local/bin/python
# Playwright pour la capture d'écran des sites (même version que le navigateur de l'image)
RUN mkdir -p /opt/kit && cd /opt/kit && npm init -y >/dev/null && npm install --no-audit --no-fund playwright@1.49.1

ARG SYRIUS_REPO=Snow17044/Syrius
ARG SYRIUS_REF=main
RUN git clone --depth 1 --branch "$SYRIUS_REF" "https://github.com/${SYRIUS_REPO}.git" /opt/syrius \\
    && chown -R 1000:1000 /opt/py /opt/kit

ENV PATH=/opt/py/bin:$PATH ATELIER_RUNNER=local ATELIER_KIT=/opt/kit RUNNER_TEMP=/tmp PORT=7860 \\
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright PYTHONUNBUFFERED=1
WORKDIR /opt/syrius
USER 1000
EXPOSE 7860
CMD ["python3", "selfcode/atelier_space.py"]
'''
ATELIER_README = """---
title: Syrius Atelier
emoji: 🛠️
colorFrom: pink
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

L'atelier rapide d'Aurora (Syrius Code) : elle y écrit, lance et teste son code. Code :
https://github.com/{repo}/blob/main/selfcode/atelier_space.py
"""


def space_host(user: str, name: str) -> str:
    """Adresse publique d'un Space : https://pseudo-nom.hf.space (minuscules, autres signes → « - »)."""
    sub = re.sub(r"[^a-z0-9]+", "-", f"{user}-{name}".lower()).strip("-")
    return f"https://{sub}.hf.space"


def setup_atelier(hf_token: str, worker_key: str, syrius_url: str, repo: str) -> dict:
    """Crée (ou met à jour) le Space de l'atelier, y range SA clé (pas HF_TOKEN) et le redémarre."""
    if not hf_token:
        raise SpaceError("Clé HF_TOKEN absente de ton Syrius (Vercel).")
    user = owner(hf_token)
    space = f"{user}/{ATELIER_SPACE}"
    status, _ = _call(hf_token, "POST", "/api/repos/create", json.dumps(
        {"name": ATELIER_SPACE, "type": "space", "sdk": "docker", "private": False}).encode())
    if status == 403:
        raise SpaceError("Ta clé Hugging Face ne permet pas de créer un Space : il faut une clé avec le droit "
                         "« Write » (huggingface.co/settings/tokens), à mettre dans HF_TOKEN sur Vercel.")
    if status == 402:
        raise SpaceError("Hugging Face demande désormais l'abonnement PRO (environ 9 $ par mois) pour ce type de "
                         "serveur. Sans lui, les sites se font dans l'atelier instantané et le reste sur GitHub.")
    if status not in (200, 201, 409):
        raise SpaceError(f"Création du Space impossible ({status}).")
    files = {"Dockerfile": ATELIER_DOCKERFILE.encode(), "README.md": ATELIER_README.format(repo=repo).encode()}
    lines = [{"key": "header", "value": {"summary": "Atelier d'Aurora", "description": ""}}]
    lines += [{"key": "file", "value": {"path": p, "encoding": "base64", "content": base64.b64encode(c).decode()}}
              for p, c in files.items()]
    status, _ = _call(hf_token, "POST", f"/api/spaces/{space}/commit/main",
                      "\n".join(json.dumps(x) for x in lines).encode(), "application/x-ndjson", timeout=60)
    if status not in (200, 201):
        raise SpaceError(f"Envoi des fichiers impossible ({status}).")
    status, _ = _call(hf_token, "POST", f"/api/spaces/{space}/secrets",
                      json.dumps({"key": "ATELIER_TOKEN", "value": worker_key}).encode())
    if status not in (200, 201):
        raise SpaceError(f"Enregistrement de la clé de l'atelier impossible ({status}).")
    _call(hf_token, "POST", f"/api/spaces/{space}/variables", json.dumps({"key": "SYRIUS_URL", "value": syrius_url}).encode())
    _call(hf_token, "POST", f"/api/spaces/{space}/restart", b"{}")
    return {"space": space, "url": space_host(user, ATELIER_SPACE), "page": f"https://huggingface.co/spaces/{space}"}


def atelier_status(hf_token: str, space: str) -> dict:
    if not hf_token or not space:
        return {"exists": False}
    code, data = _call(hf_token, "GET", f"/api/spaces/{space}/runtime")
    if code == 404:
        return {"exists": False}
    stage = str(data.get("stage", "")) if code == 200 and isinstance(data, dict) else "UNKNOWN"
    return {"exists": True, "stage": stage}
