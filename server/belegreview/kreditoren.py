"""Kreditoren — die Lieferanten eines Betriebs mit eigener Nummer (seit 03.10.2026).

Plan Kanzleiansicht, Schritt K1. Aus dem Telefonat mit der Kanzlei: kleine
Studios bleiben beim Sammelkonto (`extf.GEGENKONTO`, 70099), größere
Betriebe brauchen je Lieferant ein eigenes Kreditorenkonto, damit
Rechnungen und offene Posten nachvollziehbar bleiben.

Entscheidung des Auftraggebers: die Nummern kommen aus dem DATEV der
Kanzlei (Datei „Debitoren/Kreditoren“ oder die alten Buchungsstapel); für
neue Lieferanten vergibt babu die nächste freie Nummer. Eine vergebene
Nummer ändert sich nie — sie steht in Stapeln, die schon bei der Kanzlei
liegen.

Die Liste liegt je Betrieb in seiner Belegbox unter `stammdaten/
kreditoren.json` — Buchführungsunterlage mit Historie, und die Trennung der
Mandanten kommt über die Box von selbst.

Dieses Modul ist nur die REGEL: ohne Box, ohne Netz, ohne Uhr. Jede
Änderung gibt einen neuen Stand zurück und lässt den alten unberührt; die
Routen in `datev_seite.py` lesen, rechnen und schreiben.
"""
from __future__ import annotations

import copy
import csv
import io
import json
import math
import re
import unicodedata

import extf

PFAD = "stammdaten/kreditoren.json"
MODI = ("sammel", "einzeln")

# DATEV nimmt im Feld „Name (Adressattyp Unternehmen)“ höchstens 50 Zeichen.
NAME_MAX = 50
# Mit Sachkontenlänge 4 haben Personenkonten fünf Stellen: Debitoren
# 10000–69999, Kreditoren 70000–99999.
ERSTE_NUMMER = 70001
LETZTE_NUMMER = 99999

# Rechtsformen fallen beim Vergleichen weg: „Wella GmbH“ und „WELLA
# Deutschland GmbH & Co. KG“ sollen sich finden, „Wella“ und „Welle“ nicht.
RECHTSFORMEN = frozenset({
    "gmbh", "mbh", "kg", "ag", "ug", "ek", "ohg", "gbr", "co", "eg", "ev",
    "se", "kgaa", "haftungsbeschraenkt", "inh", "inhaber", "ltd", "inc",
})
UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


class KreditorFehler(Exception):
    """Ein Satz für die Kanzlei — kein Programmfehler."""


# ---------------------------------------------------------------------------
# Namen und Nummern
# ---------------------------------------------------------------------------

def norm_name(name: str | None) -> str:
    """„Müller & Söhne KG“ → „mueller soehne“ — zum Vergleichen und Sortieren."""
    text = str(name or "").lower().translate(UMLAUTE)
    text = "".join(z for z in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(z))
    text = text.replace(".", "")
    worte = re.sub(r"[^a-z0-9]+", " ", text).split()
    ohne = [w for w in worte if w not in RECHTSFORMEN]
    return " ".join(ohne or worte)


def buchstabe(name: str | None) -> str:
    """Der Anfangsbuchstabe für die A–Z-Leiste; Ziffern und Rest unter „#“."""
    n = norm_name(name)
    return n[0].upper() if n and "a" <= n[0] <= "z" else "#"


_anfang = buchstabe       # `liste` hat einen Parameter gleichen Namens


def ist_kreditornummer(nummer, laenge: int = int(extf.SACHKONTENLAENGE)) -> bool:
    n = str(nummer or "").strip()
    return n.isdigit() and len(n) == laenge + 1 and n[0] in "789"


def _name_pruefen(name) -> str:
    n = " ".join(str(name or "").split())
    if not n:
        raise KreditorFehler("Bitte einen Namen eingeben.")
    if len(n) > NAME_MAX:
        raise KreditorFehler(f"Der Name darf höchstens {NAME_MAX} Zeichen haben "
                             "— mehr nimmt DATEV nicht.")
    return n


def _iban(roh) -> str:
    i = re.sub(r"\s+", "", str(roh or "")).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", i):
        raise KreditorFehler("Die IBAN sieht nicht vollständig aus.")
    return i


def _ibans(roh) -> list[str]:
    werte = roh if isinstance(roh, list) else ([roh] if roh else [])
    aus: list[str] = []
    for w in werte:
        i = _iban(w)
        if i not in aus:
            aus.append(i)
    return aus


