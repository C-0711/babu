"""Steuerliche Termine eines Jahres — reine Rechnung ohne I/O.

Wer eine Frist verpasst, zahlt: Verspätungszuschlag beim Finanzamt,
Säumniszuschlag bei der Krankenkasse. Beides ist vermeidbar, wenn der
Termin rechtzeitig auf dem Schirm ist.

Gerechnet wird nach den Regeln, die für einen Salon gelten:

* Umsatzsteuer-Voranmeldung am 10. nach Ablauf des Zeitraums
  (§ 18 Abs. 1 UStG), mit Dauerfristverlängerung einen Monat später
  (§ 46 UStDV) — dann ist im Februar die Sondervorauszahlung fällig.
* Lohnsteuer-Anmeldung ebenfalls am 10. (§ 41a Abs. 1 EStG).
* Sozialversicherung am drittletzten Bankarbeitstag des Monats
  (§ 23 Abs. 1 SGB IV), der Beitragsnachweis zwei Arbeitstage davor.
* Fällt ein Termin auf Samstag, Sonntag oder Feiertag, verschiebt er
  sich auf den nächsten Werktag (§ 108 Abs. 3 AO).

babu rechnet und erinnert — festgesetzt wird vom Finanzamt.
"""
from __future__ import annotations

import datetime as _dt

# ————— Feiertage —————

# Bundeseinheitlich, jedes Jahr am selben Datum.
_FESTE_BUNDESWEIT = ((1, 1, "Neujahr"), (5, 1, "Tag der Arbeit"),
                     (10, 3, "Tag der Deutschen Einheit"),
                     (12, 25, "1. Weihnachtstag"), (12, 26, "2. Weihnachtstag"))

# Feste Feiertage einzelner Länder.
_FESTE_LAENDER = {
    (1, 6, "Heilige Drei Könige"): {"BW", "BY", "ST"},
    (3, 8, "Internationaler Frauentag"): {"BE", "MV"},
    (8, 15, "Mariä Himmelfahrt"): {"SL"},          # BY nur teilweise
    (9, 20, "Weltkindertag"): {"TH"},
    (10, 31, "Reformationstag"): {"BB", "HB", "HH", "MV", "NI", "SN", "ST", "SH", "TH"},
    (11, 1, "Allerheiligen"): {"BW", "BY", "NW", "RP", "SL"},
}

# Bewegliche Feiertage als Abstand zum Ostersonntag.
_BEWEGLICH_BUNDESWEIT = ((-2, "Karfreitag"), (1, "Ostermontag"),
                         (39, "Christi Himmelfahrt"), (50, "Pfingstmontag"))
_BEWEGLICH_LAENDER = {
    (-3, "Gründonnerstag"): set(),                  # nur Schulfrei, kein Feiertag
    (0, "Ostersonntag"): {"BB"},
    (49, "Pfingstsonntag"): {"BB"},
    (60, "Fronleichnam"): {"BW", "BY", "HE", "NW", "RP", "SL"},
}

BUNDESLAENDER = ("BW", "BY", "BE", "BB", "HB", "HH", "HE", "MV",
                 "NI", "NW", "RP", "SL", "SN", "ST", "SH", "TH")


def ostersonntag(jahr: int) -> _dt.date:
    """Osterdatum nach der Gaußschen Osterformel (Butcher-Variante)."""
    a, b, c = jahr % 19, jahr // 100, jahr % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    monat = (h + m - 7 * n + 114) // 31
    tag = ((h + m - 7 * n + 114) % 31) + 1
    return _dt.date(jahr, monat, tag)


