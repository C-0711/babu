"""Monatsabschluss: BWA und Umsatzsteuer-Voranmeldung aus den eigenen Daten.

Reine Rechnung ohne I/O — die Daten kommen aus `babu_web` (Belege des
Monats, Kassenblätter, Einstellungen), damit alles ohne Server testbar ist.

Grundhaltung: babu RECHNET und ZEIGT, geprüft und übermittelt wird vom
steuerlichen Backend. Jede Ausgabe ist ein Entwurf und sagt selbst, worauf
sie sich stützt und was noch fehlt.
"""
from __future__ import annotations

# Kostengruppen der BWA nach SKR04 — die Konten, die babu vergibt.
KOSTENGRUPPEN: list[tuple[str, str, tuple[str, ...]]] = [
    ("personal", "Löhne und Gehälter", ("6000", "6010", "6020", "6030",
                                        "6040", "6110", "6120", "6130")),
    ("material", "Material und Ware", ("5400",)),
    ("fremdleistung", "Fremdleistungen", ("5900",)),
    ("raum", "Raum", ("6310", "6325", "6330")),
    ("versicherung", "Versicherungen", ("6400",)),
    ("werbung", "Werbung", ("6600", "6610")),
    ("fahrzeug", "Auto und Fahrten", ("6530", "6531", "6673")),
    ("buero", "Büro und Technik", ("6805", "6815", "6820", "6837")),
    ("bewirtung", "Bewirtung", ("6640",)),
    ("sonstiges", "Sonstiges", ("6850",)),
]

# Umsatzsteuer-Kennziffern der Voranmeldung (Formular UStVA).
KENNZIFFERN = {
    "81": "Umsätze zu 19 %",
    "86": "Umsätze zu 7 %",
    "48": "Steuerfreie Umsätze (§ 4 Nr. 14)",
    "66": "Vorsteuer aus Rechnungen",
    "83": "Das zahlst du (oder bekommst zurück)",
}


def _rund(wert: float) -> float:
    return round(wert + 0.0, 2)


def _netto(brutto: float, satz: int) -> float:
    return _rund(brutto / (1 + satz / 100)) if satz else _rund(brutto)


def umsatz_profil(einstellungen: dict) -> dict:
    """Welche Fragen muss das Kassenbuch abends stellen?

    Der Normalfall Friseursalon ist zu 100 % 19 % — dann keine einzige
    Zusatzfrage. Alles Weitere hängt an den Stammdaten.
    """
    e = {k: (v or "").strip() for k, v in (einstellungen or {}).items()}
    klein = e.get("kleinunternehmer") == "Ja"
    fragen = []
    if not klein:
        if e.get("ust_befreiung_medizinisch") == "Ja":
            fragen.append({"feld": "umsatzFrei",
                           "frage": "Wie viel davon war Fußpflege ohne Umsatzsteuer?",
                           "hilfe": "Nur die medizinischen Behandlungen — der Rest bleibt normal."})
        if e.get("ust_sieben_prozent") == "Ja":
            fragen.append({"feld": "umsatz7",
                           "frage": "Wie viel davon war mit 7 %?",
                           "hilfe": "Der ermäßigte Satz — im Salon selten."})
        if e.get("verkauft_gutscheine") == "Ja":
            fragen.append({"feld": "gutscheinVerkauf",
                           "frage": "Für wie viel hast du heute Gutscheine verkauft?",
                           "hilfe": "Nur verkaufte Gutscheine. Eingelöste hast du schon eingetragen."})
    return {"kleinunternehmer": klein, "fragen": fragen,
            "braucht_ustva": not klein}


def erloese_monat(kassenblaetter: list[dict]) -> dict:
    """Erlöse eines Monats aus den Tagesblättern des Kassenbuchs.

    Was nicht gefragt wurde, ist 19 % — der Normalfall. Eingelöste
    Gutscheine sind KEIN Umsatz (versteuert wurde beim Verkauf),
    verkaufte Gutscheine dagegen schon (Einzweck-Gutschein).
    """
    bar = ec = frei = sieben = gutschein_verkauf = gutschein_eingeloest = 0.0
    for b in kassenblaetter:
        bar += float(b.get("einnahmenBar") or 0)
        ec += float(b.get("ecZahlungen") or 0)
        frei += float(b.get("umsatzFrei") or 0)
        sieben += float(b.get("umsatz7") or 0)
        gutschein_verkauf += float(b.get("gutscheinVerkauf") or 0)
        gutschein_eingeloest += float(b.get("gutscheineEingeloest") or 0)
    tagesumsaetze = bar + ec
    neunzehn = max(0.0, tagesumsaetze - frei - sieben) + gutschein_verkauf
    return {
        "tage": len(kassenblaetter),
        "bar": _rund(bar), "karte": _rund(ec),
        "brutto_19": _rund(neunzehn), "brutto_7": _rund(sieben),
        "steuerfrei": _rund(frei),
        "gutschein_verkauft": _rund(gutschein_verkauf),
        "gutschein_eingeloest": _rund(gutschein_eingeloest),
        "brutto_gesamt": _rund(neunzehn + sieben + frei),
        "netto_gesamt": _rund(_netto(neunzehn, 19) + _netto(sieben, 7) + frei),
    }


