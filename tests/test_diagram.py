"""Schémas 3D : validation stricte de ce que le modèle envoie."""
import pytest

from server.agent import display_messages
from server.tools import diagram
from server.tools.registry import ToolExecutor, build_tools

BASE = {"title": "Projet", "nodes": [{"id": "c", "label": "Centre"}, {"id": "a", "label": "Branche", "parent": "c"}]}


def test_schema_valide():
    d = diagram.validate({**BASE, "style": "etapes", "links": [{"from": "a", "to": "c", "label": "retour"}]})
    assert d["type"] == "diagram" and d["style"] == "etapes" and len(d["nodes"]) == 2
    assert d["links"] == [{"from": "a", "to": "c", "label": "retour"}]


@pytest.mark.parametrize("bad", [
    None, "texte", {"title": "x"}, {**BASE, "pirate": 1},
    {"title": "x", "nodes": [{"id": "a", "label": "A"}]},
    {"title": "x", "nodes": [{"id": "a", "label": "A"}] * 2},
    {"title": "x", "nodes": [{"id": f"n{i}", "label": "L"} for i in range(31)]},
    {"title": "x", "nodes": [{"id": "a", "label": "A", "script": "x"}, {"id": "b", "label": "B"}]},
    {"title": "x", "nodes": [{"id": "a", "label": 5}, {"id": "b", "label": "B"}]},
    {"title": "", "nodes": BASE["nodes"]},
    {**BASE, "links": "x"},
])
def test_schema_invalide(bad):
    with pytest.raises(diagram.DiagramError):
        diagram.validate(bad)


def test_textes_tronques_et_nettoyes():
    d = diagram.validate({"title": "T" * 500, "nodes": [{"id": "c", "label": "a\n\n  b" + "x" * 200, "note": "n" * 999},
                                                         {"id": "z", "label": "Z", "parent": "c"}]})
    assert len(d["title"]) == diagram.MAX_TITLE
    assert "\n" not in d["nodes"][0]["label"] and len(d["nodes"][0]["label"]) == diagram.MAX_LABEL
    assert len(d["nodes"][0]["note"]) == diagram.MAX_NOTE


def test_parents_inconnus_boucles_et_racines_multiples():
    d = diagram.validate({"title": "x", "style": "inconnu", "nodes": [
        {"id": "r", "label": "R"}, {"id": "a", "label": "A", "parent": "b"}, {"id": "b", "label": "B", "parent": "a"},
        {"id": "c", "label": "C", "parent": "fantome"}, {"id": "d", "label": "D"}, {"id": "e", "label": "E", "parent": "e"}]})
    assert d["style"] == "carte"
    by = {n["id"]: n for n in d["nodes"]}
    assert by["r"]["parent"] == "" and by["c"]["parent"] == "r" and by["d"]["parent"] == "r" and by["e"]["parent"] == "r"
    for n in d["nodes"]:  # plus aucune boucle : chaque idée remonte à la racine
        cur, steps = n, 0
        while cur["parent"]:
            cur, steps = by[cur["parent"]], steps + 1
            assert steps < 10
        assert cur["id"] == "r"


def test_liens_vers_idees_inexistantes_ignores():
    d = diagram.validate({**BASE, "links": [{"from": "a", "to": "zzz"}, {"from": "a", "to": "a"}]})
    assert d["links"] == []


def test_outil_toujours_disponible(cfg):
    names = {t["function"]["name"] for t in build_tools(cfg, {"internet": False})}
    assert "show_diagram" in names


@pytest.mark.anyio
async def test_outil_renvoie_un_evenement(cfg, make_db):
    ex = ToolExecutor(cfg, make_db())
    result, err, ev = await ex.run("show_diagram", BASE)
    assert not err and ev["type"] == "diagram" and "affiché" in result
    result, err, ev = await ex.run("show_diagram", {"title": "x"})
    assert err and ev is None and "INVALID_INPUT" in result


