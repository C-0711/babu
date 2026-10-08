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
import base64
import calendar
import contextvars
import datetime as dt
import hashlib
import hmac
import html as html_text
import json
import os
import re
import secrets
import time

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

import abo
import audit
import begleiter
import mandanten
import provision
import testmonat

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
    un, fehler = bw._betreiber_wache(request)
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
    # Schon ein babu-Konto? Dann wird die Person DIREKT Ambassadorin —
    # ohne zweites Konto und ohne Startpasswort (sie meldet sich wie
    # gewohnt an). Neu angelegte bekommen wie bisher ein Startpasswort.
    # nutzer_anlegen nimmt _DB_LOCK SELBST — es darf NICHT in einem
    # with _DB_LOCK-Block stehen (threading.Lock ist nicht reentrant;
    # verschachtelt = Deadlock mit sich selbst, gemessen 21.09.).
    passwort = None
    if bw.nutzer_holen(email) is None:
        # box=False (seit 02.10.2026): eine Ambassadorin braucht für ihren
        # Bereich keine Ablage. Mit dem alten Standard `box=1` und ohne
        # Mandant hing ihr Konto an der Default-Box — der Ablage eines
        # anderen Betriebs. Ihr Bereich steht auch auf der Sperrseite.
        passwort = bw.nutzer_anlegen(email, name, name, "salon", box=False)
    with bw._DB_LOCK, bw._db() as c:
        schon = c.execute("SELECT code FROM ambassador WHERE email=?",
                          (email,)).fetchone()
        if schon:
            schon_code = schon[0]
            schon_da = True
        else:
            schon_da = False
            while c.execute("SELECT 1 FROM ambassador WHERE code=?", (code,)).fetchone():
                code = _code_neu(name)
            c.execute("""INSERT INTO ambassador (code, email, name, erstellt)
                         VALUES (?,?,?,?)""",
                      (code, email, name, bw._jetzt_iso()))
    # audit NACH dem Lock-Block — audit.audit nimmt denselben _DB_LOCK,
    # innerhalb des with = Deadlock (derselbe Fehler wie bei nutzer_anlegen,
    # gemessen 24.09. am Fall „bestehendes Konto").
    audit.audit(un, "ambassador_anlegen_bereits_da" if schon_da
                else "ambassador_anlegen", ziel_un=email, code=code)
    if schon_da:
        return JSONResponse({"ok": True, "code": schon_code, "email": email,
                             "bestehendes_konto": True,
                             "hinweis": "Ist schon Ambassadorin — Code bleibt derselbe."})
    # Mail mit Code + Link zu ihrer Seite — über postfach, wie die
    # Wartelisten-Kopie. Ein Fehlschlag blockiert das Anlegen nicht
    # (das Startpasswort steht ohnehin in der Antwort der Verwaltung).
    import postfach  # noqa: PLC0415
    bestehend = passwort is None
    if postfach.eingerichtet():
        try:
            zugang = (f"Dein Startpasswort: {passwort}\n"
                      f"(Bitte beim ersten Anmelden ändern.)\n") if passwort \
                     else "Du meldest dich wie gewohnt mit deinem Passwort an.\n"
            text = (f"Hallo {name},\n\n"
                    f"du bist jetzt babu-Ambassadorin. Dein Code: {code}\n\n"
                    f"Dein Bereich: {bw.PORTAL_ORIGIN}/portal\n"
                    f"Damit erzeugst du Einladungslinks für Salons — 30 Tage "
                    f"babu komplett und kostenlos für sie, Provision für dich, sobald sie "
                    f"bleiben.\n\n{zugang}\n")
            await bw.run_in_threadpool(
                postfach.senden, email, "babu — dein Ambassador-Zug", text,
                stempel=time.strftime("%Y%m%d-%H%M%S"))
        except Exception as ex:  # noqa: BLE001
            print(f"[ambassador] Mail an {email} fehlgeschlagen: {ex!r}", flush=True)
    print(f"[ambassador] angelegt: {name} <{email}> Code {code} "
          f"({'bestehendes Konto' if bestehend else 'neu'})", flush=True)
    antwort = {"ok": True, "code": code, "email": email, "bestehendes_konto": bestehend}
    if passwort:
        antwort["startpasswort"] = passwort
    return JSONResponse(antwort)


async def api_ambassador_liste(request: Request) -> Response:
    """Verwaltung: alle Ambassadorinnen mit ihrem Stand."""
    un, fehler = bw._betreiber_wache(request)
    if fehler:
        return fehler
    with bw._DB_LOCK, bw._db() as c:
        zeilen = [{"code": z[0], "email": z[1], "name": z[2], "erstellt": z[3],
                   "aktiv": bool(z[4]), "verdient": z[5], "gezahlt": z[6],
                   "link": _link(z[0], "salon")}
                  for z in c.execute(
                      "SELECT code, email, name, erstellt, aktiv, verdient, "
                      "gezahlt FROM ambassador ORDER BY erstellt DESC")]
        for z in zeilen:
            z["salons"] = [dict(zip(_SALON_SPALTEN, s))
                           for s in c.execute(
                               f"SELECT {', '.join(_SALON_SPALTEN)} FROM "
                               "ambassador_salon WHERE code=? ORDER BY eingelöst DESC",
                               (z["code"],))]
            _testmonate_dazu(z["salons"], c)
            _pipeline_dazu(z["salons"], z["code"], c)
            # Für die Übersicht „Wer hat wen geworben" (seit 08.10.2026):
            # der Abo-Stand je Salon und wer die Ambassadorin angelegt hat.
            for s in z["salons"]:
                a = c.execute("SELECT abo_status, paket FROM mandant WHERE besitzer_un=? "
                              "ORDER BY id", (s["email"],)).fetchone()
                s["abo"] = {"status": a[0], "paket": a[1]} if a and a[0] else None
            v = c.execute("SELECT akteur_un FROM audit_log WHERE aktion='ambassador_anlegen' "
                          "AND ziel_un=? ORDER BY zeit", (z["email"],)).fetchone()
            z["angelegt_von"] = v[0] if v else None
            z["einladungen"] = _offene_einladungen(z["code"], c)
            z["geld"] = _geld(z["code"], c)
            z["zahlen"] = _zahlen(z["salons"])
    return JSONResponse({"ambassadorinnen": zeilen})


async def api_ambassador_me(request: Request) -> Response:
    """Die Ambassadorin selbst: ihr Code, ihre Salons, ihr Saldo."""
    un, fehler = bw._api_wache(request)
    if fehler:
        return fehler
    with bw._DB_LOCK, bw._db() as c:
        # Ohne `aktiv=1` (seit 03.10.2026): ein abgeschalteter Code nimmt
        # keine neuen Salons mehr an, aber Geld und Gutschriften bleiben sichtbar.
        a = c.execute("SELECT code, name, verdient, gezahlt, "
                      "COALESCE(heute_mail, 1), aktiv FROM ambassador "
                      "WHERE email=?", (un,)).fetchone()
        if not a:
            return JSONResponse({"fehler": "Du bist (noch) keine Ambassadorin."},
                                status_code=404)
        salons = [dict(zip(_SALON_SPALTEN, z))
                  for z in c.execute(
                      f"SELECT {', '.join(_SALON_SPALTEN)} FROM ambassador_salon "
                      "WHERE code=? ORDER BY eingelöst DESC", (a[0],))]
        _testmonate_dazu(salons, c)
        _pipeline_dazu(salons, a[0], c)
        einladungen = _offene_einladungen(a[0], c)
        geld = _geld(a[0], c)
        roh = _kontakt_zeilen(a[0], c)
        import kern_auszahlung as kz  # noqa: PLC0415
        profil_fehlt = kz.fehlt(kz.profil_holen(c, a[0]))
        gutschriften = kz.gutschriften_von(a[0], c)
    kontakte, heute = _begleiter(a[0], a[1], roh, aktiv=bool(a[5]))
    return JSONResponse({"code": a[0], "name": a[1], "aktiv": bool(a[5]),
                         # Der allgemeine Link für Instagram, Flyer und Mails —
                         # jeder Slug löst denselben Code ein.
                         "link": _link(a[0], "salon"),
                         "verdient": a[2], "gezahlt": a[3], "offen": a[2] - a[3],
                         "salons": salons, "zahlen": _zahlen(salons),
                         "einladungen": einladungen, "geld": geld,
                         "kontakte": kontakte, "heute": heute,
                         "heute_mail": bool(a[4]),
                         "profil_vollstaendig": not profil_fehlt,
                         "profil_fehlt": profil_fehlt, "gutschriften": gutschriften})


async def api_ambassador_heute_mail(request: Request) -> Response:
    """Die Ambassadorin selbst: die Mail „Heute für dich" an oder aus."""
    if not bw._origin_ok(request):
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    un, fehler = bw._api_wache(request)
    if fehler:
        return fehler
    try:
        an = bool(json.loads(await bw.koerper_lesen(request, 1024)).get("an"))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    with bw._DB_LOCK, bw._db() as c:
        n = c.execute("UPDATE ambassador SET heute_mail=? WHERE email=? AND aktiv=1",
                      (1 if an else 0, un)).rowcount
    if not n:
        return JSONResponse({"fehler": "Du bist (noch) keine Ambassadorin."},
                            status_code=404)
    return JSONResponse({"ok": True, "heute_mail": an})


