"""Der Terminkalender — babu führt ihn selbst.

Souverän heißt: keine Anbindung an ein fremdes Buchungssystem, keine
Abhängigkeit von dessen Preisen und Laufzeiten, und die Termine bleiben im
Haus. Der Preis dafür ist, dass babu die schwierigen Teile selbst können
muss — angefangen bei dem, der einen Salontag ruiniert: zwei Kundinnen zur
selben Zeit bei derselben Stylistin.

Reine Rechnung ohne I/O. Wo die Termine liegen, entscheidet `babu_web` —
und zwar bewusst NICHT in der Belegbox: in einem Termin steht ein
Kundenname, und in Git bleibt alles für immer stehen.
"""
from __future__ import annotations

import datetime as dt
import re

MAX_MINUTEN = 24 * 60


class KalenderFehler(ValueError):
    """So ließe sich der Termin nicht eintragen."""


def _zeit(wert) -> dt.datetime:
    try:
        return dt.datetime.fromisoformat(str(wert)[:16])
    except (TypeError, ValueError):
        raise KalenderFehler("Diese Uhrzeit können wir nicht lesen.")


def pruefen(termin: dict) -> dict:
    """Aus einer Eingabe ein gültiger Termin — mit ausgerechnetem Ende."""
    start = _zeit((termin or {}).get("start"))
    try:
        minuten = int((termin or {}).get("minuten") or 0)
    except (TypeError, ValueError):
        raise KalenderFehler("Wie lange soll der Termin dauern?")
    if minuten <= 0:
        raise KalenderFehler("Wie lange soll der Termin dauern?")
    if minuten > MAX_MINUTEN:
        raise KalenderFehler("So lange dauert kein Termin.")
    wer = str((termin or {}).get("wer") or "").strip()[:80]
    ende = start + dt.timedelta(minutes=minuten)
    return {
        **{k: v for k, v in (termin or {}).items() if k not in ("start", "ende")},
        "start": start.strftime("%Y-%m-%dT%H:%M"),
        "ende": ende.strftime("%Y-%m-%dT%H:%M"),
        "minuten": minuten,
        "wer": wer,
        "kundin": str((termin or {}).get("kundin") or "").strip()[:80],
        "leistung": str((termin or {}).get("leistung") or "").strip()[:80],
    }


def _name(wert) -> str:
    """Namen zum Vergleichen: „Jana", „ Jana " und „jana" sind dieselbe
    Person. Angezeigt wird weiter, was getippt wurde."""
    return str(wert or "").strip().casefold()


def stoert(neu: dict, bestehende: list[dict]) -> str | None:
    """Kollidiert der Termin mit einem anderen derselben Person?

    Gibt den Satz zurück, den die Nutzerin lesen soll — oder None. Ein
    Termin stört sich nie selbst (sonst ließe sich keiner verschieben), und
    Abgesagtes blockiert nichts.
    """
    a1 = _zeit(neu.get("start"))
    a2 = a1 + dt.timedelta(minutes=int(neu.get("minuten") or 0))
    wer = _name(neu.get("wer"))
    for alt in bestehende or []:
        if alt.get("abgesagt"):
            continue
        if neu.get("id") is not None and alt.get("id") == neu.get("id"):
            continue
        if _name(alt.get("wer")) != wer:
            continue
        b1 = _zeit(alt.get("start"))
        b2 = b1 + dt.timedelta(minutes=int(alt.get("minuten") or 0))
        if a1 < b2 and b1 < a2:      # Berührung am Rand ist keine Überschneidung
            kundin = alt.get("kundin") or "jemand"
            angezeigt = str(neu.get("wer") or "").strip() or "Da"
            return (f"{angezeigt} hat um {b1.strftime('%H:%M')} schon "
                    f"{kundin} — das überschneidet sich.")
    return None


def _dauer_text(minuten: int) -> str:
    h, m = divmod(max(0, minuten), 60)
    if h == 0:
        return f"{m} min"
    return f"{h} Std" if m == 0 else f"{h} Std {m} min"


