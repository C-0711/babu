# babu-Spots: Nano Banana 2 + Veo 3.1 statt simpleshow

Pipeline (Schlüssel liegt in `~/Youtube/.env`, nie committen):

1. `charakter_bibel.py <ziel>` — Referenzbilder in 9:16 (Babs, Olaf).
   Regel: IMMER Menschen im Bild; Referenzen im Ziel-Seitenverhältnis.
2. `spot_olaf.py <ziel>` — 8-s-Takes via `veo-3.1-fast-generate-preview`
   (Referenzbild + Regieanweisung, deutscher Dialog in Anführungszeichen).
3. Schnitt: Takes + Endcard (PIL, Landing-Farben #efece6/#6f8a6e) per
   ffmpeg concat; Untertitel als PIL-Overlays einbrennen (das lokale
   ffmpeg hat kein libass/drawtext). Vorlage: `spot_schnitt.sh`, `spot.srt`.
4. Veröffentlichen: `scp <spot>.mp4 h200v:~/babu-web/bilder/` —
   `/bilder/{name}` liefert mp4 mit Range-Support (Portal-Branch).

Erster Spot: „Olaf rechnet ab" (36 s, im Kostenvergleich der Landing).
Regeln: Olaf bleibt fiktive, humorvolle Kunstfigur (keine Verunglimpfung
des Berufsstands); App-Bildschirme werden NIE generiert, nur echt gefilmt;
Preise immer als Beispielpreise kennzeichnen. Videos nicht ins Repo (Größe).

Backlog: „Brauchst du eine TSE?", Mythen-Serie „Hast du gewusst …?",
Testimonial (nachgespielt, gekennzeichnet), Salon-Check-Demo mit echtem
Portal-Insert.

## Serie „Kostenwahrheit" (10 Folgen)

`serie.py` rendert alle Takes, `serie_schnitt.py` schneidet die Folgen.
Aufbau je Folge (~27 s, 9:16): Olaf zeigt das Problem — Babs kontert —
gemeinsamer Abbinder „Mein grüner Haken ist grüner als deiner." — Endcard.

Der Claim-Take (`claim-haken.mp4`) wird EINMAL gerendert und in alle
Folgen geschnitten — spart 9 Renders und hält den Abbinder identisch.

| Datei | Thema | Olaf | Babs |
|---|---|---|---|
| spot-angebot | Kein Angebot, nur eine Rechnung | „Was das kostet? Sehen Sie dann auf der Rechnung." | „Bei mir steht der Preis vorher dran." |
| spot-reden | Reden kostet | „Sie haben eine Frage? Die Zeit berechne ich." | „Fragen kostet bei mir nichts." |
| spot-kleinvieh | Die Kleinigkeiten | „Porto. Kopien. Fahrtkosten. Pauschale." | „Ein Preis. Keine Überraschungen." |
| spot-leistung | Keine Leistungsübersicht | „Paragraf 33. Zwölf Zehntel." | „Ich seh jeden Beleg. Und was damit passiert ist." |
| spot-verschlampt | Beleg verschlampt | „Ihr Beleg? Weg. Das Suchen berechne ich." | „Meine Belege liegen bei mir." |
| spot-doppelt | Doppelt abgerechnet | „Einmal. Und sicherheitshalber nochmal." | „Bei mir steht, was wann rausging." |
| spot-vorarbeit | Vorarbeit umsonst | „Schön sortiert. Der Preis bleibt gleich." | „Ich sortier nichts mehr. Foto — fertig." |
| spot-frist | Frist verpasst | „Zu spät? Den Zuschlag zahlen Sie." | „Meine Fristen stehen in meinem Kalender." |
| spot-spaet | Zahlen zu spät | „Ihre März-Zahlen? Kommen im August." | „Ich seh meine Zahlen heute Abend." |
| spot-wechsel | Wechsel zäh gemacht | „Kündigen? Da wären noch offene Honorare." | „Meine Unterlagen gehören mir. Ich geh einfach." |

Argumente und Sprachregeln: `kostenwahrheit.md`.
Gelegentlich scheitert ein Take serverseitig („internal server issue") —
`rendern()` überspringt vorhandene Dateien, ein erneuter Lauf holt nur
die fehlenden nach.

### Startbilder (`poster.py`)

Jede Folge bekommt ein erklärendes Startbild: ein Frame aus dem Olaf-Take,
weichgezeichnet und mit Verlauf abgedunkelt, dazu Marke, Play-Ring, Titel,
ein Erklärsatz und der grüne Haken mit der Adresse. So versteht man das
Thema auch ohne Klick und ohne Ton.

**Falle:** Halbtransparente Formen (Play-Ring) müssen auf einer eigenen
RGBA-Ebene gezeichnet und per `alpha_composite` gemischt werden — direkt
auf das Bild gezeichnet werden sie beim RGB-Export zu deckendem Weiß.

Auf der Landing liegen die Spots in der Sektion `#kostenwahrheit`
(zwischen Paketen und Telefon-Sektion). Videos und Poster sind
Datei-Verweise auf `/bilder/`, KEINE data-URIs — sonst wächst die
Startseite auf über 100 MB. Beim Bauen von `index-deploy.html` deshalb
nur `src="bilder/*.png"` einbetten, `poster=` und Video-`src` unangetastet
lassen.
