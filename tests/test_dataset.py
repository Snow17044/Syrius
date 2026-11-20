"""Exemples d'entraînement de Nova : actions valides, points faibles du contrôle qualité couverts, questions de contrôle jamais apprises."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "training"))
import make_dataset  # noqa: E402
from eval_set import CASES  # noqa: E402

from server import autogen  # noqa: E402

DATA = make_dataset.build()


def pairs():
    for x in DATA:
        yield x["messages"][-2]["content"], x["messages"][-1]["content"]


def test_toutes_les_actions_passent_les_controles_du_serveur():
    for q, a in pairs():
        if "<tool_call>" in a:
            fixed, why = autogen.review(q, a)
            assert fixed is not None, (q, why)


def test_les_questions_de_controle_ne_servent_jamais_a_l_entrainement():
    held_out = {q.strip().lower() for q, _, _ in CASES}
    assert not [q for q, _ in pairs() if q.strip().lower() in held_out]


def test_reveils_toujours_avec_heure_et_minute():
    alarms = [a for _, a in pairs() if '"phone_alarm"' in a]
    assert len(alarms) >= 35
    for a in alarms:
        args = json.loads(re.search(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", a, re.S).group(1))["arguments"]
        assert set(args) == {"hour", "minute"}, args  # jamais « when », jamais une heure sans minute
    assert any("alarme" in q.lower() for q, a in pairs() if '"phone_alarm"' in a)


def test_penser_a_est_un_rappel_pas_un_souvenir():
    for q, a in pairs():
        if q.lower().startswith(("fais-moi penser", "pense à me dire", "n'oublie pas de me rappeler")):
            assert '"phone_reminder"' in a and '"remember"' not in a, q


def test_questions_simples_sans_action_et_nu_refuse():
    for q, a in pairs():
        if q in ("Pourquoi le ciel est bleu ?", "Une idée de dessert facile ?"):
            assert "<tool_call>" not in a
        if "nu" in q.lower().split() or "sans vêtements" in q.lower():
            assert "<tool_call>" not in a, q


def test_ouvrir_une_application():
    apps = [a for q, a in pairs() if q.lower().startswith(("lance l'application", "démarre", "va sur"))]
    assert len(apps) >= 5 and all('"phone_open_app"' in a for a in apps)
