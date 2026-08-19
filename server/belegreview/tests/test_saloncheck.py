"""Salon-Check-Kern: Ampellogik, Sonderfälle, Sprache — ohne LLM, ohne I/O."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import saloncheck  # noqa: E402


def _kennzahlen(**ueberschreiben):
    basis = {
        "jahr": 2024,
        "stammdaten": {"rechtsform": "Einzelunternehmen",
                       "kleinunternehmer": False},
        "zahlen": {"umsatz": 100000, "wareneinsatz": 11000, "personal": 48000,
                   "raumkosten": 12000, "afa": 3000, "sonstige_kosten": 6000,
                   "gewinn": 20000, "ust_zahllast": 9000,
                   "est_vorauszahlungen": 2000},
        "unsicher": [],
    }
    for k, v in ueberschreiben.items():
        if isinstance(v, dict):
            basis[k] = {**basis[k], **v}
        else:
            basis[k] = v
    return basis


def _karte(karten, karte_id):
    return next(k for k in karten if k["id"] == karte_id)


def test_gesunder_salon_ist_gruen():
    karten = saloncheck.karten_bauen(_kennzahlen())
    assert [k["id"] for k in karten] == ["gewinn", "material", "personal",
                                        "raum", "ruecklage", "ust"]
    for karte_id in ("gewinn", "material", "personal", "raum", "ust"):
        assert _karte(karten, karte_id)["ampel"] == "gruen", karte_id
    # 30% von 20000 = 6000, minus 2000 Vorauszahlung = 4000/Jahr → 350/Monat.
    r = _karte(karten, "ruecklage")
    assert r["ampel"] == "gelb"
    assert "350 €" in r["satz"]


def test_material_gelb_und_rot():
    gelb = saloncheck.karten_bauen(_kennzahlen(zahlen={"wareneinsatz": 14000}))
    assert _karte(gelb, "material")["ampel"] == "gelb"
    rot = saloncheck.karten_bauen(_kennzahlen(zahlen={"wareneinsatz": 20000}))
    k = _karte(rot, "material")
    assert k["ampel"] == "rot"
    assert "20 von 100" in k["satz"]


def test_solo_salon_ohne_personal():
    karten = saloncheck.karten_bauen(_kennzahlen(zahlen={"personal": 0}))
    k = _karte(karten, "personal")
    assert k["ampel"] == "gruen"
    assert "allein" in k["satz"]


def test_verlust_ist_rot():
    karten = saloncheck.karten_bauen(_kennzahlen(zahlen={"gewinn": -3000}))
    assert _karte(karten, "gewinn")["ampel"] == "rot"
    # Kein Gewinn → keine Rücklagen-Mahnung.
    assert _karte(karten, "ruecklage")["ampel"] == "gruen"


def test_unsicher_wird_grau():
    karten = saloncheck.karten_bauen(_kennzahlen(unsicher=["personal", "gewinn"]))
    assert _karte(karten, "personal")["ampel"] == "grau"
    assert _karte(karten, "gewinn")["ampel"] == "grau"
    assert "nicht sicher lesen" in _karte(karten, "personal")["satz"]
    # wareneinsatz-Unsicherheit trifft die Material-Karte.
    karten = saloncheck.karten_bauen(_kennzahlen(unsicher=["wareneinsatz"]))
    assert _karte(karten, "material")["ampel"] == "grau"


def test_kleinunternehmerin():
    kn = _kennzahlen(stammdaten={"kleinunternehmer": True},
                     zahlen={"umsatz": 20000, "gewinn": 9000,
                             "wareneinsatz": 2200, "personal": 0,
                             "raumkosten": 2600})
    assert _karte(saloncheck.karten_bauen(kn), "ust")["ampel"] == "gruen"
    kn["zahlen"]["umsatz"] = 30000
    k = _karte(saloncheck.karten_bauen(kn), "ust")
    assert k["ampel"] == "gelb"
    assert "25.000 €" in k["satz"]


def test_ruecklage_rundet_auf_50():
    assert saloncheck.ruecklage_monatlich(20000, 2000) == 350
    assert saloncheck.ruecklage_monatlich(20000, 6000) == 0
    assert saloncheck.ruecklage_monatlich(1000, 0) == 50  # nie 0 bei offenem Rest


def test_fehlender_umsatz_macht_anteile_grau():
    kn = _kennzahlen()
    kn["zahlen"]["umsatz"] = None
    karten = saloncheck.karten_bauen(kn)
    for karte_id in ("gewinn", "material", "raum"):
        assert _karte(karten, karte_id)["ampel"] == "grau", karte_id


def test_kartensprache_ohne_fachwoerter():
    """Sprachregel wie in test_sprachregel.py, plus Zahlen-Fachjargon."""
    verboten = [r"\bServer\b", r"\bOCR\b", r"\bKI\b", r"\bModell\b",
                r"\bQuote\b", r"\bBenchmark\b", r"\bMarge\b", r"\bKPI\b",
                r"\bConfidence\b", r"übermitteln"]
    faelle = [
        _kennzahlen(),
        _kennzahlen(zahlen={"personal": 0}),
        _kennzahlen(zahlen={"gewinn": -3000}),
        _kennzahlen(unsicher=["gewinn", "personal", "wareneinsatz"]),
        _kennzahlen(stammdaten={"kleinunternehmer": True}),
    ]
    for kn in faelle:
        for karte in saloncheck.karten_bauen(kn):
            sichtbar = " ".join(str(karte.get(f) or "")
                                for f in ("titel", "satz", "detail",
                                          "wert", "ueblich"))
            treffer = [w for w in verboten if re.search(w, sichtbar)]
            assert not treffer, (karte["id"], treffer, sichtbar)
