"""Tableaux de bord créés par Aurora : un descriptif strict (KPI, graphiques, tableau) vérifié avant affichage.

Rien n'est exécuté : l'application dessine elle-même les graphiques à partir de ces données (nombres et textes courts).
"""
from __future__ import annotations

import math

MAX_KPIS, MAX_CHARTS, MAX_POINTS, MAX_SERIES, MAX_COLS, MAX_ROWS = 6, 4, 24, 4, 6, 20
CHART_TYPES = ("bar", "line", "pie")
TRENDS = ("up", "down", "flat")


class DashboardError(ValueError):
    """Descriptif invalide (message affichable à l'IA pour qu'elle corrige)."""


def _txt(v, n: int, what: str) -> str:
    if v is None or isinstance(v, (dict, list, bool)):
        raise DashboardError(f"{what} : texte attendu")
    s = " ".join(str(v).split())
    if not s:
        raise DashboardError(f"{what} : vide")
    return s[:n]


def _num(v, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 1e12:
        raise DashboardError(f"{what} : nombre attendu")
    return round(float(v), 4)


def _cell(v):
    if isinstance(v, bool) or v is None or isinstance(v, (dict, list)):
        return ""
    if isinstance(v, (int, float)):
        return _num(v, "cellule") if math.isfinite(v) else ""
    return " ".join(str(v).split())[:60]


def validate(args) -> dict:
    if not isinstance(args, dict):
        raise DashboardError("descriptif invalide")
    unknown = set(args) - {"title", "kpis", "charts", "table"}
    if unknown:
        raise DashboardError("champ inconnu : " + ", ".join(sorted(unknown)) + " (title, kpis, charts, table)")
    title = _txt(args.get("title"), 80, "titre")
    kpis = []
    for k in (args.get("kpis") or [])[:MAX_KPIS]:
        if not isinstance(k, dict):
            raise DashboardError("chaque KPI : label, value, note, trend")
        item = {"label": _txt(k.get("label"), 30, "KPI label"), "value": _txt(k.get("value"), 20, "KPI value")}
        if k.get("note"):
            item["note"] = _txt(k["note"], 40, "KPI note")
        if k.get("trend") in TRENDS:
            item["trend"] = k["trend"]
        kpis.append(item)
    charts = []
    for c in (args.get("charts") or [])[:MAX_CHARTS]:
        if not isinstance(c, dict) or c.get("type") not in CHART_TYPES:
            raise DashboardError("chaque graphique : type bar, line ou pie, title, labels, series")
        labels = [_txt(x, 20, "étiquette") for x in (c.get("labels") or [])[:MAX_POINTS]]
        if len(labels) < 2:
            raise DashboardError("un graphique a besoin d'au moins 2 étiquettes")
        series = []
        for s in (c.get("series") or [])[:MAX_SERIES]:
            if not isinstance(s, dict) or not isinstance(s.get("values"), list):
                raise DashboardError("chaque série : name et values (liste de nombres)")
            values = [_num(v, "valeur") for v in s["values"]]
            if len(values) != len(labels):
                raise DashboardError(f"la série « {s.get('name', '')} » doit avoir {len(labels)} valeurs (une par étiquette)")
            series.append({"name": _txt(s.get("name", "Série"), 24, "nom de série"), "values": values})
        if not series:
            raise DashboardError("un graphique a besoin d'au moins une série")
        if c["type"] == "pie":
            if len(series) != 1 or any(v < 0 for v in series[0]["values"]):
                raise DashboardError("un camembert : une seule série, valeurs positives")
        charts.append({"type": c["type"], "title": _txt(c.get("title", "Graphique"), 50, "titre du graphique"),
                       "labels": labels, "series": series})
    table = None
    t = args.get("table")
    if t:
        if not isinstance(t, dict) or not isinstance(t.get("columns"), list) or not isinstance(t.get("rows"), list):
            raise DashboardError("table : columns (liste de textes) et rows (liste de lignes)")
        cols = [_txt(x, 20, "colonne") for x in t["columns"][:MAX_COLS]]
        rows = []
        for r in t["rows"][:MAX_ROWS]:
            if not isinstance(r, list):
                raise DashboardError("chaque ligne du tableau est une liste")
            rows.append([_cell(x) for x in r[:len(cols)]] + [""] * max(0, len(cols) - len(r)))
        table = {"columns": cols, "rows": rows}
    if not (kpis or charts or table):
        raise DashboardError("un tableau de bord a besoin d'au moins un KPI, un graphique ou un tableau")
    return {"type": "dashboard", "title": title, "kpis": kpis, "charts": charts, "table": table}
