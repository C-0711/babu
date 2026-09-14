# babu live — ohne Pro

Stand: 14.09.2026, main `f4d908c` deployt, beide App-Ziele auf Ninas iPhone.
Alle Pfade relativ zum Repo; Server unter `server/belegreview/`, App unter `ios/Beleg/`.

## Kontext

Bahn 1 des Umsetzungsplans („babu Start live", `docs/umsetzung-zwei-produkte.md`) ist zur Hälfte
gebaut: Mandanten-Isolation, zwei App-Ziele, Onboarding-Werkzeug und Posteingang-Code sind seit
14.09. produktiv. Was fehlt, stand verstreut in drei Dokumenten und war teils überholt. Drei
Erkundungen haben am 14.09. jeden Punkt **am Code** geprüft (Befunde A/B/C unten). Dieser Plan
ersetzt die drei Listen durch eine geprüfte Liste mit Einordnung, Wochenplan und Nachweis.

**Rahmen (Auftraggeber, 14.09.):**
- TestFlight **extern** auf Einladung, 5–20 Betriebe; erster Build durch die Beta App Review
  (braucht Datenschutz-URL + Testkonto). Kein App-Store-Review, kein In-App-Kauf, kein
  Selbstbedienungs-Onboarding.
- Kanzlei ist Teil des Go-Live: **eigenes Kanzlei-Konto für GKM Neff Bonn** (Afflek bleibt
  Testkanzlei); Kanzlei legt Betriebe im Portal an, du legst nur die Belegbox am Gateway an.
  Echter DATEV-Import einmal vorher.
- 4–6 Wochen. Pro bleibt im Repo, baubar und getestet, wird nicht verteilt.
- Mails über einen Mail-Dienst mit API (SMTP-Relay, `postfach.py` bleibt). Apple-Konto und
  Rechtstexte (Anwältin) laufen bereits.
- Rückmeldungen je Betrieb getrennt **plus** Kopie an eine Support-Adresse.
- Sicherung außer Haus: nächtlicher rsync-Pull auf diesen Mac per VPN.
- Pilot kostenlos (Datum in der Einladung, Beispielpreise ausgeblendet); Datenlöschung und
  Auskunft als dokumentierter Betreiber-Handweg, Code erst auf Verlangen.

**Zwei billige Pflichtpunkte, die in keiner Liste standen:** `POST /api/signup`
(`babu_web.py:3925`) legt heute jedem ein Konto an → hinter `BABU_SIGNUP=0` (404), Formular
in `portal.html:7395` und `server/landing/index.html` verstecken. Und
`ITSAppUsesNonExemptEncryption = NO` in `Support/Info.plist`, sonst fragt App Store Connect bei
jedem Upload.

**Regeln, die der Plan einhält:** Lesepfad (OCR/Gemma-Semantik) wird nicht angefasst; kein
Watcher-Prozess; insp-app wird nicht ferngesteuert (Box-Anlage bleibt Handarbeit); UI-Sprachregel;
Schemaänderungen zweimal (inline + `migrations/000N`); Golden-Diff bei jedem Deploy; rsync komplett.

---

## Einordnung: Pflicht · Soll · Später

| Klasse | Punkte |
|---|---|
| **Pflicht** (ohne das kein fremder Betrieb) | B10 Rückmeldungen je Betrieb · B1 Lebenszeichen · B8 `_hat_ablage` in login/ich · Signup aus · C1 Signierung/Archiv · C2 Privacy-Manifest · C3 Version aus einer Quelle · C10 ATS-Ausnahme raus · C6 „Ablage wird eingerichtet" sichtbar · C12 Testphase-Abschnitt verstecken · A1/A1b Passwort vergessen + Mailversand · C5 Link dazu in der App · A7 Rechtstexte + AVV · B7 Sicherung außer Haus + Restore-Probe · B2-Teil Log-Rotation · A6 Onboarding als Runbook · A8 Löschung als Handweg · A9-Rest Beispielpreise ausblenden |
| **Soll** (in 6 Wochen, senkt Support) | A4 Sitzungen nach Passwortwechsel (Migration 0006) · A3 Geräte auflisten/widerrufen · A5 Bremse je Konto · B2-Rest Zugriffszeile mit Konto+Betrieb · B3/B4/B5 nur messen (Zähler in `/api/kpi`) · B6 Nachlese beim Start (berührt nur den *Aufruf* des Lesepfads; **vom Auftraggeber am 14.09. ausdrücklich freigegeben**) · C8 Hinweis bei PDF > 20 Seiten · C9 Backoff bei Upload-Retry · B10-Zusatz Support-Mail-Kopie |
| **Später** | A2 E-Mail ändern · A8 Löschung im Code · A9 Tarif/Zahlung · B3 Retry/Semaphore-4 (erst nach 2 Wochen Messung, Pod ist mit ctax geteilt) · B4 Ratenbegrenzer persistent · B5 `_DB_LOCK` lösen · B6 Job-Persistenz · B9 Posteingang scharf (7 externe Schritte, keine öffentliche IP) · C7 Offline-Einschätzung nachholen (Buchungsweg) · C11 zweites App-Icon · C13 `/ablage`-Lograuschen |

Reihenfolge-Regel: **B10 und B1 zuerst** — beides muss vor dem ersten fremden Gerät live sein,
unabhängig vom TestFlight-Stand. Der Lesepfad wird an keiner Stelle geändert.

---

## Wochenplan

| W | Code (ich) | Nur du / Dritte | Prüfbares Ergebnis |
|---|---|---|---|
| **1** | **B10** Label `betrieb-<mandant_id>` neben `von-nina` (`gitlab_meldungen.als_issue/issues_holen`), Cache je Label, `freigeben/beanstanden` nur mit eigenem Label sonst 404. **B1** `GET /healthz` + Compose-Healthcheck + `docker/wache.sh` (Cron: unhealthy → restart). **B8** `_hat_ablage` in `/api/login:1753` und `/api/ich:1864`. **Signup** hinter `BABU_SIGNUP`. **B2-Teil** `logging: max-size` in Compose. Deploy, Golden. | Mail-Dienst wählen (Postmark/Brevo/Mailgun), SPF/DKIM/DMARC für `babu.0711.io`, SMTP-Zugang als `.env` neben Compose (0600, nie im Repo). Support-Postfach anlegen. App Store Connect: App-Eintrag io.0711.beleg prüfen, Testgruppe „Pilot". GKM Neff: Termin DATEV-Import W4. Offene `von-nina`-Issues von Nina im GitLab mit `betrieb-2` etikettieren. | Suite grün; `test_rueckmeldungen_je_betrieb`: zwei Konten sehen nur eigene Meldungen; `/healthz` live 200; Nina sieht ihre Meldungen weiter. |
| **2** | **C1** `DEVELOPMENT_TEAM` in `project.yml`+pbxproj (4 Configs), `ios/Beleg/ExportOptions.plist` (app-store-connect), `ios/archiv.sh` (archive → export → upload). **C3** Version+Build aus `project.yml` (XcodeGen), `app-download/` auf TestFlight-Link. **C2** `PrivacyInfo.xcprivacy` (FileTimestamp C617.1, UserDefaults CA92.1, kein Tracking), `ITSAppUsesNonExemptEncryption=NO`. **C10** ATS-Block + `NSLocalNetworkUsageDescription` raus. **C6** Hinweiskarte aus `store.ablageFehlt` in `CaptureTab`/`ListeView`, Feld persistieren. **C12** Testphase hinter `#if DEBUG`. Harness `zuschnitt` prüft Signierung/Version/Privacy-Datei. | App-Datenschutz-Formular passend zur Privacy-Datei. Dich + Nina als interne Tester. SMTP-Zugangsdaten liegen vor. | Build 0.1.0 (2) intern in TestFlight auf deinem und Ninas iPhone; `ios/Tests/run.sh` grün, beide Ziele bauen. |
| **3** | **A1** `POST /api/passwort-vergessen {email}` ohne Anmeldung (immer 200, Bremse je IP wie `_RESET_VERSUCHE` + je Konto über `_reset_anfordern_erlaubt`), Zeile wie `_passwort_neu:4747-4755`, Mail über `postfach.senden` nach Muster `kanzlei_routen._einladung_verschicken:743-779`; beim Einlösen in `/api/passwort-reset:4796` zusätzlich `DELETE FROM app_schluessel WHERE un=?`. Portal: „Passwort vergessen?" am Login (`portal.html:~1015`). **C5** Link in `EinstellungenView` → `/portal#passwort-vergessen`. **A1b** `BABU_SMTP_*` in Compose aus `.env`. **B10-Zusatz** Kopie an Support-Adresse (10 Zeilen im POST). **A9-Rest** `PAKETE` im Salon-Check ausblenden. | Rechtstexte-Entwürfe prüfen (Verarbeitungen: Belege, Kontoauszüge, Personal, Gemma auf eigener H200V, GitLab-Meldungen). Kanzlei-Konto GKM Neff anlegen (Zugänge verwalten, Rolle kanzlei). Testmandant im Kanzlei-Portal anlegen → Einladungsmail muss echt ankommen. | Reset Ende-zu-Ende auf Produktion mit Testkonto: Mail → Link → neues Passwort → altes Gerät 401 „Zugang gilt nicht mehr". Kanzlei-Einladung kommt an. |
| **4** | **A7** Texte in `portal.html:2963-2977` und `landing/index.html:893`, Routen `/impressum`, `/datenschutz`, `/agb`; Link „Rechtliches" in `EinstellungenView`; AVV-PDF unter `/app/avv.pdf`. **B7** `docker/sichern.sh` ins Repo (aus `~/babu-sichern.sh` übernommen + Logos, `postausgang/`, Geheimnisse als `age`-Archiv mit Mac-Schlüssel, Box-Bundles je babu-Repo), launchd auf dem Mac: nächtlicher rsync-Pull `h200v:~/backups/babu/` → `~/Backups/babu/`, Alarm wenn Kopie > 48 h; Restore-Ritual in `README.md`. **A4** `nutzer.sitzung_ab` inline + `migrations/0006_sitzung_ab.sql`. **A3** `GET/DELETE /api/geraete`. | DATEV-Import bei GKM Neff: Ninas Monat über `/datev` exportieren, importieren lassen, #REW-Protokoll. Build 3 mit Rechtstexten → **Beta App Review** einreichen (Testkonto + Notizen). AVV final. | Restore-Protokoll (Dump → Wegwerf-Postgres auf dem Mac → Zeilenzahlen gleich, Bundle geklont, Geheimnisse entschlüsselt) in `docs/betrieb/restore-probe.md`; DATEV-Importprotokoll; Build 3 in Review. |
| **5** | **B3/B4/B5 messen**: `_DB_LOCK` und `_LLM_SEMAPHORE` in Mess-Hüllen (Name bleibt, AST-Wächter bleibt gültig), Zähler in `/api/kpi`-Block `betrieb`; `BABU_LLM_PLAETZE` (Standard 1) als Schalter. **B2-Rest** Zugriffszeile in `_metrik_mw` für ≥400 oder >2 s mit `request.state.un/mandant`. **C8**, **C9**, **A5**. **B6 Startnachlese** (freigegeben, Design unten). Runbook `docs/betrieb-golive.md` (Betrieb anlegen, Box am Gateway, `--nur-box`, Einladung, Support, Löschungs-Handweg A8). Golden Nina. | Zwei Testbetriebe: Konto im Kanzlei-Portal, Box am Gateway, `betrieb_anlegen.py --nur-box`. Checkliste komplett. Beta Review durch → erste 5 Betriebe per TestFlight-Einladung + AVV. | Checkliste abgehakt, Golden byte-gleich, 5 Betriebe eingeladen. |
| **6** | Puffer. Messwerte sichten (Gemma-Wartezeit p95, `db_lock_warte_max_s`) → Entscheidung B3/B5 als eigener Schritt danach. Kein neuer Umfang. | Rollout bis 20 Betriebe. Support-Rhythmus: täglich Postfach + Meldungen. | Jeder Betrieb hat einen Beleg hochgeladen; GKM Neff hat je Betrieb einen Stapel geholt. |

**Abhängigkeiten:** Apple-Eintrag → C1 Upload (W2) → Beta Review (W4, braucht A7) → externe
Einladung (W5). Mail-Dienst + DNS (W1) → A1b → A1 und Kanzlei-Einladung (W3) → Onboarding ohne
dich. B10+B1+B8 (W1) → erster fremder Betrieb. C6+C12 (W2) im ersten Build, weil jeder neue
Betrieb im Zustand „Ablage fehlt" startet. Kanzlei-Konto (W3) → DATEV-Import (W4) → Checkliste.
A4 vor A3. B7 unabhängig, vor dem ersten fremden Betrieb.

---

## Entwürfe der Pflichtpunkte (kleinste tragfähige Lösung, Bestand wiederverwenden)

**B10 Rückmeldungen.** `_betrieb_label()` neben `_box_wache`: `betrieb-<mandant_id>` aus
`_AKTIVER_MANDANT`, sonst `betrieb-default` (PAT-Konten). `als_issue(m, betrieb)` → Labels
`bug,von-nina,betrieb-N` (`von-nina` bleibt, der autonome Fixlauf filtert darauf; GitLab legt
Labels selbst an). `issues_holen(labels="von-nina,betrieb-N")` (UND-Verknüpfung, Signatur
existiert). `_MELDUNGEN_CACHE` → dict je Label. `_meldung_im_zustand` prüft zusätzlich das Label,
sonst **404**. Puffer trägt das Issue-Dict inkl. Labels. Tests in `tests/test_meldungen_routen.py`
(Fixture patcht `_box_wache`, `_AKTIVER_MANDANT` setzen): Label gesetzt; zwei Mandanten
verschiedene Listen; `freigeben` fremd → 404; PAT → `betrieb-default`. Nicht: eigene Tabelle,
Projekt je Betrieb, Meldeschleife umbauen.

**B1 Lebenszeichen.** `GET /healthz` (bewusst ≠ `/health`, das gehört `babu-eingang` auf :7843),
**synchrones `def`** (läuft durch den Threadpool, hängt also mit, wenn der Pool hängt):
`_DB_LOCK.acquire(timeout=5)` + `SELECT 1` → sonst 503 „db"; `default_box().klon.is_dir()` →
sonst 503 „box"; Gemma `:11435/v1/models` 2 s → Feld `gemma: ok|weg`, Antwort bleibt 200
`stand: degraded`; `arbeit_offen = len(_HINTERGRUND_TASKS)`. Ohne Anmeldung, keine Geheimnisse.
Compose: `healthcheck` per `python -c urllib…` (kein curl im Image), interval 30 s, start_period
90 s. Neustart bei unhealthy macht Docker nicht selbst → `docker/wache.sh` im Host-Cron alle 2 min
(`docker inspect … Health.Status` → `docker restart`, Zeile ins Log). Kein Sidecar mit
Docker-Socket. Test `tests/test_healthz.py`.

**B8.** `/api/login:1753` und `/api/ich:1864` von `box_mitglied(un)` auf `_hat_ablage(...)`
(`babu_web.py:1633`); beide außerhalb der `_DB_LOCK`-Blöcke, `mandanten._sitzung` nimmt eigene
Verbindung. Tests in `tests/test_eigene_box_ohne_kopf.py`: `box_ausstehend` → false, `box_ref` →
true, PAT → wie `box_mitglied`.

**C1–C3, C10, C2 (TestFlight).** `DEVELOPMENT_TEAM=8L87Z2GRSG` in `project.yml:33` und den vier
Configs in `project.pbxproj` (247, 277, 307, 337); `ios/Beleg/ExportOptions.plist`
(method `app-store-connect`); `ios/archiv.sh`: `xcodebuild archive` (Scheme `Beleg`, generic iOS)
→ `-exportArchive` → Upload; Version und Build nur in `project.yml:29-30`, pbxproj per XcodeGen,
Build auf 2; `app-download/index.html` und `manifest.plist` auf TestFlight-Link umstellen;
`ios/Beleg/Beleg/PrivacyInfo.xcprivacy` (Gründe C617.1, CA92.1; kein Tracking, keine gesammelten
Daten außer Konto/Belegen ohne Verknüpfung zu Identifiern → mit dem App-Privacy-Formular
abstimmen); `Info.plist:13-17` ATS-Block raus, `ITSAppUsesNonExemptEncryption=NO`. Harness
`ios/Tests/zuschnitt` prüft: Team gesetzt, Privacy-Datei im Target, Version ≠ 0.1.0/1.

**C6 + C12 (App).** `store.ablageFehlt` in `Store.swift:47-50` persistieren und in `CaptureTab`
über der Einrichtungskarte als Hinweis „Deine Ablage wird noch eingerichtet — babu meldet sich"
zeigen (Sprachregel, kein Technik-Wort); Verschwinden bei erstem 200. Testphase-Abschnitt
(`EinstellungenView.swift:149-185`) hinter `#if DEBUG`. Harness `einrichtung` um den Fall
„Ablage fehlt bleibt nach Neustart sichtbar" erweitern.

**A1 + A1b + C5 (Passwort vergessen).** Route `POST /api/passwort-vergessen {email}`: `_origin_ok`,
antwortet **immer 200** (kein Konto-Orakel), Bremse je IP (`_RESET_VERSUCHE`-Muster) und je Konto
(`_reset_anfordern_erlaubt`, `_reset_aufraeumen`), Zeile wie in `_passwort_neu:4747-4755`, Mailtext
nach `_einladung_verschicken`, Versand `postfach.senden` (SMTP-Relay des Mail-Dienstes über
`BABU_SMTP_HOST/PORT/NUTZER/PASSWORT`, `BABU_ABSENDER`). Einlösen in `/api/passwort-reset:4796`
löscht zusätzlich alle `app_schluessel` des Kontos (Übergang für A3/A4). Portal-Link am Login,
kleines Formular; App-Link in `EinstellungenView` unter dem Passwortfeld (öffnet Safari auf
`/portal#passwort-vergessen`). Tests: `tests/test_passwort_vergessen.py` (200 auch bei
unbekannter Mail, Bremse, Mail im Postausgang mit Link, Einlösen entwertet Geräteschlüssel).

**A7 (Recht).** `RECHT`-Objekt in `portal.html:2963-2977` mit den Anwaltstexten füllen, Routen
`/impressum`, `/datenschutz`, `/agb` (Beta Review braucht URLs), Landing-Fußzeile, Link in
`EinstellungenView` „Rechtliches", AVV als PDF. `test_sprachregel.py` bleibt grün (Texte enthalten
keine verbotenen Wörter in `//`-Kommentaren).

