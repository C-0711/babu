#!/usr/bin/env python3
"""DATEV-Referenzdokumente ins Wissen-Fach von babu hochladen — Mac-seitig.

Iteriert genau zwei Orte unter `~/JennyfromtheBlock/datev/` (kein
rekursiver Home-Scan, andere Unterordner wie `kontenrahmen_2026/` bleiben
unangetastet):

    <ordner>/*.pdf                die DATEV-Kontenrahmen-PDFs direkt im Ordner
    <ordner>/hilfe-center/*.md    die Hilfe-Center-Auszüge

und postet jede Datei einzeln per `POST <origin>/api/wissen` — derselbe
Bearer-Auth-Weg wie die App (`babu_web.angemeldet`: Cookie ODER Bearer),
kein neuer Server-Code für diesen CLI-Zugang nötig.

PAT-Beschaffung: Umgebungsvariable `BABU_PAT`, sonst macOS-Keychain
(`security find-generic-password`). Der Wert wird NIE ausgegeben oder
geloggt — nur seine Länge und ob er gefunden wurde. Zum Ablegen einmalig:

    security add-generic-password -a "$USER" -s babu-pat -w
    (fragt interaktiv nach dem Wert, landet nicht in der Shell-History)

Aufruf:
    python3 werkzeuge/wissen-import/datev_ordner_hochladen.py --probe
    python3 werkzeuge/wissen-import/datev_ordner_hochladen.py
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import requests

# Werte, die /api/wissen laut Vertrag versteht (Planauftrag Phase 2.1) —
# nur zur Selbstkontrolle hier, der Server ist die eigentliche Wahrheit.
THEMEN = ("kontenrahmen", "steuerschluessel", "buchungsstapel", "afa",
          "umsatzsteuer", "lohn", "jahresabschluss", "sonstiges")

# Eindeutig benennbare Dateien fest zuordnen, damit die Server-Auto-
# erkennung (die nur die ersten Seiten liest) nicht raten muss. Substring-
# Suche statt "startswith", weil das Hilfe-Center-Exportformat ein "Dok-"
# voranstellt (z. B. "Dok-0907048_Steuerschluessel-Tabelle_2026.md").
BEKANNTE_DATEIEN = {
    "0907048": "steuerschluessel",
    "0907108": "kontenrahmen",
}

KEYCHAIN_SERVICE = "babu-pat"

STANDARD_ORDNER = Path.home() / "JennyfromtheBlock" / "datev"
STANDARD_ORIGIN = "https://babu.0711.io"


def thema_aus_dateiname(name: str) -> str | None:
    """Feste Zuordnung für bekannte Dokumente — sonst None, dann
    entscheidet der Server selbst (liest die ersten Seiten, siehe
    Planauftrag 3.2 Schritt 5)."""
    for schluessel, thema in BEKANNTE_DATEIEN.items():
        if schluessel in name:
            return thema
    if name.startswith("SKR04_"):
        return "kontenrahmen"
    return None


def dateien_sammeln(ordner: Path) -> list[Path]:
    """Nur `*.pdf` direkt im Ordner und `*.md` unter `hilfe-center/` — kein
    rekursiver Scan, kein Antasten anderer Unterordner (z. B. die
    branchenspezifischen Kontenrahmen-Varianten unter `kontenrahmen_2026/`,
    die nicht Teil dieses Imports sind)."""
    pdfs = sorted(ordner.glob("*.pdf"))
    mds = sorted((ordner / "hilfe-center").glob("*.md"))
    return pdfs + mds


# ── PAT — Umgebungsvariable oder Keychain, nie geloggt ────────────────────

def _pat_aus_keychain(service: str, account: str) -> str | None:
    if not account:
        return None
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-a", account, "-s", service, "-w"],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    wert = r.stdout.strip()
    return wert or None


def pat_holen(*, service: str = KEYCHAIN_SERVICE, account: str | None = None) -> str | None:
    """`BABU_PAT` zuerst, sonst Keychain. Gibt den Wert nie preis — Aufrufer
    dürfen ihn nur weiterreichen (Header), niemals drucken oder loggen."""
    umgebung = os.environ.get("BABU_PAT")
    if umgebung:
        return umgebung
    account = account if account is not None else os.environ.get("USER", "")
    return _pat_aus_keychain(service, account)


# ── Upload ─────────────────────────────────────────────────────────────

def hochladen(pfad: Path, *, origin: str, pat: str, session=None) -> dict:
    session = session or requests
    thema = thema_aus_dateiname(pfad.name)
    params = {"name": pfad.name, "titel": pfad.stem}
    if thema:
        params["thema"] = thema
    content_type = "application/pdf" if pfad.suffix.lower() == ".pdf" else "text/markdown"
    r = session.post(f"{origin.rstrip('/')}/api/wissen", params=params,
                     data=pfad.read_bytes(),
                     headers={"Authorization": f"Bearer {pat}",
                              "Content-Type": content_type},
                     timeout=120)
    r.raise_for_status()
    return r.json()


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ordner", default=str(STANDARD_ORDNER),
                  help=f"Default {STANDARD_ORDNER}")
    p.add_argument("--origin", default=STANDARD_ORIGIN)
    p.add_argument("--probe", action="store_true",
                  help="nur auflisten, nichts hochladen (kein PAT nötig)")
    p.add_argument("--keychain-service", default=KEYCHAIN_SERVICE)
    p.add_argument("--keychain-account", default=None)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    ordner = Path(args.ordner).expanduser()
    dateien = dateien_sammeln(ordner)
    if not dateien:
        print(f"Nichts gefunden unter {ordner} (*.pdf, hilfe-center/*.md).")
        return 1

    for pfad in dateien:
        thema = thema_aus_dateiname(pfad.name) or "(Server erkennt automatisch)"
        groesse_kb = pfad.stat().st_size / 1024
        print(f"  {pfad.relative_to(ordner)}  {groesse_kb:.0f} KB  thema={thema}")

    if args.probe:
        print(f"{len(dateien)} Datei(en) — Probe, nichts hochgeladen.")
        return 0

    pat = pat_holen(service=args.keychain_service, account=args.keychain_account)
    if not pat:
        print(f"Kein PAT gefunden (Umgebungsvariable BABU_PAT oder Keychain "
              f"'{args.keychain_service}') — Abbruch. Einmalig ablegen:\n"
              f"  security add-generic-password -a \"$USER\" -s "
              f"{args.keychain_service} -w")
        return 1
    print(f"PAT gefunden ({len(pat)} Zeichen) — der Wert selbst wird nie ausgegeben.")

    ok = fehler = 0
    for pfad in dateien:
        try:
            antwort = hochladen(pfad, origin=args.origin, pat=pat)
        except Exception as exc:  # noqa: BLE001
            fehler += 1
            print(f"  FEHLER {pfad.name}: {exc}")
            continue
        if antwort.get("ok"):
            ok += 1
            print(f"  OK {pfad.name} -> {antwort.get('pfad')} "
                  f"(thema={antwort.get('thema')})")
        else:
            fehler += 1
            print(f"  FEHLER {pfad.name}: {antwort}")
    print(f"{ok} hochgeladen, {fehler} Fehler von {len(dateien)}.")
    return 0 if not fehler else 1


if __name__ == "__main__":
    sys.exit(main())
