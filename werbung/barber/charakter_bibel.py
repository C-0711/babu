"""Charakter-Bibel für babu Barber: Moe und sein Shop — Kopie von
`werbung/charakter_bibel.py` (Babs/Olaf), angepasst.

Nano Banana 2 (`gemini-3-pro-image`). Erst Moes Porträt, danach jedes weitere
Motiv MIT diesem Porträt als Referenz — so bleibt Moe in allen Bildern
derselbe Mann. Regeln wie bei Babs: immer Menschen im Bild, fiktive Figur,
kein Text im Bild, KEINE generierten App-Bildschirme (der grüne Haken ist ein
Lichtschein auf dem Telefon, keine Oberfläche).

    python3 werbung/barber/charakter_bibel.py <zielordner> [motiv …]
"""
from __future__ import annotations

import base64, json, pathlib, sys, urllib.request

key = next(z.split("=", 1)[1].strip()
           for z in pathlib.Path.home().joinpath("Youtube/.env").read_text().splitlines()
           if z.startswith("GEMINI_API_KEY="))
URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
       "gemini-3-pro-image:generateContent?key=" + key)

MOE = ("Editorial photograph, photorealistic magazine quality, shot on a full-frame "
       "camera with an 85mm lens, shallow depth of field, rich natural colour. "
       "Moe, a confident, warm Turkish-German master barber in his early thirties: "
       "short dark hair with a crisp skin fade, a well-groomed full beard with a "
       "razor-sharp line-up, kind dark eyes, a subtle smile. Black shirt with sleeves "
       "rolled up, a dark brown leather barber apron, a thin silver chain. "
       "Fictional character. ")
SHOP = ("His barbershop: dark walnut wood, warm brass lamps, a vintage cognac leather "
        "barber chair, exposed brick wall, a large mirror with a brass frame, neatly "
        "arranged clippers, combs and glass bottles, a small tulip-shaped glass of "
        "Turkish tea on the counter. Warm golden evening light, dust in the light "
        "beam. ")
KEIN_TEXT = " No text, no letters, no logos, no signage anywhere in the image."

MOTIVE = {
    # (Seitenverhältnis, Prompt, braucht Referenz)
    "moe-portrait-916": ("9:16", MOE + SHOP +
        "He stands in front of his barber chair, arms relaxed, looking into the "
        "camera with calm pride. Vertical full composition." + KEIN_TEXT, False),
    "moe-fade-916": ("9:16", MOE + SHOP +
        "He concentrates on a precise skin fade on a young client in the chair, "
        "clipper in one hand, comb in the other, fine hair in the light. The "
        "client is seen from the side, relaxed." + KEIN_TEXT, True),
    "moe-rasur-916": ("9:16", MOE + SHOP +
        "Classic hot-towel shave: he holds a straight razor with steady hands at "
        "the cheek of a reclining client, soft steam rising, white foam, "
        "a quiet, almost ceremonial moment." + KEIN_TEXT, True),
    "moe-tresen-916": ("9:16", MOE + SHOP +
        "At the wooden reception counter he holds his smartphone flat above a small "
        "paper receipt and takes a photo of it, the phone screen faces away from the "
        "camera. A cash drawer and the tea glass beside him." + KEIN_TEXT, True),
    "moe-haken-916": ("9:16", MOE + SHOP +
        "He leans on the counter and holds his smartphone towards the camera; the "
        "screen only glows with a soft green circular light, no interface visible. "
        "He smirks, satisfied, one eyebrow raised." + KEIN_TEXT, True),
    "moe-lachen-169": ("16:9", MOE + SHOP +
        "Wide shot: Moe and a regular customer in the chair laugh together at "
        "something, the customer holds a tulip glass of Turkish tea, a second barber "
        "works in the background out of focus. Horizontal cinematic composition "
        "with room on the left side." + KEIN_TEXT, True),
    "shop-abend-169": ("16:9", SHOP +
        "Wide interior at closing time: Moe sweeps the floor near the chairs, the "
        "shop glows warm against the blue dusk outside the window. Horizontal "
        "cinematic composition." + KEIN_TEXT, True),
}


def erzeugen(name, verhaeltnis, prompt, referenz: bytes | None) -> bytes:
    teile = [{"text": prompt}]
    if referenz is not None:
        teile.insert(0, {"inlineData": {"mimeType": "image/png",
                                        "data": base64.b64encode(referenz).decode()}})
        teile[1]["text"] = ("The man in the reference image is Moe — keep his face, "
                            "hair, beard and outfit exactly. " + prompt)
    body = {"contents": [{"parts": teile}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"aspectRatio": verhaeltnis,
                                                 "imageSize": "2K"}}}
    req = urllib.request.Request(URL, method="POST", headers={"Content-Type": "application/json"},
                                 data=json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=240) as r:
        antwort = json.load(r)
    t = antwort["candidates"][0]["content"]["parts"]
    return base64.b64decode(next(x["inlineData"]["data"] for x in t if "inlineData" in x))


def main():
    ziel = pathlib.Path(sys.argv[1]); ziel.mkdir(parents=True, exist_ok=True)
    wahl = sys.argv[2:] or list(MOTIVE)
    portrait = ziel / "moe-portrait-916.png"
    for name in wahl:
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
