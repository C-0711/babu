"""Warteliste, Signup, Registrierungen — die Verwaltungs-Familie (Schritt 1).

Aus babu_web.py ausgeschnitten am 21.09.2026 (Refactor-Plan,
docs/refactor-babu-web-plan.md, Schritt 1). REINER MOVE: kein Verhalten
geändert, jeder Name, jede Route, jeder Test bleibt wie er war.

Die Routen hängen an demselben `app`-Objekt wie alle anderen: dieses Modul
importiert `babu_web` (der Kern) und registriert seine Routen DORT. Die
Kern-Datei zieht sich dieses Modul am Datei-Ende herein — dadurch bleiben
`TestClient(babu_web.app)` und alle `bw.<name>`-Zugriffe aus den Tests
unangetastet.
"""
import json
import os
import time

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

import audit
import babu_web as bw


# ── Registrierung / Signup ───────────────────────────────────────────────────
# Eine Rechnung ohne Anschrift nach § 14 UStG keine ist — wer das erst beim
# Rechnungschreiben merkt, sitzt im falschen Moment vor einem leeren Feld.
REG_FELDER = ("salon", "name", "email", "telefon", "anschrift", "rechtsform",
              "steuernummer", "finanzamt", "kleinunternehmer", "iban",
              "steuerberater", "nachricht")
_REG_ZULETZT: dict[str, float] = {}


@bw.app.post("/api/registrierung")
def api_registrierung(daten: dict, request: Request) -> Response:
    if not bw._origin_ok(request):
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    ip = bw._client_ip(request)
    jetzt = time.time()
    if jetzt - _REG_ZULETZT.get(ip, 0.0) < 30:
        return JSONResponse({"fehler": "kurz warten, dann nochmal"}, status_code=429)
    sauber = {k: str(daten.get(k, "") or "")[:200].strip() for k in REG_FELDER}
    if not sauber["salon"] or "@" not in sauber["email"]:
        return JSONResponse({"fehler": "Salon-Name und E-Mail brauchen wir mindestens"},
                            status_code=400)
    _REG_ZULETZT[ip] = jetzt
    bw._zaehler_aufraeumen(_REG_ZULETZT, jetzt, 3600)
    with bw._DB_LOCK, bw._db() as c:
        c.execute("INSERT INTO registrierungen (zeit, daten) VALUES (?, ?)",
                  (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   json.dumps(sauber, ensure_ascii=False)))
    print(f"[registrierung] {sauber['salon']} <{sauber['email']}>", flush=True)
    return JSONResponse({"ok": True})


def signup_offen() -> bool:
    """Darf sich jemand selbst ein Konto anlegen?

    Im Pilot (ab 14.09.2026) nicht: Konten legt die Kanzlei im Portal an,
    Betriebe kommen auf Einladung. `BABU_SIGNUP=0` in der Compose-Datei
    schließt die Tür; ohne die Variable bleibt sie offen, damit die Tests
    und die lokale Vorschau wie bisher Konten anlegen können."""
    return os.environ.get("BABU_SIGNUP", "1") != "0"


@bw.app.get("/api/signup-offen")
def api_signup_offen() -> Response:
    """Sagt der Anmeldeseite, ob sie „Konto anlegen" zeigen soll — und ob
    „Passwort vergessen?" ein Formular sein darf: das ist es nur, wenn ein
    Mailversand eingerichtet ist. Sonst verspräche das Formular einen Link,
    der nur im Postausgang landet, und die Seite zeigt den alten Hinweis."""
    import postfach  # noqa: PLC0415
    return JSONResponse({"offen": signup_offen(),
                         "passwort_vergessen": postfach.eingerichtet()})


