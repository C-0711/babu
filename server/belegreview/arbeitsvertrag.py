"""Arbeitsverträge — aus wenigen Angaben ein vollständiger Vertrag.

Nina soll keine Vorlage mehr suchen, kopieren und von Hand anpassen. Sie
sagt, wen sie einstellt und wozu; alles andere folgt daraus: die richtige
Vertragsart, die Klauseln, die Anlagen, die Belehrungen, der Urlaubsanspruch,
die Kündigungsfristen — und die Prüfung, ob das Ganze überhaupt zulässig ist.

Drei Dinge, die den Aufbau erklären:

**Klauseln statt Vorlagen.** Es gibt nicht sechs Musterverträge, die
auseinanderdriften, sobald sich ein Gesetz ändert, sondern eine Bibliothek
von Klauseln mit Bedingungen. Ein Minijob-Vertrag ist derselbe Vertrag ohne
die Klauseln, die nicht passen, plus die, die nur dort gelten. Ändert sich
der Mindestlohn, ändert sich eine Zahl an einer Stelle.

**Rechnen statt eintragen.** Urlaubstage, Kündigungsfristen, die
Minijob-Grenze, die Höchstarbeitszeit für Jugendliche — das alles ergibt
sich aus dem Gesetz und den Eckdaten. Wer es eintippen lässt, bekommt
Tippfehler in Verträgen.

**Nein sagen können.** Ein Vertrag unter Mindestlohn, ein Minijob über der
Grenze, eine Probezeit über sechs Monate: babu erzeugt so etwas nicht. Ein
freundlicher Hinweis am Ende eines PDF hilft niemandem.

Reine Rechnung ohne I/O. Wohin der fertige Vertrag geht, entscheidet
`babu_web` — und zwar in die Belegbox, denn ein Arbeitsvertrag ist
aufbewahrungspflichtig.

Rechtsstand 22.08.2026. Die Zahlen, die sich jährlich ändern, stehen
gesammelt in `WERTE` — das ist die einzige Stelle, die zum Jahreswechsel
angefasst werden muss.
"""
from __future__ import annotations

import datetime as dt

# ———————————————————————————————————————————————————————————————
# Was sich jedes Jahr ändert — gesammelt an einer Stelle
# ———————————————————————————————————————————————————————————————

WERTE = {
    2025: {"mindestlohn": 12.82, "minijob": 556, "azubi": 682},
    2026: {"mindestlohn": 13.90, "minijob": 603, "azubi": 724},
    2027: {"mindestlohn": 14.60, "minijob": 633, "azubi": 724},  # azubi offen
}

# § 17 Abs. 2 BBiG: die Mindestvergütung steigt mit dem Ausbildungsjahr.
AZUBI_STEIGERUNG = {1: 1.00, 2: 1.18, 3: 1.35, 4: 1.40}


def werte_fuer(datum: dt.date) -> dict:
    """Die Grenzen, die am Eintrittstag gelten.

    Für Jahre nach der letzten bekannten Fassung gilt der letzte bekannte
    Wert — mit einem Hinweis, siehe `pruefen`. Stillschweigend mit einem
    veralteten Mindestlohn zu rechnen wäre der schlechtere Fehler.
    """
    jahre = sorted(WERTE)
    jahr = datum.year if datum.year in WERTE else (
        jahre[0] if datum.year < jahre[0] else jahre[-1])
    return {**WERTE[jahr], "jahr": jahr, "geschaetzt": datum.year not in WERTE}


class VertragFehler(ValueError):
    """So ließe sich der Vertrag nicht schließen."""


# ———————————————————————————————————————————————————————————————
# Die Beschäftigungsarten
# ———————————————————————————————————————————————————————————————

ARTEN = {
    "vollzeit": {
        "name": "Festanstellung in Vollzeit",
        "sv": "voll sozialversicherungspflichtig",
        "melden": "Krankenkasse der Arbeitnehmerin",
    },
    "teilzeit": {
        "name": "Festanstellung in Teilzeit",
        "sv": "voll sozialversicherungspflichtig",
        "melden": "Krankenkasse der Arbeitnehmerin",
    },
    "minijob": {
        "name": "Geringfügige Beschäftigung",
        "sv": "geringfügig entlohnt, pauschale Abgaben",
        "melden": "Minijob-Zentrale (Knappschaft-Bahn-See)",
    },
    "kurzfristig": {
        "name": "Kurzfristige Beschäftigung",
        "sv": "sozialversicherungsfrei bei Einhaltung der Zeitgrenzen",
        "melden": "Minijob-Zentrale (Knappschaft-Bahn-See)",
    },
    "werkstudent": {
        "name": "Werkstudentin",
        "sv": "nur rentenversicherungspflichtig (Werkstudentenprivileg)",
        "melden": "Krankenkasse der Arbeitnehmerin",
    },
    "ausbildung": {
        "name": "Berufsausbildung",
        "sv": "voll sozialversicherungspflichtig",
        "melden": "Krankenkasse; zusätzlich Eintragung bei der Handwerkskammer",
    },
}

# Kein Arbeitsvertrag — steht hier, damit babu warnen kann statt zu liefern.
KEINE_ANSTELLUNG = {
    "freie_mitarbeit": (
        "Freie Mitarbeit und Stuhlmiete sind kein Arbeitsverhältnis. Wer "
        "Arbeitszeit, Ort und Ablauf vorgibt, beschäftigt tatsächlich "
        "abhängig — das ist Scheinselbständigkeit, und die Beiträge werden "
        "rückwirkend nachgefordert, oft für Jahre. Im Friseurhandwerk ist "
        "das der häufigste teure Irrtum. babu erzeugt "
        "dafür keinen Vertrag; kläre das vorher über ein Statusfeststellungs"
        "verfahren bei der Deutschen Rentenversicherung."),
}


