#!/usr/bin/env python3
"""Die Speicherstufen in App Store Connect — anlegen, nachsehen, nachziehen.

Am 11.10.2026 damit angelegt: Gruppe „babu Speicher" (22463529) und die drei
Abos aus `server/belegreview/paket.py`. **Die API kann das vollständig** —
die Annahme, Abos ließen sich nur über die Weboberfläche anlegen, war falsch.

    asc_abos.py zeigen            # was dort steht (ändert nichts)
    asc_abos.py anlegen           # Gruppe und Abos, überspringt Vorhandenes
    asc_abos.py preise            # Preise für alle Gebiete setzen
    asc_abos.py texte             # Namen und Beschreibungen (de-DE, en-US)
    asc_abos.py bild <datei.png>  # Prüf-Screenshot an alle drei hängen
    asc_abos.py notiz             # Prüfnotiz an alle drei

Jeder Schritt ist für sich wiederholbar: Vorhandenes wird nicht doppelt
angelegt, und nichts wird eingereicht — das Einreichen bleibt Handarbeit.

Apples Grenzen, die beim ersten Lauf zugeschlagen haben:
  * Beschreibung höchstens **55** Zeichen, Name höchstens 30.
  * Ein Preis geht erst, wenn die **Verfügbarkeit** steht — sonst
    `UNSUPPORTED_TERRITORY`.
  * Der Screenshot braucht drei Schritte (anmelden, hochladen, mit MD5
    bestätigen); ohne den dritten bleibt er ein Fragment.
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asc_api as a  # noqa: E402

APP = "6811956687"            # babu Belege
GRUPPE_NAME = "babu Speicher"
GEBIETE = ["DEU", "AUT", "CHE"]      # wie die App selbst

#: Die Stufen — Quelle ist `paket.STUFEN`, hier nur gespiegelt, damit das
#: Werkzeug ohne den Server-Code läuft. `tests/test_apple_produkte.py` hält
#: die Kennungen im Repo zusammen.
STUFEN = [
    ("babu.speicher.1gb",   "babu Speicher 1 GB",   1,  9.99,
     ("1 GB Speicher", "Platz für rund 2.000 Belege"),
     ("1 GB storage",  "Room for about 2,000 documents")),
    ("babu.speicher.5gb",   "babu Speicher 5 GB",   2, 19.99,
     ("5 GB Speicher", "Platz für rund 9.500 Belege"),
     ("5 GB storage",  "Room for about 9,500 documents")),
    ("babu.speicher.100gb", "babu Speicher 100 GB", 3, 99.00,
     ("100 GB Speicher", "Platz für rund 190.000 Belege"),
     ("100 GB storage",  "Room for about 190,000 documents")),
]

NOTIZ = ("The three tiers differ ONLY in storage space — every babu feature "
         "is included in all of them. To reach this screen: open the app, "
         "tap \"Los geht's\" (no account, no e-mail, no password needed) and "
         "capture 10 documents; after the tenth the storage picker appears. "
         "It can also be opened any time from the storage bar on the capture "
         "screen. babu is a bookkeeping app for small businesses in Germany, "
         "Austria and Switzerland; the subscription pays for the document "
         "storage on our own servers in Germany.")


def gruppe() -> str | None:
    r = a.api("GET", f"/apps/{APP}/subscriptionGroups?limit=20")
    for g in r["daten"]["data"] if r["ok"] else []:
        if g["attributes"]["referenceName"] == GRUPPE_NAME:
            return g["id"]
    return None


def abos() -> dict[str, str]:
    """Produkt-Kennung → interne Nummer."""
    g = gruppe()
    if not g:
        return {}
    r = a.api("GET", f"/subscriptionGroups/{g}/subscriptions?limit=50")
    return {s["attributes"]["productId"]: s["id"]
            for s in (r["daten"]["data"] if r["ok"] else [])}


def _punkte(sub: str, gebiet: str) -> dict[float, str]:
    aus, pfad = {}, f"/subscriptions/{sub}/pricePoints?filter[territory]={gebiet}&limit=200"
    while pfad:
        r = a.api("GET", pfad)
        if not r["ok"]:
            return aus
        for p in r["daten"]["data"]:
            aus[float(p["attributes"]["customerPrice"])] = p["id"]
        nxt = r["daten"].get("links", {}).get("next")
        pfad = nxt.split("/v1", 1)[1] if nxt else None
    return aus


def anlegen() -> None:
    g = gruppe()
    if g:
        print(f"Gruppe steht schon: {g}")
    else:
        r = a.api("POST", "/subscriptionGroups", {"data": {
            "type": "subscriptionGroups",
            "attributes": {"referenceName": GRUPPE_NAME},
            "relationships": {"app": {"data": {"type": "apps", "id": APP}}}}})
        if not r["ok"]:
            print("Gruppe:", r["fehler"][:300]); return
        g = r["daten"]["data"]["id"]
        print("Gruppe angelegt:", g)
        for locale, name in (("de-DE", "Dein Platz bei babu"),
                             ("en-US", "Your babu storage")):
            a.api("POST", "/subscriptionGroupLocalizations", {"data": {
                "type": "subscriptionGroupLocalizations",
                "attributes": {"name": name, "locale": locale},
                "relationships": {"subscriptionGroup": {"data": {
                    "type": "subscriptionGroups", "id": g}}}}})
    da = abos()
    for pid, name, ebene, _preis, _de, _en in STUFEN:
        if pid in da:
            print(f"  {pid:22s} steht schon ({da[pid]})"); continue
        r = a.api("POST", "/subscriptions", {"data": {
            "type": "subscriptions",
            "attributes": {"name": name, "productId": pid,
                           "subscriptionPeriod": "ONE_MONTH",
                           "familySharable": False, "groupLevel": ebene},
            "relationships": {"group": {"data": {
                "type": "subscriptionGroups", "id": g}}}}})
        print(f"  {pid:22s}", "angelegt " + r["daten"]["data"]["id"]
              if r["ok"] else r["fehler"][:260])
    # Verfügbarkeit MUSS vor dem Preis stehen.
    for pid, sub in abos().items():
        av = a.api("GET", f"/subscriptions/{sub}/subscriptionAvailability")
        if av["ok"] and av["daten"].get("data"):
            continue
        a.api("POST", "/subscriptionAvailabilities", {"data": {
            "type": "subscriptionAvailabilities",
            "attributes": {"availableInNewTerritories": False},
            "relationships": {
                "subscription": {"data": {"type": "subscriptions", "id": sub}},
                "availableTerritories": {"data": [
                    {"type": "territories", "id": t} for t in GEBIETE]}}}})
        print(f"  {pid:22s} Gebiete gesetzt: {', '.join(GEBIETE)}")


def preise() -> None:
    da = abos()
    for pid, _n, _e, preis, _de, _en in STUFEN:
        sub = da.get(pid)
        if not sub:
            print(f"{pid}: gibt es nicht"); continue
        for gebiet in GEBIETE:
            pp = _punkte(sub, gebiet)
            if not pp:
                print(f"  {pid:22s} {gebiet}: kein Raster"); continue
            # Dieselbe Zahl, wenn Apple sie führt; sonst die nächstgelegene.
            ziel = preis if preis in pp else min(pp, key=lambda x: abs(x - preis))
            r = a.api("POST", "/subscriptionPrices", {"data": {
                "type": "subscriptionPrices",
                "attributes": {"preserveCurrentPrice": False},
                "relationships": {
                    "subscription": {"data": {"type": "subscriptions", "id": sub}},
                    "subscriptionPricePoint": {"data": {
                        "type": "subscriptionPricePoints", "id": pp[ziel]}}}}})
            merk = "" if abs(ziel - preis) < 0.001 else f"  (statt {preis:.2f})"
            print(f"  {pid:22s} {gebiet} {ziel:>7.2f}{merk}",
                  "ok" if r["ok"] else r["fehler"][:200])


def texte() -> None:
    da = abos()
    for pid, _n, _e, _p, de, en in STUFEN:
        sub = da.get(pid)
        if not sub:
            continue
        for locale, (name, beschr) in (("de-DE", de), ("en-US", en)):
            if len(name) > 30 or len(beschr) > 55:
                print(f"  {pid} {locale}: zu lang — Apple nimmt 30/55"); continue
            r = a.api("POST", "/subscriptionLocalizations", {"data": {
                "type": "subscriptionLocalizations",
                "attributes": {"name": name, "description": beschr,
                               "locale": locale},
                "relationships": {"subscription": {"data": {
                    "type": "subscriptions", "id": sub}}}}})
            print(f"  {pid:22s} {locale}", "ok" if r["ok"] else r["fehler"][:200])


def bild(datei: Path) -> None:
    roh = datei.read_bytes()
    for pid, sub in abos().items():
        r = a.api("POST", "/subscriptionAppStoreReviewScreenshots", {"data": {
            "type": "subscriptionAppStoreReviewScreenshots",
            "attributes": {"fileName": datei.name, "fileSize": len(roh)},
            "relationships": {"subscription": {"data": {
                "type": "subscriptions", "id": sub}}}}})
        if not r["ok"]:
            print(f"  {pid:22s} anmelden:", r["fehler"][:200]); continue
        d = r["daten"]["data"]
        for op in d["attributes"]["uploadOperations"]:
            req = urllib.request.Request(
                op["url"], method=op["method"],
                data=roh[op["offset"]:op["offset"] + op["length"]])
            for h in op["requestHeaders"]:
                req.add_header(h["name"], h["value"])
            urllib.request.urlopen(req).read()
        q = a.api("PATCH", f"/subscriptionAppStoreReviewScreenshots/{d['id']}",
                  {"data": {"type": "subscriptionAppStoreReviewScreenshots",
                            "id": d["id"],
                            "attributes": {"uploaded": True,
                                           "sourceFileChecksum":
                                               hashlib.md5(roh).hexdigest()}}})
        print(f"  {pid:22s}", q["daten"]["data"]["attributes"]["assetDeliveryState"]
              if q["ok"] else q["fehler"][:200])


def notiz() -> None:
    for pid, sub in abos().items():
        r = a.api("PATCH", f"/subscriptions/{sub}", {"data": {
            "type": "subscriptions", "id": sub,
            "attributes": {"reviewNote": NOTIZ}}})
        print(f"  {pid:22s}", "ok" if r["ok"] else r["fehler"][:200])


def zeigen() -> None:
    g = gruppe()
    print(f"Gruppe: {g or '— gibt es nicht'}")
    for pid, sub in abos().items():
        s = a.api("GET", f"/subscriptions/{sub}")["daten"]["data"]["attributes"]
        pr = a.api("GET", f"/subscriptions/{sub}/prices"
                   "?include=territory,subscriptionPricePoint&limit=50")
        punkte = {i["id"]: i["attributes"]["customerPrice"]
                  for i in pr["daten"].get("included", [])
                  if i["type"] == "subscriptionPricePoints"}
        zeilen = []
        for p in pr["daten"]["data"] if pr["ok"] else []:
            t = (p["relationships"].get("territory") or {}).get("data")
            pp = (p["relationships"].get("subscriptionPricePoint") or {}).get("data")
            zeilen.append(f"{t['id'] if t else '?'} {punkte.get(pp['id'] if pp else '', '?')}")
        loc = a.api("GET", f"/subscriptions/{sub}/subscriptionLocalizations?limit=10")
        sprachen = [x["attributes"]["locale"] for x in loc["daten"]["data"]] if loc["ok"] else []
        bild_da = bool((a.api("GET", f"/subscriptions/{sub}/appStoreReviewScreenshot")
                        ["daten"] or {}).get("data"))
        print(f"  {pid:22s} {s['state']:18s} {s['subscriptionPeriod']}")
        print(f"      Preise: {', '.join(zeilen) or '—'}")
        print(f"      Texte: {', '.join(sprachen) or '—'} · Prüfbild: "
              f"{'ja' if bild_da else 'NEIN'} · Notiz: "
              f"{'ja' if s.get('reviewNote') else 'NEIN'}")


if __name__ == "__main__":
    was = sys.argv[1] if len(sys.argv) > 1 else "zeigen"
    if was == "bild":
        bild(Path(sys.argv[2]))
    elif was in ("zeigen", "anlegen", "preise", "texte", "notiz"):
        globals()[was]()
    else:
        print(__doc__)
        sys.exit(2)
