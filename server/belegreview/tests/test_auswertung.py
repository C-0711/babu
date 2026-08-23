"""Der Bericht aus einem Jahresabschluss.

Die Zahlen in diesen Tests stammen aus einem **echten** Abschluss eines
Kosmetikbetriebs für 2024 — ohne Namen, ohne Steuernummer, ohne Anschrift,
denn davon steht nichts im Repository. Was bleibt, sind die Beträge, und
genau die machen die Tests wertvoll: sie tragen die Fälle, die man sich
nicht ausdenkt.

Zwei davon sind hier festgehalten:

* Die Steuerberatung hat in diesem Jahr **94 % des Gewinns** gekostet.
  Das ist der Befund, um den es bei babu geht — er muss zuverlässig
  erscheinen und darf nicht in einer Kennzahlentabelle untergehen.

* EÜR und Umsatzsteuererklärung wichen um zehn Cent voneinander ab, und
  das ist **kein Fehler**: das Formular schneidet die Bemessungsgrundlage
  auf volle Euro ab. Ein naiver Prüfer meldet hier einen Lesefehler. Die
  Gegenprobe muss den Fall kennen und erklären.
"""
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auswertung import (  # noqa: E402
    UEBERNEHMBAR, befunde, bericht, gewinn_gegenprobe, kennzahlen, proben,
    uebernehmbare_felder, ust_gegenprobe,
)


# Der echte Fall, in Zahlen.
JAHR = {
    "jahr": 2024,
    "umsatz": 172807.49,
    "wareneinsatz": 63122.03,
    "personal": 27548.99,        # 22.022,37 + 4.433,51 + 1.093,11
    "raumkosten": 26276.89,      # 10.354,00 + 3.656,85 + 11.898,43 + 367,61
    "steuerberatung": 15518.40,  # 6825 + 6827 + 6830
    "afa": 7777.51,              # 5.497,23 + 2.280,28
    "sonstige_kosten": 16122.19,
    "gewinn": 16441.48,
    "ust_erklaert": 32833.33,
}
VORJAHR = {"umsatz": 124766.07, "gewinn": 3677.90}


# ————— Der Befund, um den es geht —————

def test_die_steuerberatung_wird_ins_verhaeltnis_gesetzt():
    b = befunde(JAHR, VORJAHR)
    treffer = [x for x in b if "Steuerberatung" in x.titel]
    assert treffer, [x.titel for x in b]
    eins = treffer[0]
    assert eins.schwere == "ernst"          # 94 % ist nicht „achtung"
    assert "15.518,40" in eins.text
    assert "16.441,48" in eins.text
    assert "94" in eins.text                # der Anteil steht da
    assert "÷" in eins.rechenweg            # und wie er zustande kommt


def test_der_befund_steht_weit_oben():
    """Wer den Bericht überfliegt, muss ihn sehen — nicht suchen."""
    b = befunde(JAHR, VORJAHR)
    assert "Steuerberatung" in b[0].titel


def test_bei_kleinem_anteil_gibt_es_keinen_befund():
    """Sonst steht bei jedem Betrieb dasselbe da und niemand liest es mehr."""
    mild = dict(JAHR, steuerberatung=1200.00)
    assert not [x for x in befunde(mild) if "Steuerberatung" in x.titel]


def test_steuerberatung_trotz_verlust_ist_ein_eigener_fall():
    verlust = dict(JAHR, gewinn=-4000.00)
    titel = [x.titel for x in befunde(verlust)]
    assert "Steuerberatung trotz Verlust" in titel
    assert any("Verlust" in t for t in titel)


# ————— Die Gegenprobe, die nicht falsch Alarm schlagen darf —————

def test_die_zehn_cent_sind_erklaerbar_und_kein_fehler():
    p = ust_gegenprobe(172807.49, 32833.33)
    assert p.bestanden is True
    assert p.erklaerbar is True
    assert "volle Euro" in p.erklaerung


def test_die_genaue_steuer_geht_ohne_erklaerung_durch():
    p = ust_gegenprobe(172807.49, 32833.42)
    assert p.bestanden and not p.erklaerbar


def test_eine_echte_abweichung_wird_gemeldet():
    p = ust_gegenprobe(172807.49, 31000.00)
    assert p.bestanden is False
    assert "erklärt sich nicht durch Rundung" in p.erklaerung


def test_ohne_zahl_wird_nicht_geprueft_sondern_gesagt():
    p = ust_gegenprobe(172807.49, None)
    assert not p.bestanden and "Nicht prüfbar" in p.erklaerung


def test_die_gewinnprobe_geht_am_echten_fall_auf():
    p = gewinn_gegenprobe(JAHR)
    assert p.bestanden, p.erklaerung
    assert "172.807,49" in p.erklaerung and "16.441,48" in p.erklaerung


