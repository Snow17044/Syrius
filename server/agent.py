"""Le cerveau de Syrius : dialogue avec l'IA locale, outils, mémoire, réponses en direct."""
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

from .config import Config
from .db import Database
from .llm import LLMError, OllamaClient
from .tools.registry import TIMEZONE, TOOL_LABELS, ToolExecutor, build_tools

log = logging.getLogger("syrius.agent")

MAX_STEPS = 8          # allers-retours max avec les outils pour une seule question
MAX_HISTORY = 40       # messages gardés en contexte (au-delà, les plus anciens sont oubliés)
PERSONA_FILE = Path(__file__).with_name("persona.md")
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre"]


def load_persona() -> str:
    """La personnalité est dans server/persona.md : modifie ce fichier pour changer Syrius."""
    return PERSONA_FILE.read_text(encoding="utf-8").strip()


def build_system(settings: dict, memories: list[dict]) -> str:
    now = datetime.now(TIMEZONE)
    parts = [load_persona(),
             f"Nous sommes le {JOURS[now.weekday()]} {now.day} {MOIS[now.month - 1]} {now.year}."]
    if settings.get("user_name"):
        parts.append(f"Prénom de l'utilisateur : {settings['user_name']}")
    if settings.get("custom_instructions"):
        parts.append("Préférences données par l'utilisateur dans les réglages :\n" + settings["custom_instructions"])
    if memories:
        parts.append("Souvenirs (numéro : contenu) :\n" + "\n".join(f"{m['id']} : {m['content']}" for m in memories))
    else:
        parts.append("Souvenirs : aucun pour l'instant.")
    return "\n\n".join(parts)


def trim_history(stored: list[dict]) -> list[dict]:
    """Garde les derniers messages, en commençant par une vraie question de l'utilisateur."""
    if len(stored) <= MAX_HISTORY:
        return stored
    recent = stored[-MAX_HISTORY:]
    for i, m in enumerate(recent):
        if m["role"] == "user" and any(b.get("type") == "text" for b in m["content"]):
            return recent[i:]
    return recent[-1:]


def unanswered_tool_uses(stored: list[dict]) -> list[tuple[str, str]]:
    """Appels d'outils restés sans réponse (ex. coupure pendant l'exécution)."""
    if not stored or stored[-1]["role"] != "assistant":
        return []
    return [(b["id"], b["name"]) for b in stored[-1]["content"] if b.get("type") == "tool_use"]


def to_ollama(stored: list[dict], system: str) -> list[dict]:
    """Convertit l'historique enregistré au format attendu par Ollama."""
    out = [{"role": "system", "content": system}]
    for m in stored:
        if m["role"] == "user":
            for b in m["content"]:
                if b.get("type") == "tool_result":
                    out.append({"role": "tool", "tool_name": b.get("tool_name", ""), "content": b["content"]})
                elif b.get("type") == "text":
                    out.append({"role": "user", "content": b["text"]})
        else:
            text = "\n\n".join(b["text"] for b in m["content"] if b.get("type") == "text")
            msg = {"role": "assistant", "content": text}
            calls = [{"function": {"name": b["name"], "arguments": b["input"]}}
                     for b in m["content"] if b.get("type") == "tool_use"]
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
    return out


def display_messages(stored: list[dict]) -> list[dict]:
    """Version simplifiée pour l'affichage dans l'app."""
    out: list[dict] = []
    for m in stored:
        if m["role"] == "user":
            texts = [b["text"] for b in m["content"] if b.get("type") == "text"]
            if texts:
                out.append({"role": "user", "text": "\n".join(texts), "tools": []})
            continue
        texts = [b["text"] for b in m["content"] if b.get("type") == "text" and b["text"]]
        tools = [TOOL_LABELS.get(b.get("name", ""), b.get("name", ""))
                 for b in m["content"] if b.get("type") == "tool_use"]
        if out and out[-1]["role"] == "assistant":  # fusionne les étapes d'une même réponse
            prev = out[-1]
            prev["text"] = "\n\n".join(t for t in [prev["text"], *texts] if t)
            prev["tools"] += tools
        else:
            out.append({"role": "assistant", "text": "\n\n".join(texts), "tools": tools})
    return out


_THINK_TAGS = re.compile(r"<think>.*?</think>\s*", re.S)


