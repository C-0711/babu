# Einsortieren nach der Lesung + „Zweitprüfung"-Wording verschwindet

Auftrag Christoph, 26.08.2026 abends: (1) Der Stichwort-Einsortierer soll nicht mehr
beim Hochladen über das Fach entscheiden — 32 Beleg-Fotos lagen dadurch unlesbar in
`auszuege/`. Die Entscheidung fällt künftig nach der echten Lesung im Watcher; der
Upload wird dumm. Kontoauszug-PDFs mit sprechendem Dateinamen (`…Auszug…`) nehmen
weiter die Abkürzung. (2) „Erstlesung/Zweitlesung/Zweitprüfung/Erstauswertung" darf
im Frontend nirgends mehr auftauchen — der Prozess läuft unsichtbar im Hintergrund.

## Aufgaben

1. **einsortieren.py härten** (bleibt für Vertrag/Behörde als Sofort-Weiche, deren
   Hintergrund-Jobs am Upload hängen): `kontoauszug` zählt IBAN/BIC/Lastschrift nur
   noch, wenn ein echtes Auszugssignal dabei ist (kontoauszug/kontostand/buchungstag/
   auszug nr); `beleg` bekommt „rechnung", „rechnungs-nr", „zahlbar" als Merkmale.
   Tests: Rechnung mit Bankverbindung im Fuß → beleg; echter Auszugstext → kontoauszug.
2. **Upload (babu_web.py ~1758–1809):** Dateinamen-Abkürzung: PDF mit `auszug` im
   Namen → `auszuege/` wie bisher. Sonst entscheidet `einsortieren` nur noch zwischen
   vertrag/behoerde/beleg — ein `kontoauszug`-Urteil ohne Abkürzung wird zu `beleg`
   (docs/), denn das prüft der Watcher mit vollem Text nach. Tests anpassen.
3. **Watcher (review_watcher.py, `verarbeite`):** Vor der Beleg-Pipeline den vollen
   PaddleOCR-Text durch das gehärtete `einsortieren.entscheiden` schicken; Urteil
   `kontoauszug` und sicher → Datei per git mv nach `auszuege/<monat>/` committen
   („einsortiert: …"), kein Beleg-Review, fertig. (Umsätze-Parsing bleibt den
   PDF-Uploads über die bestehende Route vorbehalten — Foto-Auszüge sind sichtbar
   im Fach und werden von Hand nachgereicht, das ist heute genauso.)
4. **Migration:** die 32 Fotos aus `auszuege/2026-08/` nach `docs/2026-08/`
   verschieben (boxschreiber-Commit), Watcher liest sie dann automatisch.
5. **Wording iOS** (ListeView.swift 269/664/679/834/854, Models/Store nur Kommentare):
   sichtbare Texte ohne „Zweitprüfung": Abschnitt „PRÜFUNG", „PRÜFUNG NICHT MÖGLICH —
   FOTO PRÜFEN", „Prüfung läuft — gleich verfügbar", „Für die Prüfung bitte die
   Belegbox verbinden", Accessibility „Prüfung aktualisieren". Build muss stehen.
6. **Wording Portal** (portal.html 1873/1874/1907): Chip/Abschnitt „Geprüft ✓" bzw.
   „Prüfung"; kein „Zweitprüfung" mehr.
7. **Deploy:** babu_web.py + einsortieren.py + review_watcher.py + portal.html auf die
   H200V (Golden-Diff-Ritual für babu-web, pm2 restart babu-web UND belegreview),
   danach Migration (4) ausführen und beobachten, Push auf origin/main.

## Verifikation
- Suite grün; neue Tests für 1–3.
- Upload-Rauchtest: Foto mit IBAN im Text → landet in docs/ und bekommt ein Review.
- Die 32 migrierten Fotos erscheinen nach und nach mit Beträgen im Index.
- App/Portal zeigen nirgends mehr „Zweitprüfung/Erstlesung/Zweitlesung".
