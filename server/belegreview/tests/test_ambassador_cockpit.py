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

PROFIL = {"kontoinhaber": "Babs Beispiel", "iban": "DE02120300000000202051",
          "strasse": "Weg 1", "plz": "70173", "ort": "Stuttgart",
          "steuerstatus": "privat", "zustimmung": True}


def _auszahlen(welt, monkeypatch):
    """Der Lauf, wie Nina ihn fährt: Profil da, Lauf anlegen, überwiesen."""
    monkeypatch.setenv("BABU_FIRMA_NAME", "0711 Intelligence")
    monkeypatch.setenv("BABU_AUSZAHLUNG_IBAN", "DE89370400440532013000")
    assert welt["babs"].post("/api/ambassador/profil", json=PROFIL).status_code == 200
    r = welt["chef"].post("/api/auszahlung/lauf")
    if r.status_code != 200:
        return r
    nr = r.json()["id"]
    assert welt["chef"].post(f"/api/auszahlung/lauf/{nr}/ueberwiesen").status_code == 200
    return r

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
        json={"code": welt["code"], "salon": salon, "email": email, "slug": slug,
              "agb": True})


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


def test_erwartet_nennt_den_lauf_der_das_geld_wirklich_bringt(welt, monkeypatch):
    """E2E 08.10.2026: Die Ambassadorin las „237 € kommen am 15. Oktober" —
    verdient am 08.10., also nach dem Stichtag 30.09. Der Oktober-Lauf bringt
    nichts davon; das Geld kommt am 15.01.2027."""
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 8))
    _einloesen(welt, "a@example.org", "Salon A")
    _meilenstein(welt, "a@example.org", "gezeichnet", am=D(2026, 10, 8))
    geld = welt["babs"].get("/api/ambassador/me").json()["geld"]
    assert geld["naechster_lauf"]["datum"] == "2026-10-15"
    assert geld["naechster_lauf"]["betrag"] == 0
    assert geld["erwartet"] == {"datum": "2027-01-15", "betrag": 237}


def test_erwartet_teilt_alt_und_neu_und_wartet_auf_100_euro(welt, monkeypatch):
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 2))
    _einloesen(welt, "a@example.org", "Salon A")
    _einloesen(welt, "b@example.org", "Salon B")
    _meilenstein(welt, "a@example.org", "gezeichnet", am=D(2026, 9, 20))
    _meilenstein(welt, "b@example.org", "gezeichnet", am=D(2026, 10, 1))
    # Der erste Lauf bringt nur das Alte — dafür nennt „erwartet" ihn.
    assert welt["babs"].get("/api/ambassador/me").json()["geld"]["erwartet"] == \
        {"datum": "2026-10-15", "betrag": 237}
    # Unter 100 € insgesamt: kein Termin, der nicht stimmt.
    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE ambassador_buchung SET betrag=30")
    assert welt["babs"].get("/api/ambassador/me").json()["geld"]["erwartet"] is None


def test_unterwegs_zwischen_lauf_und_ueberweisung(welt, monkeypatch):
    """E2E 08.10.2026: Lauf erzeugt, Überweisung noch nicht bestätigt — die
    Provision hängt schon am Lauf, ist aber noch nicht „gezahlt". Dann ist sie
    unterwegs, nicht „wartet auf 100 €"."""
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 15))
    monkeypatch.setenv("BABU_FIRMA_NAME", "0711 Intelligence")
    monkeypatch.setenv("BABU_AUSZAHLUNG_IBAN", "DE89370400440532013000")
    _einloesen(welt, "a@example.org", "Salon A")
    _meilenstein(welt, "a@example.org", "gezeichnet", am=D(2026, 9, 20))
    assert welt["babs"].post("/api/ambassador/profil", json=PROFIL).status_code == 200
    r = welt["chef"].post("/api/auszahlung/lauf")
    assert r.status_code == 200, r.text
    geld = welt["babs"].get("/api/ambassador/me").json()["geld"]
    assert geld["offen"] == 237 and geld["unterwegs"] == 237
    assert geld["erwartet"] is None
    # Nach „überwiesen" ist nichts mehr unterwegs.
    assert welt["chef"].post(f"/api/auszahlung/lauf/{r.json()['id']}/ueberwiesen").status_code == 200
    geld = welt["babs"].get("/api/ambassador/me").json()["geld"]
    assert geld["unterwegs"] == 0 and geld["offen"] == 0


