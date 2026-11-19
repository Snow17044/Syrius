"""Simulateur de drone : le pilote automatique stabilise, tient sa position et se pose tout seul, même avec du vent,
des rafales, des capteurs bruités, une batterie faible ou une liaison perdue. SIMULATION SEULEMENT."""
import math

import pytest

from drone.commander import Commander, Limits, RefusedCommand
from drone.control import Noise
from drone.sim import Wind


def fly(c, altitude=5.0, secs=15):
    c.command({"cmd": "takeoff", "altitude": altitude})
    c.run(secs)
    return c


def land(c, timeout=60):
    c.command({"cmd": "land"})
    return c.run_until(lambda c: c.ap.mode == "ATTERRI", timeout)


def tilt(c):
    return max(abs(c.quad.s.att[0]), abs(c.quad.s.att[1]))


def test_decolle_et_se_stabilise_sans_vent():
    c = fly(Commander())
    s = c.quad.s
    assert abs(s.pos[2] - 5.0) < 0.3 and math.hypot(s.pos[0], s.pos[1]) < 0.3
    assert tilt(c) < 0.05 and c.ap.mode == "STATIONNAIRE"


def test_se_stabilise_depuis_une_forte_inclinaison():
    """Poussé à 25° dès le départ en l'air, avec une rotation en cours : il se remet à plat tout seul."""
    c = Commander()
    c.command({"cmd": "takeoff", "altitude": 8})
    c.run(8)
    s = c.quad.s
    s.att[0], s.att[1] = math.radians(25), math.radians(-20)
    s.rates[0] = 2.0
    c.run(6)
    assert tilt(c) < 0.05 and abs(s.pos[2] - 8) < 0.5 and not s.crashed


@pytest.mark.parametrize("wind", [(5, 0, 0), (0, -6, 0), (4, 4, 1)])
def test_tient_sa_position_dans_le_vent(wind):
    c = fly(Commander(wind=Wind(steady=wind, gust=1.5, seed=3)), secs=25)
    s = c.quad.s
    assert math.hypot(s.pos[0], s.pos[1]) < 1.0 and abs(s.pos[2] - 5) < 0.6 and not s.crashed


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_atterrit_tout_seul_avec_rafales_et_capteurs_bruites(seed):
    c = fly(Commander(wind=Wind(steady=(3, -2, 0), gust=2.0, seed=seed), noise=Noise(seed=seed)), altitude=12, secs=20)
    assert land(c)
    td = c.quad.touchdown
    assert td["speed"] < 0.6 and td["tilt"] < 0.25 and c.landing_error() < 1.5  # posé doucement, presque à plat (le vent impose ~9° d'inclinaison), près du point visé
    assert not c.quad.s.crashed and c.ap.mode == "ATTERRI"


def test_atterrissage_depuis_une_grande_hauteur():
    c = fly(Commander(), altitude=30, secs=40)
    assert land(c, timeout=120) and c.quad.touchdown["speed"] < 0.6


def test_atterrissage_pendant_un_deplacement():
    c = fly(Commander(wind=Wind(steady=(2, 0, 0), gust=1.0)))
    c.command({"cmd": "goto", "x": 20, "y": 10, "z": 8})
    c.run(4)  # en plein mouvement
    assert land(c, 80)
    assert c.quad.touchdown["speed"] < 0.6 and not c.quad.s.crashed
    assert c.landing_error() < 6.0  # posé à la verticale de l'endroit où l'ordre a été donné (il a un peu dérivé)


def test_aller_a_un_point_puis_stationnaire():
    c = fly(Commander())
    c.command({"cmd": "goto", "x": 15, "y": -10, "z": 6})
    c.run(25)
    s = c.quad.s
    assert math.hypot(s.pos[0] - 15, s.pos[1] + 10) < 0.8 and abs(s.pos[2] - 6) < 0.5


def test_batterie_faible_atterrissage_automatique():
    c = Commander()
    c.quad.s.battery = 40.0
    fly(c, secs=5)
    c.quad.s.battery = 24.0  # la batterie passe sous le seuil
    c.run(1)
    assert any("batterie faible" in e for e in c.events)
    with pytest.raises(RefusedCommand, match="sécurité active"):
        c.command({"cmd": "goto", "x": 5, "y": 5, "z": 5})  # plus d'ordres sauf « land »
    assert c.run_until(lambda c: c.ap.mode == "ATTERRI", 60) and c.quad.touchdown["speed"] < 0.6


