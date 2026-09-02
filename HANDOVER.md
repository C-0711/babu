# HANDOVER — babu / Beleg-App mit Salon-Portal

Für einen frischen Agenten oder Entwickler. Stand: 02.09.2026 abends.
Sprache in UI und Commits: Deutsch.

## 1. Mission & Stand

Beleg-App für einen **Beauty-Salon** (Zielnutzerin: Nina, Inhaberin, erfasst
Belege zwischen zwei Terminen). Seit 26.08.2026 gilt das **Zielbild: EINE
Lesung, keine Zweitspur** — die komplette Kette läuft produktiv:

```
Kamera (eigener Sucher, Auto-Auslösung mit Plausibilitäts-Gates, Entzerrung)
  → Apple Vision liest auf dem iPhone ({text, conf, box} — Geometrie in % vom Blatt)
  → POST /api/buchung/einschaetzung: Server reichert an (Profil, ungedeckte
    Abbuchungen des Monats, Verträge/Personal, Kontenkatalog) → Gemma (vLLM,
    Text) antwortet strict JSON mit Pflichtfeld dokumentklasse
  → Fragen ↔ Antworten (max. eine Runde Rückfragen) → Buchung
  → DANACH Upload: multipart /api/aufnahme (Foto + Text + Ergebnis-JSON);
    Server sortiert nach Gemmas Klasse ein, schreibt review/<stamm>.json
    (engine "Vision (Gerät) + Gemma"), meldet Doppelgänger
  → Die Belegbox ist reines Archiv. Das Bild fasst kein System mehr an
    (nur die Portal-Vorschau rendert es zur Ansicht).
```

Seit 02.09.2026 kommt eine zweite Säule dazu: **DATEV-Wissen im Kontext.**
Die SKR04-Konten liegen als durchsuchbare Atome im Kompendium, DATEV-
Referenzdokumente lassen sich hochladen und landen in Chat und Buchungs-
Prompt (Details Abschnitt 8).

**Was es NICHT mehr gibt** (gelöscht 27.08., nicht wieder einbauen):
`review_watcher.py` (pm2 `belegreview`), `belegdeutung.py`,
`leseprotokoll.py`, `doc_classify.py`, der App-FeldParser im Buchungsweg,
das Kontierung-Enum, `POST /review/<stamm>/neu-lesen` und
`POST /review/<stamm>/buchungsfragen`. Paddle-OCR (:7833) ruft babu gar
nicht mehr (seit 27.08. liest auch die Abschluss-Lane Scans über Gemma) —
der Dienst gehört ctax.

**UI-Sprachregel (verbindlich):** Kein Technik-Vokabular, keine Systemnamen,
keine Geräte-/Server-Behauptungen, kein „Erst-/Zweitlesung"-Vokabular, kein
„Embedding"/„Vektor"/„Atom" in sichtbarem Text (heißt dort „Nachschlagewerk"/
„eingelesen"/„Absätze"). Vertrauen = **ein grüner Haken**. Kein Hex-Hash in
der Oberfläche.

## 2. ⚠️ Betrieb: dieser Branch ist die Quelle

Produktiv auf der H200V ist `main`, Stand **`87624ec`** (02.09. 22:15).
**babu-web läuft seit 27.08.2026 als Docker-Container** (Quelle
`server/docker/`: host network, User 1001:1000, Volumes `~/babu-web` rw +
`~/inspektor-store` ro + PAT ro + Gemini-Env ro; Build-Kopie `~/babu-docker/`).
Deploy-Ritual: Golden vorher (`/api/belege` + `/api/abgleich/<monat>`) →
`rsync server/ h200v:~/babu-docker/` → `docker compose build && up -d` →
Golden nachher byte-diffen → Live-Rauchtest. In pm2 bleiben `babu-eingang`
und `babu-tunnel`; der pm2-Eintrag `babu-web` ist gestoppt und dient nur
als Rückweg (`docker compose down` + `pm2 start babu-web`). **Nie anfassen:**
`insp-app` (Belegbox-Gateway :7808) und `belege-review` (ANDERES Projekt).

**⚠️ pypdfium2 ist zwischen Threads nicht threadsicher** (Vorfall 02.09.,
siehe Abschnitt 8) — jeder `pdfium.PdfDocument`-Zugriff läuft über
`abschluss_lesen.PDFIUM_LOCK`. Neuer Code, der PDFs liest, MUSS dieses
Schloss mitbenutzen, sonst crasht der Container unter Last erneut.

