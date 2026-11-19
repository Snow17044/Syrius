"""Vrais exemples : les changements de code que TU as acceptés (demandes « Améliorer Syrius » fusionnées).

Chaque demande acceptée devient un exemple (demande + fichiers → modification), vérifié : la modification doit
s'appliquer proprement sur les fichiers d'origine. Les demandes refusées sont seulement comptées.
Données lues avec la commande `gh` (jeton du workflow) ; les fonctions de conversion sont pures et testées.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from . import edits, tasks

MAX_FILES, MAX_HUNKS, MAX_CHANGED, MAX_FILE_CHARS = 3, 6, 60, 6000
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")


def hunks(patch: str) -> list[tuple[str, str]]:
    """[(ancien texte, nouveau texte)] pour chaque morceau d'un patch unifié."""
    out, old, new, inside = [], [], [], False
    lines = patch.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # fin de texte, pas une ligne du patch
    for line in lines:
        if _HUNK.match(line):
            if inside and old:
                out.append(("\n".join(old), "\n".join(new)))
            old, new, inside = [], [], True
        elif not inside or line.startswith("\\"):
            continue
        elif line.startswith("+"):
            new.append(line[1:])
        elif line.startswith("-"):
            old.append(line[1:])
        else:
            old.append(line[1:])
            new.append(line[1:])
    if inside and old:
        out.append(("\n".join(old), "\n".join(new)))
    return out


def request_from_body(body: str) -> str:
    m = re.search(r"Demande du propriétaire\s*:\s*(.+?)(?:\n\n|\n---|\Z)", body or "", re.S)
    return " ".join(m.group(1).split())[:600] if m else ""


def example(request: str, base_files: dict, patches: dict, forbidden: list[str] | None = None):
    """(exemple, raison du refus). L'exemple n'existe que si la modification s'applique sur les fichiers d'origine."""
    if not request or not base_files or len(base_files) > MAX_FILES:
        return None, "demande ou fichiers absents"
    blocks, changed = [], 0
    for path in sorted(patches):
        hs = hunks(patches[path])
        if not hs or path not in base_files:
            return None, f"{path} : patch inutilisable"
        for old, new in hs:
            changed += abs(len(new.split("\n")) - len(old.split("\n"))) + 1
            blocks.append(edits.Edit(path, old, new))
    if not blocks or len(blocks) > MAX_HUNKS or changed > MAX_CHANGED * 2:
        return None, "changement trop grand pour un exemple"
    if any(len(t) > MAX_FILE_CHARS for t in base_files.values()):
        return None, "fichier trop long"
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for p, t in base_files.items():
            (root / p).parent.mkdir(parents=True, exist_ok=True)
            (root / p).write_text(t, encoding="utf-8")
        try:
            edits.apply(root, blocks, forbidden=forbidden or [], write=False)
        except edits.EditError as e:
            return None, f"ne s'applique pas : {str(e)[:80]}"
    reply = tasks.answer("Voici la modification demandée.", [(b.path, b.search, b.replace) for b in blocks])
    prompt = tasks.make_prompt(base_files, request)
    return tasks.messages(prompt, reply), ""


def _gh(*args: str, raw: bool = False) -> str:
    cmd = ["gh", "api", *(["-H", "Accept: application/vnd.github.raw"] if raw else []), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True).stdout


def collect(repo: str, root: Path, log=print) -> dict:
    """Parcourt les propositions `syrius-auto/*` : acceptées → exemples, refusées → comptées."""
    forbidden = edits.forbidden_patterns(root)
    out = {"merged": 0, "rejected": 0, "examples": [], "skipped": {}}
    prs = json.loads(_gh(f"repos/{repo}/pulls?state=closed&per_page=100"))
    for pr in prs:
        if not str(pr.get("head", {}).get("ref", "")).startswith("syrius-auto/"):
            continue
        if not pr.get("merged_at"):
            out["rejected"] += 1
            continue
        out["merged"] += 1
        try:
            files = json.loads(_gh(f"repos/{repo}/pulls/{pr['number']}/files?per_page=50"))
            if any(edits.is_forbidden(f["filename"], forbidden) or f.get("status") != "modified" or "patch" not in f
                   for f in files):
                raise ValueError("fichier protégé, nouveau ou binaire")
            base_sha = pr["base"]["sha"]
            base = {f["filename"]: _gh(f"repos/{repo}/contents/{f['filename']}?ref={base_sha}", raw=True) for f in files[:MAX_FILES + 1]}
            ex, why = example(request_from_body(pr.get("body", "")), base, {f["filename"]: f["patch"] for f in files}, forbidden)
        except Exception as e:  # noqa: BLE001 — un PR illisible ne doit pas arrêter les autres
            ex, why = None, str(e)[:80]
        if ex:
            out["examples"].append(ex)
        else:
            out["skipped"][why] = out["skipped"].get(why, 0) + 1
            log(f"PR #{pr['number']} ignorée : {why}")
    return out


if __name__ == "__main__":  # python -m coder.real DÉPÔT SORTIE.jsonl
    repo, dest = sys.argv[1], Path(sys.argv[2])
    res = collect(repo, Path(__file__).resolve().parent.parent)
    dest.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in res["examples"]), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "examples"} | {"examples": len(res["examples"])}, ensure_ascii=False))
