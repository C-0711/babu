"""Testmonat per Ambassador-Code (seit 02.10.2026).

Ein Salon öffnet den Link seiner Ambassadorin und hat SOFORT einen eigenen
Zugang mit eigener Ablage — 30 Tage in vollem Umfang. Ab Tag 31 kann er
alles ansehen, aber nichts mehr erfassen, bis die Verwaltung ihn auf
„gezeichnet" setzt oder verlängert. Entwurf:
docs/superpowers/specs/2026-10-02-testmonat-code-design.md

Die wichtigste Zusage steht in `test_einloesen_schreibt_nie_in_die_default_box`:
ein Testsalon bekommt einen eigenen Mandanten und damit eine eigene Ablage —
nie die eines anderen Betriebs (Vorfall 16.–27.09.2026).
"""
import datetime as dt
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import babu_web  # noqa: E402
import box as bx  # noqa: E402
import boxschreiber  # noqa: E402
import mandanten  # noqa: E402
import testmonat  # noqa: E402

PASSWORT = "ein-langes-passwort-hier"
HEUTE = dt.date.today()


# ————— reine Rechnung —————

def test_stand_ohne_test_ist_none():
    assert testmonat.stand(None, HEUTE) is None
    assert testmonat.stand("", HEUTE) is None


def test_dreissig_tage_inklusive_heute():
    bis = testmonat.ende_fuer_start(dt.date(2026, 10, 2))
    assert bis == dt.date(2026, 10, 31)
    s = testmonat.stand(bis.isoformat(), dt.date(2026, 10, 2))
    assert s == {"bis": "2026-10-31", "tage_uebrig": 30, "vorbei": False}


def test_letzter_tag_zaehlt_noch():
    s = testmonat.stand("2026-10-31", dt.date(2026, 10, 31))
    assert s["tage_uebrig"] == 1 and s["vorbei"] is False


def test_tag_danach_ist_vorbei():
    s = testmonat.stand("2026-10-31", dt.date(2026, 11, 1))
    assert s["tage_uebrig"] == 0 and s["vorbei"] is True


def test_verlaengern_laeuft_ab_heute_wenn_schon_vorbei():
    neu = testmonat.neues_ende("2026-10-01", 14, dt.date(2026, 10, 20))
    assert neu == dt.date(2026, 11, 2)       # heute + 13 → 14 Tage inkl. heute


def test_verlaengern_haengt_an_wenn_noch_laeuft():
    neu = testmonat.neues_ende("2026-10-31", 14, dt.date(2026, 10, 20))
    assert neu == dt.date(2026, 11, 14)


def test_sperre_nur_fuer_schreibende_anfragen():
    vorbei = {"bis": "2026-10-01", "tage_uebrig": 0, "vorbei": True}
    laeuft = {"bis": "2026-10-31", "tage_uebrig": 5, "vorbei": False}
    assert testmonat.sperrt("POST", "/api/aufnahme", vorbei) is True
    assert testmonat.sperrt("DELETE", "/api/beleg/x", vorbei) is True
    assert testmonat.sperrt("GET", "/api/belege", vorbei) is False
    assert testmonat.sperrt("HEAD", "/api/belege", vorbei) is False
    assert testmonat.sperrt("POST", "/api/aufnahme", laeuft) is False
    assert testmonat.sperrt("POST", "/api/aufnahme", None) is False
    # Rückmeldungen bleiben möglich — gerade dann will man schreiben können.
    assert testmonat.sperrt("POST", "/api/rueckmeldung", vorbei) is False
    assert testmonat.sperrt("POST", "/api/rueckmeldungen/7/freigeben", vorbei) is False


# ————— Welt: Default-Box wie heute, Ambassadorin, Verwaltung —————

def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _bare(tmp_path: Path, ziel: Path) -> Path:
    arbeit = tmp_path / f"arbeit-{abs(hash(str(ziel))) % 100000}"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    _git(arbeit, "config", "user.name", "t")
    _git(arbeit, "config", "user.email", "t@l")
    (arbeit / "README.md").write_text(ziel.name)
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "stand")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(ziel)],
                   check=True)
    return ziel


