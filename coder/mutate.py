"""Fabrique des bugs réalistes (une ligne modifiée) : la correction exacte est connue, donc l'exemple est sûr."""
from __future__ import annotations

import random
import re

SWAPS = [("<=", "<"), (">=", ">"), ("==", "!="), (" and ", " or "), (" + ", " - "), (" - ", " + "), (" < ", " <= "),
         (" > ", " >= "), ("True", "False"), (" * ", " + "), (" // ", " / "), ("not ", ""), (" in ", " not in ")]
_PLUS_ONE = re.compile(r"\b(\w+) \+ 1\b")


def candidates(source: str) -> list[tuple[int, str]]:
    """(numéro de ligne, ligne buggée) pour chaque mutation possible."""
    out = []
    for n, line in enumerate(source.split("\n")):
        s = line.strip()
        if not s or s.startswith(("#", '"""', "'''", "import ", "from ", "def ", "class ", "@")) or '"' in s and "==" not in s and "return" not in s:
            continue
        for a, b in SWAPS:
            if a in line:
                out.append((n, line.replace(a, b, 1)))
        if _PLUS_ONE.search(line):
            out.append((n, _PLUS_ONE.sub(r"\1", line, 1)))
        if re.search(r"\breturn [\w\[\]\.]+$", line) and "None" not in line:
            out.append((n, re.sub(r"return [\w\[\]\.]+$", "return None", line)))
    return out


def mutate(source: str, rng: random.Random):
    """(source buggée, ligne d'origine, ligne buggée) ou None."""
    cs = candidates(source)
    if not cs:
        return None
    n, bad = rng.choice(cs)
    lines = source.split("\n")
    good = lines[n]
    if bad == good:
        return None
    lines[n] = bad
    return "\n".join(lines), good, bad


def edit_for(buggy: str, good: str, bad: str, context: int = 1):
    """SEARCH/REPLACE qui répare : la ligne buggée plus un peu de contexte pour qu'elle soit unique."""
    lines = buggy.split("\n")
    idx = [i for i, l in enumerate(lines) if l == bad]
    for c in range(context, 6):
        for i in idx:
            lo, hi = max(0, i - c), min(len(lines), i + c + 1)
            block = lines[lo:hi]
            if sum(1 for j in range(len(lines) - len(block) + 1) if lines[j:j + len(block)] == block) == 1:
                fixed = block[:i - lo] + [good] + block[i - lo + 1:]
                while len(block) > 1 and block[-1] == "" and fixed[-1] == "":
                    block, fixed = block[:-1], fixed[:-1]
                while len(block) > 1 and block[0] == "" and fixed[0] == "":
                    block, fixed = block[1:], fixed[1:]
                return "\n".join(block), "\n".join(fixed)
    return None
