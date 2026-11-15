"""Syrius fabrique lui-même ses exemples d'entraînement (chaque nuit, avant de s'entraîner).

Une grande IA gratuite (celles que Syrius utilise déjà) écrit de nouvelles petites conversations sur un
thème. Chaque exemple est VÉRIFIÉ avant d'être gardé :
- format exact des actions <tool_call> (mêmes contrôles que le serveur : schémas, maquettes, téléphone) ;
- interdits (contenu sexuel ou violent) ;
- longueur raisonnable, français, pas de doublon.
Les meilleurs sont stockés (les plus récents d'abord, 800 au plus) et appris à l'entraînement suivant.
"""
from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request

from . import safety
from .tools import diagram, model3d
from .tools.device import DeviceInputError, build_action

KEY = "family_training_auto_v1"
MAX_AUTO = 800
TOOLS = ("show_diagram", "show_model", "phone_image", "phone_reminder", "phone_alarm", "phone_timer", "phone_call",
         "phone_sms", "phone_music", "phone_map", "phone_open_app", "phone_flashlight", "phone_volume",
         "phone_calendar", "remember")
THEMES = [
    ("cuisine et recettes simples (quantités justes)", None),
    ("culture générale : sciences, histoire, géographie (faits exacts et vérifiables)", None),
    ("conseils du quotidien : maison, budget, santé générale (avec prudence), organisation", None),
    ("écriture : petits poèmes, messages d'anniversaire, reformulations, traductions courtes", None),
    ("discussion amicale, humour fin, encouragements", None),
    ("demandes d'IMAGES (l'assistant appelle phone_image avec un prompt anglais détaillé)", "phone_image"),
    ("demandes de MAQUETTES 3D d'objets variés (show_model : title, search_en, prompt_en, description, facts)",
     "show_model"),
    ("demandes de SCHÉMAS / plans d'action (show_diagram : title, style carte|etapes|arbre, nodes avec id, label, "
     "parent, kind objectif|phase|etape|action|outil|budget|delai|risque, note)", "show_diagram"),
    ("rappels, réveils et minuteurs (phone_reminder avec when AAAA-MM-JJTHH:MM dans le futur, phone_alarm, "
     "phone_timer en secondes)", "phone_reminder"),
    ("musique, appels, SMS, carte, applications, lampe, volume (phone_music, phone_call, phone_sms, phone_map, "
     "phone_open_app, phone_flashlight, phone_volume)", "phone_music"),
    ("demandes interdites (contenu sexuel ou violent) : l'assistant refuse poliment et propose autre chose", None),
]
_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


def stored(base) -> list[dict]:
    try:
        data = json.loads(base.get_secret(KEY) or "[]")
    except ValueError:
        return []
    return [d for d in data if isinstance(d, dict) and d.get("q") and d.get("a")] if isinstance(data, list) else []


