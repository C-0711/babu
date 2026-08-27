"""Das Kassenbuch nach GoBD: nichts verschwindet, nichts ändert sich still.

Bis zum 28.08.2026 überschrieb ein zweiter Eintrag für denselben Tag den
ersten wortlos — der Index sagte dazu „ein späteres gewinnt (Korrektur)".
Für ein Kassenbuch ist das der Fehler, der die ganze Kasse angreifbar
macht: § 146 Abs. 4 AO verlangt, dass eine Aufzeichnung nicht so geändert
wird, dass der ursprüngliche Inhalt nicht mehr feststellbar ist.

Drei Dinge stellen das her, und alle drei sind hier reine Rechnung ohne
I/O — damit sie ohne Server und ohne Belegbox prüfbar sind:

1. **Begründungspflicht.** Wer einen Tag ändert, der schon eingetragen
   ist, sagt warum. Ohne Grund wird nicht geschrieben.
2. **Änderungsprotokoll.** Jede Änderung legt den vorherigen Stand mit
   Zeitpunkt, Person und Grund ab. Damit bleibt der ursprüngliche Inhalt
   feststellbar, auch ohne in die Historie der Belegbox zu sehen.
3. **Festschreibung.** Sobald die Zahlen eines Monats erklärt sind — die
   Voranmeldung ist erstellt oder der Monatsabschluss freigegeben —, ist
   der Monat zu. Eine Korrektur läuft dann über den laufenden Monat,
   nicht rückwirkend über ein Blatt, das schon beim Finanzamt liegt.

Was hier NICHT passiert: löschen. Ein Kassenblatt wird nie entfernt, auch
nicht auf Wunsch — eine Lücke in der Nummernfolge der Tage ist genau das,
wonach eine Prüfung sucht. Wer sich vertan hat, trägt den Tag neu ein und
sagt warum; beides bleibt stehen.
"""
from __future__ import annotations

# So lang muss eine Begründung mindestens sein. Kurz genug, dass „Zahlendreher"
# reicht — lang genug, dass ein Punkt oder ein „x" nicht durchgeht.
GRUND_MIN = 5
GRUND_MAX = 300

# Die Felder, deren Änderung protokolliert wird: alles, was Geld bewegt,
# plus die Notizen. Technisches (`von`, `geaendert`) gehört nicht dazu.
NICHT_PROTOKOLLIEREN = ("von", "geaendert_am", "geaendert_von", "grund")


def darf_schreiben(vorher: dict | None, grund: str | None,
                   festgeschrieben: bool) -> tuple[bool, str | None]:
    """Darf dieser Tag geschrieben werden — und wenn nein, warum nicht?

    Der Text ist der, den Nina liest: kein Paragraf, kein Fachwort, und
    er sagt, was sie stattdessen tun kann.
    """
    if festgeschrieben:
        return False, ("Dieser Monat ist abgeschlossen — die Zahlen sind "
                       "schon beim Finanzamt. Ändern lässt sich hier nichts "
                       "mehr. Trag die Korrektur im laufenden Monat ein und "
                       "schreib dazu, worauf sie sich bezieht.")
    if vorher is None:
        return True, None                      # ein neuer Tag braucht nichts
    if not (grund or "").strip():
        return False, ("Für diesen Tag steht schon etwas im Kassenbuch. "
                       "Schreib kurz dazu, was du änderst und warum — das "
                       "gehört zu einer ordentlichen Kasse.")
    if len(grund.strip()) < GRUND_MIN:
        return False, ("Ein Wort reicht als Begründung nicht. Schreib kurz, "
                       "was du änderst und warum.")
    return True, None


def unterschied(vorher: dict, nachher: dict) -> dict:
    """Was sich geändert hat — Feld für Feld, alter und neuer Wert.

    Nur echte Unterschiede; ein erneutes Speichern ohne Änderung soll kein
    Protokoll erzeugen, das nichts sagt."""
    aus: dict[str, dict] = {}
    for feld in sorted(set(vorher) | set(nachher)):
        if feld in NICHT_PROTOKOLLIEREN:
            continue
        alt, neu = vorher.get(feld), nachher.get(feld)
        if alt != neu:
            aus[feld] = {"vorher": alt, "nachher": neu}
    return aus


def protokoll_fortschreiben(bisher: list[dict] | None, vorher: dict,
                            nachher: dict, wer: str, grund: str,
                            wann: str) -> list[dict]:
    """Den Änderungseintrag anhängen. Gibt die Liste unverändert zurück,
    wenn sich fachlich nichts geändert hat."""
    felder = unterschied(vorher, nachher)
    if not felder:
        return list(bisher or [])
    return list(bisher or []) + [{
        "wann": wann,
        "wer": wer,
        "grund": (grund or "").strip()[:GRUND_MAX],
        "felder": felder,
    }]


def zustand(vorher: dict | None, protokoll: list[dict] | None,
            festgeschrieben: bool) -> dict:
    """Was die App über diesen Tag anzeigt: eingetragen, geändert, zu.

    Die Wörter sind Ninas, nicht die der Abgabenordnung — „abgeschlossen"
    statt „festgeschrieben", „Änderungen" statt „Journal"."""
    n = len(protokoll or [])
    if vorher is None:
        return {"eingetragen": False, "abgeschlossen": festgeschrieben,
                "aenderungen": 0, "text": "Noch nichts eingetragen."}
    if festgeschrieben:
        text = "Abgeschlossen — die Zahlen sind beim Finanzamt."
    elif n:
        text = (f"{n}-mal geändert" if n > 1 else "Einmal geändert")
    else:
        text = "Eingetragen."
    return {"eingetragen": True, "abgeschlossen": festgeschrieben,
            "aenderungen": n, "text": text}
