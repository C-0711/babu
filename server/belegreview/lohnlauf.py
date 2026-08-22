"""Der Monatslauf: was babu an die Lohnschiene übergibt — und nachprüft.

Die Rollenteilung steht: babu ist das System, in dem alles lebt —
Personalakte, Verträge, Zeiten, Abwesenheiten. Gerechnet und gemeldet wird
bei Buhl, denn dort liegt das GKV-Zertifikat, ohne das niemand
Sozialversicherungsmeldungen senden darf (§ 95b SGB IV).

Dieses Modul macht drei Dinge, und alle drei bleiben richtig, egal wie die
Schnittstelle im Einzelnen aussieht:

**Vollständigkeit prüfen, bevor etwas rausgeht.** Eine Abrechnung ohne
Sozialversicherungsnummer oder ohne Steuer-Identifikationsnummer scheitert
auf der anderen Seite — nur merkt man es dann später und in fremder
Sprache. babu sagt vorher, was fehlt, und zwar so, dass Nina es beschaffen
kann.

**Die Übergabe bauen.** Stammdaten plus Bewegungsdaten des Monats:
Arbeitsstunden aus dem Kalender, Abwesenheiten, Einmalzahlungen. Das ist
der Teil, den nur babu hat — der Lohnrechner kennt keine Termine.

**Nachrechnen, was zurückkommt.** babu rechnet dieselbe Abrechnung mit dem
amtlichen Programmablaufplan noch einmal und vergleicht. Beide folgen
demselben Plan, also muss dasselbe herauskommen; tut es das nicht, ist eine
Eingabe verrutscht. Das ist keine Misstrauensbekundung gegen Buhl, sondern
dieselbe Gegenprobe, die babu schon bei Belegen macht.

Beträge durchgehend in Cent. Zeiten in Minuten.
"""
from __future__ import annotations

import datetime as dt

# ———————————————————————————————————————————————————————————————
# Sozialversicherung 2026
# ———————————————————————————————————————————————————————————————
#
# Aus dem BMF-Schreiben zum Programmablaufplan 2026. Beitragssätze sind
# Gesamtsätze; wer was trägt, steht in `_haelfte`.

SV_2026 = {
    "bbg_kv_pv": 69_750_00,      # Beitragsbemessungsgrenze KV/PV, Cent/Jahr
    "bbg_rv_alv": 101_400_00,    # Beitragsbemessungsgrenze RV/ALV
    "kv_allgemein": 0.146,       # allgemeiner Beitragssatz
    "kv_ermaessigt": 0.140,
    "pv": 0.036,
    "pv_kinderlos": 0.006,       # Zuschlag, trägt die Arbeitnehmerin allein
    "pv_abschlag_je_kind": 0.0025,   # ab dem 2. Kind, höchstens vier Abschläge
    "rv": 0.186,
    "alv": 0.026,
    "umlage_u1": 0.0,            # kassenindividuell — kommt aus der Kasse
    "umlage_u2": 0.0,
    "insolvenzgeld": 0.0015,     # trägt der Arbeitgeber allein
}


class LohnlaufFehler(ValueError):
    """So ließe sich der Monat nicht übergeben."""


# ———————————————————————————————————————————————————————————————
# Was fehlt noch?
# ———————————————————————————————————————————————————————————————

# Was jede Abrechnung braucht — und warum, damit Nina weiß, wo sie es
# herbekommt.
PFLICHTFELDER = {
    "vorname": "Vorname",
    "name": "Nachname",
    "geburtsdatum": "Geburtsdatum",
    "strasse": "Straße",
    "plz": "Postleitzahl",
    "ort": "Ort",
    "staatsangehoerigkeit": "Staatsangehörigkeit",
    "rentenvers_nr": "Sozialversicherungsnummer — steht auf dem Ausweis der "
                     "Rentenversicherung; fehlt sie, vergibt die Kasse eine",
    "steuer_idnr": "Steuer-Identifikationsnummer — elfstellig, steht im "
                   "letzten Steuerbescheid oder im Brief vom Bundeszentralamt",
    "krankenkasse": "Krankenkasse",
    "iban": "IBAN",
    "eintritt": "Eintrittsdatum",
    "art": "Art der Beschäftigung",
    "entgelt": "Vereinbartes Entgelt",
    "stunden_woche": "Wochenarbeitszeit",
}