**B7 (Sicherung).** `docker/sichern.sh` aus `~/babu-sichern.sh` übernehmen (Cron zeigt danach auf
das Repo-Skript): `pg_dump -Fc` (14 Stände), je babu-Box unter `~/inspektor-store` ein
`git bundle create --all`, `~/babu-web` ohne Klone (`logos/`, `postausgang/`, `portal.db`),
Geheimnisse (`.session_geheimnis`, `.pg_passwort`, `.gitlab_token`, `.pat_babu`) als
`tar | age -r <Mac-Schlüssel>`. Mac: launchd nächtlich `rsync -a h200v:~/backups/babu/
~/Backups/babu/`, Alarm bei Kopie > 48 h (Time Machine macht die dritte Kopie). Restore-Ritual
in `README.md`: Wegwerf-Postgres auf dem Mac, `pg_restore`, `count(*)` je Tabelle gegen
Dump-Tag, `git clone <bundle>`, Geheimnisse entschlüsseln; Protokoll mit Datum in
`docs/betrieb/restore-probe.md`, einmal vor Go-Live, dann monatlich. Nicht: PITR, ganzer
`inspektor-store`, zweiter Server.

**A6 + A8 als Runbook** `docs/betrieb-golive.md`: Kanzlei legt Konto+Mandant im Portal an
(`api_mandant_anlegen`, Einladungsmail automatisch); du legst die Box am Gateway an und rufst
`werkzeuge/betrieb_anlegen.py --nur-box --box-ref …` (Rückgabecode 0); Support-Weg; Löschung:
Konto `aktiv=0`, Box archivieren (Git, nicht löschen), Auskunft als ZIP aus Box + Einstellungen,
in der Datenschutzerklärung mit 30-Tage-Frist genannt.

