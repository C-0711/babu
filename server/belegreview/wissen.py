"""Das Fallwissen des Chats — alles, was babu über diesen Salon weiß.

Bisher sah der Chat nur Belege und schnitt bei 12.000 Zeichen ab: je voller
die Box, desto weniger passte hinein, und was fehlte, merkte niemand. Hier
wird stattdessen AUSGEWÄHLT. Zur Frage passende Bereiche kommen zuerst, der
Rahmen (wer ist dieser Betrieb) immer.

Reine Rechnung ohne I/O — die Daten reicht `babu_web` herein, damit alles
ohne Server und ohne Sprachmodell testbar ist. Die Auswahl läuft über
Stichwörter statt über ein Modell: sie muss auch dann funktionieren, wenn
vLLM gerade nicht antwortet.
"""
from __future__ import annotations

import re

BUDGET = 14000

# Stichwörter je Bereich. Bewusst großzügig und in der Sprache der Nutzerin —
# sie fragt nach „Quittung", nicht nach „Belegposition".
STICHWORTE: dict[str, tuple[str, ...]] = {
    "beleg": ("beleg", "quittung", "bon", "rechnung von", "eingekauft", "gekauft",
              "ausgegeben", "ausgabe", "kosten", "einkauf", "ware", "großhandel",
              "lieferant", "vorsteuer", "abgesetzt", "absetzen", "bezahlt für"),
    "kasse": ("kasse", "kassenbuch", "umsatz", "eingenommen", "einnahme", "tag",
              "tagesumsatz", "trinkgeld", "ec", "bar", "gutschein", "abend"),
    "vertrag": ("vertrag", "miete", "versicherung", "leasing", "kündigen",
                "kündigung", "laufzeit", "frist", "dauerkosten", "monatlich",
                "strom", "telefon", "wartung"),
    "rechnung": ("rechnung", "stuhlmiete",
                 "schuldet", "offen", "forderung", "bezahlt mir", "kundin zahlt",
                 "mahnung", "rechnungsnummer", "berechnet"),
    "team": ("team", "personal", "mitarbeiter", "angestellte", "azubi", "lohn",
             "gehalt", "stunden", "aushilfe", "kollegin", "einstellen"),
    "frist": ("frist", "termin", "fällig", "abgabe", "voranmeldung", "wann muss",
              "bis wann", "verspätet", "säumnis", "kalender"),
    "zahlen": ("gewinn", "verdient", "bwa", "auswertung", "bleibt", "übrig",
               "rentabel", "lohnt", "zahlen", "monatsabschluss", "steuerlast",
               "ausgegeben", "ausgaben", "gekauft", "kosten", "wie viel"),
    "post": ("finanzamt", "amt", "brief", "bescheid", "schreiben", "behörde",
             "prüfung", "post", "kanzlei", "steuerberater"),
}


def _trifft(wort: str, text: str) -> bool:
    """Kurze Stichwörter nur als ganzes Wort — sonst steckt „ec" in
    „Rechnung" und jede Rechnungsfrage wäre plötzlich eine Kassenfrage."""
    if len(wort) <= 4 and " " not in wort:
        return re.search(rf"\b{re.escape(wort)}\b", text) is not None
    return wort in text


def themen(frage: str) -> set[str]:
    """Welche Bereiche berührt diese Frage? Leer ist erlaubt — dann ist es
    eine allgemeine Frage, und babu antwortet aus dem Rahmen heraus."""
    text = " " + (frage or "").lower() + " "
    gefunden = set()
    for bereich, worte in STICHWORTE.items():
        if any(_trifft(w, text) for w in worte):
            gefunden.add(bereich)
    return gefunden


def _euro(wert) -> str:
    try:
        return f"{float(wert):,.2f} €".replace(",", "@").replace(".", ",").replace("@", ".")
    except (TypeError, ValueError):
        return "—"


def _tag(iso: str | None) -> str:
    if not iso or len(str(iso)) < 10:
        return str(iso or "")
    j, m, t = str(iso)[:10].split("-")
    return f"{t}.{m}.{j}"


# ————— Die einzelnen Bereiche als Text —————

