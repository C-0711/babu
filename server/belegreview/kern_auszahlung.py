"""Auszahlung an Ambassadorinnen — Profil, Lauf, Gutschrift, Bankdatei (seit 03.10.2026).

Go-live-Plan Phase 3. Der Ablauf, wie Nina ihn erlebt:

    1. Vorschau      wer bekommt wie viel, wem fehlt noch etwas
    2. Lauf anlegen  je Ambassadorin eine Gutschrift (fortlaufende Nummer,
                     PDF) und EINE Bankdatei (SEPA-Sammelüberweisung)
    3. Bank          Datei ins Online-Banking von 0711 laden und freigeben
    4. Überwiesen    bestätigen — erst dann gilt das Geld als ausgezahlt, die
                     Ambassadorin bekommt Bescheid und sieht ihre Gutschrift
       (oder Verwerfen, solange nicht überwiesen: Nummern bleiben vergeben
       und als storniert dokumentiert, die Provisionen sind wieder offen)

Ausgezahlt wird, was bis zum Stichtag des letzten fälligen Laufs verdient
ist (Quartal, 15.01./04./07./10., ab 100 € — kern_ambassador), Storno
verrechnet, und nur an Ambassadorinnen mit vollständigem Profil. Wer noch
keine Kontodaten hat, wartet — das Geld bleibt offen und kommt im nächsten
Lauf mit.

Woher das Geld kommt und auf wessen Namen die Gutschrift läuft, steht in
der Umgebung (`.env`, nie im Repo):

    BABU_FIRMA_NAME, BABU_FIRMA_ANSCHRIFT („Straße|PLZ Ort"), BABU_FIRMA_USTID
    BABU_AUSZAHLUNG_NAME, BABU_AUSZAHLUNG_IBAN, BABU_AUSZAHLUNG_BIC (optional)
    BABU_PROVISION_KARENZ_TAGE   so viele Tage vor dem Stichtag muss eine
                                 Provision gebucht sein (Standard 0)
"""
from __future__ import annotations

import base64
import datetime as dt
import io
import json
import os
import re
import zipfile

from fastapi import Request
from fastapi.responses import JSONResponse, Response

import audit
import gutschrift
import onboarding
import provision
import sepa

_app = None

_PROFIL_SPALTEN = ("code", "kontoinhaber", "iban", "bic", "strasse", "plz", "ort",
                   "land", "steuerstatus", "steuernummer", "ust_id",
                   "zustimmung_am", "zustimmung_fassung", "geaendert")


def setup(app, bw):
    """Der Kern reicht sich selbst herein — siehe kern_warteliste.setup."""
    global _app
    _app = app
    globals()["bw"] = bw
    globals()["app"] = app
    for methode, pfad, fn in _ROUTEN:
        getattr(app, methode.lower())(pfad)(fn)


def _ka():
    import kern_ambassador  # noqa: PLC0415 — Familie, über babu_web schon geladen
    return kern_ambassador


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def firma() -> dict:
    return {"name": _env("BABU_FIRMA_NAME"),
            "anschrift": "\n".join(t.strip() for t in _env("BABU_FIRMA_ANSCHRIFT")
                                   .split("|") if t.strip()),
            "ust_id": _env("BABU_FIRMA_USTID")}


def schuldner() -> dict:
    return {"name": _env("BABU_AUSZAHLUNG_NAME") or _env("BABU_FIRMA_NAME"),
            "iban": _env("BABU_AUSZAHLUNG_IBAN"), "bic": _env("BABU_AUSZAHLUNG_BIC")}


def karenz() -> int:
    try:
        return max(0, int(_env("BABU_PROVISION_KARENZ_TAGE") or 0))
    except ValueError:
        return 0


def fassung() -> str:
    """Fingerabdruck der Ambassador-Vereinbarung, der zugestimmt wird."""
    import recht  # noqa: PLC0415
    return recht.fassung("ambassador")


def _ambassadorin(un: str, c) -> tuple | None:
    return c.execute("SELECT code, name, email FROM ambassador WHERE email=? AND aktiv=1",
                     (un,)).fetchone()


def profil_holen(c, code: str) -> dict | None:
    z = c.execute(f"SELECT {', '.join(_PROFIL_SPALTEN)} FROM ambassador_profil "
                  "WHERE code=?", (code,)).fetchone()
    return dict(zip(_PROFIL_SPALTEN, z)) if z else None