**Soll-Entwürfe (kurz).** A4: Spalte `nutzer.sitzung_ab`, Cookie trägt Ausgabezeit, `_pruefen`
vergleicht; Migration 0006 inline + SQL. A3: `GET /api/geraete` (Name, erstellt, zuletzt),
`DELETE /api/geraete/{hash}`; Portal-Liste unter Einstellungen. B3/B5-Messung: `_MessSchloss`
kapselt `threading.Lock` mit gleicher Oberfläche, Name `_DB_LOCK` bleibt (AST-Wächter), Zähler
`db_lock_warte_max_s`, `llm_warte_s`, `llm_halte_s`, `gemma_fehler`; Ausgabe in
`/api/kpi/{monat}` Block `betrieb` (`babu_web.py:5361`). B6 Startnachlese (freigegeben 14.09.):
FastAPI-`startup` → nach 60 s eine Task, je Box (Default + `mandant` mit `box_ref`) in kopiertem
Kontext (`_AKTIVE_BOX`), Kandidaten `status in (erfasst, unlesbar)` **und** `dokumentklasse is
None`, 3 min < Alter < 14 Tage, Deckel 20/Box, 60 gesamt, **sequenziell** über den vorhandenen
`_hintergrund_lesen`; Idempotenz durch `_review_ueberschreibbar`. Kein Retry in `_gemma()`, keine
Semaphore-4 (Pod geteilt mit ctax; erst p95-Wartezeit > 60 s messen).

