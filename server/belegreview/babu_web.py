#!/usr/bin/env python3
"""babu-web — Upload-Seite + Review-Rückkanal für babu.0711.io.

- GET /            → statische Upload-Seite (index.html im selben Ordner)
- GET /review/{n}  → Review-JSON aus babu.git (Bearer-PAT nötig, whoami wie
                     beim Eingang; Allowlist identisch). `n` ist der Datei-
                     Stamm — exakt oder als Suffix (die App kennt nur ihren
                     lokalen Namen, der Server prefixt Zeitstempel + Hex).

Liest NUR aus dem Bare-Store (git show) — schreibt nichts, kein Lock-Risiko.
/ablage und /health laufen weiter direkt zum Eingang (:7843, Tunnel-Ingress).
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

import requests
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

WURZEL = Path(__file__).resolve().parent
SEITE = Path.home() / "babu-web" / "index.html"
STORE = Path.home() / "inspektor-store" / "inspektor" / "ws-christoph0711.io" / "babu.git"
GITCHAIN_ID = os.environ.get("GITCHAIN_ID_HOST", "https://gitchain.de").rstrip("/")
GEMMA_API = os.environ.get("GEMMA_API", "http://127.0.0.1:11435/v1/chat/completions")
GEMMA_MODELL = os.environ.get("GEMMA_MODELL", "gemma4-mm")
ERLAUBT = {u.strip().lower() for u in os.environ.get("BABU_ERLAUBT", "christoph0711.io").split(",") if u.strip()}
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")

app = FastAPI(title="babu-web", docs_url=None, redoc_url=None)

# whoami-Cache: Token-Hash → (un, bis) — schont gitchain.de bei App-Polling.
_CACHE: dict[int, tuple[str, float]] = {}


def wer(request: Request) -> str | None:
    hdr = request.headers.get("authorization", "")
    if not hdr.lower().startswith("bearer "):
        return None
    token = hdr[7:].strip()
    if not token:
        return None
    # Kein Format-Vorurteil: wie der Eingang entscheidet allein whoami.
    schluessel = hash(token)
    jetzt = time.time()
    eintrag = _CACHE.get(schluessel)
    if eintrag and eintrag[1] > jetzt:
        return eintrag[0]
    try:
        r = requests.get(GITCHAIN_ID + "/auth/whoami",
                         headers={"Authorization": "Bearer " + token,
                                  "User-Agent": "gitchain-babu-web/1"},
                         timeout=8)
        if r.status_code != 200:
            return None
        ident = r.json()
        un = str(ident.get("un") or ident.get("username") or "").lower()
    except Exception:  # noqa: BLE001
        return None
    if not un:
        return None
    _CACHE[schluessel] = (un, jetzt + 300)
    return un


def git_show(pfad: str) -> bytes | None:
    r = subprocess.run(["git", "-C", str(STORE), "show", f"HEAD:{pfad}"],
                       capture_output=True, timeout=20)
    return r.stdout if r.returncode == 0 else None


def review_pfad(stamm: str) -> str | None:
    """Exakter Treffer oder Suffix-Match (Server prefixt JJJJMMTT-HHMMSS-hex-)."""
    if git_show(f"review/{stamm}.json") is not None:
        return f"review/{stamm}.json"
    r = subprocess.run(["git", "-C", str(STORE), "ls-tree", "--name-only", "HEAD:review"],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        return None
    kandidaten = [z for z in r.stdout.splitlines()
                  if z.endswith(f"-{stamm}.json") or z == f"{stamm}.json"]
    return f"review/{kandidaten[0]}" if len(kandidaten) == 1 else None


@app.get("/")
def seite() -> FileResponse:
    return FileResponse(SEITE, media_type="text/html")


@app.get("/review/{stamm}")
def review(stamm: str, request: Request) -> Response:
    un = wer(request)
    if un is None:
        return JSONResponse({"fehler": "Token fehlt oder ungültig"}, status_code=401)
    if un not in ERLAUBT:
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    if not NAME_RE.match(stamm):
        return JSONResponse({"fehler": "ungültiger Name"}, status_code=400)
    stamm = re.sub(r"\.(jpg|jpeg|png|pdf)$", "", stamm, flags=re.I)
    pfad = review_pfad(stamm)
    if pfad is None:
        return JSONResponse({"fehler": "kein Review (noch in Arbeit?)"}, status_code=404)
    daten = git_show(pfad)
    if daten is None:
        return JSONResponse({"fehler": "Lesefehler"}, status_code=500)
    # Anreicherung: Audit-Stempel (echte GitChain-Commits) + DATEV-Buchungssatz —
    # serverseitig berechnet, wirkt damit auch für bereits vorhandene Reviews.
    try:
        d = json.loads(daten)
        d["audit"] = {"aufnahme": commit_info(d.get("datei", "")),
                      "review": commit_info(pfad)}
        d["buchungssatz"] = datev_buchungssatz(d)
        return JSONResponse(d)
    except Exception:  # noqa: BLE001
        return Response(content=daten, media_type="application/json")


def commit_info(pfad: str) -> dict | None:
    if not pfad:
        return None
    r = subprocess.run(["git", "-C", str(STORE), "log", "-1",
                        "--format=%h|%cI|%an", "--", pfad],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    h, zeit, autor = r.stdout.strip().split("|", 2)
    return {"commit": h, "zeit": zeit, "autor": autor}


def datev_buchungssatz(d: dict) -> dict | None:
    """Buchungszeile in DATEV-Feldlogik (Vorstufe zum EXTF-v13-Writer, Phase 5)."""
    f = d.get("felder", {})
    e = d.get("einschaetzung", {})
    brutto, konto = f.get("brutto"), e.get("konto_skr04")
    if brutto is None or not konto:
        return None
    belegdatum = None
    datum = f.get("datum") or ""
    teile = datum.split(".")
    if len(teile) == 3:
        belegdatum = f"{int(teile[0]):02d}{int(teile[1]):02d}"   # TTMM
    belegfeld1 = re.sub(r"[^A-Za-z0-9$%&*+-/]", "", f.get("beleg_nr") or "")[:36] or None
    return {
        "umsatz": f"{brutto:.2f}".replace(".", ","),
        "soll_haben": "S",
        "konto": konto,
        "gegenkonto": "70099",
        "bu_schluessel": e.get("steuerschluessel"),
        "belegdatum": belegdatum,
        "belegfeld1": belegfeld1,
        "buchungstext": (f.get("lieferant") or "")[:60] or None,
    }


def belegdaten_kontext(max_zeichen: int = 12000) -> str:
    """Kompakte Zusammenfassung aller Reviews als Chat-Kontext (neueste zuerst)."""
    r = subprocess.run(["git", "-C", str(STORE), "ls-tree", "--name-only", "HEAD:review"],
                       capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        return ""
    dateien = [z for z in r.stdout.splitlines()
               if z.endswith(".json") and not z.endswith(".embedding.json")]
    bloecke: list[str] = []
    laenge = 0
    for name in sorted(dateien, reverse=True):
        roh = git_show(f"review/{name}")
        if roh is None:
            continue
        try:
            d = json.loads(roh)
        except Exception:  # noqa: BLE001
            continue
        f = d.get("felder", {})
        e = d.get("einschaetzung", {})
        v = d.get("vlm") or {}
        zeilen = [
            f"Beleg {d.get('datei', name)}:",
            f"  Belegart: {e.get('belegart')} · Dokumentklasse: {d.get('dokumentklasse')}",
            f"  Lieferant: {v.get('lieferant') or f.get('lieferant')} · Beleg-Nr.: {f.get('beleg_nr')} · Datum: {f.get('datum')}",
            f"  Netto {f.get('netto')} · USt {f.get('ust')} (Satz {f.get('ust_satz')} %) · Brutto {f.get('brutto')}"
            + (f" · Trinkgeld {v.get('trinkgeld')}" if v.get("trinkgeld") else ""),
            f"  Konto SKR04 {e.get('konto_skr04')} · Steuerschlüssel {e.get('steuerschluessel')}"
            + (f" · Zahlungsart {v.get('zahlungsart')}" if v.get("zahlungsart") else ""),
        ]
        if e.get("hinweise"):
            zeilen.append("  Hinweise: " + " | ".join(e["hinweise"]))
        if f.get("offen"):
            zeilen.append("  Offen: " + " | ".join(f["offen"]))
        block = "\n".join(zeilen)
        if laenge + len(block) > max_zeichen:
            break
        bloecke.append(block)
        laenge += len(block)
    return "\n\n".join(bloecke)


@app.post("/chat")
async def chat(request: Request) -> Response:
    un = wer(request)
    if un is None:
        return JSONResponse({"fehler": "Token fehlt oder ungültig"}, status_code=401)
    if un not in ERLAUBT:
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    frage = str(body.get("frage", "")).strip()
    if not frage or len(frage) > 2000:
        return JSONResponse({"fehler": "frage fehlt oder zu lang"}, status_code=400)

    kontext = belegdaten_kontext()
    if not kontext:
        return JSONResponse({"antwort": "Die Belegbox enthält noch keine Reviews."})
    payload = {
        "model": GEMMA_MODELL,
        "temperature": 0.2,
        "max_tokens": 700,
        "messages": [
            {"role": "system", "content":
                "Du bist der Belegbox-Assistent von babu (0711 Intelligence). "
                "Antworte auf Deutsch, knapp und präzise, AUSSCHLIESSLICH auf Basis "
                "der mitgelieferten Belegdaten. Keine Sie-Anrede — neutrale Formen "
                "oder Du. Nenne bei Aussagen den Beleg (Lieferant oder Dateiname). "
                "Beträge deutsch formatieren (1.234,56 €). Steht etwas nicht in den "
                "Daten, sage das offen. Keine Steuerberatung — Hinweise sind "
                "Ersteinschätzungen."},
            {"role": "user", "content": f"BELEGDATEN:\n{kontext}\n\nFRAGE: {frage}"},
        ],
    }

    # SSE-Streaming (App): Text-Deltas von vLLM direkt durchreichen.
    if body.get("stream"):
        payload["stream"] = True

        def sse():
            try:
                with requests.post(GEMMA_API, json=payload, stream=True, timeout=180) as r:
                    r.raise_for_status()
                    for zeile in r.iter_lines(decode_unicode=True):
                        if not zeile or not zeile.startswith("data: "):
                            continue
                        roh = zeile[6:]
                        if roh == "[DONE]":
                            break
                        try:
                            delta = json.loads(roh)["choices"][0]["delta"].get("content") or ""
                        except Exception:  # noqa: BLE001
                            continue
                        if delta:
                            yield "data: " + json.dumps({"d": delta}, ensure_ascii=False) + "\n\n"
            except Exception:  # noqa: BLE001
                yield "data: " + json.dumps({"fehler": "Gemma nicht erreichbar"}) + "\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    try:
        r = requests.post(GEMMA_API, json=payload, timeout=120)
        r.raise_for_status()
        antwort = r.json()["choices"][0]["message"]["content"].strip()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "Gemma nicht erreichbar"}, status_code=502)
    return JSONResponse({"antwort": antwort})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7844, workers=1)
