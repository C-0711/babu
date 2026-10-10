"""Gerätekonto und Apple-Abo über die Routen (seit 10.10.2026).

Der ganze Weg eines Telefons: App laden → Konto ohne Anmeldung → zehn Belege
frei → gesperrt → Stufe kaufen → wieder Platz → Apple meldet Kündigung →
wieder im Freikontingent. Dazu die beiden Fälle, die wehtun, wenn sie
fehlen: ein gefälschter Kaufbeleg und ein Apple-Abo, das zwei Betrieben
gehören will.

Apple wird nie angerufen: die Belege sind mit einer eigenen Kette signiert
(`apple_hilfe`), und `apple_abo._wurzel_laden` zeigt in der Fixture auf
genau diese Wurzel. Dass eine fremde Kette abgewiesen wird, prüft
`test_apple_abo.py` — hier geht es um die Routen.
"""
import datetime as dt
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import apple_abo  # noqa: E402
import babu_web  # noqa: E402
import kern_geraet  # noqa: E402
import mandanten  # noqa: E402
import paket  # noqa: E402

from apple_hilfe import jws, kette, ms  # noqa: E402

URSPRUNG = "https://testserver"
JETZT = dt.datetime.now(dt.timezone.utc)
GB = paket.GB


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "ROLLEN", {})
    monkeypatch.setattr(babu_web, "PORTAL_ORIGIN", URSPRUNG)
    monkeypatch.setenv("BABU_BETREIBER_MAIL", "nina@0711.io")
    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    kern_geraet._ZULETZT.clear()  # noqa: SLF001
    # Die Bremse gilt je Anschluss; in der Suite kommen alle Anfragen von
    # derselben Adresse, und geprüft wird sie in einem eigenen Test.
    monkeypatch.setattr(kern_geraet, "BREMSE_SEKUNDEN", 0)
    # Die Box legt im Betrieb ein Hintergrundfaden an (git push zum
    # GitChain-Dienst). Hier wird nur festgehalten, DASS er gerufen wird.
    gerufen: list[tuple] = []
    def _box(mid, name):
        gerufen.append((mid, name))
        with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
            mandanten.box_verknuepfen(mid, f"babu/suite-{mid}/belege", c=c)
    monkeypatch.setattr(kern_geraet, "_box_nachziehen", _box)
    x5c, schluessel, wurzel = kette()
    monkeypatch.setattr(apple_abo, "_wurzel_laden", lambda: wurzel)
    yield {"x5c": x5c, "schluessel": schluessel, "box": gerufen}


def _client() -> TestClient:
    return TestClient(babu_web.app, base_url=URSPRUNG)


