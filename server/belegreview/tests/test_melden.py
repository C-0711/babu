"""Wann babu sich von selbst meldet — und wann es besser still bleibt.

Der wichtigste Test ist der, dass babu NICHT meldet: wer dreimal umsonst
aufs Telefon schaut, schaltet beim vierten Mal ab und verpasst dann die
Meldung, auf die es ankam.
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import melden  # noqa: E402

HEUTE = dt.date(2026, 9, 3)


def frist(faellig="2026-09-10", art="ustva", name="Umsatzsteuer August 2026"):
    return {"art": art, "name": name, "faellig": faellig}


def vertrag(datum="2026-10-03", partner="Hausverwaltung Sonnenberg",
            sicher=True, vorbei=False):
    return {"partner": partner, "art_name": "Mietvertrag",
            "kuendigen_bis": {"datum": datum, "sicher": sicher, "vorbei": vorbei}}


def rechnung(nummer="2026-0001", datum="2026-08-20", bezahlt=None):
    return {"nummer": nummer, "datum": datum, "bezahlt_am": bezahlt,
            "brutto": 535.5, "empfaenger": {"name": "Jana Allgaier"}}


def beleg(monat="2026-08", status="geprüft"):
    return {"monat": monat, "status": status}


# ————— Fristen —————

def test_sieben_tage_vorher_wird_gemeldet():
    m = melden.fristen_meldungen([frist("2026-09-10")], HEUTE)
    assert len(m) == 1
    assert "in 7 Tagen" in m[0]["text"]
    assert m[0]["dringend"] is False


def test_einen_tag_vorher_ist_dringend():
    m = melden.fristen_meldungen([frist("2026-09-04")], HEUTE)
    assert m[0]["dringend"] is True
    assert "morgen" in m[0]["text"]


def test_dazwischen_bleibt_babu_still():
    """Nicht jeden Tag erinnern — zweimal reicht."""
    for tage in (2, 3, 4, 5, 6, 9, 20):
        faellig = (HEUTE + dt.timedelta(days=tage)).isoformat()
        assert melden.fristen_meldungen([frist(faellig)], HEUTE) == [], \
            f"{tage} Tage vorher sollte still bleiben"


def test_vergangene_fristen_schweigen():
    assert melden.fristen_meldungen([frist("2026-08-10")], HEUTE) == []


def test_kaputtes_datum_stuerzt_nicht_ab():
    assert melden.fristen_meldungen([frist("kaputt"), frist(None)], HEUTE) == []


# ————— Verträge —————

def test_kuendigungsfrist_bekommt_mehr_anlauf():
    """30 Tage, weil dahinter eine Entscheidung steckt."""
    m = melden.vertrag_meldungen([vertrag("2026-10-03")], HEUTE)
    assert len(m) == 1
    assert "Sonnenberg" in m[0]["titel"]
    assert "läuft der Vertrag weiter" in m[0]["text"]


def test_sieben_tage_vor_der_kuendigung_ist_dringend():
    m = melden.vertrag_meldungen([vertrag("2026-09-10")], HEUTE)
    assert m[0]["dringend"] is True


def test_unsichere_frist_wird_nicht_gemeldet():
    """babu hat die Frist nicht sicher gelesen — dann warnt es auch nicht
    mit einem Datum, das es sich zusammengereimt hat."""
    assert melden.vertrag_meldungen([vertrag("2026-10-03", sicher=False)], HEUTE) == []


def test_abgelaufene_frist_wird_nicht_mehr_gemeldet():
    assert melden.vertrag_meldungen([vertrag("2026-10-03", vorbei=True)], HEUTE) == []


# ————— Rechnungen —————

def test_nach_zwei_wochen_einmal_erinnern():
    m = melden.rechnung_meldungen([rechnung(datum="2026-08-20")], HEUTE)
    assert len(m) == 1
    assert "Jana Allgaier" in m[0]["titel"]
    assert "535,50" in m[0]["text"]


def test_bezahlte_rechnungen_schweigen():
    assert melden.rechnung_meldungen(
        [rechnung(datum="2026-08-20", bezahlt="2026-08-25")], HEUTE) == []


def test_nicht_jeden_tag_noergeln():
    """Nur am 14. Tag — danach ist es ihre Entscheidung."""
    for tage in (13, 15, 30, 60):
        datum = (HEUTE - dt.timedelta(days=tage)).isoformat()
        assert melden.rechnung_meldungen([rechnung(datum=datum)], HEUTE) == []


# ————— Monatsabschluss —————

def test_am_dritten_kommt_der_vormonat():
    m = melden.abschluss_meldung([beleg()], HEUTE)
    assert len(m) == 1
    assert "August" in m[0]["titel"]
    assert "gerechnet" in m[0]["text"]


def test_fehlende_belege_werden_benannt():
    m = melden.abschluss_meldung(
        [beleg(status="nachfrage"), beleg(status="erfasst"), beleg()], HEUTE)
    assert "2 Belege" in m[0]["text"]


def test_an_anderen_tagen_kein_abschluss():
    assert melden.abschluss_meldung([beleg()], dt.date(2026, 9, 4)) == []


# ————— Alles zusammen —————

def test_hoechstens_drei_meldungen():
    welt = {"fristen": [frist("2026-09-10", "ustva", "Umsatzsteuer"),
                        frist("2026-09-04", "lohn", "Lohnsteuer")],
            "vertraege": [vertrag("2026-10-03"), vertrag("2026-09-10", "Allianz")],
            "rechnungen": [rechnung(datum="2026-08-20")],
            "belege": [beleg()]}
    m = melden.meldungen(welt, HEUTE)
    assert len(m) == 3, "mehr als drei schaut sich niemand an"


def test_dringendes_steht_oben():
    welt = {"fristen": [frist("2026-09-04", "lohn", "Lohnsteuer")],
            "rechnungen": [rechnung(datum="2026-08-20")],
            "vertraege": [], "belege": []}
    m = melden.meldungen(welt, HEUTE)
    assert m[0]["art"] == "frist" and m[0]["dringend"] is True


def test_ruhiger_tag_bleibt_ruhig():
    """Der häufigste Fall: es steht nichts an, also sagt babu nichts."""
    welt = {"fristen": [frist("2026-11-10")], "vertraege": [],
            "rechnungen": [rechnung(datum="2026-09-01")], "belege": [beleg()]}
    assert melden.meldungen(welt, dt.date(2026, 9, 4)) == []


def test_jede_meldung_hat_einen_eindeutigen_schluessel():
    """Damit dieselbe Meldung nicht zweimal aufs Telefon kommt."""
    welt = {"fristen": [frist("2026-09-10")], "vertraege": [vertrag("2026-10-03")],
            "rechnungen": [rechnung(datum="2026-08-20")], "belege": [beleg()]}
    m = melden.meldungen(welt, HEUTE)
    schluessel = [x["schluessel"] for x in m]
    assert len(set(schluessel)) == len(schluessel)
    assert all(":" in s for s in schluessel)


# ————— Die Route —————

def test_die_app_kann_die_meldungen_abholen(tmp_path, monkeypatch):
    import subprocess
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

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import babu_web
    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={}, rechnungen={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200

    r = client.get("/api/meldungen")
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d["meldungen"], list)
    assert len(d["meldungen"]) <= melden.HOECHSTENS
    for m in d["meldungen"]:
        assert m["titel"] and m["text"] and m["schluessel"]


def test_ohne_anmeldung_keine_meldungen():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import babu_web
    from fastapi.testclient import TestClient
    fremd = TestClient(babu_web.app, base_url="https://testserver")
    assert fremd.get("/api/meldungen").status_code == 401
