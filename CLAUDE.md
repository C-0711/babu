# babu — Projektanweisungen für Claude

Salon-Buchhaltung: iOS-App „Beleg" (SwiftUI) + FastAPI-Server auf der H200V
(mybabu.io; babu.0711.io bleibt als zweiter Name, derselbe Tunnel). Nutzerin: Nina (Salon-Inhaberin, Mandant „SupremeStudio").
Seit 03.09.2026 dazu die Kanzlei-Seite: Steuerberater verwalten Mandanten,
arbeiten in deren Belegbox und übergeben DATEV-Stapel. Sprache in UI,
Commits und Antworten: **Deutsch**. Einstieg und Details: `HANDOVER.md`,
DATEV-Übergabe: `docs/uebergabe-datev-2026-09-02/README.md`.

## Verbindlich: das Zielbild (seit 26.08.2026)

**EINE Lesung, keine zweite.** Apple Vision liest auf dem iPhone
(`{text, conf, box}`), `POST /api/buchung/einschaetzung` reichert an
(Profil, ungedeckte Abbuchungen, Verträge/Personal), Gemma bucht strict JSON
mit Pflichtfeld `dokumentklasse`, **erst danach** archiviert
`POST /api/aufnahme` Foto + Ergebnis. Die Belegbox ist reines Archiv; das
Bild fasst kein System mehr an.

**Nicht wieder einbauen** (gelöscht 27.08., main `d5f0d5f`):
review_watcher, belegdeutung, leseprotokoll, doc_classify, die Routen
`neu-lesen`/`buchungsfragen`, der App-FeldParser im Buchungsweg, das
Kontierung-Enum. **Paddle-OCR (:7833) ruft babu gar nicht mehr** — der
Dienst gehört ctax; Scan-Blätter der Salonprüfung liest Gemma (multimodal).

**UI-Sprachregel:** kein Technik-Vokabular, keine Systemnamen, kein
„Erst-/Zweitlesung". Vertrauen = ein grüner Haken. Kein Hex-Hash.
`tests/test_sprachregel.py` prüft `portal.html` inklusive `//`-Kommentaren
(verbotene Wörter: Server, Token, Hash, Commit, Queue, Modell, KI, OCR,
Lesung) — JS-Kommentare als `/* */`. Im Portal nie Namen in
`onclick`-Attribute, nur Nummern (`MD_NAMEN`/`mdVon`).

## Verbindlich: der Server ist die Wahrheit (seit 10.10.2026)

- **Die Belegliste der App kommt aus der Belegbox**, nicht aus dem Telefon.
  `AppStore.vomServerLaden()` holt `GET /api/belege` (alle Seiten) beim
  Start, beim Sichtbarwerden und nach jeder Anmeldung und führt über
  `ServerAbgleich.zusammenfuehren` zusammen: Fehlendes kommt dazu (ohne
  Foto, die Einzelansicht lädt `/api/beleg/<stamm>/bild` nach), im Portal
  Gelöschtes geht (nur bei vollständiger Liste, nur Belegfach), wartende
  Uploads bleiben, die eigene Buchung wird nie überschrieben. Harness
  `ios/Tests/serverabgleich` (reine Logik, ohne UIKit).
- **Eine Zustandsdatei je Zugang**: `zustand-<hash des Geräteschlüssels>.json`
  (`ServerAbgleich.zustandsDateiName`), damit zwei Betriebe auf einem
  iPhone zwei Listen haben. Beim ersten Start mit Schlüssel zieht die alte
  `zustand.json` in die Datei des angemeldeten Zugangs um und bleibt als
  `.vor-trennung` liegen. An- und Abmelden wechseln die Datei
  (`zustandWechseln`). Nie wieder eine geräteweite Belegliste bauen.
- Anlass: Ninas #85/#88 (Blättern in frühere Monate ging ins Leere), ein
  zweites iPhone sah eine leere Ablage, zwei Betriebe teilten eine Liste.

## Verbindlich: Umsatz und Kasse (seit 03.09.2026)

- **Kasse GEGEN Konto abgleichen, nicht entweder-oder.** Die Karte im
  Kassenbuch (`ecZahlungen`) und die Auszahlungen der Kartenanbieter auf
  dem Kontoauszug (Salonkee, SumUp, Zettle … `ERLOES_QUELLEN` in
  `monatsabschluss.py`) sind dasselbe Geld. Was das Konto MEHR zeigt als
  das Kassenbuch, zählt als Umsatz mit (`aus_bank`); zeigt es weniger, ist
  das Gebühr/Zeitversatz und wird nur ausgewiesen, nie abgezogen. Ohne
  Kontoauszug kein Abgleich. Erstattungen und Rückzahlungen sind kein
  Umsatz. Alle Erlös-Aufrufer gehen über `_erloese_fuer()` in `babu_web.py`.
- Nina führt (Stand 03.09.) kein Kassenbuch; ihr Umsatz kommt aus den
  Salonkee-Auszahlungen (Mai 17.745 €, Juni 12.292 €, Juli 3.448 €).
  Kontoauszüge liegen als `auszuege/<monat>/*.umsaetze.json` in der Box.

## Verbindlich: Fachwissen gehört in den Wissenscontainer (seit 07.09.2026)

- Buchhalterisches Fachwissen (was ein Beleg ist, Konten, Sätze, Umlagen,
  was eine Gutschrift wirtschaftlich bedeutet) steht in
  `werkzeuge/kompendium/kontierung-grundwissen.md` — Quelle im Repo, Kopie
  auf der H200V im Container-Mount (babu-web liest sie beim Start;
  Änderung = Datei kopieren + Container neu starten). Neue Abschnitte VOR
  der generierten Kontenübersicht (`<!-- skr04-atome … -->`).
- **Ein Container je Branche, gemountet (Stand 24.10.2026, `docker inspect`):**
  `~/kompendium-friseur` → `/data/kompendium`, `~/kompendium-barber`,
  `~/kompendium-werkstatt`, `~/kompendium-bundesrecht` → `/data/kompendium-*`.
  Welches Portal gilt, steht in den Einstellungen (`portal`: friseur/barber/
  werkstatt, `sprache`: de/tr); Texte je Branche in
  `server/belegreview/portale/`. Bundesrecht geht NICHT in die Vektorsuche
  (`MIT_BUNDESRECHT = False`, gemessen schlechter), nur `kompendium.wortlaut()`
  für in der Frage genannte Vorschriften.
- Gebaut wird mit `werkzeuge/kompendium/container_bauen.py`. Seit 14.10.2026
  (abf6f53) bestimmt eine Datei im Quellordner allein, welche Atome aus ihr
  im Container stehen — eine Korrektur ersetzt die alte Fassung, statt beide
  Fassungen nebeneinander zu lassen.
- In `gemma_buchung.REGELN` steht nur VERHALTEN (welche Frage, nicht
  abgeben, was in den Buchungstext). Kontonummern nur im Katalog
  (`kontierung.py`), das Modell vergibt nie welche.
- Fall Minijob-Zentrale (Guthaben 119 €): Kategorien `sozialabgaben`
  (6110) und `pauschsteuer_minijob` (6036), Guthaben = Aufwandskorrektur,
  eine Frage „ausgezahlt oder verrechnet?". Test
  `tests/test_minijob_guthaben.py`.

## Verbindlich: Posteingang (seit 07.09.2026)

- **`server/posteingang/` ist ein EIGENER Dienst, nicht Teil von babu-web.**
  Port 25 braucht andere Rechte, und ein Absturz im Mailempfang darf die
  Belegannahme nicht mitreißen. Eigenes Image, eigener Compose-Abschnitt
  hinter `profiles: ["posteingang"]` (startet also nicht bei `up -d`).
- **Er schreibt NIE in die Belegbox**, sondern reicht jede Sendung über
  `POST /api/aufnahme` (Anhänge) und `POST /api/dokumente` (der Mailtext)
  weiter. Grund: die Box ist ein Git-Repo mit EINEM Index, und
  `boxschreiber._commit_und_push` schützt nur innerhalb eines Prozesses.
  Genau ein Dienst darf Eigentümer sein.
- **Die Empfangsadresse ist ein Zufallswort, nie ein Name** (`post_adresse`,
  `postadresse.py`). An sie schreiben Lieferanten und Ämter — eine
  Absenderliste kann es nicht geben, also IST die Nichterratbarkeit die
  Zugangskontrolle. Der lokale Teil ist über keine Route wählbar.
- Unbekannter Empfänger = **550**. Alles andere (babu-web weg, Rate-Limit,
  Ablegefehler) = **4xx**, sonst ist die Post verloren.
- **Noch nicht in Betrieb**: MX, Portweiterleitung 25 und Reverse-DNS
  fehlen. Die Liste steht in `server/posteingang/README.md`.

## Verbindlich: Abo, Provision, Auszahlung (seit 03.10.2026)

- Preise netto zzgl. 19 % USt: Solo 39, Salon 79, Salon Plus 149 €/Monat —
  Quelle `abo.PAKETE` (Cent), `saloncheck.PAKETE[…]["preis"]` muss gleich sein.
- Stripe-Konto „0711.io“ gemeinsam mit Camp45 (seit 03.10.2026, live
  eingerichtet, `BABU_ABO=1` vom Auftraggeber geschaltet); Einrichtung nur über `server/docker/stripe_einrichten.py`.
- Bezahlen nur über Stripe (`kern_abo.py`, `stripe_api.py`, kein SDK);
  Schlüssel NUR in `docker/.env`. Live-Schlüssel nur auf mybabu.io, Test-
  Schlüssel nur woanders (`stripe_api.eingerichtet`). `BABU_ABO=1` erst nach
  Freigabe der Rechtstexte.
- Wer nur ansehen darf, entscheidet `abo.zugang()` in `_box_wache`; ohne
  Abo-Spalten ist es genau der Testmonat. In der App (Bearer) nie ein Hinweis
  aufs Abschließen (`abo.TEXTE_APP`, App Store).
- Provision = 3 × Netto-Monatspreis bei der 1. und 3. bezahlten Monats-
  rechnung, gebucht NUR über `provision.buchen` (eindeutig je Salon und
  Meilenstein); Storno über `provision.stornieren`. Monate zählen je Mandant.
- Auszahlung nur als Lauf mit Gutschrift + Bankdatei (`kern_auszahlung.py`),
  „überwiesen" bestätigt der Betreiber. Kein Geld bewegt babu selbst.
- Zustimmungen tragen die Fassung (`recht.fassung`), nicht nur ein Häkchen.

## Verbindlich: Übergabe ans Steuerbüro per Mail (seit 10.10.2026)

- **„An mein Steuerbüro geben" = `POST /api/datev/senden`**: übergeben wie
  `/uebergeben` (Festschreiben, Nachtrag, 409 bei nichts Neuem) UND das
  Übergabepaket per Mail an `steuerbuero_email` (Einstellung des Betriebs;
  beim ersten Versand fragt das Portal, `GET/POST /api/datev/steuerbuero`).
  Paket = `uebergabepaket.py`: LIESMICH, EXTF-Stapel, `belege/<monat>/…`,
  `kassenbuch/<monat>.csv`, `inhalt.json`; über `BABU_PAKET_ANHANG_MAX`
  (18 MB) in Teilen. Antwortadresse = der Betrieb. Kein OneClick, kein
  Kanzlei-Zugang nötig. ERiC (Stufe C, Senden ans Finanzamt) folgt ~Dezember.
- `postfach.senden` kennt `anhaenge=[(name, bytes, mime)]` und `antwort_an`.

## Verbindlich: Konto löschen gehört in die App (seit 14.10.2026)

- **`POST /api/konto/loeschen` ist der einzige Weg** (`kern_konto.py`), in der
  App unter Einstellungen → Aufhören. Apple 5.1.1(v) verlangt es, weil
  „Los geht's" auf dem Server einen Betrieb anlegt; eine Mailadresse reicht
  ausdrücklich nicht.
- **Jede neue Tabelle mit `un` oder `mandant_id` gehört in
  `kern_konto.NACH_UN` bzw. `NACH_MANDANT`** — oder es wird entschieden, dass
  ihre Zeilen bleiben. `tests/test_konto_loeschen.py` schlägt sonst an. Das
  ist der Zweck beider Listen: nicht Bequemlichkeit, sondern ein Alarm.
- **Was bleibt, ist `geloescht`** (Mandantennummer, `box_ref`, Dateizahl,
  `box_leer`, Zeit) und sonst nichts. Kein Name, keine E-Mail. Die Zeile ist
  zugleich die **Arbeitsliste des Betreibers**: babu leert die Belegbox in
  einem Commit, aber das Repo samt Historie löscht nur er — der
  GitChain-Dienst kennt dafür keinen Weg. `box_leer = 0` heißt: da liegt noch
  etwas.
- **Die Reihenfolge ist Pflicht: erst die Box, dann die Datenbank.** Scheitert
  die Box, gilt der Zugang noch und sie kann es erneut versuchen. Umgekehrt
  wäre der Zugang weg und die Belege lägen ohne jeden Weg dorthin da.
- **Das Abo endet dadurch nicht** — ein Apple-Abo kündigt nur Apple. Die
  Rückfrage in der App sagt das wörtlich, daneben steht „Abo verwalten".
  Diesen Satz nicht wegkürzen.
- Löschen darf nur die Inhaberin eines Betriebs mit `herkunft = "app"`. Portal-
  Betriebe hängen an einer Kanzlei (409 mit dem Weg dorthin), Mitarbeiterinnen
  kommen über die Positivliste `mitarbeitrecht` gar nicht an die Route (403).

## Verbindlich: Apple-Abo (seit 14.10.2026)

- **Ebene 1 ist die GRÖSSTE Stufe** (100 GB), 3 die kleinste. Ein Wechsel auf
  eine niedrigere Zahl ist eine Höherstufung und greift sofort. `babu.storekit`
  und App Store Connect müssen das gleich führen —
  `tests/test_apple_produkte.py` hält es.
- **Beim Kauf geht `appAccountToken` mit** (`paket.kauf_kennung`, UUIDv5 aus
  der Mandantennummer, nicht gespeichert, sondern abgeleitet). Daran findet
  Apples Server Notification den Betrieb auch ohne das Telefon. Das Abo
  (`originalTransactionId`) behält Vorrang vor der Kennung.
- Belege ohne Kennung (Käufe vor dem 14.10.2026) müssen weiter durchgehen.
- Server Notifications V2: `https://mybabu.io/api/abo/apple/meldung`, dieselbe
  URL für Produktion und Sandbox.

## App Store Connect — gelesen, nicht erinnert (Stand 24.10.2026)

- App „babu Belege" 6811956687 (`io.0711.beleg`). Zugang ohne Browser über den
  API-Schlüssel `~/.config/0711/asc-babu.p8` (`werkzeuge/asc_api.py`,
  `/usr/bin/python3` hat PyJWT). **Vor jeder Einreichung
  `python3 werkzeuge/asc_pruefung.py`** — es liest, was stimmen muss. Dazu
  `asc_abos.py`, `asc_verfuegbarkeit.py`, `asc_screenshots.py`,
  `asc_testflight.py`, `asc_nutzer.py`. Den Text einer Ablehnung liefert nur
  das Resolution Center (Chrome-Sitzung des Auftraggebers), nie die API.
- **Stand 24.10.2026:** Version 1.0 REJECTED, Build 14 VALID an der Version,
  Einreichung `58ed02dd` (22.10. 01:06 UTC) UNRESOLVED_ISSUES. Apples
  Nachricht vom 24.10. 13:54, geprüft auf **iPad Air 11" (M3), iPadOS 27.0**:
  2.1(a) „multiple attachment options in the chat feature were unresponsive";
  2.1(b) die drei Speicherstufen in der App nicht gefunden, Hinweis auf
  Sandbox und Paid Apps Agreement. Frühere Antworten/Entwürfe:
  `docs/apple-antwort-2-1b-iap.md`, `docs/apple-antwort-3-1-3c.md`,
  `docs/apple-freigabe.md`. **Apple prüft auf dem iPad** — vor jeder
  Einreichung den Build auch auf einem iPad-Simulator durchklicken, besonders
  den Reiter „Fragen" mit Anhang.
- Gemessen 24.10.: App in 175 Gebieten verfügbar (Entscheid 22.10.: weltweit,
  gemacht nur für die deutsche Steuer); `CANNOT_SELL` in allen 175 Gebieten,
  `TRADER_STATUS_NOT_PROVIDED` in 27 EU-Gebieten — Statuswerte, die Ursache
  ist ungemessen. Business-Seite am 22.10. gelesen: Paid Apps Agreement aktiv
  seit 13.10., Trader Status „In Review". Abos: Gruppe „babu Speicher", drei
  Stufen READY_TO_SUBMIT, Preise und Verfügbarkeit in 175 Gebieten, liegen der
  Einreichung bei. Nie „no storefront restrictions" an Apple schreiben.
- Prüfkonto `apple-review@0711.io` = Mandant 4 „Salon Probe" (eigene Box,
  Kanzlei 10); letzter Login 23.10.2026 16:38 UTC. Passwort steht nur in ASC
  unter Sign-In Information.