---

## Verifikation

- **Je Schritt:** `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/ -q -p
  no:cacheprovider` (Timeout 600 s; 2276 grün plus 5 zeitabhängige rote in `test_kalender.py`, die
  in W1 auf relative Daten umgestellt werden) und `ios/Tests/run.sh`; beide Ziele bauen.
- **Je Deploy:** Sicherung, rsync komplett, `compose build && up -d`, `/healthz` 200 mit
  `arbeit_offen: 0`, Golden `vorher`/`nachher` (`/api/belege`, `/api/abgleich/<monat>`) für
  Nina byte-gleich, neue Routen live durchrufen, Container-Log ohne Traceback.
- **Go-Live-Checkliste (Ende W5):**
  1. Suite und Harnesse grün, Build beider Ziele.
  2. `/healthz` 200, Postgres-Healthcheck grün, `wache.sh` im Cron.
  3. Golden für Nina byte-gleich.
  4. Zwei Testbetriebe über das Kanzlei-Portal GKM Neff angelegt, Einladungsmail angekommen,
     Passwort selbst gesetzt; Box am Gateway, `--nur-box` Rückgabecode 0.
  5. Je TestFlight-Gerät: „Ablage wird noch eingerichtet" war vor der Box sichtbar, danach
     „alles bereit"; ein Beleg → genau in der eigenen Box (`git log` beider Boxen), Ninas Box
     unverändert.
  6. Kanzlei sieht beide Betriebe in `/api/kanzlei/mandanten`, Acting-as funktioniert.
  7. DATEV-Stapel je Testbetrieb erzeugt und mit `POST /api/datev/uebergeben` gesiegelt;
     Importprotokoll aus W4 liegt vor, #REW-Meldungen im Prüfbefund.
  8. Rückmeldung von Betrieb A: B sieht sie nicht, `freigeben` mit fremder iid → 404; Kopie an
     Support-Adresse angekommen.
  9. Passwort-vergessen: Mail → Link → neues Passwort → altes Gerät 401.
  10. Restore-Probelauf auf dem Mac protokolliert; Kopie außer Haus < 48 h alt; Geheimnisse im
      Archiv.
  11. `/impressum`, `/datenschutz`, `/agb` erreichbar und verlinkt (Portal, Landing, App); AVV je
      Betrieb abgelegt.
  12. `POST /api/signup` → 404; Salon-Check zeigt keine Preise; Testphase-Abschnitt in der
      TestFlight-App nicht sichtbar.
  13. Beta App Review bestanden; Testgruppe „Pilot" mit Support-Adresse in den Notizen.
  14. `docs/betrieb-golive.md` vorhanden.

