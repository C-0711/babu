"""Wer entscheidet, was auf dem Beleg steht.

Am 22.08.2026 zeigte die App auf einer Parkquittung über 3,50 € einen
Betrag von 19,00 € — den Mehrwertsteuersatz. Auf einer Rechnung über
40,00 € standen 43.783,86 €, das Stammkapital aus der Fußzeile. Und als
Lieferant stand „Rechnungsadresse", weil das die erste Zeile war.

Die Ursache war die Vorfahrt. Sie wurde an diesem Tag zweimal geändert und
steht jetzt so: **die Deutung entscheidet.** Sie liest den Beleg mit seiner
Geometrie und kann zu jeder Zahl die Zeile nennen, aus der sie stammt —
und was gebucht wird, muss nachweisbar sein. Das Bildmodell liest denselben
Beleg als Gegenprobe: es meldet Abweichungen, füllt Lücken, und schreibt
den Satz neben dem grünen Haken. Überschreiben darf es nichts.

Diese Tests halten genau das fest. Die Deutung selbst wird in
`test_belegdeutung.py` an echten Belegen geprüft.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def rw():
    import review_watcher
    return review_watcher


def feld(**werte):
    """Ein Feldsatz, wie die Deutung ihn liefert."""
    grund = {"lieferant": None, "beleg_nr": None, "datum": None,
             "netto": None, "ust": None, "brutto": None, "ust_satz": 19,
             "summenprobe_ok": False, "bewirtungssignal": False,
             "offen": [], "herkunft": {}}
    grund.update(werte)
    return grund


# ————— Beträge robust lesen —————

@pytest.mark.parametrize("roh, soll", [
    (3.5, 3.5), ("3.50", 3.5), ("3,50", 3.5), ("€40,00", 40.0),
    ("1.250,00", 1250.0), (None, None), ("", None), ("keine Zahl", None),
    (-5, None), (2_000_000, None),
])
def test_betraege_aus_der_gegenprobe(rw, roh, soll):
    assert rw._als_betrag(roh) == soll


@pytest.mark.parametrize("roh, soll", [
    ("14.08.2026", "2026-08-14"), ("1.9.2026", "2026-09-01"),
    ("14.08.26", "2026-08-14"), ("2026-08-14", "2026-08-14"),
    ("14/08/2026", "2026-08-14"),
    ("32.13.2026", None), ("irgendwann", None), ("", None), (None, None),
])
def test_datum_der_gegenprobe_wird_umgerechnet(rw, roh, soll):
    """Ohne Umrechnung wäre jedes Datum ein Widerspruch — und ein Hinweis,
    der immer erscheint, wird nicht mehr gelesen."""
    assert rw._als_datum(roh) == soll


# ————— Die Gegenprobe überschreibt nichts —————

def test_ein_gelesener_betrag_bleibt_stehen(rw):
    f = feld(brutto=40.00, herkunft={"brutto": {"regel": "Zeile nennt „Rechnungsbetrag“",
                                                "zeile": 14}})
    rw.gegenprobe_abgleichen(f, {"brutto": 43783.86})
    assert f["brutto"] == 40.00


def test_ein_gelesener_lieferant_bleibt_stehen(rw):
    f = feld(lieferant="Friseurbedarf Südwest GmbH")
    rw.gegenprobe_abgleichen(f, {"lieferant": "Rechnungsadresse"})
    assert f["lieferant"] == "Friseurbedarf Südwest GmbH"


def test_abweichung_wird_gemeldet(rw):
    f = feld(brutto=40.00)
    w = rw.gegenprobe_abgleichen(f, {"brutto": 43783.86})
    assert len(w) == 1
    assert "40.00" in w[0] and "43783.86" in w[0]


def test_gleiche_lesung_ergibt_keinen_widerspruch(rw):
    f = feld(brutto=40.00, lieferant="Salonkee S.A.", datum="2026-08-14")
    w = rw.gegenprobe_abgleichen(
        f, {"brutto": 40.0, "lieferant": "Salonkee S.A.", "datum": "14.08.2026"})
    assert w == []


def test_teiltreffer_beim_namen_ist_kein_widerspruch(rw):
    """„Salonkee“ und „Salonkee S.A.“ sind derselbe Laden."""
    f = feld(lieferant="Salonkee S.A.")
    assert rw.gegenprobe_abgleichen(f, {"lieferant": "Salonkee"}) == []


def test_centabweichung_ist_kein_widerspruch(rw):
    f = feld(brutto=40.00)
    assert rw.gegenprobe_abgleichen(f, {"brutto": 40.004}) == []


# ————— Lücken darf sie füllen, aber sichtbar —————

def test_luecke_wird_gefuellt(rw):
    f = feld(brutto=40.00)
    rw.gegenprobe_abgleichen(f, {"lieferant": "Salonkee S.A."})
    assert f["lieferant"] == "Salonkee S.A."


def test_gefuellte_luecke_ist_als_solche_erkennbar(rw):
    """Für einen so gefüllten Wert gibt es keine Zeile — das muss dranstehen."""
    f = feld(brutto=40.00)
    rw.gegenprobe_abgleichen(f, {"lieferant": "Salonkee S.A."})
    h = f["herkunft"]["lieferant"]
    assert h["zeile"] is None
    assert "Gegenprobe" in h["regel"]


def test_fehlender_betrag_aus_der_gegenprobe_wird_zur_nachfrage(rw):
    """Ein Betrag ohne Zeile im Beleg wird gebucht — also erst gefragt."""
    f = feld()
    rw.gegenprobe_abgleichen(f, {"brutto": 40.00})
    assert f["brutto"] == 40.00
    assert any("ansehen" in o for o in f["offen"])


def test_eine_null_der_gegenprobe_fuellt_keine_luecke(rw):
    """Liest auch das zweite Modell nur 0, wurde nichts gelesen —
    die Lücke bleibt Lücke statt zur falschen Gewissheit zu werden."""
    f = feld()
    rw.gegenprobe_abgleichen(f, {"brutto": 0.0})
    assert f["brutto"] is None
    assert "brutto" not in f["herkunft"]


def test_unbrauchbares_datum_fuellt_keine_luecke(rw):
    f = feld()
    rw.gegenprobe_abgleichen(f, {"datum": "neulich"})
    assert f["datum"] is None


def test_bewirtungssignal_darf_die_gegenprobe_setzen(rw):
    """Ob das ein Essen war, sieht man dem Bild an, nicht der Zeile."""
    f = feld()
    rw.gegenprobe_abgleichen(f, {"bewirtung": True})
    assert f["bewirtungssignal"] is True


# ————— Wenn die Gegenprobe ausfällt —————

@pytest.mark.parametrize("nichts", [None, {}, "nein", 42, []])
def test_ohne_gegenprobe_bleibt_alles_stehen(rw, nichts):
    f = feld(brutto=40.00, lieferant="Salonkee S.A.")
    assert rw.gegenprobe_abgleichen(f, nichts) == []
    assert f["brutto"] == 40.00 and f["lieferant"] == "Salonkee S.A."


def test_gegenprobe_mit_null_werten_stoert_nicht(rw):
    f = feld(brutto=40.00, lieferant="Salonkee S.A.")
    w = rw.gegenprobe_abgleichen(
        f, {"brutto": None, "lieferant": None, "datum": None, "beleg_nr": ""})
    assert w == [] and f["brutto"] == 40.00


# ————— Doppelgänger: derselbe Beleg, zweimal fotografiert —————

def _review_datei(ordner, name, **felder):
    import json
    (ordner / f"{name}.json").write_text(json.dumps({"felder": felder}),
                                         encoding="utf-8")


def test_gleiche_rechnungsnummer_ist_ein_doppelgaenger(rw, tmp_path):
    """Der Fall INV-DE057821 vom 26.08.: zweimal fotografiert, zweimal gebucht."""
    _review_datei(tmp_path, "alter-beleg", beleg_nr="INV-DE057821", brutto=40.0)
    f = {"beleg_nr": "INV-DE057821", "datum": "2026-02-28", "brutto": 40.0}
    assert rw.doppelgaenger_von(f, "neuer-beleg", tmp_path) == "alter-beleg"


def test_gleicher_tag_und_betrag_wird_gefragt(rw, tmp_path):
    _review_datei(tmp_path, "alter-beleg", datum="2026-02-28", brutto=40.0)
    f = {"beleg_nr": None, "datum": "2026-02-28", "brutto": 40.0}
    assert rw.doppelgaenger_von(f, "neuer-beleg", tmp_path) == "alter-beleg"


def test_kurze_nummern_und_eigene_datei_zaehlen_nicht(rw, tmp_path):
    """„1" als Beleg-Nr. trifft alles — und man ist nicht sein eigener
    Doppelgänger."""
    _review_datei(tmp_path, "alter-beleg", beleg_nr="1", brutto=9.0)
    f = {"beleg_nr": "1", "datum": None, "brutto": None}
    assert rw.doppelgaenger_von(f, "neuer-beleg", tmp_path) is None
    _review_datei(tmp_path, "neuer-beleg", beleg_nr="INV-4711", brutto=9.0)
    f2 = {"beleg_nr": "INV-4711", "datum": None, "brutto": None}
    assert rw.doppelgaenger_von(f2, "neuer-beleg", tmp_path) is None
