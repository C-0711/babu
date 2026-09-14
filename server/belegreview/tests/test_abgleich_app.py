"""Abgleich aus der App: was Nina am Telefon ändert, kommt in der Box an.

Ninas Fund vom 14.09.2026: sie hat in der App einen Beleg gelöscht und einen
anderen korrigiert — beides blieb auf dem Telefon, die Kanzlei sah den alten
Stand. Die App schickt seither jede Änderung an dieselben Routen wie das
Portal: `loeschen` und `angaben`. Serverseitig braucht das zwei Dinge, die
das Portal nie brauchte:

1. `angaben` MISCHT statt zu überschreiben — die App schickt erst den Betrag,
   später das Konto, und der zweite Aufruf darf den ersten nicht löschen.
2. `angaben` nimmt ein KONTO (Nummer) an, denn die App kennt keine Kategorie;
   kennt der Katalog die Nummer, wird sie zur Kategorie, sonst gilt sie wie
   eine Kanzlei-Korrektur. Dazu `steuerschluessel` und `status`
   („bestätigt" aus der Ein-Tap-Karte).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
GOLDEN = HIER / "golden" / "review_weingaertle.json"
STAMM = "20260812-225200-c781d6-beleg_2026-07-21_apcoa_22bf8b36"
BETRAG_OFFEN = "Der Rechnungsbetrag ist nicht sicher zu lesen."


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    _git(arbeit, "config", "user.name", "t")
    _git(arbeit, "config", "user.email", "t@l")
    golden = json.loads(GOLDEN.read_text())
    review = {k: v for k, v in golden.items() if k not in ("audit", "buchungssatz")}
    review["felder"] = dict(review["felder"], brutto=None, lieferant=None,
                            offen=[BETRAG_OFFEN], bewirtungssignal=False,
                            summenprobe_ok=True)
    (arbeit / "docs" / "2026-08").mkdir(parents=True)
    (arbeit / "review").mkdir()
    (arbeit / "docs" / "2026-08" / f"{STAMM}.jpg").write_bytes(b"\xff\xd8x")
    (arbeit / "review" / f"{STAMM}.json").write_text(json.dumps(review, ensure_ascii=False))
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "aufnahme+review")
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
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    return client


def _beleg(client) -> dict:
    return client.get(f"/api/beleg/{STAMM}").json()


def _in_liste(client) -> dict:
    return next(z for z in client.get("/api/belege").json()["belege"] if z["stamm"] == STAMM)


def test_zwei_angaben_nacheinander_bleiben_beide_erhalten(welt):
    """Erst der Betrag (Feldkorrektur), später das Konto (Ein-Tap-Karte)."""
    client = welt
    assert client.post(f"/api/angaben/{STAMM}", json={"brutto": "4,20", "lieferant": "APCOA"}).status_code == 200
    r = client.post(f"/api/angaben/{STAMM}", json={"konto": "6530", "status": "bestaetigt"})
    assert r.status_code == 200, r.text
    ang = r.json()["angaben"]
    assert ang["brutto"] == 4.20 and ang["lieferant"] == "APCOA"      # nicht überschrieben
    assert ang["konto_skr04"] == "6530" and ang["bestaetigt"] is True
    assert ang["beantwortet"] == ["brutto", "lieferant"]
    d = _beleg(client)
    assert d["felder"]["brutto"] == 4.20
    assert d["einschaetzung"]["konto_skr04"] == "6530"


def test_ein_konto_aus_dem_katalog_wird_zur_kategorie(welt):
    """Die App schickt „6530" — im Katalog sind das die Kfz-Kosten."""
    client = welt
    r = client.post(f"/api/angaben/{STAMM}", json={"konto": "6530"})
    assert r.status_code == 200, r.text
    assert r.json()["angaben"]["kategorie"] == "kfz"
    d = _beleg(client)
    assert d["einschaetzung"]["kategorie"] == "kfz"
    assert d["einschaetzung"]["konto"] == "6530"
    assert _in_liste(client)["konto_skr04"] == "6530"


def test_ein_fremdes_konto_gilt_wie_eine_korrektur(welt):
    """Eine Nummer, die der Katalog nicht kennt, wird trotzdem das Konto."""
    client = welt
    r = client.post(f"/api/angaben/{STAMM}", json={"konto": "4980", "steuerschluessel": "9"})
    assert r.status_code == 200, r.text
    assert "kategorie" not in r.json()["angaben"]
    assert _in_liste(client)["konto_skr04"] == "4980"
    assert _in_liste(client)["steuerschluessel"] == "9"
    d = _beleg(client)
    assert d["einschaetzung"]["konto_skr04"] == "4980"
    assert d["einschaetzung"]["steuerschluessel"] == "9"


def test_konto_wird_geprueft(welt):
    client = welt
    assert client.post(f"/api/angaben/{STAMM}", json={"konto": "65"}).status_code == 400
    assert client.post(f"/api/angaben/{STAMM}", json={"konto": "abc"}).status_code == 400
    # Ein unbekannter Status ist keine Angabe.
    assert client.post(f"/api/angaben/{STAMM}", json={"status": "irgendwas"}).status_code == 400


def test_bestaetigen_aus_der_app_schliesst_die_lesefragen(welt):
    """Wer auf der Ein-Tap-Karte bestätigt, hat die offenen Punkte gesehen —
    dieselbe Regel wie beim Speichern im Portal-Formular."""
    client = welt
    assert _in_liste(client)["offen"] == [BETRAG_OFFEN]
    r = client.post(f"/api/angaben/{STAMM}", json={"status": "bestaetigt"})
    assert r.status_code == 200, r.text
    z = _in_liste(client)
    assert z["offen"] == [] and z["bestaetigt"] is True
    assert z["status"] == "geprüft"
    assert _beleg(client)["bestaetigt"] is True


def test_das_portal_ueberschreibt_weiterhin_nichts_fremdes(welt):
    """Auch das Portal profitiert vom Mischen: Kategorie nach Betrag."""
    client = welt
    client.post(f"/api/angaben/{STAMM}", json={"brutto": "4,20"})
    client.post(f"/api/angaben/{STAMM}", json={"kategorie": "fahrt"})
    d = _beleg(client)
    assert d["felder"]["brutto"] == 4.20
    assert d["einschaetzung"]["kategorie"] == "fahrt"
