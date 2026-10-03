#!/usr/bin/env python3
"""golden — der Golden-Diff des Deploy-Rituals, ohne Zugangscode (seit 03.10.2026).

Das Ritual verlangt vor und nach jedem Deploy, der den Buchungsweg berührt,
`/api/belege` und `/api/abgleich/<monat>` byte-gleich zu vergleichen. Seit dem
GitChain-Standard (27.09.2026) sind alle Token auf der H200V Dienst-Token —
`/api/anmelden` mit ihnen gibt 401, der Diff ging nicht mehr.

Dieses Werkzeug läuft IM Container, unterschreibt dort eine kurze Sitzung (fünf
Minuten) für den Betreiber-Zugang mit demselben Geheimnis wie der Server und
fragt den laufenden Server über 127.0.0.1 — keine Token-Datei, kein Passwort,
nichts verlässt den Rechner. Gelesen wird nur (GET).

    docker exec babu-web python /app/werkzeuge/golden.py --monat 2026-09 \\
        > ~/golden/vor-$(date +%Y%m%d-%H%M%S).json
    … Deploy …
    docker exec babu-web python /app/werkzeuge/golden.py --monat 2026-09 \\
        > ~/golden/nach-….json
    diff ~/golden/vor-….json ~/golden/nach-….json && echo GLEICH

Ausgabe: ein JSON-Objekt {pfad: antwort}, Schlüssel sortiert (wie
`python3 -m json.tool --sort-keys`). Rückgabe 0, wenn alle Antworten 200
waren, sonst 1.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
BELEGREVIEW = next((k for k in (WURZEL / "server" / "belegreview", WURZEL)
                    if (k / "babu_web.py").is_file()), WURZEL / "server" / "belegreview")
if str(BELEGREVIEW) not in sys.path:
    sys.path.insert(0, str(BELEGREVIEW))

import babu_web as bw  # noqa: E402


def holen(basis: str, pfad: str, cookie: str) -> tuple[int, object]:
    anfrage = urllib.request.Request(basis + pfad, headers={
        "Cookie": f"{bw.SESSION_COOKIE}={cookie}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(anfrage, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        return ex.code, {"fehler": ex.read().decode("utf-8", "replace")[:300]}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Golden-Diff ohne Zugangscode")
    p.add_argument("--monat", action="append", required=True,
                   help="Monat für /api/abgleich (mehrfach möglich), z. B. 2026-09")
    p.add_argument("--zugang", default=os.environ.get("BABU_GOLDEN_ZUGANG", "christoph"),
                   help="Betreiber-Zugang (Rolle admin), Standard christoph")
    p.add_argument("--basis", default=f"http://127.0.0.1:{os.environ.get('BABU_PORT', '7844')}")
    args = p.parse_args(argv)
    if bw.rolle(args.zugang) != "admin":
        print(f"{args.zugang} ist kein Betreiber — der Diff liest die Standard-Ablage "
              "nur als admin.", file=sys.stderr)
        return 2
    cookie = bw._signieren(args.zugang, int(time.time()) + 300)  # noqa: SLF001
    ergebnis, ok = {}, True
    for pfad in ["/api/belege"] + [f"/api/abgleich/{m}" for m in args.monat]:
        status, daten = holen(args.basis, pfad, cookie)
        ergebnis[pfad] = {"status": status, "antwort": daten}
        ok = ok and status == 200
    print(json.dumps(ergebnis, ensure_ascii=False, indent=4, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
