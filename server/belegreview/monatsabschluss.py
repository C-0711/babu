"""Monatsabschluss: BWA und Umsatzsteuer-Voranmeldung aus den eigenen Daten.

Reine Rechnung ohne I/O — die Daten kommen aus `babu_web` (Belege des
Monats, Kassenblätter, Einstellungen), damit alles ohne Server testbar ist.

Grundhaltung: babu RECHNET und ZEIGT, geprüft und übermittelt wird vom
steuerlichen Backend. Jede Ausgabe ist ein Entwurf und sagt selbst, worauf
sie sich stützt und was noch fehlt.
"""
from __future__ import annotations

from geld import rund as _rund

# Kostengruppen der BWA nach SKR04 — Zuschnitt und Reihenfolge folgen der
# DATEV-Standard-BWA (Form 01, kurzfristige Erfolgsrechnung); die Konten
# stammen aus dem Starter-Kontenplan Beautysalon auf SKR04-Basis.
#
# Der Name hier ist Ninas Wort für den Bildschirm — der Zeilenname der
# DATEV-BWA steht daneben in `vordrucke.BWA_ZEILE` und geht aufs Papier.
# Bis 27.08.2026 kannten die Gruppen nur zehn Konten: Materialeinsatz,
# Porto, Fortbildung, Reparaturen, Beiträge und die Beratungskosten
# fielen alle in „Sonstiges" — genau der Eindruck, den Nina beschrieben
# hat („Sonstiger Betriebsbedarf wird zu häufig verwendet").
KOSTENGRUPPEN: list[tuple[str, str, tuple[str, ...]]] = [
    ("personal", "Löhne und Gehälter", ("6000", "6010", "6020", "6030",
                                        "6035", "6040", "6110", "6120",
                                        "6130")),
    ("material", "Material und Ware", ("5100", "5200", "5400", "5800",
                                       "5900")),
    ("raum", "Raum", ("6305", "6310", "6315", "6320", "6325", "6330",
                      "6335")),
    ("steuern_betrieb", "Abgaben für Grundbesitz und Kfz", ("6340", "7685")),
    ("versicherung", "Versicherungen und Beiträge", ("6400", "6420", "6430")),
    ("fahrzeug", "Auto", ("6520", "6530", "6531", "6540")),
    ("werbung", "Werbung, Bewirtung und Reisen", ("6600", "6605", "6610",
                                                  "6640", "6673")),
    ("abschreibung", "Abschreibungen", ("6220", "6221", "6222", "6260",
                                        "0670")),
    ("instandhaltung", "Reparatur und Wartung", ("6470", "6495")),
    ("beratung", "Beratung und Buchführung", ("6825", "6827", "6830")),
    ("buero", "Büro, Technik und Fortbildung", ("6800", "6805", "6810",
                                                "6815", "6820", "6821",
                                                "6837", "6840", "6845")),
    ("sonstiges", "Sonstiges", ("6300", "6850", "6855")),
]

# Kein Aufwand — diese Konten gehören NICHT in die Kostenseite.
#
# Sie landeten bisher stillschweigend unter „Sonstiges" und drückten damit
# das Ergebnis: eine Privatentnahme ist keine Ausgabe des Betriebs, Geld
# zwischen eigenen Konten schon gar nicht, und die Umsatzsteuer ist in der
# Netto-Rechnung der BWA bereits aus den Erlösen heraus. Anlagevermögen
# wirkt nur über die Abschreibung, nicht mit dem Kaufpreis.
NEUTRALE_KONTEN = ("1360", "1460", "2100", "2150", "2180", "3820", "3840",
                   "0400", "0650", "0675")

# Umsatzsteuer-Kennziffern der Voranmeldung (Formular UStVA).
KENNZIFFERN = {
    "81": "Umsätze zu 19 %",
    "86": "Umsätze zu 7 %",
    "48": "Steuerfreie Umsätze (§ 4 Nr. 14)",
    "66": "Vorsteuer aus Rechnungen",
    "83": "Das zahlst du (oder bekommst zurück)",
}


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


