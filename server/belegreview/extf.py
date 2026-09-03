"""EXTF-Writer — DATEV-Format Buchungsstapel (Bauplan Phase 5).

Erzeugt einen importierbaren Buchungsstapel: EXTF-Kopfzeile (Format 700,
Kategorie 21 Buchungsstapel, Formatversion 12), Spaltenzeile mit 124
Spalten, eine Buchungszeile je Steuersatz (Mehrsatz-Split: 19 % + 7 % auf
einem Bon werden zwei Sätze — der dm-Fall aus dem Testkorpus). Kodierung
ist Sache des Aufrufers: `als_bytes()` liefert Windows-1252 mit CRLF, auf
Wunsch UTF-8.

Version und Spaltenzahl sind seit 03.09.2026 an einem echten Export der
Kanzlei ausgerichtet (`historie/2026/stapel.csv` in Ninas Belegbox, siehe
`docs/uebergabe-datev-2026-09-02/23-referenzstapel-kanzlei.md`): dort steht
Formatversion 12 und eine Spaltenzeile mit 124 Spalten — babus bisherige
120 in genau derselben Reihenfolge plus vier am Ende.

Abnahme laut Spec: fehlerfreier Import in einer echten DATEV-Instanz —
die Golden-File-Tests frieren das Format ein, der Import-Test beim
Steuerberater bleibt der letzte Schritt vor dem Produktivgang.
"""
import calendar
import re
import time
from dataclasses import dataclass, field

import skr04_automatik

import kontierung as kt

BERATER = "0"        # per Env/Einstellung überschreibbar — vor Produktivgang setzen
MANDANT = "0"
SACHKONTENLAENGE = "4"
GEGENKONTO = "70099"
HERKUNFT = "BA"      # babu

SPALTEN = [
    "Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen", "WKZ Umsatz", "Kurs",
    "Basis-Umsatz", "WKZ Basis-Umsatz", "Konto", "Gegenkonto (ohne BU-Schlüssel)",
    "BU-Schlüssel", "Belegdatum", "Belegfeld 1", "Belegfeld 2", "Skonto",
    "Buchungstext", "Postensperre", "Diverse Adressnummer", "Geschäftspartnerbank",
    "Sachverhalt", "Zinssperre", "Beleglink",
    *(f"Beleginfo - {a} {i}" for i in range(1, 9) for a in ("Art", "Inhalt")),
    "KOST1 - Kostenstelle", "KOST2 - Kostenstelle", "Kost-Menge",
    "EU-Land u. UStID", "EU-Steuersatz", "Abw. Versteuerungsart",
    "Sachverhalt L+L", "Funktionsergänzung L+L", "BU 49 Hauptfunktionstyp",
    "BU 49 Hauptfunktionsnummer", "BU 49 Funktionsergänzung",
    *(f"Zusatzinformation - {a} {i}" for i in range(1, 21) for a in ("Art", "Inhalt")),
    "Stück", "Gewicht", "Zahlweise", "Forderungsart", "Veranlagungsjahr",
    "Zugeordnete Fälligkeit", "Skontotyp", "Auftragsnummer", "Buchungstyp",
    "USt-Schlüssel (Anzahlungen)", "EU-Land (Anzahlungen)",
    "Sachverhalt L+L (Anzahlungen)", "EU-Steuersatz (Anzahlungen)",
    "Erlöskonto (Anzahlungen)", "Herkunft-Kz", "Leerfeld", "KOST-Datum",
    "SEPA-Mandatsreferenz", "Skontosperre", "Gesellschaftername",
    "Beteiligtennummer", "Identifikationsnummer", "Zeichnernummer",
    "Postensperre bis", "Bezeichnung SoBil-Sachverhalt",
    "Kennzeichen SoBil-Buchung", "Festschreibung", "Leistungsdatum",
    "Datum Zuord. Steuerperiode", "Fälligkeit", "Generalumkehr (GU)",
    "Steuersatz", "Land",
    # Die letzten vier stehen so in der Spaltenzeile eines echten
    # Kanzlei-Exports (`historie/2026/stapel.csv` aus Ninas Belegbox,
    # 124 Spalten): babus bisherige 120 in genau dieser Reihenfolge, dann
    # diese vier. Sie bleiben leer — babu füllt sie nicht, aber eine
    # Spaltenzeile, die kürzer ist als die der Kanzlei, lässt beim Import
    # jedes Mal eine Rückfrage entstehen.
    "Abrechnungsreferenz", "BVV-Position",
    "EU-Land u. UStID (Ursprung)", "EU-Steuersatz (Ursprung)",
]


