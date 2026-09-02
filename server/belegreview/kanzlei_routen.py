#!/usr/bin/env python3
"""Die Mandantenseite der Kanzlei — anlegen, einladen, umschalten, sehen was ansteht.

Plan 21, Phase 4. Eine eigene Datei mit eigenem Router, aus demselben Grund
wie `datev_seite.py`: `babu_web.py` ist mit 10.600 Zeilen die Datei, in der
niemand mehr etwas findet, und die Kanzlei-Sicht ist ein geschlossenes Thema.
In `babu_web` steht deshalb nur der Import und die eine
`include_router`-Zeile.

Was hier passiert, in der Reihenfolge, in der eine Kanzlei es tut:

1. **Mandant anlegen.** Name, E-Mail. Daraus entsteht — falls es sie noch
   nicht gibt — die Kanzlei-Zeile mit dem Aufrufer als Inhaber, dann der
   Mandant auf `box_ausstehend`, dann das Konto des Salons, und zuletzt
   geht ein Link an die Salon-Adresse.
2. **Warten.** Solange keine Belegbox eingetragen ist, sagt die Liste das
   auch: „Belegbox wird eingerichtet". Das Belegbox-Gateway ist ein fremdes
   Projekt und wird von hier aus nicht ferngesteuert (Plan 21, D4).
3. **Verknüpfen.** Wer die Box tatsächlich eingerichtet hat, trägt sie ein —
   und NUR die Betreiber-Rolle `admin` darf das. Eine Kanzlei, die sich
   selbst eine beliebige Box eintragen dürfte, könnte sich damit in einen
   fremden Betrieb schreiben.
4. **Arbeiten.** Die Übersicht sagt je Mandant, wie viele Rückfragen offen
   sind; „Was ansteht" fasst dasselbe über alle Mandanten zusammen.

Drei Entscheidungen, die man sonst für Zufall halten könnte:

* **Der Link statt eines Passworts.** Das Konto des Mandanten entsteht hier
  mit einem Zufallspasswort, das niemand je sieht — nicht die Kanzlei, nicht
  das Log, und in der Datenbank steht nur sein Hash. Die Einladung ist ein
  einmal einlösbarer Link nach dem Muster aus `einladung.py`; eingelöst wird
  er über den bestehenden Weg aus `passwort_reset.py`, weil dort ein Konto
  vorausgesetzt wird, das es hier bereits gibt. (Der Auswertungs-Link aus
  `einladung.py` LEGT das Konto erst an und würde auf ein bestehendes mit
  409 antworten — derselbe Hash-Token-Gedanke, anderer Zeitpunkt.)
* **Zeitbudget statt Vollständigkeit.** „Offene Rückfragen" steht nicht in
  der Datenbank, sondern im Index der jeweiligen Belegbox — je Mandant ein
  `git`-Aufruf. Bei hunderten Mandanten darf eine einzige langsame Box die
  Übersicht nicht anhalten: es wird nebenläufig gefragt, mit Budget, und
  wer nicht rechtzeitig antwortet, steht als „nicht erreichbar" in der
  Liste. Eine Zahl, die fehlt, ist besser als eine Seite, die hängt.
* **Mitgliedschaft wird hier selbst geprüft.** Phase 3 bringt
  `_kanzlei_wache` und `salon_von_aktiv` nach `babu_web`; bis dahin fragt
  jede Route `mandanten.kanzlei_mitglied` direkt. Die Stellen sind unten
  einzeln vermerkt (`# Phase 3:`), damit der Umbau sie findet, statt sie zu
  suchen.

`babu_web` wird ausschließlich innerhalb der Funktionen importiert (lazy) —
`babu_web` bindet diesen Router ein, ein Import auf Modulebene wäre ein
Kreis. Nebeneffekt: die Tests dürfen die Wachen an `babu_web` austauschen
und dieser Router merkt es.
"""
from __future__ import annotations

import contextlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as ZeitAus
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import audit
import box as bx
import mandanten

router = APIRouter(prefix="/api/kanzlei")

# Wie viele Mandanten eine Seite trägt. Dieselbe Zahl wie in der
# Zugänge-Liste des Portals — eine Kanzlei, die zwischen beiden hin und her
# geht, soll nicht zwei Blätterungen im Kopf behalten müssen.
SEITE_GROESSE = 25
SEITE_MAX = 100

