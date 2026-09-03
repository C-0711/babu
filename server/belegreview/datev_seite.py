"""Die DATEV-Seite der Verwaltung — Stapel hinausgeben, Stapel hereinlesen.

Eine eigene Seite mit eigenem Router, damit sie neben `babu_web` steht statt
darin: der Buchungsstapel ist das einzige Stück babu, das die Kanzlei
wirklich anfasst, und er hat inzwischen mehr Fragen als eine Schaltfläche
beantworten kann (welcher Zeitraum, welche Konten, stimmt es überhaupt).

Drei Dinge, und nur die:

1. **Hinausgeben.** Buchungsstapel für einen Monat oder einen Zeitraum,
   vorher der Prüfbefund (Kontenrahmen-Vermischung, Belege ohne Konto,
   unbekannte Konten, Summen), dann erst die Datei. Das Format kommt
   vollständig aus `extf` — hier wird kein zweites DATEV-Format gepflegt.

2. **Stammdaten.** Kontenbeschriftungen der tatsächlich benutzten Konten und
   eine Liste der Lieferanten. Beides Beiwerk zum Stapel, kein eigener Weg.

3. **Hereinlesen.** Eine Stapeldatei aus DATEV wird gelesen, angezeigt und
   mit den eigenen Belegen VERGLICHEN — nicht übernommen. Es wird beim
   Hereinlesen kein einziges Byte in die Belegbox geschrieben; die Datei
   berührt nicht einmal die Platte, sie bleibt im Speicher und ist nach der
   Antwort weg. Das steht so auch auf der Seite, weil ein Vergleich, den man
   für eine Übernahme hält, schlimmer ist als kein Vergleich.

`babu_web` wird ausschließlich innerhalb der Funktionen importiert (lazy) —
`babu_web` bindet diesen Router ein, ein Import auf Modulebene wäre ein
Kreis. Nebeneffekt, der uns entgegenkommt: die Tests dürfen die Wachen an
`babu_web` austauschen und dieser Router merkt es.
"""
from __future__ import annotations

import calendar
import csv
import os
import re
import time

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

import extf
import skr04_konten

router = APIRouter(prefix="/api/datev")

# Mehr als drei Jahre am Stück will niemand ansehen, und ein Stapel über
# Jahresgrenzen ist ohnehin keiner (siehe `_zeitraum`).
MONATE_MAX = 36
# 20 MB. Ein Jahresstapel eines Salons ist ein paar hundert Kilobyte; wer
# hier an die Grenze stößt, hat die falsche Datei erwischt.
UPLOAD_MAX = 20 * 1024 * 1024
ENDUNGEN = (".csv", ".txt")

MONAT_MUSTER = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# Rate-Limit auf das Hereinlesen, je angemeldetem Zugang (nicht je IP: die
# Route setzt ohnehin `_verwalter_wache` voraus, und eine Kanzlei sitzt oft
# hinter derselben Adresse wie ihre Nachbarin). Jeder Aufruf liest die
# ganze Datei in den Speicher und parst sie — 20 im 60-Sekunden-Fenster
# lässt ein normales Durchprobieren mehrerer Monatsdateien zu, ohne dass
# jemand die Route als Upload-Kanone missbrauchen kann. Muster wie
# `_anlage_gebremst` in `kanzlei_routen.py`.
_LESE_VERSUCHE: dict[str, list[float]] = {}
LESE_MAX = 20
LESE_FENSTER = 60.0


# ---------------------------------------------------------------------------
# Wache und Zugriff auf babu_web — beides erst zur Laufzeit.
# ---------------------------------------------------------------------------

def _bw():
    import babu_web  # noqa: PLC0415
    return babu_web


def _wache(request: Request):
    """Nur Verwaltung (Inhaberin-Kanzlei-Ebene). Gilt für jede Route hier.

    Seit dem Kanzlei-Cockpit `_verwalter_box_wache` und nicht mehr
    `_verwalter_wache`: jede Route hier liest über `index_aktuell()` in die
    Belegbox, und die kam beim Acting-as aus dem Kontext — den aber setzte
    niemand. Eine Kanzlei mit `X-Mandant`-Kopf bekam deshalb ihren eigenen
    (leeren) Stapel statt des Stapels ihres Mandanten. Ohne Kopf ändert
    sich nichts; siehe `babu_web._verwalter_box_wache`.
    """
    return _bw()._verwalter_box_wache(request)


def _berater_mandant(bw) -> tuple[str, str]:
    """Berater- und Mandantennummer für den Stapelkopf.

    Diese beiden Zahlen sagen der Kanzlei-Software, WESSEN Buchhaltung sie
    gerade importiert. Aus der Serverumgebung kamen sie, solange es einen
    Betrieb je Server gab; beim Acting-as ist das die falsche Antwort —
    zwei Mandanten bekämen dieselbe Nummer und liefen im Import ineinander.

    Gefragt wird deshalb zuerst `babu_web`, das die Nummern am Mandanten
    führt. Gibt es dort (noch) nichts, bleibt es beim bisherigen Weg über
    die Umgebung. `getattr` und nicht der harte Aufruf: die Seite soll
    laufen, egal in welcher Reihenfolge die beiden Hälften ankommen.
    """
    holen = getattr(bw, "_berater_mandant", None)
    if callable(holen):
        try:
            berater, mandant = holen()
        except Exception:  # noqa: BLE001 — die Umgebung ist der Rückweg
            berater = mandant = None
        if berater or mandant:
            return str(berater or "").strip(), str(mandant or "").strip()
    return (os.environ.get("BABU_BERATER", extf.BERATER),
            os.environ.get("BABU_MANDANT", extf.MANDANT))


def _nummer_fehlt(wert: str) -> bool:
    """Ist das keine brauchbare Berater- oder Mandantennummer?

    Leer, „0" oder etwas, das keine Zahl ist. DATEV nimmt die Datei damit
    zwar an, ordnet sie aber keinem Mandanten zu — die Kanzlei muss sie
    dann von Hand zuweisen, und bei mehreren Betrieben rät sie dabei.
    """
    w = str(wert or "").strip()
    return not w.isdigit() or int(w) == 0


def _lese_gebremst(un: str) -> bool:
    jetzt = time.time()
    versuche = [t for t in _LESE_VERSUCHE.get(un, []) if jetzt - t < LESE_FENSTER]
    _LESE_VERSUCHE[un] = versuche
    if len(versuche) >= LESE_MAX:
        return True
    versuche.append(jetzt)
    _bw()._zaehler_aufraeumen(_LESE_VERSUCHE, jetzt, LESE_FENSTER)  # noqa: SLF001
    return False


def _fehler(text: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"fehler": text}, status_code=code)


# ---------------------------------------------------------------------------
# Zeitraum
# ---------------------------------------------------------------------------

