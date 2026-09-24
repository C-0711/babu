"""Die Bilder der Barber-Seite — Kopie der 17 Szenenfotos der Friseur-Seite
(`server/babu-web/index.html`, /bilder/start-*, kann-*, …), mit Moe.

Nano Banana 2 mit Moes Porträt als Referenz (`charakter_bibel.py` zuerst
laufen lassen). Format wie bei Friseur: 692 × 859 JPG, zugeschnitten, nie
gestaucht (Fehler vom 22.08.2026: „in die Länge gezogen"). Dateinamen `ba-…`,
passend zu /bilder/{name} (höchstens 40 Zeichen, a–z, 0–9, Bindestrich).
App-Bildschirme werden NIE generiert — die kommen als echte Aufnahmen.

    python3 werbung/barber/seitenbilder.py <ordner-mit-moe-portrait> [motiv …]
"""
from __future__ import annotations

import pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from charakter_bibel import KEIN_TEXT, MOE, SHOP, erzeugen  # noqa: E402

TEL = " The phone screen faces away from the camera or only glows softly; no interface visible."

MOTIVE = {  # Name: Gegenstück auf der Friseur-Seite → Prompt
    # „So fängst du an."
    "ba-start-1-laden": "Moe sits relaxed on the waiting bench of his shop in the morning and sets something up on his phone, a tea glass beside him." + TEL,
    "ba-start-2-anmelden": "Moe stands at the reception counter and quickly types something into his phone with his thumb." + TEL,
    "ba-start-3-foto": "Close-up from above: Moe's hands hold a phone over a small paper receipt on the wooden counter and photograph it; only hands, phone and receipt in frame." + TEL,
    "ba-start-4-fertig": "After closing, Moe leans relaxed against the brick wall of his empty, tidy shop, his phone lies on the shelf beside him, a satisfied calm look.",
    # „Und das kann babu dann alles."
    "ba-kann-termine": "Between two customers Moe glances at his phone, a clipper in the other hand, the next customer waits on the bench in the background." + TEL,
    "ba-kann-nachricht": "Moe sits on the armrest of the waiting bench and reads a message on his phone with an amused smile." + TEL,
    "ba-kann-belege": "An overturned shoebox on the counter with a pile of paper receipts spilling out, Moe's hand reaches in and holds his phone next to it, slightly exasperated but smiling.",
    "ba-kann-kundin": "Moe prepares a hot towel and shaving foam for a regular customer, his phone stands propped up in front of him on the counter." + TEL,
    "ba-kann-rechnung": "Moe leans on the counter and types something into his phone with concentration, in the background a customer puts on his jacket." + TEL,
    "ba-kann-kasse": "In the evening under the brass lamp Moe counts banknotes and coins behind the counter, his phone lies next to the cash." + TEL,
    # „Wirf uns deinen Papierstapel hin."
    "ba-papierstapel": "Moe carries a huge stack of folders, envelopes and receipts from last year in both arms, laughing a little at the sheer amount.",
    # „Dein Telefon kann das jetzt alles."
    "ba-scanner": "Moe photographs a receipt at the reception counter with his phone, two customers wait on the bench in the background." + TEL,
    "ba-helfer": "After closing Moe leans relaxed on the counter and looks satisfied at his phone, a fresh glass of tea beside him." + TEL,
    "ba-berater": "Moe photographs an official letter lying in front of him on the counter, with an amused, slightly skeptical expression." + TEL,
    # „Dein ganzer Laden passt in die Hosentasche."
    "ba-termine-morgens": "Early morning before opening: Moe stands at the counter, a glass of tea in one hand, his phone in the other, the chairs still empty." + TEL,
    "ba-rechnung-tresen": "Moe hands a smiling customer a sheet of paper across the reception counter, both relaxed and friendly.",
    "ba-feierabend-zahlen": "After closing Moe sits relaxed in his own barber chair in the tidy shop and looks at his phone, content." + TEL,
}


def main():
    ordner = pathlib.Path(sys.argv[1])
    portrait = (ordner / "moe-portrait-916.png").read_bytes()
    for name in sys.argv[2:] or list(MOTIVE):
        jpg = ordner / f"{name}.jpg"
        if jpg.exists():
            print(f"{name}: liegt schon da"); continue
        png = ordner / f"{name}.png"
        try:
            png.write_bytes(erzeugen(name, "4:5", MOE + SHOP + MOTIVE[name] + KEIN_TEXT, portrait))
            subprocess.run(["sips", "--resampleWidth", "692", str(png), "--out", str(png)], check=True, capture_output=True)
            subprocess.run(["sips", "--cropToHeightWidth", "859", "692", "-s", "format", "jpeg",
                            "-s", "formatOptions", "82", str(png), "--out", str(jpg)], check=True, capture_output=True)
            print(f"{name}: {jpg.stat().st_size // 1024} KB", flush=True)
        except Exception as e:  # noqa: BLE001 — nie den Schlüssel ausgeben
            print(f"{name} fehlgeschlagen: {type(e).__name__}", flush=True)


if __name__ == "__main__":
    main()
