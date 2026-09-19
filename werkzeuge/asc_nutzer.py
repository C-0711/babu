#!/usr/bin/env python3
"""ASC-Aktion: Nutzer einladen (Developer-Rolle) und Bestand anzeigen.

Aufruf:
  python3 asc_nutzer.py list                 — Nutzer des Teams anzeigen
  python3 asc_nutzer.py invite <email> <vorname> <nachname>
                                            — Einladung als Developer senden
"""
from __future__ import annotations

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from asc_api import api  # noqa: E402

ROLLE_DEVELOPER = "roles=DEVELOPER"


def _rollen_als_attribute() -> list[dict]:
    return [{"type": "roles", "id": "DEVELOPER"}]


def liste():
    r = api("GET", "/users?limit=50&include=visibleApps")
    if not r["ok"]:
        print("FEHLER", r["status"], r.get("fehler", "")[:300]); return
    for u in r["daten"]["data"]:
        a = u["attributes"]
        print(f"  {a['firstName'] or '?'} {a['lastName'] or '?'} <{a['username']}> "
              f"Rolle(n)={[x for x in (a.get('roles') or [])]} "
              f"Status={a.get('sessionState') or a.get('activated')}")


def einladen(email: str, vorname: str, nachname: str):
    # Einladungen laufen ueber /userInvitations
    # nachname ist Pflicht und darf nur Buchstaben — leer oder mit
    # Sonderzeichen lehnt Apple mit 409 ENTITY_ERROR.ATTRIBUTE ab, und ein
    # 409 ist kein Erfolg (gemessen 19.09. an info@supremebeauty.de).
    nachname = (nachname or "").strip() or "Kunde"
    body = {
        "data": {
            "type": "userInvitations",
            "attributes": {
                "firstName": vorname,
                "lastName": nachname,
                "email": email,
                "roles": ["DEVELOPER"],
                "allAppsVisible": True,
                # provisioningAllowed (Zertifikate/Profile) darf nur Admin —
                # fuer einen TestFlight-Tester ausdruecklich falsch.
                "provisioningAllowed": False,
            }
        }
    }
    r = api("POST", "/userInvitations", body)
    import json as _json
    if r["ok"]:
        d = r["daten"]["data"]
        print(f"EINGELADEN: {email} (Einladung {d['id']}, Rollen {d['attributes']['roles']})")
    elif (r["status"] == 409
          and "VOLUME" in _json.dumps(r.get("daten", {}))):
        print(f"SCHON EINGELADEN: {email}")
    else:
        print("FEHLER", r["status"])
        print(r.get("fehler", "")[:600])


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "list":
        liste()
    elif len(sys.argv) == 5 and sys.argv[1] == "invite":
        einladen(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print(__doc__)
