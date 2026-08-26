"""Salon-Check: die Strecke zwischen Hochladen und Bericht.

Nina hat am 22.08. ihre Unterlagen hochgeladen und gewartet. Hochladen,
Blätter zeigen und Bericht schreiben standen — dazwischen fehlte alles:

· Ein gescanntes Blatt hat keine Textebene. Der Klartext für die Ernte kam
  aus `seiten_text()`, und der ist bei einem Scan leer — ein fotografierter
  Bescheid gab also nichts her, obwohl alles darauf steht. Jetzt liest ein
  Blatt ohne Text Gemma (multimodal) ab.
· Eingeordnet wurde nur nach dem Abschluss-Vokabular (euer/bwa/bescheid).
  Ein Mietvertrag, ein Kontoauszug, eine Rechnung landeten als „sonstiges"
  — und für „sonstiges" ist die Positivliste leer, es wurde also nichts
  geerntet. Jetzt entscheidet `einsortieren`, was nicht ins Abschluss-
  Vokabular passt.
· Alles lag danach im Fach „Jahresabschluss". Der Mietvertrag gehört zu den
  Verträgen.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent

MIETVERTRAG = """
Mietvertrag über Gewerberäume
zwischen Hausverwaltung Lämmle GmbH, Marktplatz 1, 70173 Stuttgart
und Salon SupremeBeauty, Inhaberin Nina Ostertag
Mietgegenstand: Ladenlokal Hauptstraße 3
Monatliche Grundmiete 1.250,00 EUR
Vertragsbeginn 01.03.2024, Kündigungsfrist drei Monate
"""

KONTOAUSZUG = """
Sparkasse Stuttgart
Kontoauszug Nr. 7/2025
Kontoinhaberin: Nina Ostertag
IBAN DE02 1203 0000 0000 2020 51
BIC SOLADEST600
Buchungstag Valuta Verwendungszweck
02.07. 02.07. Lastschrift Friseurbedarf Nord
Kontostand 4.812,55 EUR
"""

BESCHEID = """
Finanzamt Stuttgart-Mitte
Rotebühlplatz 30, 70178 Stuttgart
Bescheid für 2025 über Einkommensteuer und Solidaritätszuschlag
Steuernummer 93815/12345
Festsetzung: Einkünfte aus Gewerbebetrieb 41.280,00 EUR
Rechtsbehelfsbelehrung: Gegen diesen Bescheid ist der Einspruch zulässig.
"""


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "README.md").write_text("box")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "s"],
                   check=True, capture_output=True)
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

    sys.path.insert(0, str(HIER.parent))
    import babu_web
    import boxschreiber
    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "ABSCHLUSS_TMP", tmp_path / "abschluss-tmp")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    return client, bare, babu_web


# ————— Klartext: Textebene, sonst Gemma —————

def test_ein_text_pdf_braucht_keine_blattlesung(welt, monkeypatch, tmp_path):
    """Wo eine Textebene liegt, ist sie die bessere Quelle — und kostenlos."""
    client, _, bw = welt
    import abschluss_lesen
    monkeypatch.setattr(abschluss_lesen, "seiten_text", lambda p: [BESCHEID])
    gerufen = []
    monkeypatch.setattr(bw, "_ocr_seite", lambda *a: gerufen.append(a) or "")

    pfad = tmp_path / "bescheid.pdf"
    pfad.write_bytes(b"%PDF-1.4")
    assert "93815/12345" in bw.klartext_der_unterlage(pfad)
    assert gerufen == [], "die Blatt-Lesung wurde gerufen, obwohl Text dastand"


def test_ein_gescanntes_blatt_liest_gemma(welt, monkeypatch, tmp_path):
    """Der Fall, an dem die Ernte hing: Scan ohne Textebene."""
    client, _, bw = welt
    import abschluss_lesen
    monkeypatch.setattr(abschluss_lesen, "seiten_text", lambda p: ["", ""])
    monkeypatch.setattr(abschluss_lesen, "seiten_bilder",
                        lambda p, **k: [b"\xff\xd8blatt1", b"\xff\xd8blatt2"])
    monkeypatch.setattr(bw, "_ocr_seite",
                        lambda jpeg, name: BESCHEID if b"blatt1" in jpeg else "Seite 2")

    pfad = tmp_path / "scan.pdf"
    pfad.write_bytes(b"%PDF-1.4")
    text = bw.klartext_der_unterlage(pfad)
    assert "Steuernummer 93815/12345" in text
    assert "Seite 2" in text, "auch die Folgeseiten gehören dazu"


def test_ein_foto_liest_gemma_auch(welt, monkeypatch, tmp_path):
    """Ein JPEG hat gar keine Textebene — `seiten_text` warf dort einen Fehler."""
    client, _, bw = welt
    import abschluss_lesen
    monkeypatch.setattr(abschluss_lesen, "seiten_bilder",
                        lambda p, **k: [b"\xff\xd8foto"])
    monkeypatch.setattr(bw, "_ocr_seite", lambda jpeg, name: MIETVERTRAG)

    pfad = tmp_path / "vertrag.jpg"
    pfad.write_bytes(b"\xff\xd8foto")
    assert "Mietvertrag" in bw.klartext_der_unterlage(pfad)


def test_eine_stumme_blattlesung_kippt_nichts(welt, monkeypatch, tmp_path):
    """Ohne Dienst gibt es weniger im Bericht — aber keinen Abbruch."""
    client, _, bw = welt
    import abschluss_lesen

    def kaputt(*a, **k):
        raise RuntimeError("Dienst weg")
    monkeypatch.setattr(abschluss_lesen, "seiten_text", lambda p: [""])
    monkeypatch.setattr(abschluss_lesen, "seiten_bilder", lambda p, **k: [b"x"])
    monkeypatch.setattr(bw, "_ocr_seite", kaputt)

    pfad = tmp_path / "scan.pdf"
    pfad.write_bytes(b"%PDF")
    assert bw.klartext_der_unterlage(pfad) == ""


# ————— Einordnen: nicht alles ist ein Jahresabschluss —————

def test_ein_mietvertrag_ist_ein_vertrag(welt):
    client, _, bw = welt
    assert bw.unterlage_einordnen("sonstiges", MIETVERTRAG) == "vertrag"


def test_ein_kontoauszug_ist_ein_kontoauszug(welt):
    client, _, bw = welt
    assert bw.unterlage_einordnen("sonstiges", KONTOAUSZUG) == "kontoauszug"


def test_eine_erkannte_gewinnrechnung_bleibt_eine_gewinnrechnung(welt):
    """Das Abschluss-Vokabular hat Vorrang — es ist das genauere."""
    client, _, bw = welt
    assert bw.unterlage_einordnen("euer", MIETVERTRAG) == "euer"


def test_ohne_text_bleibt_es_sonstiges(welt):
    """Raten wäre schlimmer als nichts zu wissen."""
    client, _, bw = welt
    assert bw.unterlage_einordnen("sonstiges", "") == "sonstiges"


# ————— Ernten: was jetzt herauskommt —————

def test_der_kontoauszug_gibt_seine_iban_her(welt):
    """Vorher „sonstiges" — und für sonstiges wird nichts geerntet."""
    client, _, bw = welt
    status = {"stand": "liest", "dokumente": [], "felder": [], "vorschlaege": []}
    art = bw.unterlage_einordnen("sonstiges", KONTOAUSZUG)
    bw._stammdaten_ernten("christoph0711.io", status,
                          [{"datei": "auszug.pdf", "art": art, "text": KONTOAUSZUG}],
                          2025, {})
    # Angeboten, nicht gesetzt (Regel seit 23.08.2026).
    assert bw.db_einstellungen("christoph0711.io") == {}
    v = {x["schluessel"]: x["neu"] for x in status["vorschlaege"]}
    assert v["iban"] == "DE02120300000000202051"
    assert v["bic"] == "SOLADEST600"
    # Die Anschrift der Sparkasse gehört nicht Nina — Positivliste.
    assert "betrieb_ort" not in v


