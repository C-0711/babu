"""Der Onboarding-Wizard: eine Frage pro Bildschirm.

Nina legt jemanden an, die neue Mitarbeiterin bekommt einen Link und macht
den Rest selbst auf ihrem Telefon. Am Ende liegt eine vollständige
Personalakte vor, ohne dass irgendwo ein Formular gedruckt wurde.

Der eigentliche Wert steckt nicht im Ablauf, sondern in der Prüfung. Eine
verdrehte Ziffer in der Steuer-Identifikationsnummer fällt sonst erst
Wochen später auf — beim Lohnrechner, in fremder Sprache, und dann ist der
Monat schon gelaufen. Steuer-IdNr., Sozialversicherungsnummer und IBAN
haben alle eine Prüfziffer. Wer sie nachrechnet, fängt fast jeden Zahlen­
dreher im selben Moment ab, in dem er passiert.

Ein Wort zum Ton: hier tippt keine Buchhalterin, sondern jemand zwischen
zwei Terminen. Deshalb steht in jedem Schritt, wo die Angabe zu finden ist,
und die Fehlermeldungen sagen, was zu tun ist — nicht, was falsch war.

Reine Rechnung ohne I/O. Wo die Daten liegen, entscheidet `babu_web`: in
SQLite, nicht in der Belegbox, denn eine Personalakte muss löschbar sein.
Die gescannten Dokumente gehen dagegen in die Box, sie sind
aufbewahrungspflichtig.
"""
from __future__ import annotations

import re


class OnboardingFehler(ValueError):
    """Diese Angabe können wir so nicht übernehmen."""


# ———————————————————————————————————————————————————————————————
# Prüfziffern
# ———————————————————————————————————————————————————————————————

def steuer_idnr_pruefen(roh: str) -> str:
    """Die Steuer-Identifikationsnummer — elf Ziffern mit Prüfziffer.

    Zwei Regeln, beide aus der Steuer-Identifikationsnummerverordnung:

    In den ersten zehn Ziffern kommt genau eine Ziffer doppelt oder
    dreifach vor, alle anderen höchstens einmal — und mindestens eine
    Ziffer fehlt ganz. Das allein fängt schon viele Vertipper.

    Die elfte Ziffer ist eine Prüfziffer nach ISO 7064 (MOD 11,10). Sie
    fängt den Rest.
    """
    ziffern = re.sub(r"\D", "", roh or "")
    if not ziffern:
        raise OnboardingFehler(
            "Die Steuer-Identifikationsnummer fehlt. Sie hat elf Ziffern und "
            "steht im letzten Steuerbescheid oder in dem Brief, den das "
            "Bundeszentralamt für Steuern nach der Geburt schickt.")
    if len(ziffern) != 11:
        raise OnboardingFehler(
            f"Die Steuer-Identifikationsnummer hat elf Ziffern, hier sind es "
            f"{len(ziffern)}. Nicht zu verwechseln mit der Steuernummer des "
            "Salons — die sieht anders aus.")
    if ziffern[0] == "0":
        raise OnboardingFehler("Eine Steuer-Identifikationsnummer beginnt nie "
                               "mit einer Null. Bitte noch einmal ansehen.")

    haeufigkeit: dict[str, int] = {}
    for z in ziffern[:10]:
        haeufigkeit[z] = haeufigkeit.get(z, 0) + 1
    mehrfach = [z for z, n in haeufigkeit.items() if n > 1]
    if len(haeufigkeit) > 9 or len(mehrfach) != 1 or haeufigkeit[mehrfach[0]] > 3:
        raise OnboardingFehler(
            "Diese Ziffernfolge kann keine Steuer-Identifikationsnummer sein. "
            "Vermutlich hat sich eine Ziffer verdreht.")

    if _mod11_10(ziffern[:10]) != int(ziffern[10]):
        raise OnboardingFehler(
            "Die Prüfziffer stimmt nicht — irgendwo ist eine Ziffer "
            "verrutscht. Am besten Ziffer für Ziffer vergleichen.")
    return ziffern


def _mod11_10(ziffern: str) -> int:
    """ISO 7064 MOD 11,10 — die Prüfziffer der Steuer-IdNr."""
    rest = 10
    for z in ziffern:
        zwischen = (int(z) + rest) % 10 or 10
        rest = (2 * zwischen) % 11
    return (11 - rest) % 10


