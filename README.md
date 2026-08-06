# babu — Beleg App

Automatische Belegkontierung für den deutschen Mittelstand.
Capture → Instant Reading → Kontierung (SKR03/04) → Confidence-Routing → Merkle-Siegel → DATEV EXTF-Export.

## Struktur
- `app/belegapp.html` — lauffähiger Prototyp (self-contained, einfach im Browser öffnen); Umsetzung des Designs „Unlimited-OCR Mobile“ ([Claude Design](https://claude.ai/design/p/19608eb7-6194-41ad-8d9a-316889231908?file=Unlimited-OCR+Mobile.dc.html&via=share))
- `app/workbench.html` — Desktop-Workbench: Review-Queue für Buchhalter/Steuerberater (Tastatur-Bedienung: j/k, Enter, 9/8/0, /)
- `ios/` — native iOS-App (SwiftUI): echtes VisionKit-Scannen, On-Device-OCR, SHA-256-Siegel, EXTF-Share — siehe `ios/README.md`
- `prompts/design-prompt-kontierung-app.md` — vollständiger Design-Prompt (Screens, States, Token-System)
- `docs/build-plan.md` — Bauplan für die vollständige Anwendung (Architektur, Teilsysteme, Phasen, Risiken)
- `design/unlimited-ocr/` — Design-Templates „Unlimited-OCR" (Mobile-Flow, Desktop-Reader, Workbench-Shell) — die maßgebliche Designsprache

Teil der 0711 Intelligence Platform.