def erloese_monat(kassenblaetter: list[dict], monat: str | None = None,
                  rechnungen: list[dict] | None = None,
                  versteuerung: str = "ist") -> dict:
    """Erlöse eines Monats — aus der Ladenkasse UND aus gestellten Rechnungen.

    Was nicht gefragt wurde, ist 19 % — der Normalfall. Eingelöste
    Gutscheine sind KEIN Umsatz (versteuert wurde beim Verkauf),
    verkaufte Gutscheine dagegen schon (Einzweck-Gutschein).

    Rechnungen zählen je nach Versteuerungsart in einem anderen Monat:
    bei `ist` (§ 20 UStG, Normalfall, und was die EÜR verlangt), wenn das
    Geld ankommt — bei `soll` mit dem Rechnungsdatum. Beide Quellen bleiben
    getrennt ausgewiesen (`aus_kasse` / `aus_rechnungen`), damit sichtbar
    ist, woher der Umsatz kam.
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
    aus_kasse = _rund(neunzehn + sieben + frei)

    # Rechnungen dazu — nur die, die in DIESEM Monat zählen.
    import rechnungen as _re  # noqa: PLC0415 — reine Rechnung, kein I/O
    r_neunzehn = r_sieben = r_frei = r_gesamt = offen = 0.0
    for r in (rechnungen or []):
        if not isinstance(r, dict):
            continue
        if _re.stand(r) == "offen":
            offen += float(r.get("brutto") or 0)
        if monat is None or _re.zaehlt_im_monat(r, versteuerung) != monat:
            continue
        for s_ in (r.get("saetze") or []):
            brutto_satz = float(s_["netto"]) + float(s_["ust"])
            if int(s_["satz"]) == 7:
                r_sieben += brutto_satz
            else:
                r_neunzehn += brutto_satz
        if not (r.get("saetze") or []):
            # Kleinunternehmerin: kein Steuerausweis, aber Umsatz.
            r_frei += float(r.get("brutto") or 0)
        r_gesamt += float(r.get("brutto") or 0)

    neunzehn += r_neunzehn
    sieben += r_sieben
    frei += r_frei
    return {
        "tage": len(kassenblaetter),
        "bar": _rund(bar), "karte": _rund(ec),
        "brutto_19": _rund(neunzehn), "brutto_7": _rund(sieben),
        "steuerfrei": _rund(frei),
        "gutschein_verkauft": _rund(gutschein_verkauf),
        "gutschein_eingeloest": _rund(gutschein_eingeloest),
        "aus_kasse": aus_kasse,
        "aus_rechnungen": _rund(r_gesamt),
        "offen": _rund(offen),
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
        # Gutschrift/Erstattung mindert die Vorsteuer — sie trägt ihr
        # Minus seit 27.08.2026 schon in den Beträgen (gemma_buchung setzt
        # es beim Buchen). Hier NICHT noch einmal drehen.
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


def _monatsgrenzen(monat: str) -> tuple[str, str]:
    """Erster und letzter Tag eines Monats als JJJJ-MM-TT."""
    jahr, mon = int(monat[:4]), int(monat[5:7])
    if mon == 12:
        naechster = f"{jahr + 1}-01-01"
    else:
        naechster = f"{jahr}-{mon + 1:02d}-01"
    import datetime as dt  # noqa: PLC0415
    letzter = (dt.date.fromisoformat(naechster) - dt.timedelta(days=1)).isoformat()
    return f"{monat}-01", letzter


def vertraege_fuer_monat(vertraege: list[dict], monat: str) -> tuple[list[dict], list[str]]:
    """Welche Verträge gelten in diesem Monat — und was daran unklar ist.

    Drei Dinge würden die Auswertung sonst verfälschen:

    * Ein Vertrag, der erst später beginnt, kostet heute noch nichts.
    * Ein abgelaufener Vertrag kostet vielleicht nichts mehr — vielleicht
      läuft er aber stillschweigend weiter. Er wird nicht mitgerechnet,
      aber die Auswertung sagt es, statt still zu entscheiden.
    * Von zwei Verträgen fürs selbe Konto (alter und neuer Mietvertrag)
      gilt nur der jüngere, sonst zählt die Miete doppelt.
    """
    erster, letzter = _monatsgrenzen(monat)
    gueltig: dict[str, dict] = {}
    hinweise: list[str] = []

    for v in (vertraege or []):
        konto = v.get("konto_skr04")
        if not konto or not v.get("betrag_monat"):
            continue
        beginn = (v.get("beginn") or "")[:10]
        bis = (v.get("laufzeit_bis") or "")[:10]
        if beginn and beginn > letzter:
            continue                       # fängt erst später an
        if bis and bis < erster:
            wer = v.get("partner") or v.get("art_name") or "Ein Vertrag"
            hinweise.append(
                f"{wer}: Der Vertrag lief bis {_datum_deutsch(bis)} und ist hier "
                f"nicht mitgerechnet. Läuft er weiter, sag kurz Bescheid.")
            continue
        vorher = gueltig.get(konto)
        if vorher is None or beginn >= (vorher.get("beginn") or ""):
            gueltig[konto] = v             # der jüngere gewinnt
    return list(gueltig.values()), hinweise


def _datum_deutsch(iso: str) -> str:
    teile = iso.split("-")
    return f"{teile[2]}.{teile[1]}.{teile[0]}" if len(teile) == 3 else iso


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
    neutral: list[dict] = []
    for b in belege:
        if b.get("brutto") is None:
            continue
        konto = b.get("konto_skr04") or ""
        if konto in NEUTRALE_KONTEN:
            # Privatentnahme, Geldtransit, Umsatzsteuer, Anlagenkauf: sie
            # sind kein Aufwand. Sichtbar bleiben sie trotzdem — still
            # weglassen wäre so irreführend wie falsch mitzählen.
            neutral.append({"lieferant": b.get("lieferant"),
                            "brutto": b.get("brutto"), "konto": konto})
            continue
        ust = float(b.get("ust") or 0)
        netto = float(b.get("netto") or 0) or (float(b.get("brutto")) - ust)
        schluessel, name = zuordnung.get(konto, ("sonstiges", "Sonstiges"))
        e = eimer.setdefault(schluessel, {"schluessel": schluessel, "name": name,
                                          "netto": 0.0, "anzahl": 0})
        e["netto"] += netto
        e["anzahl"] += 1
        kosten_gesamt += netto
    # Dauerkosten aus Verträgen (Miete, Versicherung, Leasing): Sie gelten
    # nur, wenn für dasselbe Konto KEIN Beleg im Monat liegt — sonst würde
    # die Miete doppelt zählen.
    dauer, vertragshinweise = vertraege_fuer_monat(vertraege or [], monat)
    if personal_monat:
        # Die Löhne kommen schon aus „Dein Team" — ein zusätzlich abgelegter
        # Arbeitsvertrag würde sie ein zweites Mal aufschlagen.
        dauer = [v for v in dauer
                 if zuordnung.get(v.get("konto_skr04") or "", ("", ""))[0] != "personal"]
    for v in dauer:
        betrag = v.get("betrag_monat")
        konto = v.get("konto_skr04")
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
    fehlt: list[str] = list(vertragshinweise)
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
        "neutral": neutral,
        "neutral_summe": _rund(sum(float(n["brutto"] or 0) for n in neutral)),
        "fehlt": fehlt,
        "hinweis": "Vorläufig — aus deinen Belegen und deinem Kassenbuch "
                   "gerechnet, noch nicht von der Buchhaltung geprüft.",
    }
    if vorjahr and vorjahr.get("umsatz"):
        monatlich = float(vorjahr["umsatz"]) / 12
        d["vorjahr_monat"] = _rund(monatlich)
        d["vorjahr_delta"] = _rund(umsatz - monatlich)
    return d