def buchungstext(review: dict) -> str:
    """Der rohe Buchungstext eines Belegs — eine Quelle für alle Wege.

    Wortgleich stand diese Bildung zweimal im Haus: hier in
    `buchungszeilen` (die Wahrheit für die Stapeldatei) und in
    `babu_web.datev_buchungssatz` (die Anzeige im Portal). Zwei Kopien
    derselben Regel driften auseinander, sobald jemand nur eine anfasst —
    und dann zeigt das Portal einen anderen Text, als in der Datei steht.

    Roh heißt: ohne Entschärfung und ohne die 60-Zeichen-Grenze. Beides
    gehört an die Stelle, die den Text in die Datei schreibt, nicht an
    seine Bildung.
    """
    v = review.get("vlm") or {}
    f = review.get("felder") or {}
    text = (v.get("buchungstext") or "").strip()
    if text:
        return text
    einordnung = ((review.get("semantik") or {}).get("belegart") or "").strip()
    lieferant = (v.get("lieferant") or f.get("lieferant") or "").strip()
    teile = _datum_teile(f.get("datum") or "")
    kurz = f"{teile[0]:02d}.{teile[1]:02d}." if teile else ""
    return " ".join(x for x in (einordnung, kurz, lieferant) if x)


def _de(betrag: float) -> str:
    """Der Betrag, wie DATEV ihn führt: immer positiv, Komma als Trenner.

    Das Vorzeichen steht in DATEV nicht am Betrag, sondern im Soll/Haben-
    Kennzeichen daneben (siehe `_soll_haben`). Ein `-119,00` in der
    Umsatzspalte ist keine Gutschrift, sondern eine Zeile, die der Import
    ablehnt.
    """
    return f"{abs(betrag):.2f}".replace(".", ",")


def _soll_haben(betrag: float) -> str:
    """`S` oder `H` — die Seite, auf der die Buchung steht.

    Eine Gutschrift (Storno, Retoure, Erstattung) trägt ihr Minus seit
    Ninas Anmerkung P1-26 schon in den Beträgen: `gemma_buchung` setzt das
    Vorzeichen einmal und alle Verbraucher rechnen ohne Sonderfall weiter.
    Für den Stapel heißt das: derselbe Betrag positiv, aber im Haben. So
    mindert die Erstattung den Aufwand, statt ihn ein zweites Mal
    aufzuschlagen — und die Vorsteuer geht denselben Weg zurück.
    """
    return "H" if round(float(betrag or 0), 2) < 0 else "S"


def _datum_teile(datum: str | None) -> tuple[int, int, int] | None:
    """(Tag, Monat, Jahr) aus einem Belegdatum — zwei Formate im Haus:
    `TT.MM.JJJJ` (Altweg, vor dem Zielbild) und `JJJJ-MM-TT` (Zielbild-Weg,
    Gemma schreibt seit 27.08.2026 ISO, siehe `_review_aus_einschaetzung`
    in babu_web.py). Tolerant gegen Leerraum um die Teile. Unlesbares
    liefert None statt eine Exception — der Beleg bleibt dann ohne
    Belegdatum im Stapel, statt den ganzen Lauf abzubrechen."""
    text = str(datum or "").strip()
    for trenner, ordnung in ((".", (0, 1, 2)), ("-", (2, 1, 0))):
        teile = [t.strip() for t in text.split(trenner)]
        if len(teile) != 3 or not all(teile):
            continue
        try:
            tag, monat, jahr = (int(teile[i]) for i in ordnung)
        except ValueError:
            continue
        return tag, monat, jahr
    return None


def _ttmm(datum: str | None) -> str | None:
    """Belegdatum fürs EXTF-Feld (`TTMM`), formatunabhängig — siehe
    `_datum_teile`. None, wenn sich das Datum nicht lesen lässt."""
    teile = _datum_teile(datum)
    return f"{teile[0]:02d}{teile[1]:02d}" if teile else None


def _feld(wert: str | None) -> str:
    if wert is None or wert == "":
        return ""
    return '"' + str(wert).replace('"', "'") + '"'


# Excel liest ein Feld, das mit einem dieser Zeichen beginnt, als FORMEL —
# auch in Anführungszeichen. Die Stapeldatei geht ans Steuerbüro und wird
# dort in Excel geöffnet; ein Lieferantenname wie `=cmd|'/c calc'!A1` wäre
# damit ein Angriff auf den Rechner der Kanzlei, nicht bloß ein hässlicher
# Buchungstext.
FORMELZEICHEN = ("=", "+", "-", "@", "\t", "\r", "\n")