async def api_ambassador_link(request: Request) -> Response:
    """Ambassadorin: einen persönlichen Einladungslink erzeugen (optional mit
    Salon-Name/E-Mail) — der Salon löst ihn ein, die Zuordnung passiert dann."""
    un, fehler = bw._api_wache(request)
    if fehler:
        return fehler
    with bw._DB_LOCK, bw._db() as c:
        a = c.execute("SELECT code, aktiv FROM ambassador WHERE email=?",
                      (un,)).fetchone()
    if not a:
        return JSONResponse({"fehler": "Du bist (noch) keine Ambassadorin."},
                            status_code=404)
    if not a[1]:
        return JSONResponse({"fehler": "Dein Code ist gerade abgeschaltet — neue "
                                       "Einladungen gehen nicht."}, status_code=403)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 4 * 1024))
    except Exception:  # noqa: BLE001
        koerper = {}
    salon = str(koerper.get("salon", "") or "").strip()[:120]
    email = str(koerper.get("email", "") or "").strip().lower()[:200] or None
    person = str(koerper.get("person", "") or "").strip()[:60]
    telefon_roh = str(koerper.get("telefon", "") or "").strip()[:40]
    telefon = begleiter.nummer(telefon_roh) if telefon_roh else None
    if telefon_roh and telefon is None:
        return JSONResponse({"fehler": "Diese Handynummer sieht nicht richtig aus."},
                            status_code=400)
    import einladung as ei  # noqa: PLC0415
    if email and not ei.mail_gueltig(email):
        return JSONResponse({"fehler": "Diese E-Mail-Adresse sieht nicht richtig aus."},
                            status_code=400)
    if email:
        # Nicht verbindbar (Abo, schon verbunden, kein Salon): gleich sagen und
        # keine offene Einladung anlegen, die nie eingelöst werden kann.
        with bw._DB_LOCK, bw._db() as c:
            stand, _grund, satz = _verbindbar(email, a[0], c)
        if stand == "nein":
            return JSONResponse({"fehler": satz}, status_code=409)
    slug = re.sub(r"[^a-z0-9]+", "-", (salon or person).lower()).strip("-")[:20] or "salon"
    if telefon or email:
        # Ein eigener Link je Einladung (seit 03.10.2026): zwei „Sabine"
        # dürfen sich beim Einlösen nicht verwechseln.
        slug = f"{slug}-{secrets.token_hex(2)}"
    jetzt = bw._jetzt_iso()
    # Jeder Link ist eine Einladung (seit 02.10.2026): wer ihn noch nicht
    # eingelöst hat, steht als potenzieller Kunde in ihrem Bereich.
    with bw._DB_LOCK, bw._db() as c:
        name = c.execute("SELECT name FROM ambassador WHERE code=?", (a[0],)).fetchone()
        cur = c.execute("""INSERT INTO ambassador_einladung
                           (code, salon, email, slug, erstellt, person, telefon, gesendet)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (a[0], salon or None, email, slug, jetzt, person or None,
                         telefon, jetzt if telefon else None))
        nr = cur.lastrowid
    link = _link(a[0], slug)
    antwort = {"link": link, "id": nr}
    if telefon:
        text = begleiter.nachricht("einladung", person=person or salon,
                                   ambassadorin=name[0] if name else "", link=link)
        antwort.update(text=text, whatsapp=begleiter.whatsapp(telefon, text))
    return JSONResponse(antwort)


# Die öffentlichen Seiten des Programms (Einlösen, Code nicht aktiv) im Look
# der Portal-Anmeldung: dieselben Farben, Schriften und Karten wie
# `#login` in portal.html. Bis 08.10.2026 hatten sie eigene Ad-hoc-Stile —
# Felder ragten aus der Karte, die Absage war eine nackte Überschrift.
_SEITE_CSS = """
:root{--gc-bg:#fff;--gc-canvas:#f7f5f0;--gc-fg:#1d1913;--gc-body:#453e31;
  --gc-desc:#6b6151;--gc-muted:#8f8574;--gc-accent:#8a7c5c;--gc-accent-hover:#736950;
  --gc-border:#e6e0d4;--gc-border-l:#ece7dc;--gc-ok:#6f8a6e;--gc-danger:#a8433a;
  --gc-serif:'Playfair Display',ui-serif,Georgia,serif;
  --gc-sans:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --gc-mono:'SF Mono',ui-monospace,Menlo,monospace}
*{margin:0;padding:0;box-sizing:border-box}
body{font:15px/1.5 var(--gc-sans);color:var(--gc-body);background:var(--gc-canvas);min-height:100dvh}
main{max-width:480px;margin:0 auto;padding:min(9dvh,90px) 20px 40px}
.heim{display:block;text-align:center;font:600 26px var(--gc-serif);color:var(--gc-fg);
  text-decoration:none;letter-spacing:-.015em;margin-bottom:22px}
.kicker{font:500 10px var(--gc-mono);letter-spacing:.14em;text-transform:uppercase;
  margin-bottom:14px;color:var(--gc-accent-hover);text-align:center}
h1{font:600 clamp(30px,6vw,40px) var(--gc-serif);letter-spacing:-.015em;color:var(--gc-fg);
  margin-bottom:8px;text-align:center;line-height:1.1;text-wrap:balance}
main > p{color:var(--gc-desc);margin-bottom:26px;text-align:center;font-size:15px}
.lkarte{background:var(--gc-bg);border:1px solid var(--gc-border);border-radius:16px;
  padding:24px;margin-bottom:16px;box-shadow:0 10px 30px rgba(31,30,26,.07)}
.lkarte input:not([type=checkbox]){width:100%;padding:14px 16px;border:1px solid var(--gc-border);
  border-radius:10px;font:16px var(--gc-sans);background:var(--gc-bg);margin-bottom:10px;
  transition:border-color .15s ease, box-shadow .15s ease}
.lkarte input:focus{border-color:var(--gc-accent);outline:none;box-shadow:0 0 0 3px rgba(133,123,97,.18)}
.lkarte input::placeholder{color:#767676}
.zustimmung{display:flex;gap:10px;align-items:flex-start;font-size:13.5px;margin:4px 0 6px;color:var(--gc-desc)}
.zustimmung input{margin-top:3px;accent-color:var(--gc-fg)}
a{color:var(--gc-accent-hover)}
.voll{width:100%;background:var(--gc-fg);color:#fff;padding:14px 26px;border:0;border-radius:12px;
  font:600 16px var(--gc-sans);margin-top:10px;cursor:pointer;transition:transform .12s ease, background .15s ease}
.voll:hover{background:#000} .voll:active{transform:translateY(1px)}
.voll[disabled]{opacity:.55;cursor:progress}
.fehler{color:var(--gc-danger);font-size:13px;margin-top:12px;background:rgba(168,67,58,.08);
  border-radius:8px;padding:9px 12px}
.meldung{color:#3f5a3e;font-weight:600;background:rgba(111,138,110,.12);border-radius:10px;padding:14px 16px}
small{display:block;margin-top:14px;color:var(--gc-muted);font-size:12px;line-height:1.5}
.nurvorlesen{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;
  clip:rect(0 0 0 0);border:0}
[hidden]{display:none!important}
.login-fuss{text-align:center;font-size:12px;color:var(--gc-muted);margin-top:28px;line-height:1.7}
.login-fuss a{color:var(--gc-muted)}
"""


def _seite(titel: str, kicker: str, ueberschrift: str, unterzeile: str,
           karte: str, roh: bool = False) -> str:
    """Ein Blatt im Look der Portal-Anmeldung. `kicker`, `ueberschrift` und
    `unterzeile` werden maskiert; `karte` ist fertiges HTML. `roh=True` heißt:
    `kicker` ist schon maskiert (er trägt den Namen der Ambassadorin)."""
    k = kicker if roh else html_text.escape(kicker)
    return f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#f4f1ec">
<title>{html_text.escape(titel)}</title><style>{_SEITE_CSS}</style></head><body><main>
<a class="heim" href="/">babu</a>
<div class="kicker">{k}</div>
<h1>{html_text.escape(ueberschrift)}</h1>
<p>{html_text.escape(unterzeile)}</p>
<div class="lkarte">{karte}</div>
<div class="login-fuss">babu · 0711 Intelligence · Stuttgart ·
<a href="/impressum">Impressum</a> · <a href="/datenschutz">Datenschutz</a> ·
<a href="/agb">Nutzungsbedingungen</a></div>
</main></body></html>"""


async def ambassador_landing(code: str, slug: str) -> Response:
    """Die Landing-Seite des Salons: Code steht fest, ein Formular nimmt
    Name/E-Mail auf und legt die Warteliste-Zeile MIT herkunft_code an.
    Bewusst öffentlich (kein Login) — der Salon kennt babu noch nicht."""
    with bw._DB_LOCK, bw._db() as c:
        a = c.execute("SELECT name FROM ambassador WHERE code=? AND aktiv=1",
                      (code,)).fetchone()
    if not a:
        return HTMLResponse(_seite(
            "babu — Code nicht aktiv", "Einladung",
            "Dieser Code ist nicht (mehr) aktiv.",
            "Frag die Person, die dir den Link geschickt hat, nach einem neuen.",
            '<p style="margin:0">Oder schau dir babu erst einmal in Ruhe an: '
            '<a href="/">mybabu.io</a></p>'), status_code=404)
    # Mit Testmonat (seit 02.10.2026) löst das Formular den Code direkt ein
    # und der Zugang steht sofort; ohne Schalter bleibt es der Weg über die
    # Warteliste, auf der die Verwaltung von Hand einlädt.
    if _testmonat_an():
        ziel = "/api/ambassador/einloesen"
        danke = ("Geschafft! Schau in dein Postfach — dort liegt der Link, mit "
                 "dem du dein Passwort setzt. Deine 30 Tage laufen ab heute.")
    else:
        ziel = "/api/warteliste"
        danke = ("Danke! Wir melden uns mit deinem Zugang — dein Testmonat "
                 "startet dann.")
    name = html_text.escape(a[0])
    # Meldungen in eigenen Elementen, die das Skript sichtbar macht. Bis
    # 08.10.2026 landete der Text in einem `display:none`-Absatz, der nie
    # aufging: nach dem Einlösen verschwand das Formular, und der Salon sah
    # eine leere Karte — bei einem Fehler sah er gar nichts.
    karte = f"""<form id="einloesen" onsubmit="return einlosen(this)" novalidate>
<label class="nurvorlesen" for="salon">Name deines Salons</label>
<input id="salon" name="salon" placeholder="Name deines Salons" autocomplete="organization" required>
<label class="nurvorlesen" for="email">Deine E-Mail</label>
<input id="email" name="email" type="email" placeholder="Deine E-Mail" autocomplete="email" required>
<label class="zustimmung"><input name="agb" type="checkbox" required>
<span>Ich stimme den <a href="/agb" target="_blank">Nutzungsbedingungen</a> zu und habe den
<a href="/datenschutz" target="_blank">Datenschutz</a> gelesen.</span></label>
<button class="voll" id="senden">Platz sichern</button>
<p class="fehler" id="fehler" role="alert" aria-live="polite" hidden></p>
</form>
<p class="meldung" id="ok" role="status" aria-live="polite" hidden></p>
<small>Wenn du einlöst, sieht {name}, ob du babu nutzt: wie viele Belege du
hochlädst, nicht die Belege selbst.</small>
<script>
function einlosen(f){{
  const ok = document.getElementById("ok"), fehler = document.getElementById("fehler"),
        knopf = document.getElementById("senden");
  fehler.hidden = true;
  if (!f.salon.value.trim() || !f.email.value.trim()){{
    fehler.textContent = "Bitte Salon und E-Mail eintragen.";
    fehler.hidden = false; return false; }}
  if (!f.agb.checked){{
    fehler.textContent = "Bitte stimm zuerst den Nutzungsbedingungen zu.";
    fehler.hidden = false; return false; }}
  knopf.disabled = true;
  fetch({json.dumps(ziel)}, {{method:"POST",
    headers:{{"Content-Type":"application/json"}},
    body: JSON.stringify({{email:f.email.value.trim(), art:"salon", code:{json.dumps(code)}, slug:{json.dumps(slug)},
      salon:f.salon.value.trim(), agb:f.agb.checked, bemerkung:"Code " + {json.dumps(code)}}})}})
  .then(r => r.json()).then(d => {{
    if (d.ok){{ ok.textContent = {json.dumps(danke)}; ok.hidden = false;
      f.style.display = "none"; }}
    else {{ fehler.textContent = d.fehler || "Da lief etwas schief — gleich nochmal versuchen.";
      fehler.hidden = false; knopf.disabled = false; }}
  }})
  .catch(() => {{ fehler.textContent = "Gerade keine Verbindung — gleich nochmal versuchen.";
    fehler.hidden = false; knopf.disabled = false; }});
  return false;}}
</script>"""
    return HTMLResponse(_seite(
        "babu — 30 Tage testen", f"Empfohlen von {name}",
        "30 Tage babu testen — kostenlos.",
        "Foto machen statt Belege sortieren. 30 Tage babu komplett, "
        "ohne Vertrag, ohne Kündigung.", karte, roh=True))



_VERBINDEN_UNGUELTIG = ("Dieser Link gilt nicht mehr — er ist abgelaufen oder "
                        "unvollständig. Frag die Person, die dich eingeladen hat, "
                        "nach einer neuen Einladung.")
# Was der Salon liest, wenn er nicht (mehr) verbinden kann — die Sätze in
# `_verbindbar` sind für die Ambassadorin geschrieben.
_VERBINDEN_NEIN = {
    "abo": "Du nutzt babu schon mit einem Abo — eine Verbindung ist dafür nicht mehr möglich.",
    "schon_andere": "Dein Salon ist schon mit einer Ambassadorin verbunden.",
    "kein_salon": "Diese Einladung passt zu keinem Salon-Zugang.",
    "selbst": "Diese Einladung passt zu keinem Salon-Zugang.",
}


async def verbinden_seite(token: str) -> Response:
    """Öffentlich: die Seite aus der Mail an einen bestehenden Salon."""
    gelesen = verbinden_lesen(token)
    if not gelesen:
        return HTMLResponse(_seite(
            "babu — Link gilt nicht mehr", "Einladung", "Dieser Link gilt nicht mehr.",
            _VERBINDEN_UNGUELTIG, '<p style="margin:0">Zu babu: '
            '<a href="/portal">anmelden</a></p>'), status_code=404)
    code, email = gelesen
    with bw._DB_LOCK, bw._db() as c:
        a = c.execute("SELECT name FROM ambassador WHERE code=? AND aktiv=1",
                      (code,)).fetchone()
        stand, grund, _satz = _verbindbar(email, code, c)
    name = html_text.escape(a[0]) if a else "babu"
    if not a or stand == "neu":
        return HTMLResponse(_seite(
            "babu — Link gilt nicht mehr", "Einladung", "Dieser Link gilt nicht mehr.",
            _VERBINDEN_UNGUELTIG, '<p style="margin:0"><a href="/portal">Zu babu</a></p>'),
            status_code=404)
    if stand == "nein":
        satz = (f"Du bist schon mit {a[0]} verbunden." if grund == "schon_dir"
                else _VERBINDEN_NEIN.get(grund, _VERBINDEN_UNGUELTIG))
        return HTMLResponse(_seite(
            "babu — Einladung", f"Einladung von {name}", "Alles beim Alten.", satz,
            '<p style="margin:0"><a href="/portal">Zu babu</a></p>', roh=True))
    karte = f"""<p style="margin:0 0 14px">Für dich ändert sich nichts: kein neuer Vertrag,
keine Kosten, deine Belege bleiben, wo sie sind.</p>
<button class="voll" id="senden" onclick="verbinden()">Mit {name} verbinden</button>
<p class="fehler" id="fehler" role="alert" aria-live="polite" hidden></p>
<p class="meldung" id="ok" role="status" aria-live="polite" hidden></p>
<small>Danach sieht {name}, ob du babu nutzt: wie viele Belege du hochlädst, nicht
die Belege selbst. Schließt du später ein Abo ab, bekommt sie dafür eine Provision
von babu — du zahlst dadurch nichts mehr.</small>
<script>
function verbinden(){{
  const ok = document.getElementById("ok"), fehler = document.getElementById("fehler"),
        knopf = document.getElementById("senden");
  fehler.hidden = true; knopf.disabled = true;
  fetch("/api/ambassador/verbinden", {{method:"POST",
    headers:{{"Content-Type":"application/json"}},
    body: JSON.stringify({{token: {json.dumps(token)}}})}})
  .then(r => r.json()).then(d => {{
    if (d.ok){{ ok.textContent = d.hinweis; ok.hidden = false; knopf.hidden = true;
      ok.insertAdjacentHTML("afterend", '<p style="margin-top:12px"><a href="/portal">Weiter zu babu ›</a></p>'); }}
    else {{ fehler.textContent = d.fehler || "Da lief etwas schief — gleich nochmal versuchen.";
      fehler.hidden = false; knopf.disabled = false; }}
  }})
  .catch(() => {{ fehler.textContent = "Gerade keine Verbindung — gleich nochmal versuchen.";
    fehler.hidden = false; knopf.disabled = false; }});
}}
</script>"""
    return HTMLResponse(_seite(
        "babu — Einladung", f"Einladung von {name}",
        f"Mit {a[0]} verbinden?",
        f"{a[0]} empfiehlt babu weiter und möchte deinen Salon in ihre Liste aufnehmen.",
        karte, roh=True))


async def api_ambassador_verbinden(request: Request) -> Response:
    """Öffentlich, mit dem Link aus der Mail: der Salon bestätigt die Verbindung.

    Wer den Link hat, hat die Mail an diese Adresse — das ist die Zustimmung.
    Alles wird beim Klick noch einmal geprüft: ein Abo, das zwischen Mail und
    Klick entstand, oder eine andere Ambassadorin, die schneller war."""
    if not bw._origin_ok(request):  # noqa: SLF001
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 4 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    gelesen = verbinden_lesen(str(koerper.get("token", "") or ""))
    if not gelesen:
        return JSONResponse({"fehler": _VERBINDEN_UNGUELTIG}, status_code=400)
    code, email = gelesen
    with bw._DB_LOCK, bw._db() as c:
        a = c.execute("SELECT name FROM ambassador WHERE code=? AND aktiv=1",
                      (code,)).fetchone()
        if not a:
            return JSONResponse({"fehler": "Diese Einladung gilt nicht mehr."},
                                status_code=409)
        stand, grund, _satz = _verbindbar(email, code, c)
        if stand == "nein" and grund == "schon_dir":
            return JSONResponse({"ok": True, "hinweis": f"Du bist schon mit {a[0]} verbunden."})
        if stand != "ja":
            return JSONResponse({"fehler": _VERBINDEN_NEIN.get(grund, _VERBINDEN_UNGUELTIG)},
                                status_code=409 if stand == "nein" else 400)
        z = c.execute("SELECT salon FROM nutzer WHERE email=?", (email,)).fetchone()
        salon = (z[0] if z else "") or ""
        # ON CONFLICT statt INSERT OR IGNORE — das versteht Postgres nicht.
        c.execute("""INSERT INTO ambassador_salon
                     (code, email, salon, eingelöst) VALUES (?,?,?,?)
                     ON CONFLICT (code, email) DO NOTHING""",
                  (code, email, salon, bw._jetzt_iso()))
        _einladung_eingeloest(code, email, "", c)
    audit.audit(email, "ambassador_verbunden", ziel_un=email, code=code)
    print(f"[ambassador] verbunden: {email} mit {code}", flush=True)
    return JSONResponse({"ok": True,
                         "hinweis": f"Verbunden — {a[0]} sieht deinen Salon jetzt in ihrer Liste."})

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
    nr = koerper.get("id")
    with bw._DB_LOCK, bw._db() as c:
        a = c.execute("SELECT name, code FROM ambassador WHERE email=? AND aktiv=1",
                      (un,)).fetchone()
        gemerkt = None
        if a and isinstance(nr, int) and not isinstance(nr, bool):
            # „Nochmal schicken": nur eine eigene, noch offene Einladung.
            gemerkt = c.execute(
                "SELECT id, salon, email, slug, person FROM ambassador_einladung "
                "WHERE id=? AND code=? AND eingeloest IS NULL", (nr, a[1])).fetchone()
            if not gemerkt:
                return JSONResponse({"fehler": "Diese Einladung gibt es nicht (mehr)."},
                                    status_code=404)
        elif a and link:
            # Ohne Nummer nur ein Link aus IHRER offenen Einladung — babu
            # verschickt von seiner Adresse nie einen fremden Link (03.10.2026).
            slug = link.rstrip("/").rsplit("/", 1)[-1][:24]
            eigen = link.rstrip("/") == _link(a[1], slug) and c.execute(
                "SELECT 1 FROM ambassador_einladung WHERE code=? AND slug=? "
                "AND eingeloest IS NULL", (a[1], slug)).fetchone()
            if not eigen:
                return JSONResponse({"fehler": "Diesen Link kennt babu nicht — bitte "
                                               "neu einladen."}, status_code=400)
    if gemerkt:
        salon = gemerkt[1] or gemerkt[4] or ""
        email, link = gemerkt[2] or "", _link(a[1], gemerkt[3])
    if "@" not in email or not link:
        return JSONResponse({"fehler": "email und link brauchen wir."}, status_code=400)
    import einladung as ei  # noqa: PLC0415
    if not ei.mail_gueltig(email):
        return JSONResponse({"fehler": "Das sieht nicht nach einer E-Mail-Adresse aus."},
                            status_code=400)
    if not a:
        return JSONResponse({"fehler": "Du bist (noch) keine Ambassadorin."},
                            status_code=404)
    with bw._DB_LOCK, bw._db() as c:
        stand, _grund, satz = _verbindbar(email, a[1], c)
    if stand == "nein":
        return JSONResponse({"fehler": satz}, status_code=409)
    import postfach  # noqa: PLC0415
    if not postfach.eingerichtet():
        return JSONResponse({"fehler": "Der Versand ist gerade nicht eingerichtet — "
                                       "schick den Link bitte selbst."}, status_code=503)
    try:
        if stand == "ja":
            # Bestehender Salon: kein Testmonat, sondern die Bitte, sich zu verbinden.
            betreff, text = _verbinden_mail(a[0], salon, a[1], email)
        else:
            anrede = f"Hallo {salon}," if salon else "Hallo,"
            betreff = "babu — 30 Tage testen (Empfehlung von " + a[0] + ")"
            text = (f"{anrede}\n\n"
                    f"{a[0]} empfiehlt dir babu: Foto machen statt Belege sortieren.\n"
                    f"30 Tage testen — kostenlos, ohne Vertrag, ohne Kündigung.\n\n"
                    f"Dein Platz: {link}\n\n"
                    f"Der Code macht's möglich — einfach öffnen und sichern.\n")
        await bw.run_in_threadpool(
            postfach.senden, email, betreff, text,
            stempel=time.strftime("%Y%m%d-%H%M%S"))
    except Exception as ex:  # noqa: BLE001
        print(f"[ambassador] Einladung an {email} fehlgeschlagen: {ex!r}", flush=True)
        return JSONResponse({"fehler": "Die Mail ging nicht raus — später nochmal."},
                            status_code=503)
    _einladung_gesendet(a[1], gemerkt[0] if gemerkt else None, link, salon, email)
    audit.audit(un, "ambassador_einladen", ziel_un=email,
                bestehend=(stand == "ja"))
    if stand == "ja":
        return JSONResponse({"ok": True, "bestehend": True, "hinweis": satz})
    return JSONResponse({"ok": True})


async def api_ambassador_aktiv(request: Request) -> Response:
    """Betreiber: einen Code ab- oder wieder einschalten.

    Abgeschaltet nimmt der Code keine neuen Salons an (Einladungsseite,
    Einlösen, neue Einladungen). Ihre Salons, ihr Geld, ihre Gutschriften und
    die Auszahlung bleiben. Das Konto selbst schaltet „Zugänge“ ab."""
    un, fehler = bw._betreiber_wache(request)
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"}, status_code=401)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 2 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit code und aktiv erwartet"}, status_code=400)
    code = str(koerper.get("code", "") or "").strip()[:60]
    aktiv = koerper.get("aktiv")
    if not code or not isinstance(aktiv, bool):
        return JSONResponse({"fehler": "code und aktiv (ja/nein) brauchen wir."},
                            status_code=400)
    with bw._DB_LOCK, bw._db() as c:
        n = c.execute("UPDATE ambassador SET aktiv=? WHERE code=?",
                      (1 if aktiv else 0, code)).rowcount
    if not n:
        return JSONResponse({"fehler": "Diesen Code gibt es nicht."}, status_code=404)
    audit.audit(un, "ambassador_code_an" if aktiv else "ambassador_code_aus", code=code)
    return JSONResponse({"ok": True, "code": code, "aktiv": aktiv})


async def api_ambassador_meilenstein(request: Request) -> Response:
    """Betreiber: einen Meilenstein von Hand anerkennen.

    Seit 03.10.2026 bucht sich die Provision selbst, sobald Stripe die erste
    bzw. dritte Monatsrechnung als bezahlt meldet (kern_abo). Dieser Weg
    bleibt für Salons ohne Abo über babu (z. B. Überweisung) und für
    Korrekturen — mit derselben Regel (provision.buchen): einmal je Salon und
    Meilenstein, nur in der Reihenfolge testet → gezeichnet → gehalten.

    koerper: code, email (des Salons), meilenstein ('gezeichnet' | 'gehalten'),
    optional paket (solo/salon/plus — sonst das Paket des Abos oder die
    Empfehlung aus den Betriebsangaben), optional betrag (EUR) mit grund:
    ein Betrag abweichend von 3 × Netto-Monatspreis braucht eine Begründung
    und steht im Audit-Log."""
    un, fehler = bw._betreiber_wache(request)
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"}, status_code=401)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 4 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    code = str(koerper.get("code", "") or "").strip()[:60]
    email = str(koerper.get("email", "") or "").strip().lower()[:200]
    meilenstein = str(koerper.get("meilenstein", "") or "").strip()
    if meilenstein not in ("gezeichnet", "gehalten"):
        return JSONResponse({"fehler": "meilenstein (gezeichnet/gehalten) nötig."},
                            status_code=400)
    paket = str(koerper.get("paket", "") or "").strip() or _paket_von(email)
    regel = provision.betrag(paket)
    betrag = koerper.get("betrag")
    grund = str(koerper.get("grund", "") or "").strip()[:200]
    if betrag is None or betrag == regel:
        betrag = regel
    elif not isinstance(betrag, (int, float)) or betrag <= 0:
        return JSONResponse({"fehler": "betrag muss positiv sein."}, status_code=400)
    elif not grund:
        return JSONResponse({"fehler": f"Abweichend von {regel} € — bitte einen Grund "
                                       f"angeben."}, status_code=400)
    betrag = int(betrag)
    if betrag <= 0:
        return JSONResponse({"fehler": "Für dieses Paket gibt es keinen Betrag — "
                                       "bitte paket angeben."}, status_code=400)
    with bw._DB_LOCK, bw._db() as c:
        r = provision.buchen(c, email=email, meilenstein=meilenstein,
                             betrag_eur=betrag, paket=paket, quelle="hand",
                             heute=_heute().isoformat(), code=code)
        if r["ok"] and meilenstein == "gezeichnet":
            # Wer abzeichnet, ist Kunde: der Testmonat endet, alles ist offen.
            direkt = testmonat.direkt_mandant_von(email, c)
            if direkt is not None:
                testmonat.setzen(direkt[0], None, c)
    if not r["ok"]:
        if r["grund"] == "keine_ambassadorin":
            return JSONResponse({"fehler": "Diesen Salon gibt es unter dem Code "
                                           "nicht."}, status_code=404)
        if r["grund"] == "selbst":
            return JSONResponse({"fehler": "Der eigene Salon bringt keine Provision."},
                                status_code=409)
        if r["grund"] == "stand":
            return JSONResponse({"fehler": f"Salon steht auf „{r.get('stand')}“ — "
                                           f"„{meilenstein}“ setzt „"
                                           f"{provision.VORHER[meilenstein]}“ voraus."},
                                status_code=409)
        return JSONResponse({"fehler": "Dieser Meilenstein ist schon gebucht."},
                            status_code=409)
    audit.audit(un, "ambassador_meilenstein", ziel_un=email, code=code,
                meilenstein=meilenstein, betrag=betrag, paket=paket,
                **({"grund": grund} if betrag != regel else {}))
    return JSONResponse({"ok": True, "meilenstein": meilenstein, "verdienst": betrag,
                         "paket": paket})


def _paket_von(email: str) -> str:
    """Paket des Salons: aus dem Abo, sonst die Empfehlung seiner Angaben."""
    with bw._DB_LOCK, bw._db() as c:
        z = c.execute("SELECT m.paket FROM mandant m WHERE m.besitzer_un=? AND "
                      "m.paket IS NOT NULL ORDER BY m.id DESC", (email,)).fetchone()
    if z and z[0]:
        return z[0]
    import saloncheck  # noqa: PLC0415
    return saloncheck.paket_empfehlung(bw.db_einstellungen(email))["paket"]


async def api_ambassador_gezahlt(request: Request) -> Response:
    """Stillgelegt (03.10.2026): Auszahlung nur noch als Lauf mit Gutschrift
    und Bankdatei (kern_auszahlung). Der alte Weg buchte „ausgezahlt" je
    Ambassadorin ohne Gutschrift — zwei Wege für dasselbe Geld vertragen
    sich nicht."""
    un, fehler = bw._betreiber_wache(request)
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"}, status_code=401)
    return JSONResponse({"fehler": "Ausgezahlt wird über den Auszahlungslauf: "
                                   "Verwaltung → Auszahlung an Ambassadorinnen."},
                        status_code=410)



# ---------------------------------------------------------------------------
# Testmonat (seit 02.10.2026) — der Code öffnet sofort einen Zugang.
# Entwurf: docs/superpowers/specs/2026-10-02-testmonat-code-design.md
# ---------------------------------------------------------------------------

def _testmonat_an() -> bool:
    """`BABU_TESTMONAT=1` schaltet das Einlösen ein. Ohne den Schalter bleibt
    der Code ein Weg auf die Warteliste — wie vor dem 02.10.2026."""
    return os.environ.get("BABU_TESTMONAT", "0").strip() == "1"


def _grenze(name: str, standard: int) -> int:
    try:
        return max(0, int(os.environ.get(name, standard)))
    except ValueError:
        return standard


def _testmonate_dazu(salons: list[dict], c) -> None:
    """Je Salon den Stand des Testmonats anhängen (`None` = keiner)."""
    heute = testmonat.heute()
    for s in salons:
        direkt = testmonat.direkt_mandant_von(s["email"], c)
        s["testmonat"] = testmonat.stand(direkt[1], heute) if direkt else None


def _zahlen(salons: list[dict]) -> dict:
    """Die Kennzahlen der Ambassadorin auf einen Blick.

    `testet` und `abgelaufen` zählen nur Salons mit Testmonat; wer über die
    Warteliste kam und noch keinen Zugang hat, steht unter `wartet`."""
    z = {"eingeladen": len(salons), "wartet": 0, "testet": 0, "abgelaufen": 0,
         "gezeichnet": 0, "gehalten": 0}
    for s in salons:
        if s["meilenstein"] in ("gezeichnet", "gehalten"):
            z[s["meilenstein"]] += 1
        elif not s.get("testmonat"):
            z["wartet"] += 1
        elif s["testmonat"]["vorbei"]:
            z["abgelaufen"] += 1
        else:
            z["testet"] += 1
    return z


def _passwort_link(email: str) -> str | None:
    """Der einmalige Link zum Passwortsetzen — wie bei der Kanzlei-Einladung
    (kanzlei_routen._reset_link_anlegen), aber über das hereingereichte `bw`
    statt eines zweiten Imports von babu_web (Dual-Modul-Falle, siehe
    kern_warteliste)."""
    import passwort_reset as pr  # noqa: PLC0415
    if not bw._reset_anfordern_erlaubt(email):  # noqa: SLF001
        return None
    bw._reset_aufraeumen(email)  # noqa: SLF001
    token, modell = pr.anfordern(email)
    with bw._DB_LOCK, bw._db() as c:
        c.execute("""INSERT INTO passwort_reset (token_hash, un, erstellt, laeuft_ab)
                     VALUES (?,?,?,?)""",
                  (modell.token_hash, modell.un, modell.erstellt.isoformat(),
                   modell.laeuft_ab.isoformat()))
    return f"{bw.PORTAL_ORIGIN.rstrip('/')}/portal#reset/{token}"


def _app_absatz() -> str:
    """Wie die App aufs Telefon kommt — siehe startguide.app_absatz."""
    import startguide  # noqa: PLC0415
    return startguide.app_absatz()


def _senden(an: str, betreff: str, text: str) -> bool:
    """Eine Mail verschicken; Rückgabe: ob sie rausging."""
    import postfach  # noqa: PLC0415
    try:
        ok, hinweis = postfach.senden(an, betreff, text,
                                      stempel=time.strftime("%Y%m%d-%H%M%S"))
        print(f"[testmonat] Mail an {an}: {hinweis}", flush=True)
        return bool(ok)
    except Exception as ex:  # noqa: BLE001
        print(f"[testmonat] Mail an {an} fehlgeschlagen: {ex!r}", flush=True)
        return False


# ————— Bestehende Salons verbinden (seit 08.10.2026) —————
#
# Entscheidung Auftraggeber 08.10.2026: Gibt die Ambassadorin die Adresse
# eines Salons ein, der babu schon nutzt, sieht sie das, und der Salon
# bekommt eine Mail mit einem Link, über den ER die Verbindung bestätigt —
# keine Ambassadorin reserviert sich Salons ohne deren Wissen. Wer schon ein
# laufendes Abo bezahlt, wurde ohne sie gewonnen (keine Provision); wer schon
# mit einer Ambassadorin verbunden ist, bleibt bei ihr. Bis dahin bekam ein
# bestehender Salon nur „Du hast schon einen Zugang" — und keine Verbindung.

VERBINDEN_TAGE = 30
_LAUFENDES_ABO = ("aktiv", "zahlung_offen")


def _verbinden_schluessel() -> bytes:
    """Aus dem Sitzungsgeheimnis abgeleitet, aber ein eigener Schlüssel: ein
    Anmelde-Cookie ist nie ein gültiger Verbinden-Link und umgekehrt."""
    return hmac.new(bw._geheimnis(), b"babu-ambassador-verbinden",  # noqa: SLF001
                    hashlib.sha256).digest()


def verbinden_token(code: str, email: str) -> str:
    """Der Link-Teil für /verbinden/<token>: Code, Adresse, Ablauf — signiert."""
    ablauf = int(time.time()) + VERBINDEN_TAGE * 86400
    nutz = base64.urlsafe_b64encode(f"{code}|{email}|{ablauf}".encode()).decode().rstrip("=")
    sig = hmac.new(_verbinden_schluessel(), nutz.encode(), hashlib.sha256).hexdigest()
    return f"{nutz}.{sig}"


def verbinden_lesen(token: str) -> tuple[str, str] | None:
    """(code, email) aus einem gültigen, nicht abgelaufenen Link — sonst None."""
    try:
        nutz, sig = str(token).split(".", 1)
        soll = hmac.new(_verbinden_schluessel(), nutz.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, soll):
            return None
        code, email, ablauf = base64.urlsafe_b64decode(
            nutz + "=" * (-len(nutz) % 4)).decode().split("|")
        if int(ablauf) < time.time():
            return None
        return code, email
    except Exception:  # noqa: BLE001 — jeder kaputte Link ist schlicht ungültig
        return None


def _verbindbar(email: str, code: str, c) -> tuple[str, str, str]:
    """Darf dieser Code diese Adresse einladen? `(stand, grund, satz)`.

    stand `neu` (kein Konto: der normale Testmonat), `ja` (bestehender Salon,
    verbindbar) oder `nein`; `satz` ist der Text für die Ambassadorin. Nimmt
    KEIN Schloss — der Aufrufer hält `_DB_LOCK` und gibt `c` mit."""
    z = c.execute("SELECT rolle, gehoert_zu FROM nutzer WHERE email=?", (email,)).fetchone()
    if not z:
        return "neu", "", ""
    amb = c.execute("SELECT email FROM ambassador WHERE code=?", (code,)).fetchone()
    if amb and str(amb[0]).lower() == email:
        return "nein", "selbst", "Dich selbst kannst du nicht einladen."
    if z[0] != "salon" or z[1]:
        return "nein", "kein_salon", ("Zu dieser Adresse gibt es schon einen babu-Zugang, "
                                      "aber keinen Salon, den du einladen kannst.")
    v = c.execute("SELECT code FROM ambassador_salon WHERE email=? ORDER BY eingelöst",
                  (email,)).fetchone()
    if v:
        if v[0] == code:
            return "nein", "schon_dir", "Dieser Salon ist schon mit dir verbunden."
        return "nein", "schon_andere", "Dieser Salon ist schon mit einer Ambassadorin verbunden."
    if c.execute("SELECT 1 FROM mandant WHERE besitzer_un=? AND abo_status IN (?,?)",
                 (email, *_LAUFENDES_ABO)).fetchone():
        return "nein", "abo", ("Dieser Salon nutzt babu schon mit einem Abo — dafür gibt "
                               "es keine Provision.")
    return "ja", "", ("Den Salon gibt es schon bei babu — er bekommt eine Einladung, "
                      "sich mit dir zu verbinden.")


def _verbinden_mail(ambassadorin: str, salon: str, code: str, email: str) -> tuple[str, str]:
    """Betreff und Text der Mail an einen bestehenden Salon."""
    link = f"{bw.PORTAL_ORIGIN.rstrip('/')}/verbinden/{verbinden_token(code, email)}"
    anrede = f"Hallo {salon}," if salon else "Hallo,"
    text = (f"{anrede}\n\n"
            f"{ambassadorin} empfiehlt babu weiter und möchte deinen Salon in ihre "
            f"Liste aufnehmen. Du nutzt babu schon — für dich ändert sich nichts: "
            f"kein neuer Vertrag, keine Kosten, deine Belege bleiben, wo sie sind.\n\n"
            f"Wenn du einverstanden bist, bestätige hier:\n\n    {link}\n\n"
            f"Danach sieht {ambassadorin}, ob du babu nutzt (wie viele Belege du "
            f"hochlädst, nicht die Belege selbst). Schließt du später ein Abo ab, "
            f"bekommt sie dafür eine Provision von babu — du zahlst dadurch nichts mehr.\n\n"
            f"Der Link gilt {VERBINDEN_TAGE} Tage. Wenn du nicht verbinden möchtest, "
            f"ignoriere diese Mail einfach.\n")
    return f"babu — {ambassadorin} möchte sich mit deinem Salon verbinden", text


_EINGELOEST = ("Geschafft! Schau in dein Postfach — dort liegt der Link, mit "
               "dem du dein Passwort setzt.")


def testmonat_willkommen(email: str, salon: str, bis, ambassadorin: str | None = None) -> bool:
    """Die Willkommensmail eines Testmonats — mit Link zum Passwortsetzen.

    Ein Baustein für alle Wege in den Testmonat (seit 08.10.2026): Code einer
    Ambassadorin, direkt über die Startseite, Einladung von der Warteliste,
    „Zugang anlegen" in der Verwaltung. Bis dahin endete die Mail mit „Wenn
    du weitermachen willst, antworte einfach auf diese Mail" — seit 03.10.
    geht das im Portal unter „Weitermachen"."""
    link = _passwort_link(email)
    herkunft = f" — empfohlen von {ambassadorin}" if ambassadorin else ""
    text = (f"Hallo,\n\n"
            f"schön, dass du babu ausprobierst{herkunft}. "
            f"Dein Zugang für „{salon}“ steht. Du hast {testmonat.TAGE} Tage "
            f"babu komplett, bis einschließlich {bis.strftime('%d.%m.%Y')}; "
            f"kostenlos, ohne Vertrag, kündigen musst du nichts.\n\n"
            f"Beim ersten Öffnen legst du dein Passwort fest:\n\n"
            f"    {link or bw.PORTAL_ORIGIN.rstrip('/') + '/portal'}\n\n")
    import startguide  # noqa: PLC0415
    text += (startguide.schritte(bw.PORTAL_ORIGIN) + "\n" + _app_absatz()
             + f"\nNach den {testmonat.TAGE} Tagen bleibt alles da und lesbar. Wenn du "
               "weitermachen willst, tippst du im Portal auf „Weitermachen“ — "
               "dort wählst du dein Paket.\n")
    return _senden(email, "Dein babu-Testmonat startet", text)


async def api_ambassador_einloesen(request: Request) -> Response:
    """Öffentlich: ein Salon löst den Code ein und hat SOFORT einen Zugang.

    Konto (ohne sichtbares Passwort), eigener Mandant in der Hauskanzlei
    „babu direkt" (die Ablage legt der Box-Anleger an), 30 Tage Testmonat,
    Zuordnung zur Ambassadorin, Willkommensmail mit Passwort-Link. Für eine
    Adresse, die schon ein Konto hat, dieselbe Antwort und nur ein Hinweis
    per Mail — das Formular darf kein Melder für bestehende Konten sein.
    """
    if not _testmonat_an():
        return JSONResponse({"fehler": "nicht gefunden"}, status_code=404)
    if not bw._origin_ok(request):  # noqa: SLF001
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    ip = bw._client_ip(request)  # noqa: SLF001
    jetzt = time.time()
    if jetzt - bw._REG_ZULETZT.get(ip, 0.0) < 30:  # noqa: SLF001
        return JSONResponse({"fehler": "kurz warten, dann nochmal"}, status_code=429)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 8 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    import einladung as ei  # noqa: PLC0415
    code = str(koerper.get("code", "") or "").strip()[:60]
    salon = str(koerper.get("salon", "") or "").strip()[:120]
    email = str(koerper.get("email", "") or "").strip().lower()[:200]
    if not salon:
        return JSONResponse({"fehler": "Wie heißt dein Salon?"}, status_code=400)
    if koerper.get("agb") is not True:
        return JSONResponse({"fehler": "Bitte den Nutzungsbedingungen zustimmen."},
                            status_code=400)
    if not ei.mail_gueltig(email):
        return JSONResponse({"fehler": "Diese E-Mail-Adresse sieht nicht "
                                       "richtig aus."}, status_code=400)
    with bw._DB_LOCK, bw._db() as c:
        a = c.execute("SELECT name FROM ambassador WHERE code=? AND aktiv=1",
                      (code,)).fetchone()
    if not a:
        return JSONResponse({"fehler": "Dieser Code ist nicht (mehr) aktiv."},
                            status_code=404)
    ambassadorin = a[0]
    bw._REG_ZULETZT[ip] = jetzt  # noqa: SLF001
    bw._zaehler_aufraeumen(bw._REG_ZULETZT, jetzt, 3600)  # noqa: SLF001

    if bw.nutzer_holen(email) is not None:
        # Ein bestehender Salon, der verbindbar ist, bekommt die Bitte, sich
        # mit der Ambassadorin zu verbinden (seit 08.10.2026); die Antwort
        # bleibt dieselbe — das öffentliche Formular verrät keine Konten.
        with bw._DB_LOCK, bw._db() as c:
            stand, _grund, _satz = _verbindbar(email, code, c)
        if stand == "ja":
            betreff, text = _verbinden_mail(ambassadorin, salon, code, email)
            await bw.run_in_threadpool(_senden, email, betreff, text)
            return JSONResponse({"ok": True, "hinweis": _EINGELOEST})
        await bw.run_in_threadpool(
            _senden, email, "Du hast schon einen Zugang zu babu",
            "Hallo,\n\njemand hat mit dieser Adresse einen babu-Testmonat "
            "angefragt. Für diese Adresse gibt es schon einen Zugang — melde "
            f"dich einfach an: {bw.PORTAL_ORIGIN.rstrip('/')}/portal\n\n"
            "Passwort vergessen? Auf der Anmeldeseite gibt es dafür einen "
            "Link.\n\nWenn du das nicht warst, ignoriere diese Nachricht.\n")
        return JSONResponse({"ok": True, "hinweis": _EINGELOEST})

    heute = testmonat.heute()
    # Gezählt wird gegen die Stempel `eingelöst`/`angelegt` — die schreibt
    # `_jetzt_iso()` in UTC. Mit dem Ortsdatum verglichen griff die Grenze
    # zwischen Mitternacht und 1 bzw. 2 Uhr nicht (die Suite fiel um 0:26
    # Ortszeit, 03.10.2026).
    tag = time.strftime("%Y-%m-%d", time.gmtime())
    with bw._DB_LOCK, bw._db() as c:
        je_code = c.execute("SELECT COUNT(*) FROM ambassador_salon "
                            "WHERE code=? AND eingelöst LIKE ?",
                            (code, tag + "%")).fetchone()[0]
        kid = testmonat.direkt_kanzlei(c)
        je_tag = c.execute("SELECT COUNT(*) FROM mandant WHERE kanzlei_id=? "
                           "AND test_bis IS NOT NULL AND angelegt LIKE ?",
                           (kid, tag + "%")).fetchone()[0]
    if (je_code >= _grenze("BABU_TEST_JE_CODE_TAG", 5)
            or je_tag >= _grenze("BABU_TEST_JE_TAG", 20)):
        print(f"[testmonat] Grenze erreicht: Code {code} heute {je_code}, "
              f"alle heute {je_tag}", flush=True)
        return JSONResponse({"fehler": "Heute sind alle Testplätze vergeben — "
                                       "versuch es morgen noch einmal."},
                            status_code=429)

    # nutzer_anlegen nimmt das Schloss selbst — NICHT in einem with-Block.
    # box=False: die Default-Box ist die Ablage eines anderen Betriebs.
    if bw.nutzer_anlegen(email, "", salon, "salon", box=False) is None:
        return JSONResponse({"ok": True, "hinweis": _EINGELOEST})  # Wettlauf
    bis = testmonat.ende_fuer_start(heute)
    with bw._DB_LOCK, bw._db() as c:
        mandant_id = mandanten.mandant_anlegen(kid, salon, email, "SKR04", c=c)
        testmonat.setzen(mandant_id, bis, c)
        # ON CONFLICT statt INSERT OR IGNORE — das versteht Postgres nicht.
        c.execute("""INSERT INTO ambassador_salon
                     (code, email, salon, eingelöst) VALUES (?,?,?,?)
                     ON CONFLICT (code, email) DO NOTHING""",
                  (code, email, salon, bw._jetzt_iso()))
        _einladung_eingeloest(code, email, str(koerper.get("slug", "") or ""), c)
    await bw.run_in_threadpool(testmonat_willkommen, email, salon, bis, ambassadorin)
    if bw.SUPPORT_MAIL:
        await bw.run_in_threadpool(
            _senden, bw.SUPPORT_MAIL, f"Testmonat gestartet: {salon}",
            f"Hallo,\n\nein Salon hat einen Ambassador-Code eingelöst:\n\n"
            f"    Salon: {salon}\n    E-Mail: {email}\n"
            f"    Empfohlen von: {ambassadorin} (Code {code})\n"
            f"    Testmonat bis: {bis.strftime('%d.%m.%Y')}\n\n"
            f"Die Ablage richtet sich von selbst ein. Gezeichnet oder "
            f"verlängern: Portal → Verwaltung → Ambassadorinnen.\n")
    import recht  # noqa: PLC0415
    audit.audit(f"code:{code}", "testmonat_eingeloest", ziel_un=email,
                mandant_id=str(mandant_id), bis=bis.isoformat(),
                agb=recht.fassung("agb"), datenschutz=recht.fassung("datenschutz"))
    print(f"[testmonat] {salon} <{email}> über {code} bis {bis}", flush=True)
    return JSONResponse({"ok": True, "hinweis": _EINGELOEST})



# ————— Testmonat direkt über die Startseite (seit 08.10.2026) —————
#
# Entscheidung Auftraggeber 08.10.2026: Wer über die Startseite kommt, startet
# sofort 30 Tage — so wie mit dem Code einer Ambassadorin, nur ohne sie. Bis
# dahin versprach die Startseite „den ersten Monat testest du kostenlos", und
# „Konto anlegen" führte auf die Warteliste.

async def testen_seite() -> Response:
    """Öffentlich: das Formular für den Testmonat ohne Code."""
    if not _testmonat_an():
        return HTMLResponse(_seite(
            "babu — 30 Tage testen", "Testmonat", "Gerade geht das nicht.",
            "Trag dich auf der Anmeldeseite auf die Warteliste ein — wir melden uns.",
            '<p style="margin:0"><a href="/portal">Zur Anmeldeseite</a></p>'), status_code=404)
    karte = f"""<form id="testen" onsubmit="return starten(this)" novalidate>
<label class="nurvorlesen" for="salon">Name deines Betriebs</label>
<input id="salon" name="salon" placeholder="Name deines Salons oder Betriebs" autocomplete="organization" required>
<label class="nurvorlesen" for="email">Deine E-Mail</label>
<input id="email" name="email" type="email" placeholder="Deine E-Mail" autocomplete="email" required>
<label class="zustimmung"><input name="agb" type="checkbox" required>
<span>Ich stimme den <a href="/agb" target="_blank">Nutzungsbedingungen</a> zu und habe den
<a href="/datenschutz" target="_blank">Datenschutz</a> gelesen.</span></label>
<button class="voll" id="senden">30 Tage starten</button>
<p class="fehler" id="fehler" role="alert" aria-live="polite" hidden></p>
</form>
<p class="meldung" id="ok" role="status" aria-live="polite" hidden></p>
<small>Danach wählst du dein Paket — oder hörst einfach auf. Kündigen musst du nichts.
Schon dabei? <a href="/portal">Hier anmelden</a>.</small>
<script>
function starten(f){{
  const ok = document.getElementById("ok"), fehler = document.getElementById("fehler"),
        knopf = document.getElementById("senden");
  fehler.hidden = true;
  if (!f.salon.value.trim() || !f.email.value.trim()){{
    fehler.textContent = "Bitte Betrieb und E-Mail eintragen."; fehler.hidden = false; return false; }}
  if (!f.agb.checked){{
    fehler.textContent = "Bitte stimm zuerst den Nutzungsbedingungen zu."; fehler.hidden = false; return false; }}
  knopf.disabled = true;
  fetch("/api/testmonat/starten", {{method:"POST", headers:{{"Content-Type":"application/json"}},
    body: JSON.stringify({{salon:f.salon.value.trim(), email:f.email.value.trim(), agb:f.agb.checked}})}})
  .then(r => r.json()).then(d => {{
    if (d.ok){{ ok.textContent = d.hinweis; ok.hidden = false; f.style.display = "none"; }}
    else {{ fehler.textContent = d.fehler || "Da lief etwas schief — gleich nochmal versuchen.";
      fehler.hidden = false; knopf.disabled = false; }}
  }})
  .catch(() => {{ fehler.textContent = "Gerade keine Verbindung — gleich nochmal versuchen.";
    fehler.hidden = false; knopf.disabled = false; }});
  return false;}}
</script>"""
    return HTMLResponse(_seite(
        "babu — 30 Tage testen", "Für deinen Betrieb", "30 Tage babu testen — kostenlos.",
        "Foto machen statt Belege sortieren. 30 Tage babu komplett, ohne Vertrag, "
        "ohne Kündigung.", karte))


async def api_testmonat_starten(request: Request) -> Response:
    """Öffentlich: Testmonat ohne Code — derselbe Weg wie beim Einlösen,
    nur ohne Ambassadorin. Für eine Adresse mit Konto dieselbe Antwort und
    nur ein Hinweis per Mail (kein Konto-Orakel)."""
    if not _testmonat_an():
        return JSONResponse({"fehler": "nicht gefunden"}, status_code=404)
    if not bw._origin_ok(request):  # noqa: SLF001
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    ip = bw._client_ip(request)  # noqa: SLF001
    jetzt = time.time()
    if jetzt - bw._REG_ZULETZT.get(ip, 0.0) < 30:  # noqa: SLF001
        return JSONResponse({"fehler": "kurz warten, dann nochmal"}, status_code=429)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 8 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    import einladung as ei  # noqa: PLC0415
    salon = str(koerper.get("salon", "") or "").strip()[:120]
    email = str(koerper.get("email", "") or "").strip().lower()[:200]
    if not salon:
        return JSONResponse({"fehler": "Wie heißt dein Betrieb?"}, status_code=400)
    if koerper.get("agb") is not True:
        return JSONResponse({"fehler": "Bitte den Nutzungsbedingungen zustimmen."},
                            status_code=400)
    if not ei.mail_gueltig(email):
        return JSONResponse({"fehler": "Diese E-Mail-Adresse sieht nicht "
                                       "richtig aus."}, status_code=400)
    bw._REG_ZULETZT[ip] = jetzt  # noqa: SLF001
    bw._zaehler_aufraeumen(bw._REG_ZULETZT, jetzt, 3600)  # noqa: SLF001
    if bw.nutzer_holen(email) is not None:
        await bw.run_in_threadpool(
            _senden, email, "Du hast schon einen Zugang zu babu",
            "Hallo,\n\njemand hat mit dieser Adresse einen babu-Testmonat "
            "angefragt. Für diese Adresse gibt es schon einen Zugang — melde "
            f"dich einfach an: {bw.PORTAL_ORIGIN.rstrip('/')}/portal\n\n"
            "Passwort vergessen? Auf der Anmeldeseite gibt es dafür einen "
            "Link.\n\nWenn du das nicht warst, ignoriere diese Nachricht.\n")
        return JSONResponse({"ok": True, "hinweis": _EINGELOEST})
    tag = time.strftime("%Y-%m-%d", time.gmtime())
    with bw._DB_LOCK, bw._db() as c:
        kid = testmonat.direkt_kanzlei(c)
        je_tag = c.execute("SELECT COUNT(*) FROM mandant WHERE kanzlei_id=? "
                           "AND test_bis IS NOT NULL AND angelegt LIKE ?",
                           (kid, tag + "%")).fetchone()[0]
    if je_tag >= _grenze("BABU_TEST_JE_TAG", 20):
        print(f"[testmonat] Grenze erreicht (direkt): heute {je_tag}", flush=True)
        return JSONResponse({"fehler": "Heute sind alle Testplätze vergeben — "
                                       "versuch es morgen noch einmal."},
                            status_code=429)
    if bw.nutzer_anlegen(email, "", salon, "salon", box=False) is None:
        return JSONResponse({"ok": True, "hinweis": _EINGELOEST})  # Wettlauf
    bis = testmonat.ende_fuer_start(testmonat.heute())
    with bw._DB_LOCK, bw._db() as c:
        mandant_id = mandanten.mandant_anlegen(kid, salon, email, "SKR04", c=c)
        testmonat.setzen(mandant_id, bis, c)
    bw.db_einstellung_setzen(email, "betrieb_name", salon)
    await bw.run_in_threadpool(testmonat_willkommen, email, salon, bis, None)
    if bw.SUPPORT_MAIL:
        await bw.run_in_threadpool(
            _senden, bw.SUPPORT_MAIL, f"Testmonat gestartet: {salon}",
            f"Hallo,\n\nein Betrieb hat über die Startseite einen Testmonat "
            f"gestartet:\n\n    Betrieb: {salon}\n    E-Mail: {email}\n"
            f"    Testmonat bis: {bis.strftime('%d.%m.%Y')}\n\n"
            f"Die Ablage richtet sich von selbst ein.\n")
    import recht  # noqa: PLC0415
    audit.audit("startseite", "testmonat_direkt", ziel_un=email,
                mandant_id=str(mandant_id), bis=bis.isoformat(),
                agb=recht.fassung("agb"), datenschutz=recht.fassung("datenschutz"))
    print(f"[testmonat] direkt: {salon} <{email}> bis {bis}", flush=True)
    return JSONResponse({"ok": True, "hinweis": _EINGELOEST})

async def api_ambassador_verlaengern(request: Request) -> Response:
    """Verwaltung: den Testmonat eines Direkt-Salons verlängern (1–60 Tage)."""
    un, fehler = bw._betreiber_wache(request)
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"}, status_code=401)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 4 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit email erwartet"}, status_code=400)
    email = str(koerper.get("email", "") or "").strip().lower()[:200]
    tage = koerper.get("tage", 14)
    if not isinstance(tage, int) or isinstance(tage, bool) or not 1 <= tage <= 60:
        return JSONResponse({"fehler": "tage zwischen 1 und 60."}, status_code=400)
    heute = testmonat.heute()
    with bw._DB_LOCK, bw._db() as c:
        direkt = testmonat.direkt_mandant_von(email, c)
        if direkt is None or not direkt[1]:
            return JSONResponse({"fehler": "Für diese Adresse läuft kein Testmonat."},
                                status_code=404)
        neu = testmonat.neues_ende(direkt[1], tage, heute)
        testmonat.setzen(direkt[0], neu, c)
    audit.audit(un, "testmonat_verlaengert", ziel_un=email,
                bis=neu.isoformat(), tage=tage)
    return JSONResponse({"ok": True,
                         "testmonat": testmonat.stand(neu.isoformat(), heute)})



