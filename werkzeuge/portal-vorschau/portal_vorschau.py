"""Lokale Portal-Vorschau mit Demo-Belegbox — nur zum Ansehen des Designs.

Start: /tmp/babu-venv/bin/python werkzeuge/portal-vorschau/portal_vorschau.py
Dann http://localhost:7899 oeffnen und einmal per JS anmelden:
  fetch("/api/anmelden",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({pat:"test-pat"})}).then(()=>location.href="/portal")
Echte Zugaenge funktionieren hier NICHT (Anmeldung ist gestubbt, jeder
Besucher gilt als angemeldet — nur fuer Screenshots gedacht), es fliesst
nichts nach aussen — reiner Anschau-Server auf 127.0.0.1.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent / "server" / "belegreview"
TMP = Path(tempfile.mkdtemp(prefix="portal-dev-"))


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


arbeit = TMP / "box"
subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
_git(arbeit, "config", "user.name", "dev")
_git(arbeit, "config", "user.email", "dev@local")

golden = json.loads((REPO / "tests/golden/review_weingaertle.json").read_text())
basis = {k: v for k, v in golden.items() if k not in ("audit", "buchungssatz")}

belege = [
    ("2026-07", "20260714-101500-aaa001-friseurbedarf", "Friseurbedarf Nord", 284.60, "2026-07-14", []),
    ("2026-07", "20260722-183000-aaa002-delila-hair", "Delila Hair GmbH", 419.90, "2026-07-22", []),
    ("2026-08", "20260812-093000-aaa003-buerobedarf", "Bürobedarf Müller", 119.00, "2026-08-12", []),
    ("2026-08", "20260826-230700-aaa004-kalugahair", "Kalugahair", 168.00, "2026-08-26",
     ["Der Steuersatz ist nicht sicher zu lesen."]),
]
for monat, stamm, lieferant, brutto, datum, offen in belege:
    d = arbeit / "docs" / monat
    d.mkdir(parents=True, exist_ok=True)
    foto = os.environ.get("BABU_VORSCHAU_FOTO")
    if foto and Path(foto).exists():
        (d / f"{stamm}.jpg").write_bytes(Path(foto).read_bytes())
    else:
        (d / f"{stamm}.jpg").write_bytes(b"\xff\xd8\xff\xe0demo" + stamm.encode())
_git(arbeit, "add", "-A")
_git(arbeit, "commit", "-q", "-m", "aufnahme: demo",
     "--author", "christoph0711.io <aufnahme@gitchain.local>")

(arbeit / "review").mkdir()
for monat, stamm, lieferant, brutto, datum, offen in belege:
    r = json.loads(json.dumps(basis))
    r["datei"] = f"docs/{monat}/{stamm}.jpg"
    r["felder"]["lieferant"] = lieferant
    r["felder"]["brutto"] = brutto
    r["felder"]["netto"] = round(brutto / 1.19, 2)
    r["felder"]["ust"] = round(brutto - brutto / 1.19, 2)
    r["felder"]["datum"] = datum
    r["felder"]["offen"] = offen
    r["felder"]["bewirtungssignal"] = False
    r["engine"] = "Vision (Gerät) + Gemma"
    (arbeit / "review" / f"{stamm}.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=1))
_git(arbeit, "add", "-A")
_git(arbeit, "commit", "-q", "-m", "review: demo",
     "--author", "babu-web <review@gitchain.local>")

bare = TMP / "babu.git"
subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

os.environ["BABU_STORE"] = str(bare)
os.environ["BABU_SEITE"] = str(REPO / "portal.html")
os.environ["BABU_SESSION_GEHEIMNIS"] = str(TMP / ".geheimnis")
os.environ["BABU_PORTAL_DB"] = str(TMP / "portal.db")
os.environ["BABU_INDEX_TTL"] = "0"
os.environ["BABU_COOKIE_SECURE"] = "0"
os.environ["BABU_ORIGIN"] = "http://localhost:7899"
sys.path.insert(0, str(REPO))
import babu_web  # noqa: E402
import boxschreiber  # noqa: E402

# Der Schreibweg zeigt IMMER auf die Wegwerf-Box dieses Laufs — niemals auf
# einen echten Klon. Damit funktionieren auch Aufnahme/Loeschen im
# Anschau-Server, und ein Fehlgriff kann nichts Echtes treffen.
boxschreiber.KLON = TMP / "klon"
boxschreiber.REMOTE = str(bare)
boxschreiber.PAT_PFAD = TMP / "kein-pat"

babu_web.wer_token = lambda token: "christoph0711.io" if token == "test-pat" else None
# Fuer Screenshot-Werkzeuge (Headless-Chrome ohne Cookie): immer angemeldet.
# Nur hier im lokalen Anschau-Server — der Produktivcode bleibt unberuehrt.
babu_web.angemeldet = lambda request: "christoph0711.io"

import uvicorn  # noqa: E402
uvicorn.run(babu_web.app, host="127.0.0.1", port=7899, workers=1)
