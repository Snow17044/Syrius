"""Projets d'exercice supplémentaires (petits modules + tests) pour varier les exemples et le banc d'essai."""

MORE = {
    "validation": {
        "validate.py": '''def is_email(s):
    if s.count("@") != 1:
        return False
    local, domain = s.split("@")
    return bool(local) and "." in domain and not domain.startswith(".") and not domain.endswith(".")


def strong_password(p):
    if len(p) < 8:
        return False
    return any(c.isdigit() for c in p) and any(c.isupper() for c in p) and any(c.islower() for c in p)


def clamp(x, lo, hi):
    if lo > hi:
        raise ValueError("bornes inversées")
    return max(lo, min(hi, x))
''',
        "test_validate.py": '''import pytest
from validate import is_email, strong_password, clamp


def test_email():
    assert is_email("a@b.fr")
    assert not is_email("a@@b.fr")
    assert not is_email("@b.fr")
    assert not is_email("a@b")
    assert not is_email("a@.fr")


def test_password():
    assert strong_password("Abcdefg1")
    assert not strong_password("abcdefg1")
    assert not strong_password("Abc1")
    assert not strong_password("ABCDEFG1")


def test_clamp():
    assert clamp(5, 0, 3) == 3
    assert clamp(-1, 0, 3) == 0
    assert clamp(2, 0, 3) == 2
    with pytest.raises(ValueError):
        clamp(1, 3, 0)
''',
    },
    "pile": {
        "stack.py": '''class Stack:
    def __init__(self):
        self.items = []

    def push(self, x):
        self.items.append(x)

    def pop(self):
        if not self.items:
            raise IndexError("pile vide")
        return self.items.pop()

    def peek(self):
        if not self.items:
            return None
        return self.items[-1]

    def size(self):
        return len(self.items)


def balanced(s):
    pairs = {")": "(", "]": "[", "}": "{"}
    st = Stack()
    for ch in s:
        if ch in "([{":
            st.push(ch)
        elif ch in pairs:
            if st.size() == 0 or st.pop() != pairs[ch]:
                return False
    return st.size() == 0
''',
        "test_stack.py": '''import pytest
from stack import Stack, balanced


def test_stack():
    s = Stack()
    s.push(1)
    s.push(2)
    assert s.peek() == 2
    assert s.pop() == 2
    assert s.size() == 1
    s.pop()
    assert s.peek() is None
    with pytest.raises(IndexError):
        s.pop()


def test_balanced():
    assert balanced("([]{})")
    assert not balanced("(]")
    assert not balanced("((")
    assert not balanced(")(")
    assert balanced("")
''',
    },
    "notes": {
        "grades.py": '''def average(notes):
    if not notes:
        return 0.0
    return sum(notes) / len(notes)


def mention(avg):
    if avg >= 16:
        return "très bien"
    if avg >= 14:
        return "bien"
    if avg >= 12:
        return "assez bien"
    if avg >= 10:
        return "passable"
    return "insuffisant"


def best(students):
    if not students:
        return None
    return max(students, key=lambda s: average(s[1]))[0]


def ranking(students):
    return [n for n, _ in sorted(students, key=lambda s: (-average(s[1]), s[0]))]
''',
        "test_grades.py": '''from grades import average, mention, best, ranking


def test_average():
    assert average([10, 12]) == 11
    assert average([]) == 0.0


def test_mention():
    assert mention(16) == "très bien"
    assert mention(14.5) == "bien"
    assert mention(12) == "assez bien"
    assert mention(10) == "passable"
    assert mention(9.9) == "insuffisant"


def test_best_and_ranking():
    s = [("Zoé", [15, 15]), ("Ali", [10, 12]), ("Bob", [15, 15])]
    assert best(s) == "Zoé"
    assert best([]) is None
    assert ranking(s) == ["Bob", "Zoé", "Ali"]
''',
    },
    "unites": {
        "units.py": '''def c_to_f(c):
    return c * 9 / 5 + 32


def f_to_c(f):
    return (f - 32) * 5 / 9


def km_to_miles(km):
    return km * 0.621371


def format_duration(seconds):
    if seconds < 0:
        raise ValueError("durée négative")
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"
''',
        "test_units.py": '''import pytest
from units import c_to_f, f_to_c, km_to_miles, format_duration


def test_temp():
    assert c_to_f(100) == 212
    assert f_to_c(32) == 0
    assert round(f_to_c(c_to_f(37)), 6) == 37


def test_km():
    assert round(km_to_miles(10), 2) == 6.21


def test_duration():
    assert format_duration(45) == "45 s"
    assert format_duration(125) == "2 min 05 s"
    assert format_duration(3725) == "1 h 02 min"
    with pytest.raises(ValueError):
        format_duration(-1)
''',
    },
}
