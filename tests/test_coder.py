"""IA programmeuse : modifications SEARCH/REPLACE sûres, exemples vérifiés par les tests, banc d'essai, point d'accès serveur."""
import json
import random

import pytest
from fastapi.testclient import TestClient

from coder import bench, edits, make_data, mutate, sandbox, tasks
from server import autogen, coderask, github_oidc
from tests.conftest import H, login
from tests.test_github_oidc import KEYS, token

FILES = {"m.py": "def f(a):\n    return a + 1\n\n\ndef g(a):\n    return a + 1\n"}


def blk(path, s, r):
    return edits.to_block(path, s, r)


def test_edits_appliquees_et_refusees(tmp_path):
    (tmp_path / "m.py").write_text(FILES["m.py"])
    (tmp_path / "selfcode").mkdir()
    (tmp_path / "selfcode" / "forbidden.txt").write_text("secret.py\nserver/\n")
    ok = edits.apply(tmp_path, edits.parse(blk("m.py", "def f(a):\n    return a + 1", "def f(a):\n    return a + 2")))
    assert "return a + 2" in (tmp_path / "m.py").read_text() and "+    return a + 2" in ok.diff
    (tmp_path / "m.py").write_text(FILES["m.py"])
    for bad, why in [(blk("m.py", "    return a + 1", "x"), "ambigu"), (blk("m.py", "absent", "x"), "introuvable"),
                     (blk("../evil.py", "a", "b"), "refusé"), (blk("/etc/passwd", "a", "b"), "refusé"),
                     (blk("secret.py", "a", "b"), "protégé"), (blk("server/x.py", "a", "b"), "protégé"),
                     (blk("autre.py", "a", "b"), "introuvable")]:
        with pytest.raises(edits.EditError, match=why):
            edits.apply(tmp_path, edits.parse(bad))
    with pytest.raises(edits.EditError):
        edits.parse("du texte sans bloc")
    with pytest.raises(edits.EditError):
        edits.parse("m.py\n<<<<<<< SEARCH\na\n=======\nb\n")  # bloc jamais fermé


def test_tout_ou_rien(tmp_path):
    (tmp_path / "m.py").write_text(FILES["m.py"])
    two = blk("m.py", "def g(a):\n    return a + 1", "def g(a):\n    return a") + "\n\n" + blk("m.py", "inconnu", "x")
    with pytest.raises(edits.EditError):
        edits.apply(tmp_path, edits.parse(two), forbidden=[])
    assert (tmp_path / "m.py").read_text() == FILES["m.py"]  # rien n'a été écrit


def test_nouveau_fichier_seulement_dans_tests(tmp_path):
    ok = edits.apply(tmp_path, [edits.Edit("tests/test_x.py", "", "def test_a():\n    pass")], forbidden=[])
    assert (tmp_path / "tests" / "test_x.py").exists() and ok.files
    with pytest.raises(edits.EditError):
        edits.apply(tmp_path, [edits.Edit("nouveau.py", "", "x = 1")], forbidden=[])


def test_depot_reel_respecte_les_fichiers_interdits(tmp_path):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    pats = edits.forbidden_patterns(root)
    assert "server/coderask.py" in pats and "coder/" in pats
    assert edits.is_forbidden("server/auth.py", pats) or edits.is_forbidden("server/coderask.py", pats)


def test_bac_a_sable():
    with sandbox.project(tasks.SEEDS["texte"]) as d:
        ok, _, n = sandbox.run_tests(d)
    assert ok and n >= 3
    with sandbox.project({"a.py": "def f():\n    return 1\n", "test_a.py": "from a import f\n\n\ndef test_a():\n    assert f() == 2\n"}) as d:
        ok, out, _ = sandbox.run_tests(d)
    assert not ok and "assert" in out
    with sandbox.project({"test_b.py": "def test_b():\n    while True:\n        pass\n"}) as d:
        ok, out, _ = sandbox.run_tests(d, timeout=3)
    assert not ok  # boucle infinie : arrêtée


