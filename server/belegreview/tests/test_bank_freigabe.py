"""Der Betrieb gibt seiner Kanzlei die Kontoumsätze frei (B1, 04.10.2026).

Ohne Schalter (`BABU_BANK_FREIGABE`) liest die Kanzlei wie bisher. Mit
Schalter braucht sie zum Lesen die Freigabe; der Betrieb selbst liest immer.
Freigeben und widerrufen darf nur der Betrieb, anfragen nur die Kanzlei.
"""
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import box as bx  # noqa: E402
import recht  # noqa: E402
from test_acting_as import _login, welt2  # noqa: F401,E402


@pytest.fixture()
def post(monkeypatch):
    """Statt Mails: eine Liste."""
    import postfach  # noqa: PLC0415
    gesendet = []
    monkeypatch.setattr(postfach, "senden",
                        lambda an, betreff, text, *, stempel: (gesendet.append((an, betreff)),
                                                               (True, "ok"))[1])
    monkeypatch.setattr(bx, "remote_aus_ref", lambda ref: str(bx.store_aus_ref(ref)))
    return gesendet


def _kanzlei(welt):
    return _login(welt["bw"], welt["kanzlei"]), {"X-Mandant": str(welt["nina_id"])}


def test_ohne_schalter_liest_die_kanzlei_wie_bisher(welt2, post):
    c, kopf = _kanzlei(welt2)
    assert c.get("/api/abgleich/2026-05", headers=kopf).status_code == 200


def test_mit_schalter_braucht_die_kanzlei_die_freigabe(welt2, post, monkeypatch):
    monkeypatch.setenv("BABU_BANK_FREIGABE", "1")
    c, kopf = _kanzlei(welt2)
    for pfad in ("/api/abgleich/2026-05", "/api/fehlende-belege", "/api/zahlungen"):
        r = c.get(pfad, headers=kopf)
        assert r.status_code == 403, pfad
        assert r.json()["bank_freigabe_fehlt"] is True
    d = c.get("/api/bank/freigabe", headers=kopf).json()
    assert (d["freigegeben"], d["noetig"], d["kanzlei"]) == (False, True, "Kanzlei Süd")
    # Der Betrieb selbst liest ohne jede Freigabe.
    nina = _login(welt2["bw"], welt2["nina"])
    assert nina.get("/api/abgleich/2026-05").status_code == 200


def test_anfragen_freigeben_widerrufen(welt2, post, monkeypatch):
    monkeypatch.setenv("BABU_BANK_FREIGABE", "1")
    c, kopf = _kanzlei(welt2)
    assert c.post("/api/bank/freigabe", json={"fassung": recht.fassung("bank_freigabe")},
                  headers=kopf).status_code == 403          # nur der Betrieb
    r = c.post("/api/bank/freigabe/anfragen", headers=kopf)
    assert r.status_code == 200, r.text
    assert post == [("nina@0711.io", "babu — dein Steuerbüro bittet um die Kontoumsätze")]
    assert c.post("/api/bank/freigabe/anfragen", headers=kopf).status_code == 429

    nina = _login(welt2["bw"], welt2["nina"])
    assert nina.get("/api/bank/freigabe").json()["angefragt_am"]
    assert nina.post("/api/bank/freigabe/anfragen").status_code == 403
    assert nina.post("/api/bank/freigabe", json={"fassung": "alt"}).status_code == 409
    r = nina.post("/api/bank/freigabe", json={"fassung": recht.fassung("bank_freigabe")})
    assert r.status_code == 200 and r.json()["freigegeben"] is True
    assert c.get("/api/abgleich/2026-05", headers=kopf).status_code == 200

    assert nina.post("/api/bank/freigabe/widerrufen").status_code == 200
    assert c.get("/api/abgleich/2026-05", headers=kopf).status_code == 403


def test_auch_mit_freigabe_bleibt_die_kanzlei_beim_lesen(welt2, post, monkeypatch):
    monkeypatch.setenv("BABU_BANK_FREIGABE", "1")
    nina = _login(welt2["bw"], welt2["nina"])
    nina.post("/api/bank/freigabe", json={"fassung": recht.fassung("bank_freigabe")})
    c, kopf = _kanzlei(welt2)
    r = c.post("/api/fehlende-belege/klaeren",
               json={"schluessel": "0123456789abcdef", "grund": "privat"}, headers=kopf)
    assert r.status_code == 403 and r.json()["nur_lesen_bank"] is True


def test_das_cockpit_zeigt_die_freigabe(welt2, post):
    nina = _login(welt2["bw"], welt2["nina"])
    nina.post("/api/bank/freigabe", json={"fassung": recht.fassung("bank_freigabe")})
    c, _ = _kanzlei(welt2)
    zeilen = {z["id"]: z for z in c.get("/api/kanzlei/mandanten").json()["mandanten"]}
    assert zeilen[welt2["nina_id"]]["bank_freigegeben"] is True
    assert zeilen[welt2["berta_id"]]["bank_freigegeben"] is False
