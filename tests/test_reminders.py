"""Rappels, agenda et briefing : validation des dates, liste et annulation."""
import json
from datetime import datetime, timedelta

import pytest

from server.tools import reminders
from server.tools.device import TZ, DeviceInputError, build_action
from server.tools.registry import ToolExecutor


def future(**kw):
    return (datetime.now(TZ) + timedelta(**kw)).strftime("%Y-%m-%dT%H:%M")


def test_rappel_valide():
    ev, done = build_action("phone_reminder", {"text": "Appeler maman", "when": future(days=1), "repeat": "daily"})
    p = ev["params"]
    assert ev["action"] == "phone_reminder" and not ev["confirm"]
    assert len(p["id"]) == 10 and p["repeat"] == "daily" and p["text"] == "Appeler maman"
    assert abs(p["at"] / 1000 - (datetime.now(TZ) + timedelta(days=1)).timestamp()) < 120
    assert "tous les jours" in done


@pytest.mark.parametrize("when", ["2020-01-01T10:00", "demain", "", None, 5, future(days=400)])
def test_rappel_date_refusee(when):
    with pytest.raises(DeviceInputError):
        build_action("phone_reminder", {"text": "x", "when": when})


def test_repetition_inconnue_devient_une_fois():
    ev, _ = build_action("phone_reminder", {"text": "x", "when": future(hours=2), "repeat": "hourly"})
    assert ev["params"]["repeat"] == "none"


def test_agenda():
    ev, _ = build_action("phone_calendar", {"title": "Dentiste", "start": future(days=3), "duration_min": 30,
                                            "location": "Lyon"})
    p = ev["params"]
    assert p["end"] - p["start"] == 30 * 60 * 1000 and p["location"] == "Lyon"
    with pytest.raises(DeviceInputError):
        build_action("phone_calendar", {"title": "x", "start": future(days=1), "duration_min": 99999})


def test_annulation_identifiant_strict():
    with pytest.raises(DeviceInputError):
        build_action("phone_reminder_cancel", {"id": "../../etc"})


@pytest.mark.anyio
async def test_liste_et_annulation(cfg, make_db):
    db = make_db()
    ex = ToolExecutor(cfg, db)
    result, err, ev = await ex.run("list_reminders", {})
    assert "Aucun" in result
    _, err, ev = await ex.run("phone_reminder", {"text": "Sport", "when": future(hours=3)})
    rid = ev["params"]["id"]
    items = json.loads((await ex.run("list_reminders", {}))[0])
    assert items[0]["id"] == rid and items[0]["texte"] == "Sport"
    result, err, ev = await ex.run("phone_reminder_cancel", {"id": rid})
    assert not err and ev["params"]["id"] == rid
    result, err, ev = await ex.run("phone_reminder_cancel", {"id": rid})
    assert err and ev is None
    assert "Aucun" in (await ex.run("list_reminders", {}))[0]


def test_rappels_passes_oublies(make_db):
    db = make_db()
    reminders.add(db, {"id": "aaaaaa", "text": "vieux", "at": 1000, "repeat": "none", "label": "x"})
    reminders.add(db, {"id": "bbbbbb", "text": "chaque jour", "at": 1000, "repeat": "daily", "label": "x"})
    assert [r["id"] for r in reminders.upcoming(db)] == ["bbbbbb"]


def test_android_rappels_securises():
    java = open("android/app/src/main/java/fr/syrius/app/Reminders.java", encoding="utf-8").read()
    assert 'id.matches("[0-9a-f]{6,20}")' in java and "FLAG_IMMUTABLE" in java
    manifest = open("android/app/src/main/AndroidManifest.xml", encoding="utf-8").read()
    assert '<receiver android:name=".AlarmReceiver" android:exported="false" />' in manifest


def test_hey_syrius_securise():
    java = open("android/app/src/main/java/fr/syrius/app/WakeModel.java", encoding="utf-8").read()
    assert 'SHA256 = "cabf6180e177eb9b3a9a9d43a437bd5e549f3a7d09525e5d69a3fed787be12ad"' in java
    assert "getCanonicalPath().startsWith(base)" in java and "MAX_UNZIPPED" in java  # zip protégé
    svc = open("android/app/src/main/java/fr/syrius/app/WakeService.java", encoding="utf-8").read()
    assert 'url.startsWith("https://")' in svc and '"X-Syrius", "1"' in svc
    manifest = open("android/app/src/main/AndroidManifest.xml", encoding="utf-8").read()
    assert 'android:name=".WakeService" android:exported="false"' in manifest
    main = open("android/app/src/main/java/fr/syrius/app/MainActivity.java", encoding="utf-8").read()
    for fn in ("wakeInfo", "wakeDownload", "wakeEnable", "wakeDelete", "batterySettings"):
        assert "trusted()" in main.split(fn + "(")[1][:300], fn
