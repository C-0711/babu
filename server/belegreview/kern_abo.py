"""Abo per Stripe — Weitermachen, Kundenportal, Webhook (seit 03.10.2026).

Go-live-Plan Phase 2. Ein Salon aus „babu direkt" schließt nach (oder
während) seines Testmonats selbst ab: Paket wählen → Stripe Checkout
(SEPA-Lastschrift oder Karte) → zurück ins Portal. Zahlungsdaten ändern,
Rechnungen und Kündigung laufen über das Stripe-Kundenportal.

Was Stripe meldet, kommt über `/api/stripe/webhook` herein und wird hier in
die Mandantenzeile übersetzt (abo.py entscheidet daraus, wer voll arbeitet).
An der ersten und dritten bezahlten Monatsrechnung bucht provision.py die
Provision der Ambassadorin — genau einmal, auch wenn Stripe ein Ereignis
wiederholt oder der tägliche Lauf es nachholt.

Ablauf je Ereignis (Reihenfolge ist Absicht):
  1. `stripe_ereignis` einmal eintragen — schon verarbeitet → fertig.
  2. Bei Stripe nachfragen (Abo frisch holen) VOR dem Datenbankschloss.
  3. Alles Schreiben in EINEM `with bw._DB_LOCK, bw._db()`-Block.
  4. Audit und Mails NACH dem Block (das Schloss ist nicht wiedereintrittsfähig).
  5. Fehler → im Ereignis vermerken, 500 → Stripe versucht es erneut.

Schalter `BABU_ABO` (Standard aus): ohne ihn gibt es keine Weitermachen-
Wege; der Webhook nimmt trotzdem an, sobald Stripe eingerichtet ist.
"""
from __future__ import annotations

import json
import time

from fastapi import Request
from fastapi.responses import JSONResponse, Response

import abo
import audit
import provision
import stripe_api
import testmonat

_app = None

#: Stripe-Ereignisse, die babu abonniert (gleiche Liste im Stripe-Dashboard).
EREIGNISSE = (
    "checkout.session.completed", "checkout.session.async_payment_failed",
    "invoice.paid", "invoice.payment_failed",
    "customer.subscription.created", "customer.subscription.updated",
    "customer.subscription.deleted",
    "charge.dispute.created", "charge.refunded",
)

#: Rechnungen, die als bezahlter MONAT zählen. Anteilige Rechnungen beim
#: Paketwechsel (`subscription_update`) zählen nicht.
MONATS_GRUENDE = ("subscription_create", "subscription_cycle")

_MANDANT_SPALTEN = ("id", "name", "besitzer_un", "test_bis", "paket", "abo_status",
                    "stripe_kunde", "stripe_abo", "abo_seit", "bezahlt_bis",
                    "abo_ende", "zahlungsfehler_seit", "kanzlei_id")

NICHT_BEREIT = ("Weitermachen geht gerade nicht über die Seite — schreib uns "
                "kurz, dann richten wir es für dich ein.")


def setup(app, bw):
    """Der Kern reicht sich selbst herein — siehe kern_warteliste.setup."""
    global _app
    _app = app
    globals()["bw"] = bw
    globals()["app"] = app
    for methode, pfad, fn in _ROUTEN:
        getattr(app, methode.lower())(pfad)(fn)


# ---------------------------------------------------------------------------
# Kleinkram
# ---------------------------------------------------------------------------

def _heute() -> str:
    return testmonat.heute().isoformat()


def _zeile(c, mandant_id: int) -> dict | None:
    z = c.execute(f"SELECT {', '.join('m.' + s for s in _MANDANT_SPALTEN)} "
                  "FROM mandant m WHERE m.id=?", (mandant_id,)).fetchone()
    return dict(zip(_MANDANT_SPALTEN, z)) if z else None


def _ist_direkt(c, m: dict) -> bool:
    z = c.execute("SELECT name FROM kanzlei WHERE id=?", (m["kanzlei_id"],)).fetchone()
    return bool(z and z[0] == testmonat.DIREKT_NAME)


def _bereit() -> bool:
    return abo.an() and stripe_api.eingerichtet(bw.PORTAL_ORIGIN)


def _betreiber_mail() -> str:
    import os  # noqa: PLC0415
    return (os.environ.get("BABU_BETREIBER_MAIL", "").strip()
            or bw.SUPPORT_MAIL)


