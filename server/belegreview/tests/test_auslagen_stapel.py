"""Auslagen im Stapel, in der Kasse und im Bankabgleich (babu Expenses D1)."""
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import extf  # noqa: E402
from auslagen_hilfe import BUCHUNG, auslagen_welt, einreichen, lea  # noqa: F401,E402
from test_acting_as import welt2  # noqa: F401,E402

SPANNE = {"von": "2026-05", "bis": "2026-05"}


def _review(**auslage):
    return {"felder": {"zahlungsart": "bar", "brutto": 23.4, "datum": "2026-05-12"},
            "einschaetzung": {"konto": "5400"}, "auslage": auslage or None}


def test_gegenkonto_ist_der_kreditor_auch_wenn_der_bon_bar_sagt():
    assert extf.gegenkonto(_review(status="freigegeben", kreditor="70007")) == "70007"
    assert extf.gegenkonto(_review(status="erstattet", kreditor="70007")) == "70007"
    assert extf.gegenkonto(_review()) == extf.KASSE
    assert extf.gegenkonto(dict(_review(status="freigegeben", kreditor="70007"),
                                gegenkonto_fest="70099")) == "70099"


def test_auslagen_zaehlen_nicht_als_barbelege_der_kasse():
    blatt = {"datum": "2026-05-12", "sonstigeAusgaben": 0}
    luecke = extf.kassenluecke([blatt], [_review(status="freigegeben", kreditor="70007")])
    assert not [h for h in luecke if h["grund"] == "barbelege_ohne_kassenbuch"]


def test_bar_erstattung_deckt_die_kassenzeile():
    blatt = {"datum": "2026-05-20", "auslagenErstattet": 48.10}
    assert [h["grund"] for h in extf.kassenluecke([blatt])] == ["kassenluecke"]
    assert extf.kassenluecke([blatt], bar_erstattungen={"2026-05": 48.10}) == []
    zu_viel = extf.kassenluecke([blatt], bar_erstattungen={"2026-05": 60.0})
    assert [h["grund"] for h in zu_viel] == ["bar_erstattung_ohne_kassenzeile"]


def test_erstattungszeilen():
    e = {"kennung": "E-2026-001", "art": "bar", "status": "ausgezahlt", "datum": "2026-05-20",
         "je_person": [{"kreditor": "70007", "name": "Lea", "von": "l", "summe": 48.1}]}
    [z] = extf.erstattungszeilen([e])
    assert (z["konto"], z["gegenkonto"], z["umsatz"], z["belegdatum"]) == ("70007", extf.KASSE, "48,10", "2005")
    assert z["text"] == "Auslagenerstattung Lea" and "E-2026-001" in z["belegfeld1"]


def test_im_stapel_nur_was_freigegeben_ist(auslagen_welt):
    lea_c, berta, _ = lea(auslagen_welt, inhaberin="berta")
    einreichen(lea_c)
    vorschau = berta.get("/api/datev/vorschau", params=SPANNE).json()
    assert vorschau["befund"]["auslagen_warten"] == 1
    s = berta.get("/api/auslagen", params={"stand": "offen"}).json()["auslagen"][0]["stamm"]
    kreditor = berta.post(f"/api/auslagen/{s}/freigeben").json()["kreditor"]
    stapel = berta.get("/api/export/2026-05.csv").content.decode("cp1252")
    assert f";{kreditor};" in stapel


def test_bar_erstattung_im_stapel_und_nachtrag_nur_einmal(auslagen_welt):
    lea_c, berta, _ = lea(auslagen_welt, inhaberin="berta")
    einreichen(lea_c)
    s = berta.get("/api/auslagen", params={"stand": "offen"}).json()["auslagen"][0]["stamm"]
    kreditor = berta.post(f"/api/auslagen/{s}/freigeben").json()["kreditor"]
    berta.post("/api/auslagen/erstattung", json={"art": "bar", "staemme": [s], "datum": "2026-05-20"})
    erst = berta.post("/api/datev/uebergeben", params=SPANNE)
    assert erst.status_code == 200, erst.text
    text = erst.content.decode("cp1252")
    assert f"23,40;S;EUR;;;;{kreditor};1600;" in text      # extf._zeile: umsatz;sh;EUR;;;;konto;gegenkonto
    assert berta.post("/api/datev/uebergeben", params=SPANNE).status_code == 409
