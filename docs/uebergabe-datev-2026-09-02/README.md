# Übergabe DATEV-Sitzung, 02.09.2026

Die Sitzung brach um 18:28 mitten im Planungsmodus ab. Dieser Ordner hält fest,
was aus dem Transkript gerettet wurde, damit die Planung ohne Neuanfang weitergeht.

## Was bereits auf main liegt (deployt, Suite 1608 grün)

- `ac0bf64` 19:45 — Buchungsstapel trägt beide Seiten (Kassenblätter als
  Tageseinnahmen, Geldtransit 1460, Kleinunternehmerin 4184); 183 Automatikkonten
  aus dem SKR04-PDF (`skr04_automatik.py`), kein BU-Schlüssel auf AV/AM-Konten.
- `39b14c6` 19:55 — Einlesen netto statt brutto, alte Historie-Stände werden aus
  den Originalen nachgelesen. Erster Fremdtest: Ninas Kanzlei-Stapel April 2026.
- `d163ac6` 20:11 — ganzer SKR04 2026 als `skr04_konten.py` (1.516 Konten) plus
  Test `test_skr04_konten.py`.

## Der offene Auftrag (18:15, `00-auftrag.md`)

1. SKR04-Konten komplett auslesen und als Embeddings im Kontext verfügbar machen.
2. Alle DATEV-Themen im Frontend und Backend hochladen, sortiert, in den Kontext
   (Chat und Buchungs-Prompt).
3. Pro-Zugang für Steuerberater, die im Backend hunderte Mandanten verwalten.
   Nachgeschoben: Postgres deployen falls nötig, alles in Docker.
4. 26 Portal-Befunde, Reihenfolge laut Auftrag: 1+2+3, dann 4, dann 6, dann 5,
   dann der Rest.

## Stand der Planung

- Drei Erkundungen sind fertig (`01`–`03`): Kompendium-Format samt harter
  Invariante (Zeilen in `atome.jsonl` == Zeilen in `vektoren.npy`, sonst schweigt
  das Kompendium), alle Ein-Box-Annahmen im Rollenmodell, Code-Stellen hinter den
  P0/P1-Befunden.
- Drei Planaufträge (`10`–`12`) waren gestartet, als die Sitzung abbrach. Sie
  wurden am Abend erneut ausgeführt (Sonnet), Ergebnisse in `20`–`22`.
- `30-gesamtplan.md` ordnet die drei Pläne in eine Reihenfolge und listet die
  Entscheidungen, die vor dem Bauen beim Auftraggeber liegen.

Die Erkundungen sind Agenten-Ausgaben mit Zeilennummern vom Stand `d163ac6`.

## Umsetzungsstand (Branch `claude/session-context-210439`)

Welle 1, 02.09. abends, fünf Agenten parallel, alles auf dem Branch, Suite 1680 grün:

- Rollen-Fallback fail-closed (Plan 21, Phase 0).
- P0-1, P0-2, P0-3 (Plan 22, Runde 1): eine Kategorie und eine Ausgaben-Zahl
  überall, gedruckte Steuerzeilen gewinnen (Server, Prompt, iOS), Export-Summe.
- Wissensschicht Phasen 2–6 (Plan 20): Modul `datev_wissen.py`, Fach „Wissen",
  `POST /api/wissen`, Suche in Chat und Buchung, Portal-Upload.
- Wissensschicht Phasen 1 und 7: Host-Skript `werkzeuge/kompendium/skr04_atome_bauen.py`
  (noch NICHT auf der H200V gelaufen) und `werkzeuge/wissen-import/datev_ordner_hochladen.py`.
- P1-7, P1-8, P2 9–16 und 19–20 (Plan 22, Runden 5 und 6). Offen: 17, 18.

Welle 2 läuft: P0-4 „Wird gelesen" + P3-26, Runde 3 (Kassenbuch, Rechnung,
Termine-Woche, Salon-Check-Korrektur). Danach Runde 4 (Desktop-Layout).

**Deployt 02.09. 21:50** (main `c6a2ed6`, Freigabe des Auftraggebers): Golden vorher/nachher
unter `~/golden/` auf der H200V, `/api/abgleich/*` byte-identisch, `/api/belege` weicht
in 392 Zeilen ab, alle `belegart` (vorher null, jetzt Kategorie — der P0-1-Fix).
Sicherung `~/backups/babu-docker-vor-deploy-20260902-2148.tgz`. Live geprüft:
`/api/ich` (`hat_passwort`), `/api/monat` (`export`), `/api/monatsabschluss`
(`aus_vertrag`), `/api/wissen/status`, `/portal` (neue Funktionen im Bundle),
Container-Log ohne Fehler.

**Kompendium-Rebuild 02.09. 21:57** auf dem Host gelaufen: Skript liegt unter
`~/babu-werkzeuge/werkzeuge/kompendium/` (Symlink `~/babu-werkzeuge/server -> ~/babu-docker`
stellt die Repo-Struktur nach). 89.760 → 91.459 Atome (1.699 SKR04), Invariante geprüft,
Sicherungen `~/kompendium/*.bak-20260902-215704`, Kontenübersicht (27 Kategorien) in
`kontierung-grundwissen.md`, Container neu gestartet, Laden im Container verifiziert.

**Produktiv-Vorfall und Fix, 02.09. 22:15** (Commit `87624ec`): der erste
DATEV-Upload-Versuch hat den Container abstürzen lassen — `pypdfium2` ist
zwischen Threads nicht threadsicher, und seit `_wissen_job` PDFs im
Hintergrund liest, überlappte das mit anderen Anfragen. Docker startete
den Prozess automatisch neu, acht von zehn Uploads blieben aus. Fix:
`PDFIUM_LOCK` in `abschluss_lesen.py`, geteilt mit `kontoauszug.py` und
drei Inline-Stellen in `babu_web.py`. `tests/test_pdfium_lock.py` beweist
es: ohne Schloss crasht der dritte parallele Testlauf zuverlässig
(`Fatal Python error: Aborted`), mit Schloss fünf von fünf grün. Deployt,
Golden byte-identisch, alle zehn DATEV-Dokumente danach erfolgreich
hochgeladen und eingelesen (zwei hängende aus dem Absturz per Hand über
die bestehende `_wissen_job`-Funktion nachgeholt, kein neuer Code dafür).

Noch nicht: der iOS-Build auf Ninas iPhone (P0-2-Anteil in `Store.swift`) — auf
Wunsch des Auftraggebers später. Der Getränkemarkt-Beleg wurde nicht nachgestellt
(Rohdaten nur lokal).
