"""Die Ersteinschätzung nach Ninas Reihenfolge.

Bis 23.08.2026 stand hier eine Lücke: `einschaetzung()` wurde von keinem Test
angefasst. Sie ist aber die Stelle, an der aus einem gelesenen Beleg ein
Buchungsvorschlag wird — und genau dort hat Nina den Fehler benannt.

Geprüft wird deshalb das Verhalten, nicht die Form: wo geraten wurde, muss
jetzt gefragt werden; wo der Betrag entscheidet, muss er entscheiden; und der
Kontenrahmen muss durchschlagen, ohne dass sich zwei Rahmen mischen.
"""
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import review_watcher as rw  # noqa: E402


def felder(**ueberschreiben):
    """Ein gelesener Beleg, so knapp wie die Einschätzung ihn braucht."""
    f = {"ust_satz": 19, "bewirtungssignal": False, "offen": [],
         "summenprobe_ok": True, "netto": None, "brutto": None, "ust": None}
    f.update(ueberschreiben)
    return f


def sem(code, kategorie, konfidenz=0.71):
    return {"belegart_code": code, "kategorie": kategorie,
            "belegart": code, "konfidenz": konfidenz}


# ————— Was der Beleg nicht hergibt, wird gefragt —————

def test_friseurbedarf_wird_nicht_mehr_geraten():
    """Ninas Kernfall: dieselbe Schere kann Verkaufsware oder Verbrauch sein.

    Vorher fiel das hart auf Konto 5400. Jetzt kommt eine Frage zurück."""
    e = rw.einschaetzung(felder(), sem("wareneingang", None), "Rechnung")
    assert e["konto"] is None
    assert e["konto_skr04"] is None
    assert "aufgebraucht" in e["rueckfrage"]
    assert e["rueckfrage"] in e["hinweise"]


def test_ein_geraet_ohne_betrag_fuehrt_zur_frage_nicht_zum_konto():
    e = rw.einschaetzung(felder(), sem("ausstattung", None), "Rechnung")
    assert e["konto"] is None and e["rueckfrage"]
    assert "netto" in e["rueckfrage"]


def test_ohne_semantik_wird_gefragt_statt_sonstiges_zu_behaupten():
    e = rw.einschaetzung(felder(), None, "Rechnung")
    assert e["kategorie"] == "sonstiges"          # Vorschlag bleibt
    assert e["konto"] == "6850"
    assert any("Leistungsart prüfen" in h for h in e["hinweise"])


# ————— Wo der Betrag entscheidet, entscheidet er —————

@pytest.mark.parametrize("netto, kategorie, konto", [
    (80.00, "sonstiges", "6850"),          # unter 250 sofort Aufwand
    (300.00, "gwg", "0670"),               # GWG
    (1500.00, "anlagevermoegen", "0650"),  # Anlage
])
def test_der_foehn_landet_dort_wo_sein_preis_ihn_hinstellt(netto, kategorie, konto):
    """Vorher fiel ein Föhn unter „sonstiges" — die GWG-Frage kam nie.

    Über 250 € gehört die Antwort „ja, allein nutzbar" dazu; hier steht sie
    schon im Beleg, weil jemand die Rückfrage beantwortet hat."""
    f = felder(netto=netto, selbstaendig_nutzbar=True)
    e = rw.einschaetzung(f, sem("ausstattung", None), "Rechnung")
    assert (e["kategorie"], e["konto"]) == (kategorie, konto)
    assert e["rueckfrage"] is None


def test_die_antwort_zubehoer_verhindert_die_falsche_anlage():
    """Ein 900-€-Teil, das zu einem Gerät gehört, ist keine eigene Anlage."""
    f = felder(netto=900.00, selbstaendig_nutzbar=False)
    e = rw.einschaetzung(f, sem("ausstattung", None), "Rechnung")
    assert e["kategorie"] is None
    assert "Gerät" in e["rueckfrage"]


def test_zwischen_250_und_800_wird_nach_der_nutzbarkeit_gefragt():
    """Über 250 € hängt alles daran, ob das Ding allein nutzbar ist —
    das weiß der Beleg nicht."""
    e = rw.einschaetzung(felder(netto=400.00), sem("ausstattung", None), "Rechnung")
    assert e["konto"] is None
    assert "allein" in e["rueckfrage"]


# ————— Eindeutiges bleibt eindeutig —————

def test_eine_erkannte_kategorie_wird_zum_konto():
    e = rw.einschaetzung(felder(), sem("miete", "miete"), "Rechnung")
    assert (e["kategorie"], e["konto"]) == ("miete", "6310")
    assert e["rueckfrage"] is None
    assert "Miete" in e["kontierung_grund"]


def test_bewirtung_uebersteuert_und_raeumt_die_rueckfrage_weg():
    e = rw.einschaetzung(felder(bewirtungssignal=True),
                         sem("wareneingang", None), "Bewirtungsbeleg")
    assert e["konto"] == "6640" and e["kategorie"] == "bewirtung"
    assert e["rueckfrage"] is None
    assert any("70 %" in h for h in e["hinweise"])


def test_eine_spendenbescheinigung_bekommt_gar_kein_konto():
    e = rw.einschaetzung(felder(), sem("miete", "miete"), "Spendenbescheinigung")
    assert e["konto"] is None and e["kategorie"] is None
    assert any("Sonderausgaben" in h for h in e["hinweise"])


# ————— Die Rahmen mischen sich nicht —————

def test_unter_skr03_bleibt_das_skr04_feld_leer(monkeypatch):
    """Sonst stünde eine SKR03-Nummer in einem Feld namens konto_skr04 —
    genau die Vermischung, die Nina ausgeschlossen hat."""
    monkeypatch.setattr(rw, "KONTENRAHMEN", "SKR03")
    e = rw.einschaetzung(felder(), sem("miete", "miete"), "Rechnung")
    assert e["kontenrahmen"] == "SKR03"
    assert e["konto"] == "4210"        # SKR03-Miete
    assert e["konto_skr04"] is None    # und eben NICHT hier


def test_unter_skr04_wird_das_alte_feld_weiter_bedient():
    e = rw.einschaetzung(felder(), sem("miete", "miete"), "Rechnung")
    assert e["konto_skr04"] == e["konto"] == "6310"


def test_ein_ungepruefte_konto_sagt_es_im_hinweis():
    e = rw.einschaetzung(felder(netto=1500.0, selbstaendig_nutzbar=True),
                         sem("ausstattung", None), "Rechnung")
    assert e["kategorie"] == "anlagevermoegen"
    assert any("nicht steuerlich bestätigt" in h for h in e["hinweise"])


# ————— Was schon vorher galt, gilt weiter —————

def test_der_steuerschluessel_haengt_am_satz():
    assert rw.einschaetzung(felder(ust_satz=7), None, "Rechnung")["steuerschluessel"] == "8"
    assert rw.einschaetzung(felder(ust_satz=0), None, "Rechnung")["steuerschluessel"] == "0"
    assert rw.einschaetzung(felder(ust_satz=19), None, "Rechnung")["steuerschluessel"] == "9"


def test_eine_gescheiterte_summenprobe_bleibt_ein_hinweis():
    e = rw.einschaetzung(felder(summenprobe_ok=False), None, "Rechnung")
    assert any("Summenprobe" in h for h in e["hinweise"])
