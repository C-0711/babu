"""Die Nachlese beim Start — ein Deploy strandet keinen Beleg mehr.

Alles, was gerade gelesen wird, lebt nur im Prozess; ein Neustart mitten in
der Lesung ließ den Beleg bis 14.09.2026 als „unlesbar" stehen, und niemand
las nach. Jetzt läuft nach dem Start GENAU EIN Durchgang (kein Watcher):
Belege ohne jede Lesung, älter als drei Minuten und jünger als zwei Wochen,
gedeckelt, sequenziell, über denselben Weg wie „Nochmal versuchen".
"""
import asyncio
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _eintrag(stamm, status="erfasst", klasse=None, minuten=10):
    t = (datetime.now(timezone.utc) - timedelta(minutes=minuten)).isoformat()
    return {"stamm": stamm, "datei": f"docs/2026-09/{stamm}.jpg", "status": status,
            "dokumentklasse": klasse, "hochgeladen": t}


def test_kandidaten_sind_nur_belege_ohne_jede_lesung():
    import babu_web as bw
    idx = {"belege": {
        "a": _eintrag("a"),                                    # erfasst, kein Review → ja
        "b": _eintrag("b", status="unlesbar", minuten=20),     # unlesbar ohne Review → ja (älter, also zuerst)
        "c": _eintrag("c", status="unlesbar", klasse="unlesbar"),  # Urteil aus dem Import → nein
        "d": _eintrag("d", status="gebucht", klasse="beleg"),  # gelesen → nein
        "e": _eintrag("e", minuten=1),                         # läuft womöglich noch → nein
        "f": _eintrag("f", minuten=15 * 1440),                 # Altfall → nein
    }}
    assert [z["stamm"] for z in bw._nachlese_kandidaten(idx)] == ["b", "a"]  # noqa: SLF001


def test_der_deckel_je_box_gilt(monkeypatch):
    import babu_web as bw
    idx = {"belege": {f"s{i}": _eintrag(f"s{i}", minuten=10 + i) for i in range(30)}}
    assert len(bw._nachlese_kandidaten(idx)) == bw.NACHLESE_JE_BOX  # noqa: SLF001


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "README.md").write_text("box")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "start"],
                   check=True, capture_output=True)
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)
    import babu_web
    import box as bx
    import boxschreiber
    monkeypatch.setattr(babu_web, "_TEST_BX", bx, raising=False)
    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(babu_web, "NACHLESE_VERZOEGERUNG_S", 0.0)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    bx.registry_leeren()
    return babu_web


def test_der_startdurchgang_liest_sequenziell_im_kontext_der_box(welt, monkeypatch):
    bw = welt
    # Zwei Belege ohne Lesung liegen im Index — der Index selbst wird gestellt,
    # damit der Test kein Git braucht; `git_show` liefert Bytes.
    idx = {"belege": {"x": _eintrag("x", minuten=20), "y": _eintrag("y", minuten=10)}}
    monkeypatch.setattr(bw, "index_aktuell", lambda: idx)
    monkeypatch.setattr(bw, "git_show", lambda datei: b"\xff\xd8bild:" + datei.encode())
    gelesen = []
    laeuft = {"jetzt": 0, "max": 0}

    async def fake_lesen(pfad, daten, endung, un):
        laeuft["jetzt"] += 1
        laeuft["max"] = max(laeuft["max"], laeuft["jetzt"])
        await asyncio.sleep(0.01)
        gelesen.append((pfad, endung, un, bw._box().ref))  # noqa: SLF001
        laeuft["jetzt"] -= 1
    monkeypatch.setattr(bw, "_hintergrund_lesen", fake_lesen)

    asyncio.run(bw._beim_start_nachlesen())  # noqa: SLF001
    assert [g[0] for g in gelesen] == ["docs/2026-09/x.jpg", "docs/2026-09/y.jpg"]  # älteste zuerst
    assert all(g[1] == ".jpg" for g in gelesen)
    assert laeuft["max"] == 1                      # nie zwei zugleich
    assert all(g[3] == bw._TEST_BX.default_box().ref for g in gelesen)   # im Kontext der Box
    assert gelesen[0][2] in bw.ERLAUBT             # Default-Box: Konto aus der Allowlist


def test_ohne_kandidaten_passiert_nichts(welt, monkeypatch):
    bw = welt
    monkeypatch.setattr(bw, "index_aktuell", lambda: {"belege": {
        "z": _eintrag("z", status="gebucht", klasse="beleg")}})
    aufrufe = []
    monkeypatch.setattr(bw, "_hintergrund_lesen", lambda *a: aufrufe.append(a))
    asyncio.run(bw._beim_start_nachlesen())  # noqa: SLF001
    assert aufrufe == []


def test_der_gesamtdeckel_greift(welt, monkeypatch):
    bw = welt
    monkeypatch.setattr(bw, "NACHLESE_MAX", 3)
    idx = {"belege": {f"s{i}": _eintrag(f"s{i}", minuten=10 + i) for i in range(10)}}
    monkeypatch.setattr(bw, "index_aktuell", lambda: idx)
    monkeypatch.setattr(bw, "git_show", lambda datei: b"x")
    n = []

    async def fake_lesen(pfad, daten, endung, un):
        n.append(pfad)
    monkeypatch.setattr(bw, "_hintergrund_lesen", fake_lesen)
    asyncio.run(bw._beim_start_nachlesen())  # noqa: SLF001
    assert len(n) == 3
