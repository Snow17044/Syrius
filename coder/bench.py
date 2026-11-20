"""Banc d'essai : de vrais bugs fabriqués avec une graine FIXE ; le score = part des bugs réparés (tests au vert)."""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

from . import edits, mutate, sandbox, stub, tasks

BENCH_SEED = 20260101
BENCH_ONLY = ("notes", "unites")  # projets JAMAIS utilisés pour l'entraînement
BENCH_VERSION = 2  # change quand les tâches changent : les scores ne se comparent qu'à version égale
IMPLEMENT = "Implémente la fonction qui est vide (raise NotImplementedError) pour que les tests passent."


def build(projects: dict | None = None, per_project: int = 3, seed: int = BENCH_SEED, implement: int = 2) -> list[dict]:
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
                out.append({"project": name, "file": src, "files": broken, "failing": log, "fix": (src, *fix),
                            "kind": "bug", "key": (name, src, bad)})
            for _ in range(implement):
                m = stub.make(files[src], rng)
                if not m:
                    continue
                stubbed, fname, search, replace = m
                broken = {**files, src: stubbed}
                with sandbox.project(broken) as d:
                    ok, log, _ = sandbox.run_tests(d)
                if ok or any(t["fix"][1] == search and t["file"] == src and t["project"] == name for t in out):
                    continue
                out.append({"project": name, "file": src, "files": broken, "failing": log, "fix": (src, search, replace),
                            "kind": "implement", "key": (name, src, search)})
    return out


def solve(task: dict, ask) -> tuple[bool, str]:
    prompt = tasks.make_prompt(task["files"], tasks.instruction(task.get("kind", "bug")), task["failing"])
    try:
        reply = ask(tasks.SYSTEM, prompt)
        with sandbox.project(task["files"]) as d:
            blocks = edits.resolve_paths(edits.parse(reply), list(task["files"]))
            edits.apply(d, blocks, forbidden=[], write=True)
            ok, log, _ = sandbox.run_tests(d)
        return ok, "" if ok else log[-200:]
    except edits.EditError as e:
        return False, f"modification refusée : {e}"
    except Exception as e:  # noqa: BLE001 — une panne du modèle compte comme un échec
        return False, f"erreur : {str(e)[:100]}"


def run(ask, tasks_list: list[dict] | None = None, limit: int | None = None) -> dict:
    ts = tasks_list if tasks_list is not None else build()
    if limit and limit < len(ts):  # échantillon réparti sur tous les projets, pas les premiers seulement
        step = len(ts) / limit
        ts = [ts[int(i * step)] for i in range(limit)]
    t0, passed, fails = time.time(), 0, []
    for t in ts:
        ok, why = solve(t, ask)
        passed += ok
        if not ok and len(fails) < 5:
            fails.append({"project": t["project"], "file": t["file"], "kind": t.get("kind", "bug"), "why": why})
    n = len(ts)
    kinds = {k: sum(1 for t in ts if t.get("kind", "bug") == k) for k in ("bug", "implement")}
    return {"version": BENCH_VERSION, "kinds": kinds, "score": passed / n if n else 0.0, "passed": passed, "n": n, "seconds": round(time.time() - t0, 1),
            "fails": fails, "at": int(time.time())}


if __name__ == "__main__":  # python -m coder.bench  → score du « modèle oracle » (vérifie que le banc est solvable)
    def oracle(_s, _p, _cache={}):
        raise RuntimeError("pas de modèle branché")
    ts = build()
    print(json.dumps({"tasks": len(ts)}))
    sys.exit(0)
