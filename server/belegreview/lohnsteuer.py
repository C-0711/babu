"""Die Lohnsteuer-Anmeldung ans Finanzamt.

Das ist der Teil des Amtswegs, den babu selbst gehen darf. Die
Sozialversicherung verlangt ein systemgeprüftes Programm mit GKV-Zertifikat
(§ 95b SGB IV) — das Finanzamt nicht: die Steuerverwaltung gibt ERiC
kostenlos heraus, nötig ist nur eine Registrierung als Entwickler.

Hier steht die Rechnung, nicht die Übertragung. Was übertragen wird, ist ein
festgelegter Satz von Kennzahlen; welche das sind, steht im amtlichen Muster
des BMF und ist unten übernommen — nicht geraten. Wie die Zahlen zum
Finanzamt kommen, entscheidet `amtsweg.py`.

Zwei Dinge, die man beim Lesen wissen sollte:

**Eine Steueranmeldung ist eine Steuererklärung** (§ 150 Abs. 1 Satz 3 AO).
Was hier herauskommt, wird ohne weiteren Bescheid zur festgesetzten Steuer.
Deshalb rechnet dieses Modul nichts weich und rundet nichts hin: es rechnet
in Cent, und wo eine Angabe fehlt, sagt es das.

**Der Anmeldungszeitraum ergibt sich aus dem Vorjahr**, nicht aus einer
Einstellung. Wer ihn falsch wählt, meldet zu selten und zahlt Säumnis­
zuschläge — oder meldet zwölfmal, wo einmal gereicht hätte.

Rechtsstand 22.08.2026, Muster der Lohnsteuer-Anmeldung 2026 (BMF-Schreiben
vom 14.08.2025).
"""
from __future__ import annotations

import datetime as dt

# ———————————————————————————————————————————————————————————————
# Die Kennzahlen des amtlichen Vordrucks
# ———————————————————————————————————————————————————————————————
#
# Reihenfolge und Nummern aus dem Muster 2026. Die Namen hier sind unsere;
# die Nummern sind es nicht — sie gehen so in die Übertragung.

KENNZAHLEN = {
    "arbeitnehmer":       (86, "Zahl der Arbeitnehmer (einschl. Aushilfs- und Teilzeitkräfte)"),
    "arbeitnehmer_bav":   (90, "davon mit BAV-Förderbetrag"),
    "lohnsteuer":         (42, "Summe der einzubehaltenden Lohnsteuer"),
    "pauschal":           (41, "Summe der pauschalen Lohnsteuer — ohne § 37b EStG"),
    "pauschal_37b":       (44, "Summe der pauschalen Lohnsteuer nach § 37b EStG"),
    "kuerzung_seeleute":  (33, "abzüglich Kürzungsbetrag für Besatzungsmitglieder"),
    "bav_foerderbetrag":  (45, "abzüglich Förderbetrag zur betrieblichen Altersversorgung (§ 100 EStG)"),
    "verbleiben":         (48, "Verbleiben"),
    "soli":               (49, "Solidaritätszuschlag"),
    "kirchensteuer_pausch": (47, "pauschale Kirchensteuer im vereinfachten Verfahren"),
    "kirchensteuer_ev":   (61, "Evangelische Kirchensteuer"),
    "kirchensteuer_rk":   (62, "Römisch-Katholische Kirchensteuer"),
    "gesamtbetrag":       (83, "Gesamtbetrag"),
    "berichtigt":         (10, "Berichtigte Anmeldung"),
    "negativ_jahresausgleich": (92, "Negativer Gesamtbetrag aufgrund Lohnsteuerjahresausgleich"),
}

# Die Beträge, die aufaddiert werden, und die, die abgezogen werden.
_PLUS = ("lohnsteuer", "pauschal", "pauschal_37b")
_MINUS = ("kuerzung_seeleute", "bav_foerderbetrag")
_AUFSCHLAG = ("soli", "kirchensteuer_pausch", "kirchensteuer_ev", "kirchensteuer_rk")


class LohnsteuerFehler(ValueError):
    """So ließe sich die Anmeldung nicht abgeben."""


# ———————————————————————————————————————————————————————————————
# Welcher Zeitraum, welche Frist
# ———————————————————————————————————————————————————————————————
#
# § 41a Abs. 2 EStG. Die Grenzen stehen seit Jahren unverändert.

