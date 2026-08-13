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
import base64
import hmac
import hashlib
import json
import os
import re
import secrets
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

import requests
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

WURZEL = Path(__file__).resolve().parent
SEITE = Path(os.environ.get("BABU_SEITE", str(Path.home() / "babu-web" / "index.html")))
STORE = Path(os.environ.get("BABU_STORE", str(Path.home() / "inspektor-store" / "inspektor"
                                              / "ws-christoph0711.io" / "babu.git")))
GEHEIMNIS_PFAD = Path(os.environ.get("BABU_SESSION_GEHEIMNIS",
                                     str(Path.home() / "babu-web" / ".session_geheimnis")))
PORTAL_ORIGIN = os.environ.get("BABU_ORIGIN", "https://babu.0711.io")
PORTAL_DB = Path(os.environ.get("BABU_PORTAL_DB", str(Path.home() / "babu-web" / "portal.db")))


# ---------------------------------------------------------------------------
# Portal-State (Lesestatus, Einstellungen): SQLite — kein Audit-Material,
# gehört nicht als Rauschen in die Belegbox-Historie.
# ---------------------------------------------------------------------------

_DB_LOCK = threading.Lock()


def _db() -> sqlite3.Connection:
    PORTAL_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(PORTAL_DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS lesestatus
        (un TEXT NOT NULL, dokument TEXT NOT NULL, zeit TEXT NOT NULL,
         PRIMARY KEY (un, dokument))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS einstellungen
        (un TEXT NOT NULL, schluessel TEXT NOT NULL, wert TEXT NOT NULL,
         PRIMARY KEY (un, schluessel))""")
    return conn


def db_gelesen(un: str) -> set[str]:
    with _DB_LOCK, _db() as c:
        return {z[0] for z in c.execute(
            "SELECT dokument FROM lesestatus WHERE un=?", (un,))}


def db_gelesen_setzen(un: str, dokument: str) -> None:
    with _DB_LOCK, _db() as c:
        c.execute("INSERT OR REPLACE INTO lesestatus VALUES (?,?,?)",
                  (un, dokument, time.strftime("%Y-%m-%dT%H:%M:%S")))


def db_einstellungen(un: str) -> dict[str, str]:
    with _DB_LOCK, _db() as c:
        return dict(c.execute(
            "SELECT schluessel, wert FROM einstellungen WHERE un=?", (un,)))


def db_einstellung_setzen(un: str, schluessel: str, wert: str) -> None:
    with _DB_LOCK, _db() as c:
        c.execute("INSERT OR REPLACE INTO einstellungen VALUES (?,?,?)",
                  (un, schluessel, wert))
GITCHAIN_ID = os.environ.get("GITCHAIN_ID_HOST", "https://gitchain.de").rstrip("/")
GEMMA_API = os.environ.get("GEMMA_API", "http://127.0.0.1:11435/v1/chat/completions")
GEMMA_MODELL = os.environ.get("GEMMA_MODELL", "gemma4-mm")
ERLAUBT = {u.strip().lower() for u in os.environ.get("BABU_ERLAUBT", "christoph0711.io").split(",") if u.strip()}
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")

app = FastAPI(title="babu-web", docs_url=None, redoc_url=None)

# whoami-Cache: Token-Hash → (un, bis) — schont gitchain.de bei App-Polling.
_CACHE: dict[int, tuple[str, float]] = {}


def wer_token(token: str) -> str | None:
    """PAT → Benutzername via whoami (mit 5-min-Cache). Kein Format-Vorurteil."""
    if not token:
        return None
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


def wer(request: Request) -> str | None:
    hdr = request.headers.get("authorization", "")
    if not hdr.lower().startswith("bearer "):
        return None
    return wer_token(hdr[7:].strip())


# ---------------------------------------------------------------------------
# Session (Portal): PAT einmal einlösen → HttpOnly-Cookie. Der PAT wird nicht
# gespeichert; das Cookie trägt nur {un, exp}, HMAC-signiert.
# ---------------------------------------------------------------------------

SESSION_COOKIE = "babu_sitzung"
SESSION_DAUER = 30 * 24 * 3600  # 30 Tage, gleitend
# Produktiv immer Secure (babu.0711.io ist TLS); nur lokale Dev-Server ohne HTTPS
# dürfen das abschalten (BABU_COOKIE_SECURE=0).
SESSION_SECURE = os.environ.get("BABU_COOKIE_SECURE", "1") != "0"


def _geheimnis() -> bytes:
    try:
        wert = GEHEIMNIS_PFAD.read_text().strip()
        if wert:
            return wert.encode()
    except FileNotFoundError:
        pass
    wert = secrets.token_hex(32)
    GEHEIMNIS_PFAD.parent.mkdir(parents=True, exist_ok=True)
    GEHEIMNIS_PFAD.write_text(wert + "\n")
    GEHEIMNIS_PFAD.chmod(0o600)
    return wert.encode()


def _signieren(un: str, exp: int) -> str:
    nutz = base64.urlsafe_b64encode(f"{un}|{exp}".encode()).decode().rstrip("=")
    sig = hmac.new(_geheimnis(), nutz.encode(), hashlib.sha256).hexdigest()
    return f"{nutz}.{sig}"


def _pruefen(wert: str) -> str | None:
    try:
        nutz, sig = wert.split(".", 1)
        erwartet = hmac.new(_geheimnis(), nutz.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, erwartet):
            return None
        roh = base64.urlsafe_b64decode(nutz + "=" * (-len(nutz) % 4)).decode()
        un, exp = roh.split("|", 1)
        if int(exp) < time.time():
            return None
        return un.lower() or None
    except Exception:  # noqa: BLE001
        return None


def _origin_ok(request: Request) -> bool:
    """CSRF-Schutz für Cookie-POSTs: Origin (falls gesendet) muss passen."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    return origin.rstrip("/") in {PORTAL_ORIGIN.rstrip("/"),
                                  "http://127.0.0.1:7844", "http://localhost:7844"}