# ---------------------------------------------------------------------------
# Ambassador-Cockpit (seit 02.10.2026): Pipeline je Kunde, Einladungen, Geld.
# Auszahlung quartalsweise zum 15. nach Quartalsende, ab 100 € (Entscheidung
# Auftraggeber). Keine Beträge „in Aussicht", solange die Preise
# Beispielpreise sind.
# ---------------------------------------------------------------------------

MINDEST_AUSZAHLUNG = 100
LAUF_MONATE = (1, 4, 7, 10)
LAUF_TAG = 15
_SALON_SPALTEN = ("email", "salon", "eingelöst", "meilenstein", "verdienst",
                  "gezeichnet_am", "gehalten_am")


def _heute() -> dt.date:
    return testmonat.heute()


def _de(tag: dt.date) -> str:
    return tag.strftime("%d.%m.%Y")


def _link(code: str, slug: str) -> str:
    return f"{bw.PORTAL_ORIGIN}/ambassador/{code}/{slug}"


def naechster_lauf(heute: dt.date) -> dt.date:
    """Der nächste Auszahlungstag (15.01./15.04./15.07./15.10.), heute eingeschlossen."""
    for jahr in (heute.year, heute.year + 1):
        for monat in LAUF_MONATE:
            tag = dt.date(jahr, monat, LAUF_TAG)
            if tag >= heute:
                return tag
    raise AssertionError("unerreichbar")


