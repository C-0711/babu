"""Betreiber und Kanzlei sind zwei Rollen — seit 03.10.2026 auch im Code.

Bis dahin hing die Betreiber-Verwaltung an `darf_verwalten` (admin ODER
kanzlei). Jede Kanzlei konnte deshalb:

1. Admin-Konten anlegen oder ein Konto zum Admin machen,
2. alle Registrierungen mit IBAN und Steuernummer lesen,
3. Warteliste und Ambassador-Programm bedienen,
4. ohne `X-Mandant` die Standard-Ablage lesen (auf der H200V die eines
   fremden Betriebs).

Go-live-Plan Phase 1. Die Kanzlei-Arbeit an IHREN Mandanten bleibt, wie sie
war — das prüfen test_acting_as und test_kanzlei_*.
"""
import json
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

PASSWORT = "ein-langes-passwort-hier"


def _bare(tmp_path: Path, ziel: Path) -> Path:
    arbeit = tmp_path / "arbeit"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for a in (("config", "user.name", "t"), ("config", "user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), *a], check=True)
    (arbeit / "README.md").write_text("standard")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "stand"], check=True)
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(ziel)], check=True)
    return ziel


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
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(babu_web, "ROLLEN", {})
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(bx, "STORE_WURZEL", tmp_path / "stores")
    monkeypatch.setattr(bx, "KLON_WURZEL", tmp_path / "klone")
    bx.registry_leeren()
    standard = _bare(tmp_path, tmp_path / "standard.git")
    monkeypatch.setattr(babu_web, "STORE", standard)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(standard))
    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    babu_web._REG_ZULETZT.clear()  # noqa: SLF001

    for email, rolle in (("betreiber@0711.io", "admin"),
                         ("kanzlei@afflek.de", "kanzlei"),
                         ("inhaberin@salon.de", "salon")):
        assert babu_web.nutzer_anlegen(email, email.split("@")[0], "Betrieb",
                                       rolle, passwort=PASSWORT) is not None
    # Eine Registrierung mit Bankdaten — das, was keine Kanzlei sehen darf.
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("INSERT INTO registrierungen (zeit, daten, status) VALUES (?,?,?)",
                  ("2026-10-03T08:00:00Z",
                   json.dumps({"email": "neu@salon.de", "salon": "Neu",
                               "iban": "DE89370400440532013000",
                               "steuernummer": "12/345/67890"}), "neu"))
    yield {"admin": _login("betreiber@0711.io"),
           "kanzlei": _login("kanzlei@afflek.de")}
    bx.registry_leeren()


# Die Betreiber-Routen: (Methode, Pfad, Rumpf). Der Rumpf ist so gewählt,
# dass ein Admin damit NICHT an der Wache scheitert, sondern frühestens an
# den Daten — so trennt der Test „verboten" (403) von „falsche Eingabe".
BETREIBER_ROUTEN = [
    ("GET", "/api/registrierungen", None),
    ("GET", "/api/warteliste", None),
    ("POST", "/api/warteliste/einrichten", {"email": "x@salon.de"}),
    ("POST", "/api/warteliste/apple-id", {"email": "x@salon.de",
                                          "apple_id": "x@icloud.com"}),
    ("POST", "/api/warteliste/ablehnen", {"email": "x@salon.de"}),
    ("POST", "/api/registrierung-einrichten", {"id": 999}),
    ("POST", "/api/ambassador", {"name": "Moe", "email": "moe@example.org"}),
    ("GET", "/api/ambassador/liste", None),
    ("POST", "/api/ambassador/meilenstein", {"code": "X", "email": "x@salon.de",
                                             "meilenstein": "gezeichnet",
                                             "betrag": 237}),
    ("POST", "/api/ambassador/verlaengern", {"code": "X", "email": "x@salon.de"}),
    ("POST", "/api/ambassador/gezahlt", {"code": "X"}),       # stillgelegt: 410
]


def _rufen(client: TestClient, methode: str, pfad: str, rumpf):
    if methode == "GET":
        return client.get(pfad)
    return client.post(pfad, json=rumpf)


@pytest.mark.parametrize("methode,pfad,rumpf", BETREIBER_ROUTEN)
def test_kanzlei_kommt_an_keine_betreiber_route(welt, methode, pfad, rumpf):
    r = _rufen(welt["kanzlei"], methode, pfad, rumpf)
    assert r.status_code == 403, f"{methode} {pfad}: {r.status_code} {r.text}"


@pytest.mark.parametrize("methode,pfad,rumpf", BETREIBER_ROUTEN)
def test_betreiber_kommt_an_jede_betreiber_route(welt, methode, pfad, rumpf):
    r = _rufen(welt["admin"], methode, pfad, rumpf)
    assert r.status_code != 403, f"{methode} {pfad}: {r.text}"


def test_registrierungen_zeigen_einer_kanzlei_keine_iban(welt):
    r = welt["kanzlei"].get("/api/registrierungen")
    assert r.status_code == 403
    assert "DE89" not in r.text and "12/345" not in r.text
    # Der Betreiber sieht sie — dafür ist die Seite da.
    assert "DE89370400440532013000" in welt["admin"].get("/api/registrierungen").text


@pytest.mark.parametrize("rolle", ["admin", "kanzlei"])
def test_kanzlei_legt_kein_betreiber_oder_kanzlei_konto_an(welt, rolle):
    r = welt["kanzlei"].post("/api/nutzer", json={"email": f"neu-{rolle}@x.de",
                                                  "rolle": rolle})
    assert r.status_code == 403
    assert babu_web.nutzer_holen(f"neu-{rolle}@x.de") is None