def angemeldet(request: Request) -> str | None:
    """Cookie ODER Bearer — Portal und App teilen dieselben /api/*-Routen."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        un = _pruefen(cookie)
        if un:
            if request.method not in ("GET", "HEAD") and not _origin_ok(request):
                return None
            return un
    return wer(request)


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


# ---------------------------------------------------------------------------
# Index über den Git-Store: einmal lesen, aus dem Speicher servieren.
# Invalidierung über HEAD (rev-parse, ~5 s TTL); Blobs Blob-OID-gecacht via
# cat-file --batch — kein Subprocess-Sturm pro Request.
# ---------------------------------------------------------------------------

BILD_ENDUNGEN = {".jpg", ".jpeg", ".png"}
BELEG_ENDUNGEN = BILD_ENDUNGEN | {".pdf", ".heic", ".xml"}
INDEX_TTL = float(os.environ.get("BABU_INDEX_TTL", "5"))

_INDEX_LOCK = threading.Lock()
_INDEX: dict = {"head": None, "geprueft": 0.0, "belege": {}, "reviews": {},
                "dokumente": [], "zeiten": {}, "oid_cache": {}}


def _git(args: list[str], timeout: int = 30) -> str | None:
    r = subprocess.run(["git", "-C", str(STORE), *args],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout if r.returncode == 0 else None


def _blobs_lesen(oids: list[str]) -> dict[str, bytes]:
    """Mehrere Blobs mit EINEM cat-file-Prozess lesen."""
    if not oids:
        return {}
    p = subprocess.run(["git", "-C", str(STORE), "cat-file", "--batch"],
                       input="\n".join(oids).encode() + b"\n",
                       capture_output=True, timeout=60)
    ergebnis: dict[str, bytes] = {}
    daten = p.stdout
    pos = 0
    while pos < len(daten):
        ende = daten.find(b"\n", pos)
        if ende < 0:
            break
        kopf = daten[pos:ende].decode(errors="replace").split()
        pos = ende + 1
        if len(kopf) == 3 and kopf[1] == "blob":
            groesse = int(kopf[2])
            ergebnis[kopf[0]] = daten[pos:pos + groesse]
            pos += groesse + 1  # + Trenn-Newline
        # "missing"-Zeilen haben keinen Body
    return ergebnis


def _monat_aus_name(name: str, pfad: str) -> str | None:
    m = re.match(r"^(\d{4})(\d{2})\d{2}-", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.match(r"^docs/(\d{4}-\d{2})/", pfad)
    return m.group(1) if m else None


def _zeiten_walk() -> dict[str, dict]:
    """Pro Pfad der jüngste Commit (== `git log -1 -- pfad`), ein Prozess."""
    out = _git(["log", "--format=@%h|%cI|%an", "--name-status"], 60) or ""
    zeiten: dict[str, dict] = {}
    aktuell: dict | None = None
    for zeile in out.splitlines():
        if zeile.startswith("@"):
            h, zeit, autor = zeile[1:].split("|", 2)
            aktuell = {"commit": h, "zeit": zeit, "autor": autor}
        elif "\t" in zeile and aktuell:
            pfad = zeile.split("\t")[-1]  # bei Renames zählt das Ziel
            zeiten.setdefault(pfad, aktuell)
    return zeiten


def _status_ableiten(review: dict | None, bewirtung_da: bool) -> str:
    if review is None:
        return "erfasst"
    f = review.get("felder") or {}
    # Trinkgeld-Differenzen sind Information, keine Frage — das Trinkgeld hat
    # die Bild-Lane bereits erfasst. Eine Frage bleibt nur die Bewirtung selbst
    # (§4 Abs. 5: Anlass + Teilnehmer), bis sie beantwortet ist.
    echte_offen = [o for o in (f.get("offen") or []) if "trinkgeld" not in str(o).lower()]
    braucht_bewirtung = bool(f.get("bewirtungssignal")) and not bewirtung_da
    if not echte_offen and not braucht_bewirtung and f.get("summenprobe_ok"):
        return "geprüft"
    return "nachfrage"


def _index_bauen(head: str) -> None:
    # Klassisches ls-tree-Format „<mode> <typ> <oid>\t<pfad>“ — läuft auch auf
    # Git < 2.36 (H200V: 2.34), das --format für ls-tree noch nicht kennt.
    out = _git(["ls-tree", "-r", "HEAD"], 60) or ""
    pfade: dict[str, str] = {}
    for zeile in out.splitlines():
        kopf, _, pfad = zeile.partition("\t")
        teile = kopf.split()
        if pfad and len(teile) == 3 and teile[1] == "blob":
            pfade[pfad] = teile[2]

    review_pfade = {p: oid for p, oid in pfade.items()
                    if p.startswith("review/") and p.endswith(".json")
                    and not p.endswith(".embedding.json")
                    and not p.endswith(".bewirtung.json")}
    bewirtung_staemme = {p[len("review/"):-len(".bewirtung.json")]
                         for p in pfade if p.endswith(".bewirtung.json")}
    beleg_pfade = [p for p in pfade
                   if p.startswith("docs/") and Path(p).suffix.lower() in BELEG_ENDUNGEN]

    oid_cache = _INDEX["oid_cache"]
    fehlend = [oid for oid in review_pfade.values() if oid not in oid_cache]
    for oid, roh in _blobs_lesen(fehlend).items():
        try:
            oid_cache[oid] = json.loads(roh)
        except Exception:  # noqa: BLE001
            oid_cache[oid] = None

    zeiten = _zeiten_walk()

    belege: dict[str, dict] = {}
    reviews: dict[str, dict] = {}
    for pfad in beleg_pfade:
        name = pfad.rsplit("/", 1)[-1]
        stamm = re.sub(r"\.[A-Za-z0-9]+$", "", name)
        review_pfad_ = f"review/{stamm}.json"
        review = oid_cache.get(review_pfade.get(review_pfad_, ""))
        bewirtung_da = stamm in bewirtung_staemme
        f = (review or {}).get("felder") or {}
        v = (review or {}).get("vlm") or {}
        e = (review or {}).get("einschaetzung") or {}
        eintrag = {
            "stamm": stamm,
            "datei": pfad,
            "bild_oid": pfade.get(pfad),
            "monat": _monat_aus_name(name, pfad),
            "hochgeladen": (zeiten.get(pfad) or {}).get("zeit"),
            "status": _status_ableiten(review, bewirtung_da),
            "review_zeit": (zeiten.get(review_pfad_) or {}).get("zeit") if review else None,
            "lieferant": v.get("lieferant") or f.get("lieferant"),
            "datum": f.get("datum"),
            "brutto": f.get("brutto"),
            "netto": f.get("netto"),
            "ust": f.get("ust"),
            "ust_satz": f.get("ust_satz"),
            "belegart": (review or {}).get("semantik", {}).get("belegart") if review else None,
            "dokumentklasse": (review or {}).get("dokumentklasse") if review else None,
            "konto_skr04": e.get("konto_skr04"),
            "steuerschluessel": e.get("steuerschluessel"),
            "buchungstext": (datev_buchungssatz(review) or {}).get("buchungstext") if review else None,
            "offen": list(f.get("offen") or []),
            "summenprobe_ok": f.get("summenprobe_ok"),
            "bewirtung": bool(f.get("bewirtungssignal")),
            "bewirtung_beantwortet": bewirtung_da,
        }
        belege[stamm] = eintrag
        if review is not None:
            reviews[stamm] = review

    # Kanzlei-Dokumente: dokumente/JJJJ-MM/<name> + <name>.meta.json-Sidecar
    meta_pfade = {p_: oid for p_, oid in pfade.items()
                  if p_.startswith("dokumente/") and p_.endswith(".meta.json")}
    fehlend_meta = [oid for oid in meta_pfade.values() if oid not in oid_cache]
    for oid, roh in _blobs_lesen(fehlend_meta).items():
        try:
            oid_cache[oid] = json.loads(roh)
        except Exception:  # noqa: BLE001
            oid_cache[oid] = None
    dokumente: list[dict] = []
    for pfad, oid in pfade.items():
        if not pfad.startswith("dokumente/") or pfad.endswith(".meta.json"):
            continue
        meta = oid_cache.get(meta_pfade.get(pfad + ".meta.json", "")) or {}
        name = pfad.rsplit("/", 1)[-1]
        dokumente.append({
            "pfad": pfad,
            "name": name,
            "titel": (meta.get("titel") or name) if isinstance(meta, dict) else name,
            "art": (meta.get("art") or "dokument") if isinstance(meta, dict) else "dokument",
            "von": (zeiten.get(pfad) or {}).get("autor"),
            "zeit": (zeiten.get(pfad) or {}).get("zeit"),
        })
    dokumente.sort(key=lambda d_: d_["zeit"] or "", reverse=True)
    _INDEX["dokumente"] = dokumente

    _INDEX["belege"] = belege
    _INDEX["reviews"] = reviews
    _INDEX["zeiten"] = zeiten
    _INDEX["head"] = head
    _INDEX["geprueft"] = time.time()


def index_aktuell() -> dict:
    with _INDEX_LOCK:
        jetzt = time.time()
        if _INDEX["head"] is not None and jetzt - _INDEX["geprueft"] < INDEX_TTL:
            return _INDEX
        kopf = (_git(["rev-parse", "HEAD"], 10) or "").strip()
        if kopf and kopf != _INDEX["head"]:
            _index_bauen(kopf)
        else:
            _INDEX["geprueft"] = jetzt
        return _INDEX


def _beleg_liste(monat: str | None = None, status: str | None = None) -> list[dict]:
    idx = index_aktuell()
    zeilen = list(idx["belege"].values())
    if monat:
        zeilen = [z for z in zeilen if z["monat"] == monat]
    if status:
        zeilen = [z for z in zeilen if z["status"] == status]
    zeilen.sort(key=lambda z: (z["hochgeladen"] or "", z["stamm"]), reverse=True)
    return zeilen


@app.get("/")
def seite() -> FileResponse:
    return FileResponse(SEITE, media_type="text/html")


@app.get("/portal")
def portal_seite() -> FileResponse:
    return FileResponse(WURZEL / "portal.html", media_type="text/html")


@app.get("/portal/manifest.json")
def portal_manifest() -> FileResponse:
    return FileResponse(WURZEL / "portal.manifest.json", media_type="application/manifest+json")


@app.get("/portal/sw.js")
def portal_sw() -> FileResponse:
    return FileResponse(WURZEL / "portal.sw.js", media_type="text/javascript")


@app.get("/portal/icon-{groesse}.png")
def portal_icon(groesse: str) -> Response:
    if groesse not in ("192", "512"):
        return JSONResponse({"fehler": "unbekannt"}, status_code=404)
    return FileResponse(WURZEL / f"portal-icon-{groesse}.png", media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------------------------
# Portal-API
# ---------------------------------------------------------------------------

def _api_wache(request: Request) -> tuple[str, None] | tuple[None, JSONResponse]:
    un = angemeldet(request)
    if un is None:
        return None, JSONResponse({"fehler": "nicht angemeldet"}, status_code=401)
    if un not in ERLAUBT:
        return None, JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    return un, None


@app.post("/api/anmelden")
async def api_anmelden(request: Request) -> Response:
    if not _origin_ok(request):
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    un = wer_token(str(body.get("pat", "")).strip())
    if un is None:
        return JSONResponse({"fehler": "Zugangscode ungültig"}, status_code=401)
    if un not in ERLAUBT:
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    exp = int(time.time()) + SESSION_DAUER
    antwort = JSONResponse({"un": un})
    antwort.set_cookie(SESSION_COOKIE, _signieren(un, exp), max_age=SESSION_DAUER,
                       httponly=True, secure=SESSION_SECURE, samesite="lax", path="/")
    return antwort


@app.post("/api/abmelden")
def api_abmelden(request: Request) -> Response:
    antwort = JSONResponse({"ok": True})
    antwort.delete_cookie(SESSION_COOKIE, path="/")
    return antwort


@app.get("/api/ich")
def api_ich(request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    # Gleitende Verlängerung: bei jedem Besuch frisch gesetzt.
    exp = int(time.time()) + SESSION_DAUER
    antwort = JSONResponse({"un": un})
    if request.cookies.get(SESSION_COOKIE):
        antwort.set_cookie(SESSION_COOKIE, _signieren(un, exp), max_age=SESSION_DAUER,
                           httponly=True, secure=SESSION_SECURE, samesite="lax", path="/")
    return antwort


@app.get("/api/belege")
def api_belege(request: Request, monat: str | None = None, status: str | None = None,
               limit: int = 200, seite_nr: int = 1) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    idx = index_aktuell()
    etag = f'"{idx["head"]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    zeilen = _beleg_liste(monat, status)
    gesamt = len(zeilen)
    limit = max(1, min(limit, 500))
    seite_nr = max(1, seite_nr)
    anfang = (seite_nr - 1) * limit
    monate = sorted({z["monat"] for z in idx["belege"].values() if z["monat"]}, reverse=True)
    return JSONResponse({"belege": zeilen[anfang:anfang + limit], "gesamt": gesamt,
                         "monate": monate, "stand": idx["head"]},
                        headers={"ETag": etag})


@app.get("/api/beleg/{stamm}")
def api_beleg(stamm: str, request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if not NAME_RE.match(stamm):
        return JSONResponse({"fehler": "ungültiger Name"}, status_code=400)
    stamm = re.sub(r"\.(jpg|jpeg|png|pdf|heic|xml)$", "", stamm, flags=re.I)
    idx = index_aktuell()
    eintrag = idx["belege"].get(stamm)
    if eintrag is None:
        # Suffix-Match wie /review (die App kennt nur ihren lokalen Namen).
        treffer = [s for s in idx["belege"] if s.endswith("-" + stamm)]
        if len(treffer) == 1:
            stamm = treffer[0]
            eintrag = idx["belege"][stamm]
    if eintrag is None:
        return JSONResponse({"fehler": "unbekannter Beleg"}, status_code=404)

    d: dict = {}
    pfad = review_pfad(stamm)
    if pfad is not None:
        roh = git_show(pfad)
        if roh is not None:
            try:
                d = json.loads(roh)
            except Exception:  # noqa: BLE001
                d = {}
    d["audit"] = {"aufnahme": commit_info(eintrag["datei"]),
                  "review": commit_info(pfad) if pfad else None}
    d["buchungssatz"] = datev_buchungssatz(d) if d else None
    d["status"] = eintrag["status"]
    d["stamm"] = stamm
    d["monat"] = eintrag["monat"]
    d["datei"] = eintrag["datei"]
    d["bild_url"] = f"/api/beleg/{stamm}/bild?v={eintrag['bild_oid']}"
    d["bewirtung_beantwortet"] = eintrag["bewirtung_beantwortet"]
    if eintrag["bewirtung_beantwortet"]:
        roh = git_show(f"review/{stamm}.bewirtung.json")
        if roh is not None:
            try:
                d["bewirtung"] = json.loads(roh)
            except Exception:  # noqa: BLE001
                pass
    return JSONResponse(d)


@app.get("/api/beleg/{stamm}/bild")
def api_beleg_bild(stamm: str, request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if not NAME_RE.match(stamm):
        return JSONResponse({"fehler": "ungültiger Name"}, status_code=400)
    eintrag = index_aktuell()["belege"].get(stamm)
    if eintrag is None:
        return JSONResponse({"fehler": "unbekannter Beleg"}, status_code=404)
    daten = git_show(eintrag["datei"])
    if daten is None:
        return JSONResponse({"fehler": "Lesefehler"}, status_code=500)
    endung = Path(eintrag["datei"]).suffix.lower()
    typ = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
           ".pdf": "application/pdf", ".heic": "image/heic", ".xml": "application/xml"}.get(endung, "application/octet-stream")
    return Response(content=daten, media_type=typ,
                    headers={"Cache-Control": "private, max-age=31536000, immutable"})


def _monat_summen(monat: str) -> dict:
    zeilen = [z for z in index_aktuell()["belege"].values() if z["monat"] == monat]
    arten: dict[str, dict] = {}
    konten: dict[str, dict] = {}
    offen_gesamt: list[dict] = []
    brutto_summe = 0.0
    groesster: dict | None = None
    for z in zeilen:
        if z["brutto"] is not None:
            brutto_summe += z["brutto"]
            art = z["belegart"] or "Sonstiges"
            a = arten.setdefault(art, {"belegart": art, "brutto": 0.0, "netto": 0.0,
                                       "ust": 0.0, "anzahl": 0, "lieferanten": []})
            a["brutto"] += z["brutto"]
            a["netto"] += z["netto"] or 0.0
            a["ust"] += z["ust"] or 0.0
            a["anzahl"] += 1
            if z["lieferant"] and z["lieferant"] not in a["lieferanten"]:
                a["lieferanten"].append(z["lieferant"])
            if z["konto_skr04"]:
                k = konten.setdefault(z["konto_skr04"], {"konto": z["konto_skr04"],
                                                         "brutto": 0.0, "anzahl": 0})
                k["brutto"] += z["brutto"]
                k["anzahl"] += 1
            if groesster is None or z["brutto"] > groesster["brutto"]:
                groesster = {"stamm": z["stamm"], "lieferant": z["lieferant"],
                             "brutto": z["brutto"], "belegart": z["belegart"]}
        if z["status"] in ("nachfrage", "erfasst"):
            offen_gesamt.append({"stamm": z["stamm"], "status": z["status"],
                                 "lieferant": z["lieferant"], "brutto": z["brutto"],
                                 "offen": z["offen"], "bewirtung": z["bewirtung"],
                                 "bewirtung_beantwortet": z["bewirtung_beantwortet"]})
    return {"monat": monat, "anzahl": len(zeilen), "brutto": round(brutto_summe, 2),
            "belegarten": sorted(arten.values(), key=lambda a: -a["brutto"]),
            "konten": sorted(konten.values(), key=lambda k: -k["brutto"]),
            "offene": offen_gesamt, "groesste_position": groesster}


@app.post("/api/bewirtung/{stamm}")
async def api_bewirtung(stamm: str, request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if not NAME_RE.match(stamm):
        return JSONResponse({"fehler": "ungültiger Name"}, status_code=400)
    eintrag = index_aktuell()["belege"].get(stamm)
    if eintrag is None:
        return JSONResponse({"fehler": "unbekannter Beleg"}, status_code=404)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    anlass = str(body.get("anlass", "")).strip()[:200]
    teilnehmer = [str(t).strip()[:80] for t in (body.get("teilnehmer") or []) if str(t).strip()][:20]
    if not anlass or not teilnehmer:
        return JSONResponse({"fehler": "Anlass und Teilnehmer gehören dazu"}, status_code=400)
    inhalt = json.dumps({
        "anlass": anlass,
        "teilnehmer": teilnehmer,
        "beantwortet_von": un,
        "beantwortet_am": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }, ensure_ascii=False, indent=1).encode()
    import boxschreiber  # noqa: PLC0415 — erst beim ersten Schreiben laden
    try:
        commit = boxschreiber.schreiben(f"review/{stamm}.bewirtung.json", inhalt,
                                        f"bewirtung: {stamm}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"}, status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0  # nächster Read sieht den neuen Stand sofort
    return JSONResponse({"ok": True, "commit": commit})


HOCHLADEN_ENDUNGEN = {".jpg", ".jpeg", ".png", ".pdf", ".heic", ".xml"}
HOCHLADEN_MAX = 40 * 1024 * 1024


@app.post("/api/hochladen")
async def api_hochladen(request: Request, name: str = "beleg.jpg") -> Response:
    """Portal-Upload ohne gespeicherten Zugangscode: Cookie-Session + Rohbytes.

    Schreibt den aufnahme:-Commit selbst über das Gateway — :7843 bleibt
    unangetastet, der Watcher findet die Datei wie jede andere.
    """
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    endung = Path(name).suffix.lower()
    if endung not in HOCHLADEN_ENDUNGEN:
        return JSONResponse({"fehler": "kein Beleg-Format"}, status_code=400)
    daten = await request.body()
    if not daten:
        return JSONResponse({"fehler": "leer"}, status_code=400)
    if len(daten) > HOCHLADEN_MAX:
        return JSONResponse({"fehler": "zu groß"}, status_code=413)
    import boxschreiber  # noqa: PLC0415
    dateiname = boxschreiber.beleg_dateiname(name)
    monat = time.strftime("%Y-%m")
    try:
        commit = boxschreiber.schreiben(f"docs/{monat}/{dateiname}", daten,
                                        f"aufnahme: {dateiname}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"}, status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit, "datei": f"docs/{monat}/{dateiname}"})


DOKUMENT_ENDUNGEN = {".pdf", ".jpg", ".jpeg", ".png"}
DOKUMENT_PFAD_RE = re.compile(r"^dokumente/[A-Za-z0-9._/ -]{1,200}$")


@app.get("/api/dokumente")
def api_dokumente(request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    gelesen = db_gelesen(un)
    dokumente = [dict(d, gelesen=d["pfad"] in gelesen)
                 for d in index_aktuell()["dokumente"]]
    return JSONResponse({"dokumente": dokumente,
                         "ungelesen": sum(1 for d in dokumente if not d["gelesen"])})


@app.get("/api/dokument/{pfad:path}")
def api_dokument(pfad: str, request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if not DOKUMENT_PFAD_RE.match(pfad) or ".." in pfad:
        return JSONResponse({"fehler": "ungültiger Pfad"}, status_code=400)
    daten = git_show(pfad)
    if daten is None:
        return JSONResponse({"fehler": "unbekanntes Dokument"}, status_code=404)
    endung = Path(pfad).suffix.lower()
    typ = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
           ".png": "image/png"}.get(endung, "application/octet-stream")
    return Response(content=daten, media_type=typ,
                    headers={"Cache-Control": "private, max-age=3600",
                             "Content-Disposition": f'inline; filename="{Path(pfad).name}"'})


@app.post("/api/dokumente")
async def api_dokument_hochladen(request: Request, name: str = "dokument.pdf",
                                 titel: str = "", art: str = "dokument") -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    endung = Path(name).suffix.lower()
    if endung not in DOKUMENT_ENDUNGEN:
        return JSONResponse({"fehler": "kein Dokument-Format"}, status_code=400)
    daten = await request.body()
    if not daten:
        return JSONResponse({"fehler": "leer"}, status_code=400)
    if len(daten) > HOCHLADEN_MAX:
        return JSONResponse({"fehler": "zu groß"}, status_code=413)
    import boxschreiber  # noqa: PLC0415
    dateiname = boxschreiber.beleg_dateiname(name)
    monat = time.strftime("%Y-%m")
    meta = json.dumps({"titel": (titel or name)[:120], "art": art[:40], "von": un},
                      ensure_ascii=False, indent=1).encode()
    try:
        commit = boxschreiber.schreiben(
            {f"dokumente/{monat}/{dateiname}": daten,
             f"dokumente/{monat}/{dateiname}.meta.json": meta},
            None, f"dokument: {dateiname}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"}, status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit,
                         "pfad": f"dokumente/{monat}/{dateiname}"})


@app.post("/api/dokument-gelesen")
async def api_dokument_gelesen(request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    pfad = str(body.get("pfad", ""))
    if not DOKUMENT_PFAD_RE.match(pfad):
        return JSONResponse({"fehler": "ungültiger Pfad"}, status_code=400)
    db_gelesen_setzen(un, pfad)
    return JSONResponse({"ok": True})


EINSTELLUNG_SCHLUESSEL = {"benachrichtigung_frage", "benachrichtigung_post",
                          "benachrichtigung_abend", "kanzlei_name", "betrieb_name"}


@app.get("/api/einstellungen")
def api_einstellungen(request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    return JSONResponse(db_einstellungen(un))


@app.post("/api/einstellungen")
async def api_einstellungen_setzen(request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    for schluessel, wert in body.items():
        if schluessel in EINSTELLUNG_SCHLUESSEL:
            db_einstellung_setzen(un, schluessel, str(wert)[:200])
    return JSONResponse(db_einstellungen(un))


@app.get("/api/monat/{monat}")
def api_monat(monat: str, request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if not re.match(r"^\d{4}-\d{2}$", monat):
        return JSONResponse({"fehler": "ungültiger Monat"}, status_code=400)
    jahr, mon = int(monat[:4]), int(monat[5:7])
    vor = f"{jahr - 1}-12" if mon == 1 else f"{jahr}-{mon - 1:02d}"
    daten = _monat_summen(monat)
    daten["vormonat"] = _monat_summen(vor)
    return JSONResponse(daten)


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

    # Sprechender Buchungstext: Gemma-Vorschlag, sonst aus Einordnung + Datum +
    # vollem Lieferantennamen zusammengesetzt — „Rotenberger“ allein sagt in
    # drei Monaten niemandem mehr etwas.
    vlm = d.get("vlm") or {}
    text = (vlm.get("buchungstext") or "").strip()
    if not text:
        einordnung = ((d.get("semantik") or {}).get("belegart") or "").strip()
        lieferant = (vlm.get("lieferant") or f.get("lieferant") or "").strip()
        datum_kurz = f"{int(teile[0]):02d}.{int(teile[1]):02d}." if len(teile) == 3 else ""
        text = " ".join(x for x in (einordnung, datum_kurz, lieferant) if x)
    return {
        "umsatz": f"{brutto:.2f}".replace(".", ","),
        "soll_haben": "S",
        "konto": konto,
        "gegenkonto": "70099",
        "bu_schluessel": e.get("steuerschluessel"),
        "belegdatum": belegdatum,
        "belegfeld1": belegfeld1,
        "buchungstext": text[:60] or None,
    }


def belegdaten_kontext(max_zeichen: int = 12000) -> str:
    """Kompakte Zusammenfassung aller Reviews als Chat-Kontext (neueste zuerst).

    Liest aus dem Index (ein rev-parse im warmen Fall) — Textformat unverändert.
    """
    reviews = index_aktuell()["reviews"]
    bloecke: list[str] = []
    laenge = 0
    for stamm in sorted(reviews, reverse=True):
        d = reviews[stamm]
        name = f"{stamm}.json"
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
    un = angemeldet(request)   # Cookie (Portal) ODER Bearer (App) — Wire-Format unverändert
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