def test_unter_100_euro_wartet(welt, monkeypatch):
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 2))
    _einloesen(welt, "a@example.org", "Salon A")
    r = welt["chef"].post("/api/ambassador/meilenstein", json={
        "code": welt["code"], "email": "a@example.org",
        "meilenstein": "gezeichnet", "betrag": 60,
        "grund": "kleiner Betrag für den Test der 100-€-Grenze"})
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
    r = _auszahlen(welt, monkeypatch)
    assert r.status_code == 200, r.text
    assert r.json()["summe_cent"] == 23700        # bis Stichtag 30.09.
    geld = welt["babs"].get("/api/ambassador/me").json()["geld"]
    assert geld["ausgezahlt"] == 237 and geld["offen"] == 237
    assert [(a["datum"], a["betrag"]) for a in geld["auszahlungen"]] == \
        [("2026-10-15", 237)]
    # Zweimal derselbe Lauf geht nicht.
    assert welt["chef"].post("/api/auszahlung/lauf").status_code == 409


def test_auszahlungslauf_unter_100_euro_abgelehnt(welt, monkeypatch):
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 15))
    _einloesen(welt, "a@example.org", "Salon A")
    welt["chef"].post("/api/ambassador/meilenstein", json={
        "code": welt["code"], "email": "a@example.org",
        "meilenstein": "gezeichnet", "betrag": 60,
        "grund": "kleiner Betrag für den Test der 100-€-Grenze"})
    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE ambassador_buchung SET datum='2026-09-01'")
    r = _auszahlen(welt, monkeypatch)
    assert r.status_code == 409
    v = welt["chef"].get("/api/auszahlung/vorschau").json()
    assert v["zeilen"][0]["grund"] == "unter 100 €"


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
    assert _auszahlen(welt, monkeypatch).status_code == 200
    bew = welt["babs"].get("/api/ambassador/me").json()["geld"]["bewegungen"]
    assert [(b["datum"], b["betrag"]) for b in bew] == [
        ("2026-10-15", -237), ("2026-10-01", 237), ("2026-09-20", 237)]
    assert bew[0]["text"] == "Auszahlung (verdient bis 30.09.2026)"
    assert bew[2]["text"] == "Provision Salon A, gezeichnet"


# ————— Handweg nach der Regel (seit 03.10.2026, provision.py) —————

def test_handweg_rechnet_den_betrag_aus_dem_paket(welt, monkeypatch):
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 2))
    _einloesen(welt, "a@example.org", "Salon A")
    r = welt["chef"].post("/api/ambassador/meilenstein", json={
        "code": welt["code"], "email": "a@example.org", "meilenstein": "gezeichnet",
        "paket": "plus"})
    assert r.status_code == 200, r.text
    assert r.json()["verdienst"] == 447
    with babu_web._DB_LOCK, babu_web._db() as c:
        z = c.execute("SELECT betrag, quelle, paket FROM ambassador_buchung").fetchone()
    assert tuple(z) == (447, "hand", "plus")


def test_handweg_ohne_paket_nimmt_die_empfehlung(welt, monkeypatch):
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 2))
    _einloesen(welt, "a@example.org", "Salon A")
    babu_web.db_einstellung_setzen("a@example.org", "kleinunternehmer", "Ja")
    r = welt["chef"].post("/api/ambassador/meilenstein", json={
        "code": welt["code"], "email": "a@example.org", "meilenstein": "gezeichnet"})
    assert r.status_code == 200 and r.json()["verdienst"] == 117


def test_abweichender_betrag_braucht_einen_grund(welt, monkeypatch):
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 2))
    _einloesen(welt, "a@example.org", "Salon A")
    r = welt["chef"].post("/api/ambassador/meilenstein", json={
        "code": welt["code"], "email": "a@example.org", "meilenstein": "gezeichnet",
        "betrag": 300})
    assert r.status_code == 400 and "Grund" in r.json()["fehler"]
    r = welt["chef"].post("/api/ambassador/meilenstein", json={
        "code": welt["code"], "email": "a@example.org", "meilenstein": "gezeichnet",
        "betrag": 300, "grund": "Sonderabsprache Messe"})
    assert r.status_code == 200 and r.json()["verdienst"] == 300