def _entschaerfen(text: str) -> str:
    """Führendes Apostroph vor alles, was Excel für eine Formel hielte.

    Das Apostroph ist Excels eigene „das ist Text"-Markierung und wird beim
    Anzeigen nicht mitgedruckt. DATEV importiert das Feld als Buchungstext,
    also mit Apostroph — ein Zeichen mehr im Text ist der Preis dafür, dass
    aus dem Text kein Befehl wird.
    """
    return "'" + text if text[:1] in FORMELZEICHEN else text


def _belegfeld1(beleg_nr: str | None) -> str | None:
    """Belegfeld 1 lässt DATEV nur wenige Zeichen zu — ein Apostroph gehört
    nicht dazu. Ein führendes Rechenzeichen fällt deshalb weg, statt
    entschärft zu werden; im Inneren stört es Excel nicht."""
    if not beleg_nr:
        return None
    sauber = re.sub(r"[^A-Za-z0-9$%&*+\-/]", "", beleg_nr).lstrip("+-*/@=")
    return sauber[:36] or None


# Vorsteuer-Schlüssel je Steuersatz. Die Corona-Sätze 5 %/16 % erkennt der
# Watcher (GUELTIGE_SAETZE) — ohne eigenen Schlüssel wären sie im Stapel als
# 19 % gebucht, und der Import zöge stillschweigend zu viel Vorsteuer.
BU_SCHLUESSEL = {0: "", 5: "7", 7: "8", 16: "5", 19: "9"}

# ── Automatikkonten ──────────────────────────────────────────────────────────
#
# Im SKR04 rechnen die mit AV/AM gekennzeichneten Konten ihre Steuer selbst
# (skr04_automatik, aus dem Kontenrahmen gelesen). Ein Steuerschlüssel
# obendrauf ist ein Widerspruch, den erst der Import bei der Kanzlei
# meldet. Also: auf ein Automatikkonto kommt kein Schlüssel — und trägt die
# Zeile einen ANDEREN Satz als das Konto, gehört sie auf das Geschwister-
# konto mit diesem Satz (5300 Wareneingang 7 % neben 5400 mit 19 %,
# 4300 Erlöse 7 % neben 4400). Beide Paare stehen so im SKR04.
GESCHWISTER = {("5400", 7): "5300", ("5300", 19): "5400",
               ("4400", 7): "4300", ("4300", 19): "4400"}

# Wohin ein Automatikkonto ausweicht, wenn gar kein Satz feststeht. 5200
# „Wareneingang" ist im SKR04 dasselbe Fach ohne die AV-Kennzeichnung — es
# rechnet nichts selbst, also erfindet es auch keine Vorsteuer. Das ist der
# ehrliche Platz für eine Buchung, deren Steuersatz niemand gelesen hat:
# die Kanzlei sieht den Betrag, trägt den Satz nach und bucht um. Auf 5400
# stehengelassen hätte DATEV stillschweigend 19 % gezogen.
OHNE_STEUER = {"5400": "5200", "5300": "5200"}

# Die Erlösseite. Kasse und Geldtransit sind Finanzkonten (F) des SKR04,
# die Erlöskonten Automatikkonten — die Steuer kommt vom Konto.
KASSE = "1600"
GELDTRANSIT = "1460"
ERLOESKONTO = {19: "4400", 7: "4300"}
ERLOES_STEUERFREI = "4100"          # Steuerfreie Umsätze § 4 Nr. 8 ff. UStG
ERLOES_KLEINUNTERNEHMER = "4184"    # Steuerfreie Erlöse Kleinunternehmer § 19


def _bu(satz: int | None) -> str | None:
    """Der Steuerschlüssel zu einem Satz. `None` heißt: Zeile zurückhalten.

    Zwei Fälle, die lange derselbe waren und es nicht sind:

    * **Kein Satz angegeben** (`satz is None`) — dann steht er eben nicht
      fest. Bis 03.09.2026 machte babu daraus `"9"`, also 19 % Vorsteuer:
      eine Zahl, die niemand gelesen hat, wurde zur Steuererklärung. Jetzt
      geht die Zeile OHNE Schlüssel mit; die Kanzlei sieht den Betrag und
      trägt den Satz nach. Ein leeres Feld ist eine Frage, eine erfundene
      19 wäre eine Antwort.
    * **Ein Satz, den es nicht gibt** (12 % etwa) — die Zeile bleibt aus dem
      Stapel. Lieber eine Buchung weniger als eine falsch besteuerte.
    """
    if satz is None:
        return ""
    try:
        return BU_SCHLUESSEL.get(int(satz))
    except (TypeError, ValueError):
        return None


