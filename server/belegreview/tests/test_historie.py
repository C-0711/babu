"""Die Zeit vor babu: DATEV-Buchungsstapel einlesen.

Wer wechselt, bringt Jahre mit. Bisher las babu davon nur Jahresunterlagen
als PDF und teilte die Jahressumme für den Vergleich durch zwölf. Hier wird
der Buchungsstapel selbst gelesen — dieselbe EXTF-Datei, die babu schreibt.

Die Gegenprobe ist deshalb besonders schön: der Stapel, den `extf.py`
erzeugt, muss von `historie.py` wieder lesbar sein.
"""
import json
import subprocess
import sys
from pathlib import Path

import historie as hi
import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

from test_mehrseiten_buendel import _im_stand, welt  # noqa: F401,E402

KOPF = ('"EXTF";700;21;"Buchungsstapel";13;20260828120000000;;"BA";"babu";;'
        '0;0;20250101;4;20250101;20251231;"Vorjahr";"";1;0;1;"EUR";;;;;;;;;;')
SPALTEN = ";".join(f"S{i}" for i in range(70))


def zeile(umsatz, sh, konto, gegen, datum, text="Buchung", bu=""):
    f = [""] * 70
    f[0], f[1], f[2] = umsatz, sh, "EUR"
    f[6], f[7], f[8] = konto, gegen, bu
    f[9], f[13] = datum, text
    return ";".join(f)


def stapel(*zeilen) -> bytes:
    return "\r\n".join([KOPF, SPALTEN, *zeilen]).encode("cp1252")


# ————— Der Kopf sagt, worum es geht —————

def test_der_kopf_nennt_zeitraum_und_jahr():
    k = hi.kopf_lesen(KOPF)
    assert k["jahr"] == 2025
    assert k["von"] == "20250101" and k["bis"] == "20251231"
    assert k["bezeichnung"] == "Buchungsstapel"


def test_eine_fremde_datei_wird_freundlich_abgewiesen():
    with pytest.raises(hi.HistorieFehler) as e:
        hi.stapel_lesen(b"Konto;Bezeichnung\n4400;Erloese\n")
    assert "EXTF" in str(e.value)
    # Kein Fachchinesisch, ein Weg nach vorn.
    assert "Buchungsstapel exportieren" in str(e.value)


# ————— Die Buchungen —————

def test_erloese_und_kosten_landen_auf_der_richtigen_seite():
    d = hi.stapel_lesen(stapel(
        zeile("1190,00", "H", "4400", "1600", "1503", "Tageslosung"),
        zeile("238,00", "S", "5400", "1800", "2003", "Wella"),
    ))
    m = d["monate"]["2025-03"]
    assert m["erloese"] == 1190.0
    assert m["kosten"] == 238.0
    assert m["ergebnis"] == 952.0
    assert m["buchungen"] == 2


def test_eine_gutschrift_mindert_die_kosten():
    """Im Haben gebuchter Aufwand ist eine Erstattung."""
    d = hi.stapel_lesen(stapel(
        zeile("238,00", "S", "5400", "1800", "0505"),   # 5. Mai
        zeile("119,00", "H", "5400", "1800", "1010"),   # 10. Oktober
    ))
    assert d["monate"]["2025-05"]["kosten"] == 238.0
    assert d["monate"]["2025-10"]["kosten"] == -119.0


def test_bestandskonten_zaehlen_weder_noch():
    """Geld zwischen Kasse und Bank ist kein Umsatz und keine Ausgabe."""
    d = hi.stapel_lesen(stapel(
        zeile("500,00", "S", "1800", "1600", "1503", "Einzahlung"),
        zeile("1190,00", "H", "4400", "1600", "1503"),
    ))
    m = d["monate"]["2025-03"]
    assert m["erloese"] == 1190.0 and m["kosten"] == 0.0
    assert m["buchungen"] == 2          # gezählt wird sie trotzdem


def test_der_kontenrahmen_entscheidet_ueber_die_seite():
    """In SKR03 sind 8xxx die Erlöse, in SKR04 die 4xxx."""
    s = stapel(zeile("1190,00", "H", "8400", "1600", "1503"))
    assert hi.stapel_lesen(s, "SKR03")["monate"]["2025-03"]["erloese"] == 1190.0
    # Unter SKR04 ist 8400 kein Erlöskonto — dann steht dort nichts.
    assert hi.stapel_lesen(s, "SKR04")["monate"]["2025-03"]["erloese"] == 0.0


def test_unlesbare_zeilen_werden_gezaehlt_nicht_verschwiegen():
    d = hi.stapel_lesen(stapel(
        zeile("1190,00", "H", "4400", "1600", "1503"),
        zeile("", "S", "5400", "1800", "2003"),          # ohne Betrag
        zeile("50,00", "S", "", "1800", "2003"),          # ohne Konto
    ))
    assert d["buchungen"] == 1
    assert d["uebersprungen"] == 2


def test_ohne_lesbare_buchung_sagt_babu_was_fehlt():
    with pytest.raises(hi.HistorieFehler) as e:
        hi.stapel_lesen(stapel(zeile("", "S", "", "", "")))
    assert "keine lesbaren Buchungen" in str(e.value)


# ————— Die Gegenprobe: babus eigener Stapel muss lesbar sein —————

