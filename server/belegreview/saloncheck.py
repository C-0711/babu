"""Salon-Check — Ampel-Karten aus den Kennzahlen des letzten Jahres.

Reine Funktionen ohne I/O und ohne LLM: kennzahlen.json rein, Karten raus.
Die Vergleichswerte sind übliche Spannen im Friseurhandwerk; die Kartentexte
folgen den Sprachregeln der Salon-UI (kein Fachvokabular, du-Form).
"""

# Übliche Anteile am Umsatz im Friseurhandwerk (untere/obere Spanne).
UEBLICH_FRISEUR = {
    "material": (0.10, 0.12),
    "personal": (0.45, 0.55),
    "raum": (0.10, 0.15),
}

# Bis zu diesem Faktor über der Spanne wird es gelb, darüber rot.
GELB_FAKTOR = 1.2

# Faustregel für die Steuer-Rücklage: Anteil vom Gewinn, auf 50 € gerundet.
RUECKLAGE_ANTEIL = 0.30
RUECKLAGE_SCHRITT = 50

# Kleinunternehmer-Grenze (Vorjahresumsatz, seit 2025).
KLEIN_GRENZE = 25000.0


def _euro(betrag: float) -> str:
    ganz = f"{round(betrag):,}".replace(",", ".")
    return f"{ganz} €"


def _prozent_von_hundert(anteil: float) -> int:
    return round(anteil * 100)


def ruecklage_monatlich(gewinn: float, vorauszahlungen: float) -> int:
    """Empfohlene monatliche Rücklage, auf volle 50 € gerundet."""
    offen = gewinn * RUECKLAGE_ANTEIL - vorauszahlungen
    if offen <= 0:
        return 0
    monat = offen / 12
    return int(round(monat / RUECKLAGE_SCHRITT) * RUECKLAGE_SCHRITT) or RUECKLAGE_SCHRITT


def _ampel_fuer_anteil(anteil: float, spanne: tuple[float, float]) -> str:
    unten, oben = spanne
    if anteil <= oben:
        return "gruen"
    if anteil <= oben * GELB_FAKTOR:
        return "gelb"
    return "rot"


def _grau(karte_id: str, titel: str, detail: str) -> dict:
    return {
        "id": karte_id, "ampel": "grau", "titel": titel,
        "satz": "Das konnten wir nicht sicher lesen — magst du kurz draufschauen?",
        "detail": detail, "wert": None, "ueblich": None,
    }


def _anteil_karte(karte_id: str, titel: str, wovon: str, betrag: float | None,
                  umsatz: float | None, unsicher: set[str]) -> dict:
    spanne = UEBLICH_FRISEUR[karte_id]
    von = _prozent_von_hundert(spanne[0])
    bis = _prozent_von_hundert(spanne[1])
    ueblich = f"{von} bis {bis} von 100 €"
    detail = (f"Wir teilen deine {wovon} durch deinen Umsatz. "
              f"Bei Friseursalons sind {von} bis {bis} von 100 € Umsatz üblich.")
    if karte_id in unsicher or betrag is None or not umsatz:
        return _grau(karte_id, titel, detail)
    anteil = betrag / umsatz
    je_hundert = _prozent_von_hundert(anteil)
    satz = (f"{titel} kostet dich {je_hundert} von 100 € Umsatz. "
            f"Üblich sind {von} bis {bis}.")
    if anteil <= spanne[1]:
        satz = (f"{titel} kostet dich {je_hundert} von 100 € Umsatz — "
                f"das passt gut. Üblich sind {von} bis {bis}.")
    return {
        "id": karte_id, "ampel": _ampel_fuer_anteil(anteil, spanne),
        "titel": titel, "satz": satz, "detail": detail,
        "wert": f"{je_hundert} von 100 €", "ueblich": ueblich,
    }


def _gewinn_karte(zahlen: dict, unsicher: set[str]) -> dict:
    detail = ("Gewinn heißt: Umsatz minus alle Kosten. "
              "Davon lebst du — und davon geht noch die Steuer ab.")
    umsatz = zahlen.get("umsatz")
    gewinn = zahlen.get("gewinn")
    if "gewinn" in unsicher or gewinn is None or not umsatz:
        return _grau("gewinn", "Dein Gewinn", detail)
    je_hundert = _prozent_von_hundert(gewinn / umsatz)
    if gewinn <= 0:
        return {
            "id": "gewinn", "ampel": "rot", "titel": "Dein Gewinn",
            "satz": (f"Letztes Jahr ist unterm Strich nichts geblieben "
                     f"({_euro(gewinn)}). Das schauen wir uns mit dir an."),
            "detail": detail, "wert": _euro(gewinn), "ueblich": None,
        }
    return {
        "id": "gewinn", "ampel": "gruen", "titel": "Dein Gewinn",
        "satz": (f"Von 100 € Umsatz bleiben dir {je_hundert} €. "
                 f"Im Jahr waren das {_euro(gewinn)}."),
        "detail": detail, "wert": _euro(gewinn), "ueblich": None,
    }


