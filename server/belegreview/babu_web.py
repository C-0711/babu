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
from fastapi.concurrency import run_in_threadpool
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
    conn.execute("""CREATE TABLE IF NOT EXISTS team
        (id INTEGER PRIMARY KEY AUTOINCREMENT, un TEXT NOT NULL,
         name TEXT NOT NULL, email TEXT, lohn_art TEXT NOT NULL DEFAULT 'fest',
         betrag REAL, stundenlohn REAL, stunden REAL,
         seit TEXT, aktiv INTEGER NOT NULL DEFAULT 1, angelegt TEXT)""")
    # Nachrüstbare Spalten: Rechte, die die Inhaberin je Person vergibt.
    for spalte, typ in (("darf_belege", "INTEGER NOT NULL DEFAULT 0"),
                        ("darf_kasse", "INTEGER NOT NULL DEFAULT 0"),
                        ("zugang", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE team ADD COLUMN {spalte} {typ}")
        except sqlite3.OperationalError:
            pass          # Spalte gibt es schon
    # Mitarbeiterkonten zeigen auf den Salon, dem die Daten gehören.
    try:
        conn.execute("ALTER TABLE nutzer ADD COLUMN gehoert_zu TEXT")
    except sqlite3.OperationalError:
        pass
    # Hat dieses Konto eine eigene Belegbox? Bestehende Zugänge sind von Hand
    # eingerichtet — sie behalten ihre (DEFAULT 1). Wer sich künftig selbst
    # registriert, bekommt sie erst, wenn wir sie angelegt haben.
    try:
        conn.execute("ALTER TABLE nutzer ADD COLUMN box INTEGER NOT NULL DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    # Termine enthalten Kundennamen — personenbezogen, also löschbar und
    # damit NICHT in der Belegbox (dort bleibt jede Fassung für immer).
    conn.execute("""CREATE TABLE IF NOT EXISTS termin
        (id INTEGER PRIMARY KEY AUTOINCREMENT, un TEXT NOT NULL,
         start TEXT NOT NULL, minuten INTEGER NOT NULL, wer TEXT,
         kundin TEXT, leistung TEXT, notiz TEXT,
         abgesagt INTEGER NOT NULL DEFAULT 0, angelegt TEXT)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS termin_un_start
        ON termin (un, start)""")
    # Kundenkartei: Namen, Notizen, Farbformeln, Allergiehinweise. Das sind
    # personenbezogene und teils gesundheitsnahe Daten — sie gehören NICHT
    # in die Belegbox, wo jede Fassung für immer bliebe, sondern hierher,
    # wo sich löschen lässt (Art. 17 DSGVO).
    conn.execute("""CREATE TABLE IF NOT EXISTS kundin
        (id INTEGER PRIMARY KEY AUTOINCREMENT, un TEXT NOT NULL,
         name TEXT NOT NULL, telefon TEXT, email TEXT, notiz TEXT,
         allergie TEXT, angelegt TEXT, zuletzt TEXT)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS kundin_un ON kundin (un, name)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS behandlung
        (id INTEGER PRIMARY KEY AUTOINCREMENT, un TEXT NOT NULL,
         kundin INTEGER NOT NULL, datum TEXT NOT NULL, leistung TEXT,
         formel TEXT, notiz TEXT, termin INTEGER, angelegt TEXT)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS behandlung_kundin
        ON behandlung (un, kundin, datum)""")
    # Leistungskatalog: was der Salon anbietet, wie lange es dauert, was es
    # kostet. Stammdaten des Betriebs.
    conn.execute("""CREATE TABLE IF NOT EXISTS leistung
        (id INTEGER PRIMARY KEY AUTOINCREMENT, un TEXT NOT NULL,
         name TEXT NOT NULL, preis REAL NOT NULL, minuten INTEGER NOT NULL,
         ust_satz INTEGER NOT NULL DEFAULT 19, aktiv INTEGER NOT NULL DEFAULT 1,
         angelegt TEXT)""")
    # Termine bekommen Preis und Abrechnung nachgerüstet.
    # Personalakte. Personenbezogen bis auf die Knochen — Geburtsdatum,
    # Anschrift, Bankverbindung, Steuernummer. Gehört deshalb hierher und
    # nicht in die Belegbox: was hier steht, muss sich löschen lassen. Die
    # gescannten Dokumente gehen dagegen in die Box, sie sind
    # aufbewahrungspflichtig.
    conn.execute("""CREATE TABLE IF NOT EXISTS mitarbeiter
        (id INTEGER PRIMARY KEY AUTOINCREMENT, un TEXT NOT NULL,
         vorname TEXT, name TEXT, geburtsdatum TEXT, geburtsname TEXT,
         geburtsort TEXT, staatsangehoerigkeit TEXT,
         strasse TEXT, plz TEXT, ort TEXT, telefon TEXT, email TEXT,
         steuer_idnr TEXT, rentenvers_nr TEXT, krankenkasse TEXT,
         kinderlos INTEGER, kinder_abschlaege INTEGER,
         iban TEXT, bic TEXT, titel_bis TEXT,
         art TEXT, eintritt TEXT, austritt TEXT, befristet_bis TEXT,
         taetigkeit TEXT, stunden_woche REAL, tage_woche REAL,
         entgelt INTEGER, urlaubstage INTEGER,
         vertrag_pfad TEXT, vertrag_fassung TEXT, vertrag_angenommen TEXT,
         belehrungen TEXT, erledigt TEXT, stand TEXT NOT NULL DEFAULT 'eingeladen',
         einladung TEXT, eingeladen_am TEXT, angelegt TEXT)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS mitarbeiter_einladung
        ON mitarbeiter (einladung)""")

    # WhatsApp: ein Gesprächsfaden je Telefonnummer, damit „2" als Antwort
    # weiß, worauf es sich bezieht. Auch das sind personenbezogene Daten —
    # deshalb hier und nicht in der Belegbox.
    conn.execute("""CREATE TABLE IF NOT EXISTS wa_faden
        (id INTEGER PRIMARY KEY AUTOINCREMENT, un TEXT NOT NULL,
         telefon TEXT NOT NULL, name TEXT, stand TEXT NOT NULL DEFAULT 'neu',
         wunsch TEXT, vorschlaege TEXT, termin INTEGER, stumm INTEGER NOT NULL
         DEFAULT 0, begonnen TEXT, zuletzt TEXT, UNIQUE (un, telefon))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS wa_nachricht
        (id INTEGER PRIMARY KEY AUTOINCREMENT, un TEXT NOT NULL,
         faden INTEGER NOT NULL, richtung TEXT NOT NULL, text TEXT NOT NULL,
         wa_id TEXT, zeit TEXT NOT NULL)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS wa_nachricht_faden
        ON wa_nachricht (faden, id)""")

    for spalte, typ in (("preis", "REAL"), ("ust_satz", "INTEGER"),
                        ("abgerechnet", "TEXT"), ("zahlart", "TEXT"),
                        ("kundin_id", "INTEGER"), ("bestaetigt", "INTEGER"),
                        ("quelle", "TEXT"), ("telefon", "TEXT"),
                        ("zahlung_ref", "TEXT")):
        try:
            conn.execute(f"ALTER TABLE termin ADD COLUMN {spalte} {typ}")
        except sqlite3.OperationalError:
            pass          # Spalte gibt es schon
    conn.execute("""CREATE TABLE IF NOT EXISTS gespraech
        (id INTEGER PRIMARY KEY AUTOINCREMENT, un TEXT NOT NULL,
         titel TEXT, begonnen TEXT NOT NULL, zuletzt TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS nachricht
        (id INTEGER PRIMARY KEY AUTOINCREMENT, gespraech INTEGER NOT NULL,
         rolle TEXT NOT NULL, text TEXT NOT NULL, zeit TEXT NOT NULL)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS nachricht_gespraech
        ON nachricht (gespraech, id)""")
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

NUTZER_ROLLEN = ("admin", "kanzlei", "salon", "mitarbeit")


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
        z = c.execute("""SELECT email, name, salon, rolle, pw, aktiv, gehoert_zu, angelegt,
                         letzter_login, box FROM nutzer WHERE email=?""",
                      (email.strip().lower(),)).fetchone()
    if not z:
        return None
    return {"email": z[0], "name": z[1], "salon": z[2], "rolle": z[3], "pw": z[4],
            "aktiv": bool(z[5]), "gehoert_zu": z[6], "angelegt": z[7],
            "letzter_login": z[8], "box": bool(z[9])}


def nutzer_anlegen(email: str, name: str, salon: str, rolle_neu: str,
                   passwort: str | None = None, box: bool = True) -> str | None:
    """Legt ein Konto an und gibt das Passwort zurück (None = existiert schon).

    Ohne `passwort` wird ein Startpasswort generiert (Verwaltungs-Weg).
    `box=False` ist der Selbstregistrierungs-Weg: das Konto steht, die
    Belegbox richten wir von Hand ein — sonst läse der Nächste, der sich
    anmeldet, die Buchhaltung eines fremden Salons.
    """
    email = email.strip().lower()
    if nutzer_holen(email):
        return None
    passwort = passwort or startpasswort()
    with _DB_LOCK, _db() as c:
        c.execute("""INSERT INTO nutzer (email, name, salon, rolle, pw, aktiv,
                     angelegt, box) VALUES (?,?,?,?,?,1,?,?)""",
                  (email, name.strip()[:120], salon.strip()[:120],
                   rolle_neu if rolle_neu in NUTZER_ROLLEN else "salon",
                   pw_hash(passwort), _jetzt_iso(), 1 if box else 0))
    return passwort


def zugelassen(un: str) -> bool:
    """PAT-Allowlist ODER aktives eigenes Konto."""
    if un in ERLAUBT:
        return True
    n = nutzer_holen(un)
    return bool(n and n["aktiv"])


def box_mitglied(un: str) -> bool:
    """Gehört dieser Zugang zu der Belegbox, die dieser Server bedient?

    Es gibt genau EINE Box je Betrieb. Ein Konto ist deshalb noch kein
    Zugang zu ihren Belegen: darin arbeiten der Betrieb selbst, sein Team —
    und die Kanzlei, die ihn betreut. Wer sich selbst registriert hat,
    behält sein Konto, sieht aber keine fremden Belege.
    """
    inhaber = salon_von(un)          # Mitarbeiterinnen erben den Salon
    if inhaber in ERLAUBT:
        return True
    n = nutzer_holen(un)
    if n and n["rolle"] in ("admin", "kanzlei"):
        return True
    besitzer = nutzer_holen(inhaber)
    return bool(besitzer and besitzer["box"])


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
# Die Rechnungsnummer wird gelesen UND vergeben — dazwischen darf
# niemand dieselbe Nummer bekommen.
_RECHNUNG_SCHLOSS = threading.Lock()
# Termine: Überschneidung prüfen und eintragen gehören zusammen.
_TERMIN_SCHLOSS = threading.Lock()
_INDEX: dict = {"head": None, "geprueft": 0.0, "belege": {}, "reviews": {},
                "dokumente": [], "freigaben": {}, "umsaetze": {},
                "kassenblaetter": {}, "zeiten": {}, "oid_cache": {},
                "rechnungen": {}}


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
                    and not p.endswith(".korrektur.json")
                    and not p.endswith(".angaben.json")}
    korrektur_pfade = {p[len("review/"):-len(".korrektur.json")]: oid
                       for p, oid in pfade.items() if p.endswith(".korrektur.json")}
    # Ergänzungen der Nutzerin (fehlender Betrag, Datum, Laden) — sie
    # beantworten genau die Fragen, die babu offen gelassen hat.
    angaben_pfade = {p[len("review/"):-len(".angaben.json")]: oid
                     for p, oid in pfade.items() if p.endswith(".angaben.json")}
    bewirtung_staemme = {p[len("review/"):-len(".bewirtung.json")]
                         for p in pfade if p.endswith(".bewirtung.json")}
    beleg_pfade = [p for p in pfade
                   if p.startswith("docs/") and Path(p).suffix.lower() in BELEG_ENDUNGEN]

    oid_cache = _INDEX["oid_cache"]
    fehlend = [oid for oid in list(review_pfade.values()) + list(korrektur_pfade.values())
               + list(angaben_pfade.values())
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
        ergaenzung = oid_cache.get(angaben_pfade.get(stamm, ""))
        if isinstance(ergaenzung, dict):
            eintrag["ergaenzt"] = True
            if ergaenzung.get("brutto") is not None:
                eintrag["brutto"] = ergaenzung["brutto"]
            for kk in ("lieferant", "datum"):
                if ergaenzung.get(kk):
                    eintrag[kk] = ergaenzung[kk]
            # Beantwortete Punkte verschwinden aus der Nachfrage-Liste.
            beantwortet = set(ergaenzung.get("beantwortet") or [])
            eintrag["offen"] = [o for o in eintrag["offen"] if o not in beantwortet]
            if not eintrag["offen"] and eintrag.get("status") == "nachfrage":
                eintrag["status"] = "erfasst"
            if review is not None:
                review = json.loads(json.dumps(review))
                review.setdefault("felder", {})
                for kk in ("brutto", "lieferant", "datum"):
                    if ergaenzung.get(kk) is not None:
                        review["felder"][kk] = ergaenzung[kk]
                review["felder"]["offen"] = eintrag["offen"]
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
    vertrag_pfade = {p_: oid for p_, oid in pfade.items()
                     if p_.startswith("dokumente/") and p_.endswith(".vertrag.json")}
    for oid, roh in _blobs_lesen([o for o in vertrag_pfade.values()
                                  if o not in oid_cache]).items():
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
                or pfad.endswith(".erklaerung.json") \
                or pfad.endswith(".vertrag.json"):
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
            "vertrag": oid_cache.get(vertrag_pfade.get(pfad + ".vertrag.json", "")),
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

    # Kassenbuch: kassenbuch/<JJJJ-MM>/<JJJJ-MM-TT>.json — die Erlösseite.
    kassen_pfade = {p_: oid for p_, oid in pfade.items()
                    if p_.startswith("kassenbuch/") and p_.endswith(".json")}
    fehlend_ka = [oid for oid in kassen_pfade.values() if oid not in oid_cache]
    for oid, roh in _blobs_lesen(fehlend_ka).items():
        try:
            oid_cache[oid] = json.loads(roh)
        except Exception:  # noqa: BLE001
            oid_cache[oid] = None
    kassenblaetter: dict[str, dict] = {}
    for p_, oid in kassen_pfade.items():
        d_ = oid_cache.get(oid)
        if isinstance(d_, dict) and d_.get("datum"):
            # Ein Blatt je Tag; ein späteres gewinnt (Korrektur).
            kassenblaetter[d_["datum"]] = d_
    _INDEX["kassenblaetter"] = kassenblaetter

    # Gestellte Rechnungen: rechnungen/<JJJJ-MM>/<nummer>.json
    rechnung_pfade = {p_: oid for p_, oid in pfade.items()
                      if p_.startswith("rechnungen/") and p_.endswith(".json")}
    for oid, roh in _blobs_lesen([o for o in rechnung_pfade.values()
                                  if o not in oid_cache]).items():
        try:
            oid_cache[oid] = json.loads(roh)
        except Exception:  # noqa: BLE001
            oid_cache[oid] = None
    rechnungen_: dict[str, dict] = {}
    for p_, oid in rechnung_pfade.items():
        d_ = oid_cache.get(oid)
        if isinstance(d_, dict) and d_.get("nummer"):
            rechnungen_[d_["nummer"]] = d_
    _INDEX["rechnungen"] = rechnungen_

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


@app.get("/einkauf")
def einkauf_seite() -> Response:
    """Was babu aus den Einkaufsrechnungen macht — vom Fuß der Startseite aus."""
    pfad = SEITE.parent / "einkauf.html"
    if not pfad.is_file():
        return JSONResponse({"fehler": "kommt bald"}, status_code=404)
    return FileResponse(pfad, media_type="text/html", headers=HTML_FRISCH)


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
    """Angemeldet und aktiv — reicht für die eigenen Daten (Konto, Team, Fristen)."""
    un = angemeldet(request)
    if un is None:
        return None, JSONResponse({"fehler": "nicht angemeldet"}, status_code=401)
    if not zugelassen(un):
        print(f"[wache] 403: '{un}' weder Allowlist noch aktives Konto", flush=True)
        return None, JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    return un, None


BOX_GESPERRT = ("Dein Zugang ist noch nicht für eine Belegbox freigeschaltet. "
                "Schreib uns kurz — dann richten wir sie für deinen Salon ein.")


def _box_wache(request: Request) -> tuple[str, None] | tuple[None, JSONResponse]:
    """Zusätzlich zur Anmeldung: Diese Belegbox muss ihm auch gehören.

    Jede Route, die Belege, Kassenbuch, Ablage oder Zahlen anfasst, geht
    hier durch — sonst läse ein frisch registriertes Konto die Buchhaltung
    eines fremden Salons.
    """
    un, fehler = _api_wache(request)
    if fehler:
        return None, fehler
    if not box_mitglied(un):
        print(f"[wache] 403: '{un}' gehört nicht zu dieser Belegbox", flush=True)
        return None, JSONResponse({"fehler": BOX_GESPERRT}, status_code=403)
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
# Ab hier wird aufgeräumt, damit die Zähler-Tabellen nicht ewig wachsen.
_IP_TABELLE_MAX = 5000


# Nur diesen direkten Absendern glauben wir eine Weiterleitungs-Kopfzeile:
# das ist der Cloudflare-Tunnel auf demselben Rechner.
TUNNEL_PEERS = {"127.0.0.1", "::1", "localhost"}


def _client_ip(request: Request) -> str:
    """Die IP der Besucherin — nicht die des Tunnels.

    Hinter cloudflared kommt jeder Request von 127.0.0.1: ein einziger
    Fehlversuch würde sonst den ganzen Salon für eine Minute aussperren.
    Den Kopfzeilen wird nur geglaubt, wenn der direkte Absender wirklich der
    lokale Tunnel ist — sonst erfände sich jeder ein frisches Kontingent.
    """
    peer = request.client.host if request.client else "?"
    if peer in TUNNEL_PEERS:
        kopf = (request.headers.get("cf-connecting-ip")
                or request.headers.get("x-forwarded-for", "").split(",")[0])
        if kopf.strip():
            return kopf.strip()[:64]
    return peer


def _zaehler_aufraeumen(tabelle: dict, jetzt: float, alter: float) -> None:
    if len(tabelle) <= _IP_TABELLE_MAX:
        return
    for schluessel, wert in list(tabelle.items()):
        letzte = max(wert) if isinstance(wert, list) else wert
        if jetzt - letzte > alter:
            tabelle.pop(schluessel, None)


@app.post("/api/login")
def api_login(body: dict, request: Request) -> Response:
    if not _origin_ok(request):
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    ip = _client_ip(request)
    jetzt = time.time()
    versuche = [t for t in _LOGIN_VERSUCHE.get(ip, []) if jetzt - t < 60]
    if len(versuche) >= 5:
        _LOGIN_VERSUCHE[ip] = versuche
        return JSONResponse({"fehler": "Zu viele Versuche — bitte eine Minute warten."},
                            status_code=429)
    versuche.append(jetzt)
    _LOGIN_VERSUCHE[ip] = versuche
    _zaehler_aufraeumen(_LOGIN_VERSUCHE, jetzt, 60)
    email = str(body.get("email", "")).strip().lower()
    passwort = str(body.get("passwort", ""))
    n = nutzer_holen(email) if email else None
    if not n or not n["aktiv"] or not pw_pruefen(passwort, n["pw"]):
        return JSONResponse({"fehler": "E-Mail oder Passwort stimmt nicht."},
                            status_code=401)
    # Geglückt: das Kontingent gehört den Fehlversuchen, nicht den Erfolgen.
    _LOGIN_VERSUCHE.pop(ip, None)
    with _DB_LOCK, _db() as c:
        c.execute("UPDATE nutzer SET letzter_login=? WHERE email=?",
                  (_jetzt_iso(), email))
    exp = int(time.time()) + SESSION_DAUER
    antwort = JSONResponse({"un": email, "rolle": n["rolle"],
                            "box": box_mitglied(email)})
    antwort.set_cookie(SESSION_COOKIE, _signieren(email, exp), max_age=SESSION_DAUER,
                       httponly=True, secure=SESSION_SECURE, samesite="lax", path="/")
    return antwort


@app.post("/api/app-anmelden")
def api_app_anmelden(body: dict, request: Request) -> Response:
    """Die App verbindet sich mit dem ganz normalen Konto (E-Mail + Passwort).
    Dabei entsteht unsichtbar ein Geräteschlüssel — er erscheint GENAU EINMAL
    in der Antwort, gespeichert wird nur sein Hash. Kein Schlüssel-Gefrickel
    mehr für die Nutzerin."""
    ip = _client_ip(request)
    jetzt = time.time()
    versuche = [t for t in _LOGIN_VERSUCHE.get(ip, []) if jetzt - t < 60]
    if len(versuche) >= 5:
        _LOGIN_VERSUCHE[ip] = versuche
        return JSONResponse({"fehler": "Zu viele Versuche — bitte eine Minute warten."},
                            status_code=429)
    versuche.append(jetzt)
    _LOGIN_VERSUCHE[ip] = versuche
    _zaehler_aufraeumen(_LOGIN_VERSUCHE, jetzt, 60)
    email = str(body.get("email", "")).strip().lower()
    passwort = str(body.get("passwort", ""))
    geraet = str(body.get("geraet", "") or "")[:80]
    n = nutzer_holen(email) if email else None
    if not n or not n["aktiv"] or not pw_pruefen(passwort, n["pw"]):
        return JSONResponse({"fehler": "E-Mail oder Passwort stimmt nicht."},
                            status_code=401)
    _LOGIN_VERSUCHE.pop(ip, None)     # geglückt — siehe /api/login
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
    # `box` sagt der Oberfläche, ob es überhaupt Belege zu zeigen gibt —
    # ohne das würde ein frisches Konto auf leere Kacheln starren.
    antwort = JSONResponse({"un": un, "rolle": rolle(un), "box": box_mitglied(un)})
    if request.cookies.get(SESSION_COOKIE):
        antwort.set_cookie(SESSION_COOKIE, _signieren(un, exp), max_age=SESSION_DAUER,
                           httponly=True, secure=SESSION_SECURE, samesite="lax", path="/")
    return antwort


@app.get("/api/belege")
def api_belege(request: Request, monat: str | None = None, status: str | None = None,
               limit: int = 200, seite_nr: int = 1) -> Response:
    un, fehler = _box_wache(request)
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
    un, fehler = _box_wache(request)
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
    # Nachgetragene Angaben gelten — sie beantworten genau die offenen Punkte.
    roh_ang = git_show(f"review/{stamm}.angaben.json")
    if roh_ang is not None:
        try:
            ang = json.loads(roh_ang)
        except Exception:  # noqa: BLE001
            ang = {}
        if isinstance(ang, dict) and ang:
            d.setdefault("felder", {})
            for kk in ("brutto", "lieferant", "datum"):
                if ang.get(kk) is not None:
                    d["felder"][kk] = ang[kk]
            beantwortet = set(ang.get("beantwortet") or [])
            d["felder"]["offen"] = [o for o in (d["felder"].get("offen") or [])
                                    if o not in beantwortet]
            d["ergaenzt"] = True
            d["angaben"] = ang
            d["buchungssatz"] = datev_buchungssatz(d) if d else None
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
    un, fehler = _box_wache(request)
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


def _zahl(wert) -> float | None:
    """Zahl aus einer Eingabe — deutsche Schreibweise erlaubt.

    Echte Zahlen gehen NICHT durch den Text-Parser. Vorher wurde bei jedem
    Wert der Punkt als Tausendertrenner entfernt — aus einem Trinkgeld von
    12.50 (JSON-Zahl) wurden so 1250, aus 2400.50 Gehalt 24005. Nur
    getippter Text wird deutsch gelesen, und auch dort trennt der Punkt nur
    dann Tausender, wenn ein Komma dabei ist.
    """
    if wert in (None, ""):
        return None
    if isinstance(wert, (int, float)) and not isinstance(wert, bool):
        return float(wert)
    text = str(wert).strip()
    if "," in text:                       # „2.400,50" — Punkt trennt Tausender
        text = text.replace(".", "").replace(",", ".")
    else:
        # Ohne Komma ist der Punkt zweideutig: „2.400" meint
        # zweitausendvierhundert, „89.50" meint Komma. Entschieden wird an
        # den Nachkommastellen — genau wie im Betragsfeld der App.
        teile = text.split(".")
        text = text if len(teile) == 2 and len(teile[1]) == 2 else "".join(teile)
    try:
        return float(text)
    except ValueError:
        return None


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
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if not NAME_RE.match(stamm):
        return JSONResponse({"fehler": "ungültiger Name"}, status_code=400)
    eintrag = (await run_in_threadpool(index_aktuell))["belege"].get(stamm)
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
        commit = await run_in_threadpool(boxschreiber.schreiben, f"review/{stamm}.bewirtung.json", inhalt,
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
        commit = await run_in_threadpool(boxschreiber.schreiben, f"docs/{monat}/{dateiname}", daten,
                                        nachricht, un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "Push fehlgeschlagen"}, status_code=502)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True,
                         "ref": os.environ.get("BABU_REF",
                                               "inspektor/ws-christoph0711.io/babu"),
                         "commit": commit, "datei": f"docs/{monat}/{dateiname}"})


def _mitarbeit_wache(un: str, recht: str, was: str) -> Response | None:
    """Mitarbeiterinnen dürfen nur, was die Inhaberin freigegeben hat."""
    if team_recht(un, recht):
        return None
    return JSONResponse(
        {"fehler": f"Dafür fehlt dir die Freigabe. {was} darf im Salon "
                   "nur, wer dafür freigeschaltet ist — frag kurz nach."},
        status_code=403)


@app.post("/api/hochladen")
async def api_hochladen(request: Request, name: str = "beleg.jpg") -> Response:
    """Portal-Upload ohne gespeicherten Zugangscode: Cookie-Session + Rohbytes.

    Schreibt den aufnahme:-Commit selbst über das Gateway — :7843 bleibt
    unangetastet, der Watcher findet die Datei wie jede andere.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if (sperre := _mitarbeit_wache(un, "darf_belege", "Belege einreichen")):
        return sperre
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
        commit = await run_in_threadpool(boxschreiber.schreiben, f"docs/{monat}/{dateiname}", daten,
                                        f"aufnahme: {dateiname}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"}, status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit, "datei": f"docs/{monat}/{dateiname}"})


# Beiakten eines Belegs: die Zweitprüfung und alles, was später dazukam.
# Beim Löschen gehen sie mit — sonst bliebe eine Prüfung ohne Beleg zurück.
BELEG_BEIAKTEN = (".json", ".md", ".embedding.json", ".angaben.json",
                  ".bewirtung.json", ".korrektur.json")


@app.post("/api/beleg/{stamm}/loeschen")
async def api_beleg_loeschen(stamm: str, request: Request) -> Response:
    """Einen falschen Beleg wegnehmen — doppelt fotografiert, unlesbar, privat.

    Gelöscht wird mit einem eigenen Commit: der aktuelle Stand zeigt den Beleg
    nicht mehr, nachvollziehbar bleibt, dass es ihn gab. Was schon im Stapel
    bei der Kanzlei liegt, bleibt.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Belege löschen darf die Inhaberin."},
                            status_code=403)
    if not NAME_RE.match(stamm):
        return JSONResponse({"fehler": "ungültiger Name"}, status_code=400)
    eintrag = (await run_in_threadpool(index_aktuell))["belege"].get(stamm)
    if eintrag is None:
        return JSONResponse({"fehler": "unbekannter Beleg"}, status_code=404)
    if eintrag["status"] == "exportiert":
        return JSONResponse(
            {"fehler": "Dieser Beleg liegt schon im Stapel bei deiner Kanzlei. "
                       "Zum Löschen sprich kurz mit ihr."}, status_code=409)

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    grund = str((body or {}).get("grund", "")).strip()[:200]
    nachricht = f"geloescht: {stamm}" + (f"\n\n{grund}" if grund else "")
    pfade = [eintrag["datei"]] + [f"review/{stamm}{a}" for a in BELEG_BEIAKTEN]

    import boxschreiber  # noqa: PLC0415
    try:
        commit = await run_in_threadpool(boxschreiber.loeschen, pfade, nachricht, un)
    except boxschreiber.NichtsZuLoeschen:
        return JSONResponse({"fehler": "unbekannter Beleg"}, status_code=404)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit, "stamm": stamm})


