"""Auslagen der Mitarbeiterinnen — Einreichen, Freigabe, Erstattung (seit 04.10.2026).

babu Expenses D1, Spezifikation docs/superpowers/specs/2026-10-04-expenses-d1-design.md.
Eine Auslage ist ein normaler Beleg mit der Beiakte `review/<stamm>.auslage.json`,
Erstattungen liegen unter `auslagen/erstattungen/`. Die reine Rechnung steht in
`auslagen.py`; dieses Modul hängt sich per `setup(app, bw)` an den Kern.
"""
from __future__ import annotations

import json
import threading

from fastapi import Request
from fastapi.responses import JSONResponse, Response

import auslagen as al
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


_ROUTEN = [
    ("GET", "/api/auslagen/meine", api_meine),
    ("GET", "/api/auslagen/meine/{stamm}", api_meine_eine),
    ("GET", "/api/auslagen/meine/{stamm}/bild", api_meine_bild),
    ("POST", "/api/auslagen/{stamm}/zurueckziehen", api_zurueckziehen),
    ("POST", "/api/auslagen/konto", api_konto),
]