GRENZE_JAEHRLICH = 1_080_00      # Cent: bis hierhin genügt einmal im Jahr
GRENZE_MONATLICH = 5_000_00      # Cent: darüber jeden Monat


def anmeldezeitraum(vorjahressteuer_cent: int) -> str:
    """Monatlich, vierteljährlich oder jährlich — entschieden vom Vorjahr."""
    if vorjahressteuer_cent < 0:
        raise LohnsteuerFehler("Die Vorjahressteuer kann nicht negativ sein.")
    if vorjahressteuer_cent <= GRENZE_JAEHRLICH:
        return "jaehrlich"
    if vorjahressteuer_cent <= GRENZE_MONATLICH:
        return "vierteljaehrlich"
    return "monatlich"


def zeitraum_erklaeren(vorjahressteuer_cent: int) -> str:
    """Warum dieser Zeitraum — damit Nina es nachvollziehen kann."""
    z = anmeldezeitraum(vorjahressteuer_cent)
    euro = vorjahressteuer_cent / 100
    if z == "jaehrlich":
        return (f"Im Vorjahr wurden {euro:.2f} € Lohnsteuer abgeführt, also "
                "höchstens 1.080 €. Damit genügt eine Anmeldung im Jahr "
                "(§ 41a Abs. 2 Satz 3 EStG).")
    if z == "vierteljaehrlich":
        return (f"Im Vorjahr wurden {euro:.2f} € Lohnsteuer abgeführt — mehr "
                "als 1.080 €, aber höchstens 5.000 €. Damit wird "
                "vierteljährlich angemeldet (§ 41a Abs. 2 Satz 2 EStG).")
    return (f"Im Vorjahr wurden {euro:.2f} € Lohnsteuer abgeführt, also mehr "
            "als 5.000 €. Damit wird monatlich angemeldet "
            "(§ 41a Abs. 2 Satz 1 EStG).")


# Der Schlüssel, mit dem der Zeitraum im Vordruck angekreuzt wird:
# Monate 01–12, Quartale 41–44, Kalenderjahr 19.
def zeitraum_schluessel(zeitraum: str, periode: int) -> int:
    if zeitraum == "monatlich":
        if not 1 <= periode <= 12:
            raise LohnsteuerFehler("Der Monat liegt zwischen 1 und 12.")
        return periode
    if zeitraum == "vierteljaehrlich":
        if not 1 <= periode <= 4:
            raise LohnsteuerFehler("Das Quartal liegt zwischen 1 und 4.")
        return 40 + periode
    if zeitraum == "jaehrlich":
        return 19
    raise LohnsteuerFehler(f"Unbekannter Anmeldungszeitraum: {zeitraum}")


def _ostersonntag(jahr: int) -> dt.date:
    """Gaußsche Osterformel — Grundlage der beweglichen Feiertage."""
    a, b, c = jahr % 19, jahr // 100, jahr % 100
    d, e = b // 4, b % 4
    f, g = (b + 8) // 25, 0
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat = (h + l - 7 * m + 114) // 31
    tag = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(jahr, monat, tag)


def bundesweite_feiertage(jahr: int) -> set[dt.date]:
    """Die Feiertage, die überall gelten.

    Landesfeiertage fehlen hier bewusst — sie hängen vom Sitz des Finanzamts
    ab und werden über `weitere_feiertage` hereingereicht. Lieber eine Frist
    einen Tag zu früh als eine versäumte.
    """
    o = _ostersonntag(jahr)
    return {
        dt.date(jahr, 1, 1), o - dt.timedelta(days=2), o + dt.timedelta(days=1),
        dt.date(jahr, 5, 1), o + dt.timedelta(days=39), o + dt.timedelta(days=50),
        dt.date(jahr, 10, 3), dt.date(jahr, 12, 25), dt.date(jahr, 12, 26),
    }


