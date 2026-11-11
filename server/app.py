"""Serveur web de Syrius (API + application téléphone)."""
import asyncio
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from . import auth
from .agent import Agent, display_messages, sse
from .config import Config, config as default_config
from .db import Database
from .tools.email_tool import EmailError

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
STATIC_FILES = {
    "app.js": "text/javascript", "style.css": "text/css", "sw.js": "text/javascript",
    "manifest.webmanifest": "application/manifest+json", "markdown.js": "text/javascript",
}
ICON_FILES = {"icon.svg": "image/svg+xml", "icon-192.png": "image/png", "icon-512.png": "image/png"}

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
       "frame-ancestors 'none'; form-action 'self'; manifest-src 'self'; worker-src 'self'")

MAX_MESSAGE_CHARS = 20000


class LoginBody(BaseModel):
    password: str = Field(max_length=256)


class MessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    pinned: bool | None = None


class PasswordChange(BaseModel):
    current: str = Field(max_length=256)
    new: str = Field(min_length=auth.MIN_PASSWORD_LEN, max_length=256)


def create_app(cfg: Config | None = None, agent: Agent | None = None) -> FastAPI:
    cfg = cfg or default_config
    db = Database(cfg.db_path)
    agent = agent or Agent(cfg, db)
    if agent.db is not db:
        agent.db = db
        agent.executor.db = db
        agent.executor.email.db = db

    app = FastAPI(title="Syrius", docs_url=None, redoc_url=None, openapi_url=None)
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
        h["Content-Security-Policy"] = CSP
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        if cfg.cookie_secure:
            h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/"):
            h["Cache-Control"] = "no-store"
        return response

    def client_ip(request: Request) -> str:
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

    @app.get("/health")
    async def health():
        return {"ok": True}

    # ------------------------------------------------------------------ connexion
    @app.get("/api/session")
    async def session(request: Request):
        return {"authenticated": auth.check_session(db, request.cookies.get(auth.COOKIE_NAME)),
                "password_set": auth.password_is_set(db)}

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
        first = not db.get_messages(cid)
        busy.add(cid)

        async def stream():
            try:
                async for event in agent.chat(cid, body.text):
                    yield sse(event)
                if first and conv["title"] == "Nouvelle discussion":
                    title = await agent.make_title(body.text)
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
                "web_search_available": bool(cfg.web_search_key), "default_model": cfg.model}

    @app.get("/api/models", dependencies=[Depends(require_auth)])
    async def list_models():
        return {"installed": await agent.list_models(), "default": cfg.model}

    @app.put("/api/settings", dependencies=[Depends(require_auth)])
    async def put_settings(body: dict):
        model = body.get("model")
        if model:  # seul un modèle réellement installé peut être choisi
            if not isinstance(model, str) or model not in await agent.list_models():
                raise HTTPException(400, "Modèle non installé sur le serveur.")
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
