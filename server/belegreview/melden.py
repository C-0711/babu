"""Was babu von sich aus sagen sollte — und wann.

Bisher muss die Inhaberin die App öffnen, um zu erfahren, dass in vier Tagen
die Voranmeldung fällig ist. Alles liegt bereit: Fristen, offene Belege,
unbezahlte Rechnungen, ablaufende Verträge. Nur holt es niemand ab.

Hier steht die Regel, nicht der Versand: aus den Daten des Salons entstehen
Meldungen mit Datum, Dringlichkeit und einem Satz in Alltagssprache. Reine
Rechnung ohne I/O — damit prüfbar ist, wann babu sich meldet und wann nicht.

Grundhaltung: lieber eine Meldung zu wenig als eine zu viel. Wer dreimal
umsonst aufs Telefon schaut, schaltet beim vierten Mal ab — und verpasst
dann die, auf die es ankam.
"""
from __future__ import annotations

import datetime as dt

# Wie lange vorher gewarnt wird. Zweimal, nicht öfter: einmal früh genug zum
# Handeln, einmal kurz davor als letzte Erinnerung.
FRIST_VORLAUF = (7, 1)
# Eine Kündigungsfrist braucht mehr Anlauf — dahinter steckt eine Entscheidung.
VERTRAG_VORLAUF = (30, 7)
# Ab wann eine unbezahlte Rechnung eine Erinnerung wert ist.
RECHNUNG_TAGE = 14
# Der Tag im Folgemonat, an dem babu den Monat zusammenfasst.
ABSCHLUSS_TAG = 3


def _datum(wert) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(wert)[:10])
    except (TypeError, ValueError):
        return None


def _tage_text(tage: int) -> str:
    if tage <= 0:
        return "heute"
    if tage == 1:
        return "morgen"
    return f"in {tage} Tagen"


def fristen_meldungen(termine: list[dict], heute: dt.date) -> list[dict]:
    """Steuertermine — der Klassiker, der Geld kostet, wenn er durchrutscht."""
    meldungen = []
    for t in termine or []:
        faellig = _datum((t or {}).get("faellig"))
        if faellig is None:
            continue
        tage = (faellig - heute).days
        if tage not in FRIST_VORLAUF:
            continue
        name = str(t.get("name") or t.get("art") or "Ein Termin")
        meldungen.append({
            "schluessel": f"frist:{t.get('art')}:{faellig.isoformat()}",
            "art": "frist",
            "titel": name,
            "text": f"Fällig {_tage_text(tage)} — am "
                    f"{faellig.strftime('%d.%m.')}.",
            "am": heute.isoformat(),
            "dringend": tage <= 1,
        })
    return meldungen


def vertrag_meldungen(vertraege: list[dict], heute: dt.date) -> list[dict]:
    """Kündigungsfristen. Verpasst kostet das ein weiteres Jahr."""
    meldungen = []
    for v in vertraege or []:
        frist = (v or {}).get("kuendigen_bis") or {}
        if not frist.get("sicher") or frist.get("vorbei"):
            continue
        bis = _datum(frist.get("datum"))
        if bis is None:
            continue
        tage = (bis - heute).days
        if tage not in VERTRAG_VORLAUF:
            continue
        partner = str(v.get("partner") or v.get("art_name") or "Ein Vertrag")
        meldungen.append({
            "schluessel": f"vertrag:{partner}:{bis.isoformat()}",
            "art": "vertrag",
            "titel": f"{partner} kündigen?",
            "text": f"Wenn du raus willst, muss die Kündigung bis "
                    f"{bis.strftime('%d.%m.')} draußen sein — {_tage_text(tage)}. "
                    f"Sonst läuft der Vertrag weiter.",
            "am": heute.isoformat(),
            "dringend": tage <= 7,
        })
    return meldungen


