"""Die Monatsberichte als Dokumente: UStVA, BWA und Summen/Salden.

Drei Vordrucke, drei Vorlagen — alle aus dem Branchen-Kompendium belegt:

* Die UStVA folgt dem amtlichen **Vordruckmuster USt 1 A 2026** (BMF vom
  29.12.2025, III C 3 - S 7344/00039/007/036): Abschnitt A mit Kz 81/86,
  steuerfreie Umsätze ohne Vorsteuerabzug Kz 48, Abschnitt F Vorsteuer
  Kz 66, Abschnitt H Vorauszahlung/Überschuss Kz 83 („dem Betrag ein
  Minus voranstellen").
* Die BWA folgt der **DATEV-BWA Nr. 1** (kurzfristige Erfolgsrechnung)
  mit ihren Zeilennummern 1010–1380.
* Die SuSa ist die klassische DATEV-Saldenliste: Konto, Bezeichnung,
  Soll, Haben, Saldo — Konten nach **SKR04** (DATEV Art.-Nr. 11175, 2026).

Gerechnet wird hier nichts Neues: Erlöse, Vorsteuer und BWA kommen aus
`monatsabschluss`; dieses Modul prüft die Buchungen mit dem SKR04-Wissen
aus `kontierung`, baut daraus die Saldenliste und rendert die Blätter als
PDF — ein eigener Mini-Schreiber, damit kein neues Paket nötig ist
(Standardschriften Helvetica/Courier, cp1252, kein Einbetten).

Alles bleibt Entwurf: geprüft und übermittelt wird vom steuerlichen
Backend, und jedes Blatt sagt das selbst.
"""
from __future__ import annotations

import re
import time
import zlib

import kontierung as kt
import monatsabschluss as ma
from geld import rund as _rund

# ── SKR04-Wissen für die Prüfung ─────────────────────────────────────────────
#
# Kategorien, deren Zahlungen KEINE Vorsteuer tragen — kein Leistungsbezug
# (Geldbewegung, Entnahme, Steuerzahlung), egal was auf dem Beleg steht.
OHNE_VORSTEUER = {"privat", "geldtransit", "gutschein", "ust_zahlung",
                  "darlehen_personal"}

# Hoheitliche Gebühren und Pflichtbeiträge: nicht steuerbar, also nie
# Vorsteuer — auch wenn auf dem Bescheid eine Zahl steht, die nach 19 %
# aussieht (Ninas Anmerkung P1-21: 19 % auf den HWK-Beitrag gerechnet).
NICHT_STEUERBAR = {"kammerbeitrag", "grundstueck", "abgaben"}

# Feste Konten der Erlös- und Steuerseite (SKR04, DATEV-Standard 11175).
# Wie in `kontierung`: DATEV-Standard, nicht von einer Steuerberatung
# geprüft — die Blätter tragen den Hinweis.
SUSA_KONTEN = {
    "kasse": ("1600", "Kasse"),
    "bank": ("1800", "Bank"),
    "vorsteuer": ("1406", "Abziehbare Vorsteuer 19 %"),
    "erloes19": ("4400", "Erlöse 19 % USt"),
    "erloes7": ("4300", "Erlöse 7 % USt"),
    "erloesfrei": ("4100", "Steuerfreie Umsätze § 4 UStG"),
    "ust19": ("3806", "Umsatzsteuer 19 %"),
    "ust7": ("3801", "Umsatzsteuer 7 %"),
}

# Die Zeilen der DATEV-Standard-BWA (Form 01, kurzfristige Erfolgsrechnung)
# in ihrer Reihenfolge, und welche babu-Kostengruppe in welche gehört.
#
# Die Zeilenbezeichnungen stammen aus dem Starter-Kontenplan Beautysalon
# auf SKR04-Basis (Spalte `bwa_zeile`), nicht aus dem Gedächtnis. Bewusst
# ohne Zeilennummern: die Form nummeriert je nach Auswertungsvariante
# anders, und eine erfundene Nummer wäre schlimmer als keine.
BWA_ZEILEN = [
    ("Personalkosten", ("personal",)),
    ("Raumkosten", ("raum",)),
    ("Betriebliche Steuern", ("steuern_betrieb",)),
    ("Versicherungen/Beiträge", ("versicherung",)),
    ("Kfz-Kosten", ("fahrzeug",)),
    ("Werbe-/Reisekosten", ("werbung",)),
    ("Abschreibungen", ("abschreibung",)),
    ("Reparatur/Instandhaltung", ("instandhaltung",)),
    ("Sonstige Kosten", ("beratung", "buero", "sonstiges")),
]


