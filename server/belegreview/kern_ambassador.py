"""Ambassador — Salon wirbt Salon (21.09.2026).

Eine Ambassadorin (zumeist eine Salon-Inhaberin, die babu selbst nutzt)
bekommt einen persönlichen Code. Damit erzeugt sie Einladungslinks
(`/ambassador/<code>/<slug>`); löst ein Salon einen ein, trägt sich seine
Warteliste-Zeile unter dem Code ein (Spalte `herkunft_code` in `warteliste`,
Migration 0009). Zeichnet er ab und bleibt 3 Monate, bekommt die
Ambassadorin je 25 % der Jahreszahlung — die Anerkennung der Meilensteine
macht die Verwaltung von Hand (Knopf in der Wartelisten-Karte), die
Zuordnung läuft automatisch.

Nina (Verwaltung) legt Ambassadorinnen an: `POST /api/ambassador` —
Konto + Code + Mail mit dem Zug zu ihrer Seite. Die Ambassadorin selbst
sieht ihre Salons unter `GET /api/ambassador/me`.
"""
import json
import re
import secrets
import time

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

import audit

_app = None


def setup(app, bw):
    """Der Kern reicht sich selbst herein — siehe kern_warteliste.setup."""
    global _app
    _app = app
    globals()["bw"] = bw
    globals()["app"] = app
    for methode, pfad, fn in _ROUTEN:
        getattr(app, methode.lower())(pfad)(fn)

# 25 % je Meilenstein (Vertriebskonzept 19.09.2026): gezeichnet + 3 Monate
# gehalten = 50 % der Jahreszahlung. Jahreszahlung = 12 × Monatspreis des
# Pakets; das Paket steht in den Einstellungen des Salons (paket_empfehlung)
# — abgelegt wird der konkrete Betrag beim Anerkennen, nicht eine Formel.
PROVISION_ANTEIL = 25


def _code_neu(name: str) -> str:
    """Lesbarer Code aus dem Namen + Prüf-Suffix: BABS-SALON → BABS-SALON-7K3Q.
    Der Suffix macht Raten unmöglich, der Namensteil macht ihn sagbar."""
    stamm = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").upper()[:20] or "AMBASSADOR"
    return f"{stamm}-{secrets.token_hex(2).upper()}"


async def api_ambassador_anlegen(request: Request) -> Response:
    """Verwaltung: eine Ambassadorin anlegen — Konto, Code, Mail mit dem Zug."""
    un, fehler = bw._verwalter_wache(request)
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"}, status_code=401)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 8 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit name und email erwartet"}, status_code=400)
    name = str(koerper.get("name", "") or "").strip()[:100]
    email = str(koerper.get("email", "") or "").strip().lower()[:200]
    if not name or "@" not in email:
        return JSONResponse({"fehler": "Name und gültige E-Mail brauchen wir."},
                            status_code=400)
    code = _code_neu(name)
    # nutzer_anlegen nimmt _DB_LOCK SELBST — es darf NICHT in einem
    # with _DB_LOCK-Block stehen (threading.Lock ist nicht reentrant;
    # verschachtelt = Deadlock mit sich selbst, gemessen 21.09.).
    passwort = bw.nutzer_anlegen(email, name, name, "salon")
    if passwort is None:
        return JSONResponse({"fehler": "Für diese E-Mail gibt es schon einen "
                                       "Zugang."}, status_code=409)
    with bw._DB_LOCK, bw._db() as c:
        while c.execute("SELECT 1 FROM ambassador WHERE code=?", (code,)).fetchone():
            code = _code_neu(name)
        c.execute("""INSERT INTO ambassador (code, email, name, erstellt)
                     VALUES (?,?,?,?)""",
                  (code, email, name, bw._jetzt_iso()))
    audit.audit(un, "ambassador_anlegen", ziel_un=email, code=code)
    # Mail mit Code + Link zu ihrer Seite — über postfach, wie die
    # Wartelisten-Kopie. Ein Fehlschlag blockiert das Anlegen nicht
    # (das Startpasswort steht ohnehin in der Antwort der Verwaltung).
    import postfach  # noqa: PLC0415
    if postfach.eingerichtet():
        try:
            text = (f"Hallo {name},\n\n"
                    f"du bist jetzt babu-Ambassadorin. Dein Code: {code}\n\n"
                    f"Dein Bereich: {bw.PORTAL_ORIGIN}/portal (danach „Ambassador“)\n"
                    f"Damit erzeugst du Einladungslinks für Salons — 30 Tage "
                    f"babu Light für sie, Provision für dich, sobald sie "
                    f"bleiben.\n\n"
                    f"Dein Startpasswort: {passwort}\n"
                    f"(Bitte beim ersten Anmelden ändern.)\n")
            await bw.run_in_threadpool(
                postfach.senden, email, "babu — dein Ambassador-Zug", text,
                stempel=time.strftime("%Y%m%d-%H%M%S"))
        except Exception as ex:  # noqa: BLE001
            print(f"[ambassador] Mail an {email} fehlgeschlagen: {ex!r}", flush=True)
    print(f"[ambassador] angelegt: {name} <{email}> Code {code}", flush=True)
    return JSONResponse({"ok": True, "code": code, "email": email,
                         "startpasswort": passwort})