_REMOTES: dict[str, str] = {}


def _login(email: str, passwort: str = PASSWORT) -> TestClient:
    client = TestClient(babu_web.app, base_url="https://testserver")
    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    r = client.post("/api/login", json={"email": email, "passwort": passwort})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(babu_web, "ROLLEN", {})
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(bx, "STORE_WURZEL", tmp_path / "stores")
    monkeypatch.setattr(bx, "KLON_WURZEL", tmp_path / "klone")
    bx.registry_leeren()
    default = _bare(tmp_path, tmp_path / "default.git")
    monkeypatch.setattr(babu_web, "STORE", default)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon-default")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(default))
    monkeypatch.setattr(boxschreiber, "REF", "inspektor/ws-default/babu")
    monkeypatch.setattr(bx, "remote_aus_ref", lambda ref: _REMOTES[ref.strip("/")])
    monkeypatch.setattr(babu_web, "_hintergrund_lesen_starten",
                        lambda pfad, daten, endung, un: None)

    monkeypatch.setenv("BABU_TESTMONAT", "1")
    monkeypatch.delenv("BABU_TEST_JE_CODE_TAG", raising=False)
    monkeypatch.delenv("BABU_TEST_JE_TAG", raising=False)
    monkeypatch.delenv("BABU_TESTFLIGHT_LINK", raising=False)
    monkeypatch.delenv("BABU_APPSTORE_LINK", raising=False)
    monkeypatch.delenv("BABU_DIREKT_INHABER", raising=False)
    babu_web._REG_ZULETZT.clear()  # noqa: SLF001
    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001

    post: list[tuple[str, str, str]] = []
    import postfach
    monkeypatch.setattr(postfach, "senden",
                        lambda an, betreff, text, *, stempel: (
                            post.append((an, betreff, text)) or (True, "ok")))
    monkeypatch.setattr(postfach, "eingerichtet", lambda: True)

    babu_web.nutzer_anlegen("chef@example.org", "Chef", "babu", "admin",
                            passwort=PASSWORT)
    chef = _login("chef@example.org")
    r = chef.post("/api/ambassador", json={"name": "Babs",
                                            "email": "babs@example.org"})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    post.clear()
    yield {"tmp": tmp_path, "default": default, "chef": chef, "code": code,
           "post": post, "bw": babu_web}
    bx.registry_leeren()


def _einloesen(email="meridian@example.org", salon="Salon Meridian", code=None,
               welt=None):
    babu_web._REG_ZULETZT.clear()  # noqa: SLF001 — IP-Bremse je Testschritt
    client = TestClient(babu_web.app, base_url="https://testserver")
    return client.post("/api/ambassador/einloesen",
                       json={"code": code or welt["code"], "salon": salon,
                             "email": email, "agb": True})


def _direkt_mandant(email: str) -> dict | None:
    with babu_web._DB_LOCK, babu_web._db() as c:
        z = c.execute(
            "SELECT m.id, m.name, m.status, m.kontenrahmen, m.test_bis, k.name "
            "FROM mandant m JOIN kanzlei k ON k.id = m.kanzlei_id "
            "WHERE m.besitzer_un=?", (email,)).fetchall()
    assert len(z) <= 1
    return dict(zip(("id", "name", "status", "kontenrahmen", "test_bis",
                     "kanzlei"), z[0])) if z else None


def _box_geben(mandant_id: int, tmp_path: Path, ref: str) -> None:
    _bare(tmp_path, bx.store_aus_ref(ref))
    _REMOTES[ref] = str(bx.store_aus_ref(ref))
    mandanten.box_verknuepfen(mandant_id, ref)


def _test_bis_setzen(mandant_id: int, tag: dt.date | None) -> None:
    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE mandant SET test_bis=? WHERE id=?",
                  (tag.isoformat() if tag else None, mandant_id))