def skr04_pruefung(belege: list[dict]) -> list[dict]:
    """Jede Buchung des Monats gegen das SKR04-Wissen halten.

    Liefert Befunde mit `folge`: `keine_vorsteuer` nimmt die USt aus der
    Voranmeldung (die Zahlung trägt keinen Vorsteuerabzug), `pruefen` ist
    ein Hinweis an die Prüfung, `info` reine Erläuterung."""
    befunde: list[dict] = []

    def b_(beleg, folge, text):
        befunde.append({"stamm": beleg.get("stamm"),
                        "lieferant": beleg.get("lieferant"),
                        "brutto": beleg.get("brutto"),
                        "kategorie": beleg.get("kategorie"),
                        "konto_skr04": beleg.get("konto_skr04"),
                        "folge": folge, "befund": text})

    for z in belege:
        kat = z.get("kategorie")
        ust = float(z.get("ust") or 0)
        brutto = z.get("brutto")
        netto = z.get("netto")
        if kat in OHNE_VORSTEUER and ust > 0:
            name = (kt.KATEGORIEN.get(kat).name if kat in kt.KATEGORIEN else kat)
            b_(z, "keine_vorsteuer",
               f"{name}: kein Leistungsbezug — die ausgewiesene Umsatzsteuer "
               "gehört nicht in die Voranmeldung.")
        elif kat in NICHT_STEUERBAR and ust > 0:
            name = (kt.KATEGORIEN.get(kat).name if kat in kt.KATEGORIEN else kat)
            b_(z, "keine_vorsteuer",
               f"{name}: hoheitliche Gebühr oder Pflichtbeitrag — nicht "
               "steuerbar, deshalb kein Vorsteuerabzug.")
        elif kat == "versicherung" and ust > 0:
            b_(z, "keine_vorsteuer",
               "Versicherungsbeiträge tragen Versicherungsteuer, keine "
               "Umsatzsteuer — kein Vorsteuerabzug (Konto 6400).")
        elif kat == "miete" and ust > 0:
            b_(z, "pruefen",
               "Miete mit Umsatzsteuer: zulässig nur, wenn der Vermieter zur "
               "Umsatzsteuer optiert hat (§ 9 UStG) — Mietvertrag prüfen.")
        elif kat == "geschenk" and ust > 0:
            b_(z, "pruefen",
               "Geschenk: Vorsteuerabzug nur, wenn höchstens 50 € netto je "
               "Person und Jahr (§ 15 Abs. 1a UStG).")
        elif kat == "bewirtung" and ust > 0:
            b_(z, "info",
               "Bewirtung: Vorsteuer voll abziehbar, als Betriebsausgabe "
               "zählen 70 % (§ 15 Abs. 1a Satz 2, § 4 Abs. 5 EStG).")
        if (isinstance(brutto, (int, float)) and isinstance(netto, (int, float))
                and abs(netto + ust - brutto) > 0.02):
            b_(z, "pruefen",
               f"Beträge gehen nicht auf: {netto:.2f} + {ust:.2f} ≠ {brutto:.2f}."
               .replace(".", ","))
    return befunde


def vorsteuer_geprueft(belege: list[dict]) -> tuple[dict, list[dict]]:
    """Vorsteuer des Monats — nach der SKR04-Prüfung.

    Buchungen ohne Vorsteuerabzug gehen mit USt 0 in die Rechnung; die
    Summenlogik selbst (Summenprobe, offene Fragen) bleibt die aus
    `monatsabschluss.vorsteuer_monat`."""
    befunde = skr04_pruefung(belege)
    gesperrt = {b["stamm"] for b in befunde if b["folge"] == "keine_vorsteuer"}
    bereinigt = [dict(z, ust=0.0, netto=z.get("brutto"))
                 if z.get("stamm") in gesperrt else z for z in belege]
    return ma.vorsteuer_monat(bereinigt), befunde


