#!/usr/bin/env python3
"""Der Taktgeber: alle 30 Minuten schaut der Mac nach, was Nina gemeldet hat.

Dieser Teil ist mit Absicht NUR Verwaltung — holen, beanspruchen, den
Claude-Lauf starten, Grenzen durchsetzen. Das Denken (Fix, Tests, Deploy
nach Ritual) steht in auftrag.md und passiert im Claude-Lauf; die harte
Grenze davor ist leitplanke.py. Läuft nur, wenn der Mac wach ist — das ist
die benannte Schwäche der ganzen Schleife (Spec, „Risiken").
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASIS = "https://gitlab.0711.io/api/v4/projects/8"
TOKEN_PFAD = Path.home() / ".babu-fixlauf.token"
REPO = Path.home() / "babu"
HIER = Path(__file__).resolve().parent
PROZESS_LABELS = {"in-arbeit", "zur-abnahme", "braucht-christoph"}
VERWAIST_NACH_H = 2
MAX_JE_LAUF = 3


def _api(pfad: str, daten: dict | None = None, methode: str = "GET"):
    req = urllib.request.Request(
        f"{BASIS}{pfad}",
        data=urllib.parse.urlencode(daten).encode() if daten else None,
        method=methode)
    req.add_header("PRIVATE-TOKEN", TOKEN_PFAD.read_text().strip())
    req.add_header("User-Agent", "curl/8")  # Cloudflare blockt urllib sonst.
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def kandidaten(issues: list[dict], jetzt_iso: str) -> list[dict]:
    """Pur und testbar: wer ist dran?

    `bug` ohne Prozess-Label — plus Verwaiste, deren `in-arbeit` seit über
    zwei Stunden nichts mehr getan hat (Lauf abgestürzt). Höchstens drei."""
    jetzt = dt.datetime.fromisoformat(jetzt_iso.replace("Z", "+00:00"))
    dran = []
    for i in issues:
        labels = set(i.get("labels") or [])
        if "bug" not in labels:
            continue
        if not (labels & PROZESS_LABELS):
            dran.append(i)
        elif "in-arbeit" in labels and not (labels & {"zur-abnahme", "braucht-christoph"}):
            stand = dt.datetime.fromisoformat(
                str(i["updated_at"]).replace("Z", "+00:00"))
            if (jetzt - stand).total_seconds() > VERWAIST_NACH_H * 3600:
                dran.append(i)
    return dran[:MAX_JE_LAUF]


def main() -> int:
    issues = _api("/issues?state=opened&labels=bug&per_page=50")
    dran = kandidaten(issues, dt.datetime.now(dt.timezone.utc).isoformat())
    if not dran:
        print("fixlauf: nichts zu tun")
        return 0
    auftrag = (HIER / "auftrag.md").read_text(encoding="utf-8")
    for issue in dran:
        iid = issue["iid"]
        try:
            war_verwaist = "in-arbeit" in (issue.get("labels") or [])
            _api(f"/issues/{iid}", {"add_labels": "in-arbeit"}, "PUT")
            _api(f"/issues/{iid}/notes",
                 {"body": "vorheriger Lauf verwaist, übernehme neu"
                  if war_verwaist else "übernehme"}, "POST")
            print(f"fixlauf: starte Claude für #{iid}: {issue['title'][:60]}")
            try:
                lauf = subprocess.run(
                    ["claude", "-p", "--dangerously-skip-permissions",
                     auftrag.replace("{{IID}}", str(iid))
                            .replace("{{TITEL}}", issue["title"])],
                    cwd=REPO, capture_output=True, text=True, timeout=45 * 60)
            except subprocess.TimeoutExpired as e:
                # subprocess.run wirft bei Timeout, statt returncode != 0 zu
                # liefern — dieselbe Behandlung wie ein gescheiterter Lauf.
                stdout = e.stdout or ""
                stderr = e.stderr or ""
                if stdout:
                    print(stdout[-2000:])
                _api(f"/issues/{iid}", {"add_labels": "braucht-christoph",
                                        "remove_labels": "in-arbeit",
                                        "assignee_ids[]": 15}, "PUT")
                _api(f"/issues/{iid}/notes",
                     {"body": "Fix-Lauf nach 45 min abgebrochen (Timeout):\n\n"
                      f"```\n{(stderr or stdout)[-1200:]}\n```"}, "POST")
                continue

            print(lauf.stdout[-2000:])
            if lauf.returncode != 0:
                # Der Lauf ist gestorben, ohne aufzuräumen — Christoph muss ran.
                # Form-Encoding: GitLab erwartet Arrays als `assignee_ids[]`.
                _api(f"/issues/{iid}", {"add_labels": "braucht-christoph",
                                        "remove_labels": "in-arbeit",
                                        "assignee_ids[]": 15}, "PUT")
                _api(f"/issues/{iid}/notes",
                     {"body": f"Fix-Lauf abgebrochen (Exit {lauf.returncode}):\n\n"
                      f"```\n{lauf.stderr[-1200:]}\n```"}, "POST")
        except Exception as exc:
            # Ein Issue darf nicht die ganze Schleife mitreißen — mit dem
            # nächsten Kandidaten weitermachen, Christoph best effort holen.
            print(f"fixlauf: Fehler bei #{iid}: {exc}")
            try:
                _api(f"/issues/{iid}", {"add_labels": "braucht-christoph",
                                        "remove_labels": "in-arbeit",
                                        "assignee_ids[]": 15}, "PUT")
            except Exception as exc2:
                print(f"fixlauf: konnte #{iid} nicht auf "
                      f"braucht-christoph setzen: {exc2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
