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


def test_ein_utf8_bom_stoert_den_kopf_nicht():
    """Echte DATEV-Exporte kommen als UTF-8 mit Byte-Order-Mark an —
    der darf nicht am „EXTF" kleben und die Datei zum Fremdling machen."""
    roh = "\r\n".join([KOPF, SPALTEN,
                       zeile("1190,00", "H", "4400", "1600", "1503")])
    d = hi.stapel_lesen(b"\xef\xbb\xbf" + roh.encode("utf-8"))
    assert d["monate"]["2025-03"]["erloese"] == 1190.0


def test_erloese_im_gegenkonto_zaehlen_auch():
    """Ninas Altsystem bucht Kasse AN Erlös — das Erlöskonto steht im
    Gegenkonto. Ohne diese Seite käme jeder Monat mit 0 € Umsatz an."""
    d = hi.stapel_lesen(stapel(
        zeile("49,00", "S", "1461", "4400", "0207", "Dienstleistungen"),
        zeile("12,50", "H", "1461", "4400", "0207", "Stornierung"),
        zeile("50,00", "S", "1800", "5400", "0208", "Erstattung Wella"),
    ))
    assert d["monate"]["2025-07"]["erloese"] == 36.5
    # Aufwand im Gegenkonto, Bank im Soll: eine Erstattung mindert die Kosten.
    assert d["monate"]["2025-08"]["kosten"] == -50.0


def test_umbuchung_innerhalb_der_erloese_aendert_nichts():
    d = hi.stapel_lesen(stapel(
        zeile("100,00", "S", "4400", "4410", "1503", "Umgliederung"),
    ))
    assert d["monate"]["2025-03"]["erloese"] == 0.0


def test_doppelte_zeilenumbrueche_zaehlen_nicht_als_uebersprungen():
    """Manche Exporte enden jede Zeile mit \\r\\r\\n — dann steht die
    Spaltenzeile eine Zeile tiefer und darf nicht als unlesbare Buchung
    gemeldet werden. „1 übersprungen" ohne Grund verunsichert nur."""
    roh = "\r\r\n".join([KOPF, SPALTEN,
                         zeile("1190,00", "H", "4400", "1600", "1503")])
    d = hi.stapel_lesen(roh.encode("cp1252"))
    assert d["monate"]["2025-03"]["erloese"] == 1190.0
    assert d["uebersprungen"] == 0


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


# ————— Steuerschlüssel auflösen (seit 02.09.2026) —————

def test_der_schluessel_macht_aus_brutto_netto():
    d = hi.stapel_lesen(stapel(zeile("238,00", "S", "6310", "1800", "0103",
                                     "Miete", bu="9")))
    m = d["monate"]["2025-03"]
    assert (m["kosten"], m["kosten_netto"], m["vorsteuer"]) == (238.0, 200.0, 38.0)
    assert m["ungeklaert"] == 0
    assert m["konten"][0]["netto"] == 200.0


def test_ein_automatikkonto_rechnet_ohne_schluessel():
    """4400 ist AM 19 % im SKR04 — DATEV rechnet die Steuer aus dem Konto,
    also tut babu es beim Lesen genauso."""
    d = hi.stapel_lesen(stapel(zeile("1190,00", "H", "4400", "1600", "1503")))
    m = d["monate"]["2025-03"]
    assert (m["erloese"], m["erloese_netto"], m["umsatzsteuer"]) == (1190.0, 1000.0, 190.0)


def test_die_automatik_gilt_auch_vom_gegenkonto_aus():
    """Kasse an Erlöse: das Automatikkonto steht im Gegenkonto."""
    d = hi.stapel_lesen(stapel(zeile("107,00", "S", "1600", "4300", "1503")))
    m = d["monate"]["2025-03"]
    # Kasse im Soll, Erlöse im Haben: der Erlös steht im Gegenkonto und
    # zählt trotzdem — mit dem Satz des Automatikkontos.
    assert (m["erloese"], m["erloese_netto"], m["umsatzsteuer"]) == (107.0, 100.0, 7.0)
    assert any(k["konto"] == "4300" and k["netto"] == 100.0 for k in m["konten"])


