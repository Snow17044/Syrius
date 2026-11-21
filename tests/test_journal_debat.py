"""Journal intime du soir, réveil Jarvis et débat entre IA (Nova contre Aurora)."""
import json
from pathlib import Path

from server import debate, journal
from server.llm import RetryableError
from server.tools.registry import build_tools, select_tools
from tests.conftest import H, login, reply

ROOT = Path(__file__).resolve().parents[1]


def events_of(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.split("\n\n") if line.startswith("data: ")]


def names(tools) -> set[str]:
    return {t["function"]["name"] for t in tools}


# --------------------------------------------------------------- journal
def test_journal_une_page_par_jour(make_db):
    db = make_db()
    journal.save(db, "J'ai fini mon exposé.", "fière", day="2026-11-19")
    journal.save(db, "Première version.", day="2026-11-20")
    journal.save(db, "  Journée calme,\n  balade au parc.  ", "  serein  ", day="2026-11-20")  # remplace
    items = journal.entries(db)
    assert [e["day"] for e in items] == ["2026-11-20", "2026-11-19"]
    assert items[0] == {"day": "2026-11-20", "text": "Journée calme,\nbalade au parc.", "mood": "serein"}
    assert journal.delete(db, "2026-11-19") and not journal.delete(db, "2026-11-19")
    assert not journal.delete(db, "../x")


def test_journal_refuse_vide_et_coupe_trop_long(make_db):
    db = make_db()
    try:
        journal.save(db, "  ")
        raise AssertionError("un résumé vide doit être refusé")
    except journal.JournalError:
        pass
    e = journal.save(db, "a" * 5000)
    assert len(e["text"]) == journal.MAX_TEXT


def test_outils_journal_choisis_selon_la_demande(cfg):
    tools = build_tools(cfg, {})
    assert {"save_journal", "read_journal"} <= names(tools)
    assert "read_journal" not in names(select_tools(tools, "Quelle heure est-il ?"))
    assert "save_journal" in names(select_tools(tools, "c'est tout"))  # fin du journal
    assert "read_journal" in names(select_tools(tools, "Réveil Jarvis : réveille-moi"))
    assert not {"save_journal", "read_journal"} & names(build_tools(cfg, {}, profile="aurore"))


def test_journal_du_soir_bout_en_bout(make_client):
    c = make_client([
        reply("", [("save_journal", {"text": "Bonne journée au travail, puis un ciné avec Léa.", "mood": "content"})]),
        reply("Voilà ta page. Bonne soirée !"),
    ])
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    ev = events_of(c.post(f"/api/conversations/{cid}/messages", json={"text": "c'est tout pour ce soir"}, headers=H).text)
    page = next(e for e in ev if e["type"] == "journal")
    assert page["mood"] == "content" and "ciné" in page["text"]
    data = c.get("/api/journal").json()
    assert data["entries"][0]["text"].startswith("Bonne journée") and data["entries"][0]["day"] == data["today"]
    assert c.delete(f"/api/journal/{data['today']}", headers=H).status_code == 200
    assert c.get("/api/journal").json()["entries"] == []
    assert c.delete("/api/journal/2020-01-01", headers=H).status_code == 404


def test_journal_prive_et_connexion_obligatoire(make_client):
    c = make_client()
    assert c.get("/api/journal").status_code == 401
    assert c.delete("/api/journal/2026-11-20", headers=H).status_code == 401


def test_persona_explique_reveil_et_journal():
    persona = (ROOT / "server" / "persona.md").read_text(encoding="utf-8")
    assert "Réveil Jarvis" in persona and "save_journal" in persona and "3114" in persona


# --------------------------------------------------------------- débat
def test_tour_de_parole():
    assert debate.next_speaker([]) == "nova"
    assert debate.next_speaker([{"who": "nova", "text": "a"}]) == "aurora"
    assert debate.next_speaker([{"who": "nova", "text": "a"}, {"who": "aurora", "text": "b"},
                                {"who": "user", "text": "c"}]) == "nova"