def _betrieb(welt: dict) -> str:
    e = welt.get("einstellungen") or {}
    if not e:
        return ""
    zeilen = ["DER BETRIEB:"]
    if e.get("betrieb_name"):
        zeilen.append(f"  Name: {e['betrieb_name']}")
    if e.get("rechtsform"):
        zeilen.append(f"  Rechtsform: {e['rechtsform']}")
    if e.get("kleinunternehmer"):
        zeilen.append("  Kleinunternehmerin (§ 19 UStG): " + e["kleinunternehmer"])
    if e.get("finanzamt"):
        zeilen.append(f"  Finanzamt: {e['finanzamt']}")
    if e.get("versteuerung"):
        art = "Ist (zahlt Umsatzsteuer, wenn das Geld ankommt)" \
            if e["versteuerung"] == "ist" else "Soll (mit Rechnungsdatum)"
        zeilen.append(f"  Versteuerung: {art}")
    return "\n".join(zeilen)


def _belege(welt: dict, grenze: int) -> str:
    belege = welt.get("belege") or []
    if not belege:
        return ""
    sortiert = sorted(belege, key=lambda b: (b.get("monat") or "", b.get("datum") or ""),
                      reverse=True)
    zeilen = [f"BELEGE ({len(belege)} in der Box, neueste zuerst):"]
    for b in sortiert:
        teil = (f"  {b.get('datum') or b.get('monat') or '—'} · "
                f"{b.get('lieferant') or 'unbekannt'} · {_euro(b.get('brutto'))}"
                f" · {b.get('belegart') or ''}")
        if b.get("konto_skr04"):
            teil += f" · Konto {b['konto_skr04']}"
        if b.get("offen"):
            teil += " · offen: " + "; ".join(str(o) for o in b["offen"][:2])
        if sum(len(z) for z in zeilen) + len(teil) > grenze:
            zeilen.append(f"  … und {len(sortiert) - len(zeilen) + 1} weitere")
            break
        zeilen.append(teil)
    return "\n".join(zeilen)


def _kasse(welt: dict, grenze: int) -> str:
    blaetter = welt.get("kassenblaetter") or []
    if not blaetter:
        return ""
    bar = sum(float(b.get("einnahmenBar") or 0) for b in blaetter)
    ec = sum(float(b.get("ecZahlungen") or 0) for b in blaetter)
    zeilen = [f"KASSENBUCH ({len(blaetter)} Tage erfasst):",
              f"  Bar zusammen: {_euro(bar)} · Karte zusammen: {_euro(ec)}",
              f"  Umsatz zusammen: {_euro(bar + ec)}"]
    for b in sorted(blaetter, key=lambda x: x.get("datum") or "", reverse=True):
        teil = (f"  {_tag(b.get('datum'))}: bar {_euro(b.get('einnahmenBar'))}, "
                f"Karte {_euro(b.get('ecZahlungen'))}")
        if sum(len(z) for z in zeilen) + len(teil) > grenze:
            break
        zeilen.append(teil)
    return "\n".join(zeilen)


def _vertraege(welt: dict, grenze: int) -> str:
    vertraege = welt.get("vertraege") or []
    if not vertraege:
        return ""
    summe = sum(float(v.get("betrag_monat") or 0) for v in vertraege)
    zeilen = [f"VERTRÄGE ({len(vertraege)}, zusammen {_euro(summe)} im Monat):"]
    for v in vertraege:
        teil = (f"  {v.get('art_name') or 'Vertrag'} · {v.get('partner') or '—'} · "
                f"{_euro(v.get('betrag_monat'))} im Monat")
        if v.get("laufzeit_bis"):
            teil += f" · läuft bis {_tag(v['laufzeit_bis'])}"
        if v.get("kuendigungsfrist"):
            teil += f" · Kündigungsfrist: {v['kuendigungsfrist']}"
        if sum(len(z) for z in zeilen) + len(teil) > grenze:
            break
        zeilen.append(teil)
    return "\n".join(zeilen)


