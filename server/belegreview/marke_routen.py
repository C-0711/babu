#!/usr/bin/env python3
"""Briefkopf und Marketing — was der Salon nach außen zeigt.

Eigenes Blatt mit eigenem Router, aus demselben Grund wie `datev_seite.py`
und `kanzlei_routen.py`: `babu_web.py` ist mit über elftausend Zeilen die
Datei, in der niemand mehr etwas findet, und der Auftritt des Salons ist ein
geschlossenes Thema. In `babu_web` steht deshalb nur noch der Import und die
eine `include_router`-Zeile.

**Dies ist ein reiner Umzug.** Kein Pfad, kein Statuscode, kein Zeitlimit und
keine Antwort hat sich dabei geändert — die iOS-App und `portal.html` rufen
dieselben Adressen wie vorher. Was hier steht, stand vorher Wort für Wort in
`babu_web.py` zwischen `/api/vertraege` und `/api/kategorien`.

Zwei Themen, die dieselben Bausteine teilen und deshalb zusammen umziehen:

1. **Der Briefkopf** (`/api/marke*`). Eine Rechnung ist oft das Einzige, was
   eine Kundin schriftlich vom Salon in die Hand bekommt. Logo und ein Stil,
   den babu aus den Firmendaten vorschlägt — das Zeichnen macht die App.
2. **Marketing** (`/api/marketing*`). Aushang, Beitrag, Gutschein. babu
   kennt Name, Farbe und Zeichen; den Text schreibt die Inhaberin.

Beide brauchen `LOGO_TYPEN`, `_gemini_schluessel` und `_bild_erzeugen`.
Sie zu trennen hieße, diese drei zweimal zu führen.

**Der Router hat KEIN Präfix** — anders als `datev_seite` und
`kanzlei_routen`. Es gibt hier zwei Adressfamilien (`/api/marke` und
`/api/marketing`), und die Route `/api/marke` selbst wäre unter einem
Präfix der leere Pfad, den FastAPI nicht annimmt. Die Pfade stehen deshalb
vollständig an den Routen — genau so, wie sie vorher in `babu_web` standen.

**Die Reihenfolge der Routen ist Absicht.** `/api/marketing/entwerfen` steht
VOR `/api/marketing/{schluessel}`; andersherum verschluckte der Platzhalter
den Entwurf. Die Reihenfolge ist die des alten Blocks, unverändert.

**Die Dateien liegen je BETRIEB getrennt** (`sha256(betrieb)[:16]`), und der
Betrieb kommt immer aus `salon_von_aktiv(un)` — nie roh aus dem angemeldeten
Konto. Arbeitet eine Kanzlei als Mandant, gehört das Logo dem Mandanten.
`tests/test_betriebsfunktionen_kennen_den_mandanten.py` bewacht das und
liest seit dem Umzug auch diese Datei.

`babu_web` wird ausschließlich innerhalb der Funktionen importiert (lazy) —
`babu_web` bindet diesen Router ein, ein Import auf Modulebene wäre ein
Kreis. Nebeneffekt: die Tests dürfen die Wachen an `babu_web` austauschen
und dieser Router merkt es.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path

import requests
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

router = APIRouter()


# ---------------------------------------------------------------------------
# Zugriff auf babu_web — erst zur Laufzeit.
# ---------------------------------------------------------------------------

def _bw():
    import babu_web  # noqa: PLC0415
    return babu_web


# ---------------------------------------------------------------------------
# Der Briefkopf: eine Rechnung ist oft das Einzige, was eine Kundin
# schriftlich vom Salon in die Hand bekommt. Logo und ein Stil, den babu aus
# den Firmendaten vorschlägt — das Zeichnen macht die App.
# ---------------------------------------------------------------------------

LOGOS = Path(os.environ.get("BABU_LOGOS", str(Path.home() / "babu-web" / "logos")))
LOGO_MAX = 4 * 1024 * 1024
LOGO_TYPEN = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg"}


def _logo_pfad(un: str) -> Path:
    return LOGOS / (hashlib.sha256(un.encode()).hexdigest()[:16] + ".bin")


def _stil_aus_einstellungen(e: dict) -> dict:
    import marke  # noqa: PLC0415
    return marke.stil_pruefen({
        "farbe": e.get("marke_farbe"), "schrift": e.get("marke_schrift"),
        "ausrichtung": e.get("marke_ausrichtung"),
        "linie": (e.get("marke_linie") or "1") != "0",
        "begruendung": e.get("marke_begruendung"),
    })


@router.get("/api/marke")
def api_marke(request: Request) -> Response:
    bw = _bw()
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    import marke  # noqa: PLC0415
    inhaber = bw.salon_von_aktiv(un)
    stil = _stil_aus_einstellungen(bw.db_einstellungen(inhaber))
    return JSONResponse({**stil, "in_worten": marke.als_text(stil),
                         "logo": _logo_pfad(inhaber).is_file()})


@router.get("/api/marke/katalog")
def api_marke_katalog(request: Request) -> Response:
    """Die vier Schritte und die Farben, aus denen gewählt wird."""
    bw = _bw()
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    import marke  # noqa: PLC0415
    return JSONResponse({"schritte": list(marke.SCHRITTE),
                         "farben": list(marke.KATALOG),
                         "stile": [{"schluessel": k, "name": k.capitalize(),
                                    "dazu": v.split(",")[0]}
                                   for k, v in marke.LOGO_STILE.items()]})


@router.post("/api/marke/farbe")
async def api_marke_farbe(request: Request) -> Response:
    """Schritt 1: eine Farbe aus dem Katalog wählen."""
    bw = _bw()
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    import marke  # noqa: PLC0415
    eintrag = marke.farbe_aus_katalog((body or {}).get("farbe"))
    if eintrag is None:
        return JSONResponse({"fehler": "Diese Farbe kennen wir nicht."},
                            status_code=400)
    bw.db_einstellung_setzen(bw.salon_von_aktiv(un), "marke_farbe", eintrag["hex"])
    return JSONResponse({"ok": True, **eintrag})


@router.post("/api/marke/logo")
async def api_marke_logo(request: Request) -> Response:
    """Das Logo des Salons — es liegt NICHT in der Belegbox: ein Logo wird
    ausgetauscht, und in Git bleibt jede Fassung für immer stehen."""
    bw = _bw()
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    if bw.rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
    try:
        daten = await bw.koerper_lesen(request, LOGO_MAX)
    except bw.KoerperZuGross:
        return JSONResponse({"fehler": "Das Bild ist zu groß — bis 4 MB."},
                            status_code=413)
    if not daten:
        return JSONResponse({"fehler": "leer"}, status_code=400)
    if not any(daten.startswith(k) for k in LOGO_TYPEN):
        return JSONResponse({"fehler": "Bitte als PNG oder JPG."}, status_code=400)
    pfad = _logo_pfad(bw.salon_von_aktiv(un))
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(daten)
    return JSONResponse({"ok": True})


@router.get("/api/marke/logo")
def api_marke_logo_holen(request: Request) -> Response:
    bw = _bw()
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    pfad = _logo_pfad(bw.salon_von_aktiv(un))
    if not pfad.is_file():
        return JSONResponse({"fehler": "kein Logo"}, status_code=404)
    daten = pfad.read_bytes()
    typ = next((t for k, t in LOGO_TYPEN.items() if daten.startswith(k)),
               "application/octet-stream")
    return Response(content=daten, media_type=typ,
                    headers={"Cache-Control": "private, max-age=300"})


@router.post("/api/marke/logo/loeschen")
def api_marke_logo_loeschen(request: Request) -> Response:
    bw = _bw()
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    _logo_pfad(bw.salon_von_aktiv(un)).unlink(missing_ok=True)
    return JSONResponse({"ok": True})


# Nano Banana (gemini-3-pro-image). Der Schlüssel steht in einer .env-Zeile
# und wird NIE geloggt. Ohne Schlüssel gibt es die Funktion schlicht nicht.
GEMINI_MODELL = os.environ.get("BABU_BILD_MODELL", "gemini-3-pro-image")
GEMINI_ENV = Path(os.environ.get("BABU_GEMINI_ENV", str(Path.home() / "Youtube" / ".env")))


def _gemini_schluessel() -> str | None:
    """Die eine Zeile parsen — die Datei enthält kaputte Zeilen, `source`
    würde daran scheitern."""
    schluessel = os.environ.get("GEMINI_API_KEY")
    if schluessel:
        return schluessel.strip()
    try:
        for zeile in GEMINI_ENV.read_text(errors="replace").splitlines():
            if zeile.strip().startswith("GEMINI_API_KEY"):
                return zeile.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        return None
    return None


@router.post("/api/marke/logo/entwerfen")
def api_marke_logo_entwerfen(request: Request, stil: str = "schlicht") -> Response:
    """babu entwirft ein Logo aus den Firmendaten.

    Der Name des Salons geht dafür an einen Dienst außerhalb des Hauses
    (Google). Das steht so in der Oberfläche — es ist die einzige Stelle in
    babu, an der Betriebsdaten das Haus verlassen.
    """
    bw = _bw()
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    if bw.rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
    schluessel = _gemini_schluessel()
    if not schluessel:
        return JSONResponse(
            {"fehler": "Für entworfene Logos fehlt der Zugang — lade solange "
                       "dein eigenes Bild hoch."}, status_code=501)

    import marke  # noqa: PLC0415
    inhaber = bw.salon_von_aktiv(un)
    einstellungen = bw.db_einstellungen(inhaber)
    auftrag = marke.logo_auftrag(einstellungen, stil,
                                 einstellungen.get("marke_farbe"))
    bild = _logo_erzeugen(auftrag, schluessel)
    if bild is None:
        return JSONResponse(
            {"fehler": "Der Entwurf kam gerade nicht durch — versuch es "
                       "gleich nochmal."}, status_code=503)

    if not bild or len(bild) > LOGO_MAX * 4:
        return JSONResponse({"fehler": "Das Bild kam unbrauchbar zurück."},
                            status_code=503)
    pfad = _logo_pfad(inhaber)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(bild)
    print(f"[logo] entworfen für {inhaber} ({len(bild)} Bytes, Stil {stil})", flush=True)
    return JSONResponse({"ok": True, "stil": stil, "bytes": len(bild)})


def _bild_erzeugen(auftrag: str, schluessel: str, format_: str = "1:1",
                   was: str = "bild") -> bytes | None:
    """Ein Bild von Nano Banana holen — blockierend, gehört in den Threadpool.

    Gibt None zurück, statt zu werfen: bei zehn gleichzeitigen Versuchen darf
    einer danebengehen, ohne die anderen mitzureißen.
    """
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_MODELL}:generateContent",
            headers={"x-goog-api-key": schluessel},
            json={"contents": [{"parts": [{"text": auftrag}]}],
                  "generationConfig": {"responseModalities": ["IMAGE"],
                                       "imageConfig": {"aspectRatio": format_}}},
            timeout=180)
        r.raise_for_status()
        teile = r.json()["candidates"][0]["content"]["parts"]
        roh = next(t["inlineData"]["data"] for t in teile if "inlineData" in t)
        return base64.b64decode(roh)
    except Exception as e:  # noqa: BLE001
        # Nie den Schlüssel mitloggen — nur den Typ des Fehlers.
        print(f"[{was}] gescheitert: {type(e).__name__}", flush=True)
        return None


def _logo_erzeugen(auftrag: str, schluessel: str) -> bytes | None:
    return _bild_erzeugen(auftrag, schluessel, "1:1", "logo")


def _vorschlag_pfad(un: str, nummer: int) -> Path:
    return LOGOS / hashlib.sha256(un.encode()).hexdigest()[:16] / f"v{nummer}.bin"


@router.post("/api/marke/vorschlaege")
async def api_marke_vorschlaege(request: Request, saat: int = 0) -> Response:
    """Ein Knopf, zehn Zeichen.

    Statt sich durch Farbe und Stil zu tasten: babu entwirft zehn auf einmal,
    eines antippen — und der ganze Auftritt steht. Die zehn entstehen
    gleichzeitig, sonst dauert es zehnmal so lang.
    """
    bw = _bw()
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    if bw.rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
    schluessel = _gemini_schluessel()
    if not schluessel:
        return JSONResponse(
            {"fehler": "Für entworfene Zeichen fehlt der Zugang — lade solange "
                       "dein eigenes Bild hoch."}, status_code=501)

    import concurrent.futures as futures  # noqa: PLC0415
    import marke  # noqa: PLC0415
    inhaber = bw.salon_von_aktiv(un)
    saetze = marke.vorschlag_saetze(bw.db_einstellungen(inhaber), saat=saat)

    def hole(satz: dict) -> tuple[dict, bytes | None]:
        return satz, _logo_erzeugen(satz["auftrag"], schluessel)

    def alle() -> list[tuple[dict, bytes | None]]:
        with futures.ThreadPoolExecutor(max_workers=len(saetze)) as pool:
            return list(pool.map(hole, saetze))

    ergebnisse = await run_in_threadpool(alle)

    ordner = _vorschlag_pfad(inhaber, 0).parent
    ordner.mkdir(parents=True, exist_ok=True)
    fertig = []
    for satz, bild in ergebnisse:
        if not bild:
            continue
        _vorschlag_pfad(inhaber, satz["nummer"]).write_bytes(bild)
        fertig.append({"nummer": satz["nummer"], "stil": satz["stil"],
                       "farbe": satz["farbe"], "farbe_name": satz["farbe_name"]})
    if not fertig:
        return JSONResponse({"fehler": "Die Entwürfe kamen gerade nicht durch — "
                                       "versuch es gleich nochmal."}, status_code=503)
    print(f"[logo] {len(fertig)} von {len(saetze)} Vorschlägen für {inhaber}",
          flush=True)
    return JSONResponse({"vorschlaege": fertig, "saat": saat})


@router.get("/api/marke/vorschlag/{nummer}")
def api_marke_vorschlag_bild(nummer: int, request: Request) -> Response:
    bw = _bw()
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    pfad = _vorschlag_pfad(bw.salon_von_aktiv(un), nummer)
    if not (0 <= nummer < 12) or not pfad.is_file():
        return JSONResponse({"fehler": "kein Vorschlag"}, status_code=404)
    daten = pfad.read_bytes()
    typ = next((t for k, t in LOGO_TYPEN.items() if daten.startswith(k)),
               "application/octet-stream")
    return Response(content=daten, media_type=typ,
                    headers={"Cache-Control": "private, max-age=300"})


@router.post("/api/marke/waehlen")
async def api_marke_waehlen(request: Request) -> Response:
    """Ein Vorschlag angetippt — und der ganze Auftritt steht."""
    bw = _bw()
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    if bw.rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
    try:
        body = await request.json()
        nummer = int((body or {}).get("nummer"))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit nummer erwartet"}, status_code=400)

    import marke  # noqa: PLC0415
    inhaber = bw.salon_von_aktiv(un)
    quelle = _vorschlag_pfad(inhaber, nummer)
    if not (0 <= nummer < 12) or not quelle.is_file():
        return JSONResponse({"fehler": "Diesen Vorschlag gibt es nicht mehr."},
                            status_code=404)

    ziel = _logo_pfad(inhaber)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(quelle.read_bytes())

    saetze = {s["nummer"]: s for s in marke.vorschlag_saetze(
        bw.db_einstellungen(inhaber), saat=int((body or {}).get("saat") or 0))}
    auftritt = marke.auftritt_aus(saetze.get(nummer, {}))
    for schluessel, wert in (("marke_farbe", auftritt["farbe"]),
                             ("marke_schrift", auftritt["schrift"]),
                             ("marke_ausrichtung", auftritt["ausrichtung"]),
                             ("marke_linie", "1" if auftritt["linie"] else "0"),
                             ("marke_begruendung", auftritt.get("begruendung", ""))):
        bw.db_einstellung_setzen(inhaber, schluessel, str(wert))
    # Die übrigen Entwürfe braucht niemand mehr.
    for n in range(12):
        if n != nummer:
            _vorschlag_pfad(inhaber, n).unlink(missing_ok=True)
    return JSONResponse({"ok": True, **auftritt,
                         "in_worten": marke.als_text(auftritt)})


# ---------------------------------------------------------------------------
# Marketing: was der Salon nach außen zeigt. babu kennt Name, Farbe und
# Zeichen — damit macht es das, wofür sonst niemand Zeit hat.
# ---------------------------------------------------------------------------

MARKETING = LOGOS.parent / "marketing" if LOGOS.name == "logos" else LOGOS / "marketing"


def _stueck_pfad(un: str, schluessel: str) -> Path:
    return (MARKETING / hashlib.sha256(un.encode()).hexdigest()[:16]
            / f"{re.sub(r'[^a-z]', '', schluessel)}.bin")


@router.get("/api/marketing")
def api_marketing(request: Request) -> Response:
    """Was babu gestalten kann — und was schon da ist."""
    bw = _bw()
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    import marketing as mk  # noqa: PLC0415
    inhaber = bw.salon_von_aktiv(un)
    stuecke = [dict(s, fertig=_stueck_pfad(inhaber, s["schluessel"]).is_file())
               for s in mk.stuecke_liste()]
    return JSONResponse({"stuecke": stuecke,
                         "farbe": bw.db_einstellungen(inhaber).get("marke_farbe")
                                  or "#1F1D1B"})


@router.post("/api/marketing/entwerfen")
async def api_marketing_entwerfen(request: Request) -> Response:
    """Ein Aushang, ein Beitrag, ein Gutschein — in den Farben des Salons.

    Was drauf steht, schreibt die Inhaberin. babu gestaltet es nur: ein
    Rabatt, den niemand beschlossen hat, hat auf keinem Aushang etwas
    verloren.
    """
    bw = _bw()
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    if bw.rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
    schluessel = _gemini_schluessel()
    if not schluessel:
        return JSONResponse({"fehler": "Dafür fehlt gerade der Zugang."},
                            status_code=501)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)

    import marketing as mk  # noqa: PLC0415
    inhaber = bw.salon_von_aktiv(un)
    einstellungen = bw.db_einstellungen(inhaber)
    try:
        stueck = mk.stueck(str((body or {}).get("stueck") or ""))
        auftrag = mk.auftrag(stueck["schluessel"], (body or {}).get("text"),
                             einstellungen)
    except mk.MarketingFehler as e:
        return JSONResponse({"fehler": str(e)}, status_code=400)

    bild = await run_in_threadpool(_bild_erzeugen, auftrag, schluessel,
                                   stueck["format"], "marketing")
    if not bild:
        return JSONResponse({"fehler": "Das kam gerade nicht durch — versuch es "
                                       "gleich nochmal."}, status_code=503)
    pfad = _stueck_pfad(inhaber, stueck["schluessel"])
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(bild)
    return JSONResponse({"ok": True, "stueck": stueck["schluessel"],
                         "name": stueck["name"], "bytes": len(bild)})


@router.get("/api/marketing/{schluessel}")
def api_marketing_bild(schluessel: str, request: Request) -> Response:
    bw = _bw()
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    pfad = _stueck_pfad(bw.salon_von_aktiv(un), schluessel)
    if not pfad.is_file():
        return JSONResponse({"fehler": "noch nichts gestaltet"}, status_code=404)
    daten = pfad.read_bytes()
    typ = next((t for k, t in LOGO_TYPEN.items() if daten.startswith(k)),
               "application/octet-stream")
    return Response(content=daten, media_type=typ,
                    headers={"Cache-Control": "private, max-age=300"})


@router.post("/api/marke/entwerfen")
def api_marke_entwerfen(request: Request) -> Response:
    """babu schlägt einen Briefkopf vor — aus dem, was es über den Salon weiß.

    Was das Modell antwortet, wird geprüft, nicht geglaubt: unbrauchbare
    Farben oder erfundene Schriften fallen auf die Vorgabe zurück. Eine
    Rechnung wird gedruckt und muss lesbar bleiben.
    """
    bw = _bw()
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler:
        return fehler
    if bw.rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
    import marke  # noqa: PLC0415
    inhaber = bw.salon_von_aktiv(un)
    einstellungen = bw.db_einstellungen(inhaber)
    frage = marke.frage_bauen(einstellungen)
    roh: dict = {}
    try:
        with bw._LLM_SEMAPHORE:  # noqa: SLF001
            r = requests.post(bw.GEMMA_API, json={
                "model": bw.GEMMA_MODELL, "temperature": 0.6, "max_tokens": 300,
                "messages": [{"role": "user", "content": frage}],
            }, timeout=90)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        treffer = re.search(r"\{.*\}", text, re.S)
        roh = json.loads(treffer.group(0)) if treffer else {}
    except Exception:  # noqa: BLE001
        return JSONResponse(
            {"fehler": "Der Vorschlag kam gerade nicht durch — versuch es "
                       "gleich nochmal, oder wähle selbst."}, status_code=503)

    stil = marke.stil_pruefen(roh)
    for schluessel, wert in (("marke_farbe", stil["farbe"]),
                             ("marke_schrift", stil["schrift"]),
                             ("marke_ausrichtung", stil["ausrichtung"]),
                             ("marke_linie", "1" if stil["linie"] else "0"),
                             ("marke_begruendung", stil.get("begruendung", ""))):
        bw.db_einstellung_setzen(inhaber, schluessel, str(wert))
    return JSONResponse({**stil, "in_worten": marke.als_text(stil)})
