"""L'Atelier d'Aurora, côté serveur de GitHub : écrire → lancer → lire les erreurs → corriger, jusqu'à ce que ça marche.

  python selfcode/atelier.py next    → prend le projet suivant sur ton Syrius (sinon s'arrête)
  python selfcode/atelier.py work    → boucle de travail (5 essais au plus), avancement envoyé après chaque essai
  python selfcode/atelier.py fail    → signale un arrêt brutal (panne, délai dépassé)

Le code écrit par l'IA tourne dans un conteneur Docker jetable : aucun secret ni variable d'environnement du
serveur de GitHub n'y entre, seul le dossier du projet y est monté, avec des limites de mémoire, de processus et
de temps. Internet y est ouvert (pip, npm), sauf l'adresse interne du serveur (bloquée par le workflow).
L'IA est interrogée via ton Syrius (/api/training/worker/coder-ask : budget quotidien, aucune clé ici).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import syrius_auth  # noqa: E402

WORK = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "atelier"
PROJ = WORK / "projet"
MAX_ATTEMPTS = 5
RUN_TIMEOUT = 420  # secondes pour installer + tester
IMAGES = {"python": "python:3.13-slim", "node": "node:22-slim",
          "web": "mcr.microsoft.com/playwright:v1.49.1-noble"}  # sites : Node + vrai navigateur (Chromium)
PLAYWRIGHT = "1.49.1"  # même version que l'image : le navigateur est déjà dedans
# « docker » : serveur de GitHub (un conteneur jetable par essai) ; « local » : serveur Hugging Face de l'atelier
# (le code tourne dans un processus séparé, sans aucun secret, avec des limites de temps et de taille).
RUNNER = os.environ.get("ATELIER_RUNNER", "docker")
KIT = os.environ.get("ATELIER_KIT", "/opt/kit")  # Playwright déjà installé (serveur Hugging Face)
TOKEN = ""  # clé de l'atelier (serveur Hugging Face) ; vide = identité officielle de GitHub
SKIP_DIRS = {"node_modules", "__pycache__", ".pytest_cache", ".venv", "venv", ".git", ".npm", ".cache"}

SYSTEM = """Tu es Aurora, une développeuse experte. Tu travailles sur un vrai ordinateur Linux : ce que tu écris est
enregistré dans un dossier, puis ta commande d'installation et ta commande de test sont VRAIMENT exécutées.
Tu reçois la sortie et tu corriges jusqu'à ce que les tests passent.

Réponds EXACTEMENT dans ce format, sans rien d'autre :
RÉSUMÉ: 1 à 3 phrases en français (ce que fait le programme, ou ce que tu as corrigé)
ENVIRONNEMENT: python, node ou web
INSTALLATION: une commande shell (ex. pip install requests  /  npm install express) ou « aucune »
TEST: une commande shell qui vérifie que tout marche et se TERMINE (code de sortie 0 = réussi)
### FICHIER: chemin/relatif.ext
```
contenu COMPLET du fichier
```
(un bloc par fichier ; à chaque essai, renvoie le contenu complet de chaque fichier que tu modifies ou crées)

Règles :
- Python : tests avec pytest (installe-le dans INSTALLATION : pip install pytest ...), TEST: python -m pytest -q
- Node.js : un package.json, tests avec node --test (intégré, rien à installer), TEST: node --test
- Un serveur (Express, Flask…) ne doit jamais tourner sans fin dans TEST : écris un test qui le démarre, fait
  une vraie requête, vérifie la réponse puis l'arrête (ex. app.listen(0) puis close()).
- SITE WEB (ENVIRONNEMENT: web) : un site statique dans le dossier site/ (site/index.html, site/style.css,
  site/script.js…), sans étape de compilation, beau et adapté au téléphone (responsive). Tu le vérifies dans un VRAI
  navigateur : INSTALLATION: npm install playwright@1.49.1  /  TEST: node --test  ; le test (tests/site.test.js)
  démarre un petit serveur http (module http de Node) sur le dossier site/, ouvre la page avec
  require('playwright').chromium (écran 390×844), vérifie qu'il n'y a AUCUNE erreur dans la console ni de ressource
  introuvable, que les éléments importants sont visibles et que les boutons/formulaires marchent (clic, saisie).
  Un site avec un serveur (Express…) est possible si on te le demande : mets alors aussi la partie visible dans site/.
