"""UStVA, BWA und SuSa als Dokumente — Rechnung, SKR04-Prüfung, Ablage.

Die UStVA folgt dem amtlichen Vordruckmuster USt 1 A 2026 (Kz 81/86/48/66/83),
die BWA dem Zeilenschema der DATEV-BWA Nr. 1, die SuSa dem SKR04. Geprüft
wird hier: die SKR04-Prüfung nimmt die richtige Vorsteuer heraus, die
Saldenliste stimmt in sich, die PDFs sind echte, lesbare PDFs, und die
Routen legen alles in die neuen Ablage-Fächer.
"""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

from test_mehrseiten_buendel import _hochladen, _im_stand, welt  # noqa: F401,E402

import vordrucke  # noqa: E402


def _beleg(**kw):
    b = {"stamm": "s1", "lieferant": "Test", "brutto": 119.0, "netto": 100.0,
         "ust": 19.0, "ust_satz": 19, "kategorie": "verbrauchsmaterial",
         "konto_skr04": "6850", "status": "geprüft", "summenprobe_ok": True,
         "offen": []}
    b.update(kw)
    return b


def test_skr04_pruefung_kennt_die_faelle_ohne_vorsteuer():
    befunde = vordrucke.skr04_pruefung([
        _beleg(stamm="p", kategorie="privat"),
        _beleg(stamm="v", kategorie="versicherung", konto_skr04="6400"),
        _beleg(stamm="m", kategorie="miete", konto_skr04="6310"),
        _beleg(stamm="b", kategorie="bewirtung", konto_skr04="6640"),
        _beleg(stamm="ok"),
    ])
    folgen = {b["stamm"]: b["folge"] for b in befunde}
    assert folgen["p"] == "keine_vorsteuer"
    assert folgen["v"] == "keine_vorsteuer"
    assert folgen["m"] == "pruefen"
    assert folgen["b"] == "info"
    assert "ok" not in folgen


def test_summenprobe_wird_beanstandet():
    befunde = vordrucke.skr04_pruefung([_beleg(stamm="x", netto=90.0)])
    assert any(b["stamm"] == "x" and "gehen nicht auf" in b["befund"]
               for b in befunde)


def test_vorsteuer_geprueft_nimmt_privat_und_versicherung_heraus():
    vorsteuer, befunde = vordrucke.vorsteuer_geprueft([
        _beleg(stamm="ok"),
        _beleg(stamm="p", kategorie="privat"),
        _beleg(stamm="v", kategorie="versicherung"),
    ])
    # Nur der eine saubere Beleg liefert seine 19,00 in Kz 66.
    assert vorsteuer["vorsteuer"] == 19.0
    assert len([b for b in befunde if b["folge"] == "keine_vorsteuer"]) == 2


def test_susa_traegt_beide_seiten():
    import monatsabschluss as ma
    erloese = ma.erloese_monat([{"einnahmenBar": 500.0, "ecZahlungen": 690.0}])
    s = vordrucke.susa("2026-02", erloese, [_beleg()])
    konten = {z["konto"]: z for z in s["zeilen"]}
    assert konten["1600"]["soll"] == 500.0                # Kasse bar
    assert konten["4400"]["haben"] == 1000.0              # Erlöse 19 % netto
    assert konten["3806"]["haben"] == 190.0               # USt 19 %
    assert konten["1406"]["soll"] == 19.0                 # Vorsteuer
    assert konten["6850"]["soll"] == 100.0                # Aufwand netto
    assert konten["1800"]["haben"] == 119.0               # Gegenkonto Bank
    assert s["summe_soll"] > 0 and s["summe_haben"] > 0


def _pdf_text(daten: bytes) -> str:
    import pypdfium2 as pdfium
    d = pdfium.PdfDocument(io.BytesIO(daten))
    text = "\n".join(d[i].get_textpage().get_text_bounded()
                     for i in range(len(d)))
    d.close()
    return text


def test_ustva_pdf_folgt_dem_amtlichen_vordruck():
    import monatsabschluss as ma
    erloese = ma.erloese_monat([{"einnahmenBar": 1190.0}])
    vorsteuer, befunde = vordrucke.vorsteuer_geprueft(
        [_beleg(), _beleg(stamm="p", kategorie="privat")])
    entwurf = ma.ustva_entwurf("2026-02", erloese, vorsteuer,
                               {"braucht_ustva": True})
    pdf = vordrucke.ustva_pdf(entwurf, {"betrieb_name": "Salon Test",
                                        "steuernummer": "93815/28461"},
                              befunde)
    assert pdf.startswith(b"%PDF")
    text = _pdf_text(pdf)
    assert "Umsatzsteuer-Voranmeldung" in text
    assert "USt 1 A 2026" in text
    assert "81" in text and "66" in text and "83" in text
    assert "1.000,00" in text          # Kz 81 netto
    assert "171,00" in text            # Zahllast 190 − 19
    assert "Privatentnahme" in text or "kein Leistungsbezug" in text


def test_bwa_pdf_folgt_datev_zeilen():
    import monatsabschluss as ma
    erloese = ma.erloese_monat([{"einnahmenBar": 1190.0}])
    bwa = ma.bwa("2026-02", erloese, [_beleg()])
    pdf = vordrucke.bwa_pdf(bwa, {"betrieb_name": "Salon Test"})
    text = _pdf_text(pdf)
    for zeile in ("1010", "1060", "1280", "1300", "1380", "DATEV-BWA Nr. 1"):
        assert zeile in text, zeile


