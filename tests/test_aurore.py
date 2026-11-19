"""Syrius Code : Aurora (IA pro), tableaux de bord, discussions séparées, réservé au propriétaire."""
import json

import pytest

from server import agent as agent_mod
from server.config import Config
from server.tools import dashboard, registry
from server.tools.registry import build_tools
from tests.conftest import H, login, reply
from tests.test_agent import events_of
from tests.test_family import member_client

GOOD = {"title": "Ventes", "kpis": [{"label": "Total", "value": "6 580 €", "trend": "up"}],
        "charts": [{"type": "bar", "title": "Par semaine", "labels": ["S1", "S2", "S3"],
                    "series": [{"name": "Ventes", "values": [1200, 1850, 1430]}]},
                   {"type": "pie", "title": "Part", "labels": ["A", "B"], "series": [{"name": "x", "values": [30, 70]}]}],
        "table": {"columns": ["Semaine", "€"], "rows": [["S1", 1200], ["S2", 1850]]}}


def names(tools):
    return {t["function"]["name"] for t in tools}


def test_les_outils_d_aurore_et_de_syrius_sont_separes():
    cfg, s = Config(), {"internet": True}
    aurore, syrius = names(build_tools(cfg, s, "aurore")), names(build_tools(cfg, s))
    assert {"scan_site", "show_dashboard", "web_search", "show_diagram"} <= aurore
    assert not any(n.startswith("phone_") for n in aurore) and "remember" not in aurore
    assert "scan_site" not in syrius and "show_dashboard" not in syrius  # le scanner n'existe plus dans Syrius
    assert any(n.startswith("phone_") for n in syrius)


def test_validation_des_tableaux_de_bord():
    ok = dashboard.validate(GOOD)
    assert ok["type"] == "dashboard" and len(ok["charts"]) == 2 and ok["table"]["rows"][0] == ["S1", 1200.0]
    bad = [{"title": "x"}, {**GOOD, "extra": 1}, {"title": "x", "charts": [{"type": "radar", "labels": ["a", "b"], "series": []}]},
           {"title": "x", "charts": [{"type": "bar", "title": "t", "labels": ["a", "b"], "series": [{"name": "s", "values": [1]}]}]},
           {"title": "x", "charts": [{"type": "pie", "title": "t", "labels": ["a", "b"], "series": [{"name": "s", "values": [1, -2]}]}]},
           {"title": "x", "charts": [{"type": "bar", "title": "t", "labels": ["a", "b"], "series": [{"name": "s", "values": [1, "2"]}]}]},
           {"title": "x", "kpis": [{"label": "a", "value": {"x": 1}}]}, "pas un dict", {"title": "", "kpis": [{"label": "a", "value": "1"}]}]
    for b in bad:
        with pytest.raises(dashboard.DashboardError):
            dashboard.validate(b)
    huge = dashboard.validate({"title": "t" * 200, "kpis": [{"label": "k" * 99, "value": "1"}] * 20})
    assert len(huge["title"]) == 80 and len(huge["kpis"]) == 6 and len(huge["kpis"][0]["label"]) == 30


def test_aurore_repond_avec_sa_consigne_et_ses_outils(make_client):
    c = make_client([reply("Bonjour, je suis Aurora.")])
    login(c)
    cid = c.post("/api/code/conversations", headers=H).json()["id"]
    ev = events_of(c.post(f"/api/code/conversations/{cid}/messages", json={"text": "Salut"}, headers=H).text)
    assert any(e["type"] == "text" for e in ev) and any(e["type"] == "done" for e in ev)
    req = c.fake.requests[0]
    sysmsg = req["messages"][0]["content"]
    assert "Aurora" in sysmsg and "Souvenirs" not in sysmsg  # pas de souvenirs personnels de Syrius
    assert not any(t["function"]["name"].startswith("phone_") for t in req.get("tools", []))


def test_aurore_construit_un_tableau_de_bord(make_client):
    c = make_client([reply("", [("show_dashboard", GOOD)]), reply("Voilà ton tableau.")])
    login(c)
    cid = c.post("/api/code/conversations", headers=H).json()["id"]
    ev = events_of(c.post(f"/api/code/conversations/{cid}/messages",
                          json={"text": "Voici mes ventes par semaine : 1200, 1850, 1430. Fais un tableau de bord."}, headers=H).text)
    dash = [e for e in ev if e["type"] == "dashboard"]
    assert dash and dash[0]["title"] == "Ventes" and dash[0]["charts"][0]["type"] == "bar"
    hist = c.get(f"/api/code/conversations/{cid}").json()["messages"]
    assert any(d.get("type") == "dashboard" for m in hist if m["role"] == "assistant" for d in m.get("diagrams", []))