def _rechnungen(welt: dict, grenze: int) -> str:
    rechnungen = welt.get("rechnungen") or []
    if not rechnungen:
        return ""
    offen = [r for r in rechnungen if not r.get("bezahlt_am")
             and not r.get("storniert_durch")]
    zeilen = [f"GESTELLTE RECHNUNGEN ({len(rechnungen)}, davon {len(offen)} offen):"]
    for r in sorted(rechnungen, key=lambda x: x.get("nummer") or "", reverse=True):
        empf = (r.get("empfaenger") or {}).get("name") or "—"
        stand = "bezahlt " + _tag(r["bezahlt_am"]) if r.get("bezahlt_am") else "OFFEN"
        teil = (f"  Nr. {r.get('nummer')} · {_tag(r.get('datum'))} · {empf} · "
                f"{_euro(r.get('brutto'))} · {stand}")
        if sum(len(z) for z in zeilen) + len(teil) > grenze:
            break
        zeilen.append(teil)
    return "\n".join(zeilen)


def _team(welt: dict, grenze: int) -> str:
    leute = [p for p in (welt.get("team") or []) if p.get("aktiv", True)]
    if not leute:
        return ""
    kosten = sum(float(p.get("kosten_monat") or 0) for p in leute)
    zeilen = [f"TEAM ({len(leute)} Personen, zusammen {_euro(kosten)} im Monat):"]
    for p in leute:
        zeilen.append(f"  {p.get('name')} · {_euro(p.get('kosten_monat'))} im Monat")
    return "\n".join(zeilen)[:grenze]


def _fristen(welt: dict, grenze: int) -> str:
    termine = welt.get("fristen") or []
    if not termine:
        return ""
    zeilen = ["NÄCHSTE TERMINE:"]
    for t in termine[:8]:
        zeilen.append(f"  {_tag(t.get('faellig'))} · {t.get('name') or t.get('art')}")
    return "\n".join(zeilen)[:grenze]


def _zahlen(welt: dict, grenze: int) -> str:
    z = welt.get("zahlen") or {}
    monate = welt.get("zahlen_monate") or {}
    if not z and not monate and not welt.get("guthaben"):
        return ""
    zeilen = []
    if z:
        zeilen.append("DIE ZAHLEN DIESES MONATS:")
        for schluessel, name in (("einnahmen", "Eingenommen (ohne Steuer)"),
                                 ("ausgaben", "Ausgegeben (ohne Steuer)"),
                                 ("ergebnis", "Bleibt")):
            if z.get(schluessel) is not None:
                zeilen.append(f"  {name}: {_euro(z[schluessel])}")
    if monate:
        zeilen.append("AUSGABEN JE MONAT (brutto, aus den Belegen):")
        for monat, m in monate.items():
            zeilen.append(f"  {monat}: {_euro(m['ausgaben_brutto'])} "
                          f"({m['belege']} Belege)")
    # Gutschriften werden selten ausgezahlt — sie werden mit der nächsten
    # Rechnung verrechnet. Wer nicht weiß, dass da noch etwas gut ist,
    # zahlt zweimal.
    guthaben = welt.get("guthaben") or []
    if guthaben:
        zeilen.append("GUTSCHRIFTEN VON LIEFERANTEN (zum Verrechnen):")
        for g in guthaben[:8]:
            teil = (f"  {g['lieferant']}: {_euro(g['guthaben'])} gutgeschrieben"
                    f" ({g['gutschriften']} "
                    + ("Gutschrift" if g["gutschriften"] == 1 else "Gutschriften")
                    + ")")
            if g["vermutlich_offen"]:
                teil += (f" — davon vermutlich noch "
                         f"{_euro(g['vermutlich_offen'])} offen")
            else:
                teil += " — seither wieder mehr bezahlt, wohl verrechnet"
            zeilen.append(teil)
    return "\n".join(zeilen)[:grenze]