def letzter_lauf(heute: dt.date) -> dt.date:
    """Der letzte Auszahlungstag, der schon da ist — den führt die Verwaltung aus."""
    return max(dt.date(jahr, monat, LAUF_TAG)
               for jahr in (heute.year - 1, heute.year) for monat in LAUF_MONATE
               if dt.date(jahr, monat, LAUF_TAG) <= heute)


def stichtag(lauf: dt.date) -> dt.date:
    """Was bis zum Ende des Quartals vor dem Lauf verdient ist, kommt mit."""
    return dt.date(lauf.year, lauf.month, 1) - dt.timedelta(days=1)


def monate_spaeter(tag: dt.date, monate: int) -> dt.date:
    jahre, rest = divmod(tag.month - 1 + monate, 12)
    jahr, monat = tag.year + jahre, rest + 1
    return dt.date(jahr, monat, min(tag.day, calendar.monthrange(jahr, monat)[1]))


def _datum(text: str | None) -> dt.date | None:
    return dt.date.fromisoformat(str(text)[:10]) if text else None


def _pipeline_dazu(salons: list[dict], code: str, c) -> None:
    """Je Salon die Zeitleiste (`stufen`) und den nächsten Schritt."""
    heute = _heute()
    for s in salons:
        eingeladen = c.execute(
            "SELECT MIN(erstellt) FROM ambassador_einladung WHERE code=? AND email=?",
            (code, s["email"])).fetchone()[0] or s["eingelöst"]
        gezeichnet = _datum(s.get("gezeichnet_am"))
        tm = s.get("testmonat")
        s["stufen"] = [
            {"stufe": "eingeladen", "datum": str(eingeladen)[:10]},
            {"stufe": "eingeloest", "datum": str(s["eingelöst"])[:10]},
            {"stufe": "test_endet", "datum": tm["bis"] if tm else None},
            {"stufe": "gezeichnet", "datum": s.get("gezeichnet_am")},
            {"stufe": "gehalten", "datum": s.get("gehalten_am"),
             "faellig": monate_spaeter(gezeichnet, 3).isoformat() if gezeichnet else None},
        ]
        s["naechster_schritt"] = _naechster_schritt(s, tm, gezeichnet, heute)


