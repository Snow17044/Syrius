"""Ordres de haut niveau + sécurités. C'est la SEULE porte d'entrée pour Syrius : il envoie des ordres simples
(JSON), jamais des commandes moteur. Chaque ordre est vérifié ; les sécurités déclenchent l'atterrissage tout seul."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .control import Autopilot, Noise
from .sim import Params, Quad, Wind


class RefusedCommand(ValueError):
    """Ordre refusé (message affichable)."""


@dataclass
class Limits:
    max_altitude: float = 30.0     # m
    fence_radius: float = 50.0     # m : zone autorisée autour du point de départ
    low_battery: float = 25.0      # % : atterrissage automatique
    link_timeout: float = 3.0      # s sans nouvelle de l'opérateur (si la surveillance est activée)


class Commander:
    def __init__(self, wind: Wind | None = None, noise: Noise | None = None, params: Params | None = None,
                 limits: Limits | None = None, dt: float = 0.005):
        self.quad = Quad(params, wind, dt)
        self.ap = Autopilot(self.quad, noise)
        self.limits = limits or Limits()
        self.events: list[str] = []
        self.log: list[tuple] = []     # (t, x, y, z, mode, batterie, inclinaison)
        self.watch_link = False
        self._last_contact = 0.0
        self._failsafe = ""

    # ---------------------------------------------------------------- ordres
    def command(self, cmd: dict) -> str:
        if not isinstance(cmd, dict) or "cmd" not in cmd:
            raise RefusedCommand("ordre illisible")
        name, lim, s = cmd["cmd"], self.limits, self.quad.s
        self._last_contact = s.t

        def num(key: str, lo: float, hi: float) -> float:
            v = cmd.get(key)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
                raise RefusedCommand(f"« {key} » doit être un nombre")
            if not lo <= v <= hi:
                raise RefusedCommand(f"« {key} » doit être entre {lo} et {hi}")
            return float(v)

        if self._failsafe and name != "land":
            raise RefusedCommand(f"sécurité active ({self._failsafe}) : seul « land » est accepté")
        if s.crashed:
            raise RefusedCommand("le drone est cassé")
        if name == "takeoff":
            if self.ap.mode != "AU_SOL":
                raise RefusedCommand("déjà en vol")
            if s.battery < lim.low_battery + 10:
                raise RefusedCommand("batterie trop faible pour décoller")
            self.ap.takeoff(num("altitude", 1.0, lim.max_altitude))
            self.events.append(f"{s.t:.1f}s décollage")
        elif name == "goto":
            if self.ap.mode in ("AU_SOL", "ATTERRI", "CRASH"):
                raise RefusedCommand("le drone n'est pas en vol")
            x, y, z = num("x", -lim.fence_radius, lim.fence_radius), num("y", -lim.fence_radius, lim.fence_radius), num("z", 1.0, lim.max_altitude)
            if math.hypot(x, y) > lim.fence_radius:
                raise RefusedCommand("hors de la zone autorisée")
            self.ap.goto(x, y, z)
            self.events.append(f"{s.t:.1f}s aller à ({x:.0f}, {y:.0f}, {z:.0f})")
        elif name == "hover":
            self.ap.hover()
        elif name == "land":
            self.ap.land()
            self.events.append(f"{s.t:.1f}s atterrissage demandé")
        elif name == "status":
            pass
        else:
            raise RefusedCommand(f"ordre inconnu : {name}")
        return self.status()

    def landing_error(self) -> float | None:
        """Distance (m) entre le point visé et l'endroit où le drone s'est posé (None si pas encore posé)."""
        td, tgt = self.quad.touchdown, self.ap.land_xy
        if not td or not tgt or self.ap.mode not in ("ATTERRI", "CRASH"):
            return None
        return math.hypot(td["pos"][0] - tgt[0], td["pos"][1] - tgt[1])

    def status(self) -> str:
        s = self.quad.s
        return (f"{self.ap.mode} · position ({s.pos[0]:.1f}, {s.pos[1]:.1f}) · hauteur {s.pos[2]:.1f} m · "
                f"batterie {s.battery:.0f} % · inclinaison {math.degrees(max(abs(s.att[0]), abs(s.att[1]))):.0f}°")

    # ---------------------------------------------------------------- temps
    def _safety(self) -> None:
        s, lim = self.quad.s, self.limits
        if self.ap.mode in ("AU_SOL", "ATTERRI", "CRASH", "ATTERRISSAGE") or self._failsafe:
            return
        why = ""
        if s.battery < lim.low_battery:
            why = "batterie faible"
        elif self.watch_link and s.t - self._last_contact > lim.link_timeout:
            why = "liaison perdue"
        elif math.hypot(s.pos[0], s.pos[1]) > lim.fence_radius + 5 or s.pos[2] > lim.max_altitude + 5:
            why = "hors de la zone autorisée"
        if why:
            self._failsafe = why
            self.events.append(f"{s.t:.1f}s SÉCURITÉ : {why} → atterrissage automatique")
            self.ap.land()

    def run(self, seconds: float, every: float = 0.1) -> None:
        n, nxt = int(seconds / self.quad.dt), 0.0
        for _ in range(n):
            self._safety()
            self.ap.step()
            self.quad.step()
            s = self.quad.s
            if s.t >= nxt:
                nxt = s.t + every
                self.log.append((round(s.t, 3), s.pos[0], s.pos[1], s.pos[2], self.ap.mode, s.battery,
                                 max(abs(s.att[0]), abs(s.att[1]))))
            if s.crashed:
                break

    def run_until(self, predicate, timeout: float) -> bool:
        t_end = self.quad.s.t + timeout
        while self.quad.s.t < t_end:
            self.run(0.1)
            if predicate(self):
                return True
        return False
