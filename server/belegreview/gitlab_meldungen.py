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

import base64
import json
import os
import time
from pathlib import Path

import requests

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


# ── GitLab-Klient: HTTP und Konfiguration ────────────────────────────────────

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
