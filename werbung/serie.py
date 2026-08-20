"""Spot-Serie „Kostenwahrheit": 10 Folgen, gleiche Figuren, gleicher Abbinder.

Aufbau je Folge: Olaf zeigt das Problem — Babs kontert — gemeinsamer
Claim-Take „Mein grüner Haken ist grüner als deiner."
"""
import base64, json, pathlib, sys, time, urllib.request

SP = pathlib.Path(__file__).parent
key = next(z.split("=", 1)[1].strip()
           for z in pathlib.Path.home().joinpath("Youtube/.env").read_text().splitlines()
           if z.startswith("GEMINI_API_KEY="))
BASIS = "https://generativelanguage.googleapis.com/v1beta"

OLAF = ("Photorealistic with slight caricature energy, dark mahogany office, "
        "warm banker's lamp, towering stacks of paper, dust in the light beam, "
        "subtle paper rustling. The smug tax advisor from the reference image, "
        "fictional character, speaking German directly to camera. ")
BABS = ("Photorealistic handheld documentary style, bright warm cream hair "
        "salon, natural window light, subtle salon ambience. The cheeky "
        "hairdresser from the reference image, speaking casual German "
        "directly to camera. ")

# (kurz, olaf_regie, olaf_text, babs_ref, babs_regie, babs_text)
FOLGEN = [
    ("angebot", "He leans back, folds his hands over his belly and smiles broadly.",
     "Was das kostet? Sehen Sie dann auf der Rechnung.",
     "babs-tresen-916.png", "She leans on the counter, shrugs lightly and smiles.",
     "Bei mir steht der Preis vorher dran. Wie beim Haareschneiden."),
    ("reden", "He taps his wristwatch with one finger, eyebrows raised, amused.",
     "Sie haben eine Frage? Die Zeit berechne ich.",
     "babs-tresen-916.png", "She holds up her phone, grinning invitingly.",
     "Fragen kostet bei mir nichts. Frag mich was."),
    ("kleinvieh", "He counts on his fingers with growing delight.",
     "Porto. Kopien. Fahrtkosten. Pauschale.",
     "babs-tresen-916.png", "She raises one finger, calm and clear.",
     "Ein Preis. Keine Überraschungen."),
    ("leistung", "He points at a document with his pen, deadpan and bureaucratic.",
     "Paragraf dreiunddreißig. Zwölf Zehntel.",
     "babs-tresen-916.png", "She looks at her phone, then at the camera, satisfied.",
     "Ich seh jeden Beleg. Und was damit passiert ist."),
    ("verschlampt", "He lifts a stack of folders, looks underneath, shrugs innocently.",
     "Ihr Beleg? Weg. Das Suchen berechne ich.",
     "babs-tresen-916.png", "She photographs a receipt on the counter, phone chimes softly.",
     "Meine Belege liegen bei mir. Fotografiert und sicher."),
    ("doppelt", "He stamps a document twice with a loud satisfying thunk, chuckling.",
     "Einmal. Und sicherheitshalber nochmal.",
     "babs-tresen-916.png", "She scrolls her phone, then looks up confidently.",
     "Bei mir steht, was wann rausging. Auf den Tag."),
    ("vorarbeit", "He looks at a neatly sorted folder, nods approvingly, then shrugs.",
     "Schön sortiert. Der Preis bleibt gleich.",
     "babs-tresen-916.png", "She tosses an imaginary pile aside and laughs.",
     "Ich sortier nichts mehr. Foto — fertig."),
    ("frist", "He glances at a calendar on the wall, entirely unbothered.",
     "Zu spät? Den Zuschlag zahlen Sie.",
     "babs-tresen-916.png", "She taps her phone calendar and nods.",
     "Meine Fristen stehen in meinem Kalender."),
    ("spaet", "He slides a thick report across the desk, slow and ceremonious.",
     "Ihre März-Zahlen? Kommen im August.",
     "babs-abend-916.png", "Evening light, she leans relaxed on the counter with her phone.",
     "Ich seh meine Zahlen heute Abend."),
    ("wechsel", "He clutches a folder protectively against his chest, smiling thinly.",
     "Kündigen? Da wären noch offene Honorare.",
     "babs-tresen-916.png", "She walks past the counter with her phone, light and free.",
     "Meine Unterlagen gehören mir. Ich geh einfach."),
]

CLAIM = (BABS + "She leans on the counter, holds the phone with the glowing "
         "green checkmark up towards the camera, smirks proudly and says in "
         "casual German: \"Mein grüner Haken ist grüner als deiner.\" "
         "She winks once. No text overlays.")


def rendern(name, ref, prompt):
    ziel = SP / f"{name}.mp4"
    if ziel.exists():
        return True
    bild = (SP / ref).read_bytes()
    req = urllib.request.Request(
        f"{BASIS}/models/veo-3.1-fast-generate-preview:predictLongRunning?key={key}",
        method="POST", headers={"Content-Type": "application/json"},
        data=json.dumps({
            "instances": [{"prompt": prompt,
                           "image": {"bytesBase64Encoded": base64.b64encode(bild).decode(),
                                     "mimeType": "image/png"}}],
            "parameters": {"aspectRatio": "9:16"},
        }).encode())
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            op = json.load(r)["name"]
    except Exception as e:
        print(f"{name}: Start fehlgeschlagen ({e})", flush=True)
        return False
    for _ in range(60):
        time.sleep(10)
        try:
            with urllib.request.urlopen(f"{BASIS}/{op}?key={key}", timeout=60) as r:
                stand = json.load(r)
        except Exception:
            continue
        if stand.get("done"):
            break
    if not stand.get("done") or "error" in stand:
        print(f"{name}: {stand.get('error', {}).get('message', 'Zeit abgelaufen')}", flush=True)
        return False
    video = stand["response"]["generateVideoResponse"]["generatedSamples"][0]["video"]
    if video.get("uri"):
        trenn = "&" if "?" in video["uri"] else "?"
        with urllib.request.urlopen(video["uri"] + f"{trenn}key={key}", timeout=300) as r:
            ziel.write_bytes(r.read())
    else:
        ziel.write_bytes(base64.b64decode(video["bytesBase64Encoded"]))
    print(f"{name}: {ziel.stat().st_size // 1024} KB", flush=True)
    return True


if __name__ == "__main__":
    rendern("claim-haken", "babs-haken-916.png", CLAIM)
    for kurz, o_regie, o_text, b_ref, b_regie, b_text in FOLGEN:
        rendern(f"s-{kurz}-olaf", "olaf-buero-916.png",
                OLAF + o_regie + f" He says in German: \"{o_text}\" No text overlays.")
        rendern(f"s-{kurz}-babs", b_ref,
                BABS + b_regie + f" She says in German: \"{b_text}\" No text overlays.")
    print("SERIE FERTIG", flush=True)
