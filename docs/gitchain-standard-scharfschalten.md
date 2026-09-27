# GitChain-Standard — Prüfung, Scharfschalten, Rückweg

Stand 27.09.2026, Branch `claude/gitchain-standard`. **Nicht live.** Scharf
geschaltet wird nur nach ausdrücklichem OK von Christoph Bertsch und nach dem
Deploy des neuen GitChain-Servers (erweiterte Rechte für `svc-babu`).

## Was sich ändert

- babu schreibt als Dienstkonto `svc-babu` (Integration `babu`, Namensraum
  `babu`) in den neuen Dienst `http://127.0.0.1:3361` statt über das alte
  Gateway :7808 mit Christophs persönlichem Token. Box je Betrieb:
  `babu/<betrieb>/belege`, privat. Token wie bisher in
  `~/gitchain-eingang/.pat_babu`, je Aufruf frisch gelesen.
- babu liest aus eigenen Lesespiegeln (`~/babu-web/lesen/<verweis>.git`),
  nicht mehr aus `~/gitchain/tresor`. Der Mount `~/inspektor-store` entfällt.
  Hängt der Dienst, liefert der Spiegel nach 15 s den alten Stand; `/healthz`
  meldet `spiegel`.
- Neue Betriebe entstehen per Push-to-create (`box_anlegen`), der
  Cron-Box-Anleger legt nichts mehr im alten Lager an.
- Anmeldung von Menschen per Token: `GET /v1/user`, Dienstkonten abgewiesen.
- Umzug `box-umzug.sh` (Trockenlauf Standard, `--scharf`, nie überschreiben),
  Rückweg `box-rueckholen.sh` (nur Fast-Forward).

## Befunde der Prüfung (27.09.2026)

1. **main ist nicht weitergelaufen** (`gitlab/main` = `8532d30` = Basis des
   Branches). Kein Rebase nötig.
