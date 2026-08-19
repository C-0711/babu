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
    conn.execute("""CREATE TABLE IF NOT EXISTS registrierungen
        (id INTEGER PRIMARY KEY AUTOINCREMENT, zeit TEXT NOT NULL,
         daten TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'neu')""")
    conn.execute("""CREATE TABLE IF NOT EXISTS nutzer
        (email TEXT PRIMARY KEY, name TEXT, salon TEXT,
         rolle TEXT NOT NULL DEFAULT 'salon', pw TEXT NOT NULL,
         aktiv INTEGER NOT NULL DEFAULT 1,
         angelegt TEXT, letzter_login TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS abschluss_status
        (un TEXT PRIMARY KEY, jahr INTEGER, json TEXT NOT NULL,
         zeit TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS app_schluessel
        (hash TEXT PRIMARY KEY, un TEXT NOT NULL, geraet TEXT,
         erstellt TEXT NOT NULL, zuletzt TEXT)""")
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

# Betriebs-Zähler (KPI, in-memory seit Prozessstart)
_METRIK = {"start": time.time(), "requests": 0, "fehler_5xx": 0, "davon_304": 0,
           "dauer_summe": 0.0}


@app.middleware("http")
async def _metrik_mw(request: Request, call_next):
    # Tippfehler-Toleranz: //portal → /portal (308 behält die Methode bei)
    pfad = request.url.path
    if "//" in pfad:
        sauber = re.sub(r"/{2,}", "/", pfad)
        from fastapi.responses import RedirectResponse  # noqa: PLC0415
        return RedirectResponse(url=sauber + (("?" + request.url.query) if request.url.query else ""),
                                status_code=308)
    t0 = time.perf_counter()
    antwort = await call_next(request)
    _METRIK["requests"] += 1
    _METRIK["dauer_summe"] += time.perf_counter() - t0
    if antwort.status_code >= 500:
        _METRIK["fehler_5xx"] += 1
    if antwort.status_code == 304:
        _METRIK["davon_304"] += 1
    return antwort

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


def app_schluessel_pruefen(token: str) -> str | None:
    """Geräteschlüssel der App (bei der Konto-Anmeldung erzeugt): Hash-Lookup,
    nur für aktive Konten. Nebenläufig günstig — kein Netz, eine SQLite-Zeile."""
    if not token:
        return None
    h = hashlib.sha256(token.encode()).hexdigest()
    with _DB_LOCK, _db() as c:
        zeile = c.execute("""SELECT s.un FROM app_schluessel s
            JOIN nutzer n ON n.email = s.un
            WHERE s.hash=? AND n.aktiv=1""", (h,)).fetchone()
        if not zeile:
            return None
        c.execute("UPDATE app_schluessel SET zuletzt=? WHERE hash=?",
                  (_jetzt_iso(), h))
    return zeile[0]


def wer(request: Request) -> str | None:
    hdr = request.headers.get("authorization", "")
    if not hdr.lower().startswith("bearer "):
        return None
    token = hdr[7:].strip()
    # Erst der eigene Geräteschlüssel (Konto-Anmeldung), dann der PAT-Weg.
    un = app_schluessel_pruefen(token)
    return un or wer_token(token)


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


# ---------------------------------------------------------------------------
# Eigene Nutzerkonten (E-Mail + Passwort) mit Rollen — zusätzlich zum
# PAT-Weg (App/Einrichtung). Passwörter als scrypt (stdlib); Startpasswörter
# erscheinen GENAU EINMAL in der API-Antwort (kein Mailversand vorhanden,
# Übergabe persönlich) und nie in Logs.
# ---------------------------------------------------------------------------

NUTZER_ROLLEN = ("admin", "kanzlei", "salon")


def pw_hash(passwort: str) -> str:
    salz = secrets.token_bytes(16)
    h = hashlib.scrypt(passwort.encode(), salt=salz, n=16384, r=8, p=1)
    return f"scrypt${salz.hex()}${h.hex()}"


def pw_pruefen(passwort: str, gespeichert: str) -> bool:
    try:
        art, salz_hex, hash_hex = gespeichert.split("$", 2)
        if art != "scrypt":
            return False
        h = hashlib.scrypt(passwort.encode(), salt=bytes.fromhex(salz_hex),
                           n=16384, r=8, p=1)
        return hmac.compare_digest(h.hex(), hash_hex)
    except Exception:  # noqa: BLE001
        return False


def startpasswort() -> str:
    """Lesbar, ohne verwechselbare Zeichen — wird persönlich weitergegeben."""
    zeichen = "abcdefghjkmnpqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(zeichen) for _ in range(4))
                    for _ in range(2))


def _jetzt_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def nutzer_holen(email: str) -> dict | None:
    with _DB_LOCK, _db() as c:
        z = c.execute("""SELECT email, name, salon, rolle, pw, aktiv, angelegt,
                         letzter_login FROM nutzer WHERE email=?""",
                      (email.strip().lower(),)).fetchone()
    if not z:
        return None
    return {"email": z[0], "name": z[1], "salon": z[2], "rolle": z[3], "pw": z[4],
            "aktiv": bool(z[5]), "angelegt": z[6], "letzter_login": z[7]}


def nutzer_anlegen(email: str, name: str, salon: str, rolle_neu: str,
                   passwort: str | None = None) -> str | None:
    """Legt ein Konto an und gibt das Passwort zurück (None = existiert schon).
    Ohne `passwort` wird ein Startpasswort generiert (Verwaltungs-Weg)."""
    email = email.strip().lower()
    if nutzer_holen(email):
        return None
    passwort = passwort or startpasswort()
    with _DB_LOCK, _db() as c:
        c.execute("""INSERT INTO nutzer (email, name, salon, rolle, pw, aktiv, angelegt)
                     VALUES (?,?,?,?,?,1,?)""",
                  (email, name.strip()[:120], salon.strip()[:120],
                   rolle_neu if rolle_neu in NUTZER_ROLLEN else "salon",
                   pw_hash(passwort), _jetzt_iso()))
    return passwort


