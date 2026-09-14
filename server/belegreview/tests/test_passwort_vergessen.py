"""„Passwort vergessen?" ohne Betreiber: `POST /api/passwort-vergessen`.

Die Mechanik ist die aus `_passwort_neu` (Zeile, Frist, Bremse), neu ist nur,
wer sie anstößt — die Person selbst — und wohin der Link geht: per Mail. Die
Route antwortet immer 200, damit sie kein Verzeichnis der Konten ist. Und
wer sein Passwort neu setzt, entwertet damit die Geräteschlüssel.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASSWORT = "ein-langes-passwort-hier"


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    import babu_web
    import postfach
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "PORTAL_ORIGIN", "https://babu.test")
    # Kein Versand eingerichtet: jede Mail liegt als .eml im Postausgang —
    # genau das, was auf der H200V passiert, bis BABU_SMTP_HOST gesetzt ist.
    monkeypatch.setattr(postfach, "HOST", "")
    monkeypatch.setattr(postfach, "POSTAUSGANG", tmp_path / "postausgang")
    babu_web._RESET_VERSUCHE.clear()  # noqa: SLF001
    assert babu_web.nutzer_anlegen("nina@salon.de", "Nina", "Salon", "salon",
                                   passwort=PASSWORT, box=True) is not None
    client = TestClient(babu_web.app, base_url="https://testserver")
    return client, babu_web, tmp_path / "postausgang"


def _mails(postausgang: Path) -> list[Path]:
    return sorted(postausgang.glob("*.eml")) if postausgang.exists() else []


def test_bekanntes_konto_bekommt_einen_link_per_mail(welt):
    client, bw, postausgang = welt
    r = client.post("/api/passwort-vergessen", json={"email": "Nina@Salon.de "})
    assert r.status_code == 200 and r.json() == {"ok": True}
    mails = _mails(postausgang)
    assert len(mails) == 1
    inhalt = mails[0].read_bytes().decode("utf-8", "replace")
    assert "nina@salon.de" in inhalt
    assert "https://babu.test/portal#reset/" in inhalt.replace("=\r\n", "").replace("=\n", "")
    # Der Link steht nur in der Mail — in der Antwort nicht.
    assert "reset" not in r.text


def test_unbekanntes_konto_bekommt_dieselbe_antwort_aber_keine_mail(welt):
    client, bw, postausgang = welt
    r = client.post("/api/passwort-vergessen", json={"email": "niemand@salon.de"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert _mails(postausgang) == []
    r = client.post("/api/passwort-vergessen", json={"email": ""})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_die_bremse_je_konto_schweigt_nach_aussen(welt, monkeypatch):
    client, bw, postausgang = welt
    monkeypatch.setattr(bw, "_reset_anfordern_erlaubt", lambda un: False)
    r = client.post("/api/passwort-vergessen", json={"email": "nina@salon.de"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert _mails(postausgang) == []


def test_die_bremse_je_ip_ist_laut(welt):
    client, bw, postausgang = welt
    for _ in range(5):
        assert client.post("/api/passwort-vergessen",
                           json={"email": "niemand@salon.de"}).status_code == 200
    assert client.post("/api/passwort-vergessen",
                       json={"email": "niemand@salon.de"}).status_code == 429


def test_der_link_aus_der_mail_setzt_das_passwort_und_entwertet_geraete(welt):
    client, bw, postausgang = welt
    # Ein verbundenes Telefon: Geräteschlüssel wie bei /api/app-anmelden.
    bw._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    r = client.post("/api/app-anmelden",
                    json={"email": "nina@salon.de", "passwort": PASSWORT, "geraet": "iPhone"})
    assert r.status_code == 200, r.text
    schluessel = r.json()["schluessel"]
    assert bw.app_schluessel_pruefen(schluessel) == "nina@salon.de"

    client.post("/api/passwort-vergessen", json={"email": "nina@salon.de"})
    inhalt = _mails(postausgang)[0].read_bytes().decode("utf-8", "replace")
    inhalt = inhalt.replace("=\r\n", "").replace("=\n", "")
    token = inhalt.split("/portal#reset/", 1)[1].split()[0]

    r = client.post("/api/passwort-reset",
                    json={"token": token, "passwort": "ganz-neu-und-lang",
                          "passwort2": "ganz-neu-und-lang"})
    assert r.status_code == 200, r.text
    # Neues Passwort gilt, das alte nicht mehr …
    bw._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    assert client.post("/api/login", json={"email": "nina@salon.de",
                                           "passwort": "ganz-neu-und-lang"}).status_code == 200
    bw._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    assert client.post("/api/login", json={"email": "nina@salon.de",
                                           "passwort": PASSWORT}).status_code == 401
    # … und das Telefon muss sich einmal neu verbinden.
    assert bw.app_schluessel_pruefen(schluessel) is None