def vorsteuer_monat(belege: list[dict]) -> dict:
    """Vorsteuer aus den Belegen — nur, was belastbar ist.

    Ein Beleg, dessen Summenprobe nicht aufgeht, liefert keine Vorsteuer:
    dort wären 19 % aus dem Brutto zurückgerechnet, und das trägt keine
    Voranmeldung. Solche Belege landen in der Prüfliste statt in Kz 66.
    """
    vorsteuer = 0.0
    netto_kosten = 0.0
    zaehlt = 0
    prueflise: list[dict] = []
    for b in belege:
        stamm = b.get("stamm")
        hinweis = None
        if b.get("brutto") is None:
            hinweis = "Betrag fehlt noch"
        elif b.get("summenprobe_ok") is False:
            hinweis = "Beträge gehen nicht auf — bitte prüfen"
        elif b.get("status") == "nachfrage":
            hinweis = "Da ist noch eine Frage offen"
        if hinweis:
            prueflise.append({"stamm": stamm, "lieferant": b.get("lieferant"),
                              "brutto": b.get("brutto"), "hinweis": hinweis})
            continue
        ust = float(b.get("ust") or 0)
        netto = float(b.get("netto") or 0) or (float(b.get("brutto") or 0) - ust)
        # Gutschrift/Erstattung mindert die Vorsteuer.
        if b.get("gutschrift"):
            ust, netto = -ust, -netto
        vorsteuer += ust
        netto_kosten += netto
        zaehlt += 1
    return {"vorsteuer": _rund(vorsteuer), "netto_kosten": _rund(netto_kosten),
            "belege_gezaehlt": zaehlt, "pruefliste": prueflise}


def ustva_entwurf(monat: str, erloese: dict, vorsteuer: dict,
                  profil: dict) -> dict:
    """Entwurf der Voranmeldung — die Kennziffern des Formulars."""
    if not profil.get("braucht_ustva"):
        return {"monat": monat, "stand": "keine",
                "hinweis": "Als Kleinunternehmerin (§ 19 UStG) gibst du keine "
                           "Umsatzsteuer-Voranmeldung ab.",
                "zeilen": [], "zahllast": 0.0, "pruefliste": []}

    netto19 = _netto(erloese["brutto_19"], 19)
    netto7 = _netto(erloese["brutto_7"], 7)
    ust = _rund(erloese["brutto_19"] - netto19 + erloese["brutto_7"] - netto7)
    zahllast = _rund(ust - vorsteuer["vorsteuer"])
    zeilen = [
        {"kz": "81", "name": KENNZIFFERN["81"], "netto": netto19,
         "steuer": _rund(erloese["brutto_19"] - netto19)},
        {"kz": "86", "name": KENNZIFFERN["86"], "netto": netto7,
         "steuer": _rund(erloese["brutto_7"] - netto7)},
        {"kz": "48", "name": KENNZIFFERN["48"], "netto": erloese["steuerfrei"],
         "steuer": 0.0},
        {"kz": "66", "name": KENNZIFFERN["66"], "netto": None,
         "steuer": vorsteuer["vorsteuer"]},
    ]
    zeilen = [z for z in zeilen if z["netto"] or z["steuer"]]
    return {
        "monat": monat, "stand": "entwurf",
        "zeilen": zeilen,
        "umsatzsteuer": ust,
        "vorsteuer": vorsteuer["vorsteuer"],
        "zahllast": zahllast,
        "satz": ("Du zahlst " + _euro(zahllast) if zahllast >= 0
                 else "Du bekommst " + _euro(-zahllast) + " zurück"),
        "pruefliste": vorsteuer["pruefliste"],
        "hinweis": "Entwurf aus deinen Zahlen. Geprüft und ans Finanzamt "
                   "geschickt wird er von deinem Steuer-Backend.",
    }


