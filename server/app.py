"""Serveur web de Syrius (API + application téléphone)."""
import asyncio
import hmac
import html
import logging
import re
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from . import auth
from . import vision
from .agent import Agent, display_messages, sse
from .config import Config, config as default_config
from .db import Database
from .store_redis import RedisDatabase, RedisError, UpstashREST
from .tools import gmail, tiles
from .tools.places import round_location
from .tools.email_tool import EmailError, outlook_poll, outlook_start

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
STATIC_FILES = {
    "app.js": "text/javascript", "style.css": "text/css", "sw.js": "text/javascript",
    "manifest.webmanifest": "application/manifest+json", "markdown.js": "text/javascript",
    "leaflet.js": "text/javascript", "leaflet.css": "text/css", "hud.js": "text/javascript",
    "maplibre-gl.js": "text/javascript", "maplibre-gl-worker.js": "text/javascript",
    "maplibre-gl.css": "text/css", "diagram.js": "text/javascript",
    "three.min.js": "text/javascript", "model3d.js": "text/javascript", "templates3d.js": "text/javascript",
    "local.js": "text/javascript", "voice.js": "text/javascript",
}
ICON_FILES = {"icon.svg": "image/svg+xml", "icon-192.png": "image/png", "icon-512.png": "image/png"}

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; "
       "img-src 'self' data: blob:; "
       "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
       "frame-ancestors 'none'; form-action 'self'; manifest-src 'self'; worker-src 'self'")

MAX_MESSAGE_CHARS = 20000


class LoginBody(BaseModel):
    password: str = Field(max_length=256)


class MessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    location: dict | None = None  # position approximative envoyée par l'app (jamais enregistrée)
    voice: bool = False  # mode conversation : la réponse sera lue à voix haute
    image: str | None = Field(default=None, max_length=3_400_000)  # photo (data URL), jamais enregistrée


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    pinned: bool | None = None


class SetupBody(BaseModel):
    code: str = Field(max_length=256)
    password: str = Field(min_length=auth.MIN_PASSWORD_LEN, max_length=256)


class PasswordChange(BaseModel):
    current: str = Field(max_length=256)
    new: str = Field(min_length=auth.MIN_PASSWORD_LEN, max_length=256)


_UPSTASH_URL = re.compile(r"https://[A-Za-z0-9.-]+\.upstash\.io")
_UPSTASH_TOKEN = re.compile(r"UPSTASH_REDIS_REST_TOKEN\s*[=:]\s*[\"']?([A-Za-z0-9_=+/-]{20,})")
_TOKEN_ONLY = re.compile(r"[A-Za-z0-9_=+/-]{20,}")


def upstash_settings(url_value: str, token_value: str) -> tuple[str, str]:
    """Retrouve l'adresse et le jeton Upstash même s'ils ont été collés en vrac
    (valeurs inversées, sans https://, bloc .env entier, guillemets, retours à la ligne)."""
    both = f"{url_value}\n{token_value}"
    m = _UPSTASH_URL.search(both)
    if m:
        url = m.group(0)
    else:
        host = re.search(r"[A-Za-z0-9.-]+\.upstash\.io", both)
        url = "https://" + host.group(0) if host else url_value.strip()
    m = _UPSTASH_TOKEN.search(both)
    if m:
        token = m.group(1)
    else:
        # Le jeton est la valeur qui n'est pas l'adresse.
        candidates = [v for v in (token_value, url_value) if v and "upstash.io" not in v]
        found = _TOKEN_ONLY.search(candidates[0]) if candidates else None
        token = found.group(0) if found else ""
    return url, token


def open_database(cfg: Config):
    """Upstash Redis si configuré (obligatoire sur Vercel), sinon SQLite local."""
    log = logging.getLogger("syrius")
    if cfg.redis_url or cfg.redis_token:
        url, token = upstash_settings(cfg.redis_url, cfg.redis_token)
        if url.startswith("https://") and token:
            return RedisDatabase(UpstashREST(url, token))
        log.error("Base Upstash ignorée : adresse %s, jeton %s",
                  "trouvée" if url.startswith("https://") else "introuvable",
                  "trouvé" if token else "introuvable")
    if cfg.behind_vercel:
        log.warning("Upstash non configuré : les données seront PERDUES à chaque redémarrage (voir README).")
    return Database(cfg.db_path)


