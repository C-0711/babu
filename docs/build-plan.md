# Bauplan: „Beleg" — vom Prototyp zum Produktivsystem

> Ziel dieses Dokuments: der vollständige Plan, um aus dem Klick-Prototyp
> (`app/belegapp.html`) und dem Design-Prompt (`prompts/design-prompt-kontierung-app.md`)
> die echte Anwendung zu bauen — Capture → Extraktion → Kontierung →
> Confidence-Routing → GoBD-Archiv mit Merkle-Siegel → DATEV-Export.
> Teil der 0711 Intelligence Platform. Leitplanke: Daten bleiben im Haus.

---

## 1. Zielbild & Scope

**Kern-Loop (unverändert aus dem Prototyp):**
Beleg erfassen → in < 1 s Felder lesen → serverseitig verifizieren → automatisch
kontieren (SKR03/04 bzw. Mandanten-Kontenplan) → nach Confidence routen →
ab Sekunde 1 GoBD-konform archivieren und Merkle-versiegeln → als
DATEV-Buchungsstapel (EXTF) exportieren, später Direct-Push via DATEV-API.

**Scope-Stufen:**

| Stufe | Inhalt | Nutzer kann … |
|---|---|---|
| **MVP (Pilot)** | iOS-Capture, Server-Extraktion, Historie+Regel-Kontierung, Review-Editor mobil, EXTF-Export (importierbar!), Siegel + Archiv | einen Monatsstapel real beim Steuerberater einspielen |
| **v1.0** | Desktop-Workbench, KI-Kontierungs-Lane, E-Rechnungs-Ingestion (ZUGFeRD/XRechnung), Batch-Capture, Onboarding komplett, Mandanten-Verwaltung | den kompletten Belegprozess eines Betriebs abbilden |
| **v1.x** | DATEV Buchungsdatenservice (Direct-Push), Android, E-Mail-Ingestion, Steuerberater-Portal mit Multi-Mandanten-Queue | ohne CSV-Umweg arbeiten; Kanzlei als eigener Nutzer |

**Explizit nicht im Scope:** eigene Finanzbuchhaltung (wir kontieren vor, gebucht
wird beim Steuerberater), Lohn, Zahlungsverkehr.

---

## 2. Systemarchitektur

```
┌─────────────┐   ┌──────────────┐   ┌───────────────────────────────┐
│ iOS-App      │   │ Workbench     │   │ Ingestion (v1.0+)             │
│ VisionKit    │   │ (Web, React)  │   │ E-Rechnung XML / E-Mail / PDF │
│ On-Dev-OCR   │   │               │   │                               │
└──────┬──────┘   └──────┬───────┘   └──────────────┬────────────────┘
       │  HTTPS / mTLS    │                          │
┌──────▼──────────────────▼──────────────────────────▼────────────────┐
│ API-Gateway (Auth/OIDC, Mandanten-Scoping, Rate-Limits)             │
└──────┬──────────────────────────────────────────────────────────────┘
       │
┌──────▼───────────────── Backend (modularer Monolith) ───────────────┐
│ Beleg-Service   Pipeline-Orchestrierung   Kontierungs-Engine        │
│ Stammdaten      Export-Service (EXTF)     Siegel-Service (Merkle)   │
└──┬─────────┬──────────────┬────────────────────────┬────────────────┘
   │         │              │                        │
┌──▼───┐ ┌──▼─────────┐ ┌──▼──────────────────┐ ┌──▼──────────────┐
│ Post │ │ Objektstore │ │ GPU-Worker (H200)    │ │ Audit-Log       │
│ gres │ │ S3/WORM     │ │ OCR-Lane + VLM-Lane  │ │ (append-only)   │
└──────┘ └────────────┘ └─────────────────────┘ └─────────────────┘
```

**Grundsatzentscheidungen:**