def _senden(an: str, betreff: str, text: str) -> None:
    if not an:
        return
    import postfach  # noqa: PLC0415
    try:
        ok, hinweis = postfach.senden(an, betreff, text,
                                      stempel=time.strftime("%Y%m%d-%H%M%S"))
        print(f"[abo] Mail an {an}: {hinweis}", flush=True)
    except Exception as ex:  # noqa: BLE001
        print(f"[abo] Mail an {an} fehlgeschlagen: {ex!r}", flush=True)


def _mein_mandant(un: str) -> tuple[dict | None, JSONResponse | None]:
    """Der Direkt-Mandant der Inhaberin. Mitarbeiterinnen schließen nicht ab."""
    n = bw.nutzer_holen(un)
    if n and n.get("gehoert_zu"):
        return None, JSONResponse({"fehler": "Das macht die Inhaberin des Salons."},
                                  status_code=403)
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        direkt = testmonat.direkt_mandant_von(un, c)
        m = _zeile(c, direkt[0]) if direkt else None
    if m is None:
        return None, JSONResponse({"fehler": "Für diesen Zugang gibt es hier kein Abo."},
                                  status_code=404)
    return m, None


def _abo_antwort(m: dict) -> dict:
    z = abo.zugang(m["test_bis"], m["abo_status"], m["abo_ende"],
                   m["zahlungsfehler_seit"], testmonat.heute())
    return {"an": abo.an(), "bereit": _bereit(),
            "testmodus": stripe_api.modus() == "test",
            "salon": m["name"], "paket": m["paket"], "abo_status": m["abo_status"],
            "bezahlt_bis": m["bezahlt_bis"], "abo_ende": m["abo_ende"],
            "test_bis": m["test_bis"], "zugang": z, "pakete": abo.preise(),
            "empfehlung": _empfehlung(m["besitzer_un"]),
            "kann_abschliessen": m["abo_status"] in (None, "beendet"),
            "kann_verwalten": bool(m["stripe_kunde"])}


def _empfehlung(besitzer: str) -> str:
    """Welches Paket passt laut Betriebsangaben (saloncheck.paket_empfehlung)?"""
    import saloncheck  # noqa: PLC0415
    try:
        return saloncheck.paket_empfehlung(bw.db_einstellungen(besitzer))["paket"]
    except Exception:  # noqa: BLE001
        return "salon"


async def _json(request: Request, grenze: int = 4 * 1024) -> dict | None:
    try:
        return json.loads(await bw.koerper_lesen(request, grenze))
    except Exception:  # noqa: BLE001
        return None


def _fassung(art: str) -> str:
    import recht  # noqa: PLC0415
    return recht.fassung(art)


# ---------------------------------------------------------------------------
# Salon: Abo ansehen, abschließen, verwalten
# ---------------------------------------------------------------------------

def api_abo(request: Request) -> Response:
    un, fehler = bw._api_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    m, fehler = _mein_mandant(un)
    if fehler:
        return fehler
    return JSONResponse(_abo_antwort(m))