@app.post("/api/aufnahme")
async def api_aufnahme(request: Request, name: str = "foto.jpg",
                       text: str = "") -> Response:
    """Ein Foto — egal wovon. babu entscheidet, wohin es gehört.

    Die Kamera fragt nicht mehr „was ist das?". Die App liest den Text schon
    auf dem Gerät und schickt ihn mit; hier fällt daraus die Entscheidung:
    Kassenbon in die Belege, Vertrag und Behördenpost in die Ablage,
    Kontoauszug zu den Auszügen. Im Zweifel Beleg — der häufigste Fall und
    der harmloseste Irrtum.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if (sperre := _mitarbeit_wache(un, "darf_belege", "Belege einreichen")):
        return sperre
    endung = Path(name).suffix.lower()
    if endung not in HOCHLADEN_ENDUNGEN:
        return JSONResponse({"fehler": "kein Beleg-Format"}, status_code=400)
    daten = await request.body()
    if not daten:
        return JSONResponse({"fehler": "leer"}, status_code=400)
    if len(daten) > HOCHLADEN_MAX:
        return JSONResponse({"fehler": "zu groß"}, status_code=413)

    import einsortieren  # noqa: PLC0415
    # Bei PDFs liest der Server selbst nach — die App hat dort keinen Text.
    gelesen = text
    if not gelesen.strip() and endung == ".pdf":
        try:
            import tempfile  # noqa: PLC0415
            import abschluss_lesen  # noqa: PLC0415
            with tempfile.NamedTemporaryFile(suffix=".pdf") as tf:
                tf.write(daten)
                tf.flush()
                gelesen = "\n".join(abschluss_lesen.seiten_text(tf.name)[:3])
        except Exception:  # noqa: BLE001
            gelesen = ""
    entscheidung = einsortieren.entscheiden(gelesen)

    import boxschreiber  # noqa: PLC0415
    dateiname = boxschreiber.beleg_dateiname(name)
    monat = time.strftime("%Y-%m")
    pfad = einsortieren.pfad_fuer(entscheidung["art"], dateiname, monat)

    dateien: dict[str, bytes] = {pfad: daten}
    art = entscheidung["art"]
    if art in ("vertrag", "behoerde"):
        # Dokumente tragen ihren Zettel mit: sonst weiß die Ablage nicht,
        # in welchen Ordner die Datei gehört.
        titel = {"vertrag": "Vertrag", "behoerde": "Post vom Amt"}[art]
        dateien[pfad + ".meta.json"] = json.dumps(
            {"titel": f"{titel} · {name}"[:120], "art": art, "von": un,
             "erkannt": entscheidung["grund"]},
            ensure_ascii=False, indent=1).encode()

    try:
        commit = await run_in_threadpool(boxschreiber.schreiben, dateien, None,
                                         f"aufnahme: {dateiname}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0

    # Verträge und Briefe liest babu im Hintergrund weiter — wie bisher.
    if art == "vertrag":
        threading.Thread(target=_vertrag_job, args=(pfad, daten, name, un),
                         daemon=True).start()
    elif art == "behoerde":
        threading.Thread(target=_brief_job, args=(pfad, daten, name, un),
                         daemon=True).start()

    return JSONResponse({"ok": True, "commit": commit, "datei": pfad,
                         "art": art, "sicher": entscheidung["sicher"],
                         "grund": entscheidung["grund"],
                         "wohin": WOHIN_TEXT.get(art, WOHIN_TEXT["beleg"])})


# Was die App der Nutzerin sagt — ohne Ordnernamen und ohne Technik.
WOHIN_TEXT = {
    "beleg": "Bei deinen Belegen",
    "vertrag": "Bei deinen Verträgen",
    "behoerde": "Bei deiner Post vom Amt",
    "kontoauszug": "Bei deinen Kontoauszügen",
}


DOKUMENT_ENDUNGEN = {".pdf", ".jpg", ".jpeg", ".png"}
DOKUMENT_PFAD_RE = re.compile(r"^dokumente/[A-Za-z0-9._/ -]{1,200}$")
# Alles, was in der Ablage steht, muss sich auch öffnen lassen — sonst führt
# ein Eintrag ins Leere. Gelöscht werden darf davon nur `dokumente/`.
ABLAGE_PFAD_RE = re.compile(
    r"^(dokumente|auszuege|abschluss|export|kassenbuch|rechnungen)/"
    r"[A-Za-z0-9._/ -]{1,200}$")


@app.get("/api/dokumente")
def api_dokumente(request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    gelesen = db_gelesen(un)
    dokumente = [dict(d, gelesen=d["pfad"] in gelesen)
                 for d in index_aktuell()["dokumente"]]
    return JSONResponse({"dokumente": dokumente,
                         "ungelesen": sum(1 for d in dokumente if not d["gelesen"])})


@app.get("/api/dokument/{pfad:path}")
def api_dokument(pfad: str, request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if not ABLAGE_PFAD_RE.match(pfad) or ".." in pfad:
        return JSONResponse({"fehler": "ungültiger Pfad"}, status_code=400)
    daten = git_show(pfad)
    if daten is None:
        return JSONResponse({"fehler": "unbekanntes Dokument"}, status_code=404)
    endung = Path(pfad).suffix.lower()
    typ = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
           ".png": "image/png", ".json": "application/json",
           ".csv": "text/csv; charset=windows-1252"}.get(endung, "application/octet-stream")
    return Response(content=daten, media_type=typ,
                    headers={"Cache-Control": "private, max-age=3600",
                             "Content-Disposition": f'inline; filename="{Path(pfad).name}"'})


# Sidecars eines Dokuments — beim Löschen gehen sie mit.
DOKUMENT_BEIAKTEN = (".meta.json", ".erklaerung.json", ".vertrag.json")


@app.post("/api/dokument-loeschen")
async def api_dokument_loeschen(request: Request) -> Response:
    """Ein Dokument wegnehmen — Post vom Amt, Kanzlei-Post, ein Vertrag.

    Nur was unter `dokumente/` liegt: Kassenbuch, Kontoauszüge, Stapel und
    Jahresabschluss musst du aufbewahren, die bleiben.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Unterlagen löschen darf die Inhaberin."},
                            status_code=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    pfad = str((body or {}).get("pfad", ""))
    if not DOKUMENT_PFAD_RE.match(pfad) or ".." in pfad:
        return JSONResponse(
            {"fehler": "Kassenbuch, Kontoauszüge und Stapel musst du aufbewahren "
                       "— die bleiben."}, status_code=400)
    pfade = [pfad] + [pfad + a for a in DOKUMENT_BEIAKTEN]

    import boxschreiber  # noqa: PLC0415
    try:
        commit = await run_in_threadpool(boxschreiber.loeschen, pfade,
                                         f"geloescht: {Path(pfad).name}", un)
    except boxschreiber.NichtsZuLoeschen:
        return JSONResponse({"fehler": "unbekanntes Dokument"}, status_code=404)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit, "pfad": pfad})


@app.post("/api/dokumente")
async def api_dokument_hochladen(request: Request, name: str = "dokument.pdf",
                                 titel: str = "", art: str = "dokument") -> Response:
    un, fehler = _box_wache(request)
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
        commit = await run_in_threadpool(boxschreiber.schreiben,
            {f"dokumente/{monat}/{dateiname}": daten,
             f"dokumente/{monat}/{dateiname}.meta.json": meta},
            None, f"dokument: {dateiname}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"}, status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    if art[:40] == "vertrag":
        threading.Thread(target=_vertrag_job,
                         args=(f"dokumente/{monat}/{dateiname}", daten, name, un),
                         daemon=True).start()
    if art[:40] == "behoerde":
        # Brief vom Amt: im Hintergrund lesen und einfach erklären.
        threading.Thread(target=_brief_job,
                         args=(f"dokumente/{monat}/{dateiname}", daten, name, un),
                         daemon=True).start()
    return JSONResponse({"ok": True, "commit": commit,
                         "pfad": f"dokumente/{monat}/{dateiname}"})


@app.post("/api/dokument-gelesen")
async def api_dokument_gelesen(request: Request) -> Response:
    un, fehler = _box_wache(request)
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
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if not darf_verwalten(un):
        return JSONResponse({"fehler": "nur für die Kanzlei"}, status_code=403)
    if not NAME_RE.match(stamm):
        return JSONResponse({"fehler": "ungültiger Name"}, status_code=400)
    if stamm not in (await run_in_threadpool(index_aktuell))["belege"]:
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
        commit = await run_in_threadpool(boxschreiber.schreiben,
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
    un, fehler = _box_wache(request)
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
            geparst = await run_in_threadpool(ka.parse_pdf, tf.name)
        except Exception:  # noqa: BLE001
            geparst = {"umsaetze": [], "monat": None, "konto": None}
    if not geparst["umsaetze"] or not geparst["monat"]:
        return JSONResponse({"fehler": "Diesen Auszug konnte ich nicht lesen — "
                             "ist es das Original-PDF der Bank?"}, status_code=422)
    import boxschreiber  # noqa: PLC0415
    dateiname = boxschreiber.beleg_dateiname(name)
    monat = geparst["monat"]
    try:
        commit = await run_in_threadpool(boxschreiber.schreiben,
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
    un, fehler = _box_wache(request)
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
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    pfad = str(body.get("pfad", ""))
    idx = await run_in_threadpool(index_aktuell)
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
        commit = await run_in_threadpool(boxschreiber.schreiben, f"freigaben/{name}.json", inhalt,
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
                          "filialen", "mehrere_unternehmen", "abschluss_art",
                          # Umsatzprofil: steuert, was das Kassenbuch fragt
                          "ust_sieben_prozent", "verkauft_gutscheine",
                          "personal_monat",
                          # Rechnungen: was auf den Kopf gehört, und wann eine
                          # Rechnung als Erlös zählt (ist = wenn bezahlt wird).
                          "anschrift", "ust_id", "iban", "bank", "versteuerung",
                          # Briefkopf der Rechnung
                          "marke_farbe", "marke_schrift", "marke_ausrichtung",
                          "marke_linie", "marke_begruendung",
                          # Wann der Laden auf hat — der Kalender braucht es.
                          "oeffnet", "schliesst"}


# Registrierung: Interessentinnen hinterlassen alle Daten — der Zugang wird
# danach persönlich eingerichtet (Allowlist bleibt der Schalter). Ohne Auth,
# aber Origin-Check, einfaches Rate-Limit je IP und strikte Feld-Whitelist.
# Was beim Einrichten erfragt wird. „anschrift" und „iban" stehen hier, weil
# eine Rechnung ohne Anschrift nach § 14 UStG keine ist — wer das erst beim
# Rechnungschreiben merkt, sitzt im falschen Moment vor einem leeren Feld.
REG_FELDER = ("salon", "name", "email", "telefon", "anschrift", "rechtsform",
              "steuernummer", "finanzamt", "kleinunternehmer", "iban",
              "steuerberater", "nachricht")
_REG_ZULETZT: dict[str, float] = {}


@app.post("/api/registrierung")
def api_registrierung(daten: dict, request: Request) -> Response:
    if not _origin_ok(request):
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    ip = _client_ip(request)
    jetzt = time.time()
    if jetzt - _REG_ZULETZT.get(ip, 0.0) < 30:
        return JSONResponse({"fehler": "kurz warten, dann nochmal"}, status_code=429)
    sauber = {k: str(daten.get(k, "") or "")[:200].strip() for k in REG_FELDER}
    if not sauber["salon"] or "@" not in sauber["email"]:
        return JSONResponse({"fehler": "Salon-Name und E-Mail brauchen wir mindestens"},
                            status_code=400)
    _REG_ZULETZT[ip] = jetzt
    _zaehler_aufraeumen(_REG_ZULETZT, jetzt, 3600)
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
    ip = _client_ip(request)
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
                      passwort=passwort, box=False) is None:
        return JSONResponse({"fehler": "Für diese E-Mail gibt es schon einen Zugang — melde dich einfach an."},
                            status_code=409)
    _REG_ZULETZT[ip] = jetzt
    _zaehler_aufraeumen(_REG_ZULETZT, jetzt, 3600)
    vorbelegung = {"betrieb_name": sauber["salon"], "rechtsform": sauber["rechtsform"],
                   "steuernummer": sauber["steuernummer"], "finanzamt": sauber["finanzamt"],
                   "kleinunternehmer": sauber["kleinunternehmer"],
                   "steuerberater_status": sauber["steuerberater"],
                   "telefon": sauber["telefon"], "email": email,
                   # Alles, was später auf der Rechnung stehen muss.
                   "anschrift": sauber["anschrift"], "iban": sauber["iban"]}
    for schluessel, wert in vorbelegung.items():
        if wert:
            db_einstellung_setzen(email, schluessel, str(wert)[:200])
    with _DB_LOCK, _db() as c:
        c.execute("INSERT INTO registrierungen (zeit, daten, status) VALUES (?, ?, 'selbst registriert')",
                  (_jetzt_iso(), json.dumps(sauber, ensure_ascii=False)))
    print(f"[signup] {sauber['salon']} <{email}>", flush=True)
    exp = int(time.time()) + SESSION_DAUER
    antwort = JSONResponse({"un": email, "rolle": "salon",
                            "box": box_mitglied(email)})
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


def salon_von(un: str) -> str:
    """Die Belegbox gehört dem Salon — Mitarbeiterinnen arbeiten darin mit."""
    n = nutzer_holen(un)
    if n and n.get("gehoert_zu"):
        return n["gehoert_zu"]
    return un


def team_recht(un: str, recht: str) -> bool:
    """Darf diese Mitarbeiterin das? Die Inhaberin darf immer alles."""
    n = nutzer_holen(un)
    if not n or not n.get("gehoert_zu"):
        return True                     # Inhaberin oder Kanzlei
    with _DB_LOCK, _db() as c:
        zeile = c.execute(
            f"SELECT {recht} FROM team WHERE zugang=? AND un=? AND aktiv=1",
            (un, n["gehoert_zu"])).fetchone()
    return bool(zeile and zeile[0])


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
                   "aktiv": bool(z[4]), "angelegt": z[5], "letzter_login": z[6],
                   "box": bool(z[7])}
                  for z in c.execute("""SELECT email, name, salon, rolle, aktiv,
                      angelegt, letzter_login, box FROM nutzer
                      ORDER BY angelegt DESC""")]
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
    elif aktion in ("box_freigeben", "box_sperren"):
        # Der Schalter, mit dem aus einer Registrierung ein echter Zugang wird.
        with _DB_LOCK, _db() as c:
            c.execute("UPDATE nutzer SET box=? WHERE email=?",
                      (1 if aktion == "box_freigeben" else 0, email))
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
                   "anschrift": daten.get("anschrift", ""),
                   "iban": daten.get("iban", ""),
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
    un, fehler = _box_wache(request)
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
    un, fehler = _box_wache(request)
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
    un, fehler = _box_wache(request)
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
    # Der Chat antwortet aus den Belegen — also gilt hier dieselbe Grenze.
    if not zugelassen(un) or not box_mitglied(un):
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    frage = str(body.get("frage", "")).strip()
    if not frage or len(frage) > 2000:
        return JSONResponse({"fehler": "frage fehlt oder zu lang"}, status_code=400)

    # Das Gespräch: entweder ein bestehendes fortsetzen oder eines beginnen.
    gespraech_id = body.get("gespraech")
    try:
        gespraech_id = int(gespraech_id) if gespraech_id else None
    except (TypeError, ValueError):
        gespraech_id = None
    if gespraech_id is not None and not gespraech_gehoert(un, gespraech_id):
        return JSONResponse({"fehler": "unbekanntes Gespräch"}, status_code=404)
    if gespraech_id is None:
        gespraech_id = gespraech_anlegen(un, frage)

    import wissen  # noqa: PLC0415
    kontext = wissen.kontext(frage, _welt_fuer(un))
    verlauf = verlauf_lesen(gespraech_id)
    nachricht_anhaengen(gespraech_id, "user", frage)
    payload = {
        "model": GEMMA_MODELL,
        "temperature": 0.2,
        "max_tokens": 700,
        "messages": [
            {"role": "system", "content":
                "Du bist der Assistent von babu (0711 Intelligence) für "
                "Friseursalons. Du sprichst mit der Inhaberin. Antworte auf "
                "Deutsch, knapp, konkret und in ganzen Sätzen. Keine "
                "Sie-Anrede — neutrale Formen oder Du. Kein Technik-Vokabular, "
                "keine Systemnamen.\n\n"
                "DU BIST FÜR ALLES DA, was ihren Betrieb angeht — nicht nur "
                "für Steuern:\n"
                "· Ihre eigenen Zahlen und Unterlagen: Belege, Kasse, "
                "Verträge, gestellte Rechnungen, Termine, Team, Post vom Amt. "
                "Das beantwortest du AUSSCHLIESSLICH aus den mitgelieferten "
                "Daten und nennst, worauf du dich stützt. Steht etwas nicht "
                "darin, sagst du das offen und rätst nicht.\n"
                "· Steuer und Recht im Salon-Alltag: Kleinunternehmer-Regel, "
                "Kassenpflicht, was absetzbar ist, Aufbewahrung, Fristen. "
                "Einfach erklärt, mit dem Hinweis, dass es eine erste "
                "Einordnung ist.\n"
                "· Führen und Organisieren: Preise und Kalkulation, "
                "Terminplanung, Auslastung, Personal und Ausbildung, "
                "Einkauf und Lieferanten, Kundinnenbindung, Reklamationen, "
                "schwierige Gespräche, Werbung, Hygiene und Arbeitsschutz.\n"
                "· Und wenn ihr der Kopf raucht: hör zu, ordne, und mach "
                "einen ersten Schritt daraus. Sie führt einen Betrieb allein "
                "— oft ist die Frage hinter der Frage die wichtigere.\n\n"
                "SO ANTWORTEST DU: Erst die Antwort, dann die Begründung. "
                "Beträge deutsch (1.234,56 €). Wenn du rechnest, zeig die "
                "Rechnung. Bei mehreren Möglichkeiten nenne eine Empfehlung, "
                "keine Liste von Optionen.\n\n"
                "DEINE GRENZEN, und du benennst sie: Du bist keine "
                "Steuerberatung, keine Rechtsberatung und keine ärztliche "
                "Auskunft. Bei Kündigungen, Verträgen mit Folgen, "
                "Betriebsprüfungen, Streit mit dem Finanzamt und allem, wo "
                "Fristen laufen, verweist du auf ihre Ansprechperson — und "
                "sagst trotzdem, was du zur Sache weißt, damit sie "
                "vorbereitet ins Gespräch geht. Erfinde nie Zahlen, Paragrafen "
                "oder Fristen. Was du nicht weißt, sagst du."},
            *verlauf,
            {"role": "user", "content":
                f"WAS BABU ÜBER DIESEN SALON WEISS:\n{kontext}\n\nFRAGE: {frage}"},
        ],
    }

    # SSE-Streaming (App): Text-Deltas von vLLM direkt durchreichen.
    if body.get("stream"):
        payload["stream"] = True

        def sse():
            gesammelt: list[str] = []
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
                            gesammelt.append(delta)
                            yield "data: " + json.dumps({"d": delta}, ensure_ascii=False) + "\n\n"
            except Exception:  # noqa: BLE001
                yield "data: " + json.dumps({"fehler": "Gemma nicht erreichbar"}) + "\n\n"
            if gesammelt:
                nachricht_anhaengen(gespraech_id, "assistant", "".join(gesammelt))
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Gespraech": str(gespraech_id)})

    try:
        r = requests.post(GEMMA_API, json=payload, timeout=120)
        r.raise_for_status()
        antwort = r.json()["choices"][0]["message"]["content"].strip()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "Gemma nicht erreichbar",
                             "gespraech": gespraech_id}, status_code=502)
    nachricht_anhaengen(gespraech_id, "assistant", antwort)
    return JSONResponse({"antwort": antwort, "gespraech": gespraech_id})


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
    un, fehler = _box_wache(request)
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
        commit = await run_in_threadpool(boxschreiber.schreiben,
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
    un, fehler = _box_wache(request)
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
    un, fehler = _box_wache(request)
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


# Verträge und Dauerkosten: Miete, Versicherung, Leasing, Wartung. Diese
# Kosten kommen oft NICHT als Beleg — ohne sie fehlt in der Auswertung
# genau das, was jeden Monat sicher abgeht.
VERTRAG_ARTEN = {
    "miete": ("Mietvertrag", "6310"),
    "versicherung": ("Versicherung", "6400"),
    "leasing": ("Leasing", "6530"),
    "strom": ("Strom, Gas, Wasser", "6325"),
    "telefon": ("Telefon und Internet", "6805"),
    "wartung": ("Wartung und Technik", "6837"),
    "arbeitsvertrag": ("Arbeitsvertrag", "6020"),
    "sonstiges": ("Sonstiger Vertrag", "6850"),
}


# Wiederkehrende Beträge auf den Monat umrechnen.
VERTRAG_TAKT = {"monatlich": 1, "vierteljaehrlich": 3, "halbjaehrlich": 6,
                "jaehrlich": 12}


def vertrag_lesen(daten: bytes, name: str, llm=None) -> dict:
    """Vertrag fotografiert → was er monatlich kostet und wann er läuft."""
    import abschluss_lesen  # noqa: PLC0415
    if llm is None:
        llm = abschluss_lesen.llm_json
    frage = (
        "Das ist ein Vertrag eines Friseursalons (Miete, Versicherung, "
        "Leasing, Strom, Telefon, Wartung oder Arbeitsvertrag). Lies die "
        "Eckdaten. Gib NUR JSON zurück: "
        '{"art": "miete|versicherung|leasing|strom|telefon|wartung|'
        'arbeitsvertrag|sonstiges", '
        '"partner": "Name des Vertragspartners", '
        '"betrag_text": "der wiederkehrende Gesamtbetrag GENAU so wie er im '
        'Vertrag steht, z. B. 1.250,00 EUR — nicht umrechnen, nicht runden", '
        '"zahlweise": "monatlich|vierteljaehrlich|halbjaehrlich|jaehrlich|einmalig", '
        '"umsatzsteuer": "zzgl|inkl|keine — steht der Betrag zuzüglich '
        'Umsatzsteuer, ist sie schon enthalten, oder fällt keine an?", '
        '"beginn": "JJJJ-MM-TT oder null", '
        '"laufzeit_bis": "JJJJ-MM-TT oder null", '
        '"kuendigungsfrist": "kurz, z. B. 3 Monate zum Quartalsende, oder null", '
        '"einfach": "2 Sätze in du-Form: was der Vertrag kostet und was wichtig ist"}. '
        "Rate nie — was nicht dasteht, ist null.")
    import tempfile  # noqa: PLC0415
    endung = Path(name).suffix.lower() or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=endung) as f:
        f.write(daten)
        f.flush()
        texte = abschluss_lesen.seiten_text(f.name) if endung == ".pdf" else []
        if texte and len((texte[0] or "").strip()) >= abschluss_lesen.TEXT_SCHWELLE:
            roh = llm([{"role": "user", "content":
                        frage + "\n\nVERTRAG:\n" + "\n\n".join(t[:6000] for t in texte[:6])}])
        else:
            bilder = abschluss_lesen.seiten_bilder(f.name)
            roh = llm([abschluss_lesen._bild_nachricht(frage, bilder[0])])

    art = str(roh.get("art") or "sonstiges").strip().lower()
    if art not in VERTRAG_ARTEN:
        art = "sonstiges"
    name_art, konto = VERTRAG_ARTEN[art]
    # Der Betrag kommt als Text und wird hier geparst — ein Sprachmodell
    # verschluckt sonst gern den Tausenderpunkt (1.250,00 → 12500).
    betrag = _zahl(str(roh.get("betrag_text") or "")
                   .replace("EUR", "").replace("€", "").strip())
    if betrag is not None and not 0 < betrag < 200_000:
        print(f"[vertrag] unplausibler Betrag verworfen: {betrag}", flush=True)
        betrag = None

    # Auf den Monat umrechnen: eine Jahresversicherung ist nicht der
    # Monatsbeitrag, und einmalige Beträge (Kaution) sind gar keine Dauerkosten.
    zahlweise = str(roh.get("zahlweise") or "monatlich").strip().lower()
    if betrag is not None:
        if zahlweise == "einmalig":
            betrag = None
        else:
            betrag = betrag / VERTRAG_TAKT.get(zahlweise, 1)

    # Die Auswertung rechnet netto. „1.487,50 € inkl. USt" wären sonst
    # 19 % zu hohe Raumkosten.
    umsatzsteuer = str(roh.get("umsatzsteuer") or "").strip().lower()
    if betrag is not None and umsatzsteuer.startswith("inkl"):
        betrag = betrag / 1.19
    if betrag is not None and not 0 < betrag < 50_000:
        print(f"[vertrag] unplausibler Monatsbetrag verworfen: {betrag}", flush=True)
        betrag = None
    return {
        "art": art, "art_name": name_art, "konto_skr04": konto,
        "partner": str(roh.get("partner") or "").strip()[:80] or None,
        "betrag_monat": round(betrag, 2) if betrag else None,
        "beginn": str(roh.get("beginn") or "").strip()[:10] or None,
        "laufzeit_bis": str(roh.get("laufzeit_bis") or "").strip()[:10] or None,
        "kuendigungsfrist": str(roh.get("kuendigungsfrist") or "").strip()[:120] or None,
        "zahlweise": zahlweise if zahlweise in VERTRAG_TAKT else "monatlich",
        "umsatzsteuer": umsatzsteuer[:6] or None,
        "einfach": str(roh.get("einfach") or "").strip()[:400],
    }


