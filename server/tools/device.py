"""Actions sur le téléphone (exécutées par l'application Android, jamais par le serveur).

Le serveur vérifie et transmet seulement une demande d'action ; c'est l'application qui
l'exécute. Les actions sensibles (appel, SMS, ouverture d'un lien) demandent toujours
une confirmation à l'utilisateur dans l'app, et l'appel/SMS s'ouvre dans l'application
Téléphone/Messages où il faut encore appuyer sur « Appeler » / « Envoyer ».
"""
import re
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Paris")
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
REPEATS = ("none", "daily", "weekly")


def _tool(name, description, properties, required):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required}}}


SETTINGS_PAGES = ["wifi", "bluetooth", "donnees_mobiles", "affichage", "son", "batterie", "localisation",
                  "general"]

DEVICE_TOOLS = [
    _tool("phone_alarm", "Programme un réveil sur le téléphone de l'utilisateur.",
          {"hour": {"type": "integer", "description": "0 à 23"}, "minute": {"type": "integer", "description": "0 à 59"},
           "label": {"type": "string"}}, ["hour", "minute"]),
    _tool("phone_timer", "Lance un minuteur sur le téléphone.",
          {"seconds": {"type": "integer", "description": "Durée en secondes (1 à 86400)"}, "label": {"type": "string"}},
          ["seconds"]),
    _tool("phone_call", "Appelle quelqu'un : l'appel part dès que l'utilisateur confirme (bouton ou « oui » à la voix).",
          {"contact": {"type": "string", "description": "Nom du contact ou numéro de téléphone"}}, ["contact"]),
    _tool("phone_sms", "Prépare un SMS (l'utilisateur confirme puis appuie sur Envoyer dans Messages).",
          {"contact": {"type": "string", "description": "Nom du contact ou numéro"},
           "message": {"type": "string"}}, ["contact", "message"]),
    _tool("phone_open_app", "Ouvre une application installée sur le téléphone (ex. YouTube, Spotify, Appareil photo).",
          {"app": {"type": "string", "description": "Nom de l'application"}}, ["app"]),
    _tool("phone_map", "Ouvre une carte sur un lieu ou une adresse, avec itinéraire si demandé.",
          {"query": {"type": "string"}, "navigate": {"type": "boolean"}}, ["query"]),
    _tool("phone_open_url", "Ouvre un site web dans le navigateur (l'utilisateur confirme d'abord).",
          {"url": {"type": "string", "description": "Adresse complète en https://"}}, ["url"]),
    _tool("phone_flashlight", "Allume ou éteint la lampe torche.", {"on": {"type": "boolean"}}, ["on"]),
    _tool("phone_volume", "Règle le volume du média (musique, vidéos) en pourcentage.",
          {"level": {"type": "integer", "description": "0 à 100"}}, ["level"]),
    _tool("phone_settings", "Ouvre une page des réglages du téléphone.",
          {"page": {"type": "string", "enum": SETTINGS_PAGES}}, ["page"]),
    _tool("phone_reminder",
          "Programme un RAPPEL : une notification sur le téléphone à la date et l'heure voulues (ex. « rappelle-moi "
          "d'appeler maman demain à 18h »). Calcule toi-même la date à partir de la date du jour.",
          {"text": {"type": "string", "description": "Ce qu'il faut rappeler, court"},
           "when": {"type": "string", "description": "Date et heure locales au format AAAA-MM-JJTHH:MM"},
           "repeat": {"type": "string", "description": "none (une fois), daily (chaque jour) ou weekly"}},
          ["text", "when"]),
    _tool("phone_reminder_cancel", "Annule un rappel (identifiant donné par list_reminders).",
          {"id": {"type": "string"}}, ["id"]),
    _tool("phone_music",
          "Musique sur le téléphone : lancer un titre, un artiste, un album ou une playlist (action play + query), "
          "ou contrôler la lecture en cours (pause, resume, next, previous).",
          {"action": {"type": "string", "description": "play, pause, resume, next ou previous"},
           "query": {"type": "string", "description": "Ce qu'il faut jouer (pour play), ex. « Daft Punk Get Lucky »"},
           "app": {"type": "string", "description": "auto (par défaut), spotify, youtube_music, youtube ou deezer"}},
          ["action"]),
    _tool("phone_calendar",
          "Ajoute un RENDEZ-VOUS dans l'agenda du téléphone (l'utilisateur valide dans son agenda).",
          {"title": {"type": "string"}, "start": {"type": "string", "description": "AAAA-MM-JJTHH:MM (heure locale)"},
           "duration_min": {"type": "integer", "description": "Durée en minutes (60 par défaut)"},
           "location": {"type": "string"}}, ["title", "start"]),
]

