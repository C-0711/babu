#!/usr/bin/env python3
"""Die Leitplanke: welcher Diff darf ohne Christoph auf die H200V?

Deterministisch und dumm mit Absicht. Ein Sprachmodell kann sich
herausreden; eine Pfadliste nicht. Wer hier anschlägt, wird nicht deployt —
Label `braucht-christoph`, fertig. Lieber zehnmal zu vorsichtig als einmal
in die Belegbox geschrieben, was niemand bestellt hat.
"""
from __future__ import annotations

import sys

# Bereich → warum er Christoph braucht. Teilstring-Abgleich auf dem Repo-Pfad
# UND auf den geänderten Diff-Zeilen (manche riskanten Stellen — Auth, Kasse-
# Routen, Schema-CREATEs — liegen in Dateien, deren Name harmlos aussieht,
# z. B. babu_web.py).
RISKANT = {
    "boxschreiber": "schreibt in die Belegbox",
    "kontierung": "Geld-/Steuerlogik",
    "geld.py": "Geld-/Steuerlogik",
    "extf": "DATEV/EXTF-Export",
    "kontenrahmen": "Kontenkatalog",
    "kasse": "Kassenlogik (§ 146a AO)",
    "lohn": "Lohn/Sozialversicherung",
    "migration": "Schema von portal.db",
    "anmelden": "Auth/Session",
    "app_schluessel": "Auth/Session",
    "_box_wache": "schreibt in die Belegbox",
    "box_mitglied": "schreibt in die Belegbox",
    "create table": "Schema von portal.db",
    "alter table": "Schema von portal.db",
}


def riskant(pfade: list[str], diff_text: str = "") -> str | None:
    """Erster Treffer mit Begründung — oder None: frei zum Deploy.

    Prüft zuerst die Pfadliste (Dateiname), danach — falls übergeben — den
    Diff-Text selbst: nur Zeilen, die mit `+` oder `-` beginnen (nicht die
    Dateikopfzeilen `+++`/`---`), case-insensitiv gegen dieselben Muster.
    """
    for pfad in pfade:
        p = pfad.lower()
        for muster, grund in RISKANT.items():
            if muster in p:
                return f"{pfad}: {grund}"

    aktuelle_datei = "?"
    for zeile in diff_text.splitlines():
        if zeile.startswith("+++ ") or zeile.startswith("--- "):
            datei = zeile[4:].split("\t")[0]
            if datei.startswith(("a/", "b/")):
                datei = datei[2:]
            aktuelle_datei = datei
            continue
        if zeile[:1] in ("+", "-"):
            z = zeile.lower()
            for muster, grund in RISKANT.items():
                if muster in z:
                    return f"{aktuelle_datei}: {grund} (Diff-Zeile: {muster})"
    return None


if __name__ == "__main__":
    diff_text = "" if sys.stdin.isatty() else sys.stdin.read()
    grund = riskant(sys.argv[1:], diff_text)
    if grund:
        print(f"RISKANT — {grund}")
        sys.exit(1)
    print("frei")