# Zeitbudget für die Frage „wie viele Rückfragen sind offen" über alle
# Boxen einer Seite. Gemessen wird je Box ein `git rev-parse` plus im
# schlechtesten Fall ein Indexaufbau; warm ist das ein paar Millisekunden.
BUDGET_GESAMT = 2.0
BUDGET_JE_BOX = 0.5
# Mehr Fäden als Boxen bringt nichts, weniger machen das Budget zur Lüge.
FAEDEN_MAX = 8

# Kontenrahmen, die `kontierung.py` kennt. Ein Tippfehler hier wäre ein
# stiller Fehler im Export — deshalb eine geschlossene Liste statt Freitext.
KONTENRAHMEN = ("SKR03", "SKR04")

# Rate-Limit auf das Anlegen, je Aufrufer (nicht je IP: das Anlegen setzt
# eine angemeldete Kanzlei voraus, und dieselbe Kanzlei sitzt oft hinter
# derselben Adresse wie ihr Nachbar). Muster wie `_LOGIN_VERSUCHE`.
_ANLAGE_VERSUCHE: dict[str, list[float]] = {}
ANLAGE_MAX = 10
ANLAGE_FENSTER = 60.0

# Was die Oberfläche über einen Status sagt. Keine Systemnamen, keine
# Zustandsautomaten — ein Satz, den eine Sachbearbeiterin vorlesen kann.
STATUS_TEXT = {
    "box_ausstehend": "Belegbox wird eingerichtet",
    "aktiv": "aktiv",
    "pausiert": "pausiert",
    "beendet": "beendet",
}
# Was sich von Hand setzen lässt. `box_ausstehend` fehlt mit Absicht: aus
# einem Mandanten mit Box wieder einen ohne zu machen, wäre kein Status-,
# sondern ein Datenwechsel.
STATUS_SETZBAR = ("aktiv", "pausiert", "beendet")


# ---------------------------------------------------------------------------
# Zugriff auf babu_web und die Portal-Datenbank — beides erst zur Laufzeit.
# ---------------------------------------------------------------------------

def _bw():
    import babu_web  # noqa: PLC0415
    return babu_web


@contextlib.contextmanager
def _sitzung():
    """Eine Portal-Verbindung unter dem Schloss.

    Dieselbe Form wie `with _DB_LOCK, _db() as c` in `babu_web`. Alles, was
    darin `mandanten`-Funktionen ruft, gibt seine Verbindung als `c=` mit —
    sonst nähme deren eigener Weg dasselbe einfache Schloss ein zweites Mal
    und hinge für immer.
    """
    bw = _bw()
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        yield c


def _fehler(text: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"fehler": text}, status_code=code)


def _wache(request: Request):
    """Nur die Verwaltung (Kanzlei oder Betreiber) kommt hier hinein.

    Phase 3: sobald `_kanzlei_wache` in `babu_web` steht, tritt sie hier an
    die Stelle von `_verwalter_wache` — sie prüft zusätzlich, dass der
    Aufrufer für DEN Mandanten arbeiten darf, statt dass jede Route unten
    das einzeln nachholt (`_darf_mandant`).
    """
    return _bw()._verwalter_wache(request)  # noqa: SLF001


def _ist_betreiber(un: str) -> bool:
    """`admin` ist die Betreiber-Ebene: sie sieht alle Kanzleien.

    ACHTUNG: liest über `rolle()` selbst aus der Datenbank und nimmt dabei
    `_DB_LOCK`. Das Schloss ist NICHT wiedereintrittsfähig — diese Frage
    wird deshalb in jeder Route EINMAL vor `_sitzung()` beantwortet und als
    `betreiber`-Wahrheitswert weitergereicht, statt tief drinnen noch einmal
    gestellt zu werden. Ein Aufruf innerhalb des Blocks hinge für immer.
    """
    return _bw().rolle(un) == "admin"


async def _koerper(request: Request) -> dict | None:
    """JSON-Körper mit derselben Grenze wie die Verwaltungsrouten daneben."""
    bw = _bw()
    try:
        return json.loads(await bw.koerper_lesen(request, 8 * 1024))
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Mitgliedschaft — bis Phase 3 hier, danach in `_kanzlei_wache`.
# ---------------------------------------------------------------------------

