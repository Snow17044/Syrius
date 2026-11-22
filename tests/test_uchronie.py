"""Uchronie : le jeu de stratégie historique (carte, maître du jeu, diplomatie, sauvegarde)."""
import json

from server import uchronie
from tests.conftest import H, login, reply


def events_of(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.split("\n") if line.startswith("data: ")]


START = {
    "date": "1er janvier 1936",
    "summary": "L'Europe se réarme. La crise économique dure.",
    "nations": [
        {"id": "gbr", "name": "Empire britannique", "color": "#c0392b", "leader": "George V", "regime": "monarchie"},
        {"id": "fra", "name": "France", "color": "#2e64fe", "leader": "Albert Sarraut"},
        {"id": "deu", "name": "Reich allemand", "color": "#c0392b", "leader": "Adolf Hitler"},  # même couleur : corrigée
        {"id": "BAD ID!", "name": "x"},
    ],
    "owners": {"ind": "gbr", "pak": "gbr", "dza": "fra", "xxx": "fra", "aut": "nimporte"},
}


def started() -> dict:
    return uchronie.build_start(1936, "", START)


def test_la_carte_est_complete_et_en_francais():
    terr = uchronie.territories()
    assert len(terr) > 180
    assert terr["fra"] == "France" and terr["deu"] == "Allemagne" and terr["usa"] == "États-Unis"
    assert "ata" not in terr  # pas d'Antarctique


def test_mise_en_place_du_monde():
    s = started()
    assert s["owners"]["ind"] == "gbr" and s["owners"]["dza"] == "fra"
    assert s["owners"]["aut"] == "aut"  # propriétaire inconnu : le territoire reste à lui-même
    assert set(s["owners"]) == set(uchronie.territories())
    assert "bad id!" not in s["nations"] and s["nations"]["aut"]["name"] == "Autriche"
    assert s["nations"]["gbr"]["color"] != s["nations"]["deu"]["color"]
    assert s["player"] == "" and s["turn"] == 0


def test_un_tour_change_la_carte():
    s = {**started(), "player": "fra"}
    new, events, advice = uchronie.apply_turn(s, {
        "date": "février 1936",
        "events": [{"title": "L'Anschluss", "text": "L'Autriche est annexée.", "mine": False}],
        "changes": [{"territory": "aut", "to": "deu"}, {"territory": "nulle-part", "to": "deu"},
                    {"territory": "cze", "to": "deu"}],
        "nations": [{"id": "deu", "leader": "Quelqu'un d'autre"}, {"id": "csr", "name": "Nouvelle République"}],
        "summary": "Tension maximale.", "advice": "Renforce l'alliance avec Londres."})
    assert new["owners"]["aut"] == "deu" and new["owners"]["cze"] == "deu"
    assert new["nations"]["deu"]["leader"] == "Quelqu'un d'autre" and new["nations"]["deu"]["name"] == "Reich allemand"
    assert "csr" in new["nations"] and new["turn"] == 1 and new["date"] == "février 1936"
    assert events[0]["title"] == "L'Anschluss" and new["log"][-1]["title"] == "L'Anschluss"
    assert advice.startswith("Renforce")


def test_reponses_d_ia_mal_formees():
    assert uchronie.parse_json('```json\n{"a": [1, 2,],}\n```') == {"a": [1, 2]}
    assert uchronie.parse_json('<think>{"faux": 1}</think> Voici : {"vrai": 1}') == {"vrai": 1}
    for bad in ("pas de json", "[1, 2]", "{cassé"):
        try:
            uchronie.parse_json(bad)
            raise AssertionError(bad)
        except uchronie.GameError:
            pass


def test_l_etat_envoye_par_le_telephone_est_reverifie():
    s = started()
    s["owners"]["fra"] = "inexistante"
    s["nations"]["gbr"]["color"] = "red; background:url(x)"
    s["nations"]["gbr"]["name"] = "x" * 500
    clean = uchronie.clean_state(s)
    assert clean["owners"]["fra"] == "fra"
    assert clean["nations"]["gbr"]["color"].startswith("#") and len(clean["nations"]["gbr"]["name"]) <= 60
    for bad in (None, [], {"nations": {}}, {**s, "player": "personne"}, {**s, "year": 99999}):
        try:
            uchronie.clean_state(bad)
            raise AssertionError(bad)
        except uchronie.GameError:
            pass