def _konto_und_rahmen(review: dict) -> tuple[str | None, str]:
    """Welches Konto der Beleg trägt — und aus welchem Rahmen es stammt.

    `konto`/`kontenrahmen` schreibt der Watcher seit BABU-57. Reviews von
    davor haben nur `konto_skr04`; die stammen aus einer Zeit, in der babu
    ausschließlich SKR04 kannte, also gelten sie als SKR04. Das ist keine
    Vermutung, sondern Aktenlage.
    """
    e = review.get("einschaetzung") or {}
    konto = e.get("konto") or e.get("konto_skr04")
    rahmen = e.get("kontenrahmen") or "SKR04"
    return (str(konto) if konto else None), rahmen


def buchungszeilen(review: dict, kleinunternehmerin: bool = False
                   ) -> list[dict]:
    """Ein Review → 1..n Buchungssätze (je Steuersatz einer).

    Für einen Betrieb ohne Umsatzsteuer (§ 19 UStG) wird daraus GENAU EINE
    Zeile über den Bruttobetrag, ohne Steuerschlüssel. Der Mehrsatz-Split
    beschreibt eine Aufteilung nach 19 % und 7 % — eine Steuer, die es hier
    nicht gibt. Sie trotzdem in den Stapel zu schreiben hieße, der Kanzlei
    eine Unterscheidung zu melden, die für diesen Betrieb keine ist.

    Die Erlösseite geht denselben Weg (`erloeszeilen`) — dort seit dem
    02.09.2026, hier seit dem 03.09.2026. Bis dahin war der Stapel einer
    Kleinunternehmerin auf der Ausgabenseite voller Vorsteuer-Schlüssel.
    """
    f = review.get("felder") or {}
    e = review.get("einschaetzung") or {}
    v = review.get("vlm") or {}
    konto, rahmen = _konto_und_rahmen(review)
    if not konto or f.get("brutto") is None:
        return []
    datum = f.get("datum") or ""
    teile = _datum_teile(datum)
    belegdatum = _ttmm(datum)
    text = (v.get("buchungstext") or "").strip()
    if not text:
        einordnung = ((review.get("semantik") or {}).get("belegart") or "").strip()
        lieferant = (v.get("lieferant") or f.get("lieferant") or "").strip()
        kurz = f"{teile[0]:02d}.{teile[1]:02d}." if teile else ""
        text = " ".join(x for x in (einordnung, kurz, lieferant) if x)
    basis = {"konto": konto, "gegenkonto": GEGENKONTO, "belegdatum": belegdatum,
             "belegfeld1": _belegfeld1(f.get("beleg_nr")),
             # Erst entschärfen, dann kürzen: sonst sprengte das Apostroph
             # die 60 Zeichen, die DATEV im Buchungstext annimmt.
             "text": _entschaerfen(text)[:60]}

    # Eine Gutschrift zieht ALLE ihre Zeilen mit ins Haben — auch wenn eine
    # einzelne Position der Steuertabelle für sich positiv gerechnet wäre.
    # Ein Beleg steht auf einer Seite; halb Soll und halb Haben wäre keine
    # Gutschrift, sondern eine Umbuchung, die niemand erfasst hat.
    gutschrift = round(float(f["brutto"]), 2) < 0

    def _wert(betrag) -> float:
        w = float(betrag or 0)
        return -abs(w) if gutschrift else w

    if kleinunternehmerin:
        wert = _wert(f["brutto"])
        return [_ohne_steuer(dict(basis, umsatz=_de(wert),
                                  sh=_soll_haben(wert), bu="", satz=None),
                             rahmen)]

    tabelle = f.get("steuertabelle") or []
    if len(tabelle) > 1:
        # Mehrsatz-Split: der 19%+7%-Bon wird zwei Buchungen.
        zeilen = [dict(basis, umsatz=_de(_wert(z["brutto"])),
                       sh=_soll_haben(_wert(z["brutto"])),
                       bu=_bu(int(z["satz"])), satz=int(z["satz"]))
                  for z in tabelle]
    else:
        satz = f.get("ust_satz")
        zeilen = [dict(basis, umsatz=_de(_wert(f["brutto"])),
                       sh=_soll_haben(_wert(f["brutto"])),
                       bu=_bu(satz), satz=satz)]
    zeilen = [_automatik_anpassen(z, rahmen) for z in zeilen]
    # Lieber eine Zeile weniger als eine mit dem falschen Steuerschlüssel:
    # was hier fehlt, fällt beim Abstimmen auf. Ein falscher Schlüssel nicht.
    brauchbar = [z for z in zeilen if z["bu"] is not None]
    for z in zeilen:
        if z["bu"] is None:
            print(f"[extf] Steuersatz {z['satz']} % unbekannt — Zeile "
                  f"'{z['text'][:40]}' bleibt aus dem Stapel", flush=True)
    return brauchbar


