"""Ambassador-Cockpit (seit 02.10.2026): Pipeline, Einladungen, Geld.

Die Ambassadorin sieht je Kunde die Zeitleiste und den nächsten Schritt,
ihre offenen Einladungen (wer noch nicht eingelöst hat) und ihr Geld: was
verdient, was ausgezahlt ist und was mit dem nächsten Auszahlungslauf
kommt. Auszahlung quartalsweise zum 15. nach Quartalsende, ab 100 €
(Entscheidung Auftraggeber, 02.10.2026). „In Aussicht" gibt es bewusst
nicht, solange die Preise Beispielpreise sind.
"""
import datetime as dt
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import babu_web  # noqa: E402
import kern_ambassador as ka  # noqa: E402

PASSWORT = "ein-langes-passwort-hier"
D = dt.date


# ————— reine Rechnung: der Auszahlungskalender —————

@pytest.mark.parametrize("heute, lauf, stichtag", [
    (D(2026, 10, 2), D(2026, 10, 15), D(2026, 9, 30)),
    (D(2026, 10, 15), D(2026, 10, 15), D(2026, 9, 30)),
    (D(2026, 10, 16), D(2027, 1, 15), D(2026, 12, 31)),
    (D(2026, 12, 31), D(2027, 1, 15), D(2026, 12, 31)),
    (D(2027, 2, 1), D(2027, 4, 15), D(2027, 3, 31)),
    (D(2027, 6, 20), D(2027, 7, 15), D(2027, 6, 30)),
])
def test_naechster_lauf_und_stichtag(heute, lauf, stichtag):
    assert ka.naechster_lauf(heute) == lauf
    assert ka.stichtag(lauf) == stichtag


@pytest.mark.parametrize("heute, lauf", [
    (D(2026, 10, 2), D(2026, 7, 15)),
    (D(2026, 10, 15), D(2026, 10, 15)),
    (D(2027, 1, 14), D(2026, 10, 15)),
])
def test_letzter_faelliger_lauf(heute, lauf):
    assert ka.letzter_lauf(heute) == lauf


def test_drei_monate_spaeter():
    assert ka.monate_spaeter(D(2026, 10, 3), 3) == D(2027, 1, 3)
    assert ka.monate_spaeter(D(2026, 11, 30), 3) == D(2027, 2, 28)


# ————— Welt —————

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
    monkeypatch.setenv("BABU_TESTMONAT", "1")
    babu_web._REG_ZULETZT.clear()  # noqa: SLF001
    post: list[tuple[str, str, str]] = []
    import postfach
    monkeypatch.setattr(postfach, "senden",
                        lambda an, betreff, text, *, stempel: (
                            post.append((an, betreff, text)) or (True, "ok")))
    monkeypatch.setattr(postfach, "eingerichtet", lambda: True)
    babu_web.nutzer_anlegen("chef@example.org", "Chef", "babu", "admin",
                            passwort=PASSWORT)
    chef = _login("chef@example.org")
    code = chef.post("/api/ambassador", json={"name": "Babs",
                                              "email": "babs@example.org"}).json()["code"]
    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE nutzer SET pw=? WHERE email=?",
                  (babu_web.pw_hash(PASSWORT), "babs@example.org"))
    post.clear()
    return {"chef": chef, "babs": _login("babs@example.org"), "code": code,
            "post": post}


def _einloesen(welt, email, salon, slug="salon"):
    babu_web._REG_ZULETZT.clear()  # noqa: SLF001
    return TestClient(babu_web.app, base_url="https://testserver").post(
        "/api/ambassador/einloesen",
        json={"code": welt["code"], "salon": salon, "email": email, "slug": slug})


def _meilenstein(welt, email, meilenstein, am: D | None = None):
    r = welt["chef"].post("/api/ambassador/meilenstein", json={
        "code": welt["code"], "email": email, "meilenstein": meilenstein,
        "betrag": 237})
    assert r.status_code == 200, r.text
    if am:
        spalte = "gezeichnet_am" if meilenstein == "gezeichnet" else "gehalten_am"
        with babu_web._DB_LOCK, babu_web._db() as c:
            c.execute(f"UPDATE ambassador_salon SET {spalte}=? WHERE email=?",
                      (am.isoformat(), email))
            c.execute("UPDATE ambassador_buchung SET datum=? WHERE email=? "
                      "AND meilenstein=?", (am.isoformat(), email, meilenstein))


# ————— Einladungen: potenzielle Kunden —————

def test_link_wird_als_einladung_gespeichert(welt):
    r = welt["babs"].post("/api/ambassador/link", json={"salon": "Salon Meridian"})
    assert r.status_code == 200, r.text
    assert r.json()["id"] > 0
    offen = welt["babs"].get("/api/ambassador/me").json()["einladungen"]
    assert [(e["salon"], e["email"], e["gesendet"]) for e in offen] == \
        [("Salon Meridian", None, None)]