async def api_abo_checkout(request: Request) -> Response:
    if not bw._origin_ok(request):  # noqa: SLF001
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    un, fehler = bw._api_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    m, fehler = _mein_mandant(un)
    if fehler:
        return fehler
    if not _bereit():
        return JSONResponse({"fehler": NICHT_BEREIT}, status_code=503)
    koerper = await _json(request)
    if koerper is None:
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    paket = str(koerper.get("paket", "")).strip()
    if paket not in abo.PAKETE:
        return JSONResponse({"fehler": "Bitte ein Paket wählen."}, status_code=400)
    if koerper.get("agb") is not True:
        return JSONResponse({"fehler": "Bitte den Nutzungsbedingungen zustimmen."},
                            status_code=400)
    if m["abo_status"] not in (None, "beendet"):
        return JSONResponse({"fehler": "Du hast schon ein Abo. Zahlungsdaten und "
                                       "Kündigung findest du unter „Abo verwalten“."},
                            status_code=409)
    ursprung = bw.PORTAL_ORIGIN.rstrip("/")
    meta = {"mandant_id": str(m["id"]), "paket": paket, "babu_origin": ursprung}
    daten = {
        "mode": "subscription",
        "line_items": [{"price": stripe_api.preis_id(paket), "quantity": 1,
                        "tax_rates": [stripe_api.steuersatz()]}],
        # Nur Karte (Entscheidung Auftraggeber 09.10.2026): ohne Klarna und
        # Link muss die Datenschutzerklärung keinen weiteren Dienst nennen.
        # Gilt nur für babus Bezahlseite — das mit Camp45 geteilte Konto
        # bleibt, wie es ist. (`sepa_debit` fest zu verlangen ließ live jede
        # Bezahlseite scheitern, solange SEPA im Konto aus ist, 03.10.2026.)
        "payment_method_types": ["card"],
        "client_reference_id": str(m["id"]),
        "metadata": meta,
        "subscription_data": {"metadata": meta},
        "billing_address_collection": "required",
        "tax_id_collection": {"enabled": True},
        # Keine `consent_collection`: Stripe verlangt dafür eine AGB-Adresse
        # im Konto, und das Konto teilt babu mit Camp45 — live lehnte Stripe
        # deshalb jede Bezahlseite ab (03.10.2026). Zugestimmt wird vorher in
        # babu (Pflichthaken `agb`, Fassung im Audit); hier stehen die Texte.
        "custom_text": {"submit": {"message": (
            f"Mit dem Abschluss gelten die [Nutzungsbedingungen]({ursprung}/agb) "
            f"und die [Datenschutzhinweise]({ursprung}/datenschutz) von babu. "
            "Monatlich kündbar zum Ende des bezahlten Monats; alles, was du "
            "erfasst hast, bleibt lesbar und exportierbar.")}},
        "locale": "de",
        "success_url": f"{ursprung}/portal#abo-danke/{{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{ursprung}/portal#abo",
    }
    if m["stripe_kunde"]:
        # Wer schon Kundin war (neu nach Ende): Name, Anschrift und
        # Steuernummer aus dem Checkout in den Kundendatensatz übernehmen —
        # ohne das lehnt Stripe Adress- und Steuernummernabfrage ab.
        daten["customer"] = m["stripe_kunde"]
        daten["customer_update"] = {"name": "auto", "address": "auto"}
    else:
        daten["customer_email"] = m["besitzer_un"]
    schluessel = f"checkout-{m['id']}-{paket}-{int(time.time() // 60)}"
    try:
        sitzung = await bw.run_in_threadpool(stripe_api.anlegen,
                                              "/checkout/sessions", daten, schluessel)
    except stripe_api.StripeFehler as ex:
        print(f"[abo] Checkout für Mandant {m['id']} abgelehnt: {ex}", flush=True)
        return JSONResponse({"fehler": NICHT_BEREIT}, status_code=502)
    audit.audit(un, "abo_checkout", mandant_id=str(m["id"]), paket=paket,
                agb=_fassung("agb"), datenschutz=_fassung("datenschutz"))
    return JSONResponse({"url": sitzung.get("url")})


async def api_abo_bestaetigen(request: Request) -> Response:
    """Zurück aus dem Checkout: die Sitzung selbst nachschlagen, damit die
    Dankeseite nicht auf den Webhook warten muss. Dieselbe Verarbeitung."""
    if not bw._origin_ok(request):  # noqa: SLF001
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    un, fehler = bw._api_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    m, fehler = _mein_mandant(un)
    if fehler:
        return fehler
    koerper = await _json(request) or {}
    sid = str(koerper.get("session", "")).strip()
    if not sid.startswith("cs_") or not stripe_api.schluessel():
        return JSONResponse({"fehler": "unbekannte Sitzung"}, status_code=400)
    try:
        sitzung = await bw.run_in_threadpool(stripe_api.holen,
                                              f"/checkout/sessions/{sid}")
    except stripe_api.StripeFehler:
        return JSONResponse({"fehler": "unbekannte Sitzung"}, status_code=400)
    if str(sitzung.get("client_reference_id")) != str(m["id"]):
        return JSONResponse({"fehler": "unbekannte Sitzung"}, status_code=400)
    if sitzung.get("status") == "complete":
        await bw.run_in_threadpool(_checkout_fertig, sitzung)
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        m = _zeile(c, m["id"])
    return JSONResponse(_abo_antwort(m))


