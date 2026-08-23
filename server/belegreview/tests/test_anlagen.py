"""Das Anlagenverzeichnis: was über 800 € netto gekauft wurde, und was davon
noch übrig ist.

Bis 23.08.2026 entschied `kontierung.py` richtig, dass ein Gerät über 800 €
Anlagevermögen ist — und danach verschwand es. Keine Liste, keine
Nutzungsdauer, keine Abschreibung. Bei einer Betriebsprüfung ist das
Anlagenverzeichnis das Erste, wonach gefragt wird.

Geprüft wird hier dreierlei:

1. **Die Nutzungsdauer wird nicht geraten.** Wo babu den amtlichen Wert kennt,
   steht er samt Quelle da; wo nicht, kommt eine Rückfrage. Ein falscher Wert
   ist schlimmer als ein fehlender — der fehlende fällt auf.
2. **Die Abschreibung rechnet auf den Cent**, linear, im Anschaffungsjahr
   monatsgenau (§ 7 Abs. 1 EStG).
3. **Nichts geht verloren.** Die Summe aller Jahresbeträge ist exakt der
   Anschaffungswert, und der Restbuchwert endet auf null.
"""
import sys
from decimal import Decimal
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import anlagen as an  # noqa: E402


def _gut(wert="2400.00", angeschafft="2026-01-15", jahre=4, **rest):
    return an.Anlagegut(bezeichnung="Prüfstück", angeschafft=angeschafft,
                        wert_cent=an.cent(wert), nutzungsdauer=jahre, **rest)


# ————— Die AfA-Tabelle: bestätigt oder gefragt, nichts dazwischen —————

def test_was_babu_sicher_weiss_traegt_seine_quelle():
    for code in ("computer", "bueromoebel", "ladeneinbauten", "pkw"):
        n = an.NUTZUNGSDAUER[code]
        assert n.geprueft and n.jahre and n.quelle, code


def test_computer_und_tablet_werden_in_einem_jahr_abgeschrieben():
    """BMF-Schreiben vom 22.02.2022 — der bekannteste Sonderfall."""
    n = an.NUTZUNGSDAUER["computer"]
    assert n.jahre == 1
    assert "2022" in n.quelle


def test_was_babu_nicht_sicher_weiss_gibt_keine_zahl_aus():
    """Die Friseur-Branchentabelle kennt babu nicht — also fragt es.

    Eine erfundene Nutzungsdauer verschiebt Gewinn über Jahre; sie fällt
    niemandem auf, bis die Prüfung kommt."""
    for code in ("frisierstuhl", "trockenhaube", "waschanlage",
                 "ladeneinrichtung", "klimageraet", "sonstiges"):
        n = an.NUTZUNGSDAUER[code]
        assert n.jahre is None, code
        assert not n.geprueft and n.hinweis, code


def test_jede_art_hat_einen_namen_in_ninas_sprache():
    for code, n in an.NUTZUNGSDAUER.items():
        assert n.name and not n.name.isupper(), code


def test_ohne_nutzungsdauer_kommt_eine_rueckfrage_kein_plan():
    g = _gut(jahre=None)
    assert g.rueckfrage and "Jahre" in g.rueckfrage
    assert an.plan(g) == []


def test_eine_bekannte_art_traegt_ihre_nutzungsdauer_bei():
    g = an.Anlagegut(bezeichnung="iPad Kasse", angeschafft="2026-03-01",
                     wert_cent=an.cent("1200.00"), art="computer")
    assert g.nutzungsdauer == 1
    assert g.rueckfrage is None


def test_eine_unbekannte_art_fuehrt_zur_frage_nicht_zur_zahl():
    g = an.Anlagegut(bezeichnung="Frisierstuhl", angeschafft="2026-03-01",
                     wert_cent=an.cent("1200.00"), art="frisierstuhl")
    assert g.nutzungsdauer is None and g.rueckfrage


def test_eine_eingetragene_nutzungsdauer_schlaegt_die_tabelle():
    """Sagt die Steuerberatung 7 Jahre, gilt 7 — nicht babus Vorschlag."""
    g = an.Anlagegut(bezeichnung="iPad", angeschafft="2026-03-01",
                     wert_cent=an.cent("1200.00"), art="computer",
                     nutzungsdauer=3)
    assert g.nutzungsdauer == 3


# ————— Lineare Abschreibung, monatsgenau —————

def test_im_januar_gekauft_heisst_zwoelf_zwoelftel():
    g = _gut(wert="2400.00", angeschafft="2026-01-15", jahre=4)
    zeilen = an.plan(g)
    assert [z.jahr for z in zeilen] == [2026, 2027, 2028, 2029]
    assert all(z.afa_cent == 60000 for z in zeilen)
    assert zeilen[-1].restbuchwert_cent == 0


