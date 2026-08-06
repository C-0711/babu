# Beleg — native iOS-App

Die echte Apple-App zum Demo-Stack: SwiftUI, im Unlimited-OCR-Design
(identische Farb-Tokens wie die Web-App, New-York-Serif für Display,
SF Mono für Werte).

**Im Unterschied zur Web-Demo ist hier alles echt:**

| Baustein | Umsetzung |
|---|---|
| Capture | `VNDocumentCameraViewController` (VisionKit) — Live-Kantenerkennung, Auto-Auslösung, Zuschnitt, Entzerrung |
| Instant Reading | On-Device-OCR mit dem Vision-Framework (`VNRecognizeTextRequest`, de-DE) — keine Cloud, Bilder verlassen das Gerät nicht |
| Feld-Extraktion | Heuristischer Parser (`FeldParser.swift`): Lieferant, Belegnummer, Datum, Netto/USt/Brutto inkl. Summenprobe auf deutschen Beträgen |
| Kontierung | Engine deterministisch vor generativ: Kreditor-Historie → Regeln → Fallback, mit Confidence-Routing (≥ 95 automatisch, 80–94 bestätigen, < 80 prüfen) |
| Siegel | Echte SHA-256-Hashes über CryptoKit, Zeitstempel, kopierbar im Provenance-Panel |
| Export | EXTF-Stapel als **CP1252-kodierte** Datei über das Share-Sheet (vereinfachtes Format — der v13-Writer ist Phase 5 des Bauplans) |

## Bauen & Ausführen

1. `ios/Beleg/Beleg.xcodeproj` in **Xcode 16 oder neuer** öffnen
   (das Projekt nutzt synchronisierte Ordner; für älteres Xcode:
   `brew install xcodegen && cd ios/Beleg && xcodegen generate`).
2. Unter *Signing & Capabilities* das eigene Team wählen (Bundle-ID
   `io.0711.beleg` ggf. anpassen).
3. Auf einem **echten iPhone** ausführen (⌘R) — der Dokument-Scanner
   braucht die Kamera. Im **Simulator** gibt es stattdessen den Button
   „Demo-Beleg einlesen": er rendert eine Beispielrechnung als Bild und
   schickt sie durch dieselbe echte OCR-Pipeline.

Mindestziel iOS 17. Keine Abhängigkeiten, kein Backend — alles läuft
on-device. Verteilung an Tester später über TestFlight.

## Struktur

```
Beleg/
  BelegApp.swift      App-Einstieg, Tabs
  Theme.swift         GC-Design-Tokens (Unlimited-OCR)
  Models.swift        Beleg, Kontenplan (SKR04), Siegel (SHA-256), Demo-Archiv
  FeldParser.swift    OCR-Zeilen → Felder + Kontierungs-Engine
  OCRService.swift    Vision-OCR + Simulator-Demo-Beleg
  ScannerView.swift   VisionKit-Dokumentenscanner (UIKit-Bridge)
  CaptureTab.swift    Erfassen → Prüfschritte → Ergebnis-Karte mit Routing
  ReviewSheet.swift   Kontierungs-Editor (Fuzzy-Suche, Steuerschlüssel)
  ListeView.swift     Belegliste, Filter, Detail mit Provenance
  ExportView.swift    EXTF-Vorschau, Share, Fixierung
  OnboardingView.swift SKR03/04-Wahl
```
