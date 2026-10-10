"""Apples signierte Belege prüfen (apple_abo.py, seit 10.10.2026).

Der Rumpf eines JWS ist Base64, nicht Verschlüsselung. Wer `/api/abo/apple`
einen selbst gebauten Rumpf schicken kann, schenkt sich 100 GB — deshalb
sind die Negativkontrollen hier die eigentliche Messung, nicht der
Glücksfall.

Die Kette, mit der der Gutfall geprüft wird, baut die Suite selbst
(`apple_hilfe.kette`) und tauscht dafür in genau einem Punkt die erwartete
Wurzel. Dass dieselbe Kette OHNE den Tausch abgewiesen wird, steht in
`test_eigene_kette_wird_abgewiesen` — ohne diesen Test wäre der Gutfall
wertlos.
"""
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import apple_abo  # noqa: E402
import paket  # noqa: E402

from apple_hilfe import jws, kette, ms  # noqa: E402

JETZT = dt.datetime.now(dt.timezone.utc)
PRODUKT = paket.STUFEN["mittel"]["apple"]


def _beleg(**kw) -> dict:
    rumpf = {"bundleId": apple_abo.BUENDEL, "productId": PRODUKT,
             "originalTransactionId": "2000000111222333",
             "transactionId": "2000000111222444",
             "expiresDate": ms(JETZT + dt.timedelta(days=30))}
    rumpf.update(kw)
    return rumpf


@pytest.fixture
def echt(monkeypatch):
    """Eine eigene Kette, die als die erwartete Wurzel gilt.

    Alles außer der Identität der Wurzel läuft unverändert: Kettenbau,
    Aussteller-Vergleich, Laufzeiten, jede Zertifikatssignatur und die
    Signatur über dem JWS."""
    x5c, schluessel, wurzel = kette()
    monkeypatch.setattr(apple_abo, "_wurzel_laden", lambda: wurzel)
    return x5c, schluessel


# ---------------------------------------------------------------------------
# Die Wurzel
# ---------------------------------------------------------------------------

def test_die_mitgelieferte_wurzel_ist_apples_und_passt_zum_abdruck():
    """Die Datei im Repo und der Fingerabdruck im Code müssen zueinander
    gehören — sonst prüft der Server gegen etwas Unbekanntes."""
    wurzel = apple_abo._wurzel_laden()
    cn = wurzel.subject.rfc4514_string()
    assert "Apple Root CA - G3" in cn
    assert wurzel.subject == wurzel.issuer          # selbstsigniert
    assert wurzel.not_valid_after_utc.year == 2039


def test_vertauschte_wurzel_wird_bemerkt(monkeypatch, tmp_path):
    """Eine andere Datei an derselben Stelle darf NICHT benutzt werden.
    Eine Signaturprüfung gegen eine unbekannte Wurzel ist keine Prüfung."""
    from cryptography.hazmat.primitives.serialization import Encoding
    _x5c, _k, fremde = kette()
    ersatz = tmp_path / "gefaelscht.cer"
    ersatz.write_bytes(fremde.public_bytes(Encoding.DER))
    monkeypatch.setattr(apple_abo, "WURZEL", ersatz)
    with pytest.raises(apple_abo.NichtEcht, match="nicht das erwartete"):
        apple_abo._wurzel_laden()


def test_fehlende_wurzeldatei_sagt_es(monkeypatch, tmp_path):
    monkeypatch.setattr(apple_abo, "WURZEL", tmp_path / "gibtsnicht.cer")
    with pytest.raises(apple_abo.NichtEcht, match="fehlt"):
        apple_abo._wurzel_laden()


# ---------------------------------------------------------------------------
# Negativkontrollen — der Kern
# ---------------------------------------------------------------------------

