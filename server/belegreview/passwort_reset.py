#!/usr/bin/env python3
"""Passwort zurücksetzen ohne Klartext über Betriebsgrenzen — Plan 21,
Abschnitt 7.

Setzt eine Kanzlei das Passwort einer Person zurück, die zum eigenen
Betrieb gehört (die Inhaberin für ihr Team, oder admin für jeden), bleibt
das alte Verhalten: ein Startpasswort, einmal in der Antwort, persönlich
weitergegeben. Reicht die Kanzlei aber in einen FREMDEN Betrieb hinein
(einen anderen Mandanten), sieht sie das neue Passwort nie — sie bekommt
nur einen Link, den sie der betroffenen Person zustellt. Erst wer den Link
öffnet, setzt sein eigenes Passwort.

Dasselbe Muster wie `einladung.py`: der Token steht nirgends im Klartext,
nur sein Hash. Auch hier reine Zustandsprüfung — keine Datenbank, keine
Route. Einzige Ausnahme ist `schema()`: die Tabelle braucht EINEN
CREATE-Aufruf irgendwo, und `_db()` in `babu_web.py` darf für diese
Aufgabe nur den einen `audit.schema(c)`-Aufruf bekommen — deshalb hängt
`schema()` hier an `audit.schema()` (siehe `audit.py`), statt einen
zweiten eigenen Aufruf in `_db()` zu brauchen.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Zwei Wochen, wie beim Auswertungs-Link (einladung.py FRIST) — lang genug
# für eine Urlaubsvertretung, kurz genug, dass ein liegen gelassener Link
# nicht noch im nächsten Quartal ein fremdes Konto öffnet.
FRIST = timedelta(days=14)

MINDEST_PASSWORT = 10

# Wie oft für dieselbe Person ein Reset-Link angefordert werden darf, bevor
# gebremst wird. Ohne Bremse könnte eine Kanzlei beliebig viele Links
# erzeugen — jeder neue Link entwertet dabei nicht automatisch den alten,
# aber die Tabelle würde zumüllen, und dieselbe Prüfung schützt auch davor,
# dass jemand den Reset-Weg zum Aussperren fremder Konten missbraucht.
VERSUCHE_MAX = 5
VERSUCHE_FENSTER = timedelta(hours=24)

# 192 Bit Zufall, wie beim Auswertungs-Schlüssel (einladung.py).
_TOKEN_BYTES = 192 // 8


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def token_erzeugen() -> str:
    """Der Teil, der in den Link geht. Genau einmal im Klartext sichtbar —
    in der Antwort an die Kanzlei, nie in der Datenbank."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def token_hash(token: str) -> str:
    """Was in der Datenbank steht. Aus ihm folgt kein Token."""
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def schema(c: sqlite3.Connection) -> None:
    """Von `audit.schema(c)` aufgerufen — siehe Modul-Docstring."""
    c.execute("""CREATE TABLE IF NOT EXISTS passwort_reset
        (id INTEGER PRIMARY KEY AUTOINCREMENT, token_hash TEXT NOT NULL UNIQUE,
         un TEXT NOT NULL, erstellt TEXT NOT NULL, laeuft_ab TEXT NOT NULL,
         eingeloest TEXT)""")
    c.execute("""CREATE INDEX IF NOT EXISTS passwort_reset_un
        ON passwort_reset (un, erstellt)""")


@dataclass
class Reset:
    """Ein angeforderter Link, der auf seine Einlösung wartet."""
    un: str
    token_hash: str
    erstellt: datetime
    laeuft_ab: datetime
    eingeloest: datetime | None = None

    @property
    def offen(self) -> bool:
        return self.eingeloest is None and _jetzt() <= self.laeuft_ab


@dataclass
class Ergebnis:
    ok: bool
    grund: str = ""
    reset: Reset | None = None
    token: str | None = None      # nur beim Anlegen, für den Link


def gebremst(frueher: list[datetime] | None) -> bool:
    """Wie `einladung.gebremst` — dieselbe Bremse, dieselbe Begründung:
    zu viele Anforderungen im Zeitfenster für dieselbe Person."""
    grenze = _jetzt() - VERSUCHE_FENSTER
    return len([t for t in (frueher or []) if t > grenze]) >= VERSUCHE_MAX


def anfordern(un: str) -> tuple[str, Reset]:
    """Token + Modell für einen neuen Link. Schreibt nichts — die Route
    entscheidet über die Bremse und legt die Zeile an."""
    token = token_erzeugen()
    jetzt = _jetzt()
    return token, Reset(un=(un or "").strip().lower(),
                        token_hash=token_hash(token), erstellt=jetzt,
                        laeuft_ab=jetzt + FRIST)


def pruefen(reset: Reset | None, token: str) -> Ergebnis:
    """Gehört dieser Token zu diesem Reset, und gilt er noch?"""
    if reset is None:
        return Ergebnis(False, "Dieser Link ist uns nicht bekannt.")
    if not secrets.compare_digest(reset.token_hash, token_hash(token)):
        return Ergebnis(False, "Dieser Link ist uns nicht bekannt.")
    if reset.eingeloest is not None:
        return Ergebnis(False, "Dieser Link wurde schon benutzt — melde dich "
                               "mit E-Mail und dem neuen Passwort an.")
    if _jetzt() > reset.laeuft_ab:
        return Ergebnis(False, "Dieser Link ist abgelaufen — bitte einen "
                               "neuen Link anfordern.")
    return Ergebnis(True, reset=reset)


def passwort_pruefen(erstes: str, zweites: str) -> Ergebnis:
    """Zweimal eingeben heißt: beide müssen gleich sein und etwas taugen."""
    if (erstes or "") != (zweites or ""):
        return Ergebnis(False, "Die beiden Passwörter sind nicht gleich.")
    if len(erstes or "") < MINDEST_PASSWORT:
        return Ergebnis(False, f"Bitte mindestens {MINDEST_PASSWORT} Zeichen — "
                               f"lieber ein Satz als ein kurzes Kunstwort.")
    return Ergebnis(True)


def einloesen(reset: Reset | None, token: str, passwort: str,
              passwort2: str) -> Ergebnis:
    """Der Schritt, aus dem ein neues Passwort wird. Prüft alles, ändert
    nichts — die Route schreibt und setzt danach `eingeloest`."""
    if not (geprueft := pruefen(reset, token)).ok:
        return geprueft
    if not (pw := passwort_pruefen(passwort, passwort2)).ok:
        return pw
    return Ergebnis(True, reset=reset)
