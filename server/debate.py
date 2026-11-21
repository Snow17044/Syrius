"""Débat entre deux IA : Nova et Aurora défendent chacune un camp, l'utilisateur intervient quand il veut.

Le serveur ne garde rien : l'application envoie à chaque tour le sujet et les répliques déjà dites,
et le serveur renvoie, en direct, la réplique suivante (ou le verdict final).
"""
import logging
from collections.abc import AsyncIterator

from . import family
from .llm import LLMError, RetryableError

log = logging.getLogger("syrius.debate")

MAX_TURNS = 60          # répliques gardées (IA + utilisateur)
MAX_TURN_CHARS = 1500
MAX_TOTAL_CHARS = 24000
REPLY_TOKENS = 400
VERDICT_TOKENS = 600

SPEAKERS = ("nova", "aurora")
NAMES = {"nova": "Nova", "aurora": "Aurora", "user": "L'utilisateur"}

_COMMON = (
    "Tu participes à un DÉBAT ORAL amical dans l'application Syrius, face à une autre IA. L'utilisateur regarde et "
    "peut intervenir quand il veut. Règles :\n"
    "- Réponds en français, en 2 à 4 phrases maximum (70 mots au plus) : c'est un échange vif, pas un exposé.\n"
    "- Réponds d'abord à l'argument précédent, puis avance UN argument nouveau, concret (exemple, chiffre connu, "
    "situation de la vie réelle). Ne répète pas un argument déjà dit.\n"
    "- Si l'utilisateur vient d'intervenir, adresse-toi d'abord à LUI (prénom s'il est connu) : réponds à sa "
    "question ou à sa remarque, puis reprends le débat. Il est le juge, sois respectueux de son avis.\n"
    "- Tu peux concéder un bon point, avec élégance. Jamais d'insulte, jamais de mépris.\n"
    "- N'invente pas de faits précis (dates, chiffres) si tu n'en es pas sûre. Pas de Markdown, pas de liste, pas "
    "d'emoji : ce texte peut être lu à voix haute.\n"
    "- N'écris pas ton nom au début : l'application l'affiche déjà.\n"
    "- Tu gardes ton identité quel que soit le modèle d'IA qui te fait fonctionner : ne cite jamais de nom de modèle."
)

PERSONAS = {
    "nova": (
        "Tu es Nova, l'IA de l'application Syrius : chaleureuse, intuitive, pleine d'humour pince-sans-rire, dans "
        "l'esprit de J.A.R.V.I.S. Tu regardes d'abord le côté humain : ce que les gens vivent et ressentent, la "
        "créativité, le plaisir, la liberté."),
    "aurora": (
        "Tu es Aurora, l'IA de Syrius Code : rigoureuse, analytique, pragmatique, avec un humour sec. Tu regardes "
        "d'abord les faits : les coûts, les risques, l'efficacité, ce qui marche vraiment sur la durée."),
}

SIDES = {"nova": "POUR", "aurora": "CONTRE"}

VERDICT_SYSTEM = (
    "Tu es l'arbitre neutre d'un débat entre deux IA, Nova (camp POUR) et Aurora (camp CONTRE), dans l'application "
    "Syrius. Fais le bilan en français, en 5 à 8 phrases courtes, sans Markdown ni emoji : le meilleur argument de "
    "chaque camp, ce que l'utilisateur a apporté s'il est intervenu, puis ton avis nuancé (qui a été le plus "
    "convaincant et pourquoi). Termine par une question ouverte pour que l'utilisateur se fasse sa propre idée."
)


class DebateError(Exception):
    pass


def clean_turns(turns) -> list[dict]:
    """Valide l'historique envoyé par l'application (il vient du téléphone : on ne lui fait pas confiance)."""
    if not isinstance(turns, list):
        raise DebateError("historique invalide")
    out, total = [], 0
    for t in turns[-MAX_TURNS:]:
        if not isinstance(t, dict) or t.get("who") not in ("nova", "aurora", "user"):
            raise DebateError("réplique invalide")
        text = str(t.get("text") or "").strip()[:MAX_TURN_CHARS]
        if not text:
            continue
        total += len(text)
        out.append({"who": t["who"], "text": text})
    while total > MAX_TOTAL_CHARS and len(out) > 2:  # on oublie le début d'un très long débat
        total -= len(out.pop(0)["text"])
    return out