def rechnung_meldungen(rechnungen: list[dict], heute: dt.date) -> list[dict]:
    """Wer schuldet noch was — einmal erinnern, nicht täglich nörgeln."""
    meldungen = []
    for r in rechnungen or []:
        if (r or {}).get("bezahlt_am") or (r or {}).get("storniert_durch"):
            continue
        gestellt = _datum((r or {}).get("datum"))
        if gestellt is None or (heute - gestellt).days != RECHNUNG_TAGE:
            continue
        empf = ((r.get("empfaenger") or {}).get("name")) or "Jemand"
        betrag = r.get("brutto")
        meldungen.append({
            "schluessel": f"rechnung:{r.get('nummer')}",
            "art": "rechnung",
            "titel": f"{empf} hat noch nicht bezahlt",
            "text": f"Rechnung {r.get('nummer')} ist seit zwei Wochen offen"
                    + (f" ({betrag:.2f} €)".replace(".", ",") if betrag else "")
                    + ".",
            "am": heute.isoformat(),
            "dringend": False,
        })
    return meldungen


def abschluss_meldung(belege: list[dict], heute: dt.date) -> list[dict]:
    """Am 3. des Monats: der Vormonat ist gerechnet — oder es fehlt noch was."""
    if heute.day != ABSCHLUSS_TAG:
        return []
    vormonat = (heute.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    offen = [b for b in (belege or [])
             if b.get("monat") == vormonat
             and b.get("status") in ("nachfrage", "erfasst")]
    monatsname = dt.date.fromisoformat(vormonat + "-01").strftime("%B")
    if offen:
        text = (f"{len(offen)} Beleg{'e' if len(offen) > 1 else ''} "
                f"brauch{'en' if len(offen) > 1 else 't'} noch kurz dich, "
                f"dann ist {monatsname} fertig.")
    else:
        text = f"{monatsname} ist gerechnet — schau ihn dir an, dann kann er raus."
    return [{
        "schluessel": f"abschluss:{vormonat}",
        "art": "abschluss",
        "titel": f"Dein {monatsname}",
        "text": text,
        "am": heute.isoformat(),
        "dringend": False,
    }]


def belegjagd_meldung(fragen: list[dict], heute: dt.date) -> list[dict]:
    """Am 3.: wozu fehlt noch ein Beleg? Das ist der Posten, der am
    Jahresende wirklich Geld kostet."""
    if heute.day != ABSCHLUSS_TAG or not fragen:
        return []
    # Abbuchungen kommen mit negativem Vorzeichen — die Mahnsumme ist der Betrag.
    summe = sum(abs(float(f.get("betrag") or 0)) for f in fragen)
    anzahl = len(fragen)
    return [{
        "schluessel": f"belegjagd:{heute.isoformat()}",
        "art": "beleg",
        "titel": f"{anzahl} Abbuchung{'en' if anzahl > 1 else ''} ohne Beleg",
        "text": (f"Zusammen {summe:.2f} €".replace(".", ",")
                 + " — ohne Beleg zählt das steuerlich nicht. Die Liste steht "
                   "unter Konto → Kontoauszug; fotografieren genügt."),
        "am": heute.isoformat(),
        "dringend": False,
    }]


# Reihenfolge, wenn mehreres zugleich ansteht: was Geld kostet zuerst.
RANG = {"frist": 0, "vertrag": 1, "beleg": 2, "abschluss": 3, "rechnung": 4}
# Mehr als das schaut sich niemand an.
HOECHSTENS = 3


def meldungen(welt: dict, heute: dt.date | None = None) -> list[dict]:
    """Alles, was babu heute von sich aus sagen würde — höchstens drei."""
    heute = heute or dt.date.today()
    alle = (fristen_meldungen(welt.get("fristen"), heute)
            + vertrag_meldungen(welt.get("vertraege"), heute)
            + rechnung_meldungen(welt.get("rechnungen"), heute)
            + abschluss_meldung(welt.get("belege"), heute)
            + belegjagd_meldung(welt.get("fehlende_belege"), heute))
    alle.sort(key=lambda m: (not m["dringend"], RANG.get(m["art"], 9),
                             m["titel"]))
    return alle[:HOECHSTENS]
