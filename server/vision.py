"""Photos envoyées à Syrius : vérification stricte avant de les transmettre à une IA qui voit.

La photo n'est jamais enregistrée : elle accompagne seulement la question en cours.
"""
from __future__ import annotations

import base64
import re

MAX_BYTES = 2_500_000  # après réduction sur le téléphone, une photo fait ~150-400 Ko
_DATA_URL = re.compile(r"^data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=\s]+)$")
_MAGIC = {"jpeg": (b"\xff\xd8\xff",), "png": (b"\x89PNG\r\n\x1a\n",), "webp": (b"RIFF",)}


class ImageError(ValueError):
    pass


def check_image(data_url) -> str:
    """Renvoie l'image (data URL nettoyée) ou lève ImageError."""
    if not isinstance(data_url, str) or len(data_url) > MAX_BYTES * 4 // 3 + 100:
        raise ImageError("Photo trop lourde (2,5 Mo maximum).")
    m = _DATA_URL.match(data_url.strip())
    if not m:
        raise ImageError("Format de photo non accepté (JPEG, PNG ou WebP).")
    kind, b64 = m.group(1), re.sub(r"\s+", "", m.group(2))
    try:
        raw = base64.b64decode(b64, validate=True)
    except ValueError:
        raise ImageError("Photo illisible.") from None
    if not raw or len(raw) > MAX_BYTES:
        raise ImageError("Photo trop lourde (2,5 Mo maximum).")
    if not raw.startswith(_MAGIC[kind]) or (kind == "webp" and raw[8:12] != b"WEBP"):
        raise ImageError("Ce fichier n'est pas une vraie image.")
    return f"data:image/{kind};base64,{b64}"


def attach(messages: list[dict], image: str) -> list[dict]:
    """Ajoute la photo au DERNIER message de l'utilisateur (format « chat completions »)."""
    for m in reversed(messages):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            m["content"] = [{"type": "text", "text": m["content"] or "Que vois-tu sur cette photo ?"},
                            {"type": "image_url", "image_url": {"url": image}}]
            break
    return messages
