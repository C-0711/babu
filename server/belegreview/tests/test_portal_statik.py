"""Zwei Kleinigkeiten, die jeder Browser bei jedem Besuch anfasst (10.10.2026).

Der Service Worker des Portals liegt unter /portal/sw.js und soll /portal
selbst bedienen — ohne `Service-Worker-Allowed` lehnt Chrome die
Registrierung ab, und das Portal hatte nie einen Offline-Stand. Und
/favicon.ico holt jeder Browser ungefragt; ein 404 je Seitenaufruf ist Lärm
im Log und ein leerer Tab-Reiter.
"""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import babu_web  # noqa: E402


def test_service_worker_darf_portal_bedienen():
    antwort = TestClient(babu_web.app).get("/portal/sw.js")
    assert antwort.status_code == 200
    assert antwort.headers["service-worker-allowed"] == "/portal"
    assert "javascript" in antwort.headers["content-type"]


def test_favicon_ist_da():
    antwort = TestClient(babu_web.app).get("/favicon.ico")
    assert antwort.status_code == 200
    assert antwort.headers["content-type"] == "image/png"
    assert antwort.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_zweitname_leitet_auf_den_einen_namen(monkeypatch):
    monkeypatch.setenv("BABU_WEITERLEITEN", "mybabu.de, www.mybabu.de")
    monkeypatch.setattr(babu_web, "PORTAL_ORIGIN", "https://mybabu.io")
    c = TestClient(babu_web.app, base_url="https://www.mybabu.de")
    antwort = c.get("/portal?x=1", follow_redirects=False)
    assert antwort.status_code == 301
    assert antwort.headers["location"] == "https://mybabu.io/portal?x=1"
    # Der eine Name selbst wird nie weitergeleitet.
    assert TestClient(babu_web.app, base_url="https://mybabu.io").get(
        "/hilfe", follow_redirects=False).status_code == 200


def test_ohne_liste_keine_weiterleitung(monkeypatch):
    monkeypatch.delenv("BABU_WEITERLEITEN", raising=False)
    assert TestClient(babu_web.app, base_url="https://www.mybabu.de").get(
        "/hilfe", follow_redirects=False).status_code == 200
