"""Freigabe durch die Inhaberin (babu Expenses D1)."""
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

from auslagen_hilfe import auslagen_welt, einreichen, lea  # noqa: F401,E402
from test_acting_as import _login, welt2  # noqa: F401,E402


def _eine(client):
    return client.get("/api/auslagen/meine").json()["auslagen"][0]


def test_offen_freigeben_legt_den_kreditor_an(auslagen_welt):
    lea_c, nina, _ = lea(auslagen_welt)
    einreichen(lea_c)
    offen = nina.get("/api/auslagen", params={"stand": "offen"}).json()
    assert [(z["name"], z["betrag"]) for z in offen["auslagen"]] == [("Lea", 23.4)]
    stamm = offen["auslagen"][0]["stamm"]
    r = nina.post(f"/api/auslagen/{stamm}/freigeben")
    assert r.status_code == 200, r.text
    kreditor = r.json()["kreditor"]
    assert _eine(lea_c)["status"] == "freigegeben" and _eine(lea_c)["kreditor"] == kreditor
    liste = nina.get("/api/datev/kreditoren").json()["eintraege"]
    assert [(k["nummer"], k["art"]) for k in liste if k["name"] == "Lea"] == [(kreditor, "mitarbeiterin")]
    zweite = einreichen(lea_c)
    assert zweite.status_code == 200
    stamm2 = next(z["stamm"] for z in nina.get("/api/auslagen", params={"stand": "offen"}).json()["auslagen"])
    assert nina.post(f"/api/auslagen/{stamm2}/freigeben").json()["kreditor"] == kreditor


def test_ablehnen_braucht_einen_grund(auslagen_welt):
    lea_c, nina, _ = lea(auslagen_welt)
    einreichen(lea_c)
    stamm = _eine(lea_c)["stamm"]
    assert nina.post(f"/api/auslagen/{stamm}/ablehnen", json={"grund": ""}).status_code == 409
    assert nina.post(f"/api/auslagen/{stamm}/ablehnen", json={"grund": "War privat"}).status_code == 200
    assert (_eine(lea_c)["status"], _eine(lea_c)["grund"]) == ("abgelehnt", "War privat")


def test_zuruecknehmen(auslagen_welt):
    lea_c, nina, _ = lea(auslagen_welt)
    einreichen(lea_c)
    stamm = _eine(lea_c)["stamm"]
    nina.post(f"/api/auslagen/{stamm}/freigeben")
    assert nina.post(f"/api/auslagen/{stamm}/zuruecknehmen").status_code == 200
    assert _eine(lea_c)["status"] == "eingereicht"


def test_nur_die_inhaberin_entscheidet(auslagen_welt):
    lea_c, nina, _ = lea(auslagen_welt)
    einreichen(lea_c)
    stamm = _eine(lea_c)["stamm"]
    assert lea_c.post(f"/api/auslagen/{stamm}/freigeben").status_code == 403
    kanzlei = _login(auslagen_welt["bw"], auslagen_welt["kanzlei"])
    kopf = {"X-Mandant": str(auslagen_welt["nina_id"])}
    assert kanzlei.get("/api/auslagen", headers=kopf).status_code == 200
    assert kanzlei.post(f"/api/auslagen/{stamm}/freigeben", headers=kopf).status_code == 403


def test_nur_lesen_sperrt_die_freigabe(auslagen_welt, monkeypatch):
    import abo  # noqa: PLC0415
    lea_c, nina, _ = lea(auslagen_welt)
    einreichen(lea_c)
    stamm = _eine(lea_c)["stamm"]
    monkeypatch.setattr(abo, "zugang", lambda **kw: {"stufe": "nur_lesen", "grund": "test_vorbei"})
    assert nina.post(f"/api/auslagen/{stamm}/freigeben").status_code == 403
    assert einreichen(lea_c).status_code == 403