# ———————————————————————————————————————————————————————————————
# Was sich ausrechnen lässt, statt es abzufragen
# ———————————————————————————————————————————————————————————————

def urlaub_mindestens(tage_woche: float, alter_bei_eintritt: int | None = None) -> int:
    """Der gesetzliche Mindesturlaub in Arbeitstagen.

    § 3 BUrlG rechnet in Werktagen bei Sechstagewoche: 24. Wer an weniger
    Tagen arbeitet, bekommt anteilig — vier Wochen bleiben vier Wochen.
    Für Jugendliche gilt § 19 JArbSchG mit mehr Tagen, gestaffelt nach
    Alter zu Beginn des Kalenderjahres.
    """
    if tage_woche <= 0:
        raise VertragFehler("An wie vielen Tagen pro Woche wird gearbeitet?")
    werktage = 24
    if alter_bei_eintritt is not None:
        if alter_bei_eintritt < 16:
            werktage = 30
        elif alter_bei_eintritt < 17:
            werktage = 27
        elif alter_bei_eintritt < 18:
            werktage = 25
    # Auf ganze Tage aufrunden: abrunden hieße, unter das Minimum zu gehen.
    import math
    return math.ceil(werktage / 6 * min(tage_woche, 6))


def kuendigungsfrist_probezeit() -> str:
    return "zwei Wochen"        # § 622 Abs. 3 BGB


def kuendigungsfrist_regulaer(monate_beschaeftigt: int = 0) -> str:
    """§ 622 BGB — die Frist verlängert sich mit der Betriebszugehörigkeit.

    Die Staffel gilt für die Kündigung durch den Arbeitgeber; für die
    Arbeitnehmerin bleibt es bei vier Wochen, wenn nichts anderes
    vereinbart ist.
    """
    jahre = monate_beschaeftigt // 12
    staffel = [(20, "sieben Monate zum Monatsende"),
               (15, "sechs Monate zum Monatsende"),
               (12, "fünf Monate zum Monatsende"),
               (10, "vier Monate zum Monatsende"),
               (8, "drei Monate zum Monatsende"),
               (5, "zwei Monate zum Monatsende"),
               (2, "einen Monat zum Monatsende")]
    for grenze, frist in staffel:
        if jahre >= grenze:
            return frist
    return "vier Wochen zum 15. oder zum Ende eines Kalendermonats"


def monatsentgelt(stundenlohn: float, stunden_woche: float) -> float:
    """Aus Stundenlohn ein Monatsentgelt — mit 13/3 Wochen je Monat.

    52 Wochen auf 12 Monate ergibt 4,3333 Wochen. Wer mit 4 rechnet, bleibt
    unter dem Mindestlohn, sobald ein Monat fünf Zahltage hat.
    """
    return round(stundenlohn * stunden_woche * 13 / 3, 2)


def stundenlohn_aus(entgelt: float, stunden_woche: float) -> float:
    if stunden_woche <= 0:
        raise VertragFehler("Wie viele Stunden pro Woche sind vereinbart?")
    return round(entgelt / (stunden_woche * 13 / 3), 2)


def alter_am(geburtsdatum: dt.date | None, stichtag: dt.date) -> int | None:
    if not geburtsdatum:
        return None
    jahre = stichtag.year - geburtsdatum.year
    if (stichtag.month, stichtag.day) < (geburtsdatum.month, geburtsdatum.day):
        jahre -= 1
    return jahre


# ———————————————————————————————————————————————————————————————
# Die Form: Papier oder nicht
# ———————————————————————————————————————————————————————————————

def form_erforderlich(angaben: dict) -> dict:
    """Reicht Textform, oder muss unterschrieben werden?

    Seit dem 1.1.2025 genügt für den Nachweis der wesentlichen
    Arbeitsbedingungen die Textform (§ 2 NachwG i. V. m. § 126b BGB) — der
    Vertrag kann also digital geschlossen werden. Drei Ausnahmen bleiben,
    und sie entscheiden darüber, ob Nina drucken muss.
    """
    if angaben.get("befristet_bis"):
        return {"form": "schriftform",
                "grund": "Eine Befristung braucht Schriftform (§ 14 Abs. 4 "
                         "TzBfG). Fehlt sie, ist nicht der Vertrag unwirksam, "
                         "sondern die Befristung — und das Arbeitsverhältnis "
                         "läuft unbefristet weiter.",
                "ausweg": "Unbefristet mit Probezeit vereinbaren — dann geht "
                          "der Vertrag rein digital."}
    if angaben.get("art") == "ausbildung":
        return {"form": "schriftform",
                "grund": "Der Berufsausbildungsvertrag muss vor Beginn "
                         "schriftlich niedergelegt und bei der Handwerkskammer "
                         "in die Lehrlingsrolle eingetragen werden.",
                "ausweg": None}
    if angaben.get("schriftform_gewuenscht"):
        return {"form": "schriftform",
                "grund": "Die Arbeitnehmerin hat Schriftform verlangt — dann "
                         "ist sie unverzüglich auszuhändigen (§ 2 Abs. 1 "
                         "Satz 4 NachwG).",
                "ausweg": None}
    return {"form": "textform",
            "grund": "Textform genügt (§ 2 NachwG, § 126b BGB). Der Vertrag "
                     "kann in der App gelesen und angenommen werden.",
            "ausweg": None}


# ———————————————————————————————————————————————————————————————
# Prüfen, bevor irgendetwas erzeugt wird
# ———————————————————————————————————————————————————————————————

