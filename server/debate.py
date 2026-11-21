"""Débat entre deux IA : Nova et Aurora défendent chacune un camp, l'utilisateur intervient quand il veut.

Le serveur ne garde rien : l'application envoie à chaque tour le sujet et les répliques déjà dites,
et le serveur renvoie, en direct, la réplique suivante (ou le verdict final).
"""
import json
import logging
import re
import time
from collections.abc import AsyncIterator

from . import family, safety
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


# ------------------------------------------------------------------ entraînement de NOS IA (Nova et Aurora)
# Les répliques des débats du propriétaire deviennent des exemples d'entraînement : Nova (notre petite IA de
# l'application) et Aurora (notre IA de Syrius Code) apprennent à argumenter en lisant ce que les grandes IA
# gratuites ont répondu à leur place. Les grandes IA, elles, ne sont pas entraînées (on ne peut pas).
TRAIN_KEY = "family_debate_train_v1"  # préfixe « family_ » : rangé dans l'espace commun, lu par l'entraînement
MAX_TRAIN = 300                       # exemples gardés par IA (les plus récents)
MAX_PROMPT = 480                      # la question d'entraînement tient en 500 caractères (limite de Nova)
_MODEL_NAMES = re.compile(r"\b(llama|gpt|qwen|mistral|gemini|claude|deepseek|groq|openai|chatgpt)\b", re.I)


def train_prompt(topic: str, turns: list[dict], speaker: str) -> str:
    """La « question » de l'exemple : le sujet, le camp à défendre et ce qui vient d'être dit."""
    other = "aurora" if speaker == "nova" else "nova"
    head = f"Débat : « {topic[:150]} ». Tu défends le {SIDES[speaker].lower()} face à {NAMES[other]}."
    before = [t for t in turns if t["who"] != speaker][-2:]
    room = MAX_PROMPT - len(head) - 10
    lines = []
    for t in reversed(before):  # la dernière réplique d'abord, elle est prioritaire
        line = f"{NAMES[t['who']]} : {t['text']}"
        if len(line) > room:
            line = line[:max(0, room - 1)].rstrip() + "…"
        if room <= 40:
            break
        lines.insert(0, line)
        room -= len(line) + 2
    if not lines:
        lines = ["C'est toi qui ouvres le débat."]
    return (head + "\n\n" + "\n\n".join(lines))[:MAX_PROMPT]


def good_reply(text: str) -> bool:
    """On n'apprend que des répliques propres : ni trop courtes ni trop longues, sans nom de modèle ni contenu interdit."""
    return (40 <= len(text) <= 900 and "<think>" not in text and not _MODEL_NAMES.search(text)
            and not safety.blocked(text))


def trained(base) -> dict[str, list[dict]]:
    try:
        data = json.loads(base.get_secret(TRAIN_KEY) or "{}")
    except ValueError:
        data = {}
    data = data if isinstance(data, dict) else {}
    return {k: [e for e in data.get(k, []) if isinstance(e, dict) and e.get("q") and e.get("a")] for k in SPEAKERS}


def learn(base, topic: str, turns: list[dict], speaker: str, text: str) -> bool:
    """Range une réplique comme exemple pour l'IA qui l'a dite. Renvoie True si elle a été gardée."""
    text = text.strip()
    if speaker not in SPEAKERS or not good_reply(text) or safety.blocked(topic):
        return False
    data = trained(base)
    q = train_prompt(topic, turns, speaker)
    if any(e["a"] == text for e in data[speaker]):
        return False
    data[speaker] = (data[speaker] + [{"q": q, "a": text, "at": int(time.time())}])[-MAX_TRAIN:]
    base.set_secret(TRAIN_KEY, json.dumps(data, ensure_ascii=False))
    return True


def train_counts(base) -> dict[str, int]:
    return {k: len(v) for k, v in trained(base).items()}


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
                      base=None, uid: str = "", train: bool = False) -> AsyncIterator[dict]:
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
        parts: list[str] = []
        try:
            async for chunk in llm.stream_chat(provider, body):
                for choice in chunk.get("choices") or []:
                    text = (choice.get("delta") or {}).get("content") or ""
                    if text:
                        streamed = True
                        parts.append(text)
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
            if train and base is not None:  # débat du propriétaire : la réplique entraîne Nova ou Aurora
                reply = re.sub(r"<think>.*?(</think>|$)", "", "".join(parts), flags=re.S).strip()
                learn(base, topic, turns, speaker, reply)
            yield {"type": "done"}
            return
    yield {"type": "error", "message": str(last) if last else "Aucune IA disponible."}