def test_der_mietvertrag_gibt_nichts_her_und_das_ist_richtig(welt):
    """Zwei Parteien auf einem Blatt: lieber nichts als das Konto des Vermieters."""
    client, _, bw = welt
    status = {"stand": "liest", "dokumente": [], "felder": [], "vorschlaege": []}
    bw._stammdaten_ernten("christoph0711.io", status,
                          [{"datei": "miete.pdf", "art": "vertrag",
                            "text": MIETVERTRAG}], 2025, {})
    assert bw.db_einstellungen("christoph0711.io") == {}


# ————— Einsortieren: das richtige Fach in der Ablage —————

def _ablegen(client, bw, name: str, fach_art: str) -> None:
    """Eine Unterlage samt Beiakte in die Box legen, wie der Lauf es tut."""
    import boxschreiber
    boxschreiber.schreiben({
        f"abschluss/2025/{name}": b"%PDF-1.4",
        f"abschluss/2025/{name}.meta.json": json.dumps(
            {"titel": name, "art": "abschluss", "erkannt": fach_art,
             "fach": bw.ABLAGE_FACH.get(fach_art, "abschluss")}).encode(),
    }, None, f"abschluss: {name}", "christoph0711.io")
    bw._INDEX.update(head=None, geprueft=0.0)