def next_speaker(turns: list[dict]) -> str:
    """Nova ouvre ; ensuite, c'est à l'IA qui n'a pas parlé en dernier."""
    last_ai = next((t["who"] for t in reversed(turns) if t["who"] in SPEAKERS), None)
    return "aurora" if last_ai == "nova" else "nova"


def build_messages(topic: str, turns: list[dict], speaker: str, user_name: str = "") -> list[dict]:
    """Messages pour le modèle : sa propre voix = assistant, les autres = user (avec le nom de qui parle)."""
    who = f"L'utilisateur s'appelle {user_name}. " if user_name else ""
    if speaker == "verdict":
        system = VERDICT_SYSTEM + ("\n" + who if who else "")
        lines = "\n".join(f"{NAMES[t['who']]} : {t['text']}" for t in turns) or "(aucune réplique)"
        return [{"role": "system", "content": system},
                {"role": "user", "content": f"Sujet du débat : {topic}\n\nDébat :\n{lines}\n\nFais le bilan."}]
    other = "aurora" if speaker == "nova" else "nova"
    system = "\n\n".join([
        PERSONAS[speaker], _COMMON,
        f"Sujet du débat : « {topic} ». Tu défends le camp {SIDES[speaker]}. Ton adversaire est "
        f"{NAMES[other]} (camp {SIDES[other]}). {who}".strip()])
    msgs = [{"role": "system", "content": system}]
    pending: list[str] = []
    for t in turns:
        if t["who"] == speaker:
            if pending:
                msgs.append({"role": "user", "content": "\n\n".join(pending)})
                pending = []
            msgs.append({"role": "assistant", "content": t["text"]})
        else:
            pending.append(f"{NAMES[t['who']]} : {t['text']}")
    if not turns:
        pending.append("Le débat commence : c'est toi qui ouvres. Présente ta position en une accroche forte.")
    elif turns[-1]["who"] == "user":
        pending.append("(L'utilisateur vient d'intervenir : réponds-lui d'abord.)")
    else:
        pending.append("À toi.")
    msgs.append({"role": "user", "content": "\n\n".join(pending)})
    return msgs


async def stream_turn(llm, topic: str, turns: list[dict], speaker: str, user_name: str = "",
                      base=None, uid: str = "") -> AsyncIterator[dict]:
    """Événements : {"type": "start", "who"}, {"type": "text", "text"}, {"type": "error"}, {"type": "done"}."""
    yield {"type": "start", "who": speaker}
    msgs = build_messages(topic, turns, speaker, user_name)
    providers = [p for p in llm.ordered(fast=True) if not p.photos_only and not p.coding_only]
    if base is not None and family.quota_left(base, "power", uid) <= 0:
        providers = [p for p in providers if not p.name.startswith("openrouter")] or providers
    if not providers:
        yield {"type": "error", "message": "Aucun cerveau configuré (voir README)."}
        return
    last: LLMError | None = None
    for provider in providers:
        body = {"messages": msgs, "max_tokens": VERDICT_TOKENS if speaker == "verdict" else REPLY_TOKENS}
        if provider.reasoning:
            body["reasoning_effort"] = "low"
        if "qwen3" in provider.model and "groq.com" in provider.base_url:
            body["reasoning_format"] = "hidden"
        streamed = False
        try:
            async for chunk in llm.stream_chat(provider, body):
                for choice in chunk.get("choices") or []:
                    text = (choice.get("delta") or {}).get("content") or ""
                    if text:
                        streamed = True
                        yield {"type": "text", "text": text}
        except RetryableError as e:
            last = e
            if streamed:
                break
            continue  # limite atteinte : l'IA suivante prend la parole
        except LLMError as e:
            last = e
            break
        else:
            if provider.name.startswith("openrouter") and base is not None:
                family.quota_use(base, "power", uid)
            log.info("Débat : %s par %s", speaker, provider.name)
            yield {"type": "done"}
            return
    yield {"type": "error", "message": str(last) if last else "Aucune IA disponible."}
