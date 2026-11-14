"""Syrius s'améliore lui-même : une IA programmeuse gratuite (via OpenRouter) modifie le code, les tests vérifient.

Étapes (appelées par le workflow « Améliorer Syrius ») :
  python selfcode/agent.py next       → prend la demande suivante sur ton Syrius (sinon s'arrête)
  python selfcode/agent.py code       → l'IA programme, puis les tests tournent dans un conteneur ISOLÉ
                                        (sans Internet ni secrets) ; jusqu'à 3 essais
  python selfcode/agent.py report ... → renvoie le résultat au tableau de bord

Garde-fous : fichiers protégés (selfcode/forbidden.txt), tests existants intouchables, aucune commande shell
proposée par l'IA n'est exécutée, et rien n'est publié : seulement proposé.
"""
from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "selfcode"
MODELS = [m.strip() for m in os.environ.get(
    "SYRIUS_CODER_MODELS", "qwen/qwen3-coder:free,nvidia/nemotron-3-ultra-550b-a55b:free,google/gemma-4-31b-it:free"
).split(",") if m.strip()]
RULES = """Tu modifies le code de Syrius, un assistant personnel (serveur Python FastAPI dans server/, interface web
dans web/, application Android dans android/). Règles strictes :
- Fais UNIQUEMENT le changement demandé, le plus petit et le plus propre possible.
- Interface et messages en français. Garde le style existant.
- N'ajoute aucune dépendance. Ne touche pas à la sécurité, aux comptes, aux mots de passe ni aux filtres.
- Fichiers interdits : {forbidden}.
- Si c'est utile, ajoute un NOUVEAU fichier de test dans tests/ (ne modifie pas les tests existants).
Demande du propriétaire :
{request}
"""


def api(path: str, body: dict | None = None) -> dict:
    url = os.environ["SYRIUS_URL"].rstrip("/") + path
    req = urllib.request.Request(url, data=json.dumps(body or {}).encode(), method="POST", headers={
        "Authorization": f"Bearer {os.environ['SYRIUS_TRAINING_TOKEN']}", "Content-Type": "application/json",
        "X-Syrius": "1", "User-Agent": "SyriusSelfCode/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310 (adresse de ton Syrius)
        return json.loads(r.read(200_000) or b"{}")


def forbidden() -> list[str]:
    lines = (ROOT / "selfcode" / "forbidden.txt").read_text(encoding="utf-8").splitlines()
    return [x.strip() for x in lines if x.strip() and not x.startswith("#")]


def changed() -> list[tuple[str, str]]:
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    return [(line[:2].strip(), line[3:].strip().strip('"')) for line in out.splitlines() if line.strip()]


def violations() -> list[str]:
    bad = []
    rules = forbidden()
    for status, path in changed():
        if path.startswith(".aider"):
            continue
        if any(path == r or (r.endswith("/") and path.startswith(r)) or fnmatch.fnmatch(path, r) for r in rules):
            bad.append(f"fichier protégé modifié : {path}")
        elif path.startswith("tests/") and status != "??":
            bad.append(f"test existant modifié : {path}")
    return bad


def run_tests() -> tuple[bool, str]:
    """Tests dans un conteneur sans réseau ni secrets : le code écrit par l'IA ne peut rien voler."""
    cmd = ["docker", "run", "--rm", "--network", "none", "-v", f"{ROOT}:/w", "-v", f"{WORK / 'cvenv'}:/cv",
           "-w", "/w", "python:3.12-slim", "/cv/bin/python", "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=1500)
    tail = "\n".join((p.stdout + p.stderr).strip().splitlines()[-60:])
    return p.returncode == 0, tail


def pick_model() -> str:
    try:
        with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=30) as r:  # nosec B310
            ids = {m["id"] for m in json.loads(r.read())["data"]}
    except Exception:  # noqa: BLE001
        ids = set()
    for m in MODELS:
        if not ids or m in ids:
            return m
    return MODELS[0]


def aider(model: str, message: str) -> None:
    msg = WORK / "message.txt"
    msg.write_text(message, encoding="utf-8")
    subprocess.run([str(WORK / "avenv" / "bin" / "aider"), "--model", f"openrouter/{model}", "--message-file", str(msg),
                    "--yes-always", "--no-auto-commits", "--no-dirty-commits", "--no-suggest-shell-commands",
                    "--no-check-update", "--analytics-disable", "--no-show-model-warnings", "--no-gitignore",
                    "--map-tokens", "2048", "--no-stream"], cwd=ROOT, timeout=1200, check=False)


def cmd_next() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    item = api("/api/training/worker/code-next").get("request")
    out = os.environ.get("GITHUB_OUTPUT")
    if not item:
        print("Aucune demande en attente.")
        if out:
            Path(out).open("a").write("go=false\n")
        return
    (WORK / "request.json").write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    print(f"Demande {item['id']} : {item['text']}")
    if out:
        Path(out).open("a").write(f"go=true\nid={item['id']}\n")


def cmd_code() -> None:
    item = json.loads((WORK / "request.json").read_text(encoding="utf-8"))
    model = pick_model()
    print(f"IA programmeuse : {model}")
    message = RULES.format(forbidden=", ".join(forbidden()), request=item["text"])
    result = {"ok": False, "summary": "", "tests": "", "model": model}
    for attempt in range(1, 4):
        aider(model, message)
        bad = violations()
        if bad:
            subprocess.run(["git", "checkout", "--", "."], cwd=ROOT, check=False)
            subprocess.run(["git", "clean", "-fdq"], cwd=ROOT, check=False)
            message = RULES.format(forbidden=", ".join(forbidden()), request=item["text"]) + \
                "\nATTENTION : ton essai précédent a été annulé car il modifiait : " + "; ".join(bad)
            result["summary"] = "Refusé : " + "; ".join(bad)
            continue
        if not [p for _, p in changed() if not p.startswith(".aider")]:
            result["summary"] = "L'IA n'a fait aucun changement."
            continue
        ok, tail = run_tests()
        print(tail)
        if ok:
            result.update(ok=True, tests=tail.splitlines()[-1] if tail else "tests réussis")
            break
        result["tests"] = (tail.splitlines()[-1] if tail else "tests échoués")[:200]
        result["summary"] = f"Les tests échouent (essai {attempt}/3)."
        message = f"Les tests échouent après ton changement. Corrige le code (pas les tests existants) :\n{tail[-3000:]}"
    (WORK / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        Path(out).open("a").write(f"ok={'true' if result['ok'] else 'false'}\n")


def cmd_report(status: str, pr: str = "") -> None:
    item = json.loads((WORK / "request.json").read_text(encoding="utf-8"))
    res = json.loads((WORK / "result.json").read_text(encoding="utf-8")) if (WORK / "result.json").exists() else {}
    summary = res.get("summary", "")
    if status == "proposed":
        stat = subprocess.run(["git", "diff", "--stat", "HEAD~1"], cwd=ROOT, capture_output=True, text=True).stdout
        summary = "Changement proposé (tests réussis). Fichiers :\n" + stat.strip()[-1200:]
    api("/api/training/worker/code-report", {"id": item["id"], "status": status, "pr": pr,
                                              "summary": summary or "Échec.", "tests": res.get("tests", "")})


if __name__ == "__main__":
    {"next": lambda: cmd_next(), "code": lambda: cmd_code(),
     "report": lambda: cmd_report(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")}[sys.argv[1]]()