def test_mutation_reparable():
    src = tasks.SEEDS["panier"]["cart.py"]
    seen = 0
    for seed in range(20):
        m = mutate.mutate(src, random.Random(seed))
        if not m:
            continue
        buggy, good, bad = m
        fix = mutate.edit_for(buggy, good, bad)
        assert fix is not None
        with sandbox.project({"x.py": buggy}) as d:
            edits.apply(d, [edits.Edit("x.py", *fix)], forbidden=[])
            assert (d / "x.py").read_text() == src
        seen += 1
    assert seen >= 10


def oracle(task):
    return lambda s, p: tasks.answer("Je corrige.", [task["fix"]])


def test_banc_d_essai_solvable_et_stable():
    ts = bench.build()
    assert len(ts) >= 12
    assert [t["fix"] for t in ts] == [t["fix"] for t in bench.build()]  # graine fixe : toujours les mêmes bugs
    assert all(bench.solve(t, oracle(t))[0] for t in ts)
    r = bench.run(lambda s, p: "je ne sais pas", ts[:4])
    assert r["score"] == 0 and r["n"] == 4
    tricheur = bench.run(lambda s, p: tasks.answer("x", [("test_textutil.py", "assert slug", "# assert slug")]), ts[:2])
    assert tricheur["score"] <= 0.5  # modifier les tests ne règle pas un bug des sources


def test_exemples_de_bugs_verifies():
    ex = make_data.bug_examples(tasks.SEEDS, 6, seed=3)
    assert len(ex) == 6
    for e in ex:
        m = e["messages"]
        assert [x["role"] for x in m] == ["system", "user", "assistant"]
        assert "Sortie des tests" in m[1]["content"] and "<<<<<<< SEARCH" in m[2]["content"]


def prof(reply_by_kind):
    def ask(system, prompt):
        return reply_by_kind(system, prompt)
    return ask


def test_projet_du_professeur_gardé_seulement_si_les_tests_passent():
    bon = json.dumps({"name": "Maths", "module": "def double(x):\n    return x * 2\n\n\ndef triple(x):\n    return x * 3\n",
                      "tests": "from maths import double, triple\n\n\ndef test_a():\n    assert double(2) == 4\n\n\ndef test_b():\n    assert triple(2) == 6\n\n\ndef test_c():\n    assert double(0) == 0\n"})
    assert make_data.new_project(lambda s, p: bon, "x") is not None
    faux = bon.replace("== 6", "== 7")
    assert make_data.new_project(lambda s, p: faux, "x") is None
    assert make_data.new_project(lambda s, p: "pas du json", "x") is None


def test_fonctionnalite_verifiee_par_les_tests():
    files = tasks.SEEDS["texte"]
    bonne = tasks.answer("J'ajoute une fonction.", [
        ("textutil.py", "def count_words(s):\n    return len(s.split())", "def count_words(s):\n    return len(s.split())\n\n\ndef shout(s):\n    return s.upper()"),
        ("test_textutil.py", "def test_count_words():", "def test_shout():\n    from textutil import shout\n    assert shout('a') == 'A'\n\n\ndef test_count_words():")])
    assert make_data.feature_example(lambda s, p: bonne, files, "Ajoute.") is not None
    sans_test = tasks.answer("x", [("textutil.py", "def count_words(s):", "def count_words(s):\n    # compte")])
    assert make_data.feature_example(lambda s, p: sans_test, files, "Ajoute.") is None  # aucun test ajouté
    casse = tasks.answer("x", [("textutil.py", "return len(s.split())", "return 0")])
    assert make_data.feature_example(lambda s, p: casse, files, "Ajoute.") is None  # tests cassés


def test_chaine_complete_sans_doublons(tmp_path):
    out = tmp_path / "coder.jsonl"
    r = make_data.run(lambda s, p: "n'importe quoi", out=out, bugs=8, projects_n=1, features_per=1, log=lambda *_: None)
    assert r["added"] == 8 and r["total"] == 8
    r2 = make_data.run(lambda s, p: "n'importe quoi", out=out, bugs=8, projects_n=1, features_per=1, log=lambda *_: None)
    assert r2["added"] == 0 and r2["total"] == 8  # mêmes exemples : pas de doublon
    assert all(json.loads(x)["messages"][0]["content"] == tasks.SYSTEM for x in out.read_text().splitlines())


