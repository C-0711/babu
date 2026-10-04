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


ALPHA = "20260501-120000-aaa111-alpha"


def test_lea_reicht_eine_auslage_ein(auslagen_welt):
    lea_c, nina, _ = lea(auslagen_welt)
    r = einreichen(lea_c)
    assert r.status_code == 200, r.text
    assert r.json()["auslage"] is True and r.json()["art"] == "beleg"
    meine = lea_c.get("/api/auslagen/meine").json()
    assert [(x["status"], x["betrag"], x["lieferant"]) for x in meine["auslagen"]] == [
        ("eingereicht", 23.4, "Rossmann")]
    assert meine["offen"] == 23.4 and meine["iban_da"] is False
    stati = [z["status"] for z in nina.get("/api/belege").json()["belege"]]
    assert "wartet" in stati


def test_ohne_recht_keine_auslage(auslagen_welt):
    lea_c, _, _ = lea(auslagen_welt, auslagen=False, belege=True)
    assert einreichen(lea_c).status_code == 403
    assert einreichen(lea_c, auslage=False).status_code == 200     # Betriebsbeleg wie bisher


def test_die_inhaberin_reicht_keine_auslage_ein(auslagen_welt):
    nina = _login(auslagen_welt["bw"], auslagen_welt["nina"])
    assert einreichen(nina).status_code == 403


def test_eine_auslage_ist_immer_ein_beleg(auslagen_welt):
    lea_c, _, _ = lea(auslagen_welt)
    r = einreichen(lea_c, buchung=dict(BUCHUNG, dokumentklasse="kontoauszug"))
    assert r.status_code == 200 and r.json()["art"] == "beleg"
    assert r.json()["datei"].startswith("docs/")


def test_eine_zweite_mitarbeiterin_sieht_die_auslage_der_ersten_nicht(auslagen_welt):
    lea_c, _, _ = lea(auslagen_welt)
    mia_c, _, _ = lea(auslagen_welt, name="Mia", email="mia@salon.de")
    einreichen(lea_c)
    assert mia_c.get("/api/auslagen/meine").json()["auslagen"] == []
    stamm = lea_c.get("/api/auslagen/meine").json()["auslagen"][0]["stamm"]
    assert lea_c.get(f"/api/auslagen/meine/{stamm}").status_code == 200
    assert lea_c.get(f"/api/auslagen/meine/{stamm}/bild").status_code == 200
    assert mia_c.get(f"/api/auslagen/meine/{stamm}").status_code == 404
    assert mia_c.get(f"/api/auslagen/meine/{stamm}/bild").status_code == 404


def test_ohne_darf_belege_keine_fremden_belege(auslagen_welt):
    lea_c, _, _ = lea(auslagen_welt)
    assert lea_c.get("/api/belege").status_code == 403
    assert lea_c.get(f"/api/beleg/{ALPHA}").status_code == 403
    assert lea_c.get(f"/api/beleg/{ALPHA}/bild").status_code == 403


def test_einschaetzung_braucht_ein_recht(auslagen_welt):
    lea_c, _, _ = lea(auslagen_welt, auslagen=False)
    assert lea_c.post("/api/buchung/einschaetzung", json={"zeilen": []}).status_code == 403


def test_zurueckziehen_nur_eingereicht_und_eigen(auslagen_welt):
    lea_c, _, _ = lea(auslagen_welt)
    mia_c, _, _ = lea(auslagen_welt, name="Mia", email="mia@salon.de")
    einreichen(lea_c)
    stamm = lea_c.get("/api/auslagen/meine").json()["auslagen"][0]["stamm"]
    assert mia_c.post(f"/api/auslagen/{stamm}/zurueckziehen").status_code == 404
    assert lea_c.post(f"/api/auslagen/{stamm}/zurueckziehen").status_code == 200
    assert lea_c.post(f"/api/auslagen/{stamm}/zurueckziehen").status_code == 409
    assert lea_c.get("/api/auslagen/meine").json()["auslagen"][0]["status"] == "zurueckgezogen"


def test_konto_fuer_erstattungen(auslagen_welt):
    lea_c, nina, pid = lea(auslagen_welt)
    assert lea_c.post("/api/auslagen/konto", json={"iban": "DE00 1234"}).status_code == 400
    r = lea_c.post("/api/auslagen/konto", json={"iban": "de89 3704 0044 0532 0130 00"})
    assert r.status_code == 200 and r.json()["iban_kurz"] == "DE89 •••• 3000"
    assert _person(nina, pid)["iban_kurz"] == "DE89 •••• 3000"
    assert lea_c.get("/api/auslagen/meine").json()["iban_da"] is True
