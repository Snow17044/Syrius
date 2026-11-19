"""Les IA ont leur nom : Nova 0.5 (application Syrius) et Aurora 0.1 (Syrius Code)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(p):
    return (ROOT / p).read_text(encoding="utf-8")


def test_nova_et_aurora_se_presentent():
    assert read("server/persona.md").startswith("Tu es Nova (version 0.5")
    assert read("server/aurore.md").startswith("Tu es Aurora (version 0.1")
    assert "Aurora 0.1" in read("web/code.html") and "Nova 0.5" in read("web/index.html")


def test_plus_aucune_trace_de_l_ancien_nom():
    for p in ("server/persona.md", "server/aurore.md", "web/code.html", "web/code.js", "web/index.html", "web/local.js",
              "README.md", "selfcode/GUIDE.md", "training/make_dataset.py"):
        assert "Aurore" not in read(p), p
    assert "Tu es Syrius" not in read("web/local.js") and "Tu es Syrius" not in read("training/make_dataset.py")


def test_le_systeme_du_telephone_suit_celui_de_l_entrainement():
    assert "Tu es Nova, l'assistant personnel" in read("web/local.js")
    assert "Tu es Nova, l'assistant personnel" in read("training/make_dataset.py")
    assert '"Nova"' in read("training/eval_set.py")