- Pas d'interface graphique de bureau, pas de saisie clavier pendant les tests, pas de clé d'API ni de mot de passe.
- Le programme doit aussi marcher sur Termux (Android) : pas de dépendance exotique ni de binaire spécial.
- Ne triche jamais : un test qui ne vérifie rien, ou un test modifié pour passer sans corriger le code, est interdit."""


def api(path: str, body: dict) -> dict:
    url = os.environ["SYRIUS_URL"].rstrip("/") + path
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {TOKEN or syrius_auth.token()}", "Content-Type": "application/json",
        "X-Syrius": "1", "User-Agent": "SyriusAtelier/1.0"})
    with urllib.request.urlopen(req, timeout=150) as r:  # nosec B310 (adresse de ton Syrius)
        return json.loads(r.read(3_000_000) or b"{}")


def ask(prompt: str) -> str:
    return str(api("/api/training/worker/coder-ask", {"system": SYSTEM, "prompt": prompt[-29000:],
                                                       "max_tokens": 6000}).get("text", ""))


# ------------------------------------------------------------------ lecture de la réponse de l'IA
_FIELD = re.compile(r"^\s*\**(RÉSUMÉ|RESUME|RÉSUME|ENVIRONNEMENT|INSTALLATION|TEST)\**\s*:\s*\**\s*(.*)$", re.I | re.M)
_FILE = re.compile(r"^#{2,4}\s*FICHIER\s*:\s*`?([^\n`]+?)`?\s*\n+```[^\n]*\n(.*?)\n```", re.S | re.M)
_SAFE_PATH = re.compile(r"^(?!/)(?!.*\.\.)[\w.\-/ ]{1,120}$")


def parse(reply: str) -> dict:
    fields = {}
    for key, value in _FIELD.findall(reply):
        k = key.upper().replace("É", "E")
        fields.setdefault("RESUME" if k.startswith("RESUM") else k, value.strip().strip("`"))
    files = {}
    for path, content in _FILE.findall(reply):
        path = path.strip()
        while path.startswith("./"):  # « ./a.py » → « a.py » ; « ../ » reste refusé
            path = path[2:]
        if _SAFE_PATH.match(path) and not any(part in SKIP_DIRS for part in path.split("/")):
            files[path] = content + "\n"
    env = fields.get("ENVIRONNEMENT", "").lower()
    env = "web" if re.search(r"\bweb\b|site|html|navigateur", env) else \
        "node" if "node" in env or "javascript" in env else "python"
    setup = fields.get("INSTALLATION", "")
    if setup.lower().strip(" .«»\"'") in ("", "aucune", "aucun", "rien", "none", "-"):
        setup = ""
    return {"summary": fields.get("RESUME", "")[:600], "env": env, "setup": setup[:300], "test": fields.get("TEST", "")[:300],
            "files": files}


# ------------------------------------------------------------------ exécution isolée
def write_files(files: dict[str, str]) -> None:
    for path, content in files.items():
        dest = (PROJ / path).resolve()
        if PROJ.resolve() not in dest.parents:
            continue  # jamais en dehors du dossier du projet
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")


def project_files() -> dict[str, str]:
    out = {}
    for p in sorted(PROJ.rglob("*")):
        rel = p.relative_to(PROJ)
        if p.is_file() and not any(part in SKIP_DIRS for part in rel.parts) and p.stat().st_size <= 60_000 \
                and rel.name not in ("package-lock.json",):
            try:
                out[str(rel)] = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
    return dict(list(out.items())[:40])


def clean_env() -> dict:
    """Environnement du code de l'IA : le strict minimum, jamais la clé de l'atelier ni un autre secret."""
    keep = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL", "PLAYWRIGHT_BROWSERS_PATH", "TZ") if k in os.environ}
    home = WORK / "home"
    home.mkdir(parents=True, exist_ok=True)
    return {**keep, "HOME": str(home), "CI": "1", "PIP_ROOT_USER_ACTION": "ignore", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "npm_config_update_notifier": "false", "npm_config_fund": "false", "npm_config_audit": "false"}


def run_local(script: str) -> tuple[bool, str]:
    """Serveur Hugging Face : le script tourne dans son propre groupe de processus, environnement vidé, limites."""
    import signal
    # limites posées par le shell lui-même (sûr même depuis un fil d'exécution) : temps de calcul, taille des fichiers
    limits = f"ulimit -t {RUN_TIMEOUT}; ulimit -f 300000; ulimit -c 0\n"
    p = subprocess.Popen(["bash", "-c", limits + script], cwd=PROJ, env=clean_env(), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        out, _ = p.communicate(timeout=RUN_TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)  # tout le groupe : serveurs et sous-processus compris
        out, _ = p.communicate()
        return False, ((out or "")[-5000:] + f"\nTROP LONG : arrêté après {RUN_TIMEOUT} s (un serveur ou une boucle "
                       "ne s'arrête pas ?)").strip()
    try:
        os.killpg(p.pid, signal.SIGKILL)  # un serveur lancé en arrière-plan ne survit pas au test
    except (ProcessLookupError, PermissionError):
        pass
    return p.returncode == 0, (out or "").strip()[-6000:]


def run(env: str, setup: str, test: str) -> tuple[bool, str]:
    """Installation puis test dans un conteneur jetable : ni secret, ni variable d'environnement de GitHub."""
    script = (f"set -e\n{setup}\necho '=== TESTS ==='\n{test}\n") if setup else f"set -e\necho '=== TESTS ==='\n{test}\n"
    if RUNNER == "local":
        return run_local(script)
    (WORK / "run.sh").write_text(script, encoding="utf-8")
    cmd = ["docker", "run", "--rm", "--memory", "2g", "--cpus", "2", "--pids-limit", "512",
           "-v", f"{PROJ}:/projet", "-v", f"{WORK / 'run.sh'}:/run.sh:ro", "-w", "/projet",
           "-e", "HOME=/tmp", "-e", "CI=1", "-e", "PIP_ROOT_USER_ACTION=ignore", "-e", "npm_config_update_notifier=false",
           IMAGES[env], "timeout", "-k", "10", str(RUN_TIMEOUT), "sh", "/run.sh"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=RUN_TIMEOUT + 60)
    except subprocess.TimeoutExpired:
        return False, f"TROP LONG : arrêté après {RUN_TIMEOUT} s (un programme ou un serveur ne s'arrête pas ?)"
    out = (p.stdout + "\n" + p.stderr).strip()
    if p.returncode == 124:
        out += f"\nTROP LONG : arrêté après {RUN_TIMEOUT} s (un serveur ou une boucle ne s'arrête pas ?)"
    return p.returncode == 0, out[-6000:]


