#!/usr/bin/env python3
"""Ein Ordner Belege auf einmal — der Massenimport je Mandant.

Der Fall, für den es das gibt: eine Kanzlei übernimmt einen neuen Mandanten
und hat dessen Belege eines halben Jahres als Ordner auf der Platte. Von
Hand wären das zweihundert Uploads und zweihundert Wartezeiten. Hier
schickt das Portal die Dateien nacheinander in einen Zwischenspeicher,
drückt einmal auf Start, und der Rest passiert von selbst — sichtbar, mit
Zähler, abbrechbar und nach einem Neustart fortsetzbar.

Drei Entscheidungen, die man sonst für Zufall halten könnte:

* **Ablegen und Lesen sind getrennt.** Erst wandern ALLE Dateien in die
  Belegbox — in Bündeln zu zwanzig, also ein Commit je zwanzig Belegen
  statt zweihundert einzelner. Erst danach wird gelesen. Der Grund ist ein
  praktischer: das Ablegen ist schnell und darf nicht auf die Buchhaltung
  warten, und wenn beim Lesen etwas schiefgeht, liegen die Belege trotzdem
  schon sicher in der Box. Was danach fehlt, ist eine Lesung — kein Beleg.

* **Ein Lauf zur Zeit im ganzen Prozess.** Nicht weil zwei nicht gingen,
  sondern weil dahinter EINE Buchhaltung steht (`_LLM_SEMAPHORE` in
  `babu_web` lässt ohnehin nur einen Aufruf durch). Zwei parallele Läufe
  würden sich gegenseitig ausbremsen und beide langsam aussehen lassen.
  Der zweite Mandant steht deshalb sichtbar auf „wartet".

* **Jeder Beleg bekommt ein Ergebnis, auch der misslungene.** Ein Beleg,
  den die Buchhaltung nicht durchbekommt, wäre sonst für immer „wird
  gelesen" — bei zweihundert Stück fällt das niemandem mehr auf. Deshalb
  wird auch aus einer Rückfrage und aus einem unlesbaren Blatt ein
  sichtbarer Beleg (`_review_aus_rueckfrage` / `_review_unlesbar` in
  `babu_web`). Das ist der eine Unterschied zum Portal-Upload, wo genau
  das NICHT passiert, weil dort ein Mensch danebensteht.

`babu_web` wird ausschließlich innerhalb der Funktionen importiert (lazy),
aus demselben Grund wie in `kanzlei_routen.py`: `babu_web` bindet die
Import-Routen ein, ein Import auf Modulebene wäre ein Kreis. Nebeneffekt:
die Tests dürfen die Hälften an `babu_web` austauschen und dieses Modul
merkt es.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import shutil
import threading
import time
from pathlib import Path

import audit
import box as bx

# ---------------------------------------------------------------------------
# Was ein Import darf und wie lange er sich merkt
# ---------------------------------------------------------------------------

#: Wo die Dateien liegen, bis der Lauf beginnt. Ausdrücklich NICHT in der
#: Belegbox: was hier liegt, ist noch nichts — die Kanzlei kann mitten im
#: Auswählen abbrechen, und ein abgebrochener Import darf keine Spur in
#: einer Historie hinterlassen, die für immer bleibt.
IMPORT_TMP = Path(os.environ.get(
    "BABU_IMPORT_TMP", str(Path.home() / "babu-web" / "import-tmp")))

#: Was ein Beleg sein kann. Das ist `babu_web.HOCHLADEN_ENDUNGEN` ohne
#: `.xml` — eine DATEV-Datei ist kein Beleg, und die Lesung könnte mit ihr
#: nichts anfangen. Absichtlich als eigene Liste und nicht zur Laufzeit
#: berechnet (der Import auf Modulebene wäre ein Kreis); dass die beiden
#: zusammenpassen, hält `tests/test_belegimport_lauf.py` fest.
IMPORT_ENDUNGEN = frozenset({".jpg", ".jpeg", ".png", ".pdf", ".heic"})

#: Wie viele Belege ein Lauf trägt. Zweihundert sind ein halbes Jahr eines
#: kleinen Betriebs; dreihundert ist die Grenze, ab der jemand besser in
#: zwei Portionen arbeitet, statt eine Stunde auf einen Balken zu sehen.
IMPORT_MAX_DATEIEN = 300
#: Wie viele Dateien in EINEN Commit gehen. Zweihundert einzelne Commits
#: wären zweihundert fetch/reset/push-Runden — das Bündel macht daraus zehn.
IMPORT_BUENDEL = 20
#: Verschnaufpause zwischen zwei Belegen. Der Import ist Hintergrundarbeit;
#: Nina, die nebenher einen Bon fotografiert, soll nicht hinter zweihundert
#: Kanzlei-Belegen anstehen. Die Pause liegt AUSSERHALB des LLM-Semaphors,
#: sonst wäre sie eine Sperre und keine Pause.
IMPORT_ATEMPAUSE_SEK = 1.0
#: Wie lange ein beendeter Lauf im Speicher bleibt — so lange fragt das
#: Portal ihn ab. Danach fliegt er raus; der Endstand steht in der
#: Datenbank (`db_import_snapshot`).
IMPORT_JOB_FRIST = 3600.0
#: Wie lange eine Datei im Zwischenspeicher liegen darf, ohne dass jemand
#: Start gedrückt hat. Danach ist das kein Import mehr, sondern Müll.
IMPORT_TMP_FRIST = 24 * 3600.0

#: Bremse auf das Starten, je Zugang — Muster wie `_anlage_gebremst` in
#: `kanzlei_routen`. Fünf Läufe in zehn Minuten sind reichlich; wer mehr
#: braucht, hat kein Import-, sondern ein Skript-Problem.
START_MAX = 5
START_FENSTER = 600.0
_START_VERSUCHE: dict[str, list[float]] = {}

#: Die Läufe, je Mandant genau einer (der letzte). Ein Dict im Prozess
#: reicht, weil `workers=1` gilt — dasselbe Muster wie `_ABSCHLUSS_JOBS`.
_IMPORT_JOBS: dict[int, dict] = {}
_IMPORT_LOCK = threading.Lock()
#: Die Bytes, die dieser Lauf schon gesehen hat (sha1). Steht bewusst
#: NEBEN dem Lauf und nicht darin: die Datenform des Laufs geht so, wie sie
#: ist, ins Portal und in die Datenbank, und Prüfsummen gehören auf keinen
#: Bildschirm.
_IMPORT_SHAS: dict[int, set[str]] = {}
#: Ein Lauf zur Zeit im ganzen Prozess (siehe Modulkopf).
_IMPORT_WORKER_LOCK = threading.Lock()

#: Die Stände eines Laufs. „wartet" heißt: die Reihe ist noch nicht dran.
LAUFEND = ("wartet", "liest")

#: Sätze für Menschen. Kein Systemname, keine Fehlernummer.
HINWEIS_WARTET = ("Ein anderer Mandant ist gerade dran — dieser Import "
                  "beginnt gleich von selbst.")
HINWEIS_UNTERBROCHEN = ("Dieser Import ist stehen geblieben. Mit "
                        "„Fortsetzen“ geht es weiter, ohne dass etwas "
                        "doppelt abgelegt wird.")
HINWEIS_FEHLER = ("Der Import ist steckengeblieben. Die schon abgelegten "
                  "Belege sind da; der Rest lässt sich fortsetzen.")
GRUND_NOCHMAL = "Diese Datei bitte noch einmal auswählen."
GRUND_VON_HAND = "Dazu hat schon jemand von Hand etwas eingetragen."
GRUND_VERLOREN = "Diese Datei ist unterwegs verloren gegangen."


class ImportFehler(RuntimeError):
    """Der Lauf kann nicht weiter — mit einem Satz, der auf den Bildschirm darf."""


def _bw():
    import babu_web  # noqa: PLC0415
    return babu_web


# ---------------------------------------------------------------------------
# Der Zwischenspeicher
# ---------------------------------------------------------------------------

def _lauf_ordner(mandant_id: int, lauf: str) -> Path:
    return IMPORT_TMP / str(mandant_id) / lauf


def _import_tmp_aufraeumen() -> None:
    """Ordner, in denen seit einem Tag nichts passiert ist, wegwerfen.

    Ohne das wüchse der Zwischenspeicher mit jedem abgebrochenen Versuch.
    Läuft beim Hochladen mit — es gibt keinen Dienst, der aufräumen könnte,
    und soll auch keinen geben (CLAUDE.md).
    """
    jetzt = time.time()
    try:
        mandanten_ordner = list(IMPORT_TMP.iterdir())
    except OSError:
        return
    for m in mandanten_ordner:
        if not m.is_dir():
            continue
        for lauf in list(m.iterdir()):
            try:
                if not lauf.is_dir():
                    continue
                if jetzt - lauf.stat().st_mtime > IMPORT_TMP_FRIST:
                    shutil.rmtree(lauf, ignore_errors=True)
            except OSError:
                continue


def _start_gebremst(un: str) -> bool:
    jetzt = time.time()
    versuche = [t for t in _START_VERSUCHE.get(un, []) if jetzt - t < START_FENSTER]
    _START_VERSUCHE[un] = versuche
    if len(versuche) >= START_MAX:
        return True
    versuche.append(jetzt)
    _bw()._zaehler_aufraeumen(_START_VERSUCHE, jetzt, START_FENSTER)  # noqa: SLF001
    return False


# ---------------------------------------------------------------------------
# Die Datenform eines Laufs — im Register und in der Datenbank dieselbe
# ---------------------------------------------------------------------------

def neuer_lauf(mandant_id: int, un: str, monat: str) -> dict:
    """Ein leerer Lauf im Stand „sammelt".

    `monat` ist der Monat, in dem die erste Datei einsortiert wird. Er
    entscheidet nicht darüber, wo ein Beleg landet (das tut der Monat der
    einzelnen Datei), sondern nur darüber, welchen Umsatz- und
    Nachbar-Kontext die Buchhaltung beim Lesen mitbekommt.
    """
    return {
        # Zeit plus vier Zufallszeichen: zwei Läufe in derselben Sekunde
        # bekämen sonst denselben Ordner im Zwischenspeicher — und damit
        # die Dateien des jeweils anderen.
        "lauf": time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
        "mandant_id": mandant_id,
        "von": un,
        "stand": "sammelt",
        "monat": monat,
        "gesamt": 0,
        "abgelegt": 0,
        "gelesen": 0,
        "gebucht": 0,
        "rueckfrage": 0,
        "unlesbar": 0,
        "doppelt": 0,
        "hinweis": "",
        "begonnen": None,
        "beendet_um": None,
        "abbruch_gewuenscht": False,
        "dateien": [],
    }


def neue_datei(name: str, datei: str, stamm: str, groesse: int) -> dict:
    return {"name": name, "datei": datei, "stamm": stamm, "groesse": groesse,
            "stand": "wartet", "grund": None, "war_schon": None,
            "dauer_s": None}


def jobs_aufraeumen() -> None:
    """Beendete Läufe nach der Frist vergessen. Wer `_IMPORT_LOCK` hält."""
    jetzt = time.time()
    for mid, status in list(_IMPORT_JOBS.items()):
        beendet = status.get("beendet_um")
        if beendet and jetzt - beendet > IMPORT_JOB_FRIST:
            del _IMPORT_JOBS[mid]
            _IMPORT_SHAS.pop(mid, None)


def _festhalten(bw, status: dict) -> None:
    """Den Stand in die Datenbank schreiben — ein Neustart soll ihn kennen."""
    try:
        bw.db_import_snapshot(int(status["mandant_id"]), status)
    except Exception as ex:  # noqa: BLE001
        print(f"[import] Stand nicht gespeichert: {ex!r}", flush=True)


# ---------------------------------------------------------------------------
# Der Lauf selbst
# ---------------------------------------------------------------------------

def _import_lauf(bw, un: str, mandant_id: int, lauf: str) -> None:
    """Ablegen, lesen, fertig — der ganze Lauf in einem Faden.

    Läuft über `babu_web._im_mandanten_kontext`, setzt also Box UND
    Mandant. Ohne den Mandanten bucht dieser Faden mit dem Profil und dem
    Kontenrahmen der Kanzlei statt denen des Salons — siehe dort.
    """
    with _IMPORT_LOCK:
        status = _IMPORT_JOBS.get(mandant_id)
    if status is None or status.get("lauf") != lauf:
        return          # zwischenzeitlich von einem neueren Lauf abgelöst
    if not _IMPORT_WORKER_LOCK.acquire(blocking=False):
        # Ein anderer Mandant ist dran. Sichtbar warten, nicht still.
        status["hinweis"] = HINWEIS_WARTET
        _festhalten(bw, status)
        _IMPORT_WORKER_LOCK.acquire()
        status["hinweis"] = ""
    try:
        _lauf_arbeiten(bw, un, mandant_id, status)
    except ImportFehler as ex:
        status["stand"] = "fehler"
        status["hinweis"] = str(ex)
        status["beendet_um"] = time.time()
        _festhalten(bw, status)
    except Exception as ex:  # noqa: BLE001
        print(f"[import] Lauf {lauf} für Mandant {mandant_id}: {ex!r}", flush=True)
        status["stand"] = "fehler"
        status["hinweis"] = HINWEIS_FEHLER
        status["beendet_um"] = time.time()
        _festhalten(bw, status)
    finally:
        _IMPORT_WORKER_LOCK.release()


def _lauf_arbeiten(bw, un: str, mandant_id: int, status: dict) -> None:
    box = bx.box_von(un, mandant_id)
    _ablegen(bw, un, box, status)
    _lesen(bw, un, box, status)
    status["stand"] = "abgebrochen" if status.get("abbruch_gewuenscht") else "fertig"
    status["beendet_um"] = time.time()
    _festhalten(bw, status)
    audit.audit(un, "kanzlei_import_ende", ziel_un=_besitzer(mandant_id),
                mandant_id=str(mandant_id), lauf=status["lauf"],
                stand=status["stand"], gesamt=status["gesamt"],
                abgelegt=status["abgelegt"], gelesen=status["gelesen"],
                gebucht=status["gebucht"], rueckfrage=status["rueckfrage"],
                unlesbar=status["unlesbar"], doppelt=status["doppelt"])


def _besitzer(mandant_id: int) -> str | None:
    import mandanten  # noqa: PLC0415
    try:
        zeile = mandanten.mandant_holen(mandant_id)
    except Exception:  # noqa: BLE001
        return None
    return (zeile or {}).get("besitzer_un")


# ── 1. Ablegen: alle Dateien in die Box, in Bündeln ────────────────────────

def _ablegen(bw, un: str, box, status: dict) -> None:
    """Die eingesammelten Dateien in die Belegbox schreiben.

    Bündelweise, damit aus zweihundert Commits zehn werden. Ein Bündel, das
    auch nach drei Anläufen nicht durchgeht, beendet den Lauf — die Dateien
    bleiben dann im Zwischenspeicher liegen und „Fortsetzen" nimmt sie
    wieder auf. Was schon abgelegt ist, bleibt abgelegt.
    """
    import boxschreiber  # noqa: PLC0415
    ordner = _lauf_ordner(int(status["mandant_id"]), status["lauf"])
    wartende = [d for d in status["dateien"] if d["stand"] == "wartet"]
    for anfang in range(0, len(wartende), IMPORT_BUENDEL):
        if status.get("abbruch_gewuenscht"):
            return
        buendel = wartende[anfang:anfang + IMPORT_BUENDEL]
        dateien: dict[str, bytes] = {}
        dabei = []
        for d in buendel:
            try:
                dateien[d["datei"]] = (ordner / d["stamm"]).read_bytes()
                dabei.append(d)
            except OSError:
                d["stand"] = "fehler"
                d["grund"] = GRUND_VERLOREN
        if not dateien:
            continue
        nachricht = f"import {status['lauf']}: {len(dateien)} Belege"
        letzter = ""
        for versuch in (1, 2, 3):
            try:
                boxschreiber.schreiben(box, dateien, None, nachricht, un)
                break
            except boxschreiber.SchreibFehler as ex:
                letzter = str(ex)
                if versuch == 3:
                    raise ImportFehler(HINWEIS_FEHLER) from ex
                time.sleep(0.7 * versuch)
        else:                                   # pragma: no cover — s. o.
            raise ImportFehler(letzter or HINWEIS_FEHLER)
        with box.index_schloss:
            box.invalidieren()
        for d in dabei:
            d["stand"] = "abgelegt"
            status["abgelegt"] += 1
            # Erst jetzt aus dem Zwischenspeicher: solange der Commit nicht
            # durch ist, ist die Kopie im Tmp das Einzige, was es gibt.
            try:
                (ordner / d["stamm"]).unlink()
            except OSError:
                pass
        _festhalten(bw, status)


# ── 2. Lesen: Beleg für Beleg durch die Buchhaltung ────────────────────────

def _lesen(bw, un: str, box, status: dict) -> None:
    status["stand"] = "liest"
    _festhalten(bw, status)
    offen = sorted([d for d in status["dateien"] if d["stand"] == "abgelegt"],
                   key=lambda d: d["name"])
    for n, d in enumerate(offen, 1):
        if status.get("abbruch_gewuenscht"):
            return
        d["stand"] = "liest"
        begonnen = time.monotonic()
        _einen_lesen(bw, un, status, d)
        d["dauer_s"] = round(time.monotonic() - begonnen, 2)
        if n % 5 == 0:
            _festhalten(bw, status)
        # AUSSERHALB des LLM-Semaphors (der steckt in `_beleg_einschaetzen`):
        # eine Pause, die eine Sperre hält, ist keine Pause.
        time.sleep(IMPORT_ATEMPAUSE_SEK)


def _einen_lesen(bw, un: str, status: dict, d: dict) -> None:
    """Einen Beleg lesen und ablegen — was auch immer dabei herauskommt.

    Kein eigener Timeout: die Grenze ist `gemma_buchung.VLM_FRIST` (120 s),
    und ein zweiter Wecker darüber würde nur eine Lesung abschneiden, die
    gerade noch rechtzeitig gewesen wäre. Was wirft oder zu lange braucht,
    wird „unlesbar" — und der Lauf geht weiter.
    """
    daten = bw.git_show(d["datei"])
    if daten is None:
        d["stand"] = "fehler"
        d["grund"] = GRUND_VERLOREN
        return
    endung = Path(d["datei"]).suffix.lower()
    try:
        ergebnis, zeilen = asyncio.run(
            bw._beleg_einschaetzen(daten, endung, un, status["monat"]))  # noqa: SLF001
    except Exception as ex:  # noqa: BLE001
        print(f"[import] {d['datei']}: {ex!r}", flush=True)
        ergebnis, zeilen = {"status": "aufgeben", "hinweis": str(ex)[:200]}, []
    status["gelesen"] += 1

    review, md, neu, grund = _entscheiden(bw, d["datei"], ergebnis, zeilen)
    geschrieben = asyncio.run(
        bw._beleg_review_ablegen(d["datei"], review, md, un))  # noqa: SLF001
    if not geschrieben:
        # Da lag schon ein Review, das stehen bleiben muss — eine Angabe von
        # Hand oder eine Lesung, die schneller war.
        d["stand"] = "uebersprungen"
        d["grund"] = GRUND_VON_HAND
        return
    d["stand"] = neu
    d["grund"] = grund
    status[neu] += 1


def _entscheiden(bw, datei: str, ergebnis: dict,
                 zeilen: list) -> tuple[dict, str, str, str | None]:
    """Aus Gemmas Antwort wird ein Review und ein Stand für die Zeile.

    Drei Wege, keine Schwelle: gebucht ist gebucht, gefragt ist gefragt, und
    alles andere — aufgeben, ein Format ohne Text, eine Ausnahme — ist
    unlesbar. Eine Konfidenz-Schwelle gäbe es hier absichtlich nicht: sie
    wäre eine zweite Meinung über eine Lesung, die es nur einmal gibt.
    """
    stand = ergebnis.get("status")
    if stand == "gebucht":
        buchung = ergebnis["buchung"]
        klasse = str(buchung.get("dokumentklasse") or "beleg")
        review, md = bw._review_aus_einschaetzung(  # noqa: SLF001
            datei, buchung, zeilen, klasse)
        hinweis = bw._doppelgaenger_hinweis(buchung)  # noqa: SLF001
        if hinweis:
            review["felder"]["offen"].append(hinweis)
            return review, md, "rueckfrage", hinweis
        return review, md, "gebucht", None
    if stand == "fragen":
        review, md = bw._review_aus_rueckfrage(  # noqa: SLF001
            datei, ergebnis.get("fragen") or [], zeilen)
        offen = review["felder"]["offen"]
        return review, md, "rueckfrage", (offen[0] if offen else None)
    hinweis = str(ergebnis.get("hinweis")
                  or "Aus diesem Blatt war nichts zu lesen.")
    review, md = bw._review_unlesbar(datei, hinweis, zeilen)  # noqa: SLF001
    return review, md, "unlesbar", bw.UNLESBAR_HINWEIS


# ---------------------------------------------------------------------------
# Was das Portal von einem Lauf sieht
# ---------------------------------------------------------------------------

def stand_lesen(bw, mandant_id: int) -> dict:
    """Der Stand des letzten Laufs — aus dem Speicher, sonst aus der Datenbank.

    Ein Lauf, der laut Datenbank noch läuft, aber im Speicher nicht mehr
    steht, hat einen Neustart erlebt. Er heißt dann „unterbrochen" und
    nicht „läuft" — sonst sähe die Kanzlei einem Balken zu, hinter dem
    niemand mehr arbeitet.
    """
    with _IMPORT_LOCK:
        jobs_aufraeumen()
        status = _IMPORT_JOBS.get(mandant_id)
    if status is not None:
        return json.loads(json.dumps(status))
    gespeichert = bw.db_import_lesen(mandant_id)
    if gespeichert is None:
        return {"stand": "leer"}
    if gespeichert.get("stand") in LAUFEND:
        gespeichert["stand"] = "unterbrochen"
        gespeichert["hinweis"] = HINWEIS_UNTERBROCHEN
    return gespeichert


def fortsetzung_bauen(alt: dict, nur: str = "") -> dict:
    """Aus dem letzten Lauf einen neuen machen — nur mit dem, was fehlt.

    Zwei Wege zurück in die Reihe: was schon in der Box liegt (Stand
    „abgelegt", „liest", und mit `nur=unlesbar` auch „unlesbar"), wird von
    dort erneut gelesen. Was nur im Zwischenspeicher lag, kann nur weiter,
    wenn die Datei noch da ist — sonst muss die Kanzlei sie noch einmal
    auswählen, und genau das steht dann als Grund daneben.
    """
    neu = neuer_lauf(int(alt["mandant_id"]), alt.get("von") or "",
                     alt.get("monat") or time.strftime("%Y-%m"))
    alt_ordner = _lauf_ordner(int(alt["mandant_id"]), alt.get("lauf") or "")
    neu_ordner = _lauf_ordner(int(alt["mandant_id"]), neu["lauf"])
    fertig = ("gebucht", "rueckfrage", "unlesbar", "doppelt", "uebersprungen")
    for d in alt.get("dateien") or []:
        if nur == "unlesbar":
            if d["stand"] != "unlesbar":
                continue
        elif d["stand"] in fertig:
            continue
        eintrag = neue_datei(d["name"], d["datei"], d["stamm"],
                             d.get("groesse") or 0)
        if d["stand"] in ("abgelegt", "liest", "unlesbar"):
            eintrag["stand"] = "abgelegt"      # liegt in der Box, wird gelesen
        else:
            quelle = alt_ordner / d["stamm"]
            if quelle.is_file():
                neu_ordner.mkdir(parents=True, exist_ok=True)
                try:
                    quelle.replace(neu_ordner / d["stamm"])
                except OSError:
                    eintrag["stand"] = "uebersprungen"
                    eintrag["grund"] = GRUND_NOCHMAL
            else:
                eintrag["stand"] = "uebersprungen"
                eintrag["grund"] = GRUND_NOCHMAL
        neu["dateien"].append(eintrag)
    neu["gesamt"] = len(neu["dateien"])
    neu["abgelegt"] = sum(1 for d in neu["dateien"] if d["stand"] == "abgelegt")
    return neu


def sha_von(daten: bytes) -> str:
    return hashlib.sha1(daten).hexdigest()
