"""Ein neues Passwort beendet die alten Sitzungen; Telefone lassen sich trennen.

Bis 14.09.2026 lief ein Sitzungs-Cookie nach einem Passwortwechsel 30 Tage
weiter und ein Geräteschlüssel unbegrenzt — wer sein Passwort wegen eines
verlorenen Telefons zurücksetzte, sperrte genau dieses Telefon nicht aus.
Jetzt trägt das Cookie seine Ausgabezeit, `nutzer.sitzung_ab` (Migration
0006) den letzten Wechsel, und `/api/geraete` zeigt und trennt Geräte.
"""
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASSWORT = "ein-langes-passwort-hier"


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    import babu_web
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    for email in ("nina@salon.de", "bea@salon.de"):
        assert babu_web.nutzer_anlegen(email, email.split("@")[0], "Salon", "salon",
                                       passwort=PASSWORT, box=True) is not None
    return babu_web


def _client(bw):
    return TestClient(bw.app, base_url="https://testserver")


def _login(bw, email=("nina@salon.de"), passwort=PASSWORT):
    c = _client(bw)
    bw._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    r = c.post("/api/login", json={"email": email, "passwort": passwort})
    assert r.status_code == 200, r.text
    return c


def test_altes_cookie_stirbt_mit_dem_passwortwechsel(welt):
    bw = welt
    alt = _login(bw)
    assert alt.get("/api/ich").status_code == 200
    # Passwortwechsel in einer ZWEITEN Sitzung — die erste soll sterben.
    zweite = _login(bw)
    time.sleep(1.1)   # sitzung_ab hat Sekundenauflösung
    r = zweite.post("/api/passwort", json={"alt": PASSWORT, "neu": "neues-langes-passwort"})
    assert r.status_code == 200, r.text
    assert alt.get("/api/ich").status_code == 401
    # Die Sitzung, die geändert hat, bekam ein frisches Cookie und bleibt drin.
    assert zweite.get("/api/ich").status_code == 200
    # Und eine neue Anmeldung mit dem neuen Passwort geht.
    assert _login(bw, passwort="neues-langes-passwort").get("/api/ich").status_code == 200


def test_cookie_ohne_ausgabezeit_gilt_bis_zum_ersten_wechsel(welt):
    """Cookies von vor dem 14.09.2026 haben nur zwei Felder. Sie bleiben
    gültig — bis das Konto ein Passwort ändert."""
    import base64, hashlib, hmac  # noqa: PLC0415
    bw = welt
    nutz = base64.urlsafe_b64encode(f"nina@salon.de|{int(time.time()) + 3600}".encode()).decode().rstrip("=")
    sig = hmac.new(bw._geheimnis(), nutz.encode(), hashlib.sha256).hexdigest()  # noqa: SLF001
    c = _client(bw)
    c.cookies.set(bw.SESSION_COOKIE, f"{nutz}.{sig}")
    assert c.get("/api/ich").status_code == 200
    # /api/ich hat das Cookie dabei gleitend erneuert — mit Ausgabezeit „jetzt".
    # Der Wechsel muss danach liegen (Sekundenauflösung), sonst gilt es noch.
    time.sleep(1.1)
    with bw._DB_LOCK, bw._db() as conn:  # noqa: SLF001
        conn.execute("UPDATE nutzer SET sitzung_ab=? WHERE email=?",
                     (bw._jetzt_iso(), "nina@salon.de"))  # noqa: SLF001
    assert c.get("/api/ich").status_code == 401


def test_geraete_sehen_und_trennen(welt):
    bw = welt
    app = _client(bw)
    bw._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    r = app.post("/api/app-anmelden", json={"email": "nina@salon.de", "passwort": PASSWORT,
                                           "geraet": "Ninas iPhone"})
    assert r.status_code == 200, r.text
    schluessel = r.json()["schluessel"]

    portal = _login(bw)
    g = portal.get("/api/geraete").json()["geraete"]
    assert [x["name"] for x in g] == ["Ninas iPhone"]
    assert schluessel not in portal.get("/api/geraete").text   # nur der Hash, nie der Schlüssel

    # Eine andere Person sieht es nicht und kann es nicht trennen.
    bea = _login(bw, "bea@salon.de")
    assert bea.get("/api/geraete").json()["geraete"] == []
    assert bea.delete("/api/geraete/" + g[0]["id"]).status_code == 404
    assert bw.app_schluessel_pruefen(schluessel) == "nina@salon.de"

    # Nina trennt es: der Schlüssel ist sofort tot.
    assert portal.delete("/api/geraete/" + g[0]["id"]).status_code == 200
    assert portal.get("/api/geraete").json()["geraete"] == []
    assert bw.app_schluessel_pruefen(schluessel) is None
