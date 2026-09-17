#!/usr/bin/env python3
"""App Store Connect API — Token bauen, Verbindung testen, Aktionen fahren.

Auth: Team-Schluessel (Issuer-ID + Key-ID + .p8). Die .p8 liegt unter
~/.config/0711/asc-babu.p8 (0600, nie im Repo). JWT nach Apples Vorgabe:
ES256, 20 Minuten Gueltigkeit.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ISSUER = "c88aa4dc-b23d-4a4b-a6b7-8c51d2479b25"
KEY_ID = "85ZL8J5Y2V"
KEY_PFAD = Path.home() / ".config/0711/asc-babu.p8"
API = "https://api.appstoreconnect.apple.com/v1"


def token() -> str:
    import jwt  # PyJWT
    jetzt = int(time.time())
    payload = {"iss": ISSUER, "exp": jetzt + 20 * 60, "aud": "appstoreconnect-v1"}
    kopf = {"alg": "ES256", "kid": KEY_ID, "typ": "JWT"}
    return jwt.encode(payload, KEY_PFAD.read_text(), algorithm="ES256",
                      headers=kopf)


def api(method: str, path: str, body: dict | None = None) -> dict:
    import urllib.request
    daten = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, method=method, data=daten, headers={
        "Authorization": "Bearer " + token(),
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            roh = r.read().decode()
            return {"ok": True, "status": r.status, "daten": json.loads(roh) if roh else {}}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "fehler": e.read().decode()[:500]}


if __name__ == "__main__":
    # 1) Verbindungstest: welche Apps sieht der Schluessel?
    apps = api("GET", "/apps?limit=10")
    print("VERBINDUNG:", "ok" if apps["ok"] else f"FEHLER {apps['status']}: {apps.get('fehler','')[:200]}")
    if apps["ok"]:
        for a in apps["daten"]["data"]:
            print(f"  App: {a['attributes']['name']} ({a['attributes']['bundleId']}) id={a['id']}")
