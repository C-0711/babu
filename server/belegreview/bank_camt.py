"""Kontoumsätze aus Dateien der Bank lesen — CAMT.053 und CSV (seit 04.10.2026).

Plan Kanzleiansicht, B2. Jede Bank bietet ihre Umsätze als Datei an: den
Standard CAMT.053 (XML, oft als ZIP mit einer Datei je Tag) oder eine CSV,
deren Spalten jede Bank anders nennt. Gelesen wird beides in das Modell aus
`bank_anbindung`; geschrieben wird hier nichts.

Sicherheit: XML mit DOCTYPE oder ENTITY wird abgelehnt (keine externen
Entitäten, keine Entitäten-Bomben), ZIPs haben Grenzen für Anzahl, Größe
und Pfade.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

import bank_anbindung as ba

ZIP_DATEIEN_MAX = 400
ZIP_GROESSE_MAX = 50 * 1024 * 1024


class ImportFehler(Exception):
    """Ein Satz für die Seite — und, bei einer CSV, die Spalten der Datei."""

    def __init__(self, text: str, spalten: list[str] | None = None):
        super().__init__(text)
        self.spalten = spalten


# ---------------------------------------------------------------------------
# Einstieg
# ---------------------------------------------------------------------------

def lesen(roh: bytes, name: str = "", iban: str | None = None,
          spalten: dict | None = None) -> dict:
    """Eine Datei der Bank → {art, konten, umsaetze, hinweise}.

    `iban` braucht nur eine CSV, die ihr Konto nicht selbst nennt;
    `spalten` ist die Zuordnung von Hand, wenn die Spalten nicht erkannt
    werden ({"buchung": "Datum", "betrag": "Umsatz", …}).
    """
    if not roh or not roh.strip():
        raise ImportFehler("Die Datei ist leer.")
    if roh[:4] == b"PK\x03\x04":
        return _zip(roh)
    kopf = roh[:2000].lstrip(b"\xef\xbb\xbf").lstrip()
    if kopf.startswith(b"<"):
        return _camt([roh])
    return _csv(roh, iban, spalten)


def _zip(roh: bytes) -> dict:
    try:
        z = zipfile.ZipFile(io.BytesIO(roh))
    except zipfile.BadZipFile as f:
        raise ImportFehler("Das ZIP lässt sich nicht öffnen.") from f
    namen = [i for i in z.infolist() if not i.is_dir()]
    if len(namen) > ZIP_DATEIEN_MAX:
        raise ImportFehler(f"Das ZIP enthält mehr als {ZIP_DATEIEN_MAX} Dateien.")
    if sum(i.file_size for i in namen) > ZIP_GROESSE_MAX:
        raise ImportFehler("Das ZIP ist entpackt zu groß.")
    teile = []
    for i in namen:
        if ".." in i.filename or i.filename.startswith("/"):
            raise ImportFehler("Das ZIP enthält einen ungültigen Pfad.")
        if i.filename.lower().endswith(".xml"):
            teile.append(z.read(i))
    if not teile:
        raise ImportFehler("Im ZIP liegt keine CAMT-Datei (.xml).")
    return _camt(teile)


# ---------------------------------------------------------------------------
# CAMT.053
# ---------------------------------------------------------------------------

def _t(knoten, pfad: str) -> str:
    """Text des ersten Treffers, Namensraum egal (`{*}`)."""
    if knoten is None:
        return ""
    x = knoten.find("/".join(f"{{*}}{p}" for p in pfad.split("/")))
    return (x.text or "").strip() if x is not None and x.text else ""


def _alle(knoten, pfad: str) -> list:
    return knoten.findall("/".join(f"{{*}}{p}" for p in pfad.split("/"))) if knoten is not None else []


def _datum(knoten, pfad: str) -> str:
    return (_t(knoten, f"{pfad}/Dt") or _t(knoten, f"{pfad}/DtTm"))[:10]


def _camt(teile: list[bytes]) -> dict:
    umsaetze: list[dict] = []
    konten: dict[str, dict] = {}
    for roh in teile:
        if re.search(rb"<!\s*(DOCTYPE|ENTITY)", roh[:10000], re.I):
            raise ImportFehler("Die Datei enthält eine DOCTYPE-Angabe — so eine "
                               "CAMT-Datei nimmt babu nicht an.")
        try:
            wurzel = ET.fromstring(roh)
        except ET.ParseError as f:
            raise ImportFehler("Die XML-Datei lässt sich nicht lesen.") from f
        auszuege = _alle(wurzel, "BkToCstmrStmt/Stmt")
        if not auszuege:
            raise ImportFehler("Das ist keine CAMT.053-Datei (Kontoauszug) — "
                               "es fehlt der Auszug darin.")
        for stmt in auszuege:
            iban = ba.iban_normal(_t(stmt, "Acct/Id/IBAN"))
            if not iban:
                raise ImportFehler("Im Auszug fehlt die IBAN des Kontos.")
            kid = ba.konto_id(iban)
            k = konten.setdefault(iban, {"iban": iban, "von": None, "bis": None,
                                         "saldo": None})
            for bal in _alle(stmt, "Bal"):
                art = _t(bal, "Tp/CdOrPrtry/Cd")
                if art in ("CLBD", "CLAV") or not k["saldo"]:
                    betrag = float(_t(bal, "Amt") or 0)
                    if _t(bal, "CdtDbtInd") == "DBIT":
                        betrag = -betrag
                    datum = _datum(bal, "Dt")
                    if art == "CLBD" and datum and (
                            not k["saldo"] or datum >= k["saldo"]["datum"]):
                        k["saldo"] = {"betrag": round(betrag, 2), "datum": datum}
            for ntry in _alle(stmt, "Ntry"):
                status = _t(ntry, "Sts/Cd") or _t(ntry, "Sts")
                if status and status != "BOOK":
                    continue            # vorgemerkt, noch nicht gebucht
                umsaetze.extend(_eintrag(ntry, iban, kid))
            for u in umsaetze:
                if u["iban"] != iban:
                    continue
                k["von"] = min(filter(None, [k["von"], u["buchung"]]))
                k["bis"] = max(filter(None, [k["bis"], u["buchung"]]))
    if not umsaetze:
        raise ImportFehler("In der Datei steht kein gebuchter Umsatz.")
    return {"art": "camt", "konten": list(konten.values()),
            "umsaetze": ba.kennungen_vergeben(umsaetze), "hinweise": []}


def _eintrag(ntry, iban: str, kid: str) -> list[dict]:
    soll = _t(ntry, "CdtDbtInd") == "DBIT"
    buchung = _datum(ntry, "BookgDt")
    valuta = _datum(ntry, "ValDt") or None
    art = _t(ntry, "AddtlNtryInf") or _t(ntry, "BkTxCd/Prtry/Cd") or None
    familie = _t(ntry, "BkTxCd/Domn/Fmly/SubFmlyCd")
    prtry = _t(ntry, "BkTxCd/Prtry/Cd")
    entgelt = familie in ("CHRG", "COMM") or bool(re.search(r"\+80[58]\b", prtry))
    details = _alle(ntry, "NtryDtls/TxDtls")
    gesamt = float(_t(ntry, "Amt") or 0)
    stuecke = []
    for tx in details or [None]:
        betrag = gesamt
        if len(details) > 1:
            einzel = _t(tx, "AmtDtls/TxAmt/Amt") or _t(tx, "Amt")
            betrag = float(einzel) if einzel else gesamt / len(details)
        partei = "Cdtr" if soll else "Dbtr"
        name = (_t(tx, f"RltdPties/{partei}/Nm") or _t(tx, f"RltdPties/{partei}/Pty/Nm"))
        gegen_iban = ba.iban_normal(_t(tx, f"RltdPties/{partei}Acct/Id/IBAN")) or None
        zweck = " ".join(x.text.strip() for x in _alle(tx, "RmtInf/Ustrd") if x.text)
        zweck = zweck or _t(tx, "AddtlTxInf")
        referenz = (_t(tx, "Refs/AcctSvcrRef") or _t(ntry, "AcctSvcrRef")
                    if len(details) <= 1 else _t(tx, "Refs/AcctSvcrRef"))
        stuecke.append({
            "konto": kid, "iban": iban, "buchung": buchung, "valuta": valuta,
            "betrag": round(-abs(betrag) if soll else abs(betrag), 2),
            "waehrung": (ntry.find("{*}Amt").get("Ccy") if ntry.find("{*}Amt") is not None
                         else "EUR") or "EUR",
            "gegenpartei": name[:140], "gegen_iban": gegen_iban,
            "zweck": zweck[:300], "art": "Entgelt" if entgelt else art,
            "saldo": None, "referenz": referenz or None, "quelle": "camt"})
    return [s for s in stuecke if s["buchung"]]


# ---------------------------------------------------------------------------
# CSV — Spalten über ihren Namen
# ---------------------------------------------------------------------------

#: Spaltennamen der Banken, kleingeschrieben und ohne Umlaute verglichen.
SPALTEN = {
    "buchung": ("buchungstag", "buchungsdatum", "buchung", "datum", "date",
                "booking date", "wertstellungsdatum"),
    "valuta": ("valutadatum", "valuta", "wertstellung", "value date"),
    "betrag": ("betrag", "umsatz", "betrag (eur)", "betrag in eur", "amount",
               "amount (eur)", "betrag eur"),
    "soll": ("soll", "belastung", "ausgang", "debit"),
    "haben": ("haben", "gutschrift", "eingang", "credit"),
    "sh": ("soll/haben", "s/h", "soll-haben-kennzeichen"),
    "gegenpartei": ("beguenstigter/zahlungspflichtiger", "name zahlungsbeteiligter",
                    "auftraggeber/empfaenger", "auftraggeber / beguenstigter",
                    "empfaenger", "zahlungsempfaenger", "payee", "name",
                    "beguenstigter", "auftraggeber"),
    "gegen_iban": ("kontonummer/iban", "iban zahlungsbeteiligter", "iban",
                   "account number", "iban auftraggeber/empfaenger"),
    "zweck": ("verwendungszweck", "payment reference", "buchungsdetails", "zweck",
              "vorgang/verwendungszweck"),
    "art": ("buchungstext", "transaction type", "umsatzart", "buchungsart"),
    "konto": ("auftragskonto", "iban auftragskonto"),
    "saldo": ("saldo nach buchung", "saldo"),
    "waehrung": ("waehrung", "currency"),
}
PFLICHT = ("buchung",)


def _ohne_umlaute(s: str) -> str:
    return (s.lower().strip().strip('"').replace("ä", "ae").replace("ö", "oe")
            .replace("ü", "ue").replace("ß", "ss"))


def _zahl(s: str) -> float | None:
    w = str(s or "").strip().replace("€", "").replace("EUR", "").replace(" ", "")
    if not w:
        return None
    minus = w.endswith("-") or w.startswith("-")
    w = w.strip("-+")
    if "," in w:
        w = w.replace(".", "").replace(",", ".")
    try:
        z = float(w)
    except ValueError:
        return None
    return -z if minus else z


def _iso_datum(s: str) -> str | None:
    w = str(s or "").strip().strip('"')
    for muster in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(w[:10], muster).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _entziffern(roh: bytes) -> str:
    if roh.startswith(b"\xef\xbb\xbf"):
        return roh.decode("utf-8-sig")
    for kodierung in ("utf-8", "cp1252"):
        try:
            return roh.decode(kodierung)
        except UnicodeDecodeError:
            continue
    raise ImportFehler("Der Zeichensatz der Datei lässt sich nicht lesen.")


def _zuordnen(kopf: list[str], spalten: dict | None) -> dict[str, int]:
    namen = [_ohne_umlaute(n) for n in kopf]
    if spalten:
        aus = {}
        for schluessel, spalte in spalten.items():
            if schluessel in SPALTEN and _ohne_umlaute(str(spalte)) in namen:
                aus[schluessel] = namen.index(_ohne_umlaute(str(spalte)))
        return aus
    aus = {}
    for schluessel, kandidaten in SPALTEN.items():
        for k in kandidaten:
            if k in namen and namen.index(k) not in aus.values():
                aus[schluessel] = namen.index(k)
                break
    return aus


def _csv(roh: bytes, iban: str | None, spalten: dict | None) -> dict:
    zeilen = [z for z in _entziffern(roh).splitlines() if z.strip()]
    kopf_nr, trenner, zuordnung, kopf = None, ";", {}, []
    for nr, zeile in enumerate(zeilen[:30]):
        t = max((";", ",", "\t"), key=zeile.count)
        felder = next(csv.reader([zeile], delimiter=t, quotechar='"'))
        z = _zuordnen(felder, spalten)
        if "buchung" in z and ("betrag" in z or ("soll" in z and "haben" in z)):
            kopf_nr, trenner, zuordnung, kopf = nr, t, z, felder
            break
    if kopf_nr is None:
        erste = zeilen[0] if zeilen else ""
        t = max((";", ",", "\t"), key=erste.count)
        alle = next(csv.reader([erste], delimiter=t, quotechar='"')) if erste else []
        raise ImportFehler("Die Spalten dieser Datei kennt babu noch nicht — "
                           "bitte einmal zuordnen, welche Spalte was ist.",
                           spalten=[s.strip().strip('"') for s in alle])
    umsaetze: list[dict] = []
    konto_ibans: set[str] = set()
    for zeile in zeilen[kopf_nr + 1:]:
        f = next(csv.reader([zeile], delimiter=trenner, quotechar='"'))

        def hol(s: str) -> str:
            i = zuordnung.get(s)
            return f[i].strip() if i is not None and i < len(f) else ""

        buchung = _iso_datum(hol("buchung"))
        if not buchung:
            continue
        if "betrag" in zuordnung:
            betrag = _zahl(hol("betrag"))
        else:
            soll_, haben_ = _zahl(hol("soll")), _zahl(hol("haben"))
            betrag = (abs(haben_) if haben_ else 0) - (abs(soll_) if soll_ else 0)
        if betrag is None:
            continue
        if hol("sh").upper().startswith("S"):
            betrag = -abs(betrag)
        elif hol("sh").upper().startswith("H"):
            betrag = abs(betrag)
        eigenes = ba.iban_normal(hol("konto")) or ba.iban_normal(iban)
        if not eigenes:
            raise ImportFehler("Für welches Konto ist diese Datei? Bitte die "
                               "IBAN des Kontos angeben.")
        konto_ibans.add(eigenes)
        saldo = _zahl(hol("saldo"))
        umsaetze.append({
            "konto": ba.konto_id(eigenes), "iban": eigenes, "buchung": buchung,
            "valuta": _iso_datum(hol("valuta")), "betrag": round(betrag, 2),
            "waehrung": hol("waehrung") or "EUR",
            "gegenpartei": hol("gegenpartei")[:140],
            "gegen_iban": ba.iban_normal(hol("gegen_iban")) or None,
            "zweck": hol("zweck")[:300], "art": hol("art") or None,
            "saldo": saldo, "referenz": None, "quelle": "csv"})
    if not umsaetze:
        raise ImportFehler("In der Datei steht kein lesbarer Umsatz.")
    konten = []
    for i in sorted(konto_ibans):
        eigene = [u for u in umsaetze if u["iban"] == i]
        letzter = max(eigene, key=lambda u: u["buchung"])
        konten.append({"iban": i, "von": min(u["buchung"] for u in eigene),
                       "bis": letzter["buchung"],
                       "saldo": ({"betrag": letzter["saldo"], "datum": letzter["buchung"]}
                                 if letzter["saldo"] is not None else None)})
    return {"art": "csv", "konten": konten,
            "umsaetze": ba.kennungen_vergeben(umsaetze), "hinweise": []}
