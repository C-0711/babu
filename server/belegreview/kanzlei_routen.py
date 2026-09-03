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

import calendar
import contextlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as ZeitAus
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

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
# Die Monatsspalte fragt EINE Box und baut dabei im schlechtesten Fall
# deren Index neu auf. Sie darf dafür länger brauchen als eine Zeile in
# einer Liste von fünfzig — aber nicht beliebig lange: was hier nicht
# ankommt, wird ein 503 mit einem Satz und kein hängender Browser.
BUDGET_DETAIL = 5.0
# Mehr Fäden als Boxen bringt nichts, weniger machen das Budget zur Lüge.
FAEDEN_MAX = 8

# Wie viele Monate die beiden Cockpit-Ansichten höchstens zeigen. Die
# Monatsspalte einer Kanzlei ist eine Arbeitsansicht, kein Archiv — wer
# weiter zurück will, geht in den Jahresabschluss.
MONATE_STANDARD = 6
MONATE_MAX = 24
UEBERSICHT_MONATE_STANDARD = 3
UEBERSICHT_MONATE_MAX = 12
# Wie viele offene Belege je Monat namentlich genannt werden. Wer mehr als
# zehn Rückfragen in einem Monat hat, braucht keine elfte Zeile, sondern
# einen Anruf.
RUECKFRAGEN_MAX = 10

# Was „offen" heißt: der Beleg wartet noch auf einen Menschen. Dieselben
# drei Stände wie in `_box_befund` — sie stehen hier einmal, damit die
# Monatsansicht und die Warteschlange nicht auseinanderlaufen können.
OFFEN_STAENDE = ("nachfrage", "unlesbar", "erfasst")

# Der Stand eines Monats in vier Wörtern. „leer" heißt: da war noch nichts.
# „offen": etwas wartet. „pruefbereit": nichts wartet mehr, der Stapel ist
# aber noch nicht heraus. „exportiert": er ist heraus.
STAND_LEER = "leer"
STAND_OFFEN = "offen"
STAND_PRUEFBEREIT = "pruefbereit"
STAND_EXPORTIERT = "exportiert"
# Die Zelle einer Box, die gerade nichts sagt. Ein Fragezeichen und keine
# Null: eine Null behauptet, es sei nichts offen.
STAND_UNBEKANNT = "?"

# An welchen Wochentagen ein Salon üblicherweise offen hat (0 = Montag).
# Es gibt bis heute keine Einstellung dafür — `oeffnet`/`schliesst` sind
# Uhrzeiten, keine Tage. Trägt der Betrieb später `oeffnungstage` ein, wird
# sie gelesen (siehe `_oeffnungstage`); bis dahin gilt Montag bis Samstag.
OEFFNUNGSTAGE_STANDARD = (0, 1, 2, 3, 4, 5)
_WOCHENTAG_KUERZEL = {"mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4,
                      "sa": 5, "so": 6}

# Was die Oberfläche sagt, wenn eine Box gerade nicht antwortet oder noch
# gar nicht da ist. Beides sind Sätze für Menschen, keine Statuscodes.
BOX_HAENGT = "Belegbox gerade nicht erreichbar"
BOX_KOMMT = "Belegbox wird eingerichtet"

# Kontenrahmen, die `kontierung.py` kennt. Ein Tippfehler hier wäre ein
# stiller Fehler im Export — deshalb eine geschlossene Liste statt Freitext.
KONTENRAHMEN = ("SKR03", "SKR04")

# Rate-Limit auf das Anlegen, je Aufrufer (nicht je IP: das Anlegen setzt
# eine angemeldete Kanzlei voraus, und dieselbe Kanzlei sitzt oft hinter
# derselben Adresse wie ihr Nachbar). Muster wie `_LOGIN_VERSUCHE`.
_ANLAGE_VERSUCHE: dict[str, list[float]] = {}
ANLAGE_MAX = 10
ANLAGE_FENSTER = 60.0

# Dieselbe Bremse für das Verknüpfen einer Box — seltener als das Anlegen
# (nur die Betreiber-Ebene darf das, Abschnitt „Verknüpfen" oben), aber ein
# falsch getippter `box_ref` schreibt einen Mandanten in einen fremden
# Betrieb, also lohnt sich auch hier ein Riegel gegen ein Skript, das die
# Route in einer Schleife trifft.
_VERKNUEPFEN_VERSUCHE: dict[str, list[float]] = {}
VERKNUEPFEN_MAX = 20
VERKNUEPFEN_FENSTER = 60.0

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


