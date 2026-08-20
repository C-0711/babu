"""Beispiel-Kassenbuch eines Friseursalons für einen vollen Monat.

Realistisch statt zufällig: montags zu, Samstag stark, Kartenanteil rund
60 %, Bargeld wird zur Bank gebracht, wenn die Schublade zu voll wird.
Der Kassenbestand läuft fort — der gezählte Schluss ist der Vortagsbestand
des nächsten Tages, genau wie im Papier-Kassenbericht.
"""
import calendar, json, pathlib, random, sys

JAHR, MONAT = 2026, 7
random.seed(20260701)          # reproduzierbar

# Wochentag → (Umsatz-Spanne brutto, Wahrscheinlichkeit Gutscheinverkauf)
TAGE = {
    0: None,                                  # Montag: Ruhetag
    1: ((380, 620), 0.10),                    # Dienstag
    2: ((450, 700), 0.10),                    # Mittwoch
    3: ((520, 820), 0.15),                    # Donnerstag
    4: ((700, 1050), 0.20),                   # Freitag
    5: ((900, 1450), 0.30),                   # Samstag
    6: None,                                  # Sonntag
}

blaetter = []
bestand = 180.0                               # Wechselgeld am Monatsanfang

for tag in range(1, calendar.monthrange(JAHR, MONAT)[1] + 1):
    wochentag = calendar.weekday(JAHR, MONAT, tag)
    profil = TAGE[wochentag]
    if profil is None:
        continue
    (unten, oben), gutschein_chance = profil
    umsatz = round(random.uniform(unten, oben), 2)

    # Kartenanteil schwankt um 60 %
    karte = round(umsatz * random.uniform(0.52, 0.68), 2)
    bar = round(umsatz - karte, 2)

    b = {
        "datum": f"{JAHR}-{MONAT:02d}-{tag:02d}",
        "bestandVortag": round(bestand, 2),
        "einnahmenBar": bar,
        "ecZahlungen": karte,
        "privateinlagen": 0.0,
        "barabhebungBank": 0.0,
        "gutscheineEingeloest": 0.0,
        "gutscheinVerkauf": 0.0,
        "trinkgeldTeamEC": 0.0,
        "sonstigeAusgaben": 0.0,
        "privatentnahmen": 0.0,
        "einzahlungBank": 0.0,
    }

    # Gutscheine: verkauft (Umsatz!) und gelegentlich eingelöst
    if random.random() < gutschein_chance:
        b["gutscheinVerkauf"] = float(random.choice([25, 30, 50, 50, 75, 100]))
    if random.random() < 0.12:
        b["gutscheineEingeloest"] = float(random.choice([25, 30, 50]))

    # Team-Trinkgeld, das mit Karte kam und bar ausgezahlt wird
    if random.random() < 0.45:
        b["trinkgeldTeamEC"] = round(random.uniform(5, 22), 2)

    # Kleinkram aus der Kasse
    if random.random() < 0.30:
        b["sonstigeAusgaben"] = round(random.uniform(6, 45), 2)

    # Gutscheinverkäufe werden bar bezahlt → erhöhen den Bestand
    bar_zufluss = bar + b["gutscheinVerkauf"]
    rechnerisch = (b["bestandVortag"] + bar_zufluss
                   - b["trinkgeldTeamEC"] - b["sonstigeAusgaben"])

    # Schublade zu voll? Dann geht Bargeld zur Bank.
    if rechnerisch > 900:
        b["einzahlungBank"] = float(int((rechnerisch - 300) / 50) * 50)
        rechnerisch -= b["einzahlungBank"]

    # Einmal im Monat etwas privat entnehmen
    if tag in (18,):
        b["privatentnahmen"] = 200.0
        rechnerisch -= 200.0

    # Meist stimmt die Kasse; zweimal im Monat verzählt man sich.
    if tag in (9, 23):
        differenz = round(random.uniform(-4.5, -0.5), 2)
        b["gezaehltSchluss"] = round(rechnerisch + differenz, 2)
        b["differenzGrund"] = "beim Zählen verzählt" if tag == 9 else "Wechselgeld nicht aufgegangen"
    else:
        b["gezaehltSchluss"] = round(rechnerisch, 2)

    bestand = b["gezaehltSchluss"]
    blaetter.append(b)

ziel = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
(ziel / "beispiel-kassenbuch.json").write_text(
    json.dumps(blaetter, ensure_ascii=False, indent=1))

# ————— Übersicht wie im Papier-Kassenbericht —————
print(f"Kassenbuch Juli 2026 — {len(blaetter)} Öffnungstage\n")
print(f"{'Tag':<12}{'Bar':>9}{'Karte':>9}{'Gutsch.':>9}{'Bank':>9}"
      f"{'Kasse':>10}{'':>3}")
print("-" * 62)
summe_bar = summe_karte = summe_gutschein = 0.0
for b in blaetter:
    wt = ["Mo","Di","Mi","Do","Fr","Sa","So"][calendar.weekday(
        JAHR, MONAT, int(b["datum"][-2:]))]
    marke = " ⚠" if b.get("differenzGrund") else ""
    print(f"{wt} {b['datum'][-5:]:<9}{b['einnahmenBar']:>9.2f}{b['ecZahlungen']:>9.2f}"
          f"{b['gutscheinVerkauf']:>9.2f}{b['einzahlungBank']:>9.2f}"
          f"{b['gezaehltSchluss']:>10.2f}{marke}")
    summe_bar += b["einnahmenBar"]
    summe_karte += b["ecZahlungen"]
    summe_gutschein += b["gutscheinVerkauf"]
print("-" * 62)
print(f"{'Summe':<12}{summe_bar:>9.2f}{summe_karte:>9.2f}{summe_gutschein:>9.2f}")
print(f"\nTagesumsätze gesamt: {summe_bar + summe_karte:,.2f} €"
      .replace(",", "@").replace(".", ",").replace("@", "."))
print(f"Gutscheine verkauft: {summe_gutschein:,.2f} €"
      .replace(",", "@").replace(".", ",").replace("@", "."))
