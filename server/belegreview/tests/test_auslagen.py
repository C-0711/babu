"""Auslagen — die reine Rechnung (babu Expenses D1)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import auslagen as al  # noqa: E402

AM = "2026-05-12T10:00:00+0200"


def test_eine_neue_auslage_ist_eingereicht():
    a = al.neu("lea@salon.de", "Lea", AM)
    assert (a["status"], a["bezahlt_mit"], a["kreditor"], a["erstattung"]) == (
        "eingereicht", "privat", None, None)
    assert al.laden(a) == a and al.laden(b"kaputt") is None and al.laden({"status": "x"}) is None


def test_der_weg_bis_erstattet():
    a = al.neu("lea@salon.de", "Lea", AM)
    f = al.uebergang(a, "freigegeben", von="nina", am=AM, kreditor="70003")
    assert (f["status"], f["kreditor"], f["entschieden_von"]) == ("freigegeben", "70003", "nina")
    r = al.reservieren(f, "E-2026-001")
    assert r["erstattung"] == "E-2026-001" and r["status"] == "freigegeben"
    with pytest.raises(al.AuslageFehler):
        al.reservieren(r, "E-2026-002")                    # steckt schon in einer Erstattung
    assert al.reservierung_loesen(r, "E-2026-001")["erstattung"] is None
    e = al.uebergang(r, "erstattet", von="nina", am=AM, erstattung="E-2026-001")
    assert e["status"] == "erstattet"


def test_verbotene_schritte():
    a = al.neu("lea@salon.de", "Lea", AM)
    with pytest.raises(al.AuslageFehler):
        al.uebergang(a, "erstattet", von="n", am=AM, erstattung="E-2026-001")
    with pytest.raises(al.AuslageFehler, match="warum"):
        al.uebergang(a, "abgelehnt", von="n", am=AM, grund=" x ")
    weg = al.uebergang(a, "zurueckgezogen", von="lea@salon.de", am=AM)
    with pytest.raises(al.AuslageFehler):
        al.uebergang(weg, "freigegeben", von="n", am=AM, kreditor="70003")
    f = al.reservieren(al.uebergang(a, "freigegeben", von="n", am=AM, kreditor="70003"), "E-2026-001")
    with pytest.raises(al.AuslageFehler, match="Erstattung"):
        al.uebergang(f, "eingereicht", von="n", am=AM)     # Freigabe zurücknehmen geht dann nicht


def test_index_stand():
    a = al.neu("lea@salon.de", "Lea", AM)
    assert al.index_stand(a) == "wartet"
    assert al.index_stand(al.uebergang(a, "abgelehnt", von="n", am=AM, grund="Privat")) == "abgelehnt"
    assert al.index_stand(al.uebergang(a, "zurueckgezogen", von="l", am=AM)) == "abgelehnt"
    assert al.index_stand(al.uebergang(a, "freigegeben", von="n", am=AM, kreditor="7")) is None


def test_je_person_und_kennung_und_zweck():
    posten = [{"kreditor": "70003", "name": "Lea", "von": "lea@s", "betrag": 23.4},
              {"kreditor": "70004", "name": "Mia", "von": "mia@s", "betrag": 5.0},
              {"kreditor": "70003", "name": "Lea", "von": "lea@s", "betrag": 24.7}]
    assert al.je_person(posten) == [
        {"kreditor": "70003", "name": "Lea", "von": "lea@s", "summe": 48.1},
        {"kreditor": "70004", "name": "Mia", "von": "mia@s", "summe": 5.0}]
    assert al.naechste_kennung([], 2026) == "E-2026-001"
    assert al.naechste_kennung(["E-2026-001", "E-2026-009", "E-2025-044"], 2026) == "E-2026-010"
    assert al.verwendungszweck("Lea", "E-2026-001") == "Auslagen Lea E-2026-001"


def test_iban():
    assert al.iban_normal(" de89 3704 0044 0532 0130 00 ") == "DE89370400440532013000"
    assert al.iban_gueltig("DE89 3704 0044 0532 0130 00") is True
    assert al.iban_gueltig("DE88 3704 0044 0532 0130 00") is False
    assert al.iban_gueltig("DE89 3704") is False


def test_bar_und_abgleich():
    bar = {"kennung": "E-2026-001", "art": "bar", "status": "ausgezahlt", "datum": "2026-05-20",
           "je_person": [{"kreditor": "70003", "name": "Lea", "von": "l", "summe": 48.1}]}
    ueb = {"kennung": "E-2026-002", "art": "ueberweisung", "status": "ueberwiesen",
           "datum": "2026-05-21", "ueberwiesen_am": "2026-05-22",
           "je_person": [{"kreditor": "70003", "name": "Lea", "von": "l", "summe": 12.0},
                         {"kreditor": "70004", "name": "Mia", "von": "m", "summe": 5.0}]}
    offen = dict(ueb, kennung="E-2026-003", status="erstellt")
    assert al.bar_je_monat([bar, ueb]) == {"2026-05": 48.1}
    assert [e["kennung"] for e in al.bar_erstattungen_im_monat([bar, ueb], "2026-05")] == ["E-2026-001"]
    assert al.abgleich_eintraege([bar, ueb, offen]) == [
        {"stamm": "E-2026-002", "brutto": 12.0, "datum": "2026-05-22", "erstattung": True},
        {"stamm": "E-2026-002", "brutto": 5.0, "datum": "2026-05-22", "erstattung": True}]