class Agent:
    def __init__(self, cfg: Config, db: Database, llm=None):
        self.cfg = cfg
        self.db = db
        self.llm = llm or OllamaClient(cfg.ollama_url)
        self.executor = ToolExecutor(cfg, db)

    def model(self, settings: dict) -> str:
        return settings.get("model") or self.cfg.model

    def _payload(self, settings: dict, messages: list[dict], tools: list[dict], think: bool | None) -> dict:
        payload = {
            "model": self.model(settings),
            "messages": messages,
            "tools": tools,
            "keep_alive": -1,  # le modèle reste chargé en mémoire : pas d'attente au réveil
            "options": {"num_ctx": self.cfg.context_tokens},
        }
        if think is not None:
            payload["think"] = think
        return payload

    async def chat(self, conversation_id: str, user_text: str) -> AsyncIterator[dict]:
        settings = self.db.get_settings()
        stored = self.db.get_messages(conversation_id)

        user_content: list[dict] = [
            {"type": "tool_result", "tool_use_id": tid, "tool_name": name, "is_error": True,
             "content": "Interrompu avant la fin."}
            for tid, name in unanswered_tool_uses(stored)]
        user_content.append({"type": "text", "text": user_text})
        history = trim_history(stored) + [{"role": "user", "content": user_content}]
        to_save = [history[-1]]
        think: bool | None = settings.get("effort", "low") != "low"

        for _step in range(MAX_STEPS):
            system = build_system(settings, self.db.list_memories())  # les souvenirs peuvent changer
            payload = self._payload(settings, to_ollama(history, system), build_tools(self.cfg, settings), think)
            text, calls, streamed_any = "", [], False
            try:
                async for chunk in self.llm.stream_chat(payload):
                    msg = chunk.get("message") or {}
                    delta = msg.get("content") or ""
                    if delta:
                        streamed_any = True
                        text += delta
                        yield {"type": "text", "text": delta}
                    for call in msg.get("tool_calls") or []:
                        fn = call.get("function") or {}
                        name = str(fn.get("name", ""))[:64]
                        calls.append({"type": "tool_use", "id": "call_" + uuid.uuid4().hex[:12],
                                      "name": name, "input": fn.get("arguments")})
                        yield {"type": "tool", "name": name, "label": TOOL_LABELS.get(name, name)}
            except LLMError as e:
                if think is not None and "think" in str(e).lower() and not streamed_any:
                    think = None  # ce modèle ne gère pas le réglage « réflexion » : on réessaie sans
                    continue
                yield {"type": "error", "message": str(e)}
                return

            text = _THINK_TAGS.sub("", text)
            content = ([{"type": "text", "text": text}] if text else []) + calls
            assistant_msg = {"role": "assistant", "content": content or [{"type": "text", "text": ""}]}
            self.db.add_messages(conversation_id, to_save + [assistant_msg])
            history.append(assistant_msg)
            to_save = []
            if not calls:
                break

            results = []
            for call in calls:
                result, is_error, ui_event = await self.executor.run(call["name"], call["input"])
                results.append({"type": "tool_result", "tool_use_id": call["id"], "tool_name": call["name"],
                                "content": result, "is_error": is_error})
                if ui_event:
                    yield ui_event
            tool_msg = {"role": "user", "content": results}
            history.append(tool_msg)
            to_save = [tool_msg]
        else:
            yield {"type": "text", "text": "\n\n(J'ai atteint ma limite d'étapes pour cette demande.)"}

        if to_save:  # résultats d'outils non suivis d'une réponse : on les garde quand même
            self.db.add_messages(conversation_id, to_save)
        yield {"type": "done"}

    async def make_title(self, first_message: str) -> str:
        fallback = first_message.strip().split("\n")[0][:50] or "Nouvelle discussion"
        settings = self.db.get_settings()
        try:
            resp = await self.llm.chat({
                "model": self.model(settings), "think": False, "keep_alive": -1,
                "options": {"num_predict": 24, "num_ctx": 2048},
                "messages": [
                    {"role": "system", "content": "Donne un titre très court (2 à 6 mots, sans guillemets) à une "
                                                  "discussion qui commence par le message fourni. Réponds uniquement le titre."},
                    {"role": "user", "content": first_message[:1500]}],
            })
            title = _THINK_TAGS.sub("", (resp.get("message") or {}).get("content", "")).strip()
            title = title.strip('"«»*# ').split("\n")[0]
            return title[:60] or fallback
        except (LLMError, OSError, ValueError):
            return fallback

    async def list_models(self) -> list[str]:
        try:
            return await self.llm.list_models()
        except (LLMError, OSError, ValueError):
            return []


def sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
