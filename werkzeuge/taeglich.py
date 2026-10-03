#!/usr/bin/env python3
"""taeglich — der tägliche Lauf von babu (seit 03.10.2026, Go-live-Plan Phase 4).

Läuft IM Container (dort liegen Datenbank, Box-Spiegel und Stripe-Schlüssel),
angestoßen vom Host-Cron:

    15 6 * * *  flock -n /tmp/babu-taeglich.lock docker exec babu-web \\
                python /app/werkzeuge/taeglich.py >> ~/logs/taeglich.log 2>&1

Vier Schritte, jeder für sich abgesichert — scheitert einer, laufen die
anderen trotzdem:

    stripe      verpasste Stripe-Ereignisse der letzten drei Tage nachholen und
                jedes laufende Abo frisch abgleichen (falls ein Webhook fehlte)
    salons      Erinnerungen an Salons: Testende in 7 und in 1 Tag, Zahlungsfrist
                an Tag 7 und 13 — nur mit Abo-Weg (BABU_ABO=1)
    ambassador  „Heute für dich": eine Mail an jede Ambassadorin, die heute etwas
                zu tun hat (dieselben Aufgaben wie im Portal), höchstens eine
    betreiber   „Heute für Nina": nur, wenn etwas anliegt

Jede Mail geht höchstens einmal am Tag: vor dem Versand wird (tag, aufgabe) in
`tageslauf` eingetragen; steht die Zeile schon, ist sie heute raus. Das hält
auch, wenn der Lauf zweimal angestoßen wird.

    taeglich.py            alles
    taeglich.py --probe    nur zeigen, nichts senden, nichts schreiben
    taeglich.py --nur stripe,betreiber
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
import traceback
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
# Im Repo liegt der Server unter server/belegreview; im Container ist dieser
# Ordner als /app/werkzeuge eingehängt und babu_web liegt direkt darüber.
BELEGREVIEW = next((k for k in (WURZEL / "server" / "belegreview", WURZEL)
                    if (k / "babu_web.py").is_file()), WURZEL / "server" / "belegreview")
if str(BELEGREVIEW) not in sys.path:
    sys.path.insert(0, str(BELEGREVIEW))

import abo  # noqa: E402
import babu_web as bw  # noqa: E402
import kern_abo  # noqa: E402
import kern_ambassador as ka  # noqa: E402
import postfach  # noqa: E402
import stripe_api  # noqa: E402
import testmonat  # noqa: E402

SCHRITTE = ("stripe", "salons", "ambassador", "betreiber")
NACHHOLEN_TAGE = 3


class Lauf:
    """Ein Lauf: heute, Probe ja/nein, und was er gesendet hat."""

    def __init__(self, probe: bool, heute: dt.date | None = None):
        self.probe = probe
        self.heute = heute or testmonat.heute()
        self.gesendet: list[tuple[str, str]] = []

    def log(self, text: str) -> None:
        print(f"[taeglich] {text}", flush=True)

    def einmal(self, aufgabe: str) -> bool:
        """Heute schon erledigt? Wenn nicht: jetzt eintragen (außer Probe)."""
        tag = self.heute.isoformat()
        with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
            if self.probe:
                return c.execute("SELECT 1 FROM tageslauf WHERE tag=? AND aufgabe=?",
                                 (tag, aufgabe)).fetchone() is None
            return c.execute("INSERT INTO tageslauf (tag, aufgabe, erledigt) "
                             "VALUES (?,?,?) ON CONFLICT (tag, aufgabe) DO NOTHING",
                             (tag, aufgabe, bw._jetzt_iso())).rowcount == 1  # noqa: SLF001

    def senden(self, aufgabe: str, an: str, betreff: str, text: str) -> None:
        if not an:
            return
        if not self.einmal(aufgabe):
            self.log(f"{aufgabe}: heute schon gesendet")
            return
        if self.probe:
            self.log(f"PROBE {aufgabe} → {an}: {betreff}")
            return
        ok, hinweis = postfach.senden(an, betreff, text,
                                      stempel=time.strftime("%Y%m%d-%H%M%S"))
        self.gesendet.append((an, betreff))
        self.log(f"{aufgabe} → {an}: {hinweis}")


def _portal() -> str:
    return bw.PORTAL_ORIGIN.rstrip("/") + "/portal"


def _de(wert: str | dt.date | None) -> str:
    if not wert:
        return ""
    tag = wert if isinstance(wert, dt.date) else dt.date.fromisoformat(str(wert)[:10])
    return tag.strftime("%d.%m.%Y")


# ---------------------------------------------------------------------------
# 1. Stripe nachholen
# ---------------------------------------------------------------------------

def schritt_stripe(lauf: Lauf) -> None:
    if not stripe_api.eingerichtet(bw.PORTAL_ORIGIN):
        lauf.log("stripe: nicht eingerichtet — übersprungen")
        return
    seit = int(time.time()) - NACHHOLEN_TAGE * 86400
    ereignisse, nach = [], None
    while True:
        daten = {"created": {"gte": seit}, "limit": 100,
                 "types": list(kern_abo.EREIGNISSE)}
        if nach:
            daten["starting_after"] = nach
        seite = stripe_api.holen("/events", **daten)
        ereignisse += seite.get("data") or []
        if not seite.get("has_more") or not seite.get("data"):
            break
        nach = seite["data"][-1]["id"]
    neu = 0
    for ev in reversed(ereignisse):          # Stripe liefert neueste zuerst
        if bool(ev.get("livemode")) == stripe_api.testmodus():
            continue
        if lauf.probe:
            continue
        try:
            if kern_abo.verarbeiten(ev) != "schon_verarbeitet":
                neu += 1
        except Exception as ex:  # noqa: BLE001
            lauf.log(f"stripe: Ereignis {ev.get('id')} gescheitert: {ex!r}")
    lauf.log(f"stripe: {len(ereignisse)} Ereignisse gesehen, {neu} nachgeholt")
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        abos = [z[0] for z in c.execute(
            "SELECT stripe_abo FROM mandant WHERE stripe_abo IS NOT NULL AND "
            "(abo_status IS NULL OR abo_status <> 'beendet')")]
    for abo_id in abos:
        if lauf.probe:
            continue
        try:
            kern_abo._abo_stand(stripe_api.holen(f"/subscriptions/{abo_id}"),  # noqa: SLF001
                                frisch=False)
        except Exception as ex:  # noqa: BLE001
            lauf.log(f"stripe: Abo {abo_id} nicht abgeglichen: {ex!r}")
    lauf.log(f"stripe: {len(abos)} laufende Abos abgeglichen")


# ---------------------------------------------------------------------------
# 2. Salons erinnern
# ---------------------------------------------------------------------------

def _direkt_mandanten() -> list[dict]:
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        return [dict(zip(("id", "name", "besitzer_un", "test_bis", "abo_status",
                          "zahlungsfehler_seit"), z)) for z in c.execute(
            "SELECT m.id, m.name, m.besitzer_un, m.test_bis, m.abo_status, "
            "m.zahlungsfehler_seit FROM mandant m JOIN kanzlei k ON k.id=m.kanzlei_id "
            "WHERE k.name=? ORDER BY m.id", (testmonat.DIREKT_NAME,))]


def schritt_salons(lauf: Lauf) -> None:
    if not abo.an():
        lauf.log("salons: Abo-Weg aus — keine Erinnerungen")
        return
    weg = _portal() + "#abo"
    for m in _direkt_mandanten():
        if m["abo_status"] is None and m["test_bis"]:
            st = testmonat.stand(m["test_bis"], lauf.heute)
            if st and not st["vorbei"] and st["tage_uebrig"] in (7, 1):
                n = st["tage_uebrig"]
                wann = "heute ist dein letzter Testtag" if n == 1 else "noch 7 Tage"
                lauf.senden(f"test:{m['id']}:{n}", m["besitzer_un"],
                            "Dein Testmonat bei babu: " + wann,
                            f"Hallo,\n\n{wann[0].upper() + wann[1:]} mit babu "
                            f"(bis {_de(m['test_bis'])}). Wenn du weitermachen "
                            f"willst, wählst du hier dein Paket:\n{weg}\n\n"
                            "Alles, was du erfasst hast, bleibt da — auch wenn du "
                            "nicht weitermachst, kannst du es weiter ansehen und "
                            "herunterladen.\n\nLiebe Grüße\nbabu\n")
        elif m["abo_status"] == "zahlung_offen" and m["zahlungsfehler_seit"]:
            seit = (lauf.heute - dt.date.fromisoformat(m["zahlungsfehler_seit"][:10])).days
            if seit in (7, 13):
                bis = dt.date.fromisoformat(m["zahlungsfehler_seit"][:10]) \
                    + dt.timedelta(days=abo.FRIST_TAGE)
                lauf.senden(f"frist:{m['id']}:{seit}", m["besitzer_un"],
                            "babu: Die letzte Zahlung ist nicht angekommen",
                            "Hallo,\n\ndie letzte Abbuchung für babu hat nicht "
                            f"geklappt. Bitte prüf bis zum {_de(bis)} deine "
                            f"Zahlungsdaten:\n{weg}\n\nDanach kannst du alles "
                            "weiter ansehen, aber nichts Neues erfassen.\n\n"
                            "Liebe Grüße\nbabu\n")


# ---------------------------------------------------------------------------
# 3. Ambassadorinnen: „Heute für dich"
# ---------------------------------------------------------------------------

def schritt_ambassador(lauf: Lauf) -> None:
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        alle = [tuple(z) for z in c.execute(
            "SELECT code, name, email FROM ambassador WHERE aktiv=1 AND "
            "COALESCE(heute_mail, 1)=1 ORDER BY code")]
    for code, name, email in alle:
        try:
            with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
                roh = ka._kontakt_zeilen(code, c)  # noqa: SLF001
            _, auftraege = ka._begleiter(code, name, roh)  # noqa: SLF001
        except Exception as ex:  # noqa: BLE001
            lauf.log(f"ambassador {code}: {ex!r}")
            continue
        if not auftraege:
            continue
        zeilen = "\n".join(
            f"• {a.get('person') or a.get('salon') or 'Ein Salon'}: {a['grund']} "
            f"→ „{a['knopf']}“" for a in auftraege)
        anzahl = len(auftraege)
        lauf.senden(f"heute:{code}", email,
                    f"Heute für dich: {anzahl} {'Salon' if anzahl == 1 else 'Salons'}",
                    f"Hallo {name},\n\nheute ist das hier dran:\n\n{zeilen}\n\n"
                    "Die Nachrichten sind schon geschrieben — öffne babu und "
                    f"tipp auf den Knopf:\n{_portal()}\n\n"
                    "Diese Mail kommt nur an Tagen, an denen etwas zu tun ist. "
                    "Abbestellen kannst du sie in babu in deinem Bereich.\n\n"
                    "Liebe Grüße\nbabu\n")


# ---------------------------------------------------------------------------
# 4. Betreiber: „Heute für Nina"
# ---------------------------------------------------------------------------

def bericht(heute: dt.date) -> list[str]:
    """Was der Betreiber heute wissen muss — leer, wenn nichts anliegt."""
    gestern = (heute - dt.timedelta(days=1)).isoformat()
    teile: list[str] = []
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        def audit_seit(*aktionen):
            frage = ",".join("?" * len(aktionen))
            return [tuple(z) for z in c.execute(
                f"SELECT aktion, ziel_un, details FROM audit_log WHERE aktion IN "
                f"({frage}) AND zeit >= ? ORDER BY id", (*aktionen, gestern))]
        neu = audit_seit("abo_abgeschlossen")
        if neu:
            teile.append("Neue Abos:\n" + "\n".join(f"• {z[1]}" for z in neu))
        weg = audit_seit("abo_gekuendigt", "abo_beendet")
        if weg:
            teile.append("Gekündigt oder beendet:\n" + "\n".join(
                f"• {z[1]} ({'gekündigt' if z[0] == 'abo_gekuendigt' else 'beendet'})"
                for z in weg))
        prov = audit_seit("provision_gebucht", "provision_storniert")
        if prov:
            teile.append("Provisionen:\n" + "\n".join(
                f"• {z[1]}: {'gebucht' if z[0] == 'provision_gebucht' else 'storniert'}"
                for z in prov))
        offen = [tuple(z) for z in c.execute(
            "SELECT name, besitzer_un, zahlungsfehler_seit FROM mandant "
            "WHERE abo_status='zahlung_offen' ORDER BY zahlungsfehler_seit")]
        if offen:
            zeilen = []
            for name, un, seit in offen:
                bis = dt.date.fromisoformat((seit or heute.isoformat())[:10]) \
                    + dt.timedelta(days=abo.FRIST_TAGE)
                zeilen.append(f"• {name} ({un}): Frist bis {_de(bis)}")
            teile.append("Zahlung nicht angekommen:\n" + "\n".join(zeilen))
        grenze = (heute - dt.timedelta(days=3)).isoformat()
        warten = [tuple(z) for z in c.execute(
            "SELECT e.person, e.salon, e.code, e.weiter_am FROM ambassador_einladung e "
            "WHERE e.weiter_am IS NOT NULL AND e.weiter_am <= ? AND NOT EXISTS ("
            "SELECT 1 FROM mandant m WHERE m.besitzer_un = e.email AND "
            "m.abo_status IN ('zahlung_laeuft','aktiv','gekuendigt'))", (grenze,))]
        if warten:
            teile.append("Wollte weitermachen, hat aber noch nicht abgeschlossen:\n"
                         + "\n".join(f"• {z[0] or z[1] or 'Salon'} (Code {z[2]}, "
                                     f"gemeldet {_de(z[3])})" for z in warten))
        fehler = c.execute("SELECT COUNT(*) FROM stripe_ereignis WHERE "
                           "verarbeitet IS NULL AND fehler IS NOT NULL").fetchone()[0]
        if fehler:
            teile.append(f"Zahlungsmeldungen mit Fehler: {fehler} — bitte ansehen.")
        regs = c.execute("SELECT COUNT(*) FROM registrierungen WHERE status='neu'"
                         ).fetchone()[0]
        wl = c.execute("SELECT COUNT(*) FROM warteliste WHERE status='wartet'"
                       ).fetchone()[0]
        if regs or wl:
            teile.append(f"Warten auf dich: {wl} auf der Warteliste, {regs} Anfragen.")
        codes = [z[0] for z in c.execute("SELECT code FROM ambassador WHERE aktiv=1")]
        lauf_tag = ka.letzter_lauf(heute)
        faellig = []
        if (heute - lauf_tag).days <= 31:
            for code in codes:
                g = ka._geld(code, c)  # noqa: SLF001
                f = g.get("faelliger_lauf") or {}
                if f.get("auszahlbar"):
                    faellig.append((code, f["betrag"]))
        if faellig:
            teile.append(f"Auszahlungslauf vom {_de(lauf_tag)} fällig: "
                         + ", ".join(f"{c_} {b} €" for c_, b in faellig))
    return teile


def schritt_betreiber(lauf: Lauf) -> None:
    an = kern_abo._betreiber_mail()  # noqa: SLF001
    teile = bericht(lauf.heute)
    if not teile:
        lauf.log("betreiber: nichts anliegend")
        return
    lauf.senden("betreiber", an, f"Heute für dich — babu, {_de(lauf.heute)}",
                "Hallo Nina,\n\n" + "\n\n".join(teile)
                + f"\n\nAlles Weitere in der Verwaltung:\n{_portal()}#verwaltung\n")


# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--probe", action="store_true", help="nur zeigen, nichts senden")
    p.add_argument("--nur", default="", help="Komma-Liste: " + ",".join(SCHRITTE))
    args = p.parse_args(argv)
    nur = [s for s in args.nur.split(",") if s] or list(SCHRITTE)
    lauf = Lauf(probe=args.probe)
    lauf.log(f"Start {lauf.heute.isoformat()}{' (Probe)' if lauf.probe else ''}")
    fehler = 0
    for name in SCHRITTE:
        if name not in nur:
            continue
        try:
            globals()[f"schritt_{name}"](lauf)
        except Exception:  # noqa: BLE001
            fehler += 1
            lauf.log(f"{name} gescheitert:\n{traceback.format_exc()}")
    lauf.log(f"Ende — {len(lauf.gesendet)} Mails, {fehler} Fehler")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
