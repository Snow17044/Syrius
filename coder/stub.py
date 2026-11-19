"""Tâches « implémente » : on vide le corps d'une fonction ; la bonne réponse (le vrai corps) est connue."""
from __future__ import annotations

import ast
import random

STUB = "    raise NotImplementedError"


def functions(source: str) -> list[tuple[str, int, int]]:
    """(nom, ligne de début, ligne de fin) des fonctions de premier niveau et des méthodes, avec au moins 2 lignes de corps."""
    out = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name != "__init__" and node.end_lineno - node.lineno >= 2:
            out.append((node.name, node.lineno, node.end_lineno))
    return sorted(out, key=lambda x: x[1])


def make(source: str, rng: random.Random):
    """(source vidée, nom, SEARCH, REPLACE) pour une fonction tirée au sort, ou None."""
    fs = [f for f in functions(source) if not _nested(source, f)]
    if not fs:
        return None
    name, a, b = rng.choice(fs)
    lines = source.split("\n")
    head_end = a  # la signature tient sur la 1re ligne dans nos exemples
    if not lines[a - 1].rstrip().endswith(":"):
        return None
    indent = len(lines[a - 1]) - len(lines[a - 1].lstrip())
    stub = lines[:head_end] + [" " * indent + STUB.strip()] + lines[b:]
    search = "\n".join(lines[a - 1:head_end] + [" " * indent + STUB.strip()])
    replace = "\n".join(lines[a - 1:b])
    return "\n".join(stub), name, search, replace


def _nested(source: str, f) -> bool:
    return False