def _nebenlaeufig(un: str, zeilen: list[dict], arbeit, leer: dict,
                  fehler: dict, *zusatz, budget: tuple[float, float] | None = None,
                  ) -> dict[int, dict]:
    """Für jede Zeile mit Box: `arbeit(bw, un, id, *zusatz)` — im Budget.

    Warum Fäden und kein `asyncio`: `index_aktuell()` ruft `git` über
    `subprocess` und ist durch und durch blockierend. Ein hängender Faden
    lässt sich nicht abbrechen — er wird deshalb NICHT abgewartet
    (`shutdown(wait=False)`), sein Mandant steht als „nicht erreichbar" in
    der Liste, und der Faden räumt sich selbst weg, wenn sein `git`
    zurückkommt.

    `arbeit` wird als Argument hereingereicht und nicht fest verdrahtet,
    weil zwei Ansichten dasselbe Muster brauchen — die Warteschlange fragt
    „was steht an", die Übersicht „wie steht jeder Monat". Der Aufrufer
    reicht dabei das Modulattribut herein, damit ein `monkeypatch` im Test
    weiter greift.
    """
    bw = _bw()
    gesamt, je_box = budget or (BUDGET_GESAMT, BUDGET_JE_BOX)
    mit_box = [z for z in zeilen if z["box_ref"]]
    befunde: dict[int, dict] = {z["id"]: dict(leer) for z in zeilen
                                if not z["box_ref"]}
    if not mit_box:
        return befunde

    ende = time.monotonic() + gesamt
    ex = ThreadPoolExecutor(max_workers=min(FAEDEN_MAX, len(mit_box)))
    try:
        auftraege = {ex.submit(arbeit, bw, un, int(z["id"]), *zusatz):
                     int(z["id"]) for z in mit_box}
        for auftrag, mid in auftraege.items():
            rest = min(je_box, max(0.0, ende - time.monotonic()))
            try:
                befunde[mid] = auftrag.result(timeout=rest)
            except (ZeitAus, Exception):  # noqa: BLE001
                # Beides führt zur selben Zeile: eine Box, aus der gerade
                # keine Zahl kommt. Warum sie schweigt, gehört ins Log,
                # nicht auf den Bildschirm der Kanzlei.
                befunde[mid] = dict(fehler)
    finally:
        ex.shutdown(wait=False)
    return befunde


def _befunde(un: str, zeilen: list[dict]) -> dict[int, dict]:
    """Für jede Zeile der Seite: was steht an? Alles zusammen im Budget."""
    return _nebenlaeufig(un, zeilen, _box_befund, OHNE_BOX, NICHT_ERREICHBAR)


# ---------------------------------------------------------------------------
# Die Monatsspalte — was in einem Monat eines Mandanten steht.
#
# Alles hier ist reine Rechnung auf einem einmal gelesenen Index. Ein Blick
# in die Box kostet einen `git`-Aufruf; sechs Monate kosten deshalb keinen
# sechsfachen, sondern denselben einen.
# ---------------------------------------------------------------------------

def _heute() -> date:
    """Der heutige Tag — als eigene Funktion, damit ein Test ihn festhalten
    kann. Ohne das hinge jede Erwartung an der Uhr des Rechners."""
    return date.today()


def _monatsliste(anzahl: int, bis: date | None = None) -> list[str]:
    """Die letzten `anzahl` Monate, jüngster zuerst — auch die leeren.

    Leere Monate stehen ausdrücklich mit drin: eine Kanzlei muss sehen,
    dass im Juli nichts kam. Eine Liste, die nur die Monate mit Belegen
    zeigt, verschweigt genau den Fall, der Arbeit macht.
    """
    heute = bis or _heute()
    jahr, monat = heute.year, heute.month
    aus = []
    for _ in range(anzahl):
        aus.append(f"{jahr:04d}-{monat:02d}")
        monat -= 1
        if monat == 0:
            jahr, monat = jahr - 1, 12
    return aus


def _oeffnungstage(einstellungen: dict) -> tuple[int, ...]:
    """An welchen Wochentagen hat dieser Betrieb auf? (0 = Montag)

    Gelesen wird der Schlüssel `oeffnungstage` aus den Einstellungen des
    MANDANTEN — nicht denen der Kanzlei. Es gibt heute kein Formularfeld
    dafür (`oeffnet`/`schliesst` sind Uhrzeiten); bis es eines gibt, greift
    Montag bis Samstag. Erlaubt sind Zahlen (1 = Montag … 7 = Sonntag) und
    Kürzel („mo,di,mi,do,fr,sa").
    """
    roh = str((einstellungen or {}).get("oeffnungstage") or "").strip().lower()
    if not roh:
        return OEFFNUNGSTAGE_STANDARD
    tage: set[int] = set()
    for stueck in re.split(r"[^a-z0-9]+", roh):
        if not stueck:
            continue
        if stueck.isdigit():
            if 1 <= int(stueck) <= 7:
                tage.add(int(stueck) - 1)
        elif stueck[:2] in _WOCHENTAG_KUERZEL:
            tage.add(_WOCHENTAG_KUERZEL[stueck[:2]])
    return tuple(sorted(tage)) or OEFFNUNGSTAGE_STANDARD


def _tage_erwartet(monat: str, tage: tuple[int, ...], heute: date) -> int:
    """Wie viele Kassentage dieser Monat haben müsste.

    Im laufenden Monat wird nur bis heute gezählt — sonst stünde am 3. des
    Monats „3 von 26" da, und die Kanzlei hielte einen ganz normalen Stand
    für einen Rückstand.
    """
    jahr, mon = int(monat[:4]), int(monat[5:7])
    if (jahr, mon) > (heute.year, heute.month):
        return 0
    letzter = calendar.monthrange(jahr, mon)[1]
    if (jahr, mon) == (heute.year, heute.month):
        letzter = min(letzter, heute.day)
    return sum(1 for t in range(1, letzter + 1)
               if date(jahr, mon, t).weekday() in tage)


