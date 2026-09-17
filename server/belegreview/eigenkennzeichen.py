#!/usr/bin/env python3
"""Die Eigen-Kennzeichen eines Betriebs — und der Abgleich gegen einen Beleg.

Seit 17.09.2026 (Fall SupremeBeauty: die Inhaberin fotografierte ihre EIGENE
Rechnung und wurde drei mal gefragt, ein- oder ausgehend — dabei stand ihre
eigene Steuernummer oben auf dem Beleg und dieselbe Zahl in ihren
Einstellungen). Diese Datei verbindet, was vorher getrennt lag:

* `profil_text()` nannte Salonname und Rechtsform — aber nicht die
  Steuernummer, nicht die Anschrift. Gemma hatte keinen Anker für „das sind
  WIR oben auf dem Beleg".
* Der Belegkopf wurde nie gegen das Profil GEPRÜFT, nur vom Modell gelesen.

`aussteller(zeilen, einstellungen)` entscheidet deterministisch: Steht der
Betriebsname oder die eigene Steuernummer im Belegskopf (oberste Zeilen,
denn dort steht der Aussteller), ist der Beleg vom Betrieb selbst
ausgestellt — eine Ausgangsrechnung. Kein Modell, keine Frage.

Bewusst KEIN Abgleich über PLZ/Ort allein: Die Postleitzahl teilt man mit
Tausenden; sie NENNT den Aussteller nicht. Name und Steuernummer sind
eindeutig genug — die Steuernummer ist es per Gesetz.
"""
from __future__ import annotations

import re
from typing import Iterable

# Wie viele Zeilen von oben zählen als „Kopf“ — der Aussteller steht dort,
# nicht im Fuß. Mehrere Seiten-Marker („— Seite 1 von 3 —“) springen wir über.
KOPF_ZEILEN = 18


def _norm(text: str) -> str:
    """Kleinbuchstaben, zusammengerückt — „Supreme Beauty“ == „supremebeauty“."""
    return re.sub(r"[\s\-_.:,;()]+", "", (text or "").lower())


def eigen_merkmale(einstellungen: dict) -> dict[str, str]:
    """Name und Steuernummer des Betriebs aus den Einstellungen, normiert.

    Leerstring heißt: das Merkmal steht nicht fest und wird nicht benutzt.
    """
    name = _norm(str(einstellungen.get("betrieb_name") or
                     einstellungen.get("salon") or ""))
    # Steuernummer in alle Schreibweisen falten: 71015/73457,
    # „71 015/73457“, 71015-73457 — die Normierung nimmt alles Trennende
    # raus; gesucht wird später ebenfalls normiert, dadurch trifft auch die
    # punktierte Form auf dem Beleg.
    stnr = re.sub(r"[^0-9]", "", str(einstellungen.get("steuernummer") or ""))
    return {"name": name, "steuernummer": stnr}


def _kopf(zeilen: Iterable) -> str:
    """Der Belegkopf als normierter Text — Zeilen dürfen Strings oder
    {text, conf, box}-Objekte sein (beides schickt die App)."""
    texte = []
    for z in zeilen:
        t = z if isinstance(z, str) else (z or {}).get("text") if isinstance(z, dict) else None
        t = str(t or "").strip()
        if not t or re.match(r"^— Seite \d+ von \d+ —$", t):
            continue
        texte.append(t)
        if len(texte) >= KOPF_ZEILEN:
            break
    return _norm(" ".join(texte))


def aussteller(zeilen: list, einstellungen: dict) -> str | None:
    """Steht der BETRIEB selbst als Aussteller oben auf dem Beleg?

    Rückgabe ist der Beweis als Satz („Betriebsname …“ bzw. „Steuernummer
    …“) — er gehört in den Prompt als Fakt, nicht als Vermutung. None heißt:
    kein Eigen-Merkmal im Kopf, der Beleg läuft ganz normal durch Gemma.

    Ein Treffer ist beweisend für den AUSSTELLER, nicht für die Richtung
    allein: Eine Ausgangsrechnung hat den Betrieb oben. Gutschriften an
    Kunden (Storno unserer Rechnung) tragen denselben Kopf — sie laufen mit
    demselben Fakt und gutschrift=True durch dieselbe Buchung.
    """
    merkmale = eigen_merkmale(einstellungen or {})
    kopf = _kopf(zeilen or [])
    if not kopf:
        return None
    name, stnr = merkmale["name"], merkmale["steuernummer"]
    # Der Name muss aus MEHR als einem Buchstaben bestehen und darf nicht in
    # „unbenannt“ enden — sonst träfe jedes Profil jeden Beleg.
    if name and len(name) >= 4 and name != "unbenannt" and name in kopf:
        roh = str(einstellungen.get("betrieb_name") or
                  einstellungen.get("salon") or "").strip()
        return f"Betriebsname „{roh}“ steht oben auf dem Beleg"
    # Die Steuernummer braucht Substanz (≥ 7 Ziffern — kürzer ist kein
    # deutsches Steuernummer-Format, nur Zufallstreffer-Gefahr). Der Kopf
    # ist alphanumerisch normiert („71015/73457“ bleibt mit Trenner) —
    # deshalb wird sie GEGEN die reine Ziffernfolge des Kopfes geprüft:
    # jede Schreibweise auf dem Beleg („71 015/73457“, „71015-73457“,
    # „Steuernummer 71015/73457“) falten auf dieselben Ziffern.
    if stnr and len(stnr) >= 7:
        kopf_ziffern = re.sub(r"[^0-9]", "", kopf)
        if stnr in kopf_ziffern:
            roh = str(einstellungen.get("steuernummer") or "").strip()
            return f"eigene Steuernummer {roh} steht oben auf dem Beleg"
    return None
