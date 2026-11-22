"""Uchronie en site à part : le jeu seul, ouvert à tous, sans compte Syrius.

Même code que Syrius : un deuxième projet Vercel branché sur ce dépôt, avec la variable UCHRONIE_SEUL=1, sert ce
site-là au lieu de l'assistant. Les IA sont les IA gratuites du propriétaire (mêmes clés que Syrius) ; pour que des
inconnus ne vident pas ses quotas, chaque visiteur a un nombre limité de demandes par jour, et le site entier aussi.

Rien n'est gardé sur le serveur à part ces compteurs : les parties restent dans le navigateur des joueurs.
Les adresses IP ne sont jamais enregistrées telles quelles (seulement une empreinte qui change chaque jour).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import uchronie
from .agent import sse
from .config import Config
from .llm import ChatClient, providers_from_config

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
STATIC = {
    "style.css": "text/css", "leaflet.js": "text/javascript", "leaflet.css": "text/css",
    "uchronie.js": "text/javascript", "uchronie.css": "text/css", "uchronie-monde.json": "application/json",
}
ICONS = {"icon.svg": "image/svg+xml", "icon-192.png": "image/png", "icon-512.png": "image/png"}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


class StartBody(BaseModel):
    year: int = Field(ge=uchronie.MIN_YEAR, le=uchronie.MAX_YEAR)
    scenario: str = Field(default="", max_length=300)


class TurnBody(BaseModel):
    state: dict
    actions: str = Field(default="", max_length=uchronie.MAX_ACTIONS)
    span: str = Field(default="mois", pattern=r"^(semaine|mois|trimestre|an)$")
    diplomacy: list[dict] = Field(default_factory=list, max_length=6)


class TalkBody(BaseModel):
    state: dict
    nation: str = Field(min_length=2, max_length=16)
    messages: list[dict] = Field(min_length=1, max_length=40)


class Quota:
    """Compteurs du jour : par visiteur et pour tout le site. Dans Upstash si configuré (partagé entre les
    serveurs de Vercel), sinon en mémoire."""

    def __init__(self, db=None, per_visitor: int = 40, per_day: int = 800):
        self.db, self.per_visitor, self.per_day = db, per_visitor, per_day
        self.mem: dict = {}
        self.lock = threading.Lock()

    @staticmethod
    def day() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load(self, day: str) -> dict:
        if self.db is None:
            return self.mem if self.mem.get("day") == day else {"day": day, "all": 0, "v": {}}
        try:
            data = json.loads(self.db.get_secret("uchronie_quota_v1") or "{}")
        except ValueError:
            data = {}
        return data if data.get("day") == day else {"day": day, "all": 0, "v": {}}

    def _save(self, data: dict) -> None:
        if self.db is None:
            self.mem = data
        else:
            self.db.set_secret("uchronie_quota_v1", json.dumps(data, separators=(",", ":")))

    def visitor(self, ip: str, day: str) -> str:
        return hashlib.sha256(f"{day}|{ip}".encode()).hexdigest()[:16]

    def left(self, ip: str) -> int:
        day = self.day()
        data = self._load(day)
        return max(0, min(self.per_visitor - data["v"].get(self.visitor(ip, day), 0), self.per_day - data["all"]))

    def take(self, ip: str) -> int:
        """Compte une demande. Renvoie ce qui reste au visiteur, ou lève HTTPException 429."""
        with self.lock:
            day = self.day()
            data = self._load(day)
            who = self.visitor(ip, day)
            if data["all"] >= self.per_day:
                raise HTTPException(429, "Le site a atteint sa limite gratuite du jour. Reviens demain !")
            if data["v"].get(who, 0) >= self.per_visitor:
                raise HTTPException(429, "Tu as utilisé toutes tes demandes du jour. Reviens demain !")
            data["v"][who] = data["v"].get(who, 0) + 1
            data["all"] += 1
            self._save(data)
            return min(self.per_visitor - data["v"][who], self.per_day - data["all"])


def client_ip(request: Request) -> str:
    # Sur Vercel, la vraie adresse du visiteur est la première de X-Forwarded-For (ajoutée par Vercel lui-même).
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return fwd or request.headers.get("x-real-ip", "") or (request.client.host if request.client else "inconnu")


def create_site(cfg: Config | None = None, llm=None, db=None) -> FastAPI:
    cfg = cfg or Config()
    if db is None and (cfg.redis_url or cfg.redis_token):
        from .app import open_database
        db = open_database(cfg)
    llm = llm or ChatClient(providers_from_config(cfg))
    quota = Quota(db, _int_env("UCHRONIE_DEMANDES_PAR_JOUEUR", 40), _int_env("UCHRONIE_DEMANDES_PAR_JOUR", 800))
    log = logging.getLogger("uchronie")
    app = FastAPI(title="Uchronie", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.quota = quota

    @app.middleware("http")
    async def headers(request: Request, call_next):
        if request.method not in ("GET", "HEAD") and request.url.path.startswith("/api/"):
            if request.headers.get("x-syrius") != "1":  # anti-CSRF, comme Syrius
                return JSONResponse({"detail": "Requête refusée"}, status_code=403)
        resp = await call_next(request)
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Strict-Transport-Security"] = "max-age=31536000"
        return resp

    @app.get("/")
    @app.get("/uchronie")
    async def page():
        return FileResponse(WEB_DIR / "uchronie.html", media_type="text/html")

    @app.get("/static/{name}")
    async def static(name: str):
        if name not in STATIC:
            raise HTTPException(404)
        return FileResponse(WEB_DIR / name, media_type=STATIC[name])

    @app.get("/icons/{name}")
    async def icons(name: str):
        if name not in ICONS:
            raise HTTPException(404)
        return FileResponse(WEB_DIR / "icons" / name, media_type=ICONS[name])

    @app.get("/api/uchronie/config")
    async def config(request: Request):
        return {"standalone": True, "left": quota.left(client_ip(request)), "per_visitor": quota.per_visitor}

    def stream(events, what: str, left: int):
        async def gen():
            yield sse({"type": "quota", "left": left})
            try:
                async for event in events:
                    yield sse(event)
            except Exception:
                log.exception("Erreur pendant %s", what)
                yield sse({"type": "error", "message": "Erreur interne."})
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})

    def checked(raw: dict) -> dict:
        try:
            state = uchronie.clean_state(raw)
        except uchronie.GameError as e:
            raise HTTPException(400, str(e)) from None
        if not state["player"]:
            raise HTTPException(400, "Choisis d'abord ta nation.")
        return state

    @app.post("/api/uchronie/start")
    async def start(body: StartBody, request: Request):
        left = quota.take(client_ip(request))
        return stream(uchronie.start_game(llm, body.year, " ".join(body.scenario.split())), "une création", left)

    @app.post("/api/uchronie/turn")
    async def turn(body: TurnBody, request: Request):
        state = checked(body.state)
        diplomacy = uchronie.clean_diplomacy(body.diplomacy, state)
        left = quota.take(client_ip(request))
        return stream(uchronie.play_turn(llm, state, body.actions.strip(), body.span, diplomacy), "un tour", left)

    @app.post("/api/uchronie/talk")
    async def talk(body: TalkBody, request: Request):
        state = checked(body.state)
        if body.nation not in state["nations"] or body.nation == state["player"]:
            raise HTTPException(400, "Nation inconnue.")
        try:
            messages = uchronie.clean_talk(body.messages)
        except uchronie.GameError as e:
            raise HTTPException(400, str(e)) from None
        left = quota.take(client_ip(request))
        return stream(uchronie.talk(llm, state, body.nation, messages), "la diplomatie", left)

    return app