def _norm(q: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", q.lower()).split())


def add(base, items: list[dict]) -> int:
    data = stored(base)
    seen = {_norm(d["q"]) for d in data}
    added = 0
    for it in items:
        k = _norm(it["q"])
        if k and k not in seen:
            seen.add(k)
            data.append({"q": it["q"], "a": it["a"], "at": int(time.time())})
            added += 1
    base.set_secret(KEY, json.dumps(data[-MAX_AUTO:], ensure_ascii=False))
    return added


def delete(base, index_from_end: int) -> bool:
    data = stored(base)
    i = len(data) - 1 - index_from_end
    if not 0 <= i < len(data):
        return False
    del data[i]
    base.set_secret(KEY, json.dumps(data, ensure_ascii=False))
    return True


_NODE_KEYS = {"id", "label", "parent", "note", "kind"}
_DIAGRAM_KEYS = {"title", "style", "nodes", "links"}
_MODEL_KEYS = {"title", "search_en", "prompt_en", "template", "description", "facts", "parts"}


def _device_keys(name: str) -> set:
    from .tools.device import DEVICE_TOOLS
    for t in DEVICE_TOOLS:
        if t["function"]["name"] == name:
            return set(t["function"]["parameters"]["properties"])
    return set()


def _clean_args(name: str, args: dict) -> dict:
    """Retire les champs inventés (fréquents chez les IA) au lieu de jeter tout l'exemple."""
    if name == "show_diagram":
        out = {k: v for k, v in args.items() if k in _DIAGRAM_KEYS}
        if isinstance(out.get("nodes"), list):
            out["nodes"] = [{k: v for k, v in n.items() if k in _NODE_KEYS} for n in out["nodes"] if isinstance(n, dict)]
        if out.get("style") not in ("carte", "etapes", "arbre"):
            out.pop("style", None)
        return out
    if name == "show_model":
        return {k: v for k, v in args.items() if k in _MODEL_KEYS}
    if name == "remember":
        return {"fact": args.get("fact")}
    keys = _device_keys(name)
    return {k: v for k, v in args.items() if k in keys} if keys else args


def review(q: str, a: str) -> tuple[str | None, str]:
    """Renvoie (réponse nettoyée ou None, raison du refus). Les actions passent les contrôles du serveur."""
    if not 3 <= len(q) <= 400:
        return None, "question trop courte ou trop longue"
    if not 2 <= len(a) <= 2500:
        return None, "réponse trop courte ou trop longue"
    calls = _CALL.findall(a)
    if a.count("<tool_call>") != len(calls) or len(calls) > 1:
        return None, "action mal écrite"
    refusal = any(w in a.lower() for w in ("je ne crée pas", "je ne fais pas", "je préfère ne pas", "interdit",
                                            "je ne peux pas"))
    if safety.blocked(q) and not (refusal and not calls):
        return None, "demande interdite sans refus"  # seul un refus poli, sans action, est accepté
    if safety.blocked(a) and not refusal:
        return None, "contenu interdit"
    for raw in calls:
        try:
            c = json.loads(raw)
        except ValueError:
            return None, "action illisible"
        name, args = c.get("name"), c.get("arguments")
        if name not in TOOLS or not isinstance(args, dict):
            return None, "outil inconnu"
        args = _clean_args(name, args)
        try:
            if name == "show_diagram":
                diagram.validate(args)
            elif name == "show_model":
                model3d.validate(args)
            elif name == "remember":
                if not isinstance(args.get("fact"), str) or not args["fact"].strip():
                    return None, "souvenir vide"
            elif name not in ("phone_reminder", "phone_calendar"):  # dates : vérifiées sur l'appareil
                build_action(name, args)
        except (ValueError, TypeError, DeviceInputError, diagram.DiagramError, model3d.ModelError) as e:
            return None, f"{name} : {str(e)[:60]}"
        fixed = "<tool_call>\n" + json.dumps({"name": name, "arguments": args}, ensure_ascii=False) + "\n</tool_call>"
        a = a.replace(f"<tool_call>{a.split('<tool_call>', 1)[1].split('</tool_call>', 1)[0]}</tool_call>", fixed)
    return a, ""


def check(q: str, a: str) -> bool:
    return review(q, a)[0] is not None


def _prompt(theme: str, tool: str | None, n: int) -> str:
    now = time.strftime("%Y-%m-%dT%H:%M")
    return (
        "Tu écris des exemples d'entraînement pour « Syrius », un assistant personnel francophone : chaleureux, "
        "concis, tutoie, pointe d'humour fin, n'invente jamais un fait. "
        f"Écris {n} conversations courtes et VARIÉES sur ce thème : {theme}. "
        "Quand l'assistant agit, sa réponse = une courte phrase en français, puis un retour à la ligne, puis "
        '<tool_call>\n{"name": "NOM", "arguments": {...}}\n</tool_call> (un seul appel, JSON valide). '
        f"Outils possibles : {', '.join(TOOLS)}. "
        f"Date actuelle : {now}. "
        + (f"Utilise surtout l'outil {tool}. " if tool else "")
        + "Réponds UNIQUEMENT avec un tableau JSON : "
        '[{"q": "message de l\'utilisateur", "a": "réponse idéale de Syrius"}, ...]. Rien d\'autre.')


def _ask(provider, prompt: str) -> str:
    body = {"model": provider.model, "max_tokens": 3500, "temperature": 0.9,
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(provider.base_url + "/chat/completions", data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "User-Agent": "Syrius/1.0",
        **({"Authorization": f"Bearer {provider.api_key}"} if provider.api_key else {})}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:  # nosec B310 (fournisseurs configurés)
        data = json.loads(r.read(2_000_000))
    return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def _parse(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except ValueError:
        return []
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and isinstance(it.get("q"), str) and isinstance(it.get("a"), str):
            out.append({"q": " ".join(it["q"].split()), "a": it["a"].strip()})
    return out


def generate(providers: list, n: int = 10, seed: int | None = None, theme_index: int | None = None) -> dict:
    """Un lot d'exemples sur un thème (choisi, ou tiré au sort). Renvoie {theme, kept, rejected, reasons, provider}."""
    rng = random.Random(seed)
    theme, tool = THEMES[theme_index % len(THEMES)] if theme_index is not None else rng.choice(THEMES)
    last = ""
    pool = [p for p in providers if not getattr(p, "photos_only", False)]
    k = rng.randrange(len(pool)) if pool else 0
    for p in pool[k:] + pool[:k]:
        try:
            items = _parse(_ask(p, _prompt(theme, tool, n)))
        except (urllib.error.URLError, OSError, ValueError) as e:
            last = str(e)[:120]
            continue
        if not items:
            last = "réponse illisible"
            continue
        kept, reasons = [], {}
        for it in items[:n * 2]:
            fixed, why = review(it["q"], it["a"])
            if fixed is None:
                reasons[why] = reasons.get(why, 0) + 1
            else:
                kept.append({"q": it["q"], "a": fixed})
        return {"theme": theme, "kept": kept, "rejected": len(items) - len(kept), "reasons": reasons,
                "provider": p.label}
    return {"theme": theme, "kept": [], "rejected": 0, "provider": "", "error": last or "aucune IA disponible"}
