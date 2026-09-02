"""Der Kassenbuch-Weg vom Portal aus — Cookie-Session statt PAT-Header.

Runde 3a (docs/uebergabe-datev-2026-09-02): das Portal bekommt ein echtes
Kassenbuch-Formular für den Rechner. Die Route `/api/kassenbuch` selbst ist
unverändert (siehe test_kassenbuch_blatt.py / test_kassenfest.py) — hier
wird nur geprüft, dass der Portal-Weg (Anmeldung per Zugangscode, danach
ausschließlich das Session-Cookie, kein Authorization-Header) exakt denselben
Vertrag erfüllt: Normalfall ohne Vorher-Stand, Sperre ohne Begründung bei
einem zweiten Schreibversuch, Erfolg mit Begründung.
"""
import json
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
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "start"],
                   check=True, capture_output=True)
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

    sys.path.insert(0, str(HIER.parent))
    import babu_web
    import boxschreiber

    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    r = client.post("/api/anmelden", json={"pat": "test-pat"})
    assert r.status_code == 200
    # Ab hier trägt der Client nur noch das Session-Cookie — kein PAT-Header
    # mehr im Spiel, genau der Weg, den das Portal im Browser geht.
    assert "Authorization" not in client.headers
    return client, bare


def _blatt(bare, datum):
    return json.loads(subprocess.run(
        ["git", "-C", str(bare), "show",
         f"HEAD:kassenbuch/{datum[:7]}/{datum}.json"],
        capture_output=True, check=True).stdout)


def test_portal_traegt_einen_neuen_tag_ein(welt):
    """Der Normalfall: noch nichts für diesen Tag, das Formular schreibt frisch."""
    client, bare = welt
    r = client.get("/api/kassenbuch/2026-08-20")
    assert r.status_code == 200
    d = r.json()
    assert d["blatt"] is None
    assert d["zustand"]["eingetragen"] is False

    body = {"datum": "2026-08-20", "bestandVortag": 100.0, "einnahmenBar": 320.5,
            "ecZahlungen": 480.0, "gezaehltSchluss": 420.5}
    r = client.post("/api/kassenbuch", json=body)
    assert r.status_code == 200, r.text
    blatt = _blatt(bare, "2026-08-20")
    assert blatt["einnahmenBar"] == 320.5
    assert blatt["ecZahlungen"] == 480.0
    assert blatt["gezaehltSchluss"] == 420.5

    # Direkt danach zeigt die Vorbelegung fürs Formular den echten Stand.
    r = client.get("/api/kassenbuch/2026-08-20")
    d = r.json()
    assert d["blatt"]["einnahmenBar"] == 320.5
    assert d["zustand"]["eingetragen"] is True


def test_zweiter_schreibversuch_ohne_grund_wird_gesperrt(welt):
    """GoBD: wer einen schon eingetragenen Tag ändert, sagt warum — sonst 400."""
    client, _ = welt
    erst = {"datum": "2026-08-21", "einnahmenBar": 200.0, "ecZahlungen": 100.0}
    assert client.post("/api/kassenbuch", json=erst).status_code == 200

    ohne_grund = dict(erst, einnahmenBar=250.0)
    r = client.post("/api/kassenbuch", json=ohne_grund)
    assert r.status_code == 400
    d = r.json()
    assert "schreib" in d["fehler"].lower() or "begründ" in d["fehler"].lower()
    # Genau dieses Feld liest das Portal aus, um das Grund-Eingabefeld
    # einzublenden statt bei jedem 400 blind zu raten.
    assert d["abgeschlossen"] is False


def test_zweiter_schreibversuch_mit_grund_geht_durch(welt):
    client, bare = welt
    erst = {"datum": "2026-08-22", "einnahmenBar": 200.0, "ecZahlungen": 100.0}
    assert client.post("/api/kassenbuch", json=erst).status_code == 200

    mit_grund = dict(erst, einnahmenBar=250.0, grund="Zahlendreher beim Zählen")
    r = client.post("/api/kassenbuch", json=mit_grund)
    assert r.status_code == 200, r.text
    blatt = _blatt(bare, "2026-08-22")
    assert blatt["einnahmenBar"] == 250.0
    assert blatt["grund"] == "Zahlendreher beim Zählen"


def test_festgeschriebener_monat_bleibt_dicht_auch_mit_grund(welt):
    """409 mit `abgeschlossen: true` — das Portal blendet dann KEIN Grundfeld
    ein, weil eine Begründung hier ohnehin nichts mehr ändert."""
    client, _ = welt
    import boxschreiber

    tag = {"datum": "2026-07-05", "einnahmenBar": 100.0}
    assert client.post("/api/kassenbuch", json=tag).status_code == 200

    # Genau EIN Ereignis schreibt fest: die Voranmeldung des Monats liegt
    # in der Box (_monat_festgeschrieben prüft exakt diese Datei).
    boxschreiber.schreiben("abschluss/2026-07/ustva.json", b"{}",
                          "ustva: 2026-07", "christoph0711.io")

    r = client.post("/api/kassenbuch",
                    json=dict(tag, einnahmenBar=999.0, grund="egal"))
    assert r.status_code == 409
    d = r.json()
    assert d["abgeschlossen"] is True
    assert "abgeschlossen" in d["fehler"].lower()

    r = client.get("/api/kassenbuch/2026-07-05")
    assert r.json()["zustand"]["abgeschlossen"] is True