def test_discussions_separees_de_syrius(make_client):
    c = make_client([reply("ok")])
    login(c)
    code_id = c.post("/api/code/conversations", headers=H).json()["id"]
    syr_id = c.post("/api/conversations", headers=H).json()["id"]
    assert [x["id"] for x in c.get("/api/code/conversations").json()] == [code_id]
    assert [x["id"] for x in c.get("/api/conversations").json()] == [syr_id]  # Aurora n'apparaît pas dans Syrius
    assert c.get(f"/api/code/conversations/{syr_id}").status_code == 404  # et réciproquement
    assert c.delete(f"/api/code/conversations/{code_id}", headers=H).status_code == 200
    assert c.get("/api/code/conversations").json() == []


def test_reserve_au_proprietaire(make_client):
    owner = make_client()
    login(owner)
    member = member_client(owner)
    for method, url in (("get", "/api/code/conversations"), ("post", "/api/code/conversations"), ("get", "/api/code/dashboards"),
                        ("post", "/api/code/dashboards"), ("get", "/api/sitescan")):
        r = getattr(member, method)(url, headers=H, **({"json": {"spec": GOOD}} if "dashboards" in url and method == "post" else {}))
        assert r.status_code == 403, (url, r.status_code)
    anon = type(owner)(owner.app, base_url="https://testserver")
    assert anon.get("/api/code/conversations").status_code == 401
    assert owner.get("/code").status_code == 200 and b"Syrius Code" in owner.get("/code").content  # la page elle-même est publique


def test_tableaux_enregistres(make_client):
    c = make_client()
    login(c)
    saved = c.post("/api/code/dashboards", headers=H, json={"spec": GOOD})
    assert saved.status_code == 200 and saved.json()["spec"]["title"] == "Ventes"
    assert c.post("/api/code/dashboards", headers=H, json={"spec": {"title": "vide"}}).status_code == 400
    lst = c.get("/api/code/dashboards").json()
    assert len(lst) == 1 and lst[0]["id"] == saved.json()["id"]
    assert c.delete(f"/api/code/dashboards/{lst[0]['id']}", headers=H).status_code == 200
    assert c.delete("/api/code/dashboards/inconnu", headers=H).status_code == 404
    for _ in range(35):
        c.post("/api/code/dashboards", headers=H, json={"spec": GOOD})
    assert len(c.get("/api/code/dashboards").json()) == 30  # plafond


def test_historique_des_scans(make_client):
    from server import sitescan
    from tests.test_sitescan import Mem, site
    base = Mem()
    for i, t in enumerate((1000, 1200, 1400)):
        sitescan.run(base, "syrius.exemple.fr", own_hosts=("syrius.exemple.fr",), fetcher=site_for("syrius.exemple.fr"), now=t)
    hist = sitescan.public_entries(base, "syrius.exemple.fr")[0]["history"]
    assert [h["at"] for h in hist] == [1000, 1200, 1400] and all("score" in h for h in hist)


def site_for(domain):
    from tests.test_sitescan import FakeSite
    return FakeSite({}, domain)


def test_page_code_coherente():
    import re
    from pathlib import Path
    web = Path(__file__).resolve().parents[1] / "web"
    html = (web / "code.html").read_text(encoding="utf-8")
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert sorted({i for i in ids if ids.count(i) > 1}) == []
    js = (web / "code.js").read_text(encoding="utf-8")
    missing = {m for m in re.findall(r'\$\(\s*["\']#([\w-]+)["\']\s*\)', js) if m not in ids}
    assert missing == set(), missing
    assert "style=" not in html  # la politique de sécurité interdit les styles dans la page
    tabs = re.findall(r'data-go="([\w-]+)"', html)
    assert tabs == re.findall(r'<section id="tab-([\w-]+)"', html)
    assert 'data-theme="nature"' in (web / "code.css").read_text(encoding="utf-8").replace("[data-theme=\"nature\"]", 'data-theme="nature"')
