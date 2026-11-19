"""Répartition du travail (téléphone / grandes IA) : test du détecteur d'ordres écrit en JavaScript."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js absent")
def test_detecteur_d_ordres():
    r = subprocess.run(["node", str(Path(__file__).parent / "js" / "route_check.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js absent")
def test_texte_lu_a_voix_haute():
    r = subprocess.run(["node", str(Path(__file__).parent / "js" / "speech_check.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