def _personal_karte(zahlen: dict, unsicher: set[str]) -> dict:
    personal = zahlen.get("personal")
    if personal == 0 and "personal" not in unsicher:
        return {
            "id": "personal", "ampel": "gruen", "titel": "Dein Team",
            "satz": "Du arbeitest allein — Personalkosten hast du keine.",
            "detail": ("Sobald du jemanden einstellst, rechnen wir die "
                       "Personalkosten hier mit ein."),
            "wert": "0 €", "ueblich": None,
        }
    return _anteil_karte("personal", "Dein Team", "Personalkosten",
                         personal, zahlen.get("umsatz"), unsicher)


def _ruecklage_karte(zahlen: dict, unsicher: set[str]) -> dict:
    detail = ("Faustregel: knapp ein Drittel vom Gewinn für die Steuer "
              "zur Seite legen. Was du schon vorausgezahlt hast, ziehen "
              "wir ab. Keine Steuerberatung — nur eine Faustregel.")
    gewinn = zahlen.get("gewinn")
    if "gewinn" in unsicher or gewinn is None:
        return _grau("ruecklage", "Deine Steuer-Rücklage", detail)
    voraus = zahlen.get("est_vorauszahlungen") or 0
    if gewinn <= 0:
        return {
            "id": "ruecklage", "ampel": "gruen", "titel": "Deine Steuer-Rücklage",
            "satz": "Für das letzte Jahr fällt kaum Steuer an — atme durch.",
            "detail": detail, "wert": "0 €", "ueblich": None,
        }
    monat = ruecklage_monatlich(gewinn, voraus)
    if monat == 0:
        return {
            "id": "ruecklage", "ampel": "gruen", "titel": "Deine Steuer-Rücklage",
            "satz": ("Deine Vorauszahlungen decken die Faustregel schon ab — "
                     "da kommt wenig nach."),
            "detail": detail, "wert": "0 €", "ueblich": None,
        }
    return {
        "id": "ruecklage", "ampel": "gelb", "titel": "Deine Steuer-Rücklage",
        "satz": (f"Leg dir am besten {_euro(monat)} im Monat zur Seite — "
                 f"dann erschrickst du beim Steuerbescheid nicht."),
        "detail": detail, "wert": f"{_euro(monat)} im Monat", "ueblich": None,
    }


def _ust_karte(stammdaten: dict, zahlen: dict, unsicher: set[str]) -> dict:
    klein = stammdaten.get("kleinunternehmer")
    umsatz = zahlen.get("umsatz")
    if klein:
        detail = ("Als Kleinunternehmerin weist du keine Umsatzsteuer aus. "
                  f"Das gilt nur, solange dein Umsatz unter {_euro(KLEIN_GRENZE)} "
                  "im Jahr bleibt.")
        if umsatz and umsatz > KLEIN_GRENZE and "umsatz" not in unsicher:
            return {
                "id": "ust", "ampel": "gelb", "titel": "Umsatzsteuer",
                "satz": (f"Dein Umsatz lag über {_euro(KLEIN_GRENZE)} — "
                         "die Kleinunternehmer-Regel passt womöglich nicht mehr. "
                         "Das klären wir mit dir."),
                "detail": detail, "wert": _euro(umsatz), "ueblich": None,
            }
        return {
            "id": "ust", "ampel": "gruen", "titel": "Umsatzsteuer",
            "satz": "Du bist Kleinunternehmerin — Umsatzsteuer ist kein Thema für dich.",
            "detail": detail, "wert": None, "ueblich": None,
        }
    detail = ("Die Umsatzsteuer nimmst du für das Finanzamt ein und "
              "führst sie ab — sie gehört nie dir.")
    zahllast = zahlen.get("ust_zahllast")
    if zahllast is None or "ust_zahllast" in unsicher:
        return _grau("ust", "Umsatzsteuer", detail)
    return {
        "id": "ust", "ampel": "gruen", "titel": "Umsatzsteuer",
        "satz": (f"{_euro(zahllast)} Umsatzsteuer hast du letztes Jahr "
                 f"ans Finanzamt gezahlt — das lief sauber."),
        "detail": detail, "wert": _euro(zahllast), "ueblich": None,
    }


def karten_bauen(kennzahlen: dict) -> list[dict]:
    """Baut die Ampel-Karten des Salon-Checks aus kennzahlen.json."""
    zahlen = kennzahlen.get("zahlen") or {}
    stammdaten = kennzahlen.get("stammdaten") or {}
    unsicher = set(kennzahlen.get("unsicher") or [])
    # Namen aus dem Schema auf Karten-Ids abbilden.
    if "wareneinsatz" in unsicher:
        unsicher.add("material")
    if "raumkosten" in unsicher:
        unsicher.add("raum")
    karten = [
        _gewinn_karte(zahlen, unsicher),
        _anteil_karte("material", "Dein Material", "Materialkosten",
                      zahlen.get("wareneinsatz"), zahlen.get("umsatz"), unsicher),
        _personal_karte(zahlen, unsicher),
        _anteil_karte("raum", "Deine Miete", "Raumkosten",
                      zahlen.get("raumkosten"), zahlen.get("umsatz"), unsicher),
        _ruecklage_karte(zahlen, unsicher),
        _ust_karte(stammdaten, zahlen, unsicher),
    ]
    return karten
