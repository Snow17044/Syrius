"""Fabrique les exemples d'entraînement de l'IA programmeuse. TOUT est vérifié en exécutant les tests.

1. Bugs fabriqués (mutate) : la correction est connue → exemples sûrs, sans IA.
2. Nouveaux projets écrits par une grande IA (« professeur ») : gardés seulement si leurs tests passent.
3. Petites fonctionnalités demandées au professeur : gardées seulement si les tests passent APRÈS la modification
   (et si le nombre de tests a augmenté).
Les exemples du banc d'essai ne sont jamais utilisés pour l'entraînement (graine différente, contrôle de doublon).
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

from . import bench, edits, mutate, sandbox, stub, tasks

OUT = Path(__file__).resolve().parent.parent / "training" / "data" / "coder.jsonl"
MAX_FILE = 3500


def bug_examples(projects: dict, n: int, seed: int, avoid: set | None = None) -> list[dict]:
    rng = random.Random(seed)
    avoid, out = avoid or set(), []
    names = sorted(projects)
    for _ in range(n * 25):
        if len(out) >= n:
            break
        name = rng.choice(names)
        files = projects[name]
        src = rng.choice(tasks.source_files(files))
        kind = "implement" if rng.random() < 0.35 else "bug"
        if kind == "implement":
            m = stub.make(files[src], rng)
            if not m:
                continue
            buggy, fname, bad, good = m  # « bad » = fonction vide, « good » = vraie fonction
            fix = (bad, good)
            good_line = bad_line = fname
        else:
            m = mutate.mutate(files[src], rng)
            if not m:
                continue
            buggy, good, bad = m
            fix = mutate.edit_for(buggy, good, bad)
            good_line, bad_line = good, bad
        key = (name, src, bad)
        if fix is None or key in avoid:
            continue
        broken = {**files, src: buggy}
        with sandbox.project(broken) as d:
            ok, log, _ = sandbox.run_tests(d)
        if ok:
            continue
        with sandbox.project(broken) as d:  # la correction doit vraiment réparer
            try:
                edits.apply(d, [edits.Edit(src, *fix)], forbidden=[])
            except edits.EditError:
                continue
            ok, _, _ = sandbox.run_tests(d)
        if not ok:
            continue
        avoid.add(key)
        if kind == "implement":
            explain = f"J'implémente `{fname}` dans {src} en suivant ce que les tests attendent."
        else:
            explain = f"Le bug est dans {src} : « {bad_line.strip()[:70]} » est faux, je rétablis « {good_line.strip()[:70]} »."
        out.append(tasks.messages(tasks.make_prompt(broken, tasks.instruction(kind), log),
                                  tasks.answer(explain, [(src, *fix)])))
    return out


def _json_block(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except ValueError:
        return None


def new_project(ask, topic: str):
    """Le professeur écrit un module + ses tests ; gardé seulement si les tests passent. Renvoie {chemin: texte} ou None."""
    reply = ask("Réponds uniquement avec un objet JSON.",
                f"Écris un petit module Python (30 à 60 lignes, 3 fonctions, sans bibliothèque externe) sur le thème : {topic}. "
                'Écris aussi ses tests pytest (au moins 5 assertions utiles, avec un cas d\'erreur). Réponds avec ce JSON exact : '
                '{"name": "nom_court_en_minuscules", "module": "code du module", "tests": "code des tests (import depuis le module)"}')
    d = _json_block(reply)
    if not isinstance(d, dict) or not all(isinstance(d.get(k), str) for k in ("name", "module", "tests")):
        return None
    name = re.sub(r"[^a-z0-9_]", "", d["name"].lower())[:24]
    if not name or name.startswith("test") or len(d["module"]) > MAX_FILE or len(d["tests"]) > MAX_FILE:
        return None
    files = {f"{name}.py": d["module"].rstrip() + "\n", f"test_{name}.py": d["tests"].rstrip() + "\n"}
    with sandbox.project(files) as p:
        ok, _, passed = sandbox.run_tests(p)
    return files if ok and passed >= 3 else None


def feature_example(ask, files: dict, instruction: str):
    """Le professeur propose la modification ; l'exemple n'est gardé que si les tests passent et qu'un test a été ajouté."""
    with sandbox.project(files) as p:
        _, _, before = sandbox.run_tests(p)
    prompt = tasks.make_prompt(files, instruction + " Ajoute aussi un test dans le fichier de tests.")
    reply = ask(tasks.SYSTEM, prompt)
    try:
        blocks = edits.parse(reply)
        with sandbox.project(files) as p:
            edits.apply(p, blocks, forbidden=[])
            ok, _, after = sandbox.run_tests(p)
    except edits.EditError:
        return None
    if not ok or after <= before:
        return None
    return tasks.messages(prompt, reply.strip())


