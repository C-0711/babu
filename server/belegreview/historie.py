"""Die Vergangenheit einlesen: DATEV-Buchungsstapel aus der Zeit davor.

Wer zu babu wechselt, bringt Jahre mit. Bisher konnte babu davon nur die
Jahresunterlagen lesen (Salon-Check: EÜR, BWA, Bescheid als PDF) und daraus
EINE Zahl je Jahr ziehen — für den Vorjahresvergleich teilte die Auswertung
sie schlicht durch zwölf. Ein Salon verdient im Dezember aber anders als im
Februar, und ein Vergleich gegen ein Zwölftel ist keiner.

Der Steuerberater kann aus DATEV den Buchungsstapel jedes Zeitraums
exportieren — dieselbe EXTF-Datei, die babu selbst schreibt (`extf.py`).
Hier wird sie gelesen: Kopfzeile für Zeitraum und Kontenrahmen, dann jede
Buchung mit Konto, Gegenkonto, Datum und Betrag. Daraus entsteht je Monat,
was die Auswertung braucht.

Reine Rechnung ohne I/O — der Aufrufer reicht die Bytes herein.

Was hier NICHT passiert: die alten Buchungen werden nicht zu Belegen. Sie
haben kein Foto, kein Siegel und keine Prüfspur; sie als babu-Belege
auszugeben wäre eine Behauptung über etwas, das nie durch babu gelaufen
ist. Sie liegen getrennt und sind als „aus DATEV übernommen" erkennbar.
"""
from __future__ import annotations

import csv
import io
import re

# Die Spalten, auf die es ankommt — ihre Position im EXTF-v13-Stapel
# (siehe extf.SPALTEN, gleiche Reihenfolge).
UMSATZ, SH, KONTO, GEGENKONTO, BU, BELEGDATUM, BELEGFELD1, TEXT = (
    0, 1, 6, 7, 8, 9, 10, 13)

# Erlöskonten in SKR04 (4000–4999) und SKR03 (8000–8999). Alles andere auf
# der Aufwandsseite ist Kosten; Bestands- und Privatkonten zählen weder
# noch — sie stehen getrennt, wie in der laufenden Auswertung auch.
ERLOES_SKR04 = range(4000, 5000)
ERLOES_SKR03 = range(8000, 9000)
AUFWAND_SKR04 = range(5000, 8000)
AUFWAND_SKR03 = range(3000, 5000)


class HistorieFehler(Exception):
    """Die Datei ist kein Buchungsstapel — mit einem Satz für die Nutzerin."""


def _zahl(wert: str) -> float | None:
    """DATEV schreibt Beträge deutsch und immer positiv (1.234,56)."""
    w = (wert or "").strip().strip('"').replace(".", "").replace(",", ".")
    if not w:
        return None
    try:
        return float(w)
    except ValueError:
        return None


def _monat(belegdatum: str, jahr: int | None) -> str | None:
    """DATEV-Belegdatum ist TTMM ohne Jahr — das steht in der Kopfzeile."""
    d = (belegdatum or "").strip().strip('"')
    if len(d) == 4 and d.isdigit() and jahr:
        return f"{jahr}-{d[2:4]}"
    if len(d) == 8 and d.isdigit():          # manche Exporte: TTMMJJJJ
        return f"{d[4:8]}-{d[2:4]}"
    return None


def kopf_lesen(zeile: str) -> dict:
    """Zeitraum, Kontenrahmen und Herkunft aus der EXTF-Kopfzeile."""
    f = next(csv.reader(io.StringIO(zeile), delimiter=";"))
    if not f or f[0].strip('"') != "EXTF":
        raise HistorieFehler(
            "Das sieht nicht nach einem DATEV-Buchungsstapel aus. Bitte in "
            "DATEV „Buchungsstapel exportieren“ wählen — die Datei beginnt "
            "dann mit EXTF.")
    def hol(i):
        return f[i].strip().strip('"') if len(f) > i else ""
    wj = hol(12)                              # Wirtschaftsjahresbeginn JJJJMMTT
    return {
        "kategorie": hol(2),
        "bezeichnung": hol(3),
        "jahr": int(wj[:4]) if wj[:4].isdigit() else None,
        "von": hol(14), "bis": hol(15),
        "name": hol(16),
        "sachkontenlaenge": hol(13),
        "berater": hol(10), "mandant": hol(11),
    }


def _seite(konto: int, rahmen: str) -> str:
    if rahmen == "SKR03":
        if konto in ERLOES_SKR03:
            return "erloes"
        if konto in AUFWAND_SKR03:
            return "aufwand"
    else:
        if konto in ERLOES_SKR04:
            return "erloes"
        if konto in AUFWAND_SKR04:
            return "aufwand"
    return "neutral"