def _anlegen(client, **kw):
    r = client.post("/api/geraet/anlegen", json={"geraet": "iPhone 17", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _mit_schluessel(konto: dict) -> TestClient:
    c = _client()
    c.headers["Authorization"] = f"Bearer {konto['schluessel']}"
    return c


def _beleg(welt, **kw) -> str:
    rumpf = {"bundleId": apple_abo.BUENDEL,
             "productId": paket.STUFEN["klein"]["apple"],
             "originalTransactionId": "2000000111222333",
             "expiresDate": ms(JETZT + dt.timedelta(days=30))}
    rumpf.update(kw)
    return jws(rumpf, welt["x5c"], welt["schluessel"])


def _meldung(welt, art: str, **kw) -> str:
    innen = _beleg(welt, **kw)
    return jws({"notificationType": art, "data": {
        "bundleId": apple_abo.BUENDEL, "signedTransactionInfo": innen}},
        welt["x5c"], welt["schluessel"])


def _platz_setzen(mandant_id, bytes_belegt=0, belege=0):
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET speicher_bytes=?, belege_gesamt=? "
                  "WHERE id=?", (bytes_belegt, belege, mandant_id))


# ---------------------------------------------------------------------------
# Das Konto entsteht ohne Anmeldung
# ---------------------------------------------------------------------------

def test_telefon_bekommt_konto_betrieb_und_schluessel(welt):
    konto = _anlegen(_client())
    assert konto["un"].startswith("app-")
    assert "@" not in konto["un"]
    assert konto["belege_frei"] == 10
    assert [s["gb"] for s in konto["stufen"]] == [1, 5, 100]
    # Der Schlüssel trägt sofort — ohne Passwort, ohne E-Mail.
    r = _mit_schluessel(konto).get("/api/ich")
    assert r.status_code == 200, r.text
    assert r.json()["un"] == konto["un"]


def test_der_betrieb_ist_ein_mandant_mit_herkunft_app(welt):
    konto = _anlegen(_client())
    m = mandanten.mandant_holen(konto["mandant"])
    assert m["besitzer_un"] == konto["un"]
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        stand = mandanten.abo_stand(konto["mandant"], c=c)
    assert stand["herkunft"] == paket.HERKUNFT_APP
    # Kein Testmonat: die zehn freien Belege sind an seine Stelle getreten.
    assert stand["test_bis"] is None
    assert stand["paket"] is None


def test_die_box_wird_sofort_angefordert_nicht_erst_vom_cron(welt):
    """Ein Telefon, das gerade den ersten Beleg fotografiert, kann nicht
    eine Minute auf den Cron-Anleger warten."""
    konto = _anlegen(_client(), betrieb="Salon Sonne")
    assert welt["box"] == [(konto["mandant"], "Salon Sonne")]


def test_der_schluessel_steht_nur_einmal_im_klartext(welt):
    konto = _anlegen(_client())
    import hashlib  # noqa: PLC0415
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        zeilen = c.execute("SELECT hash, un, geraet FROM app_schluessel "
                           "WHERE un=?", (konto["un"],)).fetchall()
    assert len(zeilen) == 1
    assert zeilen[0][0] == hashlib.sha256(konto["schluessel"].encode()).hexdigest()
    assert zeilen[0][0] != konto["schluessel"]


def test_jedes_telefon_bekommt_einen_eigenen_betrieb(welt):
    a, b = _anlegen(_client()), _anlegen(_client())
    assert a["un"] != b["un"] and a["mandant"] != b["mandant"]
    assert a["schluessel"] != b["schluessel"]


def test_die_bremse_haelt_den_kontengenerator_auf(welt, monkeypatch):
    monkeypatch.setattr(kern_geraet, "BREMSE_SEKUNDEN", 3600)
    client = _client()
    assert client.post("/api/geraet/anlegen", json={}).status_code == 200
    assert client.post("/api/geraet/anlegen", json={}).status_code == 429


def test_ohne_name_ein_platzhalter_der_nicht_peinlich_ist(welt):
    konto = _anlegen(_client(), betrieb="  ")
    assert mandanten.mandant_holen(konto["mandant"])["name"] == "Mein Betrieb"


def test_kurzname_wie_der_cron_anleger():
    """Server und box-anleger.sh müssen für denselben Betrieb denselben
    Verweis bauen — sonst entstehen zwei Boxen."""
    assert kern_geraet.kurzname("Salon Sonne", 7) == "salon-sonne-7"
    assert kern_geraet.kurzname("Müllers Friseurstübchen", 12) == \
        "muellers-friseurstuebchen-12"
    assert kern_geraet.kurzname("A&B  Hair!!", 3) == "a-b-hair-3"
    assert kern_geraet.kurzname("...", 9) == "betrieb-9"
    assert kern_geraet.kurzname("x" * 60, 1) == "x" * 40 + "-1"


# ---------------------------------------------------------------------------
# Die E-Mail kommt später
# ---------------------------------------------------------------------------

def test_email_nachreichen(welt):
    client = _mit_schluessel(_anlegen(_client()))
    r = client.post("/api/konto/email", json={"email": "Nina@Salon.DE"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "nina@salon.de"


def test_kaputte_email_wird_abgewiesen(welt):
    client = _mit_schluessel(_anlegen(_client()))
    for schrott in ("nina", "nina@", "@salon.de", ""):
        r = client.post("/api/konto/email", json={"email": schrott})
        assert r.status_code == 400, schrott


def test_email_geht_auch_wenn_gesperrt_ist(welt):
    """Sie ist der Weg zurück zu den Belegen auf einem neuen Telefon — wer
    am Freikontingent hängt, muss sie hinterlegen können."""
    konto = _anlegen(_client())
    _platz_setzen(konto["mandant"], belege=10)
    r = _mit_schluessel(konto).post("/api/konto/email",
                                    json={"email": "nina@salon.de"})
    assert r.status_code == 200, r.text


def test_email_braucht_den_schluessel(welt):
    _anlegen(_client())
    r = _client().post("/api/konto/email", json={"email": "nina@salon.de"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Zehn frei, dann eine Stufe
# ---------------------------------------------------------------------------

def test_ich_meldet_platz_und_stufen(welt):
    konto = _anlegen(_client())
    _platz_setzen(konto["mandant"], belege=4)
    daten = _mit_schluessel(konto).get("/api/ich").json()
    assert daten["speicher"]["frei_offen"] == 6
    assert daten["speicher"]["voll"] is False
    assert [s["cent"] for s in daten["stufen"]] == [999, 1999, 9900]


def test_nach_zehn_belegen_nur_noch_lesen(welt):
    konto = _anlegen(_client())
    client = _mit_schluessel(konto)
    _platz_setzen(konto["mandant"], belege=10)
    # Lesen geht weiter — die Belege bleiben, wo sie sind.
    assert client.get("/api/belege").status_code == 200
    r = client.post("/api/kassenbuch", json={"tag": "2026-10-10", "zeilen": []})
    assert r.status_code == 403, r.text
    assert "freien Belege" in r.text


def test_der_kauf_geht_auch_wenn_gesperrt_ist(welt):
    """Die Sperre darf nie den Weg blockieren, auf dem man Platz kauft."""
    konto = _anlegen(_client())
    _platz_setzen(konto["mandant"], belege=10)
    r = _mit_schluessel(konto).post("/api/abo/apple",
                                    json={"signed": _beleg(welt)})
    assert r.status_code == 200, r.text
    assert r.json()["stufe"] == "klein"


def test_gekaufte_stufe_gibt_sofort_wieder_platz(welt):
    konto = _anlegen(_client())
    client = _mit_schluessel(konto)
    _platz_setzen(konto["mandant"], belege=10)
    client.post("/api/abo/apple", json={"signed": _beleg(welt)})
    daten = client.get("/api/ich").json()
    assert daten["speicher"]["stufe"] == "klein"
    assert daten["speicher"]["grenze"] == 1 * GB
    assert daten["speicher"]["voll"] is False
    assert client.post("/api/kassenbuch",
                       json={"tag": "2026-10-10", "zeilen": []}).status_code != 403


def test_voller_platz_sperrt_trotz_laufendem_abo(welt):
    konto = _anlegen(_client())
    client = _mit_schluessel(konto)
    client.post("/api/abo/apple", json={"signed": _beleg(welt)})
    _platz_setzen(konto["mandant"], bytes_belegt=1 * GB, belege=2000)
    r = client.post("/api/kassenbuch", json={"tag": "2026-10-10", "zeilen": []})
    assert r.status_code == 403
    assert "Platz ist voll" in r.text
    assert r.json()["grund"] == "speicher_voll"


def test_gefaelschter_kaufbeleg_gibt_keinen_platz(welt):
    """Eine fremde Kette — und der Fehlertext verrät nicht, woran es lag."""
    konto = _anlegen(_client())
    fremd_x5c, fremd_schluessel, _w = kette()
    gefaelscht = jws({"bundleId": apple_abo.BUENDEL,
                      "productId": paket.STUFEN["gross"]["apple"],
                      "originalTransactionId": "9",
                      "expiresDate": ms(JETZT + dt.timedelta(days=30))},
                     fremd_x5c, fremd_schluessel)
    r = _mit_schluessel(konto).post("/api/abo/apple", json={"signed": gefaelscht})
    assert r.status_code == 400
    assert "prüfen" in r.json()["fehler"]
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert mandanten.abo_stand(konto["mandant"], c=c)["paket"] is None


def test_ein_apple_abo_gehoert_genau_einem_betrieb(welt):
    """Sonst zahlt einer, und zwei legen ab."""
    erster, zweiter = _anlegen(_client()), _anlegen(_client())
    beleg = _beleg(welt)
    assert _mit_schluessel(erster).post("/api/abo/apple",
                                        json={"signed": beleg}).status_code == 200
    r = _mit_schluessel(zweiter).post("/api/abo/apple", json={"signed": beleg})
    assert r.status_code == 409, r.text
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert mandanten.abo_stand(zweiter["mandant"], c=c)["paket"] is None


def test_derselbe_beleg_zweimal_vom_selben_betrieb_ist_in_ordnung(welt):
    """StoreKit liefert den Vorgang bei jedem Start erneut — das darf nicht
    als Streit um dasselbe Abo gelten."""
    konto = _anlegen(_client())
    client = _mit_schluessel(konto)
    for _ in range(3):
        assert client.post("/api/abo/apple",
                           json={"signed": _beleg(welt)}).status_code == 200


def test_stufenwechsel_schreibt_die_neue_stufe(welt):
    konto = _anlegen(_client())
    client = _mit_schluessel(konto)
    client.post("/api/abo/apple", json={"signed": _beleg(welt)})
    gross = _beleg(welt, productId=paket.STUFEN["gross"]["apple"])
    r = client.post("/api/abo/apple", json={"signed": gross})
    assert r.json()["stufe"] == "gross"
    assert r.json()["speicher"]["grenze"] == 100 * GB


def test_abo_ohne_schluessel_geht_nicht(welt):
    _anlegen(_client())
    assert _client().post("/api/abo/apple",
                          json={"signed": _beleg(welt)}).status_code == 401


# ---------------------------------------------------------------------------
# Was Apple meldet
# ---------------------------------------------------------------------------

def test_meldung_verlaengert(welt):
    konto = _anlegen(_client())
    _mit_schluessel(konto).post("/api/abo/apple", json={"signed": _beleg(welt)})
    neu = ms(JETZT + dt.timedelta(days=60))
    r = _client().post("/api/abo/apple/meldung",
                       json={"signedPayload": _meldung(welt, "DID_RENEW",
                                                       expiresDate=neu)})
    assert r.status_code == 200, r.text
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert mandanten.abo_stand(konto["mandant"], c=c)["paket"] == "klein"


def test_meldung_abgelaufen_setzt_zurueck_aufs_freikontingent(welt):
    konto = _anlegen(_client())
    client = _mit_schluessel(konto)
    client.post("/api/abo/apple", json={"signed": _beleg(welt)})
    vorbei = ms(JETZT - dt.timedelta(minutes=1))
    r = _client().post("/api/abo/apple/meldung",
                       json={"signedPayload": _meldung(welt, "EXPIRED",
                                                       expiresDate=vorbei)})
    assert r.status_code == 200
    stand = client.get("/api/ich").json()["speicher"]
    assert stand["stufe"] is None
    assert stand["frei_offen"] == 10        # die Belege bleiben, der Platz geht
    # Die Zuordnung bleibt, damit ein Wiedereinstieg den Betrieb findet.
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert mandanten.mandant_mit_apple_abo("2000000111222333", c=c) \
            == konto["mandant"]


def test_meldung_rueckerstattung_nimmt_den_platz_sofort(welt):
    konto = _anlegen(_client())
    client = _mit_schluessel(konto)
    client.post("/api/abo/apple", json={"signed": _beleg(welt)})
    r = _client().post("/api/abo/apple/meldung", json={
        "signedPayload": _meldung(welt, "REFUND", revocationDate=ms(JETZT))})
    assert r.status_code == 200
    assert client.get("/api/ich").json()["speicher"]["stufe"] is None


def test_gefaelschte_meldung_wird_abgewiesen(welt):
    konto = _anlegen(_client())
    _mit_schluessel(konto).post("/api/abo/apple", json={"signed": _beleg(welt)})
    fremd_x5c, fremd_schluessel, _w = kette()
    gefaelscht = jws({"notificationType": "EXPIRED", "data": {
        "bundleId": apple_abo.BUENDEL,
        "signedTransactionInfo": _beleg(welt)}}, fremd_x5c, fremd_schluessel)
    r = _client().post("/api/abo/apple/meldung", json={"signedPayload": gefaelscht})
    assert r.status_code == 400
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert mandanten.abo_stand(konto["mandant"], c=c)["paket"] == "klein"


def test_meldung_zu_einem_unbekannten_abo_ist_kein_fehler(welt):
    """Apples Meldung kann vor der Meldung der App ankommen. Ein 500 hieße:
    Apple versucht es stundenlang erneut."""
    r = _client().post("/api/abo/apple/meldung",
                       json={"signedPayload": _meldung(welt, "SUBSCRIBED")})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_meldung_ohne_vorgang_ist_angekommen(welt):
    aussen = jws({"notificationType": "CONSUMPTION_REQUEST",
                  "data": {"bundleId": apple_abo.BUENDEL}},
                 welt["x5c"], welt["schluessel"])
    r = _client().post("/api/abo/apple/meldung", json={"signedPayload": aussen})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_meldung_braucht_keine_anmeldung_aber_eine_signatur(welt):
    r = _client().post("/api/abo/apple/meldung", json={"signedPayload": "nichts"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Der Zähler
# ---------------------------------------------------------------------------

def test_platz_buchen_zaehlt_nur_aufwaerts(welt):
    konto = _anlegen(_client())
    mid = konto["mandant"]
    mandanten.platz_buchen(mid, 500_000, 1)
    mandanten.platz_buchen(mid, 500_000, 1)
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        stand = mandanten.abo_stand(mid, c=c)
    assert (stand["speicher_bytes"], stand["belege_gesamt"]) == (1_000_000, 2)
    # Der tägliche Lauf zieht die Bytes nach — die Belegzahl nie.
    mandanten.platz_messen(mid, 12_345)
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        stand = mandanten.abo_stand(mid, c=c)
    assert (stand["speicher_bytes"], stand["belege_gesamt"]) == (12_345, 2)


def test_negative_werte_zaehlen_nicht_abwaerts(welt):
    konto = _anlegen(_client())
    mandanten.platz_buchen(konto["mandant"], 1000, 1)
    mandanten.platz_buchen(konto["mandant"], -5000, -3)
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        stand = mandanten.abo_stand(konto["mandant"], c=c)
    assert (stand["speicher_bytes"], stand["belege_gesamt"]) == (1000, 1)