def _ohne_steuer(z: dict, rahmen: str) -> dict:
    """Eine Zeile für einen Betrieb, der keine Umsatzsteuer ausweist.

    Kein Schlüssel — und kein Konto, das sich seinen Satz selbst nimmt.
    Für 5400/5300 gibt es mit 5200 dasselbe Fach ohne Selbstrechnung
    (`OHNE_STEUER`); für jedes andere Automatikkonto liegt babu keins vor,
    dort bleibt das Konto stehen und der Prüfbefund meldet es rot. Geraten
    wird nicht: ein selbst ausgesuchtes Erlöskonto wäre eine Kontierung,
    keine Anpassung.
    """
    z = dict(z, bu="", satz=None)
    if rahmen != "SKR04" or not skr04_automatik.automatik(z["konto"]):
        return z
    ziel = OHNE_STEUER.get(z["konto"])
    if ziel:
        return dict(z, konto=ziel)
    print(f"[extf] Konto {z['konto']} rechnet seine Steuer selbst, dieser "
          f"Betrieb weist keine aus — die Zeile '{z['text'][:40]}' geht "
          f"unverändert mit, der Prüfbefund meldet sie", flush=True)
    return z


def _automatik_anpassen(z: dict, rahmen: str) -> dict:
    """Automatikkonto → kein Schlüssel; fremder Satz → Geschwisterkonto.

    Steht überhaupt kein Satz fest, weicht die Buchung auf das Konto ohne
    Selbstrechnung aus (`OHNE_STEUER`). Vorher stand hier `19 if satz is
    None` — dieselbe erfundene Zahl wie im alten `_bu`, nur an zweiter
    Stelle. Ein Automatikkonto hätte sie dann auch noch selbst gezogen.
    """
    if rahmen != "SKR04" or z["bu"] is None:
        return z
    a = skr04_automatik.automatik(z["konto"])
    if not a:
        return z
    if z.get("satz") is None:
        ziel = OHNE_STEUER.get(z["konto"])
        if ziel:
            return dict(z, konto=ziel, bu="")
        print(f"[extf] Konto {z['konto']} rechnet {a[1]} % selbst, die Zeile "
              f"'{z['text'][:40]}' nennt aber keinen Satz — sie geht ohne "
              f"Schlüssel mit, der Satz kommt vom Konto", flush=True)
        return dict(z, bu="")
    satz = int(z["satz"])
    if (a[1] or 0) == satz:
        return dict(z, bu="")
    ziel = GESCHWISTER.get((z["konto"], satz))
    if ziel:
        return dict(z, konto=ziel, bu="")
    print(f"[extf] Konto {z['konto']} rechnet {a[1]} % selbst, die Zeile "
          f"'{z['text'][:40]}' trägt {satz} % — Schlüssel bleibt, der Import "
          f"wird das melden", flush=True)
    return z


# ── Was an einem Beleg den Stapel stört ─────────────────────────────────────
#
# Eine reine Rechnung: rein ein Review, raus eine Liste von Feststellungen.
# Kein Zugriff auf die Belegbox, keine Ausgabe, keine Entscheidung — die
# trifft die Seite, die das anzeigt. Der Grund steht als kurzes Wort da
# (`grund`), damit sich Zeilen zählen und gruppieren lassen, und daneben ein
# Satz für Menschen (`text`).
#
# `hart` trennt zwei Sorten:
#
#   hart=False  Die Buchung geht mit, aber jemand sollte hinsehen.
#   hart=True   Die Buchung geht NICHT mit — oder sie wäre falsch.
#
# Das ist der Unterschied zwischen „nachtragen" und „nicht abgeben".

GRUENDE = ("steuersatz_unbekannt", "steuersatz_ungueltig", "ohne_konto",
           "ohne_betrag", "automatik_bei_kleinunternehmerin")


def _saetze_des_belegs(f: dict) -> list:
    """Die Steuersätze, die dieser Beleg in den Stapel bringen würde —
    dieselbe Aufteilung wie `buchungszeilen`, damit beide dasselbe sehen."""
    tabelle = f.get("steuertabelle") or []
    if len(tabelle) > 1:
        return [z.get("satz") for z in tabelle]
    return [f.get("ust_satz")]