def _passwort_setzen(email: str) -> None:
    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE nutzer SET pw=? WHERE email=?",
                  (babu_web.pw_hash(PASSWORT), email))


BON = "EDEKA\n08.09.2026\nSumme 14,88 EUR\nMwSt 7% 0,97"


def _hochladen(client, name: str):
    return client.post("/api/aufnahme", params={"name": name, "text": BON},
                       content=b"\xff\xd8\xff\xe0bild-" + name.encode())


# ————— Einlösen —————

def test_einloesen_legt_zugang_mandant_und_testmonat_an(welt):
    r = _einloesen(welt=welt)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    konto = babu_web.nutzer_holen("meridian@example.org")
    assert konto and konto["rolle"] == "salon" and not konto["box"]
    m = _direkt_mandant("meridian@example.org")
    assert m["kanzlei"] == testmonat.DIREKT_NAME
    assert m["name"] == "Salon Meridian" and m["status"] == "box_ausstehend"
    assert m["kontenrahmen"] == "SKR04"
    assert m["test_bis"] == testmonat.ende_fuer_start(HEUTE).isoformat()

    with babu_web._DB_LOCK, babu_web._db() as c:
        zuordnung = c.execute("SELECT meilenstein FROM ambassador_salon "
                              "WHERE code=? AND email=?",
                              (welt["code"], "meridian@example.org")).fetchall()
    assert zuordnung == [("testet",)]

    an = [p for p in welt["post"] if p[0] == "meridian@example.org"]
    assert len(an) == 1
    assert "/portal#reset/" in an[0][2] and "30 Tage" in an[0][2]
    assert "Apple-ID" in an[0][2]             # ohne öffentlichen Link: alter Weg


def test_einloesen_schreibt_nie_in_die_default_box(welt):
    assert _einloesen(welt=welt).status_code == 200
    # Solange die eigene Ablage fehlt: ehrlich warten, NIE die Default-Box.
    assert babu_web._hat_ablage("meridian@example.org") is False  # noqa: SLF001
    assert babu_web.box_mitglied("meridian@example.org") is False
    _passwort_setzen("meridian@example.org")
    r = _hochladen(_login("meridian@example.org"), "bon.jpg")
    assert r.status_code == 409, r.text


def test_oeffentlicher_testflight_link_steht_in_der_mail(welt, monkeypatch):
    monkeypatch.setenv("BABU_TESTFLIGHT_LINK", "https://testflight.apple.com/join/ABCD")
    assert _einloesen(welt=welt).status_code == 200
    text = [p for p in welt["post"] if p[0] == "meridian@example.org"][0][2]
    assert "https://testflight.apple.com/join/ABCD" in text
    assert "Apple-ID-Adresse" not in text


def test_app_store_link_schlaegt_testflight(welt, monkeypatch):
    """Nach Apples Freigabe (Go-live-Plan Phase 6) führt die Mail in den Store."""
    monkeypatch.setenv("BABU_TESTFLIGHT_LINK", "https://testflight.apple.com/join/ABCD")
    monkeypatch.setenv("BABU_APPSTORE_LINK", "https://apps.apple.com/de/app/id6811956687")
    assert _einloesen(welt=welt).status_code == 200
    text = [p for p in welt["post"] if p[0] == "meridian@example.org"][0][2]
    assert "https://apps.apple.com/de/app/id6811956687" in text
    assert "testflight" not in text.lower()


def test_nina_bekommt_eine_kopie(welt, monkeypatch):
    monkeypatch.setattr(babu_web, "SUPPORT_MAIL", "support@example.org")
    assert _einloesen(welt=welt).status_code == 200
    kopie = [p for p in welt["post"] if p[0] == "support@example.org"]
    assert kopie and "Salon Meridian" in kopie[0][2] and "Babs" in kopie[0][2]


