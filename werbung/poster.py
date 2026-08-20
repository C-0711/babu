"""Startbilder für die Spot-Serie: Szene + Titel + erklärender Satz."""
import pathlib, subprocess
from PIL import Image, ImageDraw, ImageFilter

SP = pathlib.Path(__file__).parent

# kurz: (Sekunde im Olaf-Take, Titel, erklärender Satz)
POSTER = {
    "angebot":     (3.0, "Kein Angebot,\nnur eine Rechnung", "Den Preis erfährst du erst hinterher."),
    "reden":       (3.0, "Reden kostet", "Jede Rückfrage wird als Zeit berechnet."),
    "kleinvieh":   (3.5, "Porto, Kopien,\nPauschale", "Lauter Kleinposten, keiner vorher genannt."),
    "leistung":    (3.0, "Paragraf statt\nLeistung", "Auf der Rechnung steht nicht, was getan wurde."),
    "verschlampt": (3.0, "Beleg weg —\nzweimal bezahlt", "Fremder Fehler, deine Rechnung."),
    "doppelt":     (3.0, "Doppelt\nabgerechnet", "Ohne eigene Aufzeichnung nicht widerlegbar."),
    "vorarbeit":   (3.0, "Vorarbeit\numsonst", "Du sortierst — der Preis bleibt gleich."),
    "frist":       (3.0, "Frist verpasst,\nZuschlag zahlst du", "Das Amt schickt ihn an dich."),
    "spaet":       (3.0, "Zahlen kommen\nzu spät", "Im August erfahren, wie der März lief."),
    "wechsel":     (3.0, "Der Wechsel wird\nzäh gemacht", "Offene Honorare, zurückgehaltene Unterlagen."),
}

def font(groesse, fett=True):
    pfade = ["/System/Library/Fonts/Supplemental/Georgia Bold.ttf"] if fett else []
    pfade += ["/System/Library/Fonts/Helvetica.ttc"]
    from PIL import ImageFont
    for p in pfade:
        try:
            return ImageFont.truetype(p, groesse)
        except OSError:
            continue
    return ImageFont.load_default(groesse)

for kurz, (sek, titel, satz) in POSTER.items():
    quelle = SP / f"s-{kurz}-olaf.mp4"
    roh = SP / f"pf-{kurz}.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(sek), "-i", str(quelle),
                    "-frames:v", "1", str(roh)], check=True)
    bild = Image.open(roh).convert("RGB").resize((720, 1280), Image.LANCZOS)

    # Szene beruhigen: leicht weichzeichnen und abdunkeln, damit Text trägt.
    bild = bild.filter(ImageFilter.GaussianBlur(1.2))
    dunkel = Image.new("RGBA", (720, 1280), (0, 0, 0, 0))
    z = ImageDraw.Draw(dunkel)
    for y in range(1280):
        # oben leicht, unten kräftig — der Text sitzt unten
        a = int(40 + 165 * max(0, (y - 430) / 850) ** 1.3)
        z.line([(0, y), (720, y)], fill=(15, 14, 12, min(a, 215)))
    bild = Image.alpha_composite(bild.convert("RGBA"), dunkel)
    z = ImageDraw.Draw(bild)

    # Kopfzeile
    f_marke = font(30)
    z.text((44, 52), "babu", font=f_marke, fill=(255, 255, 255, 235))
    f_lbl = font(19, fett=False)
    z.text((44, 96), "KOSTENWAHRHEIT", font=f_lbl, fill=(200, 194, 180, 220))

    # Play-Kreis — halbtransparent nur über eine eigene Ebene, sonst wird
    # der Alpha-Wert beim RGB-Export zu deckendem Weiß.
    mx, my, r = 360, 610, 58
    spiel = Image.new("RGBA", (720, 1280), (0, 0, 0, 0))
    zs = ImageDraw.Draw(spiel)
    zs.ellipse((mx - r, my - r, mx + r, my + r), fill=(255, 255, 255, 40),
               outline=(255, 255, 255, 205), width=3)
    zs.polygon([(mx - 16, my - 25), (mx - 16, my + 25), (mx + 26, my)],
               fill=(255, 255, 255, 235))
    bild = Image.alpha_composite(bild, spiel)
    z = ImageDraw.Draw(bild)

    # Titel + Erklärsatz
    f_titel = font(54)
    y = 880
    for zeile in titel.split("\n"):
        z.text((44, y), zeile, font=f_titel, fill=(255, 255, 255, 245))
        y += 66
    f_satz = font(27, fett=False)
    z.text((44, y + 16), satz, font=f_satz, fill=(226, 221, 210, 235))

    # Grüner Haken als Absender
    hx, hy, hr = 62, 1180, 20
    z.ellipse((hx - hr, hy - hr, hx + hr, hy + hr), fill=(111, 138, 110, 255))
    z.line([(hx - 9, hy + 1), (hx - 3, hy + 8)], fill=(255, 255, 255), width=4)
    z.line([(hx - 3, hy + 8), (hx + 10, hy - 7)], fill=(255, 255, 255), width=4)
    z.text((hx + 34, hy - 14), "babu.0711.io", font=f_satz, fill=(235, 231, 222, 230))

    ziel = SP / f"poster-{kurz}.png"
    bild.convert("RGB").save(ziel, quality=88)
    roh.unlink()
    print(f"{ziel.name}: {ziel.stat().st_size // 1024} KB")