def test_im_oktober_gekauft_heisst_drei_zwoelftel():
    """§ 7 Abs. 1 EStG: zeitanteilig ab dem Monat der Anschaffung —
    der Anschaffungsmonat zählt ganz mit."""
    g = _gut(wert="2400.00", angeschafft="2026-10-20", jahre=4)
    zeilen = an.plan(g)
    assert zeilen[0].jahr == 2026
    assert zeilen[0].afa_cent == 15000            # 600 € × 3/12
    assert zeilen[1].afa_cent == 60000
    assert zeilen[-1].jahr == 2030                # der Rest läuft ins 5. Jahr
    assert zeilen[-1].afa_cent == 45000           # 600 € × 9/12


def test_der_dezember_bringt_noch_ein_zwoelftel():
    g = _gut(wert="1200.00", angeschafft="2026-12-31", jahre=1)
    zeilen = an.plan(g)
    assert zeilen[0].afa_cent == 10000            # ein Monat von zwölf
    assert zeilen[1].afa_cent == 110000           # die restlichen elf


def test_kein_cent_geht_verloren():
    """Rundung darf den Anschaffungswert nicht verändern — sonst stimmt der
    Restbuchwert am Ende nicht, und das fällt in der Bilanz auf."""
    for wert, jahre, monat in (("1000.00", 3, 5), ("999.99", 7, 11),
                               ("12345.67", 13, 2), ("801.00", 6, 8),
                               ("2500.00", 1, 6)):
        g = _gut(wert=wert, angeschafft=f"2026-{monat:02d}-01", jahre=jahre)
        zeilen = an.plan(g)
        assert sum(z.afa_cent for z in zeilen) == an.cent(wert), (wert, jahre)
        assert zeilen[-1].restbuchwert_cent == 0, (wert, jahre)


def test_der_restbuchwert_faellt_monoton():
    g = _gut(wert="5000.00", angeschafft="2026-07-01", jahre=5)
    werte = [z.restbuchwert_cent for z in an.plan(g)]
    assert werte == sorted(werte, reverse=True)
    assert werte[0] < an.cent("5000.00")


def test_die_abschreibung_eines_bestimmten_jahres():
    g = _gut(wert="2400.00", angeschafft="2026-10-01", jahre=4)
    assert an.afa_im_jahr(g, 2026) == 15000
    assert an.afa_im_jahr(g, 2028) == 60000
    assert an.afa_im_jahr(g, 2031) == 0           # längst abgeschrieben
    assert an.afa_im_jahr(g, 2025) == 0           # gab es noch nicht


def test_der_restbuchwert_eines_bestimmten_jahres():
    g = _gut(wert="2400.00", angeschafft="2026-01-01", jahre=4)
    assert an.restbuchwert_cent(g, 2026) == 180000
    assert an.restbuchwert_cent(g, 2029) == 0
    assert an.restbuchwert_cent(g, 2025) == an.cent("2400.00")


def test_geld_bleibt_decimal():
    """Kein float: 0,1 + 0,2 ist in Binär nicht 0,3, und ein Cent Differenz
    im Anlagenverzeichnis ist ein Fehler in der Bilanz."""
    assert isinstance(an.euro(an.cent("801.00")), Decimal)
    assert an.euro(80100) == Decimal("801.00")
    assert an.cent("1.005") == 101              # kaufmännisch, nicht zur Geraden


# ————— Das Verzeichnis —————

def test_das_verzeichnis_summiert_das_jahr():
    gueter = [_gut(wert="2400.00", angeschafft="2026-01-01", jahre=4),
              _gut(wert="1200.00", angeschafft="2026-07-01", jahre=1)]
    v = an.verzeichnis(gueter, 2026)
    assert v["jahr"] == 2026
    assert v["summe"]["anschaffungswert_cent"] == 360000
    assert v["summe"]["afa_cent"] == 60000 + 60000        # 600 + 6/12 von 1200
    assert v["summe"]["restbuchwert_cent"] == 180000 + 60000
    assert len(v["anlagen"]) == 2


def test_ein_gut_ohne_nutzungsdauer_steht_trotzdem_drin_und_faellt_auf():
    """Es verschweigen wäre die alte Lücke — nur eben leiser."""
    v = an.verzeichnis([_gut(jahre=None)], 2026)
    assert len(v["anlagen"]) == 1
    assert v["anlagen"][0]["rueckfrage"]
    assert v["offen"] == 1


def test_ein_gut_aus_einem_spaeteren_jahr_zaehlt_noch_nicht_mit():
    v = an.verzeichnis([_gut(angeschafft="2027-03-01")], 2026)
    assert v["summe"]["anschaffungswert_cent"] == 0
    assert v["anlagen"] == []


