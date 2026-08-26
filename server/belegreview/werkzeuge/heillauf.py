#!/usr/bin/env python3
"""Der Sammel-Heillauf — Altbestand frisch einschätzen und eindeutige Fälle
im Review korrigieren (ein boxschreiber-Commit). Gelaufen am 25.08.2026:
45 von 76 Kandidaten geheilt.

Bedienung (auf der H200V):
  1. /tmp/lesungen.jsonl:      je Zeile {"stamm": ..., "zeilen": [...]}
     (Vision- oder Protokoll-Zeilen je Beleg)
  2. /tmp/heil_staemme.json:   Liste der Stämme, die geheilt werden sollen
  3. python3 heillauf.py       — Frage-Fälle bleiben unangetastet.
"""

import json, sys, time, urllib.request

sys.path.insert(0, "/home/christoph.bertsch/belegreview")
import boxschreiber
import gemma_buchung as gb

PAT = open("/home/christoph.bertsch/gitchain-eingang/.pat_babu").read().strip()
staemme = json.load(open("/tmp/heil_staemme.json"))
lesungen = {json.loads(z)["stamm"]: json.loads(z)["zeilen"]
            for z in open("/tmp/lesungen.jsonl")}

geheilt, fragen, uebersprungen = [], [], []
neue_dateien = {}
for stamm in staemme:
    zeilen = lesungen.get(stamm)
    pfad = f"/home/christoph.bertsch/babu-web/box/review/{stamm}.json"
    try:
        review = json.load(open(pfad))
    except Exception:
        uebersprungen.append((stamm, "kein Review")); continue
    if not zeilen:
        uebersprungen.append((stamm, "keine Lesung")); continue
    datum = (review.get("felder") or {}).get("datum") or ""
    koerper = {"zeilen": zeilen}
    if len(datum) >= 7:
        koerper["monat"] = datum[:7]
    req = urllib.request.Request(
        "http://127.0.0.1:7844/api/buchung/einschaetzung",
        json.dumps(koerper).encode(),
        {"Content-Type": "application/json", "Authorization": f"Bearer {PAT}"})
    try:
        with urllib.request.urlopen(req, timeout=240) as a:
            e = json.load(a)
    except Exception as ex:
        uebersprungen.append((stamm, repr(ex)[:60])); continue
    if e.get("status") == "gebucht" and not gb.gemischt(e["buchung"]):
        b = e["buchung"]
        review["buchung"] = e
        ein = review.setdefault("einschaetzung", {})
        ein["kategorie"] = b["kategorie"]
        ein["konto"] = b["konto"]
        if ein.get("kontenrahmen", "SKR04") == "SKR04":
            ein["konto_skr04"] = b["konto"]
        ein["belegart"] = b["kategorie_name"]
        ein["steuerschluessel"] = ("8" if b["ust_satz"] == 7
                                   else "0" if b["ust_satz"] == 0 else "9")
        ein["kontierung_grund"] = ("Heillauf 25.08.2026: neu gebucht von der "
                                   "Buchhaltung — " + (b.get("begruendung") or "")[:160])
        ein["rueckfrage"] = None
        neue_dateien[f"review/{stamm}.json"] = json.dumps(
            review, ensure_ascii=False, indent=1).encode()
        geheilt.append((stamm, b["kategorie_name"], b["konto"],
                        b.get("betrag_eur"), b.get("waehrung")))
    else:
        f1 = (e.get("fragen") or [{}])[0].get("frage", e.get("hinweis", ""))
        fragen.append((stamm, f1[:90]))
    time.sleep(0.2)

if neue_dateien:
    commit = boxschreiber.schreiben(
        neue_dateien, None,
        f"heillauf: {len(neue_dateien)} Belege neu gebucht (Buchhaltung mit Profil)",
        "christoph0711.io")
    print("COMMIT", commit)
print(f"GEHEILT {len(geheilt)} · FRAGEN {len(fragen)} · UEBERSPRUNGEN {len(uebersprungen)}")
for s, kat, konto, eur, w in geheilt:
    print(f"  ✓ {s[-44:]}: {kat} ({konto})" + (f" · {eur} € [{w}]" if w and w != "EUR" else ""))
for s, f1 in fragen:
    print(f"  ? {s[-44:]}: {f1}")
for s, g in uebersprungen:
    print(f"  – {s[-44:]}: {g}")
