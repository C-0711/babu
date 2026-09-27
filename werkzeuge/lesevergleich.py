#!/usr/bin/env python3
"""lesevergleich — liest babu aus dem eigenen Klon dasselbe wie aus dem alten Store?

Startet babu-web zweimal mit derselben leeren Datenbank und fragt dieselben
Lese-Routen ab:
  A  BABU_LESEN=store — direkt aus einem Bare-Store (Kopie der alten Box)
  B  BABU_LESEN=klon  — aus dem eigenen Lesespiegel der umgezogenen Box beim Dienst
Die Antworten müssen gleich sein (gleiche Historie ⇒ gleicher HEAD, gleiche
Belege, gleiche Ablage). Nur lesend; geschrieben wird nichts, auch nicht in
die Box. Gedacht für den Umzugstest (babu.git → babu/<betrieb>/belege).

    python werkzeuge/lesevergleich.py --store <kopie.git> --dienst <url> \\
        --box babu/babu-mig2/belege --dienst-token <datei> --dienst-konto svc-babu-e2e \\
        --mensch-token <datei> --mensch t-babu-mensch --ergebnis <datei.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

WURZEL = Path(__file__).resolve().parent.parent
BELEGREVIEW = next((k for k in (WURZEL / "server" / "belegreview", WURZEL)
                    if (k / "babu_web.py").is_file()), WURZEL / "server" / "belegreview")
ROUTEN = ["/api/belege?limit=500&seite_nr=1", "/api/belege?limit=500&seite_nr=2",
          "/api/belege?limit=500&seite_nr=3", "/api/ablage"]


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def lauf(a, modus: str, tmp: Path) -> dict:
    port = freier_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG_")}
    pat = tmp / "pat"
    shutil.copyfile(a.dienst_token, pat)
    pat.chmod(0o600)
    env.update({
        "HOME": str(tmp), "BABU_LESEN": modus, "BABU_STORE": str(a.store),
        "BABU_GATEWAY": a.dienst, "GITCHAIN_ID_HOST": a.dienst, "BABU_REF": a.box,
        "BABU_PUSH_PAT": str(pat), "BABU_GIT_NUTZER": a.dienst_konto,
        "BABU_LESE_WURZEL": str(tmp / "lesen"), "BABU_BOX_KLON": str(tmp / "klon"),
        "BABU_PORTAL_DB": str(tmp / "portal.db"), "BABU_SESSION_GEHEIMNIS": str(tmp / ".g"),
        "BABU_ERLAUBT": a.mensch, "BABU_NACHLESE": "0", "BABU_INDEX_TTL": "0",
        "BABU_ORIGIN": f"http://127.0.0.1:{port}", "BABU_PORT": str(port),
        "GEMMA_API": "http://127.0.0.1:9/v1/chat/completions",
        "EMBED_API": "http://127.0.0.1:9/v1/embeddings", "GIT_TERMINAL_PROMPT": "0",
    })
    log = open(tmp / "babu-web.log", "w")
    p = subprocess.Popen([a.python, "babu_web.py"], cwd=BELEGREVIEW, env=env,
                         stdout=log, stderr=subprocess.STDOUT)
    basis = f"http://127.0.0.1:{port}"
    antworten: dict = {}
    try:
        for _ in range(240):
            try:
                requests.get(basis + "/healthz", timeout=2)
                break
            except requests.RequestException:
                time.sleep(0.5)
        if modus == "klon":
            for _ in range(600):   # erster Klon ~335 MiB
                if (tmp / "lesen" / f"{a.box}.git" / "HEAD").is_file():
                    break
                time.sleep(0.5)
        auth = {"Authorization": "Bearer " + a.mensch_token.read_text().strip()}
        t0 = time.time()
        for r in ROUTEN:
            x = requests.get(basis + r, headers=auth, timeout=600)
            antworten[r] = {"status": x.status_code, "sha256": hashlib.sha256(x.content).hexdigest(),
                            "bytes": len(x.content),
                            "gesamt": (x.json().get("gesamt") if x.headers.get("content-type", "")
                                       .startswith("application/json") else None),
                            "stand": (x.json().get("stand") if x.headers.get("content-type", "")
                                      .startswith("application/json") else None)}
        antworten["_sekunden"] = round(time.time() - t0, 1)
        if modus == "klon":
            antworten["_spiegel"] = str((tmp / "lesen" / f"{a.box}.git").relative_to(tmp))
    finally:
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()
        log.close()
    return antworten


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True, type=Path)
    ap.add_argument("--dienst", required=True)
    ap.add_argument("--box", required=True)
    ap.add_argument("--dienst-token", required=True, type=Path)
    ap.add_argument("--dienst-konto", required=True)
    ap.add_argument("--mensch-token", required=True, type=Path)
    ap.add_argument("--mensch", required=True)
    ap.add_argument("--ergebnis", type=Path)
    ap.add_argument("--python", default=sys.executable)
    a = ap.parse_args()
    a.dienst = a.dienst.rstrip("/")
    ergebnis = {}
    for modus in ("store", "klon"):
        tmp = Path(tempfile.mkdtemp(prefix=f"babu-lv-{modus}-"))
        try:
            ergebnis[modus] = lauf(a, modus, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    gleich = all(ergebnis["store"][r] == ergebnis["klon"][r] for r in ROUTEN)
    ok = gleich and all(ergebnis["store"][r]["status"] == 200 for r in ROUTEN)
    ergebnis["gleich"] = gleich
    ergebnis["ok"] = ok
    text = json.dumps(ergebnis, ensure_ascii=False, indent=2)
    print(text)
    if a.ergebnis:
        a.ergebnis.write_text(text)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
