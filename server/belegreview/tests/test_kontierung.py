"""Die Kaskade: Verwendung → Kategorie → Konto.

Geprüft wird das, was Nina benannt hat, und zwar an den Stellen, an denen es
heute schiefgeht: der Betrag zählt JE STÜCK, Reparatur wird nie Anlage,
Geldbewegung ist kein Umsatz, und die beiden Kontenrahmen kommen sich nicht
in die Quere.
"""
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kontierung import (  # noqa: E402
    GWG_GRENZE, KATEGORIEN, RAHMEN, SOFORT_GRENZE, entscheiden,
    gehoert_zum_rahmen, konto, ungepruefte_konten,
)


# ————— Die Grenzen, auf den Cent —————

@pytest.mark.parametrize("netto, soll", [
    ("0.01", "sonstiges"),
    ("249.99", "sonstiges"),
    ("250.00", "sonstiges"),       # bis einschliesslich 250 sofort Aufwand
    ("250.01", "gwg"),
    ("799.99", "gwg"),
    ("800.00", "gwg"),             # bis einschliesslich 800 noch GWG
    ("800.01", "anlagevermoegen"),
    ("12000.00", "anlagevermoegen"),
])
def test_der_betrag_entscheidet_und_zwar_genau(netto, soll):
    e = entscheiden(verwendung="betriebsausstattung", netto_je_stueck=netto,
                    selbstaendig_nutzbar=True)
    assert e.kategorie == soll, e.begruendung
    assert not e.offen


def test_die_grenzen_sind_die_des_gesetzes():
    assert SOFORT_GRENZE == Decimal("250.00")
    assert GWG_GRENZE == Decimal("800.00")


def test_deutsches_komma_wird_verstanden():
    """Aus der Lesung kommt „300,00", nicht „300.00"."""
    e = entscheiden(verwendung="betriebsausstattung", netto_je_stueck="300,00",
                    selbstaendig_nutzbar=True)
    assert e.kategorie == "gwg"


def test_vier_stuehle_auf_einer_rechnung_sind_vier_gwg():
    """Ninas Beispiel. Maßgeblich ist das Stück, nicht die Rechnungssumme."""
    je_stueck = entscheiden(verwendung="betriebsausstattung",
                            netto_je_stueck="300.00", selbstaendig_nutzbar=True)
    summe = entscheiden(verwendung="betriebsausstattung",
                        netto_je_stueck="1200.00", selbstaendig_nutzbar=True)
    assert je_stueck.kategorie == "gwg"
    assert summe.kategorie == "anlagevermoegen"   # so sähe der Fehler aus


# ————— Wo gefragt statt geraten wird —————

def test_ohne_verwendungszweck_wird_gefragt():
    e = entscheiden(verwendung=None)
    assert e.offen and e.kategorie is None
    assert "Wofür" in e.rueckfrage


def test_ohne_betrag_wird_bei_anschaffungen_gefragt():
    e = entscheiden(verwendung="betriebsausstattung")
    assert e.offen and "netto" in e.rueckfrage


def test_ueber_250_wird_nach_selbstaendiger_nutzbarkeit_gefragt():
    e = entscheiden(verwendung="betriebsausstattung", netto_je_stueck="400.00")
    assert e.offen and "allein" in e.rueckfrage


def test_unter_250_muss_nicht_gefragt_werden():
    """Unter der Grenze ist die Antwort für die Buchung ohne Folge."""
    e = entscheiden(verwendung="betriebsausstattung", netto_je_stueck="80.00")
    assert not e.offen and e.kategorie == "sonstiges"


def test_zubehoer_gehoert_zum_hauptgegenstand():
    e = entscheiden(verwendung="betriebsausstattung", netto_je_stueck="900.00",
                    selbstaendig_nutzbar=False)
    assert e.offen and "Gerät" in e.rueckfrage
    assert e.kategorie is None


# ————— Die drei Fälle, an denen heute Geld verloren geht —————

def test_reparatur_wird_niemals_anlage():
    """Auch eine teure Reparatur bleibt Aufwand."""
    e = entscheiden(verwendung="reparatur", netto_je_stueck="5000.00")
    assert e.kategorie == "instandhaltung"
    assert "nie Anlage" in e.begruendung


def test_geld_zwischen_eigenen_konten_ist_kein_umsatz():
    e = entscheiden(verwendung="geldbewegung")
    assert e.kategorie == "geldtransit"
    assert "kein Umsatz" in e.begruendung
    assert konto("geldtransit", "SKR03") == "1360"
    assert konto("geldtransit", "SKR04") == "1460"


def test_privat_ist_keine_betriebsausgabe():
    e = entscheiden(verwendung="privat")
    assert e.kategorie == "privat"
    assert "Privatentnahme" in KATEGORIEN["privat"].name


# ————— SKR03 und SKR04 kommen sich nicht in die Quere —————

def test_derselbe_fall_liefert_je_Rahmen_ein_anderes_konto():
    a = entscheiden(verwendung="weiterverkauf", rahmen="SKR03")
    b = entscheiden(verwendung="weiterverkauf", rahmen="SKR04")
    assert (a.konto, b.konto) == ("3400", "5400")
    assert a.kategorie == b.kategorie      # die Kategorie ist dieselbe …
    assert a.konto != b.konto              # … das Konto nie


