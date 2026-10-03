"""Abo per Stripe — Routen und Webhook (kern_abo.py, seit 03.10.2026).

Stripe wird nie angerufen: `stripe_api._rufen` ist ersetzt, die Ereignisse
sind signiert wie von Stripe. Geprüft wird der ganze Weg eines Salons —
Weitermachen, erste Zahlung (Provision „gezeichnet"), dritte Zahlung
(„gehalten"), Zahlungsfehler, Kündigung, Rücklastschrift — und dass nichts
doppelt bucht, egal wie oft oder in welcher Reihenfolge Stripe meldet.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import babu_web  # noqa: E402
import mandanten  # noqa: E402
import stripe_api  # noqa: E402
import testmonat  # noqa: E402

PASSWORT = "ein-langes-passwort-hier"
GEHEIM = "whsec_test_geheim"
URSPRUNG = "https://dev.mybabu.io"


class FakeStripe:
    def __init__(self):
        self.aufrufe: list[tuple] = []
        self.abos: dict[str, dict] = {}
        self.sitzungen: dict[str, dict] = {}
        self.zahlungen: dict[str, dict] = {}

    def __call__(self, methode, pfad, daten=None, idempotenz=None):
        self.aufrufe.append((methode, pfad, daten, idempotenz))
        if pfad == "/checkout/sessions" and methode == "POST":
            return {"id": "cs_test_1", "url": "https://checkout.stripe.com/c/cs_test_1"}
        if pfad.startswith("/checkout/sessions/"):
            return self.sitzungen[pfad.rsplit("/", 1)[1]]
        if pfad.startswith("/subscriptions/"):
            return self.abos[pfad.rsplit("/", 1)[1]]
        if pfad == "/billing_portal/sessions":
            return {"url": "https://billing.stripe.com/p/session_1"}
        if pfad.startswith("/charges/"):
            return self.zahlungen[pfad.rsplit("/", 1)[1]]
        raise AssertionError(f"unerwarteter Stripe-Aufruf {methode} {pfad}")


def _login(email: str) -> TestClient:
    client = TestClient(babu_web.app, base_url="https://testserver")
    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    r = client.post("/api/login", json={"email": email, "passwort": PASSWORT})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "ROLLEN", {})
    monkeypatch.setattr(babu_web, "PORTAL_ORIGIN", URSPRUNG)
    for name, wert in (("BABU_ABO", "1"), ("BABU_STRIPE_SCHLUESSEL", "rk_test_x"),
                       ("BABU_STRIPE_WEBHOOK_GEHEIMNIS", GEHEIM),
                       ("BABU_STRIPE_PREIS_SOLO", "price_solo"),
                       ("BABU_STRIPE_PREIS_SALON", "price_salon"),
                       ("BABU_STRIPE_PREIS_PLUS", "price_plus"),
                       ("BABU_STRIPE_STEUERSATZ", "txr_19")):
        monkeypatch.setenv(name, wert)
    monkeypatch.setenv("BABU_BETREIBER_MAIL", "nina@0711.io")
    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    post: list[tuple[str, str]] = []
    import postfach
    monkeypatch.setattr(postfach, "senden", lambda an, betreff, text, *, stempel: (
        post.append((an, betreff)) or (True, "ok")))
    stripe = FakeStripe()
    monkeypatch.setattr(stripe_api, "_rufen", stripe)

    for email, rolle in (("chef@0711.io", "admin"), ("kanzlei@afflek.de", "kanzlei"),
                         ("sonne@salon.de", "salon"), ("babs@salon.de", "salon")):
        babu_web.nutzer_anlegen(email, email.split("@")[0], "Salon", rolle,
                                passwort=PASSWORT, box=False)
    babu_web.nutzer_anlegen("team@salon.de", "Team", "Salon", "mitarbeit",
                            passwort=PASSWORT, box=False)
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE nutzer SET gehoert_zu='sonne@salon.de' WHERE email='team@salon.de'")
        kid = testmonat.direkt_kanzlei(c)
        mid = mandanten.mandant_anlegen(kid, "Salon Sonne", "sonne@salon.de",
                                        "SKR04", c=c)
        testmonat.setzen(mid, testmonat.ende_fuer_start(testmonat.heute()), c)
        c.execute("INSERT INTO ambassador (code, email, name, erstellt) VALUES "
                  "('BABS-1', 'babs@salon.de', 'Babs', '2026-10-01')")
        c.execute("INSERT INTO ambassador_salon (code, email, salon, eingelöst) "
                  "VALUES ('BABS-1', 'sonne@salon.de', 'Salon Sonne', "
                  "'2026-10-02T08:00:00Z')")
    meta = {"mandant_id": str(mid), "paket": "salon", "babu_origin": URSPRUNG}
    stripe.abos["sub_1"] = _abo(meta)
    yield {"mid": mid, "meta": meta, "stripe": stripe, "post": post,
           "sonne": _login("sonne@salon.de")}


def _abo(meta, status="active", ende=False, preis="price_salon", sid="sub_1"):
    return {"id": sid, "object": "subscription", "status": status,
            "customer": "cus_1", "cancel_at_period_end": ende,
            "cancel_at": 1796000000 if ende else None, "metadata": meta,
            "items": {"data": [{"price": {"id": preis},
                                "current_period_end": 1796000000}]}}


def _rechnung(rid, grund="subscription_create", basil=False, meta=None,
              preis="price_salon", bezahlt=9401):
    zeile = {"period": {"end": 1796000000}}
    if basil:
        zeile["pricing"] = {"price_details": {"price": preis}}
        verweis = {"parent": {"subscription_details": {"subscription": "sub_1",
                                                       "metadata": meta or {}}}}
    else:
        zeile["price"] = {"id": preis}
        verweis = {"subscription": "sub_1"}
    return {"id": rid, "object": "invoice", "customer": "cus_1",
            "billing_reason": grund, "amount_paid": bezahlt, "subtotal": 7900,
            "lines": {"data": [zeile]}, **verweis}


def _sitzung(meta, mid):
    return {"id": "cs_test_1", "object": "checkout.session", "mode": "subscription",
            "status": "complete", "subscription": "sub_1", "customer": "cus_1",
            "client_reference_id": str(mid), "metadata": meta}


_NR = iter(range(1, 10_000))


def _ev(typ, obj, eid=None, live=False):
    return {"id": eid or f"evt_{next(_NR)}", "type": typ, "livemode": live,
            "created": 1790000000, "data": {"object": obj}}


def _melden(ereignis, geheim=GEHEIM, kopf=None):
    rumpf = json.dumps(ereignis).encode()
    client = TestClient(babu_web.app, base_url="https://testserver")
    return client.post("/api/stripe/webhook", content=rumpf, headers={
        "Content-Type": "application/json",
        "Stripe-Signature": kopf if kopf is not None else stripe_api.signieren(rumpf, geheim)})


def _mandant(mid):
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        z = c.execute("SELECT abo_status, paket, test_bis, stripe_abo, stripe_kunde, "
                      "zahlungsfehler_seit, abo_ende, bezahlt_bis FROM mandant "
                      "WHERE id=?", (mid,)).fetchone()
    return dict(zip(("abo_status", "paket", "test_bis", "stripe_abo", "stripe_kunde",
                     "zahlungsfehler_seit", "abo_ende", "bezahlt_bis"), z))


def _provision():
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        buchungen = [tuple(z) for z in c.execute(
            "SELECT meilenstein, betrag, quelle, stripe_rechnung FROM ambassador_buchung "
            "ORDER BY id")]
        verdient = c.execute("SELECT verdient FROM ambassador WHERE code='BABS-1'"
                             ).fetchone()[0]
        salon = tuple(c.execute("SELECT meilenstein, verdienst FROM ambassador_salon"
                                ).fetchone() or ())
    return buchungen, verdient, salon


# ————— Salon: ansehen und abschließen —————

def test_abo_zeigt_pakete_und_stand(welt):
    d = welt["sonne"].get("/api/abo").json()
    assert d["an"] is True and d["bereit"] is True and d["testmodus"] is True
    assert [p["brutto_cent"] for p in d["pakete"]] == [4641, 9401, 17731]
    assert d["kann_abschliessen"] is True and d["zugang"]["grund"] == "test"


def test_mitarbeiterin_schliesst_nicht_ab(welt):
    assert _login("team@salon.de").get("/api/abo").status_code == 403


def test_ohne_direkt_mandant_kein_abo(welt):
    assert _login("babs@salon.de").get("/api/abo").status_code == 404


def test_checkout_braucht_zustimmung_und_paket(welt):
    s = welt["sonne"]
    assert s.post("/api/abo/checkout", json={"paket": "salon"}).status_code == 400
    assert s.post("/api/abo/checkout", json={"paket": "gold", "agb": True}).status_code == 400


def test_checkout_baut_die_sitzung_fuer_diesen_server(welt):
    r = welt["sonne"].post("/api/abo/checkout", json={"paket": "salon", "agb": True})
    assert r.status_code == 200, r.text
    assert r.json()["url"].startswith("https://checkout.stripe.com/")
    methode, pfad, daten, idem = welt["stripe"].aufrufe[-1]
    assert (methode, pfad) == ("POST", "/checkout/sessions")
    assert daten["client_reference_id"] == str(welt["mid"])
    assert daten["subscription_data"]["metadata"]["babu_origin"] == URSPRUNG
    assert daten["line_items"][0] == {"price": "price_salon", "quantity": 1,
                                      "tax_rates": ["txr_19"]}
    assert daten["customer_email"] == "sonne@salon.de"
    # Zahlarten nennt babu nicht selbst: Stripe zeigt, was im Konto aktiv ist.
    # Live war SEPA im (mit Camp45 geteilten) Konto nicht freigeschaltet, und
    # ein fest verlangtes `sepa_debit` ließ jede Bezahlseite scheitern (03.10.2026).
    assert "payment_method_types" not in daten
    assert idem.startswith(f"checkout-{welt['mid']}-salon-")
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert c.execute("SELECT COUNT(*) FROM audit_log WHERE aktion='abo_checkout'"
                         ).fetchone()[0] == 1


def test_checkout_verlangt_keine_stripe_agb_url_und_nennt_die_texte(welt):
    """Live 03.10.2026: Stripe lehnte jede Bezahlseite ab („You cannot collect
    consent to your terms of service unless a URL is set in the Stripe
    Dashboard“) — das Konto teilt babu mit Camp45, dort steht keine babu-AGB.
    Zugestimmt wird in babu (agb + Fassung); die Bezahlseite nennt die Texte."""
    r = welt["sonne"].post("/api/abo/checkout", json={"paket": "salon", "agb": True})
    assert r.status_code == 200, r.text
    _m, _p, daten, _i = welt["stripe"].aufrufe[-1]
    assert "consent_collection" not in daten
    hinweis = daten["custom_text"]["submit"]["message"]
    assert f"{URSPRUNG}/agb" in hinweis and f"{URSPRUNG}/datenschutz" in hinweis
    assert len(hinweis) <= 1200      # Grenze von Stripe für custom_text


def test_checkout_aus_ohne_schalter(welt, monkeypatch):
    monkeypatch.setenv("BABU_ABO", "0")
    r = welt["sonne"].post("/api/abo/checkout", json={"paket": "salon", "agb": True})
    assert r.status_code == 503 and "schreib uns" in r.json()["fehler"]


def test_live_schluessel_auf_der_dev_spur_rechnet_nicht_ab(welt, monkeypatch):
    monkeypatch.setenv("BABU_STRIPE_SCHLUESSEL", "rk_live_x")
    assert welt["sonne"].get("/api/abo").json()["bereit"] is False
    r = welt["sonne"].post("/api/abo/checkout", json={"paket": "salon", "agb": True})
    assert r.status_code == 503
    assert not welt["stripe"].aufrufe


def test_test_schluessel_im_betrieb_rechnet_nicht_ab(monkeypatch):
    monkeypatch.setenv("BABU_STRIPE_SCHLUESSEL", "rk_test_x")
    for n in ("WEBHOOK_GEHEIMNIS", "PREIS_SOLO", "PREIS_SALON", "PREIS_PLUS",
              "STEUERSATZ"):
        monkeypatch.setenv(f"BABU_STRIPE_{n}", "x")
    assert stripe_api.eingerichtet("https://mybabu.io") is False
    assert stripe_api.eingerichtet(URSPRUNG) is True


def test_zweites_abo_wird_abgelehnt(welt):
    assert _melden(_ev("checkout.session.completed",
                       _sitzung(welt["meta"], welt["mid"]))).status_code == 200
    r = welt["sonne"].post("/api/abo/checkout", json={"paket": "plus", "agb": True})
    assert r.status_code == 409


def test_kundenportal_erst_mit_abo(welt):
    assert welt["sonne"].post("/api/abo/portal").status_code == 409
    _melden(_ev("checkout.session.completed", _sitzung(welt["meta"], welt["mid"])))
    r = welt["sonne"].post("/api/abo/portal")
    assert r.status_code == 200 and r.json()["url"].startswith("https://billing.")


def test_bestaetigen_wartet_nicht_auf_den_webhook(welt):
    welt["stripe"].sitzungen["cs_test_1"] = _sitzung(welt["meta"], welt["mid"])
    r = welt["sonne"].post("/api/abo/bestaetigen", json={"session": "cs_test_1"})
    assert r.status_code == 200, r.text
    assert r.json()["abo_status"] == "aktiv"
    assert _mandant(welt["mid"])["test_bis"] is None


def test_bestaetigen_fremde_sitzung(welt):
    welt["stripe"].sitzungen["cs_test_2"] = dict(_sitzung(welt["meta"], 999),
                                                 id="cs_test_2")
    r = welt["sonne"].post("/api/abo/bestaetigen", json={"session": "cs_test_2"})
    assert r.status_code == 400
    assert _mandant(welt["mid"])["abo_status"] is None


# ————— Webhook: Wache —————

def test_webhook_falsche_signatur(welt):
    assert _melden(_ev("invoice.paid", {}), geheim="whsec_falsch").status_code == 400
    assert _melden(_ev("invoice.paid", {}), kopf="").status_code == 400


def test_webhook_ohne_einrichtung(welt, monkeypatch):
    monkeypatch.delenv("BABU_STRIPE_WEBHOOK_GEHEIMNIS")
    assert _melden(_ev("invoice.paid", {})).status_code == 503


def test_webhook_falscher_modus(welt):
    assert _melden(_ev("invoice.paid", {}, live=True)).status_code == 400


def test_webhook_unbekanntes_ereignis_ist_ok(welt):
    r = _melden(_ev("customer.created", {"id": "cus_9"}))
    assert r.status_code == 200 and r.json()["ergebnis"] == "ignoriert"


# ————— Der ganze Weg —————

def test_ganzer_weg_bis_gehalten(welt):
    mid = welt["mid"]
    assert _melden(_ev("checkout.session.completed",
                       _sitzung(welt["meta"], mid))).json()["ergebnis"] == "aktiv"
    m = _mandant(mid)
    assert m["abo_status"] == "aktiv" and m["paket"] == "salon"
    assert m["test_bis"] is None and m["stripe_abo"] == "sub_1"
    assert ("nina@0711.io", "Neues Abo: Salon Sonne") in welt["post"]

    erstes = _ev("invoice.paid", _rechnung("in_1"))
    assert _melden(erstes).json()["ergebnis"] == "monat_1"
    assert _provision() == ([("gezeichnet", 237, "stripe", "in_1")], 237,
                            ("gezeichnet", 237))
    # Stripe wiederholt — nichts ändert sich.
    assert _melden(erstes).json()["ergebnis"] == "schon_verarbeitet"
    assert _provision()[1] == 237

    _melden(_ev("invoice.paid", _rechnung("in_2", "subscription_cycle")))
    assert _provision()[1] == 237
    assert _melden(_ev("invoice.paid", _rechnung("in_3", "subscription_cycle"))
                   ).json()["ergebnis"] == "monat_3"
    buchungen, verdient, salon = _provision()
    assert [b[0] for b in buchungen] == ["gezeichnet", "gehalten"]
    assert verdient == 474 and salon == ("gehalten", 474)
    assert _mandant(mid)["bezahlt_bis"] == stripe_api.datum(1796000000)


def test_dieselbe_rechnung_ueber_zwei_ereignisse_zaehlt_einmal(welt):
    _melden(_ev("checkout.session.completed", _sitzung(welt["meta"], welt["mid"])))
    _melden(_ev("invoice.paid", _rechnung("in_1")))
    r = _melden(_ev("invoice.paid", _rechnung("in_1")))   # neue Ereignisnummer
    assert r.json()["ergebnis"] == "schon_bezahlt"
    assert _provision()[1] == 237


def test_rechnung_vor_checkout_im_neuen_format(welt):
    """Stripe hält keine Reihenfolge ein; ab „basil" steht das Abo unter parent."""
    r = _melden(_ev("invoice.paid", _rechnung("in_1", basil=True, meta=welt["meta"])))
    assert r.json()["ergebnis"] == "monat_1"
    m = _mandant(welt["mid"])
    assert m["abo_status"] == "aktiv" and m["stripe_abo"] == "sub_1"
    assert _provision()[1] == 237


