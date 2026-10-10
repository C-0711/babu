"""Das Übergabepaket per Mail ans Steuerbüro (seit 10.10.2026).

„An mein Steuerbüro geben" ohne Portal für das Büro: beim ersten Mal fragt
babu die Adresse, dann geht eine Mail mit Stapel, Belegen und Kassenbuch
als ZIP. Übergeben wird dabei wie bisher (Festschreiben, Nachtrag, 409 bei
nichts Neuem); hier wird geprüft, was in der Mail und im Paket landet.
"""
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

from test_datev_seite import BELEGE, _welt_bauen  # noqa: E402

import uebergabepaket  # noqa: E402

EMAIL = "kanzlei@beispiel.de"


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    bw = _welt_bauen(tmp_path, monkeypatch, BELEGE)
    bw.db_einstellung_setzen("chef@0711.io", "betrieb_name", "Salon Sonne")
    bw.db_einstellung_setzen("chef@0711.io", "email", "sonne@salon.de")
    return bw


@pytest.fixture()
def post(monkeypatch):
    """Was `postfach.senden` bekommt — nichts geht wirklich raus."""
    import postfach
    gesendet = []

    def senden(an, betreff, text, *, stempel, antwort_an=None, anhaenge=None):
        gesendet.append({"an": an, "betreff": betreff, "text": text, "stempel": stempel,
                         "antwort_an": antwort_an, "anhaenge": anhaenge or []})
        return True, "ok"
    monkeypatch.setattr(postfach, "senden", senden)
    return gesendet


@pytest.fixture()
def c(welt):
    return TestClient(welt.app, base_url="https://testserver")


