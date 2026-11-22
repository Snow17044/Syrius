"""Cohérence de la page web : identifiants uniques, et tout élément cherché par le code existe dans la page."""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
HTML = (WEB / "index.html").read_text(encoding="utf-8")
IDS = re.findall(r'\bid="([^"]+)"', HTML)


def test_identifiants_uniques():
    assert sorted({i for i in IDS if IDS.count(i) > 1}) == []


def test_elements_cherches_par_le_code_existent():
    # Créés par le code lui-même (pas dans index.html)
    dynamic = set()
    for js in ("app.js", "voice.js", "local.js", "hud.js", "diagram.js", "model3d.js", "journal.js", "debate.js", "faces.js", "atelier-test.js"):
        dynamic |= set(re.findall(r'\.id\s*=\s*["\']([\w-]+)["\']', (WEB / js).read_text(encoding="utf-8")))
    missing = {}
    for js in ("app.js", "voice.js", "local.js", "journal.js", "debate.js", "faces.js"):
        src = (WEB / js).read_text(encoding="utf-8")
        for m in re.finditer(r'\$\(\s*["\']#([\w-]+)["\']\s*\)', src):
            if m.group(1) not in IDS and m.group(1) not in dynamic:
                missing.setdefault(js, set()).add(m.group(1))
    assert missing == {}, f"éléments introuvables dans la page : {missing}"


def test_chaque_onglet_a_son_panneau():
    tabs = re.findall(r'data-tab="([\w-]+)"', HTML)
    panels = re.findall(r'data-panel="([\w-]+)"', HTML)
    assert tabs and tabs == panels


def test_syrius_code_ne_deborde_pas_de_l_ecran():
    """Bug réel : un long code élargissait la page (×4) ; le téléphone dézoomait et le bouton Envoyer sortait de l'écran."""
    css = (WEB / "code.css").read_text(encoding="utf-8")
    assert ".c-app > *, .c-tab > *, #main > * { min-width: 0; }" in css and ".c-main { flex: 1; position: relative; min-height: 0; min-width: 0; }" in css
