"""Interface « Soft » : icônes dessinées (pas d'emoji), fichiers servis et mis en cache."""
import re

EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿⬀-⯿]")


def test_pas_d_emoji_dans_l_interface():
    html = open("web/index.html", encoding="utf-8").read()
    assert not EMOJI.findall(html)
    assert 'data-icon="mic"' in html and "/static/icons.js" in html


def test_icones_servies_et_en_cache():
    from server.app import STATIC_FILES
    assert STATIC_FILES.get("icons.js") == "text/javascript"
    sw = open("web/sw.js", encoding="utf-8").read()
    assert '"/static/icons.js"' in sw


def test_icones_sans_donnees_exterieures():
    # Les dessins sont des constantes : aucune donnée reçue n'est insérée comme HTML.
    js = open("web/icons.js", encoding="utf-8").read()
    assert js.count("innerHTML") == 1 and "s.innerHTML = P[name] || P.diamond" in js


def test_appel_seulement_apres_confirmation_dans_la_carte():
    js = open("web/app.js", encoding="utf-8").read()
    body = js.split("function callCard(")[1].split("\n}\n")[0]
    assert 'accept.addEventListener("click", go)' in body and "runDevice(ev)" in body.split("const go")[1]
    assert body.index("runDevice(ev)") > body.index("const go")
