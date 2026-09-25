"""Die Bilder der Werkstatt-Seite — Kopie der 17 Szenenfotos der Friseur-Seite
(und von `werbung/barber/seitenbilder.py`), mit Mario. Dazu das Heldenbild
für den Hero (`ws-held`, 16:9).

Nano Banana 2 mit Marios Porträt als Referenz (`charakter_bibel.py` zuerst).
Format wie bei Friseur: 692 × 859 JPG, zugeschnitten, nie gestaucht.
Dateinamen `ws-…` für /bilder/{name}. Nie generierte App-Bildschirme.

    python3 werbung/werkstatt/seitenbilder.py <ordner-mit-mario-portrait> [motiv …]
"""
from __future__ import annotations

import pathlib, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from charakter_bibel import KEIN_TEXT, MARIO, WERKSTATT, erzeugen  # noqa: E402

TEL = " The phone screen faces away from the camera or only glows softly; no interface visible."

MOTIVE = {  # Name: Gegenstück auf der Friseur-Seite → Prompt
    # „So fängst du an."
    "ws-start-1-laden": "In the morning Mario sits on a stack of tyres in his workshop and sets something up on his phone, a small coffee cup beside him." + TEL,
    "ws-start-2-anmelden": "Mario stands at the small wooden counter and quickly types something into his phone with his thumb." + TEL,
    "ws-start-3-foto": "Close-up from above: Mario's slightly oil-marked hands hold a phone over a small paper receipt on the workbench and photograph it; only hands, phone and receipt in frame." + TEL,
    "ws-start-4-fertig": "After closing, Mario leans relaxed against the closed roller door inside his tidy workshop, his phone lies on the workbench, a satisfied calm look.",
    # „Und das kann babu dann alles."
    "ws-kann-termine": "Between two jobs Mario glances at his phone, a torque wrench in the other hand, a customer waits at the counter in the background." + TEL,
    "ws-kann-nachricht": "Mario sits on the edge of the workbench and reads a message on his phone with an amused smile." + TEL,
    "ws-kann-belege": "An overturned shoebox on the counter with a pile of paper receipts spilling out, Mario's hand reaches in and holds his phone next to it, slightly exasperated but smiling.",
    "ws-kann-kunde": "Under the car on the lift Mario shows a customer a worn brake disc in his hand, both look at it; his phone stands propped up on the red tool chest." + TEL,
    "ws-kann-rechnung": "Mario leans on the counter and types something into his phone with concentration, in the background a customer takes his car keys from a key board." + TEL,
    "ws-kann-kasse": "In the evening under a work lamp Mario counts banknotes and coins at the counter, his phone lies next to the cash." + TEL,
    # „Wirf uns deinen Papierstapel hin."
    "ws-papierstapel": "Mario carries a huge stack of folders, envelopes and receipts from last year in both arms, laughing a little at the sheer amount.",
    # „Dein Telefon kann das jetzt alles."
    "ws-scanner": "Mario photographs a receipt at the counter with his phone, two customers wait on chairs in the background." + TEL,
    "ws-helfer": "After closing Mario leans relaxed on the workbench and looks satisfied at his phone, a small cup of coffee beside him." + TEL,
    "ws-berater": "Mario photographs an official letter lying in front of him on the counter, with an amused, slightly skeptical expression.",
    # „Dein ganzer Laden passt in die Hosentasche."
    "ws-termine-morgens": "Early morning before opening: Mario stands at the counter, a small coffee cup in one hand, his phone in the other, the roller door half open, the first car already on the lift." + TEL,
    "ws-rechnung-tresen": "Mario hands a smiling customer a sheet of paper and the car keys across the counter, both relaxed and friendly.",
    "ws-feierabend-zahlen": "After closing Mario sits relaxed on a rolling stool in the tidy workshop and looks at his phone, content." + TEL,
}
HELD = ("ws-held", "Wide shot: Mario laughs together with a regular customer next to the car on the lift, "
        "both hold small coffee cups from the copper džezva, an apprentice works on the wheel in the "
        "background out of focus. Horizontal cinematic composition.")


def main():
    ordner = pathlib.Path(sys.argv[1])
    portrait = (ordner / "mario-portrait-916.png").read_bytes()
    for name in sys.argv[2:] or [HELD[0], *MOTIVE]:
        jpg = ordner / f"{name}.jpg"
        if jpg.exists():
            print(f"{name}: liegt schon da"); continue
        png = ordner / f"{name}.png"
        try:
            if name == HELD[0]:
                png.write_bytes(erzeugen(name, "16:9", MARIO + WERKSTATT + HELD[1] + KEIN_TEXT, portrait))
                subprocess.run(["sips", "--resampleWidth", "1600", "-s", "format", "jpeg",
                                "-s", "formatOptions", "82", str(png), "--out", str(jpg)], check=True, capture_output=True)
            else:
                png.write_bytes(erzeugen(name, "4:5", MARIO + WERKSTATT + MOTIVE[name] + KEIN_TEXT, portrait))
                subprocess.run(["sips", "--resampleWidth", "692", str(png), "--out", str(png)], check=True, capture_output=True)
                subprocess.run(["sips", "--cropToHeightWidth", "859", "692", "-s", "format", "jpeg",
                                "-s", "formatOptions", "82", str(png), "--out", str(jpg)], check=True, capture_output=True)
            print(f"{name}: {jpg.stat().st_size // 1024} KB", flush=True)
        except Exception as e:  # noqa: BLE001 — nie den Schlüssel ausgeben
            print(f"{name} fehlgeschlagen: {type(e).__name__}", flush=True)


if __name__ == "__main__":
    main()