def _monatsstand(zaehler: dict, export_am: str | None, kassentage: int) -> str:
    """Der Stand eines Monats in einem Wort — die Reihenfolge ist die Regel.

    Zuerst der Export: liegt der Stapel in der Box, ist der Monat aus dem
    Haus, egal was danach noch hereinkam. Dann das Offene, weil es Arbeit
    ist. „pruefbereit" ist der Rest mit Inhalt, „leer" der ohne.
    """
    if export_am:
        return STAND_EXPORTIERT
    if zaehler["offen"]:
        return STAND_OFFEN
    if zaehler["gesamt"] or kassentage:
        return STAND_PRUEFBEREIT
    return STAND_LEER


def _zaehler(belege: list[dict]) -> dict:
    stand = {"gesamt": len(belege), "offen": 0, "geprueft": 0, "exportiert": 0}
    for z in belege:
        if z["status"] in OFFEN_STAENDE:
            stand["offen"] += 1
        elif z["status"] == "geprüft":
            stand["geprueft"] += 1
        elif z["status"] == "exportiert":
            stand["exportiert"] += 1
    return stand


def _rueckfragen(belege: list[dict]) -> list[dict]:
    """Die offenen Belege eines Monats, mit der Frage im Klartext.

    Die Frage ist die erste aus `felder.offen` — die Liste steht dem Beleg
    im Index schon zur Verfügung, und die erste ist die, die der Salon
    beantworten muss, bevor die zweite überhaupt Sinn ergibt.
    """
    offen = [z for z in belege if z["status"] in OFFEN_STAENDE]
    offen.sort(key=lambda z: (z["hochgeladen"] or "", z["stamm"]), reverse=True)
    aus = []
    for z in offen[:RUECKFRAGEN_MAX]:
        fragen = [str(f) for f in (z.get("offen") or []) if f]
        aus.append({"stamm": z["stamm"], "lieferant": z.get("lieferant"),
                    "brutto": z.get("brutto"),
                    "frage": fragen[0] if fragen else ""})
    return aus


def _umsatz(blaetter: list[dict]) -> float | None:
    """Tagesumsatz eines Monats aus den Kassenblättern — bar plus Karte.

    Bewusst NICHT `monatsabschluss.erloese_monat`: das rechnet Gutscheine,
    Rechnungen und Steuersätze mit hinein und braucht dafür Einstellungen
    und die Versteuerungsart. Hier steht eine Zahl neben der Anzahl der
    Kassentage — sie soll dasselbe sagen wie die Kasse, nicht mehr.
    """
    if not blaetter:
        return None
    summe = 0.0
    for b in blaetter:
        for feld in ("einnahmenBar", "ecZahlungen"):
            try:
                summe += float(b.get(feld) or 0)
            except (TypeError, ValueError):
                pass
    return round(summe, 2)


def _monats_befund(bw, un: str, mandant_id: int, monate: tuple[str, ...],
                   oeffnungstage: tuple[int, ...], heute: date) -> dict:
    """Ein Blick in EINE Box, aus dem alle angefragten Monate fallen.

    Läuft in einem eigenen Faden, deshalb `_im_box_kontext` — ohne das läse
    der Faden die Default-Box (siehe `_box_befund`).
    """
    box = bx.box_von(un, mandant_id)
    idx = bw._im_box_kontext(box, bw.index_aktuell)  # noqa: SLF001
    belege = list(idx["belege"].values())
    blaetter = idx.get("kassenblaetter") or {}
    zeiten = idx.get("zeiten") or {}

    aus = []
    for monat in monate:
        m_belege = [z for z in belege if z["monat"] == monat]
        zaehler = _zaehler(m_belege)
        tage = sorted(t for t in blaetter if str(t).startswith(monat))
        # Der festgeschriebene Stapel liegt als `export/<monat>/stapel.json`
        # in der Box (siehe `api_export(festschreiben=1)`); wann er dorthin
        # kam, sagt der Commit — dafür trägt der Index `zeiten`.
        export_am = (zeiten.get(f"export/{monat}/stapel.json") or {}).get("zeit")
        aus.append({
            "monat": monat,
            "belege": zaehler,
            "rueckfragen": _rueckfragen(m_belege),
            # `float(...)`: ohne das käme für einen leeren Monat die
            # Ganzzahl 0 heraus und für jeden anderen eine Kommazahl — die
            # Oberfläche formatiert sonst zwei verschiedene Dinge.
            "brutto_summe": round(float(sum(z.get("brutto") or 0
                                            for z in m_belege)), 2),
            "kassenbuch": {
                "tage_eingetragen": len(tage),
                "tage_erwartet": _tage_erwartet(monat, oeffnungstage, heute),
                "letzter_tag": tage[-1] if tage else None,
            },
            "abschluss": {
                "stand": _monatsstand(zaehler, export_am, len(tage)),
                "export_am": export_am,
            },
            "umsatz": _umsatz([blaetter[t] for t in tage]),
        })
    return {"monate": aus, "erreichbar": True}


