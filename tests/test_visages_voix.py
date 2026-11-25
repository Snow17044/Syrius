"""Mode conversation : visages animés, une voix chacun, expressions, et relais de modèle invisible."""
import json
from pathlib import Path

from server import group
from server.llm import RetryableError
from tests.conftest import H, login, reply

ROOT = Path(__file__).resolve().parents[1]


def events_of(text):
    return [json.loads(line[6:]) for line in text.split("\n\n") if line.startswith("data: ")]


def test_expressions_seulement_en_mode_conversation(make_client):
    c = make_client([reply("[rieur] Ha, bonne idée !"), reply("[sceptique] Pas si sûr."),
                     reply("Salut !"), reply("Bonjour.")])
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    c.put(f"/api/conversations/{cid}/members", json={"aurora": True}, headers=H)
    c.post(f"/api/conversations/{cid}/messages", json={"text": "On part en vacances ?", "voice": True, "faces": True}, headers=H)
    nova, aurora = c.fake.requests[0], c.fake.requests[1]
    assert group.FACES_NOTE in nova["messages"][0]["content"] and group.FACES_NOTE in aurora["messages"][0]["content"]
    c.post(f"/api/conversations/{cid}/messages", json={"text": "Et toi ?"}, headers=H)  # écrit : pas d'expressions
    assert group.FACES_NOTE not in c.fake.requests[2]["messages"][0]["content"]
    assert group.FACES_NOTE not in c.fake.requests[3]["messages"][0]["content"]


def test_chacun_ses_idees():
    assert "propres idées" in group.AURORA_SYSTEM and "propres idées" in group.NOVA_NOTE


def test_changement_de_modele_invisible(make_client):
    c = make_client([reply("Réponse.")])
    c.fake.fail["groq"] = RetryableError("Groq : limite gratuite atteinte pour le moment.")
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    ev = events_of(c.post(f"/api/conversations/{cid}/messages", json={"text": "Salut"}, headers=H).text)
    assert not any("Gemini" in str(e) or "Groq" in str(e) for e in ev)


def test_visages_et_voix_cote_application():
    faces = (ROOT / "web/faces.js").read_text(encoding="utf-8")
    for expr in ("content", "rieur", "pensif", "surpris", "sceptique", "inquiet", "fier", "neutre"):
        assert expr in faces and expr in group.FACES_NOTE
    java = (ROOT / "android/app/src/main/java/fr/syrius/app/MainActivity.java").read_text(encoding="utf-8")
    assert "public void speakAs(String text, String who)" in java and '\\"voices2\\"' in java
    assert 'voiceFor("nova");  // après une réplique d\'Aurora' in java  # la voix de Nova revient toujours
    voice = (ROOT / "web/voice.js").read_text(encoding="utf-8")
    assert "askAll" in voice and 'speakAndWait(r.text, r.who)' in voice


def test_aurora_vient_d_office_en_conversation_vocale():
    """Demande : quand on parle à Syrius, Aurora est à côté de Nova sans avoir à l'inviter."""
    voice = (ROOT / "web/voice.js").read_text(encoding="utf-8")
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    assert "window.SyriusGroup.join().then(buildFaces)" in voice and "window.SyriusGroup = {" in app
    assert "Laisser Nova seul" in voice  # on peut quand même la faire partir


def test_aurora_reparle_si_sa_voix_echoue():
    """Constat réel : Aurora ne parlait jamais sur le téléphone. Si sa voix échoue, elle reparle avec la voix de secours."""
    java = (ROOT / "android/app/src/main/java/fr/syrius/app/MainActivity.java").read_text(encoding="utf-8")
    assert 'id.startsWith("aurora")' in java and "tts.setPitch(1.18f)" in java and "auroraRetry" in java
    assert "!v.isNetworkConnectionRequired()" in java  # par défaut, une voix installée sur le téléphone
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    assert "v.name !== nova.name" in app  # web : vraiment une autre voix que Nova
