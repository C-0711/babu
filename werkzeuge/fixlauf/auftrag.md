# Fix-Auftrag: GitLab-Issue #{{IID}} — {{TITEL}}

Du arbeitest das Issue #{{IID}} im Projekt 0711/babu (gitlab.0711.io) ab.
API-Zugang: Header `PRIVATE-TOKEN: $(cat ~/.babu-fixlauf.token)`, immer mit
`-A curl/8`, Basis `https://gitlab.0711.io/api/v4/projects/8`.

## Ablauf, ohne Auslassung

1. Issue samt Notizen lesen (`GET /issues/{{IID}}`, `GET /issues/{{IID}}/notes`).
   Frühere Beanstandungen von Nina sind Teil der Aufgabe.
2. `git -C ~/babu fetch origin && git -C ~/babu worktree add /tmp/fix-{{IID}} origin/main`
   — dort arbeiten, NIE im Haupt-Checkout.
3. Ursache finden (superpowers:systematic-debugging), Fix schreiben, Test dazu.
   Tests: venv nach Memory babu-testumgebung, `python -m pytest server/belegreview/tests/ -x -q`.
4. **Leitplanke — hartes Tor:**
   `git diff --name-only origin/main | xargs python3 ~/babu/werkzeuge/fixlauf/leitplanke.py`
   Exit 1 → NICHT deployen. Stattdessen: Branch `fix/{{IID}}` pushen, Issue-Notiz
   mit Begründung + Branch, Labels `braucht-christoph` setzen / `in-arbeit` entfernen,
   `assignee_ids=15`, Worktree aufräumen, ENDE.
5. Deploy nach dem Ritual (Memory babu-salon-portal, alles per ssh h200v):
   Golden-Diff vorher ziehen → `tar`-Sicherung → `scp` der geänderten
   Server-Dateien nach `~/belegreview/` → `pm2 restart babu-web` → Golden-Diff
   nachher byte-gleich → jede berührte Route einmal lesend UND schreibend live
   rufen (Testdaten hinterher entfernen). Reißt ein Tor: Rollback aus der
   Sicherung, `pm2 restart babu-web`, dann wie Leitplanken-Fall verfahren
   (`braucht-christoph`, Notiz mit dem, was das Tor sagte).
   Reine iOS-Fixe haben keinen Deploy-Schritt — dann gilt: bauen muss gelingen
   (`xcodebuild … build`), und die Notiz sagt ehrlich „wartet auf den nächsten
   App-Build auf Ninas iPhone".
6. Commit auf main mit `#{{IID}}` in der Botschaft, `git push origin main`,
   Worktree aufräumen (`git worktree remove /tmp/fix-{{IID}}`).
7. Abschluss-Notiz ins Issue — Ursache, Änderung, Commit-SHA, wie getestet,
   deployt ja/nein. Dann Labels: `zur-abnahme` setzen, `in-arbeit` entfernen,
   `assignee_ids=14` (Nina).

## Grenzen

- NUR dieses eine Issue. Keine Gelegenheitsverbesserungen.
- Bei Unlösbarkeit oder Zweifel: wie Leitplanken-Fall — `braucht-christoph`,
  ehrliche Notiz, kein Deploy. Ein ehrliches „ich weiß nicht" ist ein
  gültiges Ergebnis, ein geratener Deploy nicht.
