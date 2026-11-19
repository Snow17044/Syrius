"""Dessin d'un vol en SVG (hauteur au cours du temps + vue de dessus). Aucune bibliothèque externe."""
from __future__ import annotations

from xml.sax.saxutils import escape

COLORS = {"DECOLLAGE": "#e3a008", "STATIONNAIRE": "#2f9e44", "ALLER_A": "#1c7ed6", "ATTERRISSAGE": "#d6336c",
          "ATTERRI": "#868e96", "AU_SOL": "#868e96", "CRASH": "#c92a2a"}


def _scale(vals, lo_px, hi_px, pad=0.05):
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-6:
        hi = lo + 1
    span = hi - lo
    lo, hi = lo - span * pad, hi + span * pad
    return lambda v: lo_px + (v - lo) / (hi - lo) * (hi_px - lo_px)


def flight_svg(log: list, events: list[str], title: str = "Vol du drone (simulation)") -> str:
    if not log:
        raise ValueError("aucune donnée de vol")
    W, H = 900, 620
    ts, xs, ys, zs = [r[0] for r in log], [r[1] for r in log], [r[2] for r in log], [r[3] for r in log]
    ax, ay = _scale(ts, 60, 860), _scale([0, max(zs)], 260, 60)
    mx = _scale(xs + [0], 60, 400)
    my = _scale(ys + [0], 590, 330)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="13">',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
           f'<text x="60" y="30" font-size="18" font-weight="bold">{escape(title)}</text>',
           f'<text x="60" y="50" fill="#555">Hauteur (m) au cours du temps (s) ; couleur = mode du pilote automatique</text>']
    for i in range(len(log) - 1):  # hauteur, colorée par mode
        a, b = log[i], log[i + 1]
        out.append(f'<line x1="{ax(a[0]):.1f}" y1="{ay(a[3]):.1f}" x2="{ax(b[0]):.1f}" y2="{ay(b[3]):.1f}" '
                   f'stroke="{COLORS.get(a[4], "#333")}" stroke-width="3"/>')
    out.append(f'<line x1="60" y1="{ay(0):.1f}" x2="860" y2="{ay(0):.1f}" stroke="#999"/>')
    out.append(f'<text x="64" y="{ay(0) - 4:.1f}" fill="#999">sol</text>')
    out.append(f'<text x="60" y="318" fill="#555">Vue de dessus (m) : le départ est le cercle vert, l\'arrivée la croix</text>')
    pts = " ".join(f"{mx(x):.1f},{my(y):.1f}" for x, y in zip(xs, ys))
    out.append(f'<polyline points="{pts}" fill="none" stroke="#1c7ed6" stroke-width="2"/>')
    out.append(f'<circle cx="{mx(xs[0]):.1f}" cy="{my(ys[0]):.1f}" r="6" fill="#2f9e44"/>')
    ex, ey = mx(xs[-1]), my(ys[-1])
    out.append(f'<path d="M{ex - 6:.1f},{ey - 6:.1f} L{ex + 6:.1f},{ey + 6:.1f} M{ex - 6:.1f},{ey + 6:.1f} L{ex + 6:.1f},{ey - 6:.1f}" '
               f'stroke="#c92a2a" stroke-width="3"/>')
    modes = []
    for r in log:
        if r[4] not in modes:
            modes.append(r[4])
    for i, m in enumerate(modes):
        out.append(f'<rect x="440" y="{340 + i * 22}" width="14" height="14" fill="{COLORS.get(m, "#333")}"/>'
                   f'<text x="462" y="{352 + i * 22}">{escape(m)}</text>')
    for i, e in enumerate(events[:9]):
        out.append(f'<text x="440" y="{352 + (len(modes) + 1) * 22 + i * 18}" fill="#333">{escape(e)}</text>')
    out.append("</svg>")
    return "\n".join(out)
