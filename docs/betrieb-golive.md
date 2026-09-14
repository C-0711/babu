# Betrieb im Pilot — das Runbook

Für den, der den Pilot betreibt (Stand 14.09.2026, Plan `docs/golive-babu-2026-09-14.md`).
Alles hier ist Handarbeit an einem Werkzeug, nicht aus dem Kopf. Was der Code prüft, steht
dabei; was nur ein Mensch tun kann, ist als solches markiert.

## 1. Einen Betrieb aufnehmen

Der Weg im Pilot: **die Kanzlei legt Konto und Mandant im Portal an, der Betreiber legt die
Belegbox an.** Selbstbedienung gibt es nicht (`BABU_SIGNUP=0`).

1. **Kanzlei, im Portal** (Rolle `kanzlei`, angemeldet): Verwaltung → Mandanten → „Neuer
   Mandant" — Name des Betriebs, E-Mail der Inhaberin, DATEV-Berater- und Mandantennummer.
   Das Konto entsteht mit `box_ausstehend`, und die **Einladungsmail geht automatisch**
   (`kanzlei_routen._einladung_verschicken`) — sobald `BABU_SMTP_*` gesetzt ist. Vorher liegt
   sie als `.eml` in `~/babu-web/postausgang/` und der Link steht in der Antwort der Kanzlei.
2. **Betreiber, auf der H200V: die Belegbox.** Das Gateway `insp-app` wird nicht
   ferngesteuert; die Box entsteht dort von Hand als leeres Repo unter dem Workspace:

   ```bash
   ssh h200v
   cd ~/gitchain/tresor/inspektor/ws-christoph0711.io/
   git init --bare --initial-branch=main <kurzname>.git
   ```

   Der `box_ref` lautet dann `inspektor/ws-christoph0711.io/<kurzname>`.
3. **Betreiber: Box verknüpfen und nachprüfen**, aus dem Container heraus (dort liegen
   Postgres-Zugang und Store):

   ```bash
   ssh h200v 'docker exec babu-web python werkzeuge/betrieb_anlegen.py --nur-box \
     --email <inhaberin@…> --box-ref inspektor/ws-christoph0711.io/<kurzname>'
   ```

   Rückgabe 0 = alles da. 3 = die Box fehlt noch am erwarteten Pfad (Schritt 2 prüfen).
   Alternativ im Portal: Verwaltung → Mandant → „Belegbox verknüpfen" (nur Betreiber-Ebene).
4. **Die Inhaberin**: setzt über den Link ihr Passwort, lädt TestFlight, installiert babu,
   meldet sich in der App unter Einstellungen an. Bis Schritt 3 steht auf ihrer Startseite
   „Deine Ablage wird noch eingerichtet" — das ist richtig so und verschwindet mit dem ersten
   Beleg danach.
5. **Nachweis**: ein Foto aus der App → `ssh h200v git -C ~/gitchain/tresor/inspektor/ws-christoph0711.io/<kurzname>.git log -1`
   zeigt den Beleg. Ninas Box (`babu.git`) bleibt unverändert.

Konten ohne Kanzlei (Testbetrieb): `werkzeuge/betrieb_anlegen.py` ohne `--nur-box` legt
Konto, Mandant und Verknüpfung in einem Lauf an; das Startpasswort erscheint genau einmal
auf der Konsole und wird persönlich weitergegeben.

## 2. Wenn etwas nicht geht

| Meldung | Bedeutung | Handgriff |
|---|---|---|
| App: „Deine Ablage wird noch eingerichtet" | Konto da, `mandant.box_ref` leer oder Box fehlt | Schritt 2 und 3 oben |
| App: „Zugang gilt nicht mehr" | Geräteschlüssel gelöscht (Passwort neu gesetzt, Gerät getrennt) oder Konto deaktiviert | in der App neu anmelden |
| Portal-Login 401 nach Passwortwechsel | gewollt: alte Sitzungen enden mit dem Wechsel | neu anmelden |
| `/healthz` 503 `db` oder `box` | Postgres weg oder Box-Klon fehlt | `docker ps`, `~/logs/wache.log`; die Wache startet bei `unhealthy` alle 2 min neu |
| `/healthz` `gemma: weg` | vLLM-Pod (:11435) antwortet nicht | Belege bleiben „wird gelesen" und werden nachgelesen; Cluster prüfen |
| Beleg nach 20 min „unlesbar" | keine Lesung angekommen | Portal: „Nochmal versuchen"; Container-Log nach `[lesen]` |
| Rückmeldung nicht in „Meine Meldungen" | Issue ohne `betrieb-<id>`-Label | Label im GitLab setzen (Ninas Alt-Issues tragen `betrieb-2`) |