def erloese_summe(monate: list[dict]) -> dict:
    """Erlöse mehrerer Monate zum Jahresauflauf addiert.

    Alle Beträge und die Tage sind additiv; `offen` nicht — jeder
    Monatslauf zählt dort ALLE offenen Rechnungen, deshalb gilt der
    letzte Stand."""
    if not monate:
        return ma.erloese_monat([])
    summe = dict(monate[0])
    for e in monate[1:]:
        for k, v in e.items():
            if k != "offen" and isinstance(v, (int, float)):
                summe[k] = summe.get(k, 0) + v
    summe["offen"] = monate[-1].get("offen", 0.0)
    return {k: (_rund(v) if isinstance(v, float) else v)
            for k, v in summe.items()}


def bwa_summe(monats_bwas: list[dict], zeitraum: str) -> dict:
    """Der Jahresauflauf als Summe der Monats-BWAs — wie die kumulierte
    Spalte der DATEV-BWA: jeder Monat mit seinen eigenen Verträgen und
    Personalkosten, dann addiert."""
    gruppen: dict[str, dict] = {}
    umsatz = kosten = tage = neutral_summe = 0.0
    neutral: list[dict] = []
    fehlt: list[str] = []
    for b in monats_bwas:
        umsatz += b["umsatz_netto"]
        kosten += b["kosten_netto"]
        tage += b.get("tage_erfasst") or 0
        neutral += b.get("neutral") or []
        neutral_summe += b.get("neutral_summe") or 0
        for g in b["gruppen"]:
            e = gruppen.setdefault(g["schluessel"],
                                   {"schluessel": g["schluessel"],
                                    "name": g["name"], "netto": 0.0,
                                    "anzahl": 0})
            e["netto"] += g["netto"]
            e["anzahl"] += g["anzahl"]
        for f in b.get("fehlt") or []:
            if f not in fehlt:
                fehlt.append(f)
    ohne_kasse = sum(1 for b in monats_bwas
                     if not b.get("tage_erfasst") and b["kosten_netto"] > 0)
    if ohne_kasse:
        fehlt.insert(0, f"Für {ohne_kasse} "
                     + ("Monat" if ohne_kasse == 1 else "Monate")
                     + " mit Belegen fehlen die Tageseinnahmen im Kassenbuch "
                     "— der Umsatz hier ist entsprechend zu niedrig.")
    umsatz = _rund(umsatz)
    geordnet = []
    for schluessel, _, _ in ma.KOSTENGRUPPEN:
        if schluessel in gruppen:
            g = gruppen[schluessel]
            g["netto"] = _rund(g["netto"])
            g["anteil"] = _rund(100 * g["netto"] / umsatz) if umsatz else None
            geordnet.append(g)
    ergebnis = _rund(umsatz - kosten)
    return {"monat": zeitraum, "stand": "entwurf",
            "umsatz_netto": umsatz, "kosten_netto": _rund(kosten),
            "ergebnis": ergebnis,
            "ergebnis_anteil": _rund(100 * ergebnis / umsatz) if umsatz else None,
            "gruppen": geordnet, "tage_erfasst": int(tage), "fehlt": fehlt,
            "neutral": neutral, "neutral_summe": _rund(neutral_summe),
            "hinweis": "Jahresauflauf — Summe der Monatsauswertungen, "
                       "vorläufig und nicht von der Buchhaltung geprüft."}


