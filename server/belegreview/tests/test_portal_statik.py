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
