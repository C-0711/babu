"""Passwort zurücksetzen ohne Klartext über Betriebsgrenzen (Plan 21, §7).

Zwei Teile: erst die reine Zustandslogik in `passwort_reset.py` (wie
`test_einladung.py` es für `einladung.py` vorführt — Token, Bremse,
Ablauf, Einlösung, ohne Datenbank), dann der HTTP-Weg über
`/api/nutzer-aktion` und `/api/passwort-reset` mit derselben
`welt`-Tradition wie `test_zugriff.py`: eine Kanzlei sieht das Passwort
eines fremden Betriebs nie, nur einen Link.
"""
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import passwort_reset as pr  # noqa: E402


def frisch(un="ziel@salon.de"):
    token, reset = pr.anfordern(un)
    return reset, token


# ————— Token / Anfordern —————

def test_ein_token_gehoert_zur_richtigen_person():
    reset, token = frisch("ziel@salon.de")
    assert reset.un == "ziel@salon.de"
    assert reset.offen
    assert token and len(token) >= 30


def test_die_adresse_wird_vereinheitlicht():
    reset, _ = frisch("  Ziel@Salon.DE  ")
    assert reset.un == "ziel@salon.de"


def test_zwei_anfragen_ergeben_zwei_verschiedene_token():
    _, a = frisch()
    _, b = frisch()
    assert a != b


def test_der_token_steht_nirgends_im_klartext():
    reset, token = frisch()
    assert token not in reset.token_hash
    assert reset.token_hash == pr.token_hash(token)


def test_nach_fuenf_versuchen_wird_gebremst():
    jetzt = pr._jetzt()  # noqa: SLF001
    frueher = [jetzt - timedelta(minutes=m) for m in (1, 5, 10, 20, 30)]
    assert pr.gebremst(frueher)


def test_alte_versuche_zaehlen_nicht_mehr_mit():
    alt = [pr._jetzt() - timedelta(days=2) for _ in range(10)]  # noqa: SLF001
    assert not pr.gebremst(alt)


# ————— Prüfen —————

def test_der_richtige_token_geht_durch():
    reset, token = frisch()
    assert pr.pruefen(reset, token).ok


def test_ein_falscher_token_faellt_durch():
    reset, _ = frisch()
    p = pr.pruefen(reset, "irgendwas-anderes")
    assert not p.ok and "nicht bekannt" in p.grund


def test_ein_unbekannter_reset_verraet_nichts_anderes():
    reset, _ = frisch()
    assert pr.pruefen(None, "x").grund == pr.pruefen(reset, "falsch").grund


def test_ein_abgelaufener_link_wird_abgelehnt():
    reset, token = frisch()
    reset.laeuft_ab = pr._jetzt() - timedelta(seconds=1)  # noqa: SLF001
    p = pr.pruefen(reset, token)
    assert not p.ok and "abgelaufen" in p.grund


def test_ein_eingeloester_link_gilt_nicht_noch_einmal():
    reset, token = frisch()
    reset.eingeloest = pr._jetzt()  # noqa: SLF001
    p = pr.pruefen(reset, token)
    assert not p.ok and "schon benutzt" in p.grund


# ————— Das Passwort, zweimal —————

def test_zwei_gleiche_gute_passwoerter_gehen_durch():
    assert pr.passwort_pruefen("ein-neues-passwort-2026", "ein-neues-passwort-2026").ok


def test_zu_kurz_wird_abgelehnt():
    p = pr.passwort_pruefen("kurz", "kurz")
    assert not p.ok and "Satz" in p.grund


def test_einloesen_prueft_beides():
    reset, token = frisch()
    ok = pr.einloesen(reset, token, "ein-neues-passwort-2026", "ein-neues-passwort-2026")
    assert ok.ok
    schlecht = pr.einloesen(reset, token, "kurz", "kurz")
    assert not schlecht.ok


