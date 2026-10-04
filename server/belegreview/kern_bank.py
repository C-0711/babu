"""Bank — Freigabe, Dateiimport und Kanzleiansicht (seit 04.10.2026).

Plan Kanzleiansicht, Schritte B1–B3. Dieses Modul hängt sich wie die
anderen Familien per `setup(app, bw)` an den Kern.

B1: Der Betrieb gibt seiner Kanzlei die Kontoumsätze zum LESEN frei — mit
Fassung des Texts (`recht.BANK_FREIGABE`), widerrufbar, nachvollziehbar im
Audit-Log. Die Kanzlei kann anfragen; der Betrieb bekommt dann eine Mail.
Ob die Freigabe schon gebraucht wird, entscheidet der Schalter
`BABU_BANK_FREIGABE` (siehe `bankrecht`); die Freigabe selbst lässt sich
auch vorher schon erteilen.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from fastapi import Request
from fastapi.responses import JSONResponse, Response

import audit
import bankrecht
import mandanten
import recht

bw = None   # der Kern, gesetzt von setup()

#: Wie oft eine Kanzlei höchstens anfragt: einmal am Tag.
ANFRAGE_ABSTAND = timedelta(hours=24)


def setup(app, kern):
    """Der Kern reicht sich selbst herein — siehe kern_warteliste.setup."""
    global bw
    bw = kern
    for methode, pfad, fn in _ROUTEN:
        getattr(app, methode.lower())(pfad)(fn)


def _fehler(text: str, code: int) -> JSONResponse:
    return JSONResponse({"fehler": text}, status_code=code)


def _kontext(request: Request):
    """Angemeldet, Betrieb bekannt — und ob eine Kanzlei fragt."""
    un, fehler = bw._api_wache(request)  # noqa: SLF001
    if fehler:
        return None, None, False, fehler
    mandant_id = bw._AKTIVER_MANDANT.get(None)  # noqa: SLF001
    if mandant_id is None:
        return None, None, False, _fehler(
            "Für diesen Zugang gibt es keinen Betrieb mit Kontoumsätzen.", 409)
    return un, mandant_id, bool(bw._ALS_KANZLEI.get()), None  # noqa: SLF001


def _mandant(mandant_id: int) -> dict:
    with mandanten.sitzung(None) as c:
        z = c.execute("SELECT m.besitzer_un, m.name, k.name FROM mandant m "
                      "JOIN kanzlei k ON k.id = m.kanzlei_id WHERE m.id=?",
                      (mandant_id,)).fetchone()
    return ({"besitzer": z[0], "betrieb": z[1], "kanzlei": z[2]} if z
            else {"besitzer": None, "betrieb": None, "kanzlei": None})


def _stand_aussen(mandant_id: int) -> dict:
    stand = mandanten.bank_stand(mandant_id)
    titel, text = recht.BANK_FREIGABE
    aktuell = recht.fassung("bank_freigabe")
    m = _mandant(mandant_id)
    return {
        "freigegeben": stand["freigegeben"],
        "am": stand["bank_freigabe_am"], "von": stand["bank_freigabe_von"],
        "fassung": stand["bank_freigabe_fassung"], "fassung_aktuell": aktuell,
        "neue_fassung": bool(stand["freigegeben"]
                             and stand["bank_freigabe_fassung"] != aktuell),
        "widerrufen_am": stand["bank_widerruf_am"],
        "angefragt_am": stand["bank_anfrage_am"],
        "noetig": bankrecht.freigabe_pflicht(),
        "kanzlei": m["kanzlei"], "betrieb": m["betrieb"],
        "titel": titel, "text": text,
    }


def api_freigabe(request: Request) -> Response:
    """Stand der Freigabe — für den Betrieb und für seine Kanzlei."""
    un, mandant_id, _, fehler = _kontext(request)
    if fehler:
        return fehler
    return JSONResponse(_stand_aussen(mandant_id))


async def api_freigeben(request: Request) -> Response:
    """Der Betrieb gibt frei — genau der Fassung, die er gelesen hat."""
    un, mandant_id, als_kanzlei, fehler = _kontext(request)
    if fehler:
        return fehler
    if als_kanzlei or bw.rolle(un) == "mitarbeit":
        return _fehler("Freigeben kann nur die Inhaberin des Betriebs.", 403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    aktuell = recht.fassung("bank_freigabe")
    if str((body or {}).get("fassung") or "") != aktuell:
        return _fehler("Der Text hat sich geändert — bitte noch einmal lesen.", 409)
    mandanten.bank_freigeben(mandant_id, un, aktuell)
    audit.audit(un, "bank_freigabe", mandant_id=str(mandant_id), fassung=aktuell)
    return JSONResponse({"ok": True, **_stand_aussen(mandant_id)})


async def api_widerrufen(request: Request) -> Response:
    """Der Betrieb nimmt die Freigabe zurück."""
    un, mandant_id, als_kanzlei, fehler = _kontext(request)
    if fehler:
        return fehler
    if als_kanzlei or bw.rolle(un) == "mitarbeit":
        return _fehler("Widerrufen kann nur die Inhaberin des Betriebs.", 403)
    mandanten.bank_widerrufen(mandant_id)
    audit.audit(un, "bank_widerruf", mandant_id=str(mandant_id))
    return JSONResponse({"ok": True, **_stand_aussen(mandant_id)})


def _senden(an: str, betreff: str, text: str) -> None:
    import postfach  # noqa: PLC0415
    try:
        ok, hinweis = postfach.senden(an, betreff, text,
                                      stempel=time.strftime("%Y%m%d-%H%M%S"))
        print(f"[bank] Mail an {an}: {hinweis}", flush=True)
    except Exception as ex:  # noqa: BLE001
        print(f"[bank] Mail an {an} fehlgeschlagen: {ex!r}", flush=True)


async def api_anfragen(request: Request) -> Response:
    """Die Kanzlei bittet um die Freigabe — der Betrieb bekommt eine Mail."""
    un, mandant_id, als_kanzlei, fehler = _kontext(request)
    if fehler:
        return fehler
    if not als_kanzlei:
        return _fehler("Anfragen kann das Steuerbüro.", 403)
    stand = mandanten.bank_stand(mandant_id)
    if stand["freigegeben"]:
        return _fehler("Der Betrieb hat schon freigegeben.", 409)
    zuletzt = stand["bank_anfrage_am"]
    if zuletzt:
        try:
            if datetime.now(timezone.utc) - datetime.fromisoformat(zuletzt) < ANFRAGE_ABSTAND:
                return _fehler("Heute wurde schon angefragt — der Betrieb hat "
                               "die Mail.", 429)
        except ValueError:
            pass
    mandanten.bank_anfragen(mandant_id)
    m = _mandant(mandant_id)
    if m["besitzer"] and "@" in m["besitzer"]:
        _senden(m["besitzer"], "babu — dein Steuerbüro bittet um die Kontoumsätze",
                f"Hallo,\n\n{m['kanzlei'] or 'Dein Steuerbüro'} möchte in babu die "
                "Umsätze deiner Geschäftskonten ansehen — um Belege und Zahlungen "
                "abzugleichen und fehlende Belege zu finden. Ansehen heißt nur "
                "lesen: niemand kann damit eine Zahlung auslösen.\n\n"
                "Freigeben oder ablehnen kannst du im Portal unter „Bank“:\n"
                f"{bw.PORTAL_ORIGIN}/portal#bank\n\n"
                "Dein babu-Team")
    audit.audit(un, "bank_anfrage", mandant_id=str(mandant_id))
    return JSONResponse({"ok": True, **_stand_aussen(mandant_id)})


_ROUTEN = [
    ("GET", "/api/bank/freigabe", api_freigabe),
    ("POST", "/api/bank/freigabe", api_freigeben),
    ("POST", "/api/bank/freigabe/widerrufen", api_widerrufen),
    ("POST", "/api/bank/freigabe/anfragen", api_anfragen),
]