def fehlt(p: dict | None) -> list[str]:
    """Was zum Auszahlen noch fehlt — in Worten, die sie versteht."""
    if not p:
        return ["Kontodaten", "Anschrift", "Steuerangabe", "Zustimmung"]
    luecken = []
    if not (p.get("kontoinhaber") and p.get("iban")):
        luecken.append("Kontodaten")
    if not (p.get("strasse") and p.get("plz") and p.get("ort")):
        luecken.append("Anschrift")
    status = p.get("steuerstatus")
    if status not in gutschrift.STEUERSTATUS:
        luecken.append("Steuerangabe")
    elif status in ("klein", "ust") and not (p.get("steuernummer") or p.get("ust_id")):
        luecken.append("Steuernummer")
    if not p.get("zustimmung_am"):
        luecken.append("Zustimmung")
    return luecken


def _oeffentlich(p: dict | None) -> dict:
    """Das Profil, wie es ins Portal geht — die IBAN nur maskiert."""
    if not p:
        return {"vorhanden": False, "fehlt": fehlt(None)}
    return {"vorhanden": True, "kontoinhaber": p["kontoinhaber"],
            "iban": gutschrift.iban_maskiert(p["iban"] or ""),
            "strasse": p["strasse"], "plz": p["plz"], "ort": p["ort"],
            "steuerstatus": p["steuerstatus"], "steuernummer": p["steuernummer"],
            "ust_id": p["ust_id"], "zustimmung_am": p["zustimmung_am"],
            "fehlt": fehlt(p)}


# ---------------------------------------------------------------------------
# Die Ambassadorin: Profil und Gutschriften
# ---------------------------------------------------------------------------

def api_profil(request: Request) -> Response:
    un, fehler = bw._api_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        a = _ambassadorin(un, c)
        if not a:
            return JSONResponse({"fehler": "Du bist (noch) keine Ambassadorin."},
                                status_code=404)
        p = profil_holen(c, a[0])
    return JSONResponse({**_oeffentlich(p), "steuerstatus_wahl": gutschrift.STEUERSTATUS})


