"""Wer entscheidet, was auf dem Beleg steht — die Regex oder das Modell?

Am 22.08.2026 zeigte die App auf einer Parkquittung über 3,50 € einen
Betrag von 19,00 €. Das war der Mehrwertsteuersatz. Auf einer Rechnung über
40,00 € standen 43.783,86 € — das Stammkapital aus der Fußzeile. Und als
Lieferant stand „Rechnungsadresse", weil das die erste Zeile war.

Die Ursache war keine kaputte Regex, sondern die Vorfahrt: das Bildmodell
durfte drei Felder füllen, und auch die nur, wenn die Regex nichts gefunden
hatte. Den Betrag durfte es nie setzen.

Eine Regex sieht Zeichen, kein Dokument. Diese Tests halten fest, dass das
Modell führt und die Textsuche zur Gegenprobe geworden ist.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def rw(monkeypatch):
    import review_watcher
    return review_watcher


# ————— Beträge robust lesen —————

@pytest.mark.parametrize("roh, soll", [
    (3.5, 3.5), ("3.50", 3.5), ("3,50", 3.5), ("€40,00", 40.0),
    ("1.250,00", 1250.0), (None, None), ("", None), ("keine Zahl", None),
    (-5, None), (2_000_000, None),
])
def test_betraege_aus_dem_modell(rw, roh, soll):
    assert rw._als_betrag(roh) == soll


# ————— Die Vorfahrt —————

def _lesen(rw, regex, vlm):
    """Die Zusammenführung nachstellen, wie sie im Watcher passiert."""
    f = {"offen": [], "ust_satz": 19, "summenprobe_ok": False, **regex}
    quelltext = Path(rw.__file__).read_text()
    anfang = quelltext.index("    regex_lesung = {k: f.get(k)")
    ende = quelltext.index('    f["widerspruch"] = widerspruch') + len(
        '    f["widerspruch"] = widerspruch')
    schnipsel = "\n".join(z[4:] if z.startswith("    ") else z
                          for z in quelltext[anfang:ende].splitlines())
    raum = {"f": f, "vlm": vlm, "_als_betrag": rw._als_betrag}
    exec(schnipsel, raum)                                    # noqa: S102
    return f


def test_das_modell_gewinnt_beim_betrag(rw):
    """Parkquittung: die Textsuche fand den Steuersatz."""
    f = _lesen(rw, {"brutto": 19.00, "netto": 15.97, "ust": 3.03},
               {"brutto": 3.50, "netto": 2.94, "ust": 0.56})
    assert f["brutto"] == 3.50
    assert f["netto"] == 2.94 and f["ust"] == 0.56
    assert "brutto" in f["herkunft_vlm"]


def test_das_modell_gewinnt_beim_lieferanten(rw):
    """Salonkee: die erste Zeile war ein Formularetikett, kein Name."""
    f = _lesen(rw, {"lieferant": "Rechnungsadresse", "brutto": 43783.86},
               {"lieferant": "Salonkee S.A.", "brutto": 40.00})
    assert f["lieferant"] == "Salonkee S.A."
    assert f["brutto"] == 40.00


def test_das_modell_fuellt_eine_fehlende_belegnummer(rw):
    f = _lesen(rw, {"beleg_nr": None, "brutto": 40.0},
               {"beleg_nr": "INV-DE057821", "brutto": 40.0})
    assert f["beleg_nr"] == "INV-DE057821"


def test_wo_das_modell_schweigt_bleibt_die_textsuche(rw):
    """Es soll führen, nicht löschen."""
    f = _lesen(rw, {"lieferant": "Bäckerei Maier", "beleg_nr": "4711",
                    "brutto": 12.50},
               {"lieferant": None, "beleg_nr": None, "brutto": None})
    assert f["lieferant"] == "Bäckerei Maier"
    assert f["beleg_nr"] == "4711" and f["brutto"] == 12.50


# ————— Widerspruch wird gezeigt, nicht verschluckt —————

def test_ein_widerspruch_wird_benannt(rw):
    f = _lesen(rw, {"brutto": 19.00}, {"brutto": 3.50})
    assert f["widerspruch"]
    assert "19.00" in f["widerspruch"][0] and "3.50" in f["widerspruch"][0]


def test_ein_widerspruch_beim_lieferanten_auch(rw):
    f = _lesen(rw, {"lieferant": "Rechnungsadresse", "brutto": 40.0},
               {"lieferant": "Salonkee S.A.", "brutto": 40.0})
    assert any("Salonkee" in w and "Rechnungsadresse" in w
               for w in f["widerspruch"])


def test_einigkeit_erzeugt_keinen_laerm(rw):
    f = _lesen(rw, {"lieferant": "Salonkee S.A.", "brutto": 40.0},
               {"lieferant": "Salonkee S.A.", "brutto": 40.0})
    assert f["widerspruch"] == []


def test_gross_und_kleinschreibung_ist_kein_widerspruch(rw):
    f = _lesen(rw, {"lieferant": "SALONKEE S.A.", "brutto": 40.0},
               {"lieferant": "Salonkee S.A.", "brutto": 40.0})
    assert f["widerspruch"] == []


def test_die_alte_lesung_bleibt_nachvollziehbar(rw):
    """Damit sich später nachsehen lässt, was die Textsuche gemeint hat."""
    f = _lesen(rw, {"brutto": 19.00, "lieferant": "MwSt."},
               {"brutto": 3.50, "lieferant": "GALERIA"})
    assert f["regex_lesung"]["brutto"] == 19.00
    assert f["regex_lesung"]["lieferant"] == "MwSt."


# ————— Was das Modell NICHT darf —————

def test_unstimmige_aufteilung_wird_nicht_uebernommen(rw):
    """Nennt das Modell Netto und Steuer, die nicht zum Brutto passen, hat
    es geraten — dann wird lieber gerechnet."""
    f = _lesen(rw, {"brutto": 100.0, "netto": 84.03, "ust": 15.97},
               {"brutto": 50.0, "netto": 30.0, "ust": 5.0})     # 30+5 ≠ 50
    assert f["brutto"] == 50.0
    assert abs(f["netto"] + f["ust"] - 50.0) < 0.011
    assert f["summenprobe_ok"] is False


def test_stimmige_aufteilung_wird_uebernommen(rw):
    f = _lesen(rw, {"brutto": 100.0}, {"brutto": 50.0, "netto": 42.02,
                                       "ust": 7.98})
    assert (f["netto"], f["ust"]) == (42.02, 7.98)
    assert f["summenprobe_ok"] is True


def test_ein_betrag_von_null_wird_ignoriert(rw):
    """„Fälliger Saldo €0,00" ist kein Rechnungsbetrag."""
    f = _lesen(rw, {"brutto": 40.0}, {"brutto": 0})
    assert f["brutto"] == 40.0


