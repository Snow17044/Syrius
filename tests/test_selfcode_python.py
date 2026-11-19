"""« Améliorer Syrius » installe les dépendances (empreintes figées pour Python 3.13) : la même version doit servir partout.
Avant : le conteneur de tests utilisait Python 3.12, les empreintes ne correspondaient pas et chaque demande échouait."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def image(path):
    return set(re.findall(r"python:(\d+\.\d+)-slim", (ROOT / path).read_text(encoding="utf-8")))


def test_meme_version_de_python_partout():
    prod = image("Dockerfile")
    assert len(prod) == 1
    for p in (".github/workflows/selfcode.yml", "selfcode/agent.py"):
        assert image(p) == prod, p
