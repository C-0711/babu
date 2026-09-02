"""Stufe-6-Tests: KSK-Parser + Zahlungsabgleich (synthetische Daten,
Layout dem echten GiroBusiness-Auszug nachgebaut — keine echten Bankdaten)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kontoauszug  # noqa: E402

SYNTHETISCH = """Kreissparkasse
Musterstadt
Frau
Erika Beispiel
1. Februar 2025
Kontoauszug 1/2025
Seite 1 von 2
GiroBusiness 12345678, DE00 0000 0000 0012 3456 78
Datum
Erläuterung
Betrag Soll EUR
Betrag Haben EUR
Kontostand am 30.12.2024, Auszug Nr. 12
3.872,50
02.01.2025 Lastschrift
Haarwaren Nord GmbH Rechnungsnr. 4711
 -952,58
09.01.2025 Rechnung
KREISSPARKASSE MUSTERSTADT Entgelt
SpkCard(Debitkarte) für 2025
 -17,85
09.01.2025 Gutschrift Überw.
SUMUP LIMITED PAYOUT 090125
 109,46
10.01.2025 Überweisung online
Extensions Süd order 0265 DATUM 10.01.2025
 -303,83
Postanschrift der Hauptstelle:
Postfach 1, 00000 Musterstadt
"""


def test_parse_text():
    d = kontoauszug.parse_text(SYNTHETISCH)
    assert d["monat"] == "2025-01"
    assert d["konto"] == "12345678"
    assert len(d["umsaetze"]) == 4
    u = d["umsaetze"][0]
    assert (u["datum"], u["betrag"]) == ("02.01.2025", -952.58)
    assert u["gegenpartei"].startswith("Haarwaren Nord")
    assert d["umsaetze"][2]["betrag"] == 109.46
    # Kontostand-Zeile ist kein Umsatz
    assert all("Kontostand" not in u["typ"] for u in d["umsaetze"])


def test_abgleich():
    d = kontoauszug.parse_text(SYNTHETISCH)
    belege = [{"stamm": "b1", "brutto": 952.58, "datum": "03.01.2025"},   # passt
              {"stamm": "b2", "brutto": 99.99, "datum": "10.01.2025"}]    # passt nicht
    a = kontoauszug.abgleich(d["umsaetze"], belege)
    assert [g["stamm"] for g in a["gedeckt"]] == ["b1"]
    assert len(a["fehlend"]) == 1                      # Extensions Süd 303,83
    assert a["fehlend"][0]["betrag"] == -303.83
    assert a["fehlend_summe"] == 303.83
    assert len(a["bankgebuehren"]) == 1                # SpkCard-Entgelt zählt nicht
    assert a["einnahmen_summe"] == 109.46


def test_abgleich_datumsfenster():
    d = kontoauszug.parse_text(SYNTHETISCH)
    zu_alt = [{"stamm": "alt", "brutto": 952.58, "datum": "20.11.2024"}]
    a = kontoauszug.abgleich(d["umsaetze"], zu_alt)
    assert not a["gedeckt"]                            # 6 Wochen daneben → kein Match


def test_monat_kommt_notfalls_aus_den_umsatzdaten():
    """Fotografierte oder fremde Auszüge haben keine „Kontoauszug N/JJJJ"-
    Zeile — dann sagt es der Inhalt: der Monat der meisten Umsätze."""
    import kontoauszug as ka
    text = """Musterbank Geschäftskonto
01.02.2026 Lastschrift
Miete Salon
-1.200,00
15.02.2026 Gutschrift
SUMUP Tagesumsatz
340,50
28.01.2026 Entgelt
Kontoführung
-8,90
"""
    d = ka.parse_text(text)
    assert d["monat"] == "2026-02"
    assert len(d["umsaetze"]) == 3


def test_parse_text_erkennt_die_bank():
    d = kontoauszug.parse_text(SYNTHETISCH)
    assert d["bank"] == "Kreissparkasse"

    ohne = kontoauszug.parse_text("Musterbank Geschäftskonto\n01.02.2026 Lastschrift\n")
    assert ohne["bank"] is None


def test_positionen_tragen_status_in_originalreihenfolge():
    """Die Checkliste der Bank-Ansicht: jede Position des Auszugs, in der
    Reihenfolge des Papiers, mit Haken-Status — gedeckte kennen ihren Beleg."""
    import kontoauszug
    d = kontoauszug.parse_text(SYNTHETISCH)
    belege = [{"stamm": "b1", "brutto": 952.58, "datum": "03.01.2025"}]
    a = kontoauszug.abgleich(d["umsaetze"], belege)
    p = a["positionen"]
    assert len(p) == len(d["umsaetze"]), "keine Position fällt unter den Tisch"
    assert [x["datum"] for x in p] == [u["datum"] for u in d["umsaetze"]]
    stati = {x["status"] for x in p}
    assert stati <= {"gedeckt", "fehlt", "bank", "einnahme"}
    gedeckt = [x for x in p if x["status"] == "gedeckt"]
    assert gedeckt and gedeckt[0]["stamm"] == "b1"
    assert all(x["stamm"] is None for x in p if x["status"] != "gedeckt")