def test_eigene_kette_wird_abgewiesen():
    """DIE Messung: eine vollständig gültige, selbst gebaute Kette, mit
    allem richtig signiert — und trotzdem Nein, weil sie nicht bei Apple
    endet. Fällt dieser Test, ist jeder andere hier wertlos."""
    x5c, schluessel, _wurzel = kette()
    with pytest.raises(apple_abo.NichtEcht, match="endet nicht bei Apple"):
        apple_abo.pruefen(jws(_beleg(), x5c, schluessel))


def test_nur_der_rumpf_ohne_signatur_reicht_nicht():
    import base64, json  # noqa: PLC0415
    roh = base64.urlsafe_b64encode(json.dumps(_beleg()).encode()).rstrip(b"=").decode()
    for versuch in (roh, f".{roh}.", f"x.{roh}.y"):
        with pytest.raises(apple_abo.NichtEcht):
            apple_abo.pruefen(versuch)


def test_veraenderter_rumpf_faellt_auf(echt):
    """Dieselbe Kette, dieselbe Signatur — aber die Stufe hochgeschrieben."""
    x5c, schluessel = echt
    gut = jws(_beleg(), x5c, schluessel)
    kopf, rumpf, sig = gut.split(".")
    import base64, json  # noqa: PLC0415
    gross = _beleg(productId=paket.STUFEN["gross"]["apple"])
    gefaelscht = base64.urlsafe_b64encode(
        json.dumps(gross).encode()).rstrip(b"=").decode()
    with pytest.raises(apple_abo.NichtEcht, match="Signatur stimmt nicht"):
        apple_abo.pruefen(f"{kopf}.{gefaelscht}.{sig}")


def test_kaputte_signatur_faellt_auf(echt):
    x5c, schluessel = echt
    with pytest.raises(apple_abo.NichtEcht, match="Signatur stimmt nicht"):
        apple_abo.pruefen(jws(_beleg(), x5c, schluessel, signatur_kaputt=True))


@pytest.mark.parametrize("alg", ["none", "HS256", "RS256", "ES384", ""])
def test_nur_es256(echt, alg):
    """`alg: none` ist der klassische JWT-Angriff — er darf nicht einmal
    bis zur Kette kommen."""
    x5c, schluessel = echt
    with pytest.raises(apple_abo.NichtEcht, match="Unerwartetes Verfahren"):
        apple_abo.pruefen(jws(_beleg(), x5c, schluessel, alg=alg))


def test_fremdes_buendel_wird_abgewiesen(echt):
    x5c, schluessel = echt
    beleg = _beleg(bundleId="com.fremd.app")
    with pytest.raises(apple_abo.NichtEcht, match="Fremdes Bündel"):
        apple_abo.pruefen(jws(beleg, x5c, schluessel))


def test_abgelaufenes_blattzertifikat(monkeypatch):
    x5c, schluessel, wurzel = kette(
        blatt_von=JETZT - dt.timedelta(days=30),
        blatt_bis=JETZT - dt.timedelta(days=1))
    monkeypatch.setattr(apple_abo, "_wurzel_laden", lambda: wurzel)
    with pytest.raises(apple_abo.NichtEcht, match="nicht \\(mehr\\) gültig"):
        apple_abo.pruefen(jws(_beleg(), x5c, schluessel))


def test_kette_ohne_zwischenzertifikat(echt):
    x5c, schluessel = echt
    with pytest.raises(apple_abo.NichtEcht, match="x5c"):
        apple_abo.pruefen(jws(_beleg(), x5c[:1], schluessel))


def test_blatt_und_wurzel_ohne_das_glied_dazwischen(echt):
    """Die Kette muss zusammenhängen — nicht nur anfangen und enden."""
    x5c, schluessel = echt
    with pytest.raises(apple_abo.NichtEcht, match="bricht"):
        apple_abo.pruefen(jws(_beleg(), [x5c[0], x5c[2]], schluessel))


