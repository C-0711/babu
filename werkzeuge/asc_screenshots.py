#!/usr/bin/env python3
"""ASC-Aktion: Screenshots einer Version austauschen (14.10.2026).

Vorgeschichte: im Store lagen fünf Bilder, von denen eines den Export-Bildschirm
zeigte, wie er vor dem 13.10. aussah — und es gab keines von „Deine Ablage",
also keines von dem Bildschirm, auf dem die drei Abos stehen. Genau den will
Apple für die Abo-Prüfung sehen.

Apple nimmt Bilder in drei Schritten an, und der dritte ist der, den man
vergisst: ohne `uploaded: true` samt MD5 bleibt das Bild für immer
`AWAITING_UPLOAD` und die Version lässt sich nicht einreichen.

    1. POST /appScreenshots          -> Reservierung + uploadOperations
    2. PUT  (je Operation)           -> die Bytes, stückweise wie angewiesen
    3. PATCH /appScreenshots/<id>    -> uploaded=true + sourceFileChecksum

    python3 werkzeuge/asc_screenshots.py zeigen
    python3 werkzeuge/asc_screenshots.py setzen APP_IPHONE_67 BILD…   (ersetzt den Satz)
"""
from __future__ import annotations

import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asc_api import api, token  # noqa: E402

APP = "6811956687"
SPRACHE = "de-DE"


def _lokalisierung() -> str:
    v = api("GET", f"/apps/{APP}/appStoreVersions?limit=1")
    vid = v["daten"]["data"][0]["id"]
    r = api("GET", f"/appStoreVersions/{vid}/appStoreVersionLocalizations")
    for l in r["daten"]["data"]:
        if l["attributes"]["locale"] == SPRACHE:
            return l["id"]
    raise SystemExit(f"Keine Lokalisierung {SPRACHE}")


def _saetze(lid: str) -> dict[str, str]:
    r = api("GET", f"/appStoreVersionLocalizations/{lid}/appScreenshotSets")
    return {s["attributes"]["screenshotDisplayType"]: s["id"] for s in r["daten"]["data"]}


def _bilder(satz_id: str) -> list[dict]:
    r = api("GET", f"/appScreenshotSets/{satz_id}/appScreenshots?limit=20")
    return r["daten"]["data"] if r["ok"] else []


def zeigen() -> int:
    lid = _lokalisierung()
    for art, sid in sorted(_saetze(lid).items()):
        bilder = _bilder(sid)
        print(f"{art}  ({len(bilder)} Bilder)  {sid}")
        for b in bilder:
            a = b["attributes"]
            zustand = (a.get("assetDeliveryState") or {}).get("state")
            print(f"   {a.get('fileName')}  {a.get('imageAsset', {}).get('width')}"
                  f"x{a.get('imageAsset', {}).get('height')}  {zustand}")
    return 0


def _hochladen(satz_id: str, pfad: Path) -> str:
    """Ein Bild in den Satz — die drei Schritte, mit dem dritten."""
    daten = pfad.read_bytes()
    r = api("POST", "/appScreenshots", {"data": {
        "type": "appScreenshots",
        "attributes": {"fileSize": len(daten), "fileName": pfad.name},
        "relationships": {"appScreenshotSet": {
            "data": {"type": "appScreenshotSets", "id": satz_id}}}}})
    if not r["ok"]:
        raise SystemExit(f"{pfad.name}: Reservierung abgelehnt — {r.get('fehler','')[:300]}")
    bild = r["daten"]["data"]
    for op in bild["attributes"]["uploadOperations"]:
        stueck = daten[op["offset"]:op["offset"] + op["length"]]
        req = urllib.request.Request(op["url"], method=op["method"], data=stueck)
        for k in op["requestHeaders"]:
            req.add_header(k["name"], k["value"])
        with urllib.request.urlopen(req) as a:
            if a.status >= 300:
                raise SystemExit(f"{pfad.name}: Teil {op['offset']} abgelehnt ({a.status})")
    p = api("PATCH", f"/appScreenshots/{bild['id']}", {"data": {
        "type": "appScreenshots", "id": bild["id"],
        "attributes": {"uploaded": True,
                       "sourceFileChecksum": hashlib.md5(daten).hexdigest()}}})
    if not p["ok"]:
        raise SystemExit(f"{pfad.name}: Abschluss abgelehnt — {p.get('fehler','')[:300]}")
    return bild["id"]


def setzen(art: str, pfade: list[str]) -> int:
    """Den Satz `art` durch genau diese Bilder ersetzen, in dieser Reihenfolge."""
    lid = _lokalisierung()
    saetze = _saetze(lid)
    if art not in saetze:
        raise SystemExit(f"{art} gibt es nicht. Da sind: {', '.join(sorted(saetze))}")
    sid = saetze[art]
    alt = _bilder(sid)
    print(f"{art}: {len(alt)} alte Bilder, {len(pfade)} neue")
    for b in alt:
        d = api("DELETE", f"/appScreenshots/{b['id']}")
        print(f"   weg: {b['attributes'].get('fileName')}"
              f"{'' if d['ok'] else '  FEHLER ' + str(d['status'])}")
    for p in pfade:
        pfad = Path(p)
        bid = _hochladen(sid, pfad)
        print(f"   neu: {pfad.name}  {bid}")
    nach = _bilder(sid)
    offen = [b for b in nach
             if (b["attributes"].get("assetDeliveryState") or {}).get("state") != "COMPLETE"]
    print(f"{art}: jetzt {len(nach)} Bilder, davon {len(offen)} noch nicht fertig")
    return 1 if offen else 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "zeigen":
        return zeigen()
    if argv[0] == "setzen" and len(argv) >= 3:
        return setzen(argv[1], argv[2:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