# ═══════════════════════════════════════════════════════════════════════
# HTTP-Weg: /api/nutzer-aktion (passwort_neu) + /api/passwort-reset
# ═══════════════════════════════════════════════════════════════════════


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    _git(arbeit, "config", "user.name", "t")
    _git(arbeit, "config", "user.email", "t@l")
    (arbeit / "README.md").write_text("box")
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "init")
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

    sys.path.insert(0, str(HIER.parent))
    import babu_web
    import boxschreiber

    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(babu_web, "PORTAL_ORIGIN", "https://babu.0711.io")
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={})
    monkeypatch.setattr(babu_web, "ROLLEN", {})
    babu_web._LOGIN_VERSUCHE.clear()
    babu_web._RESET_VERSUCHE.clear()
    return babu_web


def _neuer_client(bw):
    from fastapi.testclient import TestClient
    return TestClient(bw.app, base_url="https://testserver")


def _konto(bw, email, rolle="salon", passwort="ein-langes-passwort-hier",
          gehoert_zu=None):
    assert bw.nutzer_anlegen(email, "", "Betrieb", rolle, passwort=passwort) is not None
    if gehoert_zu:
        with bw._DB_LOCK, bw._db() as c:
            c.execute("UPDATE nutzer SET gehoert_zu=? WHERE email=?", (gehoert_zu, email))
    return email, passwort


def _login(bw, email, passwort):
    client = _neuer_client(bw)
    bw._LOGIN_VERSUCHE.clear()
    r = client.post("/api/login", json={"email": email, "passwort": passwort})
    assert r.status_code == 200, r.text
    return client


# ————— Wer ein Klartext-Startpasswort bekommt —————

def test_admin_bekommt_immer_das_startpasswort(welt):
    """admin ist die Betreiber-Rolle — Betriebsgrenzen gelten für sie nicht."""
    bw = welt
    _, admin_pw = _konto(bw, "admin@babu.local", "admin")
    _konto(bw, "irgendwer@fremder-salon.de", "salon")
    admin = _login(bw, "admin@babu.local", admin_pw)

    r = admin.post("/api/nutzer-aktion",
                   json={"email": "irgendwer@fremder-salon.de", "aktion": "passwort_neu"})
    assert r.status_code == 200
    d = r.json()
    assert "startpasswort" in d and "link" not in d


def test_inhaberin_bekommt_das_startpasswort_fuer_ihr_team(welt):
    """Eigener Betrieb: die bestehende Übergabe bleibt — persönlich, sofort."""
    bw = welt
    _, chef_pw = _konto(bw, "chefin@salon-a.de", "kanzlei")  # PAT-Zugänge sind kanzlei
    _konto(bw, "team@salon-a.de", "mitarbeit", gehoert_zu="chefin@salon-a.de")
    chefin = _login(bw, "chefin@salon-a.de", chef_pw)

    r = chefin.post("/api/nutzer-aktion",
                    json={"email": "team@salon-a.de", "aktion": "passwort_neu"})
    assert r.status_code == 200
    d = r.json()
    assert "startpasswort" in d and "link" not in d


