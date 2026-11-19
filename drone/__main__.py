"""python -m drone [--vent 6] [--rafales 2] [--graine 1] [--sortie vol.svg] : un vol complet en simulation."""
from __future__ import annotations

import argparse
import json
import math

from .commander import Commander
from .control import Noise
from .render import flight_svg
from .sim import Wind


def demo(vent: float = 6.0, rafales: float = 2.0, graine: int = 1) -> Commander:
    c = Commander(wind=Wind(steady=(vent, -vent / 3, 0), gust=rafales, seed=graine), noise=Noise(seed=graine))
    c.command({"cmd": "takeoff", "altitude": 10})
    c.run(12)
    c.command({"cmd": "goto", "x": 25, "y": 12, "z": 14})
    c.run(20)
    c.command({"cmd": "land"})
    c.run_until(lambda c: c.ap.mode in ("ATTERRI", "CRASH"), 120)
    c.run(2)
    return c


def main() -> None:
    ap = argparse.ArgumentParser(description="Simulation d'un vol de drone : décollage, déplacement, atterrissage automatique.")
    ap.add_argument("--vent", type=float, default=6.0, help="vent constant en m/s")
    ap.add_argument("--rafales", type=float, default=2.0, help="force des rafales en m/s")
    ap.add_argument("--graine", type=int, default=1)
    ap.add_argument("--sortie", default="vol.svg")
    a = ap.parse_args()
    c = demo(a.vent, a.rafales, a.graine)
    open(a.sortie, "w", encoding="utf-8").write(flight_svg(c.log, c.events))
    td = c.quad.touchdown or {}
    print(json.dumps({"état": c.status(), "événements": c.events,
                      "toucher": {"vitesse_m_s": round(td.get("speed", 0), 2), "inclinaison_deg": round(math.degrees(td.get("tilt", 0)), 1),
                                  "écart_au_point_visé_m": round(c.landing_error() or 0.0, 2)}, "cassé": c.quad.s.crashed, "dessin": a.sortie},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