async def api_profil_speichern(request: Request) -> Response:
    if not bw._origin_ok(request):  # noqa: SLF001
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    un, fehler = bw._api_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    try:
        k = json.loads(await bw.koerper_lesen(request, 4 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    text = {f: str(k.get(f, "") or "").strip()[:120]
            for f in ("kontoinhaber", "iban", "strasse", "plz", "ort",
                      "steuerstatus", "steuernummer", "ust_id")}
    if not text["kontoinhaber"] or not text["strasse"] or not text["ort"]:
        return JSONResponse({"fehler": "Bitte Kontoinhaberin und Anschrift ausfüllen."},
                            status_code=400)
    if not re.fullmatch(r"\d{5}", text["plz"]):
        return JSONResponse({"fehler": "Die Postleitzahl hat fünf Ziffern."},
                            status_code=400)
    try:
        iban = onboarding.iban_pruefen(text["iban"])
    except onboarding.OnboardingFehler:
        return JSONResponse({"fehler": "Die IBAN stimmt nicht — am besten aus der "
                                       "Banking-App kopieren."}, status_code=400)
    status = text["steuerstatus"]
    if status not in gutschrift.STEUERSTATUS:
        return JSONResponse({"fehler": "Bitte sag uns, wie du steuerlich arbeitest."},
                            status_code=400)
    ust_id = text["ust_id"].replace(" ", "").upper()
    if ust_id and not re.fullmatch(r"DE\d{9}", ust_id):
        return JSONResponse({"fehler": "Eine deutsche USt-IdNr. ist DE und neun Ziffern."},
                            status_code=400)
    if status in ("klein", "ust") and not (text["steuernummer"] or ust_id):
        return JSONResponse({"fehler": "Bitte deine Steuernummer angeben."},
                            status_code=400)
    if k.get("zustimmung") is not True:
        return JSONResponse({"fehler": "Bitte der Vereinbarung und der Abrechnung "
                                       "per Gutschrift zustimmen."}, status_code=400)
    jetzt = bw._jetzt_iso()  # noqa: SLF001
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        a = _ambassadorin(un, c)
        if not a:
            return JSONResponse({"fehler": "Du bist (noch) keine Ambassadorin."},
                                status_code=404)
        alt = profil_holen(c, a[0])
        werte = (text["kontoinhaber"], iban, text["strasse"], text["plz"], text["ort"],
                 status, text["steuernummer"] or None, ust_id or None)
        if alt:
            c.execute("""UPDATE ambassador_profil SET kontoinhaber=?, iban=?, strasse=?,
                         plz=?, ort=?, steuerstatus=?, steuernummer=?, ust_id=?,
                         zustimmung_am=COALESCE(zustimmung_am, ?), zustimmung_fassung=?,
                         geaendert=? WHERE code=?""",
                      werte + (jetzt, fassung(), jetzt, a[0]))
        else:
            c.execute("""INSERT INTO ambassador_profil (kontoinhaber, iban, strasse, plz,
                         ort, steuerstatus, steuernummer, ust_id, zustimmung_am,
                         zustimmung_fassung, geaendert, code)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      werte + (jetzt, fassung(), jetzt, a[0]))
        neu = profil_holen(c, a[0])
    iban_neu = bool(alt and alt["iban"] and alt["iban"] != iban)
    audit.audit(un, "ambassador_profil", code=a[0], steuerstatus=status,
                iban_geaendert=iban_neu, fassung=fassung())
    if iban_neu:
        await bw.run_in_threadpool(
            _ka()._senden, un, "Deine Kontoverbindung bei babu wurde geändert",  # noqa: SLF001
                      f"Hallo {a[1]},\n\ndeine Kontoverbindung für die Provision ist "
                      f"jetzt {gutschrift.iban_maskiert(iban)}.\n\nWarst du das nicht? "
                      "Dann antworte bitte sofort auf diese Mail.\n\nLiebe Grüße\nbabu\n")
    return JSONResponse(_oeffentlich(neu))


def api_gutschrift_pdf(nr: str, request: Request) -> Response:
    un, fehler = bw._api_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    nr = nr.removesuffix(".pdf")
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        z = c.execute("SELECT x.pdf, x.status, a.email FROM ambassador_auszahlung x "
                      "JOIN ambassador a ON a.code = x.code WHERE x.gutschrift_nr=?",
                      (nr,)).fetchone()
    betreiber = bw.rolle(un) == "admin"
    if not z or not z[0] or (z[2] != un and not betreiber) \
            or (not betreiber and z[1] != "ueberwiesen"):
        return JSONResponse({"fehler": "Diese Gutschrift gibt es nicht."}, status_code=404)
    return Response(base64.b64decode(z[0]), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nr}.pdf"'})


def gutschriften_von(code: str, c) -> list[dict]:
    return [{"nr": z[0], "datum": z[1], "brutto_cent": z[2], "stichtag": z[3]}
            for z in c.execute("SELECT gutschrift_nr, datum, brutto_cent, stichtag "
                               "FROM ambassador_auszahlung WHERE code=? AND "
                               "status='ueberwiesen' ORDER BY datum DESC", (code,))]


# ---------------------------------------------------------------------------
# Der Betreiber: Vorschau, Lauf, Bankdatei, überwiesen
# ---------------------------------------------------------------------------

def vorschau(c, heute: dt.date) -> dict:
    """Wer bekommt im fälligen Lauf wie viel — und wer (noch) nicht, warum."""
    ka = _ka()
    lauf = ka.letzter_lauf(heute)
    stichtag = ka.stichtag(lauf)
    bis = (stichtag - dt.timedelta(days=karenz())).isoformat()
    zeilen = []
    for code, name, email in c.execute(
            "SELECT code, name, email FROM ambassador ORDER BY name").fetchall():
        posten = [dict(zip(("id", "datum", "salon", "meilenstein", "paket", "betrag"), b))
                  for b in c.execute(
                      "SELECT id, datum, salon, meilenstein, paket, betrag FROM "
                      "ambassador_buchung WHERE code=? AND auszahlung_id IS NULL AND "
                      "datum <= ? ORDER BY datum, id", (code, bis))]
        if not posten:
            continue
        netto = sum(int(b["betrag"]) for b in posten)
        p = profil_holen(c, code)
        luecken = fehlt(p)
        status = (p or {}).get("steuerstatus")
        ust = provision.ust_cent(netto * 100, status) if netto > 0 else 0
        grund = (None if netto >= ka.MINDEST_AUSZAHLUNG and not luecken else
                 f"unter {ka.MINDEST_AUSZAHLUNG} €" if netto < ka.MINDEST_AUSZAHLUNG
                 else "fehlt: " + ", ".join(luecken))
        zeilen.append({"code": code, "name": name, "email": email, "posten": posten,
                       "netto_cent": netto * 100, "ust_cent": ust,
                       "brutto_cent": netto * 100 + ust, "zahlbar": grund is None,
                       "grund": grund})
    laeufe = [dict(zip(("id", "status"), z)) for z in c.execute(
        "SELECT id, status FROM auszahlungslauf WHERE lauf=? AND status IN "
        "('erstellt','ueberwiesen')", (lauf.isoformat(),))]
    naechster = ka.naechster_lauf(heute + dt.timedelta(days=1))
    return {"lauf": lauf.isoformat(), "stichtag": stichtag.isoformat(),
            "naechster": naechster.isoformat(),
            "bis": bis, "zeilen": zeilen, "schon": laeufe,
            "summe_cent": sum(z["brutto_cent"] for z in zeilen if z["zahlbar"]),
            "konto_fehlt": not (schuldner()["iban"] and firma()["name"])}


def api_vorschau(request: Request) -> Response:
    un, fehler = bw._betreiber_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        v = vorschau(c, _ka()._heute())  # noqa: SLF001
    for z in v["zeilen"]:
        z["posten"] = len(z["posten"])
    return JSONResponse(v)


def _beleg(nr: str, heute: dt.date, lauf: dict, z: dict, p: dict) -> dict:
    # Leistungszeitraum: von der ältesten Provision im Lauf (auch eine, die
    # unter 100 € aus einem früheren Quartal mitkommt) bis zum Stichtag.
    von = min(str(b["datum"])[:10] for b in z["posten"])
    anschrift = f"{p['strasse']}\n{p['plz']} {p['ort']}"
    return {"nr": nr, "datum": heute.isoformat(), "von": von,
            "bis": lauf["stichtag"], "aussteller": firma(),
            "empfaengerin": {"name": p["kontoinhaber"], "anschrift": anschrift,
                             "steuerstatus": p["steuerstatus"],
                             "steuernummer": p["steuernummer"], "ust_id": p["ust_id"],
                             "iban": p["iban"]},
            "posten": [{"datum": b["datum"], "salon": b["salon"],
                        "meilenstein": b["meilenstein"], "paket": b["paket"],
                        "netto_cent": int(b["betrag"]) * 100} for b in z["posten"]],
            "netto_cent": z["netto_cent"], "ust_cent": z["ust_cent"],
            "brutto_cent": z["brutto_cent"], "zustimmung_am": p["zustimmung_am"]}


async def api_lauf_anlegen(request: Request) -> Response:
    if not bw._origin_ok(request):  # noqa: SLF001
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    un, fehler = bw._betreiber_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    s, f = schuldner(), firma()
    if not (s["iban"] and f["name"]):
        return JSONResponse({"fehler": "Das Auszahlungskonto von 0711 ist noch nicht "
                                       "eingetragen."}, status_code=409)
    heute = _ka()._heute()  # noqa: SLF001
    jetzt = bw._jetzt_iso()  # noqa: SLF001
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        v = vorschau(c, heute)
        if v["schon"]:
            return JSONResponse({"fehler": "Für diesen Lauf gibt es schon Gutschriften."},
                                status_code=409)
        zahlbar = [z for z in v["zeilen"] if z["zahlbar"]]
        if not zahlbar:
            return JSONResponse({"fehler": "Für diesen Lauf ist nichts auszuzahlen."},
                                status_code=409)
        lauf_id = c.execute("""INSERT INTO auszahlungslauf (lauf, stichtag, status,
                               erstellt, von) VALUES (?,?,'erstellt',?,?)""",
                            (v["lauf"], v["stichtag"], jetzt, un)).lastrowid
        zahlungen = []
        for z in zahlbar:
            p = profil_holen(c, z["code"])
            nr = gutschrift.nummer(c, heute.year)
            beleg = _beleg(nr, heute, v, z, p)
            blatt = gutschrift.pdf(beleg)
            aid = c.execute(
                """INSERT INTO ambassador_auszahlung (code, betrag, datum, stichtag, von,
                   lauf_id, gutschrift_nr, netto_cent, ust_cent, brutto_cent, beleg,
                   pdf, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'erstellt')""",
                (z["code"], z["netto_cent"] // 100, heute.isoformat(), v["stichtag"],
                 un, lauf_id, nr, z["netto_cent"], z["ust_cent"], z["brutto_cent"],
                 json.dumps(beleg, ensure_ascii=False),
                 base64.b64encode(blatt).decode())).lastrowid
            for b in z["posten"]:
                c.execute("UPDATE ambassador_buchung SET auszahlung_id=? WHERE id=?",
                          (aid, b["id"]))
            zahlungen.append({"e2e": nr, "betrag_cent": z["brutto_cent"],
                              "name": p["kontoinhaber"], "iban": p["iban"],
                              "zweck": f"babu {gutschrift.titel(p['steuerstatus'])} {nr}"})
        msg_id = f"BABU-{v['lauf']}-{lauf_id}"
        xml = sepa.pain001(msg_id=msg_id,
                           erstellt=dt.datetime.now().replace(microsecond=0),
                           ausfuehrung=max(heute, dt.date.fromisoformat(v["lauf"])),
                           schuldner=s, zahlungen=zahlungen).decode("utf-8")
        summe = sum(z["betrag_cent"] for z in zahlungen)
        c.execute("UPDATE auszahlungslauf SET xml=?, msg_id=?, anzahl=?, summe_cent=? "
                  "WHERE id=?", (xml, msg_id, len(zahlungen), summe, lauf_id))
    audit.audit(un, "auszahlungslauf_erstellt", lauf_id=str(lauf_id), lauf=v["lauf"],
                anzahl=len(zahlungen), summe_cent=summe)
    return JSONResponse({"ok": True, "id": lauf_id, "anzahl": len(zahlungen),
                         "summe_cent": summe})


def api_laeufe(request: Request) -> Response:
    un, fehler = bw._betreiber_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        laeufe = [dict(zip(("id", "lauf", "stichtag", "status", "anzahl", "summe_cent",
                            "erstellt", "ueberwiesen"), z)) for z in c.execute(
            "SELECT id, lauf, stichtag, status, anzahl, summe_cent, erstellt, ueberwiesen "
            "FROM auszahlungslauf ORDER BY id DESC LIMIT 12")]
        for l in laeufe:
            l["gutschriften"] = [dict(zip(("nr", "name", "brutto_cent", "status"), z))
                                 for z in c.execute(
                "SELECT x.gutschrift_nr, a.name, x.brutto_cent, x.status FROM "
                "ambassador_auszahlung x JOIN ambassador a ON a.code=x.code "
                "WHERE x.lauf_id=? ORDER BY x.gutschrift_nr", (l["id"],))]
    return JSONResponse({"laeufe": laeufe})


def _lauf(c, lauf_id: int) -> dict | None:
    z = c.execute("SELECT id, lauf, status, xml FROM auszahlungslauf WHERE id=?",
                  (lauf_id,)).fetchone()
    return dict(zip(("id", "lauf", "status", "xml"), z)) if z else None


def api_lauf_xml(lauf_id: int, request: Request) -> Response:
    un, fehler = bw._betreiber_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        l = _lauf(c, lauf_id)
    if not l or not l["xml"] or l["status"] == "verworfen":
        return JSONResponse({"fehler": "Diesen Lauf gibt es nicht."}, status_code=404)
    audit.audit(un, "auszahlungslauf_bankdatei", lauf_id=str(lauf_id))
    return Response(l["xml"].encode("utf-8"), media_type="application/xml",
                    headers={"Content-Disposition":
                             f'attachment; filename="babu-auszahlung-{l["lauf"]}.xml"'})


def api_lauf_zip(lauf_id: int, request: Request) -> Response:
    un, fehler = bw._betreiber_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        l = _lauf(c, lauf_id)
        blaetter = c.execute("SELECT gutschrift_nr, pdf FROM ambassador_auszahlung "
                             "WHERE lauf_id=?", (lauf_id,)).fetchall()
    if not l or not blaetter:
        return JSONResponse({"fehler": "Diesen Lauf gibt es nicht."}, status_code=404)
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        for nr, pdf in blaetter:
            z.writestr(f"{nr}.pdf", base64.b64decode(pdf))
    return Response(puffer.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition":
                             f'attachment; filename="babu-gutschriften-{l["lauf"]}.zip"'})


async def api_lauf_ueberwiesen(lauf_id: int, request: Request) -> Response:
    if not bw._origin_ok(request):  # noqa: SLF001
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    un, fehler = bw._betreiber_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    jetzt = bw._jetzt_iso()  # noqa: SLF001
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        l = _lauf(c, lauf_id)
        if not l or l["status"] != "erstellt":
            return JSONResponse({"fehler": "Dieser Lauf ist nicht offen."},
                                status_code=409)
        zeilen = c.execute("SELECT x.id, x.code, x.betrag, x.gutschrift_nr, x.brutto_cent, "
                           "a.email, a.name FROM ambassador_auszahlung x JOIN ambassador a "
                           "ON a.code=x.code WHERE x.lauf_id=?", (lauf_id,)).fetchall()
        for aid, code, betrag, *_ in zeilen:
            c.execute("UPDATE ambassador_auszahlung SET status='ueberwiesen' WHERE id=?",
                      (aid,))
            c.execute("UPDATE ambassador SET gezahlt = gezahlt + ? WHERE code=?",
                      (int(betrag), code))
        c.execute("UPDATE auszahlungslauf SET status='ueberwiesen', ueberwiesen=?, "
                  "ueberwiesen_von=? WHERE id=?", (jetzt, un, lauf_id))
    audit.audit(un, "auszahlungslauf_ueberwiesen", lauf_id=str(lauf_id),
                anzahl=len(zeilen))
    portal = bw.PORTAL_ORIGIN.rstrip("/") + "/portal"
    for _, _, _, nr, brutto, email, name in zeilen:
        betrag = f"{brutto / 100:.2f}".replace(".", ",")
        await bw.run_in_threadpool(
            _ka()._senden, email, f"Deine Provision ist unterwegs ({nr})",  # noqa: SLF001
                      f"Hallo {name},\n\nwir haben dir {betrag} € überwiesen. "
                      "In den nächsten Tagen ist das Geld auf "
                      f"deinem Konto.\n\nDeine Gutschrift {nr} liegt in babu in deinem "
                      f"Bereich:\n{portal}\n\nDanke, dass du babu weitersagst!\n\n"
                      "Liebe Grüße\nbabu\n")
    return JSONResponse({"ok": True, "anzahl": len(zeilen)})


async def api_lauf_verwerfen(lauf_id: int, request: Request) -> Response:
    if not bw._origin_ok(request):  # noqa: SLF001
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    un, fehler = bw._betreiber_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        l = _lauf(c, lauf_id)
        if not l or l["status"] != "erstellt":
            return JSONResponse({"fehler": "Nur ein noch nicht überwiesener Lauf lässt "
                                           "sich verwerfen."}, status_code=409)
        ids = [z[0] for z in c.execute("SELECT id FROM ambassador_auszahlung WHERE "
                                       "lauf_id=?", (lauf_id,))]
        for aid in ids:
            c.execute("UPDATE ambassador_buchung SET auszahlung_id=NULL WHERE "
                      "auszahlung_id=?", (aid,))
            c.execute("UPDATE ambassador_auszahlung SET status='storniert' WHERE id=?",
                      (aid,))
        c.execute("UPDATE auszahlungslauf SET status='verworfen' WHERE id=?", (lauf_id,))
    audit.audit(un, "auszahlungslauf_verworfen", lauf_id=str(lauf_id))
    return JSONResponse({"ok": True})


_ROUTEN = [
    ("GET", "/api/ambassador/profil", api_profil),
    ("POST", "/api/ambassador/profil", api_profil_speichern),
    ("GET", "/api/ambassador/gutschrift/{nr}", api_gutschrift_pdf),
    ("GET", "/api/auszahlung/vorschau", api_vorschau),
    ("POST", "/api/auszahlung/lauf", api_lauf_anlegen),
    ("GET", "/api/auszahlung/laeufe", api_laeufe),
    ("GET", "/api/auszahlung/lauf/{lauf_id}/sepa.xml", api_lauf_xml),
    ("GET", "/api/auszahlung/lauf/{lauf_id}/gutschriften.zip", api_lauf_zip),
    ("POST", "/api/auszahlung/lauf/{lauf_id}/ueberwiesen", api_lauf_ueberwiesen),
    ("POST", "/api/auszahlung/lauf/{lauf_id}/verwerfen", api_lauf_verwerfen),
]