---

## Befund A — Konto, Recht, Geld (am Code geprüft, 14.09.)

| # | Punkt | Ist | Beleg | Tage |
|---|---|---|---|---|
| A1 | Passwort vergessen ohne Betreiber | fehlt; Reset-Mechanik (Token, 14 Tage, Bremse) existiert, hängt an `_verwalter_wache`, Link landet in der JSON-Antwort | `babu_web.py:4726-4806`, `passwort_reset.py`, `portal.html:1015` | 2–3 |
| A1b | Mailversand | `postfach.py` (SMTP) existiert, produktiv nicht konfiguriert → `.eml` im Postausgang; einziger Nutzer Kanzlei-Einladung | `postfach.py:28-93`, `kanzlei_routen.py:743-779` | 1–2 + DNS |
| A2 | E-Mail änderbar | fehlt; Schlüssel in 5 Tabellen, FK unter Postgres | — | später |
| A3 | Geräte auflisten/widerrufen | fehlt; `app_schluessel` ohne DELETE, läuft nie ab | `babu_web.py:370,1783,543-557` | 1 |
| A4 | Sitzungen nach Passwortwechsel | bleiben gültig | `babu_web.py:596,1806,4795` | 1 |
| A5 | Login-Sperre | nur je IP | `babu_web.py:1732,1767` | 0,5–1 |
| A6 | Betrieb anlegen | Werkzeug vorhanden; Box bleibt Handarbeit (Code 3), Startpasswort einmal auf Konsole | `werkzeuge/betrieb_anlegen.py:22-52,297-378,567-598` | Runbook |
| A7 | Impressum/Datenschutz/AGB | Platzhalter, in App nichts, kein AGB, kein Haken beim Signup, kein AVV | `portal.html:2963-2977`, `landing/index.html:893`, `babu_web.py:3925-3968` | 0,5–1 + extern |
| A8 | Auskunft/Löschung je Betrieb | fehlt; Belege per Lösch-Commit, Historie bleibt | `babu_web.py:2577-2601` | Handweg |
| A9 | Tarif/Testphase | drei Beispielpreise, kein Feld am Konto | `saloncheck.py:204-236` | ausblenden |

