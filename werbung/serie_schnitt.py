"""Serie schneiden: je Folge Olaf + Babs + Claim, Untertitel, Endcard."""
import pathlib, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

SP = pathlib.Path(__file__).parent
sys.path.insert(0, str(SP))
from serie import FOLGEN  # noqa: E402

CLAIM_TEXT = "Mein grüner Haken ist grüner als deiner."
TITEL = {
    "angebot": "Kein Angebot, nur eine Rechnung",
    "reden": "Reden kostet",
    "kleinvieh": "Die Kleinigkeiten",
    "leistung": "Keine Leistungsübersicht",
    "verschlampt": "Beleg verschlampt — zweimal bezahlt",
    "doppelt": "Doppelt abgerechnet",
    "vorarbeit": "Vorarbeit umsonst",
    "frist": "Frist verpasst — Zuschlag zahlst du",
    "spaet": "Zahlen kommen zu spät",
    "wechsel": "Der Wechsel wird zäh gemacht",
}


def font(groesse):
    for pfad in ("/System/Library/Fonts/Helvetica.ttc",
                 "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(pfad, groesse)
        except OSError:
            continue
    return ImageFont.load_default(groesse)


def umbrechen(text, f, zeichner, breite):
    zeilen, aktuell = [], ""
    for wort in text.split():
        probe = (aktuell + " " + wort).strip()
        if zeichner.textlength(probe, font=f) <= breite:
            aktuell = probe
        else:
            if aktuell:
                zeilen.append(aktuell)
            aktuell = wort
    if aktuell:
        zeilen.append(aktuell)
    return zeilen


def untertitel(text, ziel):
    f = font(34)
    img = Image.new("RGBA", (720, 1280), (0, 0, 0, 0))
    z = ImageDraw.Draw(img)
    zeilen = umbrechen(text, f, z, 620)
    y = 1280 - 90 - (len(zeilen) - 1) * 46
    for zeile in zeilen:
        w = z.textlength(zeile, font=f)
        x = (720 - w) / 2
        z.rounded_rectangle((x - 14, y - 8, x + w + 14, y + 44), 10, fill=(0, 0, 0, 150))
        z.text((x, y), zeile, font=f, fill=(255, 255, 255, 255))
        y += 46
    img.save(ziel)


def schneide(kurz, o_text, b_text):
    ziel = SP / f"spot-{kurz}.mp4"
    takes = [SP / f"s-{kurz}-olaf.mp4", SP / f"s-{kurz}-babs.mp4", SP / "claim-haken.mp4"]
    if not all(t.exists() for t in takes):
        print(f"{kurz}: Takes fehlen — übersprungen")
        return False
    for i, text in enumerate((o_text, b_text, CLAIM_TEXT)):
        untertitel(text, SP / f"u-{kurz}-{i}.png")
    roh = SP / f"roh-{kurz}.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(takes[0]), "-i", str(takes[1]), "-i", str(takes[2]),
        "-loop", "1", "-t", "3.5", "-i", str(SP / "endcard.png"),
        "-f", "lavfi", "-t", "3.5", "-i", "anullsrc=r=48000:cl=stereo",
        "-filter_complex",
        "[0:v]scale=720:1280,setsar=1,fps=24[v0];"
        "[1:v]scale=720:1280,setsar=1,fps=24[v1];"
        "[2:v]scale=720:1280,setsar=1,fps=24[v2];"
        "[3:v]scale=720:1280,setsar=1,fps=24,format=yuv420p[v3];"
        "[v0][0:a][v1][1:a][v2][2:a][v3][4:a]concat=n=4:v=1:a=1[vc][ac]",
        "-map", "[vc]", "-map", "[ac]", "-c:v", "libx264", "-preset", "medium",
        "-crf", "20", "-c:a", "aac", "-b:a", "160k", str(roh)], check=True)
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(roh),
        "-i", str(SP / f"u-{kurz}-0.png"), "-i", str(SP / f"u-{kurz}-1.png"),
        "-i", str(SP / f"u-{kurz}-2.png"),
        "-filter_complex",
        "[0:v][1:v]overlay=0:0:enable='between(t,0.4,7.6)'[a];"
        "[a][2:v]overlay=0:0:enable='between(t,8.4,15.6)'[b];"
        "[b][3:v]overlay=0:0:enable='between(t,16.4,23.6)'[c]",
        "-map", "[c]", "-map", "0:a", "-c:v", "libx264", "-preset", "medium",
        "-crf", "20", "-c:a", "copy", str(ziel)], check=True)
    roh.unlink()
    print(f"spot-{kurz}.mp4: {ziel.stat().st_size // 1024} KB — {TITEL[kurz]}")
    return True


if __name__ == "__main__":
    fertig = 0
    for kurz, _, o_text, _, _, b_text in FOLGEN:
        if schneide(kurz, o_text, b_text):
            fertig += 1
    print(f"{fertig} von {len(FOLGEN)} Spots geschnitten")