- TestFlight: interne Gruppe „Pilot", externe „Salons" mit öffentlichem Link
  (`BABU_TESTFLIGHT_LINK` live gesetzt). Cron `testflight_abgleich.py` (jede
  Minute) lädt Apple-IDs von der Warteliste ins Team und in „Pilot".
- Store-Screenshots sind echte App-Bildschirme aus dem Simulator mit
  erfundenen Demodaten („Salon Probe", 29.09.2026), keine Werbegrafiken
  (Richtlinie 2.3.3). Demodaten als `zustand.json` nach
  `Application Support/Beleg` einspielen (ohne Anmeldung heißt die Datei so).

## Rollen, Mandanten, DATEV

- Rollen `admin`/`kanzlei`/`salon`/`mitarbeit`; PAT-Konten über
  `BABU_ROLLEN` in `docker/compose.yml`. Als Mandant arbeiten geht über den
  Kopf `X-Mandant: <id>` oder `?mandant=<id>` (für Downloads) — nur für
  Mitglieder in `kanzlei_mitglied`, **Admin ist nicht automatisch Mitglied**.
- **Betreiber ≠ Kanzlei (seit 03.10.2026):** Warteliste, Registrierungen
  (IBAN!), Ambassador-Programm, Abos und Auszahlungen hängen an
  `_betreiber_wache` (nur `admin`), nie an `_verwalter_wache`. `admin`/
  `kanzlei` vergibt nur ein Admin (`_darf_rolle_vergeben`). Die
  Standard-Ablage ohne `X-Mandant` sehen nur Betrieb, Team und Admin —
  keine Kanzlei. Der öffentliche AVV (`/avv`, `/app/avv.pdf`) ist eine
  Vorlage ohne Betrieb; ausgefüllt unter `/avv/mein`.
- **Konten und Betriebe (DB gelesen 24.10.2026):** Admin sind
  `christoph@0711.io` und `nina.baic@googlemail.com`; Token-Konten
  `christoph`, `nina` (`BABU_ERLAUBT`, Benutzernamen des GitChain-Dienstes,
  `BABU_ROLLEN=christoph:admin`). Kanzleien 7 Afflek (`afflek@0711.io`),
  8 GKM, 10 „babu direkt" (Hauskanzlei der App-Betriebe). **Jeder Betrieb hat
  seine eigene Box `babu/<kurzname>-<id>/belege`** — Betriebe mischen sich
  nie (d28c564). Mandant 2 „SupremeStudio" = Standard-Box `babu/babu/belege`
  (Berater 16149, Mandant 19364), seit 28.09.2026 am stillen Archivkonto
  `supremestudio-archiv@0711.io` (inaktiv); alles bis dahin liegt dort unter
  `archiv/2026-09-28/`. Die Standard-Ablage ohne Mandant öffnen nur
  `BABU_ERLAUBT` und `BABU_STANDARD_KONTEN` (`nina.baic@googlemail.com`).
  5 „Nina Test" = `nina@0711.io` (E2E, leer seit 28.09.), 4 „Salon Probe" =
  `apple-review@0711.io` (Apples Prüfkonto), 1 Jenny, 3 nullsiebenelf GmbH
  (GKM), 7 DJBinary, 8 SupremeAcademy UG, 9 Supreme Beauty; 10–13 Rauchtests
  „bitte ignorieren", 16–23 „Mein Betrieb" aus der App (`app-…`-Konten). Die
  Boxen 14/15 (Rauchtests) liegen noch im Lesespiegel, ihre Mandanten sind
  über Konto-löschen weg — das Repo löscht nur der Betreiber. Startpasswörter
  werden nie ausgegeben — der Weg ist „Zugänge verwalten → Neues Startpasswort".
- DATEV-Seite `/datev` (`datev_seite.py`, `extf.py`): Format nach dem
  Kanzlei-Referenzstapel (Version 12, 124 Spalten, SKR leer; babu schreibt
  cp1252, `?zeichensatz=utf8` schaltbar), Prüfbefund vor jedem Export,
  Siegel `POST /api/datev/uebergeben` nur für die Kanzlei. **Ein echter
  DATEV-Import hat noch nie stattgefunden** — Abnahme ist der Import bei
  Kanzlei Afflek mit Protokoll; #REW-Meldungen danach in den Befund
  übersetzen.

## Betrieb H200V — Finger weg / Ritual

- **babu-web läuft seit 27.08.2026 als Docker-Container** (host network,
  `restart: unless-stopped`; Quelle `server/docker/`, Build-Kopie auf der
  H200V unter `~/babu-docker/`). **Seit 03.09.2026 Postgres 16** im
  Container `babu-postgres` (127.0.0.1:55432, Passwortdatei
  `~/babu-web/.pg_passwort`, täglicher `pg_dump` in `~/babu-sichern.sh`);
  `portal.db` bleibt liegen als Rückweg (`BABU_DB_URL` auskommentieren).
  In pm2 läuft nur noch `babu-tunnel`; `babu-eingang` und `babu-web` sind
  gestoppt und NUR Rückweg (pm2 gelesen 24.10.2026). **Nie anfassen:**
  `insp-app` (:7808 — seit 27.09.2026 nicht mehr babus Gateway, andere
  Projekte hängen daran) und `belege-review` (ANDERES Projekt).
  - **Achtung rsync + .env:** `docker/.env` auf der H200V (Support-Postfach,
    SMTP-Zugänge) liegt IM rsync-Bereich — immer `--exclude=.env` mitgeben,
    sonst löscht `--delete` sie beim nächsten Deploy. Sicherungen der `.env`
    gehören nach `~/sicherung/`, nie daneben — `--delete` räumt sie sonst ab.

- Deploy: **immer `rsync server/ h200v:~/babu-docker/` komplett, nie eine
  Einzeldatei** (seit 15.09.2026 dazu `rsync werkzeuge/ h200v:~/babu-docker/werkzeuge/`,
  der Ordner ist als `/app/werkzeuge` in den Container gemountet) (ein gemischter Build fiel nur auf, weil ein neues
  API-Feld live fehlte) → `cd ~/babu-docker/docker && docker compose build
  && docker compose up -d` → `GET /healthz` muss 200 mit `stand: ok` UND
  `spiegel: ok` liefern (seit 14.09.2026; `arbeit_offen` vor dem nächsten
  Deploy auf 0 warten) → geänderte Routen live durchrufen und ein neues Feld
  direkt abfragen. `docker/wache.sh` läuft im Host-Cron alle 2 min und startet
  bei `unhealthy` neu. **Täglicher Lauf:** Cron 06:15 `flock … docker exec
  babu-web python /app/werkzeuge/taeglich.py` (Stripe nachholen, Erinnerungen,
  „Heute für dich"; `docs/betrieb-golive.md` §1d). `BABU_SIGNUP=0` in Compose: das alte Selbstbedienungs-Konto
  bleibt aus. **Seit 08.10.2026** startet `/testen` (Startseite „Konto anlegen")
  30 Tage Test ohne Code (`BABU_TESTMONAT`); Warteliste und „Zugang anlegen"
  geben Salons ebenfalls Testmonat + Willkommensmail, Kanzleien eine
  Willkommensmail. Rückmeldungen tragen seit 14.09. ein Label je Betrieb
  (`betrieb-<mandant_id>`, Ein-Betrieb `betrieb-default`); jeder sieht nur
  seine.
- **Box-Anleger (seit 15.09.2026, seit 27.09. Push-to-create):** `docker/box-anleger.sh`
  läuft im Host-Cron jede Minute und ruft für Mandanten mit `box_ausstehend` und
  leerem `box_ref` IM Container `betrieb_anlegen.py --nur-box --box-anlegen`: die
  Box entsteht per Push als `svc-babu` unter `babu/<kurzname>-<id>/belege`
  (Kurzname = Name klein, Umlaute aufgelöst, ≤ 40 Zeichen), wird per
  `git ls-remote` geprüft, der Mandant geht auf `aktiv`. Kein `git init` mehr im
  GitChain-Speicher. Log `~/logs/box-anleger.log`, `--probe` zeigt nur.
- **Nachlese beim Start (seit 14.09.2026, vom Auftraggeber freigegeben):**
  60 s nach jedem Start liest babu-web einmalig Belege ohne jede Lesung
  nach (3 min bis 14 Tage alt, höchstens 20 je Box, 60 gesamt, sequenziell,
  `[nachlese]` im Log). Das ist kein Watcher und keine zweite Lesung — es
  ist der Weg von „Nochmal versuchen". `BABU_NACHLESE=0` schaltet ab.
- **Messwerte statt Vermutungen:** `/api/kpi/<monat>` → `betrieb.schloesser`
  (Warte-/Haltezeit von `_DB_LOCK` und `_LLM_SEMAPHORE`), `gemma_fehler`,
  `gemma_timeout`, `login_429`. `_DB_LOCK` und Gemma-Plätze
  (`BABU_LLM_PLAETZE`, Standard 1) werden erst nach zwei Wochen Messung
  angefasst. Login-Bremse: 20/min je IP, 5/min je Konto.
- **Sicherung:** `docker/sichern.sh` (Cron 17 3), Kopie nächtlich auf den
  Mac (launchd `io.0711.babu-sicherung`), Restore-Ritual
  `docs/betrieb/restore-probe.md`. Betriebs-Runbook: `docs/betrieb-golive.md`. Golden-Diff (`/api/belege` + `/api/abgleich/<monat>`
  als `python3 -m json.tool --sort-keys`, Dateien unter `~/golden/`) bleibt
  das Ritual bei Änderungen am Buchungsweg; der Auftraggeber verzichtet
  ausdrücklich darauf, wenn er es sagt.
- **GitChain-Standard (live seit 27.09.2026 21:18; Env gelesen 24.10.):** babu
  schreibt als Dienstkonto `svc-babu` (Integration `babu`, Namensraum `babu`)
  in den GitChain-Dienst `http://127.0.0.1:3361` (`BABU_GATEWAY`, Git Smart
  HTTP, `BABU_GIT_AUTH=bearer`). Token `~/gitchain-eingang/.pat_babu`
  (gcpat, 0600, ro im Container, je Aufruf frisch gelesen → Rotation ohne
  Neustart; Kopie `.pat_babu.svc`, alter Geräte-Token `.pat_babu.bak-vor-standard`).
  **Gelesen wird nur aus dem eigenen Lesespiegel** `~/babu-web/lesen/<ref>.git`
  (`BABU_LESEN=klon`, `git clone --mirror`, nachgezogen vor jedem Index-Neubau
  und nach jedem eigenen Push; `/healthz` → `spiegel`). Jede Box =
  `babu/<betrieb>/belege` mit eigener Arbeitskopie `~/babu-web/boxen/<ref>`
  — bis 27.09. teilten sich alle Mandanten EINE Kopie mit Ninas Box (GKM-Belege
  landeten bei SupremeStudio; behoben 94af952, Test `tests/test_box_trennung.py`).
  `.0711/container.json` ist Pflichtdatei der Box: GitChain weist einen Push
  ohne sie ab (`GESCHUETZT`, 5700a1d). `POST /api/anmelden {pat}` prüft
  Menschen-Tokens über `GET :3361/v1/user` (Dienstkonten abgewiesen); die
  `/api/*`-Routen nehmen danach nur das Cookie, Bearer nur auf `/review/<stamm>`.
  `insp-app` :7808 und `~/inspektor-store` benutzt babu nicht mehr (kein Mount).
  Umzug/Rückweg: `docker/box-umzug.sh`, `docker/box-rueckholen.sh`, Rückweg-Env
  als Kommentar in `compose.yml`, Unterlage `docs/gitchain-standard-scharfschalten.md`.
  Token-Werte nie in Chat, Log oder argv.
- **Seit 03.09.2026 ist die H200V Worker im Rancher-Cluster `dev-01`.** Gemma
  (:11435) und Embeddings (:11436) sind k3s-Pods mit hostPort; babu-web,
  babu-postgres und babu-tunnel laufen AUSSERHALB des Clusters und stehen in
  keinem Manifest (`gitlab.mediacockpit.dev/0711/h200-migration-manifests`).
  Nach jedem Cluster-Eingriff aus dem Container `:11435/v1/models`, `:11436`
  und `:3361/v1/user` (401 ohne Token = Dienst lebt) prüfen.
- Migrationen laufen beim ersten `_db()`-Open, nicht beim Containerstart:
  `schema_version` erst nach einem Request prüfen.
- H200V nur über OpenVPN (`ssh h200v`). Kein sqlite3-CLI auf dem Server;
  Postgres per `docker exec babu-postgres psql`.
- Vor schreibenden Rauchtests erst den Ist-Wert lesen — oder Testkonto.
- **Zwei Namen, ein Server (seit 17.09.2026):** `BABU_ORIGIN=https://mybabu.io` in
  Compose; `_origin_ok` lässt jeden POST durch, dessen Origin zum Host der Anfrage
  passt (CSRF-Frage, keine Liste). Mails tragen Links auf mybabu.io und kommen von
  `post@mybabu.io` (Resend, Domain verifiziert 17.09.; `BABU_ABSENDER` in `.env`).

## Datenbank

- **Jede Schemaänderung ZWEIMAL:** inline in `_sqlite_schema()`/Modul-
  `schema()` UND als `migrations/000N_*.sql` (`-- nur: postgres`-Marker
  für dialektspezifische Zeilen).
- Postgres prüft Fremdschlüssel wirklich. **Kein FK auf `nutzer(email)`
  für Kanzlei-/Betreiber-Identitäten** — PAT-Konten haben keine
  nutzer-Zeile (erster Mandant im Betrieb war ein 500). Bei neuen Tabellen
  mit `un`-Spalte einen PAT-Fall testen.

## Bauen & Testen

- **Beim Ändern nur die betroffenen Tests**, nicht die ganze Suite —
  `tests/test_container_bauen.py tests/test_kompendium.py …` sind Sekunden,
  die Suite sind zehn Minuten. Die volle Suite gehört vor den Deploy.
- Server-Suite: **immer mit explizitem `cd server/belegreview &&`**,
  `~/.venvs/babu/bin/python -m pytest tests/ -q -p no:cacheprovider`,
  Timeout 900 s (~10 min, 3216 grün).
- **Das venv liegt seit 14.10.2026 in `~/.venvs/babu`, nicht mehr in `/tmp`.**
  Dort hat macOS es ausgeräumt: `pyvenv.cfg` weg, Paketverzeichnisse
  ausgehöhlt, Python fiel still aufs System zurück und meldete Dinge, die
  nichts mit dem Code zu tun hatten. Welche Pakete es braucht, steht in
  `server/belegreview/anforderungen-test.txt` — nicht mehr als Prosa hier,
  denn zwei fehlten (cryptography, numpy), und ohne sie sammelt pytest fünf
  Testdateien gar nicht erst ein. Neu aufsetzen:
  `python3.12 -m venv ~/.venvs/babu && ~/.venvs/babu/bin/python -m pip install
  -r server/belegreview/anforderungen-test.txt`.
  Postgres-Lauf über eine Wegwerfinstanz (`initdb --locale=C
  --encoding=UTF8`, `BABU_TEST_DB_URL`).
- **Nie generisches `pkill -f pytest`** — parallel laufende Agenten teilen
  den Rechner. Eine Suite je Worktree.
- **Nie `git stash`** — der Stash-Stapel ist mit allen Worktrees geteilt.
- iOS-Simulator: `xcodebuild -project ios/Beleg/Beleg.xcodeproj -scheme Beleg
  -destination 'platform=iOS Simulator,name=iPhone 16e' -derivedDataPath /tmp/bsim build`.
  Für Store-Screenshots ein eigener Simulator `babu-appstore` (iPhone 17 Pro Max,
  `xcrun simctl create`), Statusleiste per `simctl status_bar … override --time 9:41`.
- **Zwei Ziele aus einem Ordner** (seit 08.09.2026): `Beleg` = babu
  (`io.0711.beleg`, Scanner + Hirn + Profilbauer + DATEV-Büchlein),
  `BelegPro` = babu Pro (`io.0711.beleg.pro`, dazu Termine, Kasse, Kundinnen,
  Rechnungen, Preise, Team, Verträge, Marketing, Briefkopf, Kartenzahlung).
  Der Unterschied steht **nur** in `ios/Beleg/Beleg/Ausbaustufe.swift`
  (Compile-Flag `BABU_PRO`) — keine Datei wird ausgelassen, keine Ansicht
  gelöscht. Wer einen Reiter oder eine Menüzeile hinzufügt, trägt sie dort
  ein. Beide Ziele bauen, `ios/Tests/zuschnitt` hält den Zuschnitt fest
  (läuft zweimal, mit und ohne Flag).
- Ninas iPhone (UDID `00008130-001411E00146001C`):
  `… 'generic/platform=iOS' DEVELOPMENT_TEAM=8L87Z2GRSG CODE_SIGN_STYLE=Automatic
  -allowProvisioningUpdates -derivedDataPath /tmp/bbuild` + `xcrun devicectl
  device install app` (WLAN wackelig: zweiter Versuch hilft, Kabel sofort).
- App-Logik-Harnesse: `ios/Tests/run.sh` — Fixtures pflegen, nie löschen.
- Lokale Vorschau des Portals: Python-Änderungen brauchen einen Neustart
  des Vorschau-Servers; Mandantenboxen lokal nur mit `BABU_STORE_WURZEL=/`
  und `box_ref` ohne führenden Slash.

## Git

- Arbeiten im Worktree, mergen per ff: im Worktree `git fetch && git rebase
  origin/main`, dann im Haupt-Checkout `git reset --hard origin/main &&
  git merge --ff-only <branch> && git push`. **Nie force-pushen** — der
  autonome Fixlauf (Meldeschleife, launchd 30 min) pusht parallel.
- Subagenten: eigener Worktree, nur committen; Übernahme per cherry-pick,
  danach `git worktree remove` + Branch löschen.
- iOS-Merge-Falle: im Haupt-Checkout gebaut ≠ im Worktree committet — vor
  dem Merge diffen.
- **Zwei Remotes:** `gitlab` (gitlab.mediacockpit.dev/0711/babu) trägt `main`;
  `origin` (GitHub C-0711/babu) hängt nach (24.10.2026: 10 Commits). Der
  Fix-Lauf arbeitet auf `origin/main` — GitHub per Merge nachziehen (nie
  Force), sonst rollt er einen alten Stand aus.
- **Worktrees aufräumen:** `git worktree list` zeigte am 24.10.2026 13 Einträge,
  darunter vier Agent-Worktrees 246–337 Commits hinter `main` mit je 1–4 nie
  übernommenen Commits, und einen toten (`/private/tmp/fix-88`, per
  `git worktree prune` entfernt). Vor neuer Arbeit `git worktree prune`;
  Agent-Worktrees nach dem Cherry-pick entfernen, Branch löschen.

## Bekannte Fallen

- Alte `zustand.json` müssen laden: neue Beleg-/Zustand-Felder IMMER
  optional (`ocrText`-Altlast: Decodable nutzt Defaults nicht).
- Simulator-Keychain ≠ iPhone-Keychain; App-Neuinstallation verliert die
  Keychain → Nina muss sich neu verbinden.
- Testdaten (echte Salon-/Bankdaten) liegen in `~/Downloads` und bleiben
  lokal — nie committen, nie hochladen.
- pypdfium2 ist nicht threadsicher: jeder PDF-Zugriff unter `PDFIUM_LOCK`.
- Golden-Vertrag `tests/test_api.py` (Weingärtle `buchungssatz`/
  `buchungstext` byte-gleich) — wer Buchungstexte anfasst, ändert die
  Fixture bewusst mit.

Die `~/CLAUDE.md` im Home beschreibt die Mac-OCR-Werkzeugkette
(`~/bin/vision-ocr/`) — anderes Projekt, dort gelten eigene verbindliche
Vorgaben.
