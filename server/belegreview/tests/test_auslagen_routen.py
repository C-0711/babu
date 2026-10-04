"""Auslagen der Mitarbeiterinnen — Rechte und Wege (babu Expenses D1)."""
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

from auslagen_hilfe import BUCHUNG, auslagen_welt, einreichen, lea  # noqa: F401,E402
from test_acting_as import _login, welt2  # noqa: F401,E402


def _person(chefin, pid):
    return next(p for p in chefin.get("/api/team").json()["team"] if p["id"] == pid)


def test_das_recht_auslagen_steht_im_team(auslagen_welt):
    _, nina, pid = lea(auslagen_welt)
    p = _person(nina, pid)
    assert p["darf_auslagen"] is True and p["darf_belege"] is False
    assert p["iban_kurz"] is None


def test_ich_nennt_der_mitarbeiterin_ihre_rechte(auslagen_welt):
    lea_c, nina, _ = lea(auslagen_welt)
    assert lea_c.get("/api/ich").json()["rechte"] == {"belege": False, "kasse": False,
                                                       "auslagen": True}
    assert "rechte" not in nina.get("/api/ich").json()


def test_ohne_den_schluessel_bleibt_das_recht_stehen(auslagen_welt):
    """Ältere Aufrufer kennen darf_auslagen nicht — sie löschen es nicht."""
    _, nina, pid = lea(auslagen_welt)
    nina.post("/api/team", json={"id": pid, "name": "Lea", "email": "lea@salon.de",
                                 "darf_belege": True})
    p = _person(nina, pid)
    assert p["darf_auslagen"] is True and p["darf_belege"] is True