def test_mail_einladung_merkt_sich_adresse_und_zeit(welt):
    link = welt["babs"].post("/api/ambassador/link",
                             json={"salon": "Salon Meridian"}).json()["link"]
    r = welt["babs"].post("/api/ambassador/einladen", json={
        "email": "meridian@example.org", "salon": "Salon Meridian", "link": link})
    assert r.status_code == 200, r.text
    offen = welt["babs"].get("/api/ambassador/me").json()["einladungen"]
    assert len(offen) == 1
    assert offen[0]["email"] == "meridian@example.org" and offen[0]["gesendet"]


def test_nochmal_schicken_per_nummer(welt):
    link = welt["babs"].post("/api/ambassador/link",
                             json={"salon": "Salon Meridian"}).json()["link"]
    welt["babs"].post("/api/ambassador/einladen", json={
        "email": "meridian@example.org", "salon": "Salon Meridian", "link": link})
    nr = welt["babs"].get("/api/ambassador/me").json()["einladungen"][0]["id"]
    welt["post"].clear()
    r = welt["babs"].post("/api/ambassador/einladen", json={"id": nr})
    assert r.status_code == 200, r.text
    assert [p[0] for p in welt["post"]] == ["meridian@example.org"]
    assert link in welt["post"][0][2]


def test_fremde_einladung_nicht_schickbar(welt):
    link = welt["babs"].post("/api/ambassador/link",
                             json={"salon": "Salon Meridian"}).json()["link"]
    welt["babs"].post("/api/ambassador/einladen", json={
        "email": "meridian@example.org", "salon": "Salon Meridian", "link": link})
    nr = welt["babs"].get("/api/ambassador/me").json()["einladungen"][0]["id"]
    welt["chef"].post("/api/ambassador", json={"name": "Moe", "email": "moe@example.org"})
    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE nutzer SET pw=? WHERE email=?",
                  (babu_web.pw_hash(PASSWORT), "moe@example.org"))
    r = _login("moe@example.org").post("/api/ambassador/einladen", json={"id": nr})
    assert r.status_code == 404


def test_einloesen_schliesst_die_einladung(welt):
    welt["babs"].post("/api/ambassador/link", json={"salon": "Salon Meridian"})
    assert _einloesen(welt, "meridian@example.org", "Salon Meridian",
                      slug="salon-meridian").status_code == 200
    me = welt["babs"].get("/api/ambassador/me").json()
    assert me["einladungen"] == []
    assert me["salons"][0]["salon"] == "Salon Meridian"
    stufen = {s["stufe"]: s["datum"] for s in me["salons"][0]["stufen"]}
    assert stufen["eingeladen"] and stufen["eingeloest"] and stufen["test_endet"]


# ————— Pipeline je Kunde —————

def test_naechster_schritt_folgt_dem_stand(welt):
    _einloesen(welt, "a@example.org", "Salon A")
    me = welt["babs"].get("/api/ambassador/me").json()
    assert "Testet noch" in me["salons"][0]["naechster_schritt"]

    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE mandant SET test_bis=? WHERE besitzer_un=?",
                  ((D.today() + dt.timedelta(days=3)).isoformat(), "a@example.org"))
    me = welt["babs"].get("/api/ambassador/me").json()
    assert "jetzt nachfragen" in me["salons"][0]["naechster_schritt"]

    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE mandant SET test_bis=? WHERE besitzer_un=?",
                  ((D.today() - dt.timedelta(days=1)).isoformat(), "a@example.org"))
    me = welt["babs"].get("/api/ambassador/me").json()
    assert "abgelaufen" in me["salons"][0]["naechster_schritt"]

    _meilenstein(welt, "a@example.org", "gezeichnet", am=D(2026, 10, 3))
    s = welt["babs"].get("/api/ambassador/me").json()["salons"][0]
    assert "03.01.2027" in s["naechster_schritt"]
    stufen = {x["stufe"]: x for x in s["stufen"]}
    assert stufen["gezeichnet"]["datum"] == "2026-10-03"
    assert stufen["gehalten"]["datum"] is None
    assert stufen["gehalten"]["faellig"] == "2027-01-03"


# ————— Geld —————

def test_geld_mit_naechstem_lauf(welt, monkeypatch):
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 2))
    _einloesen(welt, "a@example.org", "Salon A")
    _einloesen(welt, "b@example.org", "Salon B")
    _meilenstein(welt, "a@example.org", "gezeichnet", am=D(2026, 9, 20))
    _meilenstein(welt, "b@example.org", "gezeichnet", am=D(2026, 10, 1))
    geld = welt["babs"].get("/api/ambassador/me").json()["geld"]
    assert geld["verdient"] == 474 and geld["ausgezahlt"] == 0 and geld["offen"] == 474
    lauf = geld["naechster_lauf"]
    assert lauf["datum"] == "2026-10-15" and lauf["stichtag"] == "2026-09-30"
    assert lauf["betrag"] == 237 and lauf["wird_ausgezahlt"] is True
    assert geld["danach"] == 237
    assert [(p["salon"], p["betrag"]) for p in lauf["posten"]] == [("Salon A", 237)]


