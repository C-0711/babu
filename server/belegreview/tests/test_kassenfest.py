"""Das Kassenbuch nach GoBD — Ninas Punkte 6-6 und 6-7.

Bis zum 28.08.2026 überschrieb ein zweiter Eintrag für denselben Tag den
ersten wortlos. Hier steht, was stattdessen gilt: ohne Begründung wird
nicht geändert, jede Änderung wird protokolliert, und nach der
Voranmeldung ist der Monat zu.
"""
import json
import subprocess
import sys
from pathlib import Path

import kassenfest as kf
import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

from test_mehrseiten_buendel import _im_stand, welt  # noqa: F401,E402


# ————— Die Regeln, ohne Server —————

def test_ein_neuer_tag_braucht_keine_begruendung():
    ok, warum = kf.darf_schreiben(None, None, festgeschrieben=False)
    assert ok and warum is None


def test_ein_vorhandener_tag_braucht_eine_begruendung():
    ok, warum = kf.darf_schreiben({"einnahmenBar": 100.0}, None,
                                  festgeschrieben=False)
    assert not ok
    assert "schreib kurz dazu" in warum.lower()
    # Und ein „x" ist keine.
    ok, warum = kf.darf_schreiben({"einnahmenBar": 100.0}, "x",
                                  festgeschrieben=False)
    assert not ok
    ok, _ = kf.darf_schreiben({"einnahmenBar": 100.0}, "Zahlendreher",
                              festgeschrieben=False)
    assert ok


def test_nach_der_voranmeldung_geht_gar_nichts_mehr():
    """Auch nicht mit Begründung — die Zahlen liegen beim Finanzamt."""
    ok, warum = kf.darf_schreiben({"einnahmenBar": 100.0}, "guter Grund",
                                  festgeschrieben=True)
    assert not ok
    assert "abgeschlossen" in warum.lower()
    assert "laufenden Monat" in warum
    # Und ein neuer Tag im zugemachten Monat auch nicht.
    assert kf.darf_schreiben(None, None, festgeschrieben=True)[0] is False


def test_das_protokoll_haelt_den_alten_wert_fest():
    p = kf.protokoll_fortschreiben(
        None, {"einnahmenBar": 100.0, "ecZahlungen": 50.0},
        {"einnahmenBar": 120.0, "ecZahlungen": 50.0},
        "nina@0711.io", "Zahlendreher", "2026-08-28T10:00:00+0200")
    assert len(p) == 1
    assert p[0]["wer"] == "nina@0711.io"
    assert p[0]["grund"] == "Zahlendreher"
    assert p[0]["felder"] == {"einnahmenBar": {"vorher": 100.0, "nachher": 120.0}}
    # Was sich nicht geändert hat, steht nicht drin.
    assert "ecZahlungen" not in p[0]["felder"]


def test_speichern_ohne_aenderung_erzeugt_keinen_eintrag():
    gleich = {"einnahmenBar": 100.0}
    assert kf.protokoll_fortschreiben([], gleich, dict(gleich), "n", "egal",
                                      "2026-08-28T10:00:00+0200") == []


def test_technische_felder_stehen_nicht_im_protokoll():
    p = kf.protokoll_fortschreiben(
        None, {"einnahmenBar": 100.0, "von": "a"},
        {"einnahmenBar": 100.0, "von": "b", "geaendert_von": "b"},
        "b", "egal", "2026-08-28T10:00:00+0200")
    assert p == [], "nur wer gespeichert hat, ist keine fachliche Änderung"


def test_der_zustand_ist_in_ninas_worten():
    assert kf.zustand(None, [], False)["text"] == "Noch nichts eingetragen."
    assert kf.zustand({"x": 1}, [], False)["text"] == "Eingetragen."
    assert kf.zustand({"x": 1}, [{}], False)["text"] == "Einmal geändert"
    assert kf.zustand({"x": 1}, [{}, {}], False)["text"] == "2-mal geändert"
    zu = kf.zustand({"x": 1}, [], True)
    assert zu["abgeschlossen"] and "Finanzamt" in zu["text"]
    # Kein Paragraf, kein Fachwort.
    for z in (kf.zustand(None, [], False), zu):
        assert "§" not in z["text"] and "GoBD" not in z["text"]


# ————— Die ganze Strecke über den Server —————

@pytest.fixture()
def kasse(welt, monkeypatch):
    bw, bare = welt
    monkeypatch.setattr(bw, "_mitarbeit_wache", lambda un, recht, tun: None)
    from fastapi.testclient import TestClient
    return bw, bare, TestClient(bw.app, base_url="https://testserver")