def susa(monat: str, erloese: dict, belege: list[dict]) -> dict:
    """Summen- und Saldenliste des Monats aus Kasse, Erlösen und Belegen.

    Der Zahlweg der Belege ist nicht erfasst — das Gegenkonto der Ausgaben
    ist pauschal die Bank; das Blatt sagt es dazu."""
    vorsteuer, befunde = vorsteuer_geprueft(belege)
    gesperrt = {b["stamm"] for b in befunde if b["folge"] == "keine_vorsteuer"}
    konten: dict[str, dict] = {}

    def buchen(nr: str, name: str, soll=0.0, haben=0.0):
        k = konten.setdefault(nr, {"konto": nr, "name": name,
                                   "soll": 0.0, "haben": 0.0})
        k["soll"] += soll
        k["haben"] += haben

    # Erlösseite: Kasse/Bank im Soll, Erlöse netto und USt im Haben.
    nr, name = SUSA_KONTEN["kasse"]
    buchen(nr, name, soll=erloese["bar"])
    nr, name = SUSA_KONTEN["bank"]
    buchen(nr, name, soll=erloese["karte"] + erloese["aus_rechnungen"])
    n19 = _rund(erloese["brutto_19"] / 1.19)
    n7 = _rund(erloese["brutto_7"] / 1.07)
    if n19:
        buchen(*SUSA_KONTEN["erloes19"], haben=n19)
        buchen(*SUSA_KONTEN["ust19"], haben=_rund(erloese["brutto_19"] - n19))
    if n7:
        buchen(*SUSA_KONTEN["erloes7"], haben=n7)
        buchen(*SUSA_KONTEN["ust7"], haben=_rund(erloese["brutto_7"] - n7))
    if erloese["steuerfrei"]:
        buchen(*SUSA_KONTEN["erloesfrei"], haben=erloese["steuerfrei"])

    # Ausgabenseite: Aufwandskonto netto und Vorsteuer im Soll, Bank im Haben.
    namen = {k.skr04: k.name for k in kt.KATEGORIEN.values() if k.skr04}
    for z in belege:
        brutto = z.get("brutto")
        if not isinstance(brutto, (int, float)):
            continue
        ust = 0.0 if z.get("stamm") in gesperrt else float(z.get("ust") or 0)
        netto = _rund(brutto - ust)
        konto = z.get("konto_skr04") or "6850"
        buchen(konto, namen.get(konto, "—"), soll=netto)
        if ust:
            buchen(*SUSA_KONTEN["vorsteuer"], soll=ust)
        nr, name = SUSA_KONTEN["bank"]
        buchen(nr, name, haben=brutto)

    zeilen = []
    for k in sorted(konten.values(), key=lambda x: x["konto"]):
        k["soll"] = _rund(k["soll"])
        k["haben"] = _rund(k["haben"])
        k["saldo"] = _rund(k["soll"] - k["haben"])
        if k["soll"] or k["haben"]:
            zeilen.append(k)
    return {"monat": monat, "zeilen": zeilen,
            "summe_soll": _rund(sum(k["soll"] for k in zeilen)),
            "summe_haben": _rund(sum(k["haben"] for k in zeilen)),
            "befunde": befunde,
            "hinweise": ["Zahlweg der Belege nicht erfasst — Gegenkonto der "
                         "Ausgaben pauschal 1800 Bank.",
                         "Konten nach DATEV-SKR04 (Art.-Nr. 11175, 2026); "
                         "Entwurf, nicht steuerlich geprüft."]}


# ── Der PDF-Schreiber ────────────────────────────────────────────────────────

_BREITE, _HOEHE = 595, 842          # A4 in pt
_RAND = 52