def test_kanzlei_legt_weiter_salon_konten_an(welt):
    r = welt["kanzlei"].post("/api/nutzer", json={"email": "team@salon.de",
                                                  "rolle": "mitarbeit"})
    assert r.status_code == 200, r.text
    assert babu_web.nutzer_holen("team@salon.de")["rolle"] == "mitarbeit"


def test_unbekannte_rolle_wird_abgewiesen(welt):
    r = welt["admin"].post("/api/nutzer", json={"email": "x@x.de", "rolle": "gott"})
    assert r.status_code == 400
    assert babu_web.nutzer_holen("x@x.de") is None


def test_betreiber_legt_betreiber_an(welt):
    r = welt["admin"].post("/api/nutzer", json={"email": "nina@0711.io",
                                                "rolle": "admin"})
    assert r.status_code == 200, r.text
    assert babu_web.rolle("nina@0711.io") == "admin"


def test_kanzlei_stuft_niemanden_zum_betreiber_hoch(welt, monkeypatch):
    # Selbst dann nicht, wenn der Zugang in ihrer Reichweite liegt.
    monkeypatch.setattr(babu_web, "_in_reichweite", lambda un, ziel: True)
    r = welt["kanzlei"].post("/api/nutzer-aktion", json={
        "email": "inhaberin@salon.de", "aktion": "rolle", "rolle": "admin"})
    assert r.status_code == 403
    assert babu_web.rolle("inhaberin@salon.de") == "salon"
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        aktionen = [z[0] for z in c.execute("SELECT aktion FROM audit_log")]
    assert "rolle_verweigert" in aktionen


def test_kanzlei_stuft_keinen_betreiber_herab(welt, monkeypatch):
    monkeypatch.setattr(babu_web, "_in_reichweite", lambda un, ziel: True)
    r = welt["kanzlei"].post("/api/nutzer-aktion", json={
        "email": "betreiber@0711.io", "aktion": "rolle", "rolle": "salon"})
    assert r.status_code == 403
    assert babu_web.rolle("betreiber@0711.io") == "admin"


def test_betreiber_vergibt_jede_rolle(welt):
    r = welt["admin"].post("/api/nutzer-aktion", json={
        "email": "inhaberin@salon.de", "aktion": "rolle", "rolle": "kanzlei"})
    assert r.status_code == 200, r.text
    assert babu_web.rolle("inhaberin@salon.de") == "kanzlei"


def test_kanzlei_ohne_kopf_liest_die_standard_ablage_nicht(welt):
    assert welt["kanzlei"].get("/api/belege").status_code == 403
    assert babu_web.box_mitglied("kanzlei@afflek.de") is False


def test_betreiber_liest_die_standard_ablage_nur_als_konto_von_supremestudio(welt, monkeypatch):
    """Die Standard-Ablage ist die Box von SupremeStudio (seit 09.10.2026):
    die Rolle `admin` allein öffnet sie nicht mehr — über diesen Weg landeten
    am 03.10. fremde Belege bei SupremeStudio. Erst als eingetragenes Konto."""
    monkeypatch.delenv("BABU_STANDARD_KONTEN", raising=False)
    assert welt["admin"].get("/api/belege").status_code == 403
    assert babu_web.box_mitglied("betreiber@0711.io") is False
    monkeypatch.setenv("BABU_STANDARD_KONTEN", "betreiber@0711.io")
    assert welt["admin"].get("/api/belege").status_code == 200
    assert babu_web.box_mitglied("betreiber@0711.io") is True


def test_pat_betreiber_ohne_konto_bleibt_betreiber(welt, monkeypatch):
    """Der Zugangscode-Weg (BABU_ROLLEN) kennt keine nutzer-Zeile."""
    monkeypatch.setattr(babu_web, "ROLLEN", {"christoph": "admin"})
    assert babu_web.rolle("christoph") == "admin"
    assert babu_web._darf_rolle_vergeben("christoph", "admin") is True  # noqa: SLF001
    assert babu_web._darf_rolle_vergeben("kanzlei@afflek.de", "admin") is False  # noqa: SLF001
    assert babu_web._darf_rolle_vergeben("kanzlei@afflek.de", "salon") is True  # noqa: SLF001


def test_ich_meldet_die_rolle_fuer_die_portal_verwaltung(welt):
    """Das Portal entscheidet über den Betreiber-Teil anhand von /api/ich."""
    assert welt["admin"].get("/api/ich").json()["rolle"] == "admin"
    assert welt["kanzlei"].get("/api/ich").json()["rolle"] == "kanzlei"


def test_avv_mit_eigenen_angaben_nur_angemeldet(welt):
    babu_web.db_einstellung_setzen("inhaberin@salon.de", "betrieb_name", "Salon Sonne")
    babu_web.db_einstellung_setzen("inhaberin@salon.de", "anschrift", "Hauptstr. 1")
    inhaberin = _login("inhaberin@salon.de")
    r = inhaberin.get("/avv/mein")
    assert r.status_code == 200
    assert "Salon Sonne" in r.text and "Hauptstr. 1" in r.text
    # Andere sehen ihre eigenen Angaben, nicht die der Inhaberin.
    assert "Salon Sonne" not in welt["kanzlei"].get("/avv/mein").text
    # Öffentlich nur die Vorlage, ohne Anmeldung zur Anmeldung.
    anonym = TestClient(babu_web.app, base_url="https://testserver")
    assert "Salon Sonne" not in anonym.get("/avv").text
    r = anonym.get("/avv/mein", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/portal"