def test_ce_que_lit_le_maitre_du_jeu():
    s = {**started(), "player": "fra"}
    msgs = uchronie.turn_messages(s, "Je m'allie au Royaume-Uni.", "mois", [{"name": "Empire britannique", "text": "Oui."}])
    text = msgs[1]["content"]
    assert "gbr = Empire britannique" in text and "ind Inde" in text and "Je m'allie" in text and "un mois" in msgs[0]["content"]
    start = uchronie.start_messages(1936, "Napoléon a gagné à Waterloo")
    assert "fra France" in start[1]["content"] and "Waterloo" in start[1]["content"]
    assert "av. J.-C." in uchronie.start_messages(-50, "")[1]["content"]


def test_nouvelle_partie_de_bout_en_bout(make_client):
    c = make_client([reply(json.dumps(START, ensure_ascii=False))])
    login(c)
    ev = events_of(c.post("/api/uchronie/start", json={"year": 1936}, headers=H).text)
    assert ev[-1]["type"] == "done"
    state = next(e["state"] for e in ev if e["type"] == "state")
    assert state["owners"]["ind"] == "gbr"
    assert c.fake.requests[0]["max_tokens"] == uchronie.START_TOKENS


def test_maitre_du_jeu_illisible_on_redemande(make_client):
    c = make_client([reply("Désolé, je ne sais pas."), reply(json.dumps(START))])
    login(c)
    ev = events_of(c.post("/api/uchronie/start", json={"year": 1936}, headers=H).text)
    assert any(e["type"] == "state" for e in ev) and len(c.fake.requests) == 2


def test_tour_diplomatie_et_sauvegarde(make_client):
    turn = {"date": "février 1936", "events": [{"title": "Pacte franco-britannique", "text": "Signé.", "mine": True}],
            "changes": [], "nations": [], "summary": "Calme.", "advice": "Bien joué."}
    c = make_client([reply(json.dumps(turn)), reply("Londres accepte votre proposition.")])
    login(c)
    s = {**started(), "player": "fra"}
    ev = events_of(c.post("/api/uchronie/turn", json={"state": s, "actions": "Alliance avec Londres", "span": "mois",
                                                       "diplomacy": [{"nation": "gbr", "text": "Ils ont dit oui."}]},
                          headers=H).text)
    new = next(e for e in ev if e["type"] == "state")
    assert new["state"]["turn"] == 1 and new["events"][0]["mine"] and new["advice"] == "Bien joué."
    assert "Ils ont dit oui." in c.fake.requests[0]["messages"][1]["content"]
    ev = events_of(c.post("/api/uchronie/talk", json={"state": s, "nation": "gbr",
                                                       "messages": [{"who": "me", "text": "Alliance ?"}]}, headers=H).text)
    assert "".join(e.get("text", "") for e in ev) == "Londres accepte votre proposition."
    assert "George V" in c.fake.requests[1]["messages"][0]["content"]
    # Refus
    assert c.post("/api/uchronie/turn", json={"state": started(), "actions": "x"}, headers=H).status_code == 400
    assert c.post("/api/uchronie/turn", json={"state": s, "span": "siecle"}, headers=H).status_code == 422
    assert c.post("/api/uchronie/talk", json={"state": s, "nation": "fra", "messages": [{"who": "me", "text": "a"}]},
                  headers=H).status_code == 400
    assert c.post("/api/uchronie/talk", json={"state": s, "nation": "gbr", "messages": [{"who": "them", "text": "a"}]},
                  headers=H).status_code == 400
    assert c.post("/api/uchronie/start", json={"year": 5000}, headers=H).status_code == 422
    # Sauvegarde
    assert c.get("/api/uchronie/save", headers=H).json() == {"state": None}
    assert c.put("/api/uchronie/save", json={"state": new["state"]}, headers=H).json() == {"ok": True}
    assert c.get("/api/uchronie/save", headers=H).json()["state"]["owners"]["ind"] == "gbr"
    c.delete("/api/uchronie/save", headers=H)
    assert c.get("/api/uchronie/save", headers=H).json() == {"state": None}


