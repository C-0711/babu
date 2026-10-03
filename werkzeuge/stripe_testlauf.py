#!/usr/bin/env python3
"""stripe_testlauf — der ganze Abo-Weg gegen Stripe im TESTMODUS (seit 03.10.2026).

Go-live-Plan, Verifikation „Dev-Lane E2E“: spielt drei Monate Abo in Minuten
durch — mit einer Stripe-Test-Uhr (test clock) — und prüft, was babu daraus
macht. Läuft IM Dev-Container (dort liegen Test-Schlüssel und Dev-Datenbank):

    docker exec babu-web-dev python /app/werkzeuge/stripe_testlauf.py
    docker exec babu-web-dev python /app/werkzeuge/stripe_testlauf.py \
        --fehlzahlung --iban DE62370400440532013001   # Lastschrift platzt

Weigert sich, wenn der Schlüssel kein Test-Schlüssel ist oder der Server
mybabu.io ist. Legt in der Dev-Datenbank einen Test-Salon „Testlauf <Zeit>“ mit
Ambassadorin an, bei Stripe einen Kunden an einer Test-Uhr mit einem
SEPA-Mandat über Stripes veröffentlichte Test-IBAN (Standard:
DE89370400440532013000 = Zahlung gelingt; Fehl- und Rückbuchungs-IBANs stehen
in Stripes Doku „Testing SEPA Direct Debit“), schließt ein Abo ab und dreht die
Uhr zweimal um einen Monat weiter.

Geprüft wird nach jedem Schritt: Abo-Status in babu, bezahlte Monate,
Provisionen (gezeichnet nach Monat 1, gehalten nach Monat 3) — und ob die
Ereignisse per Webhook ankamen. Fehlt ein Webhook, holt das Skript die
Ereignisse selbst (wie der tägliche Lauf) und sagt es dazu.

Rechte des Schlüssels: zusätzlich zu babus eigenen (siehe .env.beispiel)
Customers, Payment Methods, Setup Intents, Subscriptions schreiben und
Test Clocks — dafür am besten einen eigenen Test-Schlüssel nehmen.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
BELEGREVIEW = next((k for k in (WURZEL / "server" / "belegreview", WURZEL)
                    if (k / "babu_web.py").is_file()), WURZEL / "server" / "belegreview")
if str(BELEGREVIEW) not in sys.path:
    sys.path.insert(0, str(BELEGREVIEW))

import abo  # noqa: E402
import babu_web as bw  # noqa: E402
import kern_abo  # noqa: E402
import mandanten  # noqa: E402
import provision  # noqa: E402
import stripe_api  # noqa: E402
import testmonat  # noqa: E402

TEST_IBAN = "DE89370400440532013000"
MONAT_S = 31 * 86400


def sagen(text: str) -> None:
    print(f"[testlauf] {text}", flush=True)


def abbruch(text: str) -> None:
    sagen("ABBRUCH: " + text)
    sys.exit(2)


def warten(pruefen, frist_s: int, takt_s: float = 3.0):
    ende = time.time() + frist_s
    while time.time() < ende:
        ergebnis = pruefen()
        if ergebnis:
            return ergebnis
        time.sleep(takt_s)
    return None


def uhr_weiter(uhr: str, bis: int) -> None:
    stripe_api.anlegen(f"/test_helpers/test_clocks/{uhr}/advance", {"frozen_time": bis})
    if not warten(lambda: stripe_api.holen(f"/test_helpers/test_clocks/{uhr}")
                  .get("status") == "ready", 300):
        abbruch("Die Test-Uhr kam nicht zur Ruhe.")


def test_salon(paket: str) -> tuple[int, str, str]:
    """Salon (Direktkunde) + Ambassadorin in der Dev-Datenbank."""
    stempel = time.strftime("%Y%m%d%H%M%S")
    salon_mail = f"testlauf-{stempel}@babu.test"
    amb_mail = f"testlauf-amb-{stempel}@babu.test"
    code = f"TESTLAUF-{stempel}"
    bw.nutzer_anlegen(salon_mail, "Testlauf", f"Testlauf {stempel}", "salon", box=False)
    bw.nutzer_anlegen(amb_mail, "Ambassadorin Test", "", "salon", box=False)
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        kid = testmonat.direkt_kanzlei(c)
        mid = mandanten.mandant_anlegen(kid, f"Testlauf {stempel}", salon_mail, "SKR04", c=c)
        testmonat.setzen(mid, testmonat.ende_fuer_start(testmonat.heute()), c)
        c.execute("INSERT INTO ambassador (code, email, name, erstellt) VALUES (?,?,?,?)",
                  (code, amb_mail, "Ambassadorin Test", bw._jetzt_iso()))  # noqa: SLF001
        c.execute("INSERT INTO ambassador_salon (code, email, salon, eingelöst) "
                  "VALUES (?,?,?,?)", (code, salon_mail, f"Testlauf {stempel}",
                                       bw._jetzt_iso()))  # noqa: SLF001
    return mid, salon_mail, code


def stand(mid: int, code: str) -> dict:
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        m = c.execute("SELECT abo_status, paket, test_bis, stripe_abo FROM mandant "
                      "WHERE id=?", (mid,)).fetchone()
        monate = c.execute("SELECT COUNT(*) FROM abo_rechnung WHERE mandant_id=? AND "
                           "status='bezahlt' AND monat_nr IS NOT NULL", (mid,)).fetchone()[0]
        buchungen = [tuple(z) for z in c.execute(
            "SELECT meilenstein, betrag FROM ambassador_buchung WHERE code=? ORDER BY id",
            (code,))]
        ereignisse = c.execute("SELECT COUNT(*) FROM stripe_ereignis").fetchone()[0]
    return {"status": m[0], "paket": m[1], "test_bis": m[2], "abo": m[3],
            "monate": monate, "buchungen": buchungen, "ereignisse": ereignisse}


def nachholen(seit: int) -> int:
    """Ereignisse selbst holen — falls der Webhook der Dev-Spur fehlt."""
    seite = stripe_api.holen("/events", created={"gte": seit}, limit=100,
                             types=list(kern_abo.EREIGNISSE))
    neu = 0
    for ev in reversed(seite.get("data") or []):
        if kern_abo.verarbeiten(ev) != "schon_verarbeitet":
            neu += 1
    return neu


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Abo-Weg gegen Stripe im Testmodus")
    p.add_argument("--paket", default="salon", choices=sorted(abo.PAKETE))
    p.add_argument("--iban", default=TEST_IBAN, help="Stripes Test-IBAN (Standard: gelingt)")
    p.add_argument("--warten", type=int, default=240, help="Sekunden je Schritt")
    p.add_argument("--fehlzahlung", action="store_true",
                   help="erwartet, dass die Lastschrift platzt (Fehl-IBAN): keine Zahlung, "
                        "zahlung_offen/beendet, keine Provision")
    args = p.parse_args(argv)

    if not stripe_api.testmodus():
        abbruch("kein Test-Schlüssel in BABU_STRIPE_SCHLUESSEL — hier läuft nur der Testmodus.")
    if bw.PORTAL_ORIGIN.rstrip("/") == stripe_api.LIVE_URSPRUNG:
        abbruch("das ist mybabu.io — der Testlauf gehört auf die Dev-Spur.")
    if not stripe_api.eingerichtet(bw.PORTAL_ORIGIN):
        abbruch("Stripe ist hier nicht vollständig eingerichtet (Preise, Steuersatz, Webhook).")
    beginn = int(time.time())
    mid, salon_mail, code = test_salon(args.paket)
    sagen(f"Test-Salon Mandant {mid} ({salon_mail}), Ambassadorin {code}")
    meta = {"mandant_id": str(mid), "paket": args.paket,
            "babu_origin": bw.PORTAL_ORIGIN.rstrip("/")}

    uhr = stripe_api.anlegen("/test_helpers/test_clocks",
                             {"frozen_time": beginn, "name": f"babu {mid}"})["id"]
    kunde = stripe_api.anlegen("/customers", {"email": salon_mail, "test_clock": uhr,
                                              "name": f"Testlauf {mid}", "metadata": meta,
                                              "address": {"country": "DE"}})["id"]
    pm = stripe_api.anlegen("/payment_methods", {
        "type": "sepa_debit", "sepa_debit": {"iban": args.iban},
        "billing_details": {"name": f"Testlauf {mid}", "email": salon_mail}})["id"]
    stripe_api.anlegen("/setup_intents", {
        "customer": kunde, "payment_method": pm, "payment_method_types": ["sepa_debit"],
        "confirm": True, "usage": "off_session",
        "mandate_data": {"customer_acceptance": {"type": "offline"}}})
    abo_obj = stripe_api.anlegen("/subscriptions", {
        "customer": kunde, "items": [{"price": stripe_api.preis_id(args.paket)}],
        "default_tax_rates": [stripe_api.steuersatz()], "default_payment_method": pm,
        "payment_settings": {"payment_method_types": ["sepa_debit"]},
        "metadata": meta})
    # Was Checkout sonst täte: Kunde und Abo am Mandanten festmachen.
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET stripe_kunde=?, stripe_abo=? WHERE id=?",
                  (kunde, abo_obj["id"], mid))
    sagen(f"Stripe: Uhr {uhr}, Kunde {kunde}, Abo {abo_obj['id']} ({abo_obj.get('status')})")

    erwartet = provision.betrag(args.paket)
    fehler = 0
    if args.fehlzahlung:
        st = warten(lambda: (s := stand(mid, code))["status"] in ("zahlung_offen", "beendet")
                    and s, args.warten)
        neu = 0 if st else nachholen(beginn - 60)
        st = st or stand(mid, code)
        ok = st["status"] in ("zahlung_offen", "beendet") and st["monate"] == 0 \
            and st["buchungen"] == []
        sagen(f"Fehlzahlung: {'OK ' if ok else 'FEHLER'} status={st['status']} "
              f"monate={st['monate']} provision={st['buchungen']}"
              + (f" (nachgeholt: {neu} — Webhook der Dev-Spur prüfen!)" if neu else " via Webhook"))
        sagen(f"Ende: {'wie erwartet' if ok else 'Abweichung'}. Aufräumen: Test-Uhr {uhr} löschen.")
        return 0 if ok else 1
    for schritt, (monate, soll) in enumerate([(1, [("gezeichnet", erwartet)]),
                                              (2, [("gezeichnet", erwartet)]),
                                              (3, [("gezeichnet", erwartet),
                                                   ("gehalten", erwartet)])]):
        if schritt:
            uhr_weiter(uhr, beginn + schritt * MONAT_S + 3600)
            sagen(f"Uhr um {schritt} Monat(e) weitergedreht")
        st = warten(lambda: (s := stand(mid, code))["monate"] >= monate and s, args.warten)
        quelle = "Webhook"
        if not st:
            neu = nachholen(beginn - 60)
            quelle = (f"nachgeholt ({neu} Ereignisse) — Webhook der Dev-Spur prüfen!" if neu
                      else "Webhook (Zahlung kam in der Frist nicht an)")
            st = stand(mid, code)
        ok = st["monate"] >= monate and st["buchungen"] == soll and \
            st["status"] in ("aktiv", "zahlung_laeuft")
        fehler += 0 if ok else 1
        sagen(f"Monat {monate}: {'OK ' if ok else 'FEHLER'} status={st['status']} "
              f"monate={st['monate']} provision={st['buchungen']} via {quelle}")
        if not ok:
            break
    sagen(f"Ende: {'alles wie erwartet' if not fehler else f'{fehler} Abweichung(en)'}. "
          f"Aufräumen bei Stripe: Test-Uhr {uhr} löschen (räumt Kunde und Abo mit ab).")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
