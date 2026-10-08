"""Push-Nachrichten über Apple (APNs) — babu Expenses D1, seit 04.10.2026.

Anmeldung per Schlüssel (`.p8`): `APNS_KEY_ID`, `APNS_TEAM_ID` und der Pfad
`APNS_SCHLUESSEL` stehen in `docker/.env`. Fehlt etwas davon, ist Push still
aus — Mails gehen trotzdem. `BABU_PUSH=0` schaltet Push ab. APNs spricht nur
HTTP/2; das Token ist ES256-signiert und wird 50 Minuten wiederverwendet.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path

THEMEN = ("io.0711.beleg", "io.0711.beleg.pro")
HOSTS = {"produktion": "https://api.push.apple.com",
         "sandbox": "https://api.sandbox.push.apple.com"}
_TOKEN = {"wert": None, "zeit": 0.0}
_SCHLOSS = threading.Lock()


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def eingerichtet() -> bool:
    return (_env("BABU_PUSH") != "0" and bool(_env("APNS_KEY_ID"))
            and bool(_env("APNS_TEAM_ID"))
            and Path(_env("APNS_SCHLUESSEL") or "/nicht/da").is_file())


def _b64(roh: bytes) -> str:
    return base64.urlsafe_b64encode(roh).rstrip(b"=").decode()


def token(jetzt: float | None = None, schluessel_pem: bytes | None = None,
          key_id: str | None = None, team_id: str | None = None) -> str:
    from cryptography.hazmat.primitives import hashes, serialization  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric import ec  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature  # noqa: PLC0415
    jetzt = jetzt or time.time()
    with _SCHLOSS:
        if schluessel_pem is None and _TOKEN["wert"] and jetzt - _TOKEN["zeit"] < 50 * 60:
            return _TOKEN["wert"]
        pem = schluessel_pem or Path(_env("APNS_SCHLUESSEL")).read_bytes()
        kopf = _b64(json.dumps({"alg": "ES256", "kid": key_id or _env("APNS_KEY_ID")},
                               separators=(",", ":")).encode())
        inhalt = _b64(json.dumps({"iss": team_id or _env("APNS_TEAM_ID"), "iat": int(jetzt)},
                                 separators=(",", ":")).encode())
        schluessel = serialization.load_pem_private_key(pem, password=None)
        r, s = decode_dss_signature(schluessel.sign(f"{kopf}.{inhalt}".encode(),
                                                    ec.ECDSA(hashes.SHA256())))
        wert = f"{kopf}.{inhalt}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
        if schluessel_pem is None:
            _TOKEN.update(wert=wert, zeit=jetzt)
        return wert


def anfrage(geraet: str, titel: str, text: str, umgebung: str, thema: str,
            jwt: str, klang: str = "default") -> tuple[str, dict, bytes]:
    url = f"{HOSTS.get(umgebung, HOSTS['produktion'])}/3/device/{geraet}"
    kopf = {"authorization": f"bearer {jwt}", "apns-topic": thema,
            "apns-push-type": "alert", "apns-priority": "10"}
    # `klang`: Dateiname im App-Bundle (z. B. „kaching.caf“ für Provisionen,
    # seit 08.10.2026) — fehlt die Datei, nimmt iOS den Standardton.
    body = json.dumps({"aps": {"alert": {"title": titel, "body": text}, "sound": klang}},
                      ensure_ascii=False).encode()
    return url, kopf, body


def _client():
    import httpx  # noqa: PLC0415
    return httpx.Client(http2=True, timeout=10)


_client_fabrik = _client


def senden_an(geraete: list[dict], titel: str, text: str, loeschen,
              klang: str = "default") -> int:
    """An jedes Gerät einmal. 410 heißt: die App ist weg — `loeschen(token)`."""
    if not geraete or not eingerichtet():
        return 0
    jwt = token()
    client = _client_fabrik()
    angenommen = 0
    try:
        for g in geraete:
            url, kopf, body = anfrage(g["token"], titel, text, g["umgebung"], g["thema"], jwt,
                                      klang)
            try:
                antwort = client.post(url, headers=kopf, content=body)
            except Exception as ex:  # noqa: BLE001
                print(f"[push] nicht erreicht: {ex!r}", flush=True)
                continue
            if antwort.status_code == 200:
                angenommen += 1
            elif antwort.status_code == 410:
                loeschen(g["token"])
            else:
                print(f"[push] Antwort {antwort.status_code}", flush=True)
    finally:
        client.close()
    return angenommen