def test_fremder_ursprung_wird_nicht_angewendet(welt):
    fremd = dict(welt["meta"], babu_origin="https://mybabu.io")
    welt["stripe"].abos["sub_1"] = _abo(fremd)
    assert _melden(_ev("invoice.paid", _rechnung("in_1", basil=True, meta=fremd))
                   ).json()["ergebnis"] == "kein_mandant"
    assert _melden(_ev("checkout.session.completed", _sitzung(fremd, welt["mid"]))
                   ).json()["ergebnis"] == "fremder_ursprung"
    assert _mandant(welt["mid"])["abo_status"] is None


def test_anteilige_rechnung_ist_kein_monat(welt):
    _melden(_ev("checkout.session.completed", _sitzung(welt["meta"], welt["mid"])))
    _melden(_ev("invoice.paid", _rechnung("in_1")))
    _melden(_ev("invoice.paid", _rechnung("in_u", "subscription_update", bezahlt=3500)))
    _melden(_ev("invoice.paid", _rechnung("in_2", "subscription_cycle")))
    assert _provision()[1] == 237          # in_u zählte nicht als Monat 2


def test_paketwechsel_vor_der_dritten_rechnung(welt):
    _melden(_ev("checkout.session.completed", _sitzung(welt["meta"], welt["mid"])))
    _melden(_ev("invoice.paid", _rechnung("in_1")))
    _melden(_ev("invoice.paid", _rechnung("in_2", "subscription_cycle")))
    _melden(_ev("invoice.paid", _rechnung("in_3", "subscription_cycle",
                                          preis="price_plus")))
    buchungen, verdient, _ = _provision()
    assert [(b[0], b[1]) for b in buchungen] == [("gezeichnet", 237), ("gehalten", 447)]
    assert _mandant(welt["mid"])["paket"] == "plus"


