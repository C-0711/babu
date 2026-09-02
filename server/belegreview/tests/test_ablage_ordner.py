"""Die Ablage als Ordner, in die man hineingeht — Ninas „wie bei Google Drive".

Am Telefon blättert man; am Schreibtisch hat man einen großen Bildschirm und
will links den Baum, rechts den Inhalt. Was dafür serverseitig fehlte:

· Suchen. Es gab keinen Weg, in dem zu suchen, was babu GELESEN hat — nur
  in Dateinamen, und die heißen 20260812-225200-c781d6-….jpg.
· Umbenennen. Ein Dokument hieß, wie die Datei hieß.
· Verschieben. Was einmal im falschen Fach lag, blieb dort.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent
GOLDEN = HIER / "golden" / "review_weingaertle.json"
STAMM = "20260812-225200-c781d6-beleg_2026-07-21_weingaerty_22bf8b36"
DOKUMENT = "dokumente/2026-08/mietvertrag.pdf"


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
    (arbeit / "docs" / "2026-08").mkdir(parents=True)
    (arbeit / "docs" / "2026-08" / f"{STAMM}.jpg").write_bytes(b"\xff\xd8x")
    (arbeit / "review").mkdir()
    (arbeit / "review" / f"{STAMM}.json").write_text(
        json.dumps(review, ensure_ascii=False))

    (arbeit / "dokumente" / "2026-08").mkdir(parents=True)
    (arbeit / DOKUMENT).write_bytes(b"%PDF-1.4 vertrag")
    (arbeit / (DOKUMENT + ".meta.json")).write_text(
        json.dumps({"titel": "mietvertrag.pdf", "art": "vertrag"}))
    (arbeit / (DOKUMENT + ".erklaerung.json")).write_text(
        json.dumps({"einfach": "Die Hausverwaltung erhöht die Nebenkosten "
                               "ab Oktober um 40 Euro."}))

    # Eine Unterlage aus dem Salon-Check, samt gelesenem Klartext.
    (arbeit / "abschluss" / "2025").mkdir(parents=True)
    (arbeit / "abschluss" / "2025" / "euer2025.pdf").write_bytes(b"%PDF euer")
    (arbeit / "abschluss" / "2025" / "euer2025.pdf.meta.json").write_text(
        json.dumps({"titel": "euer2025.pdf", "art": "abschluss",
                    "erkannt": "euer", "fach": "abschluss"}))
    (arbeit / "abschluss" / "2025" / "euer2025.pdf.text.json").write_text(
        json.dumps({"text": "Einnahmenüberschussrechnung 2025\n"
                            "Wareneinsatz Friseurbedarf Nord 8.412,00"}))

    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "stand")
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
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    return client, bare, babu_web


def _faecher(client) -> dict:
    jahre = client.get("/api/ablage").json()["jahre"]
    return {a["art"]: a for j in jahre for a in j["arten"]}


# ————— Der Baum —————

def test_die_belege_haben_ein_eigenes_fach(welt):
    """Das Fach mit dem meisten Inhalt war das einzige ohne Ordner."""
    client, _, _ = welt
    fach = _faecher(client)["beleg"]
    assert fach["name"] == "Belege"
    stueck = fach["stuecke"][0]
    assert stueck["stamm"] == STAMM
    assert "Rotenberger" in stueck["titel"], stueck["titel"]
    assert "142,60" in stueck["titel"], "ohne Betrag erkennt man keinen Bon wieder"


# ————— Suchen: in dem, was gelesen wurde —————

def test_suche_findet_was_auf_dem_beleg_steht(welt):
    """„Württembergstraße" steht auf dem Bon, in keinem Dateinamen."""
    client, _, _ = welt
    d = client.get("/api/ablage/suche", params={"q": "Württembergstraße"}).json()
    assert [t["pfad"] for t in d["treffer"]] == [f"docs/2026-08/{STAMM}.jpg"]
    assert "Württembergstraße" in d["treffer"][0]["fundstelle"]


def test_suche_findet_in_der_erklaerung_eines_briefs(welt):
    client, _, _ = welt
    d = client.get("/api/ablage/suche", params={"q": "Nebenkosten"}).json()
    assert [t["pfad"] for t in d["treffer"]] == [DOKUMENT]