def _uebersicht_befund(bw, un: str, mandant_id: int,
                       monate: tuple[str, ...]) -> dict:
    """Dieselbe Box, aber nur so viel, wie in eine Zeile der Matrix passt.

    Eigene Funktion und nicht `_monats_befund` mit Beschnitt: die Übersicht
    liest über ALLE Mandanten und darf deshalb keine Rückfragetexte,
    Umsätze und Kassenzahlen mitschleppen, die niemand ansieht.
    """
    box = bx.box_von(un, mandant_id)
    idx = bw._im_box_kontext(box, bw.index_aktuell)  # noqa: SLF001
    belege = list(idx["belege"].values())
    blaetter = idx.get("kassenblaetter") or {}
    zeiten = idx.get("zeiten") or {}

    zellen = []
    for monat in monate:
        m_belege = [z for z in belege if z["monat"] == monat]
        zaehler = _zaehler(m_belege)
        kassentage = sum(1 for t in blaetter if str(t).startswith(monat))
        export_am = (zeiten.get(f"export/{monat}/stapel.json") or {}).get("zeit")
        zellen.append({"monat": monat,
                       "stand": _monatsstand(zaehler, export_am, kassentage),
                       "offen": zaehler["offen"], "gesamt": zaehler["gesamt"]})
    # Die letzte Aktivität ist der jüngste Beleg-Upload. Nicht der jüngste
    # Commit: in der Box liegen auch Schreibvorgänge, die babu selbst
    # auslöst, und die sagen über den Mandanten nichts.
    letzte = max((z["hochgeladen"] or "" for z in belege), default="")
    return {"zellen": zellen,
            "rueckfragen": sum(1 for z in belege
                               if z["status"] in ("nachfrage", "unlesbar")),
            "letzte_aktivitaet": letzte or None,
            "erreichbar": True}


def _uebersicht_leer(monate: tuple[str, ...], stand: str) -> dict:
    """Eine Zeile ohne Zahlen — für „keine Box" und „nicht erreichbar"."""
    return {"zellen": [{"monat": m, "stand": stand, "offen": None,
                        "gesamt": None} for m in monate],
            "rueckfragen": None, "letzte_aktivitaet": None,
            "erreichbar": stand != STAND_UNBEKANNT}


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


def _verknuepfen_gebremst(un: str) -> bool:
    jetzt = time.time()
    versuche = [t for t in _VERKNUEPFEN_VERSUCHE.get(un, [])
                if jetzt - t < VERKNUEPFEN_FENSTER]
    _VERKNUEPFEN_VERSUCHE[un] = versuche
    if len(versuche) >= VERKNUEPFEN_MAX:
        return True
    versuche.append(jetzt)
    _bw()._zaehler_aufraeumen(_VERKNUEPFEN_VERSUCHE, jetzt,  # noqa: SLF001
                              VERKNUEPFEN_FENSTER)
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

    # Das Konto VOR dem Mandanten: `mandant.besitzer_un` zeigt per
    # Fremdschlüssel auf `nutzer.email`, und Postgres prüft das wirklich
    # (SQLite nicht — so blieb die umgekehrte Reihenfolge lange unbemerkt).
    # `nutzer_anlegen` nimmt das Schloss selbst, deshalb steht es zwischen
    # den beiden Sitzungen und nicht in einer.
    #
    # Das Startpasswort wird verworfen, ohne es je anzusehen: in der
    # Datenbank steht nur sein Hash, und wer sich anmelden will, geht über
    # den Link. Eine Kanzlei, die das Passwort ihres Mandanten kennt, wäre
    # genau die Vermischung, die Plan 21 §7 abstellt.
    neu = bw.nutzer_holen(mail) is None
    if neu:
        bw.nutzer_anlegen(mail, "", name, "salon", box=False)

    with _sitzung() as c:
        # Noch einmal prüfen — zwischen den Sitzungen lag kein Schloss.
        if c.execute("SELECT 1 FROM mandant WHERE kanzlei_id=? AND besitzer_un=?",
                     (kanzlei_id, mail)).fetchone():
            return _fehler("Für diese E-Mail gibt es hier schon einen "
                           "Mandanten.", 409)
        mandant_id = mandanten.mandant_anlegen(
            kanzlei_id, name, mail, kontenrahmen or None,
            berater_nr or None, mandant_nr or None, c=c)
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
    if _verknuepfen_gebremst(un):
        return _fehler("Gerade wurden viele Boxen verknüpft — "
                       "kurz warten, dann noch einmal.", 429)
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


