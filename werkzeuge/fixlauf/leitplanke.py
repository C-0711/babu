#!/usr/bin/env python3
"""Die Leitplanke: welcher Diff darf ohne Christoph auf die H200V?

Deterministisch und dumm mit Absicht. Ein Sprachmodell kann sich
herausreden; eine Pfadliste nicht. Wer hier anschlägt, wird nicht deployt —
Label `braucht-christoph`, fertig. Lieber zehnmal zu vorsichtig als einmal
in die Belegbox geschrieben, was niemand bestellt hat.
"""
from __future__ import annotations

import sys

# Bereich → warum er Christoph braucht. Teilstring-Abgleich auf dem Repo-Pfad.
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
}


def riskant(pfade: list[str]) -> str | None:
    """Erster Treffer mit Begründung — oder None: frei zum Deploy."""
    for pfad in pfade:
        p = pfad.lower()
        for muster, grund in RISKANT.items():
            if muster in p:
                return f"{pfad}: {grund}"
    return None


if __name__ == "__main__":
    grund = riskant(sys.argv[1:])
    if grund:
        print(f"RISKANT — {grund}")
        sys.exit(1)
    print("frei")
