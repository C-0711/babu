"""Das Konto löschen — ganz, vom Telefon aus (14.10.2026).

Apples Richtlinie 5.1.1(v): Wer in einer App ein Konto anlegen kann, muss es
in derselben App auch löschen können. „Los geht's" legt auf dem Server einen
Betrieb an (`kern_geraet`), also gilt die Regel für babu. Eine Adresse, an die
man schreiben kann, reicht Apple ausdrücklich nicht.

**Was gelöscht wird.** Alles, was babu über diesen Zugang in seiner Datenbank
führt — Zeile für Zeile, aus jeder Tabelle, die `un` oder `mandant_id` trägt
(`NACH_UN`, `NACH_MANDANT`) — und der Inhalt der Belegbox. Übrig bleibt eine
Zeile in `geloescht`: Mandantennummer, Box-Verweis, Zeitpunkt und die Zahl der
entfernten Dateien. Kein Name, keine Adresse, keine E-Mail.

**Was babu NICHT kann, und warum die Zeile bleibt.** Die Belegbox ist ein
Git-Repo beim GitChain-Dienst. babu kann seinen Inhalt in einem Commit
entfernen — danach zeigt der Stand nichts mehr —, aber das Repo selbst samt
Historie löscht nur der Betreiber; einen Weg dafür gibt es in der API des
Dienstes nicht (`box.py` spricht ausschließlich Git über HTTP). Genau dafür
ist `geloescht` da: sie ist die Arbeitsliste des Betreibers. Der Text in der
App sagt das, ohne es zu beschönigen.

**Wer darf.** Nur die Inhaberin ihres eigenen Betriebs, und nur bei einem
Betrieb, den die App angelegt hat (`herkunft = "app"`). Alles andere wird
abgewiesen, mit dem Weg, der stattdessen gilt:

* eine Mitarbeiterin löscht nicht den Betrieb, sondern verlässt das Team —
  das macht die Inhaberin;
* ein Betrieb aus dem Portal hängt an einer Kanzlei und ihren Stapeln; dort
  ist Löschen ein Vorgang zwischen zwei Parteien, nicht ein Knopf;
* eine Kanzlei löscht nie über die App.

**Das Abo endet dadurch nicht.** Ein Apple-Abo kündigt nur Apple. Der Text in
der App sagt das vor dem Löschen, zusammen mit dem Weg dorthin — sonst zahlt
jemand weiter für einen Platz, den es nicht mehr gibt.
"""
from __future__ import annotations

import json

from fastapi import Request
from fastapi.responses import JSONResponse, Response

import mandanten
import paket

#: Tabellen mit einer `un`-Spalte, aus denen die Zeilen dieses Zugangs
#: verschwinden. Jede einzeln aufgeführt und nicht aus dem Schema geraten:
#: eine neue Tabelle soll den Test in `tests/test_konto_loeschen.py`
#: anschlagen lassen, damit jemand entscheidet, ob ihre Zeilen mitgehen.
NACH_UN = (
    "abschluss_status",   # der Stand je Jahr
    "anlagegut",          # Anlagen und Abschreibungen
    "app_schluessel",     # die Geräteschlüssel — danach trägt kein Telefon mehr
    "behandlung",         # was an einer Kundin gemacht wurde
    "einstellungen",      # Betriebsname, Anschrift, Steuernummer, E-Mail
    "gespraech",          # die Chatfäden (ihre Nachrichten darunter)
    "kanzlei_mitglied",   # Mitgliedschaften — bei einem App-Betrieb keine
    "kundin",             # Kundinnen
    "leistung",           # Preisliste
    "lesestatus",         # was gelesen wurde
    "mitarbeiter",        # Personalakten (Geburtsdatum, IBAN, Steuer-IdNr.)
    "passwort_reset",     # offene Rücksetz-Marken
    "push_geraet",        # Push-Token
    "team",               # Team samt IBAN
    "termin",             # Termine
    "wa_faden",           # WhatsApp-Fäden
    "wa_nachricht",       # und ihre Nachrichten
)

#: Tabellen mit `mandant_id`.
NACH_MANDANT = (
    "abo_rechnung",       # Abo-Rechnungen (ein App-Betrieb hat keine: Apple
                          #   ist dort der Verkäufer, nicht babu)
    "import_status",      # Stand eines Imports
    "post_adresse",       # die Empfangsadresse des Posteingangs
)

#: Das Protokoll, das bleibt — ohne eine Angabe zur Person.
_GELOESCHT = """CREATE TABLE IF NOT EXISTS geloescht
    (mandant_id INTEGER PRIMARY KEY,
     box_ref TEXT,
     dateien INTEGER NOT NULL DEFAULT 0,
     box_leer INTEGER NOT NULL DEFAULT 0,
     zeit TEXT NOT NULL)"""