1. **Modularer Monolith statt Microservices.** Ein Deployment, klare interne
   Modulgrenzen (Beleg, Pipeline, Kontierung, Siegel, Export, Stammdaten).
   Erst schneiden, wenn ein Modul nachweislich anders skalieren muss
   (Kandidat: GPU-Worker — der ist von Tag 1 ein eigener Prozess mit Queue).
2. **Alles self-hosted / on-prem-fähig.** Postgres, S3-kompatibler Objektstore
   (MinIO/Garage) mit Object-Lock (WORM), Queue über Postgres
   (`FOR UPDATE SKIP LOCKED` genügt für die Volumina; kein Kafka).
   Keine US-Cloud-Abhängigkeit — das ist Positionierung, nicht nur Compliance.
3. **Pipeline als persistierte Zustandsmaschine.** Jeder Beleg durchläuft
   `erfasst → extrahiert → validiert → kontiert → geroutet → gesiegelt →
   exportiert`. Jeder Übergang wird im Audit-Log festgehalten — das ist
   gleichzeitig die Datenbasis für das Provenance-Panel im UI.

---

## 3. Datenmodell (Kern-Entitäten)

- **Mandant** — Kontenrahmen (SKR03/04), individueller Kontenplan,
  USt-Status (Regel/Klein­unternehmer, Ist/Soll), Wirtschaftsjahr,
  Berater-/Mandantennummer (für EXTF-Header).
- **Beleg** — Originaldatei(en) (Bild entzerrt + Original, PDF, XML),
  Belegart (Rechnung/Bon/Eigenbeleg/E-Rechnung), Status, Mandanten-FK.
- **Extraktion** — pro Lane (Device/OCR/VLM/XML) die gelesenen Felder mit
  Einzel-Confidence und Bounding-Boxes; dazu das reconcilierte Ergebnis.
- **Prüfung** — §-14-UStG-Pflichtangaben-Check (welche Angabe fehlt),
  Summenprobe, Dublettenprüfung (Kreditor + Re-Nr. + Betrag).
- **Buchungsvorschlag / Buchung** — Buchungssatz (Konto, Gegenkonto,
  Steuerschlüssel, Betrag, Belegfeld-Referenzen), Herkunft
  (`historie | regel | ki | mensch`), Confidence, Bearbeiter.
- **Kreditor** — Stammdaten inkl. gelerntes Kontierungsprofil
  (Konto-Histogramm, letzte N Buchungen).
- **Stapel** — Exporteinheit (Zeitraum, Buchungen, EXTF-Datei, Festschreibe-Status).
- **Siegel** — Hash des Belegs+Metadaten, Merkle-Pfad, Batch-Root,
  Zeitstempel (RFC 3161), Kurzform für die UI (`a3f9c1e7 …`).

Alle Tabellen mandantenscoped; Row-Level-Security in Postgres als zweite
Verteidigungslinie zusätzlich zum API-Scoping.

---

## 4. Teilsysteme im Detail

### 4.1 Capture (iOS zuerst)
- Swift/SwiftUI. `VisionKit` (`DataScannerViewController` bzw.
  `VNDocumentCameraViewController`) für Live-Kontur, Auto-Auslösung,
  Entzerrung — genau die Sequenz, die der Prototyp animiert.
- **Instant Reading on-device:** `Vision`-Framework (`RecognizeTextRequest`)
  + leichtgewichtiger Feld-Parser (Regex/Heuristik für Datum, Beträge,
  USt-IdNr., Re-Nr.) → Bounding-Box-Overlay in < 1 s. Die Device-Lesung wird
  mit hochgeladen und ist Lane 1 der Dual-Lane-Verifikation.
- Offline-Queue: Belege lokal persistieren, Background-Upload
  (`URLSession` background task), UI-Status „lokal gepuffert".
- Batch-Modus: Zähler + Filmstreifen (v1.0).
- States aus dem Design-Prompt vollständig: Suchen / Erkannt / Zu dunkel /
  Blendung / Mehrseitig / Offline.

