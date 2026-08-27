"""Wer hat bezahlt? Kontoauszug ↔ gestellte Rechnungen.

babu kennt beide Seiten: den Geldeingang auf dem Auszug und die offene
Forderung. Nur verbunden hat sie bisher niemand — also musste die Inhaberin
Haken setzen, obwohl die Antwort schon zweimal im Haus lag.

Vorgeschlagen wird, nicht entschieden: ein „bezahlt" verschiebt Umsatz in
die Voranmeldung. Ein falscher Treffer wäre kein Schönheitsfehler.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kontoauszug as ka  # noqa: E402


def umsatz(betrag=535.5, datum="02.09.2026", text="Gutschrift Jana Allgaier"):
    return {"betrag": betrag, "datum": datum, "text": text, "typ": "Gutschrift"}


def rechnung(nummer="2026-0001", brutto=535.5, datum="2026-08-21",
             name="Jana Allgaier", bezahlt=None):
    return {"nummer": nummer, "brutto": brutto, "datum": datum,
            "bezahlt_am": bezahlt, "empfaenger": {"name": name}}


# ————— Der klare Fall —————

def test_betrag_und_name_treffen_ist_sicher():
    d = ka.rechnungen_abgleich([umsatz()], [rechnung()])
    assert len(d["vorschlaege"]) == 1
    v = d["vorschlaege"][0]
    assert v["nummer"] == "2026-0001"
    assert v["bezahlt_am"] == "2026-09-02"
    assert v["sicher"] is True
    assert "Jana" in v["text"]


def test_nur_der_betrag_trifft_ist_unsicher():
    """Ohne Namen im Verwendungszweck bleibt es ein Vorschlag zum Prüfen."""
    d = ka.rechnungen_abgleich([umsatz(text="Überweisung")], [rechnung()])
    assert len(d["vorschlaege"]) == 1
    assert d["vorschlaege"][0]["sicher"] is False


def test_cent_toleranz():
    d = ka.rechnungen_abgleich([umsatz(betrag=535.51)], [rechnung(brutto=535.50)])
    assert len(d["vorschlaege"]) == 1


# ————— Was NICHT vorgeschlagen wird —————

def test_schon_bezahlte_rechnungen_bleiben_aussen_vor():
    d = ka.rechnungen_abgleich([umsatz()], [rechnung(bezahlt="2026-08-30")])
    assert d["vorschlaege"] == []


def test_abbuchungen_sind_keine_zahlungseingaenge():
    d = ka.rechnungen_abgleich([umsatz(betrag=-535.5)], [rechnung()])
    assert d["vorschlaege"] == []


def test_geld_vor_der_rechnung_zaehlt_nicht():
    """Ein Eingang von vor dem Rechnungsdatum kann nicht ihre Zahlung sein."""
    d = ka.rechnungen_abgleich([umsatz(datum="01.08.2026")], [rechnung(datum="2026-08-21")])
    assert d["vorschlaege"] == []


def test_viel_zu_spaeter_eingang_wird_nicht_zugeordnet():
    d = ka.rechnungen_abgleich([umsatz(datum="02.03.2027")], [rechnung()])
    assert d["vorschlaege"] == []


def test_falscher_betrag_wird_nicht_geraten():
    d = ka.rechnungen_abgleich([umsatz(betrag=200.0)], [rechnung(brutto=535.5)])
    assert d["vorschlaege"] == []
    assert len(d["ohne_zuordnung"]) == 1


# ————— Mehrdeutigkeit —————

def test_zwei_gleiche_betraege_ohne_namen_sind_kein_vorschlag():
    """Zwei offene Rechnungen über denselben Betrag: babu rät nicht, welche."""
    d = ka.rechnungen_abgleich(
        [umsatz(text="Überweisung")],
        [rechnung("2026-0001", name="Jana"), rechnung("2026-0002", name="Mira")])
    assert d["vorschlaege"] == []
    assert d["mehrdeutig"], "die Mehrdeutigkeit muss sichtbar sein"


def test_der_name_loest_die_mehrdeutigkeit_auf():
    d = ka.rechnungen_abgleich(
        [umsatz(text="Gutschrift Mira Sommer")],
        [rechnung("2026-0001", name="Jana Allgaier"),
         rechnung("2026-0002", name="Mira Sommer")])
    assert len(d["vorschlaege"]) == 1
    assert d["vorschlaege"][0]["nummer"] == "2026-0002"


def test_eine_zahlung_deckt_nur_eine_rechnung():
    d = ka.rechnungen_abgleich(
        [umsatz(text="Gutschrift Jana Allgaier")],
        [rechnung("2026-0001"), rechnung("2026-0002")])
    assert len(d["vorschlaege"]) <= 1


# ————— Was übrig bleibt —————

def test_unerklaerte_eingaenge_werden_gezeigt():
    """Ein Eingang ohne Rechnung ist auch eine Information."""
    d = ka.rechnungen_abgleich([umsatz(betrag=1200.0, text="Miete Untermieter")], [])
    assert len(d["ohne_zuordnung"]) == 1
    assert d["ohne_zuordnung"][0]["betrag"] == 1200.0


def test_leere_eingabe_ist_kein_fehler():
    d = ka.rechnungen_abgleich([], [])
    assert d == {"vorschlaege": [], "ohne_zuordnung": [], "mehrdeutig": []}


# ————— Die Strecke am Server —————

def test_vorschlag_bestaetigen_macht_die_rechnung_bezahlt(tmp_path, monkeypatch):
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
    for k, v in (("betrieb_name", "Salon Nina"), ("anschrift", "Hauptstraße 5"),
                 ("steuernummer", "99012/34567"), ("kleinunternehmer", "Nein")):
        babu_web.db_einstellung_setzen("christoph0711.io", k, v)

    # Rechnung stellen und einen passenden Geldeingang ablegen.
    r = client.post("/api/rechnungen", json={
        "datum": "2026-08-21",
        "empfaenger": {"name": "Jana Allgaier", "anschrift": "Blumenweg 2"},
        "positionen": [{"text": "Stuhlmiete", "einzelpreis": 450.0,
                        "ust_satz": 19, "brutto": False}]})
    assert r.status_code == 200
    nummer = r.json()["nummer"]

    boxschreiber.schreiben(
        "auszuege/2026-09/auszug.pdf.umsaetze.json",
        json.dumps({"monat": "2026-09", "umsaetze": [
            {"betrag": 535.5, "datum": "02.09.2026",
             "text": "Gutschrift Jana Allgaier", "typ": "Gutschrift"}]}).encode(),
        "auszug", "christoph0711.io")
    babu_web._INDEX["geprueft"] = 0.0

    d = client.get("/api/zahlungen").json()
    assert d["auszug_da"] is True
    assert len(d["vorschlaege"]) == 1
    v = d["vorschlaege"][0]
    assert v["nummer"] == nummer and v["sicher"] is True

    # Bestätigen — und die Rechnung gilt als bezahlt.
    assert client.post("/api/zahlungen/uebernehmen",
                       json={"nummer": nummer, "am": v["bezahlt_am"]}).status_code == 200
    liste = client.get("/api/rechnungen").json()
    assert liste["rechnungen"][0]["stand"] == "bezahlt"
    assert liste["offen_anzahl"] == 0
    # Und der Vorschlag ist weg, weil nichts mehr offen ist.
    assert client.get("/api/zahlungen").json()["vorschlaege"] == []