def _esc(t: str) -> bytes:
    roh = t.encode("cp1252", "replace")
    return roh.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class _Blatt:
    """Ein mehrseitiges A4-Blatt: y-Cursor, Zeilen, Linien, Umbruch.

    Beträge stehen in Courier (feste Zeichenbreite 0,6 × Größe) — nur so
    ist rechtsbündig ohne eingebettete Font-Metriken exakt."""

    def __init__(self):
        self.seiten: list[list[bytes]] = []
        self._neue_seite()

    def _neue_seite(self):
        self.ops: list[bytes] = []
        self.seiten.append(self.ops)
        self.y = _HOEHE - _RAND

    def _text(self, x: float, y: float, t: str, font: str, size: float):
        self.ops.append(b"BT /%s %.1f Tf %.1f %.1f Td (%s) Tj ET"
                        % (font.encode(), size, x, y, _esc(t)))

    def _rechts(self, x_rechts: float, y: float, t: str, font: str, size: float):
        breite = 0.6 * size * len(t)
        self._text(x_rechts - breite, y, t, font, size)

    def zeile(self, links: str = "", rechts: str | None = None, *,
              fett: bool = False, size: float = 9.5, einzug: float = 0,
              abstand: float | None = None, rechts_x: float = _BREITE - _RAND,
              mitte: str | None = None, mitte_x: float = 0):
        h = abstand if abstand is not None else size + 4.5
        if self.y - h < _RAND:
            self._neue_seite()
        self.y -= h
        if links:
            self._text(_RAND + einzug, self.y, links,
                       "F2" if fett else "F1", size)
        if mitte is not None:
            self._rechts(mitte_x, self.y, mitte, "F4" if fett else "F3", size)
        if rechts is not None:
            self._rechts(rechts_x, self.y, rechts, "F4" if fett else "F3", size)

    def linie(self, stark: bool = False):
        self.y -= 4
        self.ops.append(b"%.1f w %.1f %.1f m %.1f %.1f l S"
                        % (0.9 if stark else 0.4, _RAND, self.y,
                           _BREITE - _RAND, self.y))
        self.y -= 3

    def frei(self, h: float = 8):
        self.y -= h

    def bytes(self) -> bytes:
        objs: list[bytes] = []

        def obj(inhalt: bytes) -> int:
            objs.append(inhalt)
            return len(objs)

        fonts = b"".join(b"/F%d %d 0 R " % (i + 1, 900 + i) for i in range(4))
        seiten_ids = []
        for ops in self.seiten:
            strom = zlib.compress(b"\n".join(ops))
            sid = obj(b"<</Length %d /Filter /FlateDecode>>\nstream\n%s\nendstream"
                      % (len(strom), strom))
            seiten_ids.append(sid)
        # Feste Objektnummern für Fonts/Pages/Katalog hinter den Seiten.
        basis = len(objs)
        namen = [b"Helvetica", b"Helvetica-Bold", b"Courier", b"Courier-Bold"]
        font_ids = [obj(b"<</Type /Font /Subtype /Type1 /BaseFont /%s "
                        b"/Encoding /WinAnsiEncoding>>" % n) for n in namen]
        fonts = b"".join(b"/F%d %d 0 R " % (i + 1, fid)
                         for i, fid in enumerate(font_ids))
        pages_id = basis + len(namen) + len(self.seiten) + 1
        page_ids = []
        for sid in seiten_ids:
            page_ids.append(obj(
                b"<</Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] "
                b"/Resources <</Font <<%s>>>> /Contents %d 0 R>>"
                % (pages_id, _BREITE, _HOEHE, fonts, sid)))
        kids = b" ".join(b"%d 0 R" % p for p in page_ids)
        wirklich_pages = obj(b"<</Type /Pages /Kids [%s] /Count %d>>"
                             % (kids, len(page_ids)))
        assert wirklich_pages == pages_id
        katalog = obj(b"<</Type /Catalog /Pages %d 0 R>>" % pages_id)

        out = bytearray(b"%PDF-1.4\n")
        stellen = [0]
        for i, o in enumerate(objs, 1):
            stellen.append(len(out))
            out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
        for s in stellen[1:]:
            out += b"%010d 00000 n \n" % s
        out += (b"trailer<</Size %d /Root %d 0 R>>\nstartxref\n%d\n%%%%EOF\n"
                % (len(objs) + 1, katalog, xref))
        return bytes(out)


def _beleg_name(eintrag: dict) -> str:
    """Wie ein Beleg auf dem Blatt heißt — Lieferant, notfalls lesbar aus
    dem Dateistamm (nie der rohe Hex-Stamm; das Blatt liest ein Mensch)."""
    if eintrag.get("lieferant"):
        return str(eintrag["lieferant"])
    kurz = re.sub(r"^\d{8}-\d{6}-[0-9a-f]+-", "", str(eintrag.get("stamm") or ""))
    kurz = re.sub(r"_[0-9a-f]{6,}$", "", kurz)
    teile = kurz.split("_")
    if len(teile) >= 3:
        return f"{teile[2].capitalize()} · {teile[1]}"
    return kurz.replace("_", " ") or "Beleg"


def _eur(wert: float | None) -> str:
    if wert is None:
        return ""
    return f"{wert:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _kopf(b: _Blatt, titel: str, monat: str, betrieb: dict):
    b.zeile(betrieb.get("betrieb_name") or "Salon", size=9)
    stn = betrieb.get("steuernummer")
    fa = betrieb.get("finanzamt")
    if stn or fa:
        b.zeile(" · ".join(t for t in (f"Steuernummer {stn}" if stn else "",
                                       fa or "") if t), size=8)
    b.frei(6)
    b.zeile(titel, fett=True, size=15, abstand=22)
    b.zeile(f"Zeitraum {monat} · erstellt am " + time.strftime("%d.%m.%Y")
            + " · ENTWURF aus babu", size=8.5)
    b.linie(stark=True)
    b.frei(4)