## Befund B — Betrieb und Robustheit (am Code geprüft, 14.09.)

| # | Punkt | Ist | Beleg | Risiko |
|---|---|---|---|---|
| B1 | Lebenszeichen | kein `/health` in babu-web; Compose-Healthcheck nur Postgres | `compose.yml:40-53` | hoch |
| B2 | Logging | kein `logging`, ~58 `print` mit `[bereich]`-Präfix; Docker-Log unbegrenzt | `babu_web.py:1489,…` | hoch (Platte) |
| B3 | Gemma | `_LLM_SEMAPHORE(1)` global; kein Retry; `asyncio.timeout(90)` lässt den Thread bis 120 s weiterlaufen | `babu_web.py:6151,2221,2426`, `gemma_buchung.py:580` | hoch, erst messen |
| B4 | Ratenbegrenzer | je IP, im RAM | `babu_web.py:1690-1723` | mittel |
| B5 | `_DB_LOCK` | global, 107+12 Stellen, unter Postgres bewusst beibehalten | `babu_web.py:211-218` | erst messen |
| B6 | Arbeit über Neustart | alles im RAM; Neustart mitten in Lesung → „unlesbar", niemand liest nach | `babu_web.py:2432-2441,888` | hoch |
| B7 | Sicherung | nur auf dem Server, Ziel dieselbe Maschine, Geheimnisse/Logos fehlen, kein Restore-Probelauf | `README.md:134-149` | hoch |
| B8 | Mehrbetrieb | funktioniert mit Tests; `_hat_ablage` fehlt in `/api/login`, `/api/ich` | `babu_web.py:1571-1668,1753,1864` | mittel |
| B9 | Posteingang | gebaut, 29 Tests, hinter Profil; 7 externe Schritte | `server/posteingang/README.md` | später |
| B10 | Rückmeldungen | **jeder Betrieb sieht und schließt Meldungen aller anderen** | `gitlab_meldungen.py:25-36,103`, `babu_web.py:7166-7285` | **hoch** |