def test_kein_konto_gehoert_zu_beiden_rahmen():
    """Der Mischungs-Melder: hätte ein Konto in beiden Listen dieselbe
    Nummer, könnte man die Vermischung nicht mehr erkennen."""
    skr03 = {k.skr03 for k in KATEGORIEN.values() if k.skr03}
    skr04 = {k.skr04 for k in KATEGORIEN.values() if k.skr04}
    assert not (skr03 & skr04), sorted(skr03 & skr04)


def test_gehoert_zum_rahmen_erkennt_den_fremden():
    assert gehoert_zum_rahmen("5400", "SKR04")
    assert not gehoert_zum_rahmen("5400", "SKR03")   # das ist SKR04-Ware
    assert gehoert_zum_rahmen("3400", "SKR03")
    assert not gehoert_zum_rahmen("9999", "SKR04")


@pytest.mark.parametrize("rahmen", RAHMEN)
def test_jede_kategorie_kennt_beide_rahmen_oder_sagt_es(rahmen):
    """Kein stilles None: fehlt ein Konto, muss die Kategorie es zugeben."""
    for k in KATEGORIEN.values():
        if k.konto(rahmen) is None:
            assert k.hinweis, f"{k.code} hat kein {rahmen}-Konto und keinen Hinweis"


def test_ein_unbekannter_rahmen_faellt_sofort_auf():
    with pytest.raises(ValueError):
        entscheiden(verwendung="weiterverkauf", rahmen="SKR49")
    with pytest.raises(ValueError):
        konto("wareneinkauf", "SKR49")


def test_ein_unbekannter_verwendungszweck_faellt_sofort_auf():
    with pytest.raises(ValueError):
        entscheiden(verwendung="irgendwas")


# ————— Ehrlichkeit über den eigenen Stand —————

def test_ungepruefte_konten_werden_benannt_nicht_versteckt():
    offen = {k.code for k in ungepruefte_konten()}
    # Die kennen wir und geben es zu — sie dürfen nicht stillschweigend
    # als bestätigt durchgehen.
    assert "anlagevermoegen" in offen
    assert "gutschein" in offen
    for k in ungepruefte_konten():
        assert k.hinweis, f"{k.code} ist ungeprüft, sagt aber nicht warum"


def test_ein_fehlendes_konto_wird_zur_rueckfrage_nicht_zur_null():
    """`it` hat kein SKR03-Gegenstück — das darf nicht als Buchung durchgehen."""
    e = entscheiden(verwendung="weiterverkauf", rahmen="SKR03")
    assert not e.offen                       # das hier geht
    from kontierung import _fertig           # noqa: PLC0415
    f = _fertig("it", "SKR03", "Test")
    assert f.offen and f.konto is None and "SKR03" in f.rueckfrage


# ————— Die Kategorien müssen in der Auswertung ankommen —————
#
# Anlass: „aufmerksamkeit" stand auf 4605/6605 (Streuartikel) statt auf
# 4653/6643. Die Korrektur allein hätte es schlimmer gemacht — 6643 fehlte
# in den KOSTENGRUPPEN, jeder Kaffeebeleg wäre auf „Sonstiges" gefallen,
# also genau dorthin, wo Nina ihn nicht mehr sehen will (P2-22). Die alten
# Tests haben das nicht bemerkt, weil sie den Wert aus der Kategorie-Zeile
# nur gespiegelt haben. Diese drei prüfen die Aussage statt der Zahl.

def test_jedes_konto_taucht_in_der_auswertung_auf():
    """Kein Konto darf stillschweigend ins Auffangkonto fallen."""
    import monatsabschluss as ma                       # noqa: PLC0415
    zuordnung = {k: s for s, _, konten in ma.KOSTENGRUPPEN for k in konten}
    heimatlos = []
    for code, kat in KATEGORIEN.items():
        skr04 = kat.konto("SKR04")
        if not skr04 or skr04 in ma.NEUTRALE_KONTEN:
            continue                                   # kein Aufwand
        if skr04 not in zuordnung:
            heimatlos.append((code, skr04))
    assert not heimatlos, (
        "Diese Kategorien fallen in der BWA auf „Sonstiges“, weil ihr Konto "
        f"in keiner KOSTENGRUPPE steht: {heimatlos}")


def test_die_vier_zuwendungsarten_sind_auseinandergehalten():
    """Bewirtung, Aufmerksamkeit, Geschenk und Werbung sind vier Sachen mit
    vier Rechtsfolgen — sie dürfen sich kein Konto teilen."""
    konten = {code: KATEGORIEN[code].konto("SKR04")
              for code in ("bewirtung", "aufmerksamkeit", "geschenk", "werbung")}
    assert len(set(konten.values())) == 4, konten
    # 6605 ist das Streuartikelkonto — Werbekleinzeug, das die Kundin
    # mitnimmt. Kaffee im Salon wird dort verzehrt und gehört nicht dorthin.
    assert konten["aufmerksamkeit"] != "6605"


def test_kaffee_fuer_kundinnen_landet_nicht_unter_sonstiges():
    """Der Fall aus Ninas Anmerkung, einmal ganz durch die Auswertung."""
    import monatsabschluss as ma                       # noqa: PLC0415
    beleg = {"lieferant": "Kaffeeröster", "brutto": 23.80, "netto": 20.0,
             "ust": 3.80, "konto_skr04": KATEGORIEN["aufmerksamkeit"].konto("SKR04")}
    d = ma.bwa("2026-08", ma.erloese_monat([]), [beleg])
    treffer = [g for g in d["gruppen"] if g["anzahl"]]
    assert [g["schluessel"] for g in treffer] == ["werbung"], treffer
    assert treffer[0]["netto"] == pytest.approx(20.0)
