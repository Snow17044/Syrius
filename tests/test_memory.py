"""Mémoire de Syrius : ajout contrôlé (doublons, secrets, plafond) par l'IA et à la main."""
import pytest

from server import memory
from tests.conftest import H, login


class FakeDB:
    def __init__(self):
        self.items = []

    def list_memories(self):
        return list(self.items)

    def add_memory(self, content):
        self.items.append({"id": len(self.items) + 1, "content": content})
        return len(self.items)


def test_ajout_et_doublon():
    db = FakeDB()
    assert memory.add(db, "J'aime le thé vert") == (1, True)
    assert memory.add(db, "  j'aime   le THÉ vert !") == (1, False)  # même souvenir : pas de doublon
    assert len(db.items) == 1


@pytest.mark.parametrize("fact", [
    "Mon mot de passe est abricot", "Code PIN 4821", "Carte 4970 1012 3456 7890", "IBAN FR76 3000 6000 0112 3456 7890 189",
    "ab", "x" * 301, "Je veux voir du porno"])
def test_souvenirs_refuses(fact):
    with pytest.raises(memory.MemoryError_):
        memory.add(FakeDB(), fact)


def test_plafond():
    db = FakeDB()
    for i in range(memory.MAX_MEMORIES):
        memory.add(db, f"Souvenir numéro {i} sur les vacances")
    with pytest.raises(memory.MemoryError_):
        memory.add(db, "Un de trop pour la mémoire")


def test_route_ajout_manuel(make_client):
    c = make_client()
    login(c)
    r = c.post("/api/memories", headers=H, json={"fact": "Maman est née le 12 mars"})
    assert r.status_code == 200 and r.json()["new"] is True
    assert c.post("/api/memories", headers=H, json={"fact": "Maman est née le 12 mars"}).json()["new"] is False
    assert [m["content"] for m in c.get("/api/memories").json()] == ["Maman est née le 12 mars"]
    bad = c.post("/api/memories", headers=H, json={"fact": "mon mot de passe : 1234"})
    assert bad.status_code == 400 and "mots de passe" in bad.json()["detail"]
    assert c.post("/api/memories", json={"fact": "sans entête"}).status_code in (400, 401, 403)  # protégé (CSRF)