def _zeitraum(von: str | None, bis: str | None) -> tuple[list[str], str | None]:
    """Die Monate von…bis — oder eine Meldung, warum das keiner ist.

    Ein Buchungsstapel gehört in EIN Wirtschaftsjahr: die Kopfzeile trägt
    genau einen Wirtschaftsjahresbeginn, und ein Stapel, der über den
    Jahreswechsel läuft, wird beim Import geteilt oder abgelehnt. Lieber
    hier eine klare Ansage als dort eine unklare.
    """
    von = (von or "").strip()
    bis = (bis or von).strip()
    if not MONAT_MUSTER.match(von) or not MONAT_MUSTER.match(bis):
        return [], "Bitte einen Monat im Format JJJJ-MM angeben."
    if bis < von:
        return [], "Der Zeitraum endet vor seinem Anfang."
    if von[:4] != bis[:4]:
        return [], ("Ein Buchungsstapel gehört in ein Wirtschaftsjahr. "
                    "Bitte je Jahr einen eigenen Stapel erzeugen.")
    monate, jahr, mm = [], int(von[:4]), int(von[5:7])
    ende = int(bis[5:7])
    while mm <= ende:
        monate.append(f"{jahr}-{mm:02d}")
        mm += 1
    if len(monate) > MONATE_MAX:
        return [], "Der Zeitraum ist zu lang."
    return monate, None


# ---------------------------------------------------------------------------
# Was in den Stapel gehört
# ---------------------------------------------------------------------------

def _reviews(idx: dict, monat: str, kleinunternehmerin: bool = False
             ) -> tuple[list[dict], list[str], list[str], list[dict]]:
    """Die Belege eines Monats, die in den Stapel dürfen.

    Zurück kommen die Reviews, die Stämme dazu (in derselben Reihenfolge),
    die Stämme, die kein Konto tragen — die fehlen im Stapel, und genau das
    soll der Prüfbefund sagen, bevor jemand die Datei weitergibt — und die
    Feststellungen aus `extf.pruefen`, jede mit dem Beleg, an dem sie hängt.
    """
    staemme = sorted(s for s, z in idx["belege"].items()
                     if z["monat"] == monat
                     and z["status"] in ("geprüft", "exportiert"))
    reviews, mit, ohne, hinweise = [], [], [], []
    for s in staemme:
        review = idx["reviews"].get(s)
        if review is None:
            ohne.append(s)
            continue
        reviews.append(review)
        mit.append(s)
        if not extf.buchungszeilen(review, kleinunternehmerin):
            ohne.append(s)
        for h in extf.pruefen(review, kleinunternehmerin):
            hinweise.append(dict(h, beleg=s))
    return reviews, mit, ohne, hinweise


def _kassenblaetter(idx: dict, monat: str) -> list[dict]:
    return [b for tag, b in idx["kassenblaetter"].items() if tag.startswith(monat)]


def _kleinunternehmerin(bw, un: str) -> bool:
    import monatsabschluss as ma  # noqa: PLC0415
    # `salon_von_aktiv` und nicht `salon_von`: die Kleinunternehmer-Regelung
    # ist eine Angabe des BETRIEBS und entscheidet, ob im Stapel Steuer
    # steht. Roh gelesen käme beim Acting-as die Angabe der Kanzlei heraus —
    # der Stapel des Mandanten mit dem Umsatzprofil eines fremden Betriebs.
    profil = ma.umsatz_profil(bw.db_einstellungen(bw.salon_von_aktiv(un)))
    return not profil.get("braucht_ustva")


