"""Was ist da fotografiert worden — und wohin gehört es?

Die Kamera fragt nicht mehr. Bisher landete alles als Beleg unter `docs/`,
egal ob Kassenbon, Mietvertrag, Bescheid oder Kontoauszug; wer etwas anderes
ablegen wollte, musste im Portal den richtigen Knopf finden.

Entschieden wird über Stichwörter im gelesenen Text, nicht über ein
Sprachmodell: Die Einsortierung muss auch dann stimmen, wenn vLLM gerade
nicht antwortet — und sie muss erklärbar sein, wenn sie danebenliegt.

Im Zweifel Beleg. Das ist der häufigste Fall und der harmloseste Irrtum:
ein falsch abgelegter Vertrag fällt beim Durchsehen sofort auf, ein als
Vertrag abgelegter Bon würde still in der Auswertung fehlen.
"""
from __future__ import annotations

import re

# Merkmale je Art. Gewichte, weil ein einzelnes Wort nichts beweist:
# „Vertragsnummer" steht auch auf Kassenbons.
MERKMALE: dict[str, tuple[tuple[str, int], ...]] = {
    "behoerde": (
        ("rechtsbehelfsbelehrung", 6), ("einspruch", 3), ("bescheid", 4),
        ("festgesetzt", 3), ("finanzamt", 3), ("steuernummer", 2),
        ("vorauszahlung", 2), ("säumniszuschlag", 3), ("betriebsprüfung", 4),
        ("berufsgenossenschaft", 3), ("gewerbeamt", 3), ("ihk", 2),
    ),
    "kontoauszug": (
        ("kontoauszug", 6), ("iban", 3), ("kontostand", 4), ("buchungstag", 3),
        ("valuta", 3), ("lastschrift", 2), ("dauerauftrag", 2),
        ("auszug nr", 3), ("bic", 2), ("sparkasse", 1), ("volksbank", 1),
    ),
    "vertrag": (
        ("mietvertrag", 6), ("arbeitsvertrag", 6), ("leasingvertrag", 6),
        ("versicherungsschein", 6), ("kündigungsfrist", 5), ("laufzeit", 3),
        ("vertragsbeginn", 4), ("vertragspartner", 3), ("monatliche grundmiete", 4),
        ("mietzins", 4), ("jahresbeitrag", 3), ("vertragslaufzeit", 4),
        ("mietgegenstand", 4), ("vermieter", 3), ("mieter", 2),
        ("zwischen", 1), ("§", 1), ("wird vereinbart", 3), ("policen", 2),
    ),
    "beleg": (
        ("mwst", 3), ("ust", 1), ("summe", 2), ("gesamtbetrag", 3),
        ("rückgeld", 4), ("gegeben", 2), ("bar", 1), ("ec-cash", 3),
        ("kassenbon", 5), ("quittung", 4), ("beleg-nr", 3), ("netto", 2),
        ("brutto", 2), ("stk", 2), ("terminal", 2), ("trinkgeld", 2),
        ("rechnung", 3), ("rechnungs-nr", 3), ("zahlbar", 2),
    ),
}

# Bankdaten stehen auf jeder Rechnung mit Zahlungsziel („bitte überweisen Sie
# auf IBAN …"). Als Kontoauszug zählen sie nur, wenn auch ein Wort dabei ist,
# das wirklich nur ein Auszug druckt — sonst wanderten am 23.08.2026
# zweiunddreißig Rechnungsfotos ungelesen ins Auszugsfach.
AUSZUG_KERN = ("kontoauszug", "kontostand", "buchungstag", "valuta", "auszug nr")