def test_ohne_schluessel_und_ohne_automatik_ist_es_steuerfrei():
    d = hi.stapel_lesen(stapel(zeile("500,00", "S", "6310", "1800", "0103", "Miete")))
    m = d["monate"]["2025-03"]
    assert m["kosten_netto"] == 500.0 and m["vorsteuer"] == 0.0
    assert m["ungeklaert"] == 0


def test_ein_unbekannter_schluessel_bleibt_brutto_und_wird_gezaehlt():
    """Geraten wird nicht: Betrag bleibt stehen, der Zähler sagt es."""
    d = hi.stapel_lesen(stapel(zeile("238,00", "S", "6310", "1800", "0103",
                                     bu="77")))
    m = d["monate"]["2025-03"]
    assert m["kosten_netto"] == 238.0 and m["ungeklaert"] == 1


def test_die_neue_nummer_401_ist_die_alte_9():
    """DATEV Dok.-Nr. 0907048: 9 = Vorsteuer (voller Satz) = 401."""
    assert hi.steuersatz("401", "6310", "1800", "SKR04") == (19, "schluessel")
    assert hi.steuersatz("9", "6310", "1800", "SKR04") == (19, "schluessel")


def test_jeder_schluessel_den_babu_schreibt_wird_gelesen():
    import extf
    for satz, bu in extf.BU_SCHLUESSEL.items():
        if bu:
            assert hi.SCHLUESSEL_SATZ[bu] == satz, (satz, bu)


def test_babu_liest_seine_erloesseite_netto_zurueck():
    """Roundtrip in babu: Stapel mit Kassenblatt raus, netto wieder rein."""
    import extf
    review = {
        "datei": "docs/2026-02/x.jpg",
        "felder": {"lieferant": "Wella", "datum": "14.02.2026",
                   "netto": 100.0, "ust": 19.0, "brutto": 119.0,
                   "ust_satz": 19, "beleg_nr": "R-1"},
        "einschaetzung": {"konto_skr04": "5400", "steuerschluessel": "9"},
    }
    blatt = {"datum": "2026-02-14", "einnahmenBar": 100.0, "ecZahlungen": 50.0,
             "umsatz7": 20.0}
    text = extf.stapel([review], "2026-02", kassenblaetter=[blatt])
    m = hi.stapel_lesen(extf.als_bytes(text))["monate"]["2026-02"]
    assert m["erloese"] == 150.0
    # Gerundet je Buchung, wie DATEV — nicht die Summe am Ende.
    assert m["erloese_netto"] == round(round(130 / 1.19, 2) + round(20 / 1.07, 2), 2)
    assert (m["kosten"], m["kosten_netto"]) == (119.0, 100.0)
    assert m["ungeklaert"] == 0


def test_die_jahresuebersicht_kennt_netto_und_alte_staende():
    alt = {"monate": {"2025-01": {"erloese": 119.0, "kosten": 0.0, "buchungen": 1},
                      "2025-02": {"erloese": 119.0, "erloese_netto": 100.0,
                                  "kosten": 0.0, "kosten_netto": 0.0,
                                  "ungeklaert": 2, "buchungen": 1}}}
    j = hi.jahresuebersicht(alt)[0]
    assert j["erloese"] == 238.0
    assert j["erloese_netto"] == 219.0          # alter Monat bleibt brutto
    assert j["ungeklaert"] == 2


