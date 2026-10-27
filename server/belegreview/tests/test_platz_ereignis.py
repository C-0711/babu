"""Paywall messen (27.10.2026): `POST /api/platz/ereignis` und der Trichter.

Die Kaufseite meldet, woher sie kam (Quelle) und was danach geschah
(Aktion). Gezählt wird je Betrieb, ausgewertet je Monat — und nur der
Betreiber sieht den Trichter in `/api/kpi`.
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import babu_web  # noqa: E402
import kern_platz  # noqa: E402

from test_geraet_und_apple import (  # noqa: E402,F401
    _anlegen, _client, _mit_schluessel, _platz_setzen, welt)

MONAT = dt.date.today().strftime("%Y-%m")


def test_app_betrieb_meldet_und_zaehlt(welt):
    konto = _anlegen(_client(), name="Salon Test")
    c = _mit_schluessel(konto)
    assert c.post("/api/platz/ereignis",
                  json={"quelle": "angebot", "aktion": "gesehen"}).status_code == 204
    assert c.post("/api/platz/ereignis",
                  json={"quelle": "angebot", "aktion": "gekauft", "stufe": "mittel"}).status_code == 204
    t = kern_platz.trichter(MONAT)
    assert t["angebot"]["gesehen"] == 1
    assert t["angebot"]["gekauft"] == 1
    assert t["angebot"]["weiter"] == 0
    assert set(t["angebot"]) == set(kern_platz.AKTIONEN)


def test_unbekannte_werte_400(welt):
    c = _mit_schluessel(_anlegen(_client()))
    assert c.post("/api/platz/ereignis",
                  json={"quelle": "mond", "aktion": "gesehen"}).status_code == 400
    assert c.post("/api/platz/ereignis",
                  json={"quelle": "menue", "aktion": "geflogen"}).status_code == 400
    assert c.post("/api/platz/ereignis", json={"quelle": "menue"}).status_code == 400
    assert kern_platz.trichter(MONAT) == {}


def test_ohne_schluessel_401(welt):
    assert _client().post("/api/platz/ereignis",
                          json={"quelle": "menue", "aktion": "gesehen"}).status_code == 401


def test_portal_konto_409_und_nichts_gespeichert(welt):
    """Review Focus 3: ein Betrieb ohne Platz-Modell (nicht aus der App)
    bekommt 409 mit Grund, nie 500 — und es wird nichts gezählt."""
    konto = _anlegen(_client())
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET herkunft=NULL WHERE id=?", (konto["mandant"],))
    r = _mit_schluessel(konto).post("/api/platz/ereignis",
                                    json={"quelle": "menue", "aktion": "gesehen"})
    assert r.status_code == 409, r.text
    assert r.json()["fehler"] == "kein Platz-Modell"
    assert kern_platz.trichter(MONAT) == {}


def test_trichter_zaehlt_nur_den_monat(welt):
    konto = _anlegen(_client())
    c = _mit_schluessel(konto)
    assert c.post("/api/platz/ereignis",
                  json={"quelle": "streifen", "aktion": "abgebrochen"}).status_code == 204
    assert kern_platz.trichter("1999-01") == {}
    assert kern_platz.trichter(MONAT)["streifen"]["abgebrochen"] == 1


def test_kpi_zeigt_trichter_nur_admin(welt, monkeypatch):
    konto = _anlegen(_client())
    c = _mit_schluessel(konto)
    assert c.post("/api/platz/ereignis",
                  json={"quelle": "voll", "aktion": "wiederhergestellt"}).status_code == 204
    monkeypatch.setattr(babu_web, "_box_wache", lambda request: ("nina@salon.de", None))
    monkeypatch.setattr(babu_web, "kennzahlen_monat", lambda monat: {"monat": monat})
    monkeypatch.setattr(babu_web, "rolle", lambda un: "admin")
    admin_antwort = _client().get(f"/api/kpi/{MONAT}").json()
    monkeypatch.setattr(babu_web, "rolle", lambda un: "salon")
    salon_antwort = _client().get(f"/api/kpi/{MONAT}").json()
    assert "platz_trichter" in admin_antwort
    assert admin_antwort["platz_trichter"]["voll"]["wiederhergestellt"] == 1
    assert "platz_trichter" not in salon_antwort


def test_voller_platz_meldet_trotzdem(welt):
    """Review 28.10.2026: Die Nur-Lesen-Sperre (zehn freie Belege verbraucht)
    darf die Messung nicht blockieren — sonst bleibt die Quelle `voll`, für
    die das Ganze gebaut ist, systematisch leer."""
    konto = _anlegen(_client())
    c = _mit_schluessel(konto)
    _platz_setzen(konto["mandant"], belege=10)
    assert c.post("/api/kassenbuch", json={"tag": "2026-10-10", "zeilen": []}).status_code == 403
    r = c.post("/api/platz/ereignis", json={"quelle": "voll", "aktion": "gesehen"})
    assert r.status_code == 204, r.text
    assert kern_platz.trichter(MONAT)["voll"]["gesehen"] == 1