# Post von einer Behörde oder Kammer, die eine ZAHLUNG verlangt, ist ein
# Beleg — sie wird bezahlt und ist Betriebsausgabe. Der Jahresbeitrag der
# Handwerkskammer und der Abfallgebührenbescheid lagen bei Nina unter
# „Post vom Amt" und fehlten damit in der Auswertung (Anmerkungen P1-16,
# P1-20, P2-17). Ein Bescheid, der nur etwas festsetzt oder mitteilt
# (Rechtsbehelfsbelehrung, Betriebsprüfung), bleibt Post vom Amt.
ZAHLPFLICHT = (
    "handwerkskammer", "hwk-beitrag", "kammerbeitrag", "innungsbeitrag",
    "jahresbeitrag", "mitgliedsbeitrag", "pflichtbeitrag",
    "abfallgebühr", "müllgebühr", "abfallentsorgung", "straßenreinigung",
    "rundfunkbeitrag", "beitragsservice",
    "mahnung", "zahlungserinnerung", "mahngebühr", "zahlungsaufforderung",
)


def _zahlpflicht(klein: str) -> list[str]:
    return [w for w in ZAHLPFLICHT if w in klein]

# Ein Bescheid nennt oft Beträge und „Rechnung" — trotzdem ist er Post vom
# Amt. Diese Reihenfolge entscheidet bei Gleichstand.
VORRANG = ("behoerde", "kontoauszug", "vertrag", "beleg")

ZIELE = {"beleg": "docs", "vertrag": "dokumente", "behoerde": "dokumente",
         "kontoauszug": "auszuege"}

# Ab hier gilt die Entscheidung als sicher genug, um nicht nachzufragen.
SICHER_AB = 6


def _punkte(text: str) -> dict[str, int]:
    klein = " " + (text or "").lower() + " "
    ergebnis: dict[str, int] = {}
    for art, merkmale in MERKMALE.items():
        punkte = 0
        for wort, gewicht in merkmale:
            if len(wort) <= 3:
                if re.search(rf"\b{re.escape(wort)}\b", klein):
                    punkte += gewicht
            elif wort in klein:
                punkte += gewicht
        ergebnis[art] = punkte
    if ergebnis.get("kontoauszug") and not any(
            (re.search(rf"\b{re.escape(w)}\b", klein) if len(w) <= 3 else w in klein)
            for w in AUSZUG_KERN):
        ergebnis["kontoauszug"] = 0
    # Kammerbeitrag, Gebührenbescheid, Mahnung: Behördenpapier, aber zu
    # bezahlen — also ein Beleg. Der Behörden-Punktestand fällt weg, damit
    # er den Beleg nicht überstimmt.
    if _zahlpflicht(klein):
        ergebnis["behoerde"] = 0
        ergebnis["beleg"] = ergebnis.get("beleg", 0) + SICHER_AB
    return ergebnis


def _gruende(text: str, art: str) -> list[str]:
    klein = " " + (text or "").lower() + " "
    gefunden = [w for w, _ in MERKMALE[art]
                if (re.search(rf"\b{re.escape(w)}\b", klein) if len(w) <= 3
                    else w in klein)]
    if art == "beleg":
        # Zuerst der Grund, der die Entscheidung getragen hat.
        gefunden = _zahlpflicht(klein) + gefunden
    return gefunden


def entscheiden(text: str | None) -> dict:
    """Was ist das? Liefert Art, Ziel, Begründung und ob es sicher ist."""
    punkte = _punkte(text or "")
    beste = max(punkte.values()) if punkte else 0
    if beste == 0:
        return {"art": "beleg", "ziel": "docs", "punkte": 0, "sicher": False,
                "grund": "Keine eindeutigen Merkmale — als Beleg abgelegt."}
    # Bei Gleichstand entscheidet der Vorrang, nicht die Wörterbuch-Reihenfolge.
    art = min((a for a in punkte if punkte[a] == beste), key=VORRANG.index)
    gruende = _gruende(text or "", art)[:4]
    return {
        "art": art,
        "ziel": ZIELE[art],
        "punkte": beste,
        "sicher": beste >= SICHER_AB and beste > sorted(punkte.values())[-2],
        "grund": "Erkannt an: " + ", ".join(gruende) if gruende else "",
    }


def pfad_fuer(art: str, dateiname: str, monat: str) -> str:
    """Wohin die Datei in der Belegbox gehört."""
    ordner = ZIELE.get(art, "docs")
    return f"{ordner}/{monat}/{dateiname}"
