"""Spot 1 „Olaf rechnet ab": vier Takes aus der Charakter-Bibel."""
import base64, json, pathlib, sys, time, urllib.request

key = next(z.split("=", 1)[1].strip()
           for z in pathlib.Path.home().joinpath("Youtube/.env").read_text().splitlines()
           if z.startswith("GEMINI_API_KEY="))
basis = "https://generativelanguage.googleapis.com/v1beta"
SP = pathlib.Path(sys.argv[1])

OLAF_STIL = ("Photorealistic with slight caricature energy, dark mahogany "
             "office, warm banker's lamp, dust in the light, subtle paper "
             "rustling ambience. The smug tax advisor from the reference "
             "image, fictional character. ")
BABS_STIL = ("Photorealistic handheld documentary style, bright warm cream "
             "hair salon, natural light, subtle salon ambience. The cheeky "
             "hairdresser from the reference image. ")

TAKES = [
    ("t1-olaf-zaehlt", "olaf-buero-916.png", OLAF_STIL +
     "He leans back in his leather chair, fans the paper invoices like "
     "playing cards, taps them one by one and says in German with a smug, "
     "satisfied grin: \"Januar: dreihundertfünfzig. Februar: "
     "dreihundertfünfzig.\" He chuckles softly to himself. No text overlays."),
    ("t2-olaf-beratung", "olaf-buero-916.png", OLAF_STIL +
     "He puts the invoices down, grabs a heavy desk stamp, stamps a document "
     "with a loud satisfying thunk, holds it up proudly and says in German: "
     "\"Beratung? ... Kostet extra.\" He laughs heartily. No text overlays."),
    ("t3-babs-scan", "babs-tresen-916.png", BABS_STIL +
     "She holds her smartphone over the small paper receipt on the wooden "
     "counter and snaps a photo — a soft satisfying chime. She looks into "
     "the camera, smirks and says in casual German: \"Beleg? Foto. Fertig.\" "
     "No text overlays."),
    ("t4-babs-haken", "babs-haken-916.png", BABS_STIL +
     "She leans on the counter, holds the phone with the glowing green "
     "checkmark towards the camera, smirks and says in casual German: "
     "\"Ich zahl neunundsiebzig im Monat — und mein Haken ist grüner als "
     "seiner.\" She winks. No text overlays."),
]


def rendern(name, ref, prompt):
    bild = (SP / ref).read_bytes()
    req = urllib.request.Request(
        f"{basis}/models/veo-3.1-fast-generate-preview:predictLongRunning?key={key}",
        method="POST", headers={"Content-Type": "application/json"},
        data=json.dumps({
            "instances": [{"prompt": prompt,
                           "image": {"bytesBase64Encoded": base64.b64encode(bild).decode(),
                                     "mimeType": "image/png"}}],
            "parameters": {"aspectRatio": "9:16"},
        }).encode())
    with urllib.request.urlopen(req, timeout=120) as r:
        op = json.load(r)["name"]
    for _ in range(60):
        time.sleep(10)
        with urllib.request.urlopen(f"{basis}/{op}?key={key}", timeout=60) as r:
            stand = json.load(r)
        if stand.get("done"):
            break
    if "error" in stand:
        print(f"{name} FEHLER: {stand['error'].get('message')}")
        return False
    video = stand["response"]["generateVideoResponse"]["generatedSamples"][0]["video"]
    ziel = SP / f"{name}.mp4"
    if video.get("uri"):
        trenn = "&" if "?" in video["uri"] else "?"
        with urllib.request.urlopen(video["uri"] + f"{trenn}key={key}", timeout=300) as r:
            ziel.write_bytes(r.read())
    else:
        ziel.write_bytes(base64.b64decode(video["bytesBase64Encoded"]))
    print(f"{name}: {ziel.stat().st_size // 1024} KB")
    return True


for name, ref, prompt in TAKES:
    if not (SP / f"{name}.mp4").exists():
        rendern(name, ref, prompt)