Support-Rhythmus im Pilot: täglich das Support-Postfach (`BABU_SUPPORT_MAIL` bekommt jede
Rückmeldung als Kopie) und die offenen Issues mit `von-nina`.

## 3. Deploy

Ritual aus `CLAUDE.md` („Betrieb H200V"): Sicherung → `rsync server/ h200v:~/babu-docker/`
komplett → `docker compose build && up -d` → `/healthz` 200 `stand: ok` → Golden-Diff
(`/api/belege`, `/api/abgleich/<monat>`) → neue Routen durchrufen. Vor dem nächsten Deploy
`arbeit_offen` in `/healthz` auf 0 warten.

## 4. Sicherung und Wiederherstellung

Täglich 03:17 `server/docker/sichern.sh` auf der H200V, nächtlich 04:30 holt der Mac die
Kopie (`sicherung-holen.sh`, launchd) und meldet sich, wenn sie älter als 48 h ist.
Zurückspielen und die monatliche Probe: `docs/betrieb/restore-probe.md`.

## 5. Datenauskunft und Löschung (Handweg im Pilot)

Es gibt keine Route dafür; im Pilot ist es ein dokumentierter Ablauf des Betreibers,
in der Datenschutzerklärung mit 30 Tagen Frist genannt.

**Auskunft** (alles, was babu über einen Betrieb hat), als ZIP an die Inhaberin:

1. Belegbox: `git clone <box_ref>.git` aus dem Tresor, Arbeitskopie ohne `.git` packen.
2. Konto und Einstellungen: `docker exec babu-postgres psql -U babu -d babu -c "\copy (select … from einstellungen where un='<mail>') to …"` für `nutzer` (ohne `pw`), `einstellungen`, `mandant`, `termin`, `kundin`, `mitarbeiter`, `gespraech`/`nachricht`, `audit_log` (`ziel_un`).
3. Logos/Team-Fotos aus `~/babu-web/logos/<hash>` (Hash = `sha256(un)[:16]`).

**Löschung** (auf Verlangen, nach Ablauf der Aufbewahrungspflicht für die Belege selbst):

1. Konto deaktivieren: `UPDATE nutzer SET aktiv=0 WHERE email='<mail>'` — Login und
   Geräteschlüssel sind damit tot (`app_schluessel` prüft `aktiv`).
2. Mandant auf `beendet` setzen (Portal → Mandant → Status), Geräte in `/api/geraete`
   sind mit dem Konto ohnehin gesperrt.
3. Personenbezogene Tabellen löschen: `termin`, `kundin`, `behandlung`, `mitarbeiter`,
   `team`, `gespraech`/`nachricht`, `wa_faden`/`wa_nachricht`, `einstellungen` für `un`.
4. Belegbox **archivieren, nicht löschen**: die Belege sind Buchführungsunterlagen
   (Aufbewahrungspflicht); das Repo wird aus dem Workspace nach
   `~/gitchain/tresor/archiv/<kurzname>-<datum>.git` verschoben und aus `mandant.box_ref`
   entfernt. Löschung der Box selbst erst nach Ablauf der Frist — Git behält Historie, also
   ganzes Repo entfernen, nicht einzelne Commits.
5. Sicherungen: die Bundles und Dumps rollieren nach 14 Tagen von selbst aus; die
   Mac-Kopie behält Altes — dort von Hand `box-<kurzname>-*.bundle` entfernen.

Jeder Schritt mit Datum in `audit_log` (`audit.audit(<betreiber>, "loeschung", ziel_un=…)`).

## 6. Was vor dem ersten fremden Betrieb noch von Hand kommt

Der Code des Plans ist seit 14.09.2026 komplett gebaut und deployt. Diese fünf Schritte
brauchen Zugänge, die nur der Betreiber hat. Reihenfolge ist egal, bis auf 1 → 5.

**1. App Store Connect — erledigt 14.09.2026.** App „babu Belege" (Apple-ID 6811956687,
Bundle `io.0711.beleg`, SKU `babu-beleg`; „babu" allein ist im Store vergeben), Build 0.1.0 (2)
per `ios/archiv.sh Beleg` hochgeladen und verarbeitet, interne Gruppe „Pilot" mit automatischer
Verteilung, christoph@0711.io als Tester. Beta-App-Infos (Beschreibung, Feedback nina@0711.io,
Datenschutz-URL `/datenschutz`) gespeichert. Offen: Nina als App-Store-Connect-Nutzerin
(Users and Access, braucht ihren echten Namen) oder externe Gruppe nach der Beta-Review;
Review-Kontakt braucht eine Telefonnummer und ein Testkonto; Händlerstatus (DSA) im Bereich
Business vor einer Store-Einreichung. Vor jedem weiteren Upload `CURRENT_PROJECT_VERSION` in
`ios/Beleg/project.yml` **und** `project.pbxproj` hochzählen.

**2. Mail-Dienst — erledigt 14.09.2026.** Resend, Team „0711" (Anmeldung per Google mit
binary@0711.io), Domain `babu.0711.io` verifiziert (Region Irland, DKIM `resend._domainkey.babu`,
MX + SPF auf `send.babu`, alle drei bei Cloudflare in der Zone `0711.io`). API-Schlüssel
„babu-web H200V" (nur Sending access) steht als `BABU_SMTP_PASSWORT` in
`~/babu-docker/docker/.env` (Host `smtp.resend.com`, Port 587, Nutzer `resend`); Vorlage
`server/docker/.env.beispiel`. Erster echter Passwort-Link ging an christoph@0711.io.
Prüfen nach jedem Neustart: `GET /api/signup-offen` → `"passwort_vergessen": true`.
Bei „not verified" oder 535 im Log: Domain-Status unter resend.com/domains, Schlüssel neu
anlegen und per `pbpaste | ssh h200v …` in die `.env` (nie im Klartext ausgeben).
Offen: `BABU_SUPPORT_MAIL` in derselben Datei, sobald es ein Support-Postfach gibt.

