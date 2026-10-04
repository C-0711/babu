"""Erstattung per Bankdatei oder bar (babu Expenses D1)."""
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

from auslagen_hilfe import BUCHUNG, auslagen_welt, einreichen, lea  # noqa: F401,E402
from test_acting_as import welt2  # noqa: F401,E402

IBAN_LEA = "DE89370400440532013000"
IBAN_SALON = "DE02120300000000202051"


def _freigegeben(welt, n=2):
    lea_c, nina, pid = lea(welt)
    lea_c.post("/api/auslagen/konto", json={"iban": IBAN_LEA})
    for betrag in (23.40, 24.70)[:n]:
        einreichen(lea_c, buchung=dict(BUCHUNG, betrag_eur=betrag))
    staemme = [z["stamm"] for z in nina.get("/api/auslagen", params={"stand": "offen"}).json()["auslagen"]]
    for s in staemme:
        assert nina.post(f"/api/auslagen/{s}/freigeben").status_code == 200
    nina.post("/api/einstellungen", json={"betrieb_name": "Salon Nina", "iban": IBAN_SALON})
    return lea_c, nina, staemme, pid


def test_bankdatei_je_person(auslagen_welt):
    lea_c, nina, staemme, _ = _freigegeben(auslagen_welt)
    r = nina.post("/api/auslagen/erstattung", json={"art": "ueberweisung", "staemme": staemme,
                                                     "datum": "2026-05-20"})
    assert r.status_code == 200, r.text
    kennung = r.json()["kennung"]
    assert kennung == "E-2026-001" and r.json()["status"] == "erstellt"
    xml = nina.get(f"/api/auslagen/erstattung/{kennung}/bankdatei.xml").text
    assert "<InstdAmt Ccy=\"EUR\">48.10</InstdAmt>" in xml
    assert IBAN_LEA in xml and IBAN_SALON in xml and "Auslagen Lea E-2026-001" in xml
    assert all(z["erstattung"] == kennung for z in lea_c.get("/api/auslagen/meine").json()["auslagen"])
    assert lea_c.get(f"/api/auslagen/erstattung/{kennung}/bankdatei.xml").status_code == 403
    assert nina.post(f"/api/auslagen/erstattung/{kennung}/ueberwiesen",
                     json={"am": "2026-05-22"}).status_code == 200
    assert {z["status"] for z in lea_c.get("/api/auslagen/meine").json()["auslagen"]} == {"erstattet"}


def test_doppelt_erstatten_geht_nicht(auslagen_welt):
    _, nina, staemme, _ = _freigegeben(auslagen_welt)
    koerper = {"art": "ueberweisung", "staemme": staemme, "datum": "2026-05-20"}
    assert nina.post("/api/auslagen/erstattung", json=koerper).status_code == 200
    assert nina.post("/api/auslagen/erstattung", json=koerper).status_code == 409


def test_verwerfen_gibt_die_auslagen_frei(auslagen_welt):
    lea_c, nina, staemme, _ = _freigegeben(auslagen_welt)
    k = nina.post("/api/auslagen/erstattung", json={"art": "ueberweisung", "staemme": staemme,
                                                     "datum": "2026-05-20"}).json()["kennung"]
    assert nina.post(f"/api/auslagen/erstattung/{k}/verwerfen").status_code == 200
    assert all(z["erstattung"] is None for z in lea_c.get("/api/auslagen/meine").json()["auslagen"])
    assert nina.post(f"/api/auslagen/erstattung/{k}/ueberwiesen", json={"am": "2026-05-22"}).status_code == 409


def test_ohne_iban_der_mitarbeiterin_keine_bankdatei(auslagen_welt):
    lea_c, nina, pid = lea(auslagen_welt)
    einreichen(lea_c)
    s = nina.get("/api/auslagen", params={"stand": "offen"}).json()["auslagen"][0]["stamm"]
    nina.post(f"/api/auslagen/{s}/freigeben")
    nina.post("/api/einstellungen", json={"betrieb_name": "Salon Nina", "iban": IBAN_SALON})
    r = nina.post("/api/auslagen/erstattung", json={"art": "ueberweisung", "staemme": [s],
                                                     "datum": "2026-05-20"})
    assert r.status_code == 409 and "Lea" in r.json()["fehler"]
    assert nina.post("/api/auslagen/erstattung", json={"art": "bar", "staemme": [s],
                                                        "datum": "2026-05-20"}).status_code == 200


def test_bar_ergibt_einen_erstattungsbeleg(auslagen_welt):
    lea_c, nina, staemme, _ = _freigegeben(auslagen_welt, n=1)
    r = nina.post("/api/auslagen/erstattung", json={"art": "bar", "staemme": staemme,
                                                     "datum": "2026-05-20"})
    assert r.status_code == 200 and r.json()["status"] == "ausgezahlt"
    pdf = nina.get(f"/api/auslagen/erstattung/{r.json()['kennung']}/beleg.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert lea_c.get("/api/auslagen/meine").json()["auslagen"][0]["status"] == "erstattet"


def test_eine_beendete_mitarbeiterin_bekommt_ihr_geld_trotzdem(auslagen_welt):
    lea_c, nina, staemme, pid = _freigegeben(auslagen_welt, n=1)
    nina.post("/api/team-aktion", json={"id": pid, "aktion": "beenden"})
    assert nina.post("/api/auslagen/erstattung", json={"art": "ueberweisung", "staemme": staemme,
                                                        "datum": "2026-05-20"}).status_code == 200
    assert einreichen(lea_c).status_code == 403
