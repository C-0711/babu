"""Das Faktengedächtnis: was Nina babu über sich erzählt hat.

Der Gesprächsverlauf (Tabellen `gespraech`/`nachricht`) merkt sich, worüber
gerade gesprochen wurde. Er reicht nicht: „Ich habe zwei Minijobberinnen",
„montags ist zu", „die Kaffeemaschine war für den Salon" steht in keinem
Beleg und geht mit dem Faden verloren, sobald das Gespräch endet. Genau das
unterscheidet einen Kumpel von einer Auskunft — er weiß beim nächsten Mal
noch, was man ihm gesagt hat.

**Was hier gemerkt wird, hat sie selbst gesagt.** Kein Modell entscheidet
das mit: entweder sie sagt es ausdrücklich („merk dir: …") oder sie trägt
es selbst ein. Was babu bloß VERMUTET, gehört nicht hierher — ein
Gedächtnis, das sich Dinge ausdenkt, ist schlimmer als keines, weil die
Erfindung danach in jede Antwort einfließt und wie ein Fakt aussieht.

Reine Rechnung, kein I/O: die Ablage liegt in der Datenbank (siehe
`babu_web`, Tabelle `merksatz`), nicht in der Belegbox — Personenbezogenes
muss löschbar sein (Art. 17 DSGVO), und in der Box bliebe jede Fassung für
immer stehen.
"""
from __future__ import annotations

import re

# Ein Merksatz ist ein Satz, keine Abhandlung. Was länger ist, ist eine
# Frage mit Vorgeschichte — die gehört in den Verlauf, nicht ins Gedächtnis.
MAX_TEXT = 300

# So viele Sätze gehen höchstens in den Prompt. Mehr hat noch niemand
# gesagt, und ein unbegrenzter Block würde den Weltblock verdrängen.
MAX_SAETZE = 40

# Die ausdrückliche Bitte, sich etwas zu merken — in ihrer Sprache, nicht
# in unserer. Bewusst klein und wörtlich: jedes Muster hier ist eine
# Erlaubnis, etwas dauerhaft zu speichern, und die gibt sie, nicht wir.
AUSLOESER = (
    "merk dir bitte", "merke dir bitte", "merk dir", "merke dir",
    "merk bitte", "bitte merken", "zum merken",
    "denk dran", "denk daran", "behalt im kopf", "behalte im kopf",
    "vergiss nicht", "notier dir", "notiere dir",
    "für dich zur info", "zur info für dich",
)

# Was nach dem Auslöser noch weg darf, damit „merk dir, dass montags zu
# ist" zu „montags zu ist" wird und nicht zu „, dass montags zu ist".
# NUR „dass" (die Konjunktion), nicht „das" — sonst verlöre „merk dir: das
# Salonkonto ist neu" sein Subjekt.
_VORSPANN = re.compile(r"^[\s,:;\-–—]*(dass\s+)?", re.I)

# Kürzer als das ist kein Satz, sondern ein Rest: „merk dir das" endet nach
# dem Auslöser bei „das" und ist keine Angabe über den Betrieb.
MIN_TEXT = 5


def _norm(text: str) -> str:
    """Zum Vergleichen: Kleinschreibung, ein Leerzeichen, keine Satzzeichen
    am Rand. Damit gilt „Montags ist zu." als derselbe Satz wie
    „montags ist zu" und steht nicht zweimal da."""
    return re.sub(r"\s+", " ", (text or "").strip().strip(".!? ").lower())


def merksatz_aus_frage(frage: str) -> str | None:
    """Der Satz, den sie sich ausdrücklich merken lassen will — oder nichts.

    Gesucht wird der Auslöser irgendwo im Text, nicht nur am Anfang: „Ach,
    und merk dir, dass montags zu ist" ist derselbe Wunsch wie „Merk dir:
    montags ist zu". Zurück kommt IHR Wortlaut ab dem Auslöser, nicht eine
    Zusammenfassung davon.
    """
    if not frage:
        return None
    klein = frage.lower()
    beste: int | None = None
    laenge = 0
    for wort in AUSLOESER:
        stelle = klein.find(wort)
        if stelle < 0:
            continue
        # Der früheste Auslöser gewinnt; bei gleichem Anfang der längste
        # („merk dir bitte" schlägt „merk dir"), sonst bliebe „bitte" stehen.
        if beste is None or stelle < beste or (stelle == beste and len(wort) > laenge):
            beste, laenge = stelle, len(wort)
    if beste is None:
        return None
    rest = frage[beste + laenge:]
    rest = _VORSPANN.sub("", rest).strip()
    rest = rest.strip(" ,;:")
    if len(rest) < MIN_TEXT:
        return None
    return rest[:MAX_TEXT]


def ist_neu(text: str, vorhandene) -> bool:
    """Steht das schon da? Zweimal derselbe Satz ist kein zweites Wissen."""
    fertig = _norm(text)
    if not fertig:
        return False
    return all(_norm(v) != fertig for v in (vorhandene or []))


def saubern(text) -> str | None:
    """Ein von Hand eingetragener Merksatz, auf Länge gebracht."""
    if not isinstance(text, str):
        return None
    sauber = re.sub(r"\s+", " ", text).strip()
    return sauber[:MAX_TEXT] if len(sauber) >= 3 else None


def block(saetze) -> str:
    """Der Gedächtnis-Block für den Prompt.

    Steht im Prompt HINTER dem Weltblock: er ändert sich seltener als die
    Box, aber wenn er sich ändert, soll er nicht den ganzen stehenden
    Anfang ungültig machen. Und er sagt dem Modell ausdrücklich, woher das
    kommt — damit es „du hast mir gesagt, dass …" schreiben kann statt es
    als eigene Erkenntnis auszugeben.
    """
    zeilen = [str(s).strip() for s in (saetze or []) if str(s or "").strip()]
    if not zeilen:
        return ""
    kopf = ("WAS SIE DIR SELBST ERZÄHLT HAT (steht in keinem Beleg — sie hat "
            "dich gebeten, es zu behalten; beziehe dich darauf, wenn es passt, "
            "und nenne es als ihre Angabe):")
    return kopf + "\n" + "\n".join(f"  · {z}" for z in zeilen[:MAX_SAETZE])


def titel(frage: str) -> str:
    """Ein Faden braucht einen Namen, damit sie ihn in der Auskunft
    wiedererkennt. Ihre erste Frage ist der beste, den es gibt."""
    kurz = re.sub(r"\s+", " ", (frage or "").strip())
    return kurz[:80] or "Gespräch"
