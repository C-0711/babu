"""Wer darf einreichen — und wer wurde ausgesperrt.

Am 22.08.2026 meldete Nina: „ganz viele Belege in der App, im Backend
nichts." Die Ursache war ein Tor aus der Zeit vor den Konten. `/ablage` —
der einzige Weg, auf dem die App Belege hochlädt — prüfte gegen eine
Umgebungsliste mit GitChain-Namen wie „christoph0711.io". Wer sich in der
App mit E-Mail anmeldet, heißt aber „nina@0711.io" und stand nie darin.

Jedes Foto bekam 403 und blieb im Gerät liegen. Portal-Uploads gingen
durch, weil sie eine andere Tür benutzen — von außen sah das aus, als lade
die App einfach nicht hoch.

Diese Tests halten fest, dass beide Türen dieselbe sind.
"""
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "README.md").write_text("box")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "s"],
                   check=True, capture_output=True)
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

    sys.path.insert(0, str(HIER.parent))
    import babu_web
    import boxschreiber
    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(babu_web, "_vertrag_job", lambda *a, **k: None)
    monkeypatch.setattr(babu_web, "_brief_job", lambda *a, **k: None)
    # Genau die Lage vom 22.08.: nur der GitChain-Name steht in der Liste.
    monkeypatch.setattr(babu_web, "ERLAUBT", {"christoph0711.io"})
    babu_web._REG_ZULETZT.clear()
    return babu_web, tmp_path


def _konto(bw, email="nina@0711.io"):
    """Ein freigeschaltetes Konto samt Geräteschlüssel — wie in der App."""
    from fastapi.testclient import TestClient
    c = TestClient(bw.app, base_url="https://testserver")
    bw._REG_ZULETZT.clear()
    c.post("/api/signup", json={"salon": "Salon Nina", "email": email,
                                "passwort": "passwort-lang"})
    with bw._DB_LOCK, bw._db() as v:
        v.execute("UPDATE nutzer SET box=1 WHERE email=?", (email,))
    return c


JPEG = b"\xff\xd8\xff\xe0" + b"x" * 300


def test_die_app_darf_einreichen(welt):
    """Der eigentliche Befund: vorher kam hier 403."""
    bw, _ = welt
    c = _konto(bw)
    r = c.post("/ablage", files={"file": ("beleg.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 200, r.json()
    assert r.json()["ok"] is True


def test_der_alte_pat_weg_geht_weiter(welt):
    """Die Liste bleibt als zweiter Weg — GitChain-Namen stehen in keiner
    Nutzertabelle."""
    bw, _ = welt
    bw.wer_token = lambda t: "christoph0711.io" if t == "pat" else None
    from fastapi.testclient import TestClient
    c = TestClient(bw.app, base_url="https://testserver")
    r = c.post("/ablage", files={"file": ("b.jpg", JPEG, "image/jpeg")},
               headers={"Authorization": "Bearer pat"})
    assert r.status_code == 200


def test_ohne_freischaltung_bleibt_es_bei_403(welt):
    """Ein Konto ohne Belegbox darf weiterhin nichts einreichen."""
    bw, _ = welt
    c = _konto(bw, "fremd@x.de")
    with bw._DB_LOCK, bw._db() as v:
        v.execute("UPDATE nutzer SET box=0 WHERE email=?", ("fremd@x.de",))
    r = c.post("/ablage", files={"file": ("b.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 403
    assert "freigeschaltet" in r.json()["fehler"]


def test_ohne_anmeldung_bleibt_es_bei_401(welt):
    bw, _ = welt
    from fastapi.testclient import TestClient
    c = TestClient(bw.app, base_url="https://testserver")
    assert c.post("/ablage",
                  files={"file": ("b.jpg", JPEG, "image/jpeg")}).status_code == 401


def test_die_app_darf_ihre_ergebnisse_auch_lesen(welt):
    """Wer einreichen darf, darf auch nachsehen, was dabei herauskam."""
    bw, _ = welt
    c = _konto(bw)
    # Kein Review vorhanden → 404, aber eben nicht 403.
    assert c.get("/review/20260101-000000-abcdef-irgendwas").status_code != 403


def test_der_upload_landet_wirklich_in_der_box(welt):
    """403 zu beheben nützt nichts, wenn danach nichts ankommt."""
    bw, tmp = welt
    c = _konto(bw)
    c.post("/ablage", files={"file": ("beleg.jpg", JPEG, "image/jpeg")})
    stand = subprocess.run(["git", "-C", str(bw.STORE), "ls-tree", "-r",
                            "--name-only", "HEAD"],
                           capture_output=True, text=True).stdout
    assert any(p.startswith("docs/") and p.endswith(".jpg")
               for p in stand.split()), stand


def test_der_beleg_gehoert_der_hochladenden(welt):
    """Im Commit muss stehen, wer eingereicht hat — sonst ist die Box als
    Nachweis wertlos."""
    bw, _ = welt
    c = _konto(bw)
    c.post("/ablage", files={"file": ("beleg.jpg", JPEG, "image/jpeg")})
    autor = subprocess.run(["git", "-C", str(bw.STORE), "log", "-1", "--format=%an"],
                           capture_output=True, text=True).stdout.strip()
    assert autor == "nina@0711.io"


def test_dasselbe_foto_landet_nur_einmal_in_der_box(welt):
    """Doppeltipp oder zweiter Versuch nach Funkloch: byte-gleich = schon da.
    Die App bekommt trotzdem ein „ok" — für Nina IST es abgelegt."""
    bw, tmp = welt
    c = _konto(bw)
    r1 = c.post("/ablage", files={"file": ("beleg.jpg", JPEG, "image/jpeg")})
    assert r1.status_code == 200 and not r1.json().get("dublette")
    r2 = c.post("/ablage", files={"file": ("nochmal.jpg", JPEG, "image/jpeg")})
    assert r2.status_code == 200, r2.json()
    assert r2.json()["dublette"] is True
    assert r2.json()["datei"] == r1.json()["datei"], "verweist auf das Original"
    import subprocess
    baum = subprocess.run(["git", "-C", str(tmp / "babu.git"), "ls-tree", "-r",
                           "--name-only", "HEAD"],
                          capture_output=True, text=True).stdout
    assert baum.count(".jpg") == 1, "nur ein Foto in der Box"