def _post(welt: dict, grenze: int) -> str:
    dokumente = welt.get("dokumente") or []
    briefe = [d for d in dokumente if d.get("art") in ("behoerde", "kanzlei")]
    if not briefe:
        return ""
    zeilen = ["POST (Amt und Kanzlei):"]
    for d in briefe[:10]:
        teil = f"  {d.get('titel')}"
        erk = d.get("erklaerung") or {}
        if erk.get("einfach"):
            teil += " — " + str(erk["einfach"])[:200]
        if erk.get("bis_wann"):
            teil += f" (bis {_tag(erk['bis_wann'])})"
        if sum(len(z) for z in zeilen) + len(teil) > grenze:
            break
        zeilen.append(teil)
    return "\n".join(zeilen)


BEREICHE = {
    "beleg": _belege, "kasse": _kasse, "vertrag": _vertraege,
    "rechnung": _rechnungen, "team": _team, "frist": _fristen,
    "zahlen": _zahlen, "post": _post,
}

# Wenn die Frage kein Thema trifft, kommt trotzdem ein Überblick — in dieser
# Reihenfolge, damit auch „wie läuft es gerade?" eine Antwort bekommt.
GRUNDORDNUNG = ("zahlen", "kasse", "beleg", "rechnung", "frist", "vertrag",
                "team", "post")


def weltblock(welt: dict) -> str:
    """ALLES über diesen Salon, unabhängig von der Frage — für den
    stehenden Anfang des Chat-Prompts.

    Byte-stabil, solange sich die Box nicht ändert: dieselben Daten ergeben
    denselben Text, und der trifft bei jeder Frage den Prefix-Cache von
    vLLM. Deshalb wird hier nichts nach der Frage ausgewählt und das
    Beleg-Register steht ganz hinten, älteste zuerst — ein neuer Beleg
    verlängert den Text nur am Ende, statt ihn vorn umzusortieren."""
    teile = [_betrieb(welt)]
    for bereich in GRUNDORDNUNG:
        if bereich == "beleg":
            continue
        teile.append(BEREICHE[bereich](welt, 8000))

    belege = welt.get("belege") or []
    if belege:
        zeilen = [f"BELEG-REGISTER ({len(belege)} in der Box, älteste zuerst):"]
        for b in sorted(belege, key=lambda x: (x.get("monat") or "",
                                               x.get("datum") or "",
                                               x.get("lieferant") or "")):
            teil = (f"  {b.get('datum') or b.get('monat') or '—'} · "
                    f"{b.get('lieferant') or 'unbekannt'} · {_euro(b.get('brutto'))}"
                    f" · {b.get('belegart') or ''}")
            if b.get("konto_skr04"):
                teil += f" · Konto {b['konto_skr04']}"
            if b.get("offen"):
                teil += " · offen: " + "; ".join(str(o) for o in b["offen"][:2])
            zeilen.append(teil)
        teile.append("\n".join(zeilen))
    return "\n\n".join(t for t in teile if t) or "Zu diesem Salon ist noch nichts erfasst."


def kontext(frage: str, welt: dict, budget: int = BUDGET) -> str:
    """Das Wissen zu dieser Frage — ausgewählt, nicht abgeschnitten.

    Der Rahmen (wer ist dieser Betrieb) steht immer oben: davon hängt fast
    jede Antwort ab — ob Umsatzsteuer anfällt, welches Finanzamt zuständig
    ist, ob Rechnungen bei Ausstellung oder bei Zahlung zählen.
    """
    teile: list[str] = []
    rest = budget

    rahmen = _betrieb(welt)
    if rahmen:
        teile.append(rahmen)
        rest -= len(rahmen) + 2

    getroffen = themen(frage)
    reihenfolge = ([b for b in GRUNDORDNUNG if b in getroffen]
                   + [b for b in GRUNDORDNUNG if b not in getroffen])
    # Passende Bereiche bekommen den Löwenanteil, der Rest füllt auf.
    for i, bereich in enumerate(reihenfolge):
        if rest <= 200:
            break
        anteil = rest if i < max(1, len(getroffen)) else max(400, rest // 3)
        text = BEREICHE[bereich](welt, min(anteil, rest))
        if text:
            teile.append(text)
            rest -= len(text) + 2

    if not teile:
        return "Zu diesem Salon ist noch nichts erfasst."
    return "\n\n".join(teile)[:budget]