- Unlesbar entscheidet die App selbst (zu wenig Vision-Text → „bitte neu
  fotografieren"); es gibt keinen Server-Stub mehr für neue Belege.
- **EXTF-v13-Export existiert serverseitig** (`GET /api/export/{monat}.csv`,
  Rolle „kanzlei"). Die App bekommt KEINEN eigenen v13-Writer.
- Dublettenwache: byte-gleicher Upload wird abgewiesen; gleicher Beleg neu
  fotografiert → Doppelgänger-Hinweis in der App.
- Kontoauszüge (PDF) laufen weiter übers Portal; der Monat wird aus dem
  Auszug selbst bestimmt (`kontoauszug.py`), Belegabgleich je Monat mit
  Checkliste in App und Portal. Der Titel in der Ablage wird seit 02.09.
  aus Monat+Bank synthetisiert statt den Rohdateinamen zu zeigen.
- Rollen-Fallback ist seit 02.09. **fail-closed**: leere `BABU_ROLLEN`
  ergibt „salon", nicht mehr „kanzlei".

## 3. Meldeschleife (Nina → GitLab → autonomer Fix)

App-Rückmeldeknopf (+Screenshot) → Issue in **gitlab.0711.io, Projekt
`0711/babu`** (Label `von-nina`) → launchd-Fixlauf auf dem Mac alle 30 min
(`werkzeuge/fixlauf/`, Leitplanke deterministisch) → Deploy → Label
`zur-abnahme` → Nina gibt in der App unter „Meine Meldungen" frei.
Details: Memory `babu-meldeschleife`.

## 4. iOS-App (`ios/Beleg/`, SwiftUI, iOS 17, keine Dependencies)

| Datei | Zweck |
|---|---|
| ScannerView + CameraController/DocumentDetector/AutoCaptureGate/LiveFieldsReader/CaptureOverlayView/Dewarper | eigener Sucher, Gates, Live-Chips, Entzerrung; erholt sich nach Anruf |
| OCRService | Vision-Lesung inkl. Geometrie (`geoZeilen`/`geoJson`: {text, conf, box}) |
| FeldParser | nur noch Anzeige-Helfer für Live-Chips/Feld-Editor (`parse`, `parseBetrag`, `datumPlausibel`) — KEINE Kontierung mehr |
| Store | Persistenz, Hüllen-Beleg nach Aufnahme, Upload erst nach Buchung/Aufgabe, `ablageErgebnisSetzen`, Audit-Stempel. Seit 02.09.: `gemmaBuchungAnwenden` lässt Gemmas Steuertabelle vor der blinden Brutto-Rückrechnung gewinnen (P0-2, Pfand-Fehler behoben) |
| AblageService | `einschaetzung` (zeilen+profil+monat), `aufnahme` (multipart mit ergebnis), Review-Abruf, Chat-SSE, Keychain |
| BuchungsfragenView | Fragen ↔ Antworten mit Gemma, löst danach den Upload aus |
| ListeView/DetailView | grüner Haken, Feld-Editor, Lösch-Rückfrage; Review wird angezeigt, überschreibt nie lokale Buchungen |
| RueckmeldungView | Meldeknopf + „Meine Meldungen" (Meldeschleife) |

Tests: `ios/Tests/run.sh` (swiftc-Harnesse) — **Fixtures pflegen, nicht
löschen**. Server-Suite: `/tmp/babu-venv/bin/python -m pytest tests/` aus
`server/belegreview/` heraus (Python 3.12; Memory `babu-testumgebung`).
Aktueller Stand: **1684 Tests grün** auf main (`87624ec`).

**Offen:** der iOS-Build mit dem P0-2-Fix ist im Simulator geprüft
(BUILD SUCCEEDED), aber noch NICHT auf Ninas iPhone installiert — auf
ausdrücklichen Wunsch „später" verschoben.

## 5. Zugänge & Bauen

- Upload-PAT: `ssh h200v 'cd ~/gitchain-eingang && .venv/bin/python pat_minten.py --zeigen --geraet "<Name>"'`
  (Code binnen 10 min auf gitchain.de/auth/device). Keychain-only.
- Simulator: `xcodebuild -project ios/Beleg/Beleg.xcodeproj -scheme Beleg -destination 'platform=iOS Simulator,name=iPhone 16e' -derivedDataPath /tmp/bsim build`
- Ninas iPhone: `… 'generic/platform=iOS' DEVELOPMENT_TEAM=8L87Z2GRSG CODE_SIGN_STYLE=Automatic -allowProvisioningUpdates -derivedDataPath /tmp/bbuild` +
  `xcrun devicectl device install app --device 00008130-001411E00146001C <Pfad>/Beleg.app` (WLAN wackelig — zweiter Versuch hilft, Kabel sofort; Memory `babu-app-auf-ninas-iphone`).
- H200V nur über OpenVPN (`ssh h200v`).
- DATEV-Bulk-Import: `werkzeuge/wissen-import/datev_ordner_hochladen.py --ordner <dir> --origin <url>`,
  PAT aus `BABU_PAT`-Umgebungsvariable oder Keychain-Eintrag `babu-pat`.
- SKR04-Atome neu bauen (nach DATEV-Jahreswechsel): auf dem HOST (nicht im
  Container), `werkzeuge/kompendium/skr04_atome_bauen.py` — braucht die
  Repo-Struktur `<basis>/server/belegreview/` daneben (auf der H200V per
  Symlink `~/babu-werkzeuge/server -> ~/babu-docker` gelöst). Danach
  zwingend `docker compose restart babu-web`, sonst bleibt der laufende
  Prozess auf dem alten Vektorstand.

## 6. Bekannte Fallen

1. Golden-Diff vor JEDEM Server-Deploy (Abschnitt 2).
2. **pypdfium2 ist nicht threadsicher** — jeder neue PDF-Lesepfad muss
   `abschluss_lesen.PDFIUM_LOCK` verwenden, sonst Absturzrisiko unter
   Hintergrund-Last (Vorfall 02.09., Abschnitt 8).
3. Simulator-Keychain ≠ iPhone-Keychain; App-Neuinstallation verliert die
   Keychain → Nina muss sich neu verbinden.
4. Alte zustand.json müssen laden: neue Beleg-/Zustand-Felder IMMER optional
   (Achtung Altlast: `ocrText` nicht-optional mit Default — Decodable nutzt
   Defaults NICHT).
5. pm2 ist gesichert (Dump + systemd-Unit). `~/babu-sichern.sh` spiegelt die
   Belegbox täglich (cron 3:17), aber auf dieselbe Maschine — ein Ziel
   außerhalb fehlt noch.
6. iOS-Merge-Falle: im Haupt-Checkout gebaut, im Worktree committet — vor dem
   Merge diffen (Memory `babu-ios-merge-falle`).
7. Push nie mit force: `git rebase origin/main` im Worktree, dann ff-Merge —
   der Fixlauf pusht parallel.
8. **Git-Stash ist repo-weit geteilt, nicht worktree-lokal.** Laufen mehrere
   Agenten/Sessions parallel und pusht jeder per `git stash push -u`, ändern
   sich die `stash@{n}`-Indizes unter der Hand. Immer per SHA ansprechen
   (`git stash list --format='%H %gd %gs'` merken, dann `git stash apply
   <SHA>`, nie `stash@{0}` blind), sonst landet fremder Inhalt im falschen
   Worktree (passiert am 02.09. zwei parallelen Subagenten — sauber
   auseinandergezogen, kein Verlust, aber Zeit gekostet). Memory
   `babu-agent-worktrees`.

## 7. Dokumente

- `docs/build-plan.md` — ursprünglicher Gesamtplan (historisch, siehe Banner)
- `docs/uebergabe-datev-2026-09-02/` — **Übergabe der DATEV-Sitzung vom
  02.09.**: Auftrag, Erkundungen, drei vollständige Umsetzungspläne
  (Wissensschicht, Pro-Zugang/Postgres, 26 Portal-Befunde) und ein
  laufend nachgeführtes Log, was davon bereits umgesetzt und deployt ist.
  Startpunkt: `docs/uebergabe-datev-2026-09-02/README.md`.
- `server/belegreview/README.md` — Serverseite, Belegbox-Zugriff, Löschen
- Zielschaubild: https://claude.ai/code/artifact/401286bc-c7a1-48a1-ae5a-c5f8c6a26c39
- Kalugahair-Protokoll (Ende-zu-Ende mit echten Daten): https://claude.ai/code/artifact/86db5f96-7dfb-44ca-b917-9a5a33e8cd17
- DATEV-Brücke (Plan): https://claude.ai/code/artifact/0ed0012b-032c-4c92-884b-dac9b2c108f4
- Memory: `babu-zielbild`, `babu-salon-portal` (Deploy-Ritual!),
  `babu-meldeschleife`, `babu-testumgebung`, `babu-testkorpus`,
  `babu-datev-quellen`, `babu-pdfium-threadsicherheit`, `babu-agent-worktrees`

## 8. Was am 02.09.2026 abends dazukam

Großer Auftrag um 18:15 (vier Teile: SKR04-Konten als Embeddings, DATEV-
Themen hochladen, Pro-Zugang für Kanzleien, 26 Portal-Befunde) — Details
und Pläne in `docs/uebergabe-datev-2026-09-02/`. Umgesetzt und **deployt**
(main `87624ec`):

- **Rollen-Fallback fail-closed**, P0-1 bis P0-3 (eine Ausgaben-Zahl
  überall, gedruckte Bon-Steuer gewinnt vor Rückrechnung, Export-Summe
  repariert), P1-7/P1-8, zehn P2-Kleinfixe.
- **Wissensschicht:** neues Ablage-Fach „Wissen", `POST /api/wissen`,
  Hintergrund-Einlesen, Suche in Chat UND Buchungs-Prompt zusätzlich zum
  Kompendium. 1.699 SKR04-Konten als Atome im Kompendium (89.760 → 91.459),
  alle zehn lokalen DATEV-Referenzdokumente hochgeladen und eingelesen.
- **Produktiv-Vorfall behoben:** der erste DATEV-Upload-Versuch hat den
  Container abstürzen lassen (pypdfium2-Race, siehe Abschnitt 2/6) —
  gefixt, getestet (`test_pdfium_lock.py` reproduziert den Absturz ohne
  das Schloss), deployt, Golden byte-identisch.

**Nicht deployt, als lokale WIP-Commits gesichert** (zwei Subagenten wurden
vor Fertigstellung gestoppt, Suiten dort jeweils grün, aber unvollständig
und ungeprüft im Detail):

- Worktree `agent-aafec4a8878dbba40` (Commit `10329f6`): P0-4 „Wird
  gelesen" — serverseitige Hintergrund-Lesung für Portal-Uploads
  (`/api/hochladen`, `/ablage`), Status „unlesbar" nach 20 Minuten ohne
  Review, `POST /api/beleg/{stamm}/erneut-lesen`. **Fehlt noch:** P3-26
  (Rollenschutz-Verifikationstest).
- Worktree `agent-adf4cf6131fee7af7` (Commit `95fafc5`): Runde 3 —
  Kassenbuch-Formular im Portal, `POST /api/abschluss/karte-korrektur`
  (Salon-Check), Ansätze bei Termine-Woche. **Ungeklärt:** ob der Server
  das Rechnungs-PDF selbst rendert oder nur das der App ablegt (3b) —
  das entscheidet den Umfang, war noch nicht beantwortet.

Nächster Schritt für einen frischen Agenten: beide Worktrees ansehen,
Diff gegen `origin/claude/session-context-210439` prüfen, Rest der
Aufgabe fertigstellen (Plan liegt in `docs/uebergabe-datev-2026-09-02/`),
dann erst mergen. **Nicht ungeprüft übernehmen** — die Agenten kamen nicht
zu ihrem eigenen Abschlussbericht.

**Nachtrag 03.09. nachts** (Branch `claude/belege-table-rendering-db4f82`,
lokal, nicht gepusht, nicht deployt): beide WIP-Worktrees oben sind als
Runde 2 (`feb5710`) und Runde 3 (`88dd3a1`) auf dem Branch, dazu Runde 4
(Desktop-Layout), Seitenleiste, DATEV-Seite `/datev`, und Plan 21 Phase 1,
2 und §7 (Postgres-Schicht, Box-Objekt, Mandantentabellen, Audit, Reset-
Link). Was landete und mit welchen Zahlen: `docs/uebergabe-datev-2026-09-02/
README.md`, Abschnitt „Welle 3". Deploy-Hinweis: Postgres ist im Compose
enthalten, aber `BABU_DB_URL` bleibt auskommentiert — erst Migrationslauf,
dann umschalten (Server-README). Vor dem Merge: Runde 2/3 sind weiterhin
nur über die Suite geprüft, nicht im Detail gesichtet.

Plan 21 Phase 3 (Acting-as, `X-Mandant`-Kopf) und Phase 4 (Mandanten-
verwaltung im Portal, Umschalter, `/api/kanzlei/*`) sind ebenfalls auf
dem Branch (`dae28ec`, `99f7add`). Ein Steuerberater legt damit unter
„Mandanten" Betriebe an, der Betreiber verknüpft die Belegbox, und die
Kanzlei arbeitet per Umschalter in der Box des Mandanten. Wie ein Zugang
zur Kanzlei wird: Rolle „kanzlei" unter „Zugänge verwalten", dann unter
„Mandanten" den ersten Betrieb anlegen — die Kanzlei-Zeile entsteht dabei.

Endstand `20fa9a5`: Suite 1900 grün gegen SQLite UND gegen Postgres 16.
Nicht gepusht, nicht gemerged, nicht deployt — das ist der Zug des
Auftraggebers (Push des Branches, ff-Merge nach main, Deploy-Ritual mit
Golden-Diff; für Postgres zusätzlich Passwortdatei, Migrationslauf,
dann `BABU_DB_URL` einkommentieren).

Noch offen aus dem Auftrag: Plan 21 Phase 5 (Lasttest, Backup-Cron auf dem
Host, Compose-Build auf der H200V), P2-17/18 und P3-Rest.