def test_gehalten_addiert_in_der_salonzeile(welt, monkeypatch):
    """Bis 03.10.2026 überschrieb „gehalten" den Betrag von „gezeichnet"."""
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 2))
    _einloesen(welt, "a@example.org", "Salon A")
    _meilenstein(welt, "a@example.org", "gezeichnet")
    _meilenstein(welt, "a@example.org", "gehalten")
    with babu_web._DB_LOCK, babu_web._db() as c:
        assert c.execute("SELECT verdienst FROM ambassador_salon WHERE email=?",
                         ("a@example.org",)).fetchone()[0] == 474


def test_handweg_doppelt_wird_abgewiesen(welt, monkeypatch):
    monkeypatch.setattr(ka, "_heute", lambda: D(2026, 10, 2))
    _einloesen(welt, "a@example.org", "Salon A")
    _meilenstein(welt, "a@example.org", "gezeichnet")
    r = welt["chef"].post("/api/ambassador/meilenstein", json={
        "code": welt["code"], "email": "a@example.org", "meilenstein": "gezeichnet"})
    assert r.status_code == 409


def test_alter_auszahlungsweg_ist_stillgelegt(welt):
    r = welt["chef"].post("/api/ambassador/gezahlt", json={"code": welt["code"]})
    assert r.status_code == 410 and "Auszahlungslauf" in r.json()["fehler"]


# ————— Knöpfe für Nina (03.10.2026): Link sichtbar, Mail-Einladung, Code an/aus —————

def test_eigener_bereich_nennt_den_allgemeinen_link(welt):
    me = welt["babs"].get("/api/ambassador/me").json()
    assert me["aktiv"] is True
    assert me["link"].endswith(f"/ambassador/{welt['code']}/salon")
    # Der Link funktioniert wirklich: die Einladungsseite lädt.
    seite = TestClient(babu_web.app, base_url="https://testserver").get(
        me["link"].split("testserver", 1)[-1] if "testserver" in me["link"]
        else "/" + me["link"].split("/", 3)[3])
    assert seite.status_code == 200


def test_mail_einladung_ueber_die_nummer_mit_vorname(welt):
    r = welt["babs"].post("/api/ambassador/link",
                          json={"person": "Lea", "email": "lea@haarwerk.de"})
    assert r.status_code == 200
    nr = r.json()["id"]
    welt["post"].clear()
    r = welt["babs"].post("/api/ambassador/einladen", json={"id": nr})
    assert r.status_code == 200, r.text
    an, _betreff, text = welt["post"][0][:3]
    assert an == "lea@haarwerk.de"
    assert text.startswith("Hallo Lea,")
    assert f"/ambassador/{welt['code']}/" in text


def test_mail_einladung_mit_fremdem_link_verschickt_nichts(welt):
    welt["post"].clear()
    r = welt["babs"].post("/api/ambassador/einladen", json={
        "email": "opfer@example.org", "salon": "Opfer",
        "link": "https://boese.example/ambassador/X/y"})
    assert r.status_code == 400
    assert welt["post"] == []


def test_code_abschalten_stoppt_neue_salons_und_laesst_das_geld(welt):
    assert welt["babs"].post("/api/ambassador/aktiv",
                             json={"code": welt["code"], "aktiv": False}).status_code == 403
    r = welt["chef"].post("/api/ambassador/aktiv", json={"code": welt["code"], "aktiv": False})
    assert r.status_code == 200 and r.json()["aktiv"] is False
    gast = TestClient(babu_web.app, base_url="https://testserver")
    assert gast.get(f"/ambassador/{welt['code']}/salon").status_code == 404
    assert _einloesen(welt, "neu@salon.de", "Salon Neu").status_code == 404
    assert welt["babs"].post("/api/ambassador/link", json={"person": "Mia"}).status_code == 403
    me = welt["babs"].get("/api/ambassador/me")
    assert me.status_code == 200 and me.json()["aktiv"] is False
    assert welt["babs"].get("/api/ambassador/profil").status_code == 200
    liste = welt["chef"].get("/api/ambassador/liste").json()["ambassadorinnen"]
    assert [a["aktiv"] for a in liste if a["code"] == welt["code"]] == [False]
    # wieder einschalten
    assert welt["chef"].post("/api/ambassador/aktiv",
                             json={"code": welt["code"], "aktiv": True}).status_code == 200
    assert gast.get(f"/ambassador/{welt['code']}/salon").status_code == 200
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        aktionen = [z[0] for z in c.execute(
            "SELECT aktion FROM audit_log WHERE aktion LIKE 'ambassador_code_%' ORDER BY id")]
    assert aktionen == ["ambassador_code_aus", "ambassador_code_an"]