def _vertrag_job(pfad: str, daten: bytes, name: str, un: str) -> None:
    import boxschreiber  # noqa: PLC0415
    try:
        with _LLM_SEMAPHORE:
            vertrag = vertrag_lesen(daten, name)
        boxschreiber.schreiben(
            pfad + ".vertrag.json",
            json.dumps(vertrag, ensure_ascii=False, indent=1).encode(),
            f"vertrag: {name}", un)
        with _INDEX_LOCK:
            _INDEX["geprueft"] = 0.0
    except Exception as e:  # noqa: BLE001
        print(f"[vertrag] {pfad} nicht gelesen: {e}", flush=True)


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
                     "gutscheineEingeloest", "gutscheinVerkauf",
                     "umsatzFrei", "umsatz7",
                     "barabhebungBank", "ecZahlungen", "trinkgeldTeamEC",
                     "sonstigeAusgaben", "privatentnahmen", "einzahlungBank",
                     "gezaehltSchluss")
KASSENBUCH_NOTIZEN = ("differenzGrund", "sonstigeNotiz")
# Trinkgeld je Person: [{"name": "Jana", "betrag": 12.50}]. Für das Team
# steuerfrei (§ 3 Nr. 51 EStG) — dokumentiert wird es, damit bei einer
# Kassenprüfung erklärbar ist, warum Geld die Schublade verlässt.
TRINKGELD_MAX = 20
_KASSEN_DATUM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------
# Ablage: alle Unterlagen an einem Ort, nach Jahr und Art sortiert — damit
# sichtbar ist, dass die Aufbewahrungspflichten erfüllt sind.
# ---------------------------------------------------------------------------

ABLAGE_ARTEN = {
    "behoerde": ("Post vom Amt", "Bescheide, Schreiben und Fristen"),
    "kanzlei": ("Von deiner Kanzlei", "Auswertungen, Lohnunterlagen, Post"),
    "vertrag": ("Verträge", "Miete, Versicherung, Leasing — deine Dauerkosten"),
    "abschluss": ("Jahresabschluss", "EÜR, Bilanz, Anlagen, Bescheide"),
    "kontoauszug": ("Kontoauszüge", "Deine Bankunterlagen"),
    "export": ("Buchungsstapel", "Übergaben an die Buchhaltung"),
    "kassenbuch": ("Kassenbuch", "Deine Tagesblätter"),
    "rechnung": ("Rechnungen", "Was du anderen in Rechnung gestellt hast"),
}


def _jahr_aus(pfad: str, zeit: str | None) -> str:
    for teil in pfad.split("/"):
        if len(teil) >= 4 and teil[:4].isdigit() and "2000" < teil[:4] < "2100":
            return teil[:4]
    return (zeit or "")[:4] or "ohne Jahr"


@app.get("/api/ablage")
def api_ablage(request: Request) -> Response:
    """Alles Abgelegte als Ordnerbaum: Jahr → Art → Dokumente."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    index = index_aktuell()
    zeiten = index["zeiten"]
    eintraege: list[dict] = []

    for d in index["dokumente"]:
        art = d.get("art") or "kanzlei"
        if art not in ABLAGE_ARTEN:
            art = "kanzlei"
        eintraege.append({"pfad": d["pfad"], "titel": d["titel"], "art": art,
                          "zeit": d.get("zeit"), "gelesen": d.get("gelesen"),
                          "erklaerung": d.get("erklaerung"),
                          "vertrag": d.get("vertrag"),
                          "loeschbar": True})

    # Kontoauszüge, Abschlüsse, Stapel und Kassenblätter direkt aus dem Baum.
    kopf = _git(["rev-parse", "HEAD"])
    baum = _git(["ls-tree", "-r", "--name-only", (kopf or "HEAD").strip()]) or ""
    for pfad in baum.splitlines():
        if pfad.endswith((".umsaetze.json", ".meta.json", ".erklaerung.json")):
            continue
        name = pfad.rsplit("/", 1)[-1]
        if pfad.startswith("auszuege/"):
            art, titel = "kontoauszug", name
        elif pfad.startswith("abschluss/") and not name.startswith("kennzahlen"):
            art, titel = "abschluss", name
        elif pfad.startswith("export/") and pfad.endswith(".csv"):
            art, titel = "export", name
        elif pfad.startswith("kassenbuch/"):
            art, titel = "kassenbuch", "Kassenbuch " + name.removesuffix(".json")
        elif pfad.startswith("rechnungen/") and pfad.endswith(".pdf"):
            art, titel = "rechnung", "Rechnung " + name.removesuffix(".pdf")
        else:
            continue
        # Aufbewahrungspflichtig: die Oberfläche zeigt hier keinen Knopf, und
        # die Lösch-Route nimmt diese Pfade ohnehin nicht an.
        eintraege.append({"pfad": pfad, "titel": titel, "art": art,
                          "zeit": (zeiten.get(pfad) or {}).get("zeit"),
                          "gelesen": None, "erklaerung": None, "vertrag": None,
                          "loeschbar": False})

    jahre: dict[str, dict] = {}
    for e in eintraege:
        jahr = _jahr_aus(e["pfad"], e["zeit"])
        ordner = jahre.setdefault(jahr, {})
        ordner.setdefault(e["art"], []).append(e)

    ausgabe = []
    for jahr in sorted(jahre, reverse=True):
        arten = []
        for art, (name, hinweis) in ABLAGE_ARTEN.items():
            stuecke = jahre[jahr].get(art)
            if not stuecke:
                continue
            stuecke.sort(key=lambda x: x["zeit"] or "", reverse=True)
            arten.append({"art": art, "name": name, "hinweis": hinweis,
                          "anzahl": len(stuecke), "stuecke": stuecke})
        ausgabe.append({"jahr": jahr, "anzahl": sum(a["anzahl"] for a in arten),
                        "arten": arten})
    return JSONResponse({"jahre": ausgabe,
                         "gesamt": sum(j["anzahl"] for j in ausgabe)})


# ---------------------------------------------------------------------------
# Rechnungen stellen: die dritte Geldsorte. Belege gehen raus, das Kassenbuch
# nimmt ein — hier stellt der Salon selbst etwas in Rechnung (Stuhlmiete,
# Firmenkunden). Die Nummer vergibt der Server, damit die Folge lückenlos
# bleibt; das PDF baut die App und reicht es nach.
# ---------------------------------------------------------------------------

RECHNUNG_NUMMER_RE = re.compile(r"^\d{4}-\d{4}$")


def _rechnungen_lesen() -> list[dict]:
    """Alle festgeschriebenen Rechnungen aus dem Index."""
    idx = index_aktuell()
    return list(idx.get("rechnungen", {}).values())


def _versteuerung(un: str) -> str:
    wert = (db_einstellungen(salon_von(un)).get("versteuerung") or "ist").lower()
    return "soll" if wert == "soll" else "ist"


@app.get("/api/rechnungen")
def api_rechnungen(request: Request, jahr: int = 0) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    import rechnungen as re_  # noqa: PLC0415
    alle = _rechnungen_lesen()
    if jahr:
        alle = [r for r in alle if str(r.get("nummer", "")).startswith(f"{jahr}-")]
    alle.sort(key=lambda r: r.get("nummer") or "", reverse=True)
    zeilen = [dict(r, stand=re_.stand(r)) for r in alle]
    offen = [z for z in zeilen if z["stand"] == "offen"]
    return JSONResponse({
        "rechnungen": zeilen,
        "offen_anzahl": len(offen),
        "offen_summe": round(sum(float(z.get("brutto") or 0) for z in offen), 2),
        "versteuerung": _versteuerung(un),
    })


@app.post("/api/rechnungen")
async def api_rechnung_stellen(request: Request) -> Response:
    """Rechnung festschreiben — der Server vergibt die nächste Nummer.

    Erst danach baut die App das PDF (mit genau dieser Nummer) und reicht es
    nach. Reißt es dazwischen ab, existiert die Rechnung mit ihrer Nummer
    und das PDF lässt sich nachreichen — keine Lücke in der Folge.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Rechnungen stellt die Inhaberin."},
                            status_code=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)

    import rechnungen as re_  # noqa: PLC0415
    datum = str((body or {}).get("datum") or time.strftime("%Y-%m-%d"))[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum):
        return JSONResponse({"fehler": "Datum als JJJJ-MM-TT"}, status_code=400)

    einstellungen = db_einstellungen(salon_von(un))
    with _RECHNUNG_SCHLOSS:
        vorhandene = [r.get("nummer") for r in _rechnungen_lesen()]
        nummer = re_.naechste_nummer(vorhandene, int(datum[:4]))
        try:
            rechnung = re_.aufbauen(
                nummer=nummer, datum=datum,
                empfaenger=(body or {}).get("empfaenger") or {},
                positionen=(body or {}).get("positionen") or [],
                stammdaten=einstellungen,
                leistungszeitpunkt=(body or {}).get("leistungszeitpunkt"),
                hinweis_frei=str((body or {}).get("hinweis") or ""))
        except re_.RechnungFehler as e:
            return JSONResponse({"fehler": str(e)}, status_code=400)

        maengel = re_.fehlende_pflichtangaben(rechnung)
        if maengel:
            return JSONResponse({"fehler": maengel[0], "fehlt": maengel},
                                status_code=400)
        rechnung["gestellt_von"] = un
        rechnung["gestellt_am"] = _jetzt_iso()

        import boxschreiber  # noqa: PLC0415
        pfad = f"rechnungen/{datum[:7]}/{nummer}.json"
        try:
            commit = await run_in_threadpool(
                boxschreiber.schreiben, pfad,
                json.dumps(rechnung, ensure_ascii=False, indent=1).encode(),
                f"rechnung: {nummer}", un)
        except boxschreiber.SchreibFehler:
            return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                                status_code=503)
        with _INDEX_LOCK:
            _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit, "nummer": nummer,
                         "pfad": pfad, "rechnung": rechnung})


def _rechnung_holen(nummer: str) -> tuple[dict | None, str | None]:
    for r in _rechnungen_lesen():
        if r.get("nummer") == nummer:
            return r, f"rechnungen/{(r.get('datum') or '')[:7]}/{nummer}.json"
    return None, None


@app.post("/api/rechnung/{nummer}/pdf")
async def api_rechnung_pdf(nummer: str, request: Request) -> Response:
    """Das PDF nachreichen — gebaut hat es die App, aufbewahrt wird es hier."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if not RECHNUNG_NUMMER_RE.match(nummer):
        return JSONResponse({"fehler": "ungültige Nummer"}, status_code=400)
    rechnung, _ = _rechnung_holen(nummer)
    if rechnung is None:
        return JSONResponse({"fehler": "unbekannte Rechnung"}, status_code=404)
    daten = await request.body()
    if not daten or not daten.startswith(b"%PDF"):
        return JSONResponse({"fehler": "bitte als PDF"}, status_code=400)
    if len(daten) > HOCHLADEN_MAX:
        return JSONResponse({"fehler": "zu groß"}, status_code=413)
    import boxschreiber  # noqa: PLC0415
    pfad = f"rechnungen/{(rechnung.get('datum') or '')[:7]}/{nummer}.pdf"
    try:
        commit = await run_in_threadpool(boxschreiber.schreiben, pfad, daten,
                                         f"rechnung: {nummer} (PDF)", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit, "pfad": pfad})


@app.post("/api/rechnung/{nummer}/bezahlt")
async def api_rechnung_bezahlt(nummer: str, request: Request) -> Response:
    """„Bezahlt am" setzen — bei Ist-Versteuerung zählt erst das als Umsatz."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if not RECHNUNG_NUMMER_RE.match(nummer):
        return JSONResponse({"fehler": "ungültige Nummer"}, status_code=400)
    rechnung, pfad = _rechnung_holen(nummer)
    if rechnung is None:
        return JSONResponse({"fehler": "unbekannte Rechnung"}, status_code=404)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    am = str((body or {}).get("am") or time.strftime("%Y-%m-%d"))[:10]
    if am and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", am):
        return JSONResponse({"fehler": "Datum als JJJJ-MM-TT"}, status_code=400)
    rechnung = dict(rechnung, bezahlt_am=am or None)

    import boxschreiber  # noqa: PLC0415
    try:
        commit = await run_in_threadpool(
            boxschreiber.schreiben, pfad,
            json.dumps(rechnung, ensure_ascii=False, indent=1).encode(),
            f"rechnung: {nummer} bezahlt", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit, "bezahlt_am": am or None})


@app.post("/api/rechnung/{nummer}/storno")
async def api_rechnung_storno(nummer: str, request: Request) -> Response:
    """Eine falsche Rechnung wird nicht gelöscht, sondern storniert."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Rechnungen stellt die Inhaberin."},
                            status_code=403)
    if not RECHNUNG_NUMMER_RE.match(nummer):
        return JSONResponse({"fehler": "ungültige Nummer"}, status_code=400)
    original, pfad_alt = _rechnung_holen(nummer)
    if original is None:
        return JSONResponse({"fehler": "unbekannte Rechnung"}, status_code=404)
    if original.get("storniert_durch"):
        return JSONResponse({"fehler": "Diese Rechnung ist schon storniert."},
                            status_code=409)

    import rechnungen as re_  # noqa: PLC0415
    import boxschreiber  # noqa: PLC0415
    datum = time.strftime("%Y-%m-%d")
    with _RECHNUNG_SCHLOSS:
        vorhandene = [r.get("nummer") for r in _rechnungen_lesen()]
        neue_nummer = re_.naechste_nummer(vorhandene, int(datum[:4]))
        try:
            gegen = re_.storno(original, nummer=neue_nummer, datum=datum)
        except re_.RechnungFehler as e:
            return JSONResponse({"fehler": str(e)}, status_code=400)
        gegen["gestellt_von"] = un
        gegen["gestellt_am"] = _jetzt_iso()
        markiert = dict(original, storniert_durch=neue_nummer)
        try:
            commit = await run_in_threadpool(
                boxschreiber.schreiben,
                {f"rechnungen/{datum[:7]}/{neue_nummer}.json":
                    json.dumps(gegen, ensure_ascii=False, indent=1).encode(),
                 pfad_alt: json.dumps(markiert, ensure_ascii=False, indent=1).encode()},
                None, f"storno: {nummer} durch {neue_nummer}", un)
        except boxschreiber.SchreibFehler:
            return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                                status_code=503)
        with _INDEX_LOCK:
            _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit, "nummer": neue_nummer,
                         "rechnung": gegen})


# ---------------------------------------------------------------------------
# Die Vertragskiste: was jeden Monat sicher abgeht — und wann zu handeln ist.
# ---------------------------------------------------------------------------

def _geklaert_lesen() -> dict:
    """Was zu fehlenden Belegen schon geklärt wurde. Liegt in der Belegbox:
    „war privat" ist eine buchhalterische Aussage und gehört zum Prüfpfad."""
    roh = git_show("auszuege/geklaert.json")
    if roh is None:
        return {}
    try:
        d = json.loads(roh)
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


