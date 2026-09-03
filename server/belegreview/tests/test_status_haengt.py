"""P0-4/2b: „Wird gelesen" darf nicht ewig stehen bleiben.

Befund vom 02.09.2026: fünf Belege vom 27.08. und einer vom 31.08. standen
am 02.09. noch auf „Wird gelesen" — kein Fehlerzustand, kein „Nochmal
versuchen", kein Hinweis. `_status_ableiten` kippt jetzt nach
`BELEG_HAENGT_NACH_MIN` Minuten ohne Review auf „unlesbar", und
`POST /api/beleg/{stamm}/erneut-lesen` stößt den Lesepfad (2a) erneut an.
"""
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import babu_web as bw  # noqa: E402

UN = "nina@0711.io"


def _vor(minuten: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minuten)).isoformat()


# ————— _minuten_seit: zeitzonensicheres ISO-Parsing —————

def test_minuten_seit_ohne_zeitpunkt_ist_unbekannt():
    assert bw._minuten_seit(None) is None
    assert bw._minuten_seit("") is None


def test_minuten_seit_mit_kaputtem_zeitstempel_ist_unbekannt():
    assert bw._minuten_seit("kein-datum") is None


def test_minuten_seit_rechnet_richtig():
    minuten = bw._minuten_seit(_vor(10))
    assert 9.5 < minuten < 10.5


# ————— _status_ableiten: die eigentliche Schwelle —————

def test_ohne_review_und_laengst_ueber_der_schwelle_wird_unlesbar():
    """Der Befund selbst: Belege, die seit Tagen standen."""
    assert bw._status_ableiten(None, False, _vor(25)) == "unlesbar"
    assert bw._status_ableiten(None, False, _vor(60 * 24 * 5)) == "unlesbar"  # 5 Tage


def test_ohne_review_aber_frisch_bleibt_erfasst():
    """Unverändertes Verhalten: eine laufende Lesung ist kein Fehler."""
    assert bw._status_ableiten(None, False, _vor(5)) == "erfasst"


def test_ohne_review_und_ohne_zeitstempel_bleibt_erfasst():
    """Kein `hochgeladen`-Wert (z. B. Altbestand) darf nicht sofort als
    hängend gelten."""
    assert bw._status_ableiten(None, False, None) == "erfasst"


def test_deutlich_unter_der_schwelle_bleibt_erfasst():
    assert bw._status_ableiten(None, False, _vor(bw.BELEG_HAENGT_NACH_MIN - 2)) == "erfasst"


def test_deutlich_ueber_der_schwelle_wird_unlesbar():
    assert bw._status_ableiten(None, False, _vor(bw.BELEG_HAENGT_NACH_MIN + 2)) == "unlesbar"


def test_ein_vorhandenes_review_bleibt_von_der_schwelle_unberuehrt():
    """Sobald ein Review da ist, zählt gar nicht mehr, wie alt der Upload
    ist — die alte Logik entscheidet weiter."""
    review = {"felder": {"offen": [], "bewirtungssignal": False, "summenprobe_ok": None}}
    assert bw._status_ableiten(review, False, _vor(999)) == "geprüft"


# ————— Der Index trägt die Schwelle wirklich mit —————

