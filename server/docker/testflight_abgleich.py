#!/usr/bin/env python3
"""Abgleich Warteliste → TestFlight, für den Host-Cron auf der H200V.

Was passiert hier (idempotent, jede Minute gefahrlos):

1. Wartelisten-Zeilen mit apple_id und app_status='eingetragen' lesen
   (babu-Postgres, Container babu-postgres, Port 55432).
2. Apple-ID als Team-Nutzer einladen (Rolle Developer, ohne Provisioning) —
   409 (gibt es schon) ist ein Erfolg.
3. Sobald die Apple-ID ein aktiver Team-Nutzer ist (Einladung angenommen):
   in die Pilot-Gruppe aufnehmen — 409 wieder ein Erfolg. Apple schickt
   damit automatisch die TestFlight-Einladung.
4. app_status fortschreiben: eingeladen (Team-Einladung raus) / drin
   (in der Gruppe, TestFlight-Einladung ist raus).

Die .p8 liegt auf dem Mac (~/.config/0711/asc-babu.p8). Auf der H200V gilt:
mac-MacSync — dieses Skript erwartet den Schluessel unter
~/.config/0711/asc-babu.p8 AUF DEM HOST, per Cron ausgefuehrt. Er wird von
Hand einmalig kopiert (siehe docs/dev-lane-mybabu-2026-09-16.md, Abschnitt
TestFlight) — nie ins Repo, nie in den Container.

Aufruf:  python3 testflight_abgleich.py          (Arbeit)
         python3 testflight_abgleich.py --probe  (nur anzeigen)
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# psycopg und jwt laufen auf dem H200V-Host (pip3 install --user psycopg
# PyJWT) — im Mac-Editor sind sie nicht aufgeloest, das ist bekannt und okay;
# --probe auf dem Host zeigt, ob alles steht.
ISSUER = "c88aa4dc-b23d-4a4b-a6b7-8c51d2479b25"
KEY_ID = "85ZL8J5Y2V"
KEY_PFAD = Path.home() / ".config/0711/asc-babu.p8"
API = "https://api.appstoreconnect.apple.com/v1"
APP = "6811956687"          # babu Belege
GRUPPE = "88ebaf15-1cd5-41c1-a317-53e486b094e2"  # Pilot (intern)

DB = dict(host="127.0.0.1", port=55432, dbname="babu", user="babu")


def _token() -> str:
    import jwt  # PyJWT — auf dem Host: pip3 install --user PyJWT
    import time
    jetzt = int(time.time())
    return jwt.encode({"iss": ISSUER, "exp": jetzt + 20 * 60,
                       "aud": "appstoreconnect-v1"},
                      KEY_PFAD.read_text(), algorithm="ES256",
                      headers={"alg": "ES256", "kid": KEY_ID, "typ": "JWT"})


def api(method: str, path: str, body: dict | None = None):
    daten = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, method=method, data=daten, headers={
        "Authorization": "Bearer " + _token(),
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            roh = r.read().decode()
            return r.status, json.loads(roh) if roh else {}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def db(frage: str, werte: tuple = ()) -> list[tuple]:
    import psycopg
    with psycopg.connect(host=DB["host"], port=DB["port"],
                         dbname=DB["dbname"], user=DB["user"],
                         password=(Path.home() / "babu-web/.pg_passwort"
                                   ).read_text().strip()) as c:
        return c.execute(frage, werte).fetchall()


def db_set(email: str, app_status: str) -> None:
    import psycopg
    with psycopg.connect(host=DB["host"], port=DB["port"],
                         dbname=DB["dbname"], user=DB["user"],
                         password=(Path.home() / "babu-web/.pg_passwort"
                                   ).read_text().strip()) as c:
        c.execute("UPDATE warteliste SET app_status=%s WHERE email=%s",
                  (app_status, email))


def team_nutzer() -> dict[str, str]:
    """Apple-ID → Status des Team-Kontos ('aktiv' / 'eingeladen' / '-')."""
    status, d = api("GET", "/users?limit=100")
    aktiv = {u["attributes"]["username"].lower(): "aktiv"
             for u in d.get("data", [])}
    status, d = api("GET", "/userInvitations?limit=100")
    for u in d.get("data", []):
        aktiv.setdefault(u["attributes"]["email"].lower(), "eingeladen")
    return aktiv


def main(probe: bool) -> None:
    zeilen = db("""SELECT email, apple_id, app_status FROM warteliste
                   WHERE apple_id IS NOT NULL AND app_status = 'eingetragen'""")
    if not zeilen:
        print("nichts zu tun")
        return
    nutzer = team_nutzer()
    for email, apple, _status in zeilen:
        stand = nutzer.get(apple, "-")
        print(f"{email}: apple={apple} team={stand}")
        if probe:
            continue
        if stand == "-":
            code, antwort = api("POST", "/userInvitations", {
                "data": {"type": "userInvitations",
                         "attributes": {
                             "firstName": (email.split("@")[0])[:40],
                             "lastName": "", "email": apple,
                             "roles": ["DEVELOPER"],
                             "allAppsVisible": True,
                             "provisioningAllowed": False}}})
            if code in (201, 409):
                db_set(email, "eingeladen")
                print(f"  → Team-Einladung an {apple} "
                      f"({'neu' if code == 201 else 'gab es schon'})")
            else:
                print(f"  → FEHLER {code}: {json.dumps(antwort)[:200]}")
        elif stand == "aktiv":
            code, antwort = api("POST", "/betaTesters", {
                "data": {"type": "betaTesters",
                         "attributes": {"email": apple},
                         "relationships": {"betaGroups": {"data": [
                             {"type": "betaGroups", "id": GRUPPE}]}}}})
            if code in (201, 409):
                db_set(email, "drin")
                print(f"  → in Pilot-Gruppe aufgenommen "
                      f"({'neu' if code == 201 else 'war schon drin'}) — "
                      f"TestFlight-Einladung geht raus")
            else:
                print(f"  → FEHLER {code}: {json.dumps(antwort)[:200]}")


if __name__ == "__main__":
    main("--probe" in sys.argv)
