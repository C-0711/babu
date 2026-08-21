"""Zu dieser Abbuchung fehlt ein Beleg — hast du ihn noch?

Am Jahresende kostet genau das Geld: was vom Konto ging und wofür kein Beleg
da ist, zählt steuerlich nicht. Der Kontoauszug weiß, dass 141 € an den
Großhandel gingen; die Belegbox weiß, dass kein Bon dazu liegt. Gefragt hat
bisher niemand — und drei Monate später weiß es keiner mehr.

Wichtiger als das Fragen ist das Nicht-Fragen. Für die Miete liegt der
Mietvertrag in der Ablage, der IST der Beleg. Wer nach etwas gefragt wird,
das längst geklärt ist, hört beim dritten Mal weg.

Reine Rechnung ohne I/O — die Daten reicht `babu_web` herein.
"""
from __future__ import annotations

import hashlib

# Darunter fragt babu nicht nach: Kontoführungsentgelte und Centbeträge
# haben keinen Beleg und brauchen keinen.
MINDESTBETRAG = 5.0

# Womit ein fehlender Beleg erklärt werden kann. Bewusst wenige — eine lange
# Liste ist eine Ausrede-Sammlung, keine Buchhaltung.
GRUENDE = {
    "kommt_noch": "Beleg kommt noch",
    "vertrag": "Dafür liegt ein Vertrag vor",
    "privat": "War privat, gehört nicht in den Betrieb",
    "kein_beleg": "Dafür gibt es keinen Beleg",
}

# Umsatzsteuersätze, mit denen ein Vertragsbetrag vom Konto gehen kann:
# im Vertrag steht netto, abgebucht wird brutto.
SAETZE = (1.0, 1.19, 1.07)


class JagdFehler(ValueError):
    """So ließe sich das nicht klären."""


def grund_pruefen(grund: str) -> str:
    if grund not in GRUENDE:
        raise JagdFehler("Diesen Grund kennen wir nicht.")
    return grund


def schluessel_fuer(umsatz: dict) -> str:
    """Stabile Kennung einer Abbuchung — Datum, Betrag, Verwendungszweck.

    Muss über Neuladen hinweg gleich bleiben, sonst taucht eine geklärte
    Frage beim nächsten Öffnen wieder auf.
    """
    roh = (f"{umsatz.get('datum')}|{umsatz.get('betrag')}|"
           f"{(umsatz.get('text') or '')[:80]}")
    return hashlib.sha256(roh.encode()).hexdigest()[:16]


def _deckt_ein_vertrag(betrag: float, vertraege: list[dict]) -> bool:
    """Passt die Abbuchung auf einen laufenden Vertrag? Dann ist der Vertrag
    der Beleg — netto wie brutto, denn im Vertrag steht oft der Nettobetrag."""
    for v in vertraege or []:
        monat = (v or {}).get("betrag_monat")
        if not monat:
            continue
        for satz in SAETZE:
            if abs(float(monat) * satz - betrag) <= 0.02:
                return True
    return False


def offene_fragen(fehlend: list[dict], vertraege: list[dict],
                  geklaert: set[str]) -> list[dict]:
    """Wonach babu fragen würde — teuerste zuerst, Geklärtes bleibt weg."""
    fragen = []
    for u in fehlend or []:
        betrag = round(-float(u.get("betrag") or 0), 2)
        if betrag < MINDESTBETRAG:
            continue
        if _deckt_ein_vertrag(betrag, vertraege):
            continue
        kennung = schluessel_fuer(u)
        if kennung in (geklaert or set()):
            continue
        text = (u.get("text") or "").strip()
        datum = u.get("datum") or ""
        fragen.append({
            "schluessel": kennung,
            "datum": datum,
            "betrag": betrag,
            "text": text[:120],
            "frage": (f"{text[:60] or 'Eine Abbuchung'} · "
                      f"{betrag:.2f} €".replace(".", ",")
                      + f" · am {datum[:5]}"),
        })
    fragen.sort(key=lambda f: -f["betrag"])
    return fragen
