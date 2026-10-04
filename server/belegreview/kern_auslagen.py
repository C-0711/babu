"""Auslagen der Mitarbeiterinnen — Einreichen, Freigabe, Erstattung (seit 04.10.2026).

babu Expenses D1, Spezifikation docs/superpowers/specs/2026-10-04-expenses-d1-design.md.
Eine Auslage ist ein normaler Beleg mit der Beiakte `review/<stamm>.auslage.json`,
Erstattungen liegen unter `auslagen/erstattungen/`. Die reine Rechnung steht in
`auslagen.py`; dieses Modul hängt sich per `setup(app, bw)` an den Kern.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

import audit
import auslagen as al
import box as bx
import boxschreiber

bw = None   # der Kern, gesetzt von setup()
ERSTATTUNGEN = "auslagen/erstattungen"
_SCHLOSS = threading.Lock()
_SCHLOESSER: dict[str, threading.Lock] = {}


class KeineAuslage(Exception):
    """Diese Auslage gibt es nicht — oder nicht für diese Anfrage."""


def setup(app, kern):
    """Der Kern reicht sich selbst herein — siehe kern_bank.setup."""
    global bw
    bw = kern
    for methode, pfad, fn in _ROUTEN:
        getattr(app, methode.lower())(pfad)(fn)


def _fehler(text: str, code: int) -> JSONResponse:
    return JSONResponse({"fehler": text}, status_code=code)


def _schloss() -> threading.Lock:
    schluessel = str(bw._box().store)  # noqa: SLF001
    with _SCHLOSS:
        return _SCHLOESSER.setdefault(schluessel, threading.Lock())


def _frisch() -> None:
    """Den Lesespiegel nachziehen, bevor unter dem Schloss gelesen wird.

    Gesamtprüfung I5: im Modus `klon` las ein zweiter Klick sonst den alten
    Stand — dieselbe Kennung oder verwaiste Reservierungen. Im Modus `store`
    gibt es nichts nachzuziehen."""
    bx.lesestand_holen(bw._box(), sofort=True, warten=True)  # noqa: SLF001


def _pfad(stamm: str) -> str:
    return f"review/{stamm}.auslage.json"


def _als_bytes(d: dict) -> bytes:
    return json.dumps(d, ensure_ascii=False, indent=1).encode()


def _lesen(stamm: str) -> dict | None:
    if not bw.NAME_RE.match(stamm):
        return None
    return al.laden(bw.git_show(_pfad(stamm)))


def _schreiben(dateien: dict[str, bytes], nachricht: str, un: str) -> str:
    commit = boxschreiber.schreiben(bw._box(), dateien, None, nachricht, un)  # noqa: SLF001
    with bw._box().index_schloss:  # noqa: SLF001
        bw._box().invalidieren()  # noqa: SLF001
    return commit


def _aendern(stamm: str, un: str, schritt, nachricht: str) -> dict:
    """Beiakte lesen, Schritt rechnen, schreiben — unter dem Schloss der Box."""
    with _schloss():
        _frisch()
        a = _lesen(stamm)
        if a is None:
            raise KeineAuslage(stamm)
        neu = schritt(a)
        _schreiben({_pfad(stamm): _als_bytes(neu)}, nachricht, un)
    return neu


def _zeile(stamm: str, a: dict, eintrag: dict) -> dict:
    return {"stamm": stamm, "status": a["status"], "name": a.get("name"),
            "lieferant": eintrag.get("lieferant"), "datum": eintrag.get("datum"),
            "betrag": eintrag.get("brutto"), "grund": a.get("grund"),
            "eingereicht_am": a.get("eingereicht_am"), "kreditor": a.get("kreditor"),
            "erstattung": a.get("erstattung")}


# ————— Wer fragt? —————

def _mitarbeiterin(request: Request):
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return None, fehler
    if bw.rolle(un) != "mitarbeit":
        return None, _fehler("Das ist der Bereich der Mitarbeiterinnen.", 403)
    return un, None


def _inhaberin(request: Request):
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return None, fehler
    if bw.rolle(un) != "salon":
        return None, _fehler("Auslagen gibt die Inhaberin frei.", 403)
    return un, None


def _lesend(request: Request):
    """Inhaberin in ihrer Box; Kanzlei und Admin mit Mandantenkopf, nur lesen."""
    un, fehler = bw._api_wache(request)  # noqa: SLF001
    if fehler:
        return None, fehler
    if bw.darf_verwalten(un):
        return bw._verwalter_box_wache(request)  # noqa: SLF001
    return _inhaberin(request)


# ————— Die Mitarbeiterin —————

def api_meine(request: Request) -> Response:
    un, fehler = _mitarbeiterin(request)
    if fehler:
        return fehler
    idx = bw.index_aktuell()
    zeilen = [_zeile(s, a, idx["belege"].get(s) or {})
              for s, a in (idx.get("auslagen") or {}).items() if a["von"] == un]
    zeilen.sort(key=lambda z: z["eingereicht_am"] or "", reverse=True)
    offen = round(sum(z["betrag"] or 0 for z in zeilen
                      if z["status"] in ("eingereicht", "freigegeben")), 2)
    person = bw.team_person_von_zugang(un) or {}
    return JSONResponse({"auslagen": zeilen, "offen": offen,
                         "iban_da": bool(person.get("iban"))})


def _eigene(request: Request, stamm: str):
    un, fehler = _mitarbeiterin(request)
    if fehler:
        return None, None, fehler
    idx = bw.index_aktuell()
    a = (idx.get("auslagen") or {}).get(stamm)
    if a is None or a["von"] != un:
        return None, None, _fehler("Diese Auslage gibt es nicht.", 404)
    return un, (a, idx["belege"].get(stamm) or {}), None


def api_meine_eine(stamm: str, request: Request) -> Response:
    _, gefunden, fehler = _eigene(request, stamm)
    if fehler:
        return fehler
    a, eintrag = gefunden
    return JSONResponse(dict(_zeile(stamm, a, eintrag),
                             bild_url=f"/api/auslagen/meine/{stamm}/bild"))


def api_meine_bild(stamm: str, request: Request) -> Response:
    _, gefunden, fehler = _eigene(request, stamm)
    if fehler:
        return fehler
    _, eintrag = gefunden
    daten = bw.git_show(eintrag["datei"])
    if daten is None:
        return _fehler("Lesefehler", 500)
    typ = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
           ".pdf": "application/pdf", ".heic": "image/heic"}.get(
        "." + eintrag["datei"].rsplit(".", 1)[-1].lower(), "application/octet-stream")
    return Response(content=daten, media_type=typ,
                    headers={"Cache-Control": "private, max-age=31536000, immutable"})


def api_zurueckziehen(stamm: str, request: Request) -> Response:
    un, fehler = _mitarbeiterin(request)
    if fehler:
        return fehler

    def schritt(a: dict) -> dict:
        if a["von"] != un:
            raise KeineAuslage(stamm)
        return al.uebergang(a, "zurueckgezogen", von=un, am=bw._jetzt_iso())  # noqa: SLF001
    try:
        neu = _aendern(stamm, un, schritt, f"auslage zurückgezogen: {stamm}")
    except KeineAuslage:
        return _fehler("Diese Auslage gibt es nicht.", 404)
    except al.AuslageFehler as ex:
        return _fehler(str(ex), 409)
    except boxschreiber.SchreibFehler:
        return _fehler("Gerade nicht speicherbar — gleich noch einmal.", 503)
    return JSONResponse({"ok": True, "status": neu["status"]})


async def api_konto(request: Request) -> Response:
    un, fehler = _mitarbeiterin(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _fehler("JSON erwartet", 400)
    iban = al.iban_normal(body.get("iban"))
    if not al.iban_gueltig(iban):
        return _fehler("Die IBAN stimmt so nicht — bitte noch einmal prüfen.", 400)
    person = bw.team_person_von_zugang(un)
    if person is None:
        return _fehler("Für diesen Zugang gibt es keine Team-Zeile.", 409)
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        c.execute("UPDATE team SET iban=? WHERE zugang=? AND un=?",
                  (iban, un, person["salon"]))
    return JSONResponse({"ok": True, "iban_kurz": bw._iban_kurz(iban)})  # noqa: SLF001


STAND_FILTER = {"offen": ("eingereicht",),
                "zu_erstatten": ("freigegeben",),
                "erstattet": ("erstattet",),
                "alle": al.STAENDE}


def api_liste(request: Request, stand: str = "offen") -> Response:
    un, fehler = _lesend(request)
    if fehler:
        return fehler
    idx = bw.index_aktuell()
    erlaubt = STAND_FILTER.get(stand, STAND_FILTER["offen"])
    zeilen = [_zeile(s, a, idx["belege"].get(s) or {})
              for s, a in (idx.get("auslagen") or {}).items() if a["status"] in erlaubt]
    if stand == "zu_erstatten":
        zeilen = [z for z in zeilen if not z["erstattung"]]
    zeilen.sort(key=lambda z: (z["name"] or "", z["datum"] or ""))
    offene = sorted((e for e in (idx.get("erstattungen") or {}).values()
                     if e.get("status") == "erstellt"), key=lambda e: e["kennung"])
    # Alle Erstattungen, neueste zuerst — damit Bankdatei und Erstattungsbeleg
    # auch später erreichbar bleiben (Gesamtprüfung I4).
    alle = sorted((idx.get("erstattungen") or {}).values(),
                  key=lambda e: e["kennung"], reverse=True)[:50]
    return JSONResponse({"auslagen": zeilen, "erstattungen_offen": offene,
                         "erstattungen": alle,
                         "wartet": sum(1 for a in (idx.get("auslagen") or {}).values()
                                       if a["status"] == "eingereicht")})


def _kreditor_fuer(un: str, a: dict) -> str:
    """Die Kreditornummer der Mitarbeiterin — angelegt bei ihrer ersten Freigabe."""
    import datev_seite  # noqa: PLC0415
    import kreditoren as kr  # noqa: PLC0415
    person = bw.team_person_von_zugang(a["von"]) or {}
    name = person.get("name") or a.get("name") or a["von"]

    def rechnen(stand):
        return kr.mitarbeiterin(stand, name, a["von"], person.get("iban") or "",
                                un, bw._jetzt_iso())  # noqa: SLF001
    _, _, k = datev_seite._kreditoren_aendern(  # noqa: SLF001
        bw, un, rechnen, lambda k_: f"kreditor für Auslagen: {k_['nummer']} {k_['name']}")
    return k["nummer"]


def _entscheiden(request: Request, stamm: str, schritt_bauen, nachricht: str):
    un, fehler = _inhaberin(request)
    if fehler:
        return None, fehler
    try:
        neu = _aendern(stamm, un, schritt_bauen(un), nachricht)
    except KeineAuslage:
        return None, _fehler("Diese Auslage gibt es nicht.", 404)
    except al.AuslageFehler as ex:
        return None, _fehler(str(ex), 409)
    except boxschreiber.SchreibFehler:
        return None, _fehler("Gerade nicht speicherbar — gleich noch einmal.", 503)
    return neu, None


def api_freigeben(stamm: str, request: Request) -> Response:
    def bauen(un):
        def schritt(a):
            # Erst prüfen, dann den Kreditor anlegen — ein veralteter Klick auf
            # eine abgelehnte Auslage legt sonst einen Kreditor an.
            if a["status"] != "eingereicht":
                raise al.AuslageFehler("Das geht bei dieser Auslage gerade nicht.")
            eintrag = bw.index_aktuell()["belege"].get(stamm) or {}
            betrag = eintrag.get("brutto")
            if not isinstance(betrag, (int, float)) or betrag <= 0:
                raise al.AuslageFehler("Ohne Betrag lässt sich die Auslage nicht freigeben — "
                                       "bitte zuerst den Betrag nachtragen.")
            neu = al.uebergang(a, "freigegeben", von=un, am=bw._jetzt_iso(),  # noqa: SLF001
                               kreditor=_kreditor_fuer(un, a))
            # Bezahlt wird, was freigegeben wurde (Gesamtprüfung C2).
            neu.update(betrag=round(float(betrag), 2), lieferant=eintrag.get("lieferant"),
                       datum=eintrag.get("datum"))
            return neu
        return schritt
    neu, fehler = _entscheiden(request, stamm, bauen, f"auslage freigegeben: {stamm}")
    if fehler:
        return fehler
    betrag_text = f"{neu['betrag']:.2f}".replace(".", ",")
    _melden("freigegeben", [neu["von"]], "Auslage freigegeben",
            f"Deine Auslage {neu.get('lieferant') or 'Beleg'} ({betrag_text} €) ist freigegeben.")
    return JSONResponse({"ok": True, "status": neu["status"], "kreditor": neu["kreditor"]})


async def api_ablehnen(stamm: str, request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    return await run_in_threadpool(_ablehnen, stamm, request, body)


def _ablehnen(stamm: str, request: Request, body: dict) -> Response:
    def bauen(un):
        return lambda a: al.uebergang(a, "abgelehnt", von=un, am=bw._jetzt_iso(),  # noqa: SLF001
                                      grund=body.get("grund"))
    neu, fehler = _entscheiden(request, stamm, bauen, f"auslage abgelehnt: {stamm}")
    if fehler:
        return fehler
    _melden("abgelehnt", [neu["von"]], "Auslage abgelehnt",
            f"Deine Auslage {_betrag(stamm)[0]} wurde abgelehnt: {neu['grund']}.")
    return JSONResponse({"ok": True, "status": neu["status"]})


def api_zuruecknehmen(stamm: str, request: Request) -> Response:
    def bauen(un):
        def schritt(a):
            if (bw.index_aktuell()["belege"].get(stamm) or {}).get("status") == "exportiert":
                raise al.AuslageFehler("Diese Auslage ist schon übergeben.")
            return al.uebergang(a, "eingereicht", von=un, am=bw._jetzt_iso())  # noqa: SLF001
        return schritt
    neu, fehler = _entscheiden(request, stamm, bauen, f"freigabe zurückgenommen: {stamm}")
    if fehler:
        return fehler
    return JSONResponse({"ok": True, "status": neu["status"]})


def _erstattung_pfad(kennung: str, endung: str = "json") -> str:
    return f"{ERSTATTUNGEN}/{kennung}.{endung}"


def _erstattung_lesen(kennung: str) -> dict | None:
    if not al._KENNUNG.match(kennung):  # noqa: SLF001
        return None
    roh = bw.git_show(_erstattung_pfad(kennung))
    try:
        return json.loads(roh) if roh else None
    except ValueError:
        return None


def _naechste_freie(kennung: str) -> str:
    """Die erste Kennung ab `kennung`, deren Datei es noch nicht gibt (Prüfung I5)."""
    jahr, n = kennung[2:6], int(kennung.rsplit("-", 1)[1])
    while bw.git_show(_erstattung_pfad(kennung)) is not None:
        n += 1
        kennung = f"E-{jahr}-{n:03d}"
    return kennung


async def api_erstattung(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _fehler("JSON erwartet", 400)
    return await run_in_threadpool(_erstattung, request, body)


def _erstattung(request: Request, body: dict) -> Response:
    import sepa  # noqa: PLC0415
    import vordrucke  # noqa: PLC0415
    un, fehler = _inhaberin(request)
    if fehler:
        return fehler
    art = body.get("art")
    staemme = [str(s) for s in (body.get("staemme") or [])]
    datum = str(body.get("datum") or bw._jetzt_iso()[:10])[:10]  # noqa: SLF001
    if art not in ("ueberweisung", "bar") or not staemme:
        return _fehler("Bitte Auslagen und die Art der Erstattung wählen.", 400)
    einst = bw.db_einstellungen(bw.salon_von_aktiv(un))
    with _schloss():
        _frisch()
        idx = bw.index_aktuell()
        auslagen_ = {}
        for s in staemme:
            a = _lesen(s)
            if a is None or a["status"] != "freigegeben" or a.get("erstattung"):
                return _fehler("Eine der Auslagen ist nicht frei zum Erstatten — "
                               "bitte die Liste neu laden.", 409)
            # Bezahlt wird der freigegebene Betrag — hat sich der Beleg seither
            # geändert, braucht er eine neue Freigabe (Gesamtprüfung C2).
            frei = a.get("betrag")
            jetzt_ = (idx["belege"].get(s) or {}).get("brutto")
            if not isinstance(frei, (int, float)) or frei <= 0 or not isinstance(
                    jetzt_, (int, float)) or round(float(jetzt_), 2) != round(float(frei), 2):
                return _fehler(f"Der Betrag der Auslage von {a.get('name') or 'der Mitarbeiterin'} "
                               "hat sich seit der Freigabe geändert — bitte Freigabe "
                               "zurücknehmen und neu freigeben.", 409)
            auslagen_[s] = a
        kennung = _naechste_freie(al.naechste_kennung(list(idx.get("erstattungen") or {}),
                                                      int(datum[:4])))
        posten = [{"stamm": s, "kreditor": a["kreditor"], "name": a.get("name") or a["von"],
                   "von": a["von"],
                   "betrag": round(float(a["betrag"]), 2),
                   "text": f"{(idx['belege'].get(s) or {}).get('lieferant') or 'Beleg'} "
                           f"{(idx['belege'].get(s) or {}).get('datum') or ''}".strip()}
                  for s, a in auslagen_.items()]
        e = {"kennung": kennung, "art": art, "datum": datum,
             "status": "erstellt" if art == "ueberweisung" else "ausgezahlt",
             "posten": posten, "je_person": al.je_person(posten),
             "von": un, "am": bw._jetzt_iso(),  # noqa: SLF001
             "ueberwiesen_am": None, "ueberwiesen_von": None}
        dateien: dict[str, bytes] = {}
        if art == "ueberweisung":
            if not al.iban_gueltig(einst.get("iban")) or not einst.get("betrieb_name"):
                return _fehler("Für die Bankdatei fehlen Name und IBAN des Betriebs "
                               "(Einstellungen).", 409)
            zahlungen = []
            for p in e["je_person"]:
                iban = (bw.team_person_von_zugang(p["von"]) or {}).get("iban") or ""
                if not al.iban_gueltig(iban):
                    return _fehler(f"Für {p['name']} fehlt die IBAN — sie trägt sie in der "
                                   "App ein.", 409)
                zahlungen.append({"e2e": f"{kennung}-{p['kreditor']}",
                                  "betrag_cent": int(round(p["summe"] * 100)),
                                  "name": p["name"], "iban": iban,
                                  "zweck": al.verwendungszweck(p["name"], kennung)})
            try:
                dateien[_erstattung_pfad(kennung, "xml")] = sepa.pain001(
                    msg_id=kennung, erstellt=dt.datetime.now(),
                    ausfuehrung=dt.date.fromisoformat(datum),
                    schuldner={"name": einst["betrieb_name"],
                               "iban": al.iban_normal(einst["iban"]),
                               "bic": einst.get("bic") or None},
                    zahlungen=zahlungen)
            except ValueError as ex:
                return _fehler(f"Die Bankdatei ließ sich nicht bauen: {ex}", 409)
            neu = {s: al.reservieren(a, kennung) for s, a in auslagen_.items()}
        else:
            dateien[_erstattung_pfad(kennung, "pdf")] = vordrucke.erstattungsbeleg_pdf(
                e, {"betrieb_name": einst.get("betrieb_name") or "Salon"})
            neu = {s: al.uebergang(al.reservieren(a, kennung), "erstattet", von=un,
                                   am=e["am"], erstattung=kennung)
                   for s, a in auslagen_.items()}
        dateien[_erstattung_pfad(kennung)] = _als_bytes(e)
        for s, a in neu.items():
            dateien[_pfad(s)] = _als_bytes(a)
        try:
            _schreiben(dateien, f"erstattung {kennung} ({art})", un)
        except boxschreiber.SchreibFehler:
            return _fehler("Gerade nicht speicherbar — gleich noch einmal.", 503)
    audit.audit(un, "auslagen_erstattung", mandant_id=bw._mandant_fuers_log(),  # noqa: SLF001
                kennung=kennung, art=art, summe=round(sum(p["summe"] for p in e["je_person"]), 2))
    if art == "bar":
        for p in e["je_person"]:
            _melden("bar", [p["von"]], "Erstattung",
                    f"Deine Erstattung über {p['summe']:.2f} € wurde bar ausgezahlt."
                    .replace(".", ",", 1))
    return JSONResponse({"ok": True, "kennung": kennung, "status": e["status"],
                         "je_person": e["je_person"]})


def _erstattung_datei(kennung: str, request: Request, endung: str, typ: str) -> Response:
    un, fehler = _inhaberin(request)
    if fehler:
        return fehler
    if not al._KENNUNG.match(kennung):  # noqa: SLF001
        return _fehler("Diese Erstattung gibt es nicht.", 404)
    daten = bw.git_show(_erstattung_pfad(kennung, endung))
    if daten is None:
        return _fehler("Diese Datei gibt es nicht.", 404)
    return Response(content=daten, media_type=typ, headers={
        "Content-Disposition": f'attachment; filename="Auslagen_{kennung}.{endung}"'})


def api_bankdatei(kennung: str, request: Request) -> Response:
    return _erstattung_datei(kennung, request, "xml", "application/xml")


def api_erstattungsbeleg(kennung: str, request: Request) -> Response:
    return _erstattung_datei(kennung, request, "pdf", "application/pdf")


async def api_ueberwiesen(kennung: str, request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    return await run_in_threadpool(_ueberwiesen, kennung, request, body)


def _ueberwiesen(kennung: str, request: Request, body: dict) -> Response:
    un, fehler = _inhaberin(request)
    if fehler:
        return fehler
    am = str(body.get("am") or bw._jetzt_iso()[:10])[:10]  # noqa: SLF001
    with _schloss():
        _frisch()
        e = _erstattung_lesen(kennung)
        if e is None:
            return _fehler("Diese Erstattung gibt es nicht.", 404)
        if e["status"] != "erstellt":
            return _fehler("Diese Erstattung ist nicht mehr offen.", 409)
        e = dict(e, status="ueberwiesen", ueberwiesen_am=am, ueberwiesen_von=un)
        dateien = {_erstattung_pfad(kennung): _als_bytes(e)}
        for p in e["posten"]:
            a = _lesen(p["stamm"])
            if a is not None and a.get("erstattung") == kennung and a["status"] == "freigegeben":
                dateien[_pfad(p["stamm"])] = _als_bytes(
                    al.uebergang(a, "erstattet", von=un, am=bw._jetzt_iso(),  # noqa: SLF001
                                 erstattung=kennung))
        _schreiben(dateien, f"erstattung {kennung} überwiesen", un)
    audit.audit(un, "auslagen_ueberwiesen", mandant_id=bw._mandant_fuers_log(),  # noqa: SLF001
                kennung=kennung)
    for p in e["je_person"]:
        _melden("ueberwiesen", [p["von"]], "Erstattung",
                f"Deine Erstattung über {p['summe']:.2f} € ist unterwegs.".replace(".", ",", 1))
    return JSONResponse({"ok": True, "status": "ueberwiesen"})


def api_verwerfen(kennung: str, request: Request) -> Response:
    un, fehler = _inhaberin(request)
    if fehler:
        return fehler
    with _schloss():
        _frisch()
        e = _erstattung_lesen(kennung)
        if e is None:
            return _fehler("Diese Erstattung gibt es nicht.", 404)
        if e["status"] != "erstellt":
            return _fehler("Diese Erstattung ist nicht mehr offen.", 409)
        dateien = {_erstattung_pfad(kennung): _als_bytes(dict(e, status="verworfen"))}
        for p in e["posten"]:
            a = _lesen(p["stamm"])
            if a is not None:
                dateien[_pfad(p["stamm"])] = _als_bytes(al.reservierung_loesen(a, kennung))
        _schreiben(dateien, f"erstattung {kennung} verworfen", un)
    return JSONResponse({"ok": True, "status": "verworfen"})


_TOKEN_RE = re.compile(r"^[0-9a-f]{64,200}$")


def _geraete(uns: list[str]) -> list[dict]:
    if not uns:
        return []
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        zeilen = c.execute(
            f"SELECT token, umgebung, thema FROM push_geraet WHERE un IN ({','.join('?' * len(uns))})",
            tuple(uns)).fetchall()
    return [{"token": z[0], "umgebung": z[1], "thema": z[2]} for z in zeilen]


def _geraet_loeschen(token: str) -> None:
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        c.execute("DELETE FROM push_geraet WHERE token=?", (token,))


def _melden(ereignis: str, an: list[str], titel: str, text: str) -> None:
    """Push und Mail — im Hintergrund, nach dem Commit, nie blockierend."""
    def lauf():
        import postfach  # noqa: PLC0415
        import push  # noqa: PLC0415
        try:
            push.senden_an(_geraete(an), titel, text, _geraet_loeschen)
            for un_ in an:
                if "@" not in un_ or bw.db_einstellungen(un_).get("mail_auslagen") == "Nein":
                    continue
                postfach.senden(un_, f"babu · {titel}",
                                f"{text}\n\n{bw.PORTAL_ORIGIN.rstrip('/')}/portal#auslagen",
                                stempel=time.strftime("%Y%m%d-%H%M%S"))
        except Exception as ex:  # noqa: BLE001
            print(f"[auslagen] Nachricht {ereignis} nicht raus: {ex!r}", flush=True)
    threading.Thread(target=lauf, daemon=True).start()


def _betrag(stamm: str) -> tuple[str, str]:
    z = bw.index_aktuell()["belege"].get(stamm) or {}
    betrag = f"{float(z.get('brutto') or 0):.2f}".replace(".", ",")
    return z.get("lieferant") or "Beleg", betrag


def eingereicht_melden(un: str, lieferant: str | None, betrag) -> None:
    """Die Inhaberin erfährt von der neuen Auslage. Lieferant und Betrag kommen
    aus der Einschätzung — kein Indexbau auf dem Ereignis-Loop (Prüfung I2)."""
    person = bw.team_person_von_zugang(un) or {}
    text = (f"{float(betrag):.2f}".replace(".", ",") + " €"
            if isinstance(betrag, (int, float)) else "ohne Betrag")
    _melden("eingereicht", [bw.salon_von(un)], "Neue Auslage",
            f"{person.get('name') or un} hat eine Auslage eingereicht: "
            f"{lieferant or 'Beleg'}, {text}.")


async def api_push_geraet(request: Request) -> Response:
    import push  # noqa: PLC0415
    un, fehler = bw._api_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _fehler("JSON erwartet", 400)
    token = str(body.get("token") or "").strip().lower()
    umgebung = str(body.get("umgebung") or "")
    thema = str(body.get("thema") or "")
    if not _TOKEN_RE.match(token) or umgebung not in push.HOSTS or thema not in push.THEMEN:
        return _fehler("Dieses Gerät lässt sich so nicht anmelden.", 400)
    jetzt = bw._jetzt_iso()  # noqa: SLF001
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        c.execute("DELETE FROM push_geraet WHERE token=?", (token,))
        c.execute("INSERT INTO push_geraet (token, un, umgebung, thema, angelegt_am, zuletzt_am) "
                  "VALUES (?,?,?,?,?,?)", (token, un, umgebung, thema, jetzt, jetzt))
    return JSONResponse({"ok": True})


async def api_nachrichten(request: Request) -> Response:
    """Mails zu Auslagen an oder aus — für das eigene Konto, nicht den Betrieb."""
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _fehler("JSON erwartet", 400)
    bw.db_einstellung_setzen(un, "mail_auslagen", "Ja" if body.get("mail") else "Nein")
    return JSONResponse({"ok": True})


_ROUTEN = [
    ("POST", "/api/push/geraet", api_push_geraet),
    ("POST", "/api/auslagen/nachrichten", api_nachrichten),
    ("POST", "/api/auslagen/erstattung", api_erstattung),
    ("GET", "/api/auslagen/erstattung/{kennung}/bankdatei.xml", api_bankdatei),
    ("GET", "/api/auslagen/erstattung/{kennung}/beleg.pdf", api_erstattungsbeleg),
    ("POST", "/api/auslagen/erstattung/{kennung}/ueberwiesen", api_ueberwiesen),
    ("POST", "/api/auslagen/erstattung/{kennung}/verwerfen", api_verwerfen),
    ("GET", "/api/auslagen/meine", api_meine),
    ("GET", "/api/auslagen/meine/{stamm}", api_meine_eine),
    ("GET", "/api/auslagen/meine/{stamm}/bild", api_meine_bild),
    ("POST", "/api/auslagen/{stamm}/zurueckziehen", api_zurueckziehen),
    ("POST", "/api/auslagen/konto", api_konto),
    ("GET", "/api/auslagen", api_liste),
    ("POST", "/api/auslagen/{stamm}/freigeben", api_freigeben),
    ("POST", "/api/auslagen/{stamm}/ablehnen", api_ablehnen),
    ("POST", "/api/auslagen/{stamm}/zuruecknehmen", api_zuruecknehmen),
]
