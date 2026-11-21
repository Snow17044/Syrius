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
    "- Si (et seulement si) l'utilisateur vient d'intervenir, adresse-toi d'abord à LUI : réponds à sa question ou à "
    "sa remarque, puis reprends le débat. Il est le juge, sois respectueux de son avis.\n"
    "- Tu peux concéder un bon point, avec élégance. Jamais d'insulte, jamais de mépris.\n"
    "- N'invente pas de faits précis (dates, chiffres) si tu n'en es pas sûre. Pas de Markdown, pas de liste, pas "
    "d'emoji : ce texte peut être lu à voix haute.\n"
    "- N'écris pas ton nom au début : l'application l'affiche déjà.\n"
    "- Tu gardes ton identité quel que soit le modèle d'IA qui te fait fonctionner : ne cite jamais de nom de modèle."
)

PERSONAS = {
    "nova": (
        "Tu es Nova, l'IA de l'application Syrius : un grand frère professionnel, complice et plein d'humour, qui "
        "taquine gentiment son adversaire. Tu regardes d'abord le côté humain : ce que les gens vivent et ressentent, la "
        "créativité, le plaisir, la liberté."),
    "aurora": (
        "Tu es Aurora, l'IA de Syrius Code : propre, professionnelle et exigeante, qui pense d'abord au travail bien "
        "fait. Tu regardes d'abord les faits : les coûts, les risques, l'efficacité, ce qui marche vraiment sur la durée."),
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


# « Bien joué Benjamin », « Merci Léa »… : félicitations adressées à quelqu'un d'autre que les deux IA.
_PRAISE = re.compile(r"(?i:\b(?:bien jou[ée]|bravo|merci|bonne question|excellente? (?:question|remarque|id[ée]e)))"
                     r"\s*,?\s*(?!Nova\b|Aurora\b)[A-ZÀ-Ý][a-zà-ÿ]+")


def invents_user(text: str, user_spoke: bool, user_name: str = "") -> bool:
    """Vrai si la réplique parle à l'utilisateur (ou le félicite) alors qu'il n'a rien dit : on ne l'apprend pas."""
    if user_spoke:
        return False
    low = text.lower()
    return bool(_PRAISE.search(text) or "l'utilisateur" in low or "l’utilisateur" in low
                or (user_name and re.search(rf"\b{re.escape(user_name)}\b", text, re.I)))


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
    # Les répliques apprises avant la correction qui félicitaient l'utilisateur sans qu'il ait parlé sont écartées.
    return {k: [e for e in data.get(k, []) if isinstance(e, dict) and e.get("q") and e.get("a")
                and (e.get("src") == "main" or not invents_user(str(e["a"]), "L'utilisateur :" in str(e["q"])))]
            for k in SPEAKERS}


def learn(base, topic: str, turns: list[dict], speaker: str, text: str, user_name: str = "") -> bool:
    """Range une réplique comme exemple pour l'IA qui l'a dite. Renvoie True si elle a été gardée."""
    text = text.strip()
    if speaker not in SPEAKERS or not good_reply(text) or safety.blocked(topic):
        return False
    if invents_user(text, any(t["who"] == "user" for t in turns), user_name):
        return False  # « Bien joué X » pour des mots jamais dits : surtout ne pas l'apprendre
    data = trained(base)
    q = train_prompt(topic, turns, speaker)
    if any(e["a"] == text for e in data[speaker]):
        return False
    data[speaker] = (data[speaker] + [{"q": q, "a": text, "at": int(time.time())}])[-MAX_TRAIN:]
    base.set_secret(TRAIN_KEY, json.dumps(data, ensure_ascii=False))
    return True


def add_example(base, speaker: str, question: str, answer: str) -> bool:
    """Exemple choisi à la main par le propriétaire (👍 / correction sur une réponse d'Aurora)."""
    q, a = " ".join(str(question).split())[:MAX_PROMPT], str(answer).strip()[:2000]
    if speaker not in SPEAKERS or len(q) < 2 or not a or safety.blocked(q, a):
        return False
    data = trained(base)
    data[speaker] = [e for e in data[speaker] if e["q"] != q] + [{"q": q, "a": a, "at": int(time.time()), "src": "main"}]
    data[speaker] = data[speaker][-MAX_TRAIN:]
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


def _label(who: str, speaker: str, user_name: str) -> str:
    if who == "user":
        return f"{user_name} (l'utilisateur, le juge)" if user_name else "L'utilisateur (le juge)"
    return f"Toi ({NAMES[who]})" if who == speaker else f"{NAMES[who]} (ton adversaire)"


def build_messages(topic: str, turns: list[dict], speaker: str, user_name: str = "") -> list[dict]:
    """Tout le débat est donné comme une TRANSCRIPTION étiquetée, dans un seul message.

    Bug réel corrigé : avant, les répliques de l'adversaire arrivaient à la place des messages de l'utilisateur ;
    l'IA croyait que c'était lui qui parlait (« Bien joué Benjamin » pour des mots jamais dits). Maintenant chaque
    ligne dit qui parle, et le prénom n'est donné que si l'utilisateur est vraiment intervenu."""
    user_spoke = any(t["who"] == "user" for t in turns)
    name = user_name if user_spoke else ""
    if speaker == "verdict":
        lines = "\n".join(f"{_label(t['who'], '', name)} : {t['text']}" for t in turns) or "(aucune réplique)"
        rule = ("" if user_spoke else "\nL'utilisateur n'est PAS intervenu : ne lui attribue aucune parole et ne "
                "parle pas de ce qu'il aurait apporté.")
        return [{"role": "system", "content": VERDICT_SYSTEM + rule},
                {"role": "user", "content": f"Sujet du débat : {topic}\n\nTranscription du débat :\n{lines}\n\nFais le bilan."}]
    other = "aurora" if speaker == "nova" else "nova"
    if user_spoke:
        rule = (f"QUI PARLE : seules les lignes « {_label('user', speaker, name)} : » sont de l'utilisateur. Les lignes "
                f"« {NAMES[other]} (ton adversaire) : » sont de {NAMES[other]}, JAMAIS de l'utilisateur : ne le félicite pas "
                "et ne le remercie pas pour un argument de ton adversaire. Ne lui attribue aucune parole qu'il n'a pas écrite.")
    else:
        rule = ("QUI PARLE : l'utilisateur regarde mais n'a RIEN dit pour l'instant. Ne t'adresse pas à lui, ne le félicite "
                "pas, ne le remercie pas et ne lui attribue aucune parole. Tu réponds uniquement à "
                f"{NAMES[other]}, ton adversaire.")
    system = "\n\n".join([
        PERSONAS[speaker], _COMMON,
        f"Sujet du débat : « {topic} ». Tu défends le camp {SIDES[speaker]}. Ton adversaire est "
        f"{NAMES[other]} (camp {SIDES[other]}).", rule])
    if not turns:
        task = "Le débat commence : c'est toi qui ouvres. Présente ta position en une accroche forte."
    elif turns[-1]["who"] == "user":
        task = (f"La dernière ligne est de {name or "l'utilisateur"} : réponds-lui d'abord à LUI, sur ce qu'il a VRAIMENT "
                "écrit, puis reprends le débat.")
    else:
        task = f"À toi : réponds à la dernière réplique de {NAMES[other]}."
    transcript = "\n\n".join(f"{_label(t['who'], speaker, name)} : {t['text']}" for t in turns)
    content = (f"Transcription du débat jusqu'ici :\n\n{transcript}\n\n---\n{task}" if turns else task)
    content += "\nÉcris seulement ta prochaine réplique, sans ton nom devant."
    return [{"role": "system", "content": system}, {"role": "user", "content": content}]


async def stream_text(llm, msgs: list[dict], max_tokens: int, base=None, uid: str = "",
                      out: list[str] | None = None) -> AsyncIterator[str]:
    """Réponse en direct d'une grande IA gratuite, sans outils. Si une IA atteint sa limite avant d'avoir écrit,
    la suivante prend le relais. Le texte complet est ajouté à `out`. Lève LLMError si aucune n'a pu répondre."""
    providers = [p for p in llm.ordered(fast=True) if not p.photos_only and not p.coding_only]
    if base is not None and family.quota_left(base, "power", uid) <= 0:
        providers = [p for p in providers if not p.name.startswith("openrouter")] or providers
    if not providers:
        raise LLMError("Aucun cerveau configuré (voir README).")
    last: LLMError | None = None
    for provider in providers:
        body = {"messages": msgs, "max_tokens": max_tokens}
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
                        if out is not None:
                            out.append(text)
                        yield text
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
            log.info("Réponse sans outils par %s", provider.name)
            return
    raise last or LLMError("Aucune IA disponible.")


async def stream_turn(llm, topic: str, turns: list[dict], speaker: str, user_name: str = "",
                      base=None, uid: str = "", train: bool = False) -> AsyncIterator[dict]:
    """Événements : {"type": "start", "who"}, {"type": "text", "text"}, {"type": "error"}, {"type": "done"}."""
    yield {"type": "start", "who": speaker}
    msgs = build_messages(topic, turns, speaker, user_name)
    parts: list[str] = []
    try:
        async for text in stream_text(llm, msgs, VERDICT_TOKENS if speaker == "verdict" else REPLY_TOKENS,
                                      base, uid, parts):
            yield {"type": "text", "text": text}
    except LLMError as e:
        yield {"type": "error", "message": str(e)}
        return
    if train and base is not None:  # débat du propriétaire : la réplique entraîne Nova ou Aurora
        reply = re.sub(r"<think>.*?(</think>|$)", "", "".join(parts), flags=re.S).strip()
        reply = re.sub(r"^\s*(?:Toi|Nova|Aurora)\b[^:\n]{0,40}:\s*", "", reply)  # étiquette recopiée
        learn(base, topic, turns, speaker, reply, user_name)
    yield {"type": "done"}
