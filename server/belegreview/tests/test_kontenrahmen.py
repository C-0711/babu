"""Der Kontenrahmen ist eine Betriebsangabe — und ein Jahreswechsel-Vorgang.

Bis 23.08.2026 stand er ausschließlich in `BABU_KONTENRAHMEN`. Nina konnte ihn
nirgends wählen; wer ihn ändern wollte, musste an die Umgebung des Dienstes.

Geprüft wird hier zweierlei:

1. **Woher der Rahmen kommt.** Die Betriebsangabe schlägt die Umgebung — die
   Umgebung ist nur noch die Vorgabe für einen Betrieb, der nichts gewählt hat.
2. **Wann er sich ändern darf.** Mitten im Jahr entstünden zwei unvereinbare
   Kontenrahmen in einem Stapel. Deshalb wirkt ein Wechsel erst zum 1. Januar,
   und er verlangt eine ausdrückliche Bestätigung.
"""
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import kontenrahmen as kr  # noqa: E402


# ————— Woher der Rahmen kommt —————

def test_ohne_betriebsangabe_gilt_die_vorgabe():
    assert kr.aus_einstellungen({}, vorgabe="SKR04") == "SKR04"
    assert kr.aus_einstellungen({}, vorgabe="SKR03") == "SKR03"


def test_die_betriebsangabe_schlaegt_die_umgebung():
    """Das ist der Kern von BABU-57: Nina entscheidet, nicht die Env-Datei."""
    assert kr.aus_einstellungen({"kontenrahmen": "SKR03"}, vorgabe="SKR04") == "SKR03"


def test_eine_unbrauchbare_betriebsangabe_wird_nicht_geglaubt():
    """Lieber die Vorgabe als ein Rahmen, den es nicht gibt."""
    assert kr.aus_einstellungen({"kontenrahmen": "SKR49"}, vorgabe="SKR04") == "SKR04"
    assert kr.aus_einstellungen({"kontenrahmen": "  "}, vorgabe="SKR04") == "SKR04"


def test_kleinschreibung_und_leerzeichen_stoeren_nicht():
    assert kr.aus_einstellungen({"kontenrahmen": " skr03 "}) == "SKR03"


def test_eine_kaputte_vorgabe_faellt_auf_den_hausstand_zurueck():
    """Ein Tippfehler in der Umgebungsvariablen darf den Dienst nicht kippen."""
    assert kr.aus_einstellungen({}, vorgabe="Unsinn") in kr.RAHMEN


# ————— Der Wechsel ist ein Jahreswechsel —————

def test_die_erste_festlegung_ist_frei():
    """Wer noch nichts gewählt hat, mischt auch nichts — keine Rückfrage."""
    b = kr.wechsel_pruefen(alt=None, neu="SKR03", heute_jahr=2026)
    assert b.erlaubt and b.rueckfrage is None
    assert b.gilt_ab == 2026


def test_derselbe_rahmen_noch_einmal_gewaehlt_ist_kein_wechsel():
    b = kr.wechsel_pruefen(alt="SKR04", neu="SKR04", heute_jahr=2026)
    assert b.erlaubt and b.rueckfrage is None


def test_ein_wechsel_will_erst_bestaetigt_werden():
    b = kr.wechsel_pruefen(alt="SKR04", neu="SKR03", heute_jahr=2026)
    assert not b.erlaubt
    assert b.rueckfrage and "SKR03" in b.rueckfrage
    assert "2027" in b.rueckfrage          # er sagt, ab wann er wirkte


def test_ein_bestaetigter_wechsel_wirkt_zum_naechsten_1_januar():
    """Nicht sofort: das laufende Jahr behält seinen Rahmen."""
    b = kr.wechsel_pruefen(alt="SKR04", neu="SKR03", heute_jahr=2026, bestaetigt=True)
    assert b.erlaubt and b.gilt_ab == 2027
    assert b.rueckfrage is None


def test_im_laufenden_jahr_geht_es_nur_solange_nichts_gebucht_ist():
    """Ein leeres Jahr darf den Rahmen noch tauschen — ein bebuchtes nie."""
    leer = kr.wechsel_pruefen(alt="SKR04", neu="SKR03", ab_jahr=2026,
                              heute_jahr=2026, bestaetigt=True)
    assert leer.erlaubt and leer.gilt_ab == 2026

    voll = kr.wechsel_pruefen(alt="SKR04", neu="SKR03", ab_jahr=2026,
                              heute_jahr=2026, bestaetigt=True,
                              gebuchte_jahre=(2026,))
    assert not voll.erlaubt
    assert "2026" in voll.begruendung
    assert voll.gilt_ab is None


def test_rueckwirkend_geht_gar_nicht():
    b = kr.wechsel_pruefen(alt="SKR04", neu="SKR03", ab_jahr=2025,
                           heute_jahr=2026, bestaetigt=True)
    assert not b.erlaubt and "vorbei" in b.begruendung.lower()


def test_ein_wechsel_weit_in_die_zukunft_ist_erlaubt():
    b = kr.wechsel_pruefen(alt="SKR03", neu="SKR04", ab_jahr=2028,
                           heute_jahr=2026, bestaetigt=True)
    assert b.erlaubt and b.gilt_ab == 2028


def test_ein_unbekannter_rahmen_faellt_sofort_auf():
    with pytest.raises(ValueError):
        kr.wechsel_pruefen(alt="SKR04", neu="SKR49", heute_jahr=2026)


def test_der_bescheid_sagt_immer_warum():
    for alt, neu, best in (("SKR04", "SKR03", False), ("SKR04", "SKR03", True),
                           (None, "SKR03", False), ("SKR04", "SKR04", False)):
        b = kr.wechsel_pruefen(alt=alt, neu=neu, heute_jahr=2026, bestaetigt=best)
        assert b.begruendung, (alt, neu, best)


def test_neue_kategorien_kennen_beide_rahmen():
    """Ninas Anmerkungen (27.08.): Materialeinsatz am Kunden, Kunden-
    aufmerksamkeiten und USt-Zahlungen ans Finanzamt — mit Standardkonten
    in SKR03 und SKR04."""
    import kontierung as kt
    for code, skr03, skr04 in (("materialeinsatz", "3000", "5100"),
                               ("aufmerksamkeit", "4605", "6605"),
                               ("ust_zahlung", "1780", "3820")):
        k = kt.KATEGORIEN[code]
        assert k.geprueft, code
        assert k.konto("SKR03") == skr03, code
        assert k.konto("SKR04") == skr04, code
