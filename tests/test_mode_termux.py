"""Mode Termux (par défaut) : Aurora donne un seul bloc à coller dans Termux au lieu de coder toute seule."""
from server import atelier
from server.config import Config
from server.tools.registry import build_tools
from tests.conftest import H, login, reply


def names(tools):
    return {t["function"]["name"] for t in tools}


def test_mode_par_defaut_termux(make_db):
    base = make_db()
    assert atelier.get_mode(base) == "termux"
    atelier.set_mode(base, "atelier")
    assert atelier.get_mode(base) == "atelier"


def test_outils_selon_le_mode():
    cfg = Config()
    termux = names(build_tools(cfg, {"aurora_mode": "termux"}, "aurore"))
    atel = names(build_tools(cfg, {"aurora_mode": "atelier"}, "aurore"))
    assert not {"build_web_page", "run_code_project"} & termux
    assert {"build_web_page", "run_code_project"} <= atel


def test_consigne_termux_envoyee_a_aurora(make_client):
    c = make_client([reply("Voici le bloc à coller."), reply("Lancé.")])
    login(c)
    cid = c.post("/api/code/conversations", headers=H).json()["id"]
    c.post(f"/api/code/conversations/{cid}/messages", json={"text": "Fais-moi un script Python de météo"}, headers=H)
    system = c.fake.requests[0]["messages"][0]["content"]
    tools = names(c.fake.requests[0].get("tools", []))
    assert "MODE TERMUX" in system and "cat > fichier <<'EOF'" in system and "pkg install" in system
    assert "run_code_project" not in tools and "build_web_page" not in tools


def test_atelier_refuse_en_mode_termux(make_client):
    c = make_client([reply("", [("build_web_page", {"request": "Un site pour mon club de foot"})]), reply("Ok.")])
    login(c)
    cid = c.post("/api/code/conversations", headers=H).json()["id"]
    c.post(f"/api/code/conversations/{cid}/messages", json={"text": "Un site"}, headers=H)
    assert atelier.items(c.db) == []  # aucun projet lancé
    res = [b["content"] for m in c.db.get_messages(cid) for b in m["content"] if b.get("tool_name") == "build_web_page"]
    assert "Mode Termux" in res[0]


def test_changer_de_mode(make_client):
    c = make_client()
    login(c)
    assert c.get("/api/code/aurora-mode").json() == {"mode": "termux"}
    assert c.put("/api/code/aurora-mode", json={"mode": "atelier"}, headers=H).json() == {"mode": "atelier"}
    assert c.put("/api/code/aurora-mode", json={"mode": "pirate"}, headers=H).status_code == 400