def test_messages_du_debat():
    turns = [{"who": "nova", "text": "Pour !"}, {"who": "aurora", "text": "Contre !"}, {"who": "user", "text": "Et l'été ?"}]
    msgs = debate.build_messages("Les devoirs", turns, "nova", "Alex")
    assert msgs[0]["role"] == "system" and "POUR" in msgs[0]["content"] and "Alex" in msgs[0]["content"]
    assert msgs[1] == {"role": "assistant", "content": "Pour !"}
    assert "Aurora : Contre !" in msgs[2]["content"] and "L'utilisateur : Et l'été ?" in msgs[2]["content"]
    assert "réponds-lui d'abord" in msgs[2]["content"]
    first = debate.build_messages("Les devoirs", [], "nova")
    assert first[-1]["role"] == "user" and "ouvres" in first[-1]["content"]
    verdict = debate.build_messages("Les devoirs", turns, "verdict")
    assert len(verdict) == 2 and "arbitre" in verdict[0]["content"]


def test_historique_nettoye():
    long = [{"who": "nova", "text": "x" * 3000}] * 100
    out = debate.clean_turns(long)
    assert len(out) <= debate.MAX_TURNS and all(len(t["text"]) <= debate.MAX_TURN_CHARS for t in out)
    assert sum(len(t["text"]) for t in out) <= debate.MAX_TOTAL_CHARS
    for bad in ([{"who": "systeme", "text": "x"}], "pas une liste", [5]):
        try:
            debate.clean_turns(bad)
            raise AssertionError(bad)
        except debate.DebateError:
            pass


def test_debat_en_direct(make_client):
    c = make_client([reply("Les devoirs donnent de bonnes habitudes.")])
    login(c)
    r = c.post("/api/debate/turn", json={"topic": "Faut-il des devoirs ?", "turns": []}, headers=H)
    ev = events_of(r.text)
    assert ev[0] == {"type": "start", "who": "nova"} and ev[-1]["type"] == "done"
    assert "".join(e["text"] for e in ev if e["type"] == "text") == "Les devoirs donnent de bonnes habitudes."
    req = c.fake.requests[0]
    assert "tools" not in req and req["max_tokens"] == debate.REPLY_TOKENS


def test_debat_passe_a_une_autre_ia_si_limite(make_client):
    c = make_client([reply("Contre, évidemment.")])
    login(c)
    c.fake.fail["groq"] = RetryableError("Groq : limite gratuite atteinte.")
    turns = [{"who": "nova", "text": "Pour."}, {"who": "user", "text": "Aurora, qu'en penses-tu ?"}]
    ev = events_of(c.post("/api/debate/turn", json={"topic": "Le télétravail", "turns": turns}, headers=H).text)
    assert ev[0]["who"] == "aurora" and ev[-1]["type"] == "done"
    assert c.fake.requests[-1]["_provider"] == "gemini"


def test_debat_verdict_et_refus(make_client):
    c = make_client([reply("Match nul, mais Nova a été plus drôle.")])
    login(c)
    turns = [{"who": "nova", "text": "Pour."}, {"who": "aurora", "text": "Contre."}]
    ev = events_of(c.post("/api/debate/turn", json={"topic": "Les vacances", "turns": turns, "speaker": "verdict"},
                          headers=H).text)
    assert ev[0]["who"] == "verdict" and ev[-1]["type"] == "done"
    assert c.post("/api/debate/turn", json={"topic": "x", "turns": []}, headers=H).status_code == 422
    assert c.post("/api/debate/turn", json={"topic": "Les vacances", "speaker": "systeme"}, headers=H).status_code == 422
    assert c.post("/api/debate/turn", json={"topic": "Faut-il du porno ?"}, headers=H).status_code == 400
    assert c.post("/api/debate/turn", json={"topic": "Les vacances", "turns": [{"who": "x", "text": "y"}]},
                  headers=H).status_code == 400


def test_debat_connexion_obligatoire(make_client):
    c = make_client()
    assert c.post("/api/debate/turn", json={"topic": "Les vacances"}, headers=H).status_code == 401


