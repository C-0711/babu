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


# ————— Was der Watcher aus der Portal-Datenbank liest —————

def _db_mit(tmp_path, zeilen):
    import sqlite3
    pfad = tmp_path / "portal.db"
    c = sqlite3.connect(pfad)
    c.execute("""CREATE TABLE einstellungen
        (un TEXT NOT NULL, schluessel TEXT NOT NULL, wert TEXT NOT NULL,
         PRIMARY KEY (un, schluessel))""")
    c.executemany("INSERT INTO einstellungen VALUES (?,?,?)", zeilen)
    c.commit()
    c.close()
    return pfad


def test_der_watcher_liest_den_rahmen_des_betriebs(tmp_path):
    pfad = _db_mit(tmp_path, [("nina@salon.de", "kontenrahmen", "SKR03")])
    assert kr.gewaehlt(pfad, vorgabe="SKR04") == "SKR03"


def test_ohne_datenbank_bleibt_es_bei_der_vorgabe(tmp_path):
    assert kr.gewaehlt(tmp_path / "gibtsnicht.db", vorgabe="SKR04") == "SKR04"


def test_zwei_verschiedene_rahmen_werden_nicht_geraten(tmp_path):
    """Eine Belegbox je Server — stehen trotzdem zwei Rahmen da, ist das ein
    Fehler und keine Gelegenheit zum Würfeln."""
    pfad = _db_mit(tmp_path, [("a@salon.de", "kontenrahmen", "SKR03"),
                              ("b@salon.de", "kontenrahmen", "SKR04")])
    assert kr.gewaehlt(pfad, vorgabe="SKR04") == "SKR04"


def test_ein_bestimmter_betrieb_laesst_sich_ansprechen(tmp_path):
    pfad = _db_mit(tmp_path, [("a@salon.de", "kontenrahmen", "SKR03"),
                              ("b@salon.de", "kontenrahmen", "SKR04")])
    assert kr.gewaehlt(pfad, un="a@salon.de", vorgabe="SKR04") == "SKR03"


# ————— Der Watcher fragt den Betrieb, nicht die Umgebung —————

def test_der_watcher_frischt_seinen_rahmen_aus_den_betriebsangaben_auf(
        tmp_path, monkeypatch):
    """Bis 23.08.2026 stand `KONTENRAHMEN` fest, sobald der Dienst lief.

    Nina konnte umstellen, so viel sie wollte — der Watcher buchte weiter im
    alten Rahmen, bis jemand den Dienst neu startete."""
    import review_watcher as rw  # noqa: PLC0415

    pfad = _db_mit(tmp_path, [("nina@salon.de", "kontenrahmen", "SKR03")])
    monkeypatch.setattr(rw, "PORTAL_DB", pfad)
    monkeypatch.setattr(rw, "KONTENRAHMEN", "SKR04")

    rw.kontenrahmen_auffrischen()
    assert rw.KONTENRAHMEN == "SKR03"

    e = rw.einschaetzung(
        {"ust_satz": 19, "bewirtungssignal": False, "offen": [],
         "summenprobe_ok": True, "netto": None, "brutto": None, "ust": None},
        {"belegart_code": "miete", "kategorie": "miete", "belegart": "Miete",
         "konfidenz": 0.9}, "Rechnung")
    assert (e["kontenrahmen"], e["konto"]) == ("SKR03", "4210")
    assert e["konto_skr04"] is None


def test_ohne_betriebsangabe_bleibt_die_umgebung_die_vorgabe(tmp_path, monkeypatch):
    import review_watcher as rw  # noqa: PLC0415

    monkeypatch.setattr(rw, "PORTAL_DB", tmp_path / "gibtsnicht.db")
    monkeypatch.setenv("BABU_KONTENRAHMEN", "SKR03")
    monkeypatch.setattr(rw, "KONTENRAHMEN", "SKR04")
    rw.kontenrahmen_auffrischen()
    assert rw.KONTENRAHMEN == "SKR03"
