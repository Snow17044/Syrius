"""Vraies maquettes 3D (fichiers GLB texturés) pour Syrius.

1. Bibliothèque Poly Pizza (modèles créés par des artistes, licences CC0 / CC-BY) : instantané.
2. Sinon, création sur mesure : image de l'objet (Pollinations) → maquette texturée par TRELLIS.2
   (IA 3D de Microsoft, hébergée gratuitement sur Hugging Face ; environ 1 à 2 minutes, quota quotidien).

Sécurité : hôtes fixes uniquement (connexions épinglées sur une IP publique), identifiants vérifiés,
taille limitée, et seul un vrai fichier GLB (en-tête « glTF ») est renvoyé au téléphone. Les clés restent
sur le serveur (variables Vercel POLYPIZZA_API_KEY et HF_TOKEN).
"""
from __future__ import annotations

import http.client
import json
import re
import secrets
import ssl
import time
from urllib.parse import quote, urlsplit

from . import imagegen, web

MAX_GLB = 4_300_000  # limite de réponse de Vercel (4,5 Mo)
POLY_API = "api.poly.pizza"
POLY_FILES = ("static.poly.pizza",)
TRELLIS = "microsoft-trellis-2.hf.space"
_ID = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


class Real3DError(Exception):
    pass


# ------------------------------------------------------------------ HTTP épinglé
def _request(host: str, method: str, path: str, headers: dict, body: bytes | None = None,
             timeout: float = 30, limit: int = 2_000_000) -> tuple[int, dict, bytes]:
    try:
        ip = web.resolve_public(host, 443)
    except web.WebError as e:
        raise Real3DError(str(e)) from None
    conn = web._PinnedHTTPS(host, ip, 443, timeout)
    try:
        conn.request(method, path, body=body, headers={"User-Agent": "SyriusAssistant/1.0", "Connection": "close", **headers})
        resp = conn.getresponse()
        data = resp.read(limit + 1)
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, data
    except (OSError, http.client.HTTPException, ssl.SSLError):
        raise Real3DError("service 3D injoignable") from None
    finally:
        conn.close()


def check_glb(data: bytes) -> bytes:
    if len(data) < 64 or data[:4] != b"glTF":
        raise Real3DError("le service n'a pas renvoyé de modèle 3D valide")
    if len(data) > MAX_GLB:
        raise Real3DError("modèle 3D trop lourd")
    return data


def clean_query(text, limit: int = 300) -> str:
    if not isinstance(text, str):
        raise Real3DError("description invalide")
    t = " ".join(_CTRL.sub(" ", text).split())[:limit]
    if len(t) < 2:
        raise Real3DError("description trop courte")
    return t


# ------------------------------------------------------------------ Poly Pizza
def poly_search(api_key: str, query: str, limit: int = 6) -> list[dict]:
    if not api_key:
        raise Real3DError("bibliothèque 3D non configurée (clé POLYPIZZA_API_KEY absente)")
    q = clean_query(query, 80)
    status, _, body = _request(POLY_API, "GET", f"/v1.1/search/{quote(q, safe='')}?Limit={limit}",
                               {"x-auth-token": api_key, "Accept": "application/json"})
    if status in (401, 403):
        raise Real3DError("clé Poly Pizza refusée")
    if status != 200:
        raise Real3DError(f"bibliothèque 3D indisponible ({status})")
    try:
        data = json.loads(body)
    except ValueError:
        raise Real3DError("réponse illisible de la bibliothèque 3D") from None
    items = (data.get("results") or data.get("Results") or []) if isinstance(data, dict) else []
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        g = lambda *ks: next((it[k] for k in ks if it.get(k) not in (None, "")), None)  # noqa: E731
        mid, url = str(g("ID", "Id", "id") or ""), str(g("Download", "download") or "")
        parts = urlsplit(url)
        if not _ID.match(mid) or parts.scheme != "https" or parts.hostname not in POLY_FILES or not url.endswith(".glb"):
            continue
        tris = g("Tri Count", "TriCount", "triCount")
        if isinstance(tris, (int, float)) and tris > 150_000:
            continue
        creator = g("Creator", "creator") or {}
        out.append({
            "id": mid, "title": str(g("Title", "title") or "Modèle 3D")[:80],
            "creator": str(creator.get("Username", "") if isinstance(creator, dict) else creator)[:60],
            "licence": str(g("Licence", "License", "licence") or "")[:40],
            "path": parts.path,
        })
    return out


def poly_glb(path: str) -> bytes:
    if not re.fullmatch(r"/[A-Za-z0-9_\-./]{1,160}\.glb", path) or ".." in path:
        raise Real3DError("modèle introuvable")
    status, _, body = _request(POLY_FILES[0], "GET", path, {"Accept": "*/*"}, limit=MAX_GLB)
    if status != 200:
        raise Real3DError(f"modèle indisponible ({status})")
    return check_glb(body)


