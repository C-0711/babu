"""Was eine Mitarbeiterin aufrufen darf — eine Positivliste (seit 04.10.2026).

Gesamtprüfung babu Expenses D1, Befund C1: bis dahin galt für Mitarbeiterinnen
„alles, was nicht ausdrücklich gesperrt ist“. Mit nur „darf Auslagen“ sah eine
Mitarbeiterin Monatszahlen, Ablage, Auszüge, Kundinnen, Rechnungen und konnte
den Chat über alle Belege befragen. Jetzt gilt umgekehrt: nur, was hier steht —
je Recht, das die Inhaberin im Team vergibt. `babu_web._api_wache` fragt hier
für jede Anfrage einer Mitarbeiterin; alles andere gehört der Inhaberin.

Reine Regel ohne Datenbank: die Rechte reicht der Aufrufer herein.
"""
from __future__ import annotations

import re

#: Jede Mitarbeiterin: ihr Konto, ihre Meldungen, ihre Auslagen, ihr Gerät.
IMMER: list[tuple[str, str]] = [
    ("GET", r"/api/ich"),
    ("POST", r"/api/abmelden"),
    ("POST", r"/api/passwort"),
    ("GET", r"/api/rueckmeldungen"),
    ("POST", r"/api/rueckmeldung"),
    ("POST", r"/api/rueckmeldungen/[^/]+/(beanstanden|freigeben)"),
    ("GET", r"/api/auslagen/meine(/[^/]+(/bild)?)?"),
    ("POST", r"/api/auslagen/[^/]+/zurueckziehen"),
    ("POST", r"/api/auslagen/(konto|nachrichten)"),
    ("POST", r"/api/push/geraet"),
]

#: Was ein Recht zusätzlich öffnet.
JE_RECHT: dict[str, list[tuple[str, str]]] = {
    # Eigenes Geld: einreichen. Gesehen werden nur die eigenen Auslagen (IMMER).
    "auslagen": [("POST", r"/api/aufnahme"), ("POST", r"/api/buchung/einschaetzung")],
    # Belege des Betriebs fotografieren — und die Belegliste dazu.
    "belege": [("POST", r"/api/aufnahme"), ("POST", r"/api/hochladen"), ("POST", r"/ablage"),
               ("POST", r"/api/buchung/einschaetzung"), ("GET", r"/api/belege"),
               ("GET", r"/api/beleg/[^/]+(/bild)?")],
    # Kasse und Termine führen.
    "kasse": [("GET", r"/api/kassenbuch/[^/]+"), ("POST", r"/api/kassenbuch"),
              ("GET", r"/api/kasse/vorschlag"), ("GET", r"/api/termine"),
              ("POST", r"/api/termine(/vorschlag)?"),
              ("POST", r"/api/termin/[^/]+/(abrechnen|absagen|bestaetigen)")],
}


def erlaubt(methode: str, pfad: str, rechte: dict) -> bool:
    m = methode.upper()
    if m == "HEAD":
        m = "GET"
    regeln = list(IMMER)
    for recht, liste in JE_RECHT.items():
        if rechte.get(recht):
            regeln += liste
    return any(m == rm and re.fullmatch(rp, pfad) for rm, rp in regeln)
