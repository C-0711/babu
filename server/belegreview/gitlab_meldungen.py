"""GitLab ist die eine Wahrheit über Ninas Meldungen — hier wohnt der Draht dorthin.

Drei Aufgaben, eine Datei: Meldung → Issue formen, mit der GitLab-API auf der
eigenen Maschine sprechen (127.0.0.1:8929, NIE über Cloudflare), und puffern,
wenn GitLab gerade nicht da ist. Die Zusage bleibt dieselbe wie zu Fixit-Zeiten:
eine Meldung geht nie verloren, und Nina liest immer sofort „angekommen".

Labels sind die Zustandsmaschine (Spec 2026-08-26-nina-meldeschleife):
    offen ohne Prozess-Label = gemeldet · in-arbeit · zur-abnahme = bitte prüfen
    braucht-christoph zeigt Nina schlicht „in Arbeit" · geschlossen = erledigt
"""
from __future__ import annotations

import rueckmeldung as rm

ART_LABEL = {"fehler": "bug", "wunsch": "wunsch"}


def als_issue(m: rm.Meldung) -> dict:
    """Die Nutzlast für POST /projects/:id/issues — Ninas Worte, unsere Labels."""
    if not m.text.strip():
        raise ValueError("leere Meldung")
    return {
        "title": rm.titel_aus(m.text),
        "description": rm.koerper_aus(m),
        "labels": f"{ART_LABEL.get(m.art, 'bug')},von-nina",
    }


def status_von(issue: dict) -> str:
    """Was Nina sieht. `braucht-christoph` ist für sie „in Arbeit" —
    dass intern Christoph dran muss, ist nicht ihre Baustelle."""
    if issue.get("state") == "closed":
        return "erledigt"
    labels = set(issue.get("labels") or [])
    if "zur-abnahme" in labels:
        return "bitte-pruefen"
    if labels & {"in-arbeit", "braucht-christoph"}:
        return "in-arbeit"
    return "gemeldet"