2. **Live-Fehler heute auf main: alle Kanzlei-Mandanten schreiben in Ninas
   Box.** `klon_aus_ref` nahm nur den vorletzten Ordner des Verweises als
   Namen der Arbeitskopie. Der Box-Anleger legte aber alle Boxen als
   `inspektor/ws-christoph0711.io/<betrieb>` an → EINE Arbeitskopie
   `~/babu-web/boxen/ws-christoph0711.io` für die Mandanten 1, 3 und 4, deren
   origin `…/babu.git` ist (Ninas Box). Befund in `babu.git`:
   - Kanzlei GKM (Mandant 3, nullsiebenelf GmbH): `t.geib@gkm.tax` 93 und
     `neefjonas@aol.com` 8 Commits am 16.–18.09. (Adobe, Uber, Hotels,
     Christoph Bertsch Holding, GKM-Rechnung, OCULUS …).
   - `t.geib@gkm.tax` hat am 16.09. 13:09–13:10 **20 Belege gelöscht, die
     `nina@0711.io` am 13./14.09. aufgenommen hatte** (Shell, dm, Galeria,
     Maison du Caviar, Merz-Benzing …). Die Historie hat sie noch.
   - Die Boxen der Mandanten 1, 3, 4 haben 0 Commits; ihre Nutzer sehen ihre
     eigenen Uploads nie (geschrieben in Ninas Box, gelesen aus der leeren).
     Das trifft auch das App-Review-Konto (Mandant 4 „Salon Probe").
   Der Branch hat das nacheinander schon durch `remote set-url` in `_bereit`
   verdeckt, zwei gleichzeitig schreibende Betriebe teilten sich aber weiter
   einen Arbeitsordner mit zwei Schlössern. **Behoben:** Arbeitskopie = voller
   Verweis als Pfad (wie der Lesespiegel). Das gilt auch für den Rückweg mit
   den alten `inspektor/…`-Verweisen. Test `tests/test_box_trennung.py`.
3. **Erster Beleg in eine leere Box scheiterte** an `reset --hard origin/main`
   (kein `origin/main`). Mit `box_anlegen` hat jede neue Box zwar einen ersten
   Commit, der Rückweg (`--anlegen`) erzeugt aber leere Boxen. **Behoben:**
   `_bereit` erkennt die leere Box und committet auf `main`.
4. **Der Umzug nimmt die Fremdbelege mit.** `box-umzug.sh` spiegelt `babu.git`
   vollständig, samt GKM-Belegen und Löschungen. Entscheidung vor dem Umzug
   nötig (siehe offene Fragen). Historie nicht umschreiben; Vorschlag: nach
   dem Umzug ein Aufräum-Commit in `babu/babu/belege` (GKM-Belege raus, Ninas
   20 Belege wieder her) und die GKM-Belege in die neue Box von Mandant 3.
5. **Schritt 6 muss `box_ref` leeren**, sonst greift der Box-Anleger nicht
   (`WHERE status='box_ausstehend' AND COALESCE(box_ref,'')=''`). SQL unten.
6. **Zugänge:** `BABU_ERLAUBT` steht auf `christoph0711.io,nina0711.io`,
   `BABU_ROLLEN` auf `christoph0711.io:admin`. Beide Namen müssen zu
   `username` aus `GET /v1/user` im neuen Dienst passen (klein geschrieben).
   Nicht geraten — offene Frage an Christoph.
7. Die alte Arbeitskopie `~/babu-web/boxen/ws-christoph0711.io` wird nach dem
   Umzug nicht mehr benutzt und bleibt liegen (nicht löschen, Beleg für
   Befund 2). `~/babu-web/box` (Default-Box) folgt dem neuen Remote per
   `set-url` von selbst.

## Tests

- Suite: 2452 grün auf dem Branch vor dem Fix, 2456 grün danach (4 neue Tests).
- E2E gegen den Wegwerf-Dienst (Commit 42ebb36/c625af7): 23/23 mit echtem
  `svc-babu`. Kein echter Push an :3361 aus dieser Prüfung.

## Offene Fragen an Christoph

1. **Box-Name für Mandant 2:** `babu/babu/belege` (Vorgabe) oder
   `babu/supremestudio-2/belege`? Bei Änderung: `BABU_REF` in `compose.yml`,
   `box-umzug.sh --ziel-ref`, SQL in Schritt 6, Zeile 1 in `paare.tsv`.
2. **Benutzernamen im neuen Dienst** für Christoph und Nina (für
   `BABU_ERLAUBT`) — und soll Nina Admin werden (`BABU_ROLLEN`)?
3. **Fremdbelege in `babu.git`** (Befund 2/4): wie oben aufräumen, und wer
   informiert GKM und Nina?
4. **Termin** fürs Scharfschalten (nach dem Server-Deploy).
5. Nach dem Server-Deploy `BABU_GIT_AUTH=bearer`? Basic geht weiter.

## Scharfschalten (nur nach OK)

1. Sicherungen: `cp -p ~/gitchain-eingang/.pat_babu ~/gitchain-eingang/.pat_babu.bak-vor-standard`,
   `docker exec babu-postgres pg_dump -U babu babu > ~/babu-web/babu-vor-standard.sql`,
   `git -C ~/gitchain/tresor/inspektor/ws-christoph0711.io/babu.git rev-parse HEAD` notieren.
2. Alle Schreiber auf das alte Lager stoppen: Cron `wache.sh` und
   `box-anleger.sh` auskommentieren, `pm2 stop babu-eingang`,
   belege-review-Watcher (laut CLAUDE.md ein ANDERES Projekt — nur mit
   Christoph), `docker compose stop babu-web`. HEAD erneut prüfen.
3. Christoph legt in der GitChain-Verwaltung → Drittanbieter die Integration
   `babu` (Namensraum `babu`) an und gibt das Token aus. Wer es erhält:
   `umask 077`, in `~/gitchain-eingang/.pat_babu.svc` schreiben, nach
   `.pat_babu` kopieren. Den Wert nie in Chat, argv oder Log.
4. Code ausrollen: `rsync -a --delete --exclude=.env server/ h200v:~/babu-docker/`
   und `rsync -a --delete werkzeuge/ h200v:~/babu-docker/werkzeuge/`.
5. Umzug: `~/babu-docker/docker/box-umzug.sh --ziel-ref babu/babu/belege`
   (Trockenlauf, HEAD mit Schritt 1 vergleichen), dann `--scharf` → „BESTÄTIGT".
6. DB:

   ```sql
   BEGIN;
   UPDATE mandant SET box_ref = 'babu/babu/belege'
    WHERE id = 2 AND box_ref = 'inspektor/ws-christoph0711.io/babu';
   UPDATE mandant SET status = 'box_ausstehend', box_ref = NULL
    WHERE id IN (1, 3, 4);
   COMMIT;
   ```

7. `cd ~/babu-docker/docker && docker compose build && docker compose up -d`,
   dann Gegenproben: `/healthz` (`stand: ok`, `spiegel: ok`), Golden-Diff
   Nina, Beleg-Upload und Lesen, Token-Anmeldung, `box-anleger.sh --probe`
   zeigt 1/3/4 → `babu/<kurzname>/belege`. HEAD nach 1 und 7 Tagen prüfen.
8. Cron wieder an (wache, box-anleger); der Anleger legt 1/3/4 per
   Push-to-create an. `sichern.sh --trocken` einmal laufen lassen.

## Rückweg

1. Zuerst zurückholen, bevor der alte Weg wieder schreibt:
   `box-rueckholen.sh --liste paare.tsv --token-datei ~/gitchain-eingang/.pat_babu.svc`
   (Trockenlauf), dann `--scharf`. `paare.tsv` (Tab-getrennt):

   ```
   babu/babu/belege	/home/christoph.bertsch/gitchain/tresor/inspektor/ws-christoph0711.io/babu.git
   babu/jenny-from-the-block-1/belege	/home/christoph.bertsch/gitchain/tresor/inspektor/ws-christoph0711.io/jenny-from-the-block-1.git
   babu/nullsiebenelf-gmbh-3/belege	/home/christoph.bertsch/gitchain/tresor/inspektor/ws-christoph0711.io/nullsiebenelf-gmbh-3.git
   babu/salon-probe-4/belege	/home/christoph.bertsch/gitchain/tresor/inspektor/ws-christoph0711.io/salon-probe-4.git
   ```

   Betriebe, die nach dem Go-live entstanden sind: Zeile ergänzen, `--anlegen`.
2. `.pat_babu` aus `.pat_babu.bak-vor-standard`; `box_ref` zurücksetzen
   (Mandant 2 `inspektor/ws-christoph0711.io/babu`, 1/3/4 ihre alten
   `inspektor/…`-Verweise); Sicherungsspiegel in `~/backups/babu/*.git` per
   `remote set-url` auf den Tresor zurückhängen; alten Stand ausrollen und
   starten, `pm2 start babu-eingang`, Cron an.