@bw.app.post("/api/signup")
def api_signup(daten: dict, request: Request) -> Response:
    """Ganz normales Self-Signup: Konto mit eigenem Passwort, sofort angemeldet.
    Steuerdaten aus der Strecke landen direkt in den Einstellungen; die
    Verwaltung sieht den Neuzugang in der Anfragen-Historie."""
    if not signup_offen():
        # 404, nicht 403: die Tür gibt es im Pilot nicht, sie ist nicht nur zu.
        return JSONResponse({"fehler": "nicht gefunden"}, status_code=404)
    if not bw._origin_ok(request):
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    ip = bw._client_ip(request)
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
    if bw.nutzer_anlegen(email, sauber["name"], sauber["salon"], "salon",
                         passwort=passwort, box=False) is None:
        return JSONResponse({"fehler": "Für diese E-Mail gibt es schon einen Zugang — melde dich einfach an."},
                            status_code=409)
    _REG_ZULETZT[ip] = jetzt
    bw._zaehler_aufraeumen(_REG_ZULETZT, jetzt, 3600)
    vorbelegung = {"betrieb_name": sauber["salon"], "rechtsform": sauber["rechtsform"],
                   "steuernummer": sauber["steuernummer"], "finanzamt": sauber["finanzamt"],
                   "kleinunternehmer": sauber["kleinunternehmer"],
                   "steuerberater_status": sauber["steuerberater"],
                   "telefon": sauber["telefon"], "email": email,
                   # Alles, was später auf der Rechnung stehen muss.
                   "anschrift": sauber["anschrift"], "iban": sauber["iban"]}
    for schluessel, wert in vorbelegung.items():
        if wert:
            bw.db_einstellung_setzen(email, schluessel, str(wert)[:200])
    with bw._DB_LOCK, bw._db() as c:
        c.execute("INSERT INTO registrierungen (zeit, daten, status) VALUES (?, ?, 'selbst registriert')",
                  (bw._jetzt_iso(), json.dumps(sauber, ensure_ascii=False)))
    print(f"[signup] {sauber['salon']} <{email}>", flush=True)
    exp = int(time.time()) + bw.SESSION_DAUER
    antwort = JSONResponse({"un": email, "rolle": "salon",
                            "box": bw.box_mitglied(email)})
    antwort.set_cookie(bw.SESSION_COOKIE, bw._signieren(email, exp), max_age=bw.SESSION_DAUER,
                       httponly=True, secure=bw.SESSION_SECURE, samesite="lax", path="/")
    return antwort


@bw.app.get("/api/registrierungen")
def api_registrierungen(request: Request) -> Response:
    un, fehler = bw._api_wache(request)
    if fehler:
        return fehler
    if not bw.darf_verwalten(un):
        return JSONResponse({"fehler": "nur für die Kanzlei"}, status_code=403)
    with bw._DB_LOCK, bw._db() as c:
        zeilen = [{"id": z[0], "zeit": z[1], "status": z[3], **json.loads(z[2])}
                  for z in c.execute(
                      "SELECT id, zeit, daten, status FROM registrierungen ORDER BY id DESC")]
    return JSONResponse({"registrierungen": zeilen})


# ── Warteliste ──────────────────────────────────────────────────────────────
# Seit 16.09.2026: Zugang nur auf Einladung. Wer sich anmelden möchte — Salon
# oder Kanzlei —, hinterlässt E-Mail und Art; die Verwaltung entscheidet und
# richtet den Zugang mit Startpasswort ein. Derselbe Handgriff wie bei den
# „Anfragen" aus der Startseiten-Strecke, nur dass hier nichts außer der
# Adresse anfällt (kein Passwort, keine Unterlagen, kein Konto).

_WARTELISTE_FELDER = ("email", "art", "name", "salon", "telefon", "bemerkung")
_WARTELISTE_ARTEN = ("salon", "kanzlei")
_APP_STATUS = ("fehlt", "eingetragen", "eingeladen", "drin")