def _kanzleien_von(un: str, c) -> list[int]:
    """In welchen Kanzleien arbeitet dieser Zugang?

    Absichtlich eine Liste und keine einzelne Nummer: eine Vertretung kann
    für zwei Kanzleien arbeiten, und ein Modell, das das ausschließt, müsste
    man später aufbrechen.
    """
    return [int(z[0]) for z in c.execute(
        "SELECT kanzlei_id FROM kanzlei_mitglied WHERE un = ? ORDER BY kanzlei_id",
        (un,)).fetchall()]


def _eigene_kanzlei(un: str, c) -> int | None:
    """Die Kanzlei, in der dieser Zugang Inhaber ist — für das Anlegen."""
    z = c.execute("SELECT kanzlei_id FROM kanzlei_mitglied "
                  "WHERE un = ? AND rolle = 'inhaber' ORDER BY kanzlei_id",
                  (un,)).fetchone()
    return int(z[0]) if z else None


def _darf_mandant(un: str, mandant_id: int, betreiber: bool, c) -> bool:
    """Darf dieser Zugang diesen Mandanten sehen?

    Phase 3: dieselbe Frage stellt dann `_kanzlei_wache` einmal für alle
    Routen. Bis dahin steht sie hier — und zwar VOR jeder Antwort, die
    verrät, ob es den Mandanten überhaupt gibt.
    """
    if betreiber:
        return True
    return mandanten.kanzlei_mitglied(un, mandant_id, c=c)


# ---------------------------------------------------------------------------
# Mandantenliste
# ---------------------------------------------------------------------------

def _mandanten_lesen(un: str, betreiber: bool, c) -> list[dict]:
    """Alle Mandanten, die dieser Zugang sehen darf — mit Kanzlei-Namen.

    Ein einziges SELECT statt „Kanzleien holen, dann je Kanzlei die
    Mandanten": bei einer Vertretung mit zwei Kanzleien wären das zwei
    Abfragen, bei zehn zehn.
    """
    spalten = ("SELECT m.id, m.kanzlei_id, m.name, m.besitzer_un, m.box_ref, "
               "m.kontenrahmen, m.berater_nr, m.mandant_nr, m.status, "
               "m.angelegt, k.name FROM mandant m "
               "JOIN kanzlei k ON k.id = m.kanzlei_id")
    if betreiber:
        rohe = c.execute(spalten + " ORDER BY m.name").fetchall()
    else:
        kanzleien = _kanzleien_von(un, c)
        if not kanzleien:
            return []
        platz = ", ".join("?" for _ in kanzleien)
        rohe = c.execute(
            f"{spalten} WHERE m.kanzlei_id IN ({platz}) ORDER BY m.name",
            tuple(kanzleien)).fetchall()
    return [dict(zip(mandanten.MANDANT_SPALTEN + ("kanzlei_name",), r))
            for r in rohe]


def _passt(zeile: dict, q: str) -> bool:
    if not q:
        return True
    felder = (zeile.get("name"), zeile.get("besitzer_un"),
              zeile.get("berater_nr"), zeile.get("mandant_nr"),
              zeile.get("kanzlei_name"))
    return any(q in str(w or "").lower() for w in felder)


def _oeffentlich(zeile: dict, betreiber: bool) -> dict:
    """Was von einer Mandanten-Zeile nach außen geht.

    `box_ref` ist ein Ablagepfad im fremden Gateway — er sagt der Kanzlei
    nichts und gehört nicht auf ihren Bildschirm. Nur die Betreiber-Ebene
    bekommt ihn, weil genau sie ihn setzt.
    """
    offen = {
        "id": zeile["id"],
        "name": zeile["name"],
        "besitzer": zeile["besitzer_un"],
        "status": zeile["status"],
        "status_text": STATUS_TEXT.get(zeile["status"], zeile["status"]),
        "kanzlei_id": zeile["kanzlei_id"],
        "kanzlei_name": zeile.get("kanzlei_name") or "",
        "kontenrahmen": zeile["kontenrahmen"] or "",
        "berater_nr": zeile["berater_nr"] or "",
        "mandant_nr": zeile["mandant_nr"] or "",
        "angelegt": zeile["angelegt"],
        "belegbox_da": bool(zeile["box_ref"]),
    }
    if betreiber:
        offen["box_ref"] = zeile["box_ref"] or ""
    return offen