SHOT_JS = r"""
// Capture d'écran du site au format téléphone (lancée par l'atelier, pas par l'IA).
const http = require("http"), fs = require("fs"), path = require("path");
const { chromium } = require(process.env.SHOT_KIT + "/node_modules/playwright");
const root = process.argv[2], out = process.argv[3];
const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml", ".json": "application/json" };
const server = http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split("?")[0]);
  if (p.endsWith("/")) p += "index.html";
  const f = path.join(root, path.normalize(p));
  if (!f.startsWith(root) || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "Content-Type": types[path.extname(f)] || "application/octet-stream" });
  fs.createReadStream(f).pipe(res);
}).listen(0, async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  await page.goto(`http://127.0.0.1:${server.address().port}/`, { waitUntil: "networkidle", timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(800);
  await page.screenshot({ path: out, type: "jpeg", quality: 70 });
  await browser.close(); server.close();
});
"""


def screenshot() -> str:
    """Capture du site (site/index.html ou index.html) au format téléphone, en JPEG base64 ; "" si pas de site."""
    import base64
    root = "/projet/site" if (PROJ / "site" / "index.html").exists() else "/projet" if (PROJ / "index.html").exists() else ""
    if not root:
        return ""
    kit = WORK / "kit"
    kit.mkdir(exist_ok=True)
    (kit / "shot.js").write_text(SHOT_JS, encoding="utf-8")
    (kit / "capture.jpg").unlink(missing_ok=True)
    if RUNNER == "local":  # serveur Hugging Face : Playwright déjà installé dans KIT
        cmd = ["timeout", "90", "node", str(kit / "shot.js"), str(PROJ) + root[len("/projet"):], str(kit / "capture.jpg")]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=kit, env={**clean_env(), "SHOT_KIT": KIT})
        except subprocess.TimeoutExpired:
            return ""
        shot = kit / "capture.jpg"
        return base64.b64encode(shot.read_bytes()).decode() if shot.exists() and shot.stat().st_size <= 600_000 else ""
    cmd = ["docker", "run", "--rm", "--memory", "2g", "--pids-limit", "512", "-v", f"{PROJ}:/projet:ro",
           "-v", f"{kit}:/kit", "-w", "/kit", "-e", "HOME=/tmp", "-e", "npm_config_update_notifier=false",
           "-e", "SHOT_KIT=/kit", IMAGES["web"],
           "sh", "-c", f"(test -d node_modules/playwright || npm install -s --no-audit --no-fund playwright@{PLAYWRIGHT}) "
                       f"&& timeout 90 node shot.js {root} /kit/capture.jpg"]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    except subprocess.TimeoutExpired:
        return ""
    shot = kit / "capture.jpg"
    if not shot.exists() or shot.stat().st_size > 600_000:
        return ""
    return base64.b64encode(shot.read_bytes()).decode()