def feiertage(jahr: int, land: str | None = None) -> dict[_dt.date, str]:
    """Gesetzliche Feiertage — bundesweit, plus die des Bundeslands.

    Ohne Bundesland wird bewusst nur bundesweit gerechnet: lieber ein
    Termin einen Tag zu früh im Kalender als eine verpasste Frist.
    """
    land = (land or "").strip().upper()
    tage: dict[_dt.date, str] = {}
    for monat, tag, name in _FESTE_BUNDESWEIT:
        tage[_dt.date(jahr, monat, tag)] = name
    ostern = ostersonntag(jahr)
    for abstand, name in _BEWEGLICH_BUNDESWEIT:
        tage[ostern + _dt.timedelta(days=abstand)] = name
    if land in BUNDESLAENDER:
        for (monat, tag, name), laender in _FESTE_LAENDER.items():
            if land in laender:
                tage[_dt.date(jahr, monat, tag)] = name
        for (abstand, name), laender in _BEWEGLICH_LAENDER.items():
            if land in laender:
                tage[ostern + _dt.timedelta(days=abstand)] = name
        if land == "SN":                      # Buß- und Bettag: Mittwoch vor dem 23.11.
            tag = _dt.date(jahr, 11, 22)
            while tag.weekday() != 2:
                tag -= _dt.timedelta(days=1)
            tage[tag] = "Buß- und Bettag"
    return tage


def ist_werktag(tag: _dt.date, feier: dict[_dt.date, str]) -> bool:
    return tag.weekday() < 5 and tag not in feier


def werktag_ab(tag: _dt.date, feier: dict[_dt.date, str]) -> _dt.date:
    """§ 108 Abs. 3 AO: Wochenende und Feiertag schieben die Frist nach hinten."""
    while not ist_werktag(tag, feier):
        tag += _dt.timedelta(days=1)
    return tag


def ist_bankarbeitstag(tag: _dt.date, feier: dict[_dt.date, str]) -> bool:
    """Wie ein Werktag — aber Heiligabend und Silvester zahlen die Banken nicht."""
    if (tag.month, tag.day) in ((12, 24), (12, 31)):
        return False
    return ist_werktag(tag, feier)


def bankarbeitstag_rueckwaerts(letzter: _dt.date, anzahl: int,
                               feier: dict[_dt.date, str]) -> _dt.date:
    """Der n-t-letzte Bankarbeitstag, von `letzter` aus rückwärts gezählt.

    `anzahl=3` liefert den drittletzten — den Tag, an dem der
    Sozialversicherungsbeitrag beim Träger sein muss.
    """
    tag, gefunden = letzter, 0
    while True:
        if ist_bankarbeitstag(tag, feier):
            gefunden += 1
            if gefunden >= anzahl:
                return tag
        tag -= _dt.timedelta(days=1)


def _monatsende(jahr: int, monat: int) -> _dt.date:
    return (_dt.date(jahr, monat, 28) + _dt.timedelta(days=4)).replace(day=1) \
        - _dt.timedelta(days=1)


def _monatsname(monat: int) -> str:
    return ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
            "August", "September", "Oktober", "November", "Dezember")[monat - 1]


# ————— Profil: was die Stammdaten über die Termine sagen —————

def termin_profil(einstellungen: dict, hat_team: bool = False) -> dict:
    """Welche Fristen gelten für diesen Salon?

    Der Rhythmus der Voranmeldung hängt an der Steuer des Vorjahres
    (§ 18 Abs. 2 UStG). Ist er nicht hinterlegt, gilt die vorsichtige
    Annahme „monatlich" — lieber ein Termin zu viel im Kalender.
    """
    e = {k: (v or "").strip() for k, v in (einstellungen or {}).items()}
    klein = e.get("kleinunternehmer") == "Ja"
    rhythmus = e.get("ustva_rhythmus", "").lower()
    if rhythmus not in ("monatlich", "vierteljaehrlich", "keine"):
        rhythmus = "keine" if klein else "monatlich"
    return {
        "kleinunternehmer": klein,
        "ustva_rhythmus": rhythmus,
        "dauerfristverlaengerung": e.get("dauerfristverlaengerung") == "Ja",
        "lohn": bool(hat_team) or e.get("hat_personal") == "Ja",
        "lohnsteuer_rhythmus": (e.get("lohnsteuer_rhythmus", "").lower()
                                or "vierteljaehrlich"),
        "bundesland": e.get("bundesland", "").strip().upper(),
        "steuerberater": e.get("steuerberater_status") in ("Ja", "vorhanden"),
    }