def frist(jahr: int, zeitraum: str, periode: int,
          weitere_feiertage: set[dt.date] | None = None) -> dt.date:
    """Wann die Anmeldung spätestens beim Finanzamt sein muss.

    § 41a Abs. 1 EStG: der zehnte Tag nach Ablauf des Zeitraums. Fällt er auf
    einen Samstag, Sonntag oder Feiertag, verschiebt sich die Frist auf den
    nächsten Werktag (§ 108 Abs. 3 AO).
    """
    if zeitraum == "monatlich":
        ende_monat, ende_jahr = periode, jahr
    elif zeitraum == "vierteljaehrlich":
        ende_monat, ende_jahr = periode * 3, jahr
    elif zeitraum == "jaehrlich":
        ende_monat, ende_jahr = 12, jahr
    else:
        raise LohnsteuerFehler(f"Unbekannter Anmeldungszeitraum: {zeitraum}")
    zeitraum_schluessel(zeitraum, periode)      # prüft die Periode mit

    faellig = (dt.date(ende_jahr + 1, 1, 10) if ende_monat == 12
               else dt.date(ende_jahr, ende_monat + 1, 10))
    feiertage = bundesweite_feiertage(faellig.year) | (weitere_feiertage or set())
    while faellig.weekday() >= 5 or faellig in feiertage:
        faellig += dt.timedelta(days=1)
    return faellig


# ———————————————————————————————————————————————————————————————
# Die Anmeldung selbst
# ———————————————————————————————————————————————————————————————

def _cent(wert, feld: str) -> int:
    """Beträge kommen in Cent hinein und bleiben in Cent.

    Eine Steueranmeldung mit Fließkommazahlen zu rechnen heißt, irgendwann
    einen Cent Differenz zum Finanzamt zu haben und ihn nicht zu finden.
    """
    if wert in (None, ""):
        return 0
    if isinstance(wert, float):
        raise LohnsteuerFehler(
            f"{feld}: Beträge bitte in Cent als ganze Zahl — Fließkomma "
            "rundet sich in einer Steueranmeldung irgendwann auseinander.")
    try:
        return int(wert)
    except (TypeError, ValueError):
        raise LohnsteuerFehler(f"{feld} können wir nicht lesen.")


def anmeldung_bauen(roh: dict) -> dict:
    """Aus den Summen eines Zeitraums die fertige Anmeldung.

    Rechnet die abgeleiteten Zeilen selbst aus — „Verbleiben" und
    „Gesamtbetrag" werden nicht eingetragen, sondern ergeben sich.
    """
    roh = roh if isinstance(roh, dict) else {}

    steuernummer = str(roh.get("steuernummer") or "").strip()
    if not steuernummer:
        raise LohnsteuerFehler("Ohne Steuernummer nimmt das Finanzamt nichts an.")

    jahr = int(roh.get("jahr") or 0)
    if not 2020 <= jahr <= 2100:
        raise LohnsteuerFehler("Welches Jahr wird angemeldet?")

    zeitraum = str(roh.get("zeitraum") or "").strip().lower()
    if zeitraum not in ("monatlich", "vierteljaehrlich", "jaehrlich"):
        raise LohnsteuerFehler(
            "Der Anmeldungszeitraum ist monatlich, vierteljaehrlich oder "
            "jaehrlich. Er ergibt sich aus der Vorjahressteuer — siehe "
            "anmeldezeitraum().")
    periode = int(roh.get("periode") or (1 if zeitraum == "jaehrlich" else 0))

    betraege = {name: _cent(roh.get(name), bez)
                for name, (_, bez) in KENNZAHLEN.items()
                if name not in ("verbleiben", "gesamtbetrag", "berichtigt",
                                "negativ_jahresausgleich", "arbeitnehmer",
                                "arbeitnehmer_bav")}

    arbeitnehmer = int(roh.get("arbeitnehmer") or 0)
    if arbeitnehmer < 0:
        raise LohnsteuerFehler("Die Zahl der Arbeitnehmer kann nicht negativ sein.")
    if arbeitnehmer == 0 and any(betraege.values()):
        raise LohnsteuerFehler(
            "Es sind Beträge angemeldet, aber null Arbeitnehmer. Eines von "
            "beidem stimmt nicht.")

    verbleiben = (sum(betraege[k] for k in _PLUS)
                  - sum(betraege[k] for k in _MINUS))
    gesamt = verbleiben + sum(betraege[k] for k in _AUFSCHLAG)

    hinweise: list[str] = []
    if gesamt == 0 and arbeitnehmer:
        hinweise.append(
            "Nullmeldung: es wird nichts abgeführt. Sie muss trotzdem "
            "abgegeben werden, solange die Lohnsteuer-Anmeldepflicht "
            "besteht — sonst schätzt das Finanzamt.")
    if verbleiben < 0:
        hinweise.append(
            "Negativer Betrag: das kommt vor, etwa nach einem "
            "Lohnsteuer-Jahresausgleich. Er ist mit Minuszeichen zu "
            "übertragen.")

    faellig = frist(jahr, zeitraum, periode,
                    {_datum(x) for x in (roh.get("weitere_feiertage") or [])})

    return {
        "steuernummer": steuernummer,
        "jahr": jahr,
        "zeitraum": zeitraum,
        "periode": periode,
        "zeitraum_schluessel": zeitraum_schluessel(zeitraum, periode),
        "faellig_am": faellig,
        "berichtigt": bool(roh.get("berichtigt")),
        "arbeitnehmer": arbeitnehmer,
        "arbeitnehmer_bav": int(roh.get("arbeitnehmer_bav") or 0),
        "betraege": betraege,
        "verbleiben": verbleiben,
        "gesamtbetrag": gesamt,
        "hinweise": hinweise,
    }


