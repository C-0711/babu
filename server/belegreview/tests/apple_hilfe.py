"""Eine eigene Zertifikatskette und eigene JWS bauen — nur für die Suite.

Apples Belege kann niemand nachbauen, der Apples Schlüssel nicht hat; das
ist der Sinn der Sache. Um den Prüfcode trotzdem auf seinem richtigen Weg
zu messen, baut die Suite eine Kette derselben FORM (Blatt → Zwischen →
Wurzel, ES256) und tauscht in einem Test die erwartete Wurzel gegen die
eigene. Alles andere — Kettenbau, Laufzeiten, jede Signatur, der JWS —
läuft dabei unverändert durch `apple_abo`.

Dass eine selbst gebaute Kette OHNE diesen Tausch abgewiesen wird, ist die
Gegenprobe und steht in `test_apple_abo.py`.
"""
from __future__ import annotations

import base64
import datetime as dt
import json

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _zert(cn: str, schluessel, aussteller_name, aussteller_schluessel, *,
          ca: bool, von: dt.datetime, bis: dt.datetime):
    b = (x509.CertificateBuilder()
         .subject_name(_name(cn))
         .issuer_name(aussteller_name)
         .public_key(schluessel.public_key())
         .serial_number(x509.random_serial_number())
         .not_valid_before(von)
         .not_valid_after(bis)
         .add_extension(x509.BasicConstraints(ca=ca, path_length=None),
                        critical=True))
    return b.sign(aussteller_schluessel, hashes.SHA256())


def kette(*, blatt_von: dt.datetime | None = None,
          blatt_bis: dt.datetime | None = None):
    """Wurzel, Zwischen, Blatt — jedes mit eigenem Schlüssel.

    Rückgabe `(x5c, blatt_schluessel, wurzel_zert)`. `x5c` ist die Liste,
    wie sie im JWS-Kopf steht: Blatt zuerst, Wurzel zuletzt.
    """
    jetzt = dt.datetime.now(dt.timezone.utc)
    von, bis = jetzt - dt.timedelta(days=1), jetzt + dt.timedelta(days=365)
    wk = ec.generate_private_key(ec.SECP256R1())
    zk = ec.generate_private_key(ec.SECP256R1())
    bk = ec.generate_private_key(ec.SECP256R1())
    wurzel = _zert("Suite Root", wk, _name("Suite Root"), wk, ca=True,
                   von=von, bis=bis)
    zwischen = _zert("Suite Intermediate", zk, wurzel.subject, wk, ca=True,
                     von=von, bis=bis)
    blatt = _zert("Suite Leaf", bk, zwischen.subject, zk, ca=False,
                  von=blatt_von or von, bis=blatt_bis or bis)
    x5c = [base64.b64encode(z.public_bytes(Encoding.DER)).decode()
           for z in (blatt, zwischen, wurzel)]
    return x5c, bk, wurzel


def _b64(roh: bytes) -> str:
    return base64.urlsafe_b64encode(roh).rstrip(b"=").decode()


def jws(rumpf: dict, x5c: list[str], schluessel, *, alg: str = "ES256",
        signatur_kaputt: bool = False) -> str:
    """Ein JWS derselben Form, die StoreKit 2 und Apples Meldungen senden."""
    kopf = _b64(json.dumps({"alg": alg, "x5c": x5c}).encode())
    inhalt = _b64(json.dumps(rumpf).encode())
    roh = schluessel.sign(f"{kopf}.{inhalt}".encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(roh)
    sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    if signatur_kaputt:
        sig = bytes([sig[0] ^ 0xFF]) + sig[1:]
    return f"{kopf}.{inhalt}.{_b64(sig)}"


def ms(wann: dt.datetime) -> int:
    """Apple zählt in Millisekunden seit 1970."""
    return int(wann.timestamp() * 1000)