# ————— Die Termine —————

def _ustva_termine(jahr: int, profil: dict, feier: dict) -> list[dict]:
    """Voranmeldungen für die Zeiträume des Jahres — fällig danach.

    Am 10. nach Ablauf des Zeitraums, mit Dauerfristverlängerung einen
    Monat später. Die Dezember-Anmeldung fällt damit ins Folgejahr.
    """
    rhythmus = profil["ustva_rhythmus"]
    if rhythmus == "keine":
        return []
    verlaengert = profil["dauerfristverlaengerung"]
    termine = []

    if rhythmus == "monatlich":
        zeitraeume = [((jahr, m), f"{_monatsname(m)} {jahr}", m) for m in range(1, 13)]
    else:
        zeitraeume = [((jahr, q * 3), f"{q}. Quartal {jahr}", q * 3)
                      for q in range(1, 5)]

    for _, bezeichnung, letzter_monat in zeitraeume:
        # Grundfrist: 10. des Folgemonats, mit Verlängerung des übernächsten.
        versatz = 2 if verlaengert else 1
        monat, ziel_jahr = letzter_monat + versatz, jahr
        while monat > 12:
            monat -= 12
            ziel_jahr += 1
        faellig = werktag_ab(_dt.date(ziel_jahr, monat, 10),
                             feier if ziel_jahr == jahr
                             else feiertage(ziel_jahr, profil.get("bundesland")))
        termine.append({
            "art": "ustva",
            "titel": f"Umsatzsteuer {bezeichnung}",
            "datum": faellig.isoformat(),
            "zeitraum": bezeichnung,
            "was": "Voranmeldung abgeben und die Zahllast überweisen.",
            "wer": "Finanzamt",
        })
    return termine


def _sondervorauszahlung(jahr: int, profil: dict, feier: dict) -> list[dict]:
    """Wer die Dauerfristverlängerung nutzt, zahlt im Februar ein Elftel voraus."""
    if not profil["dauerfristverlaengerung"] or profil["ustva_rhythmus"] != "monatlich":
        return []
    faellig = werktag_ab(_dt.date(jahr, 2, 10), feier)
    return [{
        "art": "sondervorauszahlung",
        "titel": "Sondervorauszahlung Umsatzsteuer",
        "datum": faellig.isoformat(),
        "zeitraum": str(jahr),
        "was": ("Ein Elftel der Umsatzsteuer des Vorjahres anmelden und zahlen — "
                "dafür bleibt die Dauerfristverlängerung bestehen."),
        "wer": "Finanzamt",
    }]