**3. Rechtstexte — Erprobungsfassung seit 14.09.2026.** Impressum, Datenschutz und
Nutzungsbedingungen stehen als vom Auftraggeber freigegebene Testfassungen in
`server/belegreview/recht.py` (`TEXTE`), jede sagt in der ersten Zeile, dass sie eine
Erprobungsfassung ist. `recht.fertig()` ist damit wahr, `ios/archiv.sh` warnt nicht mehr.
Die Anwältin ersetzt die Texte vor dem allgemeinen Start an derselben Stelle; danach Suite
(`tests/test_recht.py`) und Deploy. AVV als PDF je Betrieb ablegen, nicht im Repo.

**4. Kanzlei-Konto GKM — angelegt 14.09.2026.** Konto `j.neef@gkm-group.de` (Rolle
`kanzlei`, Kanzlei-Id 8 „GKM Group Bonn", Inhaber). Das Startpasswort wurde nie ausgegeben;
der Einstieg läuft über „Passwort vergessen" im Portal: `POST /api/passwort-vergessen`
mit der Adresse schickt den Link per Mail. Danach zwei Testbetriebe nach Abschnitt 1.

**5. DATEV-Import bei GKM Neff.** Ninas Monat über `/datev` als Stapel exportieren
(Prüfbefund muss leer sein), Import bei der Kanzlei, #REW-Meldungen als Protokoll
mitnehmen — sie werden in den Prüfbefund übersetzt (`datev_seite.py`). Erst danach
`POST /api/datev/uebergeben` für echte Betriebe.
