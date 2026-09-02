#!/usr/bin/env python3
"""Einmal umziehen: `portal.db` → Postgres.

Läuft **von Hand**, nicht beim Containerstart (Plan 21, Abschnitt 9): das
Skript räumt die Zieltabellen leer, bevor es füllt. In einem `CMD` würde es
bei jedem Neustart alles wegwerfen.

    BABU_DB_URL=postgresql://… python3 werkzeug/migrate_sqlite_to_pg.py \\
        [~/babu-web/portal.db] [--trocken]

Was es tut, in dieser Reihenfolge:

1. Migrationen fahren, damit das Ziel überhaupt Tabellen hat.
2. `TRUNCATE … CASCADE` über alle Tabellen — deshalb ist ein zweiter Lauf
   so gut wie der erste. Kein inkrementelles Abgleichen: das Wartungsfenster
   ist kurz, ein Vollimport ist einfacher zu verstehen und zu prüfen.
3. Tabelle für Tabelle kopieren, `nutzer` zuerst (dort hängen die
   Fremdschlüssel dran, sobald es welche gibt).
4. Die IDENTITY-Zähler auf `max(id)` nachziehen — sonst vergäbe Postgres
   beim ersten Einfügen die 1 und liefe in einen Schlüsselkonflikt.
5. Zeilen zählen und vergleichen. Stimmt eine Zahl nicht, endet das Skript
   mit einem Fehler und die Transaktion wird zurückgerollt.

Was es **nicht** tut: Es legt **keine** `kanzlei`- oder `mandant`-Zeilen an.
Aus einem Salon-Konto mit Box eine Kanzlei mit Mandanten zu machen, wäre
geraten — Kontenrahmen, Berater- und Mandantennummer weiß nur ein Mensch.
Das bleibt ein bewusster Handgriff (Plan 21, Abschnitt 5).

Die `portal.db` wird nur gelesen. Sie bleibt liegen und ist der Rückweg:
`BABU_DB_URL` entfernen, und babu-web spricht wieder mit ihr.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

import db  # noqa: E402

#: `nutzer` zuerst — dort zeigen die Fremdschlüssel hin, sobald Phase 2 sie
#: einzieht. Der Rest ist heute unabhängig; die Reihenfolge steht trotzdem
#: fest, damit ein Lauf reproduzierbar ist.
REIHENFOLGE = (
    "nutzer",
    "abschluss_status", "anlagegut", "app_schluessel", "behandlung",
    "einladung", "einstellungen", "gespraech", "kundin", "leistung",
    "lesestatus", "meldung_puffer", "mitarbeiter", "nachricht",
    "registrierungen", "team", "termin", "wa_faden", "wa_nachricht",
)


def sqlite_tabellen(conn) -> set[str]:
    return {z[0] for z in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'")}


def sqlite_spalten(conn, tabelle: str) -> list[str]:
    return [z[1] for z in conn.execute(f"PRAGMA table_info({tabelle})")]


def pg_spalten(cur, tabelle: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s AND table_schema = current_schema()",
                (tabelle,))
    return {z[0] for z in cur.fetchall()}


def umziehen(quelle: Path, url: str, trocken: bool = False) -> dict[str, int]:
    """Kopiert alles und liefert {Tabelle: Zeilen}. Wirft bei Ungleichheit."""
    import psycopg  # noqa: PLC0415

    quell_conn = sqlite3.connect(f"file:{quelle}?mode=ro", uri=True)
    ziel = psycopg.connect(url)
    gezaehlt: dict[str, int] = {}
    try:
        db.schema_anwenden(ziel, "postgres")
        vorhanden = sqlite_tabellen(quell_conn)
        cur = ziel.cursor()

        tabellen = [t for t in REIHENFOLGE if t in vorhanden]
        fehlt = vorhanden - set(REIHENFOLGE) - {"schema_version"}
        if fehlt:
            raise SystemExit(
                f"In {quelle} stehen Tabellen, die dieses Skript nicht kennt: "
                f"{sorted(fehlt)}. Erst REIHENFOLGE ergänzen, dann umziehen.")

        if not trocken and tabellen:
            # Ein einziges TRUNCATE über alle: so gibt es keine Reihenfolge,
            # in der ein Fremdschlüssel im Weg stünde.
            cur.execute("TRUNCATE " + ", ".join(tabellen) + " RESTART IDENTITY CASCADE")

        for tabelle in tabellen:
            spalten = [s for s in sqlite_spalten(quell_conn, tabelle)
                       if s in pg_spalten(cur, tabelle)]
            if not spalten:
                raise SystemExit(f"{tabelle}: keine gemeinsamen Spalten")
            zeilen = quell_conn.execute(
                f"SELECT {', '.join(spalten)} FROM {tabelle}").fetchall()
            gezaehlt[tabelle] = len(zeilen)
            if trocken or not zeilen:
                continue
            marken = ", ".join(["%s"] * len(spalten))
            cur.executemany(
                f"INSERT INTO {tabelle} ({', '.join(spalten)}) VALUES ({marken})",
                zeilen)

            if "id" in spalten:
                # Der IDENTITY-Zähler weiß nichts von den mitgebrachten
                # Nummern. Ohne das hier vergäbe er beim nächsten Einfügen
                # die 1 — und liefe gegen den Primärschlüssel.
                cur.execute(
                    f"SELECT setval(pg_get_serial_sequence('{tabelle}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {tabelle}), 1), "
                    f"(SELECT COUNT(*) FROM {tabelle}) > 0)")

            cur.execute(f"SELECT COUNT(*) FROM {tabelle}")
            angekommen = cur.fetchone()[0]
            if angekommen != len(zeilen):
                raise SystemExit(
                    f"{tabelle}: {len(zeilen)} gelesen, {angekommen} angekommen")

        if trocken:
            ziel.rollback()
        else:
            ziel.commit()
        return gezaehlt
    except BaseException:
        ziel.rollback()
        raise
    finally:
        quell_conn.close()
        ziel.close()


def main(argv: list[str]) -> int:
    trocken = "--trocken" in argv
    reste = [a for a in argv if not a.startswith("--")]
    quelle = Path(reste[0]).expanduser() if reste else Path(
        os.environ.get("BABU_PORTAL_DB")
        or (Path.home() / "babu-web" / "portal.db"))
    url = (os.environ.get("BABU_DB_URL") or "").strip()
    if not url:
        print("BABU_DB_URL fehlt — wohin soll der Umzug gehen?", file=sys.stderr)
        return 2
    if not quelle.is_file():
        print(f"{quelle} gibt es nicht.", file=sys.stderr)
        return 2

    print(f"{'Probe' if trocken else 'Umzug'}: {quelle} → Postgres")
    gezaehlt = umziehen(quelle, url, trocken)
    breite = max((len(t) for t in gezaehlt), default=0)
    for tabelle in sorted(gezaehlt):
        print(f"  {tabelle:<{breite}}  {gezaehlt[tabelle]:>7}")
    print(f"  {'':<{breite}}  {sum(gezaehlt.values()):>7} Zeilen insgesamt")
    if trocken:
        print("Probelauf — nichts geschrieben.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