async def api_abo_portal(request: Request) -> Response:
    if not bw._origin_ok(request):  # noqa: SLF001
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    un, fehler = bw._api_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    m, fehler = _mein_mandant(un)
    if fehler:
        return fehler
    if not m["stripe_kunde"] or not stripe_api.schluessel():
        return JSONResponse({"fehler": "Es gibt noch kein Abo zum Verwalten."},
                            status_code=409)
    try:
        sitzung = await bw.run_in_threadpool(
            stripe_api.anlegen, "/billing_portal/sessions",
            {"customer": m["stripe_kunde"],
             "return_url": f"{bw.PORTAL_ORIGIN.rstrip('/')}/portal#abo",
             "locale": "de"})
    except stripe_api.StripeFehler as ex:
        print(f"[abo] Kundenportal für Mandant {m['id']}: {ex}", flush=True)
        return JSONResponse({"fehler": NICHT_BEREIT}, status_code=502)
    return JSONResponse({"url": sitzung.get("url")})


def api_abo_uebersicht(request: Request) -> Response:
    """Betreiber: alle Abos mit Stand, offenen Zahlungen und Kündigungen."""
    un, fehler = bw._betreiber_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    heute = testmonat.heute()
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        zeilen = [dict(zip(_MANDANT_SPALTEN, z)) for z in c.execute(
            f"SELECT {', '.join('m.' + s for s in _MANDANT_SPALTEN)} FROM mandant m "
            "JOIN kanzlei k ON k.id = m.kanzlei_id WHERE k.name=? ORDER BY m.id",
            (testmonat.DIREKT_NAME,))]
        rechnungen = {r[0]: r[1] for r in c.execute(
            "SELECT mandant_id, COUNT(*) FROM abo_rechnung WHERE status='bezahlt' "
            "AND monat_nr IS NOT NULL GROUP BY mandant_id")}
        fehler_ev = c.execute("SELECT COUNT(*) FROM stripe_ereignis WHERE "
                              "verarbeitet IS NULL AND fehler IS NOT NULL").fetchone()[0]
    abos = []
    for m in zeilen:
        z = abo.zugang(m["test_bis"], m["abo_status"], m["abo_ende"],
                       m["zahlungsfehler_seit"], heute)
        abos.append({"id": m["id"], "salon": m["name"], "inhaberin": m["besitzer_un"],
                     "paket": m["paket"], "abo_status": m["abo_status"],
                     "test_bis": m["test_bis"], "abo_seit": m["abo_seit"],
                     "bezahlt_bis": m["bezahlt_bis"], "abo_ende": m["abo_ende"],
                     "zahlungsfehler_seit": m["zahlungsfehler_seit"],
                     "bezahlte_monate": rechnungen.get(m["id"], 0), "zugang": z})
    return JSONResponse({"abos": abos, "modus": stripe_api.modus(), "an": abo.an(),
                         "ereignis_fehler": fehler_ev})


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

async def api_stripe_webhook(request: Request) -> Response:
    """Stripe meldet sich. Ohne Anmeldung — allein die Signatur zählt."""
    import os  # noqa: PLC0415
    geheimnis = os.environ.get("BABU_STRIPE_WEBHOOK_GEHEIMNIS", "").strip()
    if not geheimnis or not stripe_api.schluessel():
        # 503: Stripe versucht es weiter, bis der Server eingerichtet ist.
        return JSONResponse({"fehler": "nicht eingerichtet"}, status_code=503)
    try:
        rumpf = await bw.koerper_lesen(request, 256 * 1024)
    except bw.KoerperZuGross:
        return JSONResponse({"fehler": "zu groß"}, status_code=413)
    if not stripe_api.signatur_pruefen(rumpf, request.headers.get("stripe-signature", ""),
                                       geheimnis):
        print("[abo] Webhook mit falscher Signatur abgewiesen", flush=True)
        return JSONResponse({"fehler": "Signatur"}, status_code=400)
    try:
        ereignis = stripe_api.ereignis_aus(rumpf)
    except ValueError:
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    if bool(ereignis.get("livemode")) == stripe_api.testmodus():
        print(f"[abo] Ereignis {ereignis.get('id')} im falschen Modus abgewiesen",
              flush=True)
        return JSONResponse({"fehler": "Modus"}, status_code=400)
    try:
        ergebnis = await bw.run_in_threadpool(verarbeiten, ereignis)
    except Exception as ex:  # noqa: BLE001
        print(f"[abo] Ereignis {ereignis.get('id')} gescheitert: {ex!r}", flush=True)
        return JSONResponse({"fehler": "Verarbeitung"}, status_code=500)
    return JSONResponse({"ok": True, "ergebnis": ergebnis})


