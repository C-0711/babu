"""Das Gerätekonto: die App legt los, ohne dass sich jemand anmeldet.

Entschieden am 10.10.2026 zusammen mit den Speicherstufen (`paket.py`). Wer
babu im App Store lädt, fotografiert den ersten Beleg, ohne vorher ein Konto
anzulegen: keine E-Mail, kein Passwort, keine Einladung. Das Telefon bekommt
einen Schlüssel, und der Betrieb entsteht dahinter von selbst.

Die E-Mail fragt die App später und freiwillig (`/api/konto/email`) — für die
Wiederherstellung auf einem neuen Telefon und für die Rechnung. Bis dahin hat
der Betrieb einen erfundenen Bezeichner ohne @; dieselbe Form führen die
GitChain-Dienstkonten schon, der Rest des Servers kommt damit zurecht.

Kein Testmonat. An seine Stelle treten die zehn freien Belege
(`paket.BELEGE_FREI`) — großzügiger für die, die nur schauen wollen, und
ehrlicher für die, die bleiben: gezählt wird, was benutzt wurde, nicht, wie
lange die App auf dem Telefon lag.

Die Belegbox: `mandanten.mandant_anlegen` setzt `box_ausstehend`, und der
Box-Anleger auf dem Host (docker/box-anleger.sh, Cron jede Minute) richtet
sie ein. Eine Minute ist für ein Telefon, das gerade den ersten Beleg
fotografiert, zu lang — deshalb legt diese Route die Box sofort in einem
Hintergrundfaden an (`_box_nachziehen`, derselbe Weg wie
`betrieb_anlegen.py --nur-box --box-anlegen`). Scheitert der Faden, bleibt
der Mandant auf `box_ausstehend` und der Cron holt es nach: der Antwortweg
der App ändert sich dadurch nicht, nur die Wartezeit.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import time

from fastapi import Request
from fastapi.responses import JSONResponse, Response

import mandanten
import paket

#: Wie oft ein Anschluss ein Konto anlegen darf. Ohne Bremse wäre die Route
#: ein Kontengenerator — sie verlangt ja keine Anmeldung.
BREMSE_SEKUNDEN = 20
_ZULETZT: dict[str, float] = {}

#: Was im Betriebsnamen steht, bevor der erste Beleg ihn verrät. babu liest
#: den richtigen Namen später aus dem heraus, was fotografiert wird.
NAME_VORLAEUFIG = "Mein Betrieb"

_UMLAUTE = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe",
            "Ü": "ue", "ß": "ss"}


def setup(app, bw_modul):
    """Der Kern reicht sich selbst herein — siehe `kern_warteliste.setup`."""
    globals()["bw"] = bw_modul
    globals()["app"] = app
    app.post("/api/geraet/anlegen")(api_geraet_anlegen)
    app.post("/api/konto/email")(api_konto_email)


def kennung() -> str:
    """Ein Bezeichner ohne @, der keinem Menschen gehört.

    `app-` vorn, damit in jedem Protokoll sofort sichtbar ist, woher das
    Konto kommt — und damit niemand ihn für eine E-Mail hält."""
    return "app-" + secrets.token_hex(12)


def kurzname(name: str, mandant_id: int) -> str:
    """Betriebsname → Box-Namensraum, Zeichen für Zeichen wie box-anleger.sh.

    Die Mandanten-Nummer hinten, damit zwei „Salon Schmidt" nie dieselbe
    Box bekommen (eine Ablage gehört genau einem Betrieb —
    `mandanten.box_verknuepfen` erzwingt das seit 09.10.2026)."""
    for a, b in _UMLAUTE.items():
        name = name.replace(a, b)
    k = re.sub(r"-+$", "", re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40])
    return f"{k or 'betrieb'}-{mandant_id}"


def _box_nachziehen(mandant_id: int, name: str) -> None:
    """Die Belegbox anlegen und verknüpfen — im Hintergrundfaden.

    Netzarbeit (git push zum GitChain-Dienst), deshalb NICHT unter dem
    Datenbankschloss und nicht im Antwortweg der App. Jeder Fehler bleibt
    ein Protokolleintrag: der Cron-Anleger versucht es in der nächsten
    Minute erneut, und bis dahin ist der Mandant ehrlich ohne Box."""
    import boxschreiber  # noqa: PLC0415
    # Dieselben beiden Umgebungswerte, die box-anleger.sh liest — sonst
    # bauten Cron und Server zwei verschiedene Verweise für denselben Betrieb.
    praefix = os.environ.get("BABU_BOX_PRAEFIX", "babu")
    kennzahl = os.environ.get("BABU_BOX_KENNUNG", "belege")
    ref = f"{praefix}/{kurzname(name, mandant_id)}/{kennzahl}"
    try:
        boxschreiber.box_anlegen(ref, anzeige=name)
    except Exception as ex:  # noqa: BLE001 — jeder Grund endet gleich: Cron holt's
        print(f"[geraet] Box {ref} nicht angelegt ({ex.__class__.__name__}: "
              f"{str(ex)[:160]}) — der Box-Anleger holt es nach", flush=True)
        return
    try:
        with bw._db_sitzung() as c:  # noqa: SLF001
            mandanten.box_verknuepfen(mandant_id, ref, c=c)
    except Exception as ex:  # noqa: BLE001
        print(f"[geraet] Box {ref} angelegt, aber nicht verknüpft "
              f"({ex.__class__.__name__}: {str(ex)[:160]})", flush=True)
        return
    print(f"[geraet] Mandant {mandant_id} hat seine Belegbox: {ref}", flush=True)


async def api_geraet_anlegen(request: Request) -> Response:
    """Ein Telefon meldet sich zum ersten Mal — Konto, Betrieb, Schlüssel.

    Antwort wie bei `/api/app-anmelden`: der Schlüssel erscheint GENAU
    EINMAL, gespeichert wird nur sein SHA-256. Verliert ihn das Telefon,
    führt die Wiederherstellung über die hinterlegte E-Mail.
    """
    if not bw._origin_ok(request):  # noqa: SLF001
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    ip = bw._client_ip(request)  # noqa: SLF001
    jetzt = time.time()
    if jetzt - _ZULETZT.get(ip, 0.0) < BREMSE_SEKUNDEN:
        return JSONResponse({"fehler": "Kurz warten, dann noch einmal."},
                            status_code=429)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 8 * 1024) or b"{}")
    except Exception:  # noqa: BLE001
        koerper = {}
    if not isinstance(koerper, dict):
        koerper = {}
    geraet = str(koerper.get("geraet", "") or "")[:80]
    name = str(koerper.get("betrieb", "") or "").strip()[:120] or NAME_VORLAEUFIG

    un = kennung()
    # Ein Passwort, das niemand kennt und niemand braucht: dieses Konto hat
    # keinen Weg über die Portal-Anmeldung, nur den Geräteschlüssel.
    # `box=False`, weil die Ablage am Mandanten hängt, nicht am Nutzer.
    if bw.nutzer_anlegen(un, "", name, "salon",
                         passwort=secrets.token_urlsafe(32), box=False) is None:
        return JSONResponse({"fehler": "Das hat gerade nicht geklappt."},
                            status_code=500)
    import testmonat  # noqa: PLC0415
    schluessel = secrets.token_urlsafe(32)
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        mandant_id = mandanten.mandant_anlegen(
            testmonat.direkt_kanzlei(c), name, un, "SKR04", c=c)
        # Die Herkunft ist die Weiche: nur „app" unterliegt den Stufen
        # (paket.stand gibt für alles andere None zurück, und damit bleibt
        # jeder Portal-Betrieb byte-genau, wie er war).
        c.execute("UPDATE mandant SET herkunft=? WHERE id=?",
                  (paket.HERKUNFT_APP, mandant_id))
        c.execute("INSERT INTO app_schluessel VALUES (?,?,?,?,?)",
                  (hashlib.sha256(schluessel.encode()).hexdigest(), un,
                   geraet, bw._jetzt_iso(), None))  # noqa: SLF001
    bw.db_einstellung_setzen(un, "betrieb_name", name)
    _ZULETZT[ip] = jetzt
    bw._zaehler_aufraeumen(_ZULETZT, jetzt, 3600.0)  # noqa: SLF001
    threading.Thread(target=_box_nachziehen, args=(mandant_id, name),
                     name=f"box-{mandant_id}", daemon=True).start()
    print(f"[geraet] neues Konto {un}, Mandant {mandant_id} "
          f"({geraet or 'Gerät ohne Namen'})", flush=True)
    return JSONResponse({"schluessel": schluessel, "un": un,
                         "mandant": mandant_id,
                         "belege_frei": paket.BELEGE_FREI,
                         "stufen": paket.angebot()})


async def api_konto_email(request: Request) -> Response:
    """Die E-Mail nachreichen — für Wiederherstellung und Rechnung.

    Freiwillig und jederzeit. Sie ersetzt den Bezeichner nicht (der steht in
    jedem Commit der Ablage), sondern wird daneben gelegt."""
    un, fehler = bw._api_wache(request)  # noqa: SLF001
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"},
                                      status_code=401)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 8 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit email erwartet"}, status_code=400)
    import einladung as ei  # noqa: PLC0415
    email = str(koerper.get("email", "") or "").strip().lower()[:200]
    if not ei.mail_gueltig(email):
        return JSONResponse({"fehler": "Das sieht nicht nach einer E-Mail-"
                                       "Adresse aus."}, status_code=400)
    bw.db_einstellung_setzen(un, "email", email)
    print(f"[geraet] {un}: E-Mail hinterlegt", flush=True)
    return JSONResponse({"ok": True, "email": email})
