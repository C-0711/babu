"""Portale: je Branche eine Kopie von babu, auf denselben Diensten.

babu ist ein Portal für Friseursalons — mit eigener Adresse, eigener Sprache,
eigenem Expertenchat und eigenem Wissenscontainer. Eine weitere Branche
entsteht als KOPIE dieses Portals (erst Barber), nicht als Aufsatz darauf:
`cp friseur.py barber.py`, dann anpassen. Darunter bleiben die Dienste
dieselben — Konto, Kanzlei-Cockpit, Buchungsweg, Kontenrahmen, DATEV,
Monatsabschluss, Kassenbuch, Belegbox. Die Skizze steht im Plan vom
24.09.2026.

Hier steht nur, was sich zwischen zwei Portalen unterscheidet: Texte, die ans
Modell gehen, Namen, Wissensbestände. Alles, was in die Belegbox, in die
Datenbank oder in den DATEV-Stapel geschrieben wird, ist in JEDEM Portal
deutsch und kommt nicht von hier.

Welches Portal gilt, steht in den Einstellungen des Betriebs (Schlüssel
„portal"); ohne Angabe ist es Friseur — jeder Betrieb von vor dem 24.09.2026.

Kein I/O, kein Netz, keine Datenbank — importierbar aus jedem Test.
"""
from __future__ import annotations

from types import ModuleType

from . import barber, friseur, werkstatt

VORGABE = "friseur"

# Sprachen der Bedienung. Die erste ist die Vorgabe. Belegbox, Datenbank,
# DATEV-Stapel und Buchungstext sind in jeder Sprache deutsch.
SPRACHEN = ("de", "tr")

# Was jedes Portal liefern muss. Ein Portal ist ein vollständiger Satz —
# fehlt ein Name, meldet `pruefen()` das, statt dass der Dienst still auf
# ein anderes Portal ausweicht.
NAMEN = (
    "SCHLUESSEL", "NAME",
    # Buchung
    "profil_text", "BUCHUNG_AUFTRAG", "NACHSCHLAG_PRAEFIX", "KATEGORIE_HINWEISE",
    # Expertenchat
    "CHAT_ROLLE", "CHAT_AUFTRAG_ALLGEMEIN", "CHAT_WISSENSTITEL", "CHAT_WELTTITEL",
    # Wissenscontainer (Verzeichnisname unter $HOME) und Suchfrage
    "KOMPENDIUM", "SUCH_OHNE",
)

PORTALE: dict[str, ModuleType] = {m.SCHLUESSEL: m for m in (friseur, barber, werkstatt)}


def hole(schluessel: str | None) -> ModuleType:
    """Das Portal zu diesem Schlüssel — nie None, nie eine Ausnahme.

    Ein Tippfehler in den Einstellungen darf den Buchungsweg nicht anhalten;
    Unbekanntes ist Friseur, wie jeder Betrieb vor dem 24.09.2026."""
    if schluessel:
        treffer = PORTALE.get(str(schluessel).strip().lower())
        if treffer is not None:
            return treffer
    return PORTALE[VORGABE]


def kennt(schluessel: str | None) -> bool:
    """Gibt es dieses Portal wirklich? Für Eingabeprüfungen — dort soll ein
    Tippfehler auffallen, anders als im Buchungsweg."""
    return bool(schluessel) and str(schluessel).strip().lower() in PORTALE


def pruefen() -> list[str]:
    """Selbsttest: jedes Portal liefert jeden Namen, im selben Typ wie
    Friseur. Leere Liste heißt: alles in Ordnung."""
    import re  # noqa: PLC0415
    fehler = []
    vorlage = PORTALE[VORGABE]
    for s, m in PORTALE.items():
        if getattr(m, "SCHLUESSEL", None) != s:
            fehler.append(f"{s}: SCHLUESSEL stimmt nicht")
        for n in NAMEN:
            if not hasattr(m, n):
                fehler.append(f"{s}: {n} fehlt")
            elif type(getattr(m, n)) is not type(getattr(vorlage, n)):
                fehler.append(f"{s}: {n} hat einen anderen Typ als bei Friseur")
        for code, hinweis in getattr(m, "KATEGORIE_HINWEISE", {}).items():
            if re.search(r"\b\d{4}\b", hinweis or ""):
                fehler.append(f"{s}/{code}: Hinweis nennt eine Kontonummer "
                              "(Konten vergibt nur der Katalog)")
    return fehler


# Das ganze Bundesrecht (6.137 Gesetze und Verordnungen, jede Norm im Wortlaut,
# gesetze-im-internet.de, `werkzeuge/kompendium/bundesrecht_holen.py`) liegt in
# EINEM Container, den jedes Portal im Chat zusätzlich zu seinem eigenen
# durchsucht. Gebucht wird damit nicht — der Buchungs-Nachschlag bleibt beim
# Branchen-Container und lässt Gesetzestexte aus (gemma_buchung.GESETZES_QUELLEN).
BUNDESRECHT = "kompendium-bundesrecht"
MIT_BUNDESRECHT = True


def chat_bestaende(p: ModuleType) -> tuple[str, ...]:
    """Wo der Expertenchat dieses Portals sucht: sein Container, dann das
    Bundesrecht."""
    return tuple(p.KOMPENDIUM) + ((BUNDESRECHT,) if MIT_BUNDESRECHT else ())


def suchfrage(p: ModuleType, frage: str) -> str:
    """Die Frage, mit der im Wissenscontainer gesucht wird.

    Im eigenen Portal ist die Branche ohnehin klar; das Wort „Barber" in der
    Frage zieht die Vektorsuche nur zu den Friseur-Dokumenten und drängt die
    Vorschrift, die antwortet, nach hinten. Gemessen am 25.09.2026 im
    Barber-Container: mit Branchenwort 10/12 und 5/10 Fragen mit der
    richtigen Quelle unter den ersten fünf, ohne 12/12 und 8/10 (Kontrollsatz,
    nicht zum Entwurf benutzt); keine Frage wurde schlechter
    (~/.beleglex/messungen/20260925-barber-container/). Leer bei Friseur —
    dort bleibt die Frage, wie sie ist."""
    muster = getattr(p, "SUCH_OHNE", "")
    if not muster:
        return frage
    import re  # noqa: PLC0415
    return " ".join(re.sub(muster, " ", frage, flags=re.I).split()) or frage


def eigener_container(p: ModuleType) -> bool:
    """Hat dieses Portal einen eigenen Wissenscontainer neben dem Hauptbestand?

    Nein bei Friseur — dann ruft jeder Dienst das Kompendium genau so auf
    wie vor dem 24.09.2026, Byte für Byte."""
    return tuple(p.KOMPENDIUM) != ("kompendium",)