def verarbeiten(ereignis: dict) -> str:
    """Ein Stripe-Ereignis genau einmal anwenden. Auch für den täglichen Lauf."""
    eid = str(ereignis.get("id") or "")
    typ = str(ereignis.get("type") or "")
    obj = (ereignis.get("data") or {}).get("object") or {}
    if not eid:
        return "ohne_id"
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        neu = c.execute("""INSERT INTO stripe_ereignis
                           (ereignis, typ, objekt, erstellt, empfangen)
                           VALUES (?,?,?,?,?) ON CONFLICT (ereignis) DO NOTHING""",
                        (eid, typ, str(obj.get("id") or ""),
                         stripe_api.datum(ereignis.get("created")),
                         bw._jetzt_iso())).rowcount  # noqa: SLF001
        if neu != 1:
            z = c.execute("SELECT verarbeitet FROM stripe_ereignis WHERE ereignis=?",
                          (eid,)).fetchone()
            if z and z[0]:
                return "schon_verarbeitet"
    try:
        ergebnis = _anwenden(typ, obj)
    except Exception as ex:
        with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
            c.execute("UPDATE stripe_ereignis SET fehler=? WHERE ereignis=?",
                      (repr(ex)[:300], eid))
        raise
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        c.execute("UPDATE stripe_ereignis SET verarbeitet=?, fehler=NULL WHERE ereignis=?",
                  (bw._jetzt_iso(), eid))  # noqa: SLF001
    return ergebnis


def _anwenden(typ: str, obj: dict) -> str:
    if typ == "checkout.session.completed":
        return _checkout_fertig(obj)
    if typ == "checkout.session.async_payment_failed":
        return _zahlung_fehlt(obj, rechnung=None)
    if typ == "invoice.paid":
        return _rechnung_bezahlt(obj)
    if typ == "invoice.payment_failed":
        return _zahlung_fehlt(obj, rechnung=obj)
    if typ in ("customer.subscription.created", "customer.subscription.updated"):
        return _abo_stand(obj, frisch=True)
    if typ == "customer.subscription.deleted":
        return _abo_stand(obj, frisch=False)
    if typ == "charge.dispute.created":
        return _rueckbuchung(obj.get("charge"), "strittig")
    if typ == "charge.refunded":
        if not obj.get("refunded"):
            return "teilerstattung_ignoriert"
        return _rueckbuchung(obj.get("id"), "erstattet")
    return "ignoriert"


def _meta_passt(meta: dict | None) -> bool:
    """Gehört ein Objekt zu DIESEM Server? Dev und Betrieb können sich ein
    Stripe-Testkonto teilen — dann trügen fremde Nummern die gleichen
    mandant_id wie hier."""
    return (meta or {}).get("babu_origin", "").rstrip("/") == bw.PORTAL_ORIGIN.rstrip("/")


def _mandant_fuer(c, *, abo_id: str | None = None, kunde: str | None = None,
                  meta: dict | None = None) -> dict | None:
    """Abo-Nummer, dann Kundennummer, dann (nur bei passendem Ursprung) die
    Metadaten. Fehlende Stripe-Nummern werden nachgetragen — so ist egal,
    welches Ereignis zuerst ankommt."""
    m = None
    if abo_id:
        z = c.execute("SELECT id FROM mandant WHERE stripe_abo=?", (abo_id,)).fetchone()
        m = _zeile(c, z[0]) if z else None
    if m is None and kunde:
        z = c.execute("SELECT id FROM mandant WHERE stripe_kunde=? ORDER BY id DESC",
                      (kunde,)).fetchone()
        m = _zeile(c, z[0]) if z else None
    if m is None and _meta_passt(meta) and str((meta or {}).get("mandant_id", "")).isdigit():
        m = _zeile(c, int(meta["mandant_id"]))
    if m is None:
        return None
    if abo_id and not m["stripe_abo"]:
        c.execute("UPDATE mandant SET stripe_abo=? WHERE id=?", (abo_id, m["id"]))
        m["stripe_abo"] = abo_id
    if kunde and not m["stripe_kunde"]:
        c.execute("UPDATE mandant SET stripe_kunde=? WHERE id=?", (kunde, m["id"]))
        m["stripe_kunde"] = kunde
    return m


def _abo_holen(abo_id: str | None) -> dict | None:
    if not abo_id:
        return None
    return stripe_api.holen(f"/subscriptions/{abo_id}")