# ------------------------------------------------------------------ étapes
def cmd_next() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    item = api("/api/training/worker/atelier-next", {}).get("project")
    out = os.environ.get("GITHUB_OUTPUT")
    if not item:
        print("Aucun projet en attente.")
        if out:
            Path(out).open("a").write("go=false\n")
        return
    (WORK / "project.json").write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    print(f"Projet {item['id']} : {item['text'][:200]}")
    if out:
        Path(out).open("a").write(f"go=true\nid={item['id']}\n")


def report(pid: str, status: str, attempt: int, plan: dict, summary: str, log: str, shot: str = "") -> None:
    try:
        api("/api/training/worker/atelier-report", {
            "id": pid, "status": status, "attempt": attempt, "summary": summary, "log": log, "env": plan.get("env", ""),
            "setup": plan.get("setup", ""), "test": plan.get("test", ""), "files": project_files(), "screenshot": shot})
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"Avancement non envoyé : {e}")


def cmd_work() -> None:
    work(json.loads((WORK / "project.json").read_text(encoding="utf-8")))


def work(item: dict) -> None:
    """Écrire → lancer → lire les erreurs → corriger, jusqu'à MAX_ATTEMPTS essais."""
    pid = item["id"]
    shutil.rmtree(PROJ, ignore_errors=True)
    PROJ.mkdir(parents=True)
    plan: dict = {}
    prompt = f"Projet demandé :\n{item['text']}\n\nÉcris le projet complet avec ses tests."
    log, summary = "", ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        report(pid, "running", attempt, plan, f"Essai {attempt}/{MAX_ATTEMPTS} : Aurora écrit le code…", log)
        try:
            reply = ask(prompt)
        except (urllib.error.URLError, OSError, ValueError) as e:
            report(pid, "failed", attempt, plan, f"La grande IA ne répond pas ({str(e)[:120]}).", log)
            return
        new = parse(reply)
        if not new["files"] and not plan:
            prompt = (f"Projet demandé :\n{item['text']}\n\nTa réponse précédente ne respectait pas le format (aucun "
                      "bloc « ### FICHIER: »). Recommence en respectant EXACTEMENT le format.")
            log = "Réponse illisible (aucun fichier)."
            continue
        plan = {"env": new["env"] if new["files"] or not plan else plan["env"],
                "setup": new["setup"] if new["test"] else plan.get("setup", ""),
                "test": new["test"] or plan.get("test", "")}
        summary = new["summary"] or summary
        write_files(new["files"])
        if not plan["test"]:
            prompt = "Il manque la ligne TEST: (commande qui vérifie que tout marche). Renvoie la réponse complète."
            continue
        report(pid, "running", attempt, plan, f"Essai {attempt}/{MAX_ATTEMPTS} : installation et tests en cours…", log)
        ok, log = run(plan["env"], plan["setup"], plan["test"])
        print(f"--- essai {attempt} : {'RÉUSSI' if ok else 'échec'} ---\n{log[-3000:]}")
        if ok:
            shot = screenshot()  # un site : capture au format téléphone, affichée dans Syrius Code
            report(pid, "done", attempt, plan, summary or "Le programme marche : tous les tests passent.", log, shot)
            return
        files_now = "\n\n".join(f"### FICHIER: {p}\n```\n{c[:8000]}\n```" for p, c in project_files().items())
        prompt = (f"Projet demandé :\n{item['text']}\n\nFichiers actuels :\n{files_now}\n\nINSTALLATION: {plan['setup'] or 'aucune'}\n"
                  f"TEST: {plan['test']}\n\nLes tests ÉCHOUENT. Sortie réelle (fin) :\n```\n{log[-3500:]}\n```\n\n"
                  "Trouve la cause et corrige le CODE (pas les tests, sauf s'ils sont réellement faux). Renvoie le "
                  "format complet avec les fichiers modifiés.")
    report(pid, "failed", MAX_ATTEMPTS, plan,
           (summary + " — " if summary else "") + f"Les tests échouent encore après {MAX_ATTEMPTS} essais.", log)


def cmd_fail() -> None:
    """Le travail s'est arrêté net (panne, délai dépassé) : on le dit au lieu de laisser « en cours »."""
    f = WORK / "project.json"
    if f.exists():
        report(json.loads(f.read_text(encoding="utf-8"))["id"], "failed", 0, {},
               "L'atelier s'est arrêté avant la fin (panne ou délai dépassé sur le serveur de GitHub).", "")


if __name__ == "__main__":
    {"next": cmd_next, "work": cmd_work, "fail": cmd_fail}[sys.argv[1]]()