DEVICE_LABELS = {
    "phone_alarm": "Je programme le réveil", "phone_timer": "Je lance le minuteur",
    "phone_call": "Je prépare l'appel", "phone_sms": "Je prépare le SMS",
    "phone_open_app": "J'ouvre l'application", "phone_map": "J'ouvre la carte",
    "phone_open_url": "J'ouvre le lien", "phone_flashlight": "Je m'occupe de la lampe",
    "phone_volume": "Je règle le volume", "phone_settings": "J'ouvre les réglages",
    "phone_reminder": "Je programme le rappel", "phone_reminder_cancel": "J'annule le rappel",
    "phone_calendar": "J'ajoute le rendez-vous", "phone_music": "Je m'occupe de la musique",
}

# Actions qui exigent un appui de l'utilisateur dans Syrius avant de s'exécuter.
NEEDS_CONFIRMATION = {"phone_call", "phone_sms", "phone_open_url"}

_PHONE = re.compile(r"^\+?[0-9 .()-]{3,20}$")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


class DeviceInputError(ValueError):
    pass


def parse_local(value, name: str, max_days: int = 366) -> datetime:
    """« AAAA-MM-JJTHH:MM » (heure de Paris) → date, obligatoirement dans le futur et dans l'année."""
    if not isinstance(value, str):
        raise DeviceInputError(f"{name} invalide")
    try:
        dt = datetime.fromisoformat(value.strip()[:16])
    except ValueError:
        raise DeviceInputError(f"{name} : format attendu AAAA-MM-JJTHH:MM") from None
    dt = dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)
    now = datetime.now(TZ)
    if dt <= now - timedelta(minutes=1):
        raise DeviceInputError(f"{name} est déjà passé (nous sommes le {now:%Y-%m-%d %H:%M})")
    if dt > now + timedelta(days=max_days):
        raise DeviceInputError(f"{name} trop lointain")
    return dt


def human(dt: datetime) -> str:
    return f"{JOURS[dt.weekday()]} {dt.day} {MOIS[dt.month - 1]} à {dt.hour:02d}h{dt.minute:02d}"


def _text(value, name, max_len, required=True):
    if not isinstance(value, str) or (required and not value.strip()):
        raise DeviceInputError(f"{name} invalide")
    value = _CTRL.sub(" ", value).strip()
    if len(value) > max_len:
        raise DeviceInputError(f"{name} trop long")
    return value


def _int(value, name, lo, hi):
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise DeviceInputError(f"{name} doit être un nombre entre {lo} et {hi}")
    return value