def tag(datum: str, termine: list[dict], umsatz: float | None = None) -> dict:
    """Ein Tag: was gebucht war, was reinkam — und was eine gebuchte Stunde
    eingebracht hat. Das ist die Zahl, die kein Buchungsanbieter liefert,
    weil er das Geld nicht kennt."""
    aktive = [t for t in (termine or [])
              if not t.get("abgesagt") and str(t.get("start", ""))[:10] == datum]
    minuten = sum(int(t.get("minuten") or 0) for t in aktive)
    pro_stunde = (round(umsatz / (minuten / 60), 2)
                  if umsatz and minuten > 0 else None)

    # „1 Termine" liest sich wie ein Formular. Und ein Satz, der mit einer
    # Ziffer anfängt, wirkt wie ein Datenfeld — deshalb ausgeschrieben.
    wie_viele = "Ein Termin" if len(aktive) == 1 else f"{len(aktive)} Termine"
    if not aktive and umsatz:
        satz = "Kein Termin eingetragen, Umsatz war trotzdem da."
    elif not aktive:
        satz = "Noch nichts eingetragen."
    elif pro_stunde is not None:
        satz = (f"{wie_viele}, {_dauer_text(minuten)} gebucht — das sind "
                + f"{pro_stunde:.2f} € je gebuchter Stunde".replace(".", ","))
    else:
        satz = f"{wie_viele}, {_dauer_text(minuten)} gebucht."

    return {"datum": datum, "termine": len(aktive), "minuten": minuten,
            "dauer_text": _dauer_text(minuten), "umsatz": umsatz,
            "pro_stunde": pro_stunde, "satz": satz,
            "liste": sorted(aktive, key=lambda t: t.get("start") or "")}


# ---------------------------------------------------------------------------
# Freie Lücken finden. Das macht babu selbst, nicht das Sprachmodell: ein
# Modell, das Uhrzeiten „ungefähr" ausrechnet, verplant den Tag. Das Modell
# darf verstehen, was jemand will — rechnen darf es nicht.
# ---------------------------------------------------------------------------

OEFFNUNG = ("09:00", "18:00")
RASTER_MINUTEN = 15


def oeffnung_aus(einstellungen: dict) -> tuple[str, str]:
    """Öffnungszeiten aus den Einstellungen — mit der üblichen Vorgabe.

    Unsinniges (Ende vor Anfang, kaputte Zeit) fällt auf die Vorgabe zurück:
    ein Kalender ohne Zeiten wäre schlimmer als einer mit falschen.
    """
    e = einstellungen or {}
    auf = str(e.get("oeffnet") or "").strip()
    zu = str(e.get("schliesst") or "").strip()
    muster = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
    if muster.match(auf) and muster.match(zu) and auf < zu:
        return (auf, zu)
    return OEFFNUNG


def _minuten_seit_mitternacht(hhmm: str) -> int:
    stunde, minute = str(hhmm).split(":")[:2]
    return int(stunde) * 60 + int(minute)


def freie_luecken(datum: str, termine: list[dict], dauer: int,
                  wer: str = "", oeffnung: tuple[str, str] = OEFFNUNG,
                  hoechstens: int = 6) -> list[str]:
    """Wann ist an diesem Tag `dauer` Minuten am Stück frei?

    Gibt Startzeiten im 15-Minuten-Raster zurück — nicht jede denkbare
    Minute: „14:07 wäre frei" ist keine Antwort, mit der jemand arbeitet.
    """
    if dauer <= 0:
        return []
    belegt = []
    for t in termine or []:
        if t.get("abgesagt") or str(t.get("start", ""))[:10] != datum:
            continue
        if wer and str(t.get("wer") or "").strip() != wer:
            continue
        beginn = _minuten_seit_mitternacht(str(t["start"])[11:16])
        belegt.append((beginn, beginn + int(t.get("minuten") or 0)))

    auf = _minuten_seit_mitternacht(oeffnung[0])
    zu = _minuten_seit_mitternacht(oeffnung[1])
    alle: list[str] = []
    zeit = auf
    while zeit + dauer <= zu:
        ende = zeit + dauer
        if not any(zeit < b2 and b1 < ende for b1, b2 in belegt):
            alle.append(f"{zeit // 60:02d}:{zeit % 60:02d}")
        zeit += RASTER_MINUTEN
    return _gestreut(alle, hoechstens)


