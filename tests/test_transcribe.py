"""Transcription de la voix (Whisper via Groq) : formats contrôlés, hallucinations écartées, route protégée."""
import io
import json
import urllib.error

import pytest

from server import transcribe
from server.transcribe import TranscribeError

WAV = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 4000


def test_formats_audio_controles():
    assert transcribe.check_audio(WAV) == ("audio/wav", "wav")
    assert transcribe.check_audio(b"\x1aE\xdf\xa3" + b"0" * 2000)[1] == "webm"
    assert transcribe.check_audio(b"OggS" + b"0" * 2000)[1] == "ogg"
    assert transcribe.check_audio(b"0000ftypM4A " + b"0" * 2000)[1] == "m4a"
    for bad in (b"", b"RIFF", b"<html>" + b"0" * 2000, b"MZ\x90\x00" + b"0" * 2000,
                b"RIFF" + b"\x00" * 4 + b"WAVE" + b"0" * transcribe.MAX_BYTES):
        with pytest.raises(TranscribeError):
            transcribe.check_audio(bad)


def test_hallucinations_et_silence_ecartes():
    assert transcribe.clean({"text": " Quelle heure est-il ? "}) == "Quelle heure est-il ?"
    assert transcribe.clean({"text": "Sous-titres réalisés par la communauté d'Amara.org"}) == ""
    assert transcribe.clean({"text": "Mets de la musique. Merci d'avoir regardé cette vidéo !"}) == "Mets de la musique."
    seg = [{"text": " Appelle maman.", "no_speech_prob": 0.01, "avg_logprob": -0.2},
           {"text": " Abonnez-vous", "no_speech_prob": 0.9, "avg_logprob": -1.5}]
    assert transcribe.clean({"text": "x", "segments": seg}) == "Appelle maman."


def test_envoi_a_groq_uniquement(monkeypatch):
    seen = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        seen["url"], seen["auth"], seen["body"] = req.full_url, req.headers["Authorization"], req.data
        return Resp(json.dumps({"text": "Bonjour Syrius"}).encode())
    monkeypatch.setattr(transcribe.urllib.request, "urlopen", fake_urlopen)
    assert transcribe.transcribe("cle", WAV) == "Bonjour Syrius"
    assert seen["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert seen["auth"] == "Bearer cle"
    assert b'name="model"\r\n\r\nwhisper-large-v3-turbo' in seen["body"] and b'name="language"\r\n\r\nfr' in seen["body"]
    with pytest.raises(TranscribeError):
        transcribe.transcribe("", WAV)  # pas de clé

    def saturated(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 429, "x", {}, None)
    monkeypatch.setattr(transcribe.urllib.request, "urlopen", saturated)
    with pytest.raises(TranscribeError, match="saturé"):
        transcribe.transcribe("cle", WAV)


def test_route_protegee(make_client, monkeypatch):
    from tests.conftest import login
    client = make_client()
    r = client.post("/api/transcribe", content=WAV, headers={"X-Syrius": "1", "Content-Type": "audio/wav"})
    assert r.status_code == 401
    login(client)
    r = client.post("/api/transcribe", content=WAV, headers={"Content-Type": "audio/wav"})
    assert r.status_code in (400, 403)  # anti-CSRF
    monkeypatch.setattr(transcribe, "transcribe", lambda key, data: "Quelle heure est-il ?")
    r = client.post("/api/transcribe", content=WAV, headers={"X-Syrius": "1", "Content-Type": "audio/wav"})
    assert r.status_code == 200 and r.json() == {"text": "Quelle heure est-il ?"}

    def bad(key, data):
        raise TranscribeError("format audio non reconnu")
    monkeypatch.setattr(transcribe, "transcribe", bad)
    r = client.post("/api/transcribe", content=b"x" * 2000, headers={"X-Syrius": "1"})
    assert r.status_code == 400
