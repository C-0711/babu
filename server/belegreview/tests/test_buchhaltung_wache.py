"""Jede Inhaberin darf ihre Buchhaltung selbst machen (Independence Day A).

DATEV-Seite mit Prüfbefund, Kreditoren, Korrektur, Export und „Monat
abschließen“ — in ihrer eigenen Box. Mitarbeiterinnen nie, fremde Boxen nie,
Kanzleien wie bisher.
"""
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import box as bx  # noqa: E402
from test_acting_as import _login, welt2  # noqa: F401,E402

ALPHA = "20260501-120000-aaa111-alpha"


@pytest.fixture(autouse=True)
def _boxen_schreibbar(monkeypatch):
    monkeypatch.setattr(bx, "remote_aus_ref", lambda ref: str(bx.store_aus_ref(ref)))


def test_die_inhaberin_erreicht_ihre_datev_seite(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    assert nina.get("/datev").status_code == 200
    assert nina.get("/api/datev/uebersicht").status_code == 200
    assert nina.get("/api/datev/vorschau", params={"von": "2026-05", "bis": "2026-05"}).status_code == 200
    assert nina.get("/api/datev/kreditoren").status_code == 200
    assert nina.post("/api/datev/kreditoren", json={"name": "Wella"}).status_code == 200
    assert nina.get("/api/export/2026-05.csv").status_code == 200


def test_die_inhaberin_korrigiert_selbst(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    r = nina.post(f"/api/korrektur/{ALPHA}", json={"buchungstext": "Einkauf"})
    assert r.status_code in (200, 404), r.text     # 404: Beleg ohne Lesung — aber nicht 403
    assert r.status_code != 403


def test_eine_inhaberin_kommt_nicht_in_eine_fremde_box(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    kopf = {"X-Mandant": str(welt2["berta_id"])}
    assert nina.get("/api/datev/uebersicht", headers=kopf).status_code == 403
    assert nina.get("/datev", params={"mandant": welt2["berta_id"]}).status_code == 403


def test_mitarbeiterin_bekommt_nichts(welt2, monkeypatch):
    monkeypatch.setattr(welt2["bw"], "rolle", lambda un: "mitarbeit")
    nina = _login(welt2["bw"], welt2["nina"])
    assert nina.get("/datev").status_code == 403
    assert nina.get("/api/datev/uebersicht").status_code == 403
    assert nina.post(f"/api/korrektur/{ALPHA}", json={"buchungstext": "x"}).status_code == 403
    assert nina.get("/api/export/2026-05.csv").status_code == 403


def test_die_kanzlei_bleibt_wie_sie_war(welt2):
    kanzlei = _login(welt2["bw"], welt2["kanzlei"])
    kopf = {"X-Mandant": str(welt2["nina_id"])}
    assert kanzlei.get("/api/datev/uebersicht", headers=kopf).status_code == 200


def test_nur_lesen_sperrt_den_abschluss_der_inhaberin(welt2, monkeypatch):
    import abo  # noqa: PLC0415
    monkeypatch.setattr(abo, "zugang", lambda **kw: {"stufe": "nur_lesen", "grund": "test_vorbei"})
    nina = _login(welt2["bw"], welt2["nina"])
    assert nina.get("/api/datev/vorschau", params={"von": "2026-05", "bis": "2026-05"}).status_code == 200
    assert nina.post("/api/datev/uebergeben", params={"von": "2026-05", "bis": "2026-05"}).status_code == 403


def test_die_seite_weiss_wer_den_monat_abschliesst(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    assert nina.get("/api/datev/uebersicht").json()["wer"] == "steuerbuero"
    nina.post("/api/einstellungen", json={"steuerberater_modus": "Ich selbst (Independence Day)"})
    assert nina.get("/api/datev/uebersicht").json()["wer"] == "selbst"
    kanzlei = _login(welt2["bw"], welt2["kanzlei"])
    assert kanzlei.get("/api/datev/uebersicht",
                       headers={"X-Mandant": str(welt2["nina_id"])}).json()["wer"] == "kanzlei"