def test_ohne_ambassadorin_nur_das_abo(welt):
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("DELETE FROM ambassador_salon")
    _melden(_ev("checkout.session.completed", _sitzung(welt["meta"], welt["mid"])))
    assert _melden(_ev("invoice.paid", _rechnung("in_1"))).json()["ergebnis"] == "monat_1"
    assert _provision()[0] == []


# ————— Zahlungsfehler, Kündigung, Rücklastschrift —————

def test_zahlungsfehler_frist_und_erholung(welt):
    mid = welt["mid"]
    _melden(_ev("checkout.session.completed", _sitzung(welt["meta"], mid)))
    _melden(_ev("invoice.payment_failed", _rechnung("in_2", "subscription_cycle")))
    m = _mandant(mid)
    assert m["abo_status"] == "zahlung_offen"
    erster = m["zahlungsfehler_seit"]
    assert erster == testmonat.heute().isoformat()
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET zahlungsfehler_seit='2026-01-01' WHERE id=?", (mid,))
    # Der nächste Fehlversuch verlängert die Frist nicht.
    _melden(_ev("invoice.payment_failed", _rechnung("in_2", "subscription_cycle")))
    assert _mandant(mid)["zahlungsfehler_seit"] == "2026-01-01"
    d = welt["sonne"].get("/api/ich").json()
    assert d["zugang"]["stufe"] == "nur_lesen" and d["zugang"]["grund"] == "zahlung_offen"
    _melden(_ev("invoice.paid", _rechnung("in_2", "subscription_cycle")))
    m = _mandant(mid)
    assert m["abo_status"] == "aktiv" and m["zahlungsfehler_seit"] is None