def pruefen(review: dict, kleinunternehmerin: bool = False) -> list[dict]:
    """Was diesem Beleg auf dem Weg in den Stapel fehlt oder widerspricht.

    Rein rechnend und ohne Seiteneffekt, damit dieselbe Antwort in der
    Vorschau, im Prüfbefund und in einem Test herauskommt. Was hier NICHT
    passiert: der Beleg wird nicht verändert und nichts wird verworfen —
    `buchungszeilen` entscheidet weiter für sich, was es schreibt. Diese
    Funktion sagt nur, was daran auffällt.
    """
    f = review.get("felder") or {}
    konto, rahmen = _konto_und_rahmen(review)
    aus: list[dict] = []

    def melden(grund: str, text: str, hart: bool, satz=None) -> None:
        eintrag = {"grund": grund, "text": text, "hart": hart,
                   "konto": konto, "satz": satz}
        if not any(a["grund"] == grund and a["satz"] == satz for a in aus):
            aus.append(eintrag)

    if not konto:
        melden("ohne_konto",
               "Für diesen Beleg ist kein Konto festgelegt — er fehlt im "
               "Stapel.", hart=False)
    if f.get("brutto") is None:
        melden("ohne_betrag",
               "Von diesem Beleg ist kein Betrag bekannt — er fehlt im "
               "Stapel.", hart=False)

    # Ohne Umsatzsteuer spielt der Satz keine Rolle: es wird keiner in den
    # Stapel geschrieben. Ihn dann anzumahnen wäre eine Frage nach einer
    # Zahl, die niemand braucht.
    for satz in ([] if kleinunternehmerin else _saetze_des_belegs(f)):
        if satz is None:
            melden("steuersatz_unbekannt",
                   "Der Steuersatz steht nicht fest. Die Buchung geht ohne "
                   "Steuerschlüssel mit; die Kanzlei trägt ihn nach.",
                   hart=False)
        elif _bu(satz) is None:
            melden("steuersatz_ungueltig",
                   f"{satz} % ist kein Steuersatz, den DATEV kennt. Diese "
                   f"Buchung bleibt aus dem Stapel.", hart=True, satz=satz)

    # Ein Betrieb ohne Umsatzsteuer (§ 19 UStG) und ein Konto, das seine
    # Steuer selbst rechnet, schließen einander aus: DATEV zöge Vorsteuer,
    # die es nicht gibt. Die Konten, für die babu ein steuerfreies
    # Geschwisterkonto kennt, sind kein Fall — die werden umgehängt.
    if (kleinunternehmerin and konto and rahmen == "SKR04"
            and skr04_automatik.automatik(konto)
            and konto not in OHNE_STEUER):
        melden("automatik_bei_kleinunternehmerin",
               f"Konto {konto} rechnet seine Steuer selbst. In einem Betrieb "
               f"ohne Umsatzsteuer zieht das Vorsteuer, die es nicht gibt.",
               hart=True)
    return aus


def erloeszeilen(kassenblaetter: list[dict], kleinunternehmerin: bool = False
                 ) -> list[dict]:
    """Die Erlösseite: jedes Kassenblatt wird zu Tageseinnahmen.

    Bis 02.09.2026 enthielt der Stapel nur die Belege — für die Kanzlei
    die halbe Buchhaltung. Jetzt je Kassentag: Kasse an Erlöse, getrennt
    nach Steuersatz (19 % ist, was nicht 7 % oder steuerfrei war, plus
    verkaufte Gutscheine — dieselbe Rechnung wie monatsabschluss.
    erloese_monat), und der Kartenumsatz geht per Geldtransit wieder aus
    der Kasse: die Bank bekommt ihn erst mit dem Kontoauszug.

    Das Kassenblatt trennt Bar und Karte NICHT nach Steuersatz — deshalb
    läuft alles über die Kasse statt Karte direkt an Erlöse; das wäre
    eine Aufteilung, die niemand erfasst hat.

    Für die Kleinunternehmerin (§ 19 UStG) gibt es keinen Steuerausweis:
    alles auf 4184, sonst rechnete DATEV aus 4400 Umsatzsteuer heraus.
    """
    aus: list[dict] = []
    for b in sorted(kassenblaetter, key=lambda x: x.get("datum") or ""):
        datum = str(b.get("datum") or "")
        if len(datum) != 10:
            continue
        belegdatum = datum[8:10] + datum[5:7]
        bar = float(b.get("einnahmenBar") or 0)
        ec = float(b.get("ecZahlungen") or 0)
        frei = float(b.get("umsatzFrei") or 0)
        sieben = float(b.get("umsatz7") or 0)
        gutschein = float(b.get("gutscheinVerkauf") or 0)
        neunzehn = max(0.0, bar + ec - frei - sieben) + gutschein
        if kleinunternehmerin:
            frei, neunzehn, sieben = frei + neunzehn + sieben, 0.0, 0.0
        frei_konto = ERLOES_KLEINUNTERNEHMER if kleinunternehmerin else ERLOES_STEUERFREI
        # Ein Kassentag steht immer im Soll: die Beträge sind der Reihe
        # nach so aufgebaut, dass nur Positives eine Zeile ergibt (siehe
        # die `> 0`-Prüfungen unten). Einen negativen Tagesumsatz gibt es
        # nicht — eine Rückgabe mindert den Tag, sie dreht ihn nicht um.
        basis = {"belegdatum": belegdatum,
                 "belegfeld1": _belegfeld1("KB" + datum.replace("-", "")),
                 "bu": "", "satz": None, "sh": "S"}
        for betrag, konto, text in (
                (neunzehn, ERLOESKONTO[19], "Tageseinnahmen 19 %"),
                (sieben, ERLOESKONTO[7], "Tageseinnahmen 7 %"),
                (frei, frei_konto, "Tageseinnahmen steuerfrei")):
            if round(betrag, 2) > 0:
                aus.append(dict(basis, konto=KASSE, gegenkonto=konto,
                                umsatz=_de(betrag), text=text))
        if round(ec, 2) > 0:
            aus.append(dict(basis, konto=GELDTRANSIT, gegenkonto=KASSE,
                            umsatz=_de(ec), text="Kartenumsatz an Geldtransit"))
    return aus