def test_connexion_obligatoire_et_page(make_client):
    c = make_client()
    assert c.post("/api/uchronie/start", json={"year": 1936}, headers=H).status_code == 401
    assert c.get("/api/uchronie/save", headers=H).status_code == 401
    page = c.get("/uchronie")
    assert page.status_code == 200 and "Uchronie" in page.text
    assert c.get("/static/uchronie-monde.json").json()["territories"][0]["id"]


# ------------------------------------------------------------------ site à part (sans compte)
def site_client(responses=(), per_visitor=3, per_day=100):
    from fastapi.testclient import TestClient

    from server.uchronie_site import Quota, create_site
    from tests.conftest import FakeLLM
    fake = FakeLLM(list(responses))
    app = create_site(llm=fake)
    app.state.quota.__init__(None, per_visitor, per_day)
    assert isinstance(app.state.quota, Quota)
    c = TestClient(app)
    c.fake = fake
    return c


def test_site_a_part_sans_compte():
    c = site_client([reply(json.dumps(START))])
    page = c.get("/")
    assert page.status_code == 200 and "Uchronie" in page.text and "Content-Security-Policy" in page.headers
    assert c.get("/static/uchronie-monde.json").status_code == 200
    assert c.get("/static/app.js").status_code == 404  # rien de Syrius n'est servi
    assert c.get("/api/conversations").status_code == 404
    assert c.get("/api/uchronie/config").json() == {"standalone": True, "left": 3, "per_visitor": 3}
    assert c.post("/api/uchronie/start", json={"year": 1936}).status_code == 403  # anti-CSRF
    ev = events_of(c.post("/api/uchronie/start", json={"year": 1936}, headers=H).text)
    assert ev[0] == {"type": "quota", "left": 2}
    assert next(e for e in ev if e["type"] == "state")["state"]["owners"]["ind"] == "gbr"


def test_site_a_part_limite_par_joueur_et_par_jour():
    turn = {"date": "février 1936", "events": [{"title": "Calme plat", "text": "Rien."}], "summary": "Calme."}
    c = site_client([reply(json.dumps(turn)), reply("Non.")], per_visitor=2)
    s = {**started(), "player": "fra"}
    assert c.post("/api/uchronie/turn", json={"state": s}, headers=H).status_code == 200
    assert c.post("/api/uchronie/talk", json={"state": s, "nation": "gbr", "messages": [{"who": "me", "text": "Paix ?"}]},
                  headers=H).status_code == 200
    r = c.post("/api/uchronie/turn", json={"state": s}, headers=H)
    assert r.status_code == 429 and "Reviens demain" in r.json()["detail"]
    other = {**H, "X-Forwarded-For": "203.0.113.9"}  # un autre joueur, lui, peut jouer…
    assert c.get("/api/uchronie/config", headers=other).json()["left"] == 2
    c.app.state.quota.per_day = 2  # … sauf si le site entier a atteint sa limite du jour
    assert c.post("/api/uchronie/turn", json={"state": s}, headers=other).status_code == 429
    # Une partie invalide ne coûte rien
    c.app.state.quota.per_day = 100
    assert c.post("/api/uchronie/turn", json={"state": started()}, headers=other).status_code == 400
    assert c.get("/api/uchronie/config", headers=other).json()["left"] == 2


def test_chaque_empire_liste_ses_territoires():
    data = {"nations": [
        {"id": "fra", "name": "France", "territories": ["fra", "dza", "sen", "mdg", "inconnu"]},
        {"id": "sun", "name": "Union soviétique", "territories": ["rus", "kaz", "ukr"]},  # id ≠ code de territoire
    ], "owners": {"dza": "gbr", "ind": "gbr"}}
    s = uchronie.build_start(1936, "", data)
    assert s["owners"]["dza"] == "fra" and s["owners"]["mdg"] == "fra"  # la liste de l'empire l'emporte
    assert s["owners"]["kaz"] == "sun" and s["owners"]["rus"] == "sun"
    assert s["owners"]["ind"] == "gbr"  # l'ancien format marche encore
    assert "territories" in uchronie.start_messages(1936, "")[0]["content"]