def test_ohne_schalter_gibt_es_den_weg_nicht(welt, monkeypatch):
    monkeypatch.setenv("BABU_TESTMONAT", "0")
    assert _einloesen(welt=welt).status_code == 404
    assert babu_web.nutzer_holen("meridian@example.org") is None


def test_inaktiver_code_legt_nichts_an(welt):
    r = _einloesen(code="GIBT-ES-NICHT", welt=welt)
    assert r.status_code == 404
    assert babu_web.nutzer_holen("meridian@example.org") is None


def test_salonname_und_mail_sind_pflicht(welt):
    assert _einloesen(salon="", welt=welt).status_code == 400
    assert _einloesen(email="kein-at-zeichen", welt=welt).status_code == 400


def test_bestehendes_konto_bekommt_keinen_zweiten_test(welt):
    babu_web.nutzer_anlegen("alt@example.org", "", "Salon Alt", "salon",
                            passwort=PASSWORT)
    r = _einloesen(email="alt@example.org", salon="Salon Alt", welt=welt)
    assert r.status_code == 200          # dieselbe Antwort: kein Konto-Orakel
    assert _direkt_mandant("alt@example.org") is None
    an = [p for p in welt["post"] if p[0] == "alt@example.org"]
    # Seit 08.10.2026: ein bestehender, noch nicht verbundener Salon bekommt
    # statt des bloßen Hinweises die Bitte, sich mit der Ambassadorin zu
    # verbinden — weiterhin ohne zweiten Testmonat.
    assert len(an) == 1 and "/verbinden/" in an[0][2]


def test_bestehendes_konto_ohne_salon_bekommt_nur_den_hinweis(welt):
    babu_web.nutzer_anlegen("buero@example.org", "", "Büro", "kanzlei",
                            passwort=PASSWORT, box=False)
    r = _einloesen(email="buero@example.org", salon="Büro", welt=welt)
    assert r.status_code == 200
    an = [p for p in welt["post"] if p[0] == "buero@example.org"]
    assert len(an) == 1 and "schon einen Zugang" in an[0][2]


def test_zweimal_einloesen_bleibt_ein_zugang(welt):
    assert _einloesen(welt=welt).status_code == 200
    assert _einloesen(welt=welt).status_code == 200
    with babu_web._DB_LOCK, babu_web._db() as c:
        assert c.execute("SELECT COUNT(*) FROM mandant WHERE besitzer_un=?",
                         ("meridian@example.org",)).fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM ambassador_salon WHERE email=?",
                         ("meridian@example.org",)).fetchone()[0] == 1


def test_grenze_je_code_und_tag(welt, monkeypatch):
    monkeypatch.setenv("BABU_TEST_JE_CODE_TAG", "2")
    assert _einloesen(email="a@example.org", welt=welt).status_code == 200
    assert _einloesen(email="b@example.org", welt=welt).status_code == 200
    r = _einloesen(email="c@example.org", welt=welt)
    assert r.status_code == 429
    assert babu_web.nutzer_holen("c@example.org") is None


def test_grenze_insgesamt_je_tag(welt, monkeypatch):
    monkeypatch.setenv("BABU_TEST_JE_TAG", "1")
    r = welt["chef"].post("/api/ambassador", json={"name": "Moe",
                                                    "email": "moe@example.org"})
    zweiter_code = r.json()["code"]
    assert _einloesen(email="a@example.org", welt=welt).status_code == 200
    r = _einloesen(email="b@example.org", code=zweiter_code, welt=welt)
    assert r.status_code == 429


def test_landing_zeigt_den_testmonat_weg_nur_mit_schalter(welt, monkeypatch):
    client = TestClient(babu_web.app, base_url="https://testserver")
    seite = client.get(f"/ambassador/{welt['code']}/salon").text
    assert "/api/ambassador/einloesen" in seite
    monkeypatch.setenv("BABU_TESTMONAT", "0")
    seite = client.get(f"/ambassador/{welt['code']}/salon").text
    assert "/api/ambassador/einloesen" not in seite and "/api/warteliste" in seite