@bw.app.post("/api/warteliste")
async def api_warteliste_anmelden(request: Request) -> Response:
    """Öffentlich: ein Eintrag auf die Warteliste — mehr nicht.

    Die Antwort ist bewusst immer freundlich und gleich, egal ob die Adresse
    schon wartet, schon ein Konto hat oder gebremst wird. Das Formular darf
    weder Melder für bestehende Konten sein (siehe einladung.py) noch eine
    Versandwerkzeug für fremde Postfächer — deshalb IP-Bremse und
    Wiederanmeldung = Zähler hoch, keine neue Zeile.
    """
    import einladung as ei  # noqa: PLC0415
    if not bw._origin_ok(request):
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    ip = bw._client_ip(request)
    jetzt = time.time()
    if jetzt - _REG_ZULETZT.get(ip, 0.0) < 30:
        return JSONResponse({"fehler": "kurz warten, dann nochmal"}, status_code=429)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 8 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON erwartet"}, status_code=400)
    sauber = {k: str(koerper.get(k, "") or "").strip()[:200]
              for k in _WARTELISTE_FELDER}
    email = sauber["email"].lower()
    if not ei.mail_gueltig(email):
        return JSONResponse({"fehler": "Diese E-Mail-Adresse sieht nicht "
                                       "richtig aus."}, status_code=400)
    art = sauber["art"] if sauber["art"] in _WARTELISTE_ARTEN else "salon"
    # Ambassador-Code erkennen (21.09.2026): steht „Code XXX“ in der
    # Bemerkung (so schickt ihn die Ambassador-Landing), wird die Zeile
    # der Ambassadorin zugeordnet — einmalig, eine Zeile bleibt einem
    # Code treu, auch wenn die Person sich mehrfach meldet.
    import re as _re  # noqa: PLC0415
    code_fund = _re.search(r"[Cc]ode\s+([A-Za-z0-9-]{4,60})",
                           sauber["bemerkung"])
    with bw._DB_LOCK, bw._db() as c:
        vorhanden = c.execute("SELECT anfragen FROM warteliste WHERE email=?",
                              (email,)).fetchone()
        if vorhanden:
            # Dieselbe Adresse meldet sich nochmal — Wunsch ernst nehmen,
            # Zeile aber nicht vervielfachen.
            c.execute("""UPDATE warteliste SET art=?, name=?, salon=?, telefon=?,
                         bemerkung=?, anfragen=anfragen+1, zeit=?,
                         status='wartet' WHERE email=?""",
                      (art, sauber["name"], sauber["salon"], sauber["telefon"],
                       sauber["bemerkung"], bw._jetzt_iso(), email))
        else:
            c.execute("""INSERT INTO warteliste (email, art, name, salon, telefon,
                         bemerkung, zeit, herkunft_code) VALUES (?,?,?,?,?,?,?,?)""",
                      (email, art, sauber["name"], sauber["salon"],
                       sauber["telefon"], sauber["bemerkung"], bw._jetzt_iso(),
                       code_fund.group(1) if code_fund else None))
        if code_fund and not vorhanden:
            # Ambassador-Zuordnung: nur beim ERSTEN Eintrag (ein Salon
            # gehört einem Code, Zähler-Hochsetzen ändert sie nicht).
            c.execute("""INSERT OR IGNORE INTO ambassador_salon
                         (code, email, salon, eingelöst)
                         VALUES (?,?,?,?)""",
                      (code_fund.group(1), email, sauber["salon"] or "",
                       bw._jetzt_iso()))
    _REG_ZULETZT[ip] = jetzt
    bw._zaehler_aufraeumen(_REG_ZULETZT, jetzt, 3600)
    print(f"[warteliste] {art} <{email}>", flush=True)
    # Eine Kopie an Nina (BABU_SUPPORT_MAIL): sie entscheidet, wen wir
    # einladen — ohne diese Mail müsste jemand die Liste im Portal
    # zufällig finden. Wie bei der Rückmeldung: nur eine Kopie, ein
    # Fehlschlag ändert nichts an der Zusage an die Adresse (die Mail
    # liegt dann im Postausgang).
    if bw.SUPPORT_MAIL:
        import postfach  # noqa: PLC0415
        _art_name = "Steuerbüro / Kanzlei" if art == "kanzlei" else "Salon / Betrieb"
        _text = (f"Hallo,\n\n"
                 f"jemand möchte einen Zugang zu babu:\n\n"
                 f"    {_art_name}\n"
                 f"    {email}\n"
                 + (f"    Name: {sauber['name']}\n" if sauber["name"] else "")
                 + (f"    Betrieb: {sauber['salon']}\n" if sauber["salon"] else "")
                 + (f"    Telefon: {sauber['telefon']}\n" if sauber["telefon"] else "")
                 + (f"    Bemerkung: {sauber['bemerkung']}\n" if sauber["bemerkung"] else "")
                 + (f"\n(Diese Adresse hat sich schon einmal gemeldet.)\n"
                    if vorhanden else "")
                 + f"\nEinladen: Portal → Verwaltung → Warteliste → „Zugang einladen“.\n")
        try:
            ok, hinweis = await run_in_threadpool(
                postfach.senden, bw.SUPPORT_MAIL,
                f"Warteliste: {_art_name} — {email}", _text,
                stempel=time.strftime("%Y%m%d-%H%M%S"))
            print(f"[warteliste] Mail an {bw.SUPPORT_MAIL}: {hinweis}", flush=True)
        except Exception as ex:  # noqa: BLE001
            print(f"[warteliste] Mail an {bw.SUPPORT_MAIL} fehlgeschlagen: {ex!r}",
                  flush=True)
    return JSONResponse({"ok": True, "hinweis":
        "Danke! Wir melden uns an diese Adresse, sobald ein Platz frei ist."})


@bw.app.get("/api/warteliste")
def api_warteliste_lesen(request: Request) -> Response:
    un, fehler = bw._verwalter_wache(request)
    if fehler:
        return fehler
    with bw._DB_LOCK, bw._db() as c:
        zeilen = [dict(zip(("email", "art", "name", "salon", "telefon",
                            "bemerkung", "anfragen", "zeit", "status",
                            "apple_id", "app_status"), z))
                  for z in c.execute(
                      "SELECT email, art, name, salon, telefon, bemerkung, "
                      "anfragen, zeit, status, apple_id, "
                      "COALESCE(app_status, CASE WHEN apple_id IS NULL "
                      "THEN 'fehlt' ELSE 'eingetragen' END) "
                      "FROM warteliste "
                      "ORDER BY status='wartet' DESC, zeit DESC")]
    return JSONResponse({"warteliste": zeilen})