## Befund C — App und Leseweg (am Code geprüft, 14.09.)

| # | Punkt | Ist | Beleg | Tage |
|---|---|---|---|---|
| C1 | Signierung/Archiv | `DEVELOPMENT_TEAM=""` in 4 Configs, kein ExportOptions, kein Archiv-Skript | `project.pbxproj:247,277,307,337` | 0,5–1 |
| C2 | Privacy-Manifest | fehlt | — | 0,5 |
| C3 | Version | 0.1.0/1 dreifach, Build 1 verbraucht | `project.yml:29-30`, `manifest.plist:23` | 0,5 |
| C4 | Verteilung | Ad-hoc `itms-services` | `app-download/index.html:35` | entfällt |
| C5 | Passwort vergessen in App | fehlt | `EinstellungenView.swift:227-336` | 0,5 |
| C6 | `ablageFehlt` sichtbar | gesetzt, nirgends gelesen, nicht persistiert | `Store.swift:47-50,688-704` | 0,5 |
| C7 | Offline umgeht Einschätzung | Retry ohne `ergebnis`, Server rät | `Store.swift:262-270`, `babu_web.py:2676` | später |
| C8 | PDF > 20 Seiten | stumm abgeschnitten | `CaptureTab.swift:14,221` | 0,5 |
| C9 | Kein Backoff | jeder Foreground-Wechsel stößt alles an | `Store.swift:262-270` | 0,5 |
| C10 | ATS-Ausnahme | noch drin | `Support/Info.plist:13-17` | 0,25 |
| C11 | App-Icon | eins für beide Ziele | `Assets.xcassets/AppIcon` | mit Pro |
| C12 | Testphase-Abschnitt | sichtbar für alle | `EinstellungenView.swift:149-185` | 0,25 |
| C13 | `/ablage` 400 | kein Fehler: Verbindungstest mit `.txt`, 400 = Schlüssel gültig | `AblageService.swift:69-85` | Lograuschen |

In Ordnung: Einrichtungskarte im schmalen Bau (2 Zeilen), Upload `/api/aufnahme` nach
`/api/buchung/einschaetzung`, 401-Behandlung, Retry-Status je Beleg persistiert, 11 Harnesse,
`zuschnitt` prüft beide Bauten und die Sprachregel; Mandanten-Auflösung, Box-Registry,
`_client_ip`, Postgres-Secret, Aufnahmewerkzeug mit Nachprüfung.