# ------------------------------------------------------------------ TRELLIS.2 (Hugging Face)
def _gradio_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _upload(token: str, data: bytes, name: str, ctype: str) -> str:
    boundary = "syrius" + secrets.token_hex(10)
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{name}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    status, _, out = _request(TRELLIS, "POST", "/gradio_api/upload", {
        **_gradio_headers(token), "Content-Type": f"multipart/form-data; boundary={boundary}"}, body, timeout=60)
    try:
        paths = json.loads(out)
    except ValueError:
        paths = None
    if status != 200 or not isinstance(paths, list) or not paths or not isinstance(paths[0], str):
        raise Real3DError(f"envoi de l'image impossible ({status})")
    return paths[0]


_FN: dict = {}


def _fn_index(token: str, api: str) -> int:
    """Numéro de la fonction dans l'espace Gradio (lu une fois dans sa configuration publique)."""
    if not _FN:
        status, _, out = _request(TRELLIS, "GET", "/config", _gradio_headers(token), timeout=30)
        try:
            deps = json.loads(out).get("dependencies") or []
        except (ValueError, AttributeError):
            deps = []
        for i, d in enumerate(deps):
            if isinstance(d, dict) and isinstance(d.get("api_name"), str):
                _FN[d["api_name"]] = int(d.get("id", i)) if isinstance(d.get("id", i), int) else i
        if status != 200 or not _FN:
            raise Real3DError(f"service 3D indisponible ({status})")
    if api not in _FN:
        raise Real3DError(f"fonction 3D inconnue ({api})")
    return _FN[api]


def _call(token: str, session: str, api: str, data: list, timeout: float = 240):
    """Appelle une fonction de l'espace Gradio (file d'attente, protocole sse_v3) et renvoie son résultat."""
    body = {"data": data, "event_data": None, "fn_index": _fn_index(token, api), "trigger_id": None,
            "session_hash": session}
    status, _, out = _request(TRELLIS, "POST", "/gradio_api/queue/join", {
        **_gradio_headers(token), "Content-Type": "application/json"}, json.dumps(body).encode(), timeout=60)
    try:
        event = json.loads(out).get("event_id")
    except (ValueError, AttributeError):
        event = None
    if status != 200 or not event or not _ID.match(str(event)):
        raise Real3DError(f"service 3D indisponible ({api}, {status})")
    status, _, out = _request(TRELLIS, "GET", f"/gradio_api/queue/data?session_hash={session}",
                              {**_gradio_headers(token), "Accept": "text/event-stream"}, timeout=timeout,
                              limit=4_000_000)
    for line in out.decode("utf-8", "replace").splitlines():
        if not line.startswith("data:"):
            continue
        try:
            msg = json.loads(line[5:].strip())
        except ValueError:
            continue
        if not isinstance(msg, dict) or msg.get("event_id") not in (None, event):
            continue
        if msg.get("msg") != "process_completed":
            continue
        output = msg.get("output") or {}
        if msg.get("success") and isinstance(output, dict) and "data" in output:
            return output["data"]
        err = str(output.get("error") or msg.get("title") or "") if isinstance(output, dict) else ""
        if "quota" in err.lower():
            raise Real3DError("quota gratuit du jour atteint pour la création 3D (réessaie demain)")
        detail = re.sub(r"[^\w\s.,:;()'%/-]", " ", err)[:160].strip()
        raise Real3DError(f"la création 3D a échoué ({api}{' : ' + detail if detail else ''})")
    raise Real3DError(f"la création 3D n'a pas répondu à temps ({api}, {status})")


def _file_path(value) -> str:
    v = value[0] if isinstance(value, list) and value else value
    p = v.get("path") if isinstance(v, dict) else v
    if not isinstance(p, str) or not p.startswith("/tmp/") or ".." in p:
        raise Real3DError("réponse inattendue du service 3D")
    return p


def trellis_generate(token: str, prompt: str) -> bytes:
    """Description (anglais) → image → maquette 3D texturée (GLB)."""
    prompt = clean_query(prompt)
    _, image = imagegen.generate(prompt + ", single object, centered, full view, 3D render, plain white background, "
                                          "soft studio lighting, no text")
    session = secrets.token_hex(8)
    up = _upload(token, image, "objet.jpg", "image/jpeg")
    filedata = {"path": up, "meta": {"_type": "gradio.FileData"}}
    try:  # facultatif (prépare un dossier de session côté service)
        _call(token, session, "start_session", [], timeout=60)
    except Real3DError:
        pass
    pre = _call(token, session, "preprocess_image", [filedata], timeout=90)
    pre_path = _file_path(pre)
    _call(token, session, "image_to_3d", [{"path": pre_path, "meta": {"_type": "gradio.FileData"}}, 0, "512",
                                          7.5, 0.7, 12, 5.0, 7.5, 0.5, 12, 3.0, 1.0, 0.0, 12, 3.0], timeout=240)
    last = None
    for faces, tex in ((90_000, 1024), (40_000, 1024), (20_000, 512)):
        res = _call(token, session, "extract_glb", [faces, tex], timeout=120)
        glb_path = _file_path(res)
        status, _, body = _request(TRELLIS, "GET", "/gradio_api/file=" + quote(glb_path), _gradio_headers(token),
                                   timeout=90, limit=MAX_GLB)
        if status == 200 and len(body) <= MAX_GLB:
            return check_glb(body)
        last = status
        time.sleep(0.5)
    raise Real3DError(f"modèle 3D trop lourd ou indisponible ({last})")
