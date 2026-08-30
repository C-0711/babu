# babu — Beleg App

Automatische Belegkontierung für den deutschen Mittelstand.
Foto → Vision liest auf dem iPhone → Gemma bucht (strict JSON, SKR03/04) → Ablage/Einsortierung → DATEV EXTF-Export.
Aktueller Einstieg: `HANDOVER.md`.

## Struktur
- `ios/` — native iOS-App (SwiftUI): echtes VisionKit-Scannen, On-Device-OCR, SHA-256-Siegel, EXTF-Share — siehe `ios/README.md`
- `prompts/design-prompt-kontierung-app.md` — vollständiger Design-Prompt (Screens, States, Token-System)
- `docs/build-plan.md` — Bauplan für die vollständige Anwendung (Architektur, Teilsysteme, Phasen, Risiken)
- `design/unlimited-ocr/` — Design-Templates „Unlimited-OCR" (Mobile-Flow, Desktop-Reader, Workbench-Shell) — die maßgebliche Designsprache

## Der Klick-Prototyp ist Geschichte

`index.html`, `app/belegapp.html` und `app/workbench.html` waren der
self-contained Klick-Dummy vom 06.08.2026 nach dem Design „Unlimited-OCR
Mobile". Er beschrieb eine Architektur mit zwei Lesungen (Gerät gegen
Server, „Dual-Lane", Merkle-Siegel, Confidence-Routing), die mit dem
Zielbild vom 26.08.2026 abgeschafft wurde: babu liest EINMAL, auf dem
iPhone. Weil der Dummy über GitHub Pages öffentlich auslieferte, was es
nicht mehr gibt, ist er entfernt worden.

Letzter Stand: Commit `d459c64`. Wiederherstellen mit
`git show d459c64:index.html`.

Teil der 0711 Intelligence Platform.
