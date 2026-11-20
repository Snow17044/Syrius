"""Modifications de code au format « SEARCH / REPLACE » (comme aider) : lecture stricte et application sûre.

    chemin/du/fichier.py
    <<<<<<< SEARCH
    lignes à remplacer (exactement comme dans le fichier)
    =======
    nouvelles lignes
    >>>>>>> REPLACE

Garde-fous : chemin relatif dans le dépôt, jamais un fichier interdit (selfcode/forbidden.txt), le SEARCH doit se
trouver UNE SEULE fois, tout ou rien (si un bloc échoue, rien n'est écrit).
"""
from __future__ import annotations

import difflib
import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

MAX_EDITS, MAX_BLOCK = 6, 8000
SEARCH, SEP, REPLACE = "<<<<<<< SEARCH", "=======", ">>>>>>> REPLACE"
NEW_FILE_PREFIXES = ("tests/",)


class EditError(ValueError):
    """Modification illisible, dangereuse ou impossible (message affichable)."""


@dataclass
class Edit:
    path: str
    search: str
    replace: str


@dataclass
class Applied:
    files: dict = field(default_factory=dict)  # chemin -> nouveau texte
    diff: str = ""


def _clean_path(line: str) -> str:
    return re.sub(r"^[`*#\s]+|[`*:\s]+$", "", line.strip())


def parse(text: str) -> list[Edit]:
    lines = text.replace("\r\n", "\n").split("\n")
    edits: list[Edit] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() != SEARCH:
            i += 1
            continue
        k = i - 1
        while k >= 0 and (not lines[k].strip() or lines[k].strip().startswith("```")):
            k -= 1  # lignes vides et clôtures de code (```python) : le nom du fichier est au-dessus
        path = _clean_path(lines[k]) if k >= 0 else ""
        j, search = i + 1, []
        while j < len(lines) and lines[j].strip() != SEP:
            search.append(lines[j])
            j += 1
        if j >= len(lines):
            raise EditError(f"bloc sans « {SEP} »")
        m, rep = j + 1, []
        while m < len(lines) and lines[m].strip() != REPLACE:
            rep.append(lines[m])
            m += 1
        if m >= len(lines):
            raise EditError(f"bloc sans « {REPLACE} »")
        s, r = "\n".join(search), "\n".join(rep)
        if len(s) > MAX_BLOCK or len(r) > MAX_BLOCK:
            raise EditError("bloc trop long")
        edits.append(Edit(path, s, r))
        i = m + 1
    if not edits:
        raise EditError("aucune modification trouvée")
    if len(edits) > MAX_EDITS:
        raise EditError(f"{MAX_EDITS} modifications au plus")
    return edits


def to_block(path: str, search: str, replace: str) -> str:
    return f"{path}\n{SEARCH}\n{search}\n{SEP}\n{replace}\n{REPLACE}"


def forbidden_patterns(root: Path) -> list[str]:
    f = Path(root) / "selfcode" / "forbidden.txt"
    if not f.exists():
        return []
    return [x.strip() for x in f.read_text(encoding="utf-8").splitlines() if x.strip() and not x.startswith("#")]


def is_forbidden(path: str, patterns: list[str]) -> bool:
    return any(path == r or (r.endswith("/") and path.startswith(r)) or fnmatch.fnmatch(path, r) for r in patterns)


def _find(lines: list[str], block: list[str]) -> list[int]:
    n = len(block)
    exact = [i for i in range(len(lines) - n + 1) if lines[i:i + n] == block]
    if exact:
        return exact
    soft = [x.rstrip() for x in block]  # tolère les espaces en fin de ligne
    return [i for i in range(len(lines) - n + 1) if [y.rstrip() for y in lines[i:i + n]] == soft]


def resolve_paths(edits: list[Edit], known: list[str]) -> list[Edit]:
    """Corrige un nom de fichier mal écrit quand un seul fichier du projet correspond (nom seul, avec ou sans dossier
    ajouté, ou sans « .py »). Sinon l'ordre reste tel quel : il sera refusé comme avant."""
    out = []
    for e in edits:
        p = e.path
        if p not in known:
            base = p.replace("\\", "/").split("/")[-1]
            hits = [k for k in known if k == base or k.split("/")[-1] == base or k.split("/")[-1] == base + ".py"]
            if len(hits) == 1:
                p = hits[0]
        out.append(Edit(p, e.search, e.replace))
    return out


def apply(root, edits: list[Edit], forbidden: list[str] | None = None, allow_new: tuple = NEW_FILE_PREFIXES,
          write: bool = True) -> Applied:
    root = Path(root).resolve()
    forbidden = forbidden_patterns(root) if forbidden is None else forbidden
    texts: dict[str, str] = {}
    old: dict[str, str] = {}
    for e in edits:
        p = e.path
        if not p or p.startswith(("/", "~")) or ".." in Path(p).parts or "\\" in p or len(p) > 200:
            raise EditError(f"chemin refusé : {p!r}")
        if is_forbidden(p, forbidden):
            raise EditError(f"fichier protégé : {p}")
        target = (root / p).resolve()
        if root not in target.parents:
            raise EditError(f"chemin hors du dépôt : {p}")
        if p not in texts:
            if target.is_file():
                old[p] = texts[p] = target.read_text(encoding="utf-8")
            elif e.search == "" and p.startswith(allow_new):
                old[p], texts[p] = "", ""
            else:
                raise EditError(f"fichier introuvable : {p}")
        if e.search == "":
            if old[p] != "":
                raise EditError(f"SEARCH vide sur un fichier existant : {p}")
            texts[p] = e.replace + ("\n" if e.replace and not e.replace.endswith("\n") else "")
            continue
        lines = texts[p].split("\n")
        block = e.search.split("\n")
        hits = _find(lines, block)
        if not hits:
            raise EditError(f"SEARCH introuvable dans {p} : {block[0][:60]!r}")
        if len(hits) > 1:
            raise EditError(f"SEARCH ambigu dans {p} ({len(hits)} endroits) : {block[0][:60]!r}")
        h = hits[0]
        texts[p] = "\n".join(lines[:h] + e.replace.split("\n") + lines[h + len(block):])
    parts = []
    for p, new in texts.items():
        if new != old[p]:
            parts.append("".join(difflib.unified_diff(old[p].splitlines(True), new.splitlines(True), f"a/{p}", f"b/{p}")))
    diff = "".join(parts)
    changed = {p: t for p, t in texts.items() if t != old[p]}
    if write:
        for p, t in changed.items():
            f = root / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(t, encoding="utf-8")
    return Applied(changed, diff)