@router.get("/mandanten/{mandant_id}/monate")
def api_mandant_monate(mandant_id: int, request: Request,
                       anzahl: int = MONATE_STANDARD) -> JSONResponse:
    """Die Monatsspalte EINES Mandanten — die Sicht, in der die Kanzlei arbeitet.

    Sie beantwortet vier Fragen auf einmal, und zwar für jeden der letzten
    Monate: Wie viele Belege sind da und wie viele warten noch? Welche
    Rückfragen stehen namentlich offen? Ist das Kassenbuch geführt? Und ist
    der Monat schon aus dem Haus?

    Die drei Fehlerfälle sind absichtlich verschieden:

    * **404** — diesen Mandanten gibt es hier nicht. Derselbe Satz wie in
      `api_mandant`, damit sich die Nachbarkanzlei nicht abzählen lässt.
    * **409** — es gibt ihn, aber seine Belegbox wird noch eingerichtet.
      Kein Rechteproblem, sondern der Wartezustand.
    * **503** — die Box ist da, antwortet aber nicht innerhalb des Budgets.
      Ein Zustand des Servers, nicht der Anfrage; die Kanzlei soll es gleich
      noch einmal versuchen und nicht die Nummer für falsch halten.
    """
    un, fehler = _wache(request)
    if fehler:
        return fehler
    anzahl = max(1, min(int(anzahl or MONATE_STANDARD), MONATE_MAX))
    betreiber = _ist_betreiber(un)      # vor `_sitzung()`, siehe dort
    with _sitzung() as c:
        if not _darf_mandant(un, mandant_id, betreiber, c):
            return _fehler("Diesen Mandanten gibt es hier nicht.", 404)
        zeile = mandanten.mandant_holen(mandant_id, c=c)
    if zeile is None:
        return _fehler("Diesen Mandanten gibt es hier nicht.", 404)
    if not zeile["box_ref"]:
        return _fehler(BOX_KOMMT, 409)

    # Die Öffnungstage gehören dem MANDANTEN, nicht der Kanzlei — dieselbe
    # Regel wie `salon_von_aktiv`, nur ohne Kopf: hier steht der Besitzer
    # ohnehin in der Zeile. Und ausdrücklich VOR dem Faden gelesen:
    # `db_einstellungen` nimmt `_DB_LOCK`, und das ist nicht
    # wiedereintrittsfähig.
    einstellungen = _bw().db_einstellungen(zeile["besitzer_un"])
    heute = _heute()
    monate = tuple(_monatsliste(anzahl, heute))
    befund = _nebenlaeufig(un, [dict(zeile)], _monats_befund, OHNE_BOX,
                           NICHT_ERREICHBAR, monate,
                           _oeffnungstage(einstellungen), heute,
                           budget=(BUDGET_DETAIL, BUDGET_DETAIL),
                           ).get(int(mandant_id)) or dict(NICHT_ERREICHBAR)
    if not befund.get("erreichbar"):
        return _fehler(BOX_HAENGT, 503)

    return JSONResponse({
        "mandant": {"id": zeile["id"], "name": zeile["name"],
                    "besitzer": zeile["besitzer_un"],
                    "status": zeile["status"],
                    "status_text": STATUS_TEXT.get(zeile["status"],
                                                   zeile["status"])},
        "anzahl": anzahl,
        "monate": befund["monate"],
    })


@router.get("/uebersicht")
def api_uebersicht(request: Request,
                   monate: int = UEBERSICHT_MONATE_STANDARD) -> JSONResponse:
    """Alle Mandanten mal die letzten Monate — eine Zeile je Betrieb.

    Der Unterschied zur Warteschlange: die zählt zusammen, was insgesamt
    ansteht, diese hier zeigt, WO es steht. Eine Kanzlei sieht damit auf
    einen Blick, welcher Mandant im Juli hängengeblieben ist, statt sich
    das aus drei Zahlen zusammenzureimen.

    Beendete Mandanten fallen heraus, pausierte bleiben — dieselbe Regel
    und derselbe Grund wie in `api_warteschlange`. Eine Box, die nicht
    antwortet, bekommt Fragezeichen statt Nullen: eine Null behauptet, es
    sei nichts offen.
    """
    un, fehler = _wache(request)
    if fehler:
        return fehler
    anzahl = max(1, min(int(monate or UEBERSICHT_MONATE_STANDARD),
                        UEBERSICHT_MONATE_MAX))
    betreiber = _ist_betreiber(un)      # vor `_sitzung()`, siehe dort
    with _sitzung() as c:
        alle = _mandanten_lesen(un, betreiber, c)
    aktive = [z for z in alle if z["status"] != "beendet"][:SEITE_MAX]
    spalten = tuple(_monatsliste(anzahl))

    ohne_box = _uebersicht_leer(spalten, STAND_LEER)
    nicht_da = _uebersicht_leer(spalten, STAND_UNBEKANNT)
    befunde = _nebenlaeufig(un, aktive, _uebersicht_befund, ohne_box,
                            nicht_da, spalten)

    zeilen = []
    for z in aktive:
        b = befunde.get(int(z["id"]), nicht_da)
        zellen = b["zellen"]
        zeilen.append({
            "id": z["id"], "name": z["name"], "status": z["status"],
            "status_text": STATUS_TEXT.get(z["status"], z["status"]),
            "belegbox_da": bool(z["box_ref"]),
            "erreichbar": b["erreichbar"],
            "hinweis": (BOX_KOMMT if not z["box_ref"]
                        else "" if b["erreichbar"] else BOX_HAENGT),
            "rueckfragen": b["rueckfragen"],
            "offen_gesamt": sum(zl["offen"] or 0 for zl in zellen),
            "letzte_aktivitaet": b["letzte_aktivitaet"],
            "zellen": zellen,
        })
    # Wer am meisten offen hat, steht oben — und bei Gleichstand der mit
    # den meisten Rückfragen. Boxen ohne Zahlen sinken damit von selbst
    # nach unten, weil ihre Zähler leer sind und nicht null.
    zeilen.sort(key=lambda e: (-e["offen_gesamt"], -(e["rueckfragen"] or 0),
                               e["name"].lower()))
    return JSONResponse({
        "monate": list(spalten),
        "mandanten": zeilen,
        "zaehler": {
            "mandanten": len(zeilen),
            "rueckfragen": sum(e["rueckfragen"] or 0 for e in zeilen),
            "offen": sum(e["offen_gesamt"] for e in zeilen),
            "nicht_erreichbar": sum(1 for e in zeilen
                                    if e["belegbox_da"] and not e["erreichbar"]),
            "warten_auf_belegbox": sum(1 for e in zeilen
                                       if not e["belegbox_da"]),
        },
    })