@app.get("/api/monatslauf")
def api_monatslauf(request: Request) -> Response:
    """Welcher Monat wartet — und was fehlt ihm noch?

    Der Abschluss war eine Aufgabe, die man sich merken musste. Jetzt liegt
    er ab dem 3. von selbst da, samt Zahlen, und braucht nur noch einen
    Blick.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Die Zahlen sieht nur die Inhaberin."},
                            status_code=403)
    import datetime as dt  # noqa: PLC0415
    import monatslauf as ml  # noqa: PLC0415

    heute = dt.date.today()
    monat = ml.faelliger_monat(heute)
    if monat is None:
        return JSONResponse({"faellig": False,
                             "satz": "Gerade wartet nichts auf dich."})

    idx = index_aktuell()
    freigegeben = git_show(f"abschluss/{monat}/ustva.json") is not None
    fehlende = _fehlende_belege_fuer(monat)
    stand = ml.stand(monat, list(idx["belege"].values()), fehlende,
                     freigegeben, heute)

    # Die Zahlen gleich mitliefern — sonst ist es wieder eine Aufgabe.
    zahlen = None
    if not freigegeben:
        antwort = api_monatsabschluss(monat, request)
        if antwort.status_code == 200:
            d = json.loads(antwort.body)
            zahlen = {"erloese": (d.get("erloese") or {}).get("brutto_gesamt"),
                      "zahllast": (d.get("ustva") or {}).get("zahllast"),
                      "ergebnis": (d.get("bwa") or {}).get("ergebnis")}
    return JSONResponse({"faellig": True, **stand, "zahlen": zahlen})


def _fehlende_belege_fuer(monat: str) -> list[dict]:
    """Abbuchungen dieses Monats ohne Beleg — für den Monatslauf."""
    import belegjagd as bj  # noqa: PLC0415
    import kontoauszug as ka  # noqa: PLC0415
    idx = index_aktuell()
    umsaetze = idx["umsaetze"].get(monat) or []
    if not umsaetze:
        return []
    ergebnis = ka.abgleich(umsaetze, list(idx["belege"].values()))
    return bj.offene_fragen(ergebnis["fehlend"], vertraege_aktuell(),
                            set(_geklaert_lesen()))


@app.get("/api/fehlende-belege")
def api_fehlende_belege(request: Request) -> Response:
    """Wozu vom Konto Geld abging, ohne dass ein Beleg da ist.

    Das ist die Frage, die am Jahresende Geld kostet — und die sich nur
    beantworten lässt, solange die Erinnerung frisch ist.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Die Zahlen sieht nur die Inhaberin."},
                            status_code=403)
    import belegjagd as bj  # noqa: PLC0415
    import kontoauszug as ka  # noqa: PLC0415

    idx = index_aktuell()
    umsaetze = [u for liste in idx["umsaetze"].values() for u in liste]
    if not umsaetze:
        return JSONResponse({"auszug_da": False, "fragen": [], "summe": 0.0})
    ergebnis = ka.abgleich(umsaetze, list(idx["belege"].values()))
    geklaert = _geklaert_lesen()
    fragen = bj.offene_fragen(ergebnis["fehlend"], vertraege_aktuell(),
                              set(geklaert))
    return JSONResponse({
        "auszug_da": True,
        "fragen": fragen,
        "summe": round(sum(f["betrag"] for f in fragen), 2),
        "gruende": [{"schluessel": k, "name": v} for k, v in bj.GRUENDE.items()],
    })


@app.post("/api/fehlende-belege/klaeren")
async def api_fehlende_belege_klaeren(request: Request) -> Response:
    """„War privat" oder „dafür gibt es keinen Beleg" — einmal gesagt, nie
    wieder gefragt. Und nachvollziehbar, weil es in der Box steht."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
    try:
        body = await request.json()
        schluessel = str((body or {}).get("schluessel") or "")
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    if not re.fullmatch(r"[0-9a-f]{16}", schluessel):
        return JSONResponse({"fehler": "unbekannter Eintrag"}, status_code=400)

    import belegjagd as bj  # noqa: PLC0415
    try:
        grund = bj.grund_pruefen(str((body or {}).get("grund") or ""))
    except bj.JagdFehler as e:
        return JSONResponse({"fehler": str(e)}, status_code=400)

    geklaert = _geklaert_lesen()
    geklaert[schluessel] = {"grund": grund, "von": un, "am": _jetzt_iso(),
                            "notiz": str((body or {}).get("notiz") or "")[:200]}
    import boxschreiber  # noqa: PLC0415
    try:
        commit = await run_in_threadpool(
            boxschreiber.schreiben, "auszuege/geklaert.json",
            json.dumps(geklaert, ensure_ascii=False, indent=1).encode(),
            f"geklaert: {bj.GRUENDE[grund]}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit, "grund": grund})


@app.get("/api/zahlungen")
def api_zahlungen(request: Request, monat: str = "") -> Response:
    """Wer hat bezahlt? Kontoauszug ↔ offene Rechnungen.

    Vorgeschlagen, nicht entschieden: ein „bezahlt" verschiebt Umsatz in die
    Voranmeldung. Bestätigt wird mit einem Tipp.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Die Zahlen sieht nur die Inhaberin."},
                            status_code=403)
    if monat and not re.fullmatch(r"\d{4}-\d{2}", monat):
        return JSONResponse({"fehler": "Monat als JJJJ-MM"}, status_code=400)
    import kontoauszug as ka  # noqa: PLC0415

    idx = index_aktuell()
    umsaetze: list[dict] = []
    for m, liste in idx["umsaetze"].items():
        if not monat or m == monat:
            umsaetze.extend(liste)
    if not umsaetze:
        return JSONResponse({"auszug_da": False, "vorschlaege": [],
                             "ohne_zuordnung": [], "mehrdeutig": []})
    ergebnis = ka.rechnungen_abgleich(umsaetze,
                                      list(idx.get("rechnungen", {}).values()))
    ergebnis["auszug_da"] = True
    return JSONResponse(ergebnis)


@app.post("/api/zahlungen/uebernehmen")
async def api_zahlungen_uebernehmen(request: Request) -> Response:
    """Einen Vorschlag bestätigen — die Rechnung gilt dann als bezahlt."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
    try:
        body = await request.json()
        nummer = str((body or {}).get("nummer") or "")
        am = str((body or {}).get("am") or "")[:10]
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    if not RECHNUNG_NUMMER_RE.match(nummer):
        return JSONResponse({"fehler": "ungültige Nummer"}, status_code=400)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", am):
        return JSONResponse({"fehler": "Datum als JJJJ-MM-TT"}, status_code=400)

    rechnung, pfad = _rechnung_holen(nummer)
    if rechnung is None:
        return JSONResponse({"fehler": "unbekannte Rechnung"}, status_code=404)
    if rechnung.get("bezahlt_am"):
        return JSONResponse({"ok": True, "schon": True})

    import boxschreiber  # noqa: PLC0415
    try:
        commit = await run_in_threadpool(
            boxschreiber.schreiben, pfad,
            json.dumps(dict(rechnung, bezahlt_am=am), ensure_ascii=False,
                       indent=1).encode(),
            f"rechnung: {nummer} bezahlt am {am}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit, "nummer": nummer,
                         "bezahlt_am": am})


def _termine_lesen(un: str, von: str, bis: str) -> list[dict]:
    with _DB_LOCK, _db() as c:
        zeilen = c.execute(
            """SELECT id, start, minuten, wer, kundin, leistung, notiz, abgesagt,
                      preis, ust_satz, abgerechnet, zahlart, kundin_id,
                      bestaetigt, quelle, telefon, zahlung_ref
               FROM termin WHERE un=? AND start>=? AND start<=? ORDER BY start""",
            (un, von, bis + "T23:59")).fetchall()
    return [{"id": z[0], "start": z[1], "minuten": z[2], "wer": z[3],
             "kundin": z[4], "leistung": z[5], "notiz": z[6],
             "abgesagt": bool(z[7]), "preis": z[8], "ust_satz": z[9],
             "abgerechnet": z[10], "zahlart": z[11], "kundin_id": z[12],
             # Aus WhatsApp kommt der Termin als Anfrage herein. Termine aus
             # der App gelten als bestätigt — sie hat sie selbst eingetragen.
             "bestaetigt": z[13] is None or bool(z[13]),
             "quelle": z[14] or "app", "telefon": z[15],
             "zahlung_ref": z[16]}
            for z in zeilen]


@app.get("/api/termine")
def api_termine(request: Request, von: str = "", bis: str = "") -> Response:
    """Die Termine eines Zeitraums — und was der Tag eingebracht hat."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    import datetime as dt  # noqa: PLC0415
    import kalender as ka  # noqa: PLC0415

    heute = dt.date.today().isoformat()
    von = von if re.fullmatch(r"\d{4}-\d{2}-\d{2}", von or "") else heute
    bis = bis if re.fullmatch(r"\d{4}-\d{2}-\d{2}", bis or "") else von
    inhaber = salon_von(un)
    termine = _termine_lesen(inhaber, von, bis)

    # Termin trifft Geld: der Tagesumsatz kommt aus dem Kassenbuch.
    idx = index_aktuell()
    tage = []
    tag = dt.date.fromisoformat(von)
    letzter = dt.date.fromisoformat(bis)
    while tag <= letzter:
        datum = tag.isoformat()
        blatt = idx["kassenblaetter"].get(datum) or {}
        umsatz = (float(blatt.get("einnahmenBar") or 0)
                  + float(blatt.get("ecZahlungen") or 0)) or None
        tage.append(ka.tag(datum, termine, umsatz))
        tag += dt.timedelta(days=1)
    return JSONResponse({"von": von, "bis": bis, "tage": tage})


@app.post("/api/termine")
async def api_termin_anlegen(request: Request) -> Response:
    """Einen Termin eintragen — oder einen bestehenden verschieben.

    Geprüft wird vor allem eines: dass nicht zwei Kundinnen zur selben Zeit
    bei derselben Person stehen. Das ist der Fehler, der einen Tag ruiniert.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if (sperre := _mitarbeit_wache(un, "darf_kasse", "Termine eintragen")):
        return sperre
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)

    import datetime as dt  # noqa: PLC0415
    import kalender as ka  # noqa: PLC0415
    try:
        termin = ka.pruefen(body or {})
    except ka.KalenderFehler as e:
        return JSONResponse({"fehler": str(e)}, status_code=400)

    inhaber = salon_von(un)
    tag = termin["start"][:10]

    # Nicht versehentlich in die Vergangenheit buchen. Nachtragen bleibt
    # möglich — aber ausdrücklich, nicht durch einen Tippfehler im Datum.
    if tag < dt.date.today().isoformat() and not (body or {}).get("nachtragen"):
        return JSONResponse(
            {"fehler": "Das liegt in der Vergangenheit. Wenn du nachtragen "
                       "willst, sag es ausdrücklich."}, status_code=400)

    # Und nicht außerhalb der Öffnungszeiten — ein Termin um drei Uhr nachts
    # ist immer ein Vertipper.
    oeffnung = ka.oeffnung_aus(db_einstellungen(inhaber))
    if not ka.innerhalb_oeffnung(termin["start"], termin["minuten"], oeffnung):
        return JSONResponse(
            {"fehler": f"Da habt ihr nicht geöffnet — {oeffnung[0]} bis "
                       f"{oeffnung[1]}."}, status_code=400)

    # Prüfen und Schreiben unter EINEM Schloss: sonst passt zwischen die
    # Überschneidungsprüfung und den Eintrag eine zweite Anfrage, und zwei
    # Kundinnen stehen zur selben Zeit im Laden.
    with _TERMIN_SCHLOSS:
        bestehende = _termine_lesen(inhaber, tag, tag)
        termin["id"] = (body or {}).get("id")
        if (stoerung := ka.stoert(termin, bestehende)):
            return JSONResponse({"fehler": stoerung}, status_code=409)

        with _DB_LOCK, _db() as c:
            if termin.get("id"):
                c.execute("""UPDATE termin SET start=?, minuten=?, wer=?,
                             kundin=?, leistung=?, notiz=? WHERE id=? AND un=?""",
                          (termin["start"], termin["minuten"], termin["wer"],
                           termin["kundin"], termin["leistung"],
                           str((body or {}).get("notiz") or "")[:300],
                           int(termin["id"]), inhaber))
                neue_id = int(termin["id"])
            else:
                cur = c.execute("""INSERT INTO termin (un, start, minuten, wer,
                                   kundin, leistung, notiz, angelegt)
                                   VALUES (?,?,?,?,?,?,?,?)""",
                                (inhaber, termin["start"], termin["minuten"],
                                 termin["wer"], termin["kundin"],
                                 termin["leistung"],
                                 str((body or {}).get("notiz") or "")[:300],
                                 _jetzt_iso()))
                neue_id = int(cur.lastrowid)
    # `**termin` zuerst: sonst überschreibt sein leeres „id" die frische —
    # und der Termin blockiert sich beim nächsten Verschieben selbst.
    return JSONResponse({**termin, "ok": True, "id": neue_id})


@app.post("/api/termine/vorschlag")
def api_termin_vorschlag(body: dict, request: Request) -> Response:
    """Aus einem Satz ein Terminvorschlag: „Frau Holder Donnerstag Farbe".

    Das Sprachmodell darf VERSTEHEN, nicht rechnen. Es liest heraus, wer,
    was und ungefähr wann — welche Lücke tatsächlich frei ist, rechnet babu
    selbst. Ein Modell, das Uhrzeiten „ungefähr" ausrechnet, verplant den Tag.

    Und es bucht nichts: es schlägt vor, bestätigt wird mit einem Tipp.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if (sperre := _mitarbeit_wache(un, "darf_kasse", "Termine eintragen")):
        return sperre
    text = str((body or {}).get("text") or "").strip()[:400]
    if len(text) < 3:
        return JSONResponse({"fehler": "Sag kurz, wer wann kommen möchte."},
                            status_code=400)

    import datetime as dt  # noqa: PLC0415
    import kalender as ka  # noqa: PLC0415
    heute = dt.date.today()
    roh: dict = {}
    try:
        r = requests.post(GEMMA_API, json={
            "model": GEMMA_MODELL, "temperature": 0.1, "max_tokens": 300,
            "messages": [{"role": "user", "content": ka.frage_bauen(text, heute)}],
        }, timeout=90)
        r.raise_for_status()
        antwort = r.json()["choices"][0]["message"]["content"]
        treffer = re.search(r"\{.*\}", antwort, re.S)
        roh = json.loads(treffer.group(0)) if treffer else {}
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "Das habe ich gerade nicht verstanden — "
                                       "trag den Termin von Hand ein."},
                            status_code=503)

    wunsch = ka.wunsch_pruefen(roh, heute)
    if not wunsch["datum"]:
        return JSONResponse({"wunsch": wunsch, "vorschlaege": [],
                             "hinweis": "An welchem Tag soll der Termin sein?"})

    inhaber = salon_von(un)
    tag = wunsch["datum"]
    termine = _termine_lesen(inhaber, tag, tag)
    oeffnung = ka.oeffnung_aus(db_einstellungen(inhaber))
    frei = ka.freie_luecken(tag, termine, wunsch["minuten"], wunsch["wer"],
                            oeffnung=oeffnung)

    # Der Wunschzeitpunkt zuerst, wenn er wirklich frei ist. Geprüft wird am
    # Kalender, nicht an der Vorschlagsliste: die ist nur eine Auswahl fürs
    # Auge, und 14:00 kann frei sein, ohne darin vorzukommen.
    wunsch_geht = bool(wunsch["uhrzeit"]) and ka.ist_frei(
        tag, termine, wunsch["uhrzeit"], wunsch["minuten"], wunsch["wer"],
        oeffnung=oeffnung)
    if wunsch_geht:
        frei = [wunsch["uhrzeit"]] + [z for z in frei if z != wunsch["uhrzeit"]]
    hinweis = ("An dem Tag ist nichts mehr frei." if not frei else
               "" if not wunsch["uhrzeit"] or wunsch_geht else
               f"Um {wunsch['uhrzeit']} ist schon etwas — das hier ginge:")
    return JSONResponse({"wunsch": wunsch, "vorschlaege": frei[:4],
                         "hinweis": hinweis})


@app.post("/api/termin/{termin_id}/absagen")
def api_termin_absagen(termin_id: int, request: Request) -> Response:
    """Abgesagt, nicht gelöscht: die Lücke im Tag bleibt sichtbar."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        if not c.execute("SELECT 1 FROM termin WHERE id=? AND un=?",
                         (termin_id, inhaber)).fetchone():
            return JSONResponse({"fehler": "unbekannter Termin"}, status_code=404)
        c.execute("UPDATE termin SET abgesagt=1 WHERE id=? AND un=?",
                  (termin_id, inhaber))
    return JSONResponse({"ok": True})


@app.post("/api/termin/{termin_id}/loeschen")
def api_termin_loeschen(termin_id: int, request: Request) -> Response:
    """Ganz weg — Kundendaten müssen sich löschen lassen (Art. 17 DSGVO)."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        c.execute("DELETE FROM termin WHERE id=? AND un=?", (termin_id, inhaber))
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Personalakte und Onboarding.
#
# Nina legt jemanden an und bekommt einen Link. Die neue Mitarbeiterin
# öffnet ihn auf dem Telefon und füllt den Rest selbst aus — ohne Konto,
# ohne Passwort, ohne dass Nina etwas druckt. Der Link ist der Schlüssel,
# deshalb ist er lang und läuft ab.
# ---------------------------------------------------------------------------

EINLADUNG_GILT_TAGE = 14


def _mitarbeiter_zeile(z) -> dict:
    felder = ("id", "vorname", "name", "geburtsdatum", "geburtsname",
              "geburtsort", "staatsangehoerigkeit", "strasse", "plz", "ort",
              "telefon", "email", "steuer_idnr", "rentenvers_nr",
              "krankenkasse", "kinderlos", "kinder_abschlaege", "iban", "bic",
              "titel_bis", "art", "eintritt", "austritt", "befristet_bis",
              "taetigkeit", "stunden_woche", "tage_woche", "entgelt",
              "urlaubstage", "vertrag_fassung", "vertrag_angenommen",
              "belehrungen", "erledigt", "stand", "eingeladen_am")
    d = dict(zip(felder, z))
    d["belehrungen"] = json.loads(d["belehrungen"] or "[]")
    d["erledigt"] = json.loads(d["erledigt"] or "[]")
    return d


_MITARBEITER_SPALTEN = """id, vorname, name, geburtsdatum, geburtsname,
    geburtsort, staatsangehoerigkeit, strasse, plz, ort, telefon, email,
    steuer_idnr, rentenvers_nr, krankenkasse, kinderlos, kinder_abschlaege,
    iban, bic, titel_bis, art, eintritt, austritt, befristet_bis, taetigkeit,
    stunden_woche, tage_woche, entgelt, urlaubstage, vertrag_fassung,
    vertrag_angenommen, belehrungen, erledigt, stand, eingeladen_am"""


@app.get("/start/{marke}")
def start_seite(marke: str) -> FileResponse:
    """Die Seite, die die Mitarbeiterin öffnet. Eine eigene, kleine Seite —
    das Portal wäre für jemanden, der kein Konto hat, das falsche Haus."""
    return FileResponse(WURZEL / "start.html", media_type="text/html",
                        headers=HTML_FRISCH)


@app.get("/api/mitarbeiter")
def api_mitarbeiter(request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das sieht die Inhaberin."},
                            status_code=403)
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        zeilen = [_mitarbeiter_zeile(z) for z in c.execute(
            f"SELECT {_MITARBEITER_SPALTEN} FROM mitarbeiter WHERE un=? "
            "ORDER BY stand, name", (inhaber,))]
    import onboarding as ob  # noqa: PLC0415
    for m in zeilen:
        m["fortschritt"] = ob.fortschritt(m)
    return JSONResponse({"mitarbeiter": zeilen})


