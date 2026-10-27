"""Die Paywall messen (27.10.2026).

Die Kaufseite („Deine Ablage" → „Platz buchen", das Angebot nach dem ersten
Beleg, der Streifen „noch n frei", die Sperre bei vollem Platz) meldet, woher
sie kam und was danach geschah. Daraus wird je Monat ein Trichter: wie oft
gesehen, wie oft gekauft, wie oft „erst kostenlos weiter", wie oft
weggewischt. Ohne diese Zahlen bliebe jede Änderung an der Kaufseite eine
Vermutung.

**Was gespeichert wird.** Je Ereignis eine Zeile: Betrieb, Quelle, Aktion,
gewählte Stufe (nur beim Kauf), Zeitpunkt. Kein Preis, kein Gerät, kein
Name — der Betrieb ist über `mandant_id` da, und wer sein Konto löscht,
nimmt diese Zeilen mit (`kern_konto.NACH_MANDANT`).

**Wer melden darf.** Nur ein Betrieb, der in der App entstanden ist
(`herkunft = "app"`): nur er hat Stufen. Ein Portal-Betrieb hängt an einer
Kanzlei und kennt keine Kaufseite — er bekommt 409 mit dem Grund, und es
wird nichts gezählt.

**Wer die Zahlen sieht.** Der Trichter hängt in `/api/kpi/{monat}` und nur
für `admin` — die Kennzahlen einer Inhaberin sind ihre, der Trichter ist
der des Betreibers.
"""
from __future__ import annotations

import datetime as dt
import json

from fastapi import Request
from fastapi.responses import JSONResponse, Response

import paket

#: Woher die Kaufseite kam.
QUELLEN = ("angebot", "menue", "streifen", "voll")
#: Was danach geschah.
AKTIONEN = ("gesehen", "gekauft", "weiter", "abgebrochen", "wiederhergestellt")

_PLATZ_EREIGNIS = """CREATE TABLE IF NOT EXISTS platz_ereignis
    (id INTEGER PRIMARY KEY AUTOINCREMENT,
     mandant_id INTEGER NOT NULL,
     quelle TEXT NOT NULL,
     aktion TEXT NOT NULL,
     stufe TEXT,
     zeit TEXT NOT NULL)"""


def schema(c) -> None:
    """Idempotent, aus `_db()` heraus gerufen. Abbild: migrations/0020_platz_ereignis.sql."""
    c.execute(_PLATZ_EREIGNIS)


def setup(app, bw_modul):
    """Der Kern reicht sich selbst herein — siehe `kern_konto.setup`."""
    globals()["bw"] = bw_modul
    globals()["app"] = app
    app.post("/api/platz/ereignis")(api_platz_ereignis)


def _app_betrieb(un: str) -> int | None:
    """Die Nummer des App-Betriebs dieses Zugangs — oder `None`, wenn der
    Zugang keinen Betrieb mit Platz-Modell hat."""
    import testmonat  # noqa: PLC0415
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        direkt = testmonat.direkt_mandant_von(un, c)
        if not direkt:
            return None
        zeile = c.execute("SELECT herkunft FROM mandant WHERE id=?",
                          (int(direkt[0]),)).fetchone()
    if not zeile or zeile[0] != paket.HERKUNFT_APP:
        return None
    return int(direkt[0])


async def api_platz_ereignis(request: Request) -> Response:
    """`POST /api/platz/ereignis {"quelle", "aktion", "stufe"?}` → 204.

    400 bei unbekannten Werten, 409 für Konten ohne App-Betrieb. Die App
    ruft das feuer-und-vergessen; eine Antwort mit Inhalt braucht sie nicht.
    """
    un, fehler = bw._box_wache(request)  # noqa: SLF001
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"},
                                      status_code=401)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 4 * 1024) or b"{}")
    except Exception:  # noqa: BLE001
        koerper = {}
    if not isinstance(koerper, dict):
        koerper = {}
    quelle = koerper.get("quelle")
    aktion = koerper.get("aktion")
    stufe = koerper.get("stufe")
    if quelle not in QUELLEN or aktion not in AKTIONEN:
        return JSONResponse({"fehler": "unbekannte Quelle oder Aktion"},
                            status_code=400)
    if stufe is not None and (not isinstance(stufe, str) or len(stufe) > 32):
        return JSONResponse({"fehler": "unbekannte Stufe"}, status_code=400)
    mandant_id = _app_betrieb(un)
    if mandant_id is None:
        return JSONResponse({"fehler": "kein Platz-Modell"}, status_code=409)
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        c.execute("INSERT INTO platz_ereignis (mandant_id, quelle, aktion, stufe, zeit) "
                  "VALUES (?, ?, ?, ?, ?)",
                  (mandant_id, quelle, aktion, stufe,
                   dt.datetime.now(dt.timezone.utc).isoformat()))
    return Response(status_code=204)


def trichter(monat: str) -> dict[str, dict[str, int]]:
    """Je Quelle die fünf Aktionen des Monats (`YYYY-MM`), fehlende als 0.
    Quellen ohne ein einziges Ereignis fehlen ganz — ein leerer Monat ist `{}`."""
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        zeilen = c.execute(
            "SELECT quelle, aktion, COUNT(*) FROM platz_ereignis "
            "WHERE zeit LIKE ? GROUP BY quelle, aktion",
            (monat + "%",)).fetchall()
    aus: dict[str, dict[str, int]] = {}
    for quelle, aktion, n in zeilen:
        aus.setdefault(quelle, {a: 0 for a in AKTIONEN})[aktion] = int(n)
    return aus
