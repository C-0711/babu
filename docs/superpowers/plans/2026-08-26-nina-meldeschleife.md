# Nina-Meldeschleife — Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nina meldet Fehler mit dem Rückmeldeknopf, das wird ein GitLab-Issue; ein wiederkehrender Claude-Code-Lauf auf dem Mac fixt, deployt risikoarm und dokumentiert; Nina sieht und quittiert alles in der App.

**Architecture:** GitLab (`0711/babu`, id 8, auf gitlab.0711.io = Container `gitlab-0711` auf der H200V) ist die einzige Wahrheit; Labels sind die Zustandsmaschine. Der Server (babu_web) spricht GitLab lokal auf `http://127.0.0.1:8929` an und puffert bei Ausfall in portal.db. Der Fix-Lauf ist ein launchd-Job auf dem Mac, der pro Issue einen headless Claude-Code-Lauf startet; eine deterministische Leitplanke (`leitplanke.py`) entscheidet, ob deployt werden darf.

**Tech Stack:** FastAPI/Python 3.10+ (Server, H200V), SwiftUI (iOS), GitLab-REST-API v4, SQLite (portal.db), launchd + `claude -p` (Mac).

**Spec:** `docs/superpowers/specs/2026-08-26-nina-meldeschleife-design.md`

## Global Constraints

- Tests laufen auf dem Mac mit `/opt/homebrew/bin/python3.12` in einem venv (fastapi, httpx, pytest, pypdfium2, pillow-heif, requests, python-multipart) — Memory `babu-testumgebung`. Testaufrufe unten nehmen an, dass `python -m pytest` in diesem venv läuft.
- Neue Routen IMMER hinter `_api_wache`/`_box_wache` (nie `ERLAUBT`) — Memory `babu-salon-portal`.
- Server → GitLab: Basis `http://127.0.0.1:8929`, Header `PRIVATE-TOKEN`. NIE über gitlab.0711.io/Cloudflare (blockt u. a. Python-urllib-User-Agent).
- Mac → GitLab: `https://gitlab.0711.io` mit `User-Agent: curl/8` (Cloudflare).
- GitLab-Nutzer-IDs: nina = 14, christoph = 15. Projekt-ID = 8.
- Prozess-Labels (genau eins je Issue): `in-arbeit`, `zur-abnahme`, `braucht-christoph`. Kein Prozess-Label + offen = „gemeldet". Geschlossen = „erledigt".
- Der Fix-Lauf fasst nur `bug` an, nie `wunsch`. Höchstens 3 Issues je Lauf.
- Deploy nur nach dem Ritual (Sicherung → Golden-Diff vorher → scp → `pm2 restart babu-web` → Golden-Diff byte-gleich → berührte Routen live prüfen), sonst Rollback.
- Commits auf `main` tragen `#<iid>` in der Botschaft.

## Dateistruktur

| Datei | Verantwortung |
|---|---|
| `server/belegreview/gitlab_meldungen.py` (neu) | Alles GitLab: Abbildung Meldung→Issue, Klient, Status-Abbildung, Puffer |
| `server/belegreview/babu_web.py` (ändern) | Route `/api/rueckmeldung` umbauen (Fixit raus), Routen `/api/rueckmeldungen*` neu |
| `server/belegreview/rueckmeldung.py` (bleibt) | Reines Formatieren (titel_aus/koerper_aus) — wird weiterverwendet |
| `server/belegreview/tests/test_gitlab_meldungen.py` (neu) | Abbildung, Klient (requests gemockt), Puffer |
| `server/belegreview/tests/test_rueckmeldung_route.py` (ersetzen) | Route mit GitLab-Fake statt Fixit/Belegbox |
| `server/belegreview/tests/test_meldungen_routen.py` (neu) | Liste/Freigeben/Beanstanden |
| `ios/Beleg/Beleg/AblageService.swift` (ändern) | `rueckmeldenSenden` + Bild; neu: `meldungenHolen`, `meldungFreigeben`, `meldungBeanstanden` |
| `ios/Beleg/Beleg/MeldenSheet.swift` (ändern) | Bildschirmfoto einfangen + Schalter „mitschicken" |
| `ios/Beleg/Beleg/MeldungenListe.swift` (neu) | „Meine Meldungen" mit Freigabe-Knöpfen |
| `ios/Beleg/Beleg/KontoMenu.swift` (ändern) | Eintrag „Meine Meldungen" |
| `werkzeuge/fixlauf/fixlauf.py` (neu) | Mac-Takt: Issues holen, beanspruchen, Claude starten, Grenzen |
| `werkzeuge/fixlauf/leitplanke.py` (neu) | Deterministisch: darf dieser Diff deployt werden? |
| `werkzeuge/fixlauf/auftrag.md` (neu) | Der Arbeitsauftrag für den headless Claude-Lauf |
| `werkzeuge/fixlauf/io.0711.babu.fixlauf.plist` (neu) | launchd-Vorlage, alle 30 Min |
| `server/belegreview/tests/test_fixlauf.py` (neu) | Leitplanke + Kandidatenauswahl (pur) |

---

### Task 1: GitLab vorbereiten (Labels, Projekt-Token) — einmalige Ops

Kein Code im Repo; ausführen und Ergebnis prüfen. Der Admin-Token liegt auf der H200V in `~/.fixit/provision.env` (`GITLAB_ADMIN_TOKEN`).

**Files:** keine (Serverzustand).

**Interfaces:**
- Produces: Prozess-Labels im Projekt 8; Projekt-Token `app-rueckmeldung` (Rolle Developer, Scope `api`) in `~/babu-web/.gitlab_token` (H200V, 0600) und `~/.babu-fixlauf.token` (Mac, 0600).

- [ ] **Step 1: Prozess-Labels anlegen**

```bash
ssh h200v 'TOK=$(grep GITLAB_ADMIN_TOKEN ~/.fixit/provision.env | cut -d= -f2);
for L in "von-nina|#ff8fa3|Von Nina gemeldet" "in-arbeit|#fc9403|Claude arbeitet daran" "zur-abnahme|#00b140|Deployt — wartet auf Ninas Freigabe" "braucht-christoph|#7f8c8d|Leitplanke oder Tor — Christoph muss ran"; do
  IFS="|" read -r n f b <<< "$L";
  curl -s -X POST -H "PRIVATE-TOKEN: $TOK" "http://127.0.0.1:8929/api/v4/projects/8/labels" \
    --data-urlencode "name=$n" --data-urlencode "color=$f" --data-urlencode "description=$b" | head -c 80; echo;
done'
```