@app.post("/api/mitarbeiter")
async def api_mitarbeiter_anlegen(request: Request) -> Response:
    """Nina legt an: Name, Handynummer, Beschäftigung. Mehr nicht."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Einstellen macht die Inhaberin."},
                            status_code=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)

    import arbeitsvertrag as av  # noqa: PLC0415
    # Die Eckdaten müssen tragfähig sein, bevor jemand eingeladen wird —
    # sonst füllt sie zwanzig Minuten aus und der Vertrag geht dann nicht.
    try:
        eck = av.pruefen({**(body or {}),
                          "taetigkeit": (body or {}).get("taetigkeit") or "Friseurin"})
    except av.VertragFehler as f:
        return JSONResponse({"fehler": str(f)}, status_code=400)

    name = str((body or {}).get("name") or "").strip()[:80]
    if not name:
        return JSONResponse({"fehler": "Wie heißt sie?"}, status_code=400)

    import datetime as dt  # noqa: PLC0415
    einladung = secrets.token_urlsafe(24)
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        cur = c.execute(
            """INSERT INTO mitarbeiter (un, vorname, name, telefon, art,
               eintritt, befristet_bis, taetigkeit, stunden_woche, tage_woche,
               entgelt, urlaubstage, stand, einladung, eingeladen_am, angelegt)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'eingeladen',?,?,?)""",
            (inhaber, str((body or {}).get("vorname") or "").strip()[:80], name,
             str((body or {}).get("telefon") or "").strip()[:40],
             eck["art"], eck["eintritt"].isoformat(),
             eck["befristet_bis"].isoformat() if eck["befristet_bis"] else None,
             eck["taetigkeit"], eck["stunden_woche"], eck["tage_woche"],
             int(round(eck["entgelt"] * 100)), eck["urlaubstage"],
             einladung, _jetzt_iso(), _jetzt_iso()))
        neue = int(cur.lastrowid)

    return JSONResponse({
        "ok": True, "id": neue,
        "einladung": f"/start/{einladung}",
        "gilt_bis": (dt.date.today()
                     + dt.timedelta(days=EINLADUNG_GILT_TAGE)).isoformat(),
        "befunde": eck["befunde"],
        "satz": f"Schick {name} diesen Link — den Rest macht sie selbst."})


def _einladung_finden(marke: str) -> tuple[str, dict] | None:
    """Wer steckt hinter diesem Link — und gilt er noch?"""
    import datetime as dt  # noqa: PLC0415
    if not marke or len(marke) < 20:
        return None
    with _DB_LOCK, _db() as c:
        z = c.execute(
            f"SELECT un, {_MITARBEITER_SPALTEN} FROM mitarbeiter "
            "WHERE einladung=?", (marke,)).fetchone()
    if not z:
        return None
    person = _mitarbeiter_zeile(z[1:])
    try:
        seit = dt.datetime.fromisoformat(
            (person["eingeladen_am"] or "").replace("Z", "+00:00"))
        alt = (dt.datetime.now(dt.timezone.utc) - seit).days
    except ValueError:
        alt = 0
    if alt > EINLADUNG_GILT_TAGE:
        return None
    return z[0], person


@app.get("/api/onboarding/{marke}")
def api_onboarding(marke: str) -> Response:
    """Was die Mitarbeiterin sieht, wenn sie den Link öffnet.

    Ohne Anmeldung — der Link ist der Schlüssel. Deshalb kommt hier auch
    nur heraus, was sie ohnehin über sich selbst weiß.
    """
    import onboarding as ob  # noqa: PLC0415
    gefunden = _einladung_finden(marke)
    if not gefunden:
        return JSONResponse(
            {"fehler": "Dieser Link gilt nicht mehr. Bitte den Salon um "
                       "einen neuen."}, status_code=404)
    un, person = gefunden
    schritt = ob.naechster_schritt(person)
    return JSONResponse({
        "salon": db_einstellungen(un).get("betrieb_name", ""),
        "vorname": person["vorname"], "name": person["name"],
        "eintritt": person["eintritt"],
        "fortschritt": ob.fortschritt(person),
        "schritt": schritt,
        "schritte": [{"id": s["id"], "titel": s["titel"]} for s in ob.SCHRITTE],
        "erledigt": person["erledigt"],
    })


# Ausweiskopien liegen NICHT in der Belegbox.
#
# § 4a Abs. 5 AufenthG verlangt die Kopie „für die Dauer der Beschäftigung"
# — also gerade nicht für immer. In Git bliebe jede Fassung stehen, auch
# nach dem letzten Arbeitstag. Der Vertrag dagegen gehört in die Box: für
# ihn gilt eine Aufbewahrungsfrist, und dort ist er fälschungssicher.
AUSWEISE = Path(os.environ.get("BABU_AUSWEISE",
                               str(Path.home() / "babu-web" / "ausweise")))
AUSWEIS_MAX = 12 * 1024 * 1024


def _ausweis_pfad(einladung: str) -> Path:
    return AUSWEISE / (hashlib.sha256(einladung.encode()).hexdigest()[:24] + ".bin")


# Eigener Pfad, nicht `/ausweis`: so heißt schon der Wizard-Schritt.
@app.post("/api/onboarding/{marke}/ausweis-bild")
async def api_onboarding_ausweis(marke: str, request: Request) -> Response:
    """Das Ausweisfoto — in den löschbaren Ablageort, nicht in die Box."""
    gefunden = _einladung_finden(marke)
    if not gefunden:
        return JSONResponse({"fehler": "Dieser Link gilt nicht mehr."},
                            status_code=404)
    daten = await request.body()
    if not daten:
        return JSONResponse({"fehler": "Da war kein Bild dabei."},
                            status_code=400)
    if len(daten) > AUSWEIS_MAX:
        return JSONResponse(
            {"fehler": "Das Bild ist zu groß. Meist hilft es, es noch einmal "
                       "mit der Kamera aufzunehmen statt aus der Galerie zu "
                       "wählen."}, status_code=413)
    if not daten[:3] in (b"\xff\xd8\xff",) and not daten[:4] == b"%PDF":
        return JSONResponse(
            {"fehler": "Das sieht nicht nach einem Foto aus. Bitte noch "
                       "einmal aufnehmen."}, status_code=400)

    pfad = _ausweis_pfad(marke)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(daten)
    return JSONResponse({"ok": True, "groesse": len(daten)})


@app.post("/api/onboarding/{marke}/{schritt_id}")
async def api_onboarding_schritt(marke: str, schritt_id: str,
                                 request: Request) -> Response:
    """Eine Antwort speichern und zum nächsten Schritt weitergehen."""
    import onboarding as ob  # noqa: PLC0415
    gefunden = _einladung_finden(marke)
    if not gefunden:
        return JSONResponse({"fehler": "Dieser Link gilt nicht mehr."},
                            status_code=404)
    un, person = gefunden
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)

    try:
        if schritt_id == "belehrungen":
            sauber = {"belehrungen": ob.belehrungen_pruefen(
                (body or {}).get("belehrungen"))}
        else:
            sauber = ob.schritt_pruefen(schritt_id, body or {})
    except ob.OnboardingFehler as f:
        return JSONResponse({"fehler": str(f)}, status_code=400)

    erledigt = sorted(set(person["erledigt"]) | {schritt_id},
                      key=lambda x: [s["id"] for s in ob.SCHRITTE].index(x)
                      if x in ob.SCHRITT_NACH_ID else 99)
    spalten, werte = [], []
    for feld, wert in sauber.items():
        if feld in ("belehrungen",):
            spalten.append(feld); werte.append(json.dumps(wert))
        elif feld in ("vertrag_angenommen",):
            spalten.append(feld); werte.append(_jetzt_iso() if wert else None)
        elif feld == "ausweis_dokument":
            continue                      # das Bild geht über /api/aufnahme
        elif feld in ("kinderlos",):
            spalten.append(feld); werte.append(1 if wert else 0)
        else:
            spalten.append(feld); werte.append(wert)

    # Angenommener Vertrag: ab in die Belegbox. Für ihn gilt eine
    # Aufbewahrungsfrist, also gehört er dorthin, wo jede Fassung bleibt.
    if schritt_id == "vertrag" and sauber.get("vertrag_angenommen"):
        await _vertrag_ablegen(un, marke, person)

    fertig = len(erledigt) >= len(ob.SCHRITTE)
    spalten += ["erledigt", "stand"]
    werte += [json.dumps(erledigt), "vollstaendig" if fertig else "im_wizard"]

    with _DB_LOCK, _db() as c:
        c.execute(f"UPDATE mitarbeiter SET {', '.join(f'{s}=?' for s in spalten)} "
                  "WHERE einladung=?", (*werte, marke))

    person = {**person, "erledigt": erledigt}
    naechster = ob.naechster_schritt(person)
    return JSONResponse({"ok": True, "fortschritt": ob.fortschritt(person),
                         "schritt": naechster})


@app.get("/api/onboarding/{marke}/vertrag/text")
def api_onboarding_vertrag(marke: str) -> Response:
    """Der Vertrag zum Lesen — erzeugt aus den Eckdaten, die Nina angelegt hat.

    Sie soll ihn ganz sehen, bevor sie zustimmt. Ein Vertrag, den man erst
    nach der Zusage bekommt, ist keiner.
    """
    import arbeitsvertrag as av  # noqa: PLC0415
    gefunden = _einladung_finden(marke)
    if not gefunden:
        return JSONResponse({"fehler": "Dieser Link gilt nicht mehr."},
                            status_code=404)
    un, person = gefunden
    e = db_einstellungen(un)
    try:
        vertrag = av.vertrag_bauen({
            "art": person["art"], "eintritt": person["eintritt"],
            "befristet_bis": person["befristet_bis"],
            "taetigkeit": person["taetigkeit"],
            "stunden_woche": person["stunden_woche"],
            "tage_woche": person["tage_woche"],
            "urlaubstage": person["urlaubstage"],
            "entgelt": (person["entgelt"] or 0) / 100,
            "geburtsdatum": person["geburtsdatum"],
        }, {"name": e.get("betrieb_name", ""),
            "strasse": e.get("betrieb_strasse", ""),
            "ort": " ".join(x for x in (e.get("betrieb_plz"),
                                        e.get("betrieb_ort")) if x),
            "arbeitnehmerin": f"{person['vorname'] or ''} "
                              f"{person['name'] or ''}".strip()})
    except av.VertragFehler as f:
        return JSONResponse({"fehler": str(f)}, status_code=400)
    return JSONResponse({"text": av.als_text(vertrag),
                         "fassung": vertrag["fassung"],
                         "form": vertrag["form"]["form"]})


async def _vertrag_ablegen(un: str, marke: str, person: dict) -> None:
    """Den angenommenen Vertrag in die Belegbox schreiben.

    Mit Zeitstempel und Fassung: später muss nachvollziehbar sein, welchem
    Text genau jemand zugestimmt hat.
    """
    import arbeitsvertrag as av  # noqa: PLC0415
    import boxschreiber  # noqa: PLC0415
    e = db_einstellungen(un)
    try:
        vertrag = av.vertrag_bauen({
            "art": person["art"], "eintritt": person["eintritt"],
            "befristet_bis": person["befristet_bis"],
            "taetigkeit": person["taetigkeit"],
            "stunden_woche": person["stunden_woche"],
            "tage_woche": person["tage_woche"],
            "urlaubstage": person["urlaubstage"],
            "entgelt": (person["entgelt"] or 0) / 100,
            "geburtsdatum": person["geburtsdatum"],
        }, {"name": e.get("betrieb_name", ""),
            "ort": " ".join(x for x in (e.get("betrieb_plz"),
                                        e.get("betrieb_ort")) if x),
            "arbeitnehmerin": f"{person['vorname'] or ''} "
                              f"{person['name'] or ''}".strip()})
    except av.VertragFehler:
        return                      # ohne gültigen Vertrag nichts ablegen

    kennung = f"{person['eintritt']}-{(person['name'] or 'unbenannt').lower()}"
    kennung = re.sub(r"[^a-z0-9-]", "-", kennung)[:60]
    angenommen = _jetzt_iso()
    zettel = {
        "art": "arbeitsvertrag", "fassung": vertrag["fassung"],
        "angenommen": angenommen, "form": vertrag["form"]["form"],
        "arbeitnehmerin": f"{person['vorname'] or ''} "
                          f"{person['name'] or ''}".strip(),
        "eintritt": person["eintritt"], "art_beschaeftigung": person["art"],
    }
    text = (av.als_text(vertrag)
            + f"\n\nIn Textform angenommen am {angenommen} "
              f"(Fassung {vertrag['fassung']}).\n")
    try:
        await run_in_threadpool(
            boxschreiber.schreiben,
            {f"dokumente/vertraege/{kennung}.txt": text.encode(),
             f"dokumente/vertraege/{kennung}.meta.json":
                 json.dumps(zettel, ensure_ascii=False, indent=1).encode()},
            None, f"vertrag: {kennung}", un)
    except boxschreiber.SchreibFehler:
        pass            # der Wizard darf daran nicht scheitern
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0


@app.get("/api/mitarbeiter/{mitarbeiter_id}/einladung")
def api_einladung_zeigen(mitarbeiter_id: int, request: Request) -> Response:
    """Den Link noch einmal — Handynummern verschreiben sich."""
    import datetime as dt  # noqa: PLC0415
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."},
                            status_code=403)
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        z = c.execute("""SELECT einladung, eingeladen_am, name, stand
                         FROM mitarbeiter WHERE id=? AND un=?""",
                      (mitarbeiter_id, inhaber)).fetchone()
    if not z:
        return JSONResponse({"fehler": "unbekannt"}, status_code=404)
    if z[3] == "vollstaendig":
        return JSONResponse(
            {"fehler": "Sie ist schon fertig — der Link wird nicht mehr "
                       "gebraucht."}, status_code=400)
    try:
        seit = dt.datetime.fromisoformat((z[1] or "").replace("Z", "+00:00"))
    except ValueError:
        seit = dt.datetime.now(dt.timezone.utc)
    bis = (seit + dt.timedelta(days=EINLADUNG_GILT_TAGE)).date()
    if bis < dt.date.today():
        # Abgelaufen: einen frischen ausstellen, statt einen toten zu zeigen.
        neu_marke = secrets.token_urlsafe(24)
        with _DB_LOCK, _db() as c:
            c.execute("""UPDATE mitarbeiter SET einladung=?, eingeladen_am=?
                         WHERE id=? AND un=?""",
                      (neu_marke, _jetzt_iso(), mitarbeiter_id, inhaber))
        return JSONResponse({
            "einladung": f"/start/{neu_marke}",
            "gilt_bis": (dt.date.today()
                         + dt.timedelta(days=EINLADUNG_GILT_TAGE)).isoformat(),
            "satz": f"Der alte Link war abgelaufen — hier ist ein neuer für "
                    f"{z[2]}."})
    return JSONResponse({"einladung": f"/start/{z[0]}",
                         "gilt_bis": bis.isoformat(),
                         "satz": f"Der Link für {z[2]}."})


@app.post("/api/mitarbeiter/{mitarbeiter_id}/loeschen")
def api_mitarbeiter_loeschen(mitarbeiter_id: int, request: Request) -> Response:
    """Ganz weg. Eine Personalakte muss sich löschen lassen."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."},
                            status_code=403)
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        z = c.execute("SELECT einladung FROM mitarbeiter WHERE id=? AND un=?",
                      (mitarbeiter_id, inhaber)).fetchone()
        c.execute("DELETE FROM mitarbeiter WHERE id=? AND un=?",
                  (mitarbeiter_id, inhaber))
    # Die Ausweiskopie geht mit. Sie darf ohnehin nur für die Dauer der
    # Beschäftigung aufbewahrt werden.
    if z and z[0]:
        _ausweis_pfad(z[0]).unlink(missing_ok=True)
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Arbeitsverträge. Nina sagt, wen sie einstellt — den Rest rechnet
# `arbeitsvertrag.py` aus: Klauseln, Anlagen, Urlaub, Fristen, und die
# Prüfung, ob der Vertrag überhaupt zulässig wäre. Erzeugt wird hier nur
# ein Entwurf; abgelegt wird er erst, wenn beide ihn angenommen haben.
# ---------------------------------------------------------------------------

@app.get("/api/arbeitsvertrag/arten")
def api_vertragsarten(request: Request) -> Response:
    """Was zur Auswahl steht — samt dem, was daran hängt."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    import arbeitsvertrag as av  # noqa: PLC0415
    import datetime as dt  # noqa: PLC0415
    werte = av.werte_fuer(dt.date.today())
    return JSONResponse({
        "arten": [{"id": k, **v} for k, v in av.ARTEN.items()],
        "nicht_anstellung": [{"id": k, "warnung": t}
                             for k, t in av.KEINE_ANSTELLUNG.items()],
        "werte": {"jahr": werte["jahr"],
                  "mindestlohn": werte["mindestlohn"],
                  "minijob_grenze": werte["minijob"],
                  "ausbildung_mindest": werte["azubi"]},
    })


@app.post("/api/arbeitsvertrag/entwurf")
async def api_vertrag_entwurf(request: Request) -> Response:
    """Aus Eckdaten ein vollständiger Vertragsentwurf.

    Gibt bei unzulässigen Angaben bewusst einen Fehler zurück statt eines
    Vertrags mit Warnhinweis — ein Vertrag unter Mindestlohn soll gar nicht
    erst entstehen.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Verträge macht die Inhaberin."},
                            status_code=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)

    import arbeitsvertrag as av  # noqa: PLC0415
    inhaber = salon_von(un)
    e = db_einstellungen(inhaber)
    betrieb = {
        "name": e.get("betrieb_name", ""),
        "strasse": e.get("betrieb_strasse", ""),
        "ort": " ".join(x for x in (e.get("betrieb_plz"), e.get("betrieb_ort")) if x),
        "arbeitnehmerin": str((body or {}).get("arbeitnehmerin") or "").strip()[:80],
    }
    try:
        vertrag = av.vertrag_bauen(body or {}, betrieb)
    except av.VertragFehler as f:
        return JSONResponse({"fehler": str(f)}, status_code=400)

    # datetime ist nicht JSON-fähig — die Angaben als Text zurückgeben.
    angaben = {k: (v.isoformat() if hasattr(v, "isoformat") else v)
               for k, v in vertrag["angaben"].items() if k != "werte"}
    return JSONResponse({**vertrag, "angaben": angaben,
                         "text": av.als_text(vertrag)})


# ---------------------------------------------------------------------------
# Zurücksetzen für die Testphase.
#
# Damit sich das Onboarding noch einmal ansehen lässt, ohne sich neu
# anzumelden. Ausdrücklich NICHT betroffen: die Belegbox, das Konto und
# alles Personenbezogene. Gelöscht wird nach Positivliste, nicht per
# „alles weg" — sonst nimmt ein Testknopf beiläufig den WhatsApp-Zugang
# und das Logo mit.
# ---------------------------------------------------------------------------

# Was zur Einrichtung gehört und beim Zurücksetzen verschwindet.
EINRICHTUNGSFELDER = (
    "betrieb_name", "betrieb_inhaberin", "betrieb_strasse", "betrieb_plz",
    "betrieb_ort", "betrieb_telefon", "betrieb_email", "betrieb_web",
    "steuernummer", "ust_id", "finanzamt", "kleinunternehmer",
    "versteuerung", "iban", "bic", "bank", "oeffnung_von", "oeffnung_bis",
    "einrichtung_fertig", "gruendung",
)