# Nur bei bestimmten Beschäftigungsarten oder Umständen.
ZUSATZFELDER = {
    "minijob": {"rv_befreiung": "Antrag auf Befreiung von der "
                                "Rentenversicherungspflicht (oder die "
                                "ausdrückliche Angabe, dass keiner vorliegt)"},
    "ausbildung": {"ausbildungsjahr": "Ausbildungsjahr"},
}


def _leer(wert) -> bool:
    return wert is None or (isinstance(wert, str) and not wert.strip())


def was_fehlt(mitarbeiter: dict) -> list[dict]:
    """Was vor der ersten Abrechnung noch beschafft werden muss."""
    m = mitarbeiter if isinstance(mitarbeiter, dict) else {}
    fehlt = [{"feld": f, "text": t}
             for f, t in PFLICHTFELDER.items() if _leer(m.get(f))]

    for feld, text in ZUSATZFELDER.get(str(m.get("art") or ""), {}).items():
        if feld not in m:
            fehlt.append({"feld": feld, "text": text})

    # Wer keinen deutschen oder EU-Pass hat, braucht einen gültigen Titel —
    # und der Arbeitgeber muss eine Kopie vorhalten (§ 4a Abs. 5 AufenthG).
    if m.get("titel_pflichtig") and _leer(m.get("titel_bis")):
        fehlt.append({"feld": "titel_bis",
                      "text": "Gültigkeit des Aufenthaltstitels — eine Kopie "
                              "ist für die Dauer der Beschäftigung "
                              "aufzubewahren (§ 4a Abs. 5 AufenthG)"})
    return fehlt


def abrechenbar(mitarbeiter: dict) -> bool:
    return not was_fehlt(mitarbeiter)


# ———————————————————————————————————————————————————————————————
# Die Bewegungsdaten des Monats
# ———————————————————————————————————————————————————————————————

def monatsstunden(zeiten: list[dict], monat: str) -> dict:
    """Was im Monat tatsächlich gearbeitet wurde.

    Gezählt werden nur bestätigte Aufzeichnungen. Eine unbestätigte Zeit in
    eine Abrechnung zu übernehmen, hieße, ungeprüft Geld zu bewegen — und
    die Bestätigung ist zugleich der Nachweis nach dem Arbeitszeitgesetz.
    """
    if not _monat_gueltig(monat):
        raise LohnlaufFehler("Der Monat gehört als JJJJ-MM angegeben.")
    minuten = offen = 0
    tage = set()
    for z in zeiten or []:
        if str(z.get("tag", ""))[:7] != monat:
            continue
        if not z.get("bestaetigt"):
            offen += 1
            continue
        dauer = int(z.get("minuten") or 0) - int(z.get("pause_min") or 0)
        if dauer < 0:
            raise LohnlaufFehler(
                f"Am {z.get('tag')} ist die Pause länger als der Arbeitstag.")
        minuten += dauer
        tage.add(z.get("tag"))
    return {"minuten": minuten, "stunden": round(minuten / 60, 2),
            "tage": len(tage), "unbestaetigt": offen}


def abwesenheiten_zaehlen(abwesenheiten: list[dict], monat: str) -> dict:
    """Urlaub, Krankheit und Unbezahltes — jeweils in Kalendertagen."""
    zaehler = {"urlaub": 0, "krank": 0, "unbezahlt": 0}
    for a in abwesenheiten or []:
        art = str(a.get("art") or "").lower()
        if art not in zaehler:
            continue
        von, bis = _tag(a.get("von")), _tag(a.get("bis") or a.get("von"))
        if bis < von:
            raise LohnlaufFehler("Eine Abwesenheit endet vor ihrem Beginn.")
        tag = von
        while tag <= bis:
            if tag.strftime("%Y-%m") == monat:
                zaehler[art] += 1
            tag += dt.timedelta(days=1)
    return zaehler


def _tag(wert) -> dt.date:
    if isinstance(wert, dt.date):
        return wert
    try:
        return dt.date.fromisoformat(str(wert)[:10])
    except (TypeError, ValueError):
        raise LohnlaufFehler(f"Datum nicht lesbar: {wert!r}")


