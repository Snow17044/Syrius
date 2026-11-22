"""Publier sur Internet un site fait par Aurora (bouton « Publier sur Internet » de Syrius Code).

C'est TOUJOURS le propriétaire qui appuie sur le bouton : Aurora ne publie jamais rien d'elle-même.
Le site est envoyé sur le Vercel du propriétaire (clé VERCEL_TOKEN, créée pour ça) comme un projet à part
« aurora-… » : l'adresse publique est https://aurora-….vercel.app. Seuls les fichiers du site partent, jamais les
tests ni le reste du projet, et jamais rien de Syrius.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from . import atelier, safety

API = "https://api.vercel.com"
SKIP = re.compile(r"(^|/)(tests?\.js|tests?/|package(-lock)?\.json$|node_modules/|\.)", re.I)


class PublishError(Exception):
    pass


def project_name(item: dict) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", item.get("text", "").lower()
                   .translate(str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc"))).strip("-")
    words = "-".join(words.split("-")[:4])[:28].strip("-") or "site"
    return f"aurora-{words}-{item['id'][:4]}"


def site_files(item: dict) -> dict[str, str]:
    files = item.get("files") or {}
    root = atelier.site_root(files)
    if root is None:
        raise PublishError("Ce projet n'a pas de page d'accueil (index.html) : rien à publier.")
    out = {p[len(root):]: c for p, c in files.items() if p.startswith(root) and not SKIP.search(p[len(root):])}
    if "index.html" not in out:
        raise PublishError("La page d'accueil (index.html) manque.")
    return out


def _call(token: str, method: str, path: str, team: str, body: dict | None = None) -> tuple[int, dict]:
    sep = "&" if "?" in path else "?"
    url = API + path + (f"{sep}teamId={urllib.parse.quote(team)}" if team else "")
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                          "User-Agent": "Syrius/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # nosec B310 (adresse fixe de Vercel)
            return r.status, json.loads(r.read(2_000_000) or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read(20_000) or b"{}")
        except ValueError:
            return e.code, {}
    except (urllib.error.URLError, OSError, ValueError):
        raise PublishError("Vercel ne répond pas, réessaie dans un moment.") from None


def publish(item: dict, token: str, team: str = "") -> dict:
    """Envoie le site sur Vercel ; renvoie {"url": adresse publique, "name": projet}."""
    if not token:
        raise PublishError("La clé VERCEL_TOKEN n'est pas configurée dans Vercel.")
    if item.get("status") != "done":
        raise PublishError("Seul un site terminé (tests réussis) peut être publié.")
    files = site_files(item)
    if safety.blocked(*files.values()):
        raise PublishError("Publication refusée : contenu sexuel ou violent.")
    name = project_name(item)
    code, data = _call(token, "POST", "/v13/deployments?skipAutoDetectionConfirmation=1", team, {
        "name": name, "target": "production", "projectSettings": {"framework": None},
        "files": [{"file": p, "data": c} for p, c in files.items()]})
    if code == 403:
        raise PublishError("Vercel refuse la clé (droits insuffisants ou clé supprimée).")
    if code not in (200, 201) or not data.get("id"):
        msg = (data.get("error") or {}).get("message", "") if isinstance(data.get("error"), dict) else ""
        raise PublishError(f"Publication impossible ({code}){' : ' + msg[:120] if msg else ''}.")
    project = data.get("projectId", "")
    if project:  # adresse publique : pas de connexion Vercel demandée aux visiteurs
        _call(token, "PATCH", f"/v9/projects/{project}", team, {"ssoProtection": None})
    url = f"https://{name}.vercel.app"
    if project:
        code, doms = _call(token, "GET", f"/v9/projects/{project}/domains", team)
        names = [d.get("name", "") for d in (doms.get("domains") or []) if isinstance(d, dict)]
        url = next((f"https://{n}" for n in names if n.endswith(".vercel.app")), url)
    return {"url": url, "name": name, "deployment": data.get("id", "")}
