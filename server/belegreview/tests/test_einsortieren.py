"""Die Kamera fragt nicht, was das ist — babu sortiert es ein.

Bisher landete alles als Beleg unter docs/, egal ob Kassenbon, Mietvertrag,
Bescheid vom Finanzamt oder Kontoauszug. Wer einen Vertrag ablegen wollte,
musste im Portal den richtigen Knopf finden. Jetzt entscheidet der Text.

Die Entscheidung läuft über Stichwörter, nicht über ein Sprachmodell: sie
muss auch dann stimmen, wenn vLLM gerade nicht antwortet — und sie muss
erklärbar sein, wenn sie mal danebenliegt.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import einsortieren as es  # noqa: E402


BON = """Friseur Großhandel Wagner GmbH
Rechnung Nr. 4711
Shampoo 5L                 45,00
Farbe Set                  73,49
Netto                     118,49
MwSt 19 %                  22,51
Summe                     141,00
Bar gegeben               150,00
Rückgeld                    9,00
"""

MIETVERTRAG = """Mietvertrag über Gewerberäume

zwischen Hausverwaltung Sonnenberg GmbH (Vermieter)
und Salon Nina (Mieter)

§ 1 Mietgegenstand
Vermietet werden die Räume im Erdgeschoss.
§ 3 Mietzins
Die monatliche Grundmiete beträgt 1.250,00 EUR zzgl. Umsatzsteuer.
§ 8 Kündigung
Die Kündigungsfrist beträgt 3 Monate zum Quartalsende.
"""

BESCHEID = """Finanzamt Stuttgart
Steuernummer 99012/34567

Bescheid über Umsatzsteuer-Vorauszahlung für August 2026

Sehr geehrte Damen und Herren,
die festgesetzte Vorauszahlung ist bis zum 10.09.2026 zu entrichten.
Rechtsbehelfsbelehrung: Gegen diesen Bescheid kann Einspruch eingelegt werden.
"""

AUSZUG = """Sparkasse Stuttgart
Kontoauszug Nr. 8/2026
IBAN DE02 1203 0000 0000 2020 51
Alter Kontostand           2.415,33 EUR
01.08. Lastschrift Miete   1.487,50 S
05.08. Gutschrift EC       388,00 H
Neuer Kontostand           1.315,83 EUR
"""

VERSICHERUNG = """Allianz Versicherungs-AG
Versicherungsschein Nr. 4711-BG

Betriebshaftpflichtversicherung
Jahresbeitrag: 1.050,00 EUR
Vertragsbeginn: 01.01.2025
Die Kündigung ist drei Monate vor Ablauf möglich.
"""


# ————— Der Normalfall bleibt der Normalfall —————

def test_ein_kassenbon_ist_ein_beleg():
    assert es.entscheiden(BON)["art"] == "beleg"


def test_leerer_text_bleibt_beleg():
    """Im Zweifel Beleg — das ist der häufigste Fall und der harmloseste
    Irrtum: ein falsch abgelegter Vertrag fällt sofort auf, ein als
    Vertrag abgelegter Bon würde in der Auswertung fehlen."""
    for text in ("", "   ", None, "unlesbares Gekritzel"):
        assert es.entscheiden(text)["art"] == "beleg"


# ————— Was sonst noch vor die Linse kommt —————

def test_ein_mietvertrag_ist_ein_vertrag():
    d = es.entscheiden(MIETVERTRAG)
    assert d["art"] == "vertrag"
    assert d["ziel"] == "dokumente"


def test_eine_versicherungspolice_ist_ein_vertrag():
    assert es.entscheiden(VERSICHERUNG)["art"] == "vertrag"


def test_ein_bescheid_ist_post_vom_amt():
    d = es.entscheiden(BESCHEID)
    assert d["art"] == "behoerde"
    assert d["ziel"] == "dokumente"


def test_ein_kontoauszug_ist_ein_kontoauszug():
    d = es.entscheiden(AUSZUG)
    assert d["art"] == "kontoauszug"
    assert d["ziel"] == "auszuege"


def test_rechnung_mit_bankverbindung_ist_kein_kontoauszug():
    """Der Fall vom 23.08.2026: 32 Rechnungsfotos lagen im Auszugsfach,
    weil IBAN/BIC im Rechnungsfuß als Auszugssignal zählten — und was dort
    liegt, liest nie wieder jemand."""
    text = """slavic hair GmbH
