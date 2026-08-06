# Design-Prompt: „Beleg" — Mobile Capture & Kontierungs-Workbench

> Prompt zum Einfügen in Claude / ein Design-Tool. Ziel: vollständiges UI-Design (Mobile-first App + Review-Workbench) für eine automatische Belegkontierungs-Strecke.

---

## 1. Produktkontext (dem Designer als Wahrheit mitgeben)

Du designst **„Beleg"**, eine App der 0711 Intelligence Platform für den deutschen Mittelstand und deren Steuerberater. Der Kern-Loop:

1. Nutzer hält die Kamera über einen Geschäftsbeleg (Rechnung, Kassenbon, Eigenbeleg).
2. Der Beleg wird **live erkannt, automatisch ausgelöst, perfekt gecroppt und geglättet** (auch gewelltes Thermopapier).
3. **Instant Reading**: On-Device-OCR hebt die gefundenen Felder in <1 Sekunde als Overlay hervor (Lieferant, Datum, Netto, USt, Brutto, Rechnungsnummer).
4. Server-Pipeline (Dual-Lane OCR auf H200) verifiziert, kontiert automatisch gegen SKR03/SKR04 bzw. den individuellen Mandanten-Kontenplan und vergibt einen **Confidence-Score**.
5. Confidence-Routing: hoch → Dunkelverarbeitung (kein UI nötig), mittel → One-Tap-Bestätigung, niedrig → manuelle Kontierung.
6. Export als DATEV-Buchungsstapel (EXTF) bzw. später Direct-Push via DATEV-API.
7. Jeder Beleg wird ab Sekunde 1 GoBD-konform archiviert und Merkle-versiegelt — das Siegel ist ein sichtbares Vertrauensmerkmal, kein verstecktes Backend-Detail.

**Zielgruppen:** (a) Sachbearbeiter:in / Inhaber:in im Mittelstandsbetrieb — erfasst Belege nebenbei, will null Reibung; (b) Buchhalter:in / Steuerberater:in — arbeitet die Review-Queue ab, will Dichte, Tastatur-Tempo und Nachvollziehbarkeit.

**Positionierung:** Souveräne KI, Daten bleiben im Haus, deutsche Präzision. Kein Silicon-Valley-Fintech-Look, kein verspieltes Neo-Banking. Eher: das Selbstvertrauen eines Messinstruments.

---

## 2. Design-Sprache (verbindliche Leitplanken)

