"""Rechnungen stellen — der Kern, ohne I/O.

Was hier entsteht, ist die Rechnung als Zahlenwerk: Positionen, Summen je
Steuersatz, Pflichtangaben nach § 14 UStG. Wo sie liegt und wie das PDF
aussieht, ist Sache der Aufrufer (`babu_web`, die App).

Grundhaltung: babu rechnet und weist aus. Ob die Leistung steuerfrei ist
oder welcher Satz gilt, entscheidet die Nutzerin — babu rät es nicht.
"""
from __future__ import annotations

import re

from geld import rund as _rund

# Bis zu diesem Bruttobetrag genügt die Kleinbetragsrechnung (§ 33 UStDV):
# ohne Empfängeranschrift, ohne getrennten Steuerausweis.
KLEINBETRAG_GRENZE = 250.0

NUMMER_RE = re.compile(r"^(\d{4})-(\d{4})$")

# Der Satz, der auf jede Rechnung einer Kleinunternehmerin gehört.
HINWEIS_19 = ("Kein Ausweis von Umsatzsteuer nach § 19 UStG "
              "(Kleinunternehmerregelung).")


class RechnungFehler(ValueError):
    """Die Rechnung ließe sich so nicht stellen."""


def naechste_nummer(vorhandene: list[str | None], jahr: int) -> str:
    """Die nächste Nummer der Folge — `JJJJ-NNNN`, je Jahr bei 1 beginnend.

    Gezählt wird ab der HÖCHSTEN vorhandenen Nummer, nicht ab ihrer Anzahl:
    hat eine Rechnung mal keine Datei hinterlassen, darf ihre Nummer nicht
    ein zweites Mal vergeben werden.
    """
    hoechste = 0
    for wert in vorhandene or []:
        m = NUMMER_RE.match(str(wert or ""))
        if m and int(m.group(1)) == jahr:
            hoechste = max(hoechste, int(m.group(2)))
    return f"{jahr}-{hoechste + 1:04d}"


def _positionen_rechnen(positionen: list[dict], preise_brutto: bool = True,
                        klein: bool = False) -> list[dict]:
    """Die Positionen einer Rechnung, fertig gerechnet.

    Preise sind standardmäßig BRUTTO — das ist die Zahl, die Nina im Kopf
    hat und die ihre Kundin zahlt („der Schnitt kostet 45 €"). Bis zum
    28.08.2026 galt der eingegebene Preis als Netto, und aus 45 € wurden
    auf der Rechnung 53,55 € (Ninas Anmerkung, Brutto als Vorgabe).

    Gerechnet wird vom Brutto abwärts: erst die Zeilensumme brutto, dann
    das Netto daraus. So steht am Ende exakt der Betrag auf der Rechnung,
    den sie eingetippt hat — bei der umgekehrten Richtung fehlt sonst je
    Zeile ein Cent.

    Eine einzelne Position darf abweichen (`brutto: false`), falls ein
    Posten wirklich netto vereinbart ist.
    """
    fertig = []
    for p in positionen or []:
        text = str((p or {}).get("text") or "").strip()[:200]
        try:
            einzel = float(p.get("einzelpreis"))
        except (TypeError, ValueError):
            raise RechnungFehler("Eine Position ohne Betrag gibt es nicht.")
        menge = p.get("menge")
        try:
            menge = float(menge) if menge is not None else 1.0
        except (TypeError, ValueError):
            menge = 1.0
        satz = p.get("ust_satz")
        satz = int(satz) if satz in (0, 7, 19, "0", "7", "19") else 19
        # § 19 UStG: keine Umsatzsteuer. Dann ist der eingegebene Preis der
        # Preis — es gibt nichts herauszurechnen, egal was als Satz kam.
        if klein:
            satz = 0
        if not text:
            raise RechnungFehler("Jede Position braucht eine Bezeichnung.")
        # `brutto_eingegeben` steht in einer schon gerechneten Position —
        # ein Storno baut aus ihr eine neue Rechnung, und die muss dieselbe
        # Seite meinen, sonst wird ein zweites Mal Steuer herausgerechnet.
        ist_brutto = p.get("brutto")
        if ist_brutto is None:
            ist_brutto = p.get("brutto_eingegeben")
        ist_brutto = preise_brutto if ist_brutto is None else bool(ist_brutto)
        if ist_brutto and satz:
            gesamt_brutto = _rund(einzel * menge)
            gesamt = _rund(gesamt_brutto / (1 + satz / 100))
            einzel_netto = _rund(einzel / (1 + satz / 100))
        else:
            einzel_netto = _rund(einzel)
            gesamt = _rund(einzel * menge)
            gesamt_brutto = _rund(gesamt * (1 + satz / 100))
        fertig.append({"text": text, "menge": menge,
                       "einzelpreis": einzel_netto,
                       "einzelpreis_brutto": _rund(einzel) if ist_brutto
                       else _rund(einzel * (1 + satz / 100)),
                       "brutto_eingegeben": ist_brutto,
                       "ust_satz": satz, "gesamt": gesamt,
                       "gesamt_brutto": gesamt_brutto})
    if not fertig:
        raise RechnungFehler("Ohne Position ist es keine Rechnung.")
    return fertig