async def api_ambassador_liste(request: Request) -> Response:
    """Verwaltung: alle Ambassadorinnen mit ihrem Stand."""
    un, fehler = bw._verwalter_wache(request)
    if fehler:
        return fehler
    with bw._DB_LOCK, bw._db() as c:
        zeilen = [{"code": z[0], "email": z[1], "name": z[2], "erstellt": z[3],
                   "aktiv": bool(z[4]), "verdient": z[5], "gezahlt": z[6]}
                  for z in c.execute(
                      "SELECT code, email, name, erstellt, aktiv, verdient, "
                      "gezahlt FROM ambassador ORDER BY erstellt DESC")]
        for z in zeilen:
            z["salons"] = [dict(zip(("email", "salon", "eingelöst", "meilenstein",
                                     "verdienst"), s))
                           for s in c.execute(
                               "SELECT email, salon, eingelöst, meilenstein, "
                               "verdienst FROM ambassador_salon WHERE code=? "
                               "ORDER BY eingelöst DESC", (z["code"],))]
    return JSONResponse({"ambassadorinnen": zeilen})


async def api_ambassador_me(request: Request) -> Response:
    """Die Ambassadorin selbst: ihr Code, ihre Salons, ihr Saldo."""
    un, fehler = bw._api_wache(request)
    if fehler:
        return fehler
    with bw._DB_LOCK, bw._db() as c:
        a = c.execute("SELECT code, name, verdient, gezahlt FROM ambassador "
                      "WHERE email=? AND aktiv=1", (un,)).fetchone()
        if not a:
            return JSONResponse({"fehler": "Du bist (noch) keine Ambassadorin."},
                                status_code=404)
        salons = [dict(zip(("email", "salon", "eingelöst", "meilenstein",
                            "verdienst"), z))
                  for z in c.execute(
                      "SELECT email, salon, eingelöst, meilenstein, verdienst "
                      "FROM ambassador_salon WHERE code=? ORDER BY eingelöst DESC",
                      (a[0],))]
    return JSONResponse({"code": a[0], "name": a[1],
                         "verdient": a[2], "gezahlt": a[3], "offen": a[2] - a[3],
                         "salons": salons})


async def api_ambassador_link(request: Request) -> Response:
    """Ambassadorin: einen persönlichen Einladungslink erzeugen (optional mit
    Salon-Name/E-Mail) — der Salon löst ihn ein, die Zuordnung passiert dann."""
    un, fehler = bw._api_wache(request)
    if fehler:
        return fehler
    with bw._DB_LOCK, bw._db() as c:
        a = c.execute("SELECT code FROM ambassador WHERE email=? AND aktiv=1",
                      (un,)).fetchone()
    if not a:
        return JSONResponse({"fehler": "Du bist (noch) keine Ambassadorin."},
                            status_code=404)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 4 * 1024))
    except Exception:  # noqa: BLE001
        koerper = {}
    slug = re.sub(r"[^a-z0-9]+", "-",
                  str(koerper.get("salon", "")).lower()).strip("-")[:24] or "salon"
    return JSONResponse({"link": f"{bw.PORTAL_ORIGIN}/ambassador/{a[0]}/{slug}"})


async def ambassador_landing(code: str, slug: str) -> Response:
    """Die Landing-Seite des Salons: Code steht fest, ein Formular nimmt
    Name/E-Mail auf und legt die Warteliste-Zeile MIT herkunft_code an.
    Bewusst öffentlich (kein Login) — der Salon kennt babu noch nicht."""
    with bw._DB_LOCK, bw._db() as c:
        a = c.execute("SELECT name FROM ambassador WHERE code=? AND aktiv=1",
                      (code,)).fetchone()
    if not a:
        return HTMLResponse("<h1>Dieser Code ist nicht (mehr) aktiv.</h1>",
                            status_code=404)
    html = f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>babu — 30 Tage testen</title><style>