def build_action(name: str, args: dict) -> tuple[dict, str]:
    """Vérifie la demande et renvoie (action pour le téléphone, phrase de résultat pour l'IA)."""
    if not isinstance(args, dict):
        raise DeviceInputError("entrée invalide")
    allowed = {t["function"]["name"]: set(t["function"]["parameters"]["properties"]) for t in DEVICE_TOOLS}
    unknown = set(args) - allowed[name]
    if unknown:
        raise DeviceInputError(f"paramètre inconnu : {', '.join(sorted(unknown))}")

    if name == "phone_alarm":
        p = {"hour": _int(args.get("hour"), "hour", 0, 23), "minute": _int(args.get("minute"), "minute", 0, 59),
             "label": _text(args.get("label", "Syrius"), "label", 60, required=False) or "Syrius"}
        done = f"Réveil demandé pour {p['hour']:02d}h{p['minute']:02d}."
    elif name == "phone_timer":
        p = {"seconds": _int(args.get("seconds"), "seconds", 1, 86400),
             "label": _text(args.get("label", "Syrius"), "label", 60, required=False) or "Syrius"}
        done = f"Minuteur de {p['seconds']} secondes demandé."
    elif name in ("phone_call", "phone_sms"):
        contact = _text(args.get("contact"), "contact", 80)
        p = {"contact": contact, "is_number": bool(_PHONE.match(contact))}
        if name == "phone_sms":
            p["message"] = _text(args.get("message"), "message", 1000)
        done = ("Appel prêt : il part dès que l'utilisateur confirme (bouton « Confirmer » ou « oui » à la voix). "
                "Ne dis pas que l'appel est en cours." if name == "phone_call" else
                "SMS préparé : l'utilisateur doit confirmer dans l'app puis appuyer lui-même sur « Envoyer ». "
                "Ne dis pas qu'il est envoyé.")
    elif name == "phone_open_app":
        p = {"app": _text(args.get("app"), "app", 60)}
        done = f"Ouverture de « {p['app']} » demandée."
    elif name == "phone_map":
        p = {"query": _text(args.get("query"), "query", 200), "navigate": bool(args.get("navigate", False))}
        done = "Carte ouverte."
    elif name == "phone_open_url":
        url = _text(args.get("url"), "url", 500)
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise DeviceInputError("seules les adresses https:// sont autorisées")
        p = {"url": url, "host": parsed.hostname or ""}
        done = "Lien proposé : l'utilisateur doit confirmer avant l'ouverture."
    elif name == "phone_flashlight":
        if not isinstance(args.get("on"), bool):
            raise DeviceInputError("on doit être vrai/faux")
        p = {"on": args["on"]}
        done = "Lampe " + ("allumée." if p["on"] else "éteinte.")
    elif name == "phone_volume":
        p = {"level": _int(args.get("level"), "level", 0, 100)}
        done = f"Volume réglé à {p['level']} %."
    elif name == "phone_settings":
        page = args.get("page")
        if page not in SETTINGS_PAGES:
            raise DeviceInputError("page inconnue")
        p = {"page": page}
        done = "Réglages ouverts."
    elif name == "phone_reminder":
        dt = parse_local(args.get("when"), "when")
        repeat = args.get("repeat") or "none"
        if repeat not in REPEATS:
            repeat = "none"
        p = {"id": uuid.uuid4().hex[:10], "text": _text(args.get("text"), "text", 200),
             "at": int(dt.timestamp() * 1000), "repeat": repeat, "label": human(dt)}
        done = (f"Rappel programmé pour {p['label']}"
                + {"none": "", "daily": ", tous les jours", "weekly": ", toutes les semaines"}[repeat] + ".")
    elif name == "phone_reminder_cancel":
        rid = _text(args.get("id"), "id", 20)
        if not re.fullmatch(r"[0-9a-f]{6,20}", rid):
            raise DeviceInputError("identifiant de rappel invalide")
        p = {"id": rid}
        done = "Rappel annulé."
    elif name == "phone_music":
        action = args.get("action")
        if action not in ("play", "pause", "resume", "next", "previous"):
            raise DeviceInputError("action inconnue (play, pause, resume, next, previous)")
        app = args.get("app") or "auto"
        if app not in ("auto", "spotify", "youtube_music", "youtube", "deezer"):
            app = "auto"
        p = {"action": action, "app": app}
        if action == "play":
            p["query"] = _text(args.get("query"), "query", 120)
            done = f"Lecture de « {p['query']} » demandée" + ("" if app == "auto" else f" sur {app}") + "."
        else:
            done = {"pause": "Musique mise en pause.", "resume": "Lecture reprise.", "next": "Titre suivant.",
                    "previous": "Titre précédent."}[action]
    elif name == "phone_calendar":
        dt = parse_local(args.get("start"), "start", max_days=730)
        dur = args.get("duration_min", 60)
        dur = _int(dur, "duration_min", 5, 1440) if dur is not None else 60
        p = {"title": _text(args.get("title"), "title", 120), "start": int(dt.timestamp() * 1000),
             "end": int((dt + timedelta(minutes=dur)).timestamp() * 1000),
             "location": _text(args.get("location", ""), "location", 160, required=False), "label": human(dt)}
        done = f"Rendez-vous proposé dans l'agenda pour {p['label']} : l'utilisateur valide dans son agenda."
    else:
        raise DeviceInputError("action inconnue")
    event = {"type": "device", "action": name, "params": p, "confirm": name in NEEDS_CONFIRMATION}
    return event, done + " (Fonctionne uniquement dans l'application Android Syrius.)"