### 4.2 Ingestion jenseits der Kamera (v1.0)
- **E-Rechnung ist Pflichtthema:** seit 01/2025 müssen Unternehmen
  strukturierte E-Rechnungen (XRechnung, ZUGFeRD/Factur-X) empfangen können.
  Für uns ein Geschenk: XML wird direkt geparst — eigene Pipeline-Lane mit
  faktisch 100 % Extraktions-Confidence, keine OCR nötig. Der Anteil dieser
  Belege wächst jedes Jahr; die Architektur behandelt sie von Anfang an als
  ersten Klasse-Bürger (eigene `Extraktion`-Lane `xml`).
- PDF-Upload (Workbench + Mobile Share-Extension), später E-Mail-Postfach
  pro Mandant (`beleg-<mandant>@…`).

### 4.3 Extraktions-Pipeline (Server, Dual-Lane)
- **Lane A — klassische OCR:** self-hosted (PaddleOCR oder docTR) mit
  Layout-Analyse. Schnell, deterministisch, gut für gedruckte Rechnungen.
- **Lane B — VLM:** self-hosted Vision-Language-Modell auf den H200
  (Startkandidat: Qwen2.5-VL, servierte via vLLM), Prompt auf strukturiertes
  JSON-Schema (Lieferant, Adresse, USt-IdNr., Re-Nr., Datum, Positionen,
  Netto/USt/Brutto je Steuersatz). Stark bei Bons, Handschrift, gewelltem
  Thermopapier.
