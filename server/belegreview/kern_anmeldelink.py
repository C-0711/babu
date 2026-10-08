"""Anmelden per Link — ohne Passwort, in App und Portal (08.10.2026).

Für die Friseurin am iPhone: E-Mail eintippen, den Link aus der Mail
antippen, drin. Kein Startpasswort, das sie abtippen muss, kein zweites
Formular zum Passwortsetzen.

Der Link ist eine Zeile in `passwort_reset` — dieselbe Tabelle, dieselbe
Bremse, nur der Hash steht in der Datenbank. Er beweist dasselbe wie ein
Passwort-Link (die Person hat das Postfach) und darf deshalb dasselbe:
einmal eingelöst, meldet er an, statt ein Passwort zu setzen. Darum führen
auch die Willkommensmails (`kern_ambassador._passwort_link`) hierher.

- `POST /api/anmeldelink` {email, app?}: schickt den Link. Antwortet immer
  gleich — sonst wäre die Route ein Verzeichnis der Konten.
- `GET /anmelden/{token}`: die Seite hinter dem Link. Auf dem iPhone „In babu
  öffnen“ (babu:// bzw. babupro:// — die Schemata der beiden Apps), sonst
  „Weiter“ im Browser. Ein GET löst nichts ein: Mailprogramme rufen Links
  zur Vorschau auf, und wer die App erst holen muss, tippt denselben Link
  danach noch einmal.
- `POST /api/anmeldelink/einloesen` {token, app?, geraet?}: löst ein. Für die
  App ein Geräteschlüssel wie bei `/api/app-anmelden`, sonst das
  Sitzungs-Cookie wie bei `/api/login`.
"""
import datetime as dt
import hashlib
import html as html_text
import json
import secrets
import time

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

import audit

_app = None

# Ein Link, den man sich selbst schickt, gilt einen Tag — er wird gleich
# gebraucht. Die Links der Willkommensmails leben so lange wie ein
# Passwort-Link (passwort_reset.FRIST), sie liegen oft ein paar Tage.
LINK_FRIST = dt.timedelta(days=1)

_SCHEMATA = (("babu", "In der babu-App öffnen"), ("babupro", "In babu Pro öffnen"))


def setup(app, bw):
    """Der Kern reicht sich selbst herein — siehe kern_warteliste.setup."""
    global _app
    _app = app
    globals()["bw"] = bw
    for methode, pfad, fn in _ROUTEN:
        getattr(app, methode.lower())(pfad)(fn)


def link_fuer(token: str) -> str:
    return f"{bw.PORTAL_ORIGIN.rstrip('/')}/anmelden/{token}"


def link_anlegen(email: str, frist: dt.timedelta | None = None) -> str | None:
    """Neuer Anmelde-Link für `email` — None, wenn gerade gebremst.

    Nimmt das Schloss selbst; NICHT aus einem `with _DB_LOCK` heraus rufen."""
    import passwort_reset as pr  # noqa: PLC0415
    if not bw._reset_anfordern_erlaubt(email):  # noqa: SLF001
        return None
    bw._reset_aufraeumen(email)  # noqa: SLF001
    token, modell = pr.anfordern(email)
    ende = modell.erstellt + frist if frist else modell.laeuft_ab
    with bw._DB_LOCK, bw._db() as c:
        c.execute("""INSERT INTO passwort_reset (token_hash, un, erstellt, laeuft_ab)
                     VALUES (?,?,?,?)""",
                  (modell.token_hash, modell.un, modell.erstellt.isoformat(),
                   ende.isoformat()))
    return link_fuer(token)


def _ip_gebremst(request: Request) -> JSONResponse | None:
    """Fünf Versuche je Minute und IP — dieselbe Bremse wie beim Passwort-Link."""
    ip = bw._client_ip(request)  # noqa: SLF001
    jetzt = time.time()
    versuche = [t for t in bw._RESET_VERSUCHE.get(ip, []) if jetzt - t < 60]  # noqa: SLF001
    if len(versuche) >= 5:
        bw._RESET_VERSUCHE[ip] = versuche  # noqa: SLF001
        return JSONResponse({"fehler": "Zu viele Versuche — bitte eine Minute warten."},
                            status_code=429)
    versuche.append(jetzt)
    bw._RESET_VERSUCHE[ip] = versuche  # noqa: SLF001
    bw._zaehler_aufraeumen(bw._RESET_VERSUCHE, jetzt, 60)  # noqa: SLF001
    return None


def _mailtext(link: str) -> str:
    return ("Hallo,\n\n"
            "hier ist dein Link zu babu. Einmal antippen — dann bist du drin:\n\n"
            f"    {link}\n\n"
            "Auf dem iPhone tippst du danach auf „In der babu-App öffnen“.\n"
            "Der Link gilt 24 Stunden und nur einmal.\n\n"
            "Wenn du das nicht warst, ignoriere diese Nachricht einfach.\n")