# ---------------------------------------------------------------------------
# Was in einer Box ansteht — nebenläufig, mit Budget.
# ---------------------------------------------------------------------------

def _box_befund(bw, un: str, mandant_id: int) -> dict:
    """Der Blick in EINE Belegbox. Läuft in einem eigenen Faden.

    `_im_box_kontext` setzt die Box für diesen Faden — ohne das läse jeder
    Faden die Default-Box, und die Übersicht zeigte für alle Mandanten
    dieselbe Zahl.
    """
    box = bx.box_von(un, mandant_id)
    idx = bw._im_box_kontext(box, bw.index_aktuell)  # noqa: SLF001
    belege = list(idx["belege"].values())
    rueckfragen = [z for z in belege if z["status"] in ("nachfrage", "unlesbar")]
    # „Ohne Freigabe" heißt: in dem Monat wartet noch etwas auf einen
    # Menschen. „Bereit zum Ausgeben" heißt: nichts wartet mehr, aber der
    # Stapel ist noch nicht heraus.
    monate: dict[str, dict] = {}
    for z in belege:
        m = z["monat"] or ""
        if not m:
            continue
        stand = monate.setdefault(m, {"offen": 0, "geprueft": 0, "exportiert": 0})
        if z["status"] in ("nachfrage", "unlesbar", "erfasst"):
            stand["offen"] += 1
        elif z["status"] == "geprüft":
            stand["geprueft"] += 1
        elif z["status"] == "exportiert":
            stand["exportiert"] += 1
    ohne_freigabe = sorted(m for m, s in monate.items() if s["offen"])
    export_faellig = sorted(m for m, s in monate.items()
                            if not s["offen"] and s["geprueft"])
    return {"rueckfragen": len(rueckfragen),
            "monate_ohne_freigabe": ohne_freigabe,
            "export_faellig": export_faellig,
            "erreichbar": True}


NICHT_ERREICHBAR = {"rueckfragen": None, "monate_ohne_freigabe": [],
                    "export_faellig": [], "erreichbar": False}
# Ein Mandant ohne Box hat nichts, in das man schauen könnte — das ist kein
# Fehler, sondern der Wartezustand aus Schritt 2 oben.
OHNE_BOX = {"rueckfragen": None, "monate_ohne_freigabe": [],
            "export_faellig": [], "erreichbar": True}


def _befunde(un: str, zeilen: list[dict]) -> dict[int, dict]:
    """Für jede Zeile der Seite: was steht an? Alles zusammen im Budget.

    Warum Fäden und kein `asyncio`: `index_aktuell()` ruft `git` über
    `subprocess` und ist durch und durch blockierend. Ein hängender Faden
    lässt sich nicht abbrechen — er wird deshalb NICHT abgewartet
    (`shutdown(wait=False)`), sein Mandant steht als „nicht erreichbar" in
    der Liste, und der Faden räumt sich selbst weg, wenn sein `git`
    zurückkommt.
    """
    bw = _bw()
    mit_box = [z for z in zeilen if z["box_ref"]]
    befunde: dict[int, dict] = {z["id"]: dict(OHNE_BOX) for z in zeilen
                                if not z["box_ref"]}
    if not mit_box:
        return befunde

    ende = time.monotonic() + BUDGET_GESAMT
    ex = ThreadPoolExecutor(max_workers=min(FAEDEN_MAX, len(mit_box)))
    try:
        auftraege = {ex.submit(_box_befund, bw, un, int(z["id"])): int(z["id"])
                     for z in mit_box}
        for auftrag, mid in auftraege.items():
            rest = min(BUDGET_JE_BOX, max(0.0, ende - time.monotonic()))
            try:
                befunde[mid] = auftrag.result(timeout=rest)
            except (ZeitAus, Exception):  # noqa: BLE001
                # Beides führt zur selben Zeile: eine Box, aus der gerade
                # keine Zahl kommt. Warum sie schweigt, gehört ins Log,
                # nicht auf den Bildschirm der Kanzlei.
                befunde[mid] = dict(NICHT_ERREICHBAR)
    finally:
        ex.shutdown(wait=False)
    return befunde


# ---------------------------------------------------------------------------
# Routen
# ---------------------------------------------------------------------------