def _euro(wert: float) -> str:
    return f"{wert:,.2f} €".replace(",", "@").replace(".", ",").replace("@", ".")


def bwa(monat: str, erloese: dict, belege: list[dict],
        vorjahr: dict | None = None,
        personal_monat: float | None = None,
        vertraege: list[dict] | None = None) -> dict:
    """Monatliche Auswertung: was reinkam, was rausging, was bleibt."""
    gruppen = []
    kosten_gesamt = 0.0
    zuordnung = {konto: (schluessel, name)
                 for schluessel, name, konten in KOSTENGRUPPEN
                 for konto in konten}
    eimer: dict[str, dict] = {}
    for b in belege:
        if b.get("brutto") is None:
            continue
        ust = float(b.get("ust") or 0)
        netto = float(b.get("netto") or 0) or (float(b.get("brutto")) - ust)
        schluessel, name = zuordnung.get(b.get("konto_skr04") or "",
                                         ("sonstiges", "Sonstiges"))
        e = eimer.setdefault(schluessel, {"schluessel": schluessel, "name": name,
                                          "netto": 0.0, "anzahl": 0})
        e["netto"] += netto
        e["anzahl"] += 1
        kosten_gesamt += netto
    # Dauerkosten aus Verträgen (Miete, Versicherung, Leasing): Sie gelten
    # nur, wenn für dasselbe Konto KEIN Beleg im Monat liegt — sonst würde
    # die Miete doppelt zählen.
    for v in (vertraege or []):
        betrag = v.get("betrag_monat")
        konto = v.get("konto_skr04")
        if not betrag or not konto:
            continue
        schluessel, name = zuordnung.get(konto, ("sonstiges", "Sonstiges"))
        vorhanden = eimer.get(schluessel)
        if vorhanden and vorhanden["anzahl"]:
            continue                      # Beleg schlägt Vertrag
        e = eimer.setdefault(schluessel, {"schluessel": schluessel, "name": name,
                                          "netto": 0.0, "anzahl": 0})
        e["netto"] += betrag
        e["aus_vertrag"] = v.get("partner") or v.get("art_name")
        kosten_gesamt += betrag

    for schluessel, name, _ in KOSTENGRUPPEN:
        if schluessel in eimer:
            e = eimer[schluessel]
            e["netto"] = _rund(e["netto"])
            e["anteil"] = (_rund(100 * e["netto"] / erloese["netto_gesamt"])
                           if erloese["netto_gesamt"] else None)
            gruppen.append(e)

    umsatz = erloese["netto_gesamt"]
    ergebnis = _rund(umsatz - kosten_gesamt)

    # Löhne laufen übers Lohnbüro, nicht über Belege. Fehlen sie, ist das
    # Ergebnis geschönt — dann muss die Auswertung das selbst sagen.
    hat_personal = any(g["schluessel"] == "personal" for g in gruppen)
    fehlt: list[str] = []
    if not hat_personal and personal_monat is None:
        fehlt.append("Löhne und Gehälter sind hier noch nicht dabei — "
                     "dein wirklicher Gewinn liegt darunter.")
    if personal_monat:
        gruppen.insert(0, {"schluessel": "personal", "name": "Löhne und Gehälter",
                           "netto": _rund(personal_monat), "anzahl": 0,
                           "geschaetzt": True,
                           "anteil": _rund(100 * personal_monat / umsatz) if umsatz else None})
        kosten_gesamt += personal_monat
        ergebnis = _rund(umsatz - kosten_gesamt)
    d: dict = {
        "monat": monat, "stand": "entwurf",
        "umsatz_netto": umsatz,
        "kosten_netto": _rund(kosten_gesamt),
        "ergebnis": ergebnis,
        "ergebnis_anteil": _rund(100 * ergebnis / umsatz) if umsatz else None,
        "gruppen": gruppen,
        "tage_erfasst": erloese["tage"],
        "fehlt": fehlt,
        "hinweis": "Vorläufig — aus deinen Belegen und deinem Kassenbuch "
                   "gerechnet, noch nicht von der Buchhaltung geprüft.",
    }
    if vorjahr and vorjahr.get("umsatz"):
        monatlich = float(vorjahr["umsatz"]) / 12
        d["vorjahr_monat"] = _rund(monatlich)
        d["vorjahr_delta"] = _rund(umsatz - monatlich)
    return d