def _ende(abo_obj: dict) -> str | None:
    if abo_obj.get("cancel_at_period_end") or abo_obj.get("cancel_at"):
        return stripe_api.datum(abo_obj.get("cancel_at")
                                or stripe_api.periodenende(abo_obj))
    if (abo_obj.get("status") or "") == "canceled":
        return stripe_api.datum(abo_obj.get("ended_at") or abo_obj.get("canceled_at"))
    return None


def _checkout_fertig(sitzung: dict) -> str:
    if sitzung.get("mode") != "subscription":
        return "kein_abo"
    abo_id = sitzung.get("subscription")
    if isinstance(abo_id, dict):
        abo_id = abo_id.get("id")
    abo_obj = _abo_holen(abo_id) or {}
    meta = sitzung.get("metadata") or abo_obj.get("metadata") or {}
    status = abo.status_aus_stripe(abo_obj.get("status") or "incomplete",
                                   bool(abo_obj.get("cancel_at_period_end")))
    paket = (stripe_api.paket_aus_preis(stripe_api.preis_des_abos(abo_obj))
             or (meta.get("paket") if meta.get("paket") in abo.PAKETE else None))
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        if not _meta_passt(meta):
            return "fremder_ursprung"
        m = _mandant_fuer(c, abo_id=abo_id, kunde=stripe_api.kunde(sitzung), meta=meta)
        if m is None:
            return "kein_mandant"
        erstes_mal = m["abo_seit"] is None or m["abo_status"] in (None, "beendet")
        # Ein abgeschlossener Checkout IST das laufende Abo dieses Betriebs —
        # auch wenn früher schon eins da war (neu nach Ende). Ein zweites
        # neben einem laufenden lässt der Checkout gar nicht zu (409).
        c.execute("""UPDATE mandant SET abo_status=?, paket=COALESCE(?, paket),
                     abo_seit=COALESCE(abo_seit, ?), test_bis=NULL, abo_ende=?,
                     stripe_abo=COALESCE(?, stripe_abo) WHERE id=?""",
                  (status, paket, _heute(), _ende(abo_obj), abo_id, m["id"]))
    if erstes_mal:
        _senden(_betreiber_mail(), f"Neues Abo: {m['name']}",
                f"{m['name']} ({m['besitzer_un']}) hat babu abgeschlossen: "
                f"Paket {abo.PAKETE.get(paket or '', {}).get('name', paket)}.\n")
        audit.audit("stripe", "abo_abgeschlossen", ziel_un=m["besitzer_un"],
                    mandant_id=str(m["id"]), paket=paket, status=status)
    return status