def _fuss(b: _Blatt, hinweise: list[str]):
    b.frei(10)
    b.linie()
    for h in hinweise:
        b.zeile(h, size=7.5, abstand=10)


def ustva_pdf(entwurf: dict, betrieb: dict, befunde: list[dict]) -> bytes:
    """Das Blatt zur Voranmeldung — nach Vordruckmuster USt 1 A 2026."""
    b = _Blatt()
    _kopf(b, "Umsatzsteuer-Voranmeldung", entwurf["monat"], betrieb)
    b.zeile("nach amtlichem Vordruckmuster USt 1 A 2026 "
            "(BMF-Schreiben vom 29.12.2025)", size=8)
    b.frei(8)
    b.zeile("", mitte="Bemessungsgrundlage", mitte_x=_BREITE - 170, size=8)
    b.zeile("Kz", mitte="ohne Umsatzsteuer EUR", mitte_x=_BREITE - 170,
            rechts="Steuer EUR", size=8)
    b.linie()

    b.zeile("A. Steuerpflichtige Lieferungen, sonstige Leistungen "
            "und unentgeltliche Wertabgaben", fett=True, size=9.5)
    kz_texte = {
        "81": "Steuerpflichtige Umsätze zum Steuersatz von 19 %",
        "86": "Steuerpflichtige Umsätze zum Steuersatz von 7 %",
        "48": "Steuerfreie Umsätze ohne Vorsteuerabzug (z. B. § 4 Nr. 14 UStG)",
    }
    for z in entwurf["zeilen"]:
        if z["kz"] not in kz_texte:
            continue
        b.zeile(f"{z['kz']}  {kz_texte[z['kz']]}", einzug=8,
                mitte=_eur(z["netto"]), mitte_x=_BREITE - 170,
                rechts=_eur(z["steuer"]) if z["kz"] != "48" else "")
    b.zeile("Umsatzsteuer", einzug=8, rechts=_eur(entwurf["umsatzsteuer"]))
    b.frei(6)

    b.zeile("F. Abziehbare Vorsteuerbeträge", fett=True, size=9.5)
    b.zeile("66  Vorsteuerbeträge aus Rechnungen von anderen Unternehmern "
            "(§ 15 Abs. 1 S. 1 Nr. 1 UStG)", einzug=8,
            rechts=_eur(entwurf["vorsteuer"]))
    b.frei(6)

    b.zeile("H. Vorauszahlung/Überschuss", fett=True, size=9.5)
    zahllast = entwurf["zahllast"]
    b.zeile("83  Verbleibende Umsatzsteuer-Vorauszahlung / verbleibender "
            "Überschuss (Minus voranstellen)", einzug=8, fett=True,
            rechts=_eur(zahllast))
    b.zeile(entwurf.get("satz") or "", einzug=8, size=8.5)

    relevant = [x for x in befunde if x["folge"] != "info"]
    if relevant or entwurf.get("pruefliste"):
        b.frei(10)
        b.zeile("Prüfliste (SKR04-Prüfung der Buchungen)", fett=True, size=9.5)
        for f in relevant:
            b.zeile(f"· {_beleg_name(f)}: {f['befund']}", size=8, einzug=8,
                    abstand=11)
        for p in entwurf.get("pruefliste") or []:
            b.zeile(f"· {_beleg_name(p)}: {p['hinweis']} — nicht in Kz 66 "
                    "enthalten.", size=8, einzug=8, abstand=11)

    _fuss(b, ["Entwurf aus deinen Zahlen — geprüft und ans Finanzamt "
              "übermittelt wird über ELSTER durch das steuerliche Backend "
              "(§ 18 Abs. 1 UStG).",
              "Grundlage: Kassenbuch, gestellte Rechnungen und die Belege "
              "des Monats; Kennziffern nach Vordruckmuster USt 1 A 2026."])
    return b.bytes()