def ist_frei(datum: str, termine: list[dict], uhrzeit: str, dauer: int,
             wer: str = "", oeffnung: tuple[str, str] = OEFFNUNG) -> bool:
    """Ist GENAU diese Uhrzeit frei?

    Eine eigene Frage — nicht „steht sie in der Vorschlagsliste". Die Liste
    ist eine Auswahl fürs Auge; ob 14:00 geht, entscheidet der Kalender.
    """
    try:
        beginn = _minuten_seit_mitternacht(uhrzeit)
    except (ValueError, IndexError):
        return False
    ende = beginn + max(0, dauer)
    if beginn < _minuten_seit_mitternacht(oeffnung[0]) \
            or ende > _minuten_seit_mitternacht(oeffnung[1]):
        return False
    for t in termine or []:
        if t.get("abgesagt") or str(t.get("start", ""))[:10] != datum:
            continue
        if wer and str(t.get("wer") or "").strip() != wer:
            continue
        b1 = _minuten_seit_mitternacht(str(t["start"])[11:16])
        b2 = b1 + int(t.get("minuten") or 0)
        if beginn < b2 and b1 < ende:
            return False
    return True


def innerhalb_oeffnung(start: str, minuten: int,
                       oeffnung: tuple[str, str] = OEFFNUNG) -> bool:
    """Liegt der Termin ganz innerhalb der Öffnungszeiten?"""
    try:
        beginn = _minuten_seit_mitternacht(str(start)[11:16])
    except (ValueError, IndexError):
        return False
    return (beginn >= _minuten_seit_mitternacht(oeffnung[0])
            and beginn + max(0, minuten) <= _minuten_seit_mitternacht(oeffnung[1]))


def _gestreut(zeiten: list[str], hoechstens: int) -> list[str]:
    """Über den Tag verteilt statt vier Viertelstunden am Stück.

    „09:00, 09:15, 09:30, 09:45" sind keine Alternativen, sondern dieselbe
    Antwort viermal. Wer einen Termin sucht, will Vormittag ODER Nachmittag.
    """
    if len(zeiten) <= hoechstens:
        return zeiten
    schritt = (len(zeiten) - 1) / (hoechstens - 1)
    return [zeiten[round(i * schritt)] for i in range(hoechstens)]


def wunsch_pruefen(roh: dict, heute: dt.date) -> dict:
    """Was das Sprachmodell aus einem Satz gelesen hat, auf Brauchbarkeit
    prüfen. Erfundene Daten fallen raus, statt einen Termin zu erzeugen."""
    roh = roh if isinstance(roh, dict) else {}
    datum = str(roh.get("datum") or "").strip()[:10]
    try:
        gelesen = dt.date.fromisoformat(datum)
    except ValueError:
        gelesen = None
    # Termine in der Vergangenheit sind fast immer ein Lesefehler.
    if gelesen is None or gelesen < heute:
        gelesen = None

    try:
        minuten = int(roh.get("minuten") or 0)
    except (TypeError, ValueError):
        minuten = 0
    if not 0 < minuten <= MAX_MINUTEN:
        minuten = 60          # der übliche Termin, statt zu raten

    return {
        "kundin": str(roh.get("kundin") or "").strip()[:80],
        "leistung": str(roh.get("leistung") or "").strip()[:80],
        "wer": str(roh.get("wer") or "").strip()[:80],
        "datum": gelesen.isoformat() if gelesen else None,
        "uhrzeit": (str(roh.get("uhrzeit") or "").strip()[:5]
                    if ":" in str(roh.get("uhrzeit") or "") else None),
        "minuten": minuten,
        "sicher": gelesen is not None and bool(str(roh.get("kundin") or "").strip()),
    }


def frage_bauen(text: str, heute: dt.date) -> str:
    """Der Auftrag ans Sprachmodell: verstehen, nicht rechnen."""
    return (
        "Aus diesem Satz einer Friseurin soll ein Terminwunsch werden. "
        f"Heute ist {heute.isoformat()} ({heute.strftime('%A')}). "
        "Gib NUR JSON zurück: "
        '{"kundin": "Name der Kundin oder leer", '
        '"leistung": "was gemacht wird, oder leer", '
        '"wer": "welche Mitarbeiterin, oder leer", '
        '"datum": "JJJJ-MM-TT oder null", '
        '"uhrzeit": "HH:MM oder null, wenn nur ungefähr gesagt wurde", '
        '"minuten": Zahl (Schnitt 45, Farbe 120, Strähnen 150, sonst 60)}. '
        'Rechne relative Angaben wie „nächsten Donnerstag“ in ein Datum um. '
        "Rate nie: was nicht dasteht, ist null.\n\n"
        f"SATZ: {text}")