async def api_anmeldelink(request: Request) -> Response:
    """Den Link schicken. Immer dieselbe Antwort, ob es das Konto gibt oder nicht."""
    if not bw._origin_ok(request):  # noqa: SLF001
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    if (gebremst := _ip_gebremst(request)) is not None:
        return gebremst
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 2 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    email = str(koerper.get("email", "") or "").strip().lower()[:200]
    antwort = JSONResponse({"ok": True})
    if "@" not in email:
        return antwort
    n = bw.nutzer_holen(email)
    if n is None or not n["aktiv"]:
        print(f"[anmeldelink] kein aktives Konto für {email}", flush=True)
        return antwort
    link = await bw.run_in_threadpool(link_anlegen, email, LINK_FRIST)
    if link is None:
        print(f"[anmeldelink] {email} gebremst", flush=True)
        return antwort
    import postfach  # noqa: PLC0415
    ok, hinweis = await bw.run_in_threadpool(
        postfach.senden, email, "Dein Link zu babu", _mailtext(link),
        stempel=time.strftime("%Y%m%d-%H%M%S"))
    print(f"[anmeldelink] Link an {email}: {hinweis}", flush=True)
    audit.audit(email, "anmeldelink_angefordert", ziel_un=email,
                weg="app" if koerper.get("app") is True else "portal",
                zugestellt="ja" if ok else "nein")
    return antwort


def _zeile_pruefen(token: str):
    """(zeile, fehler) — die Zeile, wenn der Link gilt, sonst der Satz dazu."""
    import passwort_reset as pr  # noqa: PLC0415
    zeile = bw._reset_per_token(token) if token else None  # noqa: SLF001
    geprueft = pr.pruefen(bw._als_reset(zeile) if zeile else None, token)  # noqa: SLF001
    if geprueft.ok:
        return zeile, ""
    if zeile and zeile.get("eingeloest"):
        return None, ("Diesen Link hast du schon benutzt. Schick dir einfach einen "
                      "neuen — das dauert eine Minute.")
    if zeile:
        return None, "Dieser Link ist abgelaufen. Schick dir einfach einen neuen."
    return None, "Diesen Link kennen wir nicht. Schick dir einfach einen neuen."


async def api_anmeldelink_einloesen(request: Request) -> Response:
    """Einlösen: App bekommt einen Geräteschlüssel, der Browser ein Cookie."""
    if not bw._origin_ok(request):  # noqa: SLF001
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    if (gebremst := _ip_gebremst(request)) is not None:
        return gebremst
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 2 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    token = str(koerper.get("token", "") or "").strip()[:200]
    fuer_app = koerper.get("app") is True
    geraet = str(koerper.get("geraet", "") or "")[:80]
    zeile, grund = _zeile_pruefen(token)
    if zeile is None:
        return JSONResponse({"fehler": grund}, status_code=400)
    email = zeile["un"]
    n = bw.nutzer_holen(email)
    if n is None or not n["aktiv"]:
        return JSONResponse({"fehler": "Dieser Zugang ist nicht (mehr) aktiv."},
                            status_code=400)
    schluessel = secrets.token_urlsafe(32) if fuer_app else None
    with bw._DB_LOCK, bw._db() as c:
        # Nur wer die Zeile als Erster umlegt, ist drin — zwei Tipps auf
        # denselben Link geben nicht zwei Anmeldungen.
        if not c.execute("UPDATE passwort_reset SET eingeloest=? WHERE id=? "
                         "AND eingeloest IS NULL",
                         (bw._jetzt_iso(), zeile["id"])).rowcount:
            return JSONResponse({"fehler": "Diesen Link hast du schon benutzt. Schick "
                                           "dir einfach einen neuen."}, status_code=400)
        if schluessel:
            c.execute("INSERT INTO app_schluessel VALUES (?,?,?,?,?)",
                      (hashlib.sha256(schluessel.encode()).hexdigest(), email, geraet,
                       bw._jetzt_iso(), None))
        c.execute("UPDATE nutzer SET letzter_login=? WHERE email=?",
                  (bw._jetzt_iso(), email))
    bw._login_erfolg(bw._client_ip(request), email)  # noqa: SLF001
    audit.audit(email, "anmeldelink_eingeloest", ziel_un=email,
                weg="app" if fuer_app else "portal")
    box = bw._hat_ablage(email)  # noqa: SLF001
    if schluessel:
        print(f"[app] Gerät per Link verbunden: {email} ({geraet or 'ohne Namen'})",
              flush=True)
        return JSONResponse({"schluessel": schluessel, "un": email,
                             "rolle": n["rolle"], "box": box})
    antwort = JSONResponse({"ok": True, "un": email, "rolle": n["rolle"], "box": box})
    antwort.set_cookie(bw.SESSION_COOKIE,
                       bw._signieren(email, int(time.time()) + bw.SESSION_DAUER),  # noqa: SLF001
                       max_age=bw.SESSION_DAUER, httponly=True,
                       secure=bw.SESSION_SECURE, samesite="lax", path="/")
    return antwort


