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
import calendar
import datetime as dt
import json
import os
import re
import secrets
import time

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

import audit
import mandanten
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
            z["salons"] = [dict(zip(_SALON_SPALTEN, s))
                           for s in c.execute(
                               f"SELECT {', '.join(_SALON_SPALTEN)} FROM "
                               "ambassador_salon WHERE code=? ORDER BY eingelöst DESC",
                               (z["code"],))]
            _testmonate_dazu(z["salons"], c)
            _pipeline_dazu(z["salons"], z["code"], c)
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
        a = c.execute("SELECT code, name, verdient, gezahlt FROM ambassador "
                      "WHERE email=? AND aktiv=1", (un,)).fetchone()
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
    return JSONResponse({"code": a[0], "name": a[1],
                         "verdient": a[2], "gezahlt": a[3], "offen": a[2] - a[3],
                         "salons": salons, "zahlen": _zahlen(salons),
                         "einladungen": einladungen, "geld": geld})


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
    salon = str(koerper.get("salon", "") or "").strip()[:120]
    email = str(koerper.get("email", "") or "").strip().lower()[:200] or None
    slug = re.sub(r"[^a-z0-9]+", "-", salon.lower()).strip("-")[:24] or "salon"
    # Jeder Link ist eine Einladung (seit 02.10.2026): wer ihn noch nicht
    # eingelöst hat, steht als potenzieller Kunde in ihrem Bereich.
    with bw._DB_LOCK, bw._db() as c:
        cur = c.execute("""INSERT INTO ambassador_einladung
                           (code, salon, email, slug, erstellt) VALUES (?,?,?,?,?)""",
                        (a[0], salon or None, email, slug, bw._jetzt_iso()))
        nr = cur.lastrowid
    return JSONResponse({"link": _link(a[0], slug), "id": nr})


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
30 Tage babu komplett, ohne Vertrag, ohne Kündigung.</p>
<form onsubmit="return einlosen(this)">
<input name="salon" placeholder="Name deines Salons" required>
<input name="email" type="email" placeholder="Deine E-Mail" required>
<button class="knopf">Platz sichern</button></form>
<p id="ok" style="display:none;color:#55705a;font-weight:600"></p></div>
<script>
function einlosen(f){{
  fetch({json.dumps(ziel)}, {{method:"POST",
    headers:{{"Content-Type":"application/json"}},
    body: JSON.stringify({{email:f.email.value, art:"salon", code:{json.dumps(code)}, slug:{json.dumps(slug)},
      salon:f.salon.value, bemerkung:"Code " + {json.dumps(code)}}})}})
  .then(r => r.json()).then(d => {{
    if(d.ok){{ document.getElementById("ok").textContent = {json.dumps(danke)};
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
    nr = koerper.get("id")
    with bw._DB_LOCK, bw._db() as c:
        a = c.execute("SELECT name, code FROM ambassador WHERE email=? AND aktiv=1",
                      (un,)).fetchone()
        gemerkt = None
        if a and isinstance(nr, int) and not isinstance(nr, bool):
            # „Nochmal schicken": nur eine eigene, noch offene Einladung.
            gemerkt = c.execute(
                "SELECT id, salon, email, slug FROM ambassador_einladung "
                "WHERE id=? AND code=? AND eingeloest IS NULL", (nr, a[1])).fetchone()
            if not gemerkt:
                return JSONResponse({"fehler": "Diese Einladung gibt es nicht (mehr)."},
                                    status_code=404)
    if gemerkt:
        salon, email, link = gemerkt[1] or "", gemerkt[2] or "", _link(a[1], gemerkt[3])
    if "@" not in email or not link:
        return JSONResponse({"fehler": "email und link brauchen wir."}, status_code=400)
    import einladung as ei  # noqa: PLC0415
    if not ei.mail_gueltig(email):
        return JSONResponse({"fehler": "Das sieht nicht nach einer E-Mail-Adresse aus."},
                            status_code=400)
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
    _einladung_gesendet(a[1], gemerkt[0] if gemerkt else None, link, salon, email)
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
        # Mit Datum gebucht (seit 02.10.2026): daran hängt, in welchem
        # Auszahlungslauf die Provision kommt.
        heute = _heute().isoformat()
        c.execute(f"UPDATE ambassador_salon SET {bis}_am=? WHERE code=? AND email=?",
                  (heute, code, email))
        salon_name = c.execute("SELECT salon FROM ambassador_salon WHERE code=? "
                               "AND email=?", (code, email)).fetchone()
        c.execute("""INSERT INTO ambassador_buchung
                     (code, email, salon, meilenstein, betrag, datum)
                     VALUES (?,?,?,?,?,?)""",
                  (code, email, salon_name[0] if salon_name else None, bis,
                   betrag, heute))
        if bis == "gezeichnet":
            # Wer abzeichnet, ist Kunde: der Testmonat endet, alles ist offen.
            direkt = testmonat.direkt_mandant_von(email, c)
            if direkt is not None:
                testmonat.setzen(direkt[0], None, c)
    audit.audit(un, "ambassador_meilenstein", ziel_un=email,
                code=code, meilenstein=meilenstein, betrag=betrag)
    return JSONResponse({"ok": True, "meilenstein": bis, "verdienst": betrag})


async def api_ambassador_gezahlt(request: Request) -> Response:
    """Verwaltung: der Auszahlungslauf (seit 02.10.2026).

    Zahlt aus, was bis zum Stichtag des letzten fälligen Laufs verdient und
    noch offen ist — quartalsweise zum 15. nach Quartalsende, ab 100 €.
    Was danach verdient wurde, kommt mit dem nächsten Lauf."""
    un, fehler = bw._verwalter_wache(request)
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"}, status_code=401)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 4 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit code erwartet"}, status_code=400)
    code = str(koerper.get("code", "") or "").strip()[:60]
    heute = _heute()
    lauf = letzter_lauf(heute)
    bis = stichtag(lauf)
    with bw._DB_LOCK, bw._db() as c:
        z = c.execute("SELECT verdient, gezahlt FROM ambassador WHERE code=?",
                      (code,)).fetchone()
        if not z:
            return JSONResponse({"fehler": "Code unbekannt."}, status_code=404)
        faellig = c.execute(
            "SELECT id, betrag FROM ambassador_buchung WHERE code=? AND "
            "auszahlung_id IS NULL AND datum <= ?", (code, bis.isoformat())).fetchall()
        summe = sum(b for _, b in faellig)
        if summe <= 0:
            return JSONResponse({"fehler": f"Für den Lauf vom {_de(lauf)} ist nichts "
                                           f"fällig (Stichtag {_de(bis)})."},
                                status_code=409)
        if summe < MINDEST_AUSZAHLUNG:
            return JSONResponse({"fehler": f"{summe} € liegt unter "
                                           f"{MINDEST_AUSZAHLUNG} € — das wandert ins "
                                           f"nächste Quartal."}, status_code=409)
        cur = c.execute("""INSERT INTO ambassador_auszahlung
                           (code, betrag, datum, stichtag, von) VALUES (?,?,?,?,?)""",
                        (code, summe, heute.isoformat(), bis.isoformat(), un))
        nr = cur.lastrowid
        for bid, _ in faellig:
            c.execute("UPDATE ambassador_buchung SET auszahlung_id=? WHERE id=?",
                      (nr, bid))
        c.execute("UPDATE ambassador SET gezahlt = gezahlt + ? WHERE code=?",
                  (summe, code))
    audit.audit(un, "ambassador_gezahlt", code=code, betrag=summe,
                stichtag=bis.isoformat())
    return JSONResponse({"ok": True, "gezahlt": summe, "stichtag": bis.isoformat(),
                         "lauf": lauf.isoformat()})



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
    """Wie die App aufs Telefon kommt: über den öffentlichen TestFlight-Link,
    sobald es ihn gibt — sonst wie bisher per Apple-ID-Antwort."""
    import startguide  # noqa: PLC0415
    link = os.environ.get("BABU_TESTFLIGHT_LINK", "").strip()
    if not link:
        return startguide.testflight_absatz()
    return ("Die babu-App aufs iPhone: diesen Link auf dem Telefon öffnen —\n\n"
            f"    {link}\n\n"
            "Er führt zu TestFlight, Apples offiziellem Weg für Test-Apps. Einmal\n"
            "„Testen“ antippen, dann installiert sich babu wie jede andere App.\n"
            "In der App meldest du dich mit dieser E-Mail-Adresse an.\n")


def _senden(an: str, betreff: str, text: str) -> None:
    import postfach  # noqa: PLC0415
    try:
        ok, hinweis = postfach.senden(an, betreff, text,
                                      stempel=time.strftime("%Y%m%d-%H%M%S"))
        print(f"[testmonat] Mail an {an}: {hinweis}", flush=True)
    except Exception as ex:  # noqa: BLE001
        print(f"[testmonat] Mail an {an} fehlgeschlagen: {ex!r}", flush=True)


_EINGELOEST = ("Geschafft! Schau in dein Postfach — dort liegt der Link, mit "
               "dem du dein Passwort setzt.")


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
        await bw.run_in_threadpool(
            _senden, email, "Du hast schon einen Zugang zu babu",
            "Hallo,\n\njemand hat mit dieser Adresse einen babu-Testmonat "
            "angefragt. Für diese Adresse gibt es schon einen Zugang — melde "
            f"dich einfach an: {bw.PORTAL_ORIGIN.rstrip('/')}/portal\n\n"
            "Passwort vergessen? Auf der Anmeldeseite gibt es dafür einen "
            "Link.\n\nWenn du das nicht warst, ignoriere diese Nachricht.\n")
        return JSONResponse({"ok": True, "hinweis": _EINGELOEST})

    heute = testmonat.heute()
    tag = heute.isoformat()
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
    link = _passwort_link(email)
    text = (f"Hallo,\n\n"
            f"schön, dass du babu ausprobierst — empfohlen von {ambassadorin}. "
            f"Dein Zugang für „{salon}“ steht. Du hast {testmonat.TAGE} Tage "
            f"babu komplett, bis einschließlich {bis.strftime('%d.%m.%Y')}; "
            f"kostenlos, ohne Vertrag, kündigen musst du nichts.\n\n"
            f"Beim ersten Öffnen legst du dein Passwort fest:\n\n"
            f"    {link or bw.PORTAL_ORIGIN.rstrip('/') + '/portal'}\n\n")
    import startguide  # noqa: PLC0415
    text += (startguide.schritte(bw.PORTAL_ORIGIN) + "\n" + _app_absatz()
             + "\nNach den 30 Tagen bleibt alles da und lesbar. Wenn du "
               "weitermachen willst, antworte einfach auf diese Mail.\n")
    await bw.run_in_threadpool(_senden, email,
                               "Dein babu-Testmonat startet", text)
    if bw.SUPPORT_MAIL:
        await bw.run_in_threadpool(
            _senden, bw.SUPPORT_MAIL, f"Testmonat gestartet: {salon}",
            f"Hallo,\n\nein Salon hat einen Ambassador-Code eingelöst:\n\n"
            f"    Salon: {salon}\n    E-Mail: {email}\n"
            f"    Empfohlen von: {ambassadorin} (Code {code})\n"
            f"    Testmonat bis: {bis.strftime('%d.%m.%Y')}\n\n"
            f"Die Ablage richtet sich von selbst ein. Gezeichnet oder "
            f"verlängern: Portal → Verwaltung → Ambassadorinnen.\n")
    audit.audit(f"code:{code}", "testmonat_eingeloest", ziel_un=email,
                mandant_id=str(mandant_id), bis=bis.isoformat())
    print(f"[testmonat] {salon} <{email}> über {code} bis {bis}", flush=True)
    return JSONResponse({"ok": True, "hinweis": _EINGELOEST})


async def api_ambassador_verlaengern(request: Request) -> Response:
    """Verwaltung: den Testmonat eines Direkt-Salons verlängern (1–60 Tage)."""
    un, fehler = bw._verwalter_wache(request)
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
    """Wer eingeladen ist, aber noch nicht eingelöst hat."""
    return [dict(zip(("id", "salon", "email", "erstellt", "gesendet"), z))
            for z in c.execute(
                "SELECT e.id, e.salon, e.email, e.erstellt, e.gesendet "
                "FROM ambassador_einladung e WHERE e.code=? AND e.eingeloest IS NULL "
                "AND NOT EXISTS (SELECT 1 FROM ambassador_salon s WHERE s.code=e.code "
                "AND s.email=e.email) ORDER BY e.erstellt DESC, e.id DESC", (code,))]


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
    return {
        "verdient": verdient, "ausgezahlt": gezahlt, "offen": verdient - gezahlt,
        "naechster_lauf": {"datum": lauf.isoformat(), "stichtag": bis,
                           "betrag": betrag,
                           "wird_ausgezahlt": betrag >= MINDEST_AUSZAHLUNG,
                           "hinweis": hinweis, "posten": posten},
        "danach": sum(b["betrag"] for b in offen) - betrag,
        # Für die Verwaltung: was der Lauf, der schon da ist, auszahlen würde
        # (derselbe Stichtag wie in api_ambassador_gezahlt).
        "faelliger_lauf": _faellig(offen, heute),
        "auszahlungen": [dict(zip(("datum", "betrag", "stichtag"), a))
                         for a in c.execute(
                             "SELECT datum, betrag, stichtag FROM ambassador_auszahlung "
                             "WHERE code=? ORDER BY datum DESC, id DESC", (code,))],
    }


_ROUTEN = [
    ("POST", "/api/ambassador", api_ambassador_anlegen),
    ("GET", "/api/ambassador/liste", api_ambassador_liste),
    ("GET", "/api/ambassador/me", api_ambassador_me),
    ("POST", "/api/ambassador/link", api_ambassador_link),
    ("POST", "/api/ambassador/einladen", api_ambassador_einladen),
    ("GET", "/ambassador/{code}/{slug}", ambassador_landing),
    ("POST", "/api/ambassador/meilenstein", api_ambassador_meilenstein),
    ("POST", "/api/ambassador/einloesen", api_ambassador_einloesen),
    ("POST", "/api/ambassador/verlaengern", api_ambassador_verlaengern),
    ("POST", "/api/ambassador/gezahlt", api_ambassador_gezahlt),
]