def _rechnung_bezahlt(rechnung: dict) -> str:
    abo_id = stripe_api.abo_der_rechnung(rechnung)
    meta = stripe_api.metadaten_der_rechnung(rechnung)
    if not meta and abo_id:
        meta = (_abo_holen(abo_id) or {}).get("metadata") or {}
    grund = rechnung.get("billing_reason")
    bezahlt = int(rechnung.get("amount_paid") or 0)
    zeilen = (rechnung.get("lines") or {}).get("data") or []
    periode_ende = ((zeilen[0].get("period") or {}).get("end") if zeilen else None)
    paket_rechnung = stripe_api.paket_aus_preis(stripe_api.preis_der_rechnung(rechnung))
    heute = _heute()
    buchung = None
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        m = _mandant_fuer(c, abo_id=abo_id, kunde=stripe_api.kunde(rechnung), meta=meta)
        if m is None:
            return "kein_mandant"
        paket = paket_rechnung or m["paket"]
        alt = c.execute("SELECT status FROM abo_rechnung WHERE rechnung=?",
                        (rechnung.get("id"),)).fetchone()
        if alt and alt[0] == "bezahlt":
            return "schon_bezahlt"
        monat_nr = None
        if grund in MONATS_GRUENDE and bezahlt > 0:
            monat_nr = 1 + c.execute(
                "SELECT COUNT(*) FROM abo_rechnung WHERE mandant_id=? AND "
                "status='bezahlt' AND monat_nr IS NOT NULL", (m["id"],)).fetchone()[0]
        werte = (m["id"], abo_id, grund, paket, int(rechnung.get("subtotal_excluding_tax")
                 or rechnung.get("subtotal") or 0), bezahlt, monat_nr, heute,
                 bw._jetzt_iso())  # noqa: SLF001
        if alt:
            c.execute("""UPDATE abo_rechnung SET mandant_id=?, abo=?, grund=?, paket=?,
                         netto_cent=?, brutto_cent=?, status='bezahlt', monat_nr=?,
                         bezahlt_am=?, zeit=? WHERE rechnung=?""",
                      werte + (rechnung.get("id"),))
        else:
            c.execute("""INSERT INTO abo_rechnung (mandant_id, abo, grund, paket,
                         netto_cent, brutto_cent, status, monat_nr, bezahlt_am, zeit,
                         rechnung) VALUES (?,?,?,?,?,?,'bezahlt',?,?,?,?)""",
                      werte + (rechnung.get("id"),))
        status = "gekuendigt" if m["abo_status"] == "gekuendigt" else "aktiv"
        c.execute("""UPDATE mandant SET abo_status=?, zahlungsfehler_seit=NULL,
                     bezahlt_bis=COALESCE(?, bezahlt_bis), paket=COALESCE(?, paket),
                     test_bis=NULL, abo_seit=COALESCE(abo_seit, ?) WHERE id=?""",
                  (status, stripe_api.datum(periode_ende), paket, heute, m["id"]))
        meilenstein = provision.meilenstein_fuer(monat_nr)
        if meilenstein:
            buchung = provision.buchen(
                c, email=m["besitzer_un"], meilenstein=meilenstein,
                betrag_eur=provision.betrag(paket), paket=paket, quelle="stripe",
                heute=heute, rechnung=rechnung.get("id"))
    if buchung and buchung["ok"]:
        import kern_ambassador  # noqa: PLC0415
        kern_ambassador.kaching_melden(buchung["code"], buchung["betrag"],
                                       kern_ambassador._salon_name(m["besitzer_un"]))  # noqa: SLF001
        audit.audit("stripe", "provision_gebucht", ziel_un=m["besitzer_un"],
                    mandant_id=str(m["id"]), code=buchung["code"],
                    meilenstein=meilenstein, betrag=buchung["betrag"],
                    rechnung=rechnung.get("id"))
    return f"monat_{monat_nr}" if monat_nr else "bezahlt"


def _zahlung_fehlt(obj: dict, rechnung: dict | None) -> str:
    abo_id = stripe_api.abo_der_rechnung(rechnung) if rechnung else obj.get("subscription")
    meta = (stripe_api.metadaten_der_rechnung(rechnung) if rechnung
            else obj.get("metadata")) or {}
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        m = _mandant_fuer(c, abo_id=abo_id, kunde=stripe_api.kunde(obj), meta=meta)
        if m is None:
            return "kein_mandant"
        if rechnung and rechnung.get("id"):
            alt = c.execute("SELECT status FROM abo_rechnung WHERE rechnung=?",
                            (rechnung["id"],)).fetchone()
            if alt is None:
                c.execute("""INSERT INTO abo_rechnung (rechnung, mandant_id, abo, grund,
                             status, zeit) VALUES (?,?,?,?,'fehlgeschlagen',?)""",
                          (rechnung["id"], m["id"], abo_id,
                           rechnung.get("billing_reason"), bw._jetzt_iso()))  # noqa: SLF001
            elif alt[0] != "bezahlt":
                c.execute("UPDATE abo_rechnung SET status='fehlgeschlagen' "
                          "WHERE rechnung=?", (rechnung["id"],))
        if m["abo_status"] == "beendet":
            return "schon_beendet"
        c.execute("""UPDATE mandant SET abo_status='zahlung_offen',
                     zahlungsfehler_seit=COALESCE(zahlungsfehler_seit, ?) WHERE id=?""",
                  (_heute(), m["id"]))
    return "zahlung_offen"