def test_ein_fehlender_euro_faellt_auf():
    """Ein Euro ist kein Rundungsfehler — über sechs Posten sind es Cent."""
    schief = dict(JAHR, sonstige_kosten=17122.19)
    p = gewinn_gegenprobe(schief)
    assert not p.bestanden
    assert "fehlt ein Posten" in p.erklaerung


def test_eine_unvollstaendige_probe_wird_nicht_behauptet():
    """Eine Summe ohne alle Posten ist keine Probe, sondern Zufall."""
    luecke = {k: v for k, v in JAHR.items() if k != "personal"}
    p = gewinn_gegenprobe(luecke)
    assert not p.bestanden and "Nicht prüfbar" in p.erklaerung
    assert "personal" in p.erklaerung


def test_ohne_erklaerte_ust_gibt_es_die_probe_gar_nicht():
    ohne = {k: v for k, v in JAHR.items() if k != "ust_erklaert"}
    assert [p.name for p in proben(ohne)] == ["Gewinn aus Einnahmen minus Ausgaben"]


# ————— Die Kennzahlen —————

def test_die_quoten_stimmen():
    kz = {k.name: k for k in kennzahlen(JAHR, VORJAHR)}
    assert kz["Wareneinkauf"].anteil_am_umsatz == pytest.approx(
        Decimal("0.3652"), abs=Decimal("0.0001"))
    assert kz["Umsatz (netto)"].anteil_am_umsatz is None   # Umsatz von Umsatz
    assert kz["Gewinn"].vorjahr == Decimal("3677.90")


def test_ein_fehlender_posten_erzeugt_keine_leere_zeile():
    ohne = {k: v for k, v in JAHR.items() if k != "afa"}
    assert "Abschreibungen" not in [k.name for k in kennzahlen(ohne)]


def test_die_veraenderung_zum_vorjahr_wird_gerechnet():
    kz = {k.name: k for k in kennzahlen(JAHR, VORJAHR)}
    assert kz["Umsatz (netto)"].veraenderung == pytest.approx(
        Decimal("0.385"), abs=Decimal("0.001"))


def test_ein_vorjahr_von_null_teilt_nicht_durch_null():
    kz = {k.name: k for k in kennzahlen(JAHR, {"umsatz": 0})}
    assert kz["Umsatz (netto)"].veraenderung is None


# ————— Der Bericht —————

def test_der_bericht_traegt_die_zahlen_und_den_rechenweg():
    t = bericht(JAHR, VORJAHR)
    for muss in ("172.807,49 €", "15.518,40 €", "Was auffällt",
                 "Die Gegenproben", "Vorjahr"):
        assert muss in t, muss


def test_der_anriss_zeigt_einen_befund_und_keine_gegenproben():
    """Was vor der Anmeldung gezeigt wird: genug, um zu überzeugen —
    aber die Auswertung selbst gibt es erst, wenn klar ist, wem sie gehört."""
    t = bericht(JAHR, VORJAHR, nur_anriss=True)
    assert "Steuerberatung" in t
    assert "Die Gegenproben" not in t
    assert "Umsatz ist deutlich gewachsen" not in t   # nur der erste Befund
    assert "vollständige Bericht" in t


def test_der_bericht_kommt_auch_mit_fast_nichts_zurecht():
    t = bericht({"umsatz": 50000.0})
    assert "50.000,00 €" in t
    assert "Was auffällt" not in t      # nichts zu sagen heißt: nichts sagen


def test_deutsche_zahlen_ueberall():
    t = bericht(JAHR, VORJAHR)
    assert "172,807.49" not in t        # kein englisches Format
    assert "38,5 %" in t


# ————— Was ins Profil darf —————

def test_nur_die_erlaubten_felder_wandern_ins_profil():
    """Aus einem Steuerbescheid liest man auch die Bankverbindung des
    Finanzamts. Die gehört ganz sicher nicht in die Stammdaten des Salons."""
    gelesen = {"steuernummer": "71 015 73457", "finanzamt": "Ludwigsburg",
               "iban": "DE12 5001 0517 0648 4898 90", "bic": "PBNKDEFF",
               "sachbearbeiter": "Frau Meier", "rechtsform": "Einzelunternehmen"}
    raus = uebernehmbare_felder(gelesen)
    assert set(raus) == {"steuernummer", "finanzamt", "rechtsform"}
    assert "iban" not in raus and "bic" not in raus


def test_leere_werte_werden_nicht_uebernommen():
    assert uebernehmbare_felder({"steuernummer": "", "finanzamt": None}) == {}


def test_die_erlaubnisliste_ist_bewusst_kurz():
    """Wächst sie unbemerkt, wandert irgendwann alles ins Profil."""
    assert len(UEBERNEHMBAR) <= 12
    assert "iban" not in UEBERNEHMBAR
