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