def test_susa_pdf_ist_lesbar():
    import monatsabschluss as ma
    erloese = ma.erloese_monat([{"einnahmenBar": 1190.0}])
    s = vordrucke.susa("2026-02", erloese, [_beleg()])
    text = _pdf_text(vordrucke.susa_pdf(s, {"betrieb_name": "Salon Test"}))
    assert "Summen- und Saldenliste" in text
    assert "SKR04" in text and "1406" in text


@pytest.fixture()
def berichtswelt(welt, monkeypatch):
    bw, bare = welt
    monkeypatch.setattr(bw, "db_einstellungen",
                        lambda un: {"betrieb_name": "Salon Test",
                                    "kleinunternehmer": "Nein"})
    monkeypatch.setattr(bw, "rolle", lambda un: "inhaberin")
    monkeypatch.setattr(bw, "team_personalkosten", lambda un: None)
    monkeypatch.setattr(bw, "vertraege_aktuell", lambda: [])
    monkeypatch.setattr(bw, "_versteuerung", lambda un: "ist")
    return bw, bare


def test_route_legt_ustva_ins_neue_fach(berichtswelt):
    bw, bare = berichtswelt
    assert _hochladen(bw).status_code == 200      # Henkel-Beleg, 2026-02
    from fastapi.testclient import TestClient
    c = TestClient(bw.app, base_url="https://testserver")
    r = c.post("/api/ustva/2026-02")
    assert r.status_code == 200, r.text
    assert r.json()["datei"] == "ustva/2026-02-ustva.pdf"
    dateien = _im_stand(bare)
    assert "ustva/2026-02-ustva.pdf" in dateien
    assert "ustva/2026-02-ustva.json" in dateien
    ablage = c.get("/api/ablage").json()
    arten = {a["art"]: a for j in ablage["jahre"] for a in j["arten"]}
    assert "ustva" in arten
    assert arten["ustva"]["name"] == "Umsatzsteuervoranmeldung"
    # Das Dokument lässt sich über die Ablage-Route auch öffnen.
    assert c.get("/api/dokument/ustva/2026-02-ustva.pdf").status_code == 200


def test_route_legt_bwa_susa_und_jahresauflauf_ins_bwa_fach(berichtswelt):
    bw, bare = berichtswelt
    assert _hochladen(bw).status_code == 200
    from fastapi.testclient import TestClient
    c = TestClient(bw.app, base_url="https://testserver")
    r = c.post("/api/bwa/2026-02")
    assert r.status_code == 200, r.text
    dateien = _im_stand(bare)
    for p in ("bwa/2026-02-bwa.pdf", "bwa/2026-02-susa.pdf",
              "bwa/2026-ytd-bwa.pdf", "bwa/2026-ytd-susa.pdf"):
        assert p in dateien, p
    ablage = c.get("/api/ablage").json()
    arten = {a["art"]: a for j in ablage["jahre"] for a in j["arten"]}
    assert arten["bwa"]["anzahl"] == 4
    titel = {s["titel"] for s in arten["bwa"]["stuecke"]}
    assert "BWA Jahresauflauf 2026" in titel
    assert "Summen und Salden Jahresauflauf 2026" in titel
    # Der Jahresauflauf trägt den Zeitraum in Worten.
    import subprocess as sp
    roh = sp.run(["git", "--git-dir", str(bare), "show",
                  "HEAD:bwa/2026-ytd-bwa.pdf"], capture_output=True).stdout
    assert "Januar bis Februar" in _pdf_text(roh)


def test_bwa_summe_addiert_monate():
    import monatsabschluss as ma
    e1 = ma.erloese_monat([{"einnahmenBar": 1190.0}])
    e2 = ma.erloese_monat([{"einnahmenBar": 2380.0}])
    b1 = ma.bwa("2026-01", e1, [_beleg()])
    b2 = ma.bwa("2026-02", e2, [_beleg(stamm="s2", brutto=238.0,
                                       netto=200.0, ust=38.0)])
    ytd = vordrucke.bwa_summe([b1, b2], "Jahresauflauf 2026 (Januar bis Februar)")
    assert ytd["umsatz_netto"] == b1["umsatz_netto"] + b2["umsatz_netto"]
    assert ytd["ergebnis"] == vordrucke._rund(b1["ergebnis"] + b2["ergebnis"])
    gruppe = {g["schluessel"]: g for g in ytd["gruppen"]}["sonstiges"]
    assert gruppe["netto"] == 300.0 and gruppe["anzahl"] == 2


def test_erloese_summe_addiert_betraege_aber_nicht_offen():
    import monatsabschluss as ma
    e1 = dict(ma.erloese_monat([{"einnahmenBar": 100.0}]), offen=50.0)
    e2 = dict(ma.erloese_monat([{"einnahmenBar": 200.0}]), offen=50.0)
    s = vordrucke.erloese_summe([e1, e2])
    assert s["bar"] == 300.0 and s["tage"] == 2
    assert s["offen"] == 50.0        # Bestandsgröße, nicht additiv


def test_kleinunternehmerin_bekommt_keine_ustva(berichtswelt, monkeypatch):
    bw, _ = berichtswelt
    monkeypatch.setattr(bw, "db_einstellungen",
                        lambda un: {"kleinunternehmer": "Ja"})
    from fastapi.testclient import TestClient
    c = TestClient(bw.app, base_url="https://testserver")
    r = c.post("/api/ustva/2026-02")
    assert r.status_code == 400
    assert "Kleinunternehmerin" in r.json()["fehler"]