# ── Der Mischungs-Melder ─────────────────────────────────────────────────────
#
# BABU-57. Der Buchungsstapel ist die Stelle, an der babus Konten das Haus
# verlassen. Was hier durchrutscht, fällt beim Steuerberater auf — nach dem
# Import, und dann ist es Handarbeit. Also wird hier geprüft, und zwar an der
# einzigen Stelle, an der sich alle Konten eines Monats gleichzeitig ansehen
# lassen.
#
# Drei Fälle, drei verschiedene Antworten:
#
#   1. Das Konto gehört zum eingestellten Rahmen  → in Ordnung.
#   2. Das Konto gehört nachweislich zum ANDEREN  → Vermischung, Abbruch.
#   3. babu kennt das Konto überhaupt nicht       → durchlassen, vermerken.
#
# Fall 3 ist Absicht. `kontierung.gehoert_zum_rahmen()` ist bewusst
# konservativ und kennt nur die Konten, die babu selbst vergibt. Eine
# handkorrigierte Kontierung (8400 Erlöse, ein Konto aus der Kanzlei) wäre
# damit „fremd" — sie deshalb aus dem Stapel zu werfen hieße, fremde und
# vermutlich richtige Arbeit stillschweigend wegzuwerfen. Der Melder sucht
# Vermischung, er überstimmt keine Kontierung.


class RahmenVermischung(Exception):
    """SKR03 und SKR04 in einem Stapel. Kein Import, sondern ein Fehler."""


@dataclass
class Befund:
    """Was die Rahmenprüfung über einen Stapel sagt."""
    rahmen: str
    vermischt: list[str] = field(default_factory=list)   # Konten aus dem anderen Rahmen
    unbekannt: list[str] = field(default_factory=list)   # von babu nie vergeben
    belege: list[str] = field(default_factory=list)      # wo die Vermischung steckt

    @property
    def sauber(self) -> bool:
        return not self.vermischt

    def meldung(self) -> str:
        """Ein Satz, den Nina versteht, und die Belege dazu."""
        return (f"Dieser Stapel ist auf {self.rahmen} eingestellt, enthält aber "
                f"Konten aus dem anderen Kontenrahmen: "
                f"{', '.join(self.vermischt)}. Betroffen: "
                f"{', '.join(self.belege)}. Zwei Kontenrahmen in einem Stapel "
                f"kann die Kanzlei nicht importieren.")


def _stamm(review: dict) -> str:
    datei = str(review.get("datei") or "")
    return datei.rsplit("/", 1)[-1].rsplit(".", 1)[0] or "(unbenannter Beleg)"


def rahmen_pruefen(reviews: list[dict], rahmen: str) -> Befund:
    """Stammen alle Konten dieses Stapels aus `rahmen`?"""
    anderer = next(r for r in kt.RAHMEN if r != rahmen)
    befund = Befund(rahmen=rahmen)
    for review in reviews:
        konto, beleg_rahmen = _konto_und_rahmen(review)
        if not konto:
            continue
        # Der Beleg sagt selbst, in welchem Rahmen er kontiert wurde. Das ist
        # das verlässlichere Zeugnis als die Nummer: es gilt auch für Konten,
        # die babu nicht selbst vergeben hat.
        widerspruch = beleg_rahmen != rahmen
        if kt.gehoert_zum_rahmen(konto, rahmen) and not widerspruch:
            continue
        if widerspruch or kt.gehoert_zum_rahmen(konto, anderer):
            if konto not in befund.vermischt:
                befund.vermischt.append(konto)
            befund.belege.append(_stamm(review))
        elif konto not in befund.unbekannt:
            befund.unbekannt.append(konto)
    return befund