# Die Buchstaben der Versicherungsnummer werden zu zweistelligen Zahlen:
# A = 01 … Z = 26.
_GEWICHTE = (2, 1, 2, 5, 7, 1, 2, 1, 2, 1, 2, 1)


def sv_nummer_pruefen(roh: str) -> str:
    """Die Versicherungsnummer der Rentenversicherung.

    Zwölf Zeichen: zwei Ziffern Bereichsnummer, sechs Ziffern Geburtsdatum,
    ein Buchstabe (Anfangsbuchstabe des Geburtsnamens), zwei Ziffern
    Seriennummer, eine Prüfziffer.

    Sie steht im Sozialversicherungsausweis. Wer keinen hat, bekommt von
    der Krankenkasse einen — das ist kein Grund, das Onboarding
    aufzuhalten, deshalb darf dieses Feld auch leer bleiben.
    """
    wert = re.sub(r"[\s.-]", "", (roh or "")).upper()
    if not wert:
        raise OnboardingFehler(
            "Die Sozialversicherungsnummer fehlt. Sie steht auf dem Ausweis "
            "der Rentenversicherung. Wenn du keinen hast, lass das Feld frei "
            "— die Krankenkasse vergibt dann eine.")
    if not re.fullmatch(r"\d{8}[A-Z]\d{3}", wert):
        raise OnboardingFehler(
            "Die Sozialversicherungsnummer sieht so aus: zwei Ziffern, dann "
            "dein Geburtsdatum als TTMMJJ, ein Buchstabe, drei Ziffern — "
            "zum Beispiel 65 170839 J 003.")

    # Buchstabe zu zwei Ziffern, dann jede Stelle gewichtet und quersummiert.
    ausgeschrieben = (wert[:8]
                      + f"{ord(wert[8]) - 64:02d}"
                      + wert[9:11])
    summe = 0
    for gewicht, ziffer in zip(_GEWICHTE, ausgeschrieben):
        produkt = int(ziffer) * gewicht
        summe += produkt // 10 + produkt % 10        # Quersumme des Produkts
    if summe % 10 != int(wert[11]):
        raise OnboardingFehler(
            "Die Prüfziffer der Sozialversicherungsnummer stimmt nicht. "
            "Vergleich sie noch einmal mit dem Ausweis.")
    return wert


def iban_pruefen(roh: str) -> str:
    """IBAN mit der Modulo-97-Probe.

    Auf ein falsches Konto überwiesenes Gehalt holt niemand gern zurück.
    """
    wert = re.sub(r"\s", "", (roh or "")).upper()
    if not wert:
        raise OnboardingFehler("Ohne IBAN kommt kein Gehalt an.")
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", wert):
        raise OnboardingFehler(
            "Das sieht nicht nach einer IBAN aus. Eine deutsche beginnt mit "
            "DE und hat 22 Zeichen.")
    if wert.startswith("DE") and len(wert) != 22:
        raise OnboardingFehler(
            f"Eine deutsche IBAN hat 22 Zeichen, hier sind es {len(wert)}.")
    umgestellt = wert[4:] + wert[:4]
    zahl = "".join(str(ord(c) - 55) if c.isalpha() else c for c in umgestellt)
    if int(zahl) % 97 != 1:
        raise OnboardingFehler(
            "Die Prüfsumme der IBAN stimmt nicht — meist sind zwei Ziffern "
            "vertauscht. Am besten aus der Banking-App kopieren.")
    return wert


# ———————————————————————————————————————————————————————————————
# Die Schritte
# ———————————————————————————————————————————————————————————————
#
# Eine Frage pro Bildschirm, so wie das Kassenbuch es schon macht. Die
# Reihenfolge ist nicht beliebig: erst das, was sie auswendig weiß, dann
# das, wofür sie etwas suchen muss.

