"""Physique d'un quadricoptère : poids, poussée, inclinaison, vent, rafales, moteurs qui répondent avec un petit retard,
batterie, sol. Tout est déterministe (graine) pour pouvoir refaire exactement la même expérience."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

G = 9.81


@dataclass
class Params:
    mass: float = 1.0                    # kg
    inertia: tuple = (0.02, 0.02, 0.04)  # kg·m²
    max_thrust: float = 24.0             # N (environ 2,4 fois le poids)
    max_torque: tuple = (0.6, 0.6, 0.3)  # N·m
    motor_lag: float = 0.04              # s : les moteurs ne répondent pas instantanément
    drag: float = 0.25                   # 1/s : frottement de l'air (par rapport au vent)
    ang_damping: float = 0.01
    hover_minutes: float = 10.0          # batterie : durée du vol stationnaire de 100 % à 0 %
    crash_speed: float = 2.0             # m/s : vitesse verticale à l'impact qui casse le drone
    crash_tilt: float = 0.5              # rad (~29°) : inclinaison à l'impact qui casse le drone


@dataclass
class Wind:
    """Vent constant (m/s) + rafales (processus aléatoire lissé)."""
    steady: tuple = (0.0, 0.0, 0.0)
    gust: float = 0.0                    # écart type des rafales (m/s)
    tau: float = 2.0                     # durée typique d'une rafale (s)
    seed: int = 1
    _g: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    _rng: random.Random = field(default=None)

    def __post_init__(self):
        self._rng = random.Random(self.seed)

    def step(self, dt: float) -> tuple:
        if self.gust > 0:
            a = math.exp(-dt / self.tau)
            s = self.gust * math.sqrt(1 - a * a)
            self._g = [a * g + s * self._rng.gauss(0, 1) for g in self._g]
        return tuple(self.steady[i] + self._g[i] for i in range(3))


@dataclass
class State:
    pos: list = field(default_factory=lambda: [0.0, 0.0, 0.0])   # x, y, z (z = hauteur au-dessus du sol)
    vel: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    att: list = field(default_factory=lambda: [0.0, 0.0, 0.0])   # roulis, tangage, lacet (rad)
    rates: list = field(default_factory=lambda: [0.0, 0.0, 0.0])  # p, q, r (rad/s)
    thrust: float = 0.0                  # poussée réelle (après retard moteur)
    torque: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    battery: float = 100.0               # %
    on_ground: bool = True
    crashed: bool = False
    t: float = 0.0


class Quad:
    def __init__(self, params: Params | None = None, wind: Wind | None = None, dt: float = 0.005):
        self.p, self.wind, self.dt = params or Params(), wind or Wind(), dt
        self.s = State()
        self.cmd_thrust, self.cmd_torque = 0.0, [0.0, 0.0, 0.0]
        self.touchdown: dict | None = None  # vitesse, inclinaison, dérive au dernier contact avec le sol
        self.max_tilt_seen = 0.0

    def command(self, thrust: float, torque: tuple) -> None:
        self.cmd_thrust = min(max(thrust, 0.0), self.p.max_thrust)
        self.cmd_torque = [min(max(t, -m), m) for t, m in zip(torque, self.p.max_torque)]

    def step(self) -> None:
        p, s, dt = self.p, self.s, self.dt
        if s.crashed:
            return
        if s.battery <= 0:                       # batterie vide : plus de poussée
            self.cmd_thrust, self.cmd_torque = 0.0, [0.0, 0.0, 0.0]
        a = dt / (p.motor_lag + dt)              # retard des moteurs
        s.thrust += a * (self.cmd_thrust - s.thrust)
        s.torque = [s.torque[i] + a * (self.cmd_torque[i] - s.torque[i]) for i in range(3)]
        if s.on_ground and self.cmd_thrust < p.mass * G * 0.98:
            s.t += dt                            # posé et moteurs sous le poids : on ne bouge pas
            return
        phi, th, psi = s.att
        cph, sph, cth, sth, cps, sps = math.cos(phi), math.sin(phi), math.cos(th), math.sin(th), math.cos(psi), math.sin(psi)
        T = s.thrust / p.mass
        w = self.wind.step(dt)
        acc = [T * (cph * sth * cps + sph * sps) - p.drag * (s.vel[0] - w[0]),
               T * (cph * sth * sps - sph * cps) - p.drag * (s.vel[1] - w[1]),
               T * cph * cth - G - p.drag * (s.vel[2] - w[2])]
        for i in range(3):
            s.vel[i] += acc[i] * dt
            s.pos[i] += s.vel[i] * dt
        ix, iy, iz = p.inertia
        pr, qr, rr = s.rates
        s.rates[0] += ((s.torque[0] - (iy - iz) * qr * rr) / ix - p.ang_damping * pr) * dt
        s.rates[1] += ((s.torque[1] - (iz - ix) * pr * rr) / iy - p.ang_damping * qr) * dt
        s.rates[2] += ((s.torque[2] - (ix - iy) * pr * qr) / iz - p.ang_damping * rr) * dt
        pr, qr, rr = s.rates
        tt = math.tan(max(-1.2, min(1.2, th)))
        s.att[0] += (pr + (qr * sph + rr * cph) * tt) * dt
        s.att[1] += (qr * cph - rr * sph) * dt
        s.att[2] += ((qr * sph + rr * cph) / max(cth, 0.2)) * dt
        s.battery = max(0.0, s.battery - (100.0 / (p.hover_minutes * 60)) * (s.thrust / (p.mass * G)) * dt)
        s.t += dt
        self.max_tilt_seen = max(self.max_tilt_seen, abs(s.att[0]), abs(s.att[1]))
        if s.pos[2] <= 0.0:                      # contact avec le sol
            speed = -s.vel[2]
            tilt = max(abs(s.att[0]), abs(s.att[1]))
            self.touchdown = {"speed": max(speed, 0.0), "tilt": tilt, "drift": math.hypot(s.pos[0], s.pos[1]), "pos": (s.pos[0], s.pos[1]), "t": s.t}
            s.pos[2] = 0.0
            if speed > p.crash_speed or tilt > p.crash_tilt:
                s.crashed = True
            s.vel[2] = max(s.vel[2], 0.0) if not s.on_ground else 0.0
            if speed >= 0:
                s.vel = [s.vel[0] * 0.2, s.vel[1] * 0.2, 0.0]
                s.rates = [0.0, 0.0, 0.0]
            s.on_ground = True
        else:
            s.on_ground = False
