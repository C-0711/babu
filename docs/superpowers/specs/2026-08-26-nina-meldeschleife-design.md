# Nina-Meldeschleife: melden → automatisch fixen → freigeben

Stand 2026-08-26, entworfen im Gespräch mit Christoph. Ziel: Nina testet die App, meldet
Fehler mit einem Fingertipp, Claude Code fixt sie selbständig, alles ist dokumentiert,
und Nina gibt den Fix fachlich frei — ohne je GitLab sehen zu müssen.

**Die eine Wahrheit ist GitLab:** Projekt `0711/babu` (id 8) auf gitlab.0711.io
(Docker-Container `gitlab-0711` auf der H200V). Die App ist Fenster und Fernbedienung,
der Mac ist die Werkstatt. Zugänge und Instanz-Details: Memory `babu-gitlab-0711`.

## Rollen

- **Nina** (GitLab-User `nina`, id 14, Reporter): meldet, prüft, gibt fachlich frei.
- **Claude Code** (Projekt-Token, s. u.): fixt, deployt risikoarme Fälle, dokumentiert.
- **Christoph** (GitLab-User `christoph`, id 15, Owner): bekommt alles zugewiesen, was
  die Leitplanke stoppt oder ein Tor reißt; technische Instanz.

## Statusmodell (GitLab-Labels als Zustandsmaschine)

    offen, ohne Prozess-Label   = „gemeldet"        (wartet auf den Fix-Lauf)
    + in-arbeit                 = „in Arbeit"       (ein Lauf hat übernommen)
    + zur-abnahme               = „bitte prüfen"    (deployt, Nina zugewiesen)
    + braucht-christoph         = „braucht Christoph" (Leitplanke/Tor, Christoph zugewiesen)
    geschlossen                 = „erledigt"        (Nina hat freigegeben oder Christoph geschlossen)

Genau EIN Prozess-Label je Issue; der Fix-Lauf und die Freigabe-Knöpfe tauschen sie
atomar (Label setzen und entfernen im selben API-Aufruf). Neue Labels im Projekt:
`von-nina`, `in-arbeit`, `zur-abnahme`, `braucht-christoph` (zusätzlich zu den
bestehenden bug/wunsch/ios/portal/beleg/frage).

## Baustein 1: Melden — der Rückmeldeknopf (App → Server → GitLab)

Der bestehende Rückmeldeknopf der App bleibt die Oberfläche; sein Server-Endpunkt in
`server/belegreview/babu_web.py` wird umgebaut:

- Legt per GitLab-API ein Issue an: Titel = erste Zeile der Meldung (gekürzt auf 80
  Zeichen), Beschreibung = ganze Meldung + Metablock (angemeldete Nutzerin, App-Version,
  Zeitstempel), Labels `bug` + `von-nina`.
- Screenshot: erst `POST /projects/8/uploads`, dann die zurückgegebene Markdown-Referenz
  in die Beschreibung.
- Auth zum Server wie bisher (`_box_wache`/`box_mitglied` — NIE `ERLAUBT`, siehe Memory
  babu-salon-portal). Auth zu GitLab: neu gemünzter **Projekt-Access-Token**
  `app-rueckmeldung` (Rolle Reporter, Scope `api`), abgelegt auf der H200V als
  `~/babu-web/.gitlab_token` (0600). Der vorhandene fixit-Bot-Token wird NICHT
  mitbenutzt.
- Server → GitLab direkt übers lokale Netz der H200V (Container-Port), NICHT über
  gitlab.0711.io/Cloudflare — Cloudflare blockt u. a. den Python-urllib-User-Agent,
  und der Umweg ist unnötig. Die genaue Adresse ermittelt der Plan (docker port).
- **Puffer:** Scheitert der GitLab-Aufruf, landet die Meldung in einer neuen
  SQLite-Tabelle `meldung_puffer` (portal.db) und der nächste Aufruf des Endpunkts —
  sowie der Fix-Lauf — trägt sie nach. Die Nutzerin bekommt trotzdem sofort „Danke,
  angekommen". Die bisherige Ablage der Meldungen in der Belegbox entfällt.

## Baustein 2: Sehen & Freigeben — „Meine Meldungen" (App)

Neue Server-Endpunkte (hinter `_box_wache`), die App bekommt einen Bereich
„Meine Meldungen":

- `GET /api/meldungen` — Liste aller Issues mit Label `von-nina`, gemappt auf das
  Statusmodell oben, sortiert: „bitte prüfen" zuoberst, dann „in Arbeit", „gemeldet",
  zuletzt „erledigt" (letzte 20). Je Eintrag: Nummer, Titel, Status, letzter
  Claude-Kommentar (Kurzfassung), Weblink ins Issue (für Neugierige).
