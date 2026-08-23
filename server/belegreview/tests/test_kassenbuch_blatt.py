"""Was das Tagesblatt in der Belegbox tragen muss.

Der Server kannte die Felder für Gutscheinverkauf und Umsatzaufteilung
schon, bevor die App sie liefern konnte. Mit BABU-34/35/36 kommen die
Zahlarten und die Entnahmegründe dazu — geprüft wird hier, dass jedes
Feld die Route unbeschadet passiert und im Git-Blatt landet. Wer nur
die App prüft, merkt nicht, dass unterwegs etwas abfällt.
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
    client.post("/api/anmelden", json={"pat": "test-pat"})
    return client, bare


def blatt_lesen(bare, datum):
    return json.loads(subprocess.run(
        ["git", "-C", str(bare), "show",
         f"HEAD:kassenbuch/{datum[:7]}/{datum}.json"],
        capture_output=True, check=True).stdout)


def test_zahlarten_und_entnahmegruende_kommen_durch(welt):
    """Gutschein als eigene Zahlart, Trinkgeld per Karte, drei Entnahmegründe.

    Vor BABU-34/35/36 fielen `trinkgeldKarte`, `vorschussTeam` und
    `auslagenErstattet` still auf 0 — die Route kannte sie nicht, und
    ein unbekanntes Feld beschwert sich nicht.
    """
    client, bare = welt
    assert client.post("/api/kassenbuch", json={
        "datum": "2026-08-20",
        "einnahmenBar": 300, "ecZahlungen": 500,
        "gutscheinVerkauf": 100, "gutscheineEingeloest": 60,
        "trinkgeldKarte": 30, "trinkgeldTeamEC": 20,
        "privatentnahmen": 50, "vorschussTeam": 200, "auslagenErstattet": 8.9,
    }).status_code == 200

    b = blatt_lesen(bare, "2026-08-20")
    assert b["gutscheinVerkauf"] == 100.0
    assert b["gutscheineEingeloest"] == 60.0
    assert b["trinkgeldKarte"] == 30.0
    assert b["trinkgeldTeamEC"] == 20.0
    assert b["privatentnahmen"] == 50.0
    assert b["vorschussTeam"] == 200.0
    assert b["auslagenErstattet"] == 8.9


def test_trinkgeld_traegt_seine_spur(welt):
    """Wer wieviel bekommen hat — sonst ist bei einer Kassenprüfung nicht
    erklärbar, warum Geld die Schublade verlassen hat."""
    client, bare = welt
    assert client.post("/api/kassenbuch", json={
        "datum": "2026-08-21", "trinkgeldKarte": 30, "trinkgeldTeamEC": 30,
        "trinkgeldVerteilt": [{"name": "Jana", "betrag": 18},
                              {"name": "Merve", "betrag": 12}],
    }).status_code == 200

    b = blatt_lesen(bare, "2026-08-21")
    assert b["trinkgeldVerteilt"] == [{"name": "Jana", "betrag": 18.0},
                                      {"name": "Merve", "betrag": 12.0}]
    assert sum(a["betrag"] for a in b["trinkgeldVerteilt"]) == b["trinkgeldTeamEC"]


def test_kein_feld_geht_beim_uebertragen_verloren(welt):
    """Jedes Feld, das die Route kennt, steht auch im Blatt — auch die
    mit 0. Das Blatt ist die Unterlage, nicht nur eine Meldung."""
    client, bare = welt
    import babu_web
    assert client.post("/api/kassenbuch", json={"datum": "2026-08-22"}).status_code == 200
    b = blatt_lesen(bare, "2026-08-22")
    for feld in babu_web.KASSENBUCH_ZAHLEN:
        assert feld in b, f"{feld} fehlt im Tagesblatt"