def _betrag(text: str) -> float:
    """Deutsche Schreibweise → Zahl. `1.234,56` ist 1234,56, nicht 1,23456.

    Der Punkt fällt nur dann als Tausenderzeichen weg, wenn ein Komma
    dabeisteht. Sonst wäre `1234.56` — eine Datei, die jemand durch
    ein englisches Werkzeug geschickt hat — plötzlich 123.456 Euro,
    und der Abgleich zeigte einen Unterschied, den es nicht gibt.
    """
    # Das schmale und das geschützte Leerzeichen trifft \s nicht —
    # Excel setzt sie als Tausendertrenner, also ausdrücklich weg damit.
    t = re.sub(r"\s", "", str(text or "")).replace("\u00a0", "").replace("\u202f", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return round(float(t), 2)
    except ValueError:
        return 0.0


def _mit_vorzeichen(zeile: dict) -> float:
    """Der Betrag einer Buchungszeile mit dem Vorzeichen ihrer Seite.

    In der Datei steht jeder Betrag positiv und die Seite daneben (S/H) —
    so führt DATEV das. Zum Summieren muss das Vorzeichen zurück, sonst
    zählte eine Gutschrift über 40 € wie eine Ausgabe über 40 € und die
    Summe unter der Tabelle wäre 80 € daneben.
    """
    wert = _betrag(zeile.get("umsatz"))
    return -wert if (zeile.get("sh") or "S").upper() == "H" else wert


def _euro(wert: float) -> str:
    return f"{wert:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _tag(belegdatum: str | None, monat: str) -> str:
    """`2107` + `2026-07` → `21.07.2026`. Der Stapel führt kein Jahr mit."""
    d = str(belegdatum or "")
    if len(d) != 4 or not d.isdigit():
        return ""
    return f"{d[:2]}.{d[2:]}.{monat[:4]}"


# ---------------------------------------------------------------------------
# Prüfbefund und Vorschau
# ---------------------------------------------------------------------------

def _sammeln(bw, un: str, monate: list[str]) -> dict:
    """Alles, was Vorschau, Befund und Datei gemeinsam brauchen — einmal."""
    idx = bw.index_aktuell()
    rahmen = bw.kontenrahmen_von(un)
    klein = _kleinunternehmerin(bw, un)
    je_monat = {}
    for monat in monate:
        reviews, mit, ohne, hinweise = _reviews(idx, monat, klein)
        je_monat[monat] = {"reviews": reviews, "staemme": mit, "ohne_konto": ohne,
                           "hinweise": hinweise,
                           "blaetter": _kassenblaetter(idx, monat)}
    berater, mandant = _berater_mandant(bw)
    return {"idx": idx, "rahmen": rahmen, "kleinunternehmerin": klein,
            "berater": berater, "mandant": mandant,
            "monate": monate, "je_monat": je_monat}


def _zeilen(daten: dict) -> list[dict]:
    """Die Buchungszeilen des ganzen Zeitraums, in Monatsreihenfolge.

    Dieselben Zeilen, die auch in die Datei gehen — sie kommen aus
    `extf.buchungszeilen` und `extf.erloeszeilen`, damit Vorschau und Datei
    nicht auseinanderlaufen können. Der Monat wandert mit, weil erst er aus
    dem `TTMM` des Stapels ein Datum macht.
    """
    aus: list[dict] = []
    for monat in daten["monate"]:
        m = daten["je_monat"][monat]
        for stamm, review in zip(m["staemme"], m["reviews"]):
            for z in extf.buchungszeilen(review,
                                         daten["kleinunternehmerin"]):
                aus.append(dict(z, monat=monat, quelle=stamm, art="beleg"))
        if daten["rahmen"] != "SKR03":
            for z in extf.erloeszeilen(m["blaetter"], daten["kleinunternehmerin"]):
                aus.append(dict(z, monat=monat, quelle="Kassenbuch", art="kasse"))
    return aus


def _feststellung(hinweise: list[dict], grund: str) -> list[dict]:
    return [h for h in hinweise if h.get("grund") == grund]


def _hinweistext(hinweise: list[dict], hoechstens: int = 3) -> str | None:
    """Aus mehreren gleichartigen Feststellungen ein Satz — ohne Wiederholung.

    Derselbe Grund an zwanzig Belegen soll nicht zwanzigmal dastehen: der
    Text steht einmal, die Belege dahinter, und ab dem vierten nur noch die
    Anzahl.
    """
    if not hinweise:
        return None
    texte: dict[str, list[str]] = {}
    for h in hinweise:
        # Ein Beleg hat einen Stamm, ein Kassentag ein Datum — beides ist
        # die Antwort auf „wo denn?".
        texte.setdefault(h["text"], []).append(
            str(h.get("beleg") or h.get("tag") or ""))
    stuecke = []
    for text, belege in texte.items():
        namen = [b for b in belege if b][:hoechstens]
        rest = len([b for b in belege if b]) - len(namen)
        wo = ", ".join(namen) + (f" und {rest} weitere" if rest > 0 else "")
        stuecke.append(f"{text} Betroffen: {wo}." if wo else text)
    return " ".join(stuecke)


def _befund(daten: dict, zeilen: list[dict]) -> dict:
    """Was jemand wissen muss, BEVOR er die Datei an die Kanzlei gibt."""
    rahmen = daten["rahmen"]
    alle_reviews = [r for m in daten["je_monat"].values() for r in m["reviews"]]
    pruef = extf.rahmen_pruefen(alle_reviews, rahmen)
    ohne_konto = [s for m in daten["je_monat"].values() for s in m["ohne_konto"]]
    benutzt = sorted({z["konto"] for z in zeilen} | {z["gegenkonto"] for z in zeilen})
    # Konten, zu denen babu keine Beschriftung kennt. Nur im SKR04 prüfbar —
    # den SKR03 hat babu nicht als Liste, und Raten wäre schlechter als
    # Schweigen. Ausgenommen ist GENAU EIN Konto: das Sammelkonto, gegen
    # das babu jede Ausgabe bucht (`extf.GEGENKONTO`) — das ist ein
    # Kreditor, kein Sachkonto, und steht deshalb in keiner Kontenliste.
    # Bis 03.09.2026 stand hier `not k.startswith("7")`: damit war JEDES
    # Konto ab 70000 von der Prüfung befreit, auch ein handkorrigiertes,
    # das dort nichts zu suchen hat.
    unbenannt = ([k for k in benutzt
                  if k != extf.GEGENKONTO and skr04_konten.name(k) is None]
                 if rahmen == "SKR04" else [])
    # Konten, die babu selbst vergibt, für die aber noch keine Steuer-
    # beratung bestätigt hat, dass sie richtig sind (`kontierung.geprueft`).
    # Sie gehen mit — es sind die besten, die babu hat — aber wer die Datei
    # weitergibt, soll wissen, worüber er einmal sprechen sollte.
    import kontierung as kt  # noqa: PLC0415 — nur für diesen Befund
    unbestaetigt = sorted({k.konto(rahmen) for k in kt.ungepruefte_konten()
                           if k.konto(rahmen)} & set(benutzt))
    # Buchungen ohne Belegdatum. Gefunden am 02.09.2026 beim Bau dieser
    # Seite: `extf.buchungszeilen` liest das Datum als `TT.MM.JJJJ`, die
    # Belege des Zielbild-Wegs tragen es aber als `JJJJ-MM-TT` (so schreibt
    # es die Buchhaltung auf dem Telefon). Ergebnis ist eine Buchungszeile
    # mit leerem Belegdatum — die Kanzlei sieht das erst beim Import.
    # Hier wird es nicht repariert (das gehört in `extf`, mit eigener
    # Prüfung), aber es wird gesagt, bevor die Datei aus dem Haus geht.
    ohne_datum = [z for z in zeilen if not z.get("belegdatum")]
    # Ein Belegdatum, das nicht in den Zeitraum des Stapels fällt. Der Kopf
    # der Datei nennt von und bis; eine Buchung mit einem Datum davor oder
    # danach lehnt der Import ab oder bucht sie in einen Monat, für den
    # niemand sie gemeint hat. Verglichen wird der Monat — mehr trägt das
    # DATEV-Belegdatum nicht, es ist `TTMM` ohne Jahr.
    erlaubte_monate = {m[5:7] for m in daten["monate"]}
    ausserhalb = [z for z in zeilen if z.get("belegdatum")
                  and str(z["belegdatum"])[2:4] not in erlaubte_monate]
    # Zeichen, die Windows-1252 nicht schreiben kann. Sie werden beim
    # Herunterladen zu Fragezeichen — es sei denn, man nimmt UTF-8.
    zeichen_ersetzt = sum(extf.nicht_darstellbar(z.get("text") or "")
                          + extf.nicht_darstellbar(z.get("belegfeld1") or "")
                          for z in zeilen)
    # Die Kassentage. Sie hängen an der Erlösseite des Stapels und werden
    # dort gerechnet, nicht hier — `extf.kassen_pruefen` ist dieselbe
    # Bauart wie `extf.pruefen`.
    blaetter = [b for m in daten["je_monat"].values()
                for b in (m.get("blaetter") or [])]
    kassen = extf.kassen_pruefen(blaetter) if rahmen != "SKR03" else []
    # Die Feststellungen aus `extf.pruefen`, über alle Monate zusammengelegt.
    # `.get` und nicht `[…]`: Tests und ältere Aufrufer bauen `je_monat`
    # selbst und kennen den Schlüssel nicht.
    hinweise = [h for m in daten["je_monat"].values()
                for h in (m.get("hinweise") or [])]
    ohne_steuersatz = _feststellung(hinweise, "steuersatz_unbekannt")
    zurueckgehalten = [h for h in hinweise if h.get("hart")]
    kassen_hart = [h for h in kassen if h.get("hart")]
    kassen_weich = [h for h in kassen if not h.get("hart")]
    # Soll minus Haben: eine Gutschrift mindert die Summe, statt sie zu
    # erhöhen. Die Zahl unter der Tabelle soll dasselbe sagen wie die
    # Buchhaltung — was der Monat gekostet hat, nicht was durchgelaufen ist.
    summe = round(sum(_mit_vorzeichen(z) for z in zeilen), 2)
    gutschriften = [z for z in zeilen if (z.get("sh") or "S").upper() == "H"]
    # Berater- und Mandantennummer. Sie halten den Stapel NICHT auf — die
    # Datei ist inhaltlich richtig, sie kommt nur ohne Adresse an. Deshalb
    # steht das hier neben `sauber` und nicht darin: `sauber` sagt etwas
    # über die Buchungen, das hier über den Umschlag.
    stammdaten = [n for n, w in (("Beraternummer", daten.get("berater")),
                                 ("Mandantennummer", daten.get("mandant")))
                  if _nummer_fehlt(w)]
    return {
        "rahmen": rahmen,
        "berater": daten.get("berater") or "",
        "mandant": daten.get("mandant") or "",
        "stammdaten_fehlen": stammdaten,
        "stammdaten_text": (None if not stammdaten else
                            f"Im Kopf des Stapels fehlt die "
                            f"{' und die '.join(stammdaten)}. Die Datei "
                            f"lässt sich herunterladen, aber die Kanzlei "
                            f"muss sie von Hand dem richtigen Betrieb "
                            f"zuordnen."),
        "sauber": (pruef.sauber and not ohne_konto and not unbenannt
                   and not ohne_datum and not zurueckgehalten
                   and not ausserhalb and not kassen_hart),
        # Gelb: die Buchung geht mit, aber jemand sollte hinsehen.
        "ohne_steuersatz": [h["beleg"] for h in ohne_steuersatz],
        # Rot: die Buchung geht NICHT mit — oder sie wäre falsch.
        "zurueckgehalten": [{"beleg": h.get("beleg"), "grund": h["grund"],
                             "text": h["text"]} for h in zurueckgehalten],
        "zurueckgehalten_text": _hinweistext(zurueckgehalten),
        "ohne_belegdatum": len(ohne_datum),
        "ohne_belegdatum_belege": sorted({z["quelle"] for z in ohne_datum})[:8],
        "vermischt": pruef.vermischt,
        "vermischt_belege": pruef.belege,
        "vermischt_text": None if pruef.sauber else pruef.meldung(),
        "fremde_konten": pruef.unbekannt,
        "ohne_kontierung": ohne_konto,
        "unbenannte_konten": unbenannt,
        "unbestaetigte_konten": unbestaetigt,
        # Rot: das Belegdatum liegt nicht im Zeitraum, den der Kopf nennt.
        "ausserhalb_zeitraum": len(ausserhalb),
        "ausserhalb_zeitraum_belege": sorted({z["quelle"] for z in ausserhalb
                                              if z.get("quelle")})[:8],
        # Gelb: Zeichen, die beim Herunterladen ersetzt würden.
        "zeichen_ersetzt": zeichen_ersetzt,
        # Die Kassentage — rot, was nicht aufgeht, gelb, was vermerkt ist.
        "kassen_hart": [{"tag": h["tag"], "grund": h["grund"],
                         "text": h["text"]} for h in kassen_hart],
        "kassen_weich": [{"tag": h["tag"], "grund": h["grund"],
                          "text": h["text"]} for h in kassen_weich],
        "kassen_hart_text": _hinweistext(kassen_hart),
        "kassen_weich_text": _hinweistext(kassen_weich),
        "belege": sum(len(m["staemme"]) for m in daten["je_monat"].values()),
        "kassentage": sum(len(m["blaetter"]) for m in daten["je_monat"].values()),
        "buchungen": len(zeilen),
        "gutschriften": len(gutschriften),
        "summe": summe,
        "summe_text": _euro(summe),
    }


def _je_konto(zeilen: list[dict]) -> list[dict]:
    topf: dict[str, dict] = {}
    for z in zeilen:
        e = topf.setdefault(z["konto"], {"konto": z["konto"], "anzahl": 0, "summe": 0.0})
        e["anzahl"] += 1
        e["summe"] = round(e["summe"] + _mit_vorzeichen(z), 2)
    for e in topf.values():
        e["name"] = skr04_konten.name(e["konto"]) or ""
        e["summe_text"] = _euro(e["summe"])
    return sorted(topf.values(), key=lambda e: e["konto"])


# ---------------------------------------------------------------------------
# Die Datei — Kopfzeile über mehrere Monate
# ---------------------------------------------------------------------------

def stapel_zeitraum(daten: dict, monate: list[str], festschreibung: bool,
                    berater: str, mandant: str,
                    erzeugt: time.struct_time | None = None) -> str:
    """Ein Stapel über mehrere Monate — eine Datei, eine Kopfzeile.

    `extf.stapel` kann genau einen Monat, und das soll so bleiben: dort
    steht das Format, und je weniger Stellen es kennen, desto weniger
    Stellen können es falsch schreiben. Also wird je Monat ein Stapel
    erzeugt und die Kopfzeile des ersten auf das Ende des letzten gezogen;
    die Datenzeilen werden angehängt. Kopfzeile und Spaltenzeile stehen
    danach genau einmal in der Datei.
    """
    kopf: list[str] | None = None
    spalten = ""
    daten_zeilen: list[str] = []
    for monat in monate:
        m = daten["je_monat"][monat]
        text = extf.stapel(
            m["reviews"], monat, erzeugt=erzeugt, berater=berater, mandant=mandant,
            festschreibung=festschreibung, rahmen=daten["rahmen"],
            kassenblaetter=m["blaetter"],
            kleinunternehmerin=daten["kleinunternehmerin"])
        zeilen = [z for z in text.split("\r\n") if z]
        if kopf is None:
            kopf = zeilen[0].split(";")
        spalten = zeilen[1]
        daten_zeilen += zeilen[2:]
    if kopf is None:
        return ""
    # Feld 16 ist das Datumsende des Stapels, Feld 17 seine Bezeichnung —
    # die Zählung folgt der Kopfliste in `extf.stapel`.
    letzter = monate[-1]
    jahr, mm = int(letzter[:4]), int(letzter[5:7])
    kopf[15] = f"{jahr}{mm:02d}{calendar.monthrange(jahr, mm)[1]}"
    kopf[16] = f'"babu {monate[0]} bis {letzter}"' if len(monate) > 1 \
        else f'"babu {monate[0]}"'
    return "\r\n".join([";".join(kopf), spalten, *daten_zeilen]) + "\r\n"


def _stammdaten_kopf(kategorie: int, name: str, version: int, jahr: int,
                     berater: str, mandant: str,
                     erzeugt: time.struct_time | None = None) -> str:
    """Die EXTF-Kopfzeile für eine Stammdaten-Datei.

    Feld für Feld dieselbe Reihenfolge wie die Kopfliste in `extf.stapel` —
    es ist dasselbe Kopfformat, nur mit anderer Kategorie und ohne die
    Felder, die nur ein Buchungsstapel hat (Datum von/bis, Festschreibung).
    """
    stempel = time.strftime("%Y%m%d%H%M%S", erzeugt or time.localtime()) + "000"
    return ";".join([
        '"EXTF"', "700", str(kategorie), f'"{name}"', str(version), stempel, "",
        f'"{extf.HERKUNFT}"', '"babu"', "", berater, mandant, f"{jahr}0101",
        extf.SACHKONTENLAENGE, "", "", f'"babu {name}"', '""', "", "",
        "", '"EUR"', "", "", "", "", "", "", "", "", "",
    ])


def _csv_feld(wert) -> str:
    return '"' + str(wert or "").replace('"', "'") + '"'


# ---------------------------------------------------------------------------
# Zeichensatz der Ausgabe
# ---------------------------------------------------------------------------
#
# babu schreibt seit jeher Windows-1252 — das nimmt jede DATEV-Fassung an,
# und dabei bleibt es als Standard. Der echte Export der Kanzlei kommt aber
# als UTF-8; wer beide Dateien nebeneinanderlegt oder einen Namen mit einem
# Buchstaben braucht, den Windows-1252 gar nicht kennt, kann mit
# `?zeichensatz=utf8` umschalten. Ohne den Zusatz ändert sich nichts.

UTF8_NAMEN = ("utf8", "utf-8", "utf_8")


def _utf8_gewuenscht(zeichensatz: str) -> bool:
    return str(zeichensatz or "").strip().lower().replace(" ", "") in UTF8_NAMEN


def _csv_antwort(text: str, dateiname: str, utf8: bool) -> Response:
    art = ("text/csv; charset=utf-8" if utf8
           else "text/csv; charset=windows-1252")
    return Response(content=extf.als_bytes(text, utf8_bom=utf8),
                    media_type=art,
                    headers={"Content-Disposition":
                             f'attachment; filename="{dateiname}"'})


def spalten_abweichung(spalten: list[str]) -> str | None:
    """Trägt die gelesene Datei eine andere Spaltenzeile als babu selbst?

    Reine Rechnung, keine Wertung: die Antwort ist ein Satz für die Seite
    oder `None`. Eine abweichende Spaltenzeile ist kein Fehler — DATEV
    ergänzt Spalten von Fassung zu Fassung, und gelesen wird ohnehin über
    die Namen (siehe `_GESUCHT`). Sie ist aber der erste Hinweis darauf,
    dass die Kanzlei mit einer anderen Fassung arbeitet als babu schreibt,
    und das will man wissen, bevor man rät.
    """
    eigene = list(extf.SPALTEN)
    haben = [str(n or "").strip() for n in spalten]
    if [n.lower() for n in haben] == [n.lower() for n in eigene]:
        return None
    saetze = []
    if len(haben) != len(eigene):
        saetze.append(f"Die Datei führt {len(haben)} Spalten, babu schreibt "
                      f"{len(eigene)}.")
    erste = next((i for i, (a, b) in enumerate(zip(haben, eigene))
                  if a.lower() != b.lower()), None)
    if erste is not None:
        saetze.append(f"Die erste Abweichung steht an Stelle {erste + 1}: dort "
                      f"heißt die Spalte „{haben[erste]}“, bei babu "
                      f"„{eigene[erste]}“.")
    elif len(haben) > len(eigene):
        zusatz = ", ".join(x for x in haben[len(eigene):] if x)[:200]
        saetze.append(f"Am Ende stehen zusätzliche Spalten: {zusatz}.")
    elif len(haben) < len(eigene):
        fehlt = ", ".join(x for x in eigene[len(haben):])[:200]
        saetze.append(f"Am Ende fehlen Spalten: {fehlt}.")
    saetze.append("Gelesen wurde trotzdem — babu sucht die Spalten über "
                  "ihren Namen, nicht über ihre Stelle.")
    return " ".join(saetze)


# ---------------------------------------------------------------------------
# Routen: Übersicht, Vorschau, Datei
# ---------------------------------------------------------------------------

@router.get("/uebersicht")
def api_uebersicht(request: Request) -> Response:
    """Womit die Seite startet: welche Monate es gibt, welcher Rahmen gilt."""
    un, fehler = _wache(request)
    if fehler:
        return fehler
    bw = _bw()
    idx = bw.index_aktuell()
    monate = sorted({z["monat"] for z in idx["belege"].values()
                     if MONAT_MUSTER.match(z["monat"] or "")}, reverse=True)
    offen = {}
    for m in monate:
        zeilen = [z for z in idx["belege"].values() if z["monat"] == m]
        offen[m] = {
            "belege": len(zeilen),
            "fertig": sum(1 for z in zeilen
                          if z["status"] in ("geprüft", "exportiert")),
            "kassentage": len(_kassenblaetter(idx, m)),
        }
    berater, mandant = _berater_mandant(bw)
    return JSONResponse({
        "monate": monate,
        "je_monat": offen,
        "rahmen": bw.kontenrahmen_von(un),
        "kleinunternehmerin": _kleinunternehmerin(bw, un),
        # Wessen Buchhaltung das ist — im Kopf der Seite, damit niemand
        # den Stapel des falschen Betriebs weitergibt.
        "berater": berater, "mandant": mandant,
        "stammdaten_fehlen": [n for n, w in (("Beraternummer", berater),
                                             ("Mandantennummer", mandant))
                              if _nummer_fehlt(w)],
    })


@router.get("/vorschau")
def api_vorschau(request: Request, von: str = "", bis: str = "") -> Response:
    """Der Blick in den Stapel, bevor es ihn als Datei gibt."""
    un, fehler = _wache(request)
    if fehler:
        return fehler
    monate, meldung = _zeitraum(von, bis)
    if meldung:
        return _fehler(meldung)
    bw = _bw()
    daten = _sammeln(bw, un, monate)
    zeilen = _zeilen(daten)
    tabelle = [{
        "datum": _tag(z["belegdatum"], z["monat"]),
        "konto": z["konto"],
        "konto_name": skr04_konten.name(z["konto"]) or "",
        "gegenkonto": z["gegenkonto"],
        "umsatz": z["umsatz"],
        "sh": (z.get("sh") or "S"),
        "bu": z["bu"] or "",
        "belegfeld": z["belegfeld1"] or "",
        "text": z["text"],
        "quelle": z["quelle"],
        "art": z["art"],
    } for z in zeilen]
    return JSONResponse({
        "von": monate[0], "bis": monate[-1], "monate": monate,
        "befund": _befund(daten, zeilen),
        "zeilen": tabelle,
        "je_konto": _je_konto(zeilen),
        "festgeschrieben": all(bw._monat_festgeschrieben(m) for m in monate),
    })


@router.get("/stapel.csv")
def api_stapel(request: Request, von: str = "", bis: str = "",
               zeichensatz: str = "") -> Response:
    """Der Buchungsstapel als Datei. Schreibt nichts in die Belegbox —
    das Festschreiben hängt weiter am freigegebenen Monatsabschluss."""
    un, fehler = _wache(request)
    if fehler:
        return fehler
    monate, meldung = _zeitraum(von, bis)
    if meldung:
        return _fehler(meldung)
    bw = _bw()
    daten = _sammeln(bw, un, monate)
    try:
        text = stapel_zeitraum(
            daten, monate,
            festschreibung=all(bw._monat_festgeschrieben(m) for m in monate),
            berater=daten["berater"], mandant=daten["mandant"])
    except extf.RahmenVermischung as fehler_:
        return _fehler(str(fehler_), 409)
    name = (f"EXTF_Buchungsstapel_{monate[0]}.csv" if len(monate) == 1
            else f"EXTF_Buchungsstapel_{monate[0]}_bis_{monate[-1]}.csv")
    # Hier verlassen Steuerdaten das Haus — dieselbe Zeile wie bei
    # `/api/export/{monat}.csv` in `babu_web`, und aus demselben Grund. Die
    # Mandantennummer gehört ausdrücklich hinein: beim Acting-as sagt erst
    # sie, WESSEN Stapel jemand mitgenommen hat.
    import audit  # noqa: PLC0415 — nur dieser eine Weg auditiert
    audit.audit(un, "datev_stapel", mandant_id=bw._mandant_fuers_log(),
                von=monate[0], bis=monate[-1], monate=len(monate))
    return _csv_antwort(text, name, _utf8_gewuenscht(zeichensatz))


@router.get("/konten.csv")
def api_konten(request: Request, von: str = "", bis: str = "",
               zeichensatz: str = "") -> Response:
    """Kontenbeschriftungen der Konten, die in diesem Zeitraum vorkommen.

    Nur die benutzten: eine Datei mit dem ganzen SKR04 hilft niemandem, und
    die Kanzlei will wissen, was babu vergeben hat, nicht was DATEV kennt.
    """
    un, fehler = _wache(request)
    if fehler:
        return fehler
    monate, meldung = _zeitraum(von, bis)
    if meldung:
        return _fehler(meldung)
    bw = _bw()
    daten = _sammeln(bw, un, monate)
    zeilen = _zeilen(daten)
    konten = sorted({z["konto"] for z in zeilen} | {z["gegenkonto"] for z in zeilen})
    aus = [_stammdaten_kopf(20, "Kontenbeschriftungen", 3, int(monate[0][:4]),
                            daten["berater"], daten["mandant"]),
           ";".join(['"Konto"', '"Kontenbeschriftung"', '"Sprach-ID"',
                     '"Kontenbeschriftung lang"'])]
    for k in konten:
        name = skr04_konten.name(k) or ""
        aus.append(";".join([k, _csv_feld(name[:40]), '"de-DE"', _csv_feld(name)]))
    text = "\r\n".join(aus) + "\r\n"
    return _csv_antwort(text, f"EXTF_Kontenbeschriftungen_{monate[0]}.csv",
                        _utf8_gewuenscht(zeichensatz))


@router.get("/kreditoren.csv")
def api_kreditoren(request: Request, von: str = "", bis: str = "") -> Response:
    """Die Lieferanten des Zeitraums als Liste.

    babu bucht alle Ausgaben gegen das Sammelkonto (siehe `extf.GEGENKONTO`)
    — eigene Kreditorennummern vergibt es nicht, weil es sie nicht kennt.
    Die Nummern hier sind deshalb ausdrücklich ein VORSCHLAG zum Anlegen,
    fortlaufend ab 70001, und die Spalte heißt auch so. Wer sie anders
    vergibt, hat recht; wer sie übernimmt, hat eine Startaufstellung.
    """
    un, fehler = _wache(request)
    if fehler:
        return fehler
    monate, meldung = _zeitraum(von, bis)
    if meldung:
        return _fehler(meldung)
    bw = _bw()
    idx = bw.index_aktuell()
    topf: dict[str, dict] = {}
    for z in idx["belege"].values():
        if z["monat"] not in monate or z["status"] not in ("geprüft", "exportiert"):
            continue
        name = (z.get("lieferant") or "").strip()
        if not name:
            continue
        e = topf.setdefault(name, {"name": name, "anzahl": 0, "summe": 0.0,
                                   "erster": "", "letzter": ""})
        e["anzahl"] += 1
        e["summe"] = round(e["summe"] + float(z.get("brutto") or 0), 2)
        d = z.get("datum") or ""
        if d:
            e["erster"] = min(e["erster"] or d, d, key=_sortdatum)
            e["letzter"] = max(e["letzter"] or d, d, key=_sortdatum)
    aus = [";".join(['"Konto (Vorschlag)"', '"Name"', '"Belege"', '"Summe EUR"',
                     '"Erster Beleg"', '"Letzter Beleg"'])]
    for i, e in enumerate(sorted(topf.values(), key=lambda x: x["name"].lower())):
        aus.append(";".join([str(70001 + i), _csv_feld(e["name"]), str(e["anzahl"]),
                             _csv_feld(_euro(e["summe"])), _csv_feld(e["erster"]),
                             _csv_feld(e["letzter"])]))
    text = "\r\n".join(aus) + "\r\n"
    return Response(content=extf.als_bytes(text),
                    media_type="text/csv; charset=windows-1252",
                    headers={"Content-Disposition":
                             f'attachment; filename="Kreditoren_{monate[0]}.csv"'})


def _sortdatum(d: str) -> str:
    """`21.07.2026` sortiert sich als Text falsch — hier wird es sortierbar."""
    t = str(d or "").split(".")
    return f"{t[2]}{t[1]}{t[0]}" if len(t) == 3 else str(d or "")


# ---------------------------------------------------------------------------
# Hereinlesen: Datei lesen, verstehen, vergleichen — nie übernehmen.
# ---------------------------------------------------------------------------

class StapelFehler(Exception):
    """Die Datei ist keine, die sich lesen lässt — mit einem Satz dazu."""


def _entziffern(roh: bytes) -> str:
    """Welcher Zeichensatz? Erst UTF-8, dann Windows-1252.

    In dieser Reihenfolge, weil ein deutscher Windows-Text mit Umlauten als
    UTF-8 fast immer scheitert, ein UTF-8-Text als Windows-1252 dagegen
    stillschweigend zu Buchstabensalat wird. Wer zuerst das Strengere
    versucht, bekommt den Fehler statt des Salats.
    """
    if roh.startswith(b"\xef\xbb\xbf"):
        return roh.decode("utf-8-sig")
    for kodierung in ("utf-8", "cp1252"):
        try:
            return roh.decode(kodierung)
        except UnicodeDecodeError:
            continue
    raise StapelFehler("Der Zeichensatz der Datei lässt sich nicht lesen. "
                       "DATEV speichert Buchungsstapel als Windows-1252 "
                       "oder UTF-8.")


# Die Spalten, die für den Vergleich zählen. Gesucht wird über den NAMEN aus
# der zweiten Zeile, nicht über die Position: DATEV-Versionen schieben
# Spalten, Namen bleiben. Erst wenn kein Name passt, wird auf die Position
# in `extf.SPALTEN` zurückgefallen.
_GESUCHT = {
    "umsatz": (lambda n: n.startswith("umsatz"), 0),
    "sh": (lambda n: n.startswith("soll/haben"), 1),
    "konto": (lambda n: n == "konto", 6),
    "gegenkonto": (lambda n: n.startswith("gegenkonto"), 7),
    "bu": (lambda n: n.startswith("bu-schl"), 8),
    "belegdatum": (lambda n: n == "belegdatum", 9),
    "belegfeld1": (lambda n: n.replace(" ", "") == "belegfeld1", 10),
    "text": (lambda n: n == "buchungstext", 13),
}
PFLICHT = ("umsatz", "konto", "belegdatum")


def stapel_lesen(roh: bytes) -> dict:
    """Eine EXTF-Buchungsstapeldatei → Kopf, Zeilen, Prüfsummen.

    Wirft `StapelFehler` mit einem Satz, den man jemandem zeigen kann. Kein
    Fall endet hier in einem Abbruch mit Innenansicht: eine falsche Datei
    ist ein Bedienfehler, kein Programmfehler.
    """
    if not roh.strip():
        raise StapelFehler("Die Datei ist leer.")
    text = _entziffern(roh)
    zeilen = [z for z in text.replace("\r\n", "\n").split("\n") if z.strip()]
    if not zeilen:
        raise StapelFehler("Die Datei ist leer.")
    kopf = next(csv.reader([zeilen[0]], delimiter=";", quotechar='"'))
    kennung = (kopf[0] if kopf else "").strip().upper()
    if kennung not in ("EXTF", "DTVF"):
        raise StapelFehler("Das ist keine DATEV-Datei — in der ersten Zeile "
                           "fehlt die Kennung „EXTF“.")
    kategorie = (kopf[2] if len(kopf) > 2 else "").strip()
    if kategorie != "21":
        bezeichnung = (kopf[3] if len(kopf) > 3 else "").strip() or "unbekannt"
        raise StapelFehler(f"Diese DATEV-Datei ist kein Buchungsstapel, "
                           f"sondern „{bezeichnung}“. Gebraucht wird ein "
                           f"Buchungsstapel.")
    if len(zeilen) < 3:
        raise StapelFehler("Die Datei enthält keine Buchungen.")
    namen_roh = [n.strip().strip('"')
                 for n in next(csv.reader([zeilen[1]], delimiter=";",
                                          quotechar='"'))]
    namen = [n.lower() for n in namen_roh]
    spalte: dict[str, int] = {}
    for schluessel, (passt, standard) in _GESUCHT.items():
        treffer = next((i for i, n in enumerate(namen) if passt(n)), None)
        if treffer is None and standard < len(namen):
            treffer = standard
        if treffer is not None:
            spalte[schluessel] = treffer
    fehlend = [s for s in PFLICHT if s not in spalte]
    if fehlend:
        raise StapelFehler("Die Spaltenzeile der Datei passt nicht zu einem "
                           "Buchungsstapel — es fehlen Pflichtspalten.")

    jahr = ((kopf[14] if len(kopf) > 14 else "") or
            (kopf[12] if len(kopf) > 12 else ""))[:4]
    von = (kopf[14] if len(kopf) > 14 else "").strip()
    bis = (kopf[15] if len(kopf) > 15 else "").strip()
    monate = _monate_aus_kopf(von, bis)

    def hol(reihe: list[str], schluessel: str) -> str:
        i = spalte.get(schluessel)
        return (reihe[i].strip().strip('"') if i is not None and i < len(reihe)
                else "")

    buchungen: list[dict] = []
    for nr, zeile in enumerate(zeilen[2:], start=3):
        reihe = next(csv.reader([zeile], delimiter=";", quotechar='"'))
        if not any(f.strip() for f in reihe):
            continue
        umsatz = _betrag(hol(reihe, "umsatz"))
        datum = re.sub(r"\D", "", hol(reihe, "belegdatum"))[:4]
        buchungen.append({
            "nr": nr, "umsatz": umsatz, "umsatz_text": _euro(umsatz),
            "sh": (hol(reihe, "sh") or "S").upper()[:1],
            "konto": hol(reihe, "konto"), "gegenkonto": hol(reihe, "gegenkonto"),
            "bu": hol(reihe, "bu"), "belegdatum": datum,
            "datum": _tag(datum, f"{jahr}-01") if jahr else "",
            "belegfeld": hol(reihe, "belegfeld1"), "text": hol(reihe, "text"),
        })
    if not buchungen:
        raise StapelFehler("Die Datei enthält keine Buchungen.")
    soll = round(sum(b["umsatz"] for b in buchungen if b["sh"] != "H"), 2)
    haben = round(sum(b["umsatz"] for b in buchungen if b["sh"] == "H"), 2)
    return {
        "bezeichnung": (kopf[16] if len(kopf) > 16 else "").strip().strip('"'),
        "berater": (kopf[10] if len(kopf) > 10 else "").strip(),
        "mandant": (kopf[11] if len(kopf) > 11 else "").strip(),
        "jahr": jahr, "von": von, "bis": bis, "monate": monate,
        "formatversion": (kopf[4] if len(kopf) > 4 else "").strip().strip('"'),
        "spalten": namen_roh,
        "buchungen": buchungen,
        "summen": {"anzahl": len(buchungen), "soll": soll, "haben": haben,
                   "soll_text": _euro(soll), "haben_text": _euro(haben)},
    }


def _monate_aus_kopf(von: str, bis: str) -> list[str]:
    """`20260701` + `20260930` → die drei Monate dazwischen."""
    if len(von) != 8 or len(bis) != 8 or not von.isdigit() or not bis.isdigit():
        return []
    a, b = f"{von[:4]}-{von[4:6]}", f"{bis[:4]}-{bis[4:6]}"
    monate, mm = [], int(von[4:6])
    if a[:4] != b[:4]:
        return [a]
    while mm <= int(bis[4:6]) and len(monate) <= MONATE_MAX:
        monate.append(f"{von[:4]}-{mm:02d}")
        mm += 1
    return monate


# ── Der Abgleich ────────────────────────────────────────────────────────────
#
# Verglichen wird über Datum + Betrag + Belegfeld, und zwar in drei Wellen,
# von streng nach nachsichtig. Der Grund ist die Praxis: dieselbe Buchung
# trägt in DATEV oft eine andere Belegnummer (die Kanzlei vergibt eigene)
# und manchmal einen um Cent abweichenden Betrag (Skonto, Rundung). Wer nur
# streng vergleicht, meldet lauter Unterschiede, die keine sind.
#
#   1. Datum + Betrag + Belegfeld   — dieselbe Buchung, unstrittig
#   2. Datum + Betrag               — dieselbe Buchung, andere Belegnummer
#   3. Datum + Belegfeld            — dieselbe Buchung, ANDERER BETRAG
#
# Was danach übrig ist, hat auf der einen Seite keine Entsprechung. Welle 3
# ist die interessante: sie findet den Tippfehler, den die anderen beiden
# als „fehlt hier, fehlt dort" doppelt melden würden.

def _schluessel(z: dict, mit_feld: bool) -> tuple:
    feld = (z.get("belegfeld") or "").strip().upper()
    return (z.get("belegdatum") or "", round(z.get("umsatz") or 0, 2),
            feld if mit_feld else "")


def abgleich(unsere: list[dict], fremde: list[dict]) -> dict:
    """Drei Listen: nur im Stapel, nur bei uns, im Betrag abweichend."""
    offen_u = list(range(len(unsere)))
    offen_f = list(range(len(fremde)))

    def welle(mit_feld: bool) -> None:
        topf: dict[tuple, list[int]] = {}
        for i in offen_f:
            topf.setdefault(_schluessel(fremde[i], mit_feld), []).append(i)
        bleibt_u, getroffen = [], set()
        for i in offen_u:
            kandidaten = topf.get(_schluessel(unsere[i], mit_feld)) or []
            frei = next((k for k in kandidaten if k not in getroffen), None)
            if frei is None:
                bleibt_u.append(i)
            else:
                getroffen.add(frei)
        offen_u[:] = bleibt_u
        offen_f[:] = [i for i in offen_f if i not in getroffen]

    welle(True)
    welle(False)

    # Welle 3: gleiches Datum, gleiche Belegnummer, anderer Betrag.
    abweichend: list[dict] = []
    topf: dict[tuple, list[int]] = {}
    for i in offen_f:
        feld = (fremde[i].get("belegfeld") or "").strip().upper()
        if feld:
            topf.setdefault((fremde[i].get("belegdatum") or "", feld), []).append(i)
    verbraucht: set[int] = set()
    bleibt_u = []
    for i in offen_u:
        feld = (unsere[i].get("belegfeld") or "").strip().upper()
        schl = (unsere[i].get("belegdatum") or "", feld)
        frei = next((k for k in topf.get(schl, []) if k not in verbraucht),
                    None) if feld else None
        if frei is None:
            bleibt_u.append(i)
            continue
        verbraucht.add(frei)
        u, f = unsere[i], fremde[frei]
        abweichend.append({
            "datum": u.get("datum") or f.get("datum") or "",
            "belegfeld": u.get("belegfeld") or "",
            "text": u.get("text") or f.get("text") or "",
            "konto": u.get("konto") or "", "konto_datev": f.get("konto") or "",
            "betrag": u.get("umsatz"), "betrag_text": _euro(u.get("umsatz") or 0),
            "betrag_datev": f.get("umsatz"),
            "betrag_datev_text": _euro(f.get("umsatz") or 0),
            "differenz": round((f.get("umsatz") or 0) - (u.get("umsatz") or 0), 2),
        })
    offen_u[:] = bleibt_u
    offen_f[:] = [i for i in offen_f if i not in verbraucht]

    def zeige(z: dict) -> dict:
        return {"datum": z.get("datum") or "", "konto": z.get("konto") or "",
                "gegenkonto": z.get("gegenkonto") or "",
                "betrag_text": _euro(z.get("umsatz") or 0),
                "belegfeld": z.get("belegfeld") or "", "text": z.get("text") or ""}

    nur_datev = [zeige(fremde[i]) for i in offen_f]
    nur_babu = [zeige(unsere[i]) for i in offen_u]
    return {
        "nur_datev": nur_datev, "nur_babu": nur_babu, "abweichend": abweichend,
        "zaehler": {"gleich": len(unsere) - len(nur_babu) - len(abweichend),
                    "nur_datev": len(nur_datev), "nur_babu": len(nur_babu),
                    "abweichend": len(abweichend)},
    }


@router.post("/lesen")
async def api_lesen(request: Request, datei: UploadFile = File(...)) -> Response:
    """Eine Stapeldatei hereinlesen, anzeigen, vergleichen — nichts speichern.

    Die Datei wird in den Speicher gelesen und nach der Antwort vergessen.
    Sie landet an keiner Stelle auf der Platte, und in die Belegbox wird
    beim Hereinlesen nichts geschrieben.
    """
    un, fehler = _wache(request)
    if fehler:
        return fehler
    if _lese_gebremst(un):
        return _fehler("Gerade wurden viele Dateien hereingelesen — "
                       "kurz warten, dann noch einmal.", 429)
    name = (datei.filename or "").lower()
    if not name.endswith(ENDUNGEN):
        return _fehler("Bitte eine Datei mit der Endung .csv oder .txt wählen.")
    roh = await datei.read(UPLOAD_MAX + 1)
    if len(roh) > UPLOAD_MAX:
        return _fehler(f"Die Datei ist größer als "
                       f"{UPLOAD_MAX // (1024 * 1024)} MB.")
    try:
        gelesen = stapel_lesen(roh)
    except StapelFehler as f:
        return _fehler(str(f))
    except Exception:  # noqa: BLE001
        # Alles, was hier ankommt, ist eine Datei, mit der niemand gerechnet
        # hat. Eine Innenansicht hülfe der Nutzerin nicht.
        return _fehler("Diese Datei lässt sich nicht als Buchungsstapel lesen.")

    bw = _bw()
    monate = gelesen["monate"]
    vergleich = None
    if monate:
        daten = await run_in_threadpool(_sammeln, bw, un, monate)
        unsere = [dict(z, umsatz=_betrag(z["umsatz"]),
                       datum=_tag(z["belegdatum"], z["monat"]),
                       belegfeld=z["belegfeld1"] or "")
                  for z in _zeilen(daten)]
        vergleich = abgleich(unsere, gelesen["buchungen"])
        vergleich["monate"] = monate
    return JSONResponse({
        "kopf": {k: gelesen[k] for k in ("bezeichnung", "berater", "mandant",
                                         "jahr", "von", "bis", "monate",
                                         "formatversion")},
        "summen": gelesen["summen"],
        "zeilen": gelesen["buchungen"][:500],
        "gekuerzt": max(0, len(gelesen["buchungen"]) - 500),
        "abgleich": vergleich,
        # Eine Spaltenzeile, die anders aussieht als babus eigene, ist kein
        # Fehler — aber sie sagt, dass die Kanzlei mit einer anderen Fassung
        # arbeitet. Das gehört auf die Seite, nicht ins Rätselraten.
        "spalten_hinweis": spalten_abweichung(gelesen["spalten"]),
        "hinweis": "Gelesen und verglichen. In der Belegbox wurde nichts "
                   "geändert.",
    })


# ---------------------------------------------------------------------------
# Die Seite selbst — gated wie ihre Routen (babu_web reicht nur durch).
# ---------------------------------------------------------------------------

VERBOTEN = ("<!doctype html><html lang=de><meta charset=utf-8>"
            "<title>Kein Zugang</title>"
            "<body style=\"font:16px/1.6 -apple-system,sans-serif;"
            "max-width:34em;margin:14vh auto;padding:0 22px;color:#453e31\">"
            "<h1 style=\"font:500 26px Georgia,serif;color:#1d1913\">"
            "Kein Zugang</h1><p>Diese Seite ist der Verwaltung vorbehalten."
            "<p><a href=\"/portal\" style=\"color:#8a7c5c\">‹ Zum Portal</a>")
