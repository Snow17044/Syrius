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


def test_images_violentes_refusees(make_client):
    from server.tools.device import DeviceInputError, build_action
    with pytest.raises(DeviceInputError):
        build_action("phone_image", {"prompt": "a soldier with a gun and blood", "caption": "x"})
    event, _ = build_action("phone_image", {"prompt": "a cute cat sleeping", "caption": "Chat"})
    assert event["params"]["prompt"] == "a cute cat sleeping"
    c = make_client()
    login(c)
    r = c.post("/api/image", json={"prompt": "a violent murder scene"}, headers=H)
    assert r.status_code == 400 and "violent" in r.json()["detail"]


def test_filtre_identique_hors_ligne():
    """La liste du téléphone (hors ligne) est la même que celle du serveur."""
    import re
    from pathlib import Path
    js = Path(__file__).parents[1].joinpath("web", "app.js").read_text(encoding="utf-8")
    words = set(re.findall(r'"([a-z0-9]+)"', re.search(r"UNSAFE_WORDS = new Set\(\[(.*?)\]\)", js).group(1)))
    assert words == safety._WORDS