def zugelassen(un: str) -> bool:
    """PAT-Allowlist ODER aktives eigenes Konto."""
    if un in ERLAUBT:
        return True
    n = nutzer_holen(un)
    return bool(n and n["aktiv"])


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
                "dokumente": [], "freigaben": {}, "umsaetze": {},
                "zeiten": {}, "oid_cache": {}}


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
                    and not p.endswith(".bewirtung.json")
                    and not p.endswith(".korrektur.json")}
    korrektur_pfade = {p[len("review/"):-len(".korrektur.json")]: oid
                       for p, oid in pfade.items() if p.endswith(".korrektur.json")}
    bewirtung_staemme = {p[len("review/"):-len(".bewirtung.json")]
                         for p in pfade if p.endswith(".bewirtung.json")}
    beleg_pfade = [p for p in pfade
                   if p.startswith("docs/") and Path(p).suffix.lower() in BELEG_ENDUNGEN]

    oid_cache = _INDEX["oid_cache"]
    fehlend = [oid for oid in list(review_pfade.values()) + list(korrektur_pfade.values())
               if oid not in oid_cache]
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
            # Vorsicht: Stub-Reviews haben "semantik": null — get-Default greift
            # nur bei FEHLENDEM Schlüssel, deshalb das `or {}`.
            "belegart": ((review.get("semantik") or {}).get("belegart")) if review else None,
            "dokumentklasse": (review or {}).get("dokumentklasse") if review else None,
            "konto_skr04": e.get("konto_skr04"),
            "steuerschluessel": e.get("steuerschluessel"),
            "buchungstext": (datev_buchungssatz(review) or {}).get("buchungstext") if review else None,
            "offen": list(f.get("offen") or []),
            "summenprobe_ok": f.get("summenprobe_ok"),
            "bewirtung": bool(f.get("bewirtungssignal")),
            "bewirtung_beantwortet": bewirtung_da,
        }
        korrektur = oid_cache.get(korrektur_pfade.get(stamm, ""))
        if isinstance(korrektur, dict):
            eintrag["korrigiert"] = True
            for kk in ("konto_skr04", "steuerschluessel", "buchungstext"):
                if korrektur.get(kk):
                    eintrag[kk] = korrektur[kk]
            if review is not None:
                review = json.loads(json.dumps(review))  # Kopie, Original bleibt
                review.setdefault("einschaetzung", {})
                for kk in ("konto_skr04", "steuerschluessel"):
                    if korrektur.get(kk):
                        review["einschaetzung"][kk] = korrektur[kk]
                if korrektur.get("buchungstext"):
                    review.setdefault("vlm", {})
                    (review["vlm"] or {}).update(buchungstext=korrektur["buchungstext"])
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
    erklaerung_pfade = {p_: oid for p_, oid in pfade.items()
                        if p_.startswith("dokumente/") and p_.endswith(".erklaerung.json")}
    fehlend_erkl = [oid for oid in erklaerung_pfade.values() if oid not in oid_cache]
    for oid, roh in _blobs_lesen(fehlend_erkl).items():
        try:
            oid_cache[oid] = json.loads(roh)
        except Exception:  # noqa: BLE001
            oid_cache[oid] = None
    dokumente: list[dict] = []
    for pfad, oid in pfade.items():
        if not pfad.startswith("dokumente/") or pfad.endswith(".meta.json") \
                or pfad.endswith(".erklaerung.json"):
            continue
        meta = oid_cache.get(meta_pfade.get(pfad + ".meta.json", "")) or {}
        erklaerung = oid_cache.get(erklaerung_pfade.get(pfad + ".erklaerung.json", ""))
        name = pfad.rsplit("/", 1)[-1]
        dokumente.append({
            "pfad": pfad,
            "name": name,
            "titel": (meta.get("titel") or name) if isinstance(meta, dict) else name,
            "art": (meta.get("art") or "dokument") if isinstance(meta, dict) else "dokument",
            "erklaerung": erklaerung if isinstance(erklaerung, dict) else None,
            "von": (zeiten.get(pfad) or {}).get("autor"),
            "zeit": (zeiten.get(pfad) or {}).get("zeit"),
        })
    dokumente.sort(key=lambda d_: d_["zeit"] or "", reverse=True)
    _INDEX["dokumente"] = dokumente

    # Kontoauszüge: auszuege/<monat>/<name>.umsaetze.json sammeln
    umsatz_pfade = {p_: oid for p_, oid in pfade.items()
                    if p_.startswith("auszuege/") and p_.endswith(".umsaetze.json")}
    fehlend_um = [oid for oid in umsatz_pfade.values() if oid not in oid_cache]
    for oid, roh in _blobs_lesen(fehlend_um).items():
        try:
            oid_cache[oid] = json.loads(roh)
        except Exception:  # noqa: BLE001
            oid_cache[oid] = None
    umsaetze: dict[str, list] = {}
    for p_, oid in umsatz_pfade.items():
        d_ = oid_cache.get(oid)
        if isinstance(d_, dict) and d_.get("monat"):
            umsaetze.setdefault(d_["monat"], []).extend(d_.get("umsaetze") or [])
    _INDEX["umsaetze"] = umsaetze

    # Exportierte Belege: export/<monat>/stapel.json sammeln
    export_pfade = {p_: oid for p_, oid in pfade.items()
                    if p_.startswith("export/") and p_.endswith("stapel.json")}
    fehlend_exp = [oid for oid in export_pfade.values() if oid not in oid_cache]
    for oid, roh in _blobs_lesen(fehlend_exp).items():
        try:
            oid_cache[oid] = json.loads(roh)
        except Exception:  # noqa: BLE001
            oid_cache[oid] = None
    freigabe_pfade = {p_: oid for p_, oid in pfade.items()
                      if p_.startswith("freigaben/") and p_.endswith(".json")}
    fehlend_fg = [oid for oid in freigabe_pfade.values() if oid not in oid_cache]
    for oid, roh in _blobs_lesen(fehlend_fg).items():
        try:
            oid_cache[oid] = json.loads(roh)
        except Exception:  # noqa: BLE001
            oid_cache[oid] = None
    freigaben: dict[str, dict] = {}
    for p_, oid in freigabe_pfade.items():
        d_ = oid_cache.get(oid)
        if isinstance(d_, dict) and d_.get("dokument"):
            freigaben[d_["dokument"]] = {"von": d_.get("von"), "am": d_.get("am")}
    for eintrag_ in dokumente:
        if eintrag_["art"] == "freigabe_anfrage":
            eintrag_["freigabe"] = freigaben.get(eintrag_["pfad"])
    _INDEX["freigaben"] = freigaben

    exportiert: set[str] = set()
    for oid in export_pfade.values():
        d_ = oid_cache.get(oid)
        if isinstance(d_, dict):
            exportiert.update(d_.get("staemme") or [])
    for stamm_, z_ in belege.items():
        if stamm_ in exportiert and z_["status"] == "geprüft":
            z_["status"] = "exportiert"

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


# HTML immer revalidieren lassen: ohne Cache-Control nutzen Browser die
# Heuristik und zeigen nach einem Deploy stundenlang die alte Seite.
HTML_FRISCH = {"Cache-Control": "no-cache"}


@app.get("/")
def seite() -> FileResponse:
    return FileResponse(SEITE, media_type="text/html", headers=HTML_FRISCH)


@app.get("/portal")
def portal_seite() -> FileResponse:
    return FileResponse(WURZEL / "portal.html", media_type="text/html", headers=HTML_FRISCH)


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


# Statik für Landing-Bilder und den App-Download — feste Ordner neben der
# Startseite (~/babu-web/), strikte Namens-Allowlists, kein Pfad-Traversal.
BILDER_ORDNER = SEITE.parent / "bilder"
APP_ORDNER = SEITE.parent / "app"
APP_DATEIEN = {
    "babu.ipa": "application/octet-stream",
    "manifest.plist": "application/xml",
    "icon.png": "image/png",
}