@router.get("/mandanten")
def api_mandanten(request: Request, q: str = "", seite: int = 1,
                  je_seite: int = SEITE_GROESSE, status: str = "") -> JSONResponse:
    """Die Mandanten dieser Kanzlei — gesucht, geblättert, mit Stand.

    Gefiltert und geblättert wird im Server, nicht im Browser: bei
    hunderten Mandanten wären die Zeilen selbst schon die schwere Fracht,
    und der Blick in die Boxen (`_befunde`) lohnt sich nur für die 25, die
    jemand ansieht.
    """
    un, fehler = _wache(request)
    if fehler:
        return fehler
    betreiber = _ist_betreiber(un)      # vor `_sitzung()`, siehe dort
    with _sitzung() as c:
        alle = _mandanten_lesen(un, betreiber, c)
    suche = q.strip().lower()[:120]
    if status:
        alle = [z for z in alle if z["status"] == status]
    gefiltert = [z for z in alle if _passt(z, suche)]
    je_seite = max(1, min(int(je_seite or SEITE_GROESSE), SEITE_MAX))
    seiten = max(1, -(-len(gefiltert) // je_seite))
    seite = max(1, min(int(seite or 1), seiten))
    anfang = (seite - 1) * je_seite
    ausschnitt = gefiltert[anfang:anfang + je_seite]

    befunde = _befunde(un, ausschnitt)
    zeilen = []
    for z in ausschnitt:
        eintrag = _oeffentlich(z, betreiber)
        befund = befunde.get(int(z["id"]), dict(NICHT_ERREICHBAR))
        eintrag["rueckfragen"] = befund["rueckfragen"]
        eintrag["erreichbar"] = befund["erreichbar"]
        zeilen.append(eintrag)
    return JSONResponse({"mandanten": zeilen, "gesamt": len(gefiltert),
                         "seite": seite, "seiten": seiten,
                         "je_seite": je_seite, "darf_verknuepfen": betreiber})


@router.get("/mandanten/{mandant_id}")
def api_mandant(mandant_id: int, request: Request) -> JSONResponse:
    """Ein Mandant im Einzelnen — samt dem Satz für den Wartezustand."""
    un, fehler = _wache(request)
    if fehler:
        return fehler
    betreiber = _ist_betreiber(un)      # vor `_sitzung()`, siehe dort
    with _sitzung() as c:
        # Phase 3: `_kanzlei_wache` prüft das dann vor der Route.
        if not _darf_mandant(un, mandant_id, betreiber, c):
            # Derselbe Satz wie für „gibt es nicht": sonst ließe sich
            # abzählen, wie viele Mandanten die Nachbarkanzlei hat.
            return _fehler("Diesen Mandanten gibt es hier nicht.", 404)
        zeile = mandanten.mandant_holen(mandant_id, c=c)
        kanzlei = mandanten.kanzlei_holen(int(zeile["kanzlei_id"]), c=c) if zeile else None
    if zeile is None:
        return _fehler("Diesen Mandanten gibt es hier nicht.", 404)
    zeile["kanzlei_name"] = (kanzlei or {}).get("name") or ""
    antwort = _oeffentlich(zeile, betreiber)
    if not zeile["box_ref"]:
        antwort["hinweis"] = "Belegbox wird eingerichtet"
    return JSONResponse(antwort)


def _anlage_gebremst(un: str) -> bool:
    jetzt = time.time()
    versuche = [t for t in _ANLAGE_VERSUCHE.get(un, [])
                if jetzt - t < ANLAGE_FENSTER]
    _ANLAGE_VERSUCHE[un] = versuche
    if len(versuche) >= ANLAGE_MAX:
        return True
    versuche.append(jetzt)
    _bw()._zaehler_aufraeumen(_ANLAGE_VERSUCHE, jetzt, ANLAGE_FENSTER)  # noqa: SLF001
    return False


def _einladung_verschicken(bw, mandant_name: str, mail: str) -> str | None:
    """Der Link, mit dem der Salon sein eigenes Passwort setzt.

    Muster wie `einladung.py`: der Schlüssel steht genau einmal im Klartext
    — in dieser Nachricht — und in der Datenbank nur sein Hash. Eingelöst
    wird er über `/api/passwort-reset`, denn das Konto gibt es zu diesem
    Zeitpunkt schon (siehe Modulkopf).

    Gibt den Link zurück, damit die Kanzlei ihn notfalls selbst zustellen
    kann — ohne echten Mailversand liegt die Nachricht sonst nur im
    Postausgang und niemand erfährt davon.
    """
    import passwort_reset as pr  # noqa: PLC0415
    import postfach  # noqa: PLC0415
    if not bw._reset_anfordern_erlaubt(mail):  # noqa: SLF001
        return None
    bw._reset_aufraeumen(mail)  # noqa: SLF001
    token, modell = pr.anfordern(mail)
    with _sitzung() as c:
        c.execute("""INSERT INTO passwort_reset (token_hash, un, erstellt, laeuft_ab)
                     VALUES (?,?,?,?)""",
                  (modell.token_hash, modell.un, modell.erstellt.isoformat(),
                   modell.laeuft_ab.isoformat()))
    link = f"{bw.PORTAL_ORIGIN.rstrip('/')}/portal#reset/{token}"
    text = (f"Hallo,\n\n"
            f"dein Steuerbüro hat für „{mandant_name}“ einen Zugang zu babu "
            f"eingerichtet. Beim ersten Öffnen legst du dein Passwort fest:\n\n"
            f"    {link}\n\n"
            f"Der Link gilt {pr.FRIST.days} Tage und nur einmal. Danach meldest "
            f"du dich ganz normal mit dieser E-Mail-Adresse und deinem Passwort "
            f"an.\n\n"
            f"Wenn du damit nichts anfangen kannst, ignoriere diese Nachricht "
            f"einfach — ohne den Link passiert nichts.\n")
    ok, hinweis = postfach.senden(mail, "Dein Zugang zu babu ist eingerichtet",
                                  text, stempel=time.strftime("%Y%m%d-%H%M%S"))
    print(f"[kanzlei] Einladung an {mail}: {hinweis}", flush=True)
    return link


@router.post("/mandanten")
async def api_mandant_anlegen(request: Request) -> JSONResponse:
    """Einen Mandanten anlegen — Kanzlei, Mandant, Konto und Einladung.

    Vier Dinge in einem Schritt, weil kein einzelnes davon für sich nützlich
    ist: eine Kanzlei ohne Mandanten betreut niemanden, ein Mandant ohne
    Konto hat keinen Menschen, und ein Konto ohne Einladung kann sich nicht
    anmelden.
    """
    bw = _bw()
    if not bw._origin_ok(request):  # noqa: SLF001
        return _fehler("nicht erlaubt", 403)
    un, fehler = _wache(request)
    if fehler:
        return fehler
    if _anlage_gebremst(un):
        return _fehler("Gerade wurden viele Mandanten angelegt — "
                       "kurz warten, dann noch einmal.", 429)
    koerper = await _koerper(request)
    if koerper is None:
        return _fehler("JSON erwartet")

    import einladung as ei  # noqa: PLC0415
    name = str(koerper.get("name") or "").strip()[:120]
    mail = str(koerper.get("email") or "").strip().lower()[:200]
    kontenrahmen = str(koerper.get("kontenrahmen") or "").strip().upper()
    berater_nr = str(koerper.get("berater_nr") or "").strip()[:20]
    mandant_nr = str(koerper.get("mandant_nr") or "").strip()[:20]
    if not name:
        return _fehler("Bitte einen Namen für den Mandanten angeben.")
    if not ei.mail_gueltig(mail):
        return _fehler("Diese E-Mail-Adresse sieht nicht richtig aus.")
    if kontenrahmen and kontenrahmen not in KONTENRAHMEN:
        return _fehler("Als Kontenrahmen kennen wir SKR03 und SKR04.")

    with _sitzung() as c:
        kanzlei_id = _eigene_kanzlei(un, c)
        if kanzlei_id is None:
            # Erster Mandant: die Kanzlei entsteht mit. Ihr Name kommt aus
            # den Einstellungen, wenn dort einer steht — sonst aus dem
            # Zugang, damit in der Liste nicht „Kanzlei" als Name steht.
            kanzlei_name = ""
            for z in c.execute("SELECT wert FROM einstellungen "
                               "WHERE un=? AND schluessel='kanzlei_name'", (un,)):
                kanzlei_name = str(z[0] or "").strip()
            kanzlei_id = mandanten.kanzlei_anlegen(
                kanzlei_name[:120] or un.split("@")[0], un, c=c)
        doppelt = c.execute("SELECT 1 FROM mandant WHERE kanzlei_id=? AND "
                            "besitzer_un=?", (kanzlei_id, mail)).fetchone()
        if doppelt:
            return _fehler("Für diese E-Mail gibt es hier schon einen "
                           "Mandanten.", 409)
        mandant_id = mandanten.mandant_anlegen(
            kanzlei_id, name, mail, kontenrahmen or None,
            berater_nr or None, mandant_nr or None, c=c)

    # Konto und Einladung erst NACH dem Schloss: `nutzer_anlegen` nimmt es
    # selbst, und dasselbe Schloss ein zweites Mal zu nehmen hinge für immer.
    #
    # Das Startpasswort wird verworfen, ohne es je anzusehen: in der
    # Datenbank steht nur sein Hash, und wer sich anmelden will, geht über
    # den Link. Eine Kanzlei, die das Passwort ihres Mandanten kennt, wäre
    # genau die Vermischung, die Plan 21 §7 abstellt.
    neu = bw.nutzer_holen(mail) is None
    if neu:
        bw.nutzer_anlegen(mail, "", name, "salon", box=False)
    link = _einladung_verschicken(bw, name, mail)
    audit.audit(un, "kanzlei_mandant_anlegen", ziel_un=mail,
                mandant_id=str(mandant_id), kanzlei_id=kanzlei_id,
                konto_neu=neu, eingeladen=bool(link))
    return JSONResponse({"ok": True, "id": mandant_id, "name": name,
                         "besitzer": mail, "status": "box_ausstehend",
                         "status_text": STATUS_TEXT["box_ausstehend"],
                         "konto_neu": neu, "einladung_link": link,
                         "hinweis": "Belegbox wird eingerichtet"})


@router.post("/mandanten/{mandant_id}/box-verknuepfen")
async def api_box_verknuepfen(mandant_id: int, request: Request) -> JSONResponse:
    """Die eingerichtete Belegbox eintragen — nur die Betreiber-Ebene.

    Bewusst NICHT für die Kanzlei: wer sich hier einen beliebigen Verweis
    eintragen dürfte, schriebe sich damit in einen fremden Betrieb. Der
    Mensch, der die Box tatsächlich angelegt hat, trägt sie ein (Plan 21,
    Abschnitt 5).
    """
    bw = _bw()
    if not bw._origin_ok(request):  # noqa: SLF001
        return _fehler("nicht erlaubt", 403)
    un, fehler = _wache(request)
    if fehler:
        return fehler
    if not _ist_betreiber(un):
        return _fehler("Das trägt der Betreiber ein.", 403)
    koerper = await _koerper(request)
    if koerper is None:
        return _fehler("JSON erwartet")
    box_ref = str(koerper.get("box_ref") or "").strip().strip("/")[:200]
    if not box_ref or ".." in box_ref or box_ref.startswith("-"):
        return _fehler("Bitte einen gültigen Verweis auf die Belegbox angeben.")
    with _sitzung() as c:
        zeile = mandanten.mandant_holen(mandant_id, c=c)
        if zeile is None:
            return _fehler("Diesen Mandanten gibt es hier nicht.", 404)
        mandanten.box_verknuepfen(mandant_id, box_ref, c=c)
    audit.audit(un, "kanzlei_box_verknuepfen", ziel_un=zeile["besitzer_un"],
                mandant_id=str(mandant_id), box_ref=box_ref)
    return JSONResponse({"ok": True, "id": mandant_id, "status": "aktiv",
                         "status_text": STATUS_TEXT["aktiv"]})


@router.post("/mandanten/{mandant_id}/status")
async def api_status_setzen(mandant_id: int, request: Request) -> JSONResponse:
    """Mandat pausieren, beenden oder wieder aufnehmen.

    Nur der Inhaber der Kanzlei oder der Betreiber: eine Vertretung soll
    Belege bearbeiten dürfen, aber kein Mandat beenden.
    """
    bw = _bw()
    if not bw._origin_ok(request):  # noqa: SLF001
        return _fehler("nicht erlaubt", 403)
    un, fehler = _wache(request)
    if fehler:
        return fehler
    koerper = await _koerper(request)
    if koerper is None:
        return _fehler("JSON erwartet")
    neu = str(koerper.get("status") or "").strip()
    if neu not in STATUS_SETZBAR:
        return _fehler("Diesen Stand kennen wir nicht.")
    betreiber = _ist_betreiber(un)      # vor `_sitzung()`, siehe dort
    with _sitzung() as c:
        zeile = mandanten.mandant_holen(mandant_id, c=c)
        if zeile is None or not _darf_mandant(un, mandant_id, betreiber, c):
            return _fehler("Diesen Mandanten gibt es hier nicht.", 404)
        if not betreiber:
            kanzlei = mandanten.kanzlei_holen(int(zeile["kanzlei_id"]), c=c)
            if not kanzlei or kanzlei["inhaber_un"] != un:
                return _fehler("Das darf nur die Inhaberin der Kanzlei.", 403)
        if neu == "aktiv" and not zeile["box_ref"]:
            return _fehler("Solange die Belegbox eingerichtet wird, "
                           "lässt sich das nicht anschalten.")
        mandanten.status_setzen(mandant_id, neu, c=c)
    audit.audit(un, "kanzlei_mandant_status", ziel_un=zeile["besitzer_un"],
                mandant_id=str(mandant_id), status_neu=neu,
                status_alt=zeile["status"])
    return JSONResponse({"ok": True, "id": mandant_id, "status": neu,
                         "status_text": STATUS_TEXT[neu]})


@router.get("/warteschlange")
def api_warteschlange(request: Request, grenze: int = 50) -> JSONResponse:
    """Was über alle Mandanten hinweg ansteht.

    Beendete Mandanten fallen heraus — was dort noch offen war, ist es
    nicht mehr. Pausierte bleiben drin: pausiert heißt „gerade nicht", nicht
    „nie wieder", und die offenen Fragen von vorher stehen weiter da.
    """
    un, fehler = _wache(request)
    if fehler:
        return fehler
    betreiber = _ist_betreiber(un)      # vor `_sitzung()`, siehe dort
    with _sitzung() as c:
        alle = _mandanten_lesen(un, betreiber, c)
    grenze = max(1, min(int(grenze or 50), SEITE_MAX))
    aktive = [z for z in alle if z["status"] != "beendet"][:grenze]
    befunde = _befunde(un, aktive)

    eintraege = []
    for z in aktive:
        b = befunde.get(int(z["id"]), dict(NICHT_ERREICHBAR))
        eintraege.append({
            "id": z["id"], "name": z["name"], "status": z["status"],
            "status_text": STATUS_TEXT.get(z["status"], z["status"]),
            "belegbox_da": bool(z["box_ref"]),
            "rueckfragen": b["rueckfragen"],
            "monate_ohne_freigabe": b["monate_ohne_freigabe"],
            "export_faellig": b["export_faellig"],
            "erreichbar": b["erreichbar"],
            "hinweis": ("Belegbox wird eingerichtet" if not z["box_ref"]
                        else "" if b["erreichbar"] else "nicht erreichbar"),
        })
    # Wer am lautesten ruft, steht oben: erst die Rückfragen, dann die
    # Monate, die auf einen Menschen warten. Nicht erreichbare Mandanten
    # sortieren sich nach unten, weil ihre Zahlen nur fehlen.
    eintraege.sort(key=lambda e: (-(e["rueckfragen"] or 0),
                                  -len(e["monate_ohne_freigabe"]),
                                  e["name"].lower()))
    offen = [e for e in eintraege if (e["rueckfragen"] or 0)
             or e["monate_ohne_freigabe"] or e["export_faellig"]
             or not e["erreichbar"] or not e["belegbox_da"]]
    return JSONResponse({
        "eintraege": eintraege,
        "mandanten": len(aktive),
        "zaehler": {
            "rueckfragen": sum(e["rueckfragen"] or 0 for e in eintraege),
            "monate_ohne_freigabe": sum(len(e["monate_ohne_freigabe"])
                                        for e in eintraege),
            "export_faellig": sum(len(e["export_faellig"]) for e in eintraege),
            "nicht_erreichbar": sum(1 for e in eintraege if not e["erreichbar"]),
            "warten_auf_belegbox": sum(1 for e in eintraege
                                       if not e["belegbox_da"]),
            "offen": len(offen),
        },
    })


# `datetime` wird nur für den Typvertrag der Reset-Zeilen gebraucht — der
# Import steht oben, damit ein späterer Umbau ihn nicht sucht.
_ = datetime
