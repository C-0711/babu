"""Mitarbeiter der Kanzlei — die Inhaberin lädt selbst ein (seit 15.09.2026).

Bis dahin stellte der Betreiber jeden Sachbearbeiter von Hand in die
Kanzlei. Vier Dinge müssen hier stimmen:

1. Nur die Inhaberin lädt ein und entfernt; eine Sachbearbeiterin sieht die
   Liste, mehr nicht.
2. Ein neues Konto entsteht mit Rolle `kanzlei` und OHNE Passwort im
   Klartext — der Weg hinein ist der Link in der Einladung.
3. Ein Betriebskonto lässt sich nicht in die Kanzlei heben (es sähe sonst
   alle Mandanten), und niemand entfernt sich selbst oder eine Inhaberin.
4. Kanzlei A sieht die Mitarbeiter von Kanzlei B nicht.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import babu_web  # noqa: E402
import mandanten  # noqa: E402

PW = "ein-langes-passwort-hier"


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "POSTAUSGANG", tmp_path / "post", raising=False)
    import postfach
    monkeypatch.setattr(postfach, "POSTAUSGANG", tmp_path / "post")
    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    for mail, rolle in (("chefin@a.de", "kanzlei"), ("bea@a.de", "kanzlei"),
                        ("chef@b.de", "kanzlei"), ("nina@salon.de", "salon")):
        assert babu_web.nutzer_anlegen(mail, mail.split("@")[0].title(), "x", rolle,
                                       passwort=PW, box=False) is not None
    a = mandanten.kanzlei_anlegen("Kanzlei A", "chefin@a.de")
    mandanten.mitglied_anlegen(a, "bea@a.de", "sachbearbeiter")
    b = mandanten.kanzlei_anlegen("Kanzlei B", "chef@b.de")
    return {"a": a, "b": b, "post": tmp_path / "post"}


def _client(mail: str) -> TestClient:
    c = TestClient(babu_web.app, base_url="https://testserver")
    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    r = c.post("/api/login", json={"email": mail, "passwort": PW})
    assert r.status_code == 200, r.text
    return c


def _post(c, pfad, body):
    return c.post(pfad, json=body)


def test_die_liste_zeigt_die_eigene_kanzlei_und_wer_verwalten_darf(welt):
    d = _client("chefin@a.de").get("/api/kanzlei/mitglieder").json()
    assert [m["email"] for m in d["mitglieder"]] == ["chefin@a.de", "bea@a.de"]
    assert d["darf_verwalten"] is True and d["ich"] == "chefin@a.de"
    d = _client("bea@a.de").get("/api/kanzlei/mitglieder").json()
    assert len(d["mitglieder"]) == 2 and d["darf_verwalten"] is False
    # Kanzlei B sieht nur sich.
    d = _client("chef@b.de").get("/api/kanzlei/mitglieder").json()
    assert [m["email"] for m in d["mitglieder"]] == ["chef@b.de"]
    # Ein Betrieb sieht gar nichts.
    assert _client("nina@salon.de").get("/api/kanzlei/mitglieder").status_code == 403


def test_die_inhaberin_laedt_ein_und_die_einladung_geht_raus(welt):
    c = _client("chefin@a.de")
    r = _post(c, "/api/kanzlei/mitglieder", {"email": "tobias@a.de", "name": "Tobias Geib"})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "email": "tobias@a.de", "rolle": "sachbearbeiter",
                        "konto_neu": True, "eingeladen": True}
    n = babu_web.nutzer_holen("tobias@a.de")
    assert n["rolle"] == "kanzlei" and n["name"] == "Tobias Geib"
    assert mandanten.kanzlei_mitglied  # der Weg, den der Server im Betrieb geht
    d = c.get("/api/kanzlei/mitglieder").json()
    assert any(m["email"] == "tobias@a.de" and m["rolle"] == "sachbearbeiter"
               for m in d["mitglieder"])
    # Die Einladung liegt im Postausgang, mit Link und ohne Passwort.
    mails = list(welt["post"].glob("*tobias@a.de*.eml"))
    assert len(mails) == 1
    inhalt = mails[0].read_text()
    assert "/portal#reset/" in inhalt and "Kanzlei A" in inhalt
    assert PW not in inhalt
    # Zweimal einladen ist einmal zu viel.
    assert _post(c, "/api/kanzlei/mitglieder", {"email": "tobias@a.de"}).status_code == 409


def test_nur_die_inhaberin_darf(welt):
    bea = _client("bea@a.de")
    assert _post(bea, "/api/kanzlei/mitglieder", {"email": "x@a.de"}).status_code == 403
    assert _post(bea, "/api/kanzlei/mitglieder/entfernen", {"email": "chefin@a.de"}).status_code == 403
    assert _client("nina@salon.de").post("/api/kanzlei/mitglieder", json={"email": "x@a.de"}).status_code == 403


def test_kein_betriebskonto_und_keine_kaputte_adresse(welt):
    c = _client("chefin@a.de")
    r = _post(c, "/api/kanzlei/mitglieder", {"email": "nina@salon.de"})
    assert r.status_code == 409 and "Betrieb" in r.json()["fehler"]
    assert _post(c, "/api/kanzlei/mitglieder", {"email": "kein-at"}).status_code == 400


def test_entfernen_nimmt_nur_sachbearbeiter_und_nie_sich_selbst(welt):
    c = _client("chefin@a.de")
    assert _post(c, "/api/kanzlei/mitglieder/entfernen", {"email": "chefin@a.de"}).status_code == 400
    assert _post(c, "/api/kanzlei/mitglieder/entfernen", {"email": "chef@b.de"}).status_code == 404
    r = _post(c, "/api/kanzlei/mitglieder/entfernen", {"email": "bea@a.de"})
    assert r.status_code == 200, r.text
    assert [m["email"] for m in c.get("/api/kanzlei/mitglieder").json()["mitglieder"]] == ["chefin@a.de"]
    # Bea gibt es noch — sie sieht nur nichts mehr.
    assert babu_web.nutzer_holen("bea@a.de")["aktiv"]
    assert _client("bea@a.de").get("/api/kanzlei/mitglieder").json()["mitglieder"] == []