# ---------------------------------------------------------------------------
# Stand
# ---------------------------------------------------------------------------

def leer() -> dict:
    return {"version": 1, "modus": "sammel", "sammelkonto": extf.GEGENKONTO,
            "kreditoren": []}


def _eintrag(roh: dict) -> dict | None:
    """Ein Kreditor in seiner festen Form — oder None, wenn er keiner ist."""
    if not isinstance(roh, dict):
        return None
    nummer = str(roh.get("nummer") or "").strip()
    name = " ".join(str(roh.get("name") or "").split())[:NAME_MAX]
    if not ist_kreditornummer(nummer) or not name:
        return None
    aliase = [str(a) for a in (roh.get("aliase") or []) if str(a or "").strip()]
    iban = [str(i) for i in (roh.get("iban") or []) if str(i or "").strip()]
    return {"nummer": nummer, "name": name, "aliase": aliase, "iban": iban,
            "quelle": str(roh.get("quelle") or "babu"),
            "angelegt_am": roh.get("angelegt_am"),
            "angelegt_von": roh.get("angelegt_von"),
            "an_datev_am": roh.get("an_datev_am"),
            "aktiv": roh.get("aktiv") is not False,
            "geaendert_am": roh.get("geaendert_am"),
            "geaendert_von": roh.get("geaendert_von")}


def _sortiert(kreditoren: list[dict]) -> list[dict]:
    return sorted(kreditoren, key=lambda k: int(k["nummer"]))


def laden(roh: bytes | None) -> dict:
    """Der Stand aus der Box — Unlesbares gilt als leerer Stand."""
    stand = leer()
    if not roh:
        return stand
    try:
        d = json.loads(roh)
    except ValueError:
        return stand
    if not isinstance(d, dict):
        return stand
    if d.get("modus") in MODI:
        stand["modus"] = d["modus"]
    if ist_kreditornummer(d.get("sammelkonto")):
        stand["sammelkonto"] = str(d["sammelkonto"])
    gesehen: set[str] = set()
    for roh_k in d.get("kreditoren") or []:
        k = _eintrag(roh_k)
        if k and k["nummer"] not in gesehen:
            gesehen.add(k["nummer"])
            stand["kreditoren"].append(k)
    stand["kreditoren"] = _sortiert(stand["kreditoren"])
    return stand


def als_bytes(stand: dict) -> bytes:
    return json.dumps(stand, ensure_ascii=False, indent=1).encode()


def _finden(stand: dict, nummer: str) -> dict:
    for k in stand["kreditoren"]:
        if k["nummer"] == str(nummer):
            return k
    raise KreditorFehler(f"Den Kreditor {nummer} gibt es nicht.")


def _namensgleich(stand: dict, name: str, ausser: str | None = None) -> dict | None:
    """Gibt es diesen Lieferanten schon — unter Namen oder Nebennamen?"""
    n = norm_name(name)
    for k in stand["kreditoren"]:
        if k["nummer"] == ausser:
            continue
        if n in {norm_name(x) for x in [k["name"], *k["aliase"]]}:
            return k
    return None


def naechste_nummer(stand: dict) -> str:
    """Fortlaufend nach der höchsten Nummer; das Sammelkonto bleibt frei."""
    nummern = [int(k["nummer"]) for k in stand["kreditoren"]]
    belegt = set(nummern) | {int(stand["sammelkonto"])}
    kandidat = max(nummern) + 1 if nummern else ERSTE_NUMMER
    while kandidat in belegt:
        kandidat += 1
    if kandidat > LETZTE_NUMMER:
        raise KreditorFehler("Der Nummernkreis für Kreditoren ist voll.")
    return str(kandidat)


# ---------------------------------------------------------------------------
# Ändern
# ---------------------------------------------------------------------------

def anlegen(stand: dict, name: str, von: str, am: str,
            iban=None) -> tuple[dict, dict]:
    """Ein neuer Lieferant mit der nächsten freien Nummer."""
    name = _name_pruefen(name)
    schon = _namensgleich(stand, name)
    if schon:
        raise KreditorFehler(f"Diesen Lieferanten gibt es schon: "
                             f"{schon['nummer']} {schon['name']}.")
    neu = copy.deepcopy(stand)
    k = _eintrag({"nummer": naechste_nummer(stand), "name": name,
                  "iban": _ibans(iban), "quelle": "babu",
                  "angelegt_am": am, "angelegt_von": von})
    neu["kreditoren"] = _sortiert([*neu["kreditoren"], k])
    return neu, k