- **Charakter:** Präzisionsinstrument. Ruhig, dicht, verifizierbar. Jedes UI-Element soll aussehen, als hätte es einen Messwert. Vorbild-Vibes: Leica-Bedienoberflächen, deutsche Laborgeräte, DIN-Formulare — modern interpretiert, nicht retro.
- **Farbwelt:** Entwickle eine eigene Palette aus 4–6 benannten Hex-Werten. Vorgabe nur konzeptionell: eine tiefe, fast schwarze Basistinte; ein kühles Papierweiß; **eine einzige Signalfarbe für „verifiziert/gesiegelt"** (denkbar: ein technisches Siegelgrün oder Prüfstempel-Blau — bewusst KEIN Terracotta, KEIN Acid-Green auf Schwarz, keine der üblichen AI-Default-Paletten); dazu eine Warnfarbe für Differenzen/Low-Confidence. Confidence wird **farblich codiert und immer zusätzlich als Zahl** angezeigt (nie nur Farbe — Barrierefreiheit).
- **Typografie:** Zwei Rollen mindestens. Ein charaktervoller Display-/UI-Font mit technischer Anmutung und **tabellarischen Ziffern** (Beträge, Kontonummern, Steuerschlüssel sind die Hauptdarsteller — Ziffernqualität ist nicht verhandelbar). Dazu ein Utility-/Mono-Font für Kontonummern, Hashes, Merkle-Siegel und EXTF-Metadaten. Begründe die Paarung.
- **Signature-Element (das eine Merkmal, an das man sich erinnert):** das **Siegel**. Jeder verarbeitete Beleg trägt eine kleine, präzise Siegel-Marke (Merkle-Hash-Kurzform + Zeitstempel), die beim Abschluss der Verarbeitung mit einer kurzen, physisch anmutenden Animation „gestempelt" wird. Dieses Siegel zieht sich durch alle Screens (Capture-Abschluss, Listenansicht, Detailansicht, Export-Bestätigung) und ist der visuelle Beweis für „unveränderbar archiviert".
- **Motion:** genau drei orchestrierte Momente, sonst Ruhe: (1) Auto-Capture-Moment (Kontur rastet ein, Beleg „legt sich flach"), (2) Instant-Reading-Reveal (Felder-Bounding-Boxes erscheinen gestaffelt in ~400 ms), (3) Siegel-Stempel. `prefers-reduced-motion` wird respektiert.
- **Sprache im UI:** Deutsch, Sie-Form vermeiden — neutrale Verbform („Beleg erfassen", „Buchung bestätigen"). Fachbegriffe korrekt (Soll/Haben, Steuerschlüssel, Kreditor), aber nie Systemjargon (kein „Inference", kein „Pipeline-Status" für Endnutzer). Fehlertexte sagen, was passiert ist und was zu tun ist.

---

## 3. Screens & Flows (vollständig designen, inkl. aller States)

### 3.1 Capture (Herzstück, Mobile)
- Vollbild-Kamerastream. Dezente Eck-Marker statt Rahmen-Overlay.
- **Live-Detection-State:** erkannte Belegkontur als feine Linie, die der Belegform folgt; Statuszeile darunter mit Klartext („Beleg erkannt — ruhig halten").
- **Auto-Capture:** kein Auslöse-Button im Happy Path. Fallback-Auslöser dezent vorhanden. Nach Capture: Beleg animiert sich in die entzerrte, geglättete Ansicht.
- **Instant-Reading-Overlay:** Bounding-Boxes mit Labels (Lieferant, Datum, Netto, USt %, Brutto, Re-Nr.) direkt auf dem Belegbild. Jede Box antippbar → Inline-Korrektur. Erkannte Summenprobe (Netto + USt = Brutto ✓) als Mikro-Bestätigung.
- **Batch-Modus:** mehrere Belege nacheinander, Zähler, Stapel-Vorschau als Filmstreifen unten.
- States: Suchen / Erkannt / Zu dunkel / Blendung erkannt / Mehrseitig (Seite 2 anlegen) / Offline (lokal gepuffert, Hinweis).

### 3.2 Verarbeitung & Confidence-Routing
- Nach Upload: kompakte Fortschrittskarte pro Beleg — nicht als Spinner, sondern als **Prüfschritte mit Häkchen** (Extraktion ✓ · Pflichtangaben §14 UStG ✓ · Kontierung ✓ · Siegel ✓).
- Ergebnis-Karte zeigt: Kontierungsvorschlag als Buchungssatz („4930 Büromaterial an 70001 Kreditor Müller GmbH, 119,00 €, VSt 19 %"), Confidence als Zahl + Balken, Herkunft der Entscheidung als Badge (**Historie** / **Regel** / **KI**) — das ist Provenance als UI-Element.
- Drei Routen sichtbar machen: „Automatisch gebucht" (Siegel sofort), „Bestätigen" (ein Tap), „Prüfen" (öffnet Kontierungs-Editor).

### 3.3 Kontierungs-Editor (Review, Mobile + Desktop-Workbench)
- Split-View: links Belegbild mit hervorgehobenen Quell-Feldern, rechts Buchungssatz-Formular. Antippen eines Formularfelds highlightet die Quelle im Beleg (bidirektional).
- Kontenauswahl: Suchfeld mit Fuzzy-Suche über Kontonummer UND Bezeichnung, zuletzt verwendete Konten des Kreditors zuoberst, SKR-Standard vs. individuelles Mandantenkonto visuell unterscheidbar.
- Abweichungs-Anzeige: wenn On-Device-Reading und Server-Extraktion differieren, beide Werte nebeneinander mit markierter Differenz — Nutzer wählt, System lernt (Hinweistext: „Ihre Korrektur verbessert künftige Vorschläge für diesen Lieferanten").
- Desktop-Workbench zusätzlich: Queue links (sortiert nach Confidence aufsteigend), Tastatur-Navigation komplett (j/k, Enter = bestätigen, Ziffern = Steuerschlüssel), Durchsatz-Anzeige („34 Belege, ø 11 s/Beleg heute").

### 3.4 Belegliste / Archiv
- Dichte Tabelle (Desktop) bzw. Karten (Mobile): Datum, Lieferant, Betrag (tabellarische Ziffern, rechtsbündig), Konto, Status-Siegel, Confidence-Herkunft-Badge.
- Filter: Zeitraum, Status, Belegart, Kreditor, „nur manuelle Korrekturen".
- Detailansicht: Belegbild, vollständiger Buchungssatz, **Provenance-Panel** (welche Regel/welches Modell/welcher Mensch, Zeitstempel, Merkle-Siegel in Mono-Font, kopierbar).

### 3.5 Export
- Stapel-Bildschirm: Zeitraum wählen, Vorschau der Buchungssätze, EXTF-Download bzw. (später) „An DATEV übertragen". Nach Export: Bestätigung mit Stapel-Siegel und Hinweis, dass exportierte Buchungen fixiert sind.

### 3.6 Onboarding (pro Mandant)
- Drei Schritte, jeder ein eigener Screen: (1) SKR03/SKR04 wählen (mit Ein-Satz-Erklärung des Unterschieds und „Ihr Steuerberater weiß es sofort"), (2) optional Kontenplan-CSV hochladen (Drag-&-Drop, Parse-Vorschau mit erkannten Konten, Fehlerzeilen klar benannt), (3) Stammdaten (USt-Status, Kleinunternehmer, Ist/Soll, Wirtschaftsjahr). Fortschritt als Prüfliste, nicht als Prozentbalken.

### 3.7 Leere Zustände & Fehler
- Leere Belegliste = Einladung zum ersten Scan (Kamera-CTA), nicht Illustration-mit-Spruch.
- Fehlerfälle konkret designen: OCR unlesbar, Pflichtangabe fehlt (§14 UStG — benennen welche), Summenprobe schlägt fehl, Kontenplan-CSV fehlerhaft (Zeile + Grund), Offline-Warteschlange.

---

## 4. Technische Rahmenbedingungen fürs Design
- Mobile-first (iOS zuerst, VisionKit-Capture), Desktop-Workbench als responsive Web-App.
- Dark Mode als gleichwertige Variante (Buchhalter arbeiten abends), Capture-Screen ist ohnehin dunkel.
- WCAG AA: Confidence nie nur über Farbe, Fokus-Ringe sichtbar, Touch-Targets ≥ 44 pt, Belegbild-Kontraste unabhängig vom Overlay lesbar.
- Beträge, Konten, Steuerschlüssel immer in tabellarischen Ziffern; deutsche Zahlformatierung (1.234,56 €).

---

## 5. Erwartete Deliverables
1. **Token-System:** Palette (4–6 benannte Hex-Werte), Type-Scale (Display/Body/Mono mit Größen und Gewichten), Spacing-Raster, Radius-/Border-Logik, Motion-Timings.
2. **Signature-Spezifikation:** das Siegel — Aufbau, Zustände (in Arbeit / gesiegelt / exportiert-fixiert), Stempel-Animation als Timing-Beschreibung.
3. **High-Fidelity-Screens:** Capture (alle States), Instant-Reading-Overlay, Ergebnis-Karte mit Confidence-Routing, Kontierungs-Editor (Mobile + Desktop), Belegliste, Provenance-Detail, Export, Onboarding Schritt 1–3, zwei Fehlerzustände.
4. **Begründung:** zu jeder Kernentscheidung (Palette, Font-Paarung, Signature) zwei Sätze, warum sie aus der Welt des Produkts kommt — nicht aus einem Template.

**Selbstkritik-Schleife:** Prüfe den Entwurf vor Abgabe gegen diese Frage: „Könnte dieses Design genauso für eine beliebige Scan-App stehen?" Wenn ja — überarbeite Palette, Signature oder Typo, bis die Antwort Nein ist. Ein Accessoire entfernen, bevor du das Haus verlässt.
