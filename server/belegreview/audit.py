#!/usr/bin/env python3
"""Audit-Log für die Verwaltungsrouten — Plan 21, Abschnitt 7.

Jede Aktion, die ein Kanzlei- oder Admin-Konto an einem fremden Zugang
vornimmt (Nutzer anlegen, deaktivieren, Rolle ändern, Box frei-/sperren,
Passwort zurücksetzen, DATEV-Export), hinterlässt eine Zeile: wer, was, an
wem, wann. Ohne Mandantentabellen (die kommen erst mit dem Postgres-Umbau,
Plan 21 Abschnitt 8) gibt es noch keine echte Mandanten-ID — die Spalte
steht schon bereit und bleibt bis dahin NULL.

`_db()` in `babu_web.py` darf für diese Aufgabe nur EINEN neuen Aufruf
bekommen (`audit.schema(c)`) — alles, was diese Aufgabe an neuem Schema
braucht, hängt deshalb an diesem einen Aufruf: die Audit-Tabelle selbst,
und darüber auch `passwort_reset` (siehe `passwort_reset.py`), damit dessen
Tabelle nicht einen zweiten, eigenen Aufruf in `_db()` bräuchte.

Platzhalter bewusst `?`, keine SQLite-Sonderfunktionen (kein
`datetime('now')`, kein `INSERT OR REPLACE`) — ein anderer Umbau übersetzt
`?` → `%s` für Postgres und würde sonst hier erneut ansetzen müssen.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

# Was nie in `details` landen darf, egal wie der Aufrufer das Feld nennt —
# eine zweite Sicherung, falls irgendwo versehentlich ein Geheimnis
# mitgegeben wird. Die eigentliche Regel bleibt: Aufrufer geben so etwas
# gar nicht erst mit.
_GEHEIM = {"pw", "passwort", "passwort2", "startpasswort", "token",
           "schluessel", "pat", "code", "zugangscode", "geheimnis"}


def schema(c: sqlite3.Connection) -> None:
    """In `_db()` aufrufen — legt Audit- UND Reset-Tabelle an, wenn sie
    fehlen (siehe Modul-Docstring, warum beides hier zusammenläuft)."""
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log
        (id INTEGER PRIMARY KEY AUTOINCREMENT, zeit TEXT NOT NULL,
         akteur_un TEXT NOT NULL, aktion TEXT NOT NULL, ziel_un TEXT,
         mandant_id TEXT, details TEXT NOT NULL DEFAULT '{}')""")
    c.execute("""CREATE INDEX IF NOT EXISTS audit_log_zeit
        ON audit_log (id DESC)""")
    import passwort_reset as pr  # noqa: PLC0415
    pr.schema(c)


def _bereinigt(details: dict) -> dict:
    return {k: v for k, v in details.items() if k.lower() not in _GEHEIM}


def audit(akteur_un: str, aktion: str, ziel_un: str | None = None,
          mandant_id: str | None = None, **details) -> None:
    """Eine Zeile ins Audit-Log.

    Öffnet eine eigene Verbindung statt eine übergebene zu erwarten — die
    Verwaltungsroute hat ihre eigene `with _DB_LOCK, _db() as c:`-Zeile
    meist schon wieder verlassen, wenn sie auditiert (Absicht: das
    `_DB_LOCK` ist kein Reentrant-Lock, ein Aufruf mitten in einem
    laufenden `with`-Block würde den Prozess festfahren).

    `import babu_web` erst hier drin, nicht oben im Modul: `babu_web.py`
    ruft `audit.schema()` aus `_db()` heraus auf — ein Import auf
    Modulebene in beide Richtungen wäre ein Zirkelbezug.
    """
    import babu_web as bw  # noqa: PLC0415
    zeit = datetime.now(timezone.utc).isoformat()
    bereinigt = _bereinigt(details)
    try:
        with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
            c.execute(
                """INSERT INTO audit_log (zeit, akteur_un, aktion, ziel_un,
                   mandant_id, details) VALUES (?, ?, ?, ?, ?, ?)""",
                (zeit, akteur_un, aktion, ziel_un, mandant_id,
                 json.dumps(bereinigt, ensure_ascii=False)))
    except Exception as ex:  # noqa: BLE001
        # Ein Fehler im Log darf die eigentliche Verwaltungsaktion nicht
        # verhindern — sie ist zu diesem Zeitpunkt schon passiert.
        print(f"[audit] Zeile konnte nicht geschrieben werden: {ex!r}", flush=True)