def test_unter_100_euro_wartet(welt, monkeypatch):
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 2))
    _einloesen(welt, "a@example.org", "Salon A")
    r = welt["chef"].post("/api/ambassador/meilenstein", json={
        "code": welt["code"], "email": "a@example.org",
        "meilenstein": "gezeichnet", "betrag": 60})
    assert r.status_code == 200
    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE ambassador_buchung SET datum='2026-09-01'")
    lauf = welt["babs"].get("/api/ambassador/me").json()["geld"]["naechster_lauf"]
    assert lauf["betrag"] == 60 and lauf["wird_ausgezahlt"] is False
    assert "unter 100" in lauf["hinweis"]


def test_auszahlungslauf_zahlt_bis_zum_stichtag(welt, monkeypatch):
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 15))
    _einloesen(welt, "a@example.org", "Salon A")
    _einloesen(welt, "b@example.org", "Salon B")
    _meilenstein(welt, "a@example.org", "gezeichnet", am=D(2026, 9, 20))
    _meilenstein(welt, "b@example.org", "gezeichnet", am=D(2026, 10, 1))
    r = welt["chef"].post("/api/ambassador/gezahlt", json={"code": welt["code"]})
    assert r.status_code == 200, r.text
    assert r.json()["gezahlt"] == 237 and r.json()["stichtag"] == "2026-09-30"
    geld = welt["babs"].get("/api/ambassador/me").json()["geld"]
    assert geld["ausgezahlt"] == 237 and geld["offen"] == 237
    assert [(a["datum"], a["betrag"]) for a in geld["auszahlungen"]] == \
        [("2026-10-15", 237)]
    # Zweimal derselbe Lauf geht nicht — nichts mehr fällig.
    r = welt["chef"].post("/api/ambassador/gezahlt", json={"code": welt["code"]})
    assert r.status_code == 409


def test_auszahlungslauf_unter_100_euro_abgelehnt(welt, monkeypatch):
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 15))
    _einloesen(welt, "a@example.org", "Salon A")
    welt["chef"].post("/api/ambassador/meilenstein", json={
        "code": welt["code"], "email": "a@example.org",
        "meilenstein": "gezeichnet", "betrag": 60})
    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE ambassador_buchung SET datum='2026-09-01'")
    r = welt["chef"].post("/api/ambassador/gezahlt", json={"code": welt["code"]})
    assert r.status_code == 409 and "100" in r.json()["fehler"]


def test_verwaltung_sieht_geld_und_lauf(welt, monkeypatch):
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 2))
    _einloesen(welt, "a@example.org", "Salon A")
    _meilenstein(welt, "a@example.org", "gezeichnet", am=D(2026, 9, 20))
    a = welt["chef"].get("/api/ambassador/liste").json()["ambassadorinnen"][0]
    assert a["geld"]["naechster_lauf"]["betrag"] == 237
    assert a["salons"][0]["naechster_schritt"]


def test_keine_aussicht_solange_preise_beispiele_sind(welt):
    """Entscheidung 02.10.2026: keine Zahl „in Aussicht" vor festen Preisen."""
    _einloesen(welt, "a@example.org", "Salon A")
    me = welt["babs"].get("/api/ambassador/me").json()
    assert "aussicht" not in str(me).lower()


def test_verwaltung_sieht_den_faelligen_lauf_auch_ein_paar_tage_danach(welt, monkeypatch):
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 17))
    _einloesen(welt, "a@example.org", "Salon A")
    _meilenstein(welt, "a@example.org", "gezeichnet", am=D(2026, 9, 20))
    geld = welt["chef"].get("/api/ambassador/liste").json()["ambassadorinnen"][0]["geld"]
    assert geld["faelliger_lauf"] == {"datum": "2026-10-15", "stichtag": "2026-09-30",
                                      "betrag": 237, "auszahlbar": True}
    assert geld["naechster_lauf"]["datum"] == "2027-01-15"


def test_konto_zeigt_bewegungen_wie_ein_kontoauszug(welt, monkeypatch):
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 15))
    _einloesen(welt, "a@example.org", "Salon A")
    _einloesen(welt, "b@example.org", "Salon B")
    _meilenstein(welt, "a@example.org", "gezeichnet", am=D(2026, 9, 20))
    _meilenstein(welt, "b@example.org", "gezeichnet", am=D(2026, 10, 1))
    assert welt["chef"].post("/api/ambassador/gezahlt",
                             json={"code": welt["code"]}).status_code == 200
    bew = welt["babs"].get("/api/ambassador/me").json()["geld"]["bewegungen"]
    assert [(b["datum"], b["betrag"]) for b in bew] == [
        ("2026-10-15", -237), ("2026-10-01", 237), ("2026-09-20", 237)]
    assert bew[0]["text"] == "Auszahlung (verdient bis 30.09.2026)"
    assert bew[2]["text"] == "Provision Salon A, gezeichnet"
