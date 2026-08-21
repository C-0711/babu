"""Marketing: was der Salon nach außen zeigt.

babu kennt inzwischen den Namen, die Farbe und das Zeichen des Salons. Damit
lässt sich das machen, wofür sonst niemand Zeit hat: ein Aushang für die
Tür, ein Beitrag für Instagram, ein Gutschein zum Ausdrucken.

Hier steht nur die Regel — welche Stücke es gibt, welches Format sie haben
und wie der Auftrag ans Bildmodell lautet. Gezeichnet wird woanders, damit
prüfbar bleibt, was herauskommt.

Grundhaltung: babu erfindet keine Angebote. Was auf dem Aushang steht,
schreibt die Inhaberin — babu gestaltet es nur.
"""
from __future__ import annotations

import re

# Was ein Salon wirklich braucht. Bewusst wenige Stücke: vier, die man
# versteht, sind besser als zwanzig, durch die man sich klickt.
STUECKE = {
    "aushang": {
        "name": "Aushang für die Tür",
        "dazu": "Öffnungszeiten, Urlaub, eine Neuigkeit",
        "format": "3:4",
        "beschreibung": "ein Aushang im Hochformat für die Salontür oder das "
                        "Schaufenster, aus zwei Metern Entfernung lesbar",
    },
    "post": {
        "name": "Beitrag für Instagram",
        "dazu": "ein Bild fürs Profil oder die Story",
        "format": "1:1",
        "beschreibung": "ein quadratischer Beitrag für soziale Medien, der "
                        "auch als kleines Vorschaubild noch wirkt",
    },
    "gutschein": {
        "name": "Gutschein",
        "dazu": "zum Ausdrucken und Verschenken",
        "format": "3:2",
        "beschreibung": "ein Gutschein im Querformat mit Platz für einen "
                        "handschriftlichen Namen und einen Betrag",
    },
    "preise": {
        "name": "Preisaushang",
        "dazu": "deine Leistungen auf einen Blick",
        "format": "3:4",
        "beschreibung": "eine ruhige Preisliste im Hochformat, klar gegliedert, "
                        "ohne Schnörkel",
    },
}

# Was drauf steht, kommt von der Inhaberin — begrenzt, damit das Bildmodell
# es noch sauber setzen kann.
TEXT_MAX = 240


class MarketingFehler(ValueError):
    """So ließe sich das Stück nicht gestalten."""


def stueck(schluessel: str) -> dict:
    eintrag = STUECKE.get(str(schluessel or "").strip().lower())
    if eintrag is None:
        raise MarketingFehler("Dieses Stück kennen wir nicht.")
    return dict(eintrag, schluessel=str(schluessel).strip().lower())


def text_pruefen(text: str | None) -> str:
    """Der Text der Nutzerin — ohne ihn gibt es kein Stück.

    babu denkt sich keine Angebote aus: „20 % auf alles" muss jemand
    entschieden haben, der die Zahlen kennt.
    """
    sauber = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(sauber) < 3:
        raise MarketingFehler("Schreib kurz, was drauf stehen soll.")
    return sauber[:TEXT_MAX]


def auftrag(stueck_schluessel: str, text: str, einstellungen: dict,
            farbe: str | None = None, mit_logo: bool = False) -> str:
    """Der Auftrag ans Bildmodell — konkret, und ohne erfundene Inhalte."""
    s = stueck(stueck_schluessel)
    inhalt = text_pruefen(text)
    name = str((einstellungen or {}).get("betrieb_name") or "").strip() or "der Salon"
    ton = str(farbe or (einstellungen or {}).get("marke_farbe") or "#1F1D1B")

    zeilen = [
        f"Gestalte {s['beschreibung']} für den Friseur- und Beautysalon "
        f"„{name}“.",
        f"Hauptfarbe {ton} auf hellem, ruhigem Grund. Höchstens zwei Farben.",
        "Klar, hochwertig, viel Weißraum — kein Werbeprospekt-Look, keine "
        "Sternchen, keine Rabattschilder, keine Sprechblasen.",
        "",
        "Der Text lautet GENAU so und wird korrekt und vollständig gesetzt, "
        "ohne Zusätze, ohne Übersetzung, ohne erfundene Zeilen:",
        f"„{inhalt}“",
        "",
        f"Der Salonname „{name}“ steht klein und ruhig dabei.",
        "Keine Menschen, keine Gesichter, keine Fotografie. Flache, "
        "grafische Gestaltung. Kein Rahmen um das Bild.",
    ]
    if mit_logo:
        zeilen.append("Lass oben Platz frei, dort wird das Logo eingesetzt.")
    return "\n".join(zeilen)


def stuecke_liste() -> list[dict]:
    return [dict(v, schluessel=k) for k, v in STUECKE.items()]