def test_der_mietvertrag_landet_bei_den_vertraegen(welt):
    client, _, bw = welt
    _ablegen(client, bw, "mietvertrag.pdf", "vertrag")
    jahre = client.get("/api/ablage").json()["jahre"]
    faecher = {a["art"]: a for j in jahre for a in j["arten"]}
    assert "vertrag" in faecher, f"nur {sorted(faecher)}"
    assert faecher["vertrag"]["stuecke"][0]["titel"] == "mietvertrag.pdf"
    assert "abschluss" not in faecher


def test_die_gewinnrechnung_bleibt_beim_jahresabschluss(welt):
    client, _, bw = welt
    _ablegen(client, bw, "euer2025.pdf", "euer")
    jahre = client.get("/api/ablage").json()["jahre"]
    faecher = {a["art"] for j in jahre for a in j["arten"]}
    assert faecher == {"abschluss"}


# ————— Die Positivliste darf keine Lücke haben —————

def test_jede_erkennbare_art_hat_eine_positivliste():
    """Ohne Eintrag wird stillschweigend nichts geerntet.

    Das ist die gewollte Voreinstellung — aber nur, wenn jemand sie
    bewusst gesetzt hat. Eine Art, die niemand eingetragen hat, sieht
    genauso aus und ist ein Versehen.
    """
    sys.path.insert(0, str(HIER.parent))
    import abschluss_lesen
    import einsortieren
    import salonpruefung

    erkennbar = set(abschluss_lesen.ARTEN) | set(einsortieren.MERKMALE) \
        | {"beleg", "sonstiges"}
    fehlt = erkennbar - set(salonpruefung.ERLAUBT_JE_ART)
    assert not fehlt, f"ohne Positivliste, wird nie geerntet: {sorted(fehlt)}"


def test_jede_erkennbare_art_hat_ein_ablagefach(welt):
    client, _, bw = welt
    import abschluss_lesen
    import einsortieren
    erkennbar = set(abschluss_lesen.ARTEN) | set(einsortieren.MERKMALE)
    for art in erkennbar:
        assert bw.ABLAGE_FACH.get(art, "abschluss") in bw.ABLAGE_ARTEN, \
            f"{art} zeigt auf ein Fach, das es in der Ablage nicht gibt"