@app.post("/api/einrichtung/zuruecksetzen")
def api_einrichtung_zuruecksetzen(request: Request) -> Response:
    """Die Einrichtungsangaben löschen, damit sie neu abgefragt werden."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."},
                            status_code=403)
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        cur = c.execute(
            "DELETE FROM einstellungen WHERE un=? AND schluessel IN ({})".format(
                ",".join("?" * len(EINRICHTUNGSFELDER))),
            (inhaber, *EINRICHTUNGSFELDER))
        weg = cur.rowcount
    return JSONResponse({"ok": True, "geloescht": weg,
                         "hinweis": "Belegbox, Konto und Kundendaten sind "
                                    "unberührt."})


# ---------------------------------------------------------------------------
# Der Terminagent auf WhatsApp.
#
# Der Webhook ist die einzige Stelle in babu, an der jemand von außen
# hineinschreibt — ohne Anmeldung, nur über eine Adresse, die sich
# herumsprechen kann. Deshalb steht vor allem anderen die Signaturprüfung,
# und deshalb bucht der Agent nur „angefragt": eine Telefonnummer soll den
# Kalender nicht endgültig vollschreiben können.
# ---------------------------------------------------------------------------

WA_GRAPH = os.environ.get("WA_GRAPH", "https://graph.facebook.com/v21.0")
_WA_SCHLOSS = threading.Lock()


def _wa_konto_zu(telefon_id: str) -> str | None:
    """Welchem Salon gehört diese Absendernummer?

    Ein Webhook für alle: Meta sagt nur, an welche Geschäftsnummer die
    Nachricht ging. Findet sich dazu kein Konto, wird nichts getan — lieber
    eine Nachricht verlieren als sie im falschen Kalender einzutragen.
    """
    if not telefon_id:
        return None
    with _DB_LOCK, _db() as c:
        zeile = c.execute(
            "SELECT un FROM einstellungen WHERE schluessel='wa_telefon_id' "
            "AND wert=? LIMIT 1", (str(telefon_id),)).fetchone()
    return zeile[0] if zeile else None


def _wa_senden(un: str, telefon: str, text: str) -> bool:
    """Antworten. Ohne eingerichteten Zugang wird nur mitgeschrieben.

    Das ist Absicht, kein Notbehelf: so lässt sich der ganze Agent im
    Prüfstand durchspielen, bevor Meta das Geschäftskonto freigibt.
    """
    e = db_einstellungen(un)
    token, absender = e.get("wa_token", ""), e.get("wa_telefon_id", "")
    if not token or not absender:
        return False
    try:
        r = requests.post(
            f"{WA_GRAPH}/{absender}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"messaging_product": "whatsapp", "to": telefon,
                  "type": "text", "text": {"body": text}},
            timeout=30)
        return r.status_code < 300
    except Exception:  # noqa: BLE001
        return False        # nie den Token mitloggen


def _wa_faden(un: str, telefon: str, name: str) -> dict:
    with _DB_LOCK, _db() as c:
        z = c.execute("""SELECT id, name, stand, wunsch, vorschlaege, termin,
                         stumm FROM wa_faden WHERE un=? AND telefon=?""",
                      (un, telefon)).fetchone()
        if not z:
            cur = c.execute("""INSERT INTO wa_faden (un, telefon, name, stand,
                               begonnen, zuletzt) VALUES (?,?,?,?,?,?)""",
                            (un, telefon, name, "neu", _jetzt_iso(), _jetzt_iso()))
            return {"id": int(cur.lastrowid), "name": name, "stand": "neu",
                    "wunsch": {}, "vorschlaege": [], "termin": None,
                    "stumm": False, "frisch": True}
        if name and not z[1]:
            c.execute("UPDATE wa_faden SET name=? WHERE id=?", (name, z[0]))
    return {"id": z[0], "name": z[1] or name, "stand": z[2],
            "wunsch": json.loads(z[3] or "{}"),
            "vorschlaege": json.loads(z[4] or "[]"),
            "termin": z[5], "stumm": bool(z[6]), "frisch": False}


def _wa_faden_setzen(faden_id: int, **felder) -> None:
    erlaubt = {"stand", "wunsch", "vorschlaege", "termin", "stumm", "name"}
    paare = {k: v for k, v in felder.items() if k in erlaubt}
    if not paare:
        return
    for k in ("wunsch", "vorschlaege"):
        if k in paare and not isinstance(paare[k], str):
            paare[k] = json.dumps(paare[k], ensure_ascii=False)
    satz = ", ".join(f"{k}=?" for k in paare) + ", zuletzt=?"
    with _DB_LOCK, _db() as c:
        c.execute(f"UPDATE wa_faden SET {satz} WHERE id=?",
                  (*paare.values(), _jetzt_iso(), faden_id))


def _wa_merken(un: str, faden: int, richtung: str, text: str,
               wa_id: str = "") -> None:
    with _DB_LOCK, _db() as c:
        c.execute("""INSERT INTO wa_nachricht (un, faden, richtung, text,
                     wa_id, zeit) VALUES (?,?,?,?,?,?)""",
                  (un, faden, richtung, text[:2000], wa_id, _jetzt_iso()))


def _wa_schon_gesehen(wa_id: str) -> bool:
    """Meta stellt bei jedem Zweifel erneut zu. Ohne diese Prüfung stünde
    derselbe Termin dreimal im Kalender."""
    if not wa_id:
        return False
    with _DB_LOCK, _db() as c:
        return c.execute("SELECT 1 FROM wa_nachricht WHERE wa_id=? LIMIT 1",
                         (wa_id,)).fetchone() is not None


def _wa_kundin_zu(un: str, telefon: str) -> dict | None:
    """Kennen wir die Nummer schon? Dann heißt sie beim Namen."""
    ziffern = re.sub(r"\D", "", telefon or "")[-9:]
    if len(ziffern) < 6:
        return None
    with _DB_LOCK, _db() as c:
        for kid, name, tel in c.execute(
                "SELECT id, name, telefon FROM kundin WHERE un=? AND telefon<>''",
                (un,)):
            if re.sub(r"\D", "", tel or "")[-9:] == ziffern:
                return {"id": kid, "name": name}
    return None


def _wa_wunsch_lesen(text: str, heute, kundin: str) -> dict:
    """Was steht drin? Das Modell darf verstehen, nicht rechnen."""
    import whatsapp as wam  # noqa: PLC0415
    try:
        r = requests.post(GEMMA_API, json={
            "model": GEMMA_MODELL, "temperature": 0.1, "max_tokens": 300,
            "messages": [{"role": "user",
                          "content": wam.frage_bauen(text, heute, kundin)}],
        }, timeout=90)
        r.raise_for_status()
        antwort = r.json()["choices"][0]["message"]["content"]
        treffer = re.search(r"\{.*\}", antwort, re.S)
        return json.loads(treffer.group(0)) if treffer else {}
    except Exception:  # noqa: BLE001
        return {}


def _wa_termin_eintragen(un: str, faden: dict, datum: str, zeit: str,
                         wunsch: dict, telefon: str) -> int | None:
    """Die Zeit wirklich blockieren — aber als Anfrage.

    Wirklich blockieren, weil ein Vorschlag ohne Sperre bedeutet, dass zwei
    Kundinnen dieselbe Lücke bekommen. Als Anfrage, weil sonst jeder mit
    der Nummer den Tag zustellen könnte.
    """
    import kalender as ka  # noqa: PLC0415
    start = f"{datum}T{zeit}"
    minuten = int(wunsch.get("minuten") or 60)
    with _TERMIN_SCHLOSS:
        bestehend = _termine_lesen(un, datum, datum)
        neu = {"start": start, "minuten": minuten, "wer": wunsch.get("wer") or ""}
        if ka.stoert(ka.pruefen(neu), bestehend):
            return None
        with _DB_LOCK, _db() as c:
            cur = c.execute("""INSERT INTO termin (un, start, minuten, wer,
                               kundin, leistung, notiz, abgesagt, bestaetigt,
                               quelle, telefon, angelegt)
                               VALUES (?,?,?,?,?,?,?,0,0,'whatsapp',?,?)""",
                            (un, start, minuten, wunsch.get("wer") or "",
                             faden.get("name") or wunsch.get("kundin") or "",
                             wunsch.get("leistung") or "", "", telefon,
                             _jetzt_iso()))
            return int(cur.lastrowid)


def _wa_offene(un: str, telefon: str) -> int:
    """Wie viele unbestätigte Termine hält diese Nummer schon?

    Ohne Grenze könnte jemand mit einer Telefonnummer den Kalender
    zuschreiben — jede Anfrage sperrt schließlich echte Zeit.
    """
    with _DB_LOCK, _db() as c:
        return c.execute(
            """SELECT COUNT(*) FROM termin WHERE un=? AND telefon=?
               AND quelle='whatsapp' AND bestaetigt=0 AND abgesagt=0""",
            (un, telefon)).fetchone()[0]


def _wa_antworten(un: str, faden: dict, telefon: str, text: str) -> str:
    """Ein Zug im Gespräch: hereingekommener Text rein, Antwort raus."""
    import datetime as dt  # noqa: PLC0415
    import kalender as ka  # noqa: PLC0415
    import whatsapp as wam  # noqa: PLC0415

    heute = dt.date.today()
    e = db_einstellungen(un)
    salon = e.get("betrieb_name", "")
    was_will_sie = wam.absicht(text)

    if was_will_sie == "abbruch":
        _wa_faden_setzen(faden["id"], stumm=1, stand="stumm")
        return wam.abgemeldet()
    if faden["stumm"]:
        _wa_faden_setzen(faden["id"], stumm=0)     # sie schreibt von selbst wieder
    if was_will_sie == "mensch":
        _wa_faden_setzen(faden["id"], stand="wartet_mensch")
        return wam.an_den_salon()
    if was_will_sie == "absage":
        _wa_faden_setzen(faden["id"], stand="wartet_mensch")
        return wam.absage_angenommen()

    # Steht eine Auswahl im Raum? Dann zuerst prüfen, ob sie getroffen wurde.
    if faden["stand"] == "wartet_wahl" and faden["vorschlaege"]:
        gewaehlt = wam.wahl_lesen(text, faden["vorschlaege"])
        if gewaehlt and _wa_offene(un, telefon) >= wam.MAX_OFFEN:
            _wa_faden_setzen(faden["id"], stand="wartet_mensch", vorschlaege=[])
            return wam.genug_offen()
        if gewaehlt:
            wunsch = faden["wunsch"] or {}
            datum = wunsch.get("datum")
            termin_id = _wa_termin_eintragen(un, faden, datum, gewaehlt,
                                             wunsch, telefon)
            if termin_id is None:
                frei, _ = _wa_luecken(un, datum, wunsch)
                _wa_faden_setzen(faden["id"], vorschlaege=frei,
                                 stand="wartet_wahl" if frei else "neu")
                return wam.zeit_ist_weg(frei)
            _wa_faden_setzen(faden["id"], stand="gebucht", termin=termin_id,
                             vorschlaege=[])
            return wam.bestaetigen(datum, gewaehlt, faden.get("name") or "",
                                   wunsch.get("leistung") or "")
        # Keine erkennbare Wahl: vielleicht ein ganz neuer Wunsch.
        neuer = ka.wunsch_pruefen(_wa_wunsch_lesen(text, heute,
                                                   faden.get("name") or ""), heute)
        if not neuer["datum"]:
            return wam.nicht_verstanden(faden["vorschlaege"])
    else:
        neuer = ka.wunsch_pruefen(_wa_wunsch_lesen(text, heute,
                                                   faden.get("name") or ""), heute)

    if faden["frisch"] and not neuer["datum"]:
        _wa_faden_setzen(faden["id"], stand="wartet_wunsch")
        return wam.gruss(salon, faden.get("name") or "")
    if not neuer["datum"]:
        _wa_faden_setzen(faden["id"], stand="wartet_wunsch",
                         wunsch={**(faden["wunsch"] or {}), **{
                             k: v for k, v in neuer.items() if v}})
        return wam.nach_tag_fragen()

    wunsch = {**(faden["wunsch"] or {}), **{k: v for k, v in neuer.items() if v}}
    wunsch["tageszeit"] = wam.tageszeit_lesen(neuer.get("tageszeit")
                                              or wunsch.get("tageszeit"), text)
    frei, abweichend = _wa_luecken(un, wunsch["datum"], wunsch)
    _wa_faden_setzen(faden["id"], stand="wartet_wahl" if frei else "wartet_wunsch",
                     wunsch=wunsch, vorschlaege=frei)
    return wam.vorschlagen(wunsch["datum"], frei, wunsch.get("leistung") or "",
                           abweichend)


def _wa_luecken(un: str, datum: str, wunsch: dict) -> tuple[list[str], bool]:
    """Die freien Zeiten — und ob dabei ein Zeitwunsch übergangen wurde.

    Zweiteres gehört dazugesagt: wer „nachmittags" schreibt und 9 Uhr
    angeboten bekommt, denkt, babu habe nicht zugehört.
    """
    import kalender as ka  # noqa: PLC0415
    import whatsapp as wam  # noqa: PLC0415
    termine = _termine_lesen(un, datum, datum)
    oeffnung = ka.oeffnung_aus(db_einstellungen(un))
    minuten = int(wunsch.get("minuten") or 60)
    alle = ka.freie_luecken(datum, termine, minuten, wunsch.get("wer") or "",
                            oeffnung=oeffnung)
    hoechstens = wam.HOECHSTENS_VORSCHLAEGE

    # Die genannte Uhrzeit zuerst, wenn sie wirklich frei ist.
    gewuenscht = wunsch.get("uhrzeit")
    if gewuenscht and ka.ist_frei(datum, termine, gewuenscht, minuten,
                                  wunsch.get("wer") or "", oeffnung=oeffnung):
        return ([gewuenscht]
                + [z for z in alle if z != gewuenscht])[:hoechstens], False

    tageszeit = wunsch.get("tageszeit")
    passend = [z for z in alle if wam.passt_zur_tageszeit(z, tageszeit)]
    if passend:
        return passend[:hoechstens], False
    # Nichts zur Wunschzeit: trotzdem etwas anbieten, aber es dazusagen.
    return alle[:hoechstens], bool(alle) and bool(gewuenscht or tageszeit)


def _wa_zug(un: str, telefon: str, name: str, text: str,
            wa_id: str = "") -> str:
    """Eine Nachricht vollständig abarbeiten — merken, antworten, merken."""
    import whatsapp as wam  # noqa: PLC0415
    with _WA_SCHLOSS:
        if _wa_schon_gesehen(wa_id):
            return ""
        faden = _wa_faden(un, telefon, name)
        _wa_merken(un, faden["id"], "ein", text, wa_id)
        try:
            antwort = wam.kuerzen(_wa_antworten(un, faden, telefon, text))
        except Exception:  # noqa: BLE001
            antwort = wam.nicht_verstanden(faden.get("vorschlaege") or [])
        _wa_merken(un, faden["id"], "aus", antwort)
    _wa_senden(un, telefon, antwort)
    return antwort


@app.get("/api/whatsapp/webhook")
def api_wa_pruefung(request: Request) -> Response:
    """Metas Klopfzeichen beim Einrichten des Webhooks."""
    p = request.query_params
    if p.get("hub.mode") != "subscribe":
        return Response(status_code=400)
    marke = str(p.get("hub.verify_token") or "")
    with _DB_LOCK, _db() as c:
        treffer = c.execute(
            "SELECT 1 FROM einstellungen WHERE schluessel='wa_verify' AND wert=?",
            (marke,)).fetchone()
    if not marke or not treffer:
        return Response(status_code=403)
    return Response(str(p.get("hub.challenge") or ""), media_type="text/plain")


@app.post("/api/whatsapp/webhook")
async def api_wa_eingang(request: Request) -> Response:
    """Was die Kundin geschrieben hat.

    Antwortet immer mit 200, sobald die Signatur stimmt: Meta wiederholt
    sonst stundenlang. Was babu damit anfängt, ist Metas Sache nicht.
    """
    import whatsapp as wam  # noqa: PLC0415
    koerper = await request.body()
    if len(koerper) > 512_000:
        return JSONResponse({"ok": True})

    nutzlast = {}
    try:
        nutzlast = json.loads(koerper or b"{}")
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": True})

    for n in wam.eingang_lesen(nutzlast):
        un = _wa_konto_zu(n["an"])
        if not un:
            continue
        e = db_einstellungen(un)
        if e.get("wa_an") != "1":
            continue
        if not wam.signatur_pruefen(e.get("wa_geheimnis", ""), koerper,
                                    request.headers.get("X-Hub-Signature-256", "")):
            return JSONResponse({"ok": True}, status_code=403)
        _wa_zug(un, n["telefon"], n["name"], n["text"], n["wa_id"])
    return JSONResponse({"ok": True})


@app.get("/api/whatsapp")
def api_wa_stand(request: Request) -> Response:
    """Was eingerichtet ist — ohne die Geheimnisse herauszugeben."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    inhaber = salon_von(un)
    e = db_einstellungen(inhaber)
    with _DB_LOCK, _db() as c:
        faeden = c.execute("SELECT COUNT(*) FROM wa_faden WHERE un=?",
                           (inhaber,)).fetchone()[0]
        angefragt = c.execute(
            """SELECT COUNT(*) FROM termin WHERE un=? AND quelle='whatsapp'
               AND bestaetigt=0 AND abgesagt=0""", (inhaber,)).fetchone()[0]
    return JSONResponse({
        "an": e.get("wa_an") == "1",
        "telefon_id": e.get("wa_telefon_id", ""),
        "token_da": bool(e.get("wa_token")),
        "geheimnis_da": bool(e.get("wa_geheimnis")),
        "verify_da": bool(e.get("wa_verify")),
        "sendet": bool(e.get("wa_token") and e.get("wa_telefon_id")),
        "gespraeche": faeden, "angefragt": angefragt,
        "webhook": "/api/whatsapp/webhook",
    })


@app.post("/api/whatsapp/einstellungen")
async def api_wa_einrichten(request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das richtet die Inhaberin ein."},
                            status_code=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    inhaber = salon_von(un)
    for feld, schluessel in (("telefon_id", "wa_telefon_id"),
                             ("token", "wa_token"),
                             ("geheimnis", "wa_geheimnis"),
                             ("verify", "wa_verify")):
        wert = (body or {}).get(feld)
        if wert is not None:                 # leerer String löscht bewusst
            db_einstellung_setzen(inhaber, schluessel, str(wert).strip()[:400])
    if "an" in (body or {}):
        db_einstellung_setzen(inhaber, "wa_an", "1" if body["an"] else "0")
    return api_wa_stand(request)


@app.post("/api/whatsapp/probe")
async def api_wa_probe(request: Request) -> Response:
    """Der Prüfstand: eine Nachricht schreiben, als käme sie von außen.

    Damit lässt sich der ganze Agent durchspielen, solange Meta das
    Geschäftskonto noch nicht freigegeben hat. Geschickt wird nichts.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    text = str((body or {}).get("text") or "").strip()[:1000]
    if not text:
        return JSONResponse({"fehler": "Schreib etwas."}, status_code=400)
    telefon = str((body or {}).get("telefon") or "probe-0711")[:32]
    name = str((body or {}).get("name") or "")[:80]
    antwort = _wa_zug(salon_von(un), telefon, name, text)
    return JSONResponse({"antwort": antwort, "telefon": telefon})


@app.get("/api/whatsapp/faeden")
def api_wa_faeden(request: Request, faden: int = 0) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        if faden:
            z = c.execute("""SELECT id, telefon, name, stand FROM wa_faden
                             WHERE id=? AND un=?""", (faden, inhaber)).fetchone()
            if not z:
                return JSONResponse({"fehler": "unbekannt"}, status_code=404)
            return JSONResponse({"id": z[0], "telefon": z[1], "name": z[2],
                                 "stand": z[3], "nachrichten": [
                {"richtung": n[0], "text": n[1], "zeit": n[2]}
                for n in c.execute(
                    """SELECT richtung, text, zeit FROM wa_nachricht
                       WHERE faden=? AND un=? ORDER BY id LIMIT 200""",
                    (faden, inhaber))]})
        return JSONResponse({"faeden": [
            {"id": z[0], "telefon": z[1], "name": z[2], "stand": z[3],
             "zuletzt": z[4], "stumm": bool(z[5])}
            for z in c.execute(
                """SELECT id, telefon, name, stand, zuletzt, stumm FROM wa_faden
                   WHERE un=? ORDER BY zuletzt DESC LIMIT 60""", (inhaber,))]})


@app.post("/api/whatsapp/faden/{faden_id}/loeschen")
def api_wa_faden_loeschen(faden_id: int, request: Request) -> Response:
    """Ein Gesprächsverlauf mit Telefonnummer — muss weggehen können."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        c.execute("DELETE FROM wa_nachricht WHERE faden=? AND un=?",
                  (faden_id, inhaber))
        c.execute("DELETE FROM wa_faden WHERE id=? AND un=?",
                  (faden_id, inhaber))
    return JSONResponse({"ok": True})


@app.post("/api/termin/{termin_id}/bestaetigen")
def api_termin_bestaetigen(termin_id: int, request: Request) -> Response:
    """Die Anfrage aus WhatsApp annehmen. Erst hier steht der Termin fest."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        c.execute("UPDATE termin SET bestaetigt=1 WHERE id=? AND un=?",
                  (termin_id, inhaber))
        zeile = c.execute("SELECT start, telefon FROM termin WHERE id=? AND un=?",
                          (termin_id, inhaber)).fetchone()
    if zeile and zeile[1]:
        import whatsapp as wam  # noqa: PLC0415
        _wa_senden(inhaber, zeile[1], wam.kuerzen(
            f"Dein Termin am {zeile[0][:10]} um {zeile[0][11:16]} Uhr ist "
            "bestätigt. Wir freuen uns auf dich! ✂️"))
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Leistungskatalog: was der Salon anbietet, was es kostet, wie lang es dauert.
# Damit weiß ein Termin, was er wert ist — und die Rechnung, was draufsteht.
# ---------------------------------------------------------------------------

@app.get("/api/leistungen")
def api_leistungen(request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    inhaber = salon_von(un)         # geht selbst an die DB — vor das Schloss
    with _DB_LOCK, _db() as c:
        zeilen = c.execute("""SELECT id, name, preis, minuten, ust_satz, aktiv
                              FROM leistung WHERE un=? ORDER BY aktiv DESC, name""",
                           (inhaber,)).fetchall()
    return JSONResponse({"leistungen": [
        {"id": z[0], "name": z[1], "preis": z[2], "minuten": z[3],
         "ust_satz": z[4], "aktiv": bool(z[5])} for z in zeilen]})


@app.post("/api/leistungen")
async def api_leistung_speichern(request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Preise macht die Inhaberin."},
                            status_code=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    import abrechnung as ab  # noqa: PLC0415
    try:
        l = ab.leistung_pruefen(body or {})
    except ab.AbrechnungFehler as e:
        return JSONResponse({"fehler": str(e)}, status_code=400)
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        if (body or {}).get("id"):
            c.execute("""UPDATE leistung SET name=?, preis=?, minuten=?,
                         ust_satz=? WHERE id=? AND un=?""",
                      (l["name"], l["preis"], l["minuten"], l["ust_satz"],
                       int(body["id"]), inhaber))
            neue = int(body["id"])
        else:
            cur = c.execute("""INSERT INTO leistung (un, name, preis, minuten,
                               ust_satz, angelegt) VALUES (?,?,?,?,?,?)""",
                            (inhaber, l["name"], l["preis"], l["minuten"],
                             l["ust_satz"], _jetzt_iso()))
            neue = int(cur.lastrowid)
    return JSONResponse({"ok": True, "id": neue, **l})


@app.post("/api/leistung/{leistung_id}/loeschen")
def api_leistung_loeschen(leistung_id: int, request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        c.execute("DELETE FROM leistung WHERE id=? AND un=?",
                  (leistung_id, inhaber))
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Abrechnen: nach der Behandlung ein Tipp — bar oder Karte. Daraus wird ein
# VORSCHLAG fürs Kassenbuch, keine Buchung (siehe abrechnung.py).
# ---------------------------------------------------------------------------

@app.post("/api/termin/{termin_id}/abrechnen")
async def api_termin_abrechnen(termin_id: int, request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if (sperre := _mitarbeit_wache(un, "darf_kasse", "Abrechnen")):
        return sperre
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    import abrechnung as ab  # noqa: PLC0415
    import datetime as dt  # noqa: PLC0415
    try:
        zahlart = ab.zahlart_pruefen((body or {}).get("zahlart"))
    except ab.AbrechnungFehler as e:
        return JSONResponse({"fehler": str(e)}, status_code=400)

    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        zeile = c.execute("SELECT preis, start FROM termin WHERE id=? AND un=?",
                          (termin_id, inhaber)).fetchone()
        if not zeile:
            return JSONResponse({"fehler": "unbekannter Termin"}, status_code=404)
        preis = _zahl((body or {}).get("preis")) or zeile[0]
        if not preis or preis <= 0:
            return JSONResponse(
                {"fehler": "Was hat die Behandlung gekostet?"}, status_code=400)
        c.execute("""UPDATE termin SET abgerechnet=?, zahlart=?, preis=?,
                     zahlung_ref=? WHERE id=? AND un=?""",
                  (str((body or {}).get("am") or dt.date.today().isoformat())[:10],
                   zahlart, round(float(preis), 2),
                   # Die Nummer beim Zahlungsdienstleister. Sie ist das
                   # Einzige, was Kassenbuch und Kontoauszug später
                   # zusammenbringt — ohne sie ist die Zahlung nicht
                   # auffindbar, wenn jemand fragt.
                   str((body or {}).get("referenz") or "").strip()[:80] or None,
                   termin_id, inhaber))
    return JSONResponse({"ok": True, "zahlart": zahlart,
                         "preis": round(float(preis), 2)})


@app.get("/api/kasse/vorschlag")
def api_kasse_vorschlag(request: Request, datum: str = "") -> Response:
    """Was aus den abgerechneten Terminen für das Kassenbuch folgt.

    Ausdrücklich ein Vorschlag: bestätigt wird abends von der Inhaberin.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if (sperre := _mitarbeit_wache(un, "darf_kasse", "Das Kassenbuch führen")):
        return sperre
    import abrechnung as ab  # noqa: PLC0415
    import datetime as dt  # noqa: PLC0415
    datum = datum if re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum or "") \
        else dt.date.today().isoformat()
    return JSONResponse(ab.tagesvorschlag(
        datum, _termine_lesen(salon_von(un), datum, datum)))


# ---------------------------------------------------------------------------
# Kundenkartei. Personenbezogen und teils gesundheitsnah (Allergien,
# Farbformeln) — deshalb in SQLite und löschbar, nicht in der Belegbox.
# ---------------------------------------------------------------------------

@app.get("/api/kundinnen")
def api_kundinnen(request: Request, suche: str = "") -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        if suche.strip():
            zeilen = c.execute(
                """SELECT id, name, telefon, email, allergie, zuletzt FROM kundin
                   WHERE un=? AND name LIKE ? ORDER BY name LIMIT 50""",
                (inhaber, f"%{suche.strip()[:40]}%")).fetchall()
        else:
            zeilen = c.execute(
                """SELECT id, name, telefon, email, allergie, zuletzt FROM kundin
                   WHERE un=? ORDER BY zuletzt DESC, name LIMIT 100""",
                (inhaber,)).fetchall()
    return JSONResponse({"kundinnen": [
        {"id": z[0], "name": z[1], "telefon": z[2], "email": z[3],
         "allergie": z[4], "zuletzt": z[5]} for z in zeilen]})