def _lohn_termine(jahr: int, profil: dict, feier: dict) -> list[dict]:
    """Lohnsteuer am 10., Sozialversicherung am drittletzten Bankarbeitstag."""
    if not profil["lohn"]:
        return []
    termine = []

    monatlich = profil["lohnsteuer_rhythmus"] == "monatlich"
    monate = tuple(range(1, 13)) if monatlich else (3, 6, 9, 12)
    for letzter_monat in monate:
        monat, ziel_jahr = letzter_monat + 1, jahr
        if monat > 12:
            monat, ziel_jahr = 1, jahr + 1
        bezeichnung = (_monatsname(letzter_monat) if monatlich
                       else f"{letzter_monat // 3}. Quartal")
        faellig = werktag_ab(_dt.date(ziel_jahr, monat, 10),
                             feier if ziel_jahr == jahr
                             else feiertage(ziel_jahr, profil.get("bundesland")))
        termine.append({
            "art": "lohnsteuer",
            "titel": f"Lohnsteuer-Anmeldung {bezeichnung} {jahr}",
            "datum": faellig.isoformat(),
            "zeitraum": f"{bezeichnung} {jahr}",
            "was": "Einbehaltene Lohnsteuer anmelden und abführen.",
            "wer": "Finanzamt",
        })

    for monat in range(1, 13):
        ende = _monatsende(jahr, monat)
        beitrag = bankarbeitstag_rueckwaerts(ende, 3, feier)
        nachweis = bankarbeitstag_rueckwaerts(beitrag - _dt.timedelta(days=1), 2, feier)
        termine.append({
            "art": "sozialversicherung",
            "titel": f"Sozialversicherung {_monatsname(monat)} {jahr}",
            "datum": beitrag.isoformat(),
            "zeitraum": f"{_monatsname(monat)} {jahr}",
            "was": ("Beiträge müssen bei der Krankenkasse sein — "
                    f"Beitragsnachweis schon am {nachweis.strftime('%d.%m.')}."),
            "wer": "Krankenkasse",
            "nachweis": nachweis.isoformat(),
        })
    return termine


def _jahresfristen(jahr: int, profil: dict, feier: dict) -> list[dict]:
    """Die Steuererklärung, die IN diesem Jahr fällig wird (§ 149 AO).

    Ohne steuerliche Vertretung ist das die des Vorjahres (31. Juli),
    mit Vertretung die des Jahres davor (Ende Februar) — deshalb hängt
    nicht nur das Datum am Profil, sondern auch das Jahr.
    """
    if profil["steuerberater"]:
        vorjahr = jahr - 2
        roh = _monatsende(jahr, 2)
    else:
        vorjahr = jahr - 1
        roh = _dt.date(jahr, 7, 31)
    feier_ziel = feier
    faellig = werktag_ab(roh, feier_ziel)
    return [{
        "art": "jahreserklaerung",
        "titel": f"Steuererklärungen {vorjahr}",
        "datum": faellig.isoformat(),
        "zeitraum": str(vorjahr),
        "was": ("Umsatzsteuer-, Einkommensteuer- und Gewerbesteuererklärung "
                f"für {vorjahr} abgeben."),
        "wer": "Finanzamt",
    }]


def fristen_jahr(jahr: int, profil: dict | None = None) -> list[dict]:
    """Alle Termine, die IN diesem Jahr fällig werden — aufsteigend nach Datum.

    Kalender-Sicht, nicht Zeitraum-Sicht: Anfang Januar ist die
    Voranmeldung für den Dezember davor fällig, und die ist genau die,
    die als Nächstes ansteht. Deshalb werden auch die Zeiträume des
    Vorjahres gerechnet und anschließend nach Fälligkeit gefiltert.
    """
    profil = profil or termin_profil({})
    feier = feiertage(jahr, profil.get("bundesland"))
    feier_vor = feiertage(jahr - 1, profil.get("bundesland"))
    alle = (_ustva_termine(jahr, profil, feier)
            + _ustva_termine(jahr - 1, profil, feier_vor)
            + _sondervorauszahlung(jahr, profil, feier)
            + _lohn_termine(jahr, profil, feier)
            + _lohn_termine(jahr - 1, profil, feier_vor)
            + _jahresfristen(jahr, profil, feier))
    im_jahr = [t for t in alle if t["datum"][:4] == str(jahr)]
    return sorted(im_jahr, key=lambda t: (t["datum"], t["art"]))


def naechste(termine: list[dict], heute: _dt.date, anzahl: int = 3) -> list[dict]:
    """Was als Nächstes ansteht — mit den Tagen, die noch bleiben."""
    offen = []
    for t in termine:
        tag = _dt.date.fromisoformat(t["datum"])
        if tag >= heute:
            offen.append({**t, "in_tagen": (tag - heute).days})
    return offen[:anzahl]