def _naechster_schritt(s: dict, tm: dict | None, gezeichnet: dt.date | None,
                       heute: dt.date) -> str:
    name = s.get("salon") or "der Salon"
    if s["meilenstein"] == "gehalten":
        return "Fertig — beide Boni verdient."
    if s["meilenstein"] == "gezeichnet":
        faellig = monate_spaeter(gezeichnet, 3) if gezeichnet else None
        return (f"3-Monats-Bonus fällig am {_de(faellig)}, wenn {name} dann noch "
                f"dabei ist." if faellig else "3-Monats-Bonus folgt nach drei Monaten.")
    if not tm:
        return "Wartet auf den Zugang von babu."
    bis = _de(dt.date.fromisoformat(tm["bis"]))
    if tm["vorbei"]:
        return f"Test ist am {bis} abgelaufen — frag nach, ob {name} bleiben will."
    if tm["tage_uebrig"] <= 7:
        return f"Test endet am {bis} — jetzt nachfragen, wie es läuft."
    return f"Testet noch bis {bis} — in der letzten Woche nachfragen."


def _offene_einladungen(code: str, c) -> list[dict]:
    """Wer eingeladen ist, aber noch nicht eingelöst hat.

    `bestehend` (seit 08.10.2026): die Adresse hat schon ein babu-Konto —
    dann wartet die Einladung auf die Bestätigung der Verbindung und nicht
    auf einen Testmonat, der nie „startet"."""
    zeilen = [dict(zip(("id", "salon", "email", "erstellt", "gesendet"), z))
              for z in c.execute(
                  "SELECT e.id, e.salon, e.email, e.erstellt, e.gesendet "
                  "FROM ambassador_einladung e WHERE e.code=? AND e.eingeloest IS NULL "
                  "AND NOT EXISTS (SELECT 1 FROM ambassador_salon s WHERE s.code=e.code "
                  "AND s.email=e.email) ORDER BY e.erstellt DESC, e.id DESC", (code,))]
    for e in zeilen:
        e["bestehend"] = bool(e["email"]) and c.execute(
            "SELECT 1 FROM nutzer WHERE email=?", (e["email"],)).fetchone() is not None
    return zeilen