- `POST /api/meldungen/{iid}/freigeben` — nur erlaubt im Zustand „bitte prüfen":
  Kommentar „fachlich freigegeben von <Nutzerin>", Issue schließen.
- `POST /api/meldungen/{iid}/beanstanden` — Pflichtfeld Text: Kommentar mit dem Text,
  Label `zur-abnahme` → weg, zurück auf „gemeldet" (der nächste Fix-Lauf nimmt es
  wieder auf). Zuweisung zurück auf niemanden.

Beide Schreib-Endpunkte prüfen den Ist-Zustand des Issues vor dem Schreiben (kein
blindes Überschreiben). Der Server cached die Liste 60 s, damit die App nicht bei
jedem Öffnen GitLab anfragt.

## Baustein 3: Fixen — der wiederkehrende Lauf (Mac)

Alle 30 Minuten startet auf Christophs Mac ein Claude-Code-Lauf (headless; Mechanik —
launchd vs. Scheduled Task — entscheidet der Umsetzungsplan). Er läuft nur, wenn der
Mac wach ist; das ist eine bewusste, benannte Schwäche.

Je Lauf:

1. Offene Issues holen: Label `bug`, KEIN Prozess-Label. Außerdem `meldung_puffer`
   nachtragen, falls Einträge liegen.
2. Je Issue (einzeln, nacheinander): Label `in-arbeit` + Kommentar „übernehme",
   eigener Git-Worktree vom aktuellen `main`.
3. Fix entwickeln, Tests schreiben/laufen lassen (pytest-Umgebung siehe Memory
   babu-testumgebung).
4. **Leitplanke** (vor jedem Deploy): Berührt der Diff einen dieser Bereiche, wird
   NICHT deployt — Label `braucht-christoph`, Christoph zugewiesen, Kommentar mit
   Branch-Namen und Begründung:
   - `boxschreiber.py` oder sonstige Belegbox-Schreibpfade
   - Geld-/Steuerlogik (kontierung, geld, EXTF/DATEV, kasse, kontenrahmen)
   - Schema-Änderungen an portal.db (Migrationen)
   - Auth/Session (`_box_wache`, `box_mitglied`, app-anmelden)
5. Sonst Deploy nach dem bestehenden Ritual (Memory babu-salon-portal): Sicherung,
   Golden-Diff vorher ziehen, scp nach `~/belegreview/`, `pm2 restart babu-web`,
   Golden-Diff nachher byte-gleich, neue/berührte Routen live durchrufen. Reißt ein
   Tor: Rollback aus der Sicherung, `pm2 restart`, Label `braucht-christoph`.
6. Abschluss bei Erfolg: Commit auf `main` mit `#<iid>` in der Botschaft, Push nach
   GitHub (origin), Issue-Kommentar (Ursache → Änderung → Commit-SHA → wie getestet
   → deployt ja/nein), Label `zur-abnahme`, Nina zugewiesen.
7. Je Lauf höchstens 3 Issues (Schutz vor Amok); Rest wartet auf den nächsten Takt.

Ein Issue, das im Zustand `in-arbeit` hängen bleibt (Lauf abgestürzt), wird vom
nächsten Lauf nach 2 h Stille übernommen: Kommentar „vorheriger Lauf verwaist,
übernehme neu".

## Baustein 4: Dokumentation — fällt nebenbei an

Kein eigenes System. Jedes Issue erzählt chronologisch: Meldung mit Screenshot →
„übernehme" → Fix-Kommentar mit Commit und Testnachweis → ggf. Beanstandung und
zweite Runde → Freigabe-Kommentar von Nina. Commits verweisen mit `#<iid>` aufs
Issue. Wer Gesamtübersicht will, öffnet GitLab; wer nur den Alltag will, sieht alles
in der App.

## Nicht-Ziele (bewusst weggelassen)

- Kein Push/keine Benachrichtigung an Ninas Telefon — sie sieht „bitte prüfen" beim
  nächsten App-Öffnen. (Kandidat für später, wenn die Schleife sich bewährt.)
- Keine Wunsch-Automatik: `wunsch`-Issues fasst der Fix-Lauf NICHT an, die bespricht
  Christoph.
- Kein Fixit-Rückkanal mehr; Fixit bleibt Archiv der Vorgänge #1–#61.
- Keine Mandantenfähigkeit — eine Belegbox, eine Nina (siehe Memory babu-eine-belegbox).

## Risiken, benannt

- **Automatischer Deploy auf die Produktiv-H200V.** Abgefedert durch Leitplanke,
  Golden-Diff-Tor, Live-Routen-Prüfung, Sicherung + Rollback. Restrisiko akzeptiert
  (Testphase, ein Kunde: Nina).
- **Mac aus = keine Fixe.** Meldungen sammeln sich in GitLab, nichts geht verloren.
- **GitLab down = Melden gepuffert.** SQLite-Puffer, Nachtrag beim nächsten Kontakt.
