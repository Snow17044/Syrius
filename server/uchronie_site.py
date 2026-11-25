"""Uchronie en site à part : le jeu seul, ouvert à tous, sans compte Syrius.

Même code que Syrius : un deuxième projet Vercel branché sur ce dépôt, avec la variable UCHRONIE_SEUL=1, sert ce
site-là au lieu de l'assistant. Les IA sont les IA gratuites du propriétaire (mêmes clés que Syrius), sans limite par
joueur par défaut (on peut en fixer une). Quand elles sont toutes épuisées pour la journée, le joueur peut coller SA
propre clé gratuite (Groq ou Gemini) : il joue alors sans limite sur son propre quota. Cette clé reste dans son
navigateur ; le serveur s'en sert pour la demande en cours et ne la garde jamais.

Rien n'est gardé sur le serveur à part ces compteurs : les parties restent dans le navigateur des joueurs.
Les adresses IP ne sont jamais enregistrées telles quelles (seulement une empreinte qui change chaque jour).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import uchronie
from .agent import sse
from .config import Config
from .llm import ChatClient, Provider, providers_from_config

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
STATIC = {
    "style.css": "text/css", "leaflet.js": "text/javascript", "leaflet.css": "text/css",
    "uchronie.js": "text/javascript", "uchronie.css": "text/css", "uchronie-monde.json": "application/json",
}
ICONS = {"icon.svg": "image/svg+xml", "icon-192.png": "image/png", "icon-512.png": "image/png"}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


KEY_HEADER = "x-uchronie-cle"
_GROQ_KEY = re.compile(r"^gsk_[A-Za-z0-9]{20,100}$")
_GEMINI_KEY = re.compile(r"^AIza[0-9A-Za-z_-]{30,60}$")


def own_llm(key: str) -> ChatClient | None:
    """IA payée par personne : la clé gratuite du joueur (jamais gardée, jamais écrite dans les journaux)."""
    key = (key or "").strip()
    if _GROQ_KEY.match(key):
        return ChatClient([
            Provider("groq", "Groq (ta clé)", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b", key),
            Provider("groq2", "Groq (ta clé)", "https://api.groq.com/openai/v1", "openai/gpt-oss-20b", key)])
    if _GEMINI_KEY.match(key):
        return ChatClient([Provider("gemini", "Gemini (ta clé)", "https://generativelanguage.googleapis.com/v1beta/openai",
                                    "gemini-flash-latest", key, vision=True)])
    return None


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

    def __init__(self, db=None, per_visitor: int = 0, per_day: int = 0):  # 0 = pas de limite
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

    @property
    def unlimited(self) -> bool:
        return not self.per_visitor and not self.per_day

    def _rest(self, data: dict, who: str) -> int | None:
        rests = ([self.per_visitor - data["v"].get(who, 0)] if self.per_visitor else []) + \
                ([self.per_day - data["all"]] if self.per_day else [])
        return max(0, min(rests)) if rests else None

    def left(self, ip: str) -> int | None:
        """Demandes restantes aujourd'hui (None = illimité)."""
        if self.unlimited:
            return None
        day = self.day()
        return self._rest(self._load(day), self.visitor(ip, day))

    def take(self, ip: str) -> int | None:
        """Compte une demande. Renvoie ce qui reste au visiteur (None = illimité), ou lève HTTPException 429."""
        if self.unlimited:
            return None
        with self.lock:
            day = self.day()
            data = self._load(day)
            who = self.visitor(ip, day)
            if self.per_day and data["all"] >= self.per_day:
                raise HTTPException(429, "Le site a atteint sa limite gratuite du jour. Ajoute ta propre clé gratuite "
                                         "pour continuer sans limite !")
            if self.per_visitor and data["v"].get(who, 0) >= self.per_visitor:
                raise HTTPException(429, "Tu as utilisé tes demandes du jour. Ajoute ta propre clé gratuite pour "
                                         "continuer sans limite !")
            data["v"][who] = data["v"].get(who, 0) + 1
            data["all"] += 1
            self._save(data)
            return self._rest(data, who)


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
    quota = Quota(db, _int_env("UCHRONIE_DEMANDES_PAR_JOUEUR", 0), _int_env("UCHRONIE_DEMANDES_PAR_JOUR", 0))
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
        return {"standalone": True, "left": quota.left(client_ip(request)), "per_visitor": quota.per_visitor,
                "own_key": True}

    def brain(request: Request):
        """(IA à utiliser, demandes restantes). La clé du joueur, si elle est là, passe avant tout : rien n'est compté."""
        raw = request.headers.get(KEY_HEADER, "")
        if raw:
            mine = own_llm(raw)
            if mine is None:
                raise HTTPException(400, "Cette clé ne ressemble pas à une clé Groq (gsk_…) ou Gemini (AIza…).")
            return mine, "own"
        return llm, quota.take(client_ip(request))

    def stream(events, what: str, left):
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
        ai, left = brain(request)
        return stream(uchronie.start_game(ai, body.year, " ".join(body.scenario.split())), "une création", left)

    @app.post("/api/uchronie/turn")
    async def turn(body: TurnBody, request: Request):
        state = checked(body.state)
        diplomacy = uchronie.clean_diplomacy(body.diplomacy, state)
        ai, left = brain(request)
        return stream(uchronie.play_turn(ai, state, body.actions.strip(), body.span, diplomacy), "un tour", left)

    @app.post("/api/uchronie/talk")
    async def talk(body: TalkBody, request: Request):
        state = checked(body.state)
        if body.nation not in state["nations"] or body.nation == state["player"]:
            raise HTTPException(400, "Nation inconnue.")
        try:
            messages = uchronie.clean_talk(body.messages)
        except uchronie.GameError as e:
            raise HTTPException(400, str(e)) from None
        ai, left = brain(request)
        return stream(uchronie.talk(ai, state, body.nation, messages), "la diplomatie", left)

    return app
