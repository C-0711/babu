"""Auslagen der Mitarbeiterinnen — die reine Rechnung (babu Expenses D1, 04.10.2026).

Spezifikation: docs/superpowers/specs/2026-10-04-expenses-d1-design.md.

Eine Auslage ist ein normaler Beleg mit der Beiakte `review/<stamm>.auslage.json`.
Hier stehen ihre Stände und erlaubten Schritte, die Summen einer Erstattung je
Person, die Kennungen und was Bankabgleich und Kasse davon brauchen. Ohne Box,
ohne Netz, ohne Uhr — die Zeit reicht der Aufrufer herein.
"""
from __future__ import annotations

import json
import re

STAENDE = ("eingereicht", "freigegeben", "abgelehnt", "zurueckgezogen", "erstattet")
#: Diese Auslagen gehen nicht in den Stapel.
NICHT_IM_STAPEL = ("eingereicht", "abgelehnt", "zurueckgezogen")
UEBERGAENGE = {("eingereicht", "freigegeben"), ("eingereicht", "abgelehnt"),
               ("eingereicht", "zurueckgezogen"), ("freigegeben", "eingereicht"),
               ("freigegeben", "erstattet")}
GRUND_MIN = 3
_KENNUNG = re.compile(r"^E-(\d{4})-(\d{3,})$")


class AuslageFehler(ValueError):
    """Ein Schritt, den es so nicht gibt — mit einem Satz für die Antwort."""


def neu(von: str, name: str, am: str, bezahlt_mit: str = "privat") -> dict:
    return {"von": von, "name": name, "bezahlt_mit": bezahlt_mit,
            "status": "eingereicht", "eingereicht_am": am,
            "entschieden_von": None, "entschieden_am": None,
            "grund": None, "kreditor": None, "erstattung": None}


def laden(roh) -> dict | None:
    if isinstance(roh, (bytes, str)):
        try:
            roh = json.loads(roh)
        except ValueError:
            return None
    if not isinstance(roh, dict) or roh.get("status") not in STAENDE or not roh.get("von"):
        return None
    return {**neu(str(roh["von"]), str(roh.get("name") or ""),
                  str(roh.get("eingereicht_am") or "")), **roh}


def uebergang(a: dict, nach: str, *, von: str, am: str, grund=None, kreditor=None,
              erstattung=None) -> dict:
    if (a["status"], nach) not in UEBERGAENGE:
        raise AuslageFehler("Das geht bei dieser Auslage gerade nicht.")
    neu_ = dict(a, status=nach)
    if nach == "abgelehnt":
        g = " ".join(str(grund or "").split())
        if len(g) < GRUND_MIN:
            raise AuslageFehler("Schreib bitte kurz dazu, warum.")
        neu_.update(grund=g[:300], entschieden_von=von, entschieden_am=am)
    elif nach == "freigegeben":
        if not kreditor:
            raise AuslageFehler("Ohne Kreditor lässt sich nicht freigeben.")
        neu_.update(kreditor=str(kreditor), grund=None, entschieden_von=von,
                    entschieden_am=am)
    elif nach == "eingereicht":
        if a.get("erstattung"):
            raise AuslageFehler("Diese Auslage steckt schon in einer Erstattung.")
        neu_.update(entschieden_von=None, entschieden_am=None)
    elif nach == "erstattet":
        if not erstattung or a.get("erstattung") not in (None, erstattung):
            raise AuslageFehler("Diese Auslage gehört zu einer anderen Erstattung.")
        neu_["erstattung"] = erstattung
    return neu_


def reservieren(a: dict, kennung: str) -> dict:
    if a["status"] != "freigegeben" or a.get("erstattung"):
        raise AuslageFehler("Diese Auslage ist nicht frei zum Erstatten.")
    return dict(a, erstattung=kennung)


def reservierung_loesen(a: dict, kennung: str) -> dict:
    if a["status"] == "freigegeben" and a.get("erstattung") == kennung:
        return dict(a, erstattung=None)
    return a


def index_stand(a: dict) -> str | None:
    """Der Beleg-Stand im Index — nur für Auslagen, die (noch) nicht gebucht werden."""
    if a["status"] == "eingereicht":
        return "wartet"
    if a["status"] in ("abgelehnt", "zurueckgezogen"):
        return "abgelehnt"
    return None


def je_person(posten: list[dict]) -> list[dict]:
    summen: dict[str, dict] = {}
    for p in posten:
        e = summen.setdefault(str(p["kreditor"]), {"kreditor": str(p["kreditor"]),
                                                   "name": p["name"], "von": p["von"],
                                                   "summe": 0.0})
        e["summe"] = round(e["summe"] + float(p["betrag"]), 2)
    return sorted(summen.values(), key=lambda e: (e["name"], e["kreditor"]))


def naechste_kennung(vorhandene: list[str], jahr: int) -> str:
    hoechste = 0
    for k in vorhandene:
        m = _KENNUNG.match(str(k))
        if m and int(m.group(1)) == jahr:
            hoechste = max(hoechste, int(m.group(2)))
    return f"E-{jahr}-{hoechste + 1:03d}"


def verwendungszweck(name: str, kennung: str) -> str:
    return f"Auslagen {name} {kennung}"[:140]


def iban_normal(iban) -> str:
    return re.sub(r"\s+", "", str(iban or "")).upper()


def iban_gueltig(iban) -> bool:
    i = iban_normal(iban)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", i):
        return False
    if i.startswith("DE") and len(i) != 22:
        return False
    zahl = "".join(str(int(c, 36)) for c in i[4:] + i[:4])
    return int(zahl) % 97 == 1


def bar_erstattungen_im_monat(erstattungen, monat: str) -> list[dict]:
    return sorted((e for e in erstattungen
                   if e.get("art") == "bar" and e.get("status") == "ausgezahlt"
                   and str(e.get("datum") or "")[:7] == monat),
                  key=lambda e: e["kennung"])


def bar_je_monat(erstattungen) -> dict[str, float]:
    aus: dict[str, float] = {}
    for e in erstattungen:
        if e.get("art") == "bar" and e.get("status") == "ausgezahlt":
            m = str(e.get("datum") or "")[:7]
            aus[m] = round(aus.get(m, 0.0) + sum(p["summe"] for p in e["je_person"]), 2)
    return aus


def abgleich_eintraege(erstattungen) -> list[dict]:
    """Überwiesene Erstattungen als Gegenstück für den Bankabgleich — je Person."""
    aus = []
    for e in sorted(erstattungen, key=lambda x: x["kennung"]):
        if e.get("art") != "ueberweisung" or e.get("status") != "ueberwiesen":
            continue
        for p in e["je_person"]:
            aus.append({"stamm": e["kennung"], "brutto": p["summe"],
                        "datum": e.get("ueberwiesen_am") or e["datum"], "erstattung": True})
    return aus
