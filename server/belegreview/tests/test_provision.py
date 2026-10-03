"""Provision der Ambassadorinnen (provision.py, seit 03.10.2026).

25 % von zwölf Netto-Monatspreisen bei der ersten und noch einmal bei der
dritten bezahlten Rechnung. Gebucht wird genau einmal je Salon und
Meilenstein — egal, wie oft ein Ereignis kommt.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import babu_web  # noqa: E402
import provision  # noqa: E402


@pytest.fixture()
def c(tmp_path, monkeypatch):
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    with babu_web._DB_LOCK, babu_web._db() as verbindung:  # noqa: SLF001
        verbindung.execute("INSERT INTO ambassador (code, email, name, erstellt) "
                           "VALUES ('BABS', 'babs@salon.de', 'Babs', '2026-10-01')")
        for email in ("sonne@salon.de", "babs@salon.de"):
            verbindung.execute("INSERT INTO ambassador_salon (code, email, salon, "
                               "eingelöst) VALUES ('BABS', ?, 'Salon', "
                               "'2026-10-02T08:00:00Z')", (email,))
        yield verbindung


def _stand(c, email="sonne@salon.de"):
    s = c.execute("SELECT meilenstein, verdienst, gezeichnet_am, gehalten_am "
                  "FROM ambassador_salon WHERE email=?", (email,)).fetchone()
    a = c.execute("SELECT verdient FROM ambassador WHERE code='BABS'").fetchone()
    return tuple(s) + (a[0],)


@pytest.mark.parametrize("paket,euro", [("solo", 117), ("salon", 237), ("plus", 447),
                                        ("gibtsnicht", 0), (None, 0)])
def test_betrag_ist_drei_nettopreise(paket, euro):
    assert provision.betrag(paket) == euro


def test_meilensteine_an_der_ersten_und_dritten_rechnung():
    assert [provision.meilenstein_fuer(n) for n in range(5)] == [
        None, "gezeichnet", None, "gehalten", None]


@pytest.mark.parametrize("status,ust", [("ust", 4503), ("klein", 0),
                                        ("privat", 0), (None, 0)])
def test_ust_nur_fuer_umsatzsteuerpflichtige(status, ust):
    assert provision.ust_cent(23700, status) == ust


def _buchen(c, meilenstein, **kw):
    werte = dict(email="sonne@salon.de", meilenstein=meilenstein,
                 betrag_eur=237, paket="salon", quelle="stripe",
                 heute="2026-11-02", rechnung="in_1")
    werte.update(kw)
    return provision.buchen(c, **werte)


def test_gezeichnet_dann_gehalten_addiert(c):
    assert _buchen(c, "gezeichnet")["ok"] is True
    assert _stand(c) == ("gezeichnet", 237, "2026-11-02", None, 237)
    assert _buchen(c, "gehalten", heute="2027-01-02", rechnung="in_3")["ok"] is True
    # Bis 03.10.2026 zeigte die Salonzeile hier 237 statt 474.
    assert _stand(c) == ("gehalten", 474, "2026-11-02", "2027-01-02", 474)


def test_doppelt_bucht_nichts(c):
    assert _buchen(c, "gezeichnet")["ok"] is True
    r = _buchen(c, "gezeichnet")
    assert r["ok"] is False and r["grund"] == "schon_gebucht"
    assert _stand(c)[-1] == 237
    assert c.execute("SELECT COUNT(*) FROM ambassador_buchung").fetchone()[0] == 1


def test_gehalten_ohne_gezeichnet_bucht_nicht(c):
    r = _buchen(c, "gehalten")
    assert r["ok"] is False and r["grund"] == "stand"
    assert _stand(c)[-1] == 0


def test_ohne_ambassadorin_keine_provision(c):
    r = _buchen(c, "gezeichnet", email="fremd@salon.de")
    assert r == {"ok": False, "grund": "keine_ambassadorin", "code": None, "betrag": 0}


def test_selbstwerbung_zaehlt_nicht(c):
    r = _buchen(c, "gezeichnet", email="babs@salon.de")
    assert r["ok"] is False and r["grund"] == "selbst"
    assert _stand(c, "babs@salon.de")[-1] == 0


def test_die_buchung_kennt_herkunft_und_paket(c):
    _buchen(c, "gezeichnet", quelle="hand", rechnung=None, paket="plus",
            betrag_eur=447)
    z = c.execute("SELECT betrag, quelle, paket, stripe_rechnung, datum "
                  "FROM ambassador_buchung").fetchone()
    assert tuple(z) == (447, "hand", "plus", None, "2026-11-02")


def test_storno_einmal_und_verrechnet(c):
    _buchen(c, "gezeichnet")
    r = provision.stornieren(c, email="sonne@salon.de", meilenstein="gezeichnet",
                             heute="2026-11-20", rechnung="in_1")
    assert r["ok"] is True and r["betrag"] == -237
    assert _stand(c)[1] == 0 and _stand(c)[-1] == 0
    zweimal = provision.stornieren(c, email="sonne@salon.de", meilenstein="gezeichnet",
                                   heute="2026-11-21")
    assert zweimal["ok"] is False and zweimal["grund"] == "schon_storniert"
    summe = c.execute("SELECT SUM(betrag) FROM ambassador_buchung").fetchone()[0]
    assert summe == 0


def test_storno_ohne_buchung(c):
    r = provision.stornieren(c, email="sonne@salon.de", meilenstein="gehalten",
                             heute="2026-11-20")
    assert r["ok"] is False and r["grund"] == "nicht_gebucht"