@app.get("/bilder/{name}")
def landing_bild(name: str) -> Response:
    m = re.fullmatch(r"[a-z0-9-]{1,40}\.(png|jpg|mp4)", name)
    if not m:
        return JSONResponse({"fehler": "unbekannt"}, status_code=404)
    pfad = BILDER_ORDNER / name
    if not pfad.is_file():
        return JSONResponse({"fehler": "unbekannt"}, status_code=404)
    typ = {"png": "image/png", "jpg": "image/jpeg", "mp4": "video/mp4"}[m.group(1)]
    return FileResponse(pfad, media_type=typ,
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/app")
def app_seite() -> Response:
    pfad = APP_ORDNER / "index.html"
    if not pfad.is_file():
        return JSONResponse({"fehler": "kommt bald"}, status_code=404)
    return FileResponse(pfad, media_type="text/html", headers=HTML_FRISCH)


@app.get("/app/{name}")
def app_datei(name: str) -> Response:
    if name not in APP_DATEIEN:
        return JSONResponse({"fehler": "unbekannt"}, status_code=404)
    pfad = APP_ORDNER / name
    if not pfad.is_file():
        return JSONResponse({"fehler": "kommt bald"}, status_code=404)
    return FileResponse(pfad, media_type=APP_DATEIEN[name])


# ---------------------------------------------------------------------------
# Portal-API
# ---------------------------------------------------------------------------

def _api_wache(request: Request) -> tuple[str, None] | tuple[None, JSONResponse]:
    un = angemeldet(request)
    if un is None:
        return None, JSONResponse({"fehler": "nicht angemeldet"}, status_code=401)
    if not zugelassen(un):
        print(f"[wache] 403: '{un}' weder Allowlist noch aktives Konto", flush=True)
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


# Login mit eigenem Konto (E-Mail + Passwort) — gleiche Session wie der
# Zugangscode-Weg. Fehlermeldung immer generisch, Rate-Limit je IP.
_LOGIN_VERSUCHE: dict[str, list[float]] = {}


@app.post("/api/login")
def api_login(body: dict, request: Request) -> Response:
    if not _origin_ok(request):
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    ip = request.client.host if request.client else "?"
    jetzt = time.time()
    versuche = [t for t in _LOGIN_VERSUCHE.get(ip, []) if jetzt - t < 60]
    if len(versuche) >= 5:
        _LOGIN_VERSUCHE[ip] = versuche
        return JSONResponse({"fehler": "Zu viele Versuche — bitte eine Minute warten."},
                            status_code=429)
    versuche.append(jetzt)
    _LOGIN_VERSUCHE[ip] = versuche
    email = str(body.get("email", "")).strip().lower()
    passwort = str(body.get("passwort", ""))
    n = nutzer_holen(email) if email else None
    if not n or not n["aktiv"] or not pw_pruefen(passwort, n["pw"]):
        return JSONResponse({"fehler": "E-Mail oder Passwort stimmt nicht."},
                            status_code=401)
    with _DB_LOCK, _db() as c:
        c.execute("UPDATE nutzer SET letzter_login=? WHERE email=?",
                  (_jetzt_iso(), email))
    exp = int(time.time()) + SESSION_DAUER
    antwort = JSONResponse({"un": email, "rolle": n["rolle"]})
    antwort.set_cookie(SESSION_COOKIE, _signieren(email, exp), max_age=SESSION_DAUER,
                       httponly=True, secure=SESSION_SECURE, samesite="lax", path="/")
    return antwort


@app.post("/api/app-anmelden")
def api_app_anmelden(body: dict, request: Request) -> Response:
    """Die App verbindet sich mit dem ganz normalen Konto (E-Mail + Passwort).
    Dabei entsteht unsichtbar ein Geräteschlüssel — er erscheint GENAU EINMAL
    in der Antwort, gespeichert wird nur sein Hash. Kein Schlüssel-Gefrickel
    mehr für die Nutzerin."""
    ip = request.client.host if request.client else "?"
    jetzt = time.time()
    versuche = [t for t in _LOGIN_VERSUCHE.get(ip, []) if jetzt - t < 60]
    if len(versuche) >= 5:
        _LOGIN_VERSUCHE[ip] = versuche
        return JSONResponse({"fehler": "Zu viele Versuche — bitte eine Minute warten."},
                            status_code=429)
    versuche.append(jetzt)
    _LOGIN_VERSUCHE[ip] = versuche
    email = str(body.get("email", "")).strip().lower()
    passwort = str(body.get("passwort", ""))
    geraet = str(body.get("geraet", "") or "")[:80]
    n = nutzer_holen(email) if email else None
    if not n or not n["aktiv"] or not pw_pruefen(passwort, n["pw"]):
        return JSONResponse({"fehler": "E-Mail oder Passwort stimmt nicht."},
                            status_code=401)
    token = secrets.token_urlsafe(32)
    with _DB_LOCK, _db() as c:
        c.execute("INSERT INTO app_schluessel VALUES (?,?,?,?,?)",
                  (hashlib.sha256(token.encode()).hexdigest(), email, geraet,
                   _jetzt_iso(), None))
        c.execute("UPDATE nutzer SET letzter_login=? WHERE email=?",
                  (_jetzt_iso(), email))
    print(f"[app] Gerät verbunden: {email} ({geraet or 'ohne Namen'})", flush=True)
    return JSONResponse({"schluessel": token, "un": email, "rolle": n["rolle"]})


@app.post("/api/passwort")
async def api_passwort(request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    n = nutzer_holen(un)
    if not n:
        return JSONResponse({"fehler": "Dein Zugang hat kein Passwort — er läuft über den Zugangscode."},
                            status_code=400)
    if not pw_pruefen(str(body.get("alt", "")), n["pw"]):
        return JSONResponse({"fehler": "Das bisherige Passwort stimmt nicht."}, status_code=401)
    neu = str(body.get("neu", ""))
    if len(neu) < 8:
        return JSONResponse({"fehler": "Mindestens 8 Zeichen, bitte."}, status_code=400)
    with _DB_LOCK, _db() as c:
        c.execute("UPDATE nutzer SET pw=? WHERE email=?", (pw_hash(neu), un))
    return JSONResponse({"ok": True})


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
    antwort = JSONResponse({"un": un, "rolle": rolle(un)})
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


@app.post("/ablage")
async def ablage(request: Request) -> Response:
    """Beleg-Eingang, vertragsgleich zum bisherigen :7843-Eingang — aber über
    boxschreiber (frischer fetch+reset vor jedem Push, ein Retry). Grund:
    der alte Eingang blieb nach Fremd-Commits (Watcher-Reviews!) dauerhaft
    auf 502, weil sein Retry die abgeschnittene Git-Meldung nicht erkennt.

    Wire-Format der App: multipart Feld "file" (+ optional "notiz"),
    Antwort {ok, ref, commit, datei}; txt → 400 (Verbindungstest-Semantik).
    """
    un = angemeldet(request)   # App schickt Bearer; Portal-Cookie geht auch
    if un is None:
        return JSONResponse({"fehler": "Token fehlt oder ungültig"}, status_code=401)
    if un not in ERLAUBT:
        print(f"[ablage] 403: '{un}' nicht in BABU_ERLAUBT", flush=True)
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "multipart erwartet"}, status_code=400)
    datei = form.get("file")
    if datei is None or not getattr(datei, "filename", None):
        return JSONResponse({"fehler": "file fehlt"}, status_code=422)
    name = datei.filename
    if Path(name).suffix.lower() not in HOCHLADEN_ENDUNGEN:
        return JSONResponse({"fehler": "kein Beleg-Format"}, status_code=400)
    daten = await datei.read()
    if not daten:
        return JSONResponse({"fehler": "leer"}, status_code=400)
    if len(daten) > HOCHLADEN_MAX:
        return JSONResponse({"fehler": "zu groß"}, status_code=413)
    notiz = str(form.get("notiz") or "").strip()[:200]
    import boxschreiber  # noqa: PLC0415
    dateiname = boxschreiber.beleg_dateiname(name)
    monat = time.strftime("%Y-%m")
    nachricht = f"aufnahme: {dateiname}" + (f"\n\n{notiz}" if notiz else "")
    try:
        commit = boxschreiber.schreiben(f"docs/{monat}/{dateiname}", daten,
                                        nachricht, un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "Push fehlgeschlagen"}, status_code=502)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True,
                         "ref": os.environ.get("BABU_REF",
                                               "inspektor/ws-christoph0711.io/babu"),
                         "commit": commit, "datei": f"docs/{monat}/{dateiname}"})


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
    if art[:40] == "behoerde":
        # Brief vom Amt: im Hintergrund lesen und einfach erklären.
        threading.Thread(target=_brief_job,
                         args=(f"dokumente/{monat}/{dateiname}", daten, name, un),
                         daemon=True).start()
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


@app.get("/workbench")
def workbench_seite() -> FileResponse:
    return FileResponse(WURZEL / "workbench.html", media_type="text/html")


