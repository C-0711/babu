# Spec: Landing-Page, öffentlicher Babu-Chat, Onboarding, Briefe & Konto

Stand 18.08.2026 · Auftraggeber-Branch: `claude/project-understanding-f6f4ff`
(dort liegt die fertige Landing unter `server/landing/`) · Umsetzung der
Server-Teile: Portal-Branch `claude/project-handover-context-7bfaa2`
(babu_web.py — Golden-Test-Ritual vor jedem Deploy, Memory `babu-salon-portal`).

## Kontext

babu.0711.io hat seit 18.08. eine Landing-/Marketing-Page als Startseite
(deployed als statisches `~/babu-web/index.html`, Backup:
`index.html.vor-landing-20260818`). Sie erklärt babu in einfacher Sprache,
verlinkt /portal, enthält den Profi-Upload (POST /ablage, unverändert) und ein
Babu-Chat-Widget. Fünf Server-Aufträge machen daraus das volle Erlebnis.

## Auftrag 1 — Landing in den Portal-Branch übernehmen (SOFORT)

Die Quelle `server/landing/index.html` (+ `bilder/`, + `index-deploy.html`
mit eingebetteten data-URI-Bildern) aus dem Branch
`claude/project-understanding-f6f4ff` in den Portal-Branch kopieren und in den
Deploy-Ablauf aufnehmen. **Sonst überschreibt das nächste Portal-Deploy die
Live-Startseite wieder mit der alten Upload-Seite.**
Optional besser: kleine Static-Route `GET /bilder/{name}` (Allowlist png,
kein `..`) — dann kann die normale `index.html` statt der 500-KB-Inline-
Variante deployed werden.

## Auftrag 2 — Öffentlicher Babu-Chat `POST /api/babu-chat`

Das Landing-Widget ruft bereits `POST /api/babu-chat` mit
`{"frage": "...", "stream": true}` und erwartet SSE im Golden-Format
(`data: {"d": "…"}` / `data: [DONE]`, Fehler als `data: {"fehler": "…"}`).
Bis der Endpoint existiert, fällt das Widget auf eingebaute Antworten zurück.

- OHNE Auth, aber: Rate-Limit je IP (~10/min, In-Process reicht),
  Frage ≤ 500 Zeichen, Origin-Check auf BABU_ORIGIN.
- Backend Gemma :11435 wie /chat, Route SYNC (`def`, nicht `async def` —
  Event-Loop-Lektion aus Commit d92260a).
- System-Prompt NEU (nicht der private): erklärt babu, das Kassenbuch,
  Steuerberater-Wechsel und Steuer-Grundbegriffe in einfacher Sprache
  (Hauptschul-Niveau, du-Form); KEINE individuelle Steuerberatung, bei
  konkreten Einzelfällen auf Anmeldung/Einrichtung verweisen.
- **NIEMALS `belegdaten_kontext()` einbinden** — private Belegdaten bleiben
  hinter dem Login. Der öffentliche Bot kennt nur babu, nicht die Nutzer.

## Auftrag 3 — Registrierung light + Steuerdaten-Onboarding

Nach dem ersten Login (`/portal`) eine Einrichtung-Strecke `#einrichtung`
im Kassenbuch-Stil: EINE Frage pro Schritt, große Schrift, Fortschritt
(„Noch 5 Angaben"), alles überspringbar und später änderbar:

1. Wie heißt dein Salon? (`betrieb_name` — existiert schon)
2. Rechtsform (Auswahl: Einzelunternehmen / GbR / GmbH / UG / weiß nicht)
3. Steuernummer (Format-Hinweis, optional „hab ich nicht zur Hand")
4. Zuständiges Finanzamt (Freitext)
5. Bist du Kleinunternehmerin (§19)? (ja/nein/weiß nicht — bei „weiß nicht"
   Ein-Satz-Erklärung)
6. Hast du schon einen Steuerberater? (ja → Auftrag 4 anbieten)

Speicherung: `einstellungen`-Tabelle, `EINSTELLUNG_SCHLUESSEL` erweitern um
`rechtsform, steuernummer, finanzamt, kleinunternehmer, steuerberater_status`.
Werte fließen später in EXTF (`BABU_BERATER`/`BABU_MANDANT`-Ablösung) und in
die Beleg-Einschätzung (§19 → keine Vorsteuer).

## Auftrag 4 — Steuerberater-Wechsel / Buhl-Übergabe

Checklisten-Flow im Portal (Status je Schritt, sichtbar unter #einrichtung):
Kündigungsvorlage (Text zum Kopieren), Vollmacht (PDF-Vorlage, Upload des
unterschriebenen Scans über den bestehenden Dokumentenkanal,
`art: "vollmacht"`), Status „Übergabe läuft / Unterlagen da / fertig".
Copy-Grundlage: Landing-Sektion „Der Wechsel ist leichter, als du denkst"
und FAQ. Buhl als steuerliches Backend benennen.

## Auftrag 5 — Finanzamt-Brief-Erklärer + Steuerkalender

- Upload: bestehender Dokumentenkanal, neue Art `behoerde` (App fotografiert
  später direkt — Dokumentklasse statt Beleg).
- Verarbeitung: OCR (vorhandene Lane) + Gemma-Erklärung in einfacher Sprache
  (3 Sätze: Was ist das? Was musst du tun? Bis wann?) + Fristen-Extraktion.
- NEU Fristenmodell: `fristen/<jahr>.json` in der Box
  (`[{datum, titel, quelle, erledigt}]`) mit Standardfristen (Belege bis 5.
  des Folgemonats, USt-VA 10., ggf. Dauerfristverlängerung) + Brieffristen.
- API: `GET /api/fristen/{jahr}` (Session/Bearer) — die iOS-App blendet die
  Fristen dann im Kassenbuch-Kalender ein (App-Teil macht der
  Auftraggeber-Branch selbst, sobald die API steht).

## Auftrag 6 — Konto generisch (CSV)

Zusätzlich zum Sparkassen-PDF: CSV-Upload `POST /api/kontoauszug-csv`
(Semikolon/Komma-Erkennung, Spalten-Mapping Datum/Betrag/Verwendungszweck,
deutsche Beträge), gleicher Abgleich wie heute (`kontoauszug.abgleich`).
„Konto direkt anbinden" (FinTS) bleibt dokumentierter späterer Schritt —
die Landing-FAQ formuliert das bereits ehrlich.

## Abnahme

- babu.0711.io zeigt die Landing auch nach einem Portal-Deploy noch.
- `curl -X POST babu.0711.io/api/babu-chat -d '{"frage":"Was ist babu?"}'`
  antwortet als SSE; 11. Anfrage/min → 429.
- Einrichtung-Strecke speichert und zeigt Werte in #einstellungen.
- Test-Brief hochladen → Einfach-Erklärung + Frist erscheint in
  `GET /api/fristen/2026`.
- CSV mit 3 Testumsätzen → Abgleich findet den fehlenden Beleg.
