# Next-Gen Tax App für Beauty-Salons — babu-Portal unter babu.0711.io

## Context

babu läuft produktiv: iPhone-App (Scan → On-Device-Lesung → Kontierung → Siegel → Upload) + BelegReview auf der H200V (PaddleOCR, embeddinggemma-Semantik, Gemma-4-Bild-Lane, `review:`-Commits) + GitChain-Belegbox unter babu.0711.io. Die Screenshots des Wolters-Kluwer-Portals (ADDISON OneClick) der Steuerkanzlei sind die Funktionsreferenz: Beleghub (Kategorienbaum + Upload + „übermitteln"), Dokumente (Kanzlei→Mandant mit eSignatur/Freigabe), Kommunikation (Themen-Threads), Einstellungs-Matrix, Mobile-App (Kamera/Import/Belege/Gesendet).

**Kernbefund:** WK ist ein *Transportsystem* — Belege werden hochgeladen, sortiert, übermittelt, dann passiert aus Nutzersicht nichts. Unser Portal ist ein *Antwortsystem*: jeder Beleg kommt mit Lesung, Kontierung, grünem Haken und sichtbarem Weg bis DATEV zurück. Die Pipeline liefert das bereits — das Portal macht es sichtbar.

**WK-Funktionen, die wir übernehmen (übersetzt):** Kanzlei-Dokumente mit Ungelesen-Status, Freigabe-Workflow, Benachrichtigungen, E-Rechnung (als Metadaten-Lane). **Ersetzen:** Kategorienbaum → Auto-Kontierung; „übermitteln" + 31-Tage-Fenster → Beleg-Weg-Zeitleiste für immer; generische Threads → beleg-verankerte Nachfragen/Chat. **Streichen:** Benutzer-/Rechteverwaltung (Ein-Personen-Betrieb, kommt ggf. mit Kanzlei-Phase), Sende-Warteschlangen.

**Annahmen (Rückfrage übersprungen):** Salon-Sicht zuerst, Kanzlei als Phase B; bestehenden FastAPI-Server ausbauen (kein neuer Stack); Plan + baubare Stufe 1; E-Rechnung architektonisch verankert, später gebaut.

## Leitplanken (nicht verhandelbar)

- Alle neuen Routen in `babu-web` (:7844) — Tunnel routet alles außer `/ablage`,`/health` bereits dorthin. Kein Tunnel-Change.
- `babu-eingang` (:7843) wird **nicht angefasst** (Parallel-Session).
- iOS-Verträge eingefroren: `GET /review/{stamm}` (inkl. `audit`/`buchungssatz`), `POST /chat` (SSE `data:{"d":…}` + `data: [DONE]`), Upload-Antwortfeld `datei`. Golden-JSON-Tests je Stufe.
- Box-Writes nur via Gateway-Push (:7808) aus eigenem Clone `~/babu-web/box/` — nie im Watcher-Clone (`reset --hard` pro Takt), nie direkt in den Bare-Store.
- UI-Sprachregel (verbindlich): Deutsch, kein Technik-Vokabular, keine Systemnamen, Vertrauen = ein grüner Haken. Verbotene Wörter in der Salon-UI: Server, OCR, KI/Modell, Merkle, Hash, Commit, Token/PAT, Confidence, Queue.
- Design: `--gc-*`-Tokens aus `design/unlimited-ocr/Unlimited-OCR App.html` (Bronze #857b61 = verifiziert, ok #6f8a6e, warn #b0821f, danger #a8433a; Serif-Display, Mono-Tabellenziffern, Eyebrow-Labels), genau drei Motion-Momente (Stempel ~450 ms, Zeitleisten-Schritt, Karten-Einflug), `prefers-reduced-motion`, kein CDN (DSGVO), Beispiel-Lieferanten: Slavic Hair Company · delilà Hair Extensions · Stadtwerke · Rotenberger Weingärtle.

## Produkt: Informationsarchitektur (Salon-Portal)

Vier Reiter, nach Handlungen benannt (statt WK-Silos); Einstellungen über Avatar:

| Reiter | Inhalt | WK-Gegenstück |
|---|---|---|
| **Heute** | Monats-Cockpit „Dein August": Braucht-dich-Karten, Summen je Belegart in Alltagssprache, eine Frist, Post-Hinweis, Zuletzt | — (existiert bei WK nicht) |
| **Belege** | Liste (Filter: Alle/Braucht dich/In Prüfung/Fertig, Monats-Umschalter), Detail mit Beleg-Weg; Drag&Drop überall | Beleghub |
| **Post** | Kanzlei-Dokumente (Ungelesen-Punkt), Freigabe-Karten, Rückfragen am Dokument | Dokumente + Kommunikation |
| **Fragen** | Chat (SSE, antwortet nur aus eigenen Belegen), Beleg-Anker, klickbare Quellen | — |

### Screens (Ableitung aus vorhandenen Vorlagen)

1. **HEUTE** (`/#heute`) — aus `design/claude-design-ds/foundations/salon-einfach.html` + Karten-Stil belegapp. Blöcke: Begrüßung (Serif) + Eyebrow `DEIN AUGUST`; **Braucht dich** (Nachfrage-Karten, z. B. „Mit wem warst du essen?" — ein Tap → Sheet); **Dein Monat in Zahlen** (3–5 Zeilen: „Wareneinkauf 1.412,80 €", Vormonats-Delta; keine Kontonummern); **Frist** („Deine Kanzlei braucht die August-Belege bis 5. September."); Post-Hinweis; Zuletzt (3 Mini-Karten). Leer: „Noch keine Belege in diesem Monat…" + Drop-Zone.
2. **BELEGE-Liste** (`/#belege`) — aus belegapp `#s-liste` + `komponenten/beleg-zeile.html`. Zeile: Thumbnail, Lieferant, Status-Satz („geprüft ✓" / Nachfrage / „wird gerade gelesen …"), Betrag Mono, klein Konto+Satz. Upload-Zeile erscheint sofort mit Live-Checkliste.
3. **BELEG-Detail** (`/#beleg/<stamm>`) — aus belegapp `#s-detail`/`#s-process` + `Dokument-Reader.html` + `komponenten/siegel-audit.html`, `buchungssatz.html`. Desktop: Bild links (Zoom), Sektionen rechts; verbindliche Eyebrow-Sektionen: **BELEG-WEG** (Zeitleiste: Foto erhalten → Gelesen → Zweitprüfung ✓ → Liegt für DATEV bereit → Bei der Kanzlei), **AUS DEM FOTO** (bei E-Rechnung: **AUS DER RECHNUNG**; Zwei-Lesarten-Wahl: „Wir haben zwei Lesarten — welche stimmt?"), **ZWEITPRÜFUNG** (ein grüner Haken + menschlicher Buchungstext, keine Prozente), **DAS GEHT AN DATEV** (Buchungssatz-Boxen), **UNVERÄNDERT SEIT** (Siegelzeile + Kopieren), Nachfrage-Karte falls offen, „Frag zu diesem Beleg".
4. **AUFRÄUMEN** (`/#aufraeumen`) — Web-Fassung des Wischstapels: ein Beleg groß, „Passt — buchen" (→/Enter) / „Später" (←/Esc), Bewirtungs-Intercept, Abschluss mit Tagessumme. Leer: „Nichts zu tun. Schöner Zustand."
5. **POST** (`/#post`) — Liste neueste oben, Bronze-Punkt ungelesen, Freigabe-Karten zuoberst („Deine Kanzlei bittet um Freigabe: USt-Voranmeldung Juli · 1.214,00 €" → „Freigeben ✓" → Stempel + „Freigegeben am … — für die Kanzlei sichtbar"); Reader-Ansicht mit Download + Rückfrage.
6. **FRAGEN** (`/#fragen`) — aus FragenTab/`komponenten/chat.html`: Beispiel-Chips, Streaming, Beleg-Anker-Karte über der Eingabe, Quellenzeile klickbar. Vertrauens-Copy: „Ich antworte nur aus deinen Belegen."
7. **HOCHLADEN** — kein Screen, ein Zustand: portalweites Drop-Overlay („Ablegen — ich kümmere mich drum") → `POST /ablage` unverändert → Zeile mit Live-Checkliste (belegapp `#s-process`-Muster: Foto erhalten ✓ → wird gelesen … → Zweitprüfung …).
8. **EINSTELLUNGEN** — Zugang (Geräte-Liste, „Neues Gerät verbinden", übergangsweise Feld „Zugangscode" mit Verbindungstest-Haken), Benachrichtigungen als **drei Schalter** („Wenn ein Beleg eine Frage hat" / „Wenn Post von der Kanzlei kommt" / „Einmal am Abend eine Zusammenfassung"), Meine Kanzlei, Betrieb.

Alle Zustände definiert: Leer/Laden (Skeleton in `--gc-accent-subtle`)/Fehler („Gerade keine Verbindung. Deine Belege sind sicher — wir zeigen den Stand von eben.").

## Technik

### Auth: Session-Cookie auf whoami-Basis, Bearer bleibt

- `POST /api/anmelden` `{pat}` → `wer()`-Logik wiederverwenden (whoami + 5-min-Cache + `BABU_ERLAUBT`) → `Set-Cookie: babu_sitzung=<HMAC {un,exp}>; HttpOnly; Secure; SameSite=Lax`. Schlüssel in `~/babu-web/.session_geheimnis`. PAT wird nicht gespeichert; Schreiben nutzt Service-PAT `~/gitchain-eingang/.pat_babu`, User-`un` wird Commit-Autor.
- Dependency `angemeldet()`: Cookie ODER Bearer (iOS kompatibel). `GET /api/ich`, `POST /api/abmelden`.
- Kein CORS (same-origin), CSRF: SameSite=Lax + JSON-only + Origin-Check. Kein OIDC in Phase A/B.

### Index statt Subprocess-Sturm

In-Process-Index in babu_web (Single-Worker): Invalidierung über `git rev-parse HEAD` (~5 s TTL); Aufbau inkrementell Blob-OID-keyed via `git ls-tree -r --format` + `git cat-file --batch`; Commit-Metadaten über einen `git log --name-status`-Walk + Delta. Eintrag: `{stamm, datei, monat, hochgeladen, review_zeit, lieferant, brutto/netto/ust, ust_satz, belegart, konto_skr04, steuerschluessel, offen[], summenprobe_ok, bewirtung, status}`. Status abgeleitet: `erfasst` (kein Review) → `geprüft` (offen leer + Summenprobe ok) → `nachfrage` → später `freigegeben`/`exportiert`. Chat-Kontext `belegdaten_kontext()` auf den Index umstellen (gleicher Output).

### Neue Endpunkte (Phase A)

| Route | Zweck |
|---|---|
| `POST /api/anmelden` / `abmelden`, `GET /api/ich` | Session |
| `GET /api/belege?monat=&status=&limit=&seite=` | Liste aus Index, `ETag: <HEAD>` → 30-s-Poll mit `If-None-Match` kostet ein rev-parse (304) |
| `GET /api/beleg/{stamm}` | Superset von `/review/{stamm}` (Wiederverwendung `commit_info`, `datev_buchungssatz`) + `status`, `bild_url`, `bewirtung` |
| `GET /api/beleg/{stamm}/bild` | Bytes via `git show HEAD:docs/…`, `?v=<blob-oid>` + immutable-Cache |
| `GET /api/monat/{jjjj-mm}` | Cockpit-Aggregation: Summen je belegart/Konto, offene Punkte, größte Position |
| `POST /api/bewirtung/{stamm}` | Rückkanal: Commit `bewirtung: <datei>` als `review/<stamm>.bewirtung.json` (eigene Datei — klare Autorenschaft, kein Konflikt mit Re-Reviews) |
| `GET/POST /api/dokumente`, `GET /api/dokument/{pfad}`, `POST …/gelesen` | Kanzlei-Kanal (Stufe 3) |
| `POST /chat` | um Cookie erweitert, sonst byte-identisch |

Status-Frische: ETag-Polling zuerst; `GET /api/ereignisse` (SSE, Server pollt HEAD 5 s) als Stufe-2-Add-on. Kein WebSocket.

### Schreibpfad `boxschreiber.py` (neues Modul neben babu_web.py)

Eigener Clone `~/babu-web/box/`, Muster wie Watcher: fetch + reset → Datei → Commit `--author "<un> <portal@gitchain.local>"` → Push via Gateway :7808 mit `GIT_CONFIG_*`-Header (PAT ohne Newline — Falle Nr. 2). Push-Rennen mit Watcher → ein Retry, sonst 503.

### Daten

- **Kanzlei-Dokumente: dieselbe Box**, `dokumente/JJJJ-MM/<name>.pdf` + `<name>.meta.json` (`{titel, art, von, sichtbar_ab}`), Commit `dokument: <name>`. Watcher ignoriert das automatisch (filtert auf `docs/` + Bild-Endungen). Freigaben (Phase B): `freigaben/<id>.json` mit Antwort-Commit (auditpflichtig → Git).
- **Portal-State (Lesestatus, Prefs): SQLite `~/babu-web/portal.db`** — kein Audit-Material, gehört nicht als Rauschen in die Belegbox-Historie.

### Frontend

Selbst-enthaltenes `server/belegreview/portal.html` (→ `~/belegreview/portal.html`, `GET /portal` FileResponse): eine Datei, Hash-Routing (`#heute`, `#belege`, `#beleg/<stamm>`, `#aufraeumen`, `#post`, `#fragen`), `--gc-*`-Tokens, System-Fonts, Vanilla-JS/fetch — **bewusste Abweichung vom React-Plan des Bauplans** (dokumentieren): eine Datei + `scp` schlägt jede Toolchain bis zur Multi-Mandanten-Phase; Tokens identisch → spätere Migration ist Port, kein Redesign. Eigenes `GET /portal/manifest.json` + `sw.js` mit Scope `/portal` (App-Shell cachen, nie `/api/*`). Bestehende Upload-Seite `GET /` bleibt, bekommt Link „Zum Portal". Beim Portalbau Token-Namen aus belegapp (unprefixed) auf `--gc-*` vereinheitlichen.

### Watcher-Ausbau (entkoppelte Stufe, pm2 `belegreview`)

1. PDF via `pypdfium2` (pip-only): Seite 1 mit ~200 dpi → PNG → bestehende Pipeline; `seiten>1` als Hinweis in `offen`.
2. HEIC via `pillow-heif`.
3. E-Rechnungs-Anker: `.xml`/ZUGFeRD zunächst nur klassifizieren + Review-Stub (`lane: "xml"`) — Lane im Datenmodell verankert, Parser später.
4. `*.bewirtung.json`-Filter (nicht als Review fehlinterpretieren; analog `.embedding.json`).
5. **Salon-SKR04-Katalog** ergänzen (Embedding-Anker salonspezifisch; Konten vor Produktivgang vom Steuerberater bestätigen): `wareneingang 5400` (Haarfarbe/Extensions/Großhandel…), `fremdleistung 5900` (Stuhlmiete…), `miete 6310`, `reinigung 6330` (Handtuchservice…), `versicherung 6400`, optional `werbung 6600`. Katalog-Cache invalidiert sich selbst (Hash); kein Backfill alter Reviews; Verschiebungen vorab gegen gespeicherte OCR-Texte messen.

## Stufenplan (einzeln shipbar)

| Stufe | Inhalt | Touchpoint | Risiko |
|---|---|---|---|
| **1 — Lese-Portal (WK-Killer)** | Index, Session-Auth, `/api/belege`, `/api/beleg/{stamm}` (+`/bild`), `/api/monat`, Chat cookie-fähig, `portal.html` (Heute + Belege + Detail + Fragen). Keine Box-Writes. | `pm2 restart babu-web` | Restart unterbricht iOS-Poll für Sekunden (harmlos). Golden-Tests vorher. README-Neustartzeilen ergänzen |
| **2 — Rückkanal + Frische** | `boxschreiber.py`, `POST /api/bewirtung`, ETag-Poll im Frontend, optional SSE-Ereignisse, SQLite, PWA-Manifest/SW, Aufräumen-Ansicht | restart babu-web, neuer Clone | Push-Rennen mit Watcher → Retry testen |
| **3 — Post/Dokumentenkanal** | `dokumente/` + Endpunkte, Inbox, gelesen-Status, 3 Benachrichtigungs-Schalter (v1 Badge, Mail/Push später) | restart babu-web | Größenlimit + Endungs-Allowlist; Watcher-Ignoranz nachweisen |
| **4 — Watcher-Ausbau** | PDF, HEIC, Salon-Katalog, E-Rechnungs-Stub, Bewirtungs-Filter | pip in `~/paddle-ocr-env`, restart belegreview | Einziger Produktiv-Pipeline-Eingriff → vorher offline gegen Fixtures in separatem Clone; Katalog-Shift-Tabelle reviewen |
| **5 — Kanzlei (Phase B)** | `workbench.html` an `/api/*` (`GET /workbench`), Rolle kanzlei (Allowlist + Rollen-Map), Post senden + Freigabe-Flow, **EXTF-v13-Writer** als `GET /api/export/{jjjj-mm}.csv` (CP1252/CRLF, Golden-Files, Mehrsatz 7%+19%) | restart babu-web | EXTF-Abnahme = Import in echter DATEV-Instanz |

## Zu ändernde/neue Dateien

- `server/belegreview/babu_web.py` — Session, Index, alle `/api/*`; wiederverwenden: `wer()`, `commit_info()`, `datev_buchungssatz()`, `belegdaten_kontext()`
- `server/belegreview/boxschreiber.py` — **neu** (Gateway-Push, Vorlage: review_watcher.py Push-Teil)
- `server/belegreview/portal.html` — **neu** (Portal-PWA; Stil-Blaupause `app/workbench.html` + Screens aus `app/belegapp.html`, `design/unlimited-ocr/Dokument-Reader.html`, `design/claude-design-ds/…`)
- `server/belegreview/portal.manifest.json`, `server/belegreview/portal.sw.js` — **neu**
- `server/belegreview/review_watcher.py` — Stufe 4 (PDF/HEIC-Dispatch, Katalog, Filter)
- `server/belegreview/index.html` — nur Link „Zum Portal"
- `server/belegreview/README.md` — pm2-Neustartzeilen ergänzen (Reboot-Falle!)
- `docs/` — dieser Plan als `docs/superpowers/specs/2026-08-13-salon-portal.md` einchecken

## Verifikation

- **Stufe 1:** `/review/<stamm>` + `/chat`-SSE vor/nach Deploy byte-diffen (`jq -S`); `curl`-Kette anmelden→belege→beleg→monat; `/api/belege`-Anzahl == `ls-tree`-Zählung; If-None-Match → 304; 50× `/api/belege` < 1 s (Index greift); Browser-Test über Preview auf `https://babu.0711.io/portal` (Login, Liste, Cockpit-Summen == jq-Summen, Chat streamt); iOS-Regression on-device (Upload → 30-s-Poll → Review).
- **Stufe 2:** Bewirtungs-POST → `git log -1` zeigt `bewirtung:`-Commit mit korrektem Autor; Watcher 3 Takte fehlerfrei; erzwungenes Push-Rennen → Retry/503 sauber.
- **Stufe 3:** `dokument:`-Commit da, Watcher still, gelesen-Status überlebt Restart.
- **Stufe 4:** Fixture-Trockenlauf (2 PDFs, 2 HEICs) in separatem Clone; Katalog-Regressions-Tabelle; danach echter Test-PDF → `review:` binnen 60 s.
- **Stufe 5:** EXTF-Golden-Files + Import in echter DATEV-Umgebung; 403-Checks Rollen-Trennung.

## Vollständige Task-Liste

Nummerierung = Reihenfolge. Jede Task hat ein Abnahmekriterium (AK). Bei Freigabe des Plans wird diese Liste 1:1 in die Task-Verwaltung übernommen.

### Stufe 0 — Vorbereitung (halber Tag)

| # | Task | AK |
|---|---|---|
| 0.1 | Plan als Spec einchecken: `docs/superpowers/specs/2026-08-13-salon-portal.md` | Commit auf Branch, PR-fähig |
| 0.2 | Golden-Baseline sichern: `GET /review/<stamm>` (2 Stämme) + ein `/chat`-SSE-Mitschnitt als Fixtures unter `server/belegreview/tests/golden/` | Fixtures eingecheckt, `jq -S`-normalisiert |
| 0.3 | Bestandsaufnahme Belegbox: Anzahl Reviews, Beispiel-Stämme je Status (geprüft/nachfrage/erfasst) notieren | Tabelle im Spec-Anhang |

### Stufe 1 — Lese-Portal (der WK-Killer; ~3–5 Tage)

| # | Task | AK |
|---|---|---|
| 1.1 | Index-Modul in `babu_web.py`: HEAD-TTL-Invalidierung, `ls-tree`+`cat-file --batch`-Aufbau, `git log`-Walk für Zeiten/Autoren, Status-Ableitung (erfasst/geprüft/nachfrage) | 50× `/api/belege` sequentiell < 1 s; Index == `ls-tree`-Zählung |
| 1.2 | Session-Auth: `POST /api/anmelden` (PAT→whoami→HMAC-Cookie), `/api/abmelden`, `GET /api/ich`, `.session_geheimnis`, Origin-Check, Dependency Cookie-ODER-Bearer | curl-Kette anmelden→ich→abmelden; falscher PAT → 401; fremder `un` → 403 |
| 1.3 | `GET /api/belege` mit `monat`/`status`/`limit`/`seite` + ETag/If-None-Match | Zweiter Call → 304; Filter korrekt gegen Fixtures |
| 1.4 | `GET /api/beleg/{stamm}` (Superset von `/review`) + `GET /api/beleg/{stamm}/bild` (blob-oid, immutable-Cache) | jq-Key-Diff: Superset ⊇ `/review`; Bild lädt mit 200 + Cache-Header |
| 1.5 | `GET /api/monat/{jjjj-mm}`: Summen je Belegart/Konto, offene Punkte, größte Position, Vormonat | Summen == jq-Rechnung über Review-JSONs |
| 1.6 | `/chat` cookie-fähig; `belegdaten_kontext()` auf Index umstellen (Output identisch) | SSE-Golden-Mitschnitt byte-gleich; Chat aus Portal funktioniert |
| 1.7 | `portal.html` Grundgerüst: `--gc-*`-Tokens, Shell, Hash-Routing, Login-Karte („Zugangscode"), Fehler-/Skeleton-Zustände | Rendert auf Desktop + iPhone-Breite; Login-Fluss klappt |
| 1.8 | Ansicht HEUTE (Cockpit): Braucht-dich, Dein Monat in Zahlen, Frist, Zuletzt; Leer-Zustand | Zahlen == `/api/monat`; Sprachregel-Check (verbotene Wörter grep) |
| 1.9 | Ansicht BELEGE (Liste): Zeilen-Anatomie, Filterchips, Monats-Umschalter | Alle Status-Sätze korrekt; Thumbnail aus `/bild` |
| 1.10 | Ansicht BELEG-Detail: BELEG-WEG-Zeitleiste, AUS DEM FOTO, ZWEITPRÜFUNG, DAS GEHT AN DATEV, UNVERÄNDERT SEIT (+ Kopieren), Bild-Zoom | Alle 5 Sektionen aus `/api/beleg`; Stempel-Motion + reduced-motion |
| 1.11 | Ansicht FRAGEN: SSE-Stream, Beispiel-Chips, Beleg-Anker, klickbare Quellen | Streaming sichtbar; Abbruch-Zustand („nochmal fragen?") |
| 1.12 | `GET /portal` Route; Upload-Seite `/` bekommt Link „Zum Portal" | beide Seiten erreichbar |
| 1.13 | Deploy H200V: scp, `pm2 restart babu-web`, README-Neustartzeilen ergänzen; Golden-Diff `/review`+`/chat`; Browser-Test auf babu.0711.io; iOS-Regression (Upload→Poll→Review) | alle Verifikationspunkte Stufe 1 grün |

### Stufe 2 — Rückkanal + Frische (~2–3 Tage)

| # | Task | AK |
|---|---|---|
| 2.1 | `boxschreiber.py`: eigener Clone `~/babu-web/box/`, fetch+reset→Commit(`--author <un>`)→Gateway-Push, 1 Retry, sonst 503 | Unit-Trockenlauf gegen Test-Clone; PAT-Newline-Falle getestet |
| 2.2 | `POST /api/bewirtung/{stamm}` → `review/<stamm>.bewirtung.json`; Index+Chat filtern `.bewirtung.json` | `git log -1` = `bewirtung: <datei>`, Autor = `un`; Watcher 3 Takte fehlerfrei |
| 2.3 | Frontend: Nachfrage-Karte Bewirtung (Sheet „Mit wem warst du essen?") auf Heute + Detail | Antwort erscheint nach Reload im Detail; Status wechselt auf geprüft |
| 2.4 | ETag-Polling (30 s) im Frontend; Beleg-Weg springt live weiter; optional `GET /api/ereignisse` (SSE) | Upload → grüner Haken erscheint ohne Reload binnen 60 s |
| 2.5 | Upload-Live-Echo: portalweites Drop-Overlay → `POST /ablage` → Zeile mit Checkliste | Mehrfach-Drop; Fehlerbilder (401/413/503) mit menschlichen Sätzen |
| 2.6 | SQLite `~/babu-web/portal.db` (lesestatus, einstellungen) + Anbindung | übersteht `pm2 restart` |
| 2.7 | PWA: `portal.manifest.json` + `portal.sw.js` (Scope `/portal`, App-Shell only) | Installierbar auf iPhone; `/api/*` nie gecacht |
| 2.8 | AUFRÄUMEN-Ansicht (Web-Wischstapel, Tastatur →/←/Enter/Esc, Bewirtungs-Intercept, Tagessummen-Abschluss) | Durchlauf mit 3 Test-Belegen; Leer-Zustand |
| 2.9 | Verifikation Stufe 2 inkl. erzwungenem Push-Rennen mit Watcher | Retry greift oder sauberer 503 |

### Stufe 3 — Post/Dokumentenkanal (~2–3 Tage)

| # | Task | AK |
|---|---|---|
| 3.1 | Box-Schema `dokumente/JJJJ-MM/<name>.pdf` + `.meta.json`; Endpunkte `GET/POST /api/dokumente`, `GET /api/dokument/{pfad}`, `POST …/gelesen` | Upload-Limit + Endungs-Allowlist; `dokument:`-Commit; Watcher bleibt still |
| 3.2 | Ansicht POST: Inbox (Bronze-Punkt ungelesen), Reader (Download, Rückfrage), Freigabe-Karten-Platzhalter | Ungelesen-Status aus SQLite, überlebt Restart |
| 3.3 | Benachrichtigungen: 3 Schalter + Abend-Zusammenfassung per Mail (v1: Badge im Portal, Mail-Versand einfacher SMTP) | Schalter persistiert; Test-Mail kommt an |
| 3.4 | Ansicht EINSTELLUNGEN: Zugang/Geräte, Benachrichtigungen, Meine Kanzlei, Betrieb | Verbindungstest-Haken; Sprachregel-Check |
| 3.5 | Verifikation Stufe 3 | alle AKs grün |

### Stufe 4 — Watcher-Ausbau (~2–3 Tage, einziger Pipeline-Eingriff)

| # | Task | AK |
|---|---|---|
| 4.1 | Fixture-Suite: 2 PDFs, 2 HEICs, OCR-Texte aller Bestands-Reviews als Katalog-Regressionsbasis; separater Test-Clone | Trockenlauf-Harness läuft offline |
| 4.2 | PDF-Lane: `pypdfium2`, Seite 1 @200 dpi → PNG → Pipeline; `seiten>1` → Hinweis in `offen` | Fixture-PDFs erzeugen valide Reviews |
| 4.3 | HEIC: `pillow-heif` → JPEG | Fixture-HEICs erzeugen valide Reviews |
| 4.4 | Salon-SKR04-Katalog (wareneingang 5400, fremdleistung 5900, miete 6310, reinigung 6330, versicherung 6400, opt. werbung 6600); Regressions-Tabelle alt vs. neu | Verschiebungen reviewt; Konten vom Steuerberater bestätigt |
| 4.5 | E-Rechnungs-Stub: `.xml`/ZUGFeRD-Erkennung → Review-Stub `lane:"xml"` | XML-Fixture wird geparkt, nicht verarbeitet |
| 4.6 | `.bewirtung.json`-Filter im Watcher (analog `.embedding.json`) | Watcher-Log still bei vorhandenen Bewirtungs-Dateien |
| 4.7 | Deploy: pip in `~/paddle-ocr-env`, `pm2 restart belegreview`; echter Test-PDF via App/`/ablage` | `review:`-Commit binnen 60 s |

### Stufe 5 — Kanzlei / Phase B (~5–8 Tage)

| # | Task | AK |
|---|---|---|
| 5.1 | Rollenmodell: zweiter `BABU_ERLAUBT`-Eintrag + Rollen-Map (salon/kanzlei) in babu_web | 403-Matrix getestet |
| 5.2 | `GET /workbench`: `app/workbench.html` an `/api/*` verdrahten (Queue = nachfrage-Belege confidence-aufsteigend, Detail, Korrektur-Rückschreiben via boxschreiber) | Tastatur j/k/Enter/9/8/0 funktioniert gegen echte Daten |
| 5.3 | Kanzlei-Post: Dokument-Upload + Titel + „Freigabe anfordern" → Freigabe-Karte bei der Inhaberin; `freigaben/<id>.json` + Antwort-Commit | Rundreise Kanzlei→Salon→Freigabe→Kanzlei sichtbar |
| 5.4 | **EXTF-v13-Writer**: `GET /api/export/{jjjj-mm}.csv`, voller Header, CP1252/CRLF, Mehrsatz-Split 7 %+19 %, Golden-File-Tests | Import in echter DATEV-Instanz ohne Fehler |
| 5.5 | Beleg-Weg-Schritt „Bei der Kanzlei" an Export koppeln; Festschreibe-Status | Zeitleiste vollständig |

### Querschnitt (parallel, nicht blockierend)

| # | Task | AK |
|---|---|---|
| Q.1 | KPI-Instrumentierung: `metriken`-Tabelle in portal.db (API-Zähler, Latenzen), `GET /api/kpi/{jjjj-mm}` aus Index+Audit-Zeiten | KPI-Seite/JSON liefert die u. g. Kennzahlen |
| Q.2 | `pm2 save` + Reboot-Test H200V (sobald Parallel-Session ruht; vorher `~/.pm2/dump.pm2` sichern) | Reboot < 10 min bis alle Dienste laufen |
| Q.3 | Demo-Leichen auf dem iPhone löschen (85,40 Weingärtle) — sonst doppelt im Aufräum-Stapel | Belegliste sauber |
| Q.4 | Sprachregel-Linter: Grep-Checkliste verbotener Wörter über portal.html als Test | CI-/Pre-Deploy-Check grün |

## KPIs

Messbar aus vorhandenen Daten: `audit.aufnahme.zeit` / `audit.review.zeit` (in jedem Review), `offen[]`, `summenprobe_ok`, Index-Status, API-Zähler in portal.db (Task Q.1). Bericht: `GET /api/kpi/{jjjj-mm}`.

### Produkt (Salon-Erlebnis)

| KPI | Definition | Ziel |
|---|---|---|
| **Zeit bis grüner Haken** | Median Upload→`review:`-Commit (`audit`-Zeiten) | ≤ 60 s (P95 ≤ 3 min) |
| **Auto-geprüft-Quote** | Anteil Belege ohne Nachfrage (`offen` leer + Summenprobe ok) | ≥ 80 % |
| **Nachfragen-Erledigungszeit** | Karte erscheint → beantwortet (bewirtung.json-Commit) | Median ≤ 24 h |
| **Pflicht-Metadaten pro Beleg** | Vom Nutzer geforderte Eingaben vor Ablage (WK: Kategorie + übermitteln) | **0** |
| **Offene Belege zur Frist** | Belege im Status nachfrage/erfasst am 5. des Folgemonats | 0 |
| **Upload-Erfolgsquote** | 2xx / Versuche (App + Portal) | ≥ 99 % |

### Qualität (Pipeline)

| KPI | Definition | Ziel |
|---|---|---|
| **Feldgenauigkeit** | Brutto / Datum / Lieferant korrekt vs. bestätigten Werten (Korrektur-Log ab Stufe 5, vorher Stichprobe) | ≥ 98 % / ≥ 95 % / ≥ 90 % |
| **Kontierungs-Trefferquote** | 1 − (Kanzlei-Korrekturen ÷ Buchungen) | ≥ 95 % |
| **Summenprobe-Bestehensrate** | `summenprobe_ok` über alle Reviews | ≥ 90 % |
| **Unlesbar-Quote** | Belege mit „neu fotografieren"-Nachfrage | ≤ 3 % |
| **Fallback-Quote 6850** | Anteil Kontierung auf Sonstiges (nach Salon-Katalog, Stufe 4) | ≤ 15 % |
| **Review-Latenz Watcher** | Median Aufnahme→Review | ≤ 30 s |

### Betrieb

| KPI | Definition | Ziel |
|---|---|---|
| **API-Latenz warm** | P95 `/api/belege` / `/api/beleg` | ≤ 150 ms / ≤ 250 ms |
| **304-Quote** | Anteil 304 beim ETag-Polling | ≥ 95 % |
| **Verfügbarkeit** | babu.0711.io erreichbar (extern gemessen, `/health`) | ≥ 99,5 %/Monat |
| **5xx-Quote** | Fehler ÷ Requests | ≤ 0,5 % |
| **iOS-Vertragsstabilität** | Golden-Diffs `/review`+`/chat` je Deploy | 100 % byte-gleich |
| **Wiederanlauf nach Reboot** | Zeit bis alle 4 pm2-Dienste laufen (nach Q.2) | ≤ 10 min |

### Outcome (Business)

| KPI | Definition | Ziel |
|---|---|---|
| **Beleg-Abdeckung** | Anteil aller Salon-Belege, die digital ankommen (kein Schuhkarton) | 100 % |
| **Wochenaufwand Inhaberin** | Zeit für Belegarbeit (Selbstauskunft/Portal-Sitzungsdauer) | ≤ 15 min/Woche |
| **Monatsabschluss-Reife** | Kalendertag, an dem alle Vormonats-Belege geprüft sind | ≤ 5. des Folgemonats |
| **DATEV-Import-Erfolg** (ab Stufe 5) | Stapel ohne Importfehler ÷ Stapel | 100 % |
| **Portal-Nutzung** | Tage/Woche mit Anmeldung (Portal oder App) | ≥ 3 |

## Offene Fragen (im Bau zu entscheiden, blockieren den Start nicht)

1. Anmeldefluss langfristig: Gerätecode-Fluss vs. Magic-Link (Stufe 1: Zugangscode-Feld).
2. Zeigt der Beleg-Weg „Bei der Kanzlei" schon vor dem EXTF-Writer (dann endet er bei „liegt bereit")? → Ja, so bauen.
3. Web-Push für die PWA oder Mail genügt (Stufe 3)? → Mail zuerst.

## Anhang: Testkorpus „Steuer App" (entdeckt 13.08.2026)

`/Users/christophbertsch/Downloads/Steuer App/` — echte Salon-Daten (SupremeBeauty,
Lindenstraße 2, 71634 Ludwigsburg; Kontoauszüge auf Nicole Baic, KSK Ludwigsburg).
**Bleibt lokal — Bank- und Personendaten kommen NICHT ins Repo und nicht ungefragt
in die Belegbox.** Referenz nur über diesen Pfad.

| Ordner | Inhalt | Bedeutung für den Plan |
|---|---|---|
| `Testcase Belege 2025` | 83 einzelne Beleg-PDFs (`Beleg_JJJJMMTT_HHMMSS.pdf`, 1-seitig, aus der OneClick-App) | Realistische PDF-Fixtures für Stufe 4; born-digital (z. B. Planity-Abo 70,21 €) UND gescannte Bons |
| `Testcase Belege 2024` | 12 Monats-Bündel (z. B. „Belege April 24.pdf", 65 Seiten, ein Thermobon pro Seite, teils **kopfüber**, gemischte Sätze 19 %+7 % auf einem Bon) | Stufe 4 braucht: Mehrseiten-Split (1 Seite = 1 Beleg), Rotationskorrektur, Mehrsatz-Fall ist real |
| `Testcase Kontoauszüge 2024/2025` | je 12 KSK-GiroBusiness-Auszüge (Konto 30217038, ~9 Seiten, **Text-PDF, kein OCR nötig**): Lastschriften Henkel/Vodafone/PayPal-delilà/Planity, Überweisungen Slavic Hair, SumUp-Gutschriften, SpkCard-Entgelte | **Neue Fähigkeit (Stufe 6): Kontoauszug-Lane + Zahlungsabgleich** — „Für die delilà-Lastschrift 626,45 € vom 09.01. fehlt der Beleg" = Vollständigkeitskontrolle, die WK nicht hat |
| `Transaktionsgebühren 2024/2025` | leer (Platzhalter) | SumUp-/Terminalgebühren folgen — im Abgleich mitdenken |
| `Screenshots …WoltersKluwer` | 5 App-Screenshots (bereits ausgewertet) | Funktionsreferenz |

**Konsequenzen:**
1. Der im Bauplan als „kritischstes Einzelstück" markierte **Benchmark-Korpus existiert jetzt** — Stufe-4-Fixtures kommen hierher statt aus Kunstdaten (Auswahl kopieren, nichts committen).
2. **Stufe 4 erweitert**: Rotationserkennung (PaddleOCR `use_textline_orientation`), Mehrseiten-PDF-Split für Monats-Bündel, Mehrsatz-Steuertabelle gegen den dm-Bon testen.
3. **Neue Stufe 6 — Kontoauszug & Abgleich**: KSK-Text-PDFs parsen (Umsatzliste je Monat), Abgleich Belege ↔ Abbuchungen (Betrag+Datum+Lieferanten-Fuzzy), Portal-Ansicht „Fehlende Belege" + Cockpit-Zeile „N Abbuchungen ohne Beleg"; SumUp-Gutschriften als Einnahmen-Sicht. Datenschutz-Entscheid nötig: Auszüge in die Belegbox (Commit `auszug:`) oder nur lokal verarbeiten.

## Anhang: Bestandsaufnahme Belegbox (Task 0.3, Stand 13.08.2026)

| Zustand | Anzahl | Beispiel-Stamm |
|---|---|---|
| Review vorhanden, Status **nachfrage** (offen: Trinkgeld-Differenz 160,00 vs. 142,60; Bewirtung 6640) | 1 | `20260812-225200-c781d6-beleg_2026-07-21_weingaerty_22bf8b36` |
| **erfasst** ohne Review (PDF — Watcher kann noch kein PDF, Stufe 4) | 2 | `20260812-211943-99b8fb-beleg-test.pdf`, `20260812-211943-a018da-beleg-test.pdf` |
| Status **geprüft** (offen leer + Summenprobe ok) | 0 | — (entsteht mit den nächsten Foto-Belegen) |

Golden-Fixtures: `server/belegreview/tests/golden/` (review_weingaertle.json byte-stabil; chat_sse_mitschnitt.txt = Protokollform). pm2-Dienste zum Zeitpunkt der Aufnahme online: `babu-eingang`, `babu-tunnel`, `babu-web`, `belege-review` (Achtung: pm2-Name ist `belege-review`, nicht `belegreview`).
