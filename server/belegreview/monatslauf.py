"""Der Monatsabschluss läuft von selbst an.

Bisher war er eine Aufgabe: hingehen, Monat wählen, rechnen lassen,
freigeben. Wer das vergisst, hat am Jahresende zwölf Aufgaben auf einmal.

Jetzt ist er eine Bestätigung. Am 3. liegt der Vormonat gerechnet da, und
babu sagt in einem Satz, ob er raus kann oder was ihm noch fehlt. Aus „ich
muss noch" wird „ich schau kurz drüber" — das ist der ganze Unterschied.

Reine Rechnung ohne I/O.
"""
from __future__ import annotations

import datetime as dt

# Erst ab diesem Tag gilt der Vormonat als fällig: davor sind noch Belege
# unterwegs, und ein Abschluss, den man dreimal nachbessert, ist keiner.
FAELLIG_AB = 3

MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember")


def monatsname(monat: str) -> str:
    try:
        return MONATE[int(str(monat)[5:7]) - 1]
    except (ValueError, IndexError):
        return str(monat)


def faelliger_monat(heute: dt.date | None = None) -> str | None:
    """Welcher Monat wartet gerade auf einen Blick? None = keiner."""
    heute = heute or dt.date.today()
    if heute.day < FAELLIG_AB:
        return None
    letzter = heute.replace(day=1) - dt.timedelta(days=1)
    return letzter.strftime("%Y-%m")


def stand(monat: str, belege: list[dict], fehlende_belege: list[dict],
          freigegeben: bool, heute: dt.date | None = None) -> dict:
    """Wie weit ist dieser Monat — und was fehlt noch?

    „Offen" heißt: etwas, das die Zahlen ändern würde. Ein unklarer Beleg
    und eine Abbuchung ohne Beleg gehören dazu; eine unbezahlte Rechnung
    nicht — die zählt bei Ist-Versteuerung ohnehin erst, wenn Geld kommt.
    """
    heute = heute or dt.date.today()
    name = monatsname(monat)

    if freigegeben:
        return {"monat": monat, "monatsname": name, "stand": "freigegeben",
                "bereit": False, "offen": [],
                "satz": f"{name} ist übergeben — du musst nichts mehr tun."}

    if monat >= (faelliger_monat(heute) or "9999-99"):
        if monat != faelliger_monat(heute):
            return {"monat": monat, "monatsname": name, "stand": "laeuft",
                    "bereit": False, "offen": [],
                    "satz": f"{name} läuft noch — sammeln reicht."}

    offen: list[dict] = []
    unklar = [b for b in (belege or [])
              if b.get("monat") == monat and b.get("status") in ("nachfrage", "erfasst")]
    if unklar:
        offen.append({
            "art": "belege", "anzahl": len(unklar),
            "text": (f"{len(unklar)} Beleg{'e' if len(unklar) > 1 else ''} "
                     f"brauch{'en' if len(unklar) > 1 else 't'} noch kurz dich"),
        })
    if fehlende_belege:
        summe = sum(float(f.get("betrag") or 0) for f in fehlende_belege)
        offen.append({
            "art": "fehlend", "anzahl": len(fehlende_belege),
            "text": (f"{len(fehlende_belege)} Abbuchung"
                     f"{'en' if len(fehlende_belege) > 1 else ''} ohne Beleg "
                     f"({summe:.2f} €)".replace(".", ",")),
        })

    if not offen:
        return {"monat": monat, "monatsname": name, "stand": "bereit",
                "bereit": True, "offen": [],
                "satz": f"{name} ist gerechnet und kann raus — schau kurz drüber."}
    return {"monat": monat, "monatsname": name, "stand": "wartet",
            "bereit": False, "offen": offen,
            "satz": f"{name} ist fast fertig — es fehlt noch etwas."}