def _alias_dazu(k: dict, name: str) -> None:
    if norm_name(name) == norm_name(k["name"]):
        return
    if norm_name(name) not in {norm_name(a) for a in k["aliase"]}:
        k["aliase"].append(name)


def aendern(stand: dict, nummer: str, felder: dict, von: str,
            am: str) -> tuple[dict, dict]:
    """Name, Nebennamen, IBAN, aktiv — die Nummer bleibt, wie sie ist."""
    neu = copy.deepcopy(stand)
    k = _finden(neu, nummer)
    if "name" in felder:
        name = _name_pruefen(felder["name"])
        schon = _namensgleich(neu, name, ausser=k["nummer"])
        if schon:
            raise KreditorFehler(f"Diesen Namen trägt schon {schon['nummer']} "
                                 f"{schon['name']}.")
        alt = k["name"]
        k["name"] = name
        _alias_dazu(k, alt)
    if "aliase" in felder:
        k["aliase"] = []
        for a in felder["aliase"] or []:
            _alias_dazu(k, _name_pruefen(a))
    if "iban" in felder:
        k["iban"] = _ibans(felder["iban"])
    if "aktiv" in felder:
        k["aktiv"] = bool(felder["aktiv"])
    k["geaendert_am"], k["geaendert_von"] = am, von
    return neu, k


def einstellen(stand: dict, modus: str | None = None,
               sammelkonto: str | None = None) -> dict:
    """Sammelkonto für alle oder ein Konto je Lieferant."""
    neu = copy.deepcopy(stand)
    if modus is not None:
        if modus not in MODI:
            raise KreditorFehler("Bitte „sammel“ oder „einzeln“ wählen.")
        neu["modus"] = modus
    if sammelkonto is not None:
        s = str(sammelkonto).strip()
        if not ist_kreditornummer(s):
            raise KreditorFehler("Das Sammelkonto ist ein Kreditorenkonto mit "
                                 "fünf Stellen, zum Beispiel 70099.")
        if any(k["nummer"] == s for k in neu["kreditoren"]):
            raise KreditorFehler(f"Die Nummer {s} gehört schon einem Lieferanten.")
        neu["sammelkonto"] = s
    return neu


# ---------------------------------------------------------------------------
# Liste: Suche, Anfangsbuchstabe, Seiten
# ---------------------------------------------------------------------------

def liste(stand: dict, q: str = "", buchstabe: str = "", seite: int = 1,
          pro_seite: int = 50) -> dict:
    """Alphabetisch nach dem vergleichbaren Namen, gefiltert und in Seiten.

    `buchstaben` zählt über die ganze Liste, nicht über den Filter: die
    A–Z-Leiste zeigt, wo überhaupt etwas steht.
    """
    wahl = str(buchstabe or "").strip().upper()
    alle = sorted(stand["kreditoren"],
                  key=lambda k: (norm_name(k["name"]), k["nummer"]))
    zaehler: dict[str, int] = {}
    for k in alle:
        b = _anfang(k["name"])
        zaehler[b] = zaehler.get(b, 0) + 1
    treffer = alle
    if wahl:
        treffer = [k for k in treffer if _anfang(k["name"]) == wahl]
    suche = str(q or "").strip()
    if suche.isdigit():
        treffer = [k for k in treffer if k["nummer"].startswith(suche)]
    elif suche:
        n = norm_name(suche)
        treffer = [k for k in treffer
                   if any(n in norm_name(x) for x in [k["name"], *k["aliase"]])]
    pro_seite = max(1, min(int(pro_seite or 50), 200))
    seiten = max(1, math.ceil(len(treffer) / pro_seite))
    seite = max(1, min(int(seite or 1), seiten))
    anfang = (seite - 1) * pro_seite
    return {"eintraege": treffer[anfang:anfang + pro_seite], "gesamt": len(treffer),
            "seite": seite, "seiten": seiten, "buchstaben": dict(sorted(zaehler.items()))}


# ---------------------------------------------------------------------------
# Datei lesen: DATEV „Debitoren/Kreditoren“ oder eine einfache Liste
# ---------------------------------------------------------------------------

NUMMER_SPALTEN = ("konto", "kontonummer", "konto-nr.", "konto-nr", "kontonr",
                  "kontonr.", "kreditor", "kreditornummer", "kreditorennummer",
                  "kreditor-nr.", "nummer", "personenkonto")