def _zip(daten: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        return {n: z.read(n) for n in z.namelist()}


def test_erster_versand_braucht_die_adresse(c, post):
    r = c.post("/api/datev/senden?von=2026-07&bis=2026-07")
    assert r.status_code == 400 and r.json()["email_noetig"] is True
    assert post == []
    assert c.get("/api/datev/steuerbuero").json() == {"email": ""}
    # Nichts übergeben: der Monat ist noch nicht festgeschrieben.
    assert c.get("/api/datev/uebersicht").json()["je_monat"]["2026-07"]["uebergeben_am"] is None


def test_ungueltige_adresse(c, post):
    r = c.post("/api/datev/senden?von=2026-07&bis=2026-07", json={"email": "kanzlei"})
    assert r.status_code == 400 and "E-Mail" in r.json()["fehler"]
    assert c.post("/api/datev/steuerbuero", json={"email": "x@"}).status_code == 400
    assert post == []


def test_versand_mit_adresse_schickt_das_paket(c, post):
    r = c.post("/api/datev/senden?von=2026-07&bis=2026-07", json={"email": EMAIL})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["gesendet"] and d["an"] == EMAIL and d["teile"] == 1
    assert d["belege"] == 2 and d["buchungen"] >= 2 and d["nachtrag"] == 0
    assert "Paket an kanzlei@beispiel.de" in d["hinweis"]
    # Die Adresse bleibt, die Übersicht kennt sie.
    assert c.get("/api/datev/steuerbuero").json() == {"email": EMAIL}
    assert c.get("/api/datev/uebersicht").json()["steuerbuero_email"] == EMAIL
    # Eine Mail, an das Büro, Antwort an den Betrieb, ein ZIP.
    assert len(post) == 1
    m = post[0]
    assert m["an"] == EMAIL and m["antwort_an"] == "sonne@salon.de"
    assert "Salon Sonne" in m["betreff"] and "2026-07" in m["betreff"]
    assert len(m["anhaenge"]) == 1
    name, daten, mime = m["anhaenge"][0]
    assert name == "babu_Uebergabe_2026-07.zip" and mime == "application/zip"
    inhalt = _zip(daten)
    stapel = [n for n in inhalt if n.startswith("EXTF_") and n.endswith(".csv")]
    assert len(stapel) == 1 and inhalt[stapel[0]].startswith(b'"EXTF"')
    # Dieselbe Datei wie in der Belegbox (festgeschrieben, Kennzeichen 1).
    assert inhalt[stapel[0]].startswith(b'"EXTF";700;21;"Buchungsstapel";12;')
    belege = sorted(n for n in inhalt if n.startswith("belege/"))
    assert belege == ["belege/2026-07/20260714-101500-aaa001-friseurbedarf.jpg",
                      "belege/2026-07/20260722-183000-aaa002-delila.jpg"]
    assert inhalt[belege[0]] == b"\xff\xd8\xff\xe0demo"
    lies = inhalt["LIESMICH.txt"].decode("utf-8")
    assert "Salon Sonne" in lies and "DATEV" in lies and "Addison" in lies and stapel[0] in lies
    manifest = json.loads(inhalt["inhalt.json"])
    assert manifest["belege"] == belege and manifest["stapel"] == stapel[0]
    assert manifest["teil"] == 1 and manifest["teile"] == 1
    # Der Monat gilt als übergeben — derselbe Weg wie /uebergeben.
    assert c.get("/api/datev/uebersicht").json()["je_monat"]["2026-07"]["uebergeben_am"]


def test_zweiter_versand_nutzt_die_gespeicherte_adresse(c, post):
    assert c.post("/api/datev/senden?von=2026-07&bis=2026-07",
                  json={"email": EMAIL}).status_code == 200
    r = c.post("/api/datev/senden?von=2026-08&bis=2026-08")
    assert r.status_code == 200 and r.json()["an"] == EMAIL
    assert [m["an"] for m in post] == [EMAIL, EMAIL]
    assert "2026-08" in post[1]["betreff"]


def test_nichts_neues_kein_zweites_paket(c, post):
    assert c.post("/api/datev/senden?von=2026-07&bis=2026-07",
                  json={"email": EMAIL}).status_code == 200
    r = c.post("/api/datev/senden?von=2026-07&bis=2026-07")
    assert r.status_code == 409 and "Nachtrag" in r.json()["fehler"]
    assert len(post) == 1


def test_grosses_paket_geht_in_teilen(c, post, monkeypatch):
    monkeypatch.setattr(uebergabepaket, "ANHANG_MAX", 1)
    r = c.post("/api/datev/senden?von=2026-07&bis=2026-08", json={"email": EMAIL})
    assert r.status_code == 200
    d = r.json()
    assert d["teile"] == 3 and d["belege"] == 3 and "in 3 Teilen" in d["hinweis"]
    assert len(post) == 3
    namen = [m["anhaenge"][0][0] for m in post]
    assert namen == ["babu_Uebergabe_2026-07_bis_2026-08_Teil1von3.zip",
                     "babu_Uebergabe_2026-07_bis_2026-08_Teil2von3.zip",
                     "babu_Uebergabe_2026-07_bis_2026-08_Teil3von3.zip"]
    assert "Teil 1 von 3" in post[0]["betreff"]
    eins, zwei = _zip(post[0]["anhaenge"][0][1]), _zip(post[1]["anhaenge"][0][1])
    assert any(n.startswith("EXTF_") for n in eins) and not any(n.startswith("EXTF_") for n in zwei)
    assert sum(1 for n in eins if n.startswith("belege/")) == 1
    assert "Teil 2 von 3" in zwei["LIESMICH.txt"].decode("utf-8")


def test_mail_nicht_raus_stapel_trotzdem_abgeschlossen(c, monkeypatch):
    import postfach
    monkeypatch.setattr(postfach, "senden",
                        lambda *a, **k: (False, "kein Versand eingerichtet — liegt in x.eml"))
    r = c.post("/api/datev/senden?von=2026-07&bis=2026-07", json={"email": EMAIL})
    assert r.status_code == 200
    d = r.json()
    assert d["gesendet"] is False and "Postausgang" in d["hinweis"]
    assert c.get("/api/datev/uebersicht").json()["je_monat"]["2026-07"]["uebergeben_am"]


def test_mitarbeiterin_darf_nicht(welt, post, monkeypatch):
    monkeypatch.setattr(welt, "rolle", lambda un: "mitarbeit")
    k = TestClient(welt.app, base_url="https://testserver")
    assert k.post("/api/datev/senden?von=2026-07&bis=2026-07", json={"email": EMAIL}).status_code == 403
    assert k.get("/api/datev/steuerbuero").status_code == 403
    assert post == []


def test_kassenbuch_csv_ist_deutsch_und_vollstaendig():
    text = uebergabepaket.kassenbuch_csv([
        {"datum": "2026-07-02", "bar": 120.5, "ecZahlungen": 80.0, "notiz": "Dienstag"},
        {"datum": "2026-07-01", "bar": 99.0, "ecZahlungen": 0.0, "geschlossen": True},
    ])
    zeilen = text.splitlines()
    assert zeilen[0].split(";")[0] == "datum" and "notiz" in zeilen[0] and "geschlossen" in zeilen[0]
    assert zeilen[1].startswith("2026-07-01;99,00;0,00") and "ja" in zeilen[1]
    assert zeilen[2].startswith("2026-07-02;120,50;80,00") and "Dienstag" in zeilen[2]