def test_kuendigung_und_ende(welt):
    mid = welt["mid"]
    _melden(_ev("checkout.session.completed", _sitzung(welt["meta"], mid)))
    welt["stripe"].abos["sub_1"] = _abo(welt["meta"], ende=True)
    assert _melden(_ev("customer.subscription.updated", {"id": "sub_1"})
                   ).json()["ergebnis"] == "gekuendigt"
    assert _mandant(mid)["abo_ende"] == stripe_api.datum(1796000000)
    # Eine Zahlung in der Kündigungszeit macht sie nicht wieder „aktiv".
    _melden(_ev("invoice.paid", _rechnung("in_1")))
    assert _mandant(mid)["abo_status"] == "gekuendigt"
    ende = _abo(welt["meta"], status="canceled")
    assert _melden(_ev("customer.subscription.deleted", ende)).json()["ergebnis"] == "beendet"
    assert _mandant(mid)["abo_status"] == "beendet"


def test_neu_nach_ende(welt):
    mid = welt["mid"]
    _melden(_ev("checkout.session.completed", _sitzung(welt["meta"], mid)))
    _melden(_ev("invoice.paid", _rechnung("in_1")))
    _melden(_ev("customer.subscription.deleted", _abo(welt["meta"], status="canceled")))
    welt["stripe"].abos["sub_2"] = _abo(welt["meta"], sid="sub_2")
    neu = dict(_sitzung(welt["meta"], mid), subscription="sub_2", id="cs_test_9")
    assert _melden(_ev("checkout.session.completed", neu)).json()["ergebnis"] == "aktiv"
    assert _mandant(mid)["stripe_abo"] == "sub_2"
    # Die nächste Rechnung ist Monat 2 — kein zweites „gezeichnet".
    r = dict(_rechnung("in_9"), subscription="sub_2")
    assert _melden(_ev("invoice.paid", r)).json()["ergebnis"] == "monat_2"
    assert _provision()[1] == 237