def test_code_an_aus_braucht_code_und_ja_nein(welt):
    assert welt["chef"].post("/api/ambassador/aktiv", json={"code": welt["code"]}).status_code == 400
    assert welt["chef"].post("/api/ambassador/aktiv",
                             json={"code": "GIBTS-NICHT", "aktiv": False}).status_code == 404


def test_mail_eingeladene_stehen_in_deine_salons(welt):
    """Bis 03.10.2026 übersprang die Liste jede Einladung ohne Handynummer —
    „steht jetzt in deiner Liste“ stimmte für Mail-Einladungen nicht."""
    nr = welt["babs"].post("/api/ambassador/link",
                           json={"person": "Mia", "email": "mia@studio-mia.de"}).json()["id"]
    assert welt["babs"].post("/api/ambassador/einladen", json={"id": nr}).status_code == 200
    me = welt["babs"].get("/api/ambassador/me").json()
    mia = [k for k in me["kontakte"] if k["name"] == "Mia"]
    assert len(mia) == 1
    assert mia[0]["stand"] == "noch nicht gestartet"
    assert mia[0]["gesendet_am"] and not mia[0].get("mail_nr")     # gerade erst geschickt
    assert mia[0]["aufgabe"] is None                               # kein WhatsApp ohne Nummer
    # nach drei Tagen: „Nochmal per Mail“
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE ambassador_einladung SET gesendet='2026-01-01T09:00:00Z', "
                  "erstellt='2026-01-01T09:00:00Z' WHERE id=?", (nr,))
    mia = [k for k in welt["babs"].get("/api/ambassador/me").json()["kontakte"] if k["name"] == "Mia"]
    assert mia[0]["mail_nr"] == nr


def test_abgeschalteter_code_erinnert_nicht_an_offene_einladungen(welt):
    """Der Einladungslink führt bei abgeschaltetem Code ins Leere — also kein
    „Erinnern“ für Eingeladene, die noch nicht gestartet sind."""
    welt["babs"].post("/api/ambassador/link", json={"person": "Lea", "telefon": "0176 1112223"})
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE ambassador_einladung SET erstellt='2026-01-01T09:00:00Z', "
                  "gesendet='2026-01-01T09:00:00Z' WHERE person='Lea'")
    vorher = [k for k in welt["babs"].get("/api/ambassador/me").json()["kontakte"] if k["name"] == "Lea"]
    assert vorher[0]["aufgabe"] is not None                      # mit Code: Erinnern
    welt["chef"].post("/api/ambassador/aktiv", json={"code": welt["code"], "aktiv": False})
    nachher = [k for k in welt["babs"].get("/api/ambassador/me").json()["kontakte"] if k["name"] == "Lea"]
    assert nachher[0]["aufgabe"] is None


# ————— Bestehende Salons verbinden (seit 08.10.2026) —————
#
# Entscheidung Auftraggeber 08.10.2026: Die Ambassadorin gibt die E-Mail ein;
# gibt es den Salon schon, sieht sie das und der Salon bekommt eine Mail mit
# einem Link, über den ER die Verbindung bestätigt. Wer schon ein laufendes
# Abo bezahlt, ist nicht verbindbar; wer schon mit einer Ambassadorin
# verbunden ist, bleibt bei ihr.

import re  # noqa: E402

import mandanten  # noqa: E402
import provision  # noqa: E402


def _bestehender_salon(email="alt@salon.de", salon="Salon Alt", abo_status=None):
    babu_web.nutzer_anlegen(email, "Inhaberin", salon, "salon", passwort=PASSWORT,
                            box=False)
    with babu_web._DB_LOCK, babu_web._db() as c:
        kid = mandanten.kanzlei_anlegen("Kanzlei X", "chef@example.org", c=c)
        mid = mandanten.mandant_anlegen(kid, salon, email, "SKR04", c=c)
        if abo_status:
            c.execute("UPDATE mandant SET abo_status=?, paket='salon' WHERE id=?",
                      (abo_status, mid))
    return email


def _einladen(welt, email, person="Alte"):
    r = welt["babs"].post("/api/ambassador/link", json={"person": person, "email": email})
    if r.status_code != 200:
        return r
    return welt["babs"].post("/api/ambassador/einladen", json={"id": r.json()["id"]})