def test_fremdes_blatt_in_echter_kette(echt):
    """Ein Blatt, das nicht vom Zwischenzertifikat ausgestellt wurde."""
    x5c, _schluessel = echt
    fremd_x5c, fremd_schluessel, _w = kette()
    gemischt = [fremd_x5c[0], x5c[1], x5c[2]]
    with pytest.raises(apple_abo.NichtEcht):
        apple_abo.pruefen(jws(_beleg(), gemischt, fremd_schluessel))


# ---------------------------------------------------------------------------
# Die Entwicklungs-Wurzel (StoreKit-Testkäufe aus Xcode)
# ---------------------------------------------------------------------------

def test_ohne_schalter_gilt_nur_apple():
    """Der Normalfall und der Live-Stand: APPLE_TEST_WURZEL ist leer, und
    eine fremde Kette kommt nicht durch — auch keine von Xcode."""
    assert apple_abo.TEST_WURZEL == ""
    assert apple_abo._test_wurzel_laden() is None
    x5c, schluessel, _w = kette()
    with pytest.raises(apple_abo.NichtEcht, match="endet nicht bei Apple"):
        apple_abo.pruefen(jws(_beleg(), x5c, schluessel))


def test_mit_schalter_kommt_genau_diese_wurzel_durch(monkeypatch, tmp_path):
    from cryptography.hazmat.primitives.serialization import Encoding
    x5c, schluessel, wurzel = kette()
    datei = tmp_path / "entwicklung.cer"
    datei.write_bytes(wurzel.public_bytes(Encoding.DER))
    monkeypatch.setattr(apple_abo, "TEST_WURZEL", str(datei))
    beleg = _beleg()
    assert apple_abo.pruefen(jws(beleg, x5c, schluessel)) == beleg


def test_der_schalter_oeffnet_nicht_fuer_jede_kette(monkeypatch, tmp_path):
    """DIE Messung zum Schalter: er lässt GENAU die eingestellte Wurzel
    durch, keine andere. Sonst wäre er ein offenes Tor."""
    from cryptography.hazmat.primitives.serialization import Encoding
    _x5c, _k, erlaubt = kette()
    datei = tmp_path / "entwicklung.cer"
    datei.write_bytes(erlaubt.public_bytes(Encoding.DER))
    monkeypatch.setattr(apple_abo, "TEST_WURZEL", str(datei))
    fremd_x5c, fremd_schluessel, _andere = kette()
    with pytest.raises(apple_abo.NichtEcht, match="endet nicht bei Apple"):
        apple_abo.pruefen(jws(_beleg(), fremd_x5c, fremd_schluessel))


def test_ein_falscher_pfad_oeffnet_nichts(monkeypatch, tmp_path):
    monkeypatch.setattr(apple_abo, "TEST_WURZEL", str(tmp_path / "gibtsnicht"))
    x5c, schluessel, _w = kette()
    with pytest.raises(apple_abo.NichtEcht, match="endet nicht bei Apple"):
        apple_abo.pruefen(jws(_beleg(), x5c, schluessel))


def test_der_schalter_haengt_signatur_und_laufzeit_nicht_aus(monkeypatch, tmp_path):
    """Auch mit Entwicklungs-Wurzel wird jede Signatur geprüft."""
    from cryptography.hazmat.primitives.serialization import Encoding
    x5c, schluessel, wurzel = kette()
    datei = tmp_path / "entwicklung.cer"
    datei.write_bytes(wurzel.public_bytes(Encoding.DER))
    monkeypatch.setattr(apple_abo, "TEST_WURZEL", str(datei))
    with pytest.raises(apple_abo.NichtEcht, match="Signatur stimmt nicht"):
        apple_abo.pruefen(jws(_beleg(), x5c, schluessel, signatur_kaputt=True))


