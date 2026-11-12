"""Maquettes 3D : validation stricte de ce que le modèle envoie."""
import hashlib
import json

import pytest

from server.agent import display_messages
from server.tools import model3d
from server.tools.registry import ToolExecutor, build_tools
from tests.conftest import H, login, reply

TOUR = {"title": "Tour", "parts": [{"shape": "box", "pos": [0, 5, 0], "size": [2, 10, 2], "color": "#8d6e4f"},
                                   {"shape": "cone", "pos": [0, 12, 0], "size": [1, 4], "color": "gris"}]}


def test_maquette_valide_et_normalisee():
    m = model3d.validate({**TOUR, "facts": ["Hauteur : 330 m", 5, ""], "description": "Une tour."})
    assert m["type"] == "model" and len(m["parts"]) == 2 and m["facts"] == ["Hauteur : 330 m"]
    cone = m["parts"][1]
    assert cone["size"] == [1.0, 4.0, 1.0] and cone["rot"] == [0.0, 0.0, 0.0] and cone["color"] == "#94a3b8"


def test_valeurs_dangereuses_bornees():
    m = model3d.validate({"title": "x", "parts": [
        {"shape": "box", "pos": [1e308, float("nan"), "a"], "size": [-5, 1e9, True], "rot": [9999, 0, 0],
         "color": "url(javascript:alert(1))", "name": "<img src=x>" * 10},
        {"shape": "teapot"}, "pas un objet", {"shape": "sphere", "size": 3}]})
    box, sphere = m["parts"]
    assert box["pos"] == [model3d.MAX_COORD, 0.0, 0.0]
    assert box["size"] == [0.001, model3d.MAX_SIZE, 1.0] and box["rot"][0] == 360.0
    assert box["color"] == "#38d9ff" and len(box["name"]) == 40
    assert sphere["size"] == [3.0, 3.0, 3.0]


@pytest.mark.parametrize("bad", [None, "x", {"parts": TOUR["parts"]}, {"title": "x", "parts": []},
                                 {"title": "x", "parts": [{"shape": "teapot"}]}, {"title": "x", "parts": "box"}])
def test_maquette_invalide(bad):
    with pytest.raises(model3d.ModelError):
        model3d.validate(bad)


def test_nombre_de_pieces_limite():
    m = model3d.validate({"title": "x", "parts": [{"shape": "box"}] * 1000})
    assert len(m["parts"]) == model3d.MAX_PARTS


def test_outil_toujours_disponible(cfg):
    assert "show_model" in {t["function"]["name"] for t in build_tools(cfg, {"internet": False})}


@pytest.mark.anyio
async def test_outil_renvoie_un_evenement(cfg, make_db):
    ex = ToolExecutor(cfg, make_db())
    result, err, ev = await ex.run("show_model", TOUR)
    assert not err and ev["type"] == "model" and "affichée" in result
    result, err, ev = await ex.run("show_model", {"title": "x"})
    assert err and ev is None


def test_maquette_ecrite_en_texte():
    text = "Voici :\n```json\n" + json.dumps({"name": "show_model", "arguments": TOUR}) + "\n```\nSympa !"
    cleaned, ev = model3d.extract_from_text(text)
    assert ev and ev["title"] == "Tour" and cleaned == "Voici :\n\nSympa !"


def _chat(c, text):
    login(c)
    cid = c.post("/api/conversations", headers=H).json()["id"]
    return cid, c.post(f"/api/conversations/{cid}/messages", json={"text": text}, headers=H)


@pytest.mark.parametrize("ask", ["Montre-moi la tour Eiffel en 3D", "fais une maquette d'une fusée",
                                 "affiche un hologramme de voiture"])
def test_demande_3d_force_l_outil(make_client, ask):
    c = make_client([reply(tool_calls=[("show_model", TOUR)]), reply("La voilà.")])
    cid, r = _chat(c, ask)
    assert '"type": "model"' in r.text
    assert c.fake.requests[0]["tool_choice"]["function"]["name"] == "show_model"
    last = c.get(f"/api/conversations/{cid}").json()["messages"][-1]
    assert last["diagrams"][0]["type"] == "model"


def test_schema_3d_reste_un_schema(make_client):
    c = make_client([reply("ok")])
    _chat(c, "fais-moi un schéma 3D de mon projet")
    assert c.fake.requests[0]["tool_choice"]["function"]["name"] == "show_diagram"


def test_maquette_texte_dans_l_historique():
    stored = [{"role": "assistant", "content": [{"type": "text", "text": "Voilà"},
                                                {"type": "model", "data": TOUR}]}]
    assert display_messages(stored)[0]["diagrams"][0]["title"] == "Tour"


def test_three_intact_et_sans_html():
    digest = hashlib.sha256(open("web/three.min.js", "rb").read()).hexdigest()
    assert digest == "3b3a1c97de3ce65ec5b28c28d9f2805a738e9651622691ba771aa95c79d41d51"
    src = open("web/model3d.js", encoding="utf-8").read()
    for danger in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "new Function"):
        assert danger not in src