def test_liaison_perdue_atterrissage_automatique():
    c = Commander(wind=Wind(steady=(1, 1, 0), gust=1.0))
    c.watch_link = True
    fly(c, secs=2)
    c.run(5)  # plus aucun ordre pendant 5 s (seuil : 3 s)
    assert any("liaison perdue" in e for e in c.events)
    assert c.run_until(lambda c: c.ap.mode == "ATTERRI", 60) and not c.quad.s.crashed


def test_sortie_de_zone_declenche_l_atterrissage():
    c = Commander(limits=Limits(fence_radius=10))
    fly(c)
    c.quad.s.pos[0] = 20.0  # poussé hors de la zone (par exemple par une grosse rafale)
    c.run(0.5)
    assert any("hors de la zone" in e for e in c.events)


def test_ordres_dangereux_ou_invalides_refuses():
    c = Commander()
    for bad in ({"cmd": "takeoff", "altitude": 500}, {"cmd": "takeoff", "altitude": -3}, {"cmd": "takeoff"},
                {"cmd": "takeoff", "altitude": "haut"}, {"cmd": "takeoff", "altitude": float("nan")},
                {"cmd": "takeoff", "altitude": True}, {"cmd": "moteurs", "thrust": 99}, {"cmd": "goto", "x": 1, "y": 1, "z": 3},
                {"nope": 1}, "décolle"):
        with pytest.raises(RefusedCommand):
            c.command(bad)
    fly(c)
    with pytest.raises(RefusedCommand, match="entre"):
        c.command({"cmd": "goto", "x": 400, "y": 0, "z": 5})
    with pytest.raises(RefusedCommand, match="zone"):
        c.command({"cmd": "goto", "x": 40, "y": 40, "z": 5})  # dans le carré, mais hors du cercle autorisé
    with pytest.raises(RefusedCommand, match="déjà en vol"):
        c.command({"cmd": "takeoff", "altitude": 5})


def test_batterie_trop_faible_pour_decoller():
    c = Commander()
    c.quad.s.battery = 20.0
    with pytest.raises(RefusedCommand, match="batterie"):
        c.command({"cmd": "takeoff", "altitude": 5})


def test_sans_pilote_automatique_le_drone_tombe():
    """Contrôle négatif : le simulateur peut casser un drone ; ce n'est donc pas le décor qui le sauve."""
    c = Commander()
    c.command({"cmd": "takeoff", "altitude": 10})
    c.run(10)
    c.ap.enabled = False  # pilote coupé en plein vol
    c.run(10)
    assert c.quad.s.crashed and c.quad.touchdown["speed"] > 2.0


def test_meme_graine_meme_vol():
    def once():
        c = fly(Commander(wind=Wind(steady=(2, 1, 0), gust=2.0, seed=9), noise=Noise(seed=9)), secs=10)
        return tuple(round(v, 9) for v in c.quad.s.pos)
    assert once() == once()


def test_statut_lisible():
    c = fly(Commander())
    assert "STATIONNAIRE" in c.command({"cmd": "status"}) and "batterie" in c.status()


@pytest.mark.parametrize("seed", range(10))
def test_atterrissage_par_vent_fort(seed):
    """Vent de 8 m/s (près de 30 km/h) avec rafales de 2,5 m/s : toujours posé doucement."""
    c = fly(Commander(wind=Wind(steady=(8, 0, 0), gust=2.5, seed=seed), noise=Noise(seed=seed)), altitude=10, secs=25)
    assert land(c, 120)
    assert c.quad.touchdown["speed"] < 0.6 and not c.quad.s.crashed


def test_dessin_du_vol_et_programme(tmp_path):
    import json
    import subprocess
    import sys
    import xml.dom.minidom
    from pathlib import Path
    from drone.__main__ import demo
    from drone.render import flight_svg
    c = demo(vent=4, rafales=1.5, graine=2)
    svg = flight_svg(c.log, c.events)
    xml.dom.minidom.parseString(svg)  # SVG bien formé
    assert "ATTERRISSAGE" in svg and "<polyline" in svg and c.landing_error() < 1.5
    out = tmp_path / "vol.svg"
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-m", "drone", "--vent", "3", "--sortie", str(out)], cwd=root, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0 and out.exists()
    res = json.loads(r.stdout)
    assert res["cassé"] is False and res["toucher"]["vitesse_m_s"] < 0.6


def test_aucune_commande_vers_un_vrai_materiel():
    """Simulation seulement : aucun module du dossier ne sait parler à du matériel (réseau, port série, USB)."""
    from pathlib import Path
    for f in (Path(__file__).resolve().parents[1] / "drone").glob("*.py"):
        text = f.read_text(encoding="utf-8")
        for banned in ("import socket", "import serial", "pymavlink", "dronekit", "import requests", "urllib", "subprocess"):
            assert banned not in text, (f.name, banned)
