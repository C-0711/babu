"""Ambassador-Strecke: anlegen, Link, einlösen, Meilenstein, Auszahlung.

Der Weg, den Ninas Verwaltung und die Ambassadorin zusammen laufen —
end-to-end gegen die echte Schema-Initialisierung (SQLite-Fassung),
wie test_warteliste ihn fährt.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import babu_web  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture()
def kunde(tmp_path, monkeypatch):
    monkeypatch.setenv("BABU_SIGNUP", "1")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    with babu_web._DB_LOCK, babu_web._db() as c:
        pass  # Schema anlegen (erste Verbindung initialisiert)
    return TestClient(babu_web.app, base_url="https://testserver"), babu_web


def _als_verwaltung(k, email="chef@example.org"):
    tc, bw = k
    bw.nutzer_anlegen(email, "Chef", "babu", "admin", passwort="test-test")
    r = tc.post("/api/login", json={"email": email, "passwort": "test-test"})
    assert r.status_code == 200, r.text
    return tc, bw


def test_ambassador_voller_weg(kunde):
    tc, bw = _als_verwaltung(kunde)

    # 1) Verwaltung legt die Ambassadorin an
    r = tc.post("/api/ambassador", json={"name": "Babs", "email": "babs@example.org"})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    startpw = r.json()["startpasswort"]
    assert code.startswith("BABS")

    # 2) Ambassadorin meldet sich an, sieht ihre leere Seite
    r = tc.post("/api/login", json={"email": "babs@example.org", "passwort": startpw})
    assert r.status_code == 200, r.text
    r = tc.get("/api/ambassador/me")
    assert r.status_code == 200, r.text
    assert r.json()["code"] == code and r.json()["salons"] == []

    # 3) Link erzeugen, Landing aufrufen, Salon löst ein
    r = tc.post("/api/ambassador/link", json={"salon": "Salon Meridian"})
    assert r.status_code == 200
    link = r.json()["link"]
    assert code in link
    landing = tc.get(f"/ambassador/{code}/salon-meridian")
    assert landing.status_code == 200
    assert "Salon Meridian" not in landing.text  # Formular, nicht Text

    r = tc.post("/api/warteliste", json={
        "email": "meridian@example.org", "art": "salon",
        "salon": "Salon Meridian", "bemerkung": f"Code {code}"})
    assert r.status_code == 200, r.text

    # 4) Verwaltung erkennt den Meilenstein — reihenfolgetreu
    # (zurück in die Chef-Sitzung: Meilenstein-Anerkennung ist Verwaltungs-Sache)
    tc.post("/api/abmelden")
    r = tc.post("/api/login", json={"email": "chef@example.org", "passwort": "test-test"})
    assert r.status_code == 200, r.text
    r = tc.post("/api/ambassador/meilenstein", json={
        "code": code, "email": "meridian@example.org",
        "meilenstein": "gehalten", "betrag": 237})
    assert r.status_code == 409  # 'gehalten' setzt 'gezeichnet' voraus

    r = tc.post("/api/ambassador/meilenstein", json={
        "code": code, "email": "meridian@example.org",
        "meilenstein": "gezeichnet", "betrag": 237})
    assert r.status_code == 200, r.text

    # Doppelt abhaken schlägt fehl
    r = tc.post("/api/ambassador/meilenstein", json={
        "code": code, "email": "meridian@example.org",
        "meilenstein": "gezeichnet", "betrag": 237})
    assert r.status_code == 409

    r = tc.post("/api/ambassador/meilenstein", json={
        "code": code, "email": "meridian@example.org",
        "meilenstein": "gehalten", "betrag": 237})
    assert r.status_code == 200, r.text

    # 5) Saldo stimmt, Auszahlung setzt auf null (wieder als Babs)
    tc.post("/api/abmelden")
    r = tc.post("/api/login", json={"email": "babs@example.org", "passwort": startpw})
    assert r.status_code == 200, r.text
    r = tc.get("/api/ambassador/me")
    assert r.json()["verdient"] == 474 and r.json()["offen"] == 474
    tc.post("/api/abmelden")
    r = tc.post("/api/login", json={"email": "chef@example.org", "passwort": "test-test"})
    assert r.status_code == 200, r.text
    r = tc.post("/api/ambassador/gezahlt", json={"code": code})
    assert r.status_code == 200 and r.json()["gezahlt"] == 474
    tc.post("/api/abmelden")
    r = tc.post("/api/login", json={"email": "babs@example.org", "passwort": startpw})
    assert r.status_code == 200, r.text
    r = tc.get("/api/ambassador/me")
    assert r.json()["offen"] == 0 and r.json()["gezahlt"] == 474

    # 6) Kein Zweitkonto für dieselbe E-Mail (Verwaltungs-Route → als Chef)
    tc.post("/api/abmelden")
    r = tc.post("/api/login", json={"email": "chef@example.org", "passwort": "test-test"})
    assert r.status_code == 200, r.text
    r = tc.post("/api/ambassador", json={"name": "Babs", "email": "babs@example.org"})
    assert r.status_code == 409, r.text


def test_landing_ohne_gueltigen_code(kunde):
    tc, bw = kunde
    r = tc.get("/ambassador/KEIN-CODE/x")
    assert r.status_code == 404