def _einladung_gesendet(code: str, nr: int | None, link: str, salon: str,
                        email: str) -> None:
    """Eine verschickte Einladung merken: die genannte, sonst die offene zum
    selben Link, sonst eine neue."""
    slug = link.rstrip("/").rsplit("/", 1)[-1][:24] or "salon"
    jetzt = bw._jetzt_iso()
    with bw._DB_LOCK, bw._db() as c:
        if nr is None:
            z = c.execute("SELECT id FROM ambassador_einladung WHERE code=? AND slug=? "
                          "AND eingeloest IS NULL AND (email IS NULL OR email=?) "
                          "ORDER BY id DESC", (code, slug, email)).fetchone()
            nr = z[0] if z else None
        if nr is None:
            c.execute("""INSERT INTO ambassador_einladung
                         (code, salon, email, slug, erstellt, gesendet)
                         VALUES (?,?,?,?,?,?)""",
                      (code, salon or None, email, slug, jetzt, jetzt))
        else:
            c.execute("UPDATE ambassador_einladung SET email=?, "
                      "salon=COALESCE(?, salon), gesendet=? WHERE id=?",
                      (email, salon or None, jetzt, nr))


def _einladung_eingeloest(code: str, email: str, slug: str, c) -> None:
    """Beim Einlösen die passende Einladung schließen — über die Adresse, oder
    über den Link, wenn er einen Salonnamen trug und an keine Adresse ging."""
    slug = re.sub(r"[^a-z0-9-]+", "", slug.lower())[:24]
    c.execute("UPDATE ambassador_einladung SET eingeloest=?, email=COALESCE(email, ?) "
              "WHERE code=? AND eingeloest IS NULL AND (email=? OR "
              "(email IS NULL AND slug=? AND slug <> 'salon'))",
              (bw._jetzt_iso(), email, code, email, slug))