def test_der_export_traegt_die_kassentage_des_monats(historiewelt, monkeypatch):
    """Über den Server: ein Kassenblatt im Monat wird zur Erlösbuchung.

    Das Festschreibungs-Kennzeichen hing bis 03.09.2026 am freigegebenen
    Monatsabschluss — damit gab sich jede Vorschau als endgültig aus. Es
    kommt jetzt einzig vom Übergeben; dieser Test prüft entsprechend, dass
    die Vorschau es NICHT trägt, auch wenn die Zahlen freigegeben sind.
    """
    bw, _, c = historiewelt
    idx = {"belege": {}, "reviews": {}, "rechnungen": {},
           "kassenblaetter": {"2026-03-05": {"datum": "2026-03-05",
                                              "einnahmenBar": 200.0,
                                              "ecZahlungen": 100.0}}}
    monkeypatch.setattr(bw, "index_aktuell", lambda: idx)
    monkeypatch.setattr(bw, "darf_verwalten", lambda un: True)
    monkeypatch.setattr(bw, "_monat_festgeschrieben", lambda monat: False)
    r = c.get("/api/export/2026-03.csv")
    assert r.status_code == 200, r.text
    zeilen = r.content.decode("cp1252").rstrip("\r\n").split("\r\n")
    assert zeilen[0].split(";")[20] == "0"                 # nicht festgeschrieben
    assert zeilen[2].startswith('300,00;S;EUR;;;;1600;4400;;0503;"KB20260305"')
    assert zeilen[3].startswith("100,00;S;EUR;;;;1460;1600;;0503")
    # Die Freigabe der Zahlen im Salon ändert daran nichts mehr.
    monkeypatch.setattr(bw, "_monat_festgeschrieben", lambda monat: True)
    r = c.get("/api/export/2026-03.csv")
    assert r.content.decode("cp1252").split(";")[20] == "0"


def test_ein_bestandskonto_traegt_keine_steuer():
    """„Kasse an Erlöse": der Satz gehört den Erlösen, nicht der Kasse."""
    d = hi.stapel_lesen(stapel(zeile("119,00", "S", "1600", "4400", "1503")))
    konten = {k["konto"]: k for k in d["monate"]["2025-03"]["konten"]}
    assert konten["4400"]["netto"] == 100.0
    assert konten["1600"]["netto"] == konten["1600"]["betrag"] == 119.0


def test_ein_alter_stand_ohne_netto_wird_aus_den_originalen_nachgelesen(historiewelt, monkeypatch):
    """Vor dem 02.09.2026 lagen nur Bruttosummen in buchungen.json — die
    Originaldatei liegt daneben, also wird sie neu gelesen."""
    import json
    bw, _, c = historiewelt
    original = stapel(zeile("1190,00", "H", "4400", "1600", "1503", "Losung"))
    alt = {"monate": {"2025-03": {"monat": "2025-03", "erloese": 1190.0,
                                  "kosten": 0.0, "buchungen": 1, "konten": []}},
           "quellen": [], "rahmen": "SKR04"}
    dateien = {"historie/buchungen.json": json.dumps(alt).encode(),
               "historie/2025/stapel.csv": original}
    monkeypatch.setattr(bw, "git_show", lambda pfad: dateien.get(pfad))
    monkeypatch.setattr(bw, "_git", lambda args, timeout=30:
                        "\n".join(dateien) + "\n")
    h = bw.historie_lesen()
    assert h["monate"]["2025-03"]["erloese_netto"] == 1000.0
    r = c.get("/api/historie")
    assert r.json()["jahre"][0]["erloese_netto"] == 1000.0


def test_ein_neuer_stand_wird_nicht_nachgelesen(historiewelt, monkeypatch):
    import json
    bw, _, _ = historiewelt
    neu = {"monate": {"2025-03": {"monat": "2025-03", "erloese": 1190.0,
                                  "erloese_netto": 1000.0, "kosten": 0.0,
                                  "buchungen": 1, "konten": []}},
           "quellen": [], "rahmen": "SKR04"}
    monkeypatch.setattr(bw, "git_show", lambda pfad: json.dumps(neu).encode()
                        if pfad.endswith("buchungen.json") else None)
    monkeypatch.setattr(bw, "_git", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("darf nicht listen")))
    assert bw.historie_lesen() == neu