def test_suche_findet_im_klartext_einer_unterlage(welt):
    """Der Salon-Check hebt den gelesenen Text auf — sonst wäre er weg."""
    client, _, _ = welt
    d = client.get("/api/ablage/suche", params={"q": "Friseurbedarf"}).json()
    pfade = [t["pfad"] for t in d["treffer"]]
    assert "abschluss/2025/euer2025.pdf" in pfade


def test_suche_ist_gross_und_kleinschreibung_egal(welt):
    client, _, _ = welt
    d = client.get("/api/ablage/suche", params={"q": "rotenberger"}).json()
    assert d["treffer"], "Nina tippt klein"


def test_eine_leere_suche_liefert_nichts_statt_alles(welt):
    client, _, _ = welt
    d = client.get("/api/ablage/suche", params={"q": "  "}).json()
    assert d["treffer"] == []


def test_ohne_treffer_wird_das_auch_gesagt(welt):
    client, _, _ = welt
    d = client.get("/api/ablage/suche", params={"q": "Zebrastreifen"}).json()
    assert d["treffer"] == [] and d["gesamt"] == 0


# ————— Umbenennen —————

def test_ein_dokument_laesst_sich_umbenennen(welt):
    client, _, _ = welt
    r = client.post("/api/ablage/umbenennen",
                    json={"pfad": DOKUMENT, "titel": "Mietvertrag Hauptstraße 3"})
    assert r.status_code == 200, r.text
    stuecke = {s["pfad"]: s for f in _faecher(client).values() for s in f["stuecke"]}
    assert stuecke[DOKUMENT]["titel"] == "Mietvertrag Hauptstraße 3"


def test_ein_leerer_name_wird_abgewiesen(welt):
    client, _, _ = welt
    r = client.post("/api/ablage/umbenennen", json={"pfad": DOKUMENT, "titel": " "})
    assert r.status_code == 400


def test_was_aufbewahrt_werden_muss_behaelt_seinen_namen(welt):
    """Ein Buchungsstapel heißt, wie er heißt — daran hängt die Kanzlei."""
    client, _, _ = welt
    r = client.post("/api/ablage/umbenennen",
                    json={"pfad": "export/2026-08/EXTF_1.csv", "titel": "Egal"})
    assert r.status_code == 400


# ————— Verschieben —————

def test_ein_dokument_laesst_sich_in_ein_anderes_fach_legen(welt):
    client, _, _ = welt
    r = client.post("/api/ablage/verschieben",
                    json={"pfad": DOKUMENT, "art": "behoerde"})
    assert r.status_code == 200, r.text
    faecher = _faecher(client)
    assert DOKUMENT in [s["pfad"] for s in faecher["behoerde"]["stuecke"]]
    assert "vertrag" not in faecher


def test_eine_unterlage_aus_dem_salon_check_laesst_sich_umlegen(welt):
    """Was babu falsch eingeordnet hat, korrigiert Nina in einem Klick."""
    client, _, _ = welt
    r = client.post("/api/ablage/verschieben",
                    json={"pfad": "abschluss/2025/euer2025.pdf", "art": "vertrag"})
    assert r.status_code == 200, r.text
    faecher = _faecher(client)
    assert "abschluss/2025/euer2025.pdf" in [s["pfad"] for s in faecher["vertrag"]["stuecke"]]


def test_ein_erfundenes_fach_wird_abgewiesen(welt):
    client, _, _ = welt
    r = client.post("/api/ablage/verschieben",
                    json={"pfad": DOKUMENT, "art": "sonstwohin"})
    assert r.status_code == 400


def test_ein_beleg_wird_nicht_verschoben(welt):
    """Belege gehören zur Buchhaltung — ihr Ordner ist nicht frei wählbar."""
    client, _, _ = welt
    r = client.post("/api/ablage/verschieben",
                    json={"pfad": f"docs/2026-08/{STAMM}.jpg", "art": "vertrag"})
    assert r.status_code == 400


def test_mitarbeit_darf_die_ablage_nicht_umbauen(welt, monkeypatch):
    client, _, bw = welt
    monkeypatch.setattr(bw, "rolle", lambda un: "mitarbeit")
    r = client.post("/api/ablage/umbenennen",
                    json={"pfad": DOKUMENT, "titel": "Neu"})
    assert r.status_code == 403


# ————— Die Oberfläche muss die Ordner auch zeigen —————

PORTAL = (HIER.parent / "portal.html").read_text()


def test_das_portal_hat_baum_und_inhalt():
    assert "ablage-baum" in PORTAL, "kein Ordnerbaum"
    assert "ablage-mappe" in PORTAL, "keine Inhaltsfläche"


