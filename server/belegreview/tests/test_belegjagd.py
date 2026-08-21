"""Zu dieser Abbuchung fehlt ein Beleg — hast du ihn noch?

Am Jahresende kostet genau das Geld: eine Ausgabe, die vom Konto ging und
für die kein Beleg da ist, zählt nicht. babu sieht beide Seiten und fragt
nach, solange die Erinnerung noch frisch ist.

Und es fragt NICHT, wenn es die Antwort kennt: für die Miete liegt der
Vertrag in der Ablage, der IST der Beleg.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import belegjagd as bj  # noqa: E402


def abbuchung(betrag=-141.0, datum="03.08.2026", text="Friseur Großhandel Wagner"):
    return {"betrag": betrag, "datum": datum, "text": text}


def vertrag(betrag=1250.0, partner="Hausverwaltung Sonnenberg", art="miete"):
    return {"partner": partner, "art": art, "art_name": "Mietvertrag",
            "betrag_monat": betrag}


# ————— Wonach gefragt wird —————

def test_eine_abbuchung_ohne_beleg_wird_zur_frage():
    fragen = bj.offene_fragen([abbuchung()], [], set())
    assert len(fragen) == 1
    f = fragen[0]
    assert f["betrag"] == 141.0
    assert "Wagner" in f["text"]
    assert f["schluessel"]


def test_die_teuerste_frage_steht_oben():
    fragen = bj.offene_fragen(
        [abbuchung(-12.0, text="Klein"), abbuchung(-890.0, text="Groß")], [], set())
    assert [f["betrag"] for f in fragen] == [890.0, 12.0]


def test_der_schluessel_bleibt_gleich():
    """Sonst taucht dieselbe Frage nach jedem Neuladen wieder auf."""
    a = bj.offene_fragen([abbuchung()], [], set())[0]["schluessel"]
    b = bj.offene_fragen([abbuchung()], [], set())[0]["schluessel"]
    assert a == b


# ————— Wonach babu NICHT fragt —————

def test_fuer_die_miete_liegt_der_vertrag_vor():
    """Ein Dauerauftrag über den Vertragsbetrag braucht keinen Beleg —
    der Vertrag ist der Beleg."""
    fragen = bj.offene_fragen([abbuchung(-1250.0, text="Dauerauftrag Miete")],
                              [vertrag()], set())
    assert fragen == []


def test_vertragsbetrag_mit_umsatzsteuer_zaehlt_auch():
    """1.250 € netto laut Vertrag, 1.487,50 € gehen vom Konto."""
    fragen = bj.offene_fragen([abbuchung(-1487.50, text="Miete")],
                              [vertrag()], set())
    assert fragen == []


def test_ein_anderer_betrag_wird_trotzdem_gefragt():
    fragen = bj.offene_fragen([abbuchung(-2000.0, text="Überweisung")],
                              [vertrag()], set())
    assert len(fragen) == 1


def test_geklaertes_kommt_nicht_wieder():
    frage = bj.offene_fragen([abbuchung()], [], set())[0]
    assert bj.offene_fragen([abbuchung()], [], {frage["schluessel"]}) == []


def test_kleinbetraege_unter_der_schwelle_stoeren_nicht():
    """Wegen 1,20 € Kontoführung fragt niemand nach einem Beleg."""
    fragen = bj.offene_fragen([abbuchung(-1.20, text="Entgelt")], [], set())
    assert fragen == []


def test_eingaenge_sind_keine_ausgaben():
    assert bj.offene_fragen([abbuchung(betrag=535.5)], [], set()) == []


# ————— Was babu vermutet —————

def test_babu_sagt_was_es_vermutet():
    """Der Verwendungszweck ist ein Hinweis, kein Beweis — er hilft beim
    Erinnern: „Wagner, 141 €, am 3. August"."""
    f = bj.offene_fragen([abbuchung()], [], set())[0]
    assert "Wagner" in f["frage"]
    assert "141" in f["frage"].replace(",", ".")
    assert "03.08" in f["frage"]


# ————— Die Gründe, aus denen es keinen Beleg gibt —————

def test_die_gruende_sind_wenige_und_klar():
    assert set(bj.GRUENDE) == {"privat", "kein_beleg", "kommt_noch", "vertrag"}
    for schluessel, text in bj.GRUENDE.items():
        assert text and not text.endswith(".")


def test_unbekannter_grund_wird_abgewiesen():
    import pytest
    with pytest.raises(bj.JagdFehler):
        bj.grund_pruefen("weiss_nicht")
    assert bj.grund_pruefen("privat") == "privat"


# ————— Die Strecke am Server —————

def test_klaeren_beendet_die_frage(tmp_path, monkeypatch):
    import json
    import subprocess
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

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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
                           dokumente=[], zeiten={}, oid_cache={}, rechnungen={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200

    boxschreiber.schreiben(
        "auszuege/2026-08/auszug.pdf.umsaetze.json",
        json.dumps({"monat": "2026-08", "umsaetze": [
            {"betrag": -141.0, "datum": "03.08.2026",
             "text": "Friseur Großhandel Wagner", "typ": "Lastschrift"}]}).encode(),
        "auszug", "christoph0711.io")
    babu_web._INDEX["geprueft"] = 0.0

    d = client.get("/api/fehlende-belege").json()
    assert d["auszug_da"] is True
    assert len(d["fragen"]) == 1
    assert d["summe"] == 141.0
    schluessel = d["fragen"][0]["schluessel"]

    # Erfundener Grund geht nicht durch.
    assert client.post("/api/fehlende-belege/klaeren",
                       json={"schluessel": schluessel,
                             "grund": "keine_lust"}).status_code == 400

    assert client.post("/api/fehlende-belege/klaeren",
                       json={"schluessel": schluessel, "grund": "privat"}
                       ).status_code == 200
    # Einmal geklärt, nie wieder gefragt.
    assert client.get("/api/fehlende-belege").json()["fragen"] == []
