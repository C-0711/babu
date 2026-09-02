"""Gemeinsames für die Suite — bislang nur: wie man an ein Postgres kommt.

Zwei getrennte Dinge stehen hier:

1. **Die Fixture `pg_url`** für die mit `@pytest.mark.pg` markierten Tests.
   Sie nimmt `BABU_TEST_DB_URL`, wenn eine gesetzt ist; sonst versucht sie,
   sich mit `initdb`/`pg_ctl` eine Wegwerf-Instanz in einem Temp-Verzeichnis
   zu starten und räumt sie hinterher weg; klappt auch das nicht, wird
   übersprungen. **Die übrige Suite setzt dadurch nichts Neues voraus** —
   ohne Postgres läuft sie unverändert gegen SQLite, so wie es in CLAUDE.md
   unter „Bauen & Testen" steht.

2. **Der Schema-Haken** für den Lauf der *ganzen* Suite gegen Postgres
   (`BABU_DB_URL=… pytest tests/`). Die Suite verlässt sich überall darauf,
   dass jeder Test eine frische, leere `portal.db` bekommt — bei Postgres
   gäbe es dagegen eine einzige Datenbank für alle. Der Haken bildet jeden
   SQLite-Pfad auf ein eigenes Postgres-Schema ab; damit bleibt die
   Isolation, ohne dass ein einziger bestehender Test angefasst werden muss.
   Im Betrieb ist der Haken nicht gesetzt und es passiert nichts.
"""
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

#: Homebrew legt Postgres 16 hierhin; im Container/CI steht es im PATH.
PG_BIN_KANDIDATEN = (
    Path("/opt/homebrew/opt/postgresql@16/bin"),
    Path("/usr/local/opt/postgresql@16/bin"),
    Path("/usr/lib/postgresql/16/bin"),
)
#: Nicht 55432 — das ist im Compose der produktive Port. Die Wegwerf-Instanz
#: soll auch dann laufen können, wenn daneben ein echter Server steht.
TEST_PORT = 55433


def _pg_bin() -> Path | None:
    for ordner in PG_BIN_KANDIDATEN:
        if (ordner / "initdb").is_file():
            return ordner
    wo = shutil.which("initdb")
    return Path(wo).parent if wo else None


def _port_frei(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


# ---------------------------------------------------------------------------
# 1. Wegwerf-Instanz für die pg-Tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def pg_url(tmp_path_factory):
    """Eine Verbindungszeichenfolge auf ein echtes Postgres — oder skip."""
    von_aussen = (os.environ.get("BABU_TEST_DB_URL")
                  or os.environ.get("BABU_DB_URL") or "").strip()
    if von_aussen:
        yield von_aussen
        return

    binordner = _pg_bin()
    if binordner is None:
        pytest.skip("kein Postgres 16 gefunden (initdb fehlt)")
    if not _port_frei(TEST_PORT):
        pytest.skip(f"Port {TEST_PORT} ist belegt — Wegwerf-Instanz unmöglich")

    daten = tmp_path_factory.mktemp("pgdaten") / "cluster"
    # LC_ALL=C: ohne gültige Locale macht macOS den Postmaster beim Start
    # mehrfädig ("postmaster became multithreaded during startup"), und
    # Postgres bricht ab. Passt ohnehin zu --locale=C unten.
    umgebung = {**os.environ, "LC_ALL": "C", "LANG": "C"}
    # --locale=C: SQLite sortiert Zeichenketten binär. Damit `ORDER BY name`
    # in beiden Dialekten dieselbe Reihenfolge liefert, muss Postgres
    # dasselbe tun — sonst misst man Locale statt Code.
    lauf = subprocess.run(
        [str(binordner / "initdb"), "-D", str(daten), "-U", "babu",
         "--locale=C", "--encoding=UTF8", "-A", "trust"],
        capture_output=True, text=True, env=umgebung)
    if lauf.returncode != 0:
        pytest.skip(f"initdb schlug fehl: {lauf.stderr.strip()[:200]}")

    protokoll = daten.parent / "postgres.log"
    # `unix_socket_directories=` leer: das Temp-Verzeichnis von pytest ist
    # länger als die 103 Byte, die ein Unix-Socket-Pfad haben darf — der
    # Server startet sonst gar nicht. Über TCP auf 127.0.0.1 geht alles.
    lauf = subprocess.run(
        [str(binordner / "pg_ctl"), "-D", str(daten), "-l", str(protokoll),
         "-o", f"-p {TEST_PORT} -c listen_addresses=127.0.0.1 "
               f"-c unix_socket_directories= -c fsync=off "
               f"-c synchronous_commit=off -c full_page_writes=off",
         "-w", "start"],
        capture_output=True, text=True, env=umgebung)
    if lauf.returncode != 0:
        hinweis = protokoll.read_text(errors="replace")[-300:] \
            if protokoll.exists() else lauf.stderr
        pytest.skip(f"pg_ctl start schlug fehl: {hinweis.strip()[:300]}")

    try:
        subprocess.run([str(binordner / "createdb"), "-h", "127.0.0.1",
                        "-p", str(TEST_PORT), "-U", "babu", "babu"],
                       capture_output=True, text=True, check=False,
                       env=umgebung)
        yield f"postgresql://babu@127.0.0.1:{TEST_PORT}/babu"
    finally:
        subprocess.run([str(binordner / "pg_ctl"), "-D", str(daten),
                        "-m", "immediate", "-w", "stop"],
                       capture_output=True, text=True, check=False,
                       env=umgebung)


@pytest.fixture()
def pg_schema(pg_url):
    """Ein frisches, leeres Schema je Test — und hinterher weg damit."""
    import psycopg  # noqa: PLC0415

    name = f"t{int(time.time() * 1000) % 10**10}_{os.getpid()}"
    with psycopg.connect(pg_url) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        conn.execute(f'CREATE SCHEMA "{name}"')
        conn.commit()
    try:
        yield name
    finally:
        with psycopg.connect(pg_url) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
            conn.commit()


# ---------------------------------------------------------------------------
# 2. Ganze Suite gegen Postgres: ein Schema je „portal.db"
# ---------------------------------------------------------------------------

def _schema_zu(pfad) -> str:
    """Aus einem SQLite-Pfad einen stabilen, kurzen Schemanamen machen.

    Der Pfad selbst taugt nicht als Name (zu lang, Sonderzeichen), und
    Postgres kürzt Bezeichner stumm auf 63 Zeichen — deshalb der Hash.
    """
    return "s_" + hashlib.sha1(str(pfad).encode()).hexdigest()[:24]


def pytest_configure(config):     # noqa: ARG001
    if not (os.environ.get("BABU_DB_URL") or "").strip():
        return
    import db  # noqa: PLC0415
    db.SCHEMA_HAKEN = _schema_zu