FIRMA = ("name (adressattyp unternehmen)", "name (adressattyp keine angabe)")
PERSON = ("vorname (adressattyp natürl. person)", "name (adressattyp natürl. person)")
NAME_SPALTEN = ("name", "bezeichnung", "kontenbeschriftung", "kontobeschriftung",
                "lieferant", "firma", "kreditorname", "kurzbezeichnung")


def _entziffern(roh: bytes) -> str:
    if roh.startswith(b"\xef\xbb\xbf"):
        return roh.decode("utf-8-sig")
    for kodierung in ("utf-8", "cp1252"):
        try:
            return roh.decode(kodierung)
        except UnicodeDecodeError:
            continue
    raise KreditorFehler("Der Zeichensatz der Datei lässt sich nicht lesen.")


def _reihe(zeile: str, trenner: str) -> list[str]:
    return [f.strip().strip('"').strip()
            for f in next(csv.reader([zeile], delimiter=trenner, quotechar='"'))]


def datei_lesen(roh: bytes) -> dict:
    """Eine Kreditorenliste lesen — nichts wird dabei geschrieben.

    DATEV-Dateien werden an Kopf und Spaltennamen erkannt; Spalten werden
    über ihren NAMEN gesucht, nicht über die Stelle (DATEV schiebt Spalten
    von Fassung zu Fassung). Übernommen werden nur Kreditoren — Debitoren
    und Sachkonten in derselben Datei zählen unter `uebersprungen`.
    """
    if not roh or not roh.strip():
        raise KreditorFehler("Die Datei ist leer.")
    zeilen = [z for z in _entziffern(roh).splitlines() if z.strip()]
    erste = _reihe(zeilen[0], ";")
    if erste and erste[0].upper() in ("EXTF", "DTVF"):
        art = "datev"
        if (erste[2] if len(erste) > 2 else "") != "16":
            name = (erste[3] if len(erste) > 3 else "") or "unbekannt"
            raise KreditorFehler(f"Diese DATEV-Datei ist keine Debitoren/"
                                 f"Kreditoren-Liste, sondern „{name}“.")
        laenge = (erste[13] if len(erste) > 13 else "") or extf.SACHKONTENLAENGE
        if laenge != extf.SACHKONTENLAENGE:
            raise KreditorFehler(
                f"Die Datei führt Konten mit Sachkontenlänge {laenge}, babu "
                f"schreibt den Stapel mit {extf.SACHKONTENLAENGE}. Das klären "
                "wir bitte zuerst mit der Kanzlei.")
        if len(zeilen) < 2:
            raise KreditorFehler("In der Datei fehlt die Spaltenzeile.")
        trenner, kopf, daten = ";", _reihe(zeilen[1], ";"), zeilen[2:]
    else:
        art = "csv"
        trenner = max((";", ",", "\t"), key=zeilen[0].count)
        kopf, daten = _reihe(zeilen[0], trenner), zeilen[1:]
    namen = [n.lower() for n in kopf]

    def stelle(kandidaten) -> int | None:
        return next((namen.index(k) for k in kandidaten if k in namen), None)

    i_nummer = stelle(NUMMER_SPALTEN)
    if i_nummer is None:
        raise KreditorFehler("In der Datei fehlt die Spalte mit der Kontonummer "
                             "(zum Beispiel „Konto“).")
    i_firma = [namen.index(k) for k in FIRMA if k in namen]
    i_person = [namen.index(k) for k in PERSON if k in namen]
    i_name = [namen.index(k) for k in NAME_SPALTEN if k in namen]
    if not (i_firma or i_person or i_name):
        raise KreditorFehler("In der Datei fehlt die Spalte mit dem Namen.")
    i_iban = [i for i, n in enumerate(namen) if n.startswith("iban")]

    eintraege: list[dict] = []
    gesehen: set[str] = set()
    uebersprungen = 0
    hinweise: list[str] = []
    for zeile in daten:
        f = _reihe(zeile, trenner)

        def hol(i: int) -> str:
            return f[i] if i < len(f) else ""

        nummer = re.sub(r"\s", "", hol(i_nummer))
        if not nummer:
            continue
        name = next((hol(i) for i in i_firma if hol(i)), "")
        if not name and i_person:
            name = " ".join(hol(i) for i in i_person if hol(i))
        if not name:
            name = next((hol(i) for i in i_name if hol(i)), "")
        name = " ".join(name.split())[:NAME_MAX]
        if not ist_kreditornummer(nummer) or not name:
            uebersprungen += 1
            continue
        if nummer in gesehen:
            hinweise.append(f"Die Nummer {nummer} steht mehrfach in der Datei — "
                            "übernommen wird die erste Zeile.")
            continue
        gesehen.add(nummer)
        ibans = []
        for i in i_iban:
            try:
                ibans.extend(x for x in _ibans(hol(i)) if x not in ibans)
            except KreditorFehler:
                pass
        eintraege.append({"nummer": nummer, "name": name, "iban": ibans})
    if not eintraege:
        raise KreditorFehler("In der Datei steht kein Kreditor — gesucht werden "
                             "fünfstellige Konten ab 70000.")
    return {"art": art, "eintraege": eintraege, "uebersprungen": uebersprungen,
            "hinweise": hinweise}