@app.post("/api/korrektur/{stamm}")
async def api_korrektur(stamm: str, request: Request) -> Response:
    """Kanzlei-Korrektur (Konto/BU/Buchungstext) — als eigener Commit, damit
    Autorenschaft und Historie sauber bleiben; fließt in Liste + EXTF ein."""
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if not darf_verwalten(un):
        return JSONResponse({"fehler": "nur für die Kanzlei"}, status_code=403)
    if not NAME_RE.match(stamm):
        return JSONResponse({"fehler": "ungültiger Name"}, status_code=400)
    if stamm not in index_aktuell()["belege"]:
        return JSONResponse({"fehler": "unbekannter Beleg"}, status_code=404)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    konto = str(body.get("konto_skr04", "")).strip()
    if konto and not re.match(r"^\d{4,8}$", konto):
        return JSONResponse({"fehler": "Konto prüfen"}, status_code=400)
    daten = {"konto_skr04": konto or None,
             "steuerschluessel": str(body.get("steuerschluessel", "")).strip()[:2] or None,
             "buchungstext": str(body.get("buchungstext", "")).strip()[:60] or None,
             "von": un, "am": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    import boxschreiber  # noqa: PLC0415
    try:
        commit = boxschreiber.schreiben(
            f"review/{stamm}.korrektur.json",
            json.dumps(daten, ensure_ascii=False, indent=1).encode(),
            f"korrektur: {stamm}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit})


@app.post("/api/kontoauszug")
async def api_kontoauszug(request: Request, name: str = "auszug.pdf") -> Response:
    """Kontoauszug (Text-PDF) ablegen: Umsätze werden sofort gelesen und für
    den Zahlungsabgleich gespeichert."""
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if Path(name).suffix.lower() != ".pdf":
        return JSONResponse({"fehler": "bitte als PDF"}, status_code=400)
    daten = await request.body()
    if not daten:
        return JSONResponse({"fehler": "leer"}, status_code=400)
    if len(daten) > HOCHLADEN_MAX:
        return JSONResponse({"fehler": "zu groß"}, status_code=413)
    import tempfile
    import kontoauszug as ka  # noqa: PLC0415
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tf:
        tf.write(daten)
        tf.flush()
        try:
            geparst = ka.parse_pdf(tf.name)
        except Exception:  # noqa: BLE001
            geparst = {"umsaetze": [], "monat": None, "konto": None}
    if not geparst["umsaetze"] or not geparst["monat"]:
        return JSONResponse({"fehler": "Diesen Auszug konnte ich nicht lesen — "
                             "ist es das Original-PDF der Bank?"}, status_code=422)
    import boxschreiber  # noqa: PLC0415
    dateiname = boxschreiber.beleg_dateiname(name)
    monat = geparst["monat"]
    try:
        commit = boxschreiber.schreiben(
            {f"auszuege/{monat}/{dateiname}": daten,
             f"auszuege/{monat}/{dateiname}.umsaetze.json": json.dumps(
                 geparst, ensure_ascii=False, indent=1).encode()},
            None, f"auszug: {dateiname}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit, "monat": monat,
                         "umsaetze": len(geparst["umsaetze"])})


@app.get("/api/abgleich/{monat}")
def api_abgleich(monat: str, request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if not re.match(r"^\d{4}-\d{2}$", monat):
        return JSONResponse({"fehler": "ungültiger Monat"}, status_code=400)
    import kontoauszug as ka  # noqa: PLC0415
    idx = index_aktuell()
    umsaetze = idx["umsaetze"].get(monat, [])
    if not umsaetze:
        return JSONResponse({"monat": monat, "auszug_da": False})
    ergebnis = ka.abgleich(umsaetze, list(idx["belege"].values()))
    ergebnis["monat"] = monat
    ergebnis["auszug_da"] = True
    return JSONResponse(ergebnis)


@app.post("/api/freigabe")
async def api_freigabe(request: Request) -> Response:
    """Freigabe einer Kanzlei-Anfrage — protokollierte Portal-Handlung
    (auditpflichtig, daher Commit in der Box, nicht SQLite)."""
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    pfad = str(body.get("pfad", ""))
    idx = index_aktuell()
    dok = next((d_ for d_ in idx["dokumente"] if d_["pfad"] == pfad), None)
    if dok is None or dok["art"] != "freigabe_anfrage":
        return JSONResponse({"fehler": "keine Freigabe-Anfrage"}, status_code=400)
    if idx["freigaben"].get(pfad):
        return JSONResponse({"ok": True, "schon": True})
    name = Path(pfad).name
    inhalt = json.dumps({"dokument": pfad, "antwort": "freigegeben", "von": un,
                         "am": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
                        ensure_ascii=False, indent=1).encode()
    import boxschreiber  # noqa: PLC0415
    try:
        commit = boxschreiber.schreiben(f"freigaben/{name}.json", inhalt,
                                        f"freigabe: {name}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit})


EINSTELLUNG_SCHLUESSEL = {"benachrichtigung_frage", "benachrichtigung_post",
                          "benachrichtigung_abend", "kanzlei_name", "betrieb_name",
                          # Einrichtung/Steuerdaten (Onboarding nach dem ersten Login)
                          "rechtsform", "steuernummer", "finanzamt",
                          "kleinunternehmer", "steuerberater_status",
                          "telefon", "email",
                          # Paket-Einstufung (Fragebogen/Salon-Check)
                          "ust_befreiung_medizinisch", "steuerberater_modus",
                          "filialen", "mehrere_unternehmen", "abschluss_art"}


# Registrierung: Interessentinnen hinterlassen alle Daten — der Zugang wird
# danach persönlich eingerichtet (Allowlist bleibt der Schalter). Ohne Auth,
# aber Origin-Check, einfaches Rate-Limit je IP und strikte Feld-Whitelist.
REG_FELDER = ("salon", "name", "email", "telefon", "rechtsform", "steuernummer",
              "finanzamt", "kleinunternehmer", "steuerberater", "nachricht")
_REG_ZULETZT: dict[str, float] = {}


@app.post("/api/registrierung")
def api_registrierung(daten: dict, request: Request) -> Response:
    if not _origin_ok(request):
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    ip = request.client.host if request.client else "?"
    jetzt = time.time()
    if jetzt - _REG_ZULETZT.get(ip, 0.0) < 30:
        return JSONResponse({"fehler": "kurz warten, dann nochmal"}, status_code=429)
    sauber = {k: str(daten.get(k, "") or "")[:200].strip() for k in REG_FELDER}
    if not sauber["salon"] or "@" not in sauber["email"]:
        return JSONResponse({"fehler": "Salon-Name und E-Mail brauchen wir mindestens"},
                            status_code=400)
    _REG_ZULETZT[ip] = jetzt
    with _DB_LOCK, _db() as c:
        c.execute("INSERT INTO registrierungen (zeit, daten) VALUES (?, ?)",
                  (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   json.dumps(sauber, ensure_ascii=False)))
    print(f"[registrierung] {sauber['salon']} <{sauber['email']}>", flush=True)
    return JSONResponse({"ok": True})


@app.post("/api/signup")
def api_signup(daten: dict, request: Request) -> Response:
    """Ganz normales Self-Signup: Konto mit eigenem Passwort, sofort angemeldet.
    Steuerdaten aus der Strecke landen direkt in den Einstellungen; die
    Verwaltung sieht den Neuzugang in der Anfragen-Historie."""
    if not _origin_ok(request):
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    ip = request.client.host if request.client else "?"
    jetzt = time.time()
    if jetzt - _REG_ZULETZT.get(ip, 0.0) < 30:
        return JSONResponse({"fehler": "kurz warten, dann nochmal"}, status_code=429)
    sauber = {k: str(daten.get(k, "") or "")[:200].strip() for k in REG_FELDER}
    passwort = str(daten.get("passwort", "") or "")
    if not sauber["salon"] or "@" not in sauber["email"]:
        return JSONResponse({"fehler": "Salon-Name und E-Mail brauchen wir mindestens"},
                            status_code=400)
    if len(passwort) < 8:
        return JSONResponse({"fehler": "Das Passwort braucht mindestens 8 Zeichen."},
                            status_code=400)
    email = sauber["email"].lower()
    if nutzer_anlegen(email, sauber["name"], sauber["salon"], "salon",
                      passwort=passwort) is None:
        return JSONResponse({"fehler": "Für diese E-Mail gibt es schon einen Zugang — melde dich einfach an."},
                            status_code=409)
    _REG_ZULETZT[ip] = jetzt
    vorbelegung = {"betrieb_name": sauber["salon"], "rechtsform": sauber["rechtsform"],
                   "steuernummer": sauber["steuernummer"], "finanzamt": sauber["finanzamt"],
                   "kleinunternehmer": sauber["kleinunternehmer"],
                   "steuerberater_status": sauber["steuerberater"],
                   "telefon": sauber["telefon"], "email": email}
    for schluessel, wert in vorbelegung.items():
        if wert:
            db_einstellung_setzen(email, schluessel, str(wert)[:200])
    with _DB_LOCK, _db() as c:
        c.execute("INSERT INTO registrierungen (zeit, daten, status) VALUES (?, ?, 'selbst registriert')",
                  (_jetzt_iso(), json.dumps(sauber, ensure_ascii=False)))
    print(f"[signup] {sauber['salon']} <{email}>", flush=True)
    exp = int(time.time()) + SESSION_DAUER
    antwort = JSONResponse({"un": email, "rolle": "salon"})
    antwort.set_cookie(SESSION_COOKIE, _signieren(email, exp), max_age=SESSION_DAUER,
                       httponly=True, secure=SESSION_SECURE, samesite="lax", path="/")
    return antwort


@app.get("/api/registrierungen")
def api_registrierungen(request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if not darf_verwalten(un):
        return JSONResponse({"fehler": "nur für die Kanzlei"}, status_code=403)
    with _DB_LOCK, _db() as c:
        zeilen = [{"id": z[0], "zeit": z[1], "status": z[3], **json.loads(z[2])}
                  for z in c.execute(
                      "SELECT id, zeit, daten, status FROM registrierungen ORDER BY id DESC")]
    return JSONResponse({"registrierungen": zeilen})


def _einstellungen_mit_paket(un: str) -> dict:
    import saloncheck  # noqa: PLC0415
    e = db_einstellungen(un)
    e["paket_empfehlung"] = saloncheck.paket_empfehlung(e)
    return e


@app.get("/api/einstellungen")
def api_einstellungen(request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    return JSONResponse(_einstellungen_mit_paket(un))


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
    return JSONResponse(_einstellungen_mit_paket(un))


ROLLEN = {t.split(":")[0].strip().lower(): t.split(":")[1].strip().lower()
          for t in os.environ.get("BABU_ROLLEN", "").split(",") if ":" in t}


def rolle(un: str) -> str:
    n = nutzer_holen(un)
    if n:
        return n["rolle"]
    return ROLLEN.get(un, "kanzlei" if not ROLLEN else "salon")


def darf_verwalten(un: str) -> bool:
    return rolle(un) in ("admin", "kanzlei")


def _verwalter_wache(request: Request):
    un, fehler = _api_wache(request)
    if fehler:
        return None, fehler
    if not darf_verwalten(un):
        return None, JSONResponse({"fehler": "nur für die Verwaltung"}, status_code=403)
    return un, None


# ---------------------------------------------------------------------------
# Verwaltung: Nutzer anlegen/ändern, Registrierungs-Anfragen einrichten.
# ---------------------------------------------------------------------------

@app.get("/api/nutzer")
def api_nutzer_liste(request: Request) -> Response:
    un, fehler = _verwalter_wache(request)
    if fehler:
        return fehler
    with _DB_LOCK, _db() as c:
        zeilen = [{"email": z[0], "name": z[1], "salon": z[2], "rolle": z[3],
                   "aktiv": bool(z[4]), "angelegt": z[5], "letzter_login": z[6]}
                  for z in c.execute("""SELECT email, name, salon, rolle, aktiv,
                      angelegt, letzter_login FROM nutzer ORDER BY angelegt DESC""")]
    import saloncheck  # noqa: PLC0415
    for z in zeilen:
        z["paket"] = saloncheck.paket_empfehlung(db_einstellungen(z["email"]))["name"]
    return JSONResponse({"nutzer": zeilen})


@app.post("/api/nutzer")
async def api_nutzer_anlegen(request: Request) -> Response:
    un, fehler = _verwalter_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    email = str(body.get("email", "")).strip().lower()
    if "@" not in email:
        return JSONResponse({"fehler": "Das sieht nicht nach einer E-Mail aus."}, status_code=400)
    passwort = nutzer_anlegen(email, str(body.get("name", "")),
                              str(body.get("salon", "")), str(body.get("rolle", "salon")))
    if passwort is None:
        return JSONResponse({"fehler": "Für diese E-Mail gibt es schon einen Zugang."},
                            status_code=409)
    return JSONResponse({"ok": True, "email": email, "startpasswort": passwort})


@app.post("/api/nutzer-aktion")
async def api_nutzer_aktion(request: Request) -> Response:
    un, fehler = _verwalter_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    email = str(body.get("email", "")).strip().lower()
    aktion = str(body.get("aktion", ""))
    if not nutzer_holen(email):
        return JSONResponse({"fehler": "Diesen Zugang gibt es nicht."}, status_code=404)
    # Selbstschutz: das eigene Konto weder abschalten noch zurückstufen.
    if email == un and aktion in ("deaktivieren", "rolle"):
        return JSONResponse({"fehler": "Das eigene Konto kannst du hier nicht ändern."},
                            status_code=400)
    if aktion == "deaktivieren":
        with _DB_LOCK, _db() as c:
            c.execute("UPDATE nutzer SET aktiv=0 WHERE email=?", (email,))
    elif aktion == "aktivieren":
        with _DB_LOCK, _db() as c:
            c.execute("UPDATE nutzer SET aktiv=1 WHERE email=?", (email,))
    elif aktion == "rolle":
        neu = str(body.get("rolle", ""))
        if neu not in NUTZER_ROLLEN:
            return JSONResponse({"fehler": "unbekannte Rolle"}, status_code=400)
        with _DB_LOCK, _db() as c:
            c.execute("UPDATE nutzer SET rolle=? WHERE email=?", (neu, email))
    elif aktion == "passwort_neu":
        passwort = startpasswort()
        with _DB_LOCK, _db() as c:
            c.execute("UPDATE nutzer SET pw=? WHERE email=?", (pw_hash(passwort), email))
        return JSONResponse({"ok": True, "email": email, "startpasswort": passwort})
    else:
        return JSONResponse({"fehler": "unbekannte Aktion"}, status_code=400)
    return JSONResponse({"ok": True})


@app.post("/api/registrierung-einrichten")
async def api_registrierung_einrichten(request: Request) -> Response:
    un, fehler = _verwalter_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
        reg_id = int(body.get("id"))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit id erwartet"}, status_code=400)
    with _DB_LOCK, _db() as c:
        z = c.execute("SELECT daten, status FROM registrierungen WHERE id=?",
                      (reg_id,)).fetchone()
    if not z:
        return JSONResponse({"fehler": "Diese Anfrage gibt es nicht."}, status_code=404)
    daten = json.loads(z[0])
    email = str(daten.get("email", "")).strip().lower()
    if "@" not in email:
        return JSONResponse({"fehler": "Die Anfrage hat keine brauchbare E-Mail."},
                            status_code=400)
    passwort = nutzer_anlegen(email, daten.get("name", ""), daten.get("salon", ""), "salon")
    if passwort is None:
        return JSONResponse({"fehler": "Für diese E-Mail gibt es schon einen Zugang."},
                            status_code=409)
    # Steuerdaten aus der Anfrage als Einstellungen des neuen Kontos vorbefüllen.
    vorbelegung = {"betrieb_name": daten.get("salon", ""),
                   "rechtsform": daten.get("rechtsform", ""),
                   "steuernummer": daten.get("steuernummer", ""),
                   "finanzamt": daten.get("finanzamt", ""),
                   "kleinunternehmer": daten.get("kleinunternehmer", ""),
                   "steuerberater_status": daten.get("steuerberater", ""),
                   "telefon": daten.get("telefon", ""),
                   "email": email}
    for schluessel, wert in vorbelegung.items():
        if wert:
            db_einstellung_setzen(email, schluessel, str(wert)[:200])
    with _DB_LOCK, _db() as c:
        c.execute("UPDATE registrierungen SET status='eingerichtet' WHERE id=?", (reg_id,))
    return JSONResponse({"ok": True, "email": email, "startpasswort": passwort})


@app.get("/api/export/{monat}.csv")
def api_export(monat: str, request: Request, festschreiben: int = 0) -> Response:
    """DATEV-Buchungsstapel (EXTF v13, CP1252/CRLF). festschreiben=1 legt den
    Stapel zusätzlich in der Belegbox ab — die Belege gelten dann als
    exportiert (Beleg-Weg: „Bei der Kanzlei")."""
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if not darf_verwalten(un):
        return JSONResponse({"fehler": "nur für die Kanzlei"}, status_code=403)
    if not re.match(r"^\d{4}-\d{2}$", monat):
        return JSONResponse({"fehler": "ungültiger Monat"}, status_code=400)
    import extf  # noqa: PLC0415
    idx = index_aktuell()
    staemme = [s_ for s_, z in idx["belege"].items()
               if z["monat"] == monat and z["status"] in ("geprüft", "exportiert")]
    reviews = [idx["reviews"][s_] for s_ in sorted(staemme) if s_ in idx["reviews"]]
    text = extf.stapel(reviews, monat,
                       berater=os.environ.get("BABU_BERATER", extf.BERATER),
                       mandant=os.environ.get("BABU_MANDANT", extf.MANDANT))
    daten = extf.als_bytes(text)
    if festschreiben:
        import boxschreiber  # noqa: PLC0415
        stempel = time.strftime("%Y%m%d-%H%M%S")
        try:
            boxschreiber.schreiben(
                {f"export/{monat}/EXTF_{stempel}.csv": daten,
                 f"export/{monat}/stapel.json": json.dumps(
                     {"monat": monat, "staemme": sorted(staemme), "zeit": stempel,
                      "von": un}, ensure_ascii=False, indent=1).encode()},
                None, f"export: {monat}", un)
        except boxschreiber.SchreibFehler:
            return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                                status_code=503)
        with _INDEX_LOCK:
            _INDEX["geprueft"] = 0.0
    return Response(content=daten, media_type="text/csv; charset=windows-1252",
                    headers={"Content-Disposition":
                             f'attachment; filename="EXTF_Buchungsstapel_{monat}.csv"'})


def _median(werte: list[float]) -> float | None:
    if not werte:
        return None
    werte = sorted(werte)
    n = len(werte)
    return round(werte[n // 2] if n % 2 else (werte[n // 2 - 1] + werte[n // 2]) / 2, 1)


@app.get("/api/kpi/{monat}")
def api_kpi(monat: str, request: Request) -> Response:
    """Kennzahlen des Monats gegen die Spec-Ziele (docs/…/2026-08-13-salon-portal.md)."""
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if not re.match(r"^\d{4}-\d{2}$", monat):
        return JSONResponse({"fehler": "ungültiger Monat"}, status_code=400)
    idx = index_aktuell()
    zeilen = [z for z in idx["belege"].values() if z["monat"] == monat]
    mit_review = [z for z in zeilen if z["review_zeit"]]
    latenzen = []
    for z in mit_review:
        try:
            from datetime import datetime as _dt
            a = _dt.fromisoformat(z["hochgeladen"])
            r_ = _dt.fromisoformat(z["review_zeit"])
            latenzen.append((r_ - a).total_seconds())
        except Exception:  # noqa: BLE001
            pass
    fertig = [z for z in zeilen if z["status"] in ("geprüft", "exportiert")]
    unlesbar = [z for z in mit_review if z["dokumentklasse"] == "unlesbar"]
    fallback = [z for z in mit_review if z["konto_skr04"] == "6850"]
    summenprobe = [z for z in mit_review if z["summenprobe_ok"]]
    laufzeit = time.time() - _METRIK["start"]
    return JSONResponse({
        "monat": monat,
        "belege": len(zeilen),
        "brutto": round(sum(z["brutto"] or 0 for z in zeilen), 2),
        "zeit_bis_haken_s": {"median": _median(latenzen),
                             "ziel": 60, "werte": len(latenzen)},
        "auto_geprueft_quote": {"wert": round(len(fertig) / len(mit_review), 3) if mit_review else None,
                                "ziel": 0.8},
        "unlesbar_quote": {"wert": round(len(unlesbar) / len(mit_review), 3) if mit_review else None,
                           "ziel": 0.03},
        "fallback_6850_quote": {"wert": round(len(fallback) / len(mit_review), 3) if mit_review else None,
                                "ziel": 0.15},
        "summenprobe_quote": {"wert": round(len(summenprobe) / len(mit_review), 3) if mit_review else None,
                              "ziel": 0.9},
        "offen_zur_frist": {"wert": sum(1 for z in zeilen if z["status"] in ("nachfrage", "erfasst")),
                            "ziel": 0},
        "pflicht_metadaten_pro_beleg": {"wert": 0, "ziel": 0},
        "betrieb": {"seit_s": round(laufzeit),
                    "requests": _METRIK["requests"],
                    "fehler_5xx_quote": round(_METRIK["fehler_5xx"] / _METRIK["requests"], 4) if _METRIK["requests"] else 0,
                    "quote_304": round(_METRIK["davon_304"] / _METRIK["requests"], 3) if _METRIK["requests"] else 0,
                    "mittlere_dauer_ms": round(_METRIK["dauer_summe"] / _METRIK["requests"] * 1000, 1) if _METRIK["requests"] else 0},
    })


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
def chat(body: dict, request: Request) -> Response:
    # Sync-Route: läuft im Starlette-Threadpool, damit requests/subprocess
    # den Event-Loop nicht blockieren (workers=1). Auch der sse()-Generator
    # unten wird von StreamingResponse im Threadpool iteriert.
    un = angemeldet(request)   # Cookie (Portal) ODER Bearer (App) — Wire-Format unverändert
    if un is None:
        return JSONResponse({"fehler": "Token fehlt oder ungültig"}, status_code=401)
    if not zugelassen(un):
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
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
                "Du bist der Assistent von babu (0711 Intelligence) für "
                "Friseursalons. Antworte auf Deutsch, knapp und präzise. Keine "
                "Sie-Anrede — neutrale Formen oder Du. Zwei Arten von Fragen: "
                "(1) Fragen zu den eigenen Belegen beantwortest du AUSSCHLIESSLICH "
                "aus den mitgelieferten Belegdaten und nennst den Beleg (Lieferant "
                "oder Dateiname); steht etwas nicht in den Daten, sage das offen. "
                "(2) Allgemeine Steuer-Grundfragen (Kleinunternehmer-Regel, "
                "Kassenbuch-Pflicht, TSE, was man absetzen kann) erklärst du in "
                "einfachen Worten für den Salon-Alltag — und sagst dazu, dass das "
                "eine erste Einordnung ist. Beträge deutsch formatieren "
                "(1.234,56 €). Keine Steuerberatung — Hinweise sind "
                "Ersteinschätzungen, im Zweifel an die Ansprechperson verweisen."},
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


# ---------------------------------------------------------------------------
# Salon-Check: Abschluss-Unterlagen hochladen, im Hintergrund lesen, zuschauen.
# Der Job läuft als Thread im Prozess (workers=1 → genau ein Prozess, das
# Status-Dict ist für alle Requests sichtbar); das Portal pollt 1×/Sekunde.
# ---------------------------------------------------------------------------

ABSCHLUSS_MAX = 80 * 1024 * 1024   # Scan-Bündel eines Monats sind bis ~70 MB
ABSCHLUSS_TMP = Path(os.environ.get("BABU_ABSCHLUSS_TMP",
                                    str(Path.home() / "babu-web" / "abschluss-tmp")))
ABSCHLUSS_STAMM_KEYS = ("rechtsform", "steuernummer", "finanzamt", "kleinunternehmer")
_ABSCHLUSS_JOBS: dict[str, dict] = {}
_ABSCHLUSS_LOCK = threading.Lock()
# vLLM (:11435/:11436) teilt sich mit dem Review-Watcher — nie parallel fluten.
_LLM_SEMAPHORE = threading.Semaphore(1)


def db_abschluss_snapshot(un: str, jahr: int | None, status: dict) -> None:
    with _DB_LOCK, _db() as c:
        c.execute("INSERT OR REPLACE INTO abschluss_status VALUES (?,?,?,?)",
                  (un, jahr, json.dumps(status, ensure_ascii=False),
                   time.strftime("%Y-%m-%dT%H:%M:%S")))


def db_abschluss_lesen(un: str) -> dict | None:
    with _DB_LOCK, _db() as c:
        zeile = c.execute("SELECT json FROM abschluss_status WHERE un=?",
                          (un,)).fetchone()
    if not zeile:
        return None
    try:
        return json.loads(zeile[0])
    except ValueError:
        return None


def _abschluss_feld_uebernehmen(un: str, status: dict, feld: dict,
                                einstellungen: dict) -> None:
    """Konfliktregel: leere Einstellung wird gesetzt, belegte nie überschrieben."""
    k = feld["schluessel"]
    if k not in ABSCHLUSS_STAMM_KEYS or not feld.get("sicher"):
        return
    if k == "kleinunternehmer":
        neu = "Ja" if feld["wert"] else "Nein"
    else:
        neu = str(feld["wert"]).strip()[:200]
    alt = (einstellungen.get(k) or "").strip()
    if not alt:
        db_einstellung_setzen(un, k, neu)
        einstellungen[k] = neu
        feld["uebernommen"] = True
    elif alt != neu:
        status["vorschlaege"].append({"schluessel": k, "alt": alt, "neu": neu})


def _abschluss_job(un: str, jahr: int, pfade: list[Path]) -> None:
    import abschluss_lesen  # noqa: PLC0415
    import boxschreiber  # noqa: PLC0415
    status = _ABSCHLUSS_JOBS[un]
    einstellungen = db_einstellungen(un)

    def melden(feld: dict) -> None:
        feld["zeit"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with _ABSCHLUSS_LOCK:
            _abschluss_feld_uebernehmen(un, status, feld, einstellungen)
            status["felder"].append(feld)
            if len(status["felder"]) % 5 == 0:
                db_abschluss_snapshot(un, jahr, status)

    def fortschritt(text: str) -> None:
        status["hinweis"] = text

    try:
        status["stand"] = "liest"
        ergebnisse = []
        for pfad in pfade:
            eintrag = {"datei": pfad.name, "art": None, "seiten": None,
                       "stand": "liest"}
            with _ABSCHLUSS_LOCK:
                status["dokumente"].append(eintrag)
            with _LLM_SEMAPHORE:
                d = abschluss_lesen.dokument_lesen(
                    pfad, jahr=jahr, melden=melden, fortschritt=fortschritt)
            ergebnisse.append(d)
            with _ABSCHLUSS_LOCK:
                eintrag.update(art=d["art"], seiten=d["seiten"], stand="gelesen")
        kennzahlen = abschluss_lesen.zusammenfuehren(ergebnisse, jahr=jahr)
        with _ABSCHLUSS_LOCK:
            # Was die Summenprobe anzweifelt, verliert seinen Haken.
            for feld in status["felder"]:
                if feld["schluessel"] in kennzahlen["unsicher"]:
                    feld["sicher"] = False
        # Eine gelesene EÜR beantwortet die Paket-Frage nach der Abschluss-Art.
        if any(q["art"] == "euer" for q in kennzahlen["quellen"]) \
                and not (db_einstellungen(un).get("abschluss_art") or "").strip():
            db_einstellung_setzen(un, "abschluss_art", "EÜR")
        boxschreiber.schreiben(
            f"abschluss/{jahr}/kennzahlen.json",
            json.dumps(kennzahlen, ensure_ascii=False, indent=1).encode(),
            f"abschluss: kennzahlen {jahr}", un)
        with _ABSCHLUSS_LOCK:
            status["stand"] = "fertig"
            status["hinweis"] = "Fertig — dein Salon-Check steht."
            db_abschluss_snapshot(un, jahr, status)
        for pfad in pfade:
            pfad.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001
        print(f"[abschluss] Job für {un} gescheitert: {e}", flush=True)
        with _ABSCHLUSS_LOCK:
            status["stand"] = "fehler"
            status["hinweis"] = ("Das hat gerade nicht geklappt — "
                                 "versuch es später nochmal.")
            db_abschluss_snapshot(un, jahr, status)


def _abschluss_jahr(jahr: int) -> int | None:
    return jahr if 2000 <= jahr <= 2100 else None


@app.post("/api/abschluss")
async def api_abschluss_hochladen(request: Request, jahr: int = 0,
                                  name: str = "unterlage.pdf") -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    jahr = _abschluss_jahr(jahr or int(time.strftime("%Y")) - 1)
    if jahr is None:
        return JSONResponse({"fehler": "ungültiges Jahr"}, status_code=400)
    endung = Path(name).suffix.lower()
    if endung not in DOKUMENT_ENDUNGEN:
        return JSONResponse({"fehler": "kein Dokument-Format"}, status_code=400)
    daten = await request.body()
    if not daten:
        return JSONResponse({"fehler": "leer"}, status_code=400)
    if len(daten) > ABSCHLUSS_MAX:
        return JSONResponse({"fehler": "zu groß"}, status_code=413)
    import boxschreiber  # noqa: PLC0415
    dateiname = boxschreiber.beleg_dateiname(name)
    meta = json.dumps({"titel": name[:120], "art": "abschluss", "jahr": jahr,
                       "von": un}, ensure_ascii=False, indent=1).encode()
    try:
        commit = boxschreiber.schreiben(
            {f"abschluss/{jahr}/{dateiname}": daten,
             f"abschluss/{jahr}/{dateiname}.meta.json": meta},
            None, f"abschluss: {dateiname}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    # Arbeitskopie für den Lese-Job (der Job liest nicht aus Git).
    ablage = ABSCHLUSS_TMP / _un_ordner(un) / str(jahr)
    ablage.mkdir(parents=True, exist_ok=True)
    (ablage / dateiname).write_bytes(daten)
    return JSONResponse({"ok": True, "commit": commit, "jahr": jahr,
                         "datei": dateiname})


def _un_ordner(un: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", un)[:80]


@app.post("/api/abschluss/start")
def api_abschluss_start(request: Request, jahr: int = 0) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    jahr = _abschluss_jahr(jahr or int(time.strftime("%Y")) - 1)
    if jahr is None:
        return JSONResponse({"fehler": "ungültiges Jahr"}, status_code=400)
    with _ABSCHLUSS_LOCK:
        laufend = _ABSCHLUSS_JOBS.get(un)
        if laufend and laufend["stand"] in ("wartet", "liest"):
            return JSONResponse({"fehler": "wir lesen schon"}, status_code=409)
        ablage = ABSCHLUSS_TMP / _un_ordner(un) / str(jahr)
        pfade = sorted(p for p in ablage.glob("*")
                       if p.suffix.lower() in DOKUMENT_ENDUNGEN) \
            if ablage.is_dir() else []
        if not pfade:
            return JSONResponse({"fehler": "erst Unterlagen hochladen"},
                                status_code=400)
        status = {"stand": "wartet", "jahr": jahr, "dokumente": [],
                  "felder": [], "vorschlaege": [],
                  "hinweis": "Gleich geht's los — wir schauen uns alles an."}
        _ABSCHLUSS_JOBS[un] = status
    db_abschluss_snapshot(un, jahr, status)
    threading.Thread(target=_abschluss_job, args=(un, jahr, pfade),
                     daemon=True).start()
    return JSONResponse({"ok": True, "jahr": jahr, "dateien": len(pfade)})


@app.get("/api/abschluss/status")
def api_abschluss_status(request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    with _ABSCHLUSS_LOCK:
        status = _ABSCHLUSS_JOBS.get(un)
        if status is not None:
            return JSONResponse(status, headers={"Cache-Control": "no-store"})
    status = db_abschluss_lesen(un)
    if status is None:
        return JSONResponse({"stand": "leer"},
                            headers={"Cache-Control": "no-store"})
    if status.get("stand") in ("wartet", "liest"):
        # Prozess wurde zwischendurch neu gestartet — ehrlich sagen.
        status["stand"] = "unterbrochen"
        status["hinweis"] = ("Das Lesen wurde unterbrochen — "
                             "starte es einfach nochmal.")
    return JSONResponse(status, headers={"Cache-Control": "no-store"})


@app.get("/api/salon-check")
def api_salon_check(request: Request, jahr: int = 0) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    jahr = _abschluss_jahr(jahr or int(time.strftime("%Y")) - 1)
    if jahr is None:
        return JSONResponse({"fehler": "ungültiges Jahr"}, status_code=400)
    daten = git_show(f"abschluss/{jahr}/kennzahlen.json")
    if daten is None:
        return JSONResponse({"jahr": jahr, "stand": "leer", "karten": []})
    import saloncheck  # noqa: PLC0415
    try:
        kennzahlen = json.loads(daten)
    except ValueError:
        return JSONResponse({"fehler": "Kennzahlen unlesbar"}, status_code=500)
    return JSONResponse({"jahr": jahr, "stand": "fertig",
                         "karten": saloncheck.karten_bauen(kennzahlen),
                         "unsicher": kennzahlen.get("unsicher") or [],
                         "quellen": kennzahlen.get("quellen") or []})


# ---------------------------------------------------------------------------
# Finanzamt-Briefe: fotografieren/ablegen (art=behoerde) → babu erklärt sie
# in einfachen Worten als Sidecar <datei>.erklaerung.json.
# ---------------------------------------------------------------------------

def brief_erklaerung_bauen(daten: bytes, name: str, llm=None) -> dict:
    import abschluss_lesen  # noqa: PLC0415
    if llm is None:
        llm = abschluss_lesen.llm_json
    frage = ("Das ist ein Brief vom Finanzamt oder einer Behörde an eine "
             "Friseursalon-Inhaberin. Erklär ihn ihr in einfachen Worten "
             "(du-Form, kein Amtsdeutsch). Gib NUR JSON zurück: "
             '{"einfach": "2-3 Sätze, was der Brief bedeutet", '
             '"was_tun": "was sie jetzt tun muss — ein Satz, oder null", '
             '"bis_wann": "Datum als JJJJ-MM-TT, oder null"}. Rate nie.')
    import tempfile  # noqa: PLC0415
    endung = Path(name).suffix.lower() or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=endung) as f:
        f.write(daten)
        f.flush()
        texte = abschluss_lesen.seiten_text(f.name) if endung == ".pdf" else []
        if texte and len((texte[0] or "").strip()) >= abschluss_lesen.TEXT_SCHWELLE:
            roh = llm([{"role": "user", "content":
                        frage + "\n\nBRIEF:\n" + "\n\n".join(t[:6000] for t in texte[:5])}])
        else:
            bilder = abschluss_lesen.seiten_bilder(f.name)
            roh = llm([abschluss_lesen._bild_nachricht(frage, bilder[0])])
    return {"einfach": str(roh.get("einfach") or "").strip()[:600],
            "was_tun": (str(roh.get("was_tun")).strip()[:300]
                        if roh.get("was_tun") else None),
            "bis_wann": (str(roh.get("bis_wann")).strip()[:20]
                         if roh.get("bis_wann") else None)}


def _brief_job(pfad: str, daten: bytes, name: str, un: str) -> None:
    import boxschreiber  # noqa: PLC0415
    try:
        with _LLM_SEMAPHORE:
            erklaerung = brief_erklaerung_bauen(daten, name)
        boxschreiber.schreiben(
            pfad + ".erklaerung.json",
            json.dumps(erklaerung, ensure_ascii=False, indent=1).encode(),
            f"erklaerung: {name}", un)
        with _INDEX_LOCK:
            _INDEX["geprueft"] = 0.0
    except Exception as e:  # noqa: BLE001
        print(f"[brief] Erklärung für {pfad} gescheitert: {e}", flush=True)


# ---------------------------------------------------------------------------
# Kassenbuch-Empfang: die App legt jedes gepflegte Tagesblatt in der Box ab.
# ---------------------------------------------------------------------------

KASSENBUCH_ZAHLEN = ("bestandVortag", "einnahmenBar", "privateinlagen",
                     "barabhebungBank", "ecZahlungen", "trinkgeldTeamEC",
                     "sonstigeAusgaben", "privatentnahmen", "einzahlungBank",
                     "gezaehltSchluss")
KASSENBUCH_NOTIZEN = ("differenzGrund", "sonstigeNotiz")
_KASSEN_DATUM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@app.post("/api/kassenbuch")
async def api_kassenbuch(request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    datum = str(body.get("datum", ""))
    if not _KASSEN_DATUM_RE.match(datum):
        return JSONResponse({"fehler": "Datum fehlt (JJJJ-MM-TT)"}, status_code=400)
    blatt: dict = {"datum": datum, "von": un}
    for feld in KASSENBUCH_ZAHLEN:
        try:
            blatt[feld] = round(float(body.get(feld) or 0), 2)
        except (TypeError, ValueError):
            blatt[feld] = 0.0
    for feld in KASSENBUCH_NOTIZEN:
        wert = str(body.get(feld) or "").strip()[:300]
        if wert:
            blatt[feld] = wert
    import boxschreiber  # noqa: PLC0415
    try:
        commit = boxschreiber.schreiben(
            f"kassenbuch/{datum[:7]}/{datum}.json",
            json.dumps(blatt, ensure_ascii=False, indent=1).encode(),
            f"kassenbuch: {datum}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    return JSONResponse({"ok": True, "commit": commit, "datum": datum})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7844, workers=1)