@app.post("/api/kundinnen")
async def api_kundin_speichern(request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    name = str((body or {}).get("name") or "").strip()[:80]
    if not name:
        return JSONResponse({"fehler": "Wie heißt sie?"}, status_code=400)
    felder = {k: str((body or {}).get(k) or "").strip()[:200]
              for k in ("telefon", "email", "notiz", "allergie")}
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        if (body or {}).get("id"):
            c.execute("""UPDATE kundin SET name=?, telefon=?, email=?, notiz=?,
                         allergie=? WHERE id=? AND un=?""",
                      (name, felder["telefon"], felder["email"], felder["notiz"],
                       felder["allergie"], int(body["id"]), inhaber))
            neue = int(body["id"])
        else:
            cur = c.execute("""INSERT INTO kundin (un, name, telefon, email,
                               notiz, allergie, angelegt) VALUES (?,?,?,?,?,?,?)""",
                            (inhaber, name, felder["telefon"], felder["email"],
                             felder["notiz"], felder["allergie"], _jetzt_iso()))
            neue = int(cur.lastrowid)
    return JSONResponse({"ok": True, "id": neue, "name": name, **felder})


@app.get("/api/kundin/{kundin_id}")
def api_kundin(kundin_id: int, request: Request) -> Response:
    """Eine Kundin mit ihrem Verlauf — was wann gemacht wurde, mit welcher
    Formel. Das ist das Wissen, das sonst im Karteikasten steckt."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        z = c.execute("""SELECT id, name, telefon, email, notiz, allergie, angelegt
                         FROM kundin WHERE id=? AND un=?""",
                      (kundin_id, inhaber)).fetchone()
        if not z:
            return JSONResponse({"fehler": "unbekannt"}, status_code=404)
        verlauf = [{"id": b[0], "datum": b[1], "leistung": b[2], "formel": b[3],
                    "notiz": b[4]}
                   for b in c.execute(
                       """SELECT id, datum, leistung, formel, notiz FROM behandlung
                          WHERE un=? AND kundin=? ORDER BY datum DESC LIMIT 60""",
                       (inhaber, kundin_id))]
    return JSONResponse({"id": z[0], "name": z[1], "telefon": z[2], "email": z[3],
                         "notiz": z[4], "allergie": z[5], "angelegt": z[6],
                         "verlauf": verlauf})


@app.post("/api/kundin/{kundin_id}/behandlung")
async def api_behandlung(kundin_id: int, request: Request) -> Response:
    """Was gemacht wurde — samt Farbformel. Beim nächsten Mal steht es da."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    import datetime as dt  # noqa: PLC0415
    datum = str((body or {}).get("datum") or dt.date.today().isoformat())[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum):
        return JSONResponse({"fehler": "Datum als JJJJ-MM-TT"}, status_code=400)
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        if not c.execute("SELECT 1 FROM kundin WHERE id=? AND un=?",
                         (kundin_id, inhaber)).fetchone():
            return JSONResponse({"fehler": "unbekannt"}, status_code=404)
        c.execute("""INSERT INTO behandlung (un, kundin, datum, leistung, formel,
                     notiz, termin, angelegt) VALUES (?,?,?,?,?,?,?,?)""",
                  (inhaber, kundin_id, datum,
                   str((body or {}).get("leistung") or "").strip()[:80],
                   str((body or {}).get("formel") or "").strip()[:200],
                   str((body or {}).get("notiz") or "").strip()[:400],
                   (body or {}).get("termin"), _jetzt_iso()))
        c.execute("UPDATE kundin SET zuletzt=? WHERE id=? AND un=?",
                  (datum, kundin_id, inhaber))
    return JSONResponse({"ok": True})


@app.post("/api/kundin/{kundin_id}/loeschen")
def api_kundin_loeschen(kundin_id: int, request: Request) -> Response:
    """Ganz weg, mit allem Verlauf. Personenbezogenes muss sich löschen
    lassen — und Farbformeln und Allergiehinweise ganz besonders."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    inhaber = salon_von(un)
    with _DB_LOCK, _db() as c:
        c.execute("DELETE FROM behandlung WHERE kundin=? AND un=?",
                  (kundin_id, inhaber))
        c.execute("DELETE FROM kundin WHERE id=? AND un=?", (kundin_id, inhaber))
    return JSONResponse({"ok": True})


@app.get("/api/meldungen")
def api_meldungen(request: Request) -> Response:
    """Was babu heute von sich aus sagen würde.

    Die App holt das ab und legt daraus Erinnerungen an. Höchstens drei —
    wer dreimal umsonst aufs Telefon schaut, schaltet beim vierten Mal ab.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        # Fristen und offene Rechnungen gehen die Inhaberin an, nicht das Team.
        return JSONResponse({"meldungen": []})
    import datetime as dt  # noqa: PLC0415
    import melden  # noqa: PLC0415
    import vertraege as vt  # noqa: PLC0415

    inhaber = salon_von(un)
    idx = index_aktuell()
    heute = dt.date.today()
    einstellungen = db_einstellungen(inhaber)

    termine: list[dict] = []
    try:
        import fristen as fr  # noqa: PLC0415
        profil = fr.termin_profil(einstellungen,
                                  hat_team=bool(team_liste(inhaber, nur_aktive=True)))
        termine = fr.naechste(fr.fristen_jahr(heute.year, profil), heute, anzahl=8)
    except Exception:  # noqa: BLE001
        termine = []

    welt = {
        "fristen": termine,
        "vertraege": vt.uebersicht(vertraege_aktuell(), heute)["vertraege"],
        "rechnungen": list(idx.get("rechnungen", {}).values()),
        "belege": list(idx["belege"].values()),
    }
    return JSONResponse({"meldungen": melden.meldungen(welt, heute),
                         "stand": heute.isoformat()})


@app.get("/api/vertraege")
def api_vertraege(request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Die Zahlen sieht nur die Inhaberin."},
                            status_code=403)
    import vertraege as vt  # noqa: PLC0415
    return JSONResponse(vt.uebersicht(vertraege_aktuell()))


# ---------------------------------------------------------------------------
# Der Briefkopf: eine Rechnung ist oft das Einzige, was eine Kundin
# schriftlich vom Salon in die Hand bekommt. Logo und ein Stil, den babu aus
# den Firmendaten vorschlägt — das Zeichnen macht die App.
# ---------------------------------------------------------------------------

LOGOS = Path(os.environ.get("BABU_LOGOS", str(Path.home() / "babu-web" / "logos")))
LOGO_MAX = 4 * 1024 * 1024
LOGO_TYPEN = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg"}


def _logo_pfad(un: str) -> Path:
    return LOGOS / (hashlib.sha256(un.encode()).hexdigest()[:16] + ".bin")


def _stil_aus_einstellungen(e: dict) -> dict:
    import marke  # noqa: PLC0415
    return marke.stil_pruefen({
        "farbe": e.get("marke_farbe"), "schrift": e.get("marke_schrift"),
        "ausrichtung": e.get("marke_ausrichtung"),
        "linie": (e.get("marke_linie") or "1") != "0",
        "begruendung": e.get("marke_begruendung"),
    })


@app.get("/api/marke")
def api_marke(request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    import marke  # noqa: PLC0415
    inhaber = salon_von(un)
    stil = _stil_aus_einstellungen(db_einstellungen(inhaber))
    return JSONResponse({**stil, "in_worten": marke.als_text(stil),
                         "logo": _logo_pfad(inhaber).is_file()})


@app.get("/api/marke/katalog")
def api_marke_katalog(request: Request) -> Response:
    """Die vier Schritte und die Farben, aus denen gewählt wird."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    import marke  # noqa: PLC0415
    return JSONResponse({"schritte": list(marke.SCHRITTE),
                         "farben": list(marke.KATALOG),
                         "stile": [{"schluessel": k, "name": k.capitalize(),
                                    "dazu": v.split(",")[0]}
                                   for k, v in marke.LOGO_STILE.items()]})


@app.post("/api/marke/farbe")
async def api_marke_farbe(request: Request) -> Response:
    """Schritt 1: eine Farbe aus dem Katalog wählen."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    import marke  # noqa: PLC0415
    eintrag = marke.farbe_aus_katalog((body or {}).get("farbe"))
    if eintrag is None:
        return JSONResponse({"fehler": "Diese Farbe kennen wir nicht."},
                            status_code=400)
    db_einstellung_setzen(salon_von(un), "marke_farbe", eintrag["hex"])
    return JSONResponse({"ok": True, **eintrag})


@app.post("/api/marke/logo")
async def api_marke_logo(request: Request) -> Response:
    """Das Logo des Salons — es liegt NICHT in der Belegbox: ein Logo wird
    ausgetauscht, und in Git bleibt jede Fassung für immer stehen."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
    daten = await request.body()
    if not daten:
        return JSONResponse({"fehler": "leer"}, status_code=400)
    if len(daten) > LOGO_MAX:
        return JSONResponse({"fehler": "Das Bild ist zu groß — bis 4 MB."},
                            status_code=413)
    if not any(daten.startswith(k) for k in LOGO_TYPEN):
        return JSONResponse({"fehler": "Bitte als PNG oder JPG."}, status_code=400)
    pfad = _logo_pfad(salon_von(un))
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(daten)
    return JSONResponse({"ok": True})


@app.get("/api/marke/logo")
def api_marke_logo_holen(request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    pfad = _logo_pfad(salon_von(un))
    if not pfad.is_file():
        return JSONResponse({"fehler": "kein Logo"}, status_code=404)
    daten = pfad.read_bytes()
    typ = next((t for k, t in LOGO_TYPEN.items() if daten.startswith(k)),
               "application/octet-stream")
    return Response(content=daten, media_type=typ,
                    headers={"Cache-Control": "private, max-age=300"})


@app.post("/api/marke/logo/loeschen")
def api_marke_logo_loeschen(request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    _logo_pfad(salon_von(un)).unlink(missing_ok=True)
    return JSONResponse({"ok": True})


# Nano Banana (gemini-3-pro-image). Der Schlüssel steht in einer .env-Zeile
# und wird NIE geloggt. Ohne Schlüssel gibt es die Funktion schlicht nicht.
GEMINI_MODELL = os.environ.get("BABU_BILD_MODELL", "gemini-3-pro-image")
GEMINI_ENV = Path(os.environ.get("BABU_GEMINI_ENV", str(Path.home() / "Youtube" / ".env")))


def _gemini_schluessel() -> str | None:
    """Die eine Zeile parsen — die Datei enthält kaputte Zeilen, `source`
    würde daran scheitern."""
    schluessel = os.environ.get("GEMINI_API_KEY")
    if schluessel:
        return schluessel.strip()
    try:
        for zeile in GEMINI_ENV.read_text(errors="replace").splitlines():
            if zeile.strip().startswith("GEMINI_API_KEY"):
                return zeile.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        return None
    return None


@app.post("/api/marke/logo/entwerfen")
def api_marke_logo_entwerfen(request: Request, stil: str = "schlicht") -> Response:
    """babu entwirft ein Logo aus den Firmendaten.

    Der Name des Salons geht dafür an einen Dienst außerhalb des Hauses
    (Google). Das steht so in der Oberfläche — es ist die einzige Stelle in
    babu, an der Betriebsdaten das Haus verlassen.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
    schluessel = _gemini_schluessel()
    if not schluessel:
        return JSONResponse(
            {"fehler": "Für entworfene Logos fehlt der Zugang — lade solange "
                       "dein eigenes Bild hoch."}, status_code=501)

    import marke  # noqa: PLC0415
    inhaber = salon_von(un)
    einstellungen = db_einstellungen(inhaber)
    auftrag = marke.logo_auftrag(einstellungen, stil,
                                 einstellungen.get("marke_farbe"))
    bild = _logo_erzeugen(auftrag, schluessel)
    if bild is None:
        return JSONResponse(
            {"fehler": "Der Entwurf kam gerade nicht durch — versuch es "
                       "gleich nochmal."}, status_code=503)

    if not bild or len(bild) > LOGO_MAX * 4:
        return JSONResponse({"fehler": "Das Bild kam unbrauchbar zurück."},
                            status_code=503)
    pfad = _logo_pfad(inhaber)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(bild)
    print(f"[logo] entworfen für {inhaber} ({len(bild)} Bytes, Stil {stil})", flush=True)
    return JSONResponse({"ok": True, "stil": stil, "bytes": len(bild)})


def _bild_erzeugen(auftrag: str, schluessel: str, format_: str = "1:1",
                   was: str = "bild") -> bytes | None:
    """Ein Bild von Nano Banana holen — blockierend, gehört in den Threadpool.

    Gibt None zurück, statt zu werfen: bei zehn gleichzeitigen Versuchen darf
    einer danebengehen, ohne die anderen mitzureißen.
    """
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_MODELL}:generateContent",
            headers={"x-goog-api-key": schluessel},
            json={"contents": [{"parts": [{"text": auftrag}]}],
                  "generationConfig": {"responseModalities": ["IMAGE"],
                                       "imageConfig": {"aspectRatio": format_}}},
            timeout=180)
        r.raise_for_status()
        teile = r.json()["candidates"][0]["content"]["parts"]
        roh = next(t["inlineData"]["data"] for t in teile if "inlineData" in t)
        return base64.b64decode(roh)
    except Exception as e:  # noqa: BLE001
        # Nie den Schlüssel mitloggen — nur den Typ des Fehlers.
        print(f"[{was}] gescheitert: {type(e).__name__}", flush=True)
        return None


def _logo_erzeugen(auftrag: str, schluessel: str) -> bytes | None:
    return _bild_erzeugen(auftrag, schluessel, "1:1", "logo")


def _vorschlag_pfad(un: str, nummer: int) -> Path:
    return LOGOS / hashlib.sha256(un.encode()).hexdigest()[:16] / f"v{nummer}.bin"


@app.post("/api/marke/vorschlaege")
async def api_marke_vorschlaege(request: Request, saat: int = 0) -> Response:
    """Ein Knopf, zehn Zeichen.

    Statt sich durch Farbe und Stil zu tasten: babu entwirft zehn auf einmal,
    eines antippen — und der ganze Auftritt steht. Die zehn entstehen
    gleichzeitig, sonst dauert es zehnmal so lang.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
    schluessel = _gemini_schluessel()
    if not schluessel:
        return JSONResponse(
            {"fehler": "Für entworfene Zeichen fehlt der Zugang — lade solange "
                       "dein eigenes Bild hoch."}, status_code=501)

    import concurrent.futures as futures  # noqa: PLC0415
    import marke  # noqa: PLC0415
    inhaber = salon_von(un)
    saetze = marke.vorschlag_saetze(db_einstellungen(inhaber), saat=saat)

    def hole(satz: dict) -> tuple[dict, bytes | None]:
        return satz, _logo_erzeugen(satz["auftrag"], schluessel)

    def alle() -> list[tuple[dict, bytes | None]]:
        with futures.ThreadPoolExecutor(max_workers=len(saetze)) as pool:
            return list(pool.map(hole, saetze))

    ergebnisse = await run_in_threadpool(alle)

    ordner = _vorschlag_pfad(inhaber, 0).parent
    ordner.mkdir(parents=True, exist_ok=True)
    fertig = []
    for satz, bild in ergebnisse:
        if not bild:
            continue
        _vorschlag_pfad(inhaber, satz["nummer"]).write_bytes(bild)
        fertig.append({"nummer": satz["nummer"], "stil": satz["stil"],
                       "farbe": satz["farbe"], "farbe_name": satz["farbe_name"]})
    if not fertig:
        return JSONResponse({"fehler": "Die Entwürfe kamen gerade nicht durch — "
                                       "versuch es gleich nochmal."}, status_code=503)
    print(f"[logo] {len(fertig)} von {len(saetze)} Vorschlägen für {inhaber}",
          flush=True)
    return JSONResponse({"vorschlaege": fertig, "saat": saat})


@app.get("/api/marke/vorschlag/{nummer}")
def api_marke_vorschlag_bild(nummer: int, request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    pfad = _vorschlag_pfad(salon_von(un), nummer)
    if not (0 <= nummer < 12) or not pfad.is_file():
        return JSONResponse({"fehler": "kein Vorschlag"}, status_code=404)
    daten = pfad.read_bytes()
    typ = next((t for k, t in LOGO_TYPEN.items() if daten.startswith(k)),
               "application/octet-stream")
    return Response(content=daten, media_type=typ,
                    headers={"Cache-Control": "private, max-age=300"})


@app.post("/api/marke/waehlen")
async def api_marke_waehlen(request: Request) -> Response:
    """Ein Vorschlag angetippt — und der ganze Auftritt steht."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
    try:
        body = await request.json()
        nummer = int((body or {}).get("nummer"))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit nummer erwartet"}, status_code=400)

    import marke  # noqa: PLC0415
    inhaber = salon_von(un)
    quelle = _vorschlag_pfad(inhaber, nummer)
    if not (0 <= nummer < 12) or not quelle.is_file():
        return JSONResponse({"fehler": "Diesen Vorschlag gibt es nicht mehr."},
                            status_code=404)

    ziel = _logo_pfad(inhaber)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(quelle.read_bytes())

    saetze = {s["nummer"]: s for s in marke.vorschlag_saetze(
        db_einstellungen(inhaber), saat=int((body or {}).get("saat") or 0))}
    auftritt = marke.auftritt_aus(saetze.get(nummer, {}))
    for schluessel, wert in (("marke_farbe", auftritt["farbe"]),
                             ("marke_schrift", auftritt["schrift"]),
                             ("marke_ausrichtung", auftritt["ausrichtung"]),
                             ("marke_linie", "1" if auftritt["linie"] else "0"),
                             ("marke_begruendung", auftritt.get("begruendung", ""))):
        db_einstellung_setzen(inhaber, schluessel, str(wert))
    # Die übrigen Entwürfe braucht niemand mehr.
    for n in range(12):
        if n != nummer:
            _vorschlag_pfad(inhaber, n).unlink(missing_ok=True)
    return JSONResponse({"ok": True, **auftritt,
                         "in_worten": marke.als_text(auftritt)})


# ---------------------------------------------------------------------------
# Marketing: was der Salon nach außen zeigt. babu kennt Name, Farbe und
# Zeichen — damit macht es das, wofür sonst niemand Zeit hat.
# ---------------------------------------------------------------------------

MARKETING = LOGOS.parent / "marketing" if LOGOS.name == "logos" else LOGOS / "marketing"


def _stueck_pfad(un: str, schluessel: str) -> Path:
    return (MARKETING / hashlib.sha256(un.encode()).hexdigest()[:16]
            / f"{re.sub(r'[^a-z]', '', schluessel)}.bin")


@app.get("/api/marketing")
def api_marketing(request: Request) -> Response:
    """Was babu gestalten kann — und was schon da ist."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    import marketing as mk  # noqa: PLC0415
    inhaber = salon_von(un)
    stuecke = [dict(s, fertig=_stueck_pfad(inhaber, s["schluessel"]).is_file())
               for s in mk.stuecke_liste()]
    return JSONResponse({"stuecke": stuecke,
                         "farbe": db_einstellungen(inhaber).get("marke_farbe")
                                  or "#1F1D1B"})


@app.post("/api/marketing/entwerfen")
async def api_marketing_entwerfen(request: Request) -> Response:
    """Ein Aushang, ein Beitrag, ein Gutschein — in den Farben des Salons.

    Was drauf steht, schreibt die Inhaberin. babu gestaltet es nur: ein
    Rabatt, den niemand beschlossen hat, hat auf keinem Aushang etwas
    verloren.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
    schluessel = _gemini_schluessel()
    if not schluessel:
        return JSONResponse({"fehler": "Dafür fehlt gerade der Zugang."},
                            status_code=501)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)

    import marketing as mk  # noqa: PLC0415
    inhaber = salon_von(un)
    einstellungen = db_einstellungen(inhaber)
    try:
        stueck = mk.stueck(str((body or {}).get("stueck") or ""))
        auftrag = mk.auftrag(stueck["schluessel"], (body or {}).get("text"),
                             einstellungen)
    except mk.MarketingFehler as e:
        return JSONResponse({"fehler": str(e)}, status_code=400)

    bild = await run_in_threadpool(_bild_erzeugen, auftrag, schluessel,
                                   stueck["format"], "marketing")
    if not bild:
        return JSONResponse({"fehler": "Das kam gerade nicht durch — versuch es "
                                       "gleich nochmal."}, status_code=503)
    pfad = _stueck_pfad(inhaber, stueck["schluessel"])
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(bild)
    return JSONResponse({"ok": True, "stueck": stueck["schluessel"],
                         "name": stueck["name"], "bytes": len(bild)})


