#!/usr/bin/env python3
"""Die Empfangsadressen des Posteingangs — anlegen, sehen, stilllegen.

Ein eigenes Blatt neben `babu_web.py`, aus demselben Grund wie
`kanzlei_routen.py` und `datev_seite.py`: die 10.600 Zeilen dort sind die
Datei, in der niemand mehr etwas findet.

Zwei Sorten Route stehen hier, und sie sind streng getrennt:

1. **Verwaltung** (`/adresse/{mandant_id}`, GET/POST/stilllegen). Wer hier
   hineinkommt, ist Kanzlei oder Betreiber UND arbeitet für genau diesen
   Mandanten. Das ist der Weg, auf dem eine Adresse überhaupt entsteht —
   sie entsteht nie von selbst.
2. **Auflösung** (`/aufloesen`). Die eine Frage, die der Mailserver
   (`server/posteingang/`) stellt: „gibt es diesen lokalen Teil, und zu
   welchem Betrieb gehört er?" Sie hat KEINE angemeldete Nutzerin — der
   Fragende ist ein Dienst — und läuft deshalb gegen ein eigenes
   gemeinsames Geheimnis (`BABU_POSTEINGANG_TOKEN`), nicht gegen die
   Sitzungswache. Ohne gesetztes Geheimnis antwortet sie grundsätzlich
   nicht: ein Dienst, der versehentlich ohne Konfiguration läuft, soll
   nicht zum offenen Adressverzeichnis werden.

Warum die Auflösung überhaupt eine HTTP-Route ist und der Mailserver nicht
selbst in die Datenbank sieht: derselbe Grund, aus dem er auch nicht in die
Belegbox schreibt. Es gibt genau einen Eigentümer der Portal-Daten, und das
ist babu-web. Der Posteingang bleibt dadurch ein Dienst ohne Datenbank,
ohne Treiber und ohne Passwortdatei — er kennt nur zwei URLs.
"""
from __future__ import annotations

import contextlib
import hmac
import json
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import mandanten
import postadresse

router = APIRouter(prefix="/api/posteingang")

#: Die Domäne, unter der der Posteingang Post annimmt. Steht hier nur, damit
#: die Oberfläche eine vollständige Adresse anzeigen kann — geprüft wird sie
#: im Mailserver, nicht hier.
DOMAENE = (os.environ.get("BABU_POST_DOMAENE") or "post.babu.0711.io").strip()


def _dienst_token() -> str:
    """Das gemeinsame Geheimnis mit dem Mailserver. Leer = Auflösung tot.

    Bei jedem Aufruf frisch aus der Umgebung gelesen und nicht zur
    Importzeit eingefroren: die Tests setzen die Variable um, und ein
    festgehaltener Wert wäre dort die falsche Wahrheit.
    """
    return (os.environ.get("BABU_POSTEINGANG_TOKEN") or "").strip()


#: Wie viele aktive Adressen ein Betrieb höchstens hat. Mehrere sind
#: sinnvoll (eine für die Buchhaltung, eine für den Steuerberater), aber
#: unbegrenzt viele wären nur mehr offene Türen.
ADRESSEN_MAX = 5


def _bw():
    import babu_web  # noqa: PLC0415
    return babu_web


@contextlib.contextmanager
def _sitzung():
    """Portal-Verbindung unter dem Schloss — wie in `kanzlei_routen`.

    Alles, was darin `postadresse`/`mandanten` ruft, gibt `c=` mit; sonst
    nähme deren eigener Weg dasselbe einfache Schloss ein zweites Mal und
    hinge für immer.
    """
    bw = _bw()
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        yield c


def _fehler(text: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"fehler": text}, status_code=code)


def _wache(request: Request):
    return _bw()._verwalter_wache(request)  # noqa: SLF001


# ACHTUNG, dieselbe Falle wie in `kanzlei_routen._ist_betreiber`: `rolle()`
# liest selbst aus der Datenbank und nimmt dabei `_DB_LOCK`. Das Schloss ist
# NICHT wiedereintrittsfähig — die Frage „ist das der Betreiber?" wird
# deshalb in jeder Route EINMAL vor `_sitzung()` beantwortet und als
# Wahrheitswert weitergereicht. Ein Aufruf innerhalb des Blocks hinge für
# immer; deshalb steht hier auch keine bequeme `_darf(un, id, c)`-Hilfe, die
# genau dazu einlüde.


def _adresse(lokal: str) -> str:
    return f"{lokal}@{DOMAENE}"


# ---------------------------------------------------------------------------
# Verwaltung
# ---------------------------------------------------------------------------

