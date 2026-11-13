"""Transcription de la voix (français) avec Whisper large-v3-turbo chez Groq (gratuit, même clé que l'IA).

Bien plus fiable que la reconnaissance du téléphone (noms propres, phrases longues, accents).
Sécurité : uniquement de l'audio reconnu par son en-tête, taille et durée limitées, envoyé seulement à
api.groq.com en https ; le son n'est jamais enregistré. Les « hallucinations » connues de Whisper sur du
silence (« Sous-titres réalisés par… ») sont écartées.
"""
from __future__ import annotations

import json
import re
import secrets
import urllib.error
import urllib.request

URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL = "whisper-large-v3-turbo"
MAX_BYTES = 3_000_000
TIMEOUT = 25
PROMPT = "Conversation en français avec Syrius, l'assistant personnel. Hey Syrius !"

# Formats acceptés : en-tête attendu → (type, extension)
_FORMATS = (
    (lambda b: b[:4] == b"RIFF" and b[8:12] == b"WAVE", "audio/wav", "wav"),
    (lambda b: b[:4] == b"\x1aE\xdf\xa3", "audio/webm", "webm"),
    (lambda b: b[:4] == b"OggS", "audio/ogg", "ogg"),
    (lambda b: b[4:8] == b"ftyp", "audio/mp4", "m4a"),
)
_HALLUCINATIONS = re.compile(
    r"sous-titr|amara\.org|merci d'avoir regard|abonnez-vous|n'oubliez pas de vous abonner|"
    r"radio-canada|transcription par|soustitreur", re.I)


class TranscribeError(Exception):
    pass


def check_audio(data: bytes) -> tuple[str, str]:
    if not data or len(data) < 1000:
        raise TranscribeError("enregistrement trop court")
    if len(data) > MAX_BYTES:
        raise TranscribeError("enregistrement trop long")
    for test, ctype, ext in _FORMATS:
        if test(data):
            return ctype, ext
    raise TranscribeError("format audio non reconnu")


def clean(result: dict) -> str:
    """Texte final : segments probablement silencieux et formules parasites retirés."""
    segments = result.get("segments")
    if isinstance(segments, list) and segments:
        parts = []
        for s in segments:
            if not isinstance(s, dict):
                continue
            if s.get("no_speech_prob", 0) > 0.6 and s.get("avg_logprob", 0) < -0.8:
                continue
            parts.append(str(s.get("text", "")))
        text = " ".join(parts)
    else:
        text = str(result.get("text", ""))
    sentences = re.split(r"(?<=[.!?…])\s+", " ".join(text.split()))
    return " ".join(x for x in sentences if x and not _HALLUCINATIONS.search(x)).strip()[:2000]


def _multipart(fields: dict, filename: str, ctype: str, data: bytes) -> tuple[bytes, str]:
    boundary = "syrius" + secrets.token_hex(12)
    out = bytearray()
    for k, v in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode()
    out += data + f"\r\n--{boundary}--\r\n".encode()
    return bytes(out), boundary


def transcribe(api_key: str, data: bytes) -> str:
    if not api_key:
        raise TranscribeError("transcription indisponible (clé Groq absente)")
    ctype, ext = check_audio(data)
    body, boundary = _multipart({"model": MODEL, "language": "fr", "temperature": "0",
                                 "response_format": "verbose_json", "prompt": PROMPT},
                                f"voix.{ext}", ctype, data)
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "SyriusAssistant/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            result = json.loads(resp.read(2_000_000))
    except urllib.error.HTTPError as e:
        raise TranscribeError("service de transcription saturé" if e.code == 429
                              else f"service de transcription indisponible ({e.code})") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise TranscribeError("service de transcription injoignable") from None
    return clean(result if isinstance(result, dict) else {})