def test_das_portal_kann_zwischen_kacheln_und_liste_umschalten():
    assert "ablageAnsicht" in PORTAL
    assert "Kacheln" in PORTAL and "Liste" in PORTAL


def test_das_portal_sucht_ueber_die_neue_route():
    assert "/api/ablage/suche" in PORTAL


def test_das_portal_kann_umbenennen_und_verschieben():
    assert "/api/ablage/umbenennen" in PORTAL
    assert "/api/ablage/verschieben" in PORTAL


# ————— Vorschau und Seitenzahl: das Blatt, nicht der Dateiname —————

def _zweiseiter() -> bytes:
    """Ein echtes Zwei-Seiten-PDF, von pypdfium selbst gebaut."""
    import pypdfium2 as pdfium
    d = pdfium.PdfDocument.new()
    d.new_page(595, 842)
    d.new_page(595, 842)
    import io
    puffer = io.BytesIO()
    d.save(puffer)
    d.close()
    return puffer.getvalue()


def test_ein_pdf_traegt_seine_seitenzahl(welt, tmp_path):
    """Ein Kontoauszug über zwei Seiten zeigt sich als Stapel — dafür muss
    die Ablage wissen, wie viele Seiten er hat. Fotos haben eine."""
    client, bare, bw = welt
    import boxschreiber
    boxschreiber.schreiben({"auszuege/2026-01/auszug.pdf": _zweiseiter()},
                           None, "auszug", "t@l")
    bw._INDEX.update(geprueft=0.0)
    fach = _faecher(client)["kontoauszug"]
    stueck = next(s for s in fach["stuecke"] if s["pfad"].endswith("auszug.pdf"))
    assert stueck["seiten"] == 2
    beleg = _faecher(client)["beleg"]["stuecke"][0]
    assert beleg["seiten"] == 1


def test_auszug_titel_wird_synthetisiert(welt):
    """Kontoauszüge heißen wie ihre Rohdatei — babu kennt aber Monat und
    Bank aus dem Lesen und kann sie „Kontoauszug Juli 2026 · Kreissparkasse"
    nennen, statt des Zufallsnamens (Befund P1-7)."""
    client, _, bw = welt
    import boxschreiber
    boxschreiber.schreiben(
        {"auszuege/2026-07/20260701-abc-Auszug.pdf": _zweiseiter(),
         "auszuege/2026-07/20260701-abc-Auszug.pdf.umsaetze.json": json.dumps(
             {"konto": "12345678", "monat": "2026-07", "bank": "Kreissparkasse",
              "umsaetze": []}).encode()},
        None, "auszug", "t@l")
    bw._INDEX.update(geprueft=0.0)
    fach = _faecher(client)["kontoauszug"]
    stueck = next(s for s in fach["stuecke"] if s["pfad"].endswith("Auszug.pdf"))
    assert stueck["titel"] == "Kontoauszug Juli 2026 · Kreissparkasse"


def test_auszug_ohne_umsaetze_json_faellt_auf_den_rohnamen_zurueck(welt):
    """Alter Stand ohne Beiakte: der Rohname bleibt der Fallback."""
    client, _, bw = welt
    import boxschreiber
    boxschreiber.schreiben({"auszuege/2026-01/auszug.pdf": _zweiseiter()},
                           None, "auszug", "t@l")
    bw._INDEX.update(geprueft=0.0)
    fach = _faecher(client)["kontoauszug"]
    stueck = next(s for s in fach["stuecke"] if s["pfad"].endswith("auszug.pdf"))
    assert stueck["titel"] == "auszug.pdf"


def test_die_vorschau_liefert_die_erste_seite_als_bild(welt):
    client, _, bw = welt
    import boxschreiber
    boxschreiber.schreiben({"auszuege/2026-01/auszug.pdf": _zweiseiter()},
                           None, "auszug", "t@l")
    bw._INDEX.update(geprueft=0.0)
    r = client.get("/api/vorschau/auszuege/2026-01/auszug.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert len(r.content) > 500


def test_ein_kaputtes_pdf_bringt_die_ablage_nicht_um(welt):
    """Die Wegwerf-PDFs der Fixtures sind kein gültiges PDF — die Seitenzahl
    ist dann eben unbekannt, aber der Baum steht."""
    client, _, _ = welt
    fach = _faecher(client).get("vertrag") or _faecher(client)["kanzlei"]
    assert all("seiten" in s for s in fach["stuecke"])
