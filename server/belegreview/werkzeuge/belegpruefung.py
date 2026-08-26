#!/usr/bin/env python3
"""Die Belegprüfung — jeden Beleg der Box gegen die Profil-Einschätzung
halten: richtig / falsch / fraglich / offen, mit Fremdwährungs- und
Nullbetrags-Prüfung. Liest /tmp/durchlauf_ergebnis.jsonl (Einschätzungs-
lauf) und /tmp/lesungen.jsonl; trägt ein Review eine eigene buchung,
ist SIE der Maßstab. Ausgabe: JSON-Liste für die Prüfseite.
"""

import json, glob, os, re

gemma = {}
for z in open("/tmp/durchlauf_ergebnis.jsonl"):
    d = json.loads(z)
    gemma[d["stamm"]] = d

lesungen = {json.loads(z)["stamm"]: json.loads(z)["zeilen"]
            for z in open("/tmp/lesungen.jsonl")}

WAEHRUNG = re.compile(r"\b(AED|CHF|USD|GBP|CZK|PLN)\b")
aus = []
for f in sorted(glob.glob(os.path.expanduser("~/babu-web/box/review/*beleg_*.json"))):
    if "embedding" in f or "angaben" in f or "korrektur" in f or "bewirtung" in f:
        continue
    stamm = os.path.basename(f)[:-5]
    d = json.load(open(f))
    fl = d.get("felder") or {}
    e = d.get("einschaetzung") or {}
    g = gemma.get(stamm) or {}
    zeilen = lesungen.get(stamm) or []
    fremd = None
    for z in zeilen:
        if "€" in z or " EUR" in z.upper():
            fremd = None; break
        m = WAEHRUNG.search(z.upper())
        if m and any(c.isdigit() for c in z):
            fremd = m.group(1)
    # Nach dem Heillauf: trägt das Review eine eigene Buchung, ist SIE der
    # Maßstab — der alte Prüflauf ist dann Geschichte.
    rb = d.get("buchung") or {}
    if rb.get("status") == "gebucht":
        g = {"status": "gebucht", "buchung": rb["buchung"]}
    elif rb.get("status") in ("fragen", "aufgeben"):
        g = rb
    ist_konto = e.get("konto") or e.get("konto_skr04")
    ist_kat = e.get("kategorie") or (e.get("belegart") or "").split(" (")[0]
    urteil, grund, soll = "offen", "", ""
    gb = (g.get("buchung") or {}) if g.get("status") == "gebucht" else {}
    if g.get("status") == "gebucht":
        soll = f'{gb.get("kategorie_name")} ({gb.get("konto")})'
        if fremd and not gb.get("waehrung", "EUR") != "EUR":
            pass
        if str(ist_konto) == str(gb.get("konto")):
            urteil = "richtig"
        else:
            urteil, grund = "falsch", f'gebucht {ist_kat or ist_konto or "—"}, richtig wäre {gb.get("kategorie_name")}'
    elif g.get("status") == "fragen":
        urteil = "offen"
        grund = (g.get("fragen") or [{}])[0].get("frage", "")[:90]
        if ist_konto:  # still gebucht, obwohl die Buchhaltung fragen würde
            urteil, grund = "fraglich", f'still auf {ist_kat or ist_konto} gebucht — Buchhaltung würde fragen: {grund}'
    # Harte Fehler übersteuern
    if fremd and (fl.get("brutto") or 0) > 0 and not gb.get("betrag_eur"):
        urteil, grund = "falsch", f'{fremd}-Beleg als Euro geführt ({fl.get("brutto")} €)'
    elif fremd and gb and gb.get("waehrung") == fremd:
        grund = (grund + f' · {gb.get("betrag")} {fremd} ≈ {gb.get("betrag_eur")} €').strip(" ·")
    if not fl.get("brutto"):
        urteil, grund = "falsch", "Betrag fehlt/0 — nicht buchbar gelesen"
    aus.append({
        "stamm": stamm, "datum": fl.get("datum"),
        "lieferant": (gb.get("lieferant") or fl.get("lieferant") or "?"),
        "brutto": fl.get("brutto"), "fremd": fremd,
        "ist": f'{ist_kat or "—"}' + (f' ({ist_konto})' if ist_konto else ""),
        "soll": soll, "urteil": urteil, "grund": grund,
    })
print(json.dumps(aus, ensure_ascii=False))