FEATURES = ["Ajoute une petite fonction utile qui complète le module, avec une docstring d'une ligne.",
            "Ajoute une option facultative à l'une des fonctions existantes, sans casser les appels actuels.",
            "Rends l'une des fonctions plus robuste face aux entrées vides ou invalides (lève ValueError)."]
TOPICS = ["dates et durées", "mots de passe et validation", "recettes et quantités", "notes et moyennes scolaires",
          "inventaire de magasin", "coordonnées et distances", "chaînes et formats", "files et piles", "pourcentages",
          "emploi du temps", "conversion d'unités", "textes et mots", "scores de jeu", "tri et recherche"]


def run(ask, out: Path = OUT, bugs: int = 120, projects_n: int = 6, features_per: int = 2, seed: int = 7,
        log=print) -> dict:
    projects = {k: v for k, v in tasks.SEEDS.items() if k not in bench.BENCH_ONLY}  # le banc reste inédit
    bench_tasks = bench.build()
    got_projects = 0
    rng = random.Random(seed)
    for topic in rng.sample(TOPICS, min(projects_n, len(TOPICS))):
        try:
            f = new_project(ask, topic)
        except Exception as e:  # noqa: BLE001
            log(f"projet « {topic} » : indisponible ({str(e)[:80]})")
            continue
        if f:
            projects[f"gen_{len(projects)}"] = f
            got_projects += 1
        else:
            log(f"projet « {topic} » : refusé (tests ne passent pas)")
    items = bug_examples(projects, bugs, seed + 1, avoid={t["key"] for t in bench_tasks})  # jamais un bug du banc
    feats = 0
    for name, files in sorted(projects.items()):
        for i in range(features_per):
            try:
                ex = feature_example(ask, files, FEATURES[(i + len(name)) % len(FEATURES)])
            except Exception as e:  # noqa: BLE001
                log(f"fonctionnalité {name} : indisponible ({str(e)[:80]})")
                break
            if ex:
                items.append(ex)
                feats += 1
    seen = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(json.loads(line)["messages"][1]["content"])
            except (ValueError, KeyError, IndexError):
                pass
    fresh = [x for x in items if x["messages"][1]["content"] not in seen]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        for x in fresh:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    total = len(out.read_text(encoding="utf-8").splitlines()) if out.exists() else 0
    return {"bugs": len(items) - feats, "features": feats, "projects": got_projects, "added": len(fresh),
            "total": total, "bench_tasks": len(bench_tasks)}


def http_ask():
    """Parle à la grande IA via TON Syrius (point d'accès réservé à GitHub, avec un budget quotidien)."""
    import os
    import urllib.request
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "training"))
    import syrius_auth
    base = os.environ.get("SYRIUS_URL", "").rstrip("/")

    def ask(system: str, prompt: str) -> str:
        req = urllib.request.Request(base + "/api/training/worker/coder-ask",
                                     data=json.dumps({"system": system, "prompt": prompt}).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {syrius_auth.token()}", "X-Syrius": "1",
                                              "Content-Type": "application/json", "User-Agent": "SyriusCoder/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:  # nosec B310 (adresse de ton Syrius)
            return json.loads(r.read()).get("text", "")
    return ask


if __name__ == "__main__":
    import time
    # graine = le jour : de nouveaux bugs chaque nuit (sinon on referait toujours les mêmes exemples)
    res = run(http_ask(), bugs=int(sys.argv[1]) if len(sys.argv) > 1 else 120, seed=int(time.time() // 86400))
    print(json.dumps(res, ensure_ascii=False))
