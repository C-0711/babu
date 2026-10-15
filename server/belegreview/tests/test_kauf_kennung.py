"""Die Kaufkennung: welcher Kauf zu welchem Betrieb gehört (14.10.2026).

Zwei Lücken schließt sie, und beide sind ohne sie stumm:

**Apples erste Meldung kommt manchmal zuerst.** `api_abo_apple_meldung` fand
den Betrieb bisher nur über die `originalTransactionId`, und die steht erst
in der Datenbank, nachdem die App ihren Kauf gemeldet hat. Kommt Apples
Meldung vorher — oder meldet die App nie, weil das Telefon neu aufgesetzt
wurde und niemand sich angemeldet hat —, ging die Meldung ins Leere.

**Zwei Zugänge auf einem Telefon.** Ein von Apple signierter Beleg ist echt,
sagt aber nichts darüber, WESSEN Kauf er ist. Wer auf demselben iPhone
zwischen zwei Betrieben wechselt, meldete den Kauf des einen beim anderen an.
`mandanten.AppleAboVergeben` fängt erst den zweiten Betrieb — der erste, dem
der Kauf nicht gehört, bekam den Platz.

Die Kennung ist eine UUIDv5 aus Mandantennummer und festem Namensraum
(`paket.kauf_kennung`): dieselbe über Neuinstallation, Gerätewechsel und
Datenbankumzug hinweg, und ohne die Nummer selbst zu zeigen.

Gebaut auf der Welt von `test_geraet_und_apple` — dieselbe eigene
Zertifikatskette, Apple wird nie angerufen.
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import babu_web  # noqa: E402
import mandanten  # noqa: E402
import paket  # noqa: E402

from test_geraet_und_apple import (  # noqa: E402,F401
    JETZT, _anlegen, _beleg, _client, _meldung, _mit_schluessel, welt)


def _stand(mandant_id: int) -> dict:
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        return mandanten.abo_stand(mandant_id, c=c)


# ---------------------------------------------------------------------------
# Die Kennung selbst
# ---------------------------------------------------------------------------

def test_die_kennung_steht_in_api_ich(welt):
    konto = _anlegen(_client())
    daten = _mit_schluessel(konto).get("/api/ich").json()
    assert daten["kauf_kennung"] == paket.kauf_kennung(konto["mandant"])


def test_die_kennung_bleibt_dieselbe(welt):
    """Sonst wäre sie als Wiedererkennung nichts wert."""
    konto = _anlegen(_client())
    client = _mit_schluessel(konto)
    erst = client.get("/api/ich").json()["kauf_kennung"]
    assert client.get("/api/ich").json()["kauf_kennung"] == erst


def test_jeder_betrieb_hat_eine_andere(welt):
    a, b = _anlegen(_client()), _anlegen(_client())
    assert (_mit_schluessel(a).get("/api/ich").json()["kauf_kennung"]
            != _mit_schluessel(b).get("/api/ich").json()["kauf_kennung"])


def test_die_kennung_zeigt_die_betriebsnummer_nicht():
    """Sie geht an Apple. Eine fortlaufende Betriebsnummer hat dort nichts zu
    suchen.

    Geprüft an der reinen Funktion und mit Nummern, die lang genug sind, um
    nicht zufällig in 32 Hexzeichen zu stehen — bei einer einstelligen
    Nummer würde eine Teilstringsuche immer anschlagen und nichts messen.
    """
    for nummer in (19364, 760815, 4711000):
        kennung = paket.kauf_kennung(nummer).replace("-", "")
        assert str(nummer) not in kennung, nummer


def test_die_kennung_haengt_nur_an_der_nummer():
    """Keine Zeit, kein Zufall: dieselbe Nummer gibt für immer dieselbe
    Kennung — auch in einem anderen Prozess, auch nach einem Umzug der
    Datenbank. Darauf beruht der ganze Rückfallweg."""
    assert (paket.kauf_kennung(19364)
            == "a242d9ab-95bb-5fe4-a95d-725b8473cc04")


def test_zwei_nummern_geben_nie_dieselbe_kennung():
    kennungen = {paket.kauf_kennung(n) for n in range(1, 2001)}
    assert len(kennungen) == 2000


# ---------------------------------------------------------------------------
# Der Weg der App: ein Beleg mit fremder Kennung zählt nicht
# ---------------------------------------------------------------------------

def test_fremde_kennung_wird_abgewiesen(welt):
    """Der Fall „zwei Zugänge auf einem Telefon": der Beleg ist echt, der
    Betrieb der falsche."""
    a, b = _anlegen(_client()), _anlegen(_client())
    beleg = _beleg(welt, appAccountToken=paket.kauf_kennung(b["mandant"]))
    r = _mit_schluessel(a).post("/api/abo/apple", json={"signed": beleg})
    assert r.status_code == 409, r.text
    assert _stand(a["mandant"])["paket"] is None
    assert _stand(b["mandant"])["paket"] is None


def test_eigene_kennung_geht_durch(welt):
    konto = _anlegen(_client())
    beleg = _beleg(welt, appAccountToken=paket.kauf_kennung(konto["mandant"]))
    r = _mit_schluessel(konto).post("/api/abo/apple", json={"signed": beleg})
    assert r.status_code == 200, r.text
    assert r.json()["stufe"] == "klein"


def test_kennung_in_grossbuchstaben_geht_auch_durch(welt):
    """Apple schreibt UUIDs mal so, mal so. Daran darf kein Kauf scheitern."""
    konto = _anlegen(_client())
    beleg = _beleg(welt,
                   appAccountToken=paket.kauf_kennung(konto["mandant"]).upper())
    r = _mit_schluessel(konto).post("/api/abo/apple", json={"signed": beleg})
    assert r.status_code == 200, r.text


def test_beleg_ohne_kennung_geht_weiter_durch(welt):
    """Käufe aus der Fassung vor dem 14.10.2026 tragen keine Kennung. Für
    sie gilt wie bisher der angemeldete Zugang — sonst verlöre jemand, der
    schon bezahlt hat, seinen Platz."""
    konto = _anlegen(_client())
    r = _mit_schluessel(konto).post("/api/abo/apple", json={"signed": _beleg(welt)})
    assert r.status_code == 200, r.text
    assert r.json()["stufe"] == "klein"


# ---------------------------------------------------------------------------
# Der Weg von Apple: die Meldung findet den Betrieb allein
# ---------------------------------------------------------------------------

def test_meldung_findet_den_betrieb_ohne_die_app(welt):
    """Der Kern: die App hat NICHTS gemeldet, das Abo steht in keiner Zeile —
    und die Meldung trägt den Platz trotzdem ein."""
    konto = _anlegen(_client())
    assert _stand(konto["mandant"])["paket"] is None
    meldung = _meldung(welt, "SUBSCRIBED",
                       appAccountToken=paket.kauf_kennung(konto["mandant"]))
    r = _client().post("/api/abo/apple/meldung", json={"signedPayload": meldung})
    assert r.status_code == 200, r.text
    assert _stand(konto["mandant"])["paket"] == "klein"


def test_meldung_mit_unbekannter_kennung_traegt_nichts_ein(welt):
    """Negativkontrolle. Ohne sie misst der Test davor nur, dass die Route
    200 sagt."""
    konto = _anlegen(_client())
    meldung = _meldung(welt, "SUBSCRIBED",
                       appAccountToken="11111111-2222-3333-4444-555555555555")
    r = _client().post("/api/abo/apple/meldung", json={"signedPayload": meldung})
    assert r.status_code == 200, r.text          # Apple wiederholt sonst ewig
    assert _stand(konto["mandant"])["paket"] is None


def test_meldung_ohne_kennung_traegt_nichts_ein(welt):
    """Die zweite Negativkontrolle: der Stand von vor dem 14.10.2026."""
    konto = _anlegen(_client())
    r = _client().post("/api/abo/apple/meldung",
                       json={"signedPayload": _meldung(welt, "SUBSCRIBED")})
    assert r.status_code == 200, r.text
    assert _stand(konto["mandant"])["paket"] is None


def test_das_abo_bleibt_vorrang_vor_der_kennung(welt):
    """Steht das Abo schon bei einem Betrieb, entscheidet es — die Kennung
    ist der Rückfall, nicht der Hauptweg. Sonst könnte eine Kennung einen
    bezahlten Platz umhängen."""
    a, b = _anlegen(_client()), _anlegen(_client())
    _mit_schluessel(a).post("/api/abo/apple", json={"signed": _beleg(welt)})
    assert _stand(a["mandant"])["paket"] == "klein"
    neu = _meldung(welt, "DID_RENEW",
                   expiresDate=int((JETZT + dt.timedelta(days=60)).timestamp() * 1000),
                   appAccountToken=paket.kauf_kennung(b["mandant"]))
    r = _client().post("/api/abo/apple/meldung", json={"signedPayload": neu})
    assert r.status_code == 200, r.text
    assert _stand(a["mandant"])["paket"] == "klein"
    assert _stand(b["mandant"])["paket"] is None


def test_nur_betriebe_aus_dem_app_store_kommen_in_frage(welt):
    """Ein Portal-Betrieb kauft nicht über Apple. Er darf über die Kennung
    nie gefunden werden — sonst hinge an einer Zahl aus einem anderen
    Herkunftsweg plötzlich ein Apple-Abo."""
    konto = _anlegen(_client())
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET herkunft = ? WHERE id = ?",
                  ("portal", konto["mandant"]))
        assert mandanten.mandant_aus_kauf_kennung(
            paket.kauf_kennung(konto["mandant"]), c=c) is None


def test_beendete_betriebe_kommen_nicht_in_frage(welt):
    konto = _anlegen(_client())
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET status = ? WHERE id = ?",
                  ("beendet", konto["mandant"]))
        assert mandanten.mandant_aus_kauf_kennung(
            paket.kauf_kennung(konto["mandant"]), c=c) is None


# ---------------------------------------------------------------------------
# Ein Betrieb unter einer KANZLEI darf auch kaufen (15.10.2026)
# ---------------------------------------------------------------------------
#
# Live gefunden beim Aufräumen nach Apples Ablehnung vom 15.10.: zwei Routen
# beantworten die Frage „zu welchem Betrieb gehört dieser Zugang?"
# verschieden.
#
#   /api/ich          -> `babu_web._eigener_mandant` — der Betrieb, dessen
#                        Besitzer dieser Zugang ist, egal unter welcher
#                        Kanzlei er hängt.
#   /api/abo/apple    -> `testmonat.direkt_mandant_von` — NUR die Hauskanzlei
#                        „babu direkt".
#
# Für jeden Betrieb aus „Los geht's" ist das dasselbe. Für einen Betrieb, der
# unter einer Kanzlei liegt, nicht: der Kaufbildschirm erscheint (weil
# /api/ich die Stufen liefert), und die Meldung des Kaufs läuft danach in ein
# 404. Apple hätte abgebucht, und babu hätte den Platz nie eingetragen.
#
# Genau dieser Zugang war Apples Prüfkonto.

def _unter_fremde_kanzlei(konto: dict, name: str = "Kanzlei Fremd") -> int:
    """Den Betrieb dieses Zugangs unter eine andere Kanzlei hängen."""
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        kid = mandanten.kanzlei_anlegen(name, "berater@fremd.de", c=c)
        c.execute("UPDATE mandant SET kanzlei_id=? WHERE id=?",
                  (kid, konto["mandant"]))
    return kid


def test_der_kaufbildschirm_erscheint_auch_unter_einer_kanzlei(welt):
    """Die Voraussetzung: /api/ich liefert die Stufen weiter."""
    konto = _anlegen(_client())
    _unter_fremde_kanzlei(konto)
    daten = _mit_schluessel(konto).get("/api/ich").json()
    assert daten.get("speicher") is not None, daten
    assert len(daten.get("stufen") or []) == 3
    assert daten.get("kauf_kennung")


def test_der_kauf_wird_auch_unter_einer_kanzlei_eingetragen(welt):
    """Der Befund. Vor dem 15.10.2026 antwortete die Route hier 404."""
    konto = _anlegen(_client())
    _unter_fremde_kanzlei(konto)
    r = _mit_schluessel(konto).post("/api/abo/apple",
                                    json={"signed": _beleg(welt)})
    assert r.status_code == 200, r.text
    assert r.json()["stufe"] == "klein"
    assert _stand(konto["mandant"])["paket"] == "klein"


def test_auch_mit_kaufkennung_unter_einer_kanzlei(welt):
    """Die Kennung wird aus derselben Nummer gerechnet — sonst wiese die
    Route den eigenen Kauf als fremden ab."""
    konto = _anlegen(_client())
    _unter_fremde_kanzlei(konto)
    beleg = _beleg(welt, appAccountToken=paket.kauf_kennung(konto["mandant"]))
    r = _mit_schluessel(konto).post("/api/abo/apple", json={"signed": beleg})
    assert r.status_code == 200, r.text


def test_ohne_jeden_betrieb_bleibt_es_bei_404(welt):
    """Negativkontrolle: ein Zugang ohne Mandantenzeile darf keinen Platz
    bekommen — sonst hinge der Kauf an der Default-Box."""
    konto = _anlegen(_client())
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("DELETE FROM mandant WHERE id=?", (konto["mandant"],))
    r = _mit_schluessel(konto).post("/api/abo/apple",
                                    json={"signed": _beleg(welt)})
    assert r.status_code == 404, r.text