def create_app(cfg: Config | None = None, agent: Agent | None = None, db=None) -> FastAPI:
    cfg = cfg or default_config
    db = db or open_database(cfg)
    agent = agent or Agent(cfg, db)
    if agent.db is not db:
        agent.db = db
        agent.executor.db = db
        agent.executor.email.db = db

    app = FastAPI(title="Syrius", docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RedisError)
    async def database_error(request: Request, exc: RedisError):
        # Message clair pour l'utilisateur et le journal (jamais de secret dedans).
        logging.getLogger("syrius").error("ERREUR BASE : %s (sur %s)", exc, request.url.path)
        return JSONResponse({"detail": str(exc)}, status_code=503)
    app.state.db = db
    app.state.agent = agent
    app.state.cfg = cfg
    busy: set[str] = set()  # conversations en train de répondre

    # ------------------------------------------------------------------ sécurité
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        # Anti-CSRF : toute requête qui modifie quelque chose doit porter l'en-tête X-Syrius
        # (un site malveillant ne peut pas l'ajouter sans autorisation CORS, qu'on ne donne jamais).
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith("/api/"):
            if request.headers.get("x-syrius") != "1":
                return JSONResponse({"detail": "Requête refusée"}, status_code=403)
        response: Response = await call_next(request)
        h = response.headers
        if "content-security-policy" not in h:  # une page peut fixer une politique plus stricte
            h["Content-Security-Policy"] = CSP
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Permissions-Policy"] = "camera=(), geolocation=(self), microphone=(self)"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        if cfg.cookie_secure:
            h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/"):
            h["Cache-Control"] = "no-store"
        return response

    def client_ip(request: Request) -> str:
        if cfg.behind_vercel:  # Vercel indique la vraie adresse du visiteur dans cet en-tête
            real = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for", "")
            if real:
                return real.split(",")[0].strip()[:64]
        return request.client.host if request.client else "unknown"

    def require_auth(request: Request) -> None:
        if not auth.check_session(db, request.cookies.get(auth.COOKIE_NAME)):
            raise HTTPException(status_code=401, detail="Non connecté")

    # ------------------------------------------------------------------ pages
    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "index.html", media_type="text/html")

    @app.get("/static/{name}")
    async def static(name: str):
        if name not in STATIC_FILES:  # liste blanche : aucun accès à d'autres fichiers
            raise HTTPException(404)
        return FileResponse(WEB_DIR / name, media_type=STATIC_FILES[name])

    @app.get("/sw.js")
    async def service_worker():
        return FileResponse(WEB_DIR / "sw.js", media_type="text/javascript",
                            headers={"Service-Worker-Allowed": "/"})

    @app.get("/icons/{name}")
    async def icons(name: str):
        if name not in ICON_FILES:
            raise HTTPException(404)
        return FileResponse(WEB_DIR / "icons" / name, media_type=ICON_FILES[name])

    @app.get("/tiles/{z}/{x}/{y}.png", dependencies=[Depends(require_auth)])
    def tile(z: int, x: int, y: int):
        """Fond de carte relayé par le serveur (voir tools/tiles.py)."""
        try:
            png = tiles.fetch_tile(z, x, y)
        except tiles.TileError:
            raise HTTPException(404) from None
        return Response(png, media_type="image/png",
                        headers={"Cache-Control": "private, max-age=604800"})

    @app.get("/map3d/t/{z}/{x}/{y}.pbf", dependencies=[Depends(require_auth)])
    def tile_3d(z: int, x: int, y: int):
        """Carte 3D : données vectorielles relayées (voir tools/tiles.py)."""
        try:
            data = tiles.fetch_vector(z, x, y)
        except tiles.TileError:
            raise HTTPException(404) from None
        return Response(data, media_type="application/x-protobuf",
                        headers={"Cache-Control": "private, max-age=604800"})

    @app.get("/map3d/fonts/{fontstack}/{rng}.pbf", dependencies=[Depends(require_auth)])
    def glyphs_3d(fontstack: str, rng: str):
        try:
            data = tiles.fetch_glyphs(fontstack, rng)
        except tiles.TileError:
            raise HTTPException(404) from None
        return Response(data, media_type="application/x-protobuf",
                        headers={"Cache-Control": "private, max-age=2592000"})

    @app.get("/health")
    async def health():
        return {"ok": True, "stockage": "upstash" if isinstance(db, RedisDatabase) else "temporaire",
                "cerveaux": [b["name"] for b in agent.brains()]}

    # ------------------------------------------------------------------ connexion
    @app.get("/api/session")
    async def session(request: Request):
        password_set = auth.password_is_set(db)
        return {"authenticated": auth.check_session(db, request.cookies.get(auth.COOKIE_NAME)),
                "password_set": password_set, "setup_available": not password_set and bool(cfg.setup_code)}

    @app.post("/api/setup")
    async def setup(body: SetupBody, request: Request):
        """Premier lancement : choisir son mot de passe avec le code défini dans Vercel."""
        ip = client_ip(request)
        if auth.password_is_set(db) or not cfg.setup_code:
            raise HTTPException(403, "Configuration déjà faite.")
        if auth.is_locked_out(db, ip):
            raise HTTPException(429, "Trop d'essais. Réessaie dans 15 minutes.")
        if not hmac.compare_digest(body.code.encode(), cfg.setup_code.encode()):
            db.record_failed_login(ip)
            await asyncio.sleep(1)
            raise HTTPException(401, "Code de configuration incorrect.")
        await asyncio.to_thread(auth.set_password, db, body.password)
        return {"ok": True}

    @app.post("/api/login")
    async def login(body: LoginBody, request: Request):
        ip = client_ip(request)
        if auth.is_locked_out(db, ip):
            raise HTTPException(429, "Trop d'essais. Réessaie dans 15 minutes.")
        token = await asyncio.to_thread(auth.login, db, ip, body.password, cfg.session_days)
        if not token:
            await asyncio.sleep(1)  # ralentit les attaques par force brute
            raise HTTPException(401, "Mot de passe incorrect")
        resp = JSONResponse({"ok": True})
        resp.set_cookie(auth.COOKIE_NAME, token, max_age=cfg.session_days * 86400, httponly=True,
                        secure=cfg.cookie_secure, samesite="strict", path="/")
        return resp

    @app.post("/api/logout")
    async def logout(request: Request):
        auth.logout(db, request.cookies.get(auth.COOKIE_NAME))
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(auth.COOKIE_NAME, path="/")
        return resp

    @app.post("/api/password", dependencies=[Depends(require_auth)])
    async def change_password(body: PasswordChange, request: Request):
        stored = db.get_secret(auth.PASSWORD_KEY)
        if not stored or not await asyncio.to_thread(auth.verify_password, body.current, stored):
            raise HTTPException(403, "Mot de passe actuel incorrect")
        await asyncio.to_thread(auth.set_password, db, body.new)
        return {"ok": True, "detail": "Mot de passe changé. Reconnecte-toi."}

    # ------------------------------------------------------------------ discussions
    @app.get("/api/conversations", dependencies=[Depends(require_auth)])
    async def list_conversations(q: str = ""):
        return db.list_conversations(q[:100])

    @app.post("/api/conversations", dependencies=[Depends(require_auth)])
    async def create_conversation():
        return db.create_conversation()

    @app.get("/api/conversations/{cid}", dependencies=[Depends(require_auth)])
    async def get_conversation(cid: str):
        conv = db.get_conversation(cid)
        if not conv:
            raise HTTPException(404, "Discussion introuvable")
        return {**conv, "messages": display_messages(db.get_messages(cid))}

    @app.patch("/api/conversations/{cid}", dependencies=[Depends(require_auth)])
    async def patch_conversation(cid: str, body: ConversationPatch):
        if not db.get_conversation(cid):
            raise HTTPException(404)
        db.update_conversation(cid, title=body.title.strip() if body.title else None, pinned=body.pinned)
        return db.get_conversation(cid)

    @app.delete("/api/conversations/{cid}", dependencies=[Depends(require_auth)])
    async def delete_conversation(cid: str):
        if not db.delete_conversation(cid):
            raise HTTPException(404)
        return {"ok": True}

    @app.post("/api/conversations/{cid}/messages", dependencies=[Depends(require_auth)])
    async def send_message(cid: str, body: MessageBody):
        conv = db.get_conversation(cid)
        if not conv:
            raise HTTPException(404, "Discussion introuvable")
        if cid in busy:
            raise HTTPException(409, "Syrius répond déjà dans cette discussion.")
        image = None
        if body.image:  # photo : vérifiée (format, taille, contenu réel) avant toute utilisation
            try:
                image = vision.check_image(body.image)
            except vision.ImageError as e:
                raise HTTPException(400, str(e)) from None
        first = not db.get_messages(cid)
        busy.add(cid)

        async def stream():
            try:
                loc = round_location(body.location) if db.get_settings().get("location", True) else None
                async for event in agent.chat(cid, body.text, loc, voice=body.voice, image=image):
                    yield sse(event)
                if first and conv["title"] == "Nouvelle discussion" and db.get_messages(cid):
                    title = agent.make_title(body.text)
                    db.update_conversation(cid, title=title)
                    yield sse({"type": "title", "title": title})
            except Exception:
                logging.getLogger("syrius").exception("Erreur pendant la réponse")
                yield sse({"type": "error", "message": "Erreur interne."})
            finally:
                busy.discard(cid)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})

    # ------------------------------------------------------------------ actions confirmées
    @app.post("/api/actions/{aid}/confirm", dependencies=[Depends(require_auth)])
    async def confirm_action(aid: str):
        action = db.get_pending_action(aid)
        if not action:
            raise HTTPException(404)
        # Passage atomique pending -> sending : impossible d'envoyer deux fois.
        if not db.set_action_status(aid, "sending"):
            raise HTTPException(409, "Action déjà traitée.")
        if action["kind"] != "send_email":
            raise HTTPException(400)
        p = action["payload"]
        try:
            await asyncio.to_thread(agent.executor.email.send_email, p["to"], p["subject"], p["body"])
        except EmailError as e:
            db.set_action_status(aid, "failed", expected="sending")
            raise HTTPException(502, str(e)) from None
        except Exception:
            db.set_action_status(aid, "failed", expected="sending")
            raise HTTPException(502, "Envoi impossible.") from None
        db.set_action_status(aid, "done", expected="sending")
        return {"ok": True}

    @app.post("/api/actions/{aid}/cancel", dependencies=[Depends(require_auth)])
    async def cancel_action(aid: str):
        if not db.set_action_status(aid, "cancelled"):
            raise HTTPException(409, "Action déjà traitée.")
        return {"ok": True}

    # ------------------------------------------------------------------ réglages & mémoire
    @app.get("/api/settings", dependencies=[Depends(require_auth)])
    async def get_settings():
        return {**db.get_settings(), "email_enabled": cfg.email_enabled,
                "outlook": cfg.email_mode == "outlook" and bool(cfg.ms_client_id),
                "google": cfg.email_mode == "google",
                "google_connected": cfg.email_mode == "google" and gmail.is_connected(db),
                "web_search_available": True}

    # Connexion Outlook / Hotmail depuis l'app (code à entrer sur le site de Microsoft)
    # Connexion Gmail (OAuth Google). La page de Google s'ouvre dans le navigateur du téléphone ;
    # le retour est protégé par un « state » aléatoire, à usage unique, valable 15 minutes.
    def google_redirect_uri(request: Request) -> str:
        host = request.headers.get("host", "")
        scheme = "https" if (cfg.behind_vercel or cfg.cookie_secure) else request.url.scheme
        return f"{scheme}://{host}/api/email/google/callback"

    @app.post("/api/email/google/start", dependencies=[Depends(require_auth)])
    async def google_start(request: Request):
        try:
            return {"url": await asyncio.to_thread(gmail.start_url, cfg, db, google_redirect_uri(request))}
        except EmailError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/email/google/callback")
    async def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        if error:
            ok, text = False, "Connexion annulée."
        else:
            try:
                await asyncio.to_thread(gmail.finish, cfg, db, code[:1000], state[:200], google_redirect_uri(request))
                ok, text = True, "Gmail est connecté à Syrius."
            except EmailError as e:
                ok, text = False, str(e)
        page = ("<!doctype html><html lang=fr><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                "<title>Syrius</title><body style='background:#05080f;color:#e6f1ff;font:18px system-ui;"
                "display:grid;place-items:center;height:90vh;text-align:center'><div><p style='font-size:48px'>"
                + ("✅" if ok else "⚠️") + "</p><p>" + html.escape(text) +
                "</p><p>Tu peux fermer cette page et retourner dans l'application Syrius.</p></div></body></html>")
        resp = HTMLResponse(page, status_code=200 if ok else 400)
        resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
        return resp

    @app.post("/api/email/google/disconnect", dependencies=[Depends(require_auth)])
    async def google_disconnect():
        gmail.disconnect(db)
        return {"ok": True}

    @app.post("/api/email/outlook/start", dependencies=[Depends(require_auth)])
    async def outlook_login_start():
        try:
            return await asyncio.to_thread(outlook_start, cfg, db)
        except EmailError as e:
            raise HTTPException(400, str(e)) from None

    @app.post("/api/email/outlook/poll", dependencies=[Depends(require_auth)])
    async def outlook_login_poll():
        try:
            return {"status": await asyncio.to_thread(outlook_poll, cfg, db)}
        except EmailError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/brains", dependencies=[Depends(require_auth)])
    async def list_brains():
        return agent.brains()

    @app.put("/api/settings", dependencies=[Depends(require_auth)])
    async def put_settings(body: dict):
        brain = body.get("brain")
        if brain and brain not in {b["name"] for b in agent.brains()}:
            raise HTTPException(400, "Cerveau inconnu.")
        try:
            return db.update_settings(body)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/memories", dependencies=[Depends(require_auth)])
    async def list_memories():
        return db.list_memories()

    @app.delete("/api/memories/{mid}", dependencies=[Depends(require_auth)])
    async def delete_memory(mid: int):
        if not db.delete_memory(mid):
            raise HTTPException(404)
        return {"ok": True}

    return app


def main() -> FastAPI:
    """Point d'entrée : `uvicorn server.app:main --factory`."""
    logging.basicConfig(level=logging.INFO)
    return create_app()