def _datum(wert) -> dt.date:
    if isinstance(wert, dt.date):
        return wert
    return dt.date.fromisoformat(str(wert)[:10])


def als_kennzahlen(anmeldung: dict) -> dict[int, int | str]:
    """Die Anmeldung als das, was übertragen wird: Kennzahl → Wert.

    Genau diese Abbildung geht an ERiC. Sie steht bewusst an einer Stelle,
    damit sie sich gegen das amtliche Muster prüfen lässt, ohne den Rest zu
    lesen.
    """
    k = {KENNZAHLEN["arbeitnehmer"][0]: anmeldung["arbeitnehmer"]}
    if anmeldung["arbeitnehmer_bav"]:
        k[KENNZAHLEN["arbeitnehmer_bav"][0]] = anmeldung["arbeitnehmer_bav"]
    for name, betrag in anmeldung["betraege"].items():
        if betrag:
            k[KENNZAHLEN[name][0]] = betrag
    k[KENNZAHLEN["verbleiben"][0]] = anmeldung["verbleiben"]
    k[KENNZAHLEN["gesamtbetrag"][0]] = anmeldung["gesamtbetrag"]
    if anmeldung["berichtigt"]:
        k[KENNZAHLEN["berichtigt"][0]] = 1
    return k


def als_klartext(anmeldung: dict) -> str:
    """Zum Gegenlesen, bevor etwas ans Finanzamt geht.

    Eine Steueranmeldung sollte man einmal gesehen haben, bevor sie
    festgesetzt ist.
    """
    def euro(cent: int) -> str:
        return f"{cent / 100:,.2f} €".replace(",", "#").replace(".", ",").replace("#", ".")

    benennung = {"monatlich": f"Monat {anmeldung['periode']:02d}",
                 "vierteljaehrlich": f"{anmeldung['periode']}. Quartal",
                 "jaehrlich": "Kalenderjahr"}[anmeldung["zeitraum"]]
    zeilen = [
        f"Lohnsteuer-Anmeldung {anmeldung['jahr']} — {benennung}",
        f"Steuernummer {anmeldung['steuernummer']}",
        f"Fällig am {anmeldung['faellig_am'].strftime('%d.%m.%Y')}",
        "",
        f"  {KENNZAHLEN['arbeitnehmer'][0]:>3}  "
        f"{KENNZAHLEN['arbeitnehmer'][1]:<62}{anmeldung['arbeitnehmer']:>14}",
    ]
    for name, betrag in anmeldung["betraege"].items():
        if betrag:
            nr, bez = KENNZAHLEN[name]
            zeilen.append(f"  {nr:>3}  {bez:<62}{euro(betrag):>14}")
    nr, bez = KENNZAHLEN["verbleiben"]
    zeilen.append(f"  {nr:>3}  {bez:<62}{euro(anmeldung['verbleiben']):>14}")
    nr, bez = KENNZAHLEN["gesamtbetrag"]
    zeilen.append(f"  {nr:>3}  {bez:<62}{euro(anmeldung['gesamtbetrag']):>14}")
    if anmeldung["berichtigt"]:
        zeilen.append("\n  Berichtigte Anmeldung.")
    for h in anmeldung["hinweise"]:
        zeilen.append(f"\n  Hinweis: {h}")
    return "\n".join(zeilen)