# ---------------------------------------------------------------------------
# Massenimport: ein Ordner Belege je Mandant.
#
# Die Mechanik steht in `belegimport.py`; hier stehen nur die fünf Türen und
# was an ihnen geprüft wird. Ein `X-Mandant`-Kopf ist ausdrücklich NICHT
# nötig: der Mandant steht im Pfad, und die Route setzt den Kontext selbst
# (`bx.box_von` beim Ablegen, `_im_mandanten_kontext` für den Faden). Ein
# Kopf daneben würde nur eine zweite Wahrheit über denselben Mandanten
# einführen.
# ---------------------------------------------------------------------------

def _import_mandant(un: str, mandant_id: int, betreiber: bool):
    """(Mandantenzeile, Fehlerantwort) — die Tür vor jeder Import-Route.

    Reihenfolge wie überall hier: erst darf-ich-diesen-Mandanten-sehen
    (404, nie 403 — sonst ließe sich die Nachbarkanzlei abzählen), dann
    die beiden Zustände, in denen ein Import keinen Sinn ergibt. Beide sind
    kein Rechteproblem, deshalb 409.
    """
    with _sitzung() as c:
        if not _darf_mandant(un, mandant_id, betreiber, c):
            return None, _fehler("Diesen Mandanten gibt es hier nicht.", 404)
        zeile = mandanten.mandant_holen(mandant_id, c=c)
    if zeile is None:
        return None, _fehler("Diesen Mandanten gibt es hier nicht.", 404)
    if not zeile["box_ref"]:
        return None, _fehler(BOX_KOMMT, 409)
    if zeile["status"] != "aktiv":
        return None, _fehler(
            "Mandat ist pausiert" if zeile["status"] == "pausiert"
            else "Mandat ist beendet", 409)
    return zeile, None


def _import_tuer(request: Request, mandant_id: int, schreibend: bool = True):
    """Origin, Verwaltung, Mandant — in genau dieser Reihenfolge.

    `_ist_betreiber` steht VOR `_sitzung()`: das Schloss ist nicht
    wiedereintrittsfähig (siehe dort), ein Aufruf innerhalb des Blocks
    hinge für immer.
    """
    bw = _bw()
    if schreibend and not bw._origin_ok(request):  # noqa: SLF001
        return None, None, _fehler("nicht erlaubt", 403)
    un, fehler = _wache(request)
    if fehler:
        return None, None, fehler
    zeile, fehler = _import_mandant(un, mandant_id, _ist_betreiber(un))
    if fehler:
        return None, None, fehler
    return un, zeile, None


_OHNE_ABLAGE = {"Cache-Control": "no-store"}


