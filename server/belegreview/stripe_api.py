"""Stripe — ohne SDK, über `requests` (seit 03.10.2026).

babu braucht von Stripe nur eine Handvoll Aufrufe: Checkout-Sitzung,
Kundenportal, Abo/Rechnung/Ereignis/Zahlung lesen. Dafür lohnt keine
Bibliothek mit eigenem globalem Schlüssel; die Tests ersetzen eine einzige
Funktion (`_rufen`) und brauchen kein Netz.

Geheimnisse kommen nur aus der Umgebung (`.env` auf dem Server, nie im
Repo, nie in compose):

    BABU_STRIPE_SCHLUESSEL         rk_live_… / rk_test_… (eingeschränkter Schlüssel)
    BABU_STRIPE_WEBHOOK_GEHEIMNIS  whsec_…
    BABU_STRIPE_PREIS_SOLO|SALON|PLUS   price_…
    BABU_STRIPE_STEUERSATZ         txr_… (19 % exklusiv)
    BABU_STRIPE_VERSION            die API-Version des Webhook-Endpunkts

Schutz gegen Verwechslung: ein Live-Schlüssel arbeitet nur auf
https://mybabu.io, ein Test-Schlüssel nie dort. Sonst gilt Stripe als
„nicht eingerichtet" — lieber kein Abo als echte Abbuchungen von der
Dev-Spur oder Test-Abos im Betrieb.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time

API = "https://api.stripe.com/v1"
LIVE_URSPRUNG = "https://mybabu.io"

#: Wie alt eine Signatur höchstens sein darf (Stripe empfiehlt 5 Minuten).
TOLERANZ_S = 300


class StripeFehler(RuntimeError):
    """Stripe hat abgelehnt oder war nicht erreichbar."""


# ---------------------------------------------------------------------------
# Umgebung
# ---------------------------------------------------------------------------

def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def schluessel() -> str:
    return _env("BABU_STRIPE_SCHLUESSEL")


def testmodus() -> bool:
    return "_test_" in schluessel()


def preis_id(paket: str) -> str:
    return _env(f"BABU_STRIPE_PREIS_{paket.upper()}")


def steuersatz() -> str:
    return _env("BABU_STRIPE_STEUERSATZ")


def paket_aus_preis(preis: str | None) -> str | None:
    for paket in ("solo", "salon", "plus"):
        if preis and preis == preis_id(paket):
            return paket
    return None


def modus() -> str:
    """aus | test | live — für /healthz und die Testmodus-Fahne im Portal."""
    if not schluessel():
        return "aus"
    return "test" if testmodus() else "live"


def eingerichtet(ursprung: str) -> bool:
    """Darf auf diesem Server mit diesem Schlüssel abgerechnet werden?"""
    s = schluessel()
    if not s or not _env("BABU_STRIPE_WEBHOOK_GEHEIMNIS"):
        return False
    if not all(preis_id(p) for p in ("solo", "salon", "plus")) or not steuersatz():
        return False
    live_hier = ursprung.rstrip("/") == LIVE_URSPRUNG
    if testmodus() == live_hier:
        print(f"[stripe] AUS: {'Test' if testmodus() else 'Live'}-Schlüssel "
              f"auf {ursprung} — Verwechslungsschutz", flush=True)
        return False
    return True


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _formular(daten: dict, praefix: str = "") -> list[tuple[str, str]]:
    """Stripes Formularkodierung: a[b][0]=c für verschachtelte Werte."""
    paare: list[tuple[str, str]] = []
    for k, v in daten.items():
        name = f"{praefix}[{k}]" if praefix else str(k)
        if v is None:
            continue
        if isinstance(v, dict):
            paare += _formular(v, name)
        elif isinstance(v, (list, tuple)):
            for i, x in enumerate(v):
                if isinstance(x, dict):
                    paare += _formular(x, f"{name}[{i}]")
                else:
                    paare.append((f"{name}[{i}]", _wert(x)))
        else:
            paare.append((name, _wert(v)))
    return paare


def _wert(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _rufen(methode: str, pfad: str, daten: dict | None = None,
           idempotenz: str | None = None) -> dict:
    """Die einzige Stelle mit Netz. Tests ersetzen genau diese Funktion."""
    import requests  # noqa: PLC0415 — nur wer wirklich abrechnet, braucht es
    kopf = {"Authorization": f"Bearer {schluessel()}"}
    if _env("BABU_STRIPE_VERSION"):
        kopf["Stripe-Version"] = _env("BABU_STRIPE_VERSION")
    if idempotenz:
        kopf["Idempotency-Key"] = idempotenz
    url = API + pfad
    try:
        if methode == "GET":
            r = requests.get(url, params=_formular(daten or {}), headers=kopf, timeout=20)
        else:
            r = requests.post(url, data=_formular(daten or {}), headers=kopf, timeout=20)
    except Exception as ex:  # noqa: BLE001
        raise StripeFehler(f"Stripe nicht erreichbar: {ex!r}"[:200]) from None
    try:
        antwort = r.json()
    except ValueError:
        raise StripeFehler(f"Stripe antwortete {r.status_code} ohne JSON") from None
    if r.status_code >= 400:
        meldung = (antwort.get("error") or {}).get("message") or str(r.status_code)
        raise StripeFehler(f"Stripe {r.status_code}: {meldung}"[:300])
    return antwort


def holen(pfad: str, **daten) -> dict:
    return _rufen("GET", pfad, daten or None)


def anlegen(pfad: str, daten: dict, idempotenz: str | None = None) -> dict:
    return _rufen("POST", pfad, daten, idempotenz)


# ---------------------------------------------------------------------------
# Signatur der Webhooks
# ---------------------------------------------------------------------------

def signatur_pruefen(rumpf: bytes, kopf: str, geheimnis: str,
                     jetzt: float | None = None) -> bool:
    """`Stripe-Signature: t=…,v1=…[,v1=…]` gegen den ROHEN Rumpf prüfen.

    HMAC-SHA256 über "<t>.<rumpf>" mit dem Endpunkt-Geheimnis; jede v1 darf
    passen (Stripe schickt beim Wechsel des Geheimnisses zwei). Zu alt
    (> 5 min) heißt abgelehnt — gegen das Wiederabspielen."""
    if not kopf or not geheimnis:
        return False
    teile: dict[str, list[str]] = {}
    for stueck in kopf.split(","):
        k, _, v = stueck.strip().partition("=")
        teile.setdefault(k, []).append(v)
    try:
        t = int(teile.get("t", [""])[0])
    except ValueError:
        return False
    if abs((jetzt if jetzt is not None else time.time()) - t) > TOLERANZ_S:
        return False
    soll = hmac.new(geheimnis.encode(), f"{t}.".encode() + rumpf,
                    hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(soll, v) for v in teile.get("v1", []))


def signieren(rumpf: bytes, geheimnis: str, t: int | None = None) -> str:
    """Für Tests: den Kopf so bauen, wie Stripe ihn schickt."""
    t = int(time.time()) if t is None else t
    v1 = hmac.new(geheimnis.encode(), f"{t}.".encode() + rumpf,
                  hashlib.sha256).hexdigest()
    return f"t={t},v1={v1}"


# ---------------------------------------------------------------------------
# Leser — beide Formen der Stripe-API (vor und ab 2025-03-31 „basil")
# ---------------------------------------------------------------------------

def abo_der_rechnung(rechnung: dict) -> str | None:
    """Zu welchem Abo gehört die Rechnung? Ab „basil" steht es unter parent."""
    sub = rechnung.get("subscription")
    if isinstance(sub, dict):
        sub = sub.get("id")
    if sub:
        return sub
    eltern = rechnung.get("parent") or {}
    details = eltern.get("subscription_details") or {}
    sub = details.get("subscription")
    return sub.get("id") if isinstance(sub, dict) else sub