- **Reconciliation:** Feldweiser Vergleich Lane A/B/Device. Übereinstimmung →
  hohe Feld-Confidence; Differenz → Serverwert bevorzugt, Abweichung wird dem
  Nutzer angezeigt (der Prototyp-Flow „Gerät las 54,82 · Server 54,62").
- **Validierung:** Summenprobe (Netto + USt = Brutto, je Steuersatz),
  §-14-UStG-Pflichtangaben, USt-IdNr.-Syntaxprüfung, Dublettencheck.
- Benchmark-Harness von Woche 1: kuratierter Belegkorpus (echte anonymisierte
  Belege, alle Belegarten) mit Ground-Truth; jede Pipeline-Änderung läuft
  gegen Feld-Accuracy und Ende-zu-Ende-Quote. Ohne das ist „Dual-Lane"
  Marketing statt Messwert.

### 4.4 Kontierungs-Engine & Confidence-Routing
Drei Stufen, in dieser Reihenfolge, erste sichere Antwort gewinnt —
deterministisch vor generativ:
1. **Historie:** Kreditor-Kontierungsprofil (das „14× zuvor auf 6815" aus dem
   Prototyp). Statistisch: dominantes Konto + Stabilität → Confidence.
2. **Regeln:** mandantenspezifisch (z. B. „Stadtwerke → 6325") und global
   (Belegart-/Branchenheuristiken). Von Buchhaltern pflegbar (Workbench-UI).
3. **KI-Lane:** LLM mit SKR-Kontext, Mandanten-Kontenplan und
   Kreditor-Kontext im Prompt. Liefert Konto + Begründung; Begründung wird
   gespeichert und im Provenance-Panel angezeigt.

**Routing-Schwellen** (kalibriert, pro Mandant übersteuerbar):
hoch (≥ 0,95) → Dunkelverarbeitung, sofort gesiegelt · mittel → One-Tap-
Bestätigung · niedrig → Review-Queue. Kalibrierung wird gemessen (Brier-Score
gegen tatsächliche Korrekturen) — eine Confidence, die nicht kalibriert ist,
ist eine Lüge im UI.

**Lernschleife:** Jede menschliche Korrektur aktualisiert das
Kreditor-Profil und fließt als Beispiel in die KI-Lane (Few-Shot aus der
Mandanten-Historie, kein Fine-Tuning nötig für den Start).

### 4.5 GoBD-Archiv & Merkle-Siegel
- Original + entzerrte Fassung + Extraktions-JSON unmittelbar nach Upload in
  WORM-Objektstore (S3 Object-Lock, Compliance-Mode) — „ab Sekunde 1".
- **Siegel:** SHA-256 über Beleg-Bytes + kanonisierte Metadaten. Belege werden
  periodisch (z. B. alle 5 min) zu einem Merkle-Baum gebündelt; die Root
  erhält einen qualifizierten RFC-3161-Zeitstempel (externer TSA). Jeder
  Beleg speichert seinen Merkle-Pfad → Einzelnachweis ohne Fremdsystem
  verifizierbar. Kurzform des Hashes ist das sichtbare Siegel im UI.
- Append-only Audit-Log für jede Zustandsänderung (wer/was/wann/womit) —
  identisch mit der Provenance-Ansicht.
- **Verfahrensdokumentation** (GoBD-Pflicht!) wird parallel zum Code
  geschrieben und versioniert im Repo gepflegt — nicht nachgelagert.
  Aufbewahrungsfristen beachten (Buchungsbelege: 8 Jahre seit BEG IV).

### 4.6 DATEV-Export
- **EXTF vollständig und importierbar** — nicht die Skizze aus dem Prototyp:
  Header mit Formatversion (DTVF/EXTF 700 / v13), Berater- und
  Mandantennummer, Wirtschaftsjahresbeginn, Sachkontenlänge,
  Datumsbereich; Buchungszeilen mit allen Pflichtfeldern
  (Umsatz, S/H, Konto, Gegenkonto, BU-Schlüssel, Belegdatum, Belegfeld 1/2,
  Buchungstext, Festschreibung). **Kodierung CP1252, CRLF** — sonst brechen
  Umlaute beim Import.
- Abnahmekriterium ist nicht „Datei erzeugt", sondern **„Datei importiert
  fehlerfrei in DATEV Kanzlei-Rechnungswesen"** — Test mit echter
  DATEV-Instanz bzw. Pilot-Steuerberater, automatisierter Golden-File-Test
  im CI.
- Export „fixiert" die enthaltenen Buchungen (Festschreibe-Kennzeichen,
  Stapel-Siegel). Nachträgliche Korrektur nur als Storno/Neubuchung.
- v1.x: DATEV Buchungsdatenservice (REST, OAuth) für Direct-Push —
  erfordert DATEV-Partnervertrag; der CSV-Weg bleibt als Fallback immer
  bestehen (bewusste Entscheidung aus dem Prototyp).

### 4.7 Review-UI: Mobile Editor & Desktop-Workbench
- **Mobile Editor** (MVP): Split-View Beleg ↔ Formular, bidirektionales
  Highlighting (Feld antippen → Quelle im Beleg markiert), Fuzzy-Kontensuche
  über Nummer + Bezeichnung, zuletzt verwendete Konten des Kreditors zuerst,
  Abweichungs-Anzeige Gerät/Server.
- **Desktop-Workbench** (v1.0): Queue links (Confidence aufsteigend),
  vollständige Tastatur-Navigation (j/k, Enter, Ziffern = Steuerschlüssel),
  Durchsatz-Anzeige. Zielgruppe Buchhalter/Kanzlei — Dichte schlägt Deko.
- Web-Stack: React + TypeScript (Next.js oder Vite), Design-Tokens 1:1 aus
  dem Prototyp (`--tinte`, `--stempel`, `--warn` …) als CSS-Custom-Properties;
  Fonts **self-hosted** (DSGVO — kein Google-Fonts-CDN).

### 4.8 Onboarding & Stammdaten
Drei Schritte wie im Design-Prompt: SKR-Wahl → Kontenplan-CSV (Parse-Vorschau,
Fehlerzeilen mit Zeile + Grund) → Stammdaten (USt-Status, Ist/Soll,
Wirtschaftsjahr, Berater-/Mandantennummer). Der CSV-Import akzeptiert
DATEV-Kontenplan-Exportformate.

### 4.9 Plattform-Querschnitt
- **Auth & Rollen:** OIDC (self-hosted, z. B. Keycloak/Zitadel). Rollen:
  Erfasser, Buchhalter, Steuerberater, Mandanten-Admin.
- **Observability:** strukturierte Logs, Traces über die Pipeline-Schritte,
  Metriken (Dunkelverarbeitungsquote, ø Sekunden/Beleg, Korrekturrate pro
  Kreditor) — dieselben Zahlen sind auch Produkt-Features der Workbench.
- **Security:** mTLS intern, Verschlüsselung at rest, Mandantentrennung
  getestet (RLS-Tests), Pen-Test vor Pilot mit externen Daten.

---

## 5. Tech-Stack (Zusammenfassung)

| Schicht | Wahl | Begründung |
|---|---|---|
| iOS-App | Swift, SwiftUI, VisionKit/Vision | natives Capture-Erlebnis ist das Produkt; On-Device-OCR ohne Fremd-SDK |
| Backend | Python (FastAPI) als modularer Monolith | gleiche Sprache wie ML-Pipeline, schnelle Iteration; Typing strikt |
| GPU-Worker | vLLM + Qwen2.5-VL, PaddleOCR/docTR | self-hosted auf H200, austauschbar hinter Lane-Interface |
| Datenbank | PostgreSQL (+ RLS, Queue via SKIP LOCKED) | ein System für Daten, Queue, Volltext; weniger Betrieb |
| Objektstore | MinIO/Garage mit Object-Lock | WORM für GoBD, S3-API, on-prem |
| Web | React + TypeScript | Workbench-Dichte + Team-Verfügbarkeit |
| Auth | Keycloak/Zitadel (OIDC) | self-hosted, Mandantenfähig |
| Infra | Docker/Kubernetes on-prem, IaC, CI mit Golden-File- und Korpus-Tests | Reproduzierbarkeit; „Daten bleiben im Haus" |

---

## 6. Phasenplan

Team-Annahme: 3–4 Entwickler (1 iOS, 1–2 Backend/ML, 1 Full-Stack/Web) +
Design. Phasen überlappen; Wochen sind Richtwerte, keine Zusagen.

### Phase 0 — Fundament (Woche 1–3)
Monorepo, CI/CD, Umgebungen (dev/staging), Auth + Mandantenmodell,
Datenmodell v1, Objektstore mit WORM, Audit-Log-Grundgerüst.
**Belegkorpus + Benchmark-Harness aufsetzen** (kritischster Einzelpunkt).
✅ *Meilenstein: Beleg per API hochladen → liegt versioniert + gehasht im Archiv.*

### Phase 1 — Extraktion (Woche 3–8)
OCR-Lane A, VLM-Lane B, Reconciliation, Summenprobe, §-14-Validierung,
Dubletten. Pipeline-Zustandsmaschine + Provenance-Daten.
✅ *Meilenstein: ≥ 95 % Feld-Accuracy auf dem Korpus für gedruckte Rechnungen; Bons gemessen und Baseline dokumentiert.*

### Phase 2 — iOS-Capture (Woche 4–10, parallel)
VisionKit-Capture mit Auto-Auslösung, On-Device Instant Reading,
Offline-Queue, Upload. Design-Umsetzung nach Prototyp (Motion-Momente,
Siegel, reduced-motion).
✅ *Meilenstein: Capture → Bounding-Boxes < 1 s on-device → Beleg im Server-Archiv.*

### Phase 3 — Kontierung & Routing (Woche 8–13)
Historie-Matcher, Regel-Engine, KI-Lane, Confidence-Kalibrierung,
Routing-Schwellen, Lernschleife aus Korrekturen. SKR03/04-Stammdaten,
Kontenplan-CSV-Import.
✅ *Meilenstein: auf Korpus-Replay ≥ 60 % Dunkelverarbeitung bei < 2 % Fehlkontierung der Auto-Route.*

### Phase 4 — Review & Siegel (Woche 10–15)
Mobiler Kontierungs-Editor (Split-View, Fuzzy-Suche, Abweichung),
Belegliste + Detail/Provenance, Merkle-Batching + RFC-3161-Zeitstempel,
Siegel-UI. Beginn Verfahrensdokumentation.
✅ *Meilenstein: kompletter Loop am echten Gerät: erfassen → prüfen → gesiegelt.*

### Phase 5 — DATEV-Export & Pilot (Woche 14–18)
Vollständiger EXTF-Writer (CP1252, Festschreibung), Golden-File-Tests,
Import-Test in echter DATEV-Umgebung, Stapel-UI, Export-Fixierung.
**Pilot mit 2–3 Mandanten + deren Steuerberater.**
✅ *Meilenstein (= MVP-Abnahme): Pilot-Steuerberater importiert einen echten Monatsstapel fehlerfrei.*

### Phase 6 — v1.0-Ausbau (Woche 18–26)
Desktop-Workbench mit Tastatur-Queue, E-Rechnungs-Ingestion
(XRechnung/ZUGFeRD), Batch-Capture, Onboarding komplett, Fehler-States,
Pen-Test, Betriebs-Runbooks.
✅ *Meilenstein: Kanzlei arbeitet eine Review-Queue mit ø < 15 s/Beleg ab.*

### Danach (v1.x)
DATEV Buchungsdatenservice, Android, E-Mail-Ingestion,
Steuerberater-Portal (Multi-Mandanten), Auswertungen.

---

## 7. Risiken & Gegenmaßnahmen

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| Extraktionsqualität bei Bons/Thermopapier überschätzt | Kern-Versprechen wackelt | Korpus + Benchmark ab Woche 1; VLM-Lane früh testen; Confidence ehrlich routen statt schönrechnen |
| EXTF-Import scheitert an Details (Kodierung, BU-Schlüssel, Festschreibung) | Pilot platzt beim Steuerberater | Golden-File-Tests, früher Import-Test in echter DATEV-Instanz (Phase 5 beginnt mit dem Test, nicht endet damit) |
| Fehlkontierung in der Auto-Route | Vertrauensverlust, Haftungsfrage | konservative Schwellen zum Start, Kalibrierungs-Monitoring, Stichproben-UI für Steuerberater, alles nachvollziehbar (Provenance) |
| GoBD-Anspruch „unveränderbar" hält Prüfung nicht stand | Compliance-Kernclaim fällt | WORM + Merkle + externer Zeitstempel; Verfahrensdoku parallel; früh fachliche Review (Wirtschaftsprüfer/StB) einholen |
| DATEV-API-Zugang verzögert sich | v1.x-Feature rutscht | CSV-Export ist vollwertiger Pfad, kein Blocker (bewusste Architekturentscheidung) |
| Scope-Sog Richtung „eigene Fibu" | Fokusverlust | Scope-Grenze in Abschnitt 1 ist Teamvertrag |

**Offene Fragen (vor Phase 3 klären):**
1. Pilot-Partner: welche 2–3 Mandanten, welcher Steuerberater?
2. Hosting-Zusage konkret: eigene H200-Infrastruktur ausreichend dimensioniert
   für Ziel-Mandantenzahl (Belege/Tag)?
3. Rechtliche Prüfung des Siegel-Konzepts (reicht RFC 3161, oder qualifizierte
   Signatur für bestimmte Kunden?).

---

## 8. Sofortige nächste Schritte

1. Belegkorpus starten: 200+ echte, anonymisierte Belege sammeln und labeln
   (Ground-Truth-Schema definieren).
2. Monorepo-Struktur anlegen (`backend/`, `ios/`, `web/`, `docs/`), CI mit
   Lint + Tests, Phase 0 beginnen.
3. EXTF-Spezifikation (DATEV-Format v13) beschaffen und den Writer als
   erstes „hartes" Modul mit Golden-File-Tests bauen — er ist klein,
   risikoreich und blockiert den Pilot.
4. Prototyp-Hygiene: Fonts self-hosten, `index.html`-Duplikat durch Redirect
   ersetzen (der Prototyp bleibt als Design-Referenz und Demo erhalten).