def _faellig(offen: list[dict], heute: dt.date) -> dict:
    lauf = letzter_lauf(heute)
    bis = stichtag(lauf).isoformat()
    betrag = sum(b["betrag"] for b in offen if str(b["datum"])[:10] <= bis)
    return {"datum": lauf.isoformat(), "stichtag": bis, "betrag": betrag,
            "auszahlbar": betrag >= MINDEST_AUSZAHLUNG}


_MEILENSTEIN_TEXT = {"gezeichnet": "gezeichnet", "gehalten": "3 Monate dabei",
                     "storno_gezeichnet": "Zahlung zurückgebucht",
                     "storno_gehalten": "Zahlung zurückgebucht"}


def _bewegungen(code: str, c) -> list[dict]:
    """Das Konto der Ambassadorin wie ein Kontoauszug: jede Provision als
    Gutschrift, jede Auszahlung als Abgang — neueste zuerst."""
    zeilen = [{"datum": str(b[0])[:10],
               "text": f"Provision {b[1] or 'Salon'}, "
                       f"{_MEILENSTEIN_TEXT.get(b[2], b[2])}",
               "betrag": int(b[3]), "art": "provision"}
              for b in c.execute("SELECT datum, salon, meilenstein, betrag "
                                 "FROM ambassador_buchung WHERE code=?", (code,))]
    zeilen += [{"datum": str(a[0])[:10],
                "text": f"Auszahlung (verdient bis {_de(_datum(a[1]))})",
                "betrag": -int(a[2]), "art": "auszahlung"}
               for a in c.execute("SELECT datum, stichtag, betrag "
                                  "FROM ambassador_auszahlung WHERE code=? AND "
                                  "(status IS NULL OR status='ueberwiesen')", (code,))]
    # Am selben Tag erst die Gutschrift, dann die Auszahlung (absteigend sortiert).
    zeilen.sort(key=lambda z: (z["datum"], z["art"] == "provision"), reverse=True)
    return zeilen


def _geld(code: str, c) -> dict:
    """Verdient, ausgezahlt, offen — und was der nächste Lauf bringt."""
    heute = _heute()
    z = c.execute("SELECT verdient, gezahlt FROM ambassador WHERE code=?",
                  (code,)).fetchone()
    verdient, gezahlt = (z[0], z[1]) if z else (0, 0)
    offen = [dict(zip(("salon", "meilenstein", "betrag", "datum"), b))
             for b in c.execute(
                 "SELECT salon, meilenstein, betrag, datum FROM ambassador_buchung "
                 "WHERE code=? AND auszahlung_id IS NULL ORDER BY datum", (code,))]
    lauf = naechster_lauf(heute)
    bis = stichtag(lauf).isoformat()
    posten = [b for b in offen if str(b["datum"])[:10] <= bis]
    betrag = sum(b["betrag"] for b in posten)
    if betrag >= MINDEST_AUSZAHLUNG:
        hinweis = f"Kommt am {_de(lauf)}."
    elif betrag > 0:
        hinweis = (f"{betrag} € liegt unter {MINDEST_AUSZAHLUNG} € — das wandert ins "
                   f"nächste Quartal.")
    else:
        hinweis = f"Bis zum {_de(stichtag(lauf))} ist noch nichts verdient."
    # Wann kommt Geld wirklich? Jeder Lauf nimmt nur mit, was bis zu seinem
    # Stichtag verdient ist, und erst ab der Mindestsumme. Bis 08.10.2026
    # versprach das Portal den nächsten Lauf für ALLES Offene — auch für eine
    # Provision vom 08.10., die erst am 15.01. kommt.
    erwartet, kandidat = None, lauf
    for _ in range(8):
        grenze = stichtag(kandidat).isoformat()
        summe = sum(b["betrag"] for b in offen if str(b["datum"])[:10] <= grenze)
        if summe >= MINDEST_AUSZAHLUNG:
            erwartet = {"datum": kandidat.isoformat(), "betrag": summe}
            break
        kandidat = naechster_lauf(kandidat + dt.timedelta(days=1))
    # Erzeugt, aber noch nicht als überwiesen bestätigt: das Geld hängt schon
    # an einem Lauf (also nicht mehr in `offen`), ist aber noch nicht gezahlt.
    unterwegs = sum(int(z[0] or 0) for z in c.execute(
        "SELECT betrag FROM ambassador_auszahlung WHERE code=? AND status='erstellt'",
        (code,)))
    return {
        "erwartet": erwartet,
        "unterwegs": unterwegs,
        "verdient": verdient, "ausgezahlt": gezahlt, "offen": verdient - gezahlt,
        "naechster_lauf": {"datum": lauf.isoformat(), "stichtag": bis,
                           "betrag": betrag,
                           "wird_ausgezahlt": betrag >= MINDEST_AUSZAHLUNG,
                           "hinweis": hinweis, "posten": posten},
        "danach": sum(b["betrag"] for b in offen) - betrag,
        # Für die Verwaltung: was der Lauf, der schon da ist, auszahlen würde
        # (derselbe Stichtag wie in api_ambassador_gezahlt).
        "faelliger_lauf": _faellig(offen, heute),
        "bewegungen": _bewegungen(code, c),
        "auszahlungen": [dict(zip(("datum", "betrag", "stichtag"), a))
                         for a in c.execute(
                             "SELECT datum, betrag, stichtag FROM ambassador_auszahlung "
                             "WHERE code=? AND (status IS NULL OR status='ueberwiesen') "
                             "ORDER BY datum DESC, id DESC", (code,))],
    }



# ---------------------------------------------------------------------------
# Begleiter (seit 03.10.2026): babu sagt der Ambassadorin, was heute zu tun
# ist, und schreibt die WhatsApp vor. Regeln in begleiter.py.
# ---------------------------------------------------------------------------

_KONTAKT_SPALTEN = ("id", "salon", "email", "slug", "erstellt", "eingeloest",
                    "person", "telefon", "erinnert_am", "erinnerungen",
                    "erinnert_art", "weiter_am", "gesendet")


def aktivitaet_aus_index(idx: dict) -> tuple[int, dt.date | None]:
    """Wie viele Belege, und an welchem Tag kam der letzte?"""
    zeiten = [str(z.get("hochgeladen"))[:10] for z in (idx.get("belege") or {}).values()
              if z.get("hochgeladen")]
    letzter = dt.date.fromisoformat(max(zeiten)) if zeiten else None
    return len(idx.get("belege") or {}), letzter


def _aktivitaet(email: str) -> tuple[int, dt.date | None]:
    """Belege in der Ablage dieses Salons — gelesen in einem eigenen Kontext,
    damit die aktive Ablage dieser Anfrage unberührt bleibt. Ohne Ablage
    (noch nicht angelegt) oder bei einem Fehler: nichts."""
    import box as bx  # noqa: PLC0415
    try:
        with bw._DB_LOCK, bw._db() as c:
            direkt = testmonat.direkt_mandant_von(email, c)
        if direkt is None:
            return 0, None
        ablage = bx.box_von(email, direkt[0])
        idx = contextvars.copy_context().run(bw._im_box_kontext, ablage,  # noqa: SLF001
                                             bw.index_aktuell)
        return aktivitaet_aus_index(idx)
    except Exception as ex:  # noqa: BLE001
        print(f"[begleiter] Aktivität {email}: {ex!r}", flush=True)
        return 0, None


def _kontakt_zeilen(code: str, c) -> dict:
    """Alles aus der Datenbank, was der Begleiter braucht — in EINER Sitzung."""
    einl = [dict(zip(_KONTAKT_SPALTEN, z)) for z in c.execute(
        f"SELECT {', '.join(_KONTAKT_SPALTEN)} FROM ambassador_einladung "
        "WHERE code=? ORDER BY erstellt DESC, id DESC", (code,))]
    salons = {z[0]: dict(zip(("email", "salon", "eingelöst", "meilenstein",
                              "gezeichnet_am"), z))
              for z in c.execute("SELECT email, salon, eingelöst, meilenstein, "
                                 "gezeichnet_am FROM ambassador_salon WHERE code=?",
                                 (code,))}
    tests, abos = {}, {}
    for email in salons:
        direkt = testmonat.direkt_mandant_von(email, c)
        tests[email] = direkt[1] if direkt else None
        if direkt:
            z = c.execute("SELECT abo_status FROM mandant WHERE id=?", (direkt[0],)).fetchone()
            abos[email] = z[0] if z else None
    return {"einladungen": einl, "salons": salons, "tests": tests, "abos": abos}