def _token_aus_mail(welt, an):
    texte = [t for (empf, _b, t) in welt["post"] if empf == an]
    assert texte, f"keine Mail an {an}"
    m = re.search(r"/verbinden/([A-Za-z0-9_.=-]+)", texte[-1])
    assert m, texte[-1]
    return m.group(1)


def _verbunden(email):
    with babu_web._DB_LOCK, babu_web._db() as c:
        return [z[0] for z in c.execute(
            "SELECT code FROM ambassador_salon WHERE email=?", (email,))]


def test_bestehender_salon_wird_erst_nach_seiner_bestaetigung_verbunden(welt):
    email = _bestehender_salon()
    r = _einladen(welt, email)
    assert r.status_code == 200, r.text
    assert r.json()["bestehend"] is True
    assert "gibt es schon" in r.json()["hinweis"]
    assert _verbunden(email) == []                 # noch nicht — der Salon entscheidet
    token = _token_aus_mail(welt, email)

    gast = TestClient(babu_web.app, base_url="https://testserver")
    seite = gast.get(f"/verbinden/{token}")
    assert seite.status_code == 200
    assert "Babs" in seite.text and "verbinden" in seite.text.lower()
    assert "--gc-serif" in seite.text                # im Look des Portals

    r = gast.post("/api/ambassador/verbinden", json={"token": token})
    assert r.status_code == 200, r.text
    assert _verbunden(email) == [welt["code"]]
    # Ein zweiter Klick ändert nichts.
    assert gast.post("/api/ambassador/verbinden", json={"token": token}).status_code == 200
    assert _verbunden(email) == [welt["code"]]
    # Sie sieht den Salon, die Einladung ist eingelöst.
    me = welt["babs"].get("/api/ambassador/me").json()
    assert email in [s.get("email") for s in me["salons"]] or \
        "Salon Alt" in str(me["salons"])
    with babu_web._DB_LOCK, babu_web._db() as c:
        assert c.execute("SELECT eingeloest FROM ambassador_einladung WHERE email=?",
                         (email,)).fetchone()[0]
        # Bucht der Salon später ein Abo, verdient sie daran.
        b = provision.buchen(c, email=email, meilenstein="gezeichnet", betrag_eur=237,
                             paket="salon", quelle="stripe", heute="2026-10-08")
    assert b["ok"] is True and b["code"] == welt["code"]


@pytest.mark.parametrize("fall, erwartet", [
    ("abo", "Abo"),
    ("andere", "schon mit einer Ambassadorin"),
    ("kanzlei", "keinen Salon"),
    ("selbst", "Dich selbst"),
])
def test_nicht_verbindbar(welt, fall, erwartet):
    if fall == "abo":
        email = _bestehender_salon(abo_status="aktiv")
    elif fall == "andere":
        email = _bestehender_salon()
        code2 = welt["chef"].post("/api/ambassador", json={
            "name": "Zweite", "email": "zweite@example.org"}).json()["code"]
        with babu_web._DB_LOCK, babu_web._db() as c:
            c.execute("INSERT INTO ambassador_salon (code, email, salon, eingelöst) "
                      "VALUES (?,?,?,?)", (code2, email, "Salon Alt", "2026-10-01T00:00:00Z"))
    elif fall == "kanzlei":
        email = "buero@kanzlei.de"
        babu_web.nutzer_anlegen(email, "Büro", "Kanzlei", "kanzlei", passwort=PASSWORT,
                                box=False)
    else:
        email = "babs@example.org"
    welt["post"].clear()
    r = _einladen(welt, email)
    assert r.status_code == 409, r.text
    assert erwartet in r.json()["fehler"]
    assert welt["post"] == []                        # keine Mail
    with babu_web._DB_LOCK, babu_web._db() as c:     # und keine offene Einladung
        assert c.execute("SELECT COUNT(*) FROM ambassador_einladung WHERE email=?",
                         (email,)).fetchone()[0] == 0


def test_gekuendigtes_abo_ist_verbindbar(welt):
    email = _bestehender_salon(abo_status="gekuendigt")
    assert _einladen(welt, email).status_code == 200


def test_abo_zwischen_mail_und_klick_verhindert_die_verbindung(welt):
    email = _bestehender_salon()
    assert _einladen(welt, email).status_code == 200
    token = _token_aus_mail(welt, email)
    with babu_web._DB_LOCK, babu_web._db() as c:
        c.execute("UPDATE mandant SET abo_status='aktiv' WHERE besitzer_un=?", (email,))
    r = TestClient(babu_web.app, base_url="https://testserver").post(
        "/api/ambassador/verbinden", json={"token": token})
    assert r.status_code == 409 and "Abo" in r.json()["fehler"]
    assert _verbunden(email) == []