@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "README.md").write_text("box")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "s"],
                   check=True, capture_output=True)
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

    import boxschreiber
    monkeypatch.setattr(bw, "STORE", bare)
    monkeypatch.setattr(bw, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(bw, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(bw, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    return bw, bare, boxschreiber


def _alten_beleg_ablegen(boxschreiber, monkeypatch, pfad: str, daten: bytes,
                         vor_minuten: float) -> None:
    """Wie ein echter Portal-Upload — nur mit einem Commit-Datum in der
    Vergangenheit, damit `_zeiten_walk`/`git log --format=%cI` einen alten
    Zeitpunkt liefert. `_status_ableiten` liest genau dieses Feld."""
    zeitpunkt = _vor(vor_minuten)
    monkeypatch.setenv("GIT_COMMITTER_DATE", zeitpunkt)
    monkeypatch.setenv("GIT_AUTHOR_DATE", zeitpunkt)
    boxschreiber.schreiben(pfad, daten, f"aufnahme: {Path(pfad).name}", UN)
    monkeypatch.delenv("GIT_COMMITTER_DATE", raising=False)
    monkeypatch.delenv("GIT_AUTHOR_DATE", raising=False)


def test_ein_seit_tagen_haengender_beleg_zeigt_unlesbar_im_index(welt, monkeypatch):
    bw_, bare, boxschreiber = welt
    stamm = "20260827-090000-abcdef-beleg"
    pfad = f"docs/2026-08/{stamm}.jpg"
    _alten_beleg_ablegen(boxschreiber, monkeypatch, pfad,
                        b"\xff\xd8\xff\xe0" + b"x" * 100, 60 * 24 * 5)
    eintrag = bw_.index_aktuell()["belege"][stamm]
    assert eintrag["status"] == "unlesbar"


def test_ein_frisch_hochgeladener_beleg_bleibt_erfasst(welt, monkeypatch):
    bw_, bare, boxschreiber = welt
    stamm = "20260902-090000-abcdef-beleg"
    pfad = f"docs/2026-09/{stamm}.jpg"
    _alten_beleg_ablegen(boxschreiber, monkeypatch, pfad,
                        b"\xff\xd8\xff\xe0" + b"x" * 100, 1)
    eintrag = bw_.index_aktuell()["belege"][stamm]
    assert eintrag["status"] == "erfasst"


# ————— Die Route: „Nochmal versuchen" —————

@pytest.fixture()
def route_welt(monkeypatch):
    monkeypatch.setattr(bw, "_box_wache", lambda request: (UN, None))
    monkeypatch.setattr(bw, "git_show", lambda pfad: b"\xff\xd8\xff\xe0daten")
    gesehen = {}
    monkeypatch.setattr(bw, "_hintergrund_lesen_starten",
                        lambda pfad, daten, endung, un: gesehen.update(
                            pfad=pfad, daten=daten, endung=endung, un=un))
    from fastapi.testclient import TestClient
    c = TestClient(bw.app, base_url="https://testserver")
    return c, gesehen


def _mit_belegen(monkeypatch, belege: dict) -> None:
    monkeypatch.setattr(bw, "index_aktuell", lambda: {"belege": belege})


def test_erneut_lesen_auf_unlesbarem_beleg_stoesst_die_lesung_an(route_welt, monkeypatch):
    c, gesehen = route_welt
    _mit_belegen(monkeypatch, {"stamm-x": {"status": "unlesbar",
                                          "datei": "docs/2026-08/stamm-x.jpg"}})
    r = c.post("/api/beleg/stamm-x/erneut-lesen")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert gesehen == {"pfad": "docs/2026-08/stamm-x.jpg", "daten": b"\xff\xd8\xff\xe0daten",
                       "endung": ".jpg", "un": UN}


def test_erneut_lesen_auf_erfasstem_beleg_geht_auch(route_welt, monkeypatch):
    """Wer während der ersten Lesung schon einmal drückt, soll nicht gegen
    eine Wand laufen."""
    c, gesehen = route_welt
    _mit_belegen(monkeypatch, {"stamm-x": {"status": "erfasst",
                                          "datei": "docs/2026-08/stamm-x.pdf"}})
    r = c.post("/api/beleg/stamm-x/erneut-lesen")
    assert r.status_code == 200, r.text
    assert gesehen["endung"] == ".pdf"


def test_erneut_lesen_auf_geprueftem_beleg_gibt_409(route_welt, monkeypatch):
    c, gesehen = route_welt
    _mit_belegen(monkeypatch, {"stamm-x": {"status": "geprüft",
                                          "datei": "docs/2026-08/stamm-x.jpg"}})
    r = c.post("/api/beleg/stamm-x/erneut-lesen")
    assert r.status_code == 409
    assert gesehen == {}


def test_erneut_lesen_auf_unbekanntem_beleg_gibt_404(route_welt, monkeypatch):
    c, _ = route_welt
    _mit_belegen(monkeypatch, {})
    r = c.post("/api/beleg/nie-gehoert-davon/erneut-lesen")
    assert r.status_code == 404


# ————— Der Platzhalter aus dem Massenimport (Teilscheibe I1) —————
#
# Ein Beleg, den die Buchhaltung nicht durchbekommen hat, bekommt beim
# Massenimport trotzdem ein Review — sonst stünde er für immer auf „wird
# gelesen". Zwei Formen: eine Rückfrage („nachfrage") und ein unlesbares
# Blatt („unlesbar"). Beide dürfen später ersetzt werden, ein echtes
# Review nie.

def test_dokumentklasse_unlesbar_schlaegt_die_offen_logik():
    """Ein Review, das selbst sagt „daraus war nichts zu machen", ist
    unlesbar — auch mit leerer Fragenliste. Ohne diese Regel stünde ein
    unlesbarer Beleg als „geprüft" in der Liste."""
    review, _ = bw._review_unlesbar("docs/2026-09/x.jpg", "nichts drauf", [])
    assert review["dokumentklasse"] == "unlesbar"
    assert bw._status_ableiten(review, False, _vor(1)) == "unlesbar"
    review["felder"]["offen"] = []
    assert bw._status_ableiten(review, False, _vor(1)) == "unlesbar"


def test_eine_rueckfrage_ist_nachfrage_und_traegt_die_frage():
    review, _ = bw._review_aus_rueckfrage(
        "docs/2026-09/x.jpg", [{"frage": "Wofür war das?", "optionen": []}], [])
    assert review["dokumentklasse"] == "beleg"
    assert review["felder"]["offen"] == ["Wofür war das?"]
    assert bw._status_ableiten(review, False, _vor(1)) == "nachfrage"


def test_ein_platzhalter_traegt_keine_zahlen_und_kein_konto():
    """Der Rest des Hauses muss `None` vertragen — Buchungssatz und
    DATEV-Zeilen kommen dann gar nicht erst zustande."""
    import extf
    for review, _ in (bw._review_unlesbar("docs/2026-09/x.jpg", "leer", []),
                      bw._review_aus_rueckfrage("docs/2026-09/x.jpg", [], [])):
        assert review["felder"]["brutto"] is None
        assert review["einschaetzung"]["konto_skr04"] is None
        assert review["felder"]["herkunft"]["quelle"] == "Import durch die Kanzlei"
        assert bw.datev_buchungssatz(review) is None
        assert extf.buchungszeilen(review) == []
        assert bw.beleg_markdown(review)      # darf nicht werfen


def test_die_fragen_werden_gekuerzt_und_gedeckelt():
    lang = "x" * 500
    review, _ = bw._review_aus_rueckfrage(
        "docs/2026-09/x.jpg",
        [{"frage": lang}, "zwei", "drei", "vier", "fünf", "sechs"], [])
    offen = review["felder"]["offen"]
    assert len(offen) == 4
    assert len(offen[0]) == 200


def test_ohne_fragen_steht_wenigstens_ein_satz_da():
    """Eine leere Fragenliste würde den Beleg auf „geprüft" stellen — ohne
    dass jemand ihn angesehen hätte."""
    review, _ = bw._review_aus_rueckfrage("docs/2026-09/x.jpg", [], [])
    assert review["felder"]["offen"]
    assert bw._status_ableiten(review, False, _vor(1)) == "nachfrage"


def test_erneut_lesen_akzeptiert_einen_platzhalter(route_welt, monkeypatch):
    """Eine unbeantwortete Rückfrage aus dem Import steht auf „nachfrage" —
    und darf trotzdem noch einmal gelesen werden, weil nichts verloren
    geht."""
    import json as _json
    c, gesehen = route_welt
    platzhalter, _ = bw._review_aus_rueckfrage("docs/2026-08/stamm-x.jpg",
                                               [{"frage": "Wofür?"}], [])
    monkeypatch.setattr(bw, "git_show", lambda pfad: (
        None if pfad.endswith(".angaben.json")
        else _json.dumps(platzhalter).encode() if pfad.endswith(".json")
        else b"\xff\xd8\xff\xe0daten"))
    _mit_belegen(monkeypatch, {"stamm-x": {"status": "nachfrage",
                                           "datei": "docs/2026-08/stamm-x.jpg"}})
    r = c.post("/api/beleg/stamm-x/erneut-lesen")
    assert r.status_code == 200, r.text
    assert gesehen["pfad"] == "docs/2026-08/stamm-x.jpg"


def test_erneut_lesen_laesst_eine_echte_rueckfrage_in_ruhe(route_welt, monkeypatch):
    """Gegenprobe: ein gebuchtes Review mit offener Frage ist KEIN
    Platzhalter — dort gibt es nichts erneut zu lesen."""
    import json as _json
    c, gesehen = route_welt
    echt = {"buchung": {"status": "gebucht", "buchung": {}},
            "felder": {"offen": ["Wofür war das?"]}}
    monkeypatch.setattr(bw, "git_show", lambda pfad: (
        _json.dumps(echt).encode() if pfad.endswith(".json")
        else b"\xff\xd8\xff\xe0daten"))
    _mit_belegen(monkeypatch, {"stamm-x": {"status": "nachfrage",
                                           "datei": "docs/2026-08/stamm-x.jpg"}})
    assert c.post("/api/beleg/stamm-x/erneut-lesen").status_code == 409
    assert gesehen == {}