def _abo_stand(abo_obj: dict, frisch: bool) -> str:
    """Das Abo, wie Stripe es JETZT sieht — deshalb neu geholt: Ereignisse
    können in beliebiger Reihenfolge ankommen, der Ist-Stand nicht."""
    if frisch and abo_obj.get("id"):
        abo_obj = _abo_holen(abo_obj["id"]) or abo_obj
    status = abo.status_aus_stripe(abo_obj.get("status"),
                                   bool(abo_obj.get("cancel_at_period_end")
                                        or abo_obj.get("cancel_at")))
    paket = stripe_api.paket_aus_preis(stripe_api.preis_des_abos(abo_obj))
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        m = _mandant_fuer(c, abo_id=abo_obj.get("id"), kunde=stripe_api.kunde(abo_obj),
                          meta=abo_obj.get("metadata"))
        if m is None:
            return "kein_mandant"
        if m["stripe_abo"] and m["stripe_abo"] != abo_obj.get("id"):
            if m["abo_status"] not in (None, "beendet") or status == "beendet":
                # Ein ZWEITES Abo neben einem laufenden — oder das Ende eines
                # alten: nie still überschreiben (steht im Tagesbericht).
                print(f"[abo] Mandant {m['id']}: Abo {abo_obj.get('id')} neben "
                      f"{m['stripe_abo']} — nicht angewendet", flush=True)
                return "zweites_abo"
            # Neu nach Ende: das neue Abo ist ab jetzt das des Betriebs.
            c.execute("UPDATE mandant SET stripe_abo=? WHERE id=?",
                      (abo_obj.get("id"), m["id"]))
        if m["abo_status"] is None and status == "beendet":
            return "nie_aktiv"
        # Zahlt sie wieder (aktiv/läuft/gekündigt), endet die Frist.
        fehler_weg = status in ("aktiv", "zahlung_laeuft", "gekuendigt")
        c.execute(f"""UPDATE mandant SET abo_status=?, paket=COALESCE(?, paket),
                      abo_ende=?{', zahlungsfehler_seit=NULL' if fehler_weg else ''}
                      WHERE id=?""",
                  (status, paket, _ende(abo_obj), m["id"]))
    if status in ("gekuendigt", "beendet") and m["abo_status"] != status:
        audit.audit("stripe", f"abo_{status}", ziel_un=m["besitzer_un"],
                    mandant_id=str(m["id"]))
    return status


def _rechnung_der_zahlung(charge_id: str | None) -> str | None:
    """Zu welcher Rechnung gehört eine Zahlung? Alt: charge.invoice. Ab „basil"
    über die Rechnungszahlungen der PaymentIntent."""
    if not charge_id:
        return None
    charge = stripe_api.holen(f"/charges/{charge_id}")
    rechnung = charge.get("invoice")
    if isinstance(rechnung, dict):
        rechnung = rechnung.get("id")
    if rechnung:
        return rechnung
    pi = charge.get("payment_intent")
    if isinstance(pi, dict):
        pi = pi.get("id")
    if not pi:
        return None
    try:
        liste = stripe_api.holen("/invoice_payments",
                                 payment={"type": "payment_intent", "payment_intent": pi})
    except stripe_api.StripeFehler:
        return None
    for zahlung in liste.get("data") or []:
        r = zahlung.get("invoice")
        return r.get("id") if isinstance(r, dict) else r
    return None


def _rueckbuchung(charge_id: str | None, status: str) -> str:
    rechnung = _rechnung_der_zahlung(charge_id)
    if not rechnung:
        return "keine_rechnung"
    heute = _heute()
    storno = None
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        z = c.execute("SELECT mandant_id, monat_nr FROM abo_rechnung WHERE rechnung=?",
                      (rechnung,)).fetchone()
        if not z:
            return "rechnung_unbekannt"
        c.execute("UPDATE abo_rechnung SET status=? WHERE rechnung=?", (status, rechnung))
        m = _zeile(c, z[0])
        meilenstein = provision.meilenstein_fuer(z[1])
        if meilenstein and m:
            storno = provision.stornieren(c, email=m["besitzer_un"],
                                          meilenstein=meilenstein, heute=heute,
                                          rechnung=rechnung)
    if storno and storno["ok"]:
        audit.audit("stripe", "provision_storniert", ziel_un=m["besitzer_un"],
                    mandant_id=str(m["id"]), code=storno["code"],
                    meilenstein=meilenstein, betrag=storno["betrag"], rechnung=rechnung)
    return status


_ROUTEN = [
    ("GET", "/api/abo", api_abo),
    ("POST", "/api/abo/checkout", api_abo_checkout),
    ("POST", "/api/abo/bestaetigen", api_abo_bestaetigen),
    ("POST", "/api/abo/portal", api_abo_portal),
    ("GET", "/api/abo/uebersicht", api_abo_uebersicht),
    ("POST", "/api/stripe/webhook", api_stripe_webhook),
]
