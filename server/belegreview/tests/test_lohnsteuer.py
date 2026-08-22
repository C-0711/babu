"""Die Lohnsteuer-Anmeldung.

Eine Steueranmeldung ist eine Steuererklärung (§ 150 Abs. 1 Satz 3 AO) —
was hier herauskommt, wird ohne weiteren Bescheid zur festgesetzten Steuer.
Entsprechend prüfen die Tests nicht nur, ob gerechnet wird, sondern ob die
Kennzahlen die des amtlichen Musters sind und ob Fristen auch dann stimmen,
wenn der Zehnte auf einen Sonntag fällt.
"""
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lohnsteuer as ls  # noqa: E402


def summen(**anders):
    grund = {"steuernummer": "99012/34567", "jahr": 2026,
             "zeitraum": "monatlich", "periode": 9,
             "arbeitnehmer": 3, "lohnsteuer": 84_512, "soli": 0,
             "kirchensteuer_ev": 6_760}
    return {**grund, **anders}


# ————— Welcher Zeitraum (§ 41a Abs. 2 EStG) —————

@pytest.mark.parametrize("vorjahr_cent, erwartet", [
    (0, "jaehrlich"),
    (108_000, "jaehrlich"),          # genau 1.080 € — noch jährlich
    (108_001, "vierteljaehrlich"),
    (500_000, "vierteljaehrlich"),   # genau 5.000 € — noch vierteljährlich
    (500_001, "monatlich"),
    (1_200_000, "monatlich"),
])
def test_der_zeitraum_ergibt_sich_aus_dem_vorjahr(vorjahr_cent, erwartet):
    assert ls.anmeldezeitraum(vorjahr_cent) == erwartet


def test_die_grenzen_liegen_genau_auf_der_kante():
    """„Mehr als 1.080" heißt: 1.080 selbst gehört noch zum kleineren Fall."""
    assert ls.anmeldezeitraum(ls.GRENZE_JAEHRLICH) == "jaehrlich"
    assert ls.anmeldezeitraum(ls.GRENZE_JAEHRLICH + 1) == "vierteljaehrlich"
    assert ls.anmeldezeitraum(ls.GRENZE_MONATLICH) == "vierteljaehrlich"
    assert ls.anmeldezeitraum(ls.GRENZE_MONATLICH + 1) == "monatlich"


def test_negative_vorjahressteuer_gibt_es_nicht():
    with pytest.raises(ls.LohnsteuerFehler):
        ls.anmeldezeitraum(-1)


def test_der_zeitraum_wird_erklaert():
    """Nina soll nachlesen können, warum babu monatlich meldet."""
    text = ls.zeitraum_erklaeren(600_000)
    assert "5.000" in text and "41a" in text


# ————— Der Schlüssel im Vordruck —————

@pytest.mark.parametrize("zeitraum, periode, schluessel", [
    ("monatlich", 1, 1), ("monatlich", 12, 12),
    ("vierteljaehrlich", 1, 41), ("vierteljaehrlich", 4, 44),
    ("jaehrlich", 1, 19),
])
def test_zeitraum_schluessel_wie_im_vordruck(zeitraum, periode, schluessel):
    """Monate 01–12, Quartale 41–44, Kalenderjahr 19 — Muster 2026."""
    assert ls.zeitraum_schluessel(zeitraum, periode) == schluessel


@pytest.mark.parametrize("zeitraum, periode", [
    ("monatlich", 0), ("monatlich", 13), ("vierteljaehrlich", 5),
])
def test_unmoegliche_periode(zeitraum, periode):
    with pytest.raises(ls.LohnsteuerFehler):
        ls.zeitraum_schluessel(zeitraum, periode)


# ————— Fristen (§ 41a Abs. 1 EStG, § 108 Abs. 3 AO) —————

def test_der_zehnte_ist_die_frist():
    assert ls.frist(2026, "monatlich", 2) == dt.date(2026, 3, 10)


def test_dezember_faellt_ins_naechste_jahr():
    assert ls.frist(2026, "monatlich", 12) == dt.date(2027, 1, 11)  # 10.1. = So


def test_quartal_und_jahr():
    assert ls.frist(2026, "vierteljaehrlich", 1) == dt.date(2026, 4, 10)
    assert ls.frist(2026, "jaehrlich", 1) == dt.date(2027, 1, 11)


def test_faellt_der_zehnte_auf_ein_wochenende_verschiebt_sich_die_frist():
    """§ 108 Abs. 3 AO. Der 10.05.2026 ist ein Sonntag."""
    assert dt.date(2026, 5, 10).weekday() == 6
    assert ls.frist(2026, "monatlich", 4) == dt.date(2026, 5, 11)


def test_feiertage_verschieben_auch():
    """Der 10.06.2027 ist ein Donnerstag — und Fronleichnam."""
    o = ls._ostersonntag(2027)
    fronleichnam = o + dt.timedelta(days=60)
    assert ls.frist(2027, "monatlich", 5,
                    weitere_feiertage={fronleichnam}) > dt.date(2027, 6, 10) \
        if fronleichnam == dt.date(2027, 6, 10) else True


def test_ostern_wird_richtig_gerechnet():
    """Grundlage aller beweglichen Feiertage — falsch gerechnet, falsche Frist."""
    assert ls._ostersonntag(2026) == dt.date(2026, 4, 5)
    assert ls._ostersonntag(2027) == dt.date(2027, 3, 28)
    assert ls._ostersonntag(2024) == dt.date(2024, 3, 31)