def aufbauen(nummer: str, datum: str, empfaenger: dict, positionen: list[dict],
             stammdaten: dict, leistungszeitpunkt: str | None = None,
             hinweis_frei: str = "", preise_brutto: bool = True) -> dict:
    """Aus Eingaben eine vollständige Rechnung bauen (ohne sie festzuschreiben).

    `preise_brutto` sagt, wie die eingegebenen Preise gemeint sind —
    Vorgabe ist brutto, weil das die Zahl ist, die Nina und ihre Kundin
    kennen."""
    stamm = {k: str((stammdaten or {}).get(k) or "").strip()
             for k in ("betrieb_name", "anschrift", "steuernummer",
                       "ust_id", "kleinunternehmer", "telefon", "email",
                       "iban", "bank")}
    klein = stamm.get("kleinunternehmer") == "Ja"
    zeilen = _positionen_rechnen(positionen, preise_brutto, klein)

    if klein:
        # § 19: keine Umsatzsteuer, kein Ausweis, kein Satz in der Tabelle.
        saetze: list[dict] = []
        netto = _rund(sum(z["gesamt"] for z in zeilen))
        ust, brutto = 0.0, netto
    else:
        # Je Steuersatz EINMAL rechnen — und zwar von der Seite, die
        # eingegeben wurde. Bei Bruttopreisen aus dem Brutto zurück (sonst
        # steht am Ende ein anderer Betrag als getippt), bei Nettopreisen
        # wie bisher aufgeschlagen. Netto, Steuer und Endsumme kommen
        # danach aus DIESEN Zahlen, nie aus zwei verschiedenen Quellen —
        # sonst ergibt Netto + Steuer nicht die Endsumme.
        je_satz: dict[int, dict] = {}
        for z in zeilen:
            e = je_satz.setdefault(z["ust_satz"],
                                   {"netto": 0.0, "brutto": 0.0, "aus_brutto": True})
            e["netto"] += z["gesamt"]
            e["brutto"] += z["gesamt_brutto"]
            if not z["brutto_eingegeben"]:
                e["aus_brutto"] = False
        saetze = []
        for s, e in sorted(je_satz.items()):
            if not s:
                continue
            if e["aus_brutto"]:
                b = _rund(e["brutto"])
                n = _rund(b / (1 + s / 100))
                st = _rund(b - n)
            else:
                # Nettopreise: die Steuer direkt aus dem Netto runden. Über
                # den Umweg Brutto ginge der halbe Cent verloren (2,50 € zu
                # 19 % sind 0,475 € und damit 0,48 €, nicht 0,47 €).
                n = _rund(e["netto"])
                st = _rund(n * s / 100)
            saetze.append({"satz": s, "netto": n, "ust": st})
        # Steuerfreie Zeilen (Satz 0) tragen kein Steuerfeld, gehören aber
        # in die Summe.
        frei = _rund(sum(z["gesamt"] for z in zeilen if not z["ust_satz"]))
        netto = _rund(sum(s["netto"] for s in saetze) + frei)
        ust = _rund(sum(s["ust"] for s in saetze))
        brutto = _rund(netto + ust)
    return {
        "nummer": nummer,
        "datum": str(datum)[:10],
        "leistungszeitpunkt": str(leistungszeitpunkt or datum)[:10],
        "aussteller": stamm,
        "empfaenger": {"name": str((empfaenger or {}).get("name") or "").strip()[:120],
                       "anschrift": str((empfaenger or {}).get("anschrift") or "").strip()[:200],
                       "ust_id": str((empfaenger or {}).get("ust_id") or "").strip()[:20]},
        "positionen": zeilen,
        "netto": netto, "ust": ust, "brutto": brutto, "saetze": saetze,
        "kleinunternehmer": klein,
        "kleinbetrag": abs(brutto) <= KLEINBETRAG_GRENZE,
        "hinweis": HINWEIS_19 if klein else "",
        "hinweis_frei": str(hinweis_frei or "").strip()[:300],
        "bezahlt_am": None,
        "storniert": None,
        "storniert_durch": None,
    }


