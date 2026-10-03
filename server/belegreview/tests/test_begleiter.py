"""Der Begleiter der Ambassadorin (seit 03.10.2026).

babu schaut jeden Tag nach ihren Salons, sagt, was zu tun ist, und schreibt
die WhatsApp-Nachricht vor; die Ambassadorin tippt nur. Die Nachricht geht
von IHREM Telefon (wa.me-Link, Variante A — keine Business-API).
Entwurf: Claude-Design-Arbeitsfläche „babu Ambassador-Bereich", Reihe
„Mit Begleiter"; Regeln in `begleiter.py`.
"""
import datetime as dt
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import babu_web  # noqa: E402
import begleiter as bg  # noqa: E402
import kern_ambassador as ka  # noqa: E402

D = dt.date
HEUTE = D(2026, 10, 3)
PASSWORT = "ein-langes-passwort-hier"


# ————— Handynummer → WhatsApp —————

@pytest.mark.parametrize("roh, erwartet", [
    ("0171 234 5678", "491712345678"),
    ("+49 171 2345678", "491712345678"),
    ("0049 (171) 234-56-78", "491712345678"),
    ("01712345678", "491712345678"),
    ("+43 664 1234567", "436641234567"),
])
def test_nummer_wird_international(roh, erwartet):
    assert bg.nummer(roh) == erwartet


@pytest.mark.parametrize("roh", ["", "abc", "12", "0171", "+49 171 2345678 999 999 999"])
def test_unsinnige_nummer(roh):
    assert bg.nummer(roh) is None


def test_whatsapp_link_traegt_text():
    url = bg.whatsapp("0171 234 5678", "Hallo Sabine, & mehr")
    teile = urlparse(url)
    assert teile.netloc == "wa.me" and teile.path == "/491712345678"
    assert parse_qs(teile.query)["text"] == ["Hallo Sabine, & mehr"]


def test_anzeige_der_nummer():
    assert bg.anzeige("491712345678") == "+49 171 2345678"


# ————— Regeln: was ist heute zu tun? —————

def _kontakt(**neu):
    k = {"telefon": "491712345678", "eingeladen_am": HEUTE - dt.timedelta(days=1),
         "eingeloest_am": None, "test": None, "meilenstein": None,
         "gezeichnet_am": None, "belege": 0, "letzter_beleg": None,
         "erinnert_am": None, "erinnerungen": 0, "erinnert_art": None,
         "weiter_am": None}
    k.update(neu)
    return k


def _test(tage):
    return {"bis": (HEUTE + dt.timedelta(days=tage - 1)).isoformat(),
            "tage_uebrig": max(0, tage), "vorbei": tage <= 0}


def test_frisch_eingeladen_noch_nichts_zu_tun():
    assert bg.aufgabe(_kontakt(), HEUTE) is None


def test_nach_zwei_tagen_nicht_gestartet():
    a = bg.aufgabe(_kontakt(eingeladen_am=HEUTE - dt.timedelta(days=2)), HEUTE)
    assert a["art"] == "nicht_gestartet" and "2 Tagen" in a["grund"]


def test_drei_tage_nach_start_kein_beleg():
    k = _kontakt(eingeladen_am=HEUTE - dt.timedelta(days=5),
                 eingeloest_am=HEUTE - dt.timedelta(days=3), test=_test(27),
                 meilenstein="testet")
    assert bg.aufgabe(k, HEUTE)["art"] == "kein_beleg"


def test_drei_tage_ohne_beleg_hilfe_anbieten():
    k = _kontakt(eingeloest_am=HEUTE - dt.timedelta(days=10), test=_test(20),
                 meilenstein="testet", belege=5,
                 letzter_beleg=HEUTE - dt.timedelta(days=3))
    a = bg.aufgabe(k, HEUTE)
    assert a["art"] == "inaktiv" and a["grund"] == "Seit 3 Tagen kein Beleg"
    assert a["knopf"] == "Hilfe anbieten"


def test_wer_gestern_hochlud_braucht_nichts():
    k = _kontakt(eingeloest_am=HEUTE - dt.timedelta(days=10), test=_test(20),
                 meilenstein="testet", belege=5,
                 letzter_beleg=HEUTE - dt.timedelta(days=1))
    assert bg.aufgabe(k, HEUTE) is None


