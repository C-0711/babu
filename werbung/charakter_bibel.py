"""Charakter-Bibel für den ersten Spot: Babs + Olaf, direkt in 9:16."""
import base64, json, pathlib, sys, urllib.request

key = next(z.split("=", 1)[1].strip()
           for z in pathlib.Path.home().joinpath("Youtube/.env").read_text().splitlines()
           if z.startswith("GEMINI_API_KEY="))

BABS = ("Editorial photograph, photorealistic magazine quality. A confident, "
        "cheeky hairdresser in her late twenties with wavy dark-blonde hair, "
        "beige linen shirt and patterned apron, in a bright warm cream-colored "
        "hair salon with wooden reception counter and soft natural window "
        "light. ")
MOTIVE = {
    "babs-tresen-916": BABS + (
        "She stands at the reception counter holding her smartphone in one "
        "hand, a small paper receipt on the counter, smiling slightly at the "
        "phone. Vertical 9:16 full composition, no text anywhere."),
    "babs-haken-916": BABS + (
        "She leans casually on the counter and holds her smartphone up "
        "towards the camera, the screen glowing with a soft green circular "
        "checkmark, smirking proudly with one raised eyebrow. "
        "Vertical 9:16, no text anywhere."),
    "olaf-buero-916": (
        "Editorial photograph, photorealistic with a slight caricature-like "
        "exaggeration. A smug, wealthy tax advisor in his late fifties, "
        "slicked-back grey hair, pinstripe three-piece suit with gold watch "
        "and pocket square, leaning back in a green leather chair in a dark "
        "mahogany office. Towering stacks of paper invoices and thick binders "
        "on the desk, warm banker's lamp, dust in the light beam. He fans out "
        "several paper invoices like playing cards and grins greedily. "
        "Fictional character. Vertical 9:16, no text anywhere."),
}
ziel = pathlib.Path(sys.argv[1])
url = ("https://generativelanguage.googleapis.com/v1beta/models/"
       "gemini-3-pro-image:generateContent?key=" + key)
for name, prompt in MOTIVE.items():
    req = urllib.request.Request(url, method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"aspectRatio": "9:16"}},
        }).encode())
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            antwort = json.load(r)
        teile = antwort["candidates"][0]["content"]["parts"]
        daten = next(t["inlineData"]["data"] for t in teile if "inlineData" in t)
        (ziel / f"{name}.png").write_bytes(base64.b64decode(daten))
        print(f"{name}: {(ziel / (name + '.png')).stat().st_size // 1024} KB")
    except Exception as e:
        print(f"{name} fehlgeschlagen: {type(e).__name__}: {e}")