# ————— Tag 31: nur noch ansehen —————

def _testsalon_mit_box(welt, bis: dt.date | None) -> tuple[int, TestClient]:
    assert _einloesen(welt=welt).status_code == 200
    m = _direkt_mandant("meridian@example.org")
    _box_geben(m["id"], welt["tmp"], f"babu/salon-meridian-{m['id']}/belege")
    _test_bis_setzen(m["id"], bis)
    _passwort_setzen("meridian@example.org")
    return m["id"], _login("meridian@example.org")


def test_im_testmonat_geht_alles(welt):
    _, client = _testsalon_mit_box(welt, HEUTE)
    assert _hochladen(client, "bon.jpg").status_code == 200


def test_nach_dem_testmonat_nur_noch_ansehen(welt):
    _, client = _testsalon_mit_box(welt, HEUTE - dt.timedelta(days=1))
    r = _hochladen(client, "bon.jpg")
    assert r.status_code == 403, r.text
    assert r.json()["testmonat_vorbei"] is True
    assert "Testmonat" in r.json()["fehler"]
    assert client.get("/api/belege").status_code == 200


def test_gezeichnet_oeffnet_wieder(welt):
    mid, client = _testsalon_mit_box(welt, HEUTE - dt.timedelta(days=3))
    r = welt["chef"].post("/api/ambassador/meilenstein", json={
        "code": welt["code"], "email": "meridian@example.org",
        "meilenstein": "gezeichnet", "betrag": 237})
    assert r.status_code == 200, r.text
    assert _direkt_mandant("meridian@example.org")["test_bis"] is None
    assert _hochladen(client, "bon.jpg").status_code == 200


def test_verlaengern_oeffnet_wieder(welt):
    mid, client = _testsalon_mit_box(welt, HEUTE - dt.timedelta(days=3))
    r = welt["chef"].post("/api/ambassador/verlaengern",
                          json={"email": "meridian@example.org", "tage": 14})
    assert r.status_code == 200, r.text
    assert r.json()["testmonat"]["tage_uebrig"] == 14
    assert _hochladen(client, "bon.jpg").status_code == 200


def test_verlaengern_nur_fuer_die_verwaltung(welt):
    _testsalon_mit_box(welt, HEUTE - dt.timedelta(days=3))
    client = _login("meridian@example.org")
    r = client.post("/api/ambassador/verlaengern",
                    json={"email": "meridian@example.org", "tage": 14})
    assert r.status_code == 403


def test_verlaengern_kennt_nur_testsalons(welt):
    r = welt["chef"].post("/api/ambassador/verlaengern",
                          json={"email": "niemand@example.org", "tage": 14})
    assert r.status_code == 404
    r = welt["chef"].post("/api/ambassador/verlaengern",
                          json={"email": "x@example.org", "tage": 0})
    assert r.status_code == 400


def test_kanzlei_mandant_ohne_test_bleibt_unberuehrt(welt):
    """Bestand und Kanzlei-Mandanten haben kein test_bis — für sie ändert sich nichts."""
    babu_web.nutzer_anlegen("buero@kanzlei.de", "Büro", "Kanzlei", "kanzlei",
                            passwort=PASSWORT)
    babu_web.nutzer_anlegen("kunde@salon.de", "", "Salon K", "salon",
                            passwort=PASSWORT, box=False)
    kid = mandanten.kanzlei_anlegen("Kanzlei Süd", "buero@kanzlei.de")
    mid = mandanten.mandant_anlegen(kid, "Salon K", "kunde@salon.de")
    _box_geben(mid, welt["tmp"], "babu/salon-k/belege")
    assert _hochladen(_login("kunde@salon.de"), "bon.jpg").status_code == 200


# ————— Anzeigen —————