def test_testende_schlaegt_alles_andere():
    k = _kontakt(eingeloest_am=HEUTE - dt.timedelta(days=25), test=_test(5),
                 meilenstein="testet", belege=0)
    a = bg.aufgabe(k, HEUTE)
    assert a["art"] == "test_endet" and a["grund"] == "Test läuft noch 5 Tage"
    assert a["weitermachen"] is True


def test_letzter_testtag():
    k = _kontakt(eingeloest_am=HEUTE - dt.timedelta(days=29), test=_test(1),
                 meilenstein="testet")
    assert bg.aufgabe(k, HEUTE)["grund"] == "Heute ist der letzte Testtag"


def test_test_vorbei_nur_einmal():
    k = _kontakt(eingeloest_am=HEUTE - dt.timedelta(days=40), test=_test(0),
                 meilenstein="testet")
    assert bg.aufgabe(k, HEUTE)["art"] == "test_vorbei"
    k.update(erinnert_am=HEUTE - dt.timedelta(days=5), erinnerungen=1,
             erinnert_art="test_vorbei")
    assert bg.aufgabe(k, HEUTE) is None


def test_gezeichnet_danke_einmal():
    k = _kontakt(eingeloest_am=HEUTE - dt.timedelta(days=30), meilenstein="gezeichnet",
                 gezeichnet_am=HEUTE - dt.timedelta(days=1), belege=12,
                 letzter_beleg=HEUTE)
    assert bg.aufgabe(k, HEUTE)["art"] == "danke"
    k.update(erinnert_am=HEUTE - dt.timedelta(days=4), erinnerungen=1, erinnert_art="danke")
    assert bg.aufgabe(k, HEUTE) is None


def test_hoechstens_alle_drei_tage():
    k = _kontakt(eingeladen_am=HEUTE - dt.timedelta(days=9),
                 erinnert_am=HEUTE - dt.timedelta(days=2), erinnerungen=1,
                 erinnert_art="nicht_gestartet")
    assert bg.aufgabe(k, HEUTE) is None
    k["erinnert_am"] = HEUTE - dt.timedelta(days=3)
    assert bg.aufgabe(k, HEUTE)["art"] == "nicht_gestartet"


def test_nach_drei_erinnerungen_ist_schluss():
    k = _kontakt(eingeladen_am=HEUTE - dt.timedelta(days=20),
                 erinnert_am=HEUTE - dt.timedelta(days=5), erinnerungen=3,
                 erinnert_art="nicht_gestartet")
    assert bg.aufgabe(k, HEUTE) is None


def test_neue_lage_zaehlt_neu():
    k = _kontakt(eingeloest_am=HEUTE - dt.timedelta(days=4), test=_test(26),
                 meilenstein="testet", erinnert_am=HEUTE - dt.timedelta(days=5),
                 erinnerungen=3, erinnert_art="nicht_gestartet")
    assert bg.aufgabe(k, HEUTE)["art"] == "kein_beleg"


def test_ohne_nummer_kein_auftrag():
    assert bg.aufgabe(_kontakt(telefon=None,
                               eingeladen_am=HEUTE - dt.timedelta(days=5)), HEUTE) is None


def test_weitermachen_gemeldet_dann_ruhe_bis_nina_bucht():
    k = _kontakt(eingeloest_am=HEUTE - dt.timedelta(days=25), test=_test(5),
                 meilenstein="testet", weiter_am=HEUTE - dt.timedelta(days=1))
    assert bg.aufgabe(k, HEUTE) is None


def test_zaehler_fortschreiben():
    assert bg.zaehlen(None, 0, "inaktiv") == 1
    assert bg.zaehlen("inaktiv", 2, "inaktiv") == 3
    assert bg.zaehlen("kein_beleg", 3, "inaktiv") == 1


def test_texte_sind_persoenlich_und_ohne_fachwort():
    for art in bg.ARTEN:
        text = bg.nachricht(art, person="Sabine", ambassadorin="Babs",
                            link="https://mybabu.io/ambassador/X/s", tage=5)
        assert text.startswith("Hallo Sabine,") and text.endswith("Babs")
        for wort in ("Provision", "Stichtag", "Mandant", "Ambassador"):
            assert wort not in text.split("https://")[0]


# ————— Über die Routen —————

