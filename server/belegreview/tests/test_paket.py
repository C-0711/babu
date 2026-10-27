"""Die Stufen — Platz statt Funktionen (paket.py, seit 10.10.2026).

Ohne Datenbank, ohne Netz, ohne Apple: nur die Rechnung. Die wichtigste
Zusage steht in `test_portal_betriebe_merken_nichts`: solange ein Betrieb
nicht über den App Store gekommen ist, gibt es diese Regeln für ihn nicht.
"""
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import abo  # noqa: E402
import paket  # noqa: E402

HEUTE = dt.date(2026, 10, 20)
GB = paket.GB


def _st(**kw):
    werte = {"herkunft": paket.HERKUNFT_APP, "stufe": None,
             "verbraucht": 0, "belege": 0}
    werte.update(kw)
    return paket.stand(**werte)


def _z(**kw):
    werte = {"test_bis": None, "abo_status": None, "abo_ende": None,
             "zahlungsfehler_seit": None}
    werte.update(kw)
    return abo.zugang(heute=HEUTE, **werte)


# ---------------------------------------------------------------------------
# Was der Auftraggeber am 10.10.2026 entschieden hat
# ---------------------------------------------------------------------------

def test_drei_stufen_mit_den_beschlossenen_preisen():
    """1 GB 9,99 · 5 GB 19,99 · 100 GB 99,00 — Endpreise bei Apple."""
    assert [(a["stufe"], a["gb"], a["cent"]) for a in paket.angebot()] == [
        ("klein", 1, 999), ("mittel", 5, 1999), ("gross", 100, 9900)]


def test_jede_stufe_hat_eine_eigene_apple_kennung():
    kennungen = [a["apple"] for a in paket.angebot()]
    assert len(set(kennungen)) == len(kennungen)
    assert all(k.startswith("babu.speicher.") for k in kennungen)


def test_zehn_belege_frei():
    assert paket.BELEGE_FREI == 10


def test_funktionen_trennen_die_stufen_nie():
    """Die Entscheidung in Code gegossen: eine Stufe sagt nur, wie viel
    Platz es gibt — nie, was erlaubt ist. Kommt hier je ein Schalter dazu,
    fällt dieser Test, und das ist der Sinn."""
    for eintrag in paket.STUFEN.values():
        assert set(eintrag) == {"gb", "cent", "apple"}


# ---------------------------------------------------------------------------
# Das Freikontingent
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("belege,offen", [(0, 10), (1, 9), (9, 1), (10, 0), (11, 0)])
def test_freie_belege_zaehlen_abwaerts(belege, offen):
    st = _st(belege=belege)
    assert st["frei_offen"] == offen
    assert st["voll"] is (offen == 0)


def test_knapp_erst_bei_drei_uebrigen():
    assert _st(belege=6)["knapp"] is False      # noch 4
    assert _st(belege=7)["knapp"] is True       # noch 3
    assert _st(belege=10)["knapp"] is False     # voll ist nicht knapp


def test_ohne_stufe_zaehlen_belege_und_nicht_bytes():
    """Zehn freie Belege, auch wenn sie groß sind — „zehn Belege" ist die
    Zusage, nicht ein Megabyte-Betrag."""
    st = _st(belege=3, verbraucht=800 * 1024 * 1024)
    assert st["voll"] is False
    assert st["frei_offen"] == 7


# ---------------------------------------------------------------------------
# Mit gebuchter Stufe
# ---------------------------------------------------------------------------

def test_grenzen_der_stufen():
    assert paket.grenze("klein") == 1 * GB
    assert paket.grenze("mittel") == 5 * GB
    assert paket.grenze("gross") == 100 * GB
    assert paket.grenze(None) is None
    assert paket.grenze("erfunden") is None


def test_mit_stufe_zaehlen_bytes_und_nicht_belege():
    st = _st(stufe="klein", belege=5000, verbraucht=10)
    assert st["voll"] is False
    assert st["frei_offen"] is None


@pytest.mark.parametrize("anteil,voll,knapp", [
    (0.0, False, False), (0.5, False, False), (0.89, False, False),
    (0.9, False, True), (0.99, False, True), (1.0, True, False),
    (1.5, True, False)])
def test_warnschwelle_und_vollmeldung(anteil, voll, knapp):
    st = _st(stufe="mittel", verbraucht=int(5 * GB * anteil))
    assert (st["voll"], st["knapp"]) == (voll, knapp)


