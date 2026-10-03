"""Der tägliche Lauf (werkzeuge/taeglich.py, seit 03.10.2026).

Stripe nachholen, Salons erinnern, „Heute für dich" an Ambassadorinnen,
„Heute für Nina" — jede Mail höchstens einmal am Tag, die Probe sendet und
schreibt nichts.
"""
import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import babu_web  # noqa: E402
import testmonat  # noqa: E402
from test_kern_abo import (_abo, _ev, _melden, _rechnung, _sitzung,  # noqa: E402,F401
                           welt)

_spec = importlib.util.spec_from_file_location(
    "taeglich", HIER.parents[2] / "werkzeuge" / "taeglich.py")
taeglich = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(taeglich)


def _gesendet(welt):
    return [betreff for _, betreff in welt["post"]]


def test_probe_sendet_und_schreibt_nichts(welt):
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET test_bis=? WHERE id=?",
                  ((testmonat.heute() + dt.timedelta(days=6)).isoformat(), welt["mid"]))
    vorher = len(welt["post"])
    assert taeglich.main(["--probe", "--nur", "salons,betreiber"]) == 0
    assert len(welt["post"]) == vorher
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert c.execute("SELECT COUNT(*) FROM tageslauf").fetchone()[0] == 0


def test_testende_in_sieben_tagen_einmal(welt):
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET test_bis=? WHERE id=?",
                  ((testmonat.heute() + dt.timedelta(days=6)).isoformat(), welt["mid"]))
    taeglich.main(["--nur", "salons"])
    taeglich.main(["--nur", "salons"])
    treffer = [p for p in welt["post"] if p[0] == "sonne@salon.de"]
    assert len(treffer) == 1 and "noch 7 Tage" in treffer[0][1]


def test_ohne_abo_weg_keine_salon_mails(welt, monkeypatch):
    monkeypatch.setenv("BABU_ABO", "0")
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET test_bis=? WHERE id=?",
                  (testmonat.heute().isoformat(), welt["mid"]))
    taeglich.main(["--nur", "salons"])
    assert not [p for p in welt["post"] if p[0] == "sonne@salon.de"]


def test_zahlungsfrist_tag_sieben(welt):
    _melden(_ev("checkout.session.completed", _sitzung(welt["meta"], welt["mid"])))
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET abo_status='zahlung_offen', zahlungsfehler_seit=? "
                  "WHERE id=?", ((testmonat.heute() - dt.timedelta(days=7)).isoformat(),
                                 welt["mid"]))
    taeglich.main(["--nur", "salons"])
    assert ("sonne@salon.de", "babu: Die letzte Zahlung ist nicht angekommen") in welt["post"]


def test_bericht_fuer_nina(welt):
    _melden(_ev("checkout.session.completed", _sitzung(welt["meta"], welt["mid"])))
    _melden(_ev("invoice.paid", _rechnung("in_1")))
    teile = taeglich.bericht(testmonat.heute())
    text = "\n".join(teile)
    assert "Neue Abos" in text and "sonne@salon.de" in text
    assert "Provisionen" in text
    taeglich.main(["--nur", "betreiber"])
    taeglich.main(["--nur", "betreiber"])
    an_nina = [p for p in welt["post"] if p[1].startswith("Heute für dich — babu")]
    assert len(an_nina) == 1 and an_nina[0][0] == "nina@0711.io"


def test_bericht_leer_heisst_keine_mail(welt):
    assert taeglich.bericht(testmonat.heute()) == []
    taeglich.main(["--nur", "betreiber"])
    assert not [p for p in welt["post"] if p[1].startswith("Heute für dich — babu")]


def test_ambassadorin_bekommt_heute_fuer_dich(welt, monkeypatch):
    import kern_ambassador as ka
    monkeypatch.setattr(ka, "_begleiter", lambda code, name, roh, aktiv=True: (
        [], [{"person": "Sonja", "grund": "Test läuft noch 5 Tage",
              "knopf": "Nachfragen"}]))
    taeglich.main(["--nur", "ambassador"])
    taeglich.main(["--nur", "ambassador"])
    an_babs = [p for p in welt["post"] if p[0] == "babs@salon.de"]
    assert an_babs == [("babs@salon.de", "Heute für dich: 1 Salon")]


def test_abbestellt_heisst_keine_mail(welt, monkeypatch):
    import kern_ambassador as ka
    monkeypatch.setattr(ka, "_begleiter", lambda code, name, roh, aktiv=True: (
        [], [{"person": "Sonja", "grund": "x", "knopf": "y"}]))
    babs = welt["sonne"].__class__(babu_web.app, base_url="https://testserver")
    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    babs.post("/api/login", json={"email": "babs@salon.de",
                                  "passwort": "ein-langes-passwort-hier"})
    assert babs.post("/api/ambassador/heute-mail", json={"an": False}).json() == {
        "ok": True, "heute_mail": False}
    assert babs.get("/api/ambassador/me").json()["heute_mail"] is False
    taeglich.main(["--nur", "ambassador"])
    assert not [p for p in welt["post"] if p[0] == "babs@salon.de"]


def test_stripe_nachholen(welt):
    ev = _ev("invoice.paid", _rechnung("in_1", basil=True, meta=welt["meta"]))
    welt["stripe"].ereignisse = [ev]
    original = welt["stripe"].__call__

    def mit_events(methode, pfad, daten=None, idempotenz=None):
        if pfad == "/events":
            return {"data": list(welt["stripe"].ereignisse), "has_more": False}
        return original(methode, pfad, daten, idempotenz)
    import stripe_api
    stripe_api._rufen = mit_events  # noqa: SLF001 — welt setzt es danach zurück
    try:
        assert taeglich.main(["--nur", "stripe"]) == 0
        with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
            assert c.execute("SELECT abo_status FROM mandant WHERE id=?",
                             (welt["mid"],)).fetchone()[0] == "aktiv"
            assert c.execute("SELECT COUNT(*) FROM ambassador_buchung").fetchone()[0] == 1
        # Ein zweiter Lauf holt nichts doppelt.
        taeglich.main(["--nur", "stripe"])
        with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
            assert c.execute("SELECT COUNT(*) FROM ambassador_buchung").fetchone()[0] == 1
    finally:
        stripe_api._rufen = welt["stripe"]  # noqa: SLF001


def test_stripe_ohne_einrichtung_uebersprungen(welt, monkeypatch):
    monkeypatch.delenv("BABU_STRIPE_SCHLUESSEL")
    assert taeglich.main(["--nur", "stripe"]) == 0


@pytest.mark.parametrize("schritt", taeglich.SCHRITTE)
def test_jeder_schritt_ist_aufrufbar(schritt):
    assert callable(getattr(taeglich, f"schritt_{schritt}"))