def _login(email: str) -> TestClient:
    client = TestClient(babu_web.app, base_url="https://testserver")
    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    r = client.post("/api/login", json={"email": email, "passwort": PASSWORT})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "ROLLEN", {})
    monkeypatch.setattr(babu_web, "SUPPORT_MAIL", "support@example.org")
    monkeypatch.setenv("BABU_TESTMONAT", "1")
    monkeypatch.setattr(ka, "_heute", lambda: HEUTE)
    babu_web._REG_ZULETZT.clear()  # noqa: SLF001
    post: list[tuple[str, str, str]] = []
    import postfach
    monkeypatch.setattr(postfach, "senden",
                        lambda an, betreff, text, *, stempel: (
                            post.append((an, betreff, text)) or (True, "ok")))
    monkeypatch.setattr(postfach, "eingerichtet", lambda: True)
    # Belege der Salons: ohne echte Ablage — die Zählung selbst prüft
    # test_aktivitaet_aus_dem_index.
    aktiv: dict[str, tuple[int, D | None]] = {}
    monkeypatch.setattr(ka, "_aktivitaet", lambda email: aktiv.get(email, (0, None)))
    babu_web.nutzer_anlegen("chef@example.org", "Chef", "babu", "admin", passwort=PASSWORT)
    chef = _login("chef@example.org")
    code = chef.post("/api/ambassador", json={"name": "Babs",
                                              "email": "babs@example.org"}).json()["code"]
    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE nutzer SET pw=? WHERE email=?",
                  (babu_web.pw_hash(PASSWORT), "babs@example.org"))
    post.clear()
    return {"chef": chef, "babs": _login("babs@example.org"), "code": code,
            "post": post, "aktiv": aktiv}


def _einladen(welt, person="Sabine", telefon="0171 234 5678"):
    r = welt["babs"].post("/api/ambassador/link", json={"person": person,
                                                         "telefon": telefon})
    assert r.status_code == 200, r.text
    return r.json()


def _alt_machen(nr: int, tage: int):
    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE ambassador_einladung SET erstellt=? WHERE id=?",
                  ((HEUTE - dt.timedelta(days=tage)).isoformat() + "T09:00:00Z", nr))


def test_einladen_mit_nummer_gibt_whatsapp_link(welt):
    d = _einladen(welt)
    teile = urlparse(d["whatsapp"])
    assert teile.netloc == "wa.me" and teile.path == "/491712345678"
    text = parse_qs(teile.query)["text"][0]
    assert text.startswith("Hallo Sabine,") and d["link"] in text
    # Eindeutiger Link je Einladung — zwei „Sabine" verwechseln sich nicht.
    assert d["link"] != _einladen(welt)["link"]


def test_falsche_nummer_wird_abgewiesen(welt):
    r = welt["babs"].post("/api/ambassador/link", json={"person": "Sabine",
                                                         "telefon": "12"})
    assert r.status_code == 400


def test_heute_zeigt_was_faellig_ist(welt):
    d = _einladen(welt)
    me = welt["babs"].get("/api/ambassador/me").json()
    assert me["heute"] == []
    _alt_machen(d["id"], 2)
    heute = welt["babs"].get("/api/ambassador/me").json()["heute"]
    assert len(heute) == 1 and heute[0]["art"] == "nicht_gestartet"
    assert heute[0]["person"] == "Sabine" and heute[0]["nr"] == d["id"]
    assert parse_qs(urlparse(heute[0]["whatsapp"]).query)["text"][0].startswith("Hallo Sabine,")


def test_gesendet_merken_und_ruhe(welt):
    d = _einladen(welt)
    _alt_machen(d["id"], 2)
    r = welt["babs"].post("/api/ambassador/erinnert",
                          json={"nr": d["id"], "art": "nicht_gestartet"})
    assert r.status_code == 200, r.text
    me = welt["babs"].get("/api/ambassador/me").json()
    assert me["heute"] == []
    kontakt = [k for k in me["kontakte"] if k["nr"] == d["id"]][0]
    assert kontakt["gesendet_am"] == HEUTE.isoformat()


def test_fremde_nummer_nicht_erinnerbar(welt):
    d = _einladen(welt)
    welt["chef"].post("/api/ambassador", json={"name": "Moe", "email": "moe@example.org"})
    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE nutzer SET pw=? WHERE email=?",
                  (babu_web.pw_hash(PASSWORT), "moe@example.org"))
    r = _login("moe@example.org").post("/api/ambassador/erinnert",
                                       json={"nr": d["id"], "art": "nicht_gestartet"})
    assert r.status_code == 404


