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

from . import auth, diagnostic, family, safety
from . import transcribe, vision
from .agent import Agent, display_messages, sse
from .config import Config, config as default_config
from .db import Database
from .store_redis import RedisDatabase, RedisError, UpstashREST
from .tools import gmail, imagegen, real3d, tiles
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
    "local.js": "text/javascript", "voice.js": "text/javascript", "icons.js": "text/javascript", "gltf-loader.js": "text/javascript",
    "legal.css": "text/css",
}
ICON_FILES = {"icon.svg": "image/svg+xml", "icon-192.png": "image/png", "icon-512.png": "image/png"}

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; "
       "img-src 'self' data: blob:; "
       "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
       "frame-ancestors 'none'; form-action 'self'; manifest-src 'self'; worker-src 'self'")

MAX_MESSAGE_CHARS = 20000
# Empreintes (publiques) des clés qui signent l'application Android : clé de la CI et clé Google Play.
ANDROID_CERTS: list[str] = [
    "E4:30:06:4D:B0:68:BA:81:FB:B5:B3:61:F8:61:87:8F:9A:B8:7F:DD:D4:FD:C2:78:14:D7:82:95:2B:60:24:CD",  # clé Syrius
]


class LoginBody(BaseModel):
    password: str = Field(max_length=256)
    name: str = Field(default="", max_length=40)  # vide = propriétaire ; prénom = membre de la famille


class TestLinkBody(BaseModel):
    link: str = Field(min_length=10, max_length=80)


class JoinBody(BaseModel):
    code: str = Field(min_length=4, max_length=40)
    name: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=auth.MIN_PASSWORD_LEN, max_length=256)


class MessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    location: dict | None = None  # position approximative envoyée par l'app (jamais enregistrée)
    voice: bool = False  # mode conversation : la réponse sera lue à voix haute
    image: str | None = Field(default=None, max_length=3_400_000)  # photo (data URL), jamais enregistrée


class ImageBody(BaseModel):
    prompt: str = Field(min_length=3, max_length=600)


class Model3DSearch(BaseModel):
    query: str = Field(min_length=2, max_length=80)


class Model3DCreate(BaseModel):
    prompt: str = Field(min_length=3, max_length=300)
    key: str = Field(default="", max_length=80)  # mots-clés de l'objet : maquette déjà créée réutilisée


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    pinned: bool | None = None


class SetupBody(BaseModel):
    code: str = Field(max_length=256)
    password: str = Field(min_length=auth.MIN_PASSWORD_LEN, max_length=256)


class AccountDelete(BaseModel):
    password: str = Field(default="", max_length=256)


class ReportBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    reason: str = Field(default="", max_length=300)


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
    if not isinstance(db, family.ScopedDB):  # chaque membre de la famille a son espace privé
        db = family.ScopedDB(db, family.space_factory(db, cfg.data_dir))
    imagegen.configure(cfg)  # services d'images (clés facultatives)
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

    async def require_auth(request: Request) -> None:
        uid = auth.session_user(db, request.cookies.get(auth.COOKIE_NAME))
        if uid is None:
            raise HTTPException(status_code=401, detail="Non connecté")
        family.CURRENT.set(uid)  # toutes les données de la requête vont dans l'espace de cette personne
        family.GUEST.set(family.is_guest(db.base, uid))
        request.state.uid = uid

    def require_owner(request: Request) -> None:
        if getattr(request.state, "uid", None) != family.OWNER:
            raise HTTPException(403, "Réservé au propriétaire de Syrius.")

    def set_session_cookie(resp, token: str, max_age: int | None = None) -> None:
        resp.set_cookie(auth.COOKIE_NAME, token, max_age=max_age or cfg.session_days * 86400, httponly=True,
                        secure=cfg.cookie_secure, samesite="strict", path="/")

    # ------------------------------------------------------------------ pages
    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "index.html", media_type="text/html")

    @app.get("/confidentialite")
    async def privacy():
        """Politique de confidentialité (exigée par Google Play) et marche à suivre pour supprimer son compte."""
        page = (WEB_DIR / "confidentialite.html").read_text(encoding="utf-8")
        contact = (f"Pour toute question : {html.escape(cfg.contact_email)}" if cfg.contact_email
                   else "Pour toute question, adressez-vous à la personne qui vous a invité sur ce Syrius.")
        return HTMLResponse(page.replace("{{CONTACT}}", contact))

    @app.get("/rejoindre/{code}")
    @app.get("/essai/{link}")
    async def shared_link():
        """Liens d'invitation : ouvrent l'application Android si elle est installée, sinon le site."""
        return FileResponse(WEB_DIR / "index.html", media_type="text/html")

    @app.get("/.well-known/assetlinks.json")
    async def asset_links():
        """Prouve à Android que les liens de ce site appartiennent à l'application Syrius (App Links)."""
        certs = [c.strip().upper() for c in (ANDROID_CERTS + cfg.android_certs) if c.strip()]
        certs = [c for c in dict.fromkeys(certs) if re.fullmatch(r"([0-9A-F]{2}:){31}[0-9A-F]{2}", c)]
        return JSONResponse([{"relation": ["delegate_permission/common.handle_all_urls"],
                              "target": {"namespace": "android_app", "package_name": "fr.syrius.app",
                                         "sha256_cert_fingerprints": certs}}],
                            headers={"Cache-Control": "public, max-age=3600"})

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

    @app.post("/api/transcribe", dependencies=[Depends(require_auth)])
    async def transcribe_voice(request: Request):
        """Voix → texte (Whisper via Groq). Le son n'est jamais enregistré."""
        try:
            if int(request.headers.get("content-length", "0")) > transcribe.MAX_BYTES:
                raise HTTPException(413, "enregistrement trop long")
        except ValueError:
            raise HTTPException(400, "taille invalide") from None
        data = await request.body()
        try:
            text = await asyncio.to_thread(transcribe.transcribe, cfg.groq_api_key, data)
        except transcribe.TranscribeError as e:
            raise HTTPException(502 if "service" in str(e) else 400, str(e)) from None
        return {"text": text}

    # ------------------------------------------------------------------ vraies maquettes 3D (GLB)
    GLB_TYPE = "model/gltf-binary"

    @app.post("/api/model3d/search", dependencies=[Depends(require_auth)])
    async def model3d_search(body: Model3DSearch):
        """Cherche de vrais modèles 3D dans la bibliothèque Poly Pizza (artistes, licences CC0 / CC-BY)."""
        if safety.blocked(body.query):
            raise HTTPException(400, safety.MESSAGE.split(" Propose")[0])
        try:
            results = await asyncio.to_thread(real3d.poly_search, cfg.polypizza_api_key, body.query)
        except real3d.Real3DError as e:
            raise HTTPException(502, str(e)) from None
        return {"results": results}

    @app.get("/api/model3d/poly", dependencies=[Depends(require_auth)])
    async def model3d_poly(path: str):
        try:
            data = await asyncio.to_thread(real3d.poly_glb, path)
        except real3d.Real3DError as e:
            raise HTTPException(502, str(e)) from None
        return Response(data, media_type=GLB_TYPE, headers={"Cache-Control": "private, max-age=86400"})

    @app.post("/api/model3d/generate", dependencies=[Depends(require_auth)])
    async def model3d_generate(body: Model3DCreate, request: Request):
        """Crée une maquette texturée sur mesure (image → TRELLIS.2). Environ 1 à 2 minutes.
        Une maquette déjà créée (même objet) est réutilisée sans compter dans les quotas."""
        if safety.blocked(body.prompt, body.key):
            raise HTTPException(400, safety.MESSAGE.split(" Propose")[0])
        key = body.key.strip() or body.prompt
        cached = await asyncio.to_thread(family.cache_get, db.base, key)
        if cached:
            return Response(cached, media_type=GLB_TYPE, headers={"Cache-Control": "no-store", "X-Syrius-Cache": "1"})
        if not cfg.hf_token:
            raise HTTPException(503, "création 3D non configurée (clé HF_TOKEN absente)")
        uid = request.state.uid
        if family.quota_left(db.base, "m3d", uid) <= 0:
            raise HTTPException(429, "ta part de créations 3D du jour est utilisée (réessaie demain)")
        try:
            data = await asyncio.to_thread(real3d.trellis_generate, cfg.hf_token, body.prompt)
        except (real3d.Real3DError, imagegen.ImageGenError) as e:
            raise HTTPException(502, str(e)) from None
        family.quota_use(db.base, "m3d", uid)
        await asyncio.to_thread(family.cache_put, db.base, key, data)
        return Response(data, media_type=GLB_TYPE, headers={"Cache-Control": "no-store"})

    @app.post("/api/diagnostic", dependencies=[Depends(require_auth), Depends(require_owner)])
    def run_diagnostic():
        """Teste en direct les services d'images, de photos et de 3D (propriétaire uniquement)."""
        return {"checks": diagnostic.run(cfg, agent.llm.providers)}

    @app.post("/api/image", dependencies=[Depends(require_auth)])
    def create_image(body: ImageBody):
        """Image créée en ligne (gratuit, sans clé), relayée par le serveur (voir tools/imagegen.py)."""
        try:
            ctype, data = imagegen.generate(body.prompt)
        except imagegen.ImageGenError as e:
            raise HTTPException(502, str(e)) from None
        return Response(data, media_type=ctype, headers={"Cache-Control": "no-store"})

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
        uid = auth.session_user(db, request.cookies.get(auth.COOKIE_NAME))
        return {"authenticated": uid is not None, "owner": uid == family.OWNER,
                "member_name": family.member_name(db.base, uid) if uid else "",
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
        token = await asyncio.to_thread(auth.login, db, ip, body.password, cfg.session_days, body.name)
        if not token:
            await asyncio.sleep(1)  # ralentit les attaques par force brute
            raise HTTPException(401, "Prénom ou mot de passe incorrect" if body.name.strip() else "Mot de passe incorrect")
        resp = JSONResponse({"ok": True})
        set_session_cookie(resp, token)
        return resp

    # ------------------------------------------------------------------ famille
    @app.post("/api/family/join")
    async def family_join(body: JoinBody, request: Request):
        """Un proche crée son compte avec le code d'invitation (le propriétaire n'a rien à faire)."""
        ip = client_ip(request)
        if auth.is_locked_out(db, ip):
            raise HTTPException(429, "Trop d'essais. Réessaie dans 15 minutes.")
        try:
            family.purge_expired(db.base, db.wipe)
            uid = await asyncio.to_thread(family.join, db.base, body.code, body.name, body.password)
        except family.FamilyError as e:
            if "invitation" in str(e):
                db.record_failed_login(ip)
                await asyncio.sleep(1)
            raise HTTPException(400, str(e)) from None
        resp = JSONResponse({"ok": True})
        set_session_cookie(resp, auth.new_session(db, uid, cfg.session_days))
        return resp

    @app.post("/api/family/test")
    async def family_test_claim(body: TestLinkBody, request: Request):
        """Lien de test : accès temporaire (24 h à partir de la création du lien), sans mot de passe."""
        ip = client_ip(request)
        if auth.is_locked_out(db, ip):
            raise HTTPException(429, "Trop d'essais. Réessaie dans 15 minutes.")
        found = family.claim_test(db.base, body.link)
        if not found:
            db.record_failed_login(ip)
            await asyncio.sleep(1)
            raise HTTPException(400, "Ce lien de test n'est plus valable (24 h dépassées ou lien retiré).")
        uid, left = found
        resp = JSONResponse({"ok": True})
        set_session_cookie(resp, auth.new_session(db, uid, left / 86400), max_age=max(60, int(left)))
        return resp

    @app.get("/api/family", dependencies=[Depends(require_auth), Depends(require_owner)])
    async def family_info():
        family.purge_expired(db.base, db.wipe)
        return {"code": family.invite_code(db.base) or None, "members": family.members(db.base),
                "max": family.MAX_MEMBERS, "full": family.is_full(db.base)}

    @app.post("/api/family/code", dependencies=[Depends(require_auth), Depends(require_owner)])
    async def family_new_code():
        try:
            return {"code": family.invite_code(db.base, renew=True)}
        except family.FamilyError as e:
            raise HTTPException(409, str(e)) from None

    @app.post("/api/family/test-link", dependencies=[Depends(require_auth), Depends(require_owner)])
    async def family_new_test():
        family.purge_expired(db.base, db.wipe)
        try:
            return {"link": family.create_test(db.base), "hours": family.TEST_SECONDS // 3600}
        except family.FamilyError as e:
            raise HTTPException(409, str(e)) from None

    @app.delete("/api/family/{uid}", dependencies=[Depends(require_auth), Depends(require_owner)])
    async def family_remove(uid: str):
        if not family.remove_member(db.base, uid[:20]):
            raise HTTPException(404, "Compte introuvable")
        db.wipe(uid[:20])  # ses discussions, sa mémoire et ses réglages sont effacés
        return {"ok": True}

    @app.post("/api/account/delete", dependencies=[Depends(require_auth)])
    async def delete_account(body: AccountDelete, request: Request):
        """Suppression du compte et de toutes ses données (exigence Google Play)."""
        uid, ip = request.state.uid, client_ip(request)
        if auth.is_locked_out(db, ip):
            raise HTTPException(429, "Trop d'essais. Réessaie dans 15 minutes.")
        if uid:
            ok = await asyncio.to_thread(family.check_member_password, db.base, uid, body.password)
        else:
            ok = await asyncio.to_thread(auth.verify_password, body.password, db.base.get_secret(auth.PASSWORD_KEY) or "")
        if not ok:
            db.record_failed_login(ip)
            await asyncio.sleep(1)
            raise HTTPException(403, "Mot de passe incorrect")
        if uid:  # membre ou test : compte et espace privé effacés
            family.remove_member(db.base, uid)
            db.wipe(uid)
            auth.logout(db, request.cookies.get(auth.COOKIE_NAME))
            resp = JSONResponse({"ok": True, "deleted": "account"})
            resp.delete_cookie(auth.COOKIE_NAME, path="/")
            return resp
        # Propriétaire : ses discussions, souvenirs et rappels sont effacés (le serveur reste à lui).
        for c in db.list_conversations():
            db.delete_conversation(c["id"])
        for m in db.list_memories():
            db.delete_memory(m["id"])
        return {"ok": True, "deleted": "data"}

    @app.post("/api/report", dependencies=[Depends(require_auth)])
    async def report_content(body: ReportBody, request: Request):
        """Signaler une réponse ou une image de l'IA (exigence Google Play sur l'IA générative)."""
        uid = request.state.uid
        who = family.member_name(db.base, uid) if uid else "propriétaire"
        family.add_report(db.base, who, body.text, body.reason)
        return {"ok": True}

    @app.get("/api/reports", dependencies=[Depends(require_auth), Depends(require_owner)])
    async def list_reports():
        return family.reports(db.base)

    @app.delete("/api/reports", dependencies=[Depends(require_auth), Depends(require_owner)])
    async def clear_reports():
        family.clear_reports(db.base)
        return {"ok": True}

    @app.post("/api/logout")
    async def logout(request: Request):
        auth.logout(db, request.cookies.get(auth.COOKIE_NAME))
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(auth.COOKIE_NAME, path="/")
        return resp

    @app.post("/api/password", dependencies=[Depends(require_auth)])
    async def change_password(body: PasswordChange, request: Request):
        if request.state.uid:  # membre de la famille : son propre mot de passe
            try:
                await asyncio.to_thread(family.set_member_password, db.base, request.state.uid, body.current, body.new)
            except family.FamilyError as e:
                raise HTTPException(403, str(e)) from None
            return {"ok": True, "detail": "Mot de passe changé."}
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
        if action["kind"] != "send_email" or not family.email_allowed(cfg):
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
    async def get_settings(request: Request):
        uid = request.state.uid
        return {**db.get_settings(), "email_enabled": family.email_allowed(cfg),
                "account": family.account(db.base, uid),
                "outlook": cfg.email_mode == "outlook" and bool(cfg.ms_client_id) and uid == family.OWNER,
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
        if family.GUEST.get():
            raise HTTPException(403, "Les comptes de test n'ont pas accès aux emails.")
        try:
            prefix = request.state.uid + "." if request.state.uid else ""
            return {"url": await asyncio.to_thread(gmail.start_url, cfg, db, google_redirect_uri(request), prefix)}
        except EmailError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/email/google/callback")
    async def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
        if error:
            ok, text = False, "Connexion annulée."
        else:
            try:
                uid = state.split(".", 1)[0] if "." in state else ""
                if not family.member_exists(db.base, uid):
                    raise EmailError("Compte introuvable.")
                family.CURRENT.set(uid)  # retour de Google : on revient dans l'espace de la bonne personne
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

    @app.post("/api/email/outlook/start", dependencies=[Depends(require_auth), Depends(require_owner)])
    async def outlook_login_start():
        try:
            return await asyncio.to_thread(outlook_start, cfg, db)
        except EmailError as e:
            raise HTTPException(400, str(e)) from None

    @app.post("/api/email/outlook/poll", dependencies=[Depends(require_auth), Depends(require_owner)])
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