def test_schemas_visibles_dans_l_historique():
    stored = [
        {"role": "user", "content": [{"type": "text", "text": "fais un schéma"}]},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "1", "name": "show_diagram", "input": BASE}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": "ok"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Voilà."},
                                          {"type": "tool_use", "id": "2", "name": "show_diagram", "input": {"bad": 1}}]},
    ]
    out = display_messages(stored)
    assert out[-1]["text"] == "Voilà." and len(out[-1]["diagrams"]) == 1
    assert out[-1]["diagrams"][0]["title"] == "Projet"


def test_dessin_sans_html():
    src = open("web/diagram.js", encoding="utf-8").read()
    for danger in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "new Function"):
        assert danger not in src


def test_types_d_idees():
    d = diagram.validate({"title": "x", "nodes": [{"id": "c", "label": "C", "kind": "objectif"},
                                                  {"id": "a", "label": "A", "parent": "c", "kind": "<script>"}]})
    assert d["nodes"][0]["kind"] == "objectif" and d["nodes"][1]["kind"] == ""


# ---------------------------------------------------------------- schéma écrit en texte
import json as _json

PLAN = {"title": "Permis", "nodes": [{"id": "c", "label": "Avoir le permis"},
                                      {"id": "p1", "label": "Code", "parent": "c"}]}


@pytest.mark.parametrize("text", [
    "Voici ton schéma :\n```json\n" + _json.dumps(PLAN) + "\n```\nBonne chance !",
    "Voici ton schéma :\n```\n" + _json.dumps({"name": "show_diagram", "arguments": PLAN}) + "\n```\nBonne chance !",
    "Voici ton schéma : show_diagram(" + _json.dumps(PLAN) + ")\nBonne chance !",
    "Voici ton schéma : " + _json.dumps({"name": "show_diagram", "parameters": _json.dumps(PLAN)}) + "\nBonne chance !",
])
def test_schema_ecrit_en_texte_est_dessine(text):
    cleaned, ev = diagram.extract_from_text(text)
    assert ev and ev["type"] == "diagram" and ev["title"] == "Permis"
    assert "nodes" not in cleaned and cleaned.startswith("Voici ton schéma") and cleaned.endswith("Bonne chance !")


@pytest.mark.parametrize("text", ["Bonjour", "Un objet {\"a\": 1} sans schéma", "```json\n{\"nodes\": \"x\"}\n```",
                                  "{\"nodes\": [1, 2]}", "{ pas du json nodes"])
def test_texte_normal_inchange(text):
    assert diagram.extract_from_text(text) == (text, None)


@pytest.mark.anyio
async def test_agent_dessine_le_schema_ecrit_en_texte(make_client):
    from tests.conftest import H, login, reply
    c = make_client([reply("Voilà :\n```json\n" + _json.dumps(PLAN) + "\n```")])
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    r = c.post(f"/api/conversations/{cid}/messages", json={"text": "fais un schéma"}, headers=H)
    events = [_json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]
    types = [e["type"] for e in events]
    assert "diagram" in types and "text_replace" in types
    assert next(e for e in events if e["type"] == "text_replace")["text"] == "Voilà :"
    conv = c.get(f"/api/conversations/{cid}").json()
    last = conv["messages"][-1]
    assert last["text"] == "Voilà :" and last["diagrams"][0]["title"] == "Permis"


def _chat(c, text):
    from tests.conftest import H, login
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    return c.post(f"/api/conversations/{cid}/messages", json={"text": text}, headers=H)


def test_demande_de_schema_force_l_outil(make_client):
    from tests.conftest import reply
    c = make_client([reply(tool_calls=[("show_diagram", PLAN)]), reply("Voilà ton plan.")])
    r = _chat(c, "Fais-moi un SCHÉMA pour passer le permis")
    assert '"type": "diagram"' in r.text
    first, second = c.fake.requests
    assert first["tool_choice"] == {"type": "function", "function": {"name": "show_diagram"}}
    assert "tool_choice" not in second  # seulement pour la première étape


def test_message_normal_sans_obligation(make_client):
    from tests.conftest import reply
    c = make_client([reply("Bonjour !")])
    _chat(c, "Quelle heure est-il ?")
    assert "tool_choice" not in c.fake.requests[0]
