"""Warteliste (seit 16.09.2026): Zugang nur auf Einladung.

Wer sich anmelden möchte — Salon oder Kanzlei —, hinterlässt E-Mail und Art
auf der Warteliste. Es entsteht KEIN Konto. Die Verwaltung liest die Liste,
richtet daraus Zugänge mit Startpasswort ein oder lehnt höflich ab.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def klient(tmp_path):
    import babu_web
    babu_web.PORTAL_DB = tmp_path / "portal.db"
    babu_web._REG_ZULETZT.clear()
    return TestClient(babu_web.app, base_url="https://testserver"), babu_web


@pytest.fixture()
def verwaltung(klient):
    """Admin-Konto + Sitzung, wie sie die Verwaltung auf der H200V hat."""
    import importlib
    import postfach
    importlib.reload(postfach)
    postfach.HOST = ""
    client, bw = klient
    bw.nutzer_anlegen("chef@example.org", "Chef", "babu", "admin",
                      passwort="chef-passwort-1")
    r = client.post("/api/login", json={"email": "chef@example.org",
                                        "passwort": "chef-passwort-1"})
    assert r.status_code == 200, r.text
    return client, bw


ANMELDUNG = {"email": "salon@example.org", "art": "salon",
             "name": "Nina", "salon": "SupremeStudio"}


def test_anmeldung_landet_auf_der_warteliste(klient):
    client, bw = klient
    r = client.post("/api/warteliste", json=ANMELDUNG)
    assert r.status_code == 200 and r.json()["ok"] is True
    # KEIN Konto ist entstanden.
    assert bw.nutzer_holen("salon@example.org") is None


def test_anmeldung_hinterlaesst_mail_fuer_nina(klient, monkeypatch, tmp_path):
    """Mit eingetragenem Support-Postfach landet je Anmeldung eine .eml
    im Postausgang — ohne SMTP bleibt sie dort liegen, die Zusage an die
    Adresse bleibt dieselbe."""
    import postfach
    monkeypatch.setattr(postfach, "HOST", "")
    monkeypatch.setattr(postfach, "POSTAUSGANG", tmp_path / "postausgang")
    bw = klient[1]
    monkeypatch.setattr(bw, "SUPPORT_MAIL", "nina@0711.io")
    client = klient[0]
    r = client.post("/api/warteliste", json=ANMELDUNG)
    assert r.status_code == 200
    maildateien = list((tmp_path / "postausgang").glob("*.eml"))
    assert len(maildateien) == 1
    inhalt = maildateien[0].read_text()
    assert "salon@example.org" in inhalt
    assert "SupremeStudio" in inhalt
    assert "To: nina@0711.io" in inhalt


def test_dieselbe_adresse_zaehlt_und_vervielfacht_nicht(klient):
    client, bw = klient
    client.post("/api/warteliste", json=ANMELDUNG)
    # IP-Bremse (30 s) zurücksetzen — sonst kommt der zweite Aufruf als 429
    # durch und der Zähler bleibt bei 1. Im echten Betrieb will niemand
    # dieselbe Adresse zweimal in 30 Sekunden melden.
    bw._REG_ZULETZT.clear()
    client.post("/api/warteliste", json=ANMELDUNG)
    r = client.get("/api/warteliste")
    assert r.status_code in (401, 403)  # ohne Verwaltung nicht lesbar
    with bw._DB_LOCK, bw._db() as c:
        n, anfragen = c.execute(
            "SELECT COUNT(*), MAX(anfragen) FROM warteliste").fetchone()
    assert n == 1 and anfragen == 2


def test_unsinnige_adresse_wird_abgewiesen(klient):
    client, bw = klient
    r = client.post("/api/warteliste", json={"email": "nicht-mail", "art": "salon"})
    assert r.status_code == 400


def test_verwaltung_richtet_zugang_ein(verwaltung):
    client, bw = verwaltung
    client.post("/api/warteliste", json=ANMELDUNG)
    r = client.post("/api/warteliste/einrichten", json={
        "email": "salon@example.org", "art": "salon"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["startpasswort"]
    konto = bw.nutzer_holen("salon@example.org")
    assert konto["rolle"] == "salon" and konto["salon"] == "SupremeStudio"
    # Der Eintrag ist abgeschlossen.
    liste = client.get("/api/warteliste").json()["warteliste"]
    eintrag = [w for w in liste if w["email"] == "salon@example.org"]
    assert eintrag and eintrag[0]["status"] == "eingerichtet"


def test_kanzlei_bekommt_die_kanzleirolle(verwaltung):
    client, bw = verwaltung
    client.post("/api/warteliste", json={"email": "buero@example.org",
                                         "art": "kanzlei"})
    r = client.post("/api/warteliste/einrichten", json={
        "email": "buero@example.org", "art": "kanzlei"})
    assert r.status_code == 200
    assert bw.nutzer_holen("buero@example.org")["rolle"] == "kanzlei"


def test_zweimal_einrichten_geht_nicht(verwaltung):
    client, bw = verwaltung
    client.post("/api/warteliste", json=ANMELDUNG)
    assert client.post("/api/warteliste/einrichten",
                       json=ANMELDUNG).status_code == 200
    r = client.post("/api/warteliste/einrichten", json=ANMELDUNG)
    assert r.status_code == 409


def test_ablehnen_ohne_konto(verwaltung):
    client, bw = verwaltung
    client.post("/api/warteliste", json=ANMELDUNG)
    r = client.post("/api/warteliste/ablehnen",
                    json={"email": "salon@example.org"})
    assert r.status_code == 200
    assert bw.nutzer_holen("salon@example.org") is None


def test_fremde_adresse_nicht_einrichtbar(verwaltung):
    client, bw = verwaltung
    r = client.post("/api/warteliste/einrichten",
                    json={"email": "nie@gemeldet.org", "art": "salon"})
    assert r.status_code == 404


def test_apple_id_eintragen_und_ablesen(verwaltung):
    """Nina klebt die Apple-ID in die Karte — der Rest läuft vom Server."""
    client, bw = verwaltung
    client.post("/api/warteliste", json=ANMELDUNG)
    r = client.post("/api/warteliste/apple-id", json={
        "email": "salon@example.org", "apple_id": "salon.apple@icloud.com"})
    assert r.status_code == 200
    assert r.json()["app_status"] == "eingetragen"
    zeile = [w for w in client.get("/api/warteliste").json()["warteliste"]
             if w["email"] == "salon@example.org"]
    assert zeile[0]["apple_id"] == "salon.apple@icloud.com"
    assert zeile[0]["app_status"] == "eingetragen"


def test_apple_id_ohne_adresse_wird_abgewiesen(verwaltung):
    client, bw = verwaltung
    client.post("/api/warteliste", json=ANMELDUNG)
    r = client.post("/api/warteliste/apple-id", json={
        "email": "salon@example.org", "apple_id": "keine-mail"})
    assert r.status_code == 400


def test_apple_id_nur_fuer_verwaltung(klient):
    client, bw = klient
    r = client.post("/api/warteliste/apple-id", json={
        "email": "x@example.org", "apple_id": "a@b.de"})
    assert r.status_code in (401, 403)


def test_app_status_steht_auch_ohne_apple_id(verwaltung):
    """Alte Zeilen ohne Apple-ID sagen 'fehlt' statt nichts."""
    client, bw = verwaltung
    client.post("/api/warteliste", json=ANMELDUNG)
    zeile = [w for w in client.get("/api/warteliste").json()["warteliste"]
             if w["email"] == "salon@example.org"]
    assert zeile[0]["app_status"] == "fehlt"


def test_die_anmeldeseite_ist_die_warteliste():
    portal = (Path(__file__).resolve().parents[1] / "portal.html").read_text()
    assert 'id="wl-senden"' in portal
    assert "/api/warteliste" in portal
    # Der Selbstbedienungs-Stepper ist weg: kein Anmeldeweg mehr ins Portal.
    assert 'id="reg-start"' not in portal