@router.post("/mandanten/{mandant_id}/import/dateien")
async def api_import_datei(mandant_id: int, request: Request,
                           name: str = "beleg.jpg",
                           monat: str = "") -> JSONResponse:
    """Eine Datei in den Zwischenspeicher legen — das Portal ruft das je Datei.

    Ein Roh-Body je Datei, wie `/api/hochladen`: `_koerper` daneben nimmt
    JSON bis 8 KiB und wäre hier die falsche Tür. Geschrieben wird noch
    nichts in die Belegbox — erst „Start" tut das.
    """
    import belegimport as bi  # noqa: PLC0415
    bw = _bw()
    un, zeile, fehler = _import_tuer(request, mandant_id)
    if fehler:
        return fehler
    endung = Path(name).suffix.lower()
    if endung not in bi.IMPORT_ENDUNGEN:
        return _fehler("Damit können wir nichts anfangen — Fotos und PDF gehen.")
    if not re.match(r"^\d{4}-\d{2}$", monat or ""):
        monat = time.strftime("%Y-%m")
    try:
        daten = await bw.koerper_lesen(request, bw.HOCHLADEN_MAX)
    except bw.KoerperZuGross:
        return _fehler("Diese Datei ist zu groß.", 413)
    if not daten:
        return _fehler("Diese Datei ist leer.")

    import boxschreiber  # noqa: PLC0415
    box = bx.box_von(un, mandant_id)
    sha = bi.sha_von(daten)
    with bi._IMPORT_LOCK:  # noqa: SLF001
        status = bi._IMPORT_JOBS.get(mandant_id)  # noqa: SLF001
        if status is not None and status["stand"] in bi.LAUFEND:
            return _fehler("Für diesen Mandanten läuft gerade ein Import.", 409)
        if status is None or status["stand"] != "sammelt":
            status = bi.neuer_lauf(mandant_id, un, monat)
            bi._IMPORT_JOBS[mandant_id] = status  # noqa: SLF001
            bi._IMPORT_SHAS[mandant_id] = set()  # noqa: SLF001
        if len(status["dateien"]) >= bi.IMPORT_MAX_DATEIEN:
            return _fehler(f"Mehr als {bi.IMPORT_MAX_DATEIEN} Belege auf "
                           "einmal sind zu viel — bitte in zwei Portionen.")
        schon_im_lauf = sha in bi._IMPORT_SHAS.setdefault(mandant_id, set())  # noqa: SLF001

    # Byte für Byte dasselbe wie etwas, das schon in der Box liegt (oder
    # in diesem Lauf schon einmal kam)? Dann nichts ablegen und nichts
    # lesen — nur sagen, wo es steht.
    war_schon = (await run_in_threadpool(
        bw._im_box_kontext, box, bw._blob_schon_da, daten))  # noqa: SLF001
    if war_schon or schon_im_lauf:
        grund = ("War schon da — nichts doppelt abgelegt." if war_schon
                 else "War in dieser Auswahl schon dabei.")
        with bi._IMPORT_LOCK:  # noqa: SLF001
            status["doppelt"] += 1
            status["dateien"].append(dict(
                bi.neue_datei(name, "", "", len(daten)),
                stand="doppelt", war_schon=war_schon or "", grund=grund))
            status["gesamt"] = len(status["dateien"])
        await run_in_threadpool(bi._festhalten, bw, status)  # noqa: SLF001
        return JSONResponse({"ok": True, "lauf": status["lauf"], "name": name,
                             "doppelt": True, "war_schon": war_schon or "",
                             "gesamt": status["gesamt"]})

    dateiname = boxschreiber.beleg_dateiname(name)
    stamm = dateiname.rsplit(".", 1)[0]
    ordner = bi._lauf_ordner(mandant_id, status["lauf"])  # noqa: SLF001
    try:
        ordner.mkdir(parents=True, exist_ok=True)
        (ordner / stamm).write_bytes(daten)
    except OSError:
        return _fehler("Die Datei ließ sich gerade nicht zwischenlagern — "
                       "gleich nochmal.", 503)
    bi._import_tmp_aufraeumen()  # noqa: SLF001
    with bi._IMPORT_LOCK:  # noqa: SLF001
        bi._IMPORT_SHAS[mandant_id].add(sha)  # noqa: SLF001
        status["dateien"].append(bi.neue_datei(
            name, f"docs/{monat}/{dateiname}", stamm, len(daten)))
        status["gesamt"] = len(status["dateien"])
    await run_in_threadpool(bi._festhalten, bw, status)  # noqa: SLF001
    return JSONResponse({"ok": True, "lauf": status["lauf"], "name": name,
                         "gesamt": status["gesamt"]})


def _lauf_starten(bw, un: str, mandant_id: int, status: dict) -> None:
    """Den Faden loslassen — mit Box UND Mandant im Gepäck.

    `_im_mandanten_kontext` statt `_im_box_kontext`: der Faden BUCHT, und
    Profil wie Kontenrahmen hängen am Mandanten, nicht an der Box (siehe
    `babu_web`). Ohne das bekäme jeder Mandant den Kontenrahmen der Kanzlei.
    """
    import belegimport as bi  # noqa: PLC0415
    box = bx.box_von(un, mandant_id)
    faden = threading.Thread(
        target=bw._im_mandanten_kontext,  # noqa: SLF001
        args=(box, mandant_id, bi._import_lauf, bw, un, mandant_id,  # noqa: SLF001
              status["lauf"]),
        daemon=True)
    faden.start()


@router.post("/mandanten/{mandant_id}/import/start")
async def api_import_start(mandant_id: int, request: Request) -> JSONResponse:
    """Loslegen: was im Zwischenspeicher liegt, wandert in die Belegbox und
    wird gelesen. Antwortet sofort — zusehen kann man über `GET …/import`."""
    import belegimport as bi  # noqa: PLC0415
    bw = _bw()
    un, zeile, fehler = _import_tuer(request, mandant_id)
    if fehler:
        return fehler
    if bi._start_gebremst(un):  # noqa: SLF001
        return _fehler("Gerade wurden viele Importe gestartet — "
                       "kurz warten, dann noch einmal.", 429)
    with bi._IMPORT_LOCK:  # noqa: SLF001
        status = bi._IMPORT_JOBS.get(mandant_id)  # noqa: SLF001
        if status is not None and status["stand"] in bi.LAUFEND:
            return _fehler("Für diesen Mandanten läuft gerade ein Import.", 409)
        if status is None or status["stand"] != "sammelt" or not status["dateien"]:
            return _fehler("Es liegt nichts bereit, was sich übernehmen ließe.",
                           409)
        status["stand"] = "wartet"
        status["begonnen"] = time.time()
        anzahl = len(status["dateien"])
    await run_in_threadpool(bi._festhalten, bw, status)  # noqa: SLF001
    audit.audit(un, "kanzlei_import_start", ziel_un=zeile["besitzer_un"],
                mandant_id=str(mandant_id), lauf=status["lauf"], anzahl=anzahl)
    _lauf_starten(bw, un, mandant_id, status)
    return JSONResponse({"ok": True, "lauf": status["lauf"], "dateien": anzahl})


