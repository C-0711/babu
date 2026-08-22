"""Der erzeugte Lohnsteuerrechner.

`lohnsteuer_pap.py` wird aus dem amtlichen XML-Pseudocode des BMF erzeugt
(`werkzeug/pap_uebersetzen.py`) und nicht von Hand geschrieben. Diese Tests
prüfen deshalb zweierlei:

1. **Stimmen die Zahlen?** Die Sollwerte unten sind keine Erfindung — sie
   stammen aus dem öffentlichen Lohnsteuerrechner des BMF, Fall für Fall
   abgeglichen mit `werkzeug/pap_pruefen.py`. Weicht hier etwas ab, ist
   entweder die Übersetzung kaputt oder der Ablaufplan hat sich geändert.

2. **Verhält sich das Ganze wie eine Steuer?** Monotonie, Reihenfolge der
   Steuerklassen, Grundfreibetrag, Freigrenze beim Soli. Solche Invarianten
   fangen Übersetzungsfehler ab, für die es keinen abgeglichenen Fall gibt.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lohnsteuer_pap as pap  # noqa: E402


def lohnsteuer(brutto_euro, **anders) -> int:
    """Lohnsteuer in Cent für den Lohnzahlungszeitraum."""
    felder = {"LZZ": 2, "STKL": 1, "KVZ": "2.90", "PVZ": 1, "KRV": 0,
              "PKV": 0, "af": 0, **anders}
    z = pap.Zustand(RE4=int(round(brutto_euro * 100)), **felder)
    pap.berechnen(z)
    return int(z.LSTLZZ)


# ————— Gegen den amtlichen Rechner abgeglichen (22.08.2026) —————

@pytest.mark.parametrize("brutto, felder, soll_cent, was", [
    (3000, {}, 29308, "StKl I, monatlich"),
    (1000, {}, 0, "unter dem Grundfreibetrag"),
    (5000, {"STKL": 3, "PVZ": 0}, 40966, "StKl III"),
    (2500, {"STKL": 5}, 46566, "StKl V"),
    (2000, {"STKL": 6}, 34233, "StKl VI"),
    (3500, {"STKL": 2, "ZKF": "1.0", "PVZ": 0}, 31100, "StKl II mit Kinderfreibetrag"),
    (60000, {"LZZ": 1}, 938900, "jährlich"),
    (800, {"LZZ": 3, "STKL": 4}, 9076, "wöchentlich"),
    (150, {"LZZ": 4}, 2167, "täglich"),
    (9000, {}, 221275, "über allen Bemessungsgrenzen"),
    (4000, {"STKL": 3, "PKV": 1, "PKPV": 65000, "PVZ": 0}, 15033, "privat versichert"),
    (3000, {"PVS": 1}, 28900, "Sachsen"),
    (2100, {}, 10750, "knapp über dem Grundfreibetrag"),
])
def test_stimmt_mit_dem_bmf_rechner_ueberein(brutto, felder, soll_cent, was):
    assert lohnsteuer(brutto, **felder) == soll_cent, was


# ————— Invarianten: was für jede Steuer gelten muss —————

def test_unter_dem_grundfreibetrag_faellt_keine_steuer_an():
    """Grundfreibetrag 2026: 12.348 € im Jahr."""
    assert lohnsteuer(12348, LZZ=1) == 0
    assert lohnsteuer(12000, LZZ=1) == 0


def test_mehr_lohn_nie_weniger_steuer():
    """Ein Sprung nach unten wäre ein Übersetzungsfehler, kein Steuertarif."""
    vorher = -1
    for brutto in range(500, 12000, 250):
        jetzt = lohnsteuer(brutto)
        assert jetzt >= vorher, f"bei {brutto} € sank die Steuer"
        vorher = jetzt


def test_die_steuerklassen_stehen_in_der_richtigen_reihenfolge():
    """III günstiger als I, I günstiger als V und VI — bei gleichem Lohn."""
    drei, eins, fuenf, sechs = (lohnsteuer(3500, STKL=k, PVZ=0)
                                for k in (3, 1, 5, 6))
    assert drei < eins < fuenf <= sechs


def test_kinderfreibetraege_senken_nur_soli_und_kirchensteuer():
    """§ 51a EStG: die Lohnsteuer selbst bleibt gleich, die
    Bemessungsgrundlage für die Kirchensteuer sinkt."""
    def bk(zkf):
        z = pap.Zustand(RE4=600000, LZZ=2, STKL=1, KVZ="2.90", PVZ=0,
                        ZKF=zkf, R=1)
        pap.berechnen(z)
        return int(z.LSTLZZ), int(z.BK)
    ohne_lst, ohne_bk = bk("0")
    mit_lst, mit_bk = bk("2.0")
    assert mit_lst == ohne_lst
    assert mit_bk < ohne_bk


def test_soli_erst_ueber_der_freigrenze():
    """Freigrenze 2026: 20.350 € Jahreslohnsteuer."""
    def soli(brutto):
        z = pap.Zustand(RE4=int(brutto * 100), LZZ=1, STKL=1, KVZ="2.90", PVZ=1)
        pap.berechnen(z)
        return int(z.SOLZLZZ), int(z.LSTLZZ)
    kleiner_soli, kleine_lst = soli(60000)
    assert kleine_lst < 2035000 and kleiner_soli == 0
    grosser_soli, grosse_lst = soli(150000)
    assert grosse_lst > 2035000 and grosser_soli > 0


def test_ein_jahr_ist_zwoelf_monate():
    """Derselbe Lohn, einmal als Jahres-, einmal als Monatszeitraum."""
    jahr = lohnsteuer(36000, LZZ=1)
    monat = lohnsteuer(3000, LZZ=2)
    assert abs(jahr - monat * 12) <= 1200      # Rundung je Monat


def test_der_zusatzbeitrag_wirkt():
    """Höherer Zusatzbeitrag heißt höhere Vorsorgepauschale, also weniger
    Steuer."""
    assert lohnsteuer(3000, KVZ="4.00") < lohnsteuer(3000, KVZ="1.00")


def test_kinderlosenzuschlag_senkt_die_steuer():
    """Wer den Zuschlag zahlt, hat höhere Vorsorgeaufwendungen."""
    assert lohnsteuer(3000, PVZ=1) < lohnsteuer(3000, PVZ=0)


def test_beitragsabschlaege_fuer_kinder_wirken_umgekehrt():
    """Mehr Kinder heißt weniger Pflegebeitrag, also etwas mehr Steuer.

    Dieser Fall ließ sich über das BMF-Formular nicht abgleichen — es
    übernimmt das Feld nur bei echter Benutzereingabe. Die Richtung ergibt
    sich aber unmittelbar aus MPARA (`PVSATZAN – PVA * 0,0025`), und die
    steht so auch im gedruckten Ablaufplan.
    """
    ohne = lohnsteuer(3000, PVZ=0, PVA=0)
    mit_zwei = lohnsteuer(3000, PVZ=0, PVA=2)
    assert mit_zwei > ohne


# ————— Der erzeugte Code selbst —————

def test_der_ablaufplan_ist_vollstaendig_uebersetzt():
    """Alle 23 benannten Methoden des Pseudocodes müssen da sein."""
    erwartet = {"MPARA", "MRE4JL", "MRE4", "MRE4ALTE", "MRE4ABZ", "MBERECH",
                "MZTABFB", "MLSTJAHR", "UPLSTLZZ", "UPMLST", "UPEVP",
                "MVSPKVPV", "MVSPHB", "MST5_6", "UP5_6", "MSOLZ", "UPANTEIL",
                "MSONST", "STSMIN", "MSOLZSTS", "MOSONST", "MRE4SONST",
                "UPTAB26"}
    fehlt = {m for m in erwartet if not callable(getattr(pap, m, None))}
    assert not fehlt, f"nicht übersetzt: {sorted(fehlt)}"


def test_die_jahreswerte_stimmen():
    """Was das BMF-Schreiben für 2026 nennt — falsch übersetzt wäre alles
    andere auch falsch."""
    z = pap.Zustand(RE4=300000, LZZ=2, STKL=1, KVZ="2.90")
    pap.MPARA(z)
    assert int(z.GFB) == 12348           # Grundfreibetrag
    assert int(z.SOLZFREI) == 20350      # Freigrenze Solidaritätszuschlag
    assert int(z.BBGRVALV) == 101400     # BBG Renten-/Arbeitslosenversicherung
    assert int(z.BBGKVPV) == 69750       # BBG Kranken-/Pflegeversicherung
    assert str(z.RVSATZAN) == "0.093"    # halber RV-Satz
    assert str(z.AVSATZAN) == "0.013"    # halber ALV-Satz


def test_gerechnet_wird_mit_decimal_nicht_mit_fliesskomma():
    """Mit float käme man auf Centbeträge, die um einen Cent danebenliegen."""
    from decimal import Decimal
    z = pap.Zustand(RE4=300000, LZZ=2, STKL=1, KVZ="2.90")
    pap.berechnen(z)
    assert isinstance(z.LSTLZZ, Decimal)