def stapel_lesen(daten: bytes, rahmen: str = "SKR04") -> dict:
    """Einen DATEV-Buchungsstapel auswerten — je Monat und je Konto.

    Die Beträge sind BRUTTO, wie DATEV sie führt; der Steuersatz steckt im
    BU-Schlüssel. Netto wird hier NICHT gerechnet: dafür müsste man den
    Schlüssel je Buchung auflösen, und ein falsch geratener Satz wäre
    schlimmer als ein ehrlicher Bruttowert.
    """
    text = daten.decode("cp1252", errors="replace")
    zeilen = text.splitlines()
    if not zeilen:
        raise HistorieFehler("Die Datei ist leer.")
    # Erst die Frage „ist das überhaupt ein Stapel?" — sie hat die
    # hilfreichere Antwort als „unvollständig".
    kopf = kopf_lesen(zeilen[0])
    if len(zeilen) < 3:
        raise HistorieFehler("Der Stapel enthält keine Buchungen — nur Kopf "
                             "und Spaltenzeile.")

    monate: dict[str, dict] = {}
    gebucht = uebersprungen = 0
    for f in csv.reader(io.StringIO("\n".join(zeilen[2:])), delimiter=";"):
        if len(f) <= TEXT:
            continue
        betrag = _zahl(f[UMSATZ])
        monat = _monat(f[BELEGDATUM], kopf["jahr"])
        konto_roh = (f[KONTO] or "").strip().strip('"')
        if betrag is None or not monat or not konto_roh.isdigit():
            uebersprungen += 1
            continue
        konto = int(konto_roh)
        # Soll/Haben: „H" dreht das Vorzeichen. Eine Gutschrift im
        # Aufwand mindert die Kosten, genau wie im laufenden Betrieb.
        if (f[SH] or "").strip().strip('"').upper() == "H":
            betrag = -betrag
        m = monate.setdefault(monat, {"monat": monat, "erloese": 0.0,
                                      "kosten": 0.0, "buchungen": 0,
                                      "konten": {}})
        seite = _seite(konto, rahmen)
        if seite == "erloes":
            # Erlöse stehen im Haben — das Minus von oben dreht zurück.
            m["erloese"] += -betrag
        elif seite == "aufwand":
            m["kosten"] += betrag
        m["buchungen"] += 1
        gebucht += 1
        k = m["konten"].setdefault(konto_roh, {"konto": konto_roh,
                                               "betrag": 0.0, "anzahl": 0,
                                               "seite": seite})
        k["betrag"] += betrag if seite != "erloes" else -betrag
        k["anzahl"] += 1

    for m in monate.values():
        m["erloese"] = round(m["erloese"], 2)
        m["kosten"] = round(m["kosten"], 2)
        m["ergebnis"] = round(m["erloese"] - m["kosten"], 2)
        for k in m["konten"].values():
            k["betrag"] = round(k["betrag"], 2)
        m["konten"] = sorted(m["konten"].values(),
                             key=lambda x: -abs(x["betrag"]))[:40]
    if not monate:
        raise HistorieFehler(
            "In der Datei stehen keine lesbaren Buchungen. Stimmt der "
            "Zeitraum, und ist es ein Buchungsstapel (nicht der "
            "Kontenrahmen oder eine Saldenliste)?")
    return {"kopf": kopf, "rahmen": rahmen,
            "monate": dict(sorted(monate.items())),
            "buchungen": gebucht, "uebersprungen": uebersprungen}


def zusammenfuehren(bestand: dict | None, neu: dict) -> dict:
    """Einen weiteren Stapel dazulegen.

    Ein Monat, der schon da ist, wird ERSETZT statt addiert — wer denselben
    Zeitraum zweimal hochlädt (oder eine korrigierte Fassung), soll ihn
    nicht doppelt in der Auswertung sehen.
    """
    aus = dict(bestand or {"monate": {}, "quellen": []})
    monate = dict(aus.get("monate") or {})
    monate.update(neu["monate"])
    quellen = list(aus.get("quellen") or [])
    quellen.append({"name": neu["kopf"].get("name"),
                    "von": neu["kopf"].get("von"), "bis": neu["kopf"].get("bis"),
                    "buchungen": neu["buchungen"],
                    "monate": sorted(neu["monate"])})
    return {"monate": dict(sorted(monate.items())), "quellen": quellen,
            "rahmen": neu.get("rahmen", "SKR04")}


def jahresuebersicht(historie: dict) -> list[dict]:
    """Was babu über die Zeit davor weiß — ein Block je Jahr."""
    jahre: dict[str, dict] = {}
    for monat, m in (historie.get("monate") or {}).items():
        j = jahre.setdefault(monat[:4], {"jahr": monat[:4], "erloese": 0.0,
                                         "kosten": 0.0, "monate": 0,
                                         "buchungen": 0})
        j["erloese"] += m["erloese"]
        j["kosten"] += m["kosten"]
        j["monate"] += 1
        j["buchungen"] += m.get("buchungen", 0)
    for j in jahre.values():
        j["erloese"] = round(j["erloese"], 2)
        j["kosten"] = round(j["kosten"], 2)
        j["ergebnis"] = round(j["erloese"] - j["kosten"], 2)
        j["vollstaendig"] = j["monate"] == 12
    return sorted(jahre.values(), key=lambda x: x["jahr"], reverse=True)


def vorjahresmonat(historie: dict, monat: str) -> dict | None:
    """Derselbe Monat im Vorjahr — der Vergleich, der wirklich einer ist.

    Ohne Historie fällt die Auswertung auf ihr Zwölftel zurück; steht der
    Monat hier, vergleicht sie Februar mit Februar."""
    if not re.fullmatch(r"\d{4}-\d{2}", monat or ""):
        return None
    vorjahr = f"{int(monat[:4]) - 1}-{monat[5:7]}"
    return (historie.get("monate") or {}).get(vorjahr)