def test_ein_abgegangenes_gut_verschwindet_nicht_rueckwirkend():
    """Was 2026 im Betrieb war, steht 2026 im Verzeichnis — auch wenn es
    2027 verkauft wurde. Sonst fehlte es in der Prüfung des Vorjahres."""
    g = _gut(angeschafft="2026-01-01", abgang="2027-06-30")
    assert len(an.verzeichnis([g], 2026)["anlagen"]) == 1
    assert an.verzeichnis([g], 2028)["anlagen"] == []


def test_ein_kaputtes_datum_kippt_das_verzeichnis_nicht():
    g = an.Anlagegut(bezeichnung="Krumm", angeschafft="irgendwann",
                     wert_cent=90000, nutzungsdauer=5)
    assert g.rueckfrage and "Datum" in g.rueckfrage
    assert an.plan(g) == []


def test_die_ausgabe_ist_lesbar_und_vollstaendig():
    """Das Verzeichnis geht in den Jahresabschluss — jede Spalte, die die
    Prüfung erwartet, muss drin sein."""
    v = an.verzeichnis([_gut(wert="2400.00", angeschafft="2026-04-01", jahre=4)],
                       2026)
    zeile = v["anlagen"][0]
    for feld in ("bezeichnung", "angeschafft", "anschaffungswert",
                 "nutzungsdauer", "afa", "restbuchwert"):
        assert feld in zeile, feld
    assert zeile["anschaffungswert"] == "2400.00"
    assert zeile["afa"] == "450.00"               # 600 € × 9/12
    assert zeile["restbuchwert"] == "1950.00"


def test_die_csv_ausgabe_traegt_kopf_und_zeilen():
    text = an.als_csv([_gut(wert="2400.00", angeschafft="2026-04-01", jahre=4)],
                      2026)
    zeilen = text.strip().split("\r\n")
    assert zeilen[0].startswith("Bezeichnung;")
    assert "2400,00" in zeilen[1]                 # deutsche Notation
    assert zeilen[-1].startswith("Summe;")


def test_die_komma_regel_gilt_fuer_zahlen_nicht_fuer_text():
    """„Frisierstuhl Nr. 3" darf nicht zu „Nr, 3" werden, und ein Datum in
    der Quellenangabe bleibt ein Datum."""
    g = an.Anlagegut(bezeichnung="Frisierstuhl Nr. 3", angeschafft="2026-01-01",
                     wert_cent=an.cent("1200.00"), art="computer")
    zeile = an.als_csv([g], 2026).split("\r\n")[1]
    assert "Frisierstuhl Nr. 3" in zeile
    assert "22.02.2022" in zeile                  # die BMF-Quelle
    assert "1200,00" in zeile                     # der Betrag aber schon


def test_ein_semikolon_im_namen_sprengt_die_spalte_nicht():
    g = _gut()
    g.bezeichnung = "Stuhl; Modell A"
    zeile = an.als_csv([g], 2026).split("\r\n")[1]
    assert len(zeile.split(";")) == len(an.CSV_KOPF)


def test_der_name_wird_in_excel_keine_formel():
    """Dieselbe Falle wie beim Buchungsstapel (extf.py): die Datei geht ans
    Steuerbüro und wird dort in Excel geöffnet. Ein Name, der mit `=`
    beginnt, wäre dort eine Formel statt eines Textes."""
    for gefaehrlich in ("=cmd|'/c calc'!A1", "+1+1", "-Stuhl", "@Waschbecken"):
        g = _gut()
        g.bezeichnung = gefaehrlich
        feld = an.als_csv([g], 2026).split("\r\n")[1].split(";")[0]
        assert feld.startswith("'"), feld
        assert gefaehrlich.replace(";", ",") in feld


# ————— Die Grenze aus kontierung.py gilt hier weiter —————

def test_unter_der_800_euro_grenze_gehoert_nichts_ins_verzeichnis():
    """GWG werden im Jahr voll abgesetzt — ein Anlagegut werden sie nicht."""
    with pytest.raises(ValueError):
        an.Anlagegut(bezeichnung="Föhn", angeschafft="2026-01-01",
                     wert_cent=an.cent("300.00"), nutzungsdauer=5)


def test_genau_an_der_grenze_gilt_noch_gwg():
    with pytest.raises(ValueError):
        an.Anlagegut(bezeichnung="Stuhl", angeschafft="2026-01-01",
                     wert_cent=an.cent("800.00"), nutzungsdauer=5)
    an.Anlagegut(bezeichnung="Stuhl", angeschafft="2026-01-01",
                 wert_cent=an.cent("800.01"), nutzungsdauer=5)
