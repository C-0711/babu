"""Die Apple-Seite des Abos: was die App meldet, und was Apple meldet.

Zwei Wege führen zum selben Eintrag, und beide müssen dicht sein:

**Die App** (`POST /api/abo/apple`) schickt nach einem Kauf ihre
`signedTransactionInfo` aus StoreKit 2. Das ist der schnelle Weg — die
Nutzerin tippt „Buchen" und hat sofort Platz.

**Apple** (`POST /api/abo/apple/meldung`) schickt App Store Server
Notifications V2: Verlängerung, Kündigung, Zahlungsproblem, Rückerstattung,
Stufenwechsel. Das ist der verlässliche Weg — er kommt auch, wenn das Telefon
aus ist, und er ist der einzige, der von einem Abo erfährt, das endet.

Beide Wege prüfen die Signatur in `apple_abo.pruefen` und schreiben über
`mandanten.stufe_setzen`. Kein Weg glaubt einer Zahl im Rumpf, bevor die
Kette gegen unsere eigene Kopie der Apple-Wurzel geprüft ist.

Die Meldungen von Apple kommen ohne Anmeldung — die Echtheit steckt in der
Signatur, nicht in einem Kopf. Der Mandant wird über die
`originalTransactionId` gefunden, die beim Kauf eingetragen wurde.
"""
from __future__ import annotations

import json

from fastapi import Request
from fastapi.responses import JSONResponse, Response

import apple_abo
import mandanten
import paket


def setup(app, bw_modul):
    """Der Kern reicht sich selbst herein — siehe `kern_abo.setup`."""
    globals()["bw"] = bw_modul
    globals()["app"] = app
    app.post("/api/abo/apple")(api_abo_apple)
    app.post("/api/abo/apple/meldung")(api_abo_apple_meldung)


def _eintragen(mandant_id: int, inhalt: dict) -> tuple[str | None, dict]:
    """Den geprüften Inhalt auf einen Betrieb schreiben. Gibt die Stufe und
    den Platzstand zurück."""
    stufe, felder = apple_abo.stufe_aus_beleg(inhalt)
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        mandanten.stufe_setzen(mandant_id, stufe, felder["apple_abo"],
                              felder["apple_produkt"], c=c)
        stand = mandanten.abo_stand(mandant_id, c=c)
    platz = paket.stand(herkunft=stand.get("herkunft"), stufe=stand.get("paket"),
                        verbraucht=stand.get("speicher_bytes"),
                        belege=stand.get("belege_gesamt"))
    print(f"[apple] Mandant {mandant_id}: Stufe {stufe or '—'} "
          f"({felder['apple_produkt'] or 'ohne Produkt'}, "
          f"Abo {felder['apple_abo'] or '—'})", flush=True)
    return stufe, platz or {}


async def api_abo_apple(request: Request) -> Response:
    """Die App meldet ihren Kauf — `{"signed": "<JWS>"}`.

    Antwort: die eingetragene Stufe und der Platzstand, damit die App sofort
    anzeigen kann, was jetzt gilt, ohne `/api/ich` nachzuladen.
    """
    un, fehler = bw._api_wache(request)  # noqa: SLF001
    if fehler or not un:
        return fehler or JSONResponse({"fehler": "nicht angemeldet"},
                                      status_code=401)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 64 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit signed erwartet"},
                            status_code=400)
    jws = str((koerper or {}).get("signed", "") or "")
    if not jws:
        return JSONResponse({"fehler": "JSON mit signed erwartet"},
                            status_code=400)
    # Dieselbe Frage wie überall sonst im Server: zu welchem Betrieb gehört
    # dieser Zugang? `_eigener_mandant` fragt über den Besitzer, nicht über
    # die Hauskanzlei.
    #
    # Bis zum 15.10.2026 stand hier `testmonat.direkt_mandant_von`, und das
    # findet NUR Betriebe der Hauskanzlei „babu direkt". Ein Betrieb unter
    # einer Kanzlei sah damit den Kaufbildschirm (den liefert `/api/ich`
    # über `_eigener_mandant`), bekam aber beim Melden des Kaufs ein 404:
    # Apple hätte abgebucht, und der Platz wäre nie eingetragen worden.
    # Gefunden an Apples eigenem Prüfkonto, dessen Betrieb unter der
    # Kanzlei Afflek hängt.
    mandant_id, sperre = bw._eigener_mandant(un)  # noqa: SLF001
    if sperre is not None:
        return sperre          # hängt an mehreren Betrieben — 409 wie sonst
    if mandant_id is None:
        return JSONResponse({"fehler": "Für diesen Zugang gibt es hier "
                                       "keinen Betrieb."}, status_code=404)
    mandant_id = int(mandant_id)
    try:
        inhalt = apple_abo.pruefen(jws)
    except apple_abo.NichtEcht as ex:
        # Absichtlich knapp nach außen und ausführlich ins Protokoll: wer
        # einen Beleg fälscht, soll nicht lernen, an welchem Schritt es lag.
        print(f"[apple] Beleg abgelehnt (Mandant {mandant_id}): {ex}", flush=True)
        return JSONResponse({"fehler": "Dieser Kaufbeleg lässt sich nicht "
                                       "prüfen."}, status_code=400)
    # Trägt der Beleg eine Kaufkennung, muss sie zu diesem Betrieb gehören
    # (seit 14.10.2026). Sonst meldet ein Telefon, auf dem zwei Zugänge
    # benutzt werden, den Kauf des einen Betriebs beim anderen an — beide
    # Male mit einem echten, von Apple signierten Beleg.
    # Alte Käufe (vor dieser Fassung) tragen keine Kennung: dann gilt wie
    # bisher der angemeldete Zugang.
    kennung = str(inhalt.get("appAccountToken") or "").strip()
    if kennung and kennung.lower() != paket.kauf_kennung(mandant_id):
        print(f"[apple] Beleg mit fremder Kaufkennung (Mandant {mandant_id}): "
              f"{kennung}", flush=True)
        return JSONResponse({"fehler": "Dieser Kauf gehört zu einem anderen "
                                       "Betrieb."}, status_code=409)
    try:
        stufe, platz = _eintragen(mandant_id, inhalt)
    except mandanten.AppleAboVergeben as ex:
        print(f"[apple] {ex}", flush=True)
        return JSONResponse({"fehler": "Dieses Abo gehört schon zu einem "
                                       "anderen Betrieb."}, status_code=409)
    if stufe is None:
        return JSONResponse({"stufe": None, "speicher": platz,
                             "hinweis": "Dieser Kauf gilt nicht mehr."})
    return JSONResponse({"stufe": stufe, "speicher": platz,
                         "text": paket.text(platz)})


