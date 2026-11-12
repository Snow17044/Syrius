"""Le cerveau de Syrius : dialogue avec l'IA, outils, mémoire, réponses en direct."""
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

from .config import Config
from .db import Database
from .llm import ChatClient, LLMError, RetryableError, providers_from_config
from .tools import diagram
from .tools.registry import TIMEZONE, TOOL_LABELS, ToolExecutor, build_tools

log = logging.getLogger("syrius.agent")

UNTRUSTED_TOOLS = {"list_emails", "search_emails", "read_email", "web_search", "web_read", "show_places"}
WEB_TOOLS = {"web_search", "web_read", "show_places"}
MAX_WEB_CALLS = 8  # pages / recherches web maximum par réponse
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
    if settings.get("internet", True) is False:
        parts.append("Internet est DÉSACTIVÉ dans les réglages : tu n'as pas les outils web_search / web_read. "
                     "Si on te demande une info récente, dis-le et propose d'activer Internet dans les réglages.")
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


def to_openai(stored: list[dict], system: str) -> list[dict]:
    """Convertit l'historique enregistré au format « chat completions » (Groq, Gemini, Ollama)."""
    out = [{"role": "system", "content": system}]
    for m in stored:
        if m["role"] == "user":
            for b in m["content"]:
                if b.get("type") == "tool_result":
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]})
                elif b.get("type") == "text":
                    out.append({"role": "user", "content": b["text"]})
        else:
            text = "\n\n".join(b["text"] for b in m["content"] if b.get("type") == "text")
            msg: dict = {"role": "assistant", "content": text}
            calls = [{"id": b["id"], "type": "function",
                      "function": {"name": b["name"], "arguments": json.dumps(b["input"], ensure_ascii=False)}}
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
        diagrams = []
        for b in m["content"]:  # les schémas 3D restent consultables dans l'historique
            if b.get("type") == "tool_use" and b.get("name") == "show_diagram":
                try:
                    diagrams.append(diagram.validate(b.get("input")))
                except diagram.DiagramError:
                    pass
        if out and out[-1]["role"] == "assistant":  # fusionne les étapes d'une même réponse
            prev = out[-1]
            prev["text"] = "\n\n".join(t for t in [prev["text"], *texts] if t)
            prev["tools"] += tools
            prev["diagrams"] = prev.get("diagrams", []) + diagrams
        else:
            out.append({"role": "assistant", "text": "\n\n".join(texts), "tools": tools, "diagrams": diagrams})
    return out


_THINK_TAGS = re.compile(r"<think>.*?</think>\s*", re.S)


class Agent:
    def __init__(self, cfg: Config, db: Database, llm: ChatClient | None = None):
        self.cfg = cfg
        self.db = db
        self.llm = llm or ChatClient(providers_from_config(cfg))
        self.executor = ToolExecutor(cfg, db)

    def brains(self) -> list[dict]:
        return [{"name": p.name, "label": p.label, "model": p.model} for p in self.llm.providers]

    async def _one_step(self, provider, body: dict, state: dict) -> AsyncIterator[dict]:
        """Une réponse du modèle. Remplit state["text"] et state["calls"]."""
        partial: dict[int, dict] = {}
        async for chunk in self.llm.stream_chat(provider, body):
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                text = delta.get("content") or ""
                if text:
                    state["streamed"] = True
                    state["text"] += text
                    yield {"type": "text", "text": text}
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", len(partial))
                    cur = partial.setdefault(idx, {"id": "", "name": "", "args": ""})
                    cur["id"] = tc.get("id") or cur["id"]
                    fn = tc.get("function") or {}
                    cur["name"] += fn.get("name") or ""
                    cur["args"] += fn.get("arguments") or ""
        for idx in sorted(partial):
            cur = partial[idx]
            try:
                args = json.loads(cur["args"]) if cur["args"].strip() else {}
            except ValueError:
                args = {"__invalid_json__": cur["args"][:200]}
            name = cur["name"][:64]
            state["calls"].append({"type": "tool_use", "id": (cur["id"] or "call_" + uuid.uuid4().hex[:12])[:64],
                                   "name": name, "input": args})
            yield {"type": "tool", "name": name, "label": TOOL_LABELS.get(name, name)}

    async def chat(self, conversation_id: str, user_text: str,
                   location: dict | None = None) -> AsyncIterator[dict]:
        if not self.llm.providers:
            yield {"type": "error", "message": "Aucun cerveau configuré : ajoute une clé GROQ_API_KEY "
                                               "ou GEMINI_API_KEY (voir README)."}
            return
        settings = self.db.get_settings()
        stored = self.db.get_messages(conversation_id)

        user_content: list[dict] = [
            {"type": "tool_result", "tool_use_id": tid, "tool_name": name, "is_error": True,
             "content": "Interrompu avant la fin."}
            for tid, name in unanswered_tool_uses(stored)]
        user_content.append({"type": "text", "text": user_text})
        history = trim_history(stored) + [{"role": "user", "content": user_content}]
        to_save = [history[-1]]
        providers = self.llm.ordered(settings.get("brain", ""))
        effort = "high" if settings.get("effort") == "high" else "low"
        untrusted_seen = False
        web_calls = 0

        for _step in range(MAX_STEPS):
            system = build_system(settings, self.db.list_memories())  # les souvenirs peuvent changer
            body = {"messages": to_openai(history, system), "tools": build_tools(self.cfg, settings),
                    "max_tokens": 8000}
            state = {"text": "", "calls": [], "streamed": False}
            last_error: LLMError | None = None
            tool_retry = False
            while providers:
                provider = providers[0]
                req = dict(body)
                if provider.reasoning:
                    req["reasoning_effort"] = effort
                try:
                    async for event in self._one_step(provider, req, state):
                        yield event
                    last_error = None
                    break
                except RetryableError as e:
                    last_error = e
                    if state["streamed"] or state["calls"]:
                        break  # coupure en plein milieu : on ne mélange pas deux cerveaux
                    providers = providers[1:]  # limite atteinte : on passe au cerveau suivant
                    if providers:
                        yield {"type": "tool", "name": "switch",
                               "label": f"{e} Je passe sur {providers[0].label}."}
                except LLMError as e:
                    last_error = e
                    # Le modèle a appelé un outil inexistant ou mal formé : on réessaie une fois.
                    if "validation failed" in str(e).lower() and not state["streamed"] and not tool_retry:
                        tool_retry = True
                        state = {"text": "", "calls": [], "streamed": False}
                        last_error = None
                        continue
                    break
            if last_error is not None:
                yield {"type": "error", "message": str(last_error)}
                if state["text"]:  # garde ce qui a déjà été écrit
                    self.db.add_messages(conversation_id, to_save + [
                        {"role": "assistant", "content": [{"type": "text", "text": state["text"]}]}])
                return

            # Journal de diagnostic : seulement le nom des outils, jamais le contenu.
            log.info("Réponse %s : %d caractères, outils=%s", provider.name, len(state["text"]),
                     [c["name"] for c in state["calls"]] or "aucun")
            text = _THINK_TAGS.sub("", state["text"])
            content = ([{"type": "text", "text": text}] if text else []) + state["calls"]
            assistant_msg = {"role": "assistant", "content": content or [{"type": "text", "text": ""}]}
            self.db.add_messages(conversation_id, to_save + [assistant_msg])
            history.append(assistant_msg)
            to_save = []
            if not state["calls"]:
                break

            results = []
            if any(c["name"] in UNTRUSTED_TOOLS for c in state["calls"]):
                untrusted_seen = True  # même si l'action téléphone est demandée dans le même lot
            for call in state["calls"]:
                if call["name"] in WEB_TOOLS:
                    web_calls += 1
                if call["name"] in WEB_TOOLS and web_calls > MAX_WEB_CALLS:
                    result, is_error, ui_event = "Limite de pages web atteinte pour cette réponse.", True, None
                else:
                    result, is_error, ui_event = await self.executor.run(call["name"], call["input"],
                                                                         {"location": location})
                if call["name"] in UNTRUSTED_TOOLS and not is_error:
                    untrusted_seen = True
                if ui_event and ui_event.get("type") == "device" and untrusted_seen:
                    # Un contenu extérieur (email, web) a été lu dans cette réponse :
                    # toute action sur le téléphone doit être confirmée par l'utilisateur.
                    ui_event = {**ui_event, "confirm": True, "after_untrusted": True}
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

    @staticmethod
    def make_title(first_message: str) -> str:
        # Titre tiré du premier message : n'utilise pas le quota gratuit de l'IA.
        line = " ".join(first_message.split())
        return (line[:48] + "…") if len(line) > 50 else (line or "Nouvelle discussion")


def sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