def test_xcodes_testwurzel_liegt_da_wo_erwartet():
    """Die Datei, auf die der Schalter im Entwicklungslauf zeigt. Fehlt
    Xcode, wird der Test übersprungen — er misst die Umgebung, nicht babu."""
    from pathlib import Path as _P  # noqa: PLC0415
    pfad = _P("/Applications/Xcode.app/Contents/PlugIns/IDEStoreKitEditor"
              ".ideplugin/Contents/Resources/StoreKitTestCertificate.cer")
    if not pfad.is_file():
        pytest.skip("Xcode liegt hier nicht")
    from cryptography.x509 import load_der_x509_certificate  # noqa: PLC0415
    zert = load_der_x509_certificate(pfad.read_bytes())
    assert "StoreKit" in zert.subject.rfc4514_string()
    # Und sie ist NICHT Apples Wurzel — sonst wäre der Schalter sinnlos.
    assert (zert.public_key().public_numbers()
            != apple_abo._wurzel_laden().public_key().public_numbers())


# ---------------------------------------------------------------------------
# Der Gutfall
# ---------------------------------------------------------------------------

def test_echter_beleg_kommt_durch_und_unveraendert(echt):
    x5c, schluessel = echt
    beleg = _beleg()
    assert apple_abo.pruefen(jws(beleg, x5c, schluessel)) == beleg


def test_beleg_ohne_buendel_im_rumpf_kommt_durch(echt):
    """Die äußere Meldung von Apple trägt `bundleId` erst in `data` — ein
    fehlendes Feld ist kein fremdes Bündel."""
    x5c, schluessel = echt
    aussen = {"notificationType": "DID_RENEW", "data": {"bundleId": apple_abo.BUENDEL}}
    assert apple_abo.pruefen(jws(aussen, x5c, schluessel)) == aussen


def test_buendel_in_data_wird_auch_geprueft(echt):
    x5c, schluessel = echt
    aussen = {"notificationType": "DID_RENEW", "data": {"bundleId": "com.fremd.app"}}
    with pytest.raises(apple_abo.NichtEcht, match="Fremdes Bündel"):
        apple_abo.pruefen(jws(aussen, x5c, schluessel))


# ---------------------------------------------------------------------------
# Vom Beleg zur Stufe
# ---------------------------------------------------------------------------

def test_stufe_aus_laufendem_abo():
    stufe, felder = apple_abo.stufe_aus_beleg(_beleg())
    assert stufe == "mittel"
    assert felder == {"apple_abo": "2000000111222333",
                      "apple_produkt": PRODUKT}


def test_abgelaufenes_abo_gibt_keine_stufe_mehr():
    beleg = _beleg(expiresDate=ms(JETZT - dt.timedelta(minutes=1)))
    stufe, felder = apple_abo.stufe_aus_beleg(beleg)
    assert stufe is None
    # Die Zuordnung bleibt: derselbe Betrieb, nur ohne Platz. Sonst fände
    # die nächste Meldung (Wiedereinstieg) den Betrieb nicht mehr.
    assert felder["apple_abo"] == "2000000111222333"


def test_zurueckerstattetes_abo_endet_sofort():
    for kw in ({"revocationDate": ms(JETZT)}, {"revocationReason": 0}):
        stufe, _f = apple_abo.stufe_aus_beleg(_beleg(**kw))
        assert stufe is None, kw


def test_unbekanntes_produkt_gibt_keine_stufe():
    stufe, felder = apple_abo.stufe_aus_beleg(_beleg(productId="babu.speicher.1000gb"))
    assert stufe is None
    assert felder["apple_produkt"] == "babu.speicher.1000gb"


def test_kaputtes_ablaufdatum_wird_nicht_als_gueltig_gelesen():
    with pytest.raises(apple_abo.NichtEcht):
        apple_abo.stufe_aus_beleg(_beleg(expiresDate="irgendwann"))


def test_abo_ohne_ablaufdatum_gilt():
    """Nicht-erneuernde Käufe tragen kein `expiresDate`."""
    beleg = _beleg()
    del beleg["expiresDate"]
    assert apple_abo.stufe_aus_beleg(beleg)[0] == "mittel"