def test_point_d_acces_serveur(make_client, monkeypatch):
    owner = make_client()
    login(owner)
    monkeypatch.setattr(github_oidc, "_jwks", lambda: KEYS)
    monkeypatch.setattr(github_oidc.time, "time", lambda: 1500)
    seen = []
    monkeypatch.setattr(autogen, "_ask", lambda p, prompt, *a, **k: seen.append(prompt) or "def f(): pass")
    worker = TestClient(owner.app, base_url="https://testserver")
    W = {**H, "Authorization": f"Bearer {token()}"}
    r = worker.post("/api/training/worker/coder-ask", headers=W, json={"system": "s", "prompt": "Écris une fonction."})
    assert r.status_code == 200 and r.json()["text"] == "def f(): pass" and r.json()["used"] == 1
    assert owner.post("/api/training/worker/coder-ask", headers=H, json={"prompt": "Écris une fonction."}).status_code == 401
    monkeypatch.setattr(coderask, "DAILY_BUDGET", 1)
    assert worker.post("/api/training/worker/coder-ask", headers=W, json={"prompt": "Écris une fonction."}).status_code == 429
    assert worker.post("/api/training/worker/coder-ask", headers=W, json={"prompt": "court"}).status_code == 422


def test_taches_implemente_et_banc_plus_large():
    ts = bench.build()
    kinds = {t["kind"] for t in ts}
    assert kinds == {"bug", "implement"} and len(ts) >= 25
    imp = next(t for t in ts if t["kind"] == "implement")
    assert "NotImplementedError" in imp["files"][imp["file"]] and "Implémente" in tasks.make_prompt(
        imp["files"], tasks.instruction("implement"), imp["failing"])
    assert all(bench.solve(t, oracle(t))[0] for t in ts)
    r = bench.run(lambda s, p: "rien", limit=6)
    assert r["n"] == 6 and r["version"] == bench.BENCH_VERSION and len({f["project"] for f in r["fails"]}) >= 2  # réparti


def test_le_banc_reste_inedit(tmp_path):
    bench_keys = {t["key"] for t in bench.build()}
    r = make_data.run(lambda s, p: "x", out=tmp_path / "c.jsonl", bugs=60, projects_n=0, features_per=0,
                      log=lambda *_: None)
    assert r["added"] >= 30
    text = (tmp_path / "c.jsonl").read_text()
    for proj in bench.BENCH_ONLY:  # projets réservés au banc : jamais dans l'entraînement
        for t in bench.build():
            if t["project"] == proj:
                assert t["files"][t["file"]] not in text
    ex = make_data.bug_examples({k: v for k, v in tasks.SEEDS.items() if k not in bench.BENCH_ONLY}, 40, 5, avoid=set(bench_keys))
    assert len(ex) >= 25  # les bugs possibles de 5 petits projets sont en nombre limité


def test_graines_differentes_donnent_de_nouveaux_exemples(tmp_path):
    out = tmp_path / "c.jsonl"
    a = make_data.run(lambda s, p: "x", out=out, bugs=20, projects_n=0, features_per=0, seed=1, log=lambda *_: None)
    b = make_data.run(lambda s, p: "x", out=out, bugs=20, projects_n=0, features_per=0, seed=2, log=lambda *_: None)
    assert b["added"] >= 5 and b["total"] == a["total"] + b["added"]


def test_comparaison_avant_apres():
    from coder import compare
    av = {"version": 2, "score": 0.20, "passed": 6, "n": 31}
    assert compare.verdict(av, {**av, "score": 0.40, "passed": 12})[0]
    assert not compare.verdict(av, {**av, "score": 0.22})[0]  # gain trop faible
    assert "Moins bon" in compare.verdict(av, {**av, "score": 0.1})[1]
    assert not compare.verdict(av, {**av, "version": 3, "score": 0.9})[0]  # banc différent
