"""Mehrseitige Belege: EIN PDF, EIN Beleg, die Endsumme vom letzten Blatt.

Ninas Wunsch vom 26.08. (GitLab #69): eine Rechnung über mehrere Seiten
machte vorher aus jeder Seite einen eigenen Beleg. Jetzt bündelt die App
die Seiten zu einem PDF und schickt Gemmas Ergebnis mit — diese Tests
sichern die Server-Strecke dafür ab, die vorher für PDFs ungetestet war.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent

# Ein minimales, aber echtes einseitiges PDF — pypdfium2 muss es öffnen können.
MINI_PDF = (b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 280]>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
            b"0000000052 00000 n \n0000000101 00000 n \n"
            b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n164\n%%EOF\n")


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
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(babu_web, "_box_wache",
                        lambda request: ("nina@0711.io", None))
    monkeypatch.setattr(babu_web, "_mitarbeit_wache",
                        lambda un, recht, tun: None)
    return babu_web, bare


def _im_stand(bare):
    r = subprocess.run(["git", "--git-dir", str(bare), "ls-tree", "-r",
                        "--name-only", "HEAD"], capture_output=True, text=True)
    return r.stdout.splitlines()


ERGEBNIS = {
    "klasse": "beleg",
    "buchung": {"lieferant": "Henkel", "datum": "2026-02-24",
                "betrag_eur": 189.61, "ust_satz": 19,
                "kategorie": "ware", "dokumentklasse": "beleg"},
    "zeilen": [{"text": "— Seite 1 von 2 —", "conf": 1},
               {"text": "Henkel Rechnung", "conf": 0.99, "box": [10, 5, 40, 2]},
               {"text": "Übertrag 120,00", "conf": 0.98, "box": [60, 90, 25, 2]},
               {"text": "— Seite 2 von 2 —", "conf": 1},
               {"text": "Zahlungsbetrag EUR 189,61", "conf": 1, "box": [55, 80, 35, 2]}],
}


def _hochladen(bw, dateiname="beleg_2026-02-24_henkel_ab12cd34.pdf"):
    from fastapi.testclient import TestClient
    c = TestClient(bw.app, base_url="https://testserver")
    return c.post(f"/api/aufnahme?name={dateiname}",
                  files={"file": (dateiname, MINI_PDF, "application/pdf")},
                  data={"text": "— Seite 1 von 2 —\nHenkel Rechnung\n"
                                "— Seite 2 von 2 —\nZahlungsbetrag EUR 189,61",
                        "ergebnis": json.dumps(ERGEBNIS)})


def test_buendel_pdf_wird_ein_beleg_mit_review(welt):
    bw, bare = welt
    r = _hochladen(bw)
    assert r.status_code == 200, r.text
    dateien = _im_stand(bare)
    pdfs = [d for d in dateien if d.startswith("docs/") and d.endswith(".pdf")]
    assert len(pdfs) == 1, dateien
    stamm = Path(pdfs[0]).stem
    review_roh = subprocess.run(
        ["git", "--git-dir", str(bare), "show", f"HEAD:review/{stamm}.json"],
        capture_output=True).stdout
    review = json.loads(review_roh)
    assert review["felder"]["brutto"] == 189.61
    assert review["dokumentklasse"] == "beleg"
    # Beide Seiten stehen in der archivierten Lesung.
    assert "Seite 2 von 2" in review["ocr_text"]
    # Gebucht ohne offene Fragen = geprüft. Zielbild-Reviews tragen
    # summenprobe_ok = None (keine Probe mehr) — das darf den grünen
    # Zustand nicht aufhalten (Abnahme-Fund vom 27.08.).
    from fastapi.testclient import TestClient
    c = TestClient(bw.app, base_url="https://testserver")
    d = c.get(f"/api/beleg/{stamm}").json()
    assert d["status"] == "geprüft", d["status"]


def test_auszug_im_namen_schlaegt_die_buchhaltung_nicht(welt):
    """Die Falle: PDFs mit „auszug" im Namen gingen ins Kontoauszugsfach —
    auch wenn die Buchhaltung längst „beleg" entschieden hatte."""
    bw, bare = welt
    r = _hochladen(bw, dateiname="beleg_2026-02-24_kontoauszugservice_ab12cd34.pdf")
    assert r.status_code == 200, r.text
    dateien = _im_stand(bare)
    assert any(d.startswith("docs/") and d.endswith(".pdf") for d in dateien), dateien
    assert not any(d.startswith("auszuege/") for d in dateien), dateien


def test_marker_zeilen_ueberleben_die_normalisierung(welt):
    bw, _ = welt
    zeilen = bw._zeilen_normalisieren(ERGEBNIS["zeilen"])
    assert "— Seite 1 von 2 —" in zeilen[0]
    assert any("Zahlungsbetrag" in z for z in zeilen)


def test_normalisierung_kappt_auch_buendel_bei_250(welt):
    bw, _ = welt
    viele = [{"text": f"Zeile {i}", "conf": 1} for i in range(400)]
    assert len(bw._zeilen_normalisieren(viele)) == 250