def _monat_gueltig(monat: str) -> bool:
    import re
    return bool(re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", str(monat or "")))


# ———————————————————————————————————————————————————————————————
# Sozialversicherung überschlagen
# ———————————————————————————————————————————————————————————————

def sv_beitraege(brutto_cent: int, *, kv_zusatz: float = 0.029,
                 kinderlos: bool = False, kinder_abschlaege: int = 0,
                 rv_pflichtig: bool = True, alv_pflichtig: bool = True,
                 kv_pflichtig: bool = True, werte: dict | None = None) -> dict:
    """Was auf ein Monatsbrutto an Beiträgen entfällt — überschlägig.

    Ausdrücklich ein Überschlag für die Vorschau: „was kostet mich diese
    Einstellung?" Gerechnet und gemeldet wird bei Buhl. Umlagen U1/U2 sind
    kassenindividuell und deshalb nicht enthalten.
    """
    if brutto_cent < 0:
        raise LohnlaufFehler("Ein negatives Brutto gibt es nicht.")
    w = {**SV_2026, **(werte or {})}

    kv_pv_basis = min(brutto_cent, w["bbg_kv_pv"] // 12)
    rv_alv_basis = min(brutto_cent, w["bbg_rv_alv"] // 12)

    an = ag = 0
    teile = {}

    if kv_pflichtig:
        kv = round(kv_pv_basis * (w["kv_allgemein"] + kv_zusatz))
        teile["kv"] = kv
        an += kv // 2
        ag += kv - kv // 2

        pv_satz = w["pv"] - min(kinder_abschlaege, 4) * w["pv_abschlag_je_kind"]
        pv = round(kv_pv_basis * pv_satz)
        # Der Zuschlag für Kinderlose trägt allein die Arbeitnehmerin.
        zuschlag = round(kv_pv_basis * w["pv_kinderlos"]) if kinderlos else 0
        teile["pv"] = pv + zuschlag
        an += pv // 2 + zuschlag
        ag += pv - pv // 2

    if rv_pflichtig:
        rv = round(rv_alv_basis * w["rv"])
        teile["rv"] = rv
        an += rv // 2
        ag += rv - rv // 2

    if alv_pflichtig:
        alv = round(rv_alv_basis * w["alv"])
        teile["alv"] = alv
        an += alv // 2
        ag += alv - alv // 2

    # Insolvenzgeldumlage trägt der Arbeitgeber allein.
    insolvenz = round(rv_alv_basis * w["insolvenzgeld"])
    ag += insolvenz
    teile["insolvenzgeld"] = insolvenz

    return {"arbeitnehmer": an, "arbeitgeber": ag, "teile": teile,
            "gesamtkosten": brutto_cent + ag}


# ———————————————————————————————————————————————————————————————
# Die Übergabe
# ———————————————————————————————————————————————————————————————

UEBERGABE_FASSUNG = "1"


def uebergabe_bauen(betrieb: dict, leute: list[dict], monat: str) -> dict:
    """Alles, was die Lohnschiene für einen Monat braucht.

    Bewusst nicht auf eine bestimmte Schnittstelle zugeschnitten: das hier
    ist, was babu weiß. Die Abbildung auf Buhls Felder ist ein eigener,
    kleiner Schritt — und wenn die Schiene einmal wechselt, bleibt das hier.
    """
    if not _monat_gueltig(monat):
        raise LohnlaufFehler("Der Monat gehört als JJJJ-MM angegeben.")
    if not str(betrieb.get("betriebsnummer") or "").strip():
        raise LohnlaufFehler(
            "Ohne Betriebsnummer der Agentur für Arbeit kann nicht "
            "abgerechnet werden. Sie wird einmalig online beantragt.")

    zeilen, unvollstaendig = [], []
    for m in leute:
        fehlt = was_fehlt(m)
        if fehlt:
            unvollstaendig.append({
                "name": f"{m.get('vorname', '')} {m.get('name', '')}".strip()
                        or "ohne Namen",
                "fehlt": fehlt})
            continue

        stunden = monatsstunden(m.get("zeiten"), monat)
        abwesend = abwesenheiten_zaehlen(m.get("abwesenheiten"), monat)
        zeilen.append({
            "person": {k: m.get(k) for k in (
                "vorname", "name", "geburtsdatum", "geburtsname",
                "geburtsort", "staatsangehoerigkeit", "strasse", "plz",
                "ort", "rentenvers_nr", "steuer_idnr")},
            "beschaeftigung": {k: m.get(k) for k in (
                "art", "eintritt", "austritt", "befristet_bis", "taetigkeit",
                "stunden_woche", "tage_woche", "entgelt", "urlaubstage")},
            "sozialversicherung": {
                "krankenkasse": m.get("krankenkasse"),
                "kv_zusatzbeitrag": m.get("kv_zusatzbeitrag"),
                "rv_befreiung": m.get("rv_befreiung"),
                "kinderlos": m.get("kinderlos"),
                "kinder_abschlaege": m.get("kinder_abschlaege", 0)},
            "bank": {"iban": m.get("iban"), "bic": m.get("bic")},
            "monat": {**stunden, **abwesend,
                      "einmalzahlungen": m.get("einmalzahlungen") or []},
        })

    return {
        "fassung": UEBERGABE_FASSUNG,
        "monat": monat,
        "erstellt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "betrieb": {k: betrieb.get(k) for k in (
            "name", "betriebsnummer", "steuernummer", "strasse", "plz",
            "ort", "finanzamt")},
        "mitarbeiter": zeilen,
        "unvollstaendig": unvollstaendig,
        "bereit": not unvollstaendig and bool(zeilen),
    }


def uebergabe_pruefen(uebergabe: dict) -> list[str]:
    """Was einer Übergabe im Weg steht — in Ninas Sprache."""
    hindernisse = []
    if not uebergabe.get("mitarbeiter"):
        hindernisse.append("Für diesen Monat ist niemand abzurechnen.")
    for u in uebergabe.get("unvollstaendig") or []:
        was = ", ".join(f["text"].split(" — ")[0] for f in u["fehlt"])
        hindernisse.append(f"{u['name']}: es fehlt noch {was}.")
    for m in uebergabe.get("mitarbeiter") or []:
        offen = m["monat"].get("unbestaetigt") or 0
        if offen:
            name = f"{m['person'].get('vorname', '')} {m['person'].get('name', '')}".strip()
            hindernisse.append(
                f"{name}: {offen} Arbeitstage sind noch nicht bestätigt. "
                "Unbestätigte Zeiten gehen nicht in die Abrechnung.")
    return hindernisse


# ———————————————————————————————————————————————————————————————
# Die Gegenprobe
# ———————————————————————————————————————————————————————————————

def _euro(cent: int) -> str:
    """Deutsch, mit Vorzeichen — die Zahl liest eine Friseurin, kein Server."""
    return f"{cent / 100:+.2f} €".replace(".", ",")


def _benennung(feld: str) -> str:
    return {"lohnsteuer": "die Lohnsteuer",
            "soli": "der Solidaritätszuschlag"}.get(feld, feld)


def gegenprobe(zeile: dict, antwort: dict, *, steuerklasse: int,
               kv_zusatz: str = "2.90") -> dict:
    """Was die Schiene zurückmeldet, noch einmal selbst nachrechnen.

    Beide Seiten folgen demselben amtlichen Programmablaufplan, also muss
    dieselbe Lohnsteuer herauskommen. Weicht sie ab, ist mit hoher
    Wahrscheinlichkeit eine Eingabe verrutscht — ein Stundensatz, eine
    Steuerklasse, ein Zusatzbeitrag. Genau dafür ist die Gegenprobe da.
    """
    import lohnsteuer_pap as pap  # noqa: PLC0415

    brutto = int(zeile["beschaeftigung"]["entgelt"])
    sv = zeile.get("sozialversicherung", {})
    z = pap.Zustand(
        RE4=brutto, LZZ=2, STKL=steuerklasse,
        KVZ=str(sv.get("kv_zusatzbeitrag") or kv_zusatz).replace(",", "."),
        PVZ=1 if sv.get("kinderlos") else 0,
        PVA=int(sv.get("kinder_abschlaege") or 0),
        KRV=0, PKV=0, af=0)
    pap.berechnen(z)

    unsere = {"lohnsteuer": int(z.LSTLZZ), "soli": int(z.SOLZLZZ)}
    ihre = {"lohnsteuer": int(antwort.get("lohnsteuer") or 0),
            "soli": int(antwort.get("soli") or 0)}

    abweichungen = [
        {"feld": feld, "babu": unsere[feld], "schiene": ihre[feld],
         "differenz": ihre[feld] - unsere[feld]}
        for feld in unsere if unsere[feld] != ihre[feld]]

    return {
        "stimmt": not abweichungen,
        "babu": unsere,
        "schiene": ihre,
        "abweichungen": abweichungen,
        "satz": ("Nachgerechnet, stimmt überein."
                 if not abweichungen else
                 "Nachgerechnet: " + "; ".join(
                     f"{_benennung(a['feld'])} weicht um "
                     f"{_euro(a['differenz'])} ab" for a in abweichungen)
                 + ". Vor dem Auszahlen die Eingaben prüfen."),
    }
