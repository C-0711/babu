# Fix-Auftrag: GitLab-Issue #{{IID}} — {{TITEL}}

Du arbeitest das Issue #{{IID}} im Projekt 0711/babu (gitlab.0711.io) ab.
API-Zugang: Header `PRIVATE-TOKEN: $(cat ~/.babu-fixlauf.token)`, immer mit
`-A curl/8`, Basis `https://gitlab.0711.io/api/v4/projects/8`.

## Ablauf, ohne Auslassung

1. Issue samt Notizen lesen (`GET /issues/{{IID}}`, `GET /issues/{{IID}}/notes`).
   Frühere Beanstandungen von Nina sind Teil der Aufgabe.
2. `git -C ~/babu fetch origin && git -C ~/babu worktree add -b fix/{{IID}} /tmp/fix-{{IID}} origin/main`
   — dort arbeiten, NIE im Haupt-Checkout. **Wichtig: `-b fix/{{IID}}` nicht
   weglassen.** Ohne eigenen Branch-Namen erzeugt `worktree add` einen
   detached HEAD; ein Commit dort landet auf keinem Branch. „Commit auf
   main, `git push origin main`" würde dann die main des Haupt-Checkouts
   pushen (ohne den Fix), Git meldet dabei still „up to date", der Worktree
   wird hinterher aufgeräumt — und der Commit ist verwaist, obwohl die Notiz
   im Issue einen Commit-SHA nennt, der auf `origin/main` nie ankommt.
3. Ursache finden (superpowers:systematic-debugging), Fix schreiben, Test dazu.
   Tests: venv nach Memory babu-testumgebung, `python -m pytest server/belegreview/tests/ -x -q`.
   Noch NICHT committen — das passiert in Schritt 4, nach der Leitplanke,
   aber vor der Entscheidung deploy/kein-deploy (beide Pfade brauchen einen
   echten Commit zum Pushen).
4. **Stagen, Leitplanke — hartes Tor, dann committen.** `git diff origin/main`
   zeigt NUR bereits getrackte Änderungen — neue Dateien (Migrationen, neue
   Routen-Module) blieben unsichtbar und liefen am Tor vorbei. Deshalb erst
   stagen, dann gegen den Stage-Bereich prüfen, Pfade NUL-getrennt einlesen
   (ein ungequotetes `$(...)` zerlegt Pfade mit Leerzeichen in mehrere
   Argumente):

   ```
   git add -A
   git diff --cached origin/main > /tmp/fixlauf-diff-{{IID}}.txt
   pfade=()
   while IFS= read -r -d '' datei; do pfade+=("$datei"); done \
       < <(git diff --cached --name-only -z origin/main)
   python3 ~/babu/werkzeuge/fixlauf/leitplanke.py "${pfade[@]}" < /tmp/fixlauf-diff-{{IID}}.txt
   ```

   (Kein `readarray`/`mapfile` — der Mac bringt nur Bash 3.2 mit, das kennt
   beides nicht. Die `while read -d ''`-Schleife tut dasselbe.)

   Danach in JEDEM Fall committen — `git commit -m "... #{{IID}}"` auf dem
   Branch `fix/{{IID}}` — bevor es weitergeht:

   - **Exit 1 (RISKANT) → NICHT deployen.** `git push origin fix/{{IID}}`
     (der benannte Branch, NICHT main — der Fix ist ja gerade nicht
     freigegeben), Issue-Notiz mit Begründung + Branch, Labels
     `braucht-christoph` setzen / `in-arbeit` entfernen, `assignee_ids[]=15`,
     Worktree aufräumen, ENDE.
   - **Exit 0 (frei) → weiter zu Schritt 5.**
5. **Push VOR dem Deploy**, nicht danach: `git push origin HEAD:main`.
   Schlägt der Push fehl (z. B. main ist seit dem Fetch weitergelaufen) →
   KEIN Deploy, stattdessen wie der Leitplanken-Fall in Schritt 4 verfahren
   (`git push origin fix/{{IID}}`, `braucht-christoph`, ehrliche Notiz,
   Worktree aufräumen, ENDE). Der Push muss stehen, bevor irgendetwas auf
   der H200V berührt wird — sonst kann ein Deploy passieren, dessen Commit
   gar nicht auf `origin/main` liegt.
6. Deploy nach dem Ritual (Memory babu-salon-portal, alles per ssh h200v):
   Golden-Diff vorher ziehen → `tar`-Sicherung → `scp` der geänderten
   Server-Dateien nach `~/belegreview/` → `pm2 restart babu-web` → Golden-Diff
   nachher byte-gleich → jede berührte Route einmal lesend UND schreibend live
   rufen (Testdaten hinterher entfernen). Reißt ein Tor: Rollback aus der
   Sicherung, `pm2 restart babu-web`, dann wie Leitplanken-Fall verfahren
   (`braucht-christoph`, Notiz mit dem, was das Tor sagte — der Commit auf
   main bleibt in diesem Fall stehen, nur der Deploy wird zurückgerollt).
   Reine iOS-Fixe haben keinen Deploy-Schritt — dann gilt: bauen muss gelingen
   (`xcodebuild … build`), und die Notiz sagt ehrlich „wartet auf den nächsten
   App-Build auf Ninas iPhone".
7. Worktree aufräumen (`git worktree remove /tmp/fix-{{IID}}`).
8. Abschluss-Notiz ins Issue — Ursache, Änderung, Commit-SHA, wie getestet,
   deployt ja/nein. Dann Labels: `zur-abnahme` setzen, `in-arbeit` entfernen,
   `assignee_ids[]=14` (Nina).

## Grenzen

- NUR dieses eine Issue. Keine Gelegenheitsverbesserungen.
- Bei Unlösbarkeit oder Zweifel: wie Leitplanken-Fall — `braucht-christoph`,
  ehrliche Notiz, kein Deploy. Ein ehrliches „ich weiß nicht" ist ein
  gültiges Ergebnis, ein geratener Deploy nicht.
