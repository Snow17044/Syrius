"""Projets d'exercice (petits modules + tests) et mise en forme des demandes faites à l'IA programmeuse."""
from __future__ import annotations

from . import edits

SYSTEM = ("Tu es Aurora, une IA programmeuse rapide et précise. Tu réponds par UNE phrase d'explication puis par un ou "
          "plusieurs blocs de modification, rien d'autre. Chaque bloc commence par le nom du fichier, écrit EXACTEMENT comme dans "
          "les titres « ### » du projet (le titre « ### stack.py » donne la ligne « stack.py », sans dossier ajouté), puis :\n"
          "<<<<<<< SEARCH\nlignes exactes à remplacer\n=======\nnouvelles lignes\n>>>>>>> REPLACE\n"
          "Le SEARCH doit exister une seule fois dans le fichier.")

SEEDS = {
    "texte": {
        "textutil.py": '''def slug(s):
    out = []
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")


def truncate(s, n):
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def count_words(s):
    return len(s.split())
''',
        "test_textutil.py": '''from textutil import slug, truncate, count_words


def test_slug():
    assert slug("Bonjour le Monde !") == "bonjour-le-monde"
    assert slug("  a  b ") == "a-b"


def test_truncate():
    assert truncate("abc", 5) == "abc"
    assert truncate("abcdefgh", 5) == "abcd…"
    assert truncate("abcde", 5) == "abcde"


def test_count_words():
    assert count_words("un deux  trois") == 3
    assert count_words("") == 0
''',
    },
    "panier": {
        "cart.py": '''def total(items):
    return sum(price * qty for price, qty in items)


def apply_discount(amount, percent):
    if percent < 0 or percent > 100:
        raise ValueError("pourcentage invalide")
    return round(amount * (100 - percent) / 100, 2)


def split_bill(amount, people):
    if people <= 0:
        raise ValueError("personnes invalides")
    base = amount // people
    rest = amount - base * people
    return [base + (1 if i < rest else 0) for i in range(people)]
''',
        "test_cart.py": '''import pytest
from cart import total, apply_discount, split_bill


def test_total():
    assert total([(2, 3), (1, 5)]) == 11
    assert total([]) == 0


def test_discount():
    assert apply_discount(200, 25) == 150
    assert apply_discount(10, 0) == 10
    with pytest.raises(ValueError):
        apply_discount(10, 101)


def test_split():
    assert split_bill(10, 3) == [4, 3, 3]
    assert sum(split_bill(7, 2)) == 7
    with pytest.raises(ValueError):
        split_bill(5, 0)
''',
    },
    "listes": {
        "seqs.py": '''def chunk(xs, n):
    if n <= 0:
        raise ValueError("n doit être positif")
    return [xs[i:i + n] for i in range(0, len(xs), n)]


def unique(xs):
    seen = set()
    out = []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def moving_average(xs, k):
    if k <= 0 or k > len(xs):
        return []
    return [sum(xs[i:i + k]) / k for i in range(len(xs) - k + 1)]


def second_largest(xs):
    vals = sorted(set(xs), reverse=True)
    if len(vals) < 2:
        return None
    return vals[1]
''',
        "test_seqs.py": '''import pytest
from seqs import chunk, unique, moving_average, second_largest


def test_chunk():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    with pytest.raises(ValueError):
        chunk([1], 0)


def test_unique():
    assert unique([3, 1, 3, 2, 1]) == [3, 1, 2]


def test_moving_average():
    assert moving_average([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]
    assert moving_average([1, 2], 3) == []


def test_second_largest():
    assert second_largest([5, 1, 5, 3]) == 3
    assert second_largest([2, 2]) is None
''',
    },
}


from .seeds_more import MORE  # noqa: E402

SEEDS.update(MORE)


def source_files(files: dict) -> list[str]:
    return sorted(p for p in files if p.endswith(".py") and not p.split("/")[-1].startswith("test_"))


def render_files(files: dict, only: list[str] | None = None) -> str:
    return "\n\n".join(f"### {p}\n```python\n{files[p].rstrip()}\n```" for p in (only or sorted(files)))


INSTRUCTIONS = {"bug": "Les tests échouent. Corrige le bug avec une modification minimale.",
                "implement": "Implémente la fonction qui est vide (raise NotImplementedError) pour que les tests passent."}


def instruction(kind: str) -> str:
    return INSTRUCTIONS.get(kind, INSTRUCTIONS["bug"])


def make_prompt(files: dict, instruction: str, failing: str = "") -> str:
    p = f"{instruction}\n\nFichiers du projet :\n\n{render_files(files)}"
    if failing:
        p += f"\n\nSortie des tests :\n```\n{failing.strip()[-900:]}\n```"
    return p


def answer(explain: str, search_replace: list[tuple[str, str, str]]) -> str:
    return explain.strip() + "\n\n" + "\n\n".join(edits.to_block(*e) for e in search_replace)


def messages(prompt: str, reply: str) -> dict:
    return {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt},
                         {"role": "assistant", "content": reply}]}
