"""Pilote automatique : capteurs bruités, stabilisation (angles), maintien de position et d'altitude, atterrissage.

Principe en cascade, comme sur un vrai drone :
 position -> vitesse souhaitée -> accélération souhaitée -> inclinaison souhaitée -> couples moteurs.
Le régulateur ne voit que des mesures BRUITÉES (jamais l'état exact du simulateur).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .sim import G, Quad


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


@dataclass
class Noise:
    pos: float = 0.02      # m
    vel: float = 0.05      # m/s
    att: float = 0.002     # rad
    rate: float = 0.01     # rad/s
    seed: int = 7


class Sensors:
    def __init__(self, noise: Noise):
        self.n, self.rng = noise, random.Random(noise.seed)

    def read(self, s) -> dict:
        g = self.rng.gauss
        return {"pos": [s.pos[i] + g(0, self.n.pos) for i in range(3)],
                "vel": [s.vel[i] + g(0, self.n.vel) for i in range(3)],
                "att": [s.att[i] + g(0, self.n.att) for i in range(3)],
                "rates": [s.rates[i] + g(0, self.n.rate) for i in range(3)],
                "battery": s.battery}


@dataclass
class Gains:
    kp_pos: float = 0.8
    kp_vel: float = 2.6
    ki_vel: float = 0.5
    kp_alt: float = 1.2
    kp_vz: float = 4.0
    ki_vz: float = 1.5
    kp_att: float = 80.0
    kd_att: float = 12.0
    kp_yaw: float = 4.0
    kd_yaw: float = 3.0
    max_tilt: float = 0.35      # rad (~20°)
    v_xy: float = 4.0           # m/s
    v_up: float = 2.0
    v_down: float = 1.5


class Autopilot:
    """Modes : AU_SOL, DECOLLAGE, STATIONNAIRE, ALLER_A, ATTERRISSAGE, ATTERRI, CRASH."""

    def __init__(self, quad: Quad, noise: Noise | None = None, gains: Gains | None = None):
        self.q, self.g = quad, gains or Gains()
        self.sensors = Sensors(noise or Noise())
        self.mode = "AU_SOL"
        self.target = [0.0, 0.0, 0.0]
        self.target_yaw = 0.0
        self.i_vel = [0.0, 0.0]
        self.i_vz = 0.0
        self.m = {}  # dernières mesures
        self._v_f = [0.0, 0.0, 0.0]   # vitesse filtrée
        self.enabled = True           # False : pilote coupé (pour montrer que, sans lui, le drone tombe)
        self.landed_at: float | None = None
        self.land_xy: tuple | None = None

    # --- ordres de haut niveau (validés par le Commander) ---
    def takeoff(self, altitude: float) -> None:
        self.target = [self.q.s.pos[0], self.q.s.pos[1], altitude]
        self.mode = "DECOLLAGE"

    def goto(self, x: float, y: float, z: float) -> None:
        self.target = [x, y, z]
        self.mode = "ALLER_A"

    def hover(self) -> None:
        self.target = list(self.q.s.pos)
        self.mode = "STATIONNAIRE"

    def land(self) -> None:
        if self.mode in ("AU_SOL", "ATTERRI", "CRASH"):
            return
        self.target = [self.q.s.pos[0], self.q.s.pos[1], 0.0]
        self.land_xy = (self.q.s.pos[0], self.q.s.pos[1])  # point visé : à la verticale de l'endroit où l'ordre a été donné
        self.mode = "ATTERRISSAGE"

    # --- boucle de contrôle (appelée à chaque pas) ---
    def step(self) -> None:
        q, s, g, dt = self.q, self.q.s, self.g, self.q.dt
        if s.crashed:
            self.mode = "CRASH"
            q.command(0, (0, 0, 0))
            return
        if self.mode == "AU_SOL" or not self.enabled:
            if not self.enabled and not s.on_ground:
                q.command(0.0, (0, 0, 0))   # pilote coupé : moteurs à zéro
            else:
                q.command(0.0, (0, 0, 0))
            return
        if self.mode == "ATTERRI":
            q.command(0.0, (0, 0, 0))
            return
        m = self.sensors.read(s)
        self.m = m
        a = 0.25
        self._v_f = [self._v_f[i] + a * (m["vel"][i] - self._v_f[i]) for i in range(3)]
        x, y, z = m["pos"]
        phi, th, psi = m["att"]
        p, qq, r = m["rates"]
        tx, ty, tz = self.target

        # vitesse horizontale souhaitée (limitée) ; en atterrissage on garde la position
        vx_d = clamp(g.kp_pos * (tx - x), -g.v_xy, g.v_xy)
        vy_d = clamp(g.kp_pos * (ty - y), -g.v_xy, g.v_xy)
        # vitesse verticale souhaitée
        if self.mode == "ATTERRISSAGE":
            h = max(z, 0.0)
            vz_d = -clamp(0.2 + 0.4 * h, 0.2, g.v_down)   # descente de plus en plus douce près du sol
            if h < 0.2:
                vz_d = -0.15
        else:
            vz_d = clamp(g.kp_alt * (tz - z), -g.v_down, g.v_up)
        # intégrales (compensent le vent constant et la batterie qui baisse), avec butée
        self.i_vel[0] = clamp(self.i_vel[0] + (vx_d - self._v_f[0]) * dt, -3.0, 3.0)
        self.i_vel[1] = clamp(self.i_vel[1] + (vy_d - self._v_f[1]) * dt, -3.0, 3.0)
        self.i_vz = clamp(self.i_vz + (vz_d - self._v_f[2]) * dt, -2.0, 2.0)
        ax = g.kp_vel * (vx_d - self._v_f[0]) + g.ki_vel * self.i_vel[0]
        ay = g.kp_vel * (vy_d - self._v_f[1]) + g.ki_vel * self.i_vel[1]
        kp_vz = g.kp_vz * (2.0 if self.mode == "ATTERRISSAGE" and z < 3.0 else 1.0)  # près du sol : réaction plus ferme
        az = kp_vz * (vz_d - self._v_f[2]) + g.ki_vz * self.i_vz
        # accélération -> inclinaison (dans le repère du drone, selon le lacet)
        cps, sps = math.cos(psi), math.sin(psi)
        axb, ayb = ax * cps + ay * sps, -ax * sps + ay * cps
        th_d = clamp(axb / G, -g.max_tilt, g.max_tilt)
        ph_d = clamp(-ayb / G, -g.max_tilt, g.max_tilt)
        # poussée totale (corrigée de l'inclinaison)
        tilt_cos = max(math.cos(phi) * math.cos(th), 0.5)
        thrust = q.p.mass * (G + az) / tilt_cos
        # couples
        ix, iy, iz = q.p.inertia
        tau_x = ix * (g.kp_att * (ph_d - phi) - g.kd_att * p)
        tau_y = iy * (g.kp_att * (th_d - th) - g.kd_att * qq)
        yaw_err = (self.target_yaw - psi + math.pi) % (2 * math.pi) - math.pi
        tau_z = iz * (g.kp_yaw * yaw_err - g.kd_yaw * r)
        q.command(thrust, (tau_x, tau_y, tau_z))
        # atterrissage terminé : contact avec le sol, on coupe les moteurs
        if self.mode == "ATTERRISSAGE" and s.on_ground:
            self.mode = "ATTERRI"
            self.landed_at = s.t
            q.command(0.0, (0, 0, 0))
        # décollage terminé : on passe en stationnaire à la bonne hauteur
        if self.mode == "DECOLLAGE" and abs(tz - z) < 0.3 and abs(self._v_f[2]) < 0.4:
            self.mode = "STATIONNAIRE"
