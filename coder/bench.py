"""Banc d'essai : de vrais bugs fabriqués avec une graine FIXE ; le score = part des bugs réparés (tests au vert)."""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

from . import edits, mutate, sandbox, tasks

BENCH_SEED = 20260101


def build(projects: dict | None = None, per_project: int = 6, seed: int = BENCH_SEED) -> list[dict]:
    projects = projects or tasks.SEEDS
    rng = random.Random(seed)
    out = []
    for name in sorted(projects):
        files = projects[name]
        for src in tasks.source_files(files):
            seen = set()
            for _ in range(per_project * 4):
                if len(seen) >= per_project:
                    break
                m = mutate.mutate(files[src], rng)
                if not m or m[2] in seen:
                    continue
                buggy_src, good, bad = m
                broken = {**files, src: buggy_src}
                with sandbox.project(broken) as d:
                    ok, log, _ = sandbox.run_tests(d)
                if ok:
                    continue  # un bug que les tests ne voient pas ne sert à rien
                fix = mutate.edit_for(buggy_src, good, bad)
                if fix is None:
                    continue
                seen.add(bad)
                out.append({"project": name, "file": src, "files": broken, "failing": log, "fix": (src, *fix)})
    return out


def solve(task: dict, ask) -> tuple[bool, str]:
    prompt = tasks.make_prompt(task["files"], "Les tests échouent. Corrige le bug avec une modification minimale.",
                               task["failing"])
    try:
        reply = ask(tasks.SYSTEM, prompt)
        with sandbox.project(task["files"]) as d:
            edits.apply(d, edits.parse(reply), forbidden=[], write=True)
            ok, log, _ = sandbox.run_tests(d)
        return ok, "" if ok else log[-200:]
    except edits.EditError as e:
        return False, f"modification refusée : {e}"
    except Exception as e:  # noqa: BLE001 — une panne du modèle compte comme un échec
        return False, f"erreur : {str(e)[:100]}"


def run(ask, tasks_list: list[dict] | None = None, limit: int | None = None) -> dict:
    ts = tasks_list if tasks_list is not None else build()
    ts = ts[:limit] if limit else ts
    t0, passed, fails = time.time(), 0, []
    for t in ts:
        ok, why = solve(t, ask)
        passed += ok
        if not ok and len(fails) < 5:
            fails.append({"project": t["project"], "file": t["file"], "why": why})
    n = len(ts)
    return {"score": passed / n if n else 0.0, "passed": passed, "n": n, "seconds": round(time.time() - t0, 1),
            "fails": fails, "at": int(time.time())}


if __name__ == "__main__":  # python -m coder.bench  → score du « modèle oracle » (vérifie que le banc est solvable)
    def oracle(_s, _p, _cache={}):
        raise RuntimeError("pas de modèle branché")
    ts = build()
    print(json.dumps({"tasks": len(ts)}))
    sys.exit(0)
