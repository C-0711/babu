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


def test_nur_lesen_sperrt_auch_festschreiben_und_korrektur(welt2, monkeypatch):
    """Festschreiben per GET ist eine Übergabe — es darf die Abo-Sperre nicht
    umgehen, nur weil GET sonst als lesend gilt (Review 04.10.2026)."""
    import abo  # noqa: PLC0415
    monkeypatch.setattr(abo, "zugang", lambda **kw: {"stufe": "nur_lesen", "grund": "test_vorbei"})
    nina = _login(welt2["bw"], welt2["nina"])
    r = nina.get("/api/export/2026-05.csv", params={"festschreiben": 1})
    assert r.status_code == 403, r.text
    assert r.json().get("nur_lesen") is True
    assert nina.post(f"/api/korrektur/{ALPHA}", json={"buchungstext": "x"}).status_code == 403
    assert nina.get("/api/export/2026-05.csv").status_code == 200     # die Vorschau bleibt


def test_festschreiben_von_einer_fremden_seite_wird_abgelehnt(welt2):
    """Ein Link auf einer fremden Seite darf keinen Monat festschreiben."""
    nina = _login(welt2["bw"], welt2["nina"])
    for quelle in ("cross-site", "same-site"):
        r = nina.get("/api/export/2026-05.csv", params={"festschreiben": 1},
                     headers={"Sec-Fetch-Site": quelle})
        assert r.status_code == 403, (quelle, r.text)
    kanzlei = _login(welt2["bw"], welt2["kanzlei"])
    r = kanzlei.get("/api/export/2026-05.csv", params={"festschreiben": 1},
                    headers={"Sec-Fetch-Site": "cross-site", "X-Mandant": str(welt2["nina_id"])})
    assert r.status_code == 403


def test_die_kanzlei_liest_immer_die_texte_fuers_steuerbuero(welt2):
    """Das Portal fragt /api/ich ohne Mandantenkopf. Für die Kanzlei darf das
    nicht „selbst“ ergeben — sonst liest sie „trägst du in Mein ELSTER ein“."""
    nina = _login(welt2["bw"], welt2["nina"])
    nina.post("/api/einstellungen", json={"steuerberater_modus": "Ich selbst (Independence Day)"})
    kanzlei = _login(welt2["bw"], welt2["kanzlei"])
    assert kanzlei.get("/api/ich").json()["arbeitsweise"] == "steuerbuero"
    kopf = {"X-Mandant": str(welt2["nina_id"])}
    assert kanzlei.get("/api/ich", headers=kopf).json()["arbeitsweise"] == "steuerbuero"
    assert nina.get("/api/ich").json()["arbeitsweise"] == "selbst"


def test_der_hinweis_schon_uebergeben_spricht_die_leserin_an(welt2):
    """„liegt alles bei der Kanzlei“ nur für die Kanzlei; die Inhaberin liest
    „bei deinem Steuerbüro“ bzw. „abgeschlossen“ (Review 04.10.2026)."""
    spanne = {"von": "2026-05", "bis": "2026-05"}
    nina = _login(welt2["bw"], welt2["nina"])
    r = nina.post("/api/datev/uebergeben", params=spanne)
    assert r.status_code == 409 and "bei deinem Steuerbüro" in r.json()["fehler"], r.text
    nina.post("/api/einstellungen", json={"steuerberater_modus": "Ich selbst (Independence Day)"})
    text = nina.post("/api/datev/uebergeben", params=spanne).json()["fehler"]
    assert "abgeschlossen" in text and "Kanzlei" not in text and "Steuerbüro" not in text
    kanzlei = _login(welt2["bw"], welt2["kanzlei"])
    r = kanzlei.post("/api/datev/uebergeben", params=spanne,
                     headers={"X-Mandant": str(welt2["nina_id"])})
    assert "bei der Kanzlei" in r.json()["fehler"]


def test_der_satz_zum_uebergebenen_monat_kennt_drei_leserinnen():
    import datev_seite  # noqa: PLC0415
    u = [{"monat": "2026-05", "uebergeben_am": "03.06.2026", "buchungen": 12, "nachtrag_offen": 0}]
    assert "bei der Kanzlei" in datev_seite._uebergabe_text(u)
    assert "bei deinem Steuerbüro" in datev_seite._uebergabe_text(u, bei="bei deinem Steuerbüro")
    selbst = datev_seite._uebergabe_text(u, bei=None)
    assert "abgeschlossen" in selbst and "Kanzlei" not in selbst


def test_datev_seite_und_portal_sagen_niemandem_mehr_deine_kanzlei():
    for name in ("datev.html", "portal.html"):
        roh = (HIER.parent / name).read_text()
        for verboten in ("deine Kanzlei", "deiner Kanzlei"):
            zeilen = [z.strip() for z in roh.splitlines() if verboten in z
                      and "von deiner kanzlei" not in z.lower()]   # Post der Kanzlei: Absender
            assert not zeilen, (name, zeilen)