def test_ohne_modell_bleibt_alles_beim_alten(rw):
    f = _lesen(rw, {"lieferant": "Bäckerei", "brutto": 12.5}, None)
    assert f["lieferant"] == "Bäckerei" and f["brutto"] == 12.5
    assert f["widerspruch"] == []


# ————— Der Steuersatz wird gerechnet, nicht gesucht —————

@pytest.mark.parametrize("netto, ust, satz", [
    (1.21, 0.09, 7),      # Bäckerbon: „7,00 %" fand die Heuristik nie
    (2.94, 0.56, 19),
    (100.0, 0.0, 0),      # Kleinunternehmer
    (100.0, 5.0, 5),
    (100.0, 16.0, 16),
])
def test_der_satz_folgt_aus_netto_und_steuer(rw, netto, ust, satz):
    f = _lesen(rw, {"brutto": 99.0, "ust_satz": 19},
               {"brutto": round(netto + ust, 2), "netto": netto, "ust": ust})
    assert f["ust_satz"] == satz


def test_ein_krummer_satz_wird_nicht_uebernommen(rw):
    """Kommt etwas heraus, das es im Gesetz nicht gibt, hat das Modell
    geraten — dann bleibt der alte Satz stehen."""
    f = _lesen(rw, {"brutto": 99.0, "ust_satz": 19},
               {"brutto": 113.0, "netto": 100.0, "ust": 13.0})   # 13 %
    assert f["ust_satz"] == 19


def test_ohne_stimmige_aufteilung_bleibt_der_satz(rw):
    f = _lesen(rw, {"brutto": 99.0, "ust_satz": 7},
               {"brutto": 50.0, "netto": 30.0, "ust": 5.0})
    assert f["ust_satz"] == 7
