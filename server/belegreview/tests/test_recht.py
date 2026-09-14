"""Impressum, Datenschutz, Nutzungsbedingungen — eigene Seiten, eine Quelle.

Apple verlangt für die Beta App Review eine Datenschutz-Adresse ohne
Anmeldung; das Portal und die Landing-Seite zeigen dieselben Texte. Solange
ein Text ein Platzhalter ist, sagt er das selbst — und `recht.fertig()`
hält den externen TestFlight-Start zurück.
"""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import recht  # noqa: E402


def _client():
    import babu_web
    return TestClient(babu_web.app, base_url="https://testserver")


def test_die_drei_seiten_gibt_es_ohne_anmeldung():
    c = _client()
    for art in ("impressum", "datenschutz", "agb"):
        r = c.get(f"/{art}")
        assert r.status_code == 200, art
        assert r.headers["content-type"].startswith("text/html")
        assert recht.TEXTE[art][0] in r.text
        assert "<script" not in r.text


def test_platzhalter_sagen_es_selbst():
    c = _client()
    for art in recht.ARTEN:
        if not recht.fertig(art):
            assert "noch ein Platzhalter" in c.get(f"/{art}").text


def test_api_liefert_dieselben_texte(monkeypatch):
    c = _client()
    d = c.get("/api/recht").json()
    assert set(d) == {"impressum", "datenschutz", "agb"}
    assert d["datenschutz"]["titel"] == "Datenschutz"
    assert d["impressum"]["fertig"] is recht.fertig("impressum")
    # Ein echter Text macht die Art fertig — und den Hinweis auf der Seite weg.
    monkeypatch.setitem(recht.TEXTE, "agb", ("Nutzungsbedingungen", "§ 1 Geltung. Diese Bedingungen gelten …"))
    assert recht.fertig("agb") is True
    assert "noch ein Platzhalter" not in c.get("/agb").text
    assert "§ 1 Geltung" in c.get("/agb").text


def test_portal_und_landing_verlinken_die_seiten():
    portal = (HIER.parent / "portal.html").read_text()
    landing = (HIER.parent.parent / "landing" / "index.html").read_text()
    assert "/api/recht" in portal
    for pfad in ("/impressum", "/datenschutz", "/agb"):
        assert f'href="{pfad}"' in landing, pfad
    assert "Impressum &amp; Datenschutz folgen" not in landing
