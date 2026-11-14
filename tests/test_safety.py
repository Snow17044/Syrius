"""Garde-fou : pas de contenu sexuel ni violent dans les schémas et les maquettes 3D."""
import pytest

from server import safety
from server.tools import diagram, model3d
from tests.conftest import H, login


@pytest.mark.parametrize("text", ["Femme nue", "modèle NSFW", "un pistolet chargé", "AK47", "scène de meurtre",
                                  "decapitation", "Torture", "porn star", "érotique", "a bloody knife", "bombe"])
def test_contenus_interdits(text):
    assert safety.blocked(text)
    assert safety.blocked({"title": "x", "facts": [text]})


@pytest.mark.parametrize("text", ["Tour Eiffel", "circulation du sang", "route de campagne", "numéro de série",
                                  "violet", "violon", "au sein de l'équipe", "explosion d'un volcan", "chevalier"])
def test_contenus_autorises(text):
    assert not safety.blocked(text)


def test_maquette_et_schema_refuses():
    with pytest.raises(model3d.ModelError):
        model3d.validate({"title": "Pistolet", "search_en": "gun", "prompt_en": "a black gun"})
    with pytest.raises(diagram.DiagramError):
        diagram.validate({"title": "Plan", "nodes": [{"id": "a", "label": "acheter des armes"}]})


def test_routes_3d_refusees(make_client):
    c = make_client()
    login(c)
    r = c.post("/api/model3d/generate", json={"prompt": "a naked woman", "key": "naked woman"}, headers=H)
    assert r.status_code == 400 and "sexuel" in r.json()["detail"]
    assert c.post("/api/model3d/search", json={"query": "rifle"}, headers=H).status_code == 400
