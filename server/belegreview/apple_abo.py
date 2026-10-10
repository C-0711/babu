"""Apples signierte Belege prüfen — ohne fremde Bibliothek, mit `cryptography`.

Seit 10.10.2026 verkauft babu drei Speicherstufen im App Store (`paket.py`).
Was davon ankommt, ist nie eine Zahl, der man glauben darf, sondern ein JWS:
StoreKit 2 gibt der App eine `signedTransactionInfo`/`signedRenewalInfo`, und
Apple schickt dem Server dieselbe Form als `signedPayload` in den App Store
Server Notifications V2. Beides ist ES256 über einer Zertifikatskette, die
bei `Apple Root CA - G3` endet.

**Warum selbst prüfen und nicht einfach den Inhalt lesen.** Der Rumpf eines
JWS ist Base64, nicht Verschlüsselung — wer `/api/abo/apple` einen selbst
gebauten Rumpf schickt, schenkt sich sonst 100 GB. Geprüft wird deshalb in
dieser Reihenfolge, und jeder Schritt darf Nein sagen:

1. `x5c` aus dem Kopf: Blatt → Zwischenzertifikat → Wurzel.
2. Die Wurzel MUSS unsere eigene Datei sein (`zertifikate/AppleRootCA-G3.cer`,
   Fingerabdruck in `WURZEL_SHA256`) — nicht die, die in `x5c` mitkommt.
   Sonst prüfte man eine Kette gegen ihre eigene Behauptung.
3. Jede Signatur der Kette, jede Laufzeit.
4. Die Signatur über `kopf.rumpf` mit dem Schlüssel des Blatts.
5. Erst dann der Inhalt: `bundleId` muss unser Bündel sein, `productId` eine
   unserer Stufen.

**Warum keine Bibliothek.** Das Image hat `cryptography` längst (für das
APNs-Token, `push.py`), aber kein PyJWT. Eine neue Abhängigkeit für 60 Zeilen
ES256-Prüfung wäre mehr Risiko als Nutzen — und die Schritte oben will man
ohnehin selbst in der Hand haben.
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import paket

#: Unsere Kopie der Wurzel. Was in `x5c` als Wurzel mitkommt, wird gegen
#: DIESE Datei geprüft — siehe HERKUNFT.md daneben.
WURZEL = Path(__file__).resolve().parent / "zertifikate" / "AppleRootCA-G3.cer"

#: SHA-256 der Datei, wie am 10.10.2026 von apple.com geholt. Stimmt der
#: Abdruck nicht, verweigert das Modul den Dienst: eine Signaturprüfung gegen
#: eine unbekannte Wurzel ist keine Prüfung.
WURZEL_SHA256 = ("63343abfb89a6a03ebb57e9b3f5fa7be7c4f5c756f3017b3a8c488c3"
                 "653e9179")

#: Das Bündel, auf das Apple die Belege ausstellt.
BUENDEL = os.environ.get("APPLE_BUNDLE_ID", "io.0711.beleg")

#: NUR FÜR ENTWICKLUNG: eine zweite Wurzel, die auch gelten soll.
#:
#: StoreKit-Testkäufe aus Xcode (`babu.storekit`) sind NICHT von Apple
#: signiert, sondern von Xcodes eigener Testwurzel
#: (`StoreKitTestCertificate.cer`, CN=StoreKit). Ohne diesen Schalter lässt
#: sich der Kaufweg lokal gar nicht durchspielen — und ein Weg, den niemand
#: durchspielen kann, wird nie geprüft.
#:
#: Leer ist der Normalfall und der Live-Stand. Gesetzt wird es nur auf einem
#: Entwicklungsserver, von Hand, mit dem Pfad zur Datei — es steht in keiner
#: Compose-Datei und in keinem Image. Jeder Beleg, der NUR über diese Wurzel
#: durchkommt, wird beim Annehmen laut protokolliert.
TEST_WURZEL = os.environ.get("APPLE_TEST_WURZEL", "")


class NichtEcht(Exception):
    """Der Beleg hält der Prüfung nicht stand — Grund im Text."""


def _b64(teil: str) -> bytes:
    """Base64url ohne Polster, wie JWS es schreibt."""
    return base64.urlsafe_b64decode(teil + "=" * (-len(teil) % 4))


def _test_wurzel_laden():
    """Die Entwicklungs-Wurzel, falls eine eingestellt ist — sonst None."""
    if not TEST_WURZEL:
        return None
    from cryptography.x509 import load_der_x509_certificate  # noqa: PLC0415
    try:
        roh = Path(TEST_WURZEL).read_bytes()
    except OSError as ex:
        print(f"[apple] APPLE_TEST_WURZEL={TEST_WURZEL!r} nicht lesbar: {ex}",
              flush=True)
        return None
    try:
        return load_der_x509_certificate(roh)
    except Exception:  # noqa: BLE001 — auch PEM zulassen
        from cryptography.x509 import load_pem_x509_certificate  # noqa: PLC0415
        try:
            return load_pem_x509_certificate(roh)
        except Exception as ex:  # noqa: BLE001
            print(f"[apple] APPLE_TEST_WURZEL ist kein Zertifikat: {ex}",
                  flush=True)
            return None


def _wurzel_laden():
    from cryptography.hazmat.primitives import hashes  # noqa: PLC0415
    from cryptography.x509 import load_der_x509_certificate  # noqa: PLC0415
    try:
        roh = WURZEL.read_bytes()
    except OSError as ex:
        raise NichtEcht(f"Wurzelzertifikat fehlt ({WURZEL}): {ex}") from ex
    wurzel = load_der_x509_certificate(roh)
    abdruck = wurzel.fingerprint(hashes.SHA256()).hex()
    if abdruck != WURZEL_SHA256:
        raise NichtEcht(f"Wurzelzertifikat ist nicht das erwartete "
                        f"(SHA-256 {abdruck})")
    return wurzel


def _kette_pruefen(x5c: list[str], jetzt: float):
    """Blatt → Zwischen → Wurzel prüfen und das Blatt zurückgeben."""
    import datetime as dt  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa  # noqa: PLC0415
    from cryptography.x509 import load_der_x509_certificate  # noqa: PLC0415

    if not isinstance(x5c, list) or len(x5c) < 2:
        raise NichtEcht("x5c fehlt oder ist zu kurz")
    kette = [load_der_x509_certificate(base64.b64decode(z)) for z in x5c]
    wurzel = _wurzel_laden()
    # Apple hängt die Wurzel an; sie muss BITGLEICH unsere sein. Vergleich
    # über den öffentlichen Schlüssel, nicht über den Namen — ein Name ist
    # frei wählbar, ein Schlüssel nicht.
    mitgeschickt = kette[-1].public_key().public_numbers()
    if mitgeschickt != wurzel.public_key().public_numbers():
        test = _test_wurzel_laden()
        if test is None or mitgeschickt != test.public_key().public_numbers():
            raise NichtEcht("Die Kette endet nicht bei Apple Root CA - G3")
        print("[apple] ACHTUNG: Beleg über die Entwicklungs-Wurzel "
              f"({TEST_WURZEL}) angenommen — kein Kauf bei Apple", flush=True)
        wurzel = test
    kette[-1] = wurzel
    stunde = dt.datetime.fromtimestamp(jetzt, dt.timezone.utc)
    for i, zert in enumerate(kette):
        if not (zert.not_valid_before_utc <= stunde <= zert.not_valid_after_utc):
            raise NichtEcht(f"Zertifikat {i} der Kette ist nicht (mehr) gültig")
    for i in range(len(kette) - 1):
        kind, eltern = kette[i], kette[i + 1]
        if kind.issuer != eltern.subject:
            raise NichtEcht(f"Kette bricht bei Zertifikat {i}")
        schluessel = eltern.public_key()
        try:
            if isinstance(schluessel, ec.EllipticCurvePublicKey):
                schluessel.verify(kind.signature, kind.tbs_certificate_bytes,
                                  ec.ECDSA(kind.signature_hash_algorithm))
            elif isinstance(schluessel, rsa.RSAPublicKey):
                schluessel.verify(kind.signature, kind.tbs_certificate_bytes,
                                  padding.PKCS1v15(), kind.signature_hash_algorithm)
            else:
                raise NichtEcht(f"Unbekannte Schlüsselart in Zertifikat {i + 1}")
        except NichtEcht:
            raise
        except Exception as ex:  # noqa: BLE001
            raise NichtEcht(f"Signatur von Zertifikat {i} stimmt nicht") from ex
    return kette[0]


def pruefen(jws: str, *, jetzt: float | None = None) -> dict:
    """Ein signierter Apple-Beleg → sein Inhalt, oder `NichtEcht`.

    Prüft Kette, Laufzeiten, Signatur und zuletzt das Bündel. Der Inhalt
    kommt UNVERÄNDERT zurück; welche Felder zählen, entscheidet der Aufrufer
    (`stufe_aus_beleg`).
    """
    from cryptography.hazmat.primitives import hashes  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric import ec  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric.utils import (  # noqa: PLC0415
        encode_dss_signature)

    jetzt = time.time() if jetzt is None else jetzt
    teile = str(jws or "").split(".")
    if len(teile) != 3:
        raise NichtEcht("Das ist kein JWS (drei Teile erwartet)")
    try:
        kopf = json.loads(_b64(teile[0]))
        rumpf = json.loads(_b64(teile[1]))
        signatur = _b64(teile[2])
    except Exception as ex:  # noqa: BLE001
        raise NichtEcht("JWS lässt sich nicht lesen") from ex
    if kopf.get("alg") != "ES256":
        raise NichtEcht(f"Unerwartetes Verfahren: {kopf.get('alg')!r}")
    if len(signatur) != 64:
        raise NichtEcht("Signatur hat nicht die Länge einer ES256-Signatur")
    blatt = _kette_pruefen(kopf.get("x5c") or [], jetzt)
    schluessel = blatt.public_key()
    if not isinstance(schluessel, ec.EllipticCurvePublicKey):
        raise NichtEcht("Das Blattzertifikat trägt keinen EC-Schlüssel")
    # JWS schreibt r‖s, X.509 erwartet DER — umpacken, nicht umdeuten.
    roh = encode_dss_signature(int.from_bytes(signatur[:32], "big"),
                               int.from_bytes(signatur[32:], "big"))
    try:
        schluessel.verify(roh, f"{teile[0]}.{teile[1]}".encode(),
                          ec.ECDSA(hashes.SHA256()))
    except Exception as ex:  # noqa: BLE001
        raise NichtEcht("Die Signatur stimmt nicht") from ex
    if not isinstance(rumpf, dict):
        raise NichtEcht("Der Inhalt ist kein Objekt")
    buendel = rumpf.get("bundleId") or (rumpf.get("data") or {}).get("bundleId")
    if buendel and buendel != BUENDEL:
        raise NichtEcht(f"Fremdes Bündel: {buendel!r}")
    return rumpf


def stufe_aus_beleg(inhalt: dict) -> tuple[str | None, dict]:
    """Welche Stufe gilt — und was davon in die Datenbank gehört.

    Rückgabe `(stufe, felder)`. `stufe` ist None, wenn der Beleg KEINEN
    laufenden Zugang mehr belegt (gekündigt und abgelaufen, zurückerstattet,
    hochgestuft auf etwas, das wir nicht kennen). `felder` trägt immer
    `apple_abo` (die originalTransactionId — der Faden, der ein Abo über
    Verlängerungen, Stufenwechsel und Gerätewechsel hinweg zusammenhält) und
    `apple_produkt`.
    """
    produkt = str(inhalt.get("productId") or "")
    original = str(inhalt.get("originalTransactionId") or "")
    felder = {"apple_abo": original or None, "apple_produkt": produkt or None}
    stufe = paket.stufe_fuer_produkt(produkt)
    if inhalt.get("revocationDate") or inhalt.get("revocationReason") is not None:
        return None, felder          # zurückerstattet: der Zugang endet sofort
    ablauf = inhalt.get("expiresDate")
    if ablauf is not None:
        try:
            # Apple zählt in Millisekunden seit 1970.
            if float(ablauf) / 1000.0 <= time.time():
                return None, felder
        except (TypeError, ValueError):
            raise NichtEcht(f"expiresDate ist keine Zahl: {ablauf!r}") from None
    return stufe, felder