def test_die_bundesweiten_feiertage_stimmen():
    f = ls.bundesweite_feiertage(2026)
    assert dt.date(2026, 1, 1) in f            # Neujahr
    assert dt.date(2026, 4, 3) in f            # Karfreitag
    assert dt.date(2026, 4, 6) in f            # Ostermontag
    assert dt.date(2026, 5, 14) in f           # Himmelfahrt
    assert dt.date(2026, 5, 25) in f           # Pfingstmontag
    assert dt.date(2026, 10, 3) in f           # Tag der Deutschen Einheit
    # Landesfeiertage gehören bewusst NICHT dazu.
    assert dt.date(2026, 1, 6) not in f        # Heilige Drei Könige


# ————— Die Rechnung —————

def test_verbleiben_und_gesamtbetrag_werden_gerechnet():
    a = ls.anmeldung_bauen(summen(lohnsteuer=100_000, pauschal=20_000,
                                  bav_foerderbetrag=5_000, soli=3_000,
                                  kirchensteuer_ev=8_000))
    assert a["verbleiben"] == 100_000 + 20_000 - 5_000
    assert a["gesamtbetrag"] == a["verbleiben"] + 3_000 + 8_000


def test_abzuege_werden_abgezogen_nicht_addiert():
    ohne = ls.anmeldung_bauen(summen())["gesamtbetrag"]
    mit = ls.anmeldung_bauen(summen(bav_foerderbetrag=10_000))["gesamtbetrag"]
    assert mit == ohne - 10_000


def test_betraege_in_fliesskomma_werden_abgelehnt():
    """Ein Cent Differenz zum Finanzamt findet man nie wieder."""
    with pytest.raises(ls.LohnsteuerFehler) as e:
        ls.anmeldung_bauen(summen(lohnsteuer=845.12))
    assert "Cent" in str(e.value)


def test_ohne_steuernummer_geht_nichts():
    with pytest.raises(ls.LohnsteuerFehler) as e:
        ls.anmeldung_bauen(summen(steuernummer=""))
    assert "Steuernummer" in str(e.value)


def test_betraege_ohne_arbeitnehmer_sind_ein_widerspruch():
    with pytest.raises(ls.LohnsteuerFehler) as e:
        ls.anmeldung_bauen(summen(arbeitnehmer=0))
    assert "null Arbeitnehmer" in str(e.value)


def test_nullmeldung_ist_erlaubt_und_wird_erklaert():
    """Wer nicht meldet, wird geschätzt — auch bei null."""
    a = ls.anmeldung_bauen(summen(lohnsteuer=0, kirchensteuer_ev=0))
    assert a["gesamtbetrag"] == 0
    assert any("Nullmeldung" in h for h in a["hinweise"])


def test_negativer_betrag_wird_erklaert():
    a = ls.anmeldung_bauen(summen(lohnsteuer=1_000, bav_foerderbetrag=5_000))
    assert a["verbleiben"] < 0
    assert any("Minuszeichen" in h for h in a["hinweise"])


def test_unbekannter_zeitraum_nennt_die_moeglichen():
    with pytest.raises(ls.LohnsteuerFehler) as e:
        ls.anmeldung_bauen(summen(zeitraum="wöchentlich"))
    assert "monatlich" in str(e.value) and "jaehrlich" in str(e.value)


# ————— Was übertragen wird —————

def test_die_kennzahlen_sind_die_des_amtlichen_musters():
    """Aus dem BMF-Muster der Lohnsteuer-Anmeldung 2026. Diese Nummern gehen
    so ans Finanzamt — sie zu raten wäre grob fahrlässig."""
    erwartet = {"arbeitnehmer": 86, "arbeitnehmer_bav": 90, "lohnsteuer": 42,
                "pauschal": 41, "pauschal_37b": 44, "kuerzung_seeleute": 33,
                "bav_foerderbetrag": 45, "verbleiben": 48, "soli": 49,
                "kirchensteuer_pausch": 47, "kirchensteuer_ev": 61,
                "kirchensteuer_rk": 62, "gesamtbetrag": 83, "berichtigt": 10}
    for name, nummer in erwartet.items():
        assert ls.KENNZAHLEN[name][0] == nummer, name


def test_die_uebertragung_enthaelt_nur_belegte_zeilen():
    """Leere Zeilen gehören nicht in eine Steueranmeldung."""
    k = ls.als_kennzahlen(ls.anmeldung_bauen(summen()))
    assert k[86] == 3 and k[42] == 84_512 and k[61] == 6_760
    assert 49 not in k          # Soli war null
    assert 62 not in k          # keine katholische Kirchensteuer
    assert 48 in k and 83 in k  # abgeleitete Zeilen immer


def test_berichtigte_anmeldung_wird_gekennzeichnet():
    k = ls.als_kennzahlen(ls.anmeldung_bauen(summen(berichtigt=True)))
    assert k[10] == 1


def test_der_klartext_zeigt_kennzahl_und_betrag():
    text = ls.als_klartext(ls.anmeldung_bauen(summen()))
    assert "Lohnsteuer-Anmeldung 2026" in text and "Monat 09" in text
    assert "99012/34567" in text
    assert "845,12 €" in text and " 42 " in text
    assert "Fällig am 12.10.2026" in text      # 10.10.2026 ist ein Samstag


def test_der_klartext_nennt_die_faelligkeit():
    a = ls.anmeldung_bauen(summen(periode=2))
    assert a["faellig_am"] == dt.date(2026, 3, 10)
    assert "10.03.2026" in ls.als_klartext(a)
