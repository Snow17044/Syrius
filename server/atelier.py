"""L'Atelier d'Aurora : elle écrit un programme, le LANCE et le TESTE elle-même, puis le corrige jusqu'à ce qu'il marche.

Comme un développeur sur son ordinateur : Aurora travaille sur un serveur Linux gratuit de GitHub (workflow
« Atelier d'Aurora »). Elle écrit les fichiers, installe ce qu'il faut, lance les tests, lit les erreurs et corrige
(jusqu'à 5 essais). Le code qui tourne est enfermé dans un conteneur sans aucun secret. Le résultat (fichiers, sortie
des tests) revient ici et s'affiche dans Syrius Code.

Réservé au propriétaire. Le serveur de GitHub ne peut que prendre le projet suivant et en donner l'avancement.
"""
from __future__ import annotations

import base64
import hmac
import io
import json
import re
import secrets
import time
import zipfile

from . import safety

KEY = "family_atelier_v1"
SHOT_KEY = "family_atelier_shot_"  # + id : capture d'écran du site (rangée à part, la liste reste légère)
MAX_SHOT_BYTES = 600_000
WORKFLOW = "atelier.yml"
MAX_ITEMS = 20
MAX_FILES = 60
MAX_FILE_CHARS = 60_000
MAX_TOTAL_CHARS = 450_000  # gros sites : plusieurs pages, scripts et styles
STATUSES = ("pending", "running", "done", "failed")
_ID = re.compile(r"^[0-9a-f]{8}$")
_PATH = re.compile(r"^(?!/)(?!.*\.\.)[\w.\-/ ]{1,120}$")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class AtelierError(ValueError):
    pass


# ------------------------------------------------------------------ atelier rapide (serveur Hugging Face)
WORKER_KEY = "family_atelier_worker_v1"  # clé propre à l'atelier : ne sert QU'À prendre et rendre les projets
SPACE_KEY = "family_atelier_space_v1"    # {"space": "pseudo/syrius-atelier", "url": "https://….hf.space"}


def worker_token(base, renew: bool = False) -> str:
    t = base.get_secret(WORKER_KEY)
    if renew or not t:
        t = "atl_" + secrets.token_urlsafe(32)
        base.set_secret(WORKER_KEY, t)
    return t


def check_worker(base, given: str) -> bool:
    t = base.get_secret(WORKER_KEY) or ""
    return bool(t and given) and hmac.compare_digest(t.encode(), str(given).encode())


def space(base) -> dict:
    try:
        d = json.loads(base.get_secret(SPACE_KEY) or "{}")
    except ValueError:
        d = {}
    return d if isinstance(d, dict) else {}


def set_space(base, info: dict) -> None:
    base.set_secret(SPACE_KEY, json.dumps({k: info.get(k, "") for k in ("space", "url", "page")}))