Rechnung Nr. 2026-0312
Extensions blond 60cm      184,00
Netto                      154,62
MwSt 19 %                   29,38
Gesamtbetrag               184,00
Bitte überweisen Sie per Lastschrift oder auf:
IBAN DE44 5001 0517 5407 3249 31
BIC INGDDEFFXXX"""
    d = es.entscheiden(text)
    assert d["art"] == "beleg"
    assert d["ziel"] == "docs"


def test_ein_echter_auszug_bleibt_trotz_haertung_ein_auszug():
    """Die Härtung darf echte Auszüge nicht kosten — die tragen Kernwörter
    wie Kontostand und Buchungstag, die keine Rechnung druckt."""
    d = es.entscheiden(AUSZUG)
    assert d["art"] == "kontoauszug"
    assert d["sicher"] is True


# ————— Die schwierigen Fälle —————

def test_rechnung_vom_finanzamt_ist_trotzdem_post():
    """„Bescheid" schlägt „Rechnung" — sonst landet der Steuerbescheid
    als Betriebsausgabe in der Buchhaltung."""
    text = "Finanzamt Stuttgart\nBescheid\nzu zahlender Betrag 1.240,00 EUR\n" \
           "Rechnungsbetrag\nRechtsbehelfsbelehrung"
    assert es.entscheiden(text)["art"] == "behoerde"


def test_ein_bon_mit_dem_wort_vertrag_bleibt_ein_bon():
    """Ein Bon über eine Vertragsgebühr ist kein Vertrag."""
    text = BON + "\nVertragsnummer 12345\n"
    assert es.entscheiden(text)["art"] == "beleg"


def test_ein_langer_vertrag_schlaegt_einzelne_belegwoerter():
    text = MIETVERTRAG + "\nSumme 1.250,00\nMwSt 19 %\n"
    assert es.entscheiden(text)["art"] == "vertrag"


def test_die_entscheidung_ist_erklaerbar():
    """Wenn babu danebenliegt, muss nachvollziehbar sein, warum."""
    d = es.entscheiden(MIETVERTRAG)
    assert d["grund"], "ohne Begründung ist die Einsortierung nicht prüfbar"
    assert any(w in d["grund"].lower() for w in ("vertrag", "kündigung", "miet"))


def test_sicherheit_wird_mitgeliefert():
    """Bei knapper Entscheidung soll die App nachfragen dürfen."""
    sicher = es.entscheiden(MIETVERTRAG)
    unsicher = es.entscheiden("Irgendein Zettel ohne klare Merkmale")
    assert sicher["sicher"] is True
    assert unsicher["sicher"] is False


# ————— Wohin es dann geht —————

@pytest.mark.parametrize("art, anfang", [
    ("beleg", "docs/"),
    ("vertrag", "dokumente/"),
    ("behoerde", "dokumente/"),
    ("kontoauszug", "auszuege/"),
])
def test_der_pfad_passt_zur_art(art, anfang):
    pfad = es.pfad_fuer(art, "20260822-101500-abc123-foto.jpg", "2026-08")
    assert pfad.startswith(anfang)
    assert pfad.endswith("foto.jpg")


def test_unbekannte_art_landet_bei_den_belegen():
    pfad = es.pfad_fuer("quatsch", "20260822-101500-abc123-foto.jpg", "2026-08")
    assert pfad.startswith("docs/")


# ————— Die Strecke: fotografieren und richtig ablegen —————

import json  # noqa: E402
import subprocess  # noqa: E402


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
    # Die Hintergrund-Leser brauchen ein Sprachmodell — in Tests still legen.
    monkeypatch.setattr(babu_web, "_vertrag_job", lambda *a, **k: None)
    monkeypatch.setattr(babu_web, "_brief_job", lambda *a, **k: None)
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={}, rechnungen={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    return client, bare


def _stand(bare) -> list[str]:
    return subprocess.run(["git", "-C", str(bare), "ls-tree", "-r", "--name-only", "HEAD"],
                          capture_output=True, text=True).stdout.split()


def test_ein_bon_landet_bei_den_belegen(welt):
    client, bare = welt
    r = client.post("/api/aufnahme", params={"name": "foto.jpg", "text": BON},
                    content=b"\xff\xd8\xff\xe0bild")
    assert r.status_code == 200
    d = r.json()
    assert d["art"] == "beleg"
    assert d["wohin"] == "Bei deinen Belegen"
    assert any(p.startswith("docs/") for p in _stand(bare))


def test_ein_vertrag_landet_in_der_ablage(welt):
    """Derselbe Knopf, dasselbe Foto — anderer Inhalt, anderer Ort."""
    client, bare = welt
    r = client.post("/api/aufnahme", params={"name": "foto.jpg", "text": MIETVERTRAG},
                    content=b"\xff\xd8\xff\xe0bild")
    assert r.status_code == 200
    assert r.json()["art"] == "vertrag"
    assert r.json()["wohin"] == "Bei deinen Verträgen"
    stand = _stand(bare)
    assert any(p.startswith("dokumente/") and p.endswith(".jpg") for p in stand)
    # Der Zettel muss mit, sonst weiß die Ablage den Ordner nicht.
    meta = [p for p in stand if p.endswith(".meta.json")]
    assert meta, "ohne Meta-Zettel landet der Vertrag im falschen Ordner"


def test_ein_vertrag_taucht_in_der_ablage_auf(welt):
    client, _ = welt
    client.post("/api/aufnahme", params={"name": "foto.jpg", "text": MIETVERTRAG},
                content=b"\xff\xd8\xff\xe0bild")
    jahre = client.get("/api/ablage").json()["jahre"]
    arten = {a["art"] for j in jahre for a in j["arten"]}
    assert "vertrag" in arten


def test_ein_bescheid_landet_bei_der_post(welt):
    client, _ = welt
    r = client.post("/api/aufnahme", params={"name": "foto.jpg", "text": BESCHEID},
                    content=b"\xff\xd8\xff\xe0bild")
    assert r.json()["art"] == "behoerde"
    assert r.json()["wohin"] == "Bei deiner Post vom Amt"


def test_die_app_erfaehrt_warum(welt):
    """Bei einer knappen Entscheidung soll die App nachfragen können."""
    client, _ = welt
    r = client.post("/api/aufnahme", params={"name": "foto.jpg", "text": MIETVERTRAG},
                    content=b"\xff\xd8\xff\xe0bild")
    assert r.json()["sicher"] is True
    assert r.json()["grund"]

    r2 = client.post("/api/aufnahme", params={"name": "foto.jpg", "text": "Zettel"},
                     content=b"\xff\xd8\xff\xe0bild")
    assert r2.json()["sicher"] is False


def test_ohne_zugang_kein_ablegen(welt):
    client, bw = welt
    from fastapi.testclient import TestClient
    import babu_web
    fremd = TestClient(babu_web.app, base_url="https://testserver")
    assert fremd.post("/api/aufnahme", content=b"x").status_code == 401
