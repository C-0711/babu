#!/usr/bin/env python3
"""postadresse — an welche E-Mail-Adresse ein Betrieb seine Post bekommt.

babu verspricht die digitale Erfassung des ganzen Schriftverkehrs, konnte
bis hierher aber nur senden (`postfach.py`). Post kam nur ins System, wenn
Nina sie abfotografiert hat. Der Posteingang (`server/posteingang/`) macht
daraus einen echten Empfänger — und diese Tabelle ist das einzige, was
darüber entscheidet, in WESSEN Belegbox eine Sendung fällt.

**Der lokale Teil ist ein Zufallswort, kein Name.** Das ist die ganze
Zugangskontrolle des Posteingangs und deshalb eine bewusste Entscheidung:
an diese Adresse schreiben Lieferanten, Ämter und Krankenkassen. Sie muss
also für JEDEN Absender offen sein — es gibt keine Absenderliste, die man
pflegen könnte, ohne die Funktion zu zerstören. Wäre die Adresse dagegen
erratbar (`nina@…`, `supremestudio@…`), könnte jeder Fremde Belege in eine
fremde Belegbox schicken und darin Buchungen erzeugen. Die Nichterratbarkeit
ersetzt die fehlende Absenderprüfung; 16 Zeichen aus einem 31er-Alphabet
sind rund 79 Bit.

Was hier bewusst NICHT passiert:

* **Keine Adresse entsteht von selbst.** Wie bei der Belegbox ist das ein
  Handgriff (`anlegen`), kein Nebeneffekt einer Anmeldung. Eine Adresse,
  die niemand bestellt hat, wäre eine offene Tür, von der niemand weiß.
* **Keine Löschung, nur Stilllegung.** Steht eine Adresse einmal auf einem
  Briefkopf, kommt Post noch Monate später. `aktiv = 0` weist sie ab, ohne
  dass die Zuordnung aus der Geschichte verschwindet — und ohne dass der
  Zufallswert je ein zweites Mal vergeben wird.

Zum SQL: Platzhalter `?`, Typen wie überall (`db.py` übersetzt). Der
Schlüssel ist `lokal` selbst und nicht eine laufende `id` — die Adresse ist
von Natur aus eindeutig, und eine Tabelle ohne `id`-Spalte braucht keinen
Eintrag in `db.ID_TABELLEN`.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone

import mandanten

# Ohne i/l/o/0/1: die Adresse wird abgetippt, vom Telefon abgelesen und in
# Rechnungsprogramme eingetragen. Verwechselbare Zeichen kosten dort echte
# Post, und die 31 statt 36 Zeichen kosten nur zwei Bit.
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
GRUPPEN = 4
GRUPPE_LAENGE = 4

#: Was als lokaler Teil überhaupt in Frage kommt. Absichtlich eng: was hier
#: nicht durchkommt, wird gar nicht erst nachgeschlagen — ein SMTP-Empfänger
#: bekommt zu lesen, was ein Fremder ihm schickt.
LOKAL_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")

_TABELLE = """CREATE TABLE IF NOT EXISTS post_adresse
    (lokal TEXT PRIMARY KEY,
     mandant_id INTEGER NOT NULL REFERENCES mandant(id),
     angelegt TEXT NOT NULL,
     aktiv INTEGER NOT NULL DEFAULT 1)"""

_INDEX = """CREATE INDEX IF NOT EXISTS post_adresse_mandant
    ON post_adresse (mandant_id, aktiv)"""

SPALTEN = ("lokal", "mandant_id", "angelegt", "aktiv")


def schema(c) -> None:
    """Die Tabelle anlegen. Idempotent, aus `_db()` heraus gerufen —
    und zwar NACH `mandanten.schema()`: der Fremdschlüssel zeigt dorthin."""
    c.execute(_TABELLE)
    c.execute(_INDEX)


def _jetzt_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def neues_lokal() -> str:
    """Ein Zufallswort in Vierergruppen: `k7mq-3rtx-9wpd-2fhn`.

    Die Bindestriche sind reine Lesehilfe (in einem lokalen Teil erlaubt) —
    wer die Adresse vorliest, verliert sich sonst in sechzehn Zeichen.
    """
    return "-".join("".join(secrets.choice(ALPHABET) for _ in range(GRUPPE_LAENGE))
                    for _ in range(GRUPPEN))


def normieren(roh: str) -> str:
    """Aus dem, was im RCPT stand, den lokalen Teil machen — oder "".

    Drei Dinge passieren hier, und alle drei sind der Grund, warum das
    NICHT in der Aufrufstelle steht:

    * Kleinschreibung. Absender schreiben `K7MQ-…`, die Tabelle nicht.
    * Die Domäne fällt weg — geprüft wird sie beim Empfänger, nicht hier.
    * Ein `+`-Zusatz fällt weg (`k7mq-…+rechnung@`). Das ist die übliche
      Unteradressierung; sie ändert die Zuordnung nicht, und sie zu
      verbieten hieße nur, gutgemeinte Post zu verlieren.
    """
    wert = (roh or "").strip().lower()
    if "@" in wert:
        wert = wert.split("@", 1)[0]
    if "+" in wert:
        wert = wert.split("+", 1)[0]
    return wert if LOKAL_RE.match(wert) else ""


def anlegen(mandant_id: int, c=None, lokal: str | None = None) -> str:
    """Eine neue Empfangsadresse für diesen Betrieb; gibt den lokalen Teil.

    `lokal` ist nur für Tests und für die Übernahme einer schon gedruckten
    Adresse gedacht — im Normalfall würfelt die Funktion selbst.
    """
    wert = normieren(lokal) if lokal else neues_lokal()
    if not wert:
        raise ValueError("ungültiger lokaler Teil")
    with mandanten.sitzung(c) as cc:
        cc.execute("INSERT INTO post_adresse (lokal, mandant_id, angelegt, aktiv) "
                   "VALUES (?, ?, ?, 1)", (wert, int(mandant_id), _jetzt_iso()))
    return wert


def aufloesen(lokal: str, c=None) -> int | None:
    """Welcher Betrieb steckt hinter dieser Adresse — oder None.

    None heißt für den Posteingang: 550, Post abweisen. Deshalb wird hier
    ausdrücklich nur die AKTIVE Zeile gefunden; eine stillgelegte Adresse
    ist so gut wie keine.
    """
    wert = normieren(lokal)
    if not wert:
        return None
    with mandanten.sitzung(c) as cc:
        roh = cc.execute("SELECT mandant_id FROM post_adresse "
                         "WHERE lokal = ? AND aktiv = 1", (wert,)).fetchone()
    return int(roh[0]) if roh else None


def fuer_mandant(mandant_id: int, nur_aktive: bool = True, c=None) -> list[dict]:
    """Die Adressen eines Betriebs, jüngste zuerst."""
    sql = ("SELECT lokal, mandant_id, angelegt, aktiv FROM post_adresse "
           "WHERE mandant_id = ?")
    if nur_aktive:
        sql += " AND aktiv = 1"
    sql += " ORDER BY angelegt DESC, lokal"
    with mandanten.sitzung(c) as cc:
        rohe = cc.execute(sql, (int(mandant_id),)).fetchall()
    return [dict(zip(SPALTEN, r)) for r in rohe]


def stilllegen(lokal: str, mandant_id: int, c=None) -> bool:
    """Adresse abschalten — nur die eigene.

    `mandant_id` steht in der Bedingung und nicht bloß in einer Prüfung
    davor: sonst legte ein Aufrufer mit einer geratenen Adresse die eines
    fremden Betriebs still.
    """
    wert = normieren(lokal)
    if not wert:
        return False
    with mandanten.sitzung(c) as cc:
        zeiger = cc.execute("UPDATE post_adresse SET aktiv = 0 "
                            "WHERE lokal = ? AND mandant_id = ? AND aktiv = 1",
                            (wert, int(mandant_id)))
        return bool(zeiger.rowcount)