SCHRITTE = [
    {
        "id": "person",
        "titel": "Wer bist du?",
        "hilfe": "Bitte genau so, wie es im Ausweis steht.",
        "felder": ["vorname", "name", "geburtsdatum", "geburtsname",
                   "geburtsort", "staatsangehoerigkeit"],
        "pflicht": ["vorname", "name", "geburtsdatum"],
    },
    {
        "id": "anschrift",
        "titel": "Wo wohnst du?",
        "hilfe": "Die Adresse braucht das Finanzamt, nicht wir.",
        "felder": ["strasse", "plz", "ort", "telefon", "email"],
        "pflicht": ["strasse", "plz", "ort"],
    },
    {
        "id": "ausweis",
        "titel": "Ausweis fotografieren",
        "hilfe": "Personalausweis oder Aufenthaltstitel — babu liest ab, was "
                 "es lesen kann, du bestätigst nur.",
        "felder": ["ausweis_dokument", "titel_bis"],
        "pflicht": ["ausweis_dokument"],
    },
    {
        "id": "steuer",
        "titel": "Deine Steuer-Identifikationsnummer",
        "hilfe": "Elf Ziffern. Sie steht im letzten Steuerbescheid oder in "
                 "dem Brief vom Bundeszentralamt für Steuern.",
        "felder": ["steuer_idnr"],
        "pflicht": ["steuer_idnr"],
    },
    {
        "id": "sozialversicherung",
        "titel": "Krankenkasse und Sozialversicherungsnummer",
        "hilfe": "Die Nummer steht auf dem Ausweis der Rentenversicherung. "
                 "Hast du keinen, lass sie frei.",
        "felder": ["krankenkasse", "rentenvers_nr", "kinderlos",
                   "kinder_abschlaege"],
        "pflicht": ["krankenkasse"],
    },
    {
        "id": "bank",
        "titel": "Wohin soll das Gehalt?",
        "hilfe": "Am einfachsten aus der Banking-App kopieren.",
        "felder": ["iban", "bic"],
        "pflicht": ["iban"],
    },
    {
        "id": "vertrag",
        "titel": "Dein Arbeitsvertrag",
        "hilfe": "Lies ihn in Ruhe durch. Angenommen wird er erst unten.",
        "felder": ["vertrag_angenommen"],
        "pflicht": ["vertrag_angenommen"],
    },
    {
        "id": "belehrungen",
        "titel": "Kurz bestätigen",
        "hilfe": "Arbeitsschutz, Hautschutz und Datenschutz — jeweils ein "
                 "Absatz, jeweils ein Haken.",
        "felder": ["belehrungen"],
        "pflicht": ["belehrungen"],
    },
]

SCHRITT_NACH_ID = {s["id"]: s for s in SCHRITTE}


def naechster_schritt(stand: dict) -> dict | None:
    """Was als Nächstes dran ist — oder nichts mehr."""
    erledigt = set(stand.get("erledigt") or [])
    for schritt in SCHRITTE:
        if schritt["id"] not in erledigt:
            return schritt
    return None


def fortschritt(stand: dict) -> dict:
    """Wie weit sie ist. Eine Zahl, die stimmt, motiviert mehr als ein Balken."""
    erledigt = len(set(stand.get("erledigt") or []) & set(SCHRITT_NACH_ID))
    offen = len(SCHRITTE) - erledigt
    return {
        "erledigt": erledigt,
        "gesamt": len(SCHRITTE),
        "fertig": offen == 0,
        "satz": ("Alles erledigt — dein erster Tag steht im Kalender."
                 if offen == 0 else
                 f"Noch {offen} von {len(SCHRITTE)} Schritten."
                 if offen > 1 else "Nur noch ein Schritt."),
    }


# ———————————————————————————————————————————————————————————————
# Was in einem Schritt geprüft wird
# ———————————————————————————————————————————————————————————————

_PRUEFER = {
    "steuer_idnr": steuer_idnr_pruefen,
    "rentenvers_nr": sv_nummer_pruefen,
    "iban": iban_pruefen,
}

_MAX = {"vorname": 80, "name": 80, "geburtsname": 80, "geburtsort": 80,
        "staatsangehoerigkeit": 60, "strasse": 120, "ort": 80,
        "telefon": 40, "email": 120, "krankenkasse": 120, "bic": 20}