Erwartet: vier JSON-Antworten mit `"name":"…"` (oder „already exists" bei Wiederholung).

- [ ] **Step 2: Projekt-Token münzen und ablegen**

```bash
ssh h200v 'TOK=$(grep GITLAB_ADMIN_TOKEN ~/.fixit/provision.env | cut -d= -f2);
umask 077;
curl -s -X POST -H "PRIVATE-TOKEN: $TOK" "http://127.0.0.1:8929/api/v4/projects/8/access_tokens" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"app-rueckmeldung\",\"scopes\":[\"api\"],\"access_level\":30,\"expires_at\":\"2027-08-01\"}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)[\"token\"])" > ~/babu-web/.gitlab_token;
wc -c ~/babu-web/.gitlab_token'
ssh h200v 'cat ~/babu-web/.gitlab_token' > ~/.babu-fixlauf.token && chmod 600 ~/.babu-fixlauf.token
```

- [ ] **Step 3: Token prüfen (von beiden Seiten)**

```bash
ssh h200v 'curl -s -o /dev/null -w "%{http_code}\n" -H "PRIVATE-TOKEN: $(cat ~/babu-web/.gitlab_token)" "http://127.0.0.1:8929/api/v4/projects/8"'
curl -s -o /dev/null -w "%{http_code}\n" -A "curl/8" -H "PRIVATE-TOKEN: $(cat ~/.babu-fixlauf.token)" "https://gitlab.0711.io/api/v4/projects/8"
```

Erwartet: zweimal `200`.

---

### Task 2: `gitlab_meldungen.py` — Abbildung (pur, TDD)

**Files:**
- Create: `server/belegreview/gitlab_meldungen.py`
- Test: `server/belegreview/tests/test_gitlab_meldungen.py`

**Interfaces:**
- Consumes: `rueckmeldung.Meldung`, `rueckmeldung.titel_aus`, `rueckmeldung.koerper_aus`.
- Produces: `als_issue(m: rueckmeldung.Meldung) -> dict` (Schlüssel `title`, `description`, `labels`);
  `status_von(issue: dict) -> str` (einer von `"gemeldet" | "in-arbeit" | "bitte-pruefen" | "erledigt"`).

- [ ] **Step 1: Fehlschlagende Tests schreiben**

```python
# server/belegreview/tests/test_gitlab_meldungen.py
"""Die Abbildung Meldung → GitLab-Issue und Labels → Status."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gitlab_meldungen as gm  # noqa: E402
import rueckmeldung as rm  # noqa: E402


def test_fehler_wird_bug_issue():
    m = rm.Meldung(text="Der Beleg vom Bäcker zeigt 19 % statt 7 %.",
                   art="fehler", quelle="app", von="nina@0711.io",
                   geraet="iPhone, iOS 26", fassung="42")
    issue = gm.als_issue(m)
    assert issue["title"] == "Der Beleg vom Bäcker zeigt 19 % statt 7 %"
    assert "19 % statt 7 %" in issue["description"]
    assert "iPhone, iOS 26" in issue["description"]
    assert issue["labels"] == "bug,von-nina"


def test_wunsch_bekommt_wunsch_label():
    m = rm.Meldung(text="Ich hätte gern eine Suche.", art="wunsch")
    assert gm.als_issue(m)["labels"] == "wunsch,von-nina"


def _issue(state="opened", labels=()):
    return {"state": state, "labels": list(labels)}


def test_status_abbildung():
    assert gm.status_von(_issue()) == "gemeldet"
    assert gm.status_von(_issue(labels=["bug", "in-arbeit"])) == "in-arbeit"
    assert gm.status_von(_issue(labels=["zur-abnahme"])) == "bitte-pruefen"
    # braucht-christoph ist für Nina schlicht „in Arbeit" — sie muss nichts tun.
    assert gm.status_von(_issue(labels=["braucht-christoph"])) == "in-arbeit"
    assert gm.status_von(_issue(state="closed", labels=["zur-abnahme"])) == "erledigt"
```

- [ ] **Step 2: Laufen lassen, Scheitern sehen**

Run: `python -m pytest server/belegreview/tests/test_gitlab_meldungen.py -v`
Expected: FAIL — `ModuleNotFoundError: gitlab_meldungen`.

- [ ] **Step 3: Minimal umsetzen**

```python
# server/belegreview/gitlab_meldungen.py
"""GitLab ist die eine Wahrheit über Ninas Meldungen — hier wohnt der Draht dorthin.

Drei Aufgaben, eine Datei: Meldung → Issue formen, mit der GitLab-API auf der
eigenen Maschine sprechen (127.0.0.1:8929, NIE über Cloudflare), und puffern,
wenn GitLab gerade nicht da ist. Die Zusage bleibt dieselbe wie zu Fixit-Zeiten:
eine Meldung geht nie verloren, und Nina liest immer sofort „angekommen".

Labels sind die Zustandsmaschine (Spec 2026-08-26-nina-meldeschleife):
    offen ohne Prozess-Label = gemeldet · in-arbeit · zur-abnahme = bitte prüfen
    braucht-christoph zeigt Nina schlicht „in Arbeit" · geschlossen = erledigt
"""
from __future__ import annotations

import rueckmeldung as rm

ART_LABEL = {"fehler": "bug", "wunsch": "wunsch"}


def als_issue(m: rm.Meldung) -> dict:
    """Die Nutzlast für POST /projects/:id/issues — Ninas Worte, unsere Labels."""
    if not m.text.strip():
        raise ValueError("leere Meldung")
    return {
        "title": rm.titel_aus(m.text),
        "description": rm.koerper_aus(m),
        "labels": f"{ART_LABEL.get(m.art, 'bug')},von-nina",
    }


def status_von(issue: dict) -> str:
    """Was Nina sieht. `braucht-christoph` ist für sie „in Arbeit" —
    dass intern Christoph dran muss, ist nicht ihre Baustelle."""
    if issue.get("state") == "closed":
        return "erledigt"
    labels = set(issue.get("labels") or [])
    if "zur-abnahme" in labels:
        return "bitte-pruefen"
    if labels & {"in-arbeit", "braucht-christoph"}:
        return "in-arbeit"
    return "gemeldet"
```

- [ ] **Step 4: Tests grün sehen**

Run: `python -m pytest server/belegreview/tests/test_gitlab_meldungen.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add server/belegreview/gitlab_meldungen.py server/belegreview/tests/test_gitlab_meldungen.py
git commit -m "Meldung wird GitLab-Issue: Abbildung und Statusmaschine"
```

---

### Task 3: `gitlab_meldungen.py` — Klient und Puffer

**Files:**
- Modify: `server/belegreview/gitlab_meldungen.py`
- Test: `server/belegreview/tests/test_gitlab_meldungen.py` (erweitern)

**Interfaces:**
- Produces (alles in `gitlab_meldungen`):
  - `issue_anlegen(issue: dict, bild_jpeg: bytes | None = None) -> tuple[bool, str]` — legt an, hängt ggf. das Bild per Upload-API an; `(True, "<iid>")` oder `(False, "<grund>")`.
  - `issues_holen(labels: str = "von-nina") -> list[dict] | None` — `None` bei Netzfehler.
  - `notiz(iid: int, text: str) -> bool`
  - `issue_aendern(iid: int, **felder) -> bool` — dünner PUT (z. B. `state_event="close"`, `remove_labels="zur-abnahme"`, `assignee_ids=[0]`).
  - `issue_holen(iid: int) -> dict | None`
  - `puffer_ablegen(conn, nutzlast: dict) -> None` / `puffer_nachtragen(conn) -> int` — Tabelle `meldung_puffer(id, angelegt_am, nutzlast)`; nachtragen versucht jeden Eintrag einmal, löscht bei Erfolg, gibt die Zahl der nachgetragenen zurück.
- Konfiguration (Modulkonstanten, per Umgebung übersteuerbar): `BABU_GITLAB` (Standard `http://127.0.0.1:8929`), `BABU_GITLAB_PROJEKT` (Standard `8`), `BABU_GITLAB_TOKEN` (Pfad, Standard `~/babu-web/.gitlab_token`).

- [ ] **Step 1: Fehlschlagende Tests schreiben (requests gemockt, Puffer mit sqlite in tmp)**

```python
# ans Ende von test_gitlab_meldungen.py
import json
import sqlite3


class _Antwort:
    def __init__(self, status, daten):
        self.status_code, self._daten = status, daten
        self.text = json.dumps(daten)
    def json(self):
        return self._daten


def _klient(monkeypatch, tmp_path, antworten):
    """gitlab_meldungen mit Token-Datei und aufgezeichneten HTTP-Antworten."""
    tok = tmp_path / "tok"
    tok.write_text("glpat-test")
    monkeypatch.setattr(gm, "TOKEN_PFAD", tok)
    rufe = []
    def _ruf(methode, url, **kw):
        rufe.append((methode, url, kw))
        return antworten.pop(0)
    monkeypatch.setattr(gm, "_http", _ruf)
    return rufe


def test_issue_anlegen_mit_bild(monkeypatch, tmp_path):
    rufe = _klient(monkeypatch, tmp_path, [
        _Antwort(201, {"markdown": "![f](/uploads/abc/f.jpg)"}),
        _Antwort(201, {"iid": 77}),
    ])
    ok, was = gm.issue_anlegen({"title": "t", "description": "d", "labels": "bug,von-nina"},
                               bild_jpeg=b"\xff\xd8kein-echtes-jpeg")
    assert (ok, was) == (True, "77")
    assert "/uploads" in rufe[0][1]
    # Das Bild steht als Markdown in der Beschreibung des zweiten Aufrufs.
    assert "/uploads/abc/f.jpg" in rufe[1][2]["json"]["description"]


def test_issue_anlegen_meldet_ausfall(monkeypatch, tmp_path):
    def _kaputt(methode, url, **kw):
        raise OSError("keine Verbindung")
    monkeypatch.setattr(gm, "_http", _kaputt)
    (tmp_path / "tok").write_text("glpat-test")
    monkeypatch.setattr(gm, "TOKEN_PFAD", tmp_path / "tok")
    ok, grund = gm.issue_anlegen({"title": "t", "description": "d", "labels": "bug"})
    assert ok is False and "Verbindung" in grund


def test_puffer_haelt_und_traegt_nach(monkeypatch, tmp_path):
    conn = sqlite3.connect(tmp_path / "portal.db")
    gm.puffer_ablegen(conn, {"issue": {"title": "t", "description": "d", "labels": "bug"},
                             "bild_b64": None})
    _klient(monkeypatch, tmp_path, [_Antwort(201, {"iid": 5})])
    assert gm.puffer_nachtragen(conn) == 1
    rest = conn.execute("select count(*) from meldung_puffer").fetchone()[0]
    assert rest == 0
```

- [ ] **Step 2: Scheitern sehen**

Run: `python -m pytest server/belegreview/tests/test_gitlab_meldungen.py -v`
Expected: neue Tests FAIL (`AttributeError: TOKEN_PFAD` bzw. `_http`).

- [ ] **Step 3: Umsetzen**

```python
# ergänzen in gitlab_meldungen.py (nach den Abbildungsfunktionen)
import base64
import json
import os
import time
from pathlib import Path

import requests

BASIS = os.environ.get("BABU_GITLAB", "http://127.0.0.1:8929").rstrip("/")
PROJEKT = os.environ.get("BABU_GITLAB_PROJEKT", "8")
TOKEN_PFAD = Path(os.environ.get("BABU_GITLAB_TOKEN",
                                 str(Path.home() / "babu-web" / ".gitlab_token")))


def _token() -> str | None:
    try:
        t = TOKEN_PFAD.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return t or None


def _http(methode: str, url: str, **kw):
    """Eine Naht für die Tests — alles HTTP läuft hier durch."""
    kw.setdefault("timeout", 15)
    kw.setdefault("headers", {})["PRIVATE-TOKEN"] = _token() or ""
    return requests.request(methode, url, **kw)


def _api(pfad: str) -> str:
    return f"{BASIS}/api/v4/projects/{PROJEKT}{pfad}"


def issue_anlegen(issue: dict, bild_jpeg: bytes | None = None) -> tuple[bool, str]:
    """Anlegen, Bild zuerst — scheitert der Upload, kommt das Issue ohne Bild.
    Ein fehlendes Foto ist ärgerlich; eine fehlende Meldung wäre ein Bruch."""
    if not _token():
        return False, "kein GitLab-Token hinterlegt"
    beschreibung = issue["description"]
    if bild_jpeg:
        try:
            r = _http("POST", _api("/uploads"),
                      files={"file": ("bildschirm.jpg", bild_jpeg, "image/jpeg")})
            if r.status_code == 201:
                beschreibung += "\n\n" + r.json()["markdown"]
        except Exception:  # noqa: BLE001
            pass
    try:
        r = _http("POST", _api("/issues"),
                  json={**issue, "description": beschreibung})
    except Exception as ex:  # noqa: BLE001
        return False, f"GitLab nicht erreichbar: {ex!r}"[:160]
    if r.status_code != 201:
        return False, f"GitLab antwortete {r.status_code}: {r.text[:120]}"
    return True, str(r.json().get("iid", "angelegt"))


def issues_holen(labels: str = "von-nina") -> list[dict] | None:
    try:
        r = _http("GET", _api(f"/issues?labels={labels}&per_page=50"
                              "&order_by=updated_at&sort=desc"))
    except Exception:  # noqa: BLE001
        return None
    return r.json() if r.status_code == 200 else None


def issue_holen(iid: int) -> dict | None:
    try:
        r = _http("GET", _api(f"/issues/{iid}"))
    except Exception:  # noqa: BLE001
        return None
    return r.json() if r.status_code == 200 else None


def notiz(iid: int, text: str) -> bool:
    try:
        r = _http("POST", _api(f"/issues/{iid}/notes"), json={"body": text})
    except Exception:  # noqa: BLE001
        return False
    return r.status_code == 201


def issue_aendern(iid: int, **felder) -> bool:
    try:
        r = _http("PUT", _api(f"/issues/{iid}"), json=felder)
    except Exception:  # noqa: BLE001
        return False
    return r.status_code == 200


# ── Der Puffer: GitLab darf fehlen, die Meldung nicht ────────────────────────

def _puffer_tabelle(conn) -> None:
    conn.execute("""create table if not exists meldung_puffer(
        id integer primary key,
        angelegt_am text not null,
        nutzlast text not null)""")
    conn.commit()


def puffer_ablegen(conn, nutzlast: dict) -> None:
    """nutzlast = {"issue": <als_issue()>, "bild_b64": str | None}"""
    _puffer_tabelle(conn)
    conn.execute("insert into meldung_puffer(angelegt_am, nutzlast) values(?, ?)",
                 (time.strftime("%Y-%m-%dT%H:%M:%S"),
                  json.dumps(nutzlast, ensure_ascii=False)))
    conn.commit()


def puffer_nachtragen(conn) -> int:
    """Jeden Eintrag genau einmal versuchen; was durchgeht, wird gelöscht.
    Was nicht durchgeht, bleibt liegen und wartet auf den nächsten Anlass."""
    _puffer_tabelle(conn)
    zeilen = conn.execute("select id, nutzlast from meldung_puffer order by id").fetchall()
    geschafft = 0
    for zid, roh in zeilen:
        d = json.loads(roh)
        bild = base64.b64decode(d["bild_b64"]) if d.get("bild_b64") else None
        ok, _ = issue_anlegen(d["issue"], bild_jpeg=bild)
        if not ok:
            break  # GitLab ist weg — der Rest scheitert genauso.
        conn.execute("delete from meldung_puffer where id = ?", (zid,))
        conn.commit()
        geschafft += 1
    return geschafft
```

- [ ] **Step 4: Alle Tests der Datei grün sehen**

Run: `python -m pytest server/belegreview/tests/test_gitlab_meldungen.py -v`
Expected: alles PASS.

- [ ] **Step 5: Commit**

```bash
git add server/belegreview/gitlab_meldungen.py server/belegreview/tests/test_gitlab_meldungen.py
git commit -m "GitLab-Klient und Meldungspuffer: verlieren ist keine Option"
```

---

### Task 4: `/api/rueckmeldung` auf GitLab umbauen, Fixit ausbauen

**Files:**
- Modify: `server/belegreview/babu_web.py` — Route bei Zeile ~4677, Fixit-Block bei ~4198–4248
- Test: `server/belegreview/tests/test_rueckmeldung_route.py` (neu schreiben)

**Interfaces:**
- Consumes: `gitlab_meldungen.als_issue`, `issue_anlegen`, `puffer_ablegen`, `puffer_nachtragen`; `_api_wache`, `_db()` aus babu_web.
- Produces: `POST /api/rueckmeldung` nimmt zusätzlich optional `bild` (base64-JPEG, nach Decodierung max. 3 MB). Antwort bleibt `{"ok": true, "titel": …}`; neu `"issue": <iid|null>`. Die App braucht KEINE Änderung, um weiter zu funktionieren (Bild ist optional).

- [ ] **Step 1: Alte Route lesen** (`babu_web.py:4677`) und den Fixit-Abschnitt identifizieren: Konstanten `FIXIT`, `FIXIT_PAT_PFAD`, `FIXIT_KANAL` und Funktionen `_fixit_pat`, `_an_fixit` (Zeilen ~4198–4248). `RUECKMELDUNG_MAX` bleibt.

- [ ] **Step 2: Tests neu schreiben (Route mit gemocktem gitlab_meldungen)**

Die bisherige `test_rueckmeldung_route.py` testet Belegbox-Ablage + Fixit-Weiterreichen — beides entfällt. Datei ersetzen:

```python
# server/belegreview/tests/test_rueckmeldung_route.py
"""Der Rückmeldeknopf: eine Meldung geht nie verloren.

GitLab da → Issue. GitLab weg → Puffer in portal.db, Antwort trotzdem „ok".
"""
import base64
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def klient(tmp_path, monkeypatch):
    monkeypatch.setenv("BABU_PORTAL_DB", str(tmp_path / "portal.db"))
    import babu_web
    import gitlab_meldungen as gm
    babu_web.PORTAL_DB = tmp_path / "portal.db"
    # Wache: jede Anfrage ist nina.
    monkeypatch.setattr(babu_web, "_api_wache", lambda request: ("nina@0711.io", None))
    return TestClient(babu_web.app), babu_web, gm


def test_gitlab_da_wird_issue(klient, monkeypatch):
    c, bw, gm = klient
    gesehen = {}
    def _anlegen(issue, bild_jpeg=None):
        gesehen.update(issue=issue, bild=bild_jpeg)
        return True, "91"
    monkeypatch.setattr(gm, "issue_anlegen", _anlegen)
    r = c.post("/api/rueckmeldung", json={
        "text": "Die Kacheln springen beim Blättern.",
        "art": "fehler", "ansicht": "Dokumente",
        "bild": base64.b64encode(b"jpegbytes").decode()})
    assert r.status_code == 200
    assert r.json()["issue"] == "91"
    assert gesehen["issue"]["labels"] == "bug,von-nina"
    assert gesehen["bild"] == b"jpegbytes"


def test_gitlab_weg_wird_gepuffert(klient, monkeypatch):
    c, bw, gm = klient
    monkeypatch.setattr(gm, "issue_anlegen", lambda *a, **k: (False, "weg"))
    r = c.post("/api/rueckmeldung", json={"text": "Etwas stimmt nicht."})
    assert r.status_code == 200 and r.json()["ok"] is True
    with bw._db() as conn:
        n = conn.execute("select count(*) from meldung_puffer").fetchone()[0]
    assert n == 1


def test_zu_grosses_bild_wird_abgelehnt(klient, monkeypatch):
    c, bw, gm = klient
    monkeypatch.setattr(gm, "issue_anlegen", lambda *a, **k: (True, "1"))
    riesig = base64.b64encode(b"x" * (3 * 1024 * 1024 + 1)).decode()
    r = c.post("/api/rueckmeldung", json={"text": "Bild zu groß.", "bild": riesig})
    assert r.status_code == 400
```

- [ ] **Step 3: Scheitern sehen**

Run: `python -m pytest server/belegreview/tests/test_rueckmeldung_route.py -v`
Expected: FAIL (Route kennt `issue`/`bild` nicht, `meldung_puffer` existiert nicht).

- [ ] **Step 4: Route umbauen**

Fixit-Konstanten und `_fixit_pat`/`_an_fixit` LÖSCHEN (der erklärende Kommentarblock ~4198–4217 gleich mit; `RUECKMELDUNG_MAX = 8000` und `BILD_MAX = 3 * 1024 * 1024` bleiben/kommen daneben). Route ersetzen:

```python
@app.post("/api/rueckmeldung")
async def api_rueckmeldung(request: Request) -> Response:
    """Was Nina auffällt — ein Feld, ein Knopf, ein GitLab-Issue.

    Die eine Zusage: eine Meldung geht nie verloren. GitLab weg? Dann liegt
    sie in `meldung_puffer` (portal.db) und der nächste Aufruf hier oder von
    /api/rueckmeldungen trägt sie nach. Nina liest in beiden Fällen „angekommen"."""
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)

    text = str(body.get("text") or "").strip()[:RUECKMELDUNG_MAX]
    if len(text) < 3:
        return JSONResponse({"fehler": "Schreib kurz, was los ist — ein Satz "
                             "genügt."}, status_code=400)

    bild: bytes | None = None
    if body.get("bild"):
        try:
            bild = base64.b64decode(str(body["bild"]), validate=True)
        except Exception:  # noqa: BLE001
            return JSONResponse({"fehler": "Bild nicht lesbar"}, status_code=400)
        if len(bild) > BILD_MAX:
            return JSONResponse({"fehler": "Bild zu groß"}, status_code=400)

    import gitlab_meldungen as gm  # noqa: PLC0415
    import rueckmeldung as rm  # noqa: PLC0415
    meldung = rm.Meldung(
        text=text,
        art="wunsch" if str(body.get("art")) == "wunsch" else "fehler",
        quelle="portal" if str(body.get("quelle")) == "portal" else "app",
        ansicht=str(body.get("ansicht") or "")[:80] or None,
        beleg=str(body.get("beleg") or "")[:80] or None,
        von=un,
        geraet=str(body.get("geraet") or "")[:80] or None,
        fassung=str(body.get("fassung") or "")[:40] or None,
    )
    try:
        issue = gm.als_issue(meldung)
    except ValueError as ex:
        return JSONResponse({"fehler": str(ex)}, status_code=400)

    ok, was = await run_in_threadpool(gm.issue_anlegen, issue, bild)
    if not ok:
        with _db() as conn:
            gm.puffer_ablegen(conn, {"issue": issue,
                                     "bild_b64": body.get("bild") or None})
    else:
        # Wenn GitLab wieder da ist, gleich Liegengebliebenes mitnehmen.
        with _db() as conn:
            await run_in_threadpool(gm.puffer_nachtragen, conn)
    print(f"[rückmeldung] {un}: {issue['title'][:60]} — "
          f"{'issue ' + was if ok else 'gepuffert (' + was + ')'}", flush=True)
    return JSONResponse({"ok": True, "titel": issue["title"],
                         "issue": was if ok else None})
```

`import base64` gehört in den Importblock am Dateianfang, falls dort noch nicht vorhanden.

- [ ] **Step 5: Grün sehen, ganze Suite dazu**

Run: `python -m pytest server/belegreview/tests/test_rueckmeldung_route.py server/belegreview/tests/ -x -q`
Expected: neue Tests PASS, keine Regressionen (Suite-Fehlschläge, die schon vor dem Umbau da waren, notieren statt verschlimmern).

- [ ] **Step 6: Commit**

```bash
git add server/belegreview/babu_web.py server/belegreview/tests/test_rueckmeldung_route.py
git commit -m "Rückmeldeknopf legt GitLab-Issues an — Fixit-Draht gekappt"
```

---

### Task 5: `/api/rueckmeldungen` — Liste, Freigeben, Beanstanden

**Namenskorrektur (26.08., während der Umsetzung):** `GET /api/meldungen` existiert bereits (proaktive Erinnerungen aus melden.py, babu_web.py:7288, von der App konsumiert). Die neuen Routen heißen deshalb durchgängig `/api/rueckmeldungen…`.

**Files:**
- Modify: `server/belegreview/babu_web.py` (direkt unter der Rückmeldungs-Route)
- Test: `server/belegreview/tests/test_meldungen_routen.py` (neu)

**Interfaces:**
- Consumes: `gitlab_meldungen.issues_holen/issue_holen/notiz/issue_aendern/status_von/puffer_nachtragen`.
- Produces:
  - `GET /api/rueckmeldungen` → `{"meldungen": [{"iid": int, "titel": str, "status": str, "kommentar": str|null, "link": str}]}` — Sortierung: bitte-pruefen, in-arbeit, gemeldet, erledigt (nur die letzten 20 erledigten); 60 s Modul-Cache.
  - `POST /api/rueckmeldungen/{iid}/freigeben` → nur bei Status `bitte-pruefen`; Notiz „fachlich freigegeben von <un>", `state_event="close"`. Sonst 409.
  - `POST /api/rueckmeldungen/{iid}/beanstanden` mit `{"text": "…"}` (Pflicht) → Notiz „Beanstandung von <un>: <text>", `remove_labels="zur-abnahme"`, `assignee_ids=[]`. Sonst 409/400.

- [ ] **Step 1: Fehlschlagende Tests schreiben**

```python
# server/belegreview/tests/test_meldungen_routen.py
"""„Meine Meldungen": sehen, freigeben, beanstanden — GitLab bleibt unsichtbar."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _issue(iid, state="opened", labels=(), titel="t"):
    return {"iid": iid, "state": state, "labels": list(labels), "title": titel,
            "web_url": f"https://gitlab.0711.io/0711/babu/-/issues/{iid}"}


@pytest.fixture()
def klient(tmp_path, monkeypatch):
    monkeypatch.setenv("BABU_PORTAL_DB", str(tmp_path / "portal.db"))
    import babu_web
    import gitlab_meldungen as gm
    babu_web.PORTAL_DB = tmp_path / "portal.db"
    babu_web._MELDUNGEN_CACHE.update(stand=0.0, daten=None)  # Cache leeren
    monkeypatch.setattr(babu_web, "_api_wache", lambda request: ("nina@0711.io", None))
    return TestClient(babu_web.app), babu_web, gm


def test_liste_sortiert_pruefen_zuoberst(klient, monkeypatch):
    c, bw, gm = klient
    monkeypatch.setattr(gm, "issues_holen", lambda labels="von-nina": [
        _issue(1, labels=["bug"]),
        _issue(2, state="closed"),
        _issue(3, labels=["zur-abnahme"]),
        _issue(4, labels=["in-arbeit"]),
    ])
    monkeypatch.setattr(gm, "puffer_nachtragen", lambda conn: 0)
    monkeypatch.setattr(bw, "_letzte_claude_notiz", lambda iid: "deployt, bitte prüfen")
    r = c.get("/api/rueckmeldungen")
    stati = [m["status"] for m in r.json()["meldungen"]]
    assert stati == ["bitte-pruefen", "in-arbeit", "gemeldet", "erledigt"]
    assert r.json()["meldungen"][0]["kommentar"] == "deployt, bitte prüfen"


def test_freigeben_nur_im_richtigen_zustand(klient, monkeypatch):
    c, bw, gm = klient
    monkeypatch.setattr(gm, "issue_holen", lambda iid: _issue(3, labels=["zur-abnahme"]))
    protokoll = []
    monkeypatch.setattr(gm, "notiz", lambda iid, text: protokoll.append(("notiz", text)) or True)
    monkeypatch.setattr(gm, "issue_aendern", lambda iid, **f: protokoll.append(("put", f)) or True)
    assert c.post("/api/rueckmeldungen/3/freigeben").status_code == 200
    assert protokoll[0] == ("notiz", "fachlich freigegeben von nina@0711.io")
    assert protokoll[1][1]["state_event"] == "close"

    monkeypatch.setattr(gm, "issue_holen", lambda iid: _issue(1, labels=["bug"]))
    assert c.post("/api/rueckmeldungen/1/freigeben").status_code == 409


def test_beanstanden_braucht_text_und_setzt_zurueck(klient, monkeypatch):
    c, bw, gm = klient
    monkeypatch.setattr(gm, "issue_holen", lambda iid: _issue(3, labels=["zur-abnahme"]))
    protokoll = []
    monkeypatch.setattr(gm, "notiz", lambda iid, text: protokoll.append(text) or True)
    monkeypatch.setattr(gm, "issue_aendern", lambda iid, **f: protokoll.append(f) or True)
    assert c.post("/api/rueckmeldungen/3/beanstanden", json={}).status_code == 400
    r = c.post("/api/rueckmeldungen/3/beanstanden", json={"text": "Farbe stimmt noch nicht"})
    assert r.status_code == 200
    assert "Farbe stimmt noch nicht" in protokoll[0]
    assert protokoll[1]["remove_labels"] == "zur-abnahme"
```

- [ ] **Step 2: Scheitern sehen**

Run: `python -m pytest server/belegreview/tests/test_meldungen_routen.py -v`
Expected: FAIL (`_MELDUNGEN_CACHE` existiert nicht, Routen 404).

- [ ] **Step 3: Routen umsetzen** (in babu_web.py, unter `/api/rueckmeldung`)

```python
# ── „Meine Meldungen": die App schaut auf GitLab, ohne es zu wissen ──────────
#
# 60 s Cache, weil die App die Liste bei jedem Öffnen zieht und GitLab auf
# derselben Maschine wohnt wie der Rest — kein Grund, es im Takt zu löchern.
_MELDUNGEN_CACHE: dict = {"stand": 0.0, "daten": None}
_STATUS_RANG = {"bitte-pruefen": 0, "in-arbeit": 1, "gemeldet": 2, "erledigt": 3}


def _letzte_claude_notiz(iid: int) -> str | None:
    """Die Kurzfassung dessen, was der Fix-Lauf zuletzt geschrieben hat."""
    import gitlab_meldungen as gm  # noqa: PLC0415
    try:
        r = gm._http("GET", gm._api(f"/issues/{iid}/notes?sort=desc&per_page=5"))
        if r.status_code != 200:
            return None
        for n in r.json():
            if not n.get("system"):
                return " ".join(str(n.get("body") or "").split())[:160] or None
    except Exception:  # noqa: BLE001
        return None
    return None


@app.get("/api/rueckmeldungen")
async def api_rueckmeldungen(request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    import gitlab_meldungen as gm  # noqa: PLC0415
    jetzt = time.time()
    if _MELDUNGEN_CACHE["daten"] is not None and jetzt - _MELDUNGEN_CACHE["stand"] < 60:
        return JSONResponse({"meldungen": _MELDUNGEN_CACHE["daten"]})
    with _db() as conn:
        await run_in_threadpool(gm.puffer_nachtragen, conn)
    issues = await run_in_threadpool(gm.issues_holen)
    if issues is None:
        alt = _MELDUNGEN_CACHE["daten"]
        return JSONResponse({"meldungen": alt or [],
                             "hinweis": "gerade nicht erreichbar" if alt is None else None})
    eintraege = []
    for i in issues:
        status = gm.status_von(i)
        eintraege.append({
            "iid": i["iid"], "titel": i["title"], "status": status,
            "kommentar": (await run_in_threadpool(_letzte_claude_notiz, i["iid"])
                          if status == "bitte-pruefen" else None),
            "link": i.get("web_url"),
        })
    eintraege.sort(key=lambda e: (_STATUS_RANG[e["status"]], -e["iid"]))
    erledigt = [e for e in eintraege if e["status"] == "erledigt"][:20]
    eintraege = [e for e in eintraege if e["status"] != "erledigt"] + erledigt
    _MELDUNGEN_CACHE.update(stand=jetzt, daten=eintraege)
    return JSONResponse({"meldungen": eintraege})


def _meldung_im_zustand(iid: int, erwartet: str):
    """Vor jedem Schreiben den Ist-Zustand prüfen — kein blindes Überschreiben."""
    import gitlab_meldungen as gm  # noqa: PLC0415
    issue = gm.issue_holen(iid)
    if issue is None:
        return None, JSONResponse({"fehler": "gerade nicht erreichbar"}, status_code=503)
    if gm.status_von(issue) != erwartet:
        return None, JSONResponse({"fehler": "die Meldung ist nicht (mehr) zur "
                                   "Prüfung offen"}, status_code=409)
    return issue, None


@app.post("/api/rueckmeldungen/{iid}/freigeben")
async def api_rueckmeldung_freigeben(iid: int, request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    import gitlab_meldungen as gm  # noqa: PLC0415
    _, fehler = await run_in_threadpool(_meldung_im_zustand, iid, "bitte-pruefen")
    if fehler:
        return fehler
    await run_in_threadpool(gm.notiz, iid, f"fachlich freigegeben von {un}")
    ok = await run_in_threadpool(gm.issue_aendern, iid, state_event="close")
    _MELDUNGEN_CACHE.update(stand=0.0)
    return JSONResponse({"ok": ok})


@app.post("/api/rueckmeldungen/{iid}/beanstanden")
async def api_rueckmeldung_beanstanden(iid: int, request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    text = str(body.get("text") or "").strip()
    if len(text) < 3:
        return JSONResponse({"fehler": "Sag kurz, was noch nicht stimmt — ein "
                             "Satz genügt."}, status_code=400)
    import gitlab_meldungen as gm  # noqa: PLC0415
    _, fehler = await run_in_threadpool(_meldung_im_zustand, iid, "bitte-pruefen")
    if fehler:
        return fehler
    await run_in_threadpool(gm.notiz, iid, f"Beanstandung von {un}: {text[:2000]}")
    ok = await run_in_threadpool(gm.issue_aendern, iid,
                                 remove_labels="zur-abnahme", assignee_ids=[])
    _MELDUNGEN_CACHE.update(stand=0.0)
    return JSONResponse({"ok": ok})
```

- [ ] **Step 4: Grün sehen**

Run: `python -m pytest server/belegreview/tests/test_meldungen_routen.py server/belegreview/tests/test_rueckmeldung_route.py -v`
Expected: alles PASS.

- [ ] **Step 5: Commit**

```bash
git add server/belegreview/babu_web.py server/belegreview/tests/test_meldungen_routen.py
git commit -m "Meine Meldungen: Liste, Freigabe und Beanstandung über den Server"
```

---

### Task 6: Server-Stand auf die H200V deployen (Ritual)

**Files:** keine neuen — Betrieb.

**Interfaces:**
- Consumes: Tasks 1–5 gemergt auf `main` (oder den Branch, der deployt wird — vorher `git log` gegen H200V-Stand prüfen, Memory `babu-ios-merge-falle`).
- Produces: laufende Routen auf der H200V; Voraussetzung für Task 7–10.

- [ ] **Step 1: Golden-Diff VORHER ziehen**

Zuerst den Golden-Stamm bestimmen — den zuletzt benutzten (Memory: Deutsche-Post-Beleg); existiert er im Live-Index nicht mehr, einen anderen Stamm aus dem Index wählen. Dann:

```bash
STAMM=<im-index-nachgeschlagener-stamm>
ssh h200v "curl -s -H \"Authorization: Bearer \$(cat ~/gitchain-eingang/.pat_babu)\" http://127.0.0.1:7844/review/$STAMM | python3 -m json.tool --sort-keys > /tmp/golden-vorher.json; wc -l /tmp/golden-vorher.json"
```

Die Datei muss substanziell sein (hunderte Zeilen). Ist sie leer oder ein Fehler-JSON: anhalten und den Stamm klären — NICHT blind weitermachen.

- [ ] **Step 2: Sicherung und Deploy**

```bash
ssh h200v 'tar czf ~/backups/belegreview-vor-deploy-$(date +%Y%m%d-%H%M).tgz -C ~ belegreview'
scp server/belegreview/babu_web.py server/belegreview/gitlab_meldungen.py server/belegreview/rueckmeldung.py h200v:~/belegreview/
ssh h200v 'pm2 restart babu-web'
```

(`server/belegreview/index.html` bewusst NICHT deployen — Alt-Seite, Memory `babu-salon-portal`.)

- [ ] **Step 3: Golden-Diff NACHHER + Routen live**

```bash
ssh h200v "curl -s -H \"Authorization: Bearer \$(cat ~/gitchain-eingang/.pat_babu)\" http://127.0.0.1:7844/review/$STAMM | python3 -m json.tool --sort-keys > /tmp/golden-nachher.json; diff /tmp/golden-vorher.json /tmp/golden-nachher.json && echo BYTE-GLEICH"
ssh h200v 'curl -s -X POST -H "Authorization: Bearer $(cat ~/gitchain-eingang/.pat_babu)" -H "Content-Type: application/json" http://127.0.0.1:7844/api/rueckmeldung -d "{\"text\":\"Probelauf Meldeschleife — bitte ignorieren\"}"'
ssh h200v 'curl -s -H "Authorization: Bearer $(cat ~/gitchain-eingang/.pat_babu)" http://127.0.0.1:7844/api/rueckmeldungen | head -c 300'
```

Erwartet: `BYTE-GLEICH`; Rückmeldung antwortet `{"ok": true, "issue": "<iid>"}`; Liste enthält den Probelauf mit Status `gemeldet`. Danach aufräumen: das Probelauf-Issue in GitLab schließen (`issue_aendern` per curl oder Web).

- [ ] **Step 4: Bei gerissenem Tor — Rollback**

```bash
ssh h200v 'tar xzf ~/backups/belegreview-vor-deploy-<stempel>.tgz -C ~ && pm2 restart babu-web'
```

---

### Task 7: iOS — Bildschirmfoto am Rückmeldeknopf

**Files:**
- Modify: `ios/Beleg/Beleg/MeldenSheet.swift`
- Modify: `ios/Beleg/Beleg/AblageService.swift:535` (`rueckmeldenSenden`)

**Interfaces:**
- Consumes: `POST /api/rueckmeldung` mit optionalem Feld `bild` (base64-JPEG) aus Task 4.
- Produces: `AblageService.rueckmeldenSenden(…, bildB64: String?)` — neuer letzter Parameter mit Standard `nil`.

- [ ] **Step 1: Foto einfangen, BEVOR das Blatt aufgeht** (in `MeldenKnopf`, MeldenSheet.swift:126)

```swift
/// Das Foto entsteht im Moment des Knopfdrucks — was Nina sah, nicht das Blatt.
private func bildschirmfoto() -> UIImage? {
    guard let szene = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene }).first,
          let fenster = szene.windows.first(where: { $0.isKeyWindow }) else { return nil }
    let maler = UIGraphicsImageRenderer(bounds: fenster.bounds)
    return maler.image { _ in
        fenster.drawHierarchy(in: fenster.bounds, afterScreenUpdates: false)
    }
}
```

`MeldenKnopf` bekommt `@State private var foto: UIImage?`; im Button: `foto = bildschirmfoto(); offen = true`. Das Sheet: `MeldenSheet(ansicht: ansicht, beleg: beleg, foto: foto)`.

- [ ] **Step 2: Schalter und Versand im MeldenSheet**

Neue Eigenschaften: `var foto: UIImage?` und `@State private var fotoMitschicken = true`. Unter dem Texteditor, nur wenn `foto != nil`:

```swift
if let foto {
    Toggle(isOn: $fotoMitschicken) {
        HStack(spacing: 10) {
            Image(uiImage: foto)
                .resizable().scaledToFill()
                .frame(width: 34, height: 60).clipped()
                .clipShape(RoundedRectangle(cornerRadius: 4))
            Text("Bildschirmfoto mitschicken").font(.footnote)
        }
    }
    .tint(GC.ok)
}
```

In `senden()` vor dem Aufruf:

```swift
let bildB64: String? = (fotoMitschicken ? foto : nil)
    .flatMap { $0.jpegData(compressionQuality: 0.6) }
    .map { $0.base64EncodedString() }
```

und `bildB64: bildB64` an `rueckmeldenSenden` durchreichen.

- [ ] **Step 3: AblageService erweitern** — Signatur um `bildB64: String? = nil` ergänzen; im Körper:

```swift
if let bildB64 { koerper["bild"] = bildB64 }
```

- [ ] **Step 4: Bauen und am Simulator prüfen**

Run: `xcodebuild -project ios/Beleg/Beleg.xcodeproj -scheme Beleg -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -3`
Expected: `BUILD SUCCEEDED`. Dann in der App (Simulator): Rückmeldeknopf → Vorschaubild sichtbar → Abschicken → in GitLab hat das Issue ein angehängtes Bild.

- [ ] **Step 5: Commit**

```bash
git add ios/Beleg/Beleg/MeldenSheet.swift ios/Beleg/Beleg/AblageService.swift
git commit -m "Rückmeldung nimmt den Bildschirm mit — ein Foto sagt, wo es klemmt"
```

---

### Task 8: iOS — „Meine Meldungen" mit Freigabe

**Files:**
- Create: `ios/Beleg/Beleg/MeldungenListe.swift`
- Modify: `ios/Beleg/Beleg/AblageService.swift` (drei neue Funktionen)
- Modify: `ios/Beleg/Beleg/KontoMenu.swift` (Eintrag in der ersten `Section`, Zeile ~46)

**Interfaces:**
- Consumes: `GET /api/rueckmeldungen`, `POST /api/rueckmeldungen/{iid}/freigeben`, `POST /api/rueckmeldungen/{iid}/beanstanden` (Task 5); Muster `werBinIch` (AblageService) für Bearer-Aufrufe.
- Produces: `AblageService.meldungenHolen(basis:pat:) async -> [Meldungszeile]`, `meldungFreigeben(iid:basis:pat:)`, `meldungBeanstanden(iid:text:basis:pat:)`; `struct Meldungszeile: Identifiable, Decodable { let iid: Int; let titel: String; let status: String; let kommentar: String?; var id: Int { iid } }`.

- [ ] **Step 1: Service-Funktionen** (AblageService.swift, unter `rueckmeldenSenden`)

```swift
struct Meldungszeile: Identifiable, Decodable {
    let iid: Int
    let titel: String
    let status: String      // gemeldet | in-arbeit | bitte-pruefen | erledigt
    let kommentar: String?
    var id: Int { iid }
}

extension AblageService {
    /// Ninas Meldungen samt Stand (`GET /api/rueckmeldungen`).
    static func meldungenHolen(basis: URL, pat: String) async -> [Meldungszeile]? {
        var request = URLRequest(url: basis.appendingPathComponent("api/rueckmeldungen"))
        request.timeoutInterval = 15
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        struct Antwort: Decodable { let meldungen: [Meldungszeile] }
        guard let (daten, antwort) = try? await URLSession.shared.data(for: request),
              (antwort as? HTTPURLResponse)?.statusCode == 200,
              let json = try? JSONDecoder().decode(Antwort.self, from: daten)
        else { return nil }
        return json.meldungen
    }

    private static func _meldungPost(pfad: String, koerper: [String: Any]?,
                                     basis: URL, pat: String) async -> Bool {
        var request = URLRequest(url: basis.appendingPathComponent(pfad))
        request.httpMethod = "POST"
        request.timeoutInterval = 15
        request.setValue("Bearer \(pat)", forHTTPHeaderField: "Authorization")
        if let koerper {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: koerper)
        }
        guard let (_, antwort) = try? await URLSession.shared.data(for: request)
        else { return false }
        return (antwort as? HTTPURLResponse)?.statusCode == 200
    }

    /// „Passt ✓" — schließt den Vorgang mit Ninas Freigabe.
    static func meldungFreigeben(iid: Int, basis: URL, pat: String) async -> Bool {
        await _meldungPost(pfad: "api/rueckmeldungen/\(iid)/freigeben",
                           koerper: nil, basis: basis, pat: pat)
    }

    /// „Stimmt noch nicht" — mit einem Satz zurück in die Runde.
    static func meldungBeanstanden(iid: Int, text: String,
                                   basis: URL, pat: String) async -> Bool {
        await _meldungPost(pfad: "api/rueckmeldungen/\(iid)/beanstanden",
                           koerper: ["text": text], basis: basis, pat: pat)
    }
}
```

- [ ] **Step 2: Die Liste** (`MeldungenListe.swift`, neu)

```swift
import SwiftUI

/// Nina sieht hier, was aus ihren Meldungen wurde — und gibt Fixe frei.
///
/// Die Schleife schließt sich in der App: melden (Rückmeldeknopf), verfolgen
/// (diese Liste), freigeben (zwei Knöpfe). GitLab führt Buch; Nina muss es
/// nie öffnen. „Bitte prüfen" steht zuoberst, denn das ist der einzige
/// Zustand, in dem sie gebraucht wird.
struct MeldungenListe: View {
    @EnvironmentObject var store: AppStore
    @State private var zeilen: [Meldungszeile]?
    @State private var beanstandung: Meldungszeile?
    @State private var beanstandungsText = ""
    @State private var laeuft = false

    private static let statusText = [
        "gemeldet": "Gemeldet", "in-arbeit": "In Arbeit",
        "bitte-pruefen": "Bitte prüfen", "erledigt": "Erledigt"]

    var body: some View {
        List {
            if let zeilen {
                if zeilen.isEmpty {
                    Text("Noch keine Meldungen — der Knopf mit der Sprechblase "
                         + "wartet oben rechts in jeder Ansicht.")
                        .font(.footnote).foregroundStyle(GC.desc)
                }
                ForEach(zeilen) { z in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(z.titel).font(.subheadline).lineLimit(2)
                            Spacer()
                            Text(Self.statusText[z.status] ?? z.status)
                                .font(.caption2.weight(.semibold))
                                .padding(.horizontal, 8).padding(.vertical, 3)
                                .background(z.status == "bitte-pruefen" ? GC.ok.opacity(0.15)
                                            : GC.bg, in: Capsule())
                        }
                        if z.status == "bitte-pruefen" {
                            if let k = z.kommentar {
                                Text(k).font(.footnote).foregroundStyle(GC.desc).lineLimit(3)
                            }
                            HStack {
                                Button("Passt ✓") { Task { await freigeben(z) } }
                                    .buttonStyle(.borderedProminent).tint(GC.ok)
                                Button("Stimmt noch nicht") {
                                    beanstandungsText = ""
                                    beanstandung = z
                                }
                                .buttonStyle(.bordered)
                            }
                            .disabled(laeuft)
                            .controlSize(.small)
                        }
                    }
                    .padding(.vertical, 2)
                }
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Meine Meldungen")
        .task { await laden() }
        .refreshable { await laden() }
        .alert("Was stimmt noch nicht?", isPresented: .init(
            get: { beanstandung != nil },
            set: { if !$0 { beanstandung = nil } })) {
            TextField("Ein Satz genügt", text: $beanstandungsText)
            Button("Abschicken") { Task { await beanstanden() } }
            Button("Abbrechen", role: .cancel) {}
        }
    }

    private func laden() async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { zeilen = []; return }
        zeilen = await AblageService.meldungenHolen(basis: url, pat: pat) ?? zeilen ?? []
    }

    private func freigeben(_ z: Meldungszeile) async {
        guard let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT() else { return }
        laeuft = true
        defer { laeuft = false }
        if await AblageService.meldungFreigeben(iid: z.iid, basis: url, pat: pat) {
            await laden()
        }
    }

    private func beanstanden() async {
        guard let z = beanstandung, let url = URL(string: store.ablageURL),
              let pat = KeychainHelfer.ladePAT(),
              beanstandungsText.trimmingCharacters(in: .whitespaces).count >= 3
        else { return }
        laeuft = true
        defer { laeuft = false }
        if await AblageService.meldungBeanstanden(iid: z.iid, text: beanstandungsText,
                                                  basis: url, pat: pat) {
            beanstandung = nil
            await laden()
        }
    }
}
```

- [ ] **Step 3: Einstieg im Konto-Menü** (KontoMenu.swift, erste `Section` ab Zeile ~46, nach dem Muster der Nachbarn):

```swift
NavigationLink {
    MeldungenListe()
} label: {
    Label("Meine Meldungen", systemImage: "exclamationmark.bubble")
}
```

- [ ] **Step 4: Bauen und am Simulator die Schleife einmal ganz gehen**

Run: `xcodebuild -project ios/Beleg/Beleg.xcodeproj -scheme Beleg -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -3`
Expected: `BUILD SUCCEEDED`. Dann: Meldung abschicken → erscheint als „Gemeldet"; in GitLab von Hand Label `zur-abnahme` setzen → nach Neuladen „Bitte prüfen" mit Knöpfen → „Passt ✓" → Issue in GitLab geschlossen mit Freigabe-Notiz.

- [ ] **Step 5: Commit**

```bash
git add ios/Beleg/Beleg/MeldungenListe.swift ios/Beleg/Beleg/AblageService.swift ios/Beleg/Beleg/KontoMenu.swift
git commit -m "Meine Meldungen in der App: sehen, freigeben, beanstanden"
```

---

### Task 9: Fix-Lauf — Leitplanke und Taktgeber (Mac)

**Files:**
- Create: `werkzeuge/fixlauf/leitplanke.py`
- Create: `werkzeuge/fixlauf/fixlauf.py`
- Create: `werkzeuge/fixlauf/auftrag.md`
- Test: `server/belegreview/tests/test_fixlauf.py`

**Interfaces:**
- Consumes: GitLab-API über `https://gitlab.0711.io` (Token `~/.babu-fixlauf.token`, User-Agent `curl/8`); `claude`-CLI; Haupt-Checkout `~/babu`.
- Produces: `leitplanke.py` als Modul (`riskant(pfade: list[str]) -> str | None` — Begründung oder None) UND als CLI (`python3 leitplanke.py <pfad>…`, Exit 1 = riskant); `fixlauf.py` mit `kandidaten(issues: list[dict], jetzt_iso: str) -> list[dict]` (pur, testbar) und `main()`.

- [ ] **Step 1: Fehlschlagende Tests**

```python
# server/belegreview/tests/test_fixlauf.py
"""Die Leitplanke und die Kandidatenwahl — deterministisch, ohne Netz."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "werkzeuge" / "fixlauf"))

import fixlauf  # noqa: E402
import leitplanke  # noqa: E402


def test_leitplanke_stoppt_die_vier_bereiche():
    assert leitplanke.riskant(["server/belegreview/boxschreiber.py"])
    assert leitplanke.riskant(["server/belegreview/kontierung.py"])
    assert leitplanke.riskant(["server/belegreview/extf.py"])
    assert leitplanke.riskant(["server/belegreview/migrationen/007_x.sql"])


def test_leitplanke_laesst_ui_durch():
    assert leitplanke.riskant(["ios/Beleg/Beleg/MeldenSheet.swift",
                               "server/belegreview/portal.html"]) is None


def _i(iid, labels, updated="2026-08-26T10:00:00Z"):
    return {"iid": iid, "labels": labels, "updated_at": updated}


def test_kandidaten_nur_bug_ohne_prozesslabel_max_drei():
    issues = [
        _i(1, ["bug"]), _i(2, ["wunsch"]), _i(3, ["bug", "zur-abnahme"]),
        _i(4, ["bug", "braucht-christoph"]), _i(5, ["bug"]), _i(6, ["bug"]),
        _i(7, ["bug"]),
    ]
    iids = [k["iid"] for k in fixlauf.kandidaten(issues, "2026-08-26T10:30:00Z")]
    assert iids == [1, 5, 6]  # 7 fällt der Drei-Grenze zum Opfer


def test_verwaiste_in_arbeit_wird_nach_zwei_stunden_wieder_kandidat():
    frisch = _i(8, ["bug", "in-arbeit"], updated="2026-08-26T09:30:00Z")
    verwaist = _i(9, ["bug", "in-arbeit"], updated="2026-08-26T07:00:00Z")
    iids = [k["iid"] for k in fixlauf.kandidaten([frisch, verwaist],
                                                 "2026-08-26T10:30:00Z")]
    assert iids == [9]
```

- [ ] **Step 2: Scheitern sehen**

Run: `python -m pytest server/belegreview/tests/test_fixlauf.py -v`
Expected: FAIL — Module fehlen.

- [ ] **Step 3: `leitplanke.py`**

```python
#!/usr/bin/env python3
"""Die Leitplanke: welcher Diff darf ohne Christoph auf die H200V?

Deterministisch und dumm mit Absicht. Ein Sprachmodell kann sich
herausreden; eine Pfadliste nicht. Wer hier anschlägt, wird nicht deployt —
Label `braucht-christoph`, fertig. Lieber zehnmal zu vorsichtig als einmal
in die Belegbox geschrieben, was niemand bestellt hat.
"""
from __future__ import annotations

import sys

# Bereich → warum er Christoph braucht. Teilstring-Abgleich auf dem Repo-Pfad.
RISKANT = {
    "boxschreiber": "schreibt in die Belegbox",
    "kontierung": "Geld-/Steuerlogik",
    "geld.py": "Geld-/Steuerlogik",
    "extf": "DATEV/EXTF-Export",
    "kontenrahmen": "Kontenkatalog",
    "kasse": "Kassenlogik (§ 146a AO)",
    "lohn": "Lohn/Sozialversicherung",
    "migration": "Schema von portal.db",
    "anmelden": "Auth/Session",
    "app_schluessel": "Auth/Session",
}


def riskant(pfade: list[str]) -> str | None:
    """Erster Treffer mit Begründung — oder None: frei zum Deploy."""
    for pfad in pfade:
        p = pfad.lower()
        for muster, grund in RISKANT.items():
            if muster in p:
                return f"{pfad}: {grund}"
    return None


if __name__ == "__main__":
    grund = riskant(sys.argv[1:])
    if grund:
        print(f"RISKANT — {grund}")
        sys.exit(1)
    print("frei")
```

- [ ] **Step 4: `fixlauf.py`**

```python
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
        elif "in-arbeit" in labels and not (labels - {"bug", "von-nina", "in-arbeit"}):
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
        war_verwaist = "in-arbeit" in (issue.get("labels") or [])
        _api(f"/issues/{iid}", {"add_labels": "in-arbeit"}, "PUT")
        _api(f"/issues/{iid}/notes",
             {"body": "vorheriger Lauf verwaist, übernehme neu"
              if war_verwaist else "übernehme"}, "POST")
        print(f"fixlauf: starte Claude für #{iid}: {issue['title'][:60]}")
        lauf = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions",
             auftrag.replace("{{IID}}", str(iid))
                    .replace("{{TITEL}}", issue["title"])],
            cwd=REPO, capture_output=True, text=True, timeout=45 * 60)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: `auftrag.md`** — der Arbeitsauftrag des headless Laufs

```markdown
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
```

- [ ] **Step 6: Tests grün sehen**

Run: `python -m pytest server/belegreview/tests/test_fixlauf.py -v`
Expected: 4 PASS.

- [ ] **Step 7: Commit**

```bash
git add werkzeuge/fixlauf/ server/belegreview/tests/test_fixlauf.py
git commit -m "Fix-Lauf: Taktgeber, Leitplanke und Arbeitsauftrag"
```

---

### Task 10: Fix-Lauf scharf schalten (launchd) und Probelauf

**Files:**
- Create: `werkzeuge/fixlauf/io.0711.babu.fixlauf.plist` (Vorlage, wird nach `~/Library/LaunchAgents/` kopiert)

**Interfaces:**
- Consumes: Tasks 1 und 9; `~/.babu-fixlauf.token` auf dem Mac.
- Produces: laufender 30-Minuten-Takt; Log unter `~/Library/Logs/babu-fixlauf.log`.

- [ ] **Step 1: plist schreiben**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>io.0711.babu.fixlauf</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/christophbertsch/babu/werkzeuge/fixlauf/fixlauf.py</string>
    </array>
    <key>StartInterval</key><integer>1800</integer>
    <key>StandardOutPath</key><string>/Users/christophbertsch/Library/Logs/babu-fixlauf.log</string>
    <key>StandardErrorPath</key><string>/Users/christophbertsch/Library/Logs/babu-fixlauf.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

(fixlauf.py braucht nur die Standardbibliothek — `/usr/bin/python3` genügt hier, die MLX-Falle greift nicht. `claude` liegt in `/opt/homebrew/bin`, darum der PATH.)

- [ ] **Step 2: Laden und einmal von Hand feuern**

```bash
cp werkzeuge/fixlauf/io.0711.babu.fixlauf.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/io.0711.babu.fixlauf.plist
launchctl kickstart gui/$(id -u)/io.0711.babu.fixlauf
sleep 5; tail -5 ~/Library/Logs/babu-fixlauf.log
```

Expected: `fixlauf: nichts zu tun` (wenn gerade kein unbeanspruchtes `bug`-Issue offen ist).

- [ ] **Step 3: Probelauf mit einem ungefährlichen, echten Issue**

Ein bewusst kleines Test-Issue anlegen (z. B. Tippfehler in einem Portal-Text), dann:

```bash
launchctl kickstart gui/$(id -u)/io.0711.babu.fixlauf
tail -f ~/Library/Logs/babu-fixlauf.log
```

Expected, in dieser Reihenfolge im Issue sichtbar: Notiz „übernehme" + Label `in-arbeit` → Abschluss-Notiz mit Commit und Deploy-Nachweis → Label `zur-abnahme`, Nina zugewiesen. Danach in der App unter „Meine Meldungen": Status „Bitte prüfen" → „Passt ✓" → Issue geschlossen. **Damit ist die Schleife einmal komplett gelaufen.**

- [ ] **Step 4: Commit**

```bash
git add werkzeuge/fixlauf/io.0711.babu.fixlauf.plist
git commit -m "Fix-Lauf im 30-Minuten-Takt: launchd-Vorlage"
```

---

## Selbstprüfung gegen die Spec

- Baustein 1 (Melden): Tasks 2–4, 7. Puffer: Task 3/4. Screenshot: Tasks 4 (Server) + 7 (App). ✓
- Baustein 2 (Sehen/Freigeben): Tasks 5, 8. Statusabbildung inkl. „braucht-christoph → in Arbeit für Nina": Task 2. ✓
- Baustein 3 (Fix-Lauf): Tasks 9, 10. Leitplanke, Verwaisten-Übernahme, Max-3, Ritual, Rollback: Task 9. ✓
- Baustein 4 (Doku): Notizen/Labels in Tasks 4, 5, 9; `#iid` in Commits: auftrag.md. ✓
- Abweichung von der Spec, bewusst: `puffer_nachtragen` läuft server-seitig (bei /api/rueckmeldung und /api/rueckmeldungen) statt im Fix-Lauf — gleicher Effekt, kein Mac-Umweg zur portal.db.
- Nicht-Ziele respektiert: kein Push an Nina, `wunsch` unangetastet (Task 9 filtert auf `bug`), kein Fixit-Rückkanal (Task 4 baut ihn aus).
