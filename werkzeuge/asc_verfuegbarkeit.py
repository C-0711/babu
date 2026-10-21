#!/usr/bin/env python3
"""Wo es die App „babu Belege" im App Store gibt — lesen und setzen.

    asc_verfuegbarkeit.py zeigen     # je Status, wie viele Gebiete (ändert nichts)
    asc_verfuegbarkeit.py weltweit   # jedes Gebiet auf verfügbar

Entscheid des Auftraggebers 22.10.2026: **weltweit, aber nur für die
deutsche Buchhaltung und Steuer.** Wer im Ausland lebt und in Deutschland
steuerpflichtig ist, soll die App laden können. Der Zuschnitt auf deutsches
Recht (SKR04, DATEV, deutsches Steuerbüro) steht in den Texten, nicht in
der Länderliste. Vorher (11.10.2026) nur Deutschland.

Gesetzt wird je Gebiet über `PATCH /v1/territoryAvailabilities/<id>` —
am 22.10. an USA ausprobiert und zurückgelesen, bevor alle folgten.
Die Statuswerte (`contentStatuses`) gibt das Werkzeug so aus, wie Apple
sie liefert; was einer bedeutet, steht nicht hier.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asc_api as a  # noqa: E402

APP = "6811956687"


def gebiete() -> list[dict]:
    """Alle Gebiete mit Kennung, Länderkürzel und Attributen (v2)."""
    aus, pfad = [], (f"/appAvailabilities/{APP}/territoryAvailabilities"
                     "?limit=200&include=territory")
    while pfad:
        req = urllib.request.Request("https://api.appstoreconnect.apple.com/v2" + pfad,
                                     headers={"Authorization": "Bearer " + a.token()})
        with urllib.request.urlopen(req) as r:
            d = json.load(r)
        for x in d["data"]:
            aus.append({"id": x["id"],
                        "land": x["relationships"]["territory"]["data"]["id"],
                        **x["attributes"]})
        nxt = d.get("links", {}).get("next")
        pfad = nxt.split("/v2", 1)[1] if nxt else None
    return aus


def zeigen() -> None:
    alle = gebiete()
    print(f"{sum(g['available'] for g in alle)} von {len(alle)} Gebieten verfügbar")
    zahl = Counter((g["available"], tuple(g.get("contentStatuses") or [])) for g in alle)
    for (verf, status), n in zahl.most_common():
        print(f"  {n:4d}  {'verfügbar' if verf else 'nicht verfügbar':16s} {', '.join(status)}")


def weltweit() -> None:
    ok = fehler = 0
    for g in gebiete():
        if g["available"]:
            continue
        # Apple schliesst bei 174 Aufrufen hintereinander gelegentlich die
        # Verbindung (22.10.2026 erlebt). Das Gebiet bleibt dann einfach
        # „nicht verfügbar", und der nächste Lauf nimmt es mit.
        try:
            r = a.api("PATCH", f"/territoryAvailabilities/{g['id']}", {"data": {
                "type": "territoryAvailabilities", "id": g["id"],
                "attributes": {"available": True}}})
        except OSError as e:
            r = {"ok": False, "status": "-", "fehler": f"Verbindung: {e}"}
        if r["ok"]:
            ok += 1
        else:
            fehler += 1
            print(f"  {g['land']}: {r['status']} {r['fehler'][:160]}")
    print(f"{ok} Gebiete umgestellt, {fehler} abgelehnt")
    zeigen()


if __name__ == "__main__":
    was = sys.argv[1] if len(sys.argv) > 1 else "zeigen"
    if was in ("zeigen", "weltweit"):
        globals()[was]()
    else:
        print(__doc__)
        sys.exit(2)