def wake(base) -> bool:
    """Réveille l'atelier rapide : le projet démarre en quelques secondes. False s'il n'existe pas ou ne répond pas."""
    import urllib.error
    import urllib.request
    url = str(space(base).get("url") or "")
    if not re.fullmatch(r"https://[a-z0-9-]+\.hf\.space", url):
        return False
    req = urllib.request.Request(url + "/wake", data=b"{}", method="POST", headers={
        "X-Atelier-Key": worker_token(base), "User-Agent": "Syrius/1.0", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:  # nosec B310 (adresse de ton atelier, vérifiée ci-dessus)
            # « ok » : c'est bien l'atelier qui répond (pas la page d'attente d'un serveur endormi)
            return r.status == 202 and r.read(20).strip() == b"ok"
    except (urllib.error.URLError, OSError, ValueError):
        return False  # endormi ou en construction : GitHub prend le relais


def _load(base) -> list[dict]:
    try:
        data = json.loads(base.get_secret(KEY) or "[]")
    except ValueError:
        return []
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def _save(base, items: list[dict]) -> None:
    for old in items[:-MAX_ITEMS]:  # les projets oubliés emportent leur capture
        base.set_secret(SHOT_KEY + str(old.get("id", "")), "")
    base.set_secret(KEY, json.dumps(items[-MAX_ITEMS:], ensure_ascii=False))


def _fresh(item: dict, now: float) -> dict:
    if item.get("status") == "running" and now - item.get("updated", 0) > 3600:
        item = {**item, "status": "failed", "summary": "Pas de nouvelles du serveur de GitHub (interrompu)."}
    if item.get("status") == "pending" and now - item.get("created", 0) > 3 * 3600:
        item = {**item, "status": "failed", "summary": "Le serveur de GitHub n'a pas pris le projet (atelier pas lancé ?)."}
    return item


def items(base) -> list[dict]:
    now = time.time()
    return [_fresh(d, now) for d in _load(base)][::-1]


def get(base, pid: str) -> dict | None:
    return next((d for d in items(base) if d.get("id") == pid), None)


def add(base, text: str) -> dict:
    t = str(text).strip()
    if not 10 <= len(t) <= 4000:
        raise AtelierError("Décris le programme en 10 à 4000 caractères.")
    if safety.blocked(t):
        raise AtelierError("Projet refusé : pas de contenu sexuel ni violent.")
    data = _load(base)
    if sum(1 for d in data if _fresh(d, time.time()).get("status") in ("pending", "running")) >= 2:
        raise AtelierError("2 projets sont déjà en cours dans l'atelier : attends qu'ils soient finis.")
    now = int(time.time())
    item = {"id": secrets.token_hex(4), "token": secrets.token_urlsafe(18), "text": t, "status": "pending",
            "created": now, "updated": now,
            "summary": "", "attempt": 0, "files": {}, "log": "", "setup": "", "test": "", "env": ""}
    data.append(item)
    _save(base, data)
    return item


def note(base, pid: str, text: str) -> None:
    """Message affiché sur la carte d'un projet en attente (ex. pourquoi il n'a pas démarré tout de suite)."""
    data = _load(base)
    for d in data:
        if d.get("id") == pid and d.get("status") == "pending":
            d["summary"] = _CTRL.sub("", str(text))[:600]
            _save(base, data)
            return


def take_next(base) -> dict | None:
    """Pour le serveur de GitHub : le plus ancien projet en attente (marqué « en cours »)."""
    data = _load(base)
    for d in data:
        if d.get("status") == "pending" and d.get("mode") != "instant":  # les sites instantanés se font dans l'appli
            d["status"], d["updated"], d["summary"] = "running", int(time.time()), "L'atelier démarre…"
            _save(base, data)
            return {"id": d["id"], "text": d["text"]}
    return None


def _files(raw) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out, total = {}, 0
    for path, content in list(raw.items())[:MAX_FILES]:
        if not isinstance(path, str) or not isinstance(content, str) or not _PATH.match(path):
            continue
        content = content[:MAX_FILE_CHARS]
        if total + len(content) > MAX_TOTAL_CHARS:
            break
        total += len(content)
        out[path] = content
    return out


def report(base, body: dict) -> None:
    """Avancement envoyé par le serveur de GitHub (à chaque essai, puis le résultat final)."""
    if not isinstance(body, dict):
        raise AtelierError("résultat invalide")
    pid, status = str(body.get("id", "")), body.get("status")
    if not _ID.match(pid) or status not in ("running", "done", "failed"):
        raise AtelierError("résultat invalide")
    data = _load(base)
    for d in data:
        if d.get("id") != pid:
            continue
        d["status"] = status
        d["updated"] = int(time.time())
        d["summary"] = _CTRL.sub("", str(body.get("summary") or ""))[:1500]
        try:
            d["attempt"] = max(0, min(int(body.get("attempt") or 0), 20))
        except (TypeError, ValueError):
            pass
        d["log"] = str(body.get("log") or "")[-6000:]
        for k in ("setup", "test"):
            d[k] = _CTRL.sub("", str(body.get(k) or ""))[:300]
        d["env"] = body.get("env") if body.get("env") in ("python", "node", "web") else ""
        files = _files(body.get("files"))
        if files:
            d["files"] = files
        shot = body.get("screenshot")
        if isinstance(shot, str) and shot:
            try:
                raw = base64.b64decode(shot, validate=True)
            except ValueError:
                raw = b""
            if raw[:3] == b"\xff\xd8\xff" and len(raw) <= MAX_SHOT_BYTES:  # une vraie image JPEG, pas trop lourde
                base.set_secret(SHOT_KEY + pid, shot)
                d["has_shot"] = True
        _save(base, data)
        return
    raise AtelierError("projet inconnu")


# ------------------------------------------------------------------ aperçu du site, capture, téléchargement
def check_token(item: dict | None, token: str) -> bool:
    return bool(item and item.get("token") and token) and hmac.compare_digest(str(item["token"]), str(token))


def screenshot(base, pid: str) -> bytes:
    try:
        return base64.b64decode(base.get_secret(SHOT_KEY + pid) or "", validate=True)
    except ValueError:
        return b""


def site_root(files: dict) -> str | None:
    """Dossier du site : « site/ » s'il existe, sinon la racine si elle a un index.html ; None = pas de site."""
    if "site/index.html" in files:
        return "site/"
    if "index.html" in files:
        return ""
    return None


TYPES = {"html": "text/html; charset=utf-8", "css": "text/css; charset=utf-8", "js": "text/javascript; charset=utf-8",
         "mjs": "text/javascript; charset=utf-8", "json": "application/json", "svg": "image/svg+xml",
         "txt": "text/plain; charset=utf-8", "md": "text/plain; charset=utf-8", "xml": "text/plain; charset=utf-8",
         "webmanifest": "application/manifest+json"}


def site_file(item: dict, path: str) -> tuple[str, str] | None:
    files = item.get("files") or {}
    root = site_root(files)
    if root is None:
        return None
    path = (path or "index.html").lstrip("/")
    if path.endswith("/") or not path:
        path += "index.html"
    content = files.get(root + path)
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if content is None or ext not in TYPES:
        return None
    return content, TYPES[ext]


def zip_bytes(item: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, content in (item.get("files") or {}).items():
            z.writestr(path, content)
    return buf.getvalue()


def public(item: dict) -> dict:
    """Ce que l'application reçoit : jamais le jeton seul, mais les adresses d'aperçu et de téléchargement."""
    out = {k: v for k, v in item.items() if k != "token"}
    if item.get("token") and item.get("files"):
        out["zip_url"] = f"/atelier/{item['id']}/{item['token']}/projet.zip"
        if site_root(item["files"]) is not None:
            out["site_url"] = f"/atelier/{item['id']}/{item['token']}/site/"
    return out


def for_aurora(item: dict) -> str:
    """Résultat lisible par Aurora (outil check_code_project)."""
    st = {"pending": "en attente", "running": "en cours", "done": "TERMINÉ : les tests passent",
          "failed": "ÉCHEC"}[item["status"]]
    parts = [f"Projet {item['id']} : {st} (essai {item.get('attempt', 0)}/5).", f"Résumé : {item.get('summary') or '—'}"]
    if item.get("setup") or item.get("test"):
        parts.append(f"Environnement : {item.get('env') or '?'} ; installation : {item.get('setup') or 'aucune'} ; "
                     f"test : {item.get('test') or '?'}")
    for path, content in (item.get("files") or {}).items():
        parts.append(f"### {path}\n```\n{content[:6000]}\n```")
    if item.get("log"):
        parts.append("Dernière sortie des tests :\n```\n" + item["log"][-1500:] + "\n```")
    return "\n\n".join(parts)[:20000]


# ------------------------------------------------------------------ atelier INSTANTANÉ (sites web, dans l'appli)
# Pour un site statique (HTML/CSS/JS), pas besoin de serveur : l'application ouvre le site dans une boîte fermée
# (iframe « sandbox »), lance les tests d'Aurora, et renvoie les erreurs ici pour qu'elle corrige. Instantané.
MAX_INSTANT_ATTEMPTS = 4   # tests + corrections
MAX_INSTANT_STEPS = 10     # passages d'écriture d'un gros site (fichiers écrits en plusieurs fois)
PROMPT_FILES_CHARS = 22_000  # contenu des fichiers renvoyé à l'IA à chaque passage (le reste : seulement le nom)
WEB_SYSTEM = """Tu es Aurora, une développeuse web experte, soignée et exigeante. Tu fais un site STATIQUE (HTML, CSS,
JavaScript, sans serveur ni étape de compilation), beau, moderne et adapté au téléphone (responsive). Il est ouvert
dans un vrai navigateur puis testé automatiquement ; tu reçois les erreurs et tu corriges.

Réponds EXACTEMENT dans ce format, sans rien d'autre :
RÉSUMÉ: 1 à 3 phrases en français (ce que fait le site, ou ce que tu as corrigé)
### FICHIER: index.html
```
contenu COMPLET
```
### FICHIER: style.css
```
…
```
### FICHIER: script.js
```
…
```
### FICHIER: tests.js
```
window.__tests = [
  { nom: "le titre s'affiche", test: async (t) => { t.assert(t.text("h1").length > 0, "titre vide"); } },
  { nom: "le bouton compte", test: async (t) => { t.click("#plus"); await t.wait(100); t.assert(t.text("#n") === "1", "compteur"); } },
];
```
Règles :
- index.html à la racine, qui charge style.css et script.js (chemins relatifs) ; ajoute d'autres fichiers si utile.
- tests.js est OBLIGATOIRE : 2 à 6 tests réels de ce que l'utilisateur a demandé. Outils de t : t.q(sélecteur) → élément,
  t.click(sélecteur), t.type(sélecteur, texte), t.text(sélecteur) → texte, t.assert(condition, message), t.wait(ms).
  Les tests ne doivent jamais modifier le site pour réussir.
- Aucune erreur dans la console, aucune ressource introuvable. Pas de localStorage obligatoire (il peut être bloqué) :
  entoure-le de try/catch. Pas de clé d'API, pas de mot de passe, rien de sexuel ni de violent.
- À chaque correction, renvoie le format complet avec le contenu ENTIER de chaque fichier modifié.
- GROS SITE (plusieurs pages, beaucoup de contenu) : c'est possible. Si tout ne tient pas dans une seule réponse, écris
  d'abord index.html, style.css, script.js et tests.js, puis termine par une ligne
  SUITE: autre-page.html, autre.css, …
  qui liste les fichiers qu'il te reste à écrire : on te les redemandera, en plusieurs fois s'il le faut. Pas de ligne
  SUITE quand le site est complet. Les pages se relient par des liens relatifs et partagent style.css."""

_FILE_RX = re.compile(r"^#{2,4}\s*FICHIER\s*:\s*`?([^\n`]+?)`?\s*\n+```[^\n]*\n(.*?)\n```", re.S | re.M)
_SUMMARY_RX = re.compile(r"^\s*\**R[ÉE]SUM[ÉE]\**\s*:\s*\**\s*(.*)$", re.I | re.M)


def parse_reply(reply: str) -> dict:
    files = {}
    for path, content in _FILE_RX.findall(reply or ""):
        path = path.strip()
        while path.startswith("./"):
            path = path[2:]
        if _PATH.match(path) and not path.startswith("node_modules"):
            files[path] = content + "\n"
    m = _SUMMARY_RX.search(reply or "")
    todo = []
    s = re.search(r"^\s*\**SUITE\**\s*:\s*(.+)$", reply or "", re.I | re.M)
    if s:
        todo = [p.strip(" `.") for p in s.group(1).split(",")]
        todo = [p for p in todo if _PATH.match(p) and p not in files][:20]
    return {"files": files, "summary": _CTRL.sub(" ", m.group(1)).strip()[:600] if m else "", "todo": todo}


def add_instant(base, text: str) -> dict:
    item = add(base, text)
    data = _load(base)
    for d in data:
        if d["id"] == item["id"]:
            d["mode"] = "instant"
            d["env"] = "web"
            d["summary"] = "Aurora prépare le site…"
    _save(base, data)
    return {**item, "mode": "instant"}


def _files_for_prompt(files: dict, focus: str = "") -> str:
    """Contenu des fichiers pour l'IA, dans la limite d'une demande : d'abord ceux cités dans les erreurs, puis les
    principaux ; les autres sont seulement nommés (gros sites)."""
    order = sorted(files, key=lambda p: (p not in focus, p not in ("index.html", "script.js", "style.css", "tests.js"), p))
    out, room, named = [], PROMPT_FILES_CHARS, []
    for p in order:
        c = files[p]
        if len(c) <= room:
            out.append(f"### FICHIER: {p}\n```\n{c}\n```")
            room -= len(c)
        else:
            named.append(f"{p} ({len(c)} caractères)")
    if named:
        out.append("Autres fichiers déjà écrits (non montrés ici) : " + ", ".join(named))
    return "\n\n".join(out)


def instant_prompt(item: dict, feedback: str = "") -> str:
    if not item.get("files"):
        return f"Site demandé :\n{item['text']}\n\nÉcris le site complet avec ses tests."
    files = _files_for_prompt(item["files"], feedback)
    if item.get("todo") and not feedback:  # gros site : on continue l'écriture
        return (f"Site demandé :\n{item['text']}\n\nDéjà écrit :\n{files}\n\nÉcris maintenant ces fichiers : "
                f"{', '.join(item['todo'])}. Même format ; termine par SUITE: … s'il en reste encore.")
    return (f"Site demandé :\n{item['text']}\n\nFichiers actuels :\n{files}\n\nRésultat RÉEL dans le navigateur :\n"
            f"{feedback[:3500]}\n\nCorrige la cause (le code du site, pas les tests sauf s'ils sont faux). "
            "Renvoie le format complet avec les fichiers modifiés.")


def instant_update(base, pid: str, *, files: dict | None = None, summary: str | None = None, status: str | None = None,
                   log: str | None = None, attempt: int | None = None, todo: list | None = None,
                   steps: int | None = None) -> dict | None:
    data = _load(base)
    for d in data:
        if d.get("id") != pid or d.get("mode") != "instant":
            continue
        if files:
            merged = {**(d.get("files") or {}), **files}
            d["files"] = _files(merged)
        if summary is not None:
            d["summary"] = _CTRL.sub(" ", summary)[:1500]
        if status in STATUSES:
            d["status"] = status
        if log is not None:
            d["log"] = str(log)[-6000:]
        if attempt is not None:
            d["attempt"] = max(0, min(int(attempt), 20))
        if todo is not None:
            d["todo"] = [p for p in todo if isinstance(p, str)][:20]
        if steps is not None:
            d["steps"] = max(0, min(int(steps), 50))
        d["updated"] = int(time.time())
        _save(base, data)
        return d
    return None
