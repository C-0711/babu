"""`GET /healthz` — das Lebenszeichen für Compose-Healthcheck und wache.sh.

Drei Prüfungen: Datenbank und Box-Klon sind hart (503), Gemma ist weich
(`stand: degraded`, weiter 200) — ohne Gemma nimmt babu-web Belege an und
liest sie nach. Ohne Anmeldung, ohne Geheimnisse.
"""
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    import babu_web
    import box as bx
    babu_web.PORTAL_DB = tmp_path / "portal.db"
    klon = tmp_path / "klon"
    klon.mkdir()
    monkeypatch.setattr(bx, "default_box",
                        lambda: types.SimpleNamespace(klon=klon))
    # Gemma antwortet — sonst nichts Weiteres nötig.
    monkeypatch.setattr(babu_web.requests, "get",
                        lambda url, timeout=0: types.SimpleNamespace(status_code=200))
    return TestClient(babu_web.app), babu_web, bx, klon


def test_alles_da_ist_ok(welt):
    client, bw, bx, klon = welt
    r = client.get("/healthz")
    assert r.status_code == 200
    d = r.json()
    assert d["stand"] == "ok"
    assert d["db"] == "ok" and d["box"] == "ok" and d["gemma"] == "ok"
    assert d["arbeit_offen"] == 0 and d["seit_s"] >= 0
    # Keine Anmeldung, keine Geheimnisse — nur die fünf Felder plus stand.
    assert set(d) == {"db", "box", "gemma", "seit_s", "arbeit_offen", "stand"}


def test_ohne_gemma_nur_degraded(welt, monkeypatch):
    client, bw, bx, klon = welt

    def weg(url, timeout=0):
        raise ConnectionError("vLLM ist weg")
    monkeypatch.setattr(bw.requests, "get", weg)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["gemma"] == "weg"
    assert r.json()["stand"] == "degraded"


def test_ohne_datenbank_503(welt, monkeypatch):
    client, bw, bx, klon = welt

    def kaputt():
        raise RuntimeError("keine Verbindung")
    monkeypatch.setattr(bw, "_db", kaputt)
    r = client.get("/healthz")
    assert r.status_code == 503
    assert r.json()["db"] == "weg" and r.json()["stand"] == "gestoert"
    # Das Schloss ist danach wieder frei — sonst hinge der nächste Request.
    assert bw._DB_LOCK.acquire(timeout=1)
    bw._DB_LOCK.release()


def test_ohne_box_klon_503(welt):
    client, bw, bx, klon = welt
    klon.rmdir()
    r = client.get("/healthz")
    assert r.status_code == 503
    assert r.json()["box"] == "weg"


def test_festgefahrenes_schloss_ist_503_statt_haengen(welt, monkeypatch):
    client, bw, bx, klon = welt
    assert bw._DB_LOCK.acquire(timeout=1)
    try:
        r = client.get("/healthz")
        assert r.status_code == 503
        assert r.json()["db"] == "schloss"
    finally:
        bw._DB_LOCK.release()
