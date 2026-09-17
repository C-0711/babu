#!/usr/bin/env python3
"""ASC-Aktion: TestFlight-Gruppen und Build-Status von babu Belege anzeigen,
Tester in eine Gruppe aufnehmen (interne Tester muessen Team-Nutzer sein)."""
from __future__ import annotations

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from asc_api import api  # noqa: E402

APP = "6811956687"  # babu Belege


def _name(beziehung: dict, daten: list[dict]) -> str:
    for d in daten or []:
        if d["id"] == beziehung["data"]["id"]:
            a = d.get("attributes", {})
            return a.get("firstName", "") + " " + a.get("lastName", "")
    return "?"


def gruppen():
    r = api("GET", f"/apps/{APP}/betaGroups?limit=20")
    if not r["ok"]:
        print("FEHLER", r["status"], r.get("fehler", "")[:300]); return {}
    tester = r["daten"].get("included", [])
    gefunden = {}
    for g in r["daten"]["data"]:
        a = g["attributes"]
        print(f"Gruppe: {a['name']} ({'intern' if a['isInternalGroup'] else 'extern'}) "
              f"id={g['id']}")
        for t in (g.get("relationships", {}).get("betaTesters", {}).get("data", []) or []):
            print(f"   Tester: {t['id']}")
        gefunden[a["name"]] = g["id"]
    return gefunden


def builds():
    r = api("GET", f"/apps/{APP}/builds?limit=10")
    if not r["ok"]:
        print("Builds FEHLER", r["status"]); return
    for b in r["daten"]["data"]:
        a = b["attributes"]
        ver = a.get("version") or ""
        proc = a.get("processing") if isinstance(a.get("processing"), bool) else a.get("uploaded")
        print(f"  Build {a.get('versionAttribute') or ''}{ver} "
              f"verarbeitet={a.get('processed') or a.get('notProcessed') or '?'} "
              f"verarbeitung={a.get('processing') or '?'} id={b['id']}")


def tester_hinzu(gruppen_id: str, email: str):
    # betaTesters anlegen: interner Tester braucht das Apple-ID-Konto
    body = {"data": {"type": "betaTesters",
                     "attributes": {"email": email},
                     "relationships": {
                         "betaGroups": {"data": [{"type": "betaGroups", "id": gruppen_id}]}}}}
    r = api("POST", "/betaTesters", body)
    if r["ok"]:
        print("TESTER IN GRUPPE:", email)
    else:
        print("FEHLER", r["status"], r.get("fehler", "")[:600])


if __name__ == "__main__":
    g = gruppen()
    print()
    builds()
    if len(sys.argv) == 4 and sys.argv[1] == "add":
        gid = g.get(sys.argv[2])
        if gid:
            tester_hinzu(gid, sys.argv[3])
        else:
            print("Gruppe nicht gefunden:", sys.argv[2])
