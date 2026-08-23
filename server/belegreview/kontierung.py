#!/usr/bin/env python3
"""Wofür → welche Kategorie → welches Konto. In genau dieser Reihenfolge.

Ninas Regel, 22.08.2026, wörtlich:

    „Der wirtschaftliche Verwendungszweck entscheidet über die Buchungs-
    kategorie, erst die Buchungskategorie entscheidet über das Sachkonto.
    SKR03 und SKR04 dürfen nicht vermischt werden."

Vorher lief es andersherum: der Belegtext wurde per Embedding direkt auf ein
SKR04-Konto abgebildet. Damit landet dieselbe Schere je nach Formulierung des
Lieferanten in drei verschiedenen Konten — sie kann Verkaufsware sein,
Verbrauchsmaterial oder Betriebsausstattung, und der Beleg sagt das nicht. Was
entscheidet, ist die Verwendung, und die weiß nur der Betrieb.

Deshalb dieses Modul. Es rechnet nicht, es liest nichts, es fragt niemanden —
es entscheidet, und es sagt warum. Wo die Verwendung aus dem Beleg nicht
hervorgeht, liefert es eine **Rückfrage** statt einer Vermutung.

Zwei Dinge, die hier bewusst so sind:

1. **Ein Rahmen, nie zwei.** `konto()` bekommt den Kontenrahmen des Betriebs
   und zieht ausschließlich aus dem. Es gibt keinen Weg, der ein SKR03- und
   ein SKR04-Konto in denselben Stapel bringt.

2. **Ungeprüfte Konten sind als ungeprüft markiert.** Die Nummern unten
   stammen aus dem DATEV-Standard, nicht von einer Steuerberatung. Wo ich
   mir sicher bin, steht `geprueft=True`; der Rest trägt eine Rückfrage bei
   sich, statt sich sicher zu geben. Ein falsches Konto ist schlimmer als
   ein fehlendes: das fehlende fällt auf.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# ── Die zwei Grenzen, an denen sich alles entscheidet ────────────────────────
#
# § 6 Abs. 2 EStG, Netto und JE GEGENSTAND — nicht je Rechnung. Vier Stühle zu
# 300 € auf einer Rechnung über 1.200 € sind vier GWG, keine Anlage. Das ist
# der Fehler, den Nina ausdrücklich benannt hat.
SOFORT_GRENZE = Decimal("250.00")   # bis hier: sofort Aufwand
GWG_GRENZE = Decimal("800.00")      # bis hier: GWG, im Jahr voll abgesetzt

RAHMEN = ("SKR03", "SKR04")


@dataclass(frozen=True)
class Kategorie:
    """Eine Buchungskategorie mit ihrem Konto in beiden Rahmen."""
    code: str
    name: str
    skr03: str | None
    skr04: str | None
    geprueft: bool = False
    hinweis: str = ""

    def konto(self, rahmen: str) -> str | None:
        if rahmen not in RAHMEN:
            raise ValueError(f"unbekannter Kontenrahmen: {rahmen!r}")
        return self.skr03 if rahmen == "SKR03" else self.skr04


# ── Die Kategorien ───────────────────────────────────────────────────────────
#
# Reihenfolge ist Absicht: erst was der Betrieb einkauft, dann was er
# anschafft, dann was kein Aufwand ist. Die letzten drei sind die, an denen
# heute die Fehler passieren.

_K = [
    # ── Einkauf und Verbrauch ────────────────────────────────────────────
    Kategorie("wareneinkauf", "Wareneinkauf (Weiterverkauf)",
              "3400", "5400", geprueft=True,
              hinweis="Ware, die die Kundin mitnimmt: Shampoo, Pflege, Styling."),
    Kategorie("verbrauchsmaterial", "Verbrauchsmaterial Salon",
              "4980", "6850", geprueft=True,
              hinweis="Wird im Salon aufgebraucht: Farbe, Folie, Handschuhe."),
    Kategorie("fremdleistung", "Fremdleistungen",
              "3100", "5900", geprueft=True,
              hinweis="Stuhlmiete, freie Kosmetikerin, Subunternehmerin."),

    # ── Anschaffungen — hier entscheidet der Betrag ───────────────────────
    Kategorie("gwg", "Geringwertiges Wirtschaftsgut",
              "0480", "0670", geprueft=True,
              hinweis="Selbständig nutzbar, 250,01–800 € netto je Stück. "
                      "Im Jahr der Anschaffung voll abgesetzt."),
    Kategorie("anlagevermoegen", "Anlagevermögen",
              "0420", "0650",
              hinweis="Über 800 € netto. Wird über die Nutzungsdauer verteilt "
                      "und gehört ins Anlagenverzeichnis."),
    Kategorie("instandhaltung", "Reparatur und Wartung",
              "4805", "6470",
              hinweis="Erhält Vorhandenes — nie Anlage, auch bei hohem Betrag."),

    # ── Laufender Aufwand ─────────────────────────────────────────────────
    Kategorie("miete", "Miete Geschäftsräume", "4210", "6310", geprueft=True),
    Kategorie("energie", "Strom, Gas, Wasser", "4240", "6325", geprueft=True),
    Kategorie("reinigung", "Reinigung und Wäsche", "4250", "6330",
              hinweis="Handtuchservice und Mietwäsche laufen bei manchen "
                      "Betrieben über Fremdleistung — einmal festlegen."),
    Kategorie("versicherung", "Versicherungen", "4360", "6400", geprueft=True),
    Kategorie("werbung", "Werbung", "4600", "6600", geprueft=True),
    Kategorie("geschenk", "Geschenke", "4630", "6610", geprueft=True),
    Kategorie("bewirtung", "Bewirtung", "4650", "6640", geprueft=True),
    Kategorie("kfz", "Kfz-Kosten", "4530", "6530", geprueft=True),
    Kategorie("fahrt", "Reise- und Fahrtkosten", "4670", "6673",
              hinweis="Trennung Unternehmerin/Arbeitnehmerin noch nicht "
                      "abgebildet — die Konten unterscheiden sich dort."),
    Kategorie("telekom", "Telefon und Internet", "4920", "6805", geprueft=True),
    Kategorie("buerobedarf", "Bürobedarf", "4930", "6815", geprueft=True),
    Kategorie("literatur", "Fachliteratur", "4940", "6820", geprueft=True),
    Kategorie("it", "IT, Hosting, Software", None, "6837",
              hinweis="SKR03-Gegenstück noch nicht bestätigt."),
    Kategorie("sonstiges", "Sonstiger Betriebsbedarf",
              "4980", "6850", geprueft=True),

    # ── Kein Aufwand — die drei, an denen es heute schiefgeht ─────────────
    Kategorie("geldtransit", "Geldtransit",
              "1360", "1460", geprueft=True,
              hinweis="Geld zwischen eigenen Konten. KEIN Umsatz, keine "
                      "Umsatzsteuer — der Umsatz war schon beim Kunden da."),
    Kategorie("gutschein", "Verbindlichkeit aus Gutscheinen",
              None, None,
              hinweis="Beim VERKAUF entsteht die Verbindlichkeit, beim "
                      "Einlösen der Erlös. Konten noch nicht bestätigt."),
    Kategorie("privat", "Privatentnahme",
              "1800", "2100", geprueft=True,
              hinweis="Keine Betriebsausgabe, mindert nur den Bestand."),
    Kategorie("darlehen_personal", "Vorschuss an Mitarbeitende",
              None, None,
              hinweis="Forderung, kein Aufwand — wird mit dem Lohn "
                      "verrechnet. Konten noch nicht bestätigt."),
]

KATEGORIEN: dict[str, Kategorie] = {k.code: k for k in _K}


# ── Verwendungszwecke: das, was Nina beantworten kann ────────────────────────
#
# Bewusst in ihrer Sprache und bewusst wenige. Jeder Zweck führt eindeutig auf
# eine Kategorie — außer „betriebsausstattung", wo erst der Betrag entscheidet.
# Das ist keine Lücke, das IST die Regel.

VERWENDUNG = {
    "weiterverkauf": "Die Kundin nimmt es mit",
    "verbrauch": "Wird im Salon aufgebraucht",
    "betriebsausstattung": "Gerät oder Einrichtung, bleibt im Salon",
    "reparatur": "Repariert oder wartet etwas Vorhandenes",
    "fremdleistung": "Jemand anderes hat eine Leistung erbracht",
    "miete_leasing": "Miete, Pacht oder Leasing",
    "geldbewegung": "Geld zwischen eigenen Konten",
    "privat": "Privat, nicht für den Salon",
}


@dataclass
class Entscheidung:
    """Was gebucht wird, in welchem Rahmen — und warum."""
    kategorie: str | None
    konto: str | None
    rahmen: str
    begruendung: str
    rueckfrage: str | None = None
    geprueft: bool = False

    @property
    def offen(self) -> bool:
        """True, solange gefragt werden muss statt gebucht."""
        return self.rueckfrage is not None


def _cent(wert) -> Decimal | None:
    """Betrag als Decimal — Fließkomma hat in Geld nichts verloren."""
    if wert is None:
        return None
    try:
        return Decimal(str(wert).replace(",", ".").strip())
    except Exception:  # noqa: BLE001
        return None


def entscheiden(*, verwendung: str | None,
                netto_je_stueck=None,
                selbstaendig_nutzbar: bool | None = None,
                rahmen: str = "SKR04") -> Entscheidung:
    """Die Kaskade. Erst wofür, dann welche Kategorie, dann welches Konto.

    Gibt eine Rückfrage zurück, wo die Antwort fehlt — nie eine Vermutung.
    """
    if rahmen not in RAHMEN:
        raise ValueError(f"unbekannter Kontenrahmen: {rahmen!r}")

    if not verwendung:
        return Entscheidung(
            None, None, rahmen,
            "Ohne Verwendungszweck lässt sich keine Kategorie bestimmen.",
            rueckfrage="Wofür hast du das gekauft?")

    if verwendung not in VERWENDUNG:
        raise ValueError(f"unbekannter Verwendungszweck: {verwendung!r}")

    einfach = {
        "weiterverkauf": ("wareneinkauf", "Ware für den Weiterverkauf."),
        "verbrauch": ("verbrauchsmaterial", "Wird im Salon aufgebraucht."),
        "fremdleistung": ("fremdleistung", "Leistung von jemand anderem."),
        "miete_leasing": ("miete", "Miete, Pacht oder Leasing."),
        "reparatur": ("instandhaltung",
                      "Erhält Vorhandenes — Aufwand, nie Anlage, "
                      "unabhängig vom Betrag."),
        "geldbewegung": ("geldtransit",
                         "Geld zwischen eigenen Konten: kein Umsatz, "
                         "keine Umsatzsteuer."),
        "privat": ("privat", "Nicht betrieblich veranlasst."),
    }
    if verwendung in einfach:
        code, grund = einfach[verwendung]
        return _fertig(code, rahmen, grund)

    # ── Betriebsausstattung: jetzt erst zählt der Betrag ──────────────────
    if selbstaendig_nutzbar is False:
        return Entscheidung(
            None, None, rahmen,
            "Nicht selbständig nutzbar — gehört zum Hauptgegenstand und "
            "teilt dessen Behandlung.",
            rueckfrage="Zu welchem Gerät gehört das?")

    netto = _cent(netto_je_stueck)
    if netto is None:
        return Entscheidung(
            None, None, rahmen,
            "Bei Anschaffungen entscheidet der Nettobetrag je Stück.",
            rueckfrage="Was hat ein Stück netto gekostet?")

    if selbstaendig_nutzbar is None and netto > SOFORT_GRENZE:
        return Entscheidung(
            None, None, rahmen,
            "Über 250 € netto hängt die Behandlung daran, ob der Gegenstand "
            "allein nutzbar ist.",
            rueckfrage="Kannst du das allein benutzen, oder gehört es zu "
                       "etwas anderem?")

    if netto <= SOFORT_GRENZE:
        return _fertig("sonstiges", rahmen,
                       f"Bis {SOFORT_GRENZE:.0f} € netto je Stück sofort "
                       f"Aufwand (§ 6 Abs. 2 EStG).")
    if netto <= GWG_GRENZE:
        return _fertig("gwg", rahmen,
                       f"{SOFORT_GRENZE:.2f} bis {GWG_GRENZE:.0f} € netto je "
                       f"Stück: geringwertiges Wirtschaftsgut, im Jahr der "
                       f"Anschaffung voll abgesetzt.")
    return _fertig("anlagevermoegen", rahmen,
                   f"Über {GWG_GRENZE:.0f} € netto je Stück: Anlagevermögen, "
                   f"über die Nutzungsdauer verteilt.")


def _fertig(code: str, rahmen: str, grund: str) -> Entscheidung:
    k = KATEGORIEN[code]
    konto = k.konto(rahmen)
    if konto is None:
        return Entscheidung(
            code, None, rahmen, grund,
            rueckfrage=f"Für „{k.name}“ ist im {rahmen} noch kein Konto "
                       f"hinterlegt — bitte einmal festlegen.",
            geprueft=False)
    return Entscheidung(code, konto, rahmen, grund, geprueft=k.geprueft)


def konto(kategorie: str, rahmen: str) -> str | None:
    """Das Konto einer Kategorie im gewählten Rahmen — und nur in dem."""
    if kategorie not in KATEGORIEN:
        raise ValueError(f"unbekannte Kategorie: {kategorie!r}")
    return KATEGORIEN[kategorie].konto(rahmen)


def gehoert_zum_rahmen(kontonummer: str, rahmen: str) -> bool:
    """Stammt dieses Konto aus diesem Rahmen? Der Mischungs-Melder.

    Bewusst konservativ: es prüft gegen die hier geführten Konten. Was babu
    nicht selbst vergeben hat, gilt als fremd und wird nicht stillschweigend
    durchgewinkt.
    """
    if rahmen not in RAHMEN:
        raise ValueError(f"unbekannter Kontenrahmen: {rahmen!r}")
    return any(k.konto(rahmen) == str(kontonummer) for k in KATEGORIEN.values())


def ungepruefte_konten() -> list[Kategorie]:
    """Was eine Steuerberatung noch bestätigen muss. Ehrlich statt still."""
    return [k for k in KATEGORIEN.values() if not k.geprueft]