def test_ruecklastschrift_storniert_die_provision(welt):
    _melden(_ev("checkout.session.completed", _sitzung(welt["meta"], welt["mid"])))
    _melden(_ev("invoice.paid", _rechnung("in_1")))
    welt["stripe"].zahlungen["ch_1"] = {"id": "ch_1", "invoice": "in_1"}
    r = _melden(_ev("charge.dispute.created", {"id": "dp_1", "charge": "ch_1"}))
    assert r.json()["ergebnis"] == "strittig"
    buchungen, verdient, salon = _provision()
    assert [(b[0], b[1]) for b in buchungen] == [("gezeichnet", 237),
                                                 ("storno_gezeichnet", -237)]
    assert verdient == 0 and salon[1] == 0
    # Eine zweite Meldung (Erstattung derselben Zahlung) storniert nicht noch einmal.
    _melden(_ev("charge.refunded", {"id": "ch_1", "refunded": True}))
    assert _provision()[1] == 0


def test_teilerstattung_aendert_nichts(welt):
    r = _melden(_ev("charge.refunded", {"id": "ch_1", "refunded": False}))
    assert r.json()["ergebnis"] == "teilerstattung_ignoriert"


# ————— Betreiber —————

def test_uebersicht_nur_fuer_den_betreiber(welt):
    _melden(_ev("checkout.session.completed", _sitzung(welt["meta"], welt["mid"])))
    _melden(_ev("invoice.paid", _rechnung("in_1")))
    assert _login("kanzlei@afflek.de").get("/api/abo/uebersicht").status_code == 403
    d = _login("chef@0711.io").get("/api/abo/uebersicht").json()
    assert d["modus"] == "test" and d["ereignis_fehler"] == 0
    (a,) = d["abos"]
    assert (a["salon"], a["abo_status"], a["bezahlte_monate"]) == ("Salon Sonne", "aktiv", 1)


def test_ein_gescheitertes_ereignis_bleibt_offen_und_wird_nachgeholt(welt, monkeypatch):
    import kern_abo
    echt = kern_abo._rechnung_bezahlt  # noqa: SLF001

    def kaputt(_):
        raise RuntimeError("Datenbank weg")
    monkeypatch.setattr(kern_abo, "_rechnung_bezahlt", kaputt)
    ev = _ev("invoice.paid", _rechnung("in_1", basil=True, meta=welt["meta"]))
    assert _melden(ev).status_code == 500
    monkeypatch.setattr(kern_abo, "_rechnung_bezahlt", echt)
    assert _melden(ev).json()["ergebnis"] == "monat_1"
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        z = c.execute("SELECT verarbeitet, fehler FROM stripe_ereignis").fetchone()
    assert z[0] and z[1] is None