def metadaten_der_rechnung(rechnung: dict) -> dict:
    """Die Metadaten des Abos, wie Stripe sie in die Rechnung kopiert."""
    details = (rechnung.get("parent") or {}).get("subscription_details") or {}
    return (details.get("metadata")
            or (rechnung.get("subscription_details") or {}).get("metadata") or {})


def periodenende(abo_obj: dict) -> int | None:
    """Ende der laufenden Periode (Unix-Zeit). Ab „basil" je Position."""
    posten = ((abo_obj.get("items") or {}).get("data") or [])
    if posten and posten[0].get("current_period_end"):
        return int(posten[0]["current_period_end"])
    wert = abo_obj.get("current_period_end")
    return int(wert) if wert else None


def preis_des_abos(abo_obj: dict) -> str | None:
    posten = ((abo_obj.get("items") or {}).get("data") or [])
    if not posten:
        return None
    preis = posten[0].get("price") or {}
    return preis.get("id") if isinstance(preis, dict) else preis


def preis_der_rechnung(rechnung: dict) -> str | None:
    """Preis der ersten Rechnungszeile — alt `price`, ab „basil" `pricing`."""
    zeilen = ((rechnung.get("lines") or {}).get("data") or [])
    for z in zeilen:
        preis = z.get("price")
        if isinstance(preis, dict) and preis.get("id"):
            return preis["id"]
        if isinstance(preis, str):
            return preis
        details = (z.get("pricing") or {}).get("price_details") or {}
        if details.get("price"):
            return details["price"]
    return None


def kunde(obj: dict) -> str | None:
    k = obj.get("customer")
    return k.get("id") if isinstance(k, dict) else k


def datum(unix: int | None) -> str | None:
    if not unix:
        return None
    return time.strftime("%Y-%m-%d", time.gmtime(int(unix)))


def ereignis_aus(rumpf: bytes) -> dict:
    return json.loads(rumpf.decode("utf-8"))