def test_babu_liest_seinen_eigenen_stapel_wieder():
    import extf
    review = {
        "datei": "docs/2026-02/x.jpg",
        "felder": {"lieferant": "Wella", "datum": "14.02.2026",
                   "netto": 100.0, "ust": 19.0, "brutto": 119.0,
                   "ust_satz": 19, "beleg_nr": "R-1"},
        "einschaetzung": {"konto_skr04": "5400", "steuerschluessel": "9"},
    }
    text = extf.stapel([review], "2026-02")
    d = hi.stapel_lesen(extf.als_bytes(text))
    assert d["kopf"]["jahr"] == 2026
    m = d["monate"]["2026-02"]
    assert m["kosten"] == 119.0, m
    assert m["buchungen"] >= 1


# ————— Mehrere Stapel, Jahre, Vergleich —————

def test_derselbe_monat_wird_ersetzt_nicht_addiert():
    """Eine korrigierte Fassung darf nicht doppelt zählen."""
    erst = hi.stapel_lesen(stapel(zeile("1000,00", "H", "4400", "1600", "1503")))
    zweit = hi.stapel_lesen(stapel(zeile("1200,00", "H", "4400", "1600", "1503")))
    z = hi.zusammenfuehren(hi.zusammenfuehren(None, erst), zweit)
    assert z["monate"]["2025-03"]["erloese"] == 1200.0
    assert len(z["quellen"]) == 2


def test_die_jahresuebersicht_sagt_wo_monate_fehlen():
    d = hi.stapel_lesen(stapel(
        zeile("1000,00", "H", "4400", "1600", "1503"),
        zeile("1500,00", "H", "4400", "1600", "1504"),
    ))
    j = hi.jahresuebersicht(hi.zusammenfuehren(None, d))
    assert j[0]["jahr"] == "2025"
    assert j[0]["erloese"] == 2500.0
    assert j[0]["monate"] == 2
    assert j[0]["vollstaendig"] is False


def test_der_vergleich_trifft_denselben_monat():
    d = hi.stapel_lesen(stapel(zeile("1000,00", "H", "4400", "1600", "1502")))
    h = hi.zusammenfuehren(None, d)
    assert hi.vorjahresmonat(h, "2026-02")["erloese"] == 1000.0
    assert hi.vorjahresmonat(h, "2026-03") is None
    assert hi.vorjahresmonat(h, "unsinn") is None


def test_die_auswertung_vergleicht_monat_mit_monat():
    import monatsabschluss as ma
    erloese = ma.erloese_monat([{"einnahmenBar": 1190.0}])
    echt = ma.bwa("2026-02", erloese, [], vorjahr={"umsatz": 60000.0,
                                                   "monat_umsatz": 1200.0})
    assert echt["vorjahr_monat"] == 1200.0
    assert echt["vorjahr_quelle"] == "monat"
    # Ohne Stapel bleibt das Zwölftel — aber es sagt, dass es geschätzt ist.
    geschaetzt = ma.bwa("2026-02", erloese, [], vorjahr={"umsatz": 60000.0})
    assert geschaetzt["vorjahr_monat"] == 5000.0
    assert geschaetzt["vorjahr_quelle"] == "jahresschnitt"


# ————— Die Strecke über den Server —————

@pytest.fixture()
def historiewelt(welt, monkeypatch):
    bw, bare = welt
    monkeypatch.setattr(bw, "rolle", lambda un: "inhaberin")
    monkeypatch.setattr(bw, "kontenrahmen_von", lambda un: "SKR04")
    from fastapi.testclient import TestClient
    return bw, bare, TestClient(bw.app, base_url="https://testserver")


def test_hochladen_legt_stapel_und_zahlen_ab(historiewelt):
    _, bare, c = historiewelt
    daten = stapel(zeile("1190,00", "H", "4400", "1600", "1503", "Losung"),
                   zeile("238,00", "S", "5400", "1800", "2003", "Wella"))
    r = c.post("/api/historie",
               files={"file": ("EXTF_2025.csv", daten, "text/csv")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["gelesen"] == 2 and d["monate"] == ["2025-03"]
    assert d["jahre"][0]["erloese"] == 1190.0

    dateien = _im_stand(bare)
    assert "historie/buchungen.json" in dateien
    # Die Originaldatei bleibt liegen — nachrechenbar muss es sein.
    assert any(p.startswith("historie/2025/") and p.endswith(".csv")
               for p in dateien), dateien


def test_eine_falsche_datei_kommt_nicht_in_die_box(historiewelt):
    _, bare, c = historiewelt
    r = c.post("/api/historie",
               files={"file": ("konten.csv", b"Konto;Name\n4400;Erloese\n",
                               "text/csv")})
    assert r.status_code == 400
    assert "EXTF" in r.json()["fehler"]
    assert "historie/buchungen.json" not in _im_stand(bare)


def test_zweiter_stapel_ergaenzt_den_ersten(historiewelt):
    bw, bare, c = historiewelt
    for datum, betrag in (("1503", "1000,00"), ("1508", "2000,00")):
        r = c.post("/api/historie", files={"file": (
            f"EXTF_{datum}.csv",
            stapel(zeile(betrag, "H", "4400", "1600", datum)), "text/csv")})
        assert r.status_code == 200, r.text
    d = c.get("/api/historie").json()
    assert d["monate_gesamt"] == 2
    assert d["jahre"][0]["erloese"] == 3000.0
    assert len(d["quellen"]) == 2


def test_die_uebersicht_sagt_dass_es_kein_beleg_ist(historiewelt):
    _, _, c = historiewelt
    d = c.get("/api/historie").json()
    assert "keine Belege" in d["hinweis"]
    assert "kein Siegel" in d["hinweis"]