@router.get("/mandanten/{mandant_id}/import")
def api_import_stand(mandant_id: int, request: Request) -> JSONResponse:
    """Wie weit ist der Import? `Cache-Control: no-store`, weil sich die
    Antwort im Sekundentakt ändert und ein Zwischenspeicher hier lügt."""
    import belegimport as bi  # noqa: PLC0415
    bw = _bw()
    un, zeile, fehler = _import_tuer(request, mandant_id, schreibend=False)
    if fehler:
        return fehler
    return JSONResponse(bi.stand_lesen(bw, mandant_id), headers=_OHNE_ABLAGE)


@router.post("/mandanten/{mandant_id}/import/abbrechen")
async def api_import_abbrechen(mandant_id: int, request: Request) -> JSONResponse:
    """Anhalten. Der laufende Beleg wird noch fertig — mitten in einer
    Lesung abzubrechen hieße, ein halbes Ergebnis abzulegen."""
    import belegimport as bi  # noqa: PLC0415
    un, zeile, fehler = _import_tuer(request, mandant_id)
    if fehler:
        return fehler
    with bi._IMPORT_LOCK:  # noqa: SLF001
        status = bi._IMPORT_JOBS.get(mandant_id)  # noqa: SLF001
        if status is None:
            return _fehler("Da läuft gerade nichts.", 409)
        status["abbruch_gewuenscht"] = True
    audit.audit(un, "kanzlei_import_abbruch", ziel_un=zeile["besitzer_un"],
                mandant_id=str(mandant_id), lauf=status["lauf"])
    return JSONResponse({"ok": True})


@router.post("/mandanten/{mandant_id}/import/fortsetzen")
async def api_import_fortsetzen(mandant_id: int, request: Request,
                                nur: str = "") -> JSONResponse:
    """Weitermachen, wo es aufgehört hat — nach einem Abbruch, einem Fehler
    oder einem Neustart.

    Ohne `nur` kommt alles noch nicht Gelesene wieder in die Reihe; mit
    `nur=unlesbar` genau die Belege, aus denen beim ersten Mal nichts wurde
    (der Platzhalter, den sie tragen, darf ersetzt werden — eine Angabe von
    Hand nie, dafür sorgt `_review_ueberschreibbar`).
    """
    import belegimport as bi  # noqa: PLC0415
    bw = _bw()
    un, zeile, fehler = _import_tuer(request, mandant_id)
    if fehler:
        return fehler
    if bi._start_gebremst(un):  # noqa: SLF001
        return _fehler("Gerade wurden viele Importe gestartet — "
                       "kurz warten, dann noch einmal.", 429)
    with bi._IMPORT_LOCK:  # noqa: SLF001
        alt = bi._IMPORT_JOBS.get(mandant_id)  # noqa: SLF001
        if alt is not None and alt["stand"] in bi.LAUFEND:
            return _fehler("Für diesen Mandanten läuft gerade ein Import.", 409)
    if alt is None:
        alt = bw.db_import_lesen(mandant_id)
    if alt is None:
        return _fehler("Es gibt keinen Import, der sich fortsetzen ließe.", 409)
    neu = bi.fortsetzung_bauen(alt, "unlesbar" if nur == "unlesbar" else "")
    offen = [d for d in neu["dateien"] if d["stand"] in ("wartet", "abgelegt")]
    if not offen:
        return _fehler("Es ist nichts mehr offen — alles ist durch.", 409)
    neu["stand"] = "wartet"
    neu["begonnen"] = time.time()
    with bi._IMPORT_LOCK:  # noqa: SLF001
        bi._IMPORT_JOBS[mandant_id] = neu  # noqa: SLF001
        bi._IMPORT_SHAS[mandant_id] = set()  # noqa: SLF001
    await run_in_threadpool(bi._festhalten, bw, neu)  # noqa: SLF001
    audit.audit(un, "kanzlei_import_start", ziel_un=zeile["besitzer_un"],
                mandant_id=str(mandant_id), lauf=neu["lauf"],
                anzahl=len(offen), fortsetzung=True, nur=nur or "alles")
    _lauf_starten(bw, un, mandant_id, neu)
    return JSONResponse({"ok": True, "lauf": neu["lauf"], "dateien": len(offen)})


# `datetime` wird nur für den Typvertrag der Reset-Zeilen gebraucht — der
# Import steht oben, damit ein späterer Umbau ihn nicht sucht.
_ = datetime