async def api_abo_apple_meldung(request: Request) -> Response:
    """App Store Server Notifications V2 — `{"signedPayload": "<JWS>"}`.

    Apple erwartet 200 für „angekommen" und wiederholt bei allem anderen.
    Deshalb: 200 auch dann, wenn die Meldung einen Betrieb betrifft, den wir
    nicht (mehr) kennen — eine Wiederholung würde daran nichts ändern. Nur
    eine Meldung, deren Signatur nicht stimmt, wird mit 400 abgewiesen, und
    ein Fehler auf unserer Seite mit 500, damit Apple es noch einmal versucht.
    """
    if not bw._origin_ok(request):  # noqa: SLF001
        return JSONResponse({"fehler": "nicht erlaubt"}, status_code=403)
    try:
        koerper = json.loads(await bw.koerper_lesen(request, 256 * 1024))
    except Exception:  # noqa: BLE001
        return JSONResponse({"fehler": "JSON mit signedPayload erwartet"},
                            status_code=400)
    try:
        aussen = apple_abo.pruefen(str((koerper or {}).get("signedPayload", "")))
    except apple_abo.NichtEcht as ex:
        print(f"[apple] Meldung abgelehnt: {ex}", flush=True)
        return JSONResponse({"fehler": "Signatur stimmt nicht"}, status_code=400)
    art = str(aussen.get("notificationType") or "")
    unterart = str(aussen.get("subtype") or "")
    daten = aussen.get("data") or {}
    signiert = daten.get("signedTransactionInfo")
    if not signiert:
        # REFUND_DECLINED, CONSUMPTION_REQUEST und andere kommen ohne
        # Vorgang — angekommen, nichts zu tun.
        print(f"[apple] Meldung {art}/{unterart or '—'} ohne Vorgang", flush=True)
        return JSONResponse({"ok": True})
    try:
        inhalt = apple_abo.pruefen(str(signiert))
    except apple_abo.NichtEcht as ex:
        print(f"[apple] Meldung {art}: innerer Beleg abgelehnt: {ex}", flush=True)
        return JSONResponse({"fehler": "Signatur stimmt nicht"}, status_code=400)
    original = str(inhalt.get("originalTransactionId") or "")
    if not original:
        print(f"[apple] Meldung {art} ohne originalTransactionId", flush=True)
        return JSONResponse({"ok": True})
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        mandant_id = mandanten.mandant_mit_apple_abo(original, c=c)
        if mandant_id is None:
            # Rückfall über die Kaufkennung (seit 14.10.2026): Apples erste
            # Meldung kommt manchmal, bevor die App ihren Kauf gemeldet hat,
            # und ein neu aufgesetztes Telefon meldet gar nichts, bis sich
            # jemand anmeldet. Die Kennung steht in jedem Vorgang, den Apple
            # ausstellt — damit findet die Meldung den Betrieb allein.
            mandant_id = mandanten.mandant_aus_kauf_kennung(
                inhalt.get("appAccountToken"), c=c)
            if mandant_id is not None:
                print(f"[apple] Meldung {art}: Abo {original} über die "
                      f"Kaufkennung zu Mandant {mandant_id}", flush=True)
    if mandant_id is None:
        # Weder Abo noch Kennung bekannt — etwa ein Kauf aus einer Fassung
        # vor der Kaufkennung, den die App noch nicht gemeldet hat. Die App
        # trägt gleich darauf ein, und die nächste Meldung findet ihn.
        print(f"[apple] Meldung {art}/{unterart or '—'}: Abo {original} "
              f"gehört (noch) keinem Betrieb", flush=True)
        return JSONResponse({"ok": True})
    try:
        stufe, _platz = _eintragen(mandant_id, inhalt)
    except mandanten.AppleAboVergeben as ex:
        print(f"[apple] Meldung {art}: {ex}", flush=True)
        return JSONResponse({"ok": True})
    print(f"[apple] Meldung {art}/{unterart or '—'} → Mandant {mandant_id}: "
          f"Stufe {stufe or '—'}", flush=True)
    return JSONResponse({"ok": True})
