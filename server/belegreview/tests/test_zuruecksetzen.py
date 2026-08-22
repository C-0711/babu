"""Zurücksetzen für die Testphase.

Ein Knopf, der etwas löscht, wird danach beurteilt, was er NICHT löscht.
Hier steht deshalb vor allem, was ein Zurücksetzen unberührt lassen muss:
die Belegbox, das Konto, die Kundinnen, den WhatsApp-Zugang.
"""
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent


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

    sys.path.insert(0, str(HIER.parent))
    import babu_web
    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None
    babu_web._REG_ZULETZT.clear()

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    return client, babu_web


def _einrichten(client):
    client.post("/api/einstellungen", json={
        "betrieb_name": "Salon Nina", "steuernummer": "99012/34567",
        "kleinunternehmer": "Nein", "versteuerung": "ist"})


# ————— Was weggeht —————

def test_die_einrichtung_ist_danach_leer(welt):
    client, _ = welt
    _einrichten(client)
    assert client.get("/api/einstellungen").json().get("betrieb_name") == "Salon Nina"

    r = client.post("/api/einrichtung/zuruecksetzen")
    assert r.status_code == 200 and r.json()["ok"] is True

    e = client.get("/api/einstellungen").json()
    for feld in ("betrieb_name", "steuernummer", "kleinunternehmer", "versteuerung"):
        assert not e.get(feld), f"{feld} steht noch da"


def test_zweimal_zuruecksetzen_geht_auch(welt):
    """Kein Fehler, wenn schon nichts mehr da ist."""
    client, _ = welt
    assert client.post("/api/einrichtung/zuruecksetzen").status_code == 200
    assert client.post("/api/einrichtung/zuruecksetzen").status_code == 200


# ————— Was ausdrücklich bleibt —————

def test_die_belegbox_bleibt_unberuehrt(welt):
    """Belege sind Auditmaterial. Ein Testknopf fasst sie nicht an."""
    client, _ = welt
    _einrichten(client)
    vorher = client.get("/api/ablage").json()
    kopf_vorher = client.get("/api/belege").json()

    client.post("/api/einrichtung/zuruecksetzen")

    assert client.get("/api/ablage").json() == vorher
    assert client.get("/api/belege").json() == kopf_vorher


def test_das_konto_bleibt_angemeldet(welt):
    client, _ = welt
    _einrichten(client)
    client.post("/api/einrichtung/zuruecksetzen")
    ich = client.get("/api/ich")
    assert ich.status_code == 200 and ich.json()["box"] is True


def test_kundinnen_und_termine_bleiben(welt):
    """„Werkseinstellung" heißt Einrichtung, nicht Datenverlust."""
    client, _ = welt
    _einrichten(client)
    client.post("/api/kundinnen", json={"name": "Frau Holder", "allergie": "PPD"})
    client.post("/api/leistungen", json={"name": "Farbe", "preis": "89,00",
                                         "minuten": 120})
    client.post("/api/einrichtung/zuruecksetzen")

    assert len(client.get("/api/kundinnen").json()["kundinnen"]) == 1
    assert len(client.get("/api/leistungen").json()["leistungen"]) == 1


def test_der_whatsapp_zugang_bleibt(welt):
    """Sonst nimmt ein Testknopf beiläufig den Anbieterzugang mit."""
    client, _ = welt
    client.post("/api/whatsapp/einstellungen", json={
        "telefon_id": "555000", "token": "EAAG-geheim", "an": True})
    _einrichten(client)
    client.post("/api/einrichtung/zuruecksetzen")

    w = client.get("/api/whatsapp").json()
    assert w["token_da"] is True and w["telefon_id"] == "555000" and w["an"] is True


def test_geloescht_wird_nur_die_positivliste(welt):
    """Gegenprobe: eine Einstellung außerhalb der Liste überlebt."""
    client, bw = welt
    _einrichten(client)
    bw.db_einstellung_setzen("christoph0711.io", "marke_farbe", "#8B6F4E")
    client.post("/api/einrichtung/zuruecksetzen")
    assert bw.db_einstellungen("christoph0711.io").get("marke_farbe") == "#8B6F4E"


def test_die_liste_deckt_die_einrichtung_ab(welt):
    """Was das Portal abfragt, muss auch zurückgesetzt werden — sonst
    startet die Einrichtung mit halb gefüllten Feldern."""
    _, bw = welt
    for feld in ("betrieb_name", "steuernummer", "kleinunternehmer",
                 "versteuerung"):
        assert feld in bw.EINRICHTUNGSFELDER


# ————— Wer darf das —————

def test_ohne_anmeldung_geht_nichts(welt):
    _, bw = welt
    from fastapi.testclient import TestClient
    fremd = TestClient(bw.app, base_url="https://testserver")
    assert fremd.post("/api/einrichtung/zuruecksetzen").status_code == 401


def test_fremdes_konto_setzt_nichts_zurueck(welt):
    client, bw = welt
    _einrichten(client)
    from fastapi.testclient import TestClient
    fremd = TestClient(bw.app, base_url="https://testserver")
    bw._REG_ZULETZT.clear()
    fremd.post("/api/signup", json={"salon": "Fremd", "email": "f@x.de",
                                    "passwort": "passwort-lang"})
    assert fremd.post("/api/einrichtung/zuruecksetzen").status_code == 403
    assert client.get("/api/einstellungen").json().get("betrieb_name") == "Salon Nina"