# --------------------------------------------------------------- les débats entraînent Nova et Aurora
GOOD = "Les devoirs apprennent l'autonomie : réviser seul le soir, c'est apprendre à s'organiser."


def test_exemple_d_entrainement_d_un_debat(make_db):
    base = make_db()
    turns = [{"who": "nova", "text": "Pour !"}, {"who": "aurora", "text": "Contre, car " + "x" * 900},
             {"who": "user", "text": "Et l'été ?"}]
    assert debate.learn(base, "Les devoirs", turns, "nova", GOOD)
    assert not debate.learn(base, "Les devoirs", turns, "nova", GOOD)  # pas de doublon
    ex = debate.trained(base)["nova"][0]
    assert ex["a"] == GOOD and len(ex["q"]) <= debate.MAX_PROMPT
    assert "« Les devoirs »" in ex["q"] and "L'utilisateur : Et l'été ?" in ex["q"] and "pour" in ex["q"]
    for bad in ("Trop court.", "Comme Llama, je pense que les devoirs sont une très bonne chose pour tous.",
                "<think>hmm</think> Les devoirs sont une très bonne chose pour tout le monde vraiment."):
        assert not debate.learn(base, "Les devoirs", turns, "aurora", bad)
    assert debate.train_counts(base) == {"nova": 1, "aurora": 0}


def test_debat_du_proprietaire_entraine_nos_ia(make_client):
    from server import training
    c = make_client([reply(GOOD), reply("Contre : les devoirs creusent les inégalités entre les élèves, c'est prouvé.")])
    login(c)
    c.post("/api/debate/turn", json={"topic": "Faut-il des devoirs ?"}, headers=H)
    c.post("/api/debate/turn", json={"topic": "Faut-il des devoirs ?", "turns": [{"who": "nova", "text": GOOD}]}, headers=H)
    assert debate.train_counts(c.db) == {"nova": 1, "aurora": 1}
    assert c.get("/api/training").json()["debates"] == {"nova": 1, "aurora": 1}
    # l'entraînement (GitHub) les récupère : Nova dans ses exemples de la nuit, Aurora à part
    tok = training.token(c.db)
    auth = {"Authorization": f"Bearer {tok}"}
    nova = [e for e in c.get("/api/training/worker/examples", headers=auth).json() if e["a"] == GOOD]
    assert nova and nova[0]["auto"] is True
    aurora = c.get("/api/training/worker/debates?who=aurora", headers=auth).json()
    assert len(aurora) == 1 and aurora[0]["a"].startswith("Contre")
    assert c.get("/api/training/worker/debates?who=x", headers=auth).status_code == 400
    assert c.get("/api/training/worker/debates?who=aurora").status_code == 401


def test_debat_d_un_proche_n_entraine_pas(make_client):
    from tests.test_family import member_client
    c = make_client([reply(GOOD)])
    login(c)
    lea = member_client(c)
    ev = events_of(lea.post("/api/debate/turn", json={"topic": "Faut-il des devoirs ?"}, headers=H).text)
    assert ev[-1]["type"] == "done"
    assert debate.train_counts(c.db.base if hasattr(c.db, "base") else c.db) == {"nova": 0, "aurora": 0}


def test_script_aurora_garde_10_pour_cent(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT / "training"))
    import debate_data
    data = tmp_path / "coder.jsonl"
    data.write_text("\n".join(json.dumps({"messages": [{"role": "system", "content": "code"}]}) for _ in range(50)) + "\n",
                    encoding="utf-8")
    items = [{"q": f"Débat {i}", "a": f"Réplique {i}"} for i in range(20)]
    monkeypatch.setattr(debate_data, "fetch", lambda: items)
    monkeypatch.setattr(sys, "argv", ["debate_data.py", str(data)])
    debate_data.main()
    lines = data.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 55 and json.loads(lines[0])["messages"][0]["content"] == "code"
    last = json.loads(lines[-1])["messages"]
    assert "Aurora" in last[0]["content"] and last[2]["content"] == "Réplique 19"