_SEITE_EXTRA = """<style>
.neben{display:block;width:100%;text-align:center;background:#fff;color:var(--gc-fg);
  border:1px solid var(--gc-border);border-radius:12px;padding:13px 20px;font:600 15px var(--gc-sans);
  margin-top:10px;cursor:pointer;text-decoration:none}
a.voll{display:block;text-align:center;text-decoration:none}
.leise{display:block;text-align:center;margin-top:14px;font-size:13px;color:var(--gc-muted)}
.trenner{border:0;border-top:1px solid var(--gc-border-l);margin:18px 0 6px}
.frage{font-size:13.5px;color:var(--gc-desc);margin:14px 0 0;text-align:center}
</style>"""


def _neu_anfordern_html() -> str:
    """Das Formular „Neuen Link schicken“ — auf der Fehlerseite."""
    return """<form onsubmit="return neuerLink(this)" novalidate>
<label class="nurvorlesen" for="email">Deine E-Mail</label>
<input id="email" name="email" type="email" placeholder="Deine E-Mail" autocomplete="email" required>
<button class="voll" id="senden">Neuen Link schicken</button>
<p class="fehler" id="fehler" role="alert" hidden></p></form>
<p class="meldung" id="ok" role="status" hidden>Schau in dein Postfach — der neue Link ist unterwegs.</p>
<script>
function neuerLink(f){
  const fehler = document.getElementById("fehler"), ok = document.getElementById("ok");
  fehler.hidden = true;
  if (!f.email.value.includes("@")){ fehler.textContent = "Bitte deine E-Mail eintragen."; fehler.hidden = false; return false; }
  document.getElementById("senden").disabled = true;
  fetch("/api/anmeldelink", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({email: f.email.value.trim()})})
  .then(r => r.json()).then(d => {
    if (d.ok){ ok.hidden = false; f.style.display = "none"; }
    else { fehler.textContent = d.fehler || "Das ging gerade nicht."; fehler.hidden = false;
      document.getElementById("senden").disabled = false; }
  }).catch(() => { fehler.textContent = "Gerade keine Verbindung — gleich nochmal."; fehler.hidden = false;
      document.getElementById("senden").disabled = false; });
  return false;
}
</script>"""


async def anmelden_seite(token: str) -> Response:
    """Die Seite hinter dem Link: App öffnen oder im Browser weiter."""
    import kern_ambassador as ka  # noqa: PLC0415
    import startguide  # noqa: PLC0415
    token = token.strip()[:200]
    zeile, grund = _zeile_pruefen(token)
    if zeile is None:
        return HTMLResponse(ka._seite(  # noqa: SLF001
            "babu — Anmelden", "Anmelden", "Der Link geht nicht mehr.", grund,
            _SEITE_EXTRA + _neu_anfordern_html()), status_code=400)
    t = html_text.escape(token, quote=True)
    holen = startguide.app_link()
    app_knoepfe = "".join(
        f'<a class="{"voll" if i == 0 else "leise"}" href="{schema}://anmelden/{t}">{text}</a>'
        for i, (schema, text) in enumerate(_SCHEMATA))
    holen_html = (f'<p class="frage">Noch keine App auf dem iPhone?</p>'
                  f'<a class="neben" href="{html_text.escape(holen, quote=True)}">App holen</a>'
                  f'<p class="frage">Danach diesen Link aus der Mail noch einmal antippen.</p>'
                  if holen else "")
    karte = f"""{_SEITE_EXTRA}
<div id="iphone" hidden>{app_knoepfe}{holen_html}<hr class="trenner"></div>
<button class="voll" id="weiter" type="button" onclick="weiter()">Im Browser weiter</button>
<a class="leise" href="/portal#reset/{t}">Lieber ein Passwort festlegen</a>
<p class="fehler" id="fehler" role="alert" hidden></p>
<script>
const iphone = /iPhone|iPad|iPod/.test(navigator.userAgent)
  || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
if (iphone){{
  document.getElementById("iphone").hidden = false;
  const w = document.getElementById("weiter");
  w.className = "neben"; w.textContent = "Lieber im Browser weiter";
}}
function weiter(){{
  const fehler = document.getElementById("fehler"), knopf = document.getElementById("weiter");
  knopf.disabled = true; fehler.hidden = true;
  fetch("/api/anmeldelink/einloesen", {{method:"POST", headers:{{"Content-Type":"application/json"}},
    body: JSON.stringify({{token: {json.dumps(token)}}})}})
  .then(r => r.json()).then(d => {{
    if (d.ok) location.href = "/portal";
    else {{ fehler.textContent = d.fehler || "Das ging gerade nicht."; fehler.hidden = false; knopf.disabled = false; }}
  }}).catch(() => {{ fehler.textContent = "Gerade keine Verbindung — gleich nochmal."; fehler.hidden = false;
    knopf.disabled = false; }});
}}
</script>"""
    return HTMLResponse(ka._seite(  # noqa: SLF001
        "babu — Anmelden", "Anmelden", "Du bist gleich drin.",
        "Ein Tipp noch — dann geht's los.", karte))


_ROUTEN = [
    ("POST", "/api/anmeldelink", api_anmeldelink),
    ("POST", "/api/anmeldelink/einloesen", api_anmeldelink_einloesen),
    ("GET", "/anmelden/{token}", anmelden_seite),
]