def test_ich_nennt_den_testmonat(welt):
    _, client = _testsalon_mit_box(welt, HEUTE + dt.timedelta(days=4))
    d = client.get("/api/ich").json()
    assert d["testmonat"] == {"bis": (HEUTE + dt.timedelta(days=4)).isoformat(),
                              "tage_uebrig": 5, "vorbei": False}


def test_ich_ohne_test_ohne_feld(welt):
    assert "testmonat" not in welt["chef"].get("/api/ich").json()


def test_ambassadorin_sieht_die_resttage(welt):
    _testsalon_mit_box(welt, HEUTE + dt.timedelta(days=17))
    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE nutzer SET pw=? WHERE email=?",
                  (babu_web.pw_hash(PASSWORT), "babs@example.org"))
    salons = _login("babs@example.org").get("/api/ambassador/me").json()["salons"]
    assert salons[0]["testmonat"]["tage_uebrig"] == 18
    liste = welt["chef"].get("/api/ambassador/liste").json()["ambassadorinnen"]
    assert liste[0]["salons"][0]["testmonat"]["tage_uebrig"] == 18


# ————— Warteliste: eigener Mandant statt Default-Box —————

def test_warteliste_einrichten_gibt_eine_eigene_ablage(welt):
    client = TestClient(babu_web.app, base_url="https://testserver")
    babu_web._REG_ZULETZT.clear()  # noqa: SLF001
    assert client.post("/api/warteliste", json={
        "email": "pilot@example.org", "art": "salon",
        "salon": "Salon Pilot"}).status_code == 200
    r = welt["chef"].post("/api/warteliste/einrichten",
                          json={"email": "pilot@example.org", "art": "salon"})
    assert r.status_code == 200, r.text
    assert r.json()["startpasswort"]
    konto = babu_web.nutzer_holen("pilot@example.org")
    assert not konto["box"]
    m = _direkt_mandant("pilot@example.org")
    assert m["kanzlei"] == testmonat.DIREKT_NAME and m["test_bis"] is None
    assert babu_web._hat_ablage("pilot@example.org") is False  # noqa: SLF001


def test_es_gibt_genau_eine_hauskanzlei(welt):
    assert _einloesen(email="a@example.org", welt=welt).status_code == 200
    assert _einloesen(email="b@example.org", welt=welt).status_code == 200
    with babu_web._DB_LOCK, babu_web._db() as c:
        assert c.execute("SELECT COUNT(*) FROM kanzlei WHERE name=?",
                         (testmonat.DIREKT_NAME,)).fetchone()[0] == 1


# ————— Kennzahlen der Ambassadorin —————

def test_kennzahlen_der_ambassadorin(welt):
    _einloesen(email="a@example.org", salon="Salon A", welt=welt)
    _einloesen(email="b@example.org", salon="Salon B", welt=welt)
    _einloesen(email="c@example.org", salon="Salon C", welt=welt)
    _test_bis_setzen(_direkt_mandant("b@example.org")["id"],
                     HEUTE - dt.timedelta(days=1))
    welt["chef"].post("/api/ambassador/meilenstein", json={
        "code": welt["code"], "email": "c@example.org",
        "meilenstein": "gezeichnet", "betrag": 237})
    # dazu einer über den alten Wartelisten-Weg, noch ohne Zugang
    babu_web._REG_ZULETZT.clear()  # noqa: SLF001
    TestClient(babu_web.app, base_url="https://testserver").post(
        "/api/warteliste", json={"email": "d@example.org", "art": "salon",
                                 "salon": "Salon D",
                                 "bemerkung": f"Code {welt['code']}"})
    liste = welt["chef"].get("/api/ambassador/liste").json()["ambassadorinnen"]
    assert liste[0]["zahlen"] == {"eingeladen": 4, "wartet": 1, "testet": 1,
                                  "abgelaufen": 1, "gezeichnet": 1, "gehalten": 0}


def test_neue_ambassadorin_haengt_nicht_an_der_default_box(welt):
    assert babu_web.nutzer_holen("babs@example.org")["box"] is False
    assert babu_web.box_mitglied("babs@example.org") is False


