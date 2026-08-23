"""Aus dem Termin abrechnen — und was daraus fürs Kassenbuch folgt.

babu kennt den Termin und seit heute auch den Preis. Nach der Behandlung
genügt ein Tipp: bar, Karte oder Gutschein.

Was babu daraus ausdrücklich NICHT macht: das Kassenbuch selbst schreiben.
Es legt die Tagessummen fertig hin, bestätigt werden sie abends von der
Inhaberin. Der Unterschied ist keine Förmlichkeit — eine Kasse, die
Umsätze selbst aufzeichnet, ist ein elektronisches Aufzeichnungssystem
(§ 146a AO) und bräuchte eine zertifizierte Sicherheitseinrichtung. Ein
Vorschlag, den ein Mensch bestätigt, ist das nicht.

Reine Rechnung ohne I/O.
"""
from __future__ import annotations

# „gutschein" heißt: die Kundin hat mit einem Gutschein bezahlt, also einen
# eingelöst. Kein Geld wechselt den Besitzer und es entsteht kein neuer
# Erlös — beides war beim VERKAUF des Gutscheins (Einzweck-Gutschein, der
# Salon kennt seinen Steuersatz). Zahlt sie drauf, weil die Behandlung
# teurer war, ist nur die Differenz eine Zahlung; ein Termin trägt aber nur
# eine Zahlart, also wird ein solcher Termin heute mit der Zahlart der
# Aufzahlung abgerechnet. Aufteilen kann babu das noch nicht.
ZAHLARTEN = ("bar", "karte", "gutschein")
SAETZE = (0, 7, 19)
PREIS_MAX = 10_000.0


class AbrechnungFehler(ValueError):
    """So ließe sich das nicht abrechnen."""


def _zahl(wert) -> float | None:
    """Zahl aus einer Eingabe — deutsche Schreibweise erlaubt.

    Echte Zahlen gehen NICHT durch den Text-Parser: aus 89.5 würde sonst
    895, weil der Punkt als Tausendertrenner gilt. Nur getippter Text wird
    deutsch gelesen.
    """
    if wert in (None, ""):
        return None
    if isinstance(wert, (int, float)) and not isinstance(wert, bool):
        return float(wert)
    text = str(wert).strip()
    if "," in text:                      # „1.250,00" — Punkt trennt Tausender
        text = text.replace(".", "").replace(",", ".")
    else:
        teile = text.split(".")          # „2.400" = 2400, „89.50" = 89,50
        text = text if len(teile) == 2 and len(teile[1]) == 2 else "".join(teile)
    try:
        return float(text)
    except ValueError:
        return None


def leistung_pruefen(roh: dict) -> dict:
    """Eine Leistung des Katalogs: Name, Preis, Dauer, Steuersatz."""
    name = str((roh or {}).get("name") or "").strip()[:80]
    if not name:
        raise AbrechnungFehler("Wie heißt die Leistung?")
    preis = _zahl((roh or {}).get("preis"))
    if preis is None or not 0 < preis <= PREIS_MAX:
        raise AbrechnungFehler("Was kostet sie? (z. B. 42,00)")
    minuten = _zahl((roh or {}).get("minuten"))
    minuten = int(minuten) if minuten and 0 < minuten <= 1440 else 60
    satz = (roh or {}).get("ust_satz")
    try:
        satz = int(satz)
    except (TypeError, ValueError):
        satz = 19
    return {"name": name, "preis": round(preis, 2), "minuten": minuten,
            "ust_satz": satz if satz in SAETZE else 19}


def zahlart_pruefen(wert: str) -> str:
    art = str(wert or "").strip().lower()
    if art not in ZAHLARTEN:
        raise AbrechnungFehler("Bar, Karte oder Gutschein?")
    return art


def _euro(wert: float) -> str:
    return f"{wert:,.2f} €".replace(",", "@").replace(".", ",").replace("@", ".")


def tagesvorschlag(datum: str, termine: list[dict]) -> dict:
    """Was aus den abgerechneten Terminen dieses Tages folgt.

    Ein VORSCHLAG für das Kassenbuch, keine Buchung. Deshalb steht hier
    weder ein Zeitpunkt noch eine Bestätigung — beides gehört zur
    Bestätigung der Inhaberin, nicht hierher.
    """
    bar = karte = gutschein = sieben = 0.0
    gezaehlt = 0
    offen = 0
    for t in termine or []:
        if t.get("abgesagt"):
            continue
        if not t.get("abgerechnet"):
            if str(t.get("start", ""))[:10] == datum:
                offen += 1
            continue
        if str(t.get("abgerechnet"))[:10] != datum:
            continue
        preis = float(t.get("preis") or 0)
        if preis <= 0:
            continue
        gezaehlt += 1
        art = t.get("zahlart")
        if art == "karte":
            karte += preis
        elif art == "gutschein":
            # Gehört ins Kassenbuch auf `gutscheineEingeloest`: kein
            # Bargeld in der Schublade, kein neuer Erlös. Liefe es wie
            # früher in `bar`, stimmte am Abend der Kassenbestand nicht
            # mehr — und die Aufteilung 7/19 zählte einen Umsatz mit, den
            # es an diesem Tag nicht gab. Deshalb auch kein `sieben`.
            gutschein += preis
            continue
        else:
            bar += preis
        if int(t.get("ust_satz") or 19) == 7:
            sieben += preis

    zusammen = round(bar + karte, 2)
    if not gezaehlt:
        satz = "Heute ist noch nichts abgerechnet."
    else:
        satz = (f"{gezaehlt} abgerechnet: {_euro(bar)} bar, {_euro(karte)} Karte "
                f"— zusammen {_euro(zusammen)}.")
        if gutschein:
            satz += (f" Dazu {_euro(gutschein)} mit Gutschein bezahlt — dafür "
                     f"kam das Geld schon beim Verkauf herein.")
    return {"datum": datum, "vorschlag": True, "termine": gezaehlt, "offen": offen,
            "bar": round(bar, 2), "karte": round(karte, 2),
            "gutschein": round(gutschein, 2),
            "umsatz7": round(sieben, 2), "zusammen": zusammen, "satz": satz}


def rechnungsposition(termin: dict) -> dict:
    """Aus einem Termin die Position für eine Rechnung — für Firmenkunden,
    die nicht bar bezahlen."""
    preis = _zahl((termin or {}).get("preis"))
    if preis is None or preis <= 0:
        raise AbrechnungFehler("Der Termin hat keinen Preis.")
    return {"text": str((termin or {}).get("leistung") or "Behandlung")[:80],
            "einzelpreis": round(preis, 2), "menge": 1,
            "ust_satz": int((termin or {}).get("ust_satz") or 19)}