def test_kontakte_mit_status_und_aktivitaet(welt):
    d = _einladen(welt)
    babu_web._REG_ZULETZT.clear()  # noqa: SLF001
    r = TestClient(babu_web.app, base_url="https://testserver").post(
        "/api/ambassador/einloesen",
        json={"code": welt["code"], "salon": "Salon Meridian",
              "email": "meridian@example.org", "slug": d["link"].rsplit("/", 1)[-1],
              "agb": True})
    assert r.status_code == 200, r.text
    welt["aktiv"]["meridian@example.org"] = (5, HEUTE)
    kontakte = welt["babs"].get("/api/ambassador/me").json()["kontakte"]
    k = [x for x in kontakte if x["nr"] == d["id"]][0]
    assert k["name"] == "Sabine" and k["salon"] == "Salon Meridian"
    assert k["stand"] == "probiert aus"
    assert k["aktiv"] == "5 Belege hochgeladen, zuletzt heute"


def test_drei_tage_ohne_beleg_steht_unter_heute(welt):
    d = _einladen(welt)
    babu_web._REG_ZULETZT.clear()  # noqa: SLF001
    TestClient(babu_web.app, base_url="https://testserver").post(
        "/api/ambassador/einloesen",
        json={"code": welt["code"], "salon": "Salon Meridian",
              "email": "meridian@example.org", "slug": d["link"].rsplit("/", 1)[-1],
              "agb": True})
    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE ambassador_salon SET eingelöst=?",
                  ((HEUTE - dt.timedelta(days=10)).isoformat() + "T09:00:00Z",))
    welt["aktiv"]["meridian@example.org"] = (5, HEUTE - dt.timedelta(days=3))
    heute = welt["babs"].get("/api/ambassador/me").json()["heute"]
    assert [h["art"] for h in heute] == ["inaktiv"]
    assert heute[0]["knopf"] == "Hilfe anbieten"


def test_weitermachen_meldet_nina(welt):
    d = _einladen(welt)
    r = welt["babs"].post("/api/ambassador/weitermachen", json={"nr": d["id"]})
    assert r.status_code == 200, r.text
    an_nina = [p for p in welt["post"] if p[0] == "support@example.org"]
    assert an_nina and "Sabine" in an_nina[0][2] and "Babs" in an_nina[0][2]
    kontakt = [k for k in welt["babs"].get("/api/ambassador/me").json()["kontakte"]
               if k["nr"] == d["id"]][0]
    assert kontakt["stand"] == "will weitermachen"


def test_aktivitaet_aus_dem_index():
    idx = {"belege": {
        "a": {"hochgeladen": "2026-09-28T10:00:00+02:00"},
        "b": {"hochgeladen": "2026-10-01T18:30:00+02:00"},
        "c": {"hochgeladen": None}}}
    assert ka.aktivitaet_aus_index(idx) == (3, D(2026, 10, 1))
    assert ka.aktivitaet_aus_index({"belege": {}}) == (0, None)


# ————— Mit Abo-Weg (seit 03.10.2026) —————

def test_test_lagen_tragen_den_weg_zum_abschluss():
    weg = "https://mybabu.io/portal#abo"
    for art in ("test_endet", "test_vorbei"):
        t = bg.nachricht(art, person="Sonja", ambassadorin="Babs", tage=3,
                                weiter=weg)
        assert weg in t and "Babs" in t
        ohne = bg.nachricht(art, person="Sonja", ambassadorin="Babs", tage=3)
        assert weg not in ohne
    # Andere Lagen bleiben, wie sie sind.
    assert bg.nachricht("kein_beleg", person="S", ambassadorin="B", weiter=weg) \
        == bg.nachricht("kein_beleg", person="S", ambassadorin="B")


# ————— Stand mit Abo (seit 03.10.2026) —————

@pytest.mark.parametrize("abo,meilenstein,wort", [
    ("zahlung_laeuft", "testet", "hat abgeschlossen"),
    ("aktiv", "testet", "hat abgeschlossen"),
    ("aktiv", "gezeichnet", "macht mit"),
    ("zahlung_offen", "gezeichnet", "Zahlung offen"),
    ("gekuendigt", "gehalten", "gekündigt"),
    ("beendet", "gezeichnet", "Abo beendet"),
    (None, "testet", "wartet auf Zugang"),
])
def test_stand_wort_kennt_das_abo(abo, meilenstein, wort):
    k = {"meilenstein": meilenstein, "eingeloest_am": HEUTE, "abo": abo}
    assert ka._stand_wort(k, None) == wort
