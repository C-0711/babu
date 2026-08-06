# Unlimited-OCR — Design-Templates

Export aus dem Claude-Design-Projekt
[„Unlimited-OCR Mobile"](https://claude.ai/design/p/19608eb7-6194-41ad-8d9a-316889231908?file=Unlimited-OCR+Mobile.dc.html&via=share).
**Diese Designsprache ist die Leitlinie für die Beleg-App** (Entscheidung 08/2026):
warme Papier-Palette (`#efece6` Desk, `#857b61` Bronze-Akzent, `#6f8a6e` ok,
`#b0821f` warn), Playfair Display (Display-Serif) + Inter (UI) + SF Mono (Werte).
Token-System als CSS-Variablen `--gc-*` in `Unlimited-OCR App.html` und
`Dokument-Reader.html`.

Die `.dc.html`-Dateien sind interaktive Claude-Design-Komponenten und brauchen
`support.js` (Runtime) bzw. `ios-frame.jsx` (iPhone-Rahmen) im selben Ordner.
`Dokument-Reader.html` und `Unlimited-OCR App.html` laufen standalone im Browser
(`reader-data.js` liefert Demo-Inhalte).

## Inventar & Zuordnung zur Beleg-App

| Template | Inhalt | Passt zu |
|---|---|---|
| `Unlimited-OCR Mobile.dc.html` | iPhone-App: Dokumente-Liste, Scan (Eck-Marker, Einrasten, Sweep), Live-Parse-Stream, **„Prüfen"** (Konflikt-Auflösung mit zwei Lesarten, Confidence-Balken + Zahl, Herkunfts-Tag, Begründung), Reader (Zwilling/Text/Felder/JSON), Server-Screen | Capture, Verarbeitung, One-Tap-Bestätigung + Gerät↔Server-Abweichung, Beleg-Detail/Felder, Belegliste |
| `Unlimited-OCR App.html` | Desktop-Vollapp: Header mit Upload + Modellwahl, komplettes `--gc-*`-Token-System | Shell der Desktop-Workbench |
| `Dokument-Reader.html` | Desktop-Reader: Modi Zwilling/Markdown/Blocks/Raw, Thumbnail-Spalte, Zoom, Seitennavigation | Beleg-Viewer (linke Hälfte des Kontierungs-Editors) |
| `Live Parse Demo.dc.html` | Split-View: Quellseiten mit Layout-Boxen links, Live-Stream/Reader rechts | Quelle↔Ergebnis-Kopplung der Workbench, Demo |
| `GitChain Connect.dc.html` | Variantensammlung Verbindungs-Flow (lokal vs. Sovereign Cloud, 1a–1c/2a–2b) | Onboarding/Server-Einstellungen, Siegel-/Archiv-Erzählung |

**Noch ohne Template (kommt aus dem Beleg-Prototyp, wird auf diese Optik
umgezogen):** Kontierungs-Formular (Sachkonto-Suche, Steuerschlüssel,
Buchungssatz), EXTF-Export-Screen, SKR-Onboarding.

Hinweis: Die Templates laden Fonts vom Google-CDN — fürs Produkt werden die
Schriften self-hosted (DSGVO).