def schema(c) -> None:
    """Idempotent, aus `_db()` heraus gerufen. Abbild: migrations/0019_konto_loeschen.sql."""
    c.execute(_GELOESCHT)


def setup(app, bw_modul):
    """Der Kern reicht sich selbst herein — siehe `kern_geraet.setup`."""
    globals()["bw"] = bw_modul
    globals()["app"] = app
    app.post("/api/konto/loeschen")(api_konto_loeschen)


def _box_leeren(mandant_id: int, box_ref: str, un: str) -> tuple[int, bool]:
    """Die Belegbox leer machen, in einem Commit.

    Rückgabe `(dateien, geleert)`. Scheitert es (Dienst weg, Box nie
    angelegt, Anmeldung abgelehnt), ist `geleert` False — und das Löschen in
    der Datenbank läuft trotzdem durch. Eine Box, die stehen bleibt, steht in
    `geloescht` und ist damit die Arbeitsliste des Betreibers; ein Zugang,
    der trotz bestätigter Löschung weiter gilt, wäre ein gebrochenes
    Versprechen.

    Gezählt und entfernt wird in `boxschreiber.alles_loeschen` — im frisch
    zurückgesetzten Klon, hinter dem Schloss der Box. Hier wird nichts
    vorher aufgelistet: eine Liste von außen wäre beim Commit schon veraltet.
    """
    try:
        import box as bx  # noqa: PLC0415
        import boxschreiber  # noqa: PLC0415
        kasten = bx.box_aus_ref(mandant_id, box_ref)
        _kurz, dateien = boxschreiber.alles_loeschen(
            kasten, f"konto geloescht: Mandant {mandant_id}", un)
    except Exception as ex:  # noqa: BLE001
        # `NichtsZuLoeschen` heißt: die Box war schon leer. Alles andere ist
        # ein echter Fehlschlag — beides steht hier zusammen, weil die
        # Unterscheidung nur die eine Zeile darunter braucht.
        import boxschreiber  # noqa: PLC0415
        if isinstance(ex, boxschreiber.NichtsZuLoeschen):
            return 0, True
        print(f"[konto] Box {box_ref} nicht geleert: {ex}", flush=True)
        return 0, False
    return dateien, True


def darf_loeschen(un: str) -> tuple[int | None, str | None]:
    """`(mandant_id, None)` wenn dieser Zugang seinen Betrieb löschen darf —
    sonst `(None, Grund im Klartext)`.

    Zwei der drei Prüfungen hier sind das HINTERE Schloss, gemessen am
    14.10.2026 (`tests/test_konto_loeschen.py`):

    * Die Rolle `mitarbeit` kommt über die Route gar nicht bis hierher —
      `_api_wache` lässt sie nur an die Pfade der Positivliste
      (`mitarbeitrecht`), und dieser Pfad steht nicht darin: 403 mit
      `grund: freigabe`.
    * Der Besitzer-Vergleich greift über die Route nie, weil
      `testmonat.direkt_mandant_von` den Betrieb schon nach `besitzer_un`
      sucht — gehört er einem anderen, gibt es für diesen Zugang keinen.

    Beide bleiben trotzdem stehen: käme der Pfad in die Positivliste oder
    fände die Suche einmal einen fremden Betrieb, entscheiden sie allein.
    Die Herkunft ist die einzige Prüfung, die hier wirklich zuschlägt.
    """
    import testmonat  # noqa: PLC0415
    if bw.rolle(un) == "mitarbeit":
        return None, ("Dein Zugang gehört zum Team eines Betriebs. Dort "
                      "nimmt dich die Inhaberin heraus — gelöscht wird der "
                      "Betrieb damit nicht.")
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        direkt = testmonat.direkt_mandant_von(un, c)
        if not direkt:
            return None, "Für diesen Zugang gibt es hier keinen Betrieb."
        mandant_id = int(direkt[0])
        zeile = c.execute("SELECT herkunft, besitzer_un FROM mandant WHERE id=?",
                          (mandant_id,)).fetchone()
    if not zeile:
        return None, "Für diesen Zugang gibt es hier keinen Betrieb."
    herkunft, besitzer = zeile[0], zeile[1]
    if besitzer != un:
        return None, ("Dieser Betrieb gehört einem anderen Zugang. Löschen "
                      "kann ihn nur, wem er gehört.")
    if herkunft != paket.HERKUNFT_APP:
        return None, ("Dieser Betrieb ist nicht in der App entstanden und "
                      "arbeitet mit einem Steuerbüro zusammen. Schreib uns, "
                      "dann klären wir das Löschen gemeinsam — in der App "
                      "wäre es ein Knopf mit Folgen für beide Seiten.")
    return mandant_id, None