body{{font-family:-apple-system,sans-serif;background:#efece6;color:#2a2a26;
padding:32px 16px;max-width:560px;margin:0 auto;line-height:1.55}}
.karte{{background:#faf8f4;border:1px solid #d8d3c8;border-radius:14px;padding:24px}}
h1{{font-size:22px}} .knopf{{background:#6f8a6e;color:#fff;border:none;
padding:12px 20px;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer}}
input{{width:100%;padding:10px;margin:6px 0 14px;border:1px solid #d8d3c8;
border-radius:8px;font-size:14px}}</style></head><body>
<div class="karte"><h1>babu 30 Tage testen — kostenlos</h1>
<p>Foto machen statt Belege sortieren. Empfohlen von <b>{a[0]}</b> —
30 Tage babu Light, ohne Vertrag, ohne Kündigung.</p>
<form onsubmit="return einlosen(this)">
<input name="salon" placeholder="Name deines Salons" required>
<input name="email" type="email" placeholder="Deine E-Mail" required>
<button class="knopf">Platz sichern</button></form>
<p id="ok" style="display:none;color:#55705a;font-weight:600"></p></div>
<script>
function einlosen(f){{
  fetch("/api/warteliste", {{method:"POST",
    headers:{{"Content-Type":"application/json"}},
    body: JSON.stringify({{email:f.email.value, art:"salon",
      salon:f.salon.value, bemerkung:"Code " + {json.dumps(code)}}})}})
  .then(r => r.json()).then(d => {{
    if(d.ok){{ document.getElementById("ok").textContent =
      "Danke! Wir melden uns mit deinem Zugang — dein Testmonat startet dann.";
      f.style.display="none"; }}
    else {{ document.getElementById("ok").textContent = d.fehler || "Da lief etwas schief."; }}
  }});
  return false;}}
</script></body></html>"""
    return HTMLResponse(html)


async def api_ambassador_einladen(request: Request) -> Response:
    """Ambassadorin verschickt die Einladung an einen Salon direkt aus dem
    Portal — die Mail trägt ihren Namen, den Link und die 30-Tage-Zusage."""
    un, fehler = bw._api_wache(request)
    if fehler:
        return fehler
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 8 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit email erwartet"}, status_code=400)
    email = str(koerper.get("email", "") or "").strip().lower()[:200]
    salon = str(koerper.get("salon", "") or "").strip()[:120]
    link = str(koerper.get("link", "") or "").strip()[:400]
    if "@" not in email or not link:
        return JSONResponse({"fehler": "email und link brauchen wir."}, status_code=400)
    import einladung as ei  # noqa: PLC0415
    if not ei.mail_gueltig(email):
        return JSONResponse({"fehler": "Das sieht nicht nach einer E-Mail-Adresse aus."},
                            status_code=400)
    with bw._DB_LOCK, bw._db() as c:
        a = c.execute("SELECT name FROM ambassador WHERE email=? AND aktiv=1",
                      (un,)).fetchone()
    if not a:
        return JSONResponse({"fehler": "Du bist (noch) keine Ambassadorin."},
                            status_code=404)
    import postfach  # noqa: PLC0415
    if not postfach.eingerichtet():
        return JSONResponse({"fehler": "Der Versand ist gerade nicht eingerichtet — "
                                       "schick den Link bitte selbst."}, status_code=503)
    try:
        anrede = f"Hallo {salon}," if salon else "Hallo,"
        text = (f"{anrede}\n\n"
                f"{a[0]} empfiehlt dir babu: Foto machen statt Belege sortieren.\n"
                f"30 Tage testen — kostenlos, ohne Vertrag, ohne Kündigung.\n\n"
                f"Dein Platz: {link}\n\n"
                f"Der Code macht's möglich — einfach öffnen und sichern.\n")
        await bw.run_in_threadpool(
            postfach.senden, email,
            "babu — 30 Tage testen (Empfehlung von " + a[0] + ")", text,
            stempel=time.strftime("%Y%m%d-%H%M%S"))
    except Exception as ex:  # noqa: BLE001
        print(f"[ambassador] Einladung an {email} fehlgeschlagen: {ex!r}", flush=True)
        return JSONResponse({"fehler": "Die Mail ging nicht raus — später nochmal."},
                            status_code=503)
    audit.audit(un, "ambassador_einladen", ziel_un=email)
    return JSONResponse({"ok": True})


async def api_ambassador_meilenstein(request: Request) -> Response:
    """Verwaltung: einen Meilenstein anerkennen (manuelles Abhaken).

    koerper: code, email (des Salons), meilenstein ('gezeichnet' | 'gehalten'),
    betrag (EUR, aus dem Paket des Salons). Setzt den Stand, addiert das
    Guthaben der Ambassadorin — ein Rückschritt ('testet') ist nicht möglich,
    doppeltes Anerkennen desselben Meilensteins wird abgewiesen."""
    un, fehler = bw._verwalter_wache(request)
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"}, status_code=401)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 4 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    code = str(koerper.get("code", "") or "").strip()[:60]
    email = str(koerper.get("email", "") or "").strip().lower()[:200]
    meilenstein = str(koerper.get("meilenstein", "") or "").strip()
    betrag = koerper.get("betrag")
    if meilenstein not in ("gezeichnet", "gehalten") \
            or not isinstance(betrag, (int, float)) or betrag <= 0:
        return JSONResponse({"fehler": "meilenstein (gezeichnet/gehalten) und "
                                       "positiver betrag nötig."}, status_code=400)
    betrag = int(betrag)
    folge = {"gezeichnet": ("testet", "gezeichnet"),
             "gehalten": ("gezeichnet", "gehalten")}
    von, bis = folge[meilenstein]
    with bw._DB_LOCK, bw._db() as c:
        z = c.execute("""SELECT meilenstein, verdienst FROM ambassador_salon
                         WHERE code=? AND email=?""", (code, email)).fetchone()
        if not z:
            return JSONResponse({"fehler": "Diesen Salon gibt es unter dem Code "
                                           "nicht."}, status_code=404)
        if z[0] != von:
            return JSONResponse({"fehler": f"Salon steht auf „{z[0]}“ — "
                                           f"„{bis}“ setzt „{von}“ voraus."},
                                status_code=409)
        c.execute("""UPDATE ambassador_salon SET meilenstein=?, verdienst=?
                     WHERE code=? AND email=?""", (bis, betrag, code, email))
        c.execute("UPDATE ambassador SET verdient = verdient + ? WHERE code=?",
                  (betrag, code))
    audit.audit(un, "ambassador_meilenstein", ziel_un=email,
                code=code, meilenstein=meilenstein, betrag=betrag)
    return JSONResponse({"ok": True, "meilenstein": bis, "verdienst": betrag})


async def api_ambassador_gezahlt(request: Request) -> Response:
    """Verwaltung: Quartalsauszahlung verbucht — Saldo auf 0 setzen."""
    un, fehler = bw._verwalter_wache(request)
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"}, status_code=401)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 4 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit code erwartet"}, status_code=400)
    code = str(koerper.get("code", "") or "").strip()[:60]
    with bw._DB_LOCK, bw._db() as c:
        z = c.execute("SELECT verdient, gezahlt FROM ambassador WHERE code=?",
                      (code,)).fetchone()
        if not z:
            return JSONResponse({"fehler": "Code unbekannt."}, status_code=404)
        offen = z[0] - z[1]
        if offen <= 0:
            return JSONResponse({"fehler": "Nichts offen."}, status_code=409)
        c.execute("UPDATE ambassador SET gezahlt = verdient WHERE code=?", (code,))
    audit.audit(un, "ambassador_gezahlt", code=code, betrag=offen)
    return JSONResponse({"ok": True, "gezahlt": offen})


_ROUTEN = [
    ("POST", "/api/ambassador", api_ambassador_anlegen),
    ("GET", "/api/ambassador/liste", api_ambassador_liste),
    ("GET", "/api/ambassador/me", api_ambassador_me),
    ("POST", "/api/ambassador/link", api_ambassador_link),
    ("POST", "/api/ambassador/einladen", api_ambassador_einladen),
    ("GET", "/ambassador/{code}/{slug}", ambassador_landing),
    ("POST", "/api/ambassador/meilenstein", api_ambassador_meilenstein),
    ("POST", "/api/ambassador/gezahlt", api_ambassador_gezahlt),
]
