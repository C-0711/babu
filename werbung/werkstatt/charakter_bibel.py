"""Charakter-Bibel für babu Werkstatt: Mario und seine Werkstatt — Kopie von
`werbung/barber/charakter_bibel.py` (Moe), angepasst.

Mario ist Kfz-Meister, Deutsch-Serbe aus dem Schwäbischen. Nano Banana 2
(`gemini-3-pro-image`): erst sein Porträt, danach jedes Motiv MIT dem Porträt
als Referenz. Regeln wie bei Babs und Moe: immer Menschen im Bild, fiktive
Figur, kein Text, keine Markenlogos, keine Kennzeichen, KEINE generierten
App-Bildschirme.

    python3 werbung/werkstatt/charakter_bibel.py <zielordner> [motiv …]
"""
from __future__ import annotations

import base64, json, pathlib, sys, urllib.request

key = next(z.split("=", 1)[1].strip()
           for z in pathlib.Path.home().joinpath("Youtube/.env").read_text().splitlines()
           if z.startswith("GEMINI_API_KEY="))
URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
       "gemini-3-pro-image:generateContent?key=" + key)

MARIO = ("Editorial photograph, photorealistic magazine quality, shot on a full-frame "
         "camera, rich natural colour. Mario, a warm, confident German-Serbian master car "
         "mechanic from Swabia in his early forties: short dark hair with a little grey at "
         "the temples, neatly trimmed dark stubble beard, strong forearms, friendly laugh "
         "lines, a relaxed grin. Dark navy work jacket with the sleeves pushed up over a grey "
         "t-shirt, navy work trousers, a clean red shop rag in the back pocket. Fictional character. ")
WERKSTATT = ("His independent car repair workshop in a small Swabian town: clean and well "
             "organised, a silver hatchback raised on a two-post lift, a red rolling tool chest, "
             "a pegboard wall of neatly hung tools, a diagnostic laptop on a stand, light grey "
             "epoxy floor, a wide open roller door with warm afternoon light and green vineyard "
             "hills outside, a small wooden counter with a copper džezva coffee pot and two "
             "small coffee cups. Cars without any brand logos and without licence plates. ")
KEIN_TEXT = (" Only plain unlabeled bottles and cans. No text, no letters, no logos, no brand "
             "marks, no licence plates, no signage anywhere in the image.")

MOTIVE = {
    "mario-portrait-916": ("9:16", MARIO + WERKSTATT +
        "He stands in front of the car on the lift, arms relaxed, looking into the camera "
        "with calm pride. Vertical full composition." + KEIN_TEXT, False),
}


def erzeugen(name, verhaeltnis, prompt, referenz: bytes | None) -> bytes:
    teile = [{"text": prompt}]
    if referenz is not None:
        teile.insert(0, {"inlineData": {"mimeType": "image/png",
                                        "data": base64.b64encode(referenz).decode()}})
        teile[1]["text"] = ("The man in the reference image is Mario — keep his face, "
                            "hair, beard and outfit exactly. " + prompt)
    body = {"contents": [{"parts": teile}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"aspectRatio": verhaeltnis, "imageSize": "2K"}}}
    req = urllib.request.Request(URL, method="POST", headers={"Content-Type": "application/json"},
                                 data=json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=240) as r:
        antwort = json.load(r)
    t = antwort["candidates"][0]["content"]["parts"]
    return base64.b64decode(next(x["inlineData"]["data"] for x in t if "inlineData" in x))


def main():
    ziel = pathlib.Path(sys.argv[1]); ziel.mkdir(parents=True, exist_ok=True)
    portrait = ziel / "mario-portrait-916.png"
    for name in sys.argv[2:] or list(MOTIVE):
        verh, prompt, mit_ref = MOTIVE[name]
        datei = ziel / f"{name}.png"
        if datei.exists():
            print(f"{name}: liegt schon da"); continue
        try:
            ref = portrait.read_bytes() if mit_ref and portrait.exists() else None
            datei.write_bytes(erzeugen(name, verh, prompt, ref))
            print(f"{name}: {datei.stat().st_size // 1024} KB")
        except Exception as e:  # noqa: BLE001 — nie den Schlüssel ausgeben
            print(f"{name} fehlgeschlagen: {type(e).__name__}")


if __name__ == "__main__":
    main()