def test_eine_fremde_produktkennung_wird_nie_zu_platz():
    """Eine Kennung, die wir nicht kennen, darf nicht stillschweigend ein
    Kontingent ergeben — sonst schenkte ein Tippfehler im App Store Platz."""
    assert paket.stufe_fuer_produkt("babu.speicher.1gb") == "klein"
    assert paket.stufe_fuer_produkt("babu.speicher.1000gb") is None
    assert paket.stufe_fuer_produkt(None) is None
    assert _st(stufe="babu.speicher.1000gb", belege=10)["voll"] is True


# ---------------------------------------------------------------------------
# Die Grenze zum Bestand
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("herkunft", [None, "", "portal", "kanzlei"])
def test_portal_betriebe_merken_nichts(herkunft):
    """Die Zusage an jeden Betrieb, der schon da ist."""
    assert paket.stand(herkunft=herkunft, stufe="klein",
                       verbraucht=999 * GB, belege=99999) is None


@pytest.mark.parametrize("herkunft", [None, "portal"])
def test_zugang_bleibt_fuer_portal_byte_fuer_byte(herkunft):
    """`abo.zugang` muss mit und ohne die neuen Werte dasselbe sagen,
    solange die Herkunft nicht „app" ist."""
    for test_bis, status in ((None, None), ("2026-10-19", None),
                             ("2026-10-25", None), (None, "aktiv"),
                             (None, "zahlung_offen"), (None, "gekuendigt")):
        alt = _z(test_bis=test_bis, abo_status=status)
        neu = _z(test_bis=test_bis, abo_status=status, herkunft=herkunft,
                 paket="klein", speicher_bytes=500 * GB, belege_gesamt=99999)
        assert alt == neu


def test_app_ohne_stufe_darf_zehn_belege_dann_nur_lesen():
    offen = _z(herkunft="app", belege_gesamt=9)
    assert offen == {"stufe": "voll", "grund": None, "bis": None}
    voll = _z(herkunft="app", belege_gesamt=10)
    assert voll == {"stufe": "nur_lesen", "grund": "frei_aufgebraucht",
                    "bis": None}


def test_voller_platz_schlaegt_das_laufende_abo():
    """Ein bezahltes Abo gibt keinen Platz, den es nicht gibt."""
    z = _z(herkunft="app", abo_status="aktiv", paket="klein",
           speicher_bytes=1 * GB, belege_gesamt=20)
    assert z == {"stufe": "nur_lesen", "grund": "speicher_voll", "bis": None}


def test_gekuendigtes_abo_nimmt_keinen_platz_weg():
    """Umgekehrt: wer Platz hat, dem nimmt die Abo-Regel ihn nicht — die
    Abo-Regel entscheidet weiter, aber nicht wegen des Platzes."""
    z = _z(herkunft="app", abo_status="gekuendigt", paket="klein",
           speicher_bytes=1, belege_gesamt=20)
    assert z["grund"] == "gekuendigt"


def test_der_kauf_weg_bleibt_offen_wenn_der_platz_voll_ist():
    """Die Sperre darf nie die Anfrage blockieren, mit der man Platz kauft."""
    z = _z(herkunft="app", belege_gesamt=10)
    assert abo.sperrt("POST", "/api/aufnahme", z) is True
    assert abo.sperrt("POST", "/api/abo/apple", z) is False
    assert abo.sperrt("GET", "/api/belege", z) is False
    # Die Kaufseite misst sich auch dann, wenn der Platz voll ist — genau
    # dort entsteht die Wand, die gemessen werden soll (Review 28.10.2026).
    assert abo.sperrt("POST", "/api/platz/ereignis", z) is False


@pytest.mark.parametrize("grund", ["frei_aufgebraucht", "speicher_voll"])
def test_der_satz_zum_platz_sagt_dass_nichts_verloren_geht(grund):
    satz = abo.text({"stufe": "nur_lesen", "grund": grund})
    assert "bleib" in satz.lower()
    for fassung in (True, False):
        assert abo.text({"stufe": "nur_lesen", "grund": grund}, fassung) == satz


def test_text_schweigt_solange_alles_passt():
    assert paket.text(_st()) is None
    assert paket.text(_st(stufe="gross", verbraucht=1 * GB)) is None
    assert paket.text(None) is None


def test_text_nennt_die_eine_zahl_im_singular():
    assert paket.text(_st(belege=9)) == "Noch 1 Beleg frei."
    assert paket.text(_st(belege=8)) == "Noch 2 Belege frei."


def test_kein_negativer_stand_bei_kaputten_werten():
    st = paket.stand(herkunft="app", stufe=None, verbraucht=-5, belege=-3)
    assert (st["verbraucht"], st["belege"], st["frei_offen"]) == (0, 0, 10)