def _tag(c, datum="2026-08-27", bar=500.0, grund=None):
    koerper = {"datum": datum, "einnahmenBar": bar, "ecZahlungen": 200.0}
    if grund:
        koerper["grund"] = grund
    return c.post("/api/kassenbuch", json=koerper)


def test_erster_eintrag_geht_ohne_weiteres(kasse):
    _, bare, c = kasse
    r = _tag(c)
    assert r.status_code == 200, r.text
    assert r.json()["zustand"]["text"] == "Eingetragen."
    assert "kassenbuch/2026-08/2026-08-27.json" in _im_stand(bare)


def test_zweiter_eintrag_ohne_grund_wird_abgelehnt(kasse):
    _, bare, c = kasse
    assert _tag(c).status_code == 200
    r = _tag(c, bar=999.0)
    assert r.status_code == 400
    assert "Schreib kurz dazu" in r.json()["fehler"]
    # Und der alte Wert steht unverändert.
    blatt = json.loads(subprocess.run(
        ["git", "--git-dir", str(bare), "show",
         "HEAD:kassenbuch/2026-08/2026-08-27.json"],
        capture_output=True).stdout)
    assert blatt["einnahmenBar"] == 500.0


def test_aenderung_mit_grund_wird_protokolliert(kasse):
    _, bare, c = kasse
    assert _tag(c).status_code == 200
    r = _tag(c, bar=530.0, grund="Zahlendreher beim Abtippen")
    assert r.status_code == 200, r.text
    assert r.json()["zustand"]["aenderungen"] == 1

    p = json.loads(subprocess.run(
        ["git", "--git-dir", str(bare), "show",
         "HEAD:kassenbuch/2026-08/2026-08-27.aenderungen.json"],
        capture_output=True).stdout)
    assert len(p) == 1
    assert p[0]["grund"] == "Zahlendreher beim Abtippen"
    assert p[0]["felder"]["einnahmenBar"] == {"vorher": 500.0, "nachher": 530.0}
    # Der neue Stand trägt, wer und warum.
    blatt = json.loads(subprocess.run(
        ["git", "--git-dir", str(bare), "show",
         "HEAD:kassenbuch/2026-08/2026-08-27.json"],
        capture_output=True).stdout)
    assert blatt["einnahmenBar"] == 530.0
    assert blatt["grund"] == "Zahlendreher beim Abtippen"
    assert blatt["geaendert_von"] == "nina@0711.io"


def test_nach_der_voranmeldung_ist_der_monat_zu(kasse, monkeypatch):
    bw, _, c = kasse
    assert _tag(c).status_code == 200
    # Die Voranmeldung des Monats liegt jetzt in der Box.
    echt = bw.git_show
    monkeypatch.setattr(bw, "git_show", lambda p: (
        b"%PDF" if p == "ustva/2026-08-ustva.pdf" else echt(p)))
    r = _tag(c, bar=530.0, grund="fällt mir jetzt erst auf")
    assert r.status_code == 409
    assert r.json()["abgeschlossen"] is True
    assert "beim Finanzamt" in r.json()["fehler"]


def test_die_route_zeigt_den_zustand_eines_tages(kasse):
    _, _, c = kasse
    leer = c.get("/api/kassenbuch/2026-08-27").json()
    assert leer["blatt"] is None
    assert leer["zustand"]["eingetragen"] is False

    assert _tag(c).status_code == 200
    assert _tag(c, bar=530.0, grund="Zahlendreher").status_code == 200
    d = c.get("/api/kassenbuch/2026-08-27").json()
    assert d["blatt"]["einnahmenBar"] == 530.0
    assert len(d["aenderungen"]) == 1
    assert d["zustand"]["text"] == "Einmal geändert"


def test_das_protokoll_ist_kein_eigenes_dokument_in_der_ablage(kasse):
    """Sonst stünde neben jedem Kassentag eine zweite Zeile im Ordner."""
    _, _, c = kasse
    assert _tag(c).status_code == 200
    assert _tag(c, bar=530.0, grund="Zahlendreher").status_code == 200
    ablage = c.get("/api/ablage").json()
    stuecke = [s for j in ablage["jahre"] for a in j["arten"]
               for s in a["stuecke"]]
    assert not [s for s in stuecke if "aenderungen" in s["pfad"]], stuecke


def test_das_geaenderte_blatt_zaehlt_einmal_in_den_zahlen(kasse):
    """Das Protokoll darf die Auswertung nicht verdoppeln."""
    bw, _, c = kasse
    assert _tag(c).status_code == 200
    assert _tag(c, bar=530.0, grund="Zahlendreher").status_code == 200
    blaetter = bw.index_aktuell()["kassenblaetter"]
    assert list(blaetter) == ["2026-08-27"]
    assert blaetter["2026-08-27"]["einnahmenBar"] == 530.0