def _datum(wert, feld: str) -> dt.date:
    if isinstance(wert, dt.date):
        return wert
    try:
        return dt.date.fromisoformat(str(wert)[:10])
    except (TypeError, ValueError):
        raise VertragFehler(f"{feld} können wir nicht lesen (JJJJ-MM-TT).")


def pruefen(roh: dict) -> dict:
    """Die Angaben auf Brauchbarkeit prüfen und ergänzen.

    Wirft, wo ein Vertrag rechtswidrig wäre. Sammelt Hinweise, wo er
    zulässig, aber erklärungsbedürftig ist.
    """
    roh = roh if isinstance(roh, dict) else {}
    art = str(roh.get("art") or "").strip().lower()
    if art in KEINE_ANSTELLUNG:
        raise VertragFehler(KEINE_ANSTELLUNG[art])
    if art not in ARTEN:
        raise VertragFehler("Welche Art der Beschäftigung? Möglich sind: "
                            + ", ".join(ARTEN))

    eintritt = _datum(roh.get("eintritt"), "Das Eintrittsdatum")
    geburtsdatum = (_datum(roh["geburtsdatum"], "Das Geburtsdatum")
                    if roh.get("geburtsdatum") else None)
    alter = alter_am(geburtsdatum, eintritt)

    try:
        stunden = float(roh.get("stunden_woche") or 0)
        tage = float(roh.get("tage_woche") or 0)
    except (TypeError, ValueError):
        raise VertragFehler("Stunden und Tage bitte als Zahl.")
    if stunden <= 0:
        raise VertragFehler("Wie viele Stunden pro Woche sind vereinbart?")
    if tage <= 0:
        tage = min(5, max(1, round(stunden / 8)))       # plausibel schätzen
    if stunden > 48:
        raise VertragFehler("Mehr als 48 Stunden je Woche lässt das "
                            "Arbeitszeitgesetz im Durchschnitt nicht zu "
                            "(§ 3 ArbZG).")

    werte = werte_fuer(eintritt)
    befunde: list[dict] = []
    if werte["geschaetzt"]:
        befunde.append({"art": "hinweis", "text":
            f"Für {eintritt.year} sind die Werte noch nicht hinterlegt — "
            f"gerechnet wird mit denen von {werte['jahr']}. Vor dem Eintritt "
            "prüfen."})

    # Entgelt: entweder Monatslohn oder Stundenlohn, das jeweils andere folgt.
    entgelt = roh.get("entgelt")
    stundenlohn = roh.get("stundenlohn")
    if entgelt in (None, "") and stundenlohn in (None, ""):
        raise VertragFehler("Was wird bezahlt — Monatsgehalt oder Stundenlohn?")
    if entgelt not in (None, ""):
        entgelt = round(float(entgelt), 2)
        stundenlohn = stundenlohn_aus(entgelt, stunden)
    else:
        stundenlohn = round(float(stundenlohn), 2)
        entgelt = monatsentgelt(stundenlohn, stunden)

    # ————— Was babu nicht erzeugt —————
    #
    # Der Mindestlohn gilt nicht ausnahmslos (§ 22 MiLoG). Auszubildende
    # fallen heraus — für sie gilt die Mindestausbildungsvergütung nach
    # § 17 BBiG, die deutlich niedriger liegt. Und Jugendliche ohne
    # abgeschlossene Berufsausbildung ebenfalls. Wer das übersieht, lehnt
    # zulässige Verträge ab; wer es zu weit auslegt, drückt Löhne.

    lehrjahr = int(roh.get("ausbildungsjahr") or 1)
    if art == "ausbildung":
        if lehrjahr not in AZUBI_STEIGERUNG:
            raise VertragFehler("Das Ausbildungsjahr liegt zwischen 1 und 4.")
        mindest_azubi = round(werte["azubi"] * AZUBI_STEIGERUNG[lehrjahr])
        if entgelt < mindest_azubi:
            raise VertragFehler(
                f"Die Mindestausbildungsvergütung liegt im {lehrjahr}. "
                f"Ausbildungsjahr bei {mindest_azubi} € im Monat "
                f"(§ 17 BBiG, Stand {werte['jahr']}); hier wären es "
                f"{entgelt:.2f} €.")
        befunde.append({"art": "hinweis", "text":
            "Auszubildende fallen nicht unter den Mindestlohn (§ 22 Abs. 3 "
            f"MiLoG). Maßgeblich ist die Mindestausbildungsvergütung von "
            f"{mindest_azubi} € — ein einschlägiger Tarifvertrag kann mehr "
            "vorsehen."})
    elif (alter is not None and alter < 18
          and not roh.get("berufsausbildung_abgeschlossen")):
        befunde.append({"art": "hinweis", "text":
            "Unter 18 ohne abgeschlossene Berufsausbildung gilt der "
            "Mindestlohn nicht (§ 22 Abs. 2 MiLoG). Das ist eine Ausnahme "
            "zugunsten der Ausbildung, kein Freibrief — angemessen muss die "
            "Vergütung trotzdem sein."})
    elif stundenlohn < werte["mindestlohn"]:
        raise VertragFehler(
            f"Das wären {stundenlohn:.2f} € je Stunde. Der Mindestlohn liegt "
            f"{werte['jahr']} bei {werte['mindestlohn']:.2f} €. Bei "
            f"{stunden:g} Stunden je Woche sind mindestens "
            f"{monatsentgelt(werte['mindestlohn'], stunden):.2f} € im Monat "
            "nötig.")

    if art == "minijob" and entgelt > werte["minijob"]:
        raise VertragFehler(
            f"Ein Minijob endet {werte['jahr']} bei {werte['minijob']} € im "
            f"Monat; hier wären es {entgelt:.2f} €. Entweder die Stunden "
            f"senken (höchstens {werte['minijob'] / (stundenlohn * 13 / 3):.1f} "
            "je Woche) oder als Teilzeit anmelden.")

    if art == "werkstudent" and stunden > 20:
        befunde.append({"art": "warnung", "text":
            "Über 20 Stunden je Woche entfällt das Werkstudentenprivileg in "
            "der Vorlesungszeit — dann wird die Stelle voll "
            "sozialversicherungspflichtig."})

    probezeit = int(roh.get("probezeit_monate", 6) or 0)
    if probezeit > 6:
        raise VertragFehler("Eine Probezeit von mehr als sechs Monaten ist "
                            "nicht zulässig (§ 622 Abs. 3 BGB).")

    befristet_bis = (_datum(roh["befristet_bis"], "Das Befristungsende")
                     if roh.get("befristet_bis") else None)
    if befristet_bis and befristet_bis <= eintritt:
        raise VertragFehler("Das Befristungsende liegt vor dem Eintritt.")
    if befristet_bis and probezeit:
        dauer_monate = (befristet_bis.year - eintritt.year) * 12 + \
                       befristet_bis.month - eintritt.month
        if probezeit > max(1, dauer_monate // 4):
            befunde.append({"art": "warnung", "text":
                "Bei einem befristeten Vertrag muss die Probezeit im "
                "Verhältnis zur Laufzeit stehen (§ 15 Abs. 3 TzBfG). Ein "
                "Viertel der Laufzeit ist ein brauchbarer Anhalt."})

    # ————— Jugendliche —————

    if alter is not None and alter < 18:
        if stunden > 40:
            raise VertragFehler("Für Jugendliche sind höchstens 40 Stunden je "
                                "Woche zulässig (§ 8 JArbSchG).")
        if tage > 5:
            raise VertragFehler("Jugendliche dürfen an höchstens fünf Tagen "
                                "je Woche beschäftigt werden (§ 15 JArbSchG).")
        befunde.append({"art": "hinweis", "text":
            "Unter 18: Das Jugendarbeitsschutzgesetz gilt — längere "
            "Urlaubsansprüche, feste Ruhezeiten, keine Nachtarbeit. Vor "
            "Beginn ist eine ärztliche Erstuntersuchung nachzuweisen "
            "(§ 32 JArbSchG)."})

    if art == "kurzfristig":
        befunde.append({"art": "hinweis", "text":
            "Kurzfristig heißt: höchstens drei Monate oder 70 Arbeitstage im "
            "Kalenderjahr und nicht berufsmäßig ausgeübt. Wird eine der "
            "Grenzen gerissen, wird die Beschäftigung rückwirkend "
            "beitragspflichtig."})

    urlaub = int(roh.get("urlaubstage") or 0)
    mindest = urlaub_mindestens(tage, alter)
    if urlaub and urlaub < mindest:
        raise VertragFehler(
            f"{urlaub} Urlaubstage sind zu wenig. Bei {tage:g} Arbeitstagen "
            f"je Woche stehen mindestens {mindest} Tage zu (§ 3 BUrlG"
            + (", § 19 JArbSchG" if alter is not None and alter < 18 else "")
            + ").")

    return {
        "art": art,
        "ausbildungsjahr": lehrjahr if art == "ausbildung" else None,
        "eintritt": eintritt,
        "geburtsdatum": geburtsdatum,
        "alter_bei_eintritt": alter,
        "befristet_bis": befristet_bis,
        "probezeit_monate": probezeit,
        "stunden_woche": stunden,
        "tage_woche": tage,
        "entgelt": entgelt,
        "stundenlohn": stundenlohn,
        "urlaubstage": urlaub or mindest,
        "urlaub_mindestens": mindest,
        "taetigkeit": str(roh.get("taetigkeit") or "").strip()[:120]
                      or "Friseurin",
        "arbeitsort": str(roh.get("arbeitsort") or "").strip()[:120],
        "schriftform_gewuenscht": bool(roh.get("schriftform_gewuenscht")),
        "werte": werte,
        "befunde": befunde,
    }


# ———————————————————————————————————————————————————————————————
# Die Klauselbibliothek
# ———————————————————————————————————————————————————————————————
#
# Jede Klausel weiß selbst, wann sie gilt. `wenn` bekommt die geprüften
# Angaben und antwortet mit ja oder nein; fehlt sie, gilt die Klausel immer.
# `nachweis` nennt die Pflichtangabe nach § 2 NachwG, die sie abdeckt —
# daran prüft `pflichtangaben_fehlen`, ob der Vertrag vollständig ist.

def _euro(wert: float) -> str:
    return f"{wert:,.2f} €".replace(",", "#").replace(".", ",").replace("#", ".")


def _tag(datum: dt.date) -> str:
    return datum.strftime("%d.%m.%Y")


KLAUSELN: list[dict] = [
    {
        "id": "beginn",
        "titel": "Beginn des Arbeitsverhältnisses",
        "nachweis": ["beginn"],
        "text": lambda a, b: (
            f"Das Arbeitsverhältnis beginnt am {_tag(a['eintritt'])}."
            + (f" Es ist befristet bis zum {_tag(a['befristet_bis'])} und "
               "endet zu diesem Zeitpunkt, ohne dass es einer Kündigung "
               "bedarf." if a["befristet_bis"] else " Es wird auf unbestimmte "
               "Zeit geschlossen.")),
    },
    {
        "id": "probezeit",
        "titel": "Probezeit",
        "wenn": lambda a: a["probezeit_monate"] > 0,
        "nachweis": ["probezeit"],
        "text": lambda a, b: (
            f"Die ersten {a['probezeit_monate']} Monate gelten als Probezeit. "
            f"Während der Probezeit kann das Arbeitsverhältnis beiderseits mit "
            f"einer Frist von {kuendigungsfrist_probezeit()} gekündigt werden "
            "(§ 622 Abs. 3 BGB)."),
    },
    {
        "id": "taetigkeit",
        "titel": "Tätigkeit",
        "nachweis": ["taetigkeit"],
        "text": lambda a, b: (
            f"Die Arbeitnehmerin wird als {a['taetigkeit']} eingestellt. Zu "
            "den Aufgaben gehören die im Friseurhandwerk üblichen Tätigkeiten "
            "einschließlich Beratung, Bedienung der Kasse und Pflege des "
            "Arbeitsplatzes. Der Arbeitgeber kann ihr andere, gleichwertige "
            "Aufgaben zuweisen, die ihrer Ausbildung und Erfahrung "
            "entsprechen."),
    },
    {
        "id": "arbeitsort",
        "titel": "Arbeitsort",
        "nachweis": ["arbeitsort"],
        "text": lambda a, b: (
            f"Arbeitsort ist {a['arbeitsort'] or b.get('ort') or 'der Betrieb'}"
            ". Ein Einsatz an einem anderen Ort des Betriebes ist nach "
            "vorheriger Ankündigung möglich."),
    },
    {
        "id": "arbeitszeit",
        "titel": "Arbeitszeit",
        "nachweis": ["arbeitszeit", "ruhepausen", "schichten"],
        "text": lambda a, b: (
            f"Die regelmäßige wöchentliche Arbeitszeit beträgt "
            f"{a['stunden_woche']:g} Stunden, verteilt auf "
            f"{a['tage_woche']:g} Arbeitstage. Lage und Verteilung werden im "
            "Dienstplan festgelegt und rechtzeitig bekannt gegeben.\n\n"
            "Die Ruhepausen betragen bei einer Arbeitszeit von mehr als sechs "
            "Stunden mindestens 30 Minuten, bei mehr als neun Stunden "
            "mindestens 45 Minuten (§ 4 ArbZG). Zwischen zwei Arbeitstagen "
            "liegt eine ununterbrochene Ruhezeit von mindestens elf Stunden "
            "(§ 5 ArbZG).\n\n"
            "Beginn, Ende und Dauer der täglichen Arbeitszeit werden "
            "aufgezeichnet. Die Arbeitnehmerin bestätigt die Aufzeichnung "
            "arbeitstäglich in der vom Arbeitgeber bereitgestellten Anwendung."),
    },
    {
        "id": "arbeitszeit_jugend",
        "titel": "Besondere Arbeitszeiten für Jugendliche",
        "wenn": lambda a: (a["alter_bei_eintritt"] is not None
                           and a["alter_bei_eintritt"] < 18),
        "text": lambda a, b: (
            "Für die Arbeitnehmerin gilt das Jugendarbeitsschutzgesetz. Die "
            "tägliche Arbeitszeit beträgt höchstens acht Stunden, die "
            "wöchentliche höchstens 40 Stunden an höchstens fünf Tagen. "
            "Nachtarbeit, Sonn- und Feiertagsarbeit sind nur in den engen "
            "Grenzen des Gesetzes zulässig."),
    },
    {
        "id": "mehrarbeit",
        "titel": "Mehrarbeit",
        "text": lambda a, b: (
            "Mehrarbeit wird nur geleistet, wenn sie angeordnet oder "
            "ausdrücklich vereinbart ist. Sie wird vorrangig durch Freizeit "
            "ausgeglichen; ist das aus betrieblichen Gründen nicht möglich, "
            "wird sie mit dem vereinbarten Stundensatz vergütet. Eine "
            "pauschale Abgeltung von Mehrarbeit ist nicht vereinbart."),
    },
    {
        "id": "verguetung",
        "titel": "Vergütung",
        "nachweis": ["entgelt", "entgelt_zusammensetzung", "faelligkeit"],
        "text": lambda a, b: (
            f"Die Arbeitnehmerin erhält ein monatliches Bruttoentgelt von "
            f"{_euro(a['entgelt'])}. Das entspricht bei "
            f"{a['stunden_woche']:g} Wochenstunden einem Stundensatz von "
            f"{_euro(a['stundenlohn'])} und liegt damit über dem gesetzlichen "
            f"Mindestlohn von {_euro(a['werte']['mindestlohn'])} "
            f"({a['werte']['jahr']}).\n\n"
            "Weitere Entgeltbestandteile, Zuschläge oder Zulagen sind nicht "
            "vereinbart. Das Entgelt ist zum Ende des Kalendermonats fällig "
            "und wird bargeldlos auf ein von der Arbeitnehmerin benanntes "
            "Konto überwiesen.\n\n"
            "Beginnt oder endet das Arbeitsverhältnis innerhalb eines Monats, "
            "wird das Entgelt anteilig nach Kalendertagen gezahlt."),
    },
    {
        "id": "minijob_rv",
        "titel": "Rentenversicherung bei geringfügiger Beschäftigung",
        "wenn": lambda a: a["art"] == "minijob",
        "text": lambda a, b: (
            "Die Beschäftigung ist geringfügig entlohnt. Sie ist "
            "rentenversicherungspflichtig; die Arbeitnehmerin trägt den "
            "Eigenanteil. Sie kann sich auf Antrag von der Versicherungs"
            "pflicht befreien lassen. Der Antrag ist dem Arbeitgeber "
            "schriftlich vorzulegen und wirkt für die Dauer der "
            "Beschäftigung.\n\n"
            f"Das Entgelt darf {_euro(a['werte']['minijob'])} im Monat nicht "
            "überschreiten. Ein gelegentliches, nicht vorhersehbares "
            "Überschreiten ist in engen Grenzen unschädlich."),
    },
    {
        "id": "kurzfristig_grenzen",
        "titel": "Zeitgrenzen der kurzfristigen Beschäftigung",
        "wenn": lambda a: a["art"] == "kurzfristig",
        "text": lambda a, b: (
            "Die Beschäftigung ist von vornherein auf längstens drei Monate "
            "oder 70 Arbeitstage im Kalenderjahr begrenzt und wird nicht "
            "berufsmäßig ausgeübt. Die Arbeitnehmerin versichert, dem "
            "Arbeitgeber alle weiteren kurzfristigen Beschäftigungen dieses "
            "Kalenderjahres unaufgefordert mitzuteilen."),
    },
    {
        "id": "entgeltfortzahlung",
        "titel": "Entgeltfortzahlung im Krankheitsfall",
        "text": lambda a, b: (
            "Im Krankheitsfall wird das Entgelt nach dem "
            "Entgeltfortzahlungsgesetz für bis zu sechs Wochen "
            "fortgezahlt.\n\n"
            "Die Arbeitsunfähigkeit ist unverzüglich anzuzeigen. Die "
            "Bescheinigung ruft der Arbeitgeber elektronisch bei der "
            "Krankenkasse ab (eAU); die Arbeitnehmerin muss sie nicht "
            "einreichen. Sie ist jedoch verpflichtet, die Arbeitsunfähigkeit "
            "ärztlich feststellen zu lassen."),
    },
    {
        "id": "urlaub",
        "titel": "Urlaub",
        "nachweis": ["urlaub"],
        "text": lambda a, b: (
            f"Der Urlaubsanspruch beträgt {a['urlaubstage']} Arbeitstage im "
            f"Kalenderjahr bei {a['tage_woche']:g} Arbeitstagen je Woche. Der "
            f"gesetzliche Mindestanspruch liegt bei {a['urlaub_mindestens']} "
            "Tagen.\n\n"
            "Der Urlaub wird nach den betrieblichen Möglichkeiten und den "
            "Wünschen der Arbeitnehmerin festgelegt und über die vom "
            "Arbeitgeber bereitgestellte Anwendung beantragt. Er ist im "
            "laufenden Kalenderjahr zu nehmen; eine Übertragung bis zum "
            "31. März des Folgejahres ist bei betrieblichen oder in der "
            "Person liegenden Gründen möglich. Der Arbeitgeber weist "
            "rechtzeitig auf noch offene Urlaubstage hin."),
    },
    {
        "id": "nebentaetigkeit",
        "titel": "Nebentätigkeit",
        "text": lambda a, b: (
            "Eine Nebentätigkeit ist dem Arbeitgeber vor Aufnahme "
            "anzuzeigen. Er kann ihr widersprechen, wenn sie berechtigte "
            "betriebliche Interessen beeinträchtigt, insbesondere bei "
            "Wettbewerb, bei Überschreitung der zulässigen Höchstarbeitszeit "
            "oder bei Beeinträchtigung der Arbeitsleistung. Ein "
            "Zustimmungsvorbehalt besteht nicht."),
    },
    {
        "id": "verschwiegenheit",
        "titel": "Verschwiegenheit und Kundendaten",
        "text": lambda a, b: (
            "Die Arbeitnehmerin bewahrt über betriebliche Angelegenheiten "
            "Stillschweigen, insbesondere über Kundendaten, Farbformeln, "
            "Preise und Geschäftsbeziehungen. Kundendaten dürfen "
            "ausschließlich zu betrieblichen Zwecken und nur über die dafür "
            "vorgesehenen Anwendungen verarbeitet werden; das Anlegen "
            "eigener Listen, Kopien oder Fotos ist unzulässig.\n\n"
            "Die Pflicht besteht auch nach Ende des Arbeitsverhältnisses "
            "fort. Eine gesonderte Verpflichtung auf das Datengeheimnis wird "
            "als Anlage geschlossen."),
    },
    {
        "id": "arbeitsschutz",
        "titel": "Arbeits- und Hautschutz",
        "text": lambda a, b: (
            "Die Arbeitnehmerin hält die Arbeitsschutzvorschriften ein und "
            "nimmt an den Unterweisungen teil (§ 12 ArbSchG).\n\n"
            "Im Friseurhandwerk gilt besonders der Hautschutz nach TRGS 530. "
            "Der Arbeitgeber stellt Schutzhandschuhe, Haut- und "
            "Pflegemittel sowie einen Hautschutzplan bereit; die "
            "Arbeitnehmerin benutzt sie. Zuständiger Unfallversicherungs"
            "träger ist die Berufsgenossenschaft für Gesundheitsdienst und "
            "Wohlfahrtspflege (BGW)."),
    },
    {
        "id": "fortbildung",
        "titel": "Fortbildung",
        "nachweis": ["fortbildung"],
        "text": lambda a, b: (
            "Der Arbeitgeber ermöglicht Fortbildungen, soweit sie für die "
            "Tätigkeit erforderlich sind; die dafür aufgewendete Zeit gilt "
            "als Arbeitszeit und die Kosten trägt der Arbeitgeber.\n\n"
            "Übernimmt der Arbeitgeber darüber hinaus die Kosten einer "
            "Fortbildung, die der Arbeitnehmerin auch außerhalb des Betriebes "
            "nützt, kann eine Rückzahlung nur in einer gesonderten, vor "
            "Beginn geschlossenen Vereinbarung geregelt werden. Diese muss "
            "die Rückzahlung zeitanteilig abstufen."),
    },
    {
        "id": "kuendigung",
        "titel": "Beendigung des Arbeitsverhältnisses",
        "nachweis": ["kuendigung", "kuendigungsfristen", "klagefrist"],
        "text": lambda a, b: (
            "Nach Ablauf der Probezeit gilt für beide Seiten die "
            f"gesetzliche Kündigungsfrist von "
            f"{kuendigungsfrist_regulaer()}. Für den Arbeitgeber verlängert "
            "sie sich mit der Dauer der Betriebszugehörigkeit nach § 622 "
            "Abs. 2 BGB.\n\n"
            "Die Kündigung bedarf der Schriftform; die elektronische Form ist "
            "ausgeschlossen (§ 623 BGB). Dasselbe gilt für einen "
            "Aufhebungsvertrag.\n\n"
            "Will die Arbeitnehmerin geltend machen, dass eine Kündigung "
            "unwirksam ist, muss sie innerhalb von drei Wochen nach Zugang "
            "der schriftlichen Kündigung Klage beim Arbeitsgericht erheben "
            "(§ 4 KSchG). Andernfalls gilt die Kündigung als von Anfang an "
            "wirksam."),
    },
    {
        "id": "ausschlussfrist",
        "titel": "Ausschlussfristen",
        "text": lambda a, b: (
            "Ansprüche aus dem Arbeitsverhältnis verfallen, wenn sie nicht "
            "innerhalb von drei Monaten nach Fälligkeit in Textform geltend "
            "gemacht werden.\n\n"
            "Ausgenommen sind Ansprüche auf den gesetzlichen Mindestlohn, "
            "Ansprüche aus vorsätzlicher oder grob fahrlässiger Verletzung "
            "von Leben, Körper oder Gesundheit, Ansprüche aus vorsätzlichen "
            "Pflichtverletzungen sowie alle weiteren Ansprüche, auf die nach "
            "dem Gesetz nicht verzichtet werden kann."),
    },
    {
        "id": "tarif",
        "titel": "Tarifverträge und Betriebsvereinbarungen",
        "nachweis": ["tarif"],
        "text": lambda a, b: (
            "Auf das Arbeitsverhältnis findet kein Tarifvertrag Anwendung. "
            "Betriebsvereinbarungen bestehen nicht. Werden solche Regelungen "
            "künftig anwendbar, gelten sie in ihrer jeweiligen Fassung."),
    },
    {
        "id": "altersvorsorge",
        "titel": "Betriebliche Altersversorgung",
        "nachweis": ["altersversorgung"],
        "text": lambda a, b: (
            "Eine betriebliche Altersversorgung ist nicht zugesagt. Die "
            "Arbeitnehmerin kann Entgeltumwandlung nach § 1a BetrAVG "
            "verlangen; der Versorgungsträger wird dann gesondert benannt."),
    },
    {
        "id": "nebenabreden",
        "titel": "Änderungen und Nebenabreden",
        "text": lambda a, b: (
            "Änderungen und Ergänzungen dieses Vertrages werden in Textform "
            "festgehalten. Individuell ausgehandelte Abreden gelten auch ohne "
            "Einhaltung dieser Form."),
    },
    {
        "id": "salvatorisch",
        "titel": "Schlussbestimmung",
        "text": lambda a, b: (
            "Ist eine Bestimmung dieses Vertrages unwirksam, bleiben die "
            "übrigen wirksam. An die Stelle der unwirksamen Bestimmung tritt "
            "die gesetzliche Regelung."),
    },
]


# ———————————————————————————————————————————————————————————————
# Pflichtangaben nach § 2 NachwG
# ———————————————————————————————————————————————————————————————

PFLICHTANGABEN = {
    "parteien": "Name und Anschrift beider Vertragsparteien",
    "beginn": "Zeitpunkt des Beginns des Arbeitsverhältnisses",
    "befristung": "Enddatum bei befristeten Arbeitsverhältnissen",
    "arbeitsort": "Arbeitsort",
    "taetigkeit": "Beschreibung der Tätigkeit",
    "probezeit": "Dauer der Probezeit",
    "entgelt": "Höhe des Arbeitsentgelts",
    "entgelt_zusammensetzung": "Zusammensetzung des Entgelts, Zuschläge und Zulagen",
    "faelligkeit": "Fälligkeit und Art der Auszahlung",
    "arbeitszeit": "Vereinbarte Arbeitszeit",
    "ruhepausen": "Ruhepausen und Ruhezeiten",
    "schichten": "Schichtsystem und Schichtrhythmus, soweit vereinbart",
    "urlaub": "Dauer des jährlichen Erholungsurlaubs",
    "fortbildung": "Anspruch auf Fortbildung, soweit vorhanden",
    "altersversorgung": "Versorgungsträger bei betrieblicher Altersversorgung",
    "kuendigung": "Verfahren bei Kündigung, Schriftformerfordernis",
    "kuendigungsfristen": "Kündigungsfristen",
    "klagefrist": "Frist zur Erhebung der Kündigungsschutzklage",
    "tarif": "Hinweis auf anwendbare Tarifverträge und Betriebsvereinbarungen",
}


def pflichtangaben_fehlen(vertrag: dict) -> list[str]:
    """Welche Pflichtangabe deckt keine Klausel ab?

    Der Nachweis ist kein Formalismus: fehlt eine Angabe, kann das ein
    Bußgeld nach § 4 NachwG kosten, und im Streit gilt im Zweifel die
    Darstellung der Arbeitnehmerin.
    """
    abgedeckt = {"parteien"}                 # steht im Kopf, nicht in einem §
    for teil in vertrag.get("paragraphen", []):
        abgedeckt.update(teil.get("nachweis") or [])
    if not vertrag.get("angaben", {}).get("befristet_bis"):
        abgedeckt.add("befristung")
    if not vertrag.get("angaben", {}).get("probezeit_monate"):
        abgedeckt.add("probezeit")
    return [PFLICHTANGABEN[k] for k in PFLICHTANGABEN if k not in abgedeckt]


# ———————————————————————————————————————————————————————————————
# Anlagen und Belehrungen
# ———————————————————————————————————————————————————————————————

def anlagen_fuer(a: dict) -> list[dict]:
    """Was neben dem Vertrag noch unterschrieben oder bestätigt wird."""
    liste = [
        {"id": "datengeheimnis", "titel": "Verpflichtung auf das Datengeheimnis",
         "grund": "Art. 88 DSGVO, § 26 BDSG — Kundendaten, Farbformeln, Fotos",
         "pflicht": True},
        {"id": "arbeitsschutz", "titel": "Unterweisung Arbeitsschutz",
         "grund": "§ 12 ArbSchG, vor Aufnahme der Tätigkeit",
         "pflicht": True},
        {"id": "hautschutz", "titel": "Hautschutzunterweisung nach TRGS 530",
         "grund": "Friseurhandwerk: Feuchtarbeit, Handschuhe, Hautschutzplan",
         "pflicht": True},
        {"id": "arbeitszeit", "titel": "Hinweis zur Arbeitszeiterfassung",
         "grund": "BAG 13.09.2022 – 1 ABR 22/21",
         "pflicht": True},
    ]
    if a["art"] == "minijob":
        liste.append({"id": "rv_befreiung",
                      "titel": "Antrag auf Befreiung von der Rentenversicherungspflicht",
                      "grund": "freiwillig; wirkt für die Dauer der Beschäftigung",
                      "pflicht": False})
    if a["art"] == "kurzfristig":
        liste.append({"id": "vorbeschaeftigung",
                      "titel": "Erklärung über Vorbeschäftigungen im Kalenderjahr",
                      "grund": "Zeitgrenzen 3 Monate / 70 Arbeitstage",
                      "pflicht": True})
    if a["art"] == "werkstudent":
        liste.append({"id": "immatrikulation",
                      "titel": "Immatrikulationsbescheinigung",
                      "grund": "Nachweis des Werkstudentenprivilegs, je Semester",
                      "pflicht": True})
    if a["art"] == "ausbildung":
        liste.append({"id": "hwk",
                      "titel": "Eintragung in die Lehrlingsrolle der Handwerkskammer",
                      "grund": "vor Beginn der Ausbildung",
                      "pflicht": True})
    if a["alter_bei_eintritt"] is not None and a["alter_bei_eintritt"] < 18:
        liste.append({"id": "erstuntersuchung",
                      "titel": "Ärztliche Erstuntersuchung",
                      "grund": "§ 32 JArbSchG, nicht älter als 14 Monate",
                      "pflicht": True})
        liste.append({"id": "jarbschg",
                      "titel": "Aushang und Belehrung Jugendarbeitsschutz",
                      "grund": "§ 48 JArbSchG",
                      "pflicht": True})
    return liste


# ———————————————————————————————————————————————————————————————
# Der fertige Vertrag
# ———————————————————————————————————————————————————————————————

VORLAGE_FASSUNG = "2026-08-22"


def vertrag_bauen(roh: dict, betrieb: dict | None = None) -> dict:
    """Aus Eckdaten ein vollständiger Vertrag.

    Gibt eine Struktur zurück, keine Zeichenkette — wie daraus ein PDF oder
    ein Bildschirm wird, entscheidet die Oberfläche.
    """
    a = pruefen(roh)
    b = betrieb or {}

    paragraphen = []
    for klausel in KLAUSELN:
        bedingung = klausel.get("wenn")
        if bedingung and not bedingung(a):
            continue
        paragraphen.append({
            "id": klausel["id"],
            "titel": klausel["titel"],
            "text": klausel["text"](a, b),
            "nachweis": klausel.get("nachweis", []),
        })

    vertrag = {
        "fassung": VORLAGE_FASSUNG,
        "art": a["art"],
        "art_name": ARTEN[a["art"]]["name"],
        "sozialversicherung": ARTEN[a["art"]]["sv"],
        "melden_an": ARTEN[a["art"]]["melden"],
        "angaben": a,
        "betrieb": b,
        "form": form_erforderlich({**roh, "art": a["art"]}),
        "paragraphen": paragraphen,
        "anlagen": anlagen_fuer(a),
        "befunde": a["befunde"],
    }
    fehlt = pflichtangaben_fehlen(vertrag)
    vertrag["pflichtangaben_fehlen"] = fehlt
    if fehlt:
        vertrag["befunde"] = vertrag["befunde"] + [{
            "art": "warnung",
            "text": "Dem Nachweis fehlen noch Angaben: " + "; ".join(fehlt)}]
    return vertrag


def als_text(vertrag: dict) -> str:
    """Der Vertrag als lesbarer Fließtext — für PDF und Bildschirm."""
    a, b = vertrag["angaben"], vertrag["betrieb"]
    kopf = [
        "Arbeitsvertrag",
        "",
        "zwischen",
        b.get("name", "— Arbeitgeber —"),
        *(z for z in (b.get("strasse"), b.get("ort")) if z),
        "— nachfolgend Arbeitgeber —",
        "",
        "und",
        b.get("arbeitnehmerin", "— Arbeitnehmerin —"),
        "— nachfolgend Arbeitnehmerin —",
        "",
    ]
    teile = [f"§ {i} {p['titel']}\n\n{p['text']}"
             for i, p in enumerate(vertrag["paragraphen"], 1)]
    anlagen = ["Anlagen zu diesem Vertrag:"] + [
        f"— {x['titel']}" for x in vertrag["anlagen"]]
    return "\n".join(kopf) + "\n\n".join(teile) + "\n\n" + "\n".join(anlagen)