def fehlende_pflichtangaben(rechnung: dict) -> list[str]:
    """Was § 14 UStG verlangt und noch fehlt — in Klartext für die Nutzerin."""
    a = (rechnung or {}).get("aussteller") or {}
    e = (rechnung or {}).get("empfaenger") or {}
    fehlt = []
    if not a.get("betrieb_name"):
        fehlt.append("Auf die Rechnung gehört dein Betriebsname.")
    if not a.get("anschrift"):
        fehlt.append("Auf die Rechnung gehört deine Anschrift.")
    if not (a.get("steuernummer") or a.get("ust_id")):
        fehlt.append("Auf die Rechnung gehört deine Steuernummer.")
    if not e.get("name"):
        fehlt.append("Der Empfänger braucht einen Namen.")
    # Unter 250 € darf die Anschrift der Empfängerin fehlen (§ 33 UStDV).
    if not e.get("anschrift") and not rechnung.get("kleinbetrag"):
        fehlt.append("Der Empfänger braucht eine Anschrift.")
    if not rechnung.get("nummer"):
        fehlt.append("Die Rechnung braucht eine Nummer.")
    if not rechnung.get("datum"):
        fehlt.append("Die Rechnung braucht ein Datum.")
    return fehlt


def storno(rechnung: dict, nummer: str, datum: str) -> dict:
    """Die Gegenrechnung: gleiche Positionen, negative Beträge, mit Verweis.

    Eine gestellte Rechnung wird nicht gelöscht und nicht verändert — sie
    wird storniert. Das ist die einzige Form, die eine Prüfung übersteht.
    """
    if (rechnung or {}).get("storniert"):
        return _nicht_nochmal()
    # Die Gegenposition muss von DERSELBEN Seite gerechnet werden wie das
    # Original — bei einem Bruttopreis also vom Brutto, sonst weicht das
    # Storno um Rundungscents von der Rechnung ab, die es aufhebt.
    zeilen = []
    for z in rechnung["positionen"]:
        aus_brutto = z.get("brutto_eingegeben", False)
        preis = z.get("einzelpreis_brutto") if aus_brutto else z["einzelpreis"]
        zeilen.append(dict(
            z, brutto=aus_brutto, einzelpreis=-_rund(preis or 0.0),
            gesamt=-z["gesamt"],
            text=f"Storno zu Rechnung {rechnung['nummer']}: {z['text']}"))
    s = aufbauen(nummer=nummer, datum=datum,
                 empfaenger=rechnung["empfaenger"], positionen=zeilen,
                 stammdaten=rechnung["aussteller"],
                 leistungszeitpunkt=rechnung.get("leistungszeitpunkt"))
    s["storniert"] = rechnung["nummer"]
    s["hinweis_frei"] = f"Storno zu Rechnung {rechnung['nummer']}."
    return s


def _nicht_nochmal():
    raise RechnungFehler("Ein Storno lässt sich nicht noch einmal stornieren.")


def stand(rechnung: dict) -> str:
    """offen · bezahlt · storniert — was in der Liste steht."""
    r = rechnung or {}
    if r.get("storniert_durch") or r.get("storniert"):
        return "storniert"
    return "bezahlt" if r.get("bezahlt_am") else "offen"


def zaehlt_im_monat(rechnung: dict, versteuerung: str = "ist") -> str | None:
    """In welchem Monat zählt diese Rechnung als Erlös?

    Ist-Versteuerung (§ 20 UStG, und was die EÜR verlangt): wenn das Geld
    ankommt. Soll-Versteuerung: wenn die Rechnung gestellt wird. Eine
    stornierte Rechnung zählt gar nicht — das Storno selbst schon.
    """
    r = rechnung or {}
    if r.get("storniert_durch"):
        return None
    if str(versteuerung).lower() == "soll":
        return (r.get("datum") or "")[:7] or None
    return (r.get("bezahlt_am") or "")[:7] or None
