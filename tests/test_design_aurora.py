"""Aurora soigne le design : guide de design dans toutes ses consignes, et contrôle automatique dans le banc d'essai."""
from pathlib import Path

from server import atelier
from server.agent import TERMUX_MODE

ROOT = Path(__file__).resolve().parents[1]


def test_guide_de_design_partout():
    for text in (atelier.WEB_SYSTEM, TERMUX_MODE):
        assert atelier.DESIGN_GUIDE in text
    for rule in ("4.5:1", "44 px", "prefers-color-scheme", "variables CSS", "max-width"):
        assert rule in atelier.DESIGN_GUIDE
    assert len(atelier.WEB_SYSTEM) < 8000  # la consigne entière arrive à l'IA (limite du relais)


def test_banc_d_essai_controle_le_design():
    js = (ROOT / "web/atelier-test.js").read_text(encoding="utf-8")
    for check in ('meta[name="viewport"]', "times", "fontSize) < 15", 'querySelector("h1")', "< 36", "4.5", 'hasAttribute("alt")'):
        assert check in js, check
    assert '"Design : " + d' in js  # remontées comme des erreurs à corriger