def _zeile(b: dict) -> str:
    felder = [""] * len(SPALTEN)
    felder[0] = b["umsatz"]
    felder[1] = b.get("sh") or "S"
    felder[2] = "EUR"
    felder[6] = b["konto"]
    felder[7] = b["gegenkonto"]
    felder[8] = b["bu"]
    felder[9] = b["belegdatum"] or ""
    felder[10] = _feld(b["belegfeld1"])
    felder[13] = _feld(b["text"])
    return ";".join(felder)


def stapel(reviews: list[dict], monat: str, erzeugt: time.struct_time | None = None,
           berater: str = BERATER, mandant: str = MANDANT,
           festschreibung: bool = True, rahmen: str | None = None,
           kassenblaetter: list[dict] | None = None,
           kleinunternehmerin: bool = False) -> str:
    """Kompletter Stapel als Text (Zeilen mit CRLF verbinden macht als_bytes).

    Mit `rahmen` läuft der Mischungs-Melder mit: ein Konto aus dem anderen
    Kontenrahmen bricht den Export ab, statt ihn zu erzeugen. Ohne `rahmen`
    bleibt alles wie vorher — der Melder ist eine Zutat, kein Umbau.

    `kassenblaetter` bringt die Erlösseite mit (erloeszeilen) — nur für
    SKR04: die SKR03-Konten der Erlösseite liegen babu nicht als Quelle
    vor, und geraten wird nicht.
    """
    if rahmen:
        befund = rahmen_pruefen(reviews, rahmen)
        if not befund.sauber:
            raise RahmenVermischung(befund.meldung())
        for konto in befund.unbekannt:
            print(f"[extf] Konto {konto} hat babu nicht selbst vergeben — "
                  f"gegen {rahmen} nicht prüfbar, geht unverändert mit",
                  flush=True)
    erzeugt = erzeugt or time.localtime()
    jahr, mm = int(monat[:4]), int(monat[5:7])
    von = f"{jahr}{mm:02d}01"
    bis = f"{jahr}{mm:02d}{calendar.monthrange(jahr, mm)[1]}"
    stempel = time.strftime("%Y%m%d%H%M%S", erzeugt) + "000"
    kopf = [
        # Feld 5 ist die Formatversion. Der echte Kanzlei-Export trägt 12
        # (gemessen an `historie/2026/stapel.csv`); babu schrieb 13, was
        # die Kanzlei-Software zwar annimmt, aber als neueres Format
        # behandelt. Gleichziehen statt vorauseilen.
        '"EXTF"', "700", "21", '"Buchungsstapel"', "12", stempel, "",
        f'"{HERKUNFT}"', '"babu"', "", berater, mandant, f"{jahr}0101",
        SACHKONTENLAENGE, von, bis, f'"babu {monat}"', '""', "1", "0",
        "1" if festschreibung else "0", '"EUR"',
        "", "", "", "", "", "", "", "", "",
    ]
    zeilen = [";".join(kopf), ";".join(SPALTEN)]
    for review in reviews:
        zeilen += [_zeile(b) for b in buchungszeilen(review,
                                                     kleinunternehmerin)]
    if kassenblaetter:
        if rahmen == "SKR03":
            print(f"[extf] {len(kassenblaetter)} Kassenblätter bleiben aus dem "
                  f"SKR03-Stapel — Erlöskonten nur für SKR04 hinterlegt",
                  flush=True)
        else:
            zeilen += [_zeile(b) for b in erloeszeilen(kassenblaetter,
                                                       kleinunternehmerin)]
    return "\r\n".join(zeilen) + "\r\n"


def als_bytes(text: str, utf8_bom: bool = False) -> bytes:
    """Die Datei als Bytes — Windows-1252 wie bisher, auf Wunsch UTF-8.

    Windows-1252 bleibt der Standard: so schreibt babu seit jeher, und so
    liest es jede DATEV-Fassung. Der echte Kanzlei-Export dagegen kommt als
    UTF-8 mit vorangestelltem Erkennungszeichen — wer eine babu-Datei neben
    eine Kanzlei-Datei legt, will sie im selben Zeichensatz haben. Mit
    `utf8_bom` gibt es genau das, und nur dann.

    Der Unterschied ist nicht kosmetisch: in Windows-1252 fehlen Zeichen,
    die in Namen vorkommen (das lange Gedankenstrich-Minus, türkische und
    polnische Buchstaben) — `errors="replace"` macht daraus ein Fragezeichen.
    In UTF-8 bleibt der Name stehen, wie er ist.
    """
    if utf8_bom:
        return b"\xef\xbb\xbf" + text.encode("utf-8")
    return text.encode("cp1252", errors="replace")