def _begleiter(code: str, ambassadorin: str, roh: dict,
               aktiv: bool = True) -> tuple[list, list]:
    """Die Kontaktliste und „Heute für dich" — eine Zeile je Einladung, dazu
    eingelöste Salons ohne gespeicherte Einladung (ohne Nummer, ohne Knopf)."""
    heute = _heute()
    salons = roh["salons"]
    gesehen: set[str] = set()
    zeilen = []
    for e in roh["einladungen"]:
        email = e["email"] if e["email"] in salons else None
        if email:
            gesehen.add(email)
        elif e["eingeloest"]:
            continue                      # eingelöst, aber nicht über diesen Code
        if not e["telefon"] and not e["email"] and not email:
            continue                      # alter Link ohne Nummer und ohne Mail: Cockpit zeigt ihn
        zeilen.append((e, salons.get(email) if email else None))
    for email, s in salons.items():
        if email not in gesehen:
            zeilen.append((None, s))

    kontakte, auftraege = [], []
    for e, s in zeilen:
        email = s["email"] if s else None
        test_bis = roh["tests"].get(email) if email else None
        st = testmonat.stand(test_bis, heute) if test_bis else None
        belege, letzter = _aktivitaet(email) if email else (0, None)
        k = {"telefon": e["telefon"] if e else None,
             "eingeladen_am": _datum(e["erstellt"]) if e else _datum(s["eingelöst"]),
             "eingeloest_am": _datum(s["eingelöst"]) if s else None,
             "test": st, "meilenstein": s["meilenstein"] if s else None,
             "abo": (roh.get("abos") or {}).get(email) if email else None,
             "gezeichnet_am": _datum(s.get("gezeichnet_am")) if s else None,
             "belege": belege, "letzter_beleg": letzter,
             "erinnert_am": _datum(e["erinnert_am"]) if e else None,
             "erinnerungen": (e["erinnerungen"] or 0) if e else 0,
             "erinnert_art": e["erinnert_art"] if e else None,
             "weiter_am": _datum(e["weiter_am"]) if e else None}
        person = (e["person"] if e else None) or (s["salon"] if s else None) or "Salon"
        satz, ton = begleiter.aktiv_satz(s is not None, belege, letzter, heute)
        stand = _stand_wort(k, st)
        # Ein Salon, der babu schon nutzt, „startet" nicht — er bestätigt die
        # Verbindung (seit 08.10.2026; vorher hieß er „noch nicht gestartet").
        if e and s is None and e["email"] and bw.nutzer_holen(e["email"]) is not None:
            stand, satz, ton = ("wartet auf Bestätigung",
                                "Nutzt babu schon — muss die Verbindung bestätigen", "neutral")
        zeile = {"nr": e["id"] if e else None, "name": person,
                 "salon": (s["salon"] if s else None) or (e["salon"] if e else None),
                 "telefon": begleiter.anzeige(e["telefon"]) if e and e["telefon"] else None,
                 "stand": stand, "aktiv": satz, "ton": ton,
                 "gesendet_am": e["erinnert_am"][:10] if e and e["erinnert_am"]
                 and (heute - _datum(e["erinnert_am"])).days < begleiter.ABSTAND_TAGE
                 else None,
                 "aufgabe": None}
        if e and not e["telefon"] and e["email"] and s is None and aktiv:
            # Per Mail eingeladen (seit 03.10.2026): kein WhatsApp-Auftrag, aber
            # nach drei Tagen ohne Start ein Knopf „Nochmal per Mail“.
            weg = e["gesendet"] or e["erstellt"]
            if weg and (heute - _datum(weg)).days < begleiter.ABSTAND_TAGE:
                zeile["gesendet_am"] = weg[:10]
            else:
                zeile["mail_nr"] = e["id"]
        # Abgeschalteter Code: keine Erinnerung an noch nicht eingelöste
        # Einladungen — ihr Link führt ins Leere. Hilfe für Salons im Test bleibt.
        a = begleiter.aufgabe(k, heute) if (e is None or e["telefon"]) and (aktiv or s) else None
        if a and e:
            text = begleiter.nachricht(
                a["art"], person=person, ambassadorin=ambassadorin,
                link=_link(code, e["slug"]),
                tage=st["tage_uebrig"] if st else None,
                weiter=_weiter_link() if abo.an() else None)
            a.update(nr=e["id"], person=person, salon=zeile["salon"],
                     telefon=zeile["telefon"], nachricht=text,
                     whatsapp=begleiter.whatsapp(e["telefon"], text))
            zeile["aufgabe"] = a
            auftraege.append(a)
        kontakte.append(zeile)
    rang = {art: i for i, art in enumerate(begleiter.ARTEN)}
    auftraege.sort(key=lambda a: rang[a["art"]])
    return kontakte, auftraege


def _stand_wort(k: dict, st: dict | None) -> str:
    m = k["meilenstein"]
    abo_stand = k.get("abo")
    if abo_stand == "zahlung_offen":
        return "Zahlung offen"        # sie kann beim Nachholen helfen
    if abo_stand in ("gekuendigt", "beendet"):
        return "Abo beendet" if abo_stand == "beendet" else "gekündigt"
    if m in ("gezeichnet", "gehalten"):
        return "macht mit"
    if abo_stand in ("zahlung_laeuft", "aktiv"):
        return "hat abgeschlossen"    # erste Lastschrift läuft noch
    if k.get("weiter_am"):
        return "will weitermachen"
    if k["eingeloest_am"] is None:
        return "noch nicht gestartet"
    if st is None:
        return "wartet auf Zugang"   # alter Wartelisten-Weg, noch kein Zugang
    if st["vorbei"]:
        return "Test vorbei"
    return "probiert aus"


async def _eigene_einladung(request: Request):
    """Gemeinsamer Anfang der Begleiter-Routen: angemeldet, Ambassadorin,
    und die genannte Einladung gehört ihr. Gibt (un, code, name, zeile, koerper)."""
    un, fehler = bw._api_wache(request)
    if fehler:
        return None, fehler
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 4 * 1024))
    except Exception:  # noqa: BLE001
        return None, JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    nr = koerper.get("nr")
    if not isinstance(nr, int) or isinstance(nr, bool):
        return None, JSONResponse({"fehler": "nr fehlt"}, status_code=400)
    with bw._DB_LOCK, bw._db() as c:
        a = c.execute("SELECT code, name FROM ambassador WHERE email=? AND aktiv=1",
                      (un,)).fetchone()
        z = c.execute(f"SELECT {', '.join(_KONTAKT_SPALTEN)} FROM ambassador_einladung "
                      "WHERE id=? AND code=?", (nr, a[0] if a else "")).fetchone()
    if not a or not z:
        return None, JSONResponse({"fehler": "Diese Einladung gibt es hier nicht."},
                                  status_code=404)
    return (un, a[0], a[1], dict(zip(_KONTAKT_SPALTEN, z)), koerper), None


async def api_ambassador_erinnert(request: Request) -> Response:
    """Sie hat die vorgeschlagene Nachricht verschickt — merken (für die
    Grenze „alle drei Tage" und „höchstens drei je Lage")."""
    werte, fehler = await _eigene_einladung(request)
    if fehler:
        return fehler
    un, code, _name, z, koerper = werte
    art = str(koerper.get("art", "") or "")
    if art not in begleiter.ARTEN:
        return JSONResponse({"fehler": "unbekannte Art"}, status_code=400)
    anzahl = begleiter.zaehlen(z["erinnert_art"], z["erinnerungen"] or 0, art)
    with bw._DB_LOCK, bw._db() as c:
        c.execute("UPDATE ambassador_einladung SET erinnert_am=?, erinnerungen=?, "
                  "erinnert_art=? WHERE id=?",
                  (_heute().isoformat(), anzahl, art, z["id"]))
    audit.audit(un, "begleiter_erinnert", code=code, nr=str(z["id"]), art=art)
    return JSONResponse({"ok": True, "erinnerungen": anzahl})


def _weiter_link() -> str:
    """Wo der Salon selbst abschließt (Seite „Weitermachen", seit 03.10.2026)."""
    return f"{bw.PORTAL_ORIGIN.rstrip('/')}/portal#abo"


async def api_ambassador_weitermachen(request: Request) -> Response:
    """Der Salon will weitermachen — Nina bekommt Bescheid und bucht ihn als
    gezeichnet; bis dahin schlägt babu für ihn nichts mehr vor."""
    werte, fehler = await _eigene_einladung(request)
    if fehler:
        return fehler
    un, code, name, z, _koerper = werte
    with bw._DB_LOCK, bw._db() as c:
        c.execute("UPDATE ambassador_einladung SET weiter_am=? WHERE id=?",
                  (_heute().isoformat(), z["id"]))
    wer = z["person"] or z["salon"] or "Ein Salon"
    selbst = abo.an() and bool(z["email"])
    if selbst:
        # Seit 03.10.2026 schließt der Salon selbst ab — er bekommt den Weg
        # per Mail; die Provision bucht sich mit der ersten Zahlung.
        await bw.run_in_threadpool(
            _senden, z["email"], "So machst du mit babu weiter",
            f"Hallo {z['person'] or ''},\n\n{name} hat uns gesagt, dass du mit babu "
            "weitermachen willst — schön!\n\nHier wählst du dein Paket und "
            f"schließt in zwei Minuten ab:\n{_weiter_link()}\n\nAlles, was du im "
            "Testmonat erfasst hast, bleibt da.\n\nLiebe Grüße\nbabu\n")
    if bw.SUPPORT_MAIL:
        await bw.run_in_threadpool(
            _senden, bw.SUPPORT_MAIL, f"Will weitermachen: {wer}",
            f"Hallo,\n\n{wer}"
            + (f" ({z['salon']})" if z["salon"] and z["salon"] != wer else "")
            + f" will bei babu weitermachen. Gemeldet von {name} (Code {code})"
            + (f", Telefon {begleiter.anzeige(z['telefon'])}" if z["telefon"] else "")
            + (".\n\nDer Salon hat den Link zum Abschließen per Mail bekommen; die "
               "Provision bucht sich mit der ersten Zahlung.\n" if selbst else
               ".\n\nBitte in der Verwaltung als gezeichnet buchen.\n"))
    audit.audit(un, "begleiter_weitermachen", code=code, nr=str(z["id"]))
    return JSONResponse({"ok": True})


_ROUTEN = [
    ("POST", "/api/ambassador", api_ambassador_anlegen),
    ("GET", "/api/ambassador/liste", api_ambassador_liste),
    ("GET", "/api/ambassador/me", api_ambassador_me),
    ("POST", "/api/ambassador/link", api_ambassador_link),
    ("POST", "/api/ambassador/einladen", api_ambassador_einladen),
    ("GET", "/ambassador/{code}/{slug}", ambassador_landing),
    ("GET", "/verbinden/{token}", verbinden_seite),
    ("GET", "/testen", testen_seite),
    ("POST", "/api/testmonat/starten", api_testmonat_starten),
    ("POST", "/api/ambassador/verbinden", api_ambassador_verbinden),
    ("POST", "/api/ambassador/meilenstein", api_ambassador_meilenstein),
    ("POST", "/api/ambassador/aktiv", api_ambassador_aktiv),
    ("POST", "/api/ambassador/einloesen", api_ambassador_einloesen),
    ("POST", "/api/ambassador/verlaengern", api_ambassador_verlaengern),
    ("POST", "/api/ambassador/erinnert", api_ambassador_erinnert),
    ("POST", "/api/ambassador/weitermachen", api_ambassador_weitermachen),
    ("POST", "/api/ambassador/heute-mail", api_ambassador_heute_mail),
    ("POST", "/api/ambassador/gezahlt", api_ambassador_gezahlt),
]
