"""Push über Apple und Mails zu Auslagen (babu Expenses D1)."""
import base64
import json
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature  # noqa: E402

import push  # noqa: E402
from auslagen_hilfe import auslagen_welt, einreichen, lea  # noqa: F401,E402
from test_acting_as import _login, welt2  # noqa: F401,E402


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def test_das_token_ist_es256_signiert():
    schluessel = ec.generate_private_key(ec.SECP256R1())
    pem = schluessel.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption())
    t = push.token(jetzt=1_790_000_000, schluessel_pem=pem, key_id="ABC123", team_id="8L87Z2GRSG")
    kopf, inhalt, sig = t.split(".")
    assert json.loads(_b64d(kopf)) == {"alg": "ES256", "kid": "ABC123"}
    assert json.loads(_b64d(inhalt)) == {"iss": "8L87Z2GRSG", "iat": 1_790_000_000}
    roh = _b64d(sig)
    der = encode_dss_signature(int.from_bytes(roh[:32], "big"), int.from_bytes(roh[32:], "big"))
    schluessel.public_key().verify(der, f"{kopf}.{inhalt}".encode(), ec.ECDSA(hashes.SHA256()))


def test_die_anfrage():
    url, kopf, body = push.anfrage("ab" * 32, "Titel", "Text", "sandbox", "io.0711.beleg", "jwt")
    assert url == "https://api.sandbox.push.apple.com/3/device/" + "ab" * 32
    assert kopf["apns-topic"] == "io.0711.beleg" and kopf["authorization"] == "bearer jwt"
    assert json.loads(body)["aps"]["alert"] == {"title": "Titel", "body": "Text"}


def test_ohne_schluessel_ist_push_aus(monkeypatch):
    monkeypatch.delenv("APNS_KEY_ID", raising=False)
    monkeypatch.setattr(push, "_client_fabrik", lambda: (_ for _ in ()).throw(AssertionError("kein Client")))
    assert push.eingerichtet() is False
    assert push.senden_an([{"token": "ab" * 32, "umgebung": "produktion", "thema": "io.0711.beleg"}],
                          "T", "X", loeschen=lambda t: None) == 0


def test_410_loescht_das_geraet(monkeypatch, tmp_path):
    monkeypatch.setattr(push, "eingerichtet", lambda: True)
    monkeypatch.setattr(push, "token", lambda **kw: "jwt")

    class Antwort:
        def __init__(self, code): self.status_code = code

    class Client:
        def __init__(self): self.codes = [200, 410]
        def post(self, url, headers, content): return Antwort(self.codes.pop(0))
        def close(self): pass
    monkeypatch.setattr(push, "_client_fabrik", Client)
    geloescht = []
    geraete = [{"token": "aa" * 32, "umgebung": "produktion", "thema": "io.0711.beleg"},
               {"token": "bb" * 32, "umgebung": "produktion", "thema": "io.0711.beleg"}]
    assert push.senden_an(geraete, "T", "X", loeschen=geloescht.append) == 1
    assert geloescht == ["bb" * 32]


def test_ein_geraet_melden(auslagen_welt):
    nina = _login(auslagen_welt["bw"], auslagen_welt["nina"])
    gut = {"token": "ab" * 32, "umgebung": "sandbox", "thema": "io.0711.beleg"}
    assert nina.post("/api/push/geraet", json=gut).status_code == 200
    assert nina.post("/api/push/geraet", json=dict(gut, token="zz")).status_code == 400
    assert nina.post("/api/push/geraet", json=dict(gut, thema="com.fremd")).status_code == 400


def test_nachrichten_kommen_nach_dem_commit(auslagen_welt, monkeypatch):
    import kern_auslagen  # noqa: PLC0415
    gemeldet = []
    monkeypatch.setattr(kern_auslagen, "_melden", lambda ereignis, an, titel, text: gemeldet.append((ereignis, an)))
    lea_c, nina, _ = lea(auslagen_welt)
    einreichen(lea_c)
    assert gemeldet == [("eingereicht", [auslagen_welt["nina"]])]
    s = nina.get("/api/auslagen", params={"stand": "offen"}).json()["auslagen"][0]["stamm"]
    nina.post(f"/api/auslagen/{s}/freigeben")
    assert gemeldet[-1] == ("freigegeben", ["lea@salon.de"])


def test_mails_lassen_sich_abschalten(auslagen_welt):
    lea_c, _, _ = lea(auslagen_welt)
    assert lea_c.post("/api/auslagen/nachrichten", json={"mail": False}).status_code == 200
    assert auslagen_welt["bw"].db_einstellungen("lea@salon.de")["mail_auslagen"] == "Nein"