@bw.app.post("/api/warteliste/einrichten")
async def api_warteliste_einrichten(request: Request) -> Response:
    """Verwaltung: aus einem Wartelisten-Eintrag wird ein Zugang.

    Salon → Betriebskonto mit Belegbox (der Box-Anleger richtet sie nach,
    wie bei jedem Mandanten). Kanzlei → Konto mit Rolle „kanzlei"; Kanzlei
    und Mandanten legt die Inhaberin danach im Portal an.
    """
    un, fehler = bw._verwalter_wache(request)
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"}, status_code=401)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 8 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit email erwartet"}, status_code=400)
    email = str(koerper.get("email", "") or "").strip().lower()[:200]
    rolle_neu = "kanzlei" if koerper.get("art") == "kanzlei" else "salon"
    with bw._DB_LOCK, bw._db() as c:
        z = c.execute("SELECT art, name, salon, telefon FROM warteliste "
                      "WHERE email=?", (email,)).fetchone()
    if not z:
        return JSONResponse({"fehler": "Diese Adresse steht nicht auf der "
                                       "Warteliste."}, status_code=404)
    art, name, salon, telefon = z
    betrieb = salon or name or (email.split("@")[0])
    passwort = bw.nutzer_anlegen(email, name or "", betrieb, rolle_neu)
    if passwort is None:
        return JSONResponse({"fehler": "Für diese E-Mail gibt es schon einen "
                                       "Zugang."}, status_code=409)
    for schluessel, wert in (("betrieb_name", betrieb), ("telefon", telefon),
                             ("email", email)):
        if wert:
            bw.db_einstellung_setzen(email, schluessel, str(wert)[:200])
    with bw._DB_LOCK, bw._db() as c:
        c.execute("UPDATE warteliste SET status='eingerichtet' WHERE email=?",
                  (email,))
    audit.audit(un, "warteliste_einrichten", ziel_un=email)
    print(f"[warteliste] eingerichtet: {art} <{email}>", flush=True)
    return JSONResponse({"ok": True, "email": email, "startpasswort": passwort})


@bw.app.post("/api/warteliste/apple-id")
async def api_warteliste_apple_id(request: Request) -> Response:
    """Verwaltung: die Apple-ID-Adresse zu einem Wartelisten-Eintrag.

    Die App-Einladung läuft über TestFlight, und die geht an die Apple-ID —
    nicht an die babu-Adresse (startguide.testflight_absatz erklärt das dem
    Salon). Die Verwaltung klebt die Adresse hier ein, sobald sie die Antwort
    hat; der Abgleich-Dienst auf der H200V (Host-Cron, testflight_abgleich)
    trägt sie von selbst bei Apple ein und setzt app_status weiter
    (eingetragen → eingeladen → drin).
    """
    import einladung as ei  # noqa: PLC0415
    un, fehler = bw._verwalter_wache(request)
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"}, status_code=401)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 8 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit email erwartet"}, status_code=400)
    email = str(koerper.get("email", "") or "").strip().lower()[:200]
    apple = str(koerper.get("apple_id", "") or "").strip().lower()[:200]
    if not apple or not ei.mail_gueltig(apple):
        return JSONResponse({"fehler": "Das sieht nicht nach einer E-Mail-"
                                       "Adresse aus."}, status_code=400)
    with bw._DB_LOCK, bw._db() as c:
        n = c.execute("""UPDATE warteliste SET apple_id=?, app_status='eingetragen'
                         WHERE email=?""", (apple, email)).rowcount
    if not n:
        return JSONResponse({"fehler": "Diese Adresse steht nicht auf der "
                                       "Warteliste."}, status_code=404)
    audit.audit(un, "warteliste_apple_id", ziel_un=email, apple_id=apple)
    print(f"[warteliste] Apple-ID für {email}: {apple}", flush=True)
    return JSONResponse({"ok": True, "apple_id": apple, "app_status": "eingetragen"})


@bw.app.post("/api/warteliste/ablehnen")
async def api_warteliste_ablehnen(request: Request) -> Response:
    """Verwaltung: höflich Nein — der Eintrag bleibt mit Stand „abgelehnt“."""
    un, fehler = bw._verwalter_wache(request)
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"}, status_code=401)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 8 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit email erwartet"}, status_code=400)
    email = str(koerper.get("email", "") or "").strip().lower()[:200]
    with bw._DB_LOCK, bw._db() as c:
        n = c.execute("UPDATE warteliste SET status='abgelehnt' WHERE email=?",
                      (email,)).rowcount
    if not n:
        return JSONResponse({"fehler": "Diese Adresse steht nicht auf der "
                                       "Warteliste."}, status_code=404)
    audit.audit(un, "warteliste_ablehnen", ziel_un=email)
    return JSONResponse({"ok": True})