def schritt_pruefen(schritt_id: str, daten: dict) -> dict:
    """Eine Antwort prüfen und in die Form bringen, in der sie gespeichert wird."""
    schritt = SCHRITT_NACH_ID.get(schritt_id)
    if not schritt:
        raise OnboardingFehler(f"Diesen Schritt gibt es nicht: {schritt_id}")
    daten = daten if isinstance(daten, dict) else {}

    sauber: dict = {}
    for feld in schritt["felder"]:
        wert = daten.get(feld)

        if feld in _PRUEFER:
            # Freiwillige Felder dürfen leer bleiben; ausgefüllte werden geprüft.
            if wert in (None, "") and feld not in schritt["pflicht"]:
                continue
            sauber[feld] = _PRUEFER[feld](wert)
            continue

        if feld == "geburtsdatum":
            if wert in (None, ""):
                continue
            sauber[feld] = _geburtsdatum(wert)
            continue

        if feld == "plz":
            ziffern = re.sub(r"\D", "", str(wert or ""))
            if ziffern and len(ziffern) != 5:
                raise OnboardingFehler("Eine deutsche Postleitzahl hat fünf "
                                       "Ziffern.")
            if ziffern:
                sauber[feld] = ziffern
            continue

        if feld in ("vertrag_angenommen", "kinderlos"):
            sauber[feld] = bool(wert)
            continue

        if feld == "kinder_abschlaege":
            try:
                sauber[feld] = max(0, min(4, int(wert or 0)))
            except (TypeError, ValueError):
                raise OnboardingFehler("Die Zahl der Kinder bitte als Zahl.")
            continue

        if feld == "belehrungen":
            sauber[feld] = sorted({str(x)[:40] for x in (wert or [])})
            continue

        if wert not in (None, ""):
            sauber[feld] = str(wert).strip()[:_MAX.get(feld, 200)]

    fehlt = [f for f in schritt["pflicht"] if not sauber.get(f)]
    if fehlt:
        raise OnboardingFehler(_fehltext(schritt, fehlt))
    return sauber


BELEHRUNGEN = ("arbeitsschutz", "hautschutz", "datenschutz")


def _fehltext(schritt: dict, fehlt: list[str]) -> str:
    benennung = {
        "vorname": "dein Vorname", "name": "dein Nachname",
        "geburtsdatum": "dein Geburtsdatum", "strasse": "die Straße",
        "plz": "die Postleitzahl", "ort": "der Ort",
        "krankenkasse": "deine Krankenkasse",
        "ausweis_dokument": "ein Foto deines Ausweises",
        "vertrag_angenommen": "deine Zustimmung zum Vertrag",
        "belehrungen": "die Bestätigungen",
    }
    was = [benennung.get(f, f) for f in fehlt]
    if len(was) == 1:
        return f"Es fehlt noch {was[0]}."
    return "Es fehlt noch: " + ", ".join(was) + "."


def _geburtsdatum(wert) -> str:
    import datetime as dt
    text = str(wert).strip()
    for form in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            d = dt.datetime.strptime(text, form).date()
            break
        except ValueError:
            continue
    else:
        raise OnboardingFehler("Das Geburtsdatum bitte als TT.MM.JJJJ.")
    heute = dt.date.today()
    alter = heute.year - d.year - ((heute.month, heute.day) < (d.month, d.day))
    if not 13 <= alter <= 100:
        raise OnboardingFehler(
            "Das Geburtsdatum kann so nicht stimmen — bitte noch einmal "
            "ansehen.")
    return d.isoformat()


def belehrungen_pruefen(bestaetigt) -> list[str]:
    """Alle drei müssen einzeln bestätigt sein.

    Ein Sammelhaken über „ich habe alles gelesen" ist bequem und im
    Streitfall wertlos.
    """
    gesetzt = {str(x) for x in (bestaetigt or [])}
    fehlt = [b for b in BELEHRUNGEN if b not in gesetzt]
    if fehlt:
        benennung = {"arbeitsschutz": "Arbeitsschutz",
                     "hautschutz": "Hautschutz",
                     "datenschutz": "Datenschutz"}
        raise OnboardingFehler(
            "Bitte noch bestätigen: "
            + ", ".join(benennung[f] for f in fehlt) + ".")
    return sorted(gesetzt & set(BELEHRUNGEN))