# ————— Postgres-Fallen (Befund 02.10.2026) —————

def test_kein_sqlite_eigenes_insert_im_servercode():
    """`INSERT OR IGNORE`/`OR REPLACE` kennt Postgres nicht — die DB-Schicht
    übersetzt nur Platzhalter. Daran scheiterte live jede Code-Einlösung
    über die Warteliste (24.09.–02.10.2026). Für Upserts gibt es db.upsert()."""
    import re
    # Eine SQL-Zeichenkette, die mit INSERT OR … beginnt — nicht ein Satz in
    # einem Kommentar, der die Regel erwähnt (audit.py tut das).
    muster = re.compile(r"[\"']{1,3}\s*INSERT\s+OR\s+(IGNORE|REPLACE)")
    for datei in sorted(HIER.parent.glob("*.py")):
        if datei.name == "db.py":
            continue
        treffer = muster.search(datei.read_text(encoding="utf-8"))
        assert treffer is None, f"{datei.name}: {treffer.group(0)!r}"


def test_unbekannter_code_auf_der_warteliste_ordnet_nichts_zu(welt):
    """In Postgres zeigt ambassador_salon.code auf ambassador(code) — ein frei
    getippter Code darf keine Zeile versuchen (dort wäre es ein 500)."""
    babu_web._REG_ZULETZT.clear()  # noqa: SLF001
    r = TestClient(babu_web.app, base_url="https://testserver").post(
        "/api/warteliste", json={"email": "frei@example.org", "art": "salon",
                                 "salon": "Salon Frei", "bemerkung": "Code ERFUNDEN-1234"})
    assert r.status_code == 200, r.text
    with babu_web._DB_LOCK, babu_web._db() as c:
        assert c.execute("SELECT COUNT(*) FROM ambassador_salon WHERE email=?",
                         ("frei@example.org",)).fetchone()[0] == 0


def test_einloesen_braucht_die_zustimmung(welt):
    babu_web._REG_ZULETZT.clear()  # noqa: SLF001
    r = TestClient(babu_web.app, base_url="https://testserver").post(
        "/api/ambassador/einloesen",
        json={"code": welt["code"], "salon": "Salon X", "email": "x@example.org"})
    assert r.status_code == 400 and "zustimmen" in r.json()["fehler"]
    assert babu_web.nutzer_holen("x@example.org") is None


def test_einloesen_merkt_die_fassung_der_texte(welt):
    import recht
    assert _einloesen(welt=welt).status_code == 200
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        details = c.execute("SELECT details FROM audit_log WHERE "
                            "aktion='testmonat_eingeloest'").fetchone()[0]
    assert recht.fassung("agb") in details and recht.fassung("datenschutz") in details


def test_landing_fragt_nach_zustimmung(welt, monkeypatch):
    seite = TestClient(babu_web.app, base_url="https://testserver").get(
        f"/ambassador/{welt['code']}/salon").text
    assert 'name="agb"' in seite and "/agb" in seite and "/datenschutz" in seite


def test_landing_zeigt_bestaetigung_und_fehler(welt, monkeypatch):
    """Bis 08.10.2026 setzte das Formular den Text in ein Element mit
    `display:none` und machte es nie sichtbar: nach dem Einlösen verschwand
    das Formular, und der Salon sah eine leere Karte — bei einem Fehler
    (E-Mail schon vergeben, zu viele Einlösungen) sah er gar nichts."""
    seite = TestClient(babu_web.app, base_url="https://testserver").get(
        f"/ambassador/{welt['code']}/salon").text
    assert 'id="ok"' in seite and 'id="fehler"' in seite
    assert "ok.hidden = false" in seite and "fehler.hidden = false" in seite
    assert ".catch(" in seite                      # keine Verbindung: auch das sagen
    assert "--gc-serif" in seite and 'class="lkarte"' in seite   # Look des Portals