def loeschen(un: str, mandant_id: int) -> dict:
    """Konto, Betrieb und Belegbox — und was danach zu tun bleibt.

    Erst die Box, dann die Datenbank: scheitert die Box, bleibt der Zugang
    noch gültig und die Nutzerin kann es erneut versuchen. Umgekehrt wäre der
    Zugang weg und die Belege lägen noch da, ohne jeden Weg dorthin.
    """
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        zeile = c.execute("SELECT box_ref FROM mandant WHERE id=?",
                          (mandant_id,)).fetchone()
    box_ref = (zeile[0] if zeile else None) or ""
    dateien, box_leer = (_box_leeren(mandant_id, box_ref, un)
                         if box_ref else (0, True))

    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        # Die Nachrichten hängen an den Fäden, nicht am Zugang.
        faeden = [z[0] for z in c.execute(
            "SELECT id FROM gespraech WHERE un=?", (un,)).fetchall()]
        for faden in faeden:
            c.execute("DELETE FROM nachricht WHERE gespraech=?", (faden,))
        # Das Gedächtnis hängt am Bezeichner des Betriebs.
        c.execute("DELETE FROM merksatz WHERE betrieb=?", (un,))
        for tabelle in NACH_UN:
            c.execute(f"DELETE FROM {tabelle} WHERE un=?", (un,))  # noqa: S608
        for tabelle in NACH_MANDANT:
            c.execute(f"DELETE FROM {tabelle} WHERE mandant_id=?",  # noqa: S608
                      (mandant_id,))
        # Das Protokoll nennt niemanden: nur, DASS gelöscht wurde — und was
        # dem Betreiber zu tun bleibt.
        c.execute("DELETE FROM audit_log WHERE ziel_un=? OR akteur_un=? "
                  "OR mandant_id=?", (un, un, mandant_id))
        c.execute(db_upsert_geloescht(), (mandant_id, box_ref, dateien,
                                          1 if box_leer else 0,
                                          bw._jetzt_iso()))  # noqa: SLF001
        # Zuletzt die beiden Zeilen, auf die alles zeigt.
        c.execute("DELETE FROM mandant WHERE id=?", (mandant_id,))
        c.execute("DELETE FROM nutzer WHERE email=?", (un,))
    print(f"[konto] geloescht: Mandant {mandant_id}, {dateien} Dateien, "
          f"Box {'geleert' if box_leer else 'NICHT geleert'}", flush=True)
    return {"mandant": mandant_id, "dateien": dateien, "box_leer": box_leer}


def db_upsert_geloescht() -> str:
    """Ein zweiter Lauf darf nicht an der Primärschlüssel-Kollision scheitern."""
    import db  # noqa: PLC0415
    return db.upsert("geloescht",
                     ("mandant_id", "box_ref", "dateien", "box_leer", "zeit"),
                     ("mandant_id",))


async def api_konto_loeschen(request: Request) -> Response:
    """`POST /api/konto/loeschen {"bestaetigt": true}` — und das Konto ist weg.

    `bestaetigt` ist Pflicht: ein POST ohne Rumpf soll nicht löschen können,
    auch nicht aus einer alten Fassung der App oder einem verirrten Aufruf.
    """
    un, fehler = bw._api_wache(request)  # noqa: SLF001
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"},
                                      status_code=401)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 8 * 1024) or b"{}")
    except Exception:  # noqa: BLE001
        koerper = {}
    if not isinstance(koerper, dict) or koerper.get("bestaetigt") is not True:
        return JSONResponse({"fehler": "Zum Löschen fehlt die Bestätigung."},
                            status_code=400)
    mandant_id, grund = darf_loeschen(un)
    if mandant_id is None:
        return JSONResponse({"fehler": grund}, status_code=409)
    ergebnis = loeschen(un, mandant_id)
    if not ergebnis["box_leer"]:
        # Der Zugang ist weg, die Belege sind es nicht. Das wird gesagt,
        # nicht verschwiegen — die Nutzerin soll wissen, dass noch etwas
        # offen ist, und wir haben es in `geloescht` stehen.
        return JSONResponse({"ok": True, **ergebnis,
                             "hinweis": "Dein Konto ist gelöscht. Deine "
                                        "Belege konnte babu gerade nicht "
                                        "entfernen — das holen wir nach."})
    return JSONResponse({"ok": True, **ergebnis})