# ---------------------------------------------------------------------------
# Übernehmen: erst ansehen, dann zusammenführen
# ---------------------------------------------------------------------------

def vorschau(stand: dict, eintraege: list[dict], quelle: str) -> dict:
    """Was eine Übernahme ändern würde — ohne etwas zu ändern."""
    vorhanden = {k["nummer"]: k for k in stand["kreditoren"]}
    namen: dict[str, str] = {}
    for k in stand["kreditoren"]:
        for x in [k["name"], *k["aliase"]]:
            namen.setdefault(norm_name(x), k["nummer"])
    neu, geaendert, doppelt, gleich = [], [], [], 0
    for e in eintraege:
        k = vorhanden.get(e["nummer"])
        if k is not None:
            iban_neu = [i for i in (e.get("iban") or []) if i not in k["iban"]]
            if quelle == "historie" or (e["name"] == k["name"] and not iban_neu):
                gleich += 1
            else:
                geaendert.append({"nummer": e["nummer"], "alt": k["name"],
                                  "neu": e["name"], "iban_neu": iban_neu})
            continue
        neu.append({"nummer": e["nummer"], "name": e["name"]})
        n = norm_name(e["name"])
        if n in namen and namen[n] != e["nummer"]:
            doppelt.append({"nummer": e["nummer"], "name": e["name"],
                            "schon": namen[n]})
        namen.setdefault(n, e["nummer"])
    return {"neu": neu, "geaendert": geaendert, "gleich": gleich,
            "doppelt": doppelt}


def zusammenfuehren(stand: dict, eintraege: list[dict], quelle: str, von: str,
                    am: str) -> tuple[dict, dict]:
    """Übernehmen. DATEV gewinnt beim Namen, die Historie ergänzt nur.

    Was aus DATEV oder den alten Stapeln kommt, gibt es dort schon:
    `an_datev_am` ist gesetzt, eine Stammdaten-Lieferung braucht es nicht.
    """
    if quelle not in ("datev", "historie"):
        raise KreditorFehler("Unbekannte Quelle.")
    neu_stand = copy.deepcopy(stand)
    vorhanden = {k["nummer"]: k for k in neu_stand["kreditoren"]}
    zaehler = {"neu": 0, "geaendert": 0}
    for e in eintraege:
        nummer = str(e.get("nummer") or "")
        name = " ".join(str(e.get("name") or "").split())[:NAME_MAX]
        if not ist_kreditornummer(nummer) or not name \
                or nummer == neu_stand["sammelkonto"]:
            continue
        ibans = [i for i in (e.get("iban") or []) if i]
        k = vorhanden.get(nummer)
        if k is None:
            k = _eintrag({"nummer": nummer, "name": name, "iban": ibans,
                          "quelle": quelle, "angelegt_am": am,
                          "angelegt_von": von, "an_datev_am": am})
            neu_stand["kreditoren"].append(k)
            vorhanden[nummer] = k
            zaehler["neu"] += 1
            continue
        if quelle == "historie":
            continue
        geaendert = False
        if name != k["name"]:
            # Die Schreibweise der Kanzlei gilt — auch wenn nur „GmbH“ dazukam.
            # Nebenname wird der alte nur, wenn er sich wirklich unterscheidet.
            alt = k["name"]
            k["name"] = name
            _alias_dazu(k, alt)
            geaendert = True
        for i in ibans:
            if i not in k["iban"]:
                k["iban"].append(i)
                geaendert = True
        k["quelle"] = "datev"
        k["an_datev_am"] = k["an_datev_am"] or am
        if geaendert:
            k["geaendert_am"], k["geaendert_von"] = am, von
            zaehler["geaendert"] += 1
    neu_stand["kreditoren"] = _sortiert(neu_stand["kreditoren"])
    return neu_stand, zaehler