def test_kanzlei_bekommt_fuer_fremden_salon_nur_einen_link(welt):
    """Der eigentliche Fall aus Plan 21 §7: Kanzlei → fremder Salon."""
    bw = welt
    _, kanzlei_pw = _konto(bw, "kanzlei@babu.local", "kanzlei")
    _konto(bw, "inhaberin@fremder-salon.de", "salon")
    kanzlei = _login(bw, "kanzlei@babu.local", kanzlei_pw)

    r = kanzlei.post("/api/nutzer-aktion",
                     json={"email": "inhaberin@fremder-salon.de", "aktion": "passwort_neu"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert "link" in d and "startpasswort" not in d
    assert d["link"].startswith("https://babu.0711.io/portal#reset/")


# ————— Einlösen —————

def test_der_link_setzt_das_passwort_und_gilt_nur_einmal(welt):
    bw = welt
    _, kanzlei_pw = _konto(bw, "kanzlei@babu.local", "kanzlei")
    _konto(bw, "inhaberin@fremder-salon.de", "salon", passwort="das-alte-passwort")
    kanzlei = _login(bw, "kanzlei@babu.local", kanzlei_pw)
    link = kanzlei.post(
        "/api/nutzer-aktion",
        json={"email": "inhaberin@fremder-salon.de", "aktion": "passwort_neu"}
    ).json()["link"]
    token = link.split("#reset/")[1]

    anonym = _neuer_client(bw)
    r = anonym.post("/api/passwort-reset",
                    json={"token": token, "passwort": "ein-ganz-neues-passwort",
                          "passwort2": "ein-ganz-neues-passwort"})
    assert r.status_code == 200, r.text

    # Altes Passwort tot, neues lebt.
    bw._LOGIN_VERSUCHE.clear()
    alt = anonym.post("/api/login", json={"email": "inhaberin@fremder-salon.de",
                                          "passwort": "das-alte-passwort"})
    assert alt.status_code == 401
    bw._LOGIN_VERSUCHE.clear()
    neu = anonym.post("/api/login", json={"email": "inhaberin@fremder-salon.de",
                                          "passwort": "ein-ganz-neues-passwort"})
    assert neu.status_code == 200

    # Und der Link ist verbraucht.
    nochmal = anonym.post("/api/passwort-reset",
                          json={"token": token, "passwort": "noch-ein-passwort-2026",
                                "passwort2": "noch-ein-passwort-2026"})
    assert nochmal.status_code == 400
    assert "schon benutzt" in nochmal.json()["fehler"]


def test_ein_abgelaufener_link_wird_am_einloesen_abgelehnt(welt):
    bw = welt
    _, kanzlei_pw = _konto(bw, "kanzlei@babu.local", "kanzlei")
    _konto(bw, "inhaberin@fremder-salon.de", "salon")
    kanzlei = _login(bw, "kanzlei@babu.local", kanzlei_pw)
    link = kanzlei.post(
        "/api/nutzer-aktion",
        json={"email": "inhaberin@fremder-salon.de", "aktion": "passwort_neu"}
    ).json()["link"]
    token = link.split("#reset/")[1]

    with bw._DB_LOCK, bw._db() as c:
        c.execute("UPDATE passwort_reset SET laeuft_ab='2000-01-01T00:00:00+00:00' "
                 "WHERE token_hash=?", (pr.token_hash(token),))

    anonym = _neuer_client(bw)
    r = anonym.post("/api/passwort-reset",
                    json={"token": token, "passwort": "ein-ganz-neues-passwort",
                          "passwort2": "ein-ganz-neues-passwort"})
    assert r.status_code == 400
    assert "abgelaufen" in r.json()["fehler"]


def test_ein_unbekannter_token_wird_wie_ein_falscher_behandelt(welt):
    bw = welt
    anonym = _neuer_client(bw)
    r = anonym.post("/api/passwort-reset",
                    json={"token": "erfunden", "passwort": "ein-ganz-neues-passwort",
                          "passwort2": "ein-ganz-neues-passwort"})
    assert r.status_code == 400
    assert "nicht bekannt" in r.json()["fehler"]


# ————— Rate-Limit —————

def test_anfordern_wird_gebremst(welt):
    bw = welt
    _, kanzlei_pw = _konto(bw, "kanzlei@babu.local", "kanzlei")
    _konto(bw, "inhaberin@fremder-salon.de", "salon")
    kanzlei = _login(bw, "kanzlei@babu.local", kanzlei_pw)

    letzte = None
    for _ in range(pr.VERSUCHE_MAX):
        letzte = kanzlei.post(
            "/api/nutzer-aktion",
            json={"email": "inhaberin@fremder-salon.de", "aktion": "passwort_neu"})
        assert letzte.status_code == 200
    gebremst = kanzlei.post(
        "/api/nutzer-aktion",
        json={"email": "inhaberin@fremder-salon.de", "aktion": "passwort_neu"})
    assert gebremst.status_code == 429


def test_einloesen_wird_pro_ip_gebremst(welt):
    bw = welt
    anonym = _neuer_client(bw)
    for _ in range(5):
        r = anonym.post("/api/passwort-reset",
                        json={"token": "falsch", "passwort": "ein-neues-passwort-2026",
                              "passwort2": "ein-neues-passwort-2026"})
        assert r.status_code == 400
    gebremst = anonym.post("/api/passwort-reset",
                           json={"token": "falsch", "passwort": "ein-neues-passwort-2026",
                                 "passwort2": "ein-neues-passwort-2026"})
    assert gebremst.status_code == 429


# ————— Alte Zeilen räumen sich auf —————

def test_eingeloeste_zeilen_werden_beim_naechsten_anfordern_aufgeraeumt(welt):
    bw = welt
    _, kanzlei_pw = _konto(bw, "kanzlei@babu.local", "kanzlei")
    _konto(bw, "inhaberin@fremder-salon.de", "salon")
    kanzlei = _login(bw, "kanzlei@babu.local", kanzlei_pw)

    link = kanzlei.post(
        "/api/nutzer-aktion",
        json={"email": "inhaberin@fremder-salon.de", "aktion": "passwort_neu"}
    ).json()["link"]
    token = link.split("#reset/")[1]
    anonym = _neuer_client(bw)
    anonym.post("/api/passwort-reset",
               json={"token": token, "passwort": "ein-ganz-neues-passwort",
                     "passwort2": "ein-ganz-neues-passwort"})
    with bw._DB_LOCK, bw._db() as c:
        vorher = c.execute("SELECT COUNT(*) FROM passwort_reset WHERE un=?",
                           ("inhaberin@fremder-salon.de",)).fetchone()[0]
    assert vorher == 1     # die eingelöste Zeile steht noch

    kanzlei.post("/api/nutzer-aktion",
                json={"email": "inhaberin@fremder-salon.de", "aktion": "passwort_neu"})
    with bw._DB_LOCK, bw._db() as c:
        nachher = c.execute("SELECT COUNT(*) FROM passwort_reset WHERE un=?",
                           ("inhaberin@fremder-salon.de",)).fetchone()[0]
    assert nachher == 1    # die alte ist weg, nur die neue Zeile bleibt


# ————— Cross-Check gegen die test_zugriff.py-Tradition —————

def test_der_link_gibt_kein_konto_frei_das_es_nicht_gab(welt):
    """Wird das Konto zwischen Anfordern und Einlösen gelöscht, darf der
    Link trotzdem nicht plötzlich ein neues Konto anlegen — er setzt nur
    ein Passwort, er schafft keinen Zugang."""
    bw = welt
    _, kanzlei_pw = _konto(bw, "kanzlei@babu.local", "kanzlei")
    _konto(bw, "inhaberin@fremder-salon.de", "salon")
    kanzlei = _login(bw, "kanzlei@babu.local", kanzlei_pw)
    link = kanzlei.post(
        "/api/nutzer-aktion",
        json={"email": "inhaberin@fremder-salon.de", "aktion": "passwort_neu"}
    ).json()["link"]
    token = link.split("#reset/")[1]

    with bw._DB_LOCK, bw._db() as c:
        c.execute("DELETE FROM nutzer WHERE email=?", ("inhaberin@fremder-salon.de",))

    anonym = _neuer_client(bw)
    r = anonym.post("/api/passwort-reset",
                    json={"token": token, "passwort": "ein-ganz-neues-passwort",
                          "passwort2": "ein-ganz-neues-passwort"})
    assert r.status_code == 404
    assert bw.nutzer_holen("inhaberin@fremder-salon.de") is None
