# Spec: Salon-Check — Abschluss hochladen, zuschauen, Ampel-Report

> **Hinweis (27.08.2026):** Dieses Dokument beschreibt den Stand seiner
> Entstehung. Der Watcher / die zweite Lesung existiert seit dem Zielbild
> nicht mehr — was heute gilt, steht in `HANDOVER.md`.


Stand 19.08.2026 · Auftraggeber-Branch: `claude/project-understanding-f6f4ff` ·
Umsetzung Server/Portal: Portal-Branch `claude/project-handover-context-7bfaa2`
(Commit `b26af87`) · Landing: dieser Branch. **Alle Aufträge sind umgesetzt
und live** — dieses Dokument hält Vertrag und Betriebsregeln fest.

## Kontext

Die Salonbesitzerin lädt die Unterlagen ihres letzten Jahresabschlusses hoch
(EÜR, BWA, Steuerbescheide, Anlagenverzeichnis — Fotos oder PDFs, beliebige
Reihenfolge). babu liest alles selbst (Belegwerk-Lesekompetenz als USP),
richtet das Konto ein und erzeugt einen Ampel-Report in Friseur-Sprache.
Show-Moment: Im Portal füllt sich Feld für Feld sichtbar von selbst aus
(„Zuschauen statt Abtippen").

## Auftrag 1 — Report-Kern `saloncheck.py`

Reine Funktionen ohne I/O: `karten_bauen(kennzahlen) -> [karte]` mit
`{id, ampel: gruen|gelb|rot|grau, titel, satz, detail, wert, ueblich}`.
Übliche Friseur-Spannen (Material 10–12 %, Personal 45–55 %, Raum 10–15 %
vom Umsatz), Gelb bis Faktor 1,2 über der Spanne, darüber Rot. Werte in
`unsicher[]` oder fehlend → Grau („Das konnten wir nicht sicher lesen").
Steuer-Rücklage: 30 % vom Gewinn minus Vorauszahlungen, monatlich auf 50 €
gerundet. Sonderfälle: Solo-Salon (personal == 0), Kleinunternehmerin
(Grenze 25.000 €). Kartentexte ohne Fachjargon (kein „Quote/Benchmark/Marge").

## Auftrag 2 — Lese-Strecke `abschluss_lesen.py`

Eigenständig neben dem Beleg-Watcher (nichts aus `review_watcher.py`
importieren!). Lane-Wahl: ≥ 200 Zeichen Text auf Seite 1 → Text-Lane
(pypdfium2-Volltext, ein Gemma-JSON-Prompt je Dokument), sonst Scan-Lane
(Seiten als JPEG ≤ 1600 px → Bild-Prompt je Seite → Konsolidierung).
`art_erkennen`: Ankerbegriffe zuerst (EÜR/BWA/Bescheid/Anlagen/SuSa),
LLM-Fallback mit fester Auswahl, temp 0. Jeder gefundene Wert geht sofort
durch den `melden(feld)`-Callback (daraus lebt die Zuschauen-Ansicht).
**Summenproben sind Pflicht:** Gewinn ≈ Umsatz − Kosten (1 % Toleranz) und
EÜR-Gewinn vs. Bescheid; Verstöße → `unsicher[]`, nie automatisch übernehmen.
Vorrang beim Zusammenführen: EÜR vor BWA vor SuSa; Vorauszahlungen nur aus
dem Bescheid. Ergebnis: ein Commit `abschluss/<jahr>/kennzahlen.json`.

## Auftrag 3 — Job + Endpunkte (babu_web.py)

Hintergrund-Thread im Prozess (workers=1 → ein Prozess, Status-Dict
`_ABSCHLUSS_JOBS` sichtbar für alle Requests), Snapshot in `portal.db`
(`abschluss_status`), `threading.Semaphore(1)` vor allen LLM-Aufrufen
(vLLM teilt sich mit dem Watcher). KEIN SSE — das Portal pollt 1×/s.
Endpunkte hinter `_api_wache`:
- `POST /api/abschluss?jahr=&name=` — Rohbytes, `ABSCHLUSS_MAX` 80 MB,
  Box-Commit + Arbeitskopie unter `~/babu-web/abschluss-tmp/<un>/<jahr>/`
- `POST /api/abschluss/start?jahr=` — 409 solange ein Job läuft,
  400 ohne Unterlagen
- `GET /api/abschluss/status` — Job-Dict; nach Prozess-Neustart Snapshot
  mit `stand: "unterbrochen"` („starte es einfach nochmal")
- `GET /api/salon-check?jahr=` — kennzahlen.json → Karten

Konto-Einrichtung: Stammdaten (rechtsform, steuernummer, finanzamt,
kleinunternehmer) auf die bestehenden `EINSTELLUNG_SCHLUESSEL`. Konfliktregel:
leerer Schlüssel wird gesetzt, belegter NIE überschrieben — stattdessen
`vorschlaege[]` → Bestätigungs-Chip im Portal → normales
`POST /api/einstellungen`.

## Auftrag 4 — Portal-Reiter (portal.html)

Reiter „Salon-Check" (`#a-saloncheck` + `ansichten`-Map). Drei Zustände:
1. *Ablegen*: Erklärkarte + Mehrfach-Upload, danach „Loslesen ›"
2. *Zuschauen*: 1s-Poll; jedes neue Feld fliegt als Zeile ein, Haken nach
   ~450 ms; Hinweis-Satz („Ich lese Gewinnrechnung — Seite 3 von 7");
   ehrliche Dauer-Ansage; `prefers-reduced-motion` respektiert
3. *Fertig*: Ampel-Karten mit ⓘ („Mehr dazu"), „Für die Kanzlei drucken"
   (window.print), „Neu lesen"

## Auftrag 5 — Landing-Sektion (dieser Branch)

Sektion „Neu · Der Salon-Check" nach dem Screenshots-Block: links
Nano-Banana-2-Bild (freche Friseuse mit Papierstapel,
`bilder/salon-check.png`), rechts Telefon-Mockup, das sich per
IntersectionObserver-Schleife selbst ausfüllt (reduced-motion → fertiger
Endzustand). Headline „Wirf uns deinen Papierstapel hin. Wir lesen alles.",
CTA → /portal. Deploy: `index-deploy.html` (data-URIs, Achtung: die
Bild-Regex muss `src="/bilder/…"` MIT führendem Slash matchen) →
Static-Swap nach `~/babu-web/index.html`.

## Abnahme (alle erfüllt, 19.08.2026)

- Suite 65/65 (23 neue Tests: Kern, Pipeline, API-Lebenszyklus)
- Golden-Diff `/review/<weingärtle>` nach `pm2 restart babu-web` byte-gleich
- Live-Probe: echtes Gemma liest synthetische EÜR fehlerfrei
  (9/9 Felder, Summenprobe 0,0 % Abweichung)
- Live-Routen: status leer / salon-check leer / start ohne Dateien 400 /
  ohne Anmeldung 401
- Landing live mit Bild + Animation (Cache-Buster-Check: 3 Treffer)

## Bewusst v2

Kanzlei-PDF (v1: Druckansicht), Fristen-Kalender, CSV-Kontoimport,
iOS-App-Tab, Mehrjahres-Vergleich, SuSa als strukturierter Import.

## Offen / Risiko

**Kein echtes EÜR/BWA/Bescheid-Dokument im Testkorpus** — die Extraktion ist
technisch verifiziert (synthetisch + echtes Gemma), fachlich erst nach
Unterlagen der Salon-Mandantin abnehmbar. Bitte EÜR + Anlagenverzeichnis
(+ eine Monats-BWA) anfordern. Echte Dokumente bleiben lokal, nie ins Repo.
