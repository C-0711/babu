"""In welchen Monat ein Beleg gehört.

Das ist keine Anzeigefrage. Der Monat steuert den Monatsabschluss, den
DATEV-Stapel und die Umsatzsteuer-Voranmeldung. Er muss vom BELEGDATUM
kommen, nicht vom Hochladen.

Aufgefallen am 23.08.2026 an Ninas Testlauf: Sie fotografierte einen
Kassenbon vom 5. März ab, und babu buchte ihn in den August. Damit stimmt
weder der Abschluss des einen noch der des anderen Monats — und die
Voranmeldung erst recht nicht.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import babu_web as bw  # noqa: E402

# So heißen die Dateien wirklich: Zeitstempel des Hochladens, dann der Name.
NAME = "20260823-120315-d56b1b-beleg_2026-03-05_mueller_f2effa1a.jpg"
PFAD = f"docs/2026-08/{NAME}"


def test_das_belegdatum_bestimmt_den_monat():
    """Der Fall aus Ninas Testlauf: Bon vom 5. März, hochgeladen im August."""
    assert bw._beleg_monat("2026-03-05", NAME, PFAD) == "2026-03"


def test_ohne_datum_bleibt_der_hochladezeitpunkt():
    """Irgendwo muss der Beleg auftauchen, sonst fehlt er ganz."""
    assert bw._beleg_monat(None, NAME, PFAD) == "2026-08"


@pytest.mark.parametrize("murks", ["", "05.03.2026", "2026-3-5", "irgendwann",
                                   "2026-03", 20260305, None, {}])
def test_ein_unbrauchbares_datum_faellt_auf_den_notnagel_zurueck(murks):
    """Lieber der falsche Monat als gar keiner — aber nur bei Murks."""
    assert bw._beleg_monat(murks, NAME, PFAD) == "2026-08"


def test_jahreswechsel():
    """Ein Bon vom 31. Dezember, im Januar hochgeladen, gehört ins alte Jahr —
    sonst wandert er über den Jahresabschluss hinweg."""
    name = "20270105-090000-abc-beleg.jpg"
    assert bw._beleg_monat("2026-12-31", name, f"docs/2027-01/{name}") == "2026-12"


def test_derselbe_monat_bleibt_derselbe():
    assert bw._beleg_monat("2026-08-23", NAME, PFAD) == "2026-08"


def test_ohne_datum_und_ohne_zeitstempel_im_namen():
    """Ein Dateiname ohne Zeitstempel — dann rettet der Ordner."""
    assert bw._beleg_monat(None, "rechnung.pdf", "docs/2026-05/rechnung.pdf") == "2026-05"


def test_gar_nichts_ergibt_gar_nichts():
    assert bw._beleg_monat(None, "rechnung.pdf", "irgendwo/rechnung.pdf") is None


def test_der_notnagel_selbst_liest_weiter_den_zeitstempel():
    """`_monat_aus_name` bleibt, was es war — es ist jetzt nur nicht mehr
    die erste Wahl."""
    assert bw._monat_aus_name(NAME, PFAD) == "2026-08"