def bwa_pdf(bwa: dict, betrieb: dict) -> bytes:
    """Kurzfristige Erfolgsrechnung im Schema der DATEV-Standard-BWA."""
    b = _Blatt()
    _kopf(b, "Betriebswirtschaftliche Auswertung", bwa["monat"], betrieb)
    b.zeile("Kurzfristige Erfolgsrechnung im Schema der "
            "DATEV-Standard-BWA (Form 01)", size=8)
    b.frei(8)
    umsatz = bwa["umsatz_netto"]

    def prozent(wert):
        return (f"{100 * wert / umsatz:5.1f} %".replace(".", ",")
                if umsatz else "")

    b.zeile("Position", mitte="EUR", mitte_x=_BREITE - 130,
            rechts="% Umsatz", size=8)
    b.linie()
    gruppen = {g["schluessel"]: g for g in bwa["gruppen"]}

    def z(name, wert, fett=False):
        b.zeile(name, fett=fett, mitte=_eur(wert),
                mitte_x=_BREITE - 130, rechts=prozent(wert))

    z("Umsatzerlöse", umsatz)
    z("Gesamtleistung", umsatz, fett=True)
    material = _rund(gruppen["material"]["netto"] if "material" in gruppen else 0)
    z("Mat./Wareneinkauf", material)
    rohertrag = _rund(umsatz - material)
    z("Rohertrag", rohertrag, fett=True)
    b.frei(4)
    kosten = 0.0
    for name, schluessel in BWA_ZEILEN:
        wert = _rund(sum(gruppen[s]["netto"] for s in schluessel
                         if s in gruppen))
        kosten += wert
        if wert:
            z(name, wert)
    z("Gesamtkosten", _rund(kosten), fett=True)
    b.linie()
    z("Betriebsergebnis", _rund(rohertrag - kosten), fett=True)
    z("Vorläufiges Ergebnis", bwa["ergebnis"], fett=True)

    if bwa.get("neutral"):
        # Kein Aufwand, aber Geld, das den Betrieb verlassen hat: das darf
        # weder im Ergebnis stehen noch verschwinden.
        b.frei(8)
        b.zeile("Nicht im Ergebnis (kein Aufwand): Privatentnahmen, "
                "Geldtransit, Umsatzsteuer, Anlagenkäufe", size=8)
        b.zeile("zusammen", einzug=8, size=8,
                mitte=_eur(bwa.get("neutral_summe")), mitte_x=_BREITE - 130)

    if bwa.get("fehlt"):
        b.frei(10)
        b.zeile("Was hier noch fehlt", fett=True, size=9.5)
        for f in bwa["fehlt"]:
            b.zeile("· " + f, size=8, einzug=8, abstand=11)
    _fuss(b, [bwa.get("hinweis") or "",
              "Zeilenschema der DATEV-Standard-BWA (Form 01); Kostengruppen "
              "aus den SKR04-Konten der Buchungen."])
    return b.bytes()


def susa_pdf(s: dict, betrieb: dict) -> bytes:
    """Summen- und Saldenliste — Konto · Bezeichnung · Soll · Haben · Saldo."""
    b = _Blatt()
    _kopf(b, "Summen- und Saldenliste", s["monat"], betrieb)
    b.zeile("Konten nach DATEV-SKR04 (Art.-Nr. 11175, 2026)", size=8)
    b.frei(8)
    b.zeile("Konto  Bezeichnung", mitte="Soll EUR", mitte_x=_BREITE - 200,
            rechts="Haben EUR", rechts_x=_BREITE - 110, size=8)
    b.zeile("", rechts="Saldo EUR", size=8, abstand=10)
    b.linie()
    for k in s["zeilen"]:
        b.zeile(f"{k['konto']}   {k['name']}",
                mitte=_eur(k["soll"]) if k["soll"] else "",
                mitte_x=_BREITE - 200)
        b.zeile("", mitte=_eur(k["haben"]) if k["haben"] else "",
                mitte_x=_BREITE - 110,
                rechts=("S " if k["saldo"] >= 0 else "H ")
                + _eur(abs(k["saldo"])), abstand=1)
    b.linie(stark=True)
    b.zeile("Summen", fett=True, mitte=_eur(s["summe_soll"]),
            mitte_x=_BREITE - 200, rechts=_eur(s["summe_haben"]),
            rechts_x=_BREITE - 110)
    _fuss(b, s["hinweise"])
    return b.bytes()
