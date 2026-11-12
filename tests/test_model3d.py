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


# ---------------------------------------------------------------- format compact + symétrie
def test_format_compact_une_ligne_par_piece():
    m = model3d.validate({"title": "T", "parts": [
        "box 0,30,0 8,60,8 0,0,-20 #8d6e4f Pilier nord 2",
        "cone 0,80 2,10 gris",
        "sphere 0,1,0 3",
        "teapot 0,0,0 1",
        "",
    ]})
    box, cone, sphere = m["parts"]
    assert box == {"shape": "box", "pos": [0.0, 30.0, 0.0], "size": [8.0, 60.0, 8.0], "rot": [0.0, 0.0, -20.0],
                   "color": "#8d6e4f", "name": "Pilier nord 2"}
    assert cone["pos"] == [0.0, 80.0, 0.0] and cone["size"] == [2.0, 10.0, 1.0] and cone["color"] == "#94a3b8"
    assert sphere["size"] == [3.0, 3.0, 3.0]


def test_symetrie_xz_cree_4_pieces():
    m = model3d.validate({"title": "T", "parts": ["box 40,30,40 8,60,8 10,0,-20 #8d6e4f sym:xz Pilier"]})
    pos = sorted(tuple(p["pos"]) for p in m["parts"])
    assert pos == [(-40, 30, -40), (-40, 30, 40), (40, 30, -40), (40, 30, 40)]
    rots = {tuple(p["pos"]): p["rot"] for p in m["parts"]}
    assert rots[(40.0, 30.0, 40.0)] == [10.0, 0.0, -20.0] and rots[(-40.0, 30.0, 40.0)] == [10.0, -0.0, 20.0]
    assert rots[(40.0, 30.0, -40.0)] == [-10.0, -0.0, -20.0]


def test_symetrie_ne_depasse_pas_la_limite():
    m = model3d.validate({"title": "T", "parts": ["box 1,1,1 1 sym:xz"] * 500})
    assert len(m["parts"]) == model3d.MAX_PARTS


def test_demande_3d_legere(make_client):
    c = make_client([reply(tool_calls=[("show_model", {"title": "T", "parts": ["box 0,1,0 1"]})]), reply("ok")])
    _chat(c, "montre la tour Eiffel en 3D")
    first, second = c.fake.requests
    assert [t["function"]["name"] for t in first["tools"]] == ["show_model"]  # seulement l'outil utile
    assert first["max_tokens"] <= 3000 and len(second["tools"]) > 5


def test_demande_trop_lourde_reessaie_en_plus_leger(make_client):
    from server.llm import TooLargeError
    c = make_client([reply("Réponse légère.")])
    calls = {"n": 0}
    orig = c.fake.stream_chat

    async def flaky(provider, body):
        calls["n"] += 1
        if calls["n"] == 1:
            c.fake.requests.append({**body, "_provider": provider.name})
            raise TooLargeError("Groq : demande trop lourde pour sa limite gratuite.")
        async for chunk in orig(provider, body):
            yield chunk
    c.fake.stream_chat = flaky
    c.agent.llm = c.fake
    _cid, r = _chat(c, "bonjour")
    assert "légère." in r.text
    assert [q["_provider"] for q in c.fake.requests] == ["groq", "groq"]  # même cerveau, sans changer
    assert c.fake.requests[1]["max_tokens"] < c.fake.requests[0]["max_tokens"]


def test_ia_hors_ligne_securisee():
    src = open("web/local.js", encoding="utf-8").read()
    for danger in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "new Function"):
        assert danger not in src
    java = open("android/app/src/main/java/fr/syrius/app/LocalAI.java", encoding="utf-8").read()
    # seuls deux fichiers connus, vérifiés par empreinte SHA-256 avant usage
    assert java.count('.task",') == 2 and "MessageDigest.getInstance(\"SHA-256\")" in java
    assert "https://huggingface.co/litert-community/" in java and "http://" not in java
    main = open("android/app/src/main/java/fr/syrius/app/MainActivity.java", encoding="utf-8").read()
    for fn in ("localInfo", "localDownload", "localCancel", "localDelete", "localChat", "localStop"):
        body = main.split("public " + ("String " if fn in ("localInfo", "localDownload", "localChat") else "void ") + fn)[1][:400]
        assert "trusted()" in body, fn