@app.get("/api/marketing/{schluessel}")
def api_marketing_bild(schluessel: str, request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    pfad = _stueck_pfad(salon_von(un), schluessel)
    if not pfad.is_file():
        return JSONResponse({"fehler": "noch nichts gestaltet"}, status_code=404)
    daten = pfad.read_bytes()
    typ = next((t for k, t in LOGO_TYPEN.items() if daten.startswith(k)),
               "application/octet-stream")
    return Response(content=daten, media_type=typ,
                    headers={"Cache-Control": "private, max-age=300"})


@app.post("/api/marke/entwerfen")
def api_marke_entwerfen(request: Request) -> Response:
    """babu schlägt einen Briefkopf vor — aus dem, was es über den Salon weiß.

    Was das Modell antwortet, wird geprüft, nicht geglaubt: unbrauchbare
    Farben oder erfundene Schriften fallen auf die Vorgabe zurück. Eine
    Rechnung wird gedruckt und muss lesbar bleiben.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
    import marke  # noqa: PLC0415
    inhaber = salon_von(un)
    einstellungen = db_einstellungen(inhaber)
    frage = marke.frage_bauen(einstellungen)
    roh: dict = {}
    try:
        with _LLM_SEMAPHORE:
            r = requests.post(GEMMA_API, json={
                "model": GEMMA_MODELL, "temperature": 0.6, "max_tokens": 300,
                "messages": [{"role": "user", "content": frage}],
            }, timeout=90)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        treffer = re.search(r"\{.*\}", text, re.S)
        roh = json.loads(treffer.group(0)) if treffer else {}
    except Exception:  # noqa: BLE001
        return JSONResponse(
            {"fehler": "Der Vorschlag kam gerade nicht durch — versuch es "
                       "gleich nochmal, oder wähle selbst."}, status_code=503)

    stil = marke.stil_pruefen(roh)
    for schluessel, wert in (("marke_farbe", stil["farbe"]),
                             ("marke_schrift", stil["schrift"]),
                             ("marke_ausrichtung", stil["ausrichtung"]),
                             ("marke_linie", "1" if stil["linie"] else "0"),
                             ("marke_begruendung", stil.get("begruendung", ""))):
        db_einstellung_setzen(inhaber, schluessel, str(wert))
    return JSONResponse({**stil, "in_worten": marke.als_text(stil)})


@app.post("/api/angaben/{stamm}")
async def api_angaben(stamm: str, request: Request) -> Response:
    """Was babu nicht lesen konnte, trägt die Nutzerin selbst nach —
    Betrag, Datum, Laden. Eigener Commit, das Original bleibt unberührt."""
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if not NAME_RE.match(stamm):
        return JSONResponse({"fehler": "ungültiger Name"}, status_code=400)
    if stamm not in (await run_in_threadpool(index_aktuell))["belege"]:
        return JSONResponse({"fehler": "unbekannter Beleg"}, status_code=404)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)

    daten: dict = {"von": un, "am": _jetzt_iso(), "beantwortet": []}
    roh = str(body.get("brutto", "")).strip().replace(".", "").replace(",", ".")
    if roh:
        try:
            betrag = round(float(roh), 2)
        except ValueError:
            return JSONResponse({"fehler": "Den Betrag konnten wir nicht lesen — z. B. 4,20"},
                                status_code=400)
        if not 0 < betrag < 1_000_000:
            return JSONResponse({"fehler": "Der Betrag sieht nicht richtig aus."},
                                status_code=400)
        daten["brutto"] = betrag
        daten["beantwortet"].append("brutto")
    lieferant = str(body.get("lieferant", "")).strip()[:80]
    if lieferant:
        daten["lieferant"] = lieferant
        daten["beantwortet"].append("lieferant")
    datum = str(body.get("datum", "")).strip()[:10]
    if datum:
        daten["datum"] = datum
        daten["beantwortet"].append("datum")
    notiz = str(body.get("notiz", "")).strip()[:200]
    if notiz:
        daten["notiz"] = notiz
    if not daten["beantwortet"] and not notiz:
        return JSONResponse({"fehler": "Bitte mindestens eine Angabe ausfüllen."},
                            status_code=400)

    import boxschreiber  # noqa: PLC0415
    try:
        commit = await run_in_threadpool(boxschreiber.schreiben,
            f"review/{stamm}.angaben.json",
            json.dumps(daten, ensure_ascii=False, indent=1).encode(),
            f"angaben: {stamm}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit, "angaben": daten})


def vertraege_aktuell() -> list[dict]:
    """Alle gelesenen Verträge — die Dauerkosten des Salons."""
    return [d["vertrag"] for d in index_aktuell()["dokumente"]
            if isinstance(d.get("vertrag"), dict)]


# ---------------------------------------------------------------------------
# Dein Team: wer im Salon arbeitet und was er kostet. Bewusst minimal —
# Steuerklasse, Sozialversicherung und Lohnsteuer macht das Lohnbüro.
# babu braucht nur die Summe, damit die Auswertung stimmt.
# ---------------------------------------------------------------------------

def team_liste(un: str, nur_aktive: bool = False) -> list[dict]:
    with _DB_LOCK, _db() as c:
        sql = """SELECT id, name, email, lohn_art, betrag, stundenlohn, stunden,
                        seit, aktiv, darf_belege, darf_kasse, zugang
                 FROM team WHERE un=?"""
        if nur_aktive:
            sql += " AND aktiv=1"
        zeilen = c.execute(sql + " ORDER BY aktiv DESC, name", (un,)).fetchall()
    leute = []
    for z in zeilen:
        person = {"id": z[0], "name": z[1], "email": z[2], "lohn_art": z[3],
                  "betrag": z[4], "stundenlohn": z[5], "stunden": z[6],
                  "seit": z[7], "aktiv": bool(z[8]),
                  "darf_belege": bool(z[9]), "darf_kasse": bool(z[10]),
                  "hat_zugang": bool(z[11])}
        person["kosten_monat"] = round(
            (z[4] or 0.0) if z[3] == "fest" else (z[5] or 0.0) * (z[6] or 0.0), 2)
        person["foto"] = (f"/api/team-foto/{z[0]}"
                          if _foto_pfad(un, z[0]).is_file() else None)
        leute.append(person)
    return leute


def team_personalkosten(un: str) -> float | None:
    """Was das Team im Monat kostet — Grundlage der Auswertung."""
    aktive = [p for p in team_liste(un, nur_aktive=True) if p["kosten_monat"]]
    return round(sum(p["kosten_monat"] for p in aktive), 2) if aktive else None


@app.get("/api/team")
def api_team(request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Das Team verwaltet die Inhaberin."},
                            status_code=403)
    leute = team_liste(un)
    return JSONResponse({
        "team": leute,
        "kosten_monat": round(sum(p["kosten_monat"] for p in leute if p["aktiv"]), 2),
        "anzahl_aktiv": sum(1 for p in leute if p["aktiv"]),
    })


@app.post("/api/team")
async def api_team_speichern(request: Request) -> Response:
    """Anlegen oder ändern — vier Angaben reichen."""
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)

    name = str(body.get("name", "")).strip()[:80]
    if not name:
        return JSONResponse({"fehler": "Wie heißt sie oder er?"}, status_code=400)
    email = str(body.get("email", "")).strip().lower()[:120]
    if email and "@" not in email:
        return JSONResponse({"fehler": "Die E-Mail sieht nicht richtig aus."},
                            status_code=400)
    lohn_art = "stunden" if str(body.get("lohn_art")) == "stunden" else "fest"
    betrag = _zahl(body.get("betrag"))
    stundenlohn = _zahl(body.get("stundenlohn"))
    stunden = _zahl(body.get("stunden"))
    if lohn_art == "fest" and betrag is not None and not 0 <= betrag < 50_000:
        return JSONResponse({"fehler": "Der Betrag sieht nicht richtig aus."},
                            status_code=400)
    if lohn_art == "stunden" and stundenlohn is not None and not 0 <= stundenlohn < 500:
        return JSONResponse({"fehler": "Der Stundenlohn sieht nicht richtig aus."},
                            status_code=400)
    seit = str(body.get("seit", "")).strip()[:10] or None
    person_id = body.get("id")

    with _DB_LOCK, _db() as c:
        darf_belege = 1 if body.get("darf_belege") else 0
        darf_kasse = 1 if body.get("darf_kasse") else 0
        if person_id:
            c.execute("""UPDATE team SET name=?, email=?, lohn_art=?, betrag=?,
                         stundenlohn=?, stunden=?, seit=?, darf_belege=?,
                         darf_kasse=? WHERE id=? AND un=?""",
                      (name, email or None, lohn_art, betrag, stundenlohn,
                       stunden, seit, darf_belege, darf_kasse,
                       int(person_id), un))
        else:
            c.execute("""INSERT INTO team (un, name, email, lohn_art, betrag,
                         stundenlohn, stunden, seit, angelegt, darf_belege, darf_kasse)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                      (un, name, email or None, lohn_art, betrag, stundenlohn,
                       stunden, seit, _jetzt_iso(), darf_belege, darf_kasse))
    return JSONResponse({"ok": True, "team": team_liste(un),
                         "kosten_monat": team_personalkosten(un) or 0.0})


@app.post("/api/team-zugang")
async def api_team_zugang(request: Request) -> Response:
    """Die Inhaberin gibt jemandem einen eigenen Zugang zur App.

    Das Konto zeigt auf ihren Salon: was die Mitarbeiterin einreicht,
    landet in DER Belegbox — nicht in einer eigenen. Was sie darf,
    steht in ihren Rechten.
    """
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Zugänge vergibt die Inhaberin."},
                            status_code=403)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    person_id = body.get("id")
    with _DB_LOCK, _db() as c:
        zeile = c.execute("SELECT name, email, zugang FROM team WHERE id=? AND un=?",
                          (int(person_id or 0), un)).fetchone()
    if not zeile:
        return JSONResponse({"fehler": "unbekannt"}, status_code=404)
    name, email, vorhanden = zeile
    if vorhanden:
        return JSONResponse({"fehler": f"{name} hat schon einen Zugang."},
                            status_code=409)
    if not email or "@" not in email:
        return JSONResponse(
            {"fehler": f"Für den Zugang braucht {name} eine E-Mail-Adresse."},
            status_code=400)

    startpasswort = nutzer_anlegen(email.lower(), name,
                                   db_einstellungen(un).get("betrieb_name") or "",
                                   "mitarbeit")
    if startpasswort is None:
        return JSONResponse({"fehler": "Diese E-Mail hat schon ein Konto."},
                            status_code=409)
    with _DB_LOCK, _db() as c:
        c.execute("UPDATE nutzer SET gehoert_zu=? WHERE email=?", (un, email.lower()))
        c.execute("UPDATE team SET zugang=? WHERE id=? AND un=?",
                  (email.lower(), int(person_id), un))
    print(f"[team] Zugang für {email.lower()} im Salon {un}", flush=True)
    return JSONResponse({"ok": True, "email": email.lower(),
                         "startpasswort": startpasswort,
                         "hinweis": "Startpasswort jetzt notieren und persönlich "
                                    "weitergeben — es erscheint nur dieses eine Mal."})


@app.post("/api/team-aktion")
async def api_team_aktion(request: Request) -> Response:
    """Jemand hört auf oder kommt zurück — Daten bleiben, nur der Haken geht."""
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    person_id = body.get("id")
    aktion = str(body.get("aktion", ""))
    if not person_id or aktion not in ("beenden", "zurueck", "loeschen"):
        return JSONResponse({"fehler": "unbekannte Aktion"}, status_code=400)
    with _DB_LOCK, _db() as c:
        if aktion == "loeschen":
            c.execute("DELETE FROM team WHERE id=? AND un=?", (int(person_id), un))
            _foto_pfad(un, int(person_id)).unlink(missing_ok=True)
        else:
            an = 1 if aktion == "zurueck" else 0
            c.execute("UPDATE team SET aktiv=? WHERE id=? AND un=?",
                      (an, int(person_id), un))
            # Wer nicht mehr da ist, kommt auch nicht mehr in die App.
            zugang = c.execute("SELECT zugang FROM team WHERE id=? AND un=?",
                               (int(person_id), un)).fetchone()
            if zugang and zugang[0]:
                c.execute("UPDATE nutzer SET aktiv=? WHERE email=?", (an, zugang[0]))
    return JSONResponse({"ok": True, "team": team_liste(un),
                         "kosten_monat": team_personalkosten(un) or 0.0})


# Mitarbeiterfotos liegen NICHT in der Git-Box: Personenfotos müssen
# löschbar sein (Art. 17 DSGVO), und in Git bleibt alles für immer stehen.
TEAM_FOTOS = Path(os.environ.get("BABU_TEAM_FOTOS",
                                 str(Path.home() / "babu-web" / "team-fotos")))
FOTO_MAX = 8 * 1024 * 1024


def _foto_pfad(un: str, person_id: int) -> Path:
    ordner = TEAM_FOTOS / hashlib.sha256(un.encode()).hexdigest()[:16]
    return ordner / f"{person_id}.jpg"


@app.post("/api/team-foto")
async def api_team_foto(request: Request, id: int) -> Response:
    """Foto einer Mitarbeiterin — aufgenommen in der App, hier abgelegt."""
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    with _DB_LOCK, _db() as c:
        if not c.execute("SELECT 1 FROM team WHERE id=? AND un=?",
                         (id, un)).fetchone():
            return JSONResponse({"fehler": "unbekannt"}, status_code=404)
    daten = await request.body()
    if not daten or len(daten) > FOTO_MAX:
        return JSONResponse({"fehler": "Das Bild ist zu groß."}, status_code=413)
    pfad = _foto_pfad(un, id)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(daten)
    return JSONResponse({"ok": True, "url": f"/api/team-foto/{id}"})


@app.get("/api/team-foto/{person_id}")
def api_team_foto_holen(person_id: int, request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    pfad = _foto_pfad(un, person_id)
    if not pfad.is_file():
        return JSONResponse({"fehler": "kein Bild"}, status_code=404)
    return FileResponse(pfad, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=300"})


@app.get("/api/monatsabschluss/{monat}")
def api_monatsabschluss(monat: str, request: Request) -> Response:
    """BWA und Umsatzsteuer-Entwurf eines Monats — aus Belegen und Kassenbuch.

    Entwurf, kein fertiger Abschluss: geprüft und übermittelt wird vom
    steuerlichen Backend. Was babu nicht sicher weiß, steht in der Prüfliste.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if not re.fullmatch(r"\d{4}-\d{2}", monat):
        return JSONResponse({"fehler": "Monat als JJJJ-MM"}, status_code=400)
    import monatsabschluss as ma  # noqa: PLC0415

    idx = index_aktuell()
    blaetter = [b for tag, b in idx["kassenblaetter"].items()
                if tag.startswith(monat)]
    belege = [z for z in idx["belege"].values() if z["monat"] == monat]
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Die Zahlen sieht nur die Inhaberin."},
                            status_code=403)
    einstellungen = db_einstellungen(un)

    profil = ma.umsatz_profil(einstellungen)
    erloese = ma.erloese_monat(blaetter, monat=monat,
                               rechnungen=list(idx.get("rechnungen", {}).values()),
                               versteuerung=_versteuerung(un))
    vorsteuer = ma.vorsteuer_monat(belege)

    # Vorjahreswerte aus dem Salon-Check, wenn vorhanden.
    vorjahr = None
    jahr = int(monat[:4]) - 1
    roh = git_show(f"abschluss/{jahr}/kennzahlen.json")
    if roh:
        try:
            vorjahr = (json.loads(roh) or {}).get("zahlen")
        except Exception:  # noqa: BLE001
            vorjahr = None

    return JSONResponse({
        "monat": monat,
        "erloese": erloese,
        "bwa": ma.bwa(monat, erloese, belege, vorjahr,
                      personal_monat=(team_personalkosten(un)
                                      or _zahl(einstellungen.get("personal_monat"))),
                      vertraege=vertraege_aktuell()),
        "ustva": ma.ustva_entwurf(monat, erloese, vorsteuer, profil),
        "profil": profil,
    })


@app.post("/api/monatsabschluss/{monat}/freigeben")
def api_monatsabschluss_freigeben(monat: str, request: Request) -> Response:
    """Den Entwurf zur Prüfung übergeben — an das steuerliche Backend.

    babu rechnet und legt ab; geprüft und ans Finanzamt übermittelt wird
    dort. Die Ablage ist der Nachweis: Zahlen, Prüfliste und Zeitpunkt
    liegen unveränderlich in der Belegbox.
    """
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if not re.fullmatch(r"\d{4}-\d{2}", monat):
        return JSONResponse({"fehler": "Monat als JJJJ-MM"}, status_code=400)
    if rolle(un) == "mitarbeit":
        return JSONResponse({"fehler": "Freigeben darf nur die Inhaberin."},
                            status_code=403)

    antwort = api_monatsabschluss(monat, request)
    if antwort.status_code != 200:
        return antwort
    zahlen = json.loads(antwort.body)

    offen = (zahlen.get("ustva") or {}).get("pruefliste") or []
    inhalt = json.dumps({
        "monat": monat, "von": un,
        "am": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ustva": zahlen.get("ustva"), "bwa": zahlen.get("bwa"),
        "erloese": zahlen.get("erloese"),
        "hinweis": "Entwurf aus babu — Prüfung und Übermittlung durch das Steuer-Backend.",
    }, ensure_ascii=False, indent=1).encode()

    import boxschreiber  # noqa: PLC0415
    try:
        commit = boxschreiber.schreiben(f"abschluss/{monat}/ustva.json", inhalt,
                                        f"monatsabschluss {monat} freigegeben", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    with _INDEX_LOCK:
        _INDEX["geprueft"] = 0.0
    return JSONResponse({"ok": True, "commit": commit, "monat": monat,
                         "offene_punkte": len(offen)})


@app.get("/api/fristen/{jahr}")
def api_fristen(jahr: str, request: Request) -> Response:
    """Die steuerlichen Termine eines Jahres — und was als Nächstes ansteht.

    Gerechnet aus den Stammdaten: Kleinunternehmerin bekommt keine
    Voranmeldungen, wer ein Team hat zusätzlich Lohnsteuer und die
    Sozialversicherung (der Termin, der am schnellsten Geld kostet).
    """
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if not re.fullmatch(r"\d{4}", jahr):
        return JSONResponse({"fehler": "Jahr als JJJJ"}, status_code=400)
    import datetime as dt  # noqa: PLC0415
    import fristen as fr  # noqa: PLC0415

    inhaber = salon_von(un)
    profil = fr.termin_profil(db_einstellungen(inhaber),
                             hat_team=bool(team_liste(inhaber, nur_aktive=True)))
    termine = fr.fristen_jahr(int(jahr), profil)
    heute = dt.date.today()
    return JSONResponse({
        "jahr": int(jahr), "profil": profil, "termine": termine,
        "naechste": fr.naechste(termine, heute, anzahl=3),
    })


@app.post("/api/kassenbuch")
async def api_kassenbuch(request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler:
        return fehler
    if (sperre := _mitarbeit_wache(un, "darf_kasse", "Das Kassenbuch führen")):
        return sperre
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
    verteilt = []
    for eintrag in (body.get("trinkgeldVerteilt") or [])[:TRINKGELD_MAX]:
        if not isinstance(eintrag, dict):
            continue
        name = str(eintrag.get("name") or "").strip()[:80]
        betrag = _zahl(eintrag.get("betrag"))
        if name and betrag and betrag > 0:
            verteilt.append({"name": name, "betrag": round(betrag, 2)})
    if verteilt:
        blatt["trinkgeldVerteilt"] = verteilt
    blatt["von"] = un                     # wer es eingetragen hat
    import boxschreiber  # noqa: PLC0415
    try:
        commit = await run_in_threadpool(boxschreiber.schreiben,
            f"kassenbuch/{datum[:7]}/{datum}.json",
            json.dumps(blatt, ensure_ascii=False, indent=1).encode(),
            f"kassenbuch: {datum}", un)
    except boxschreiber.SchreibFehler:
        return JSONResponse({"fehler": "gerade nicht speicherbar — gleich nochmal"},
                            status_code=503)
    return JSONResponse({"ok": True, "commit": commit, "datum": datum})


# ---------------------------------------------------------------------------
# Gespräche: der Chat merkt sich, worüber gesprochen wurde. Bisher stand jede
# Frage für sich — eine Rückfrage („und wie viel war das nochmal?") lief ins
# Leere. Gespeichert wird in SQLite: ein Chatverlauf ist kein Auditmaterial,
# er enthält Persönliches und muss löschbar bleiben (Art. 17 DSGVO).
# ---------------------------------------------------------------------------

# So viele Züge gehen als Verlauf ans Modell. Mehr hilft selten und kostet
# Platz, den das Fallwissen besser gebrauchen kann.
VERLAUF_ZUEGE = 6


def gespraech_anlegen(un: str, titel: str) -> int:
    with _DB_LOCK, _db() as c:
        cur = c.execute(
            "INSERT INTO gespraech (un, titel, begonnen, zuletzt) VALUES (?,?,?,?)",
            (un, titel[:120], _jetzt_iso(), _jetzt_iso()))
        return int(cur.lastrowid)


def gespraech_gehoert(un: str, gespraech_id: int) -> bool:
    with _DB_LOCK, _db() as c:
        return c.execute("SELECT 1 FROM gespraech WHERE id=? AND un=?",
                         (gespraech_id, un)).fetchone() is not None


def nachricht_anhaengen(gespraech_id: int, rolle: str, text: str) -> None:
    with _DB_LOCK, _db() as c:
        c.execute("INSERT INTO nachricht (gespraech, rolle, text, zeit) VALUES (?,?,?,?)",
                  (gespraech_id, rolle, text, _jetzt_iso()))
        c.execute("UPDATE gespraech SET zuletzt=? WHERE id=?",
                  (_jetzt_iso(), gespraech_id))


def verlauf_lesen(gespraech_id: int, zuege: int = VERLAUF_ZUEGE) -> list[dict]:
    """Die letzten Züge, älteste zuerst — so erwartet es das Modell."""
    with _DB_LOCK, _db() as c:
        zeilen = c.execute(
            "SELECT rolle, text FROM nachricht WHERE gespraech=? ORDER BY id DESC LIMIT ?",
            (gespraech_id, zuege * 2)).fetchall()
    return [{"role": z[0], "content": z[1]} for z in reversed(zeilen)]


def _welt_fuer(un: str) -> dict:
    """Alles, was babu über diesen Salon weiß — für das Fallwissen des Chats."""
    inhaber = salon_von(un)
    idx = index_aktuell()
    monat = time.strftime("%Y-%m")
    einstellungen = db_einstellungen(inhaber)

    fristen: list[dict] = []
    try:
        import datetime as _dt  # noqa: PLC0415
        import fristen as fr  # noqa: PLC0415
        profil = fr.termin_profil(einstellungen,
                                  hat_team=bool(team_liste(inhaber, nur_aktive=True)))
        termine = fr.fristen_jahr(int(monat[:4]), profil)
        fristen = fr.naechste(termine, _dt.date.today(), anzahl=6)
    except Exception:  # noqa: BLE001
        fristen = []

    zahlen: dict = {}
    try:
        import monatsabschluss as ma  # noqa: PLC0415
        blaetter = [b for tag, b in idx["kassenblaetter"].items() if tag.startswith(monat)]
        belege_monat = [z for z in idx["belege"].values() if z["monat"] == monat]
        erloese = ma.erloese_monat(blaetter, monat=monat,
                                   rechnungen=list(idx.get("rechnungen", {}).values()),
                                   versteuerung=_versteuerung(un))
        bwa = ma.bwa(monat, erloese, belege_monat, None,
                     personal_monat=team_personalkosten(inhaber),
                     vertraege=vertraege_aktuell())
        zahlen = {"einnahmen": erloese.get("netto_gesamt"),
                  "ausgaben": (bwa or {}).get("ausgaben"),
                  "ergebnis": (bwa or {}).get("ergebnis")}
    except Exception:  # noqa: BLE001
        zahlen = {}

    return {
        "einstellungen": einstellungen,
        "belege": list(idx["belege"].values()),
        "kassenblaetter": list(idx["kassenblaetter"].values()),
        "vertraege": vertraege_aktuell(),
        "rechnungen": list(idx.get("rechnungen", {}).values()),
        "team": team_liste(inhaber, nur_aktive=True),
        "fristen": fristen,
        "zahlen": zahlen,
        "dokumente": idx["dokumente"],
    }


@app.get("/api/gespraeche")
def api_gespraeche(request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    with _DB_LOCK, _db() as c:
        zeilen = [{"id": z[0], "titel": z[1], "begonnen": z[2], "zuletzt": z[3],
                   "nachrichten": z[4]}
                  for z in c.execute("""
                      SELECT g.id, g.titel, g.begonnen, g.zuletzt,
                             (SELECT COUNT(*) FROM nachricht n WHERE n.gespraech = g.id)
                      FROM gespraech g WHERE g.un=? ORDER BY g.zuletzt DESC""", (un,))]
    return JSONResponse({"gespraeche": zeilen})


@app.get("/api/gespraech/{gespraech_id}")
def api_gespraech(gespraech_id: int, request: Request) -> Response:
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if not gespraech_gehoert(un, gespraech_id):
        return JSONResponse({"fehler": "unbekanntes Gespräch"}, status_code=404)
    with _DB_LOCK, _db() as c:
        nachrichten = [{"rolle": z[0], "text": z[1], "zeit": z[2]}
                       for z in c.execute(
                           "SELECT rolle, text, zeit FROM nachricht WHERE gespraech=? ORDER BY id",
                           (gespraech_id,))]
    return JSONResponse({"id": gespraech_id, "nachrichten": nachrichten})


@app.post("/api/gespraech/{gespraech_id}/loeschen")
def api_gespraech_loeschen(gespraech_id: int, request: Request) -> Response:
    """Ein Gespräch wegwerfen — es gehört der Nutzerin, nicht dem Archiv."""
    un, fehler = _api_wache(request)
    if fehler:
        return fehler
    if not gespraech_gehoert(un, gespraech_id):
        return JSONResponse({"fehler": "unbekanntes Gespräch"}, status_code=404)
    with _DB_LOCK, _db() as c:
        c.execute("DELETE FROM nachricht WHERE gespraech=?", (gespraech_id,))
        c.execute("DELETE FROM gespraech WHERE id=?", (gespraech_id,))
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7844, workers=1)