@router.get("/adresse/{mandant_id}")
async def adressen_lesen(mandant_id: int, request: Request) -> JSONResponse:
    un, fehler = _wache(request)
    if fehler:
        return fehler
    betreiber = _bw().rolle(un) == "admin"
    with _sitzung() as c:
        if not (betreiber or mandanten.kanzlei_mitglied(un, mandant_id, c=c)):
            return _fehler("Für diesen Mandanten ist dein Zugang nicht "
                           "freigeschaltet.", 403)
        zeilen = postadresse.fuer_mandant(mandant_id, nur_aktive=False, c=c)
    return JSONResponse({
        "mandant_id": mandant_id,
        "domaene": DOMAENE,
        "adressen": [{"adresse": _adresse(z["lokal"]), "lokal": z["lokal"],
                      "angelegt": z["angelegt"], "aktiv": bool(z["aktiv"])}
                     for z in zeilen]})


@router.post("/adresse/{mandant_id}")
async def adresse_anlegen(mandant_id: int, request: Request) -> JSONResponse:
    """Eine neue Empfangsadresse würfeln.

    Der lokale Teil kommt aus `postadresse.neues_lokal()` und wird
    ausdrücklich NICHT vom Aufrufer bestimmt: eine Kanzlei, die sich
    `nina@…` wünschen dürfte, hätte damit die Nichterratbarkeit abgeschafft,
    auf der die ganze Zuordnung steht.
    """
    un, fehler = _wache(request)
    if fehler:
        return fehler
    betreiber = _bw().rolle(un) == "admin"
    with _sitzung() as c:
        if not (betreiber or mandanten.kanzlei_mitglied(un, mandant_id, c=c)):
            return _fehler("Für diesen Mandanten ist dein Zugang nicht "
                           "freigeschaltet.", 403)
        if mandanten.mandant_holen(mandant_id, c=c) is None:
            return _fehler("unbekannter Mandant", 404)
        if len(postadresse.fuer_mandant(mandant_id, c=c)) >= ADRESSEN_MAX:
            return _fehler(f"Mehr als {ADRESSEN_MAX} Adressen sind nicht "
                           "vorgesehen — leg eine alte still.", 409)
        lokal = postadresse.anlegen(mandant_id, c=c)
    return JSONResponse({"ok": True, "lokal": lokal, "adresse": _adresse(lokal),
                         "domaene": DOMAENE})


@router.post("/adresse/{mandant_id}/stilllegen")
async def adresse_stilllegen(mandant_id: int, request: Request) -> JSONResponse:
    un, fehler = _wache(request)
    if fehler:
        return fehler
    try:
        koerper = json.loads(await _bw().koerper_lesen(request, 8 * 1024))
    except Exception:  # noqa: BLE001
        return _fehler("JSON erwartet")
    lokal = str((koerper or {}).get("lokal", ""))
    betreiber = _bw().rolle(un) == "admin"
    with _sitzung() as c:
        if not (betreiber or mandanten.kanzlei_mitglied(un, mandant_id, c=c)):
            return _fehler("Für diesen Mandanten ist dein Zugang nicht "
                           "freigeschaltet.", 403)
        if not postadresse.stilllegen(lokal, mandant_id, c=c):
            return _fehler("unbekannte Adresse", 404)
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Auflösung — die eine Frage des Mailservers
# ---------------------------------------------------------------------------

@router.get("/aufloesen")
async def aufloesen(request: Request, lokal: str = "") -> JSONResponse:
    """`lokal` → `{mandant_id}`, oder 404.

    404 ist für den Mailserver das Signal für ein 550: Post an eine Adresse,
    die es nicht (mehr) gibt, wird abgewiesen und nirgends abgelegt. Jede
    andere Antwort — auch ein 500 oder ein Verbindungsfehler — muss dort zu
    einem 4xx werden, damit der absendende Server es später erneut versucht
    und echte Post nicht verlorengeht.
    """
    token = _dienst_token()
    mit = (request.headers.get("x-posteingang-token") or "").strip()
    # `compare_digest` und nicht `==`: der Vergleich läuft gegen einen Wert,
    # den ein Fremder wiederholt raten darf.
    if not token or not mit or not hmac.compare_digest(token, mit):
        return _fehler("nicht erlaubt", 403)
    mandant_id = None
    with _sitzung() as c:
        mandant_id = postadresse.aufloesen(lokal, c=c)
    if mandant_id is None:
        return _fehler("unbekannte Adresse", 404)
    return JSONResponse({"mandant_id": mandant_id})