def test_gefaelschter_oder_abgelaufener_link(welt, monkeypatch):
    email = _bestehender_salon()
    assert _einladen(welt, email).status_code == 200
    token = _token_aus_mail(welt, email)
    gast = TestClient(babu_web.app, base_url="https://testserver")
    falsch = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    assert gast.post("/api/ambassador/verbinden", json={"token": falsch}).status_code == 400
    assert "gilt nicht" in gast.get(f"/verbinden/{falsch}").text
    # Ein Anmelde-Cookie ist kein Verbinden-Link (eigener Schlüssel).
    cookie = babu_web._signieren(email, int(ka.time.time()) + 3600)
    assert gast.post("/api/ambassador/verbinden", json={"token": cookie}).status_code == 400
    monkeypatch.setattr(ka.time, "time", lambda: 10**12)
    assert gast.post("/api/ambassador/verbinden", json={"token": token}).status_code == 400
    assert _verbunden(email) == []


def test_oeffentlicher_link_schickt_bestehendem_salon_die_verbinden_mail(welt):
    email = _bestehender_salon()
    welt["post"].clear()
    r = _einloesen(welt, email, "Salon Alt")
    assert r.status_code == 200
    assert "/verbinden/" in welt["post"][-1][2]
    assert _verbunden(email) == []


def test_uebersicht_wer_hat_wen_geworben(welt):
    """Die Betreiber-Liste trägt alles für die Übersicht: wer die
    Ambassadorin angelegt hat, ihre Salons mit Abo-Stand, offene Einladungen."""
    assert _einloesen(welt, "neu@salon.de", "Salon Neu").status_code == 200
    email = _bestehender_salon("alt2@salon.de", "Salon Alt2", abo_status="gekuendigt")
    assert _einladen(welt, email).status_code == 200
    a = next(x for x in welt["chef"].get("/api/ambassador/liste").json()["ambassadorinnen"]
             if x["code"] == welt["code"])
    assert a["angelegt_von"] == "chef@example.org"
    salon = next(s for s in a["salons"] if s["email"] == "neu@salon.de")
    assert salon["abo"] is None and salon["testmonat"]
    assert [e["email"] for e in a["einladungen"]] == ["alt2@salon.de"]


def test_bestehender_salon_wartet_auf_bestaetigung_in_ihrer_liste(welt):
    email = _bestehender_salon("wartet@salon.de", "Salon Wartet")
    assert _einladen(welt, email, person="Wanda").status_code == 200
    kontakte = welt["babs"].get("/api/ambassador/me").json()["kontakte"]
    k = next(x for x in kontakte if x["name"] == "Wanda")
    assert k["stand"] == "wartet auf Bestätigung"
    assert "bestätigen" in k["aktiv"]


# ————— Ka-ching (08.10.2026) —————

def test_ka_ching_wenn_ein_salon_mitmacht(welt, monkeypatch):
    """Wird ein Salon zahlende Kundin, geht an die Ambassadorin eine Push-
    Nachricht mit dem Kassenklang; ohne Push-Schlüssel passiert still nichts.
    Den Klang fürs Portal gibt es öffentlich."""
    import push
    import threading
    gesendet = []
    monkeypatch.setattr(push, "eingerichtet", lambda: True)
    monkeypatch.setattr(push, "senden_an", lambda geraete, titel, text, loeschen, klang="default":
                        gesendet.append((titel, text, klang)) or 1)

    class Sofort:          # der Hintergrund-Thread läuft im Test gleich mit
        def __init__(self, target, daemon=None): self.ziel = target
        def start(self): self.ziel()
    monkeypatch.setattr(threading, "Thread", Sofort)
    assert _einloesen(welt, "kim@example.org", "Kims Haarstudio").status_code == 200
    _meilenstein(welt, "kim@example.org", "gezeichnet")
    assert gesendet == [("Ka-ching! +237 €", "Kims Haarstudio macht mit. Dein Geld wächst.",
                         "kaching.caf")]
    klang = TestClient(babu_web.app).get("/klang/kaching.m4a")
    assert klang.status_code == 200 and klang.headers["content-type"] == "audio/mp4"
    assert len(klang.content) > 5000
