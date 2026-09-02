"""Audit-Log der Verwaltungsrouten (Plan 21, Abschnitt 7).

Jede Aktion an einem fremden Zugang — Konto anlegen, deaktivieren,
Rolle ändern, Box frei-/sperren, Passwort zurücksetzen, DATEV-Export —
muss eine Zeile hinterlassen: wer, was, an wem. Kein Geheimnis darf darin
landen, und lesen darf das Log nur admin.
"""
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
import babu_web as _babu_web_beim_einsammeln  # noqa: E402

ECHTES_WER_TOKEN = _babu_web_beim_einsammeln.wer_token


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    """Eine minimale Box (für den Export-Test) + ein frisches portal.db."""
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


def _audit_zeilen(bw) -> list[dict]:
    with bw._DB_LOCK, bw._db() as c:
        return [dict(zip(("id", "zeit", "akteur_un", "aktion", "ziel_un",
                          "mandant_id", "details"), z))
                for z in c.execute(
                    "SELECT id, zeit, akteur_un, aktion, ziel_un, mandant_id, "
                    "details FROM audit_log ORDER BY id")]


# ————— Zeilen entstehen —————

def test_nutzer_anlegen_schreibt_eine_zeile(welt):
    bw = welt
    _, admin_pw = _konto(bw, "admin@babu.local", "admin")
    verwaltung = _login(bw, "admin@babu.local", admin_pw)

    r = verwaltung.post("/api/nutzer", json={"email": "neu@salon.de", "name": "Neu",
                                             "salon": "Neuer Salon", "rolle": "salon"})
    assert r.status_code == 200

    zeilen = _audit_zeilen(bw)
    treffer = [z for z in zeilen if z["aktion"] == "nutzer_anlegen"]
    assert len(treffer) == 1
    assert treffer[0]["akteur_un"] == "admin@babu.local"
    assert treffer[0]["ziel_un"] == "neu@salon.de"


@pytest.mark.parametrize("aktion,zusatz", [
    ("deaktivieren", {}),
    ("aktivieren", {}),
    ("rolle", {"rolle": "mitarbeit"}),
    ("box_freigeben", {}),
    ("box_sperren", {}),
])
def test_jede_nutzer_aktion_schreibt_eine_zeile(welt, aktion, zusatz):
    bw = welt
    _, admin_pw = _konto(bw, "admin@babu.local", "admin")
    _konto(bw, "ziel@salon.de", "salon")
    verwaltung = _login(bw, "admin@babu.local", admin_pw)

    r = verwaltung.post("/api/nutzer-aktion",
                        json={"email": "ziel@salon.de", "aktion": aktion, **zusatz})
    assert r.status_code == 200, r.text

    treffer = [z for z in _audit_zeilen(bw) if z["aktion"] == aktion]
    assert len(treffer) == 1
    assert treffer[0]["ziel_un"] == "ziel@salon.de"
    assert treffer[0]["akteur_un"] == "admin@babu.local"


def test_passwort_neu_schreibt_eine_zeile_startpasswort_weg(welt):
    """Innerhalb des eigenen Betriebs bleibt es beim Startpasswort — auditiert
    wird trotzdem, nur eben mit `weg=startpasswort` statt `weg=link`."""
    bw = welt
    _, admin_pw = _konto(bw, "admin@babu.local", "admin")
    _konto(bw, "ziel@salon.de", "salon")
    verwaltung = _login(bw, "admin@babu.local", admin_pw)

    r = verwaltung.post("/api/nutzer-aktion",
                        json={"email": "ziel@salon.de", "aktion": "passwort_neu"})
    assert r.status_code == 200
    assert "startpasswort" in r.json()

    treffer = [z for z in _audit_zeilen(bw) if z["aktion"] == "passwort_neu"]
    assert len(treffer) == 1
    assert treffer[0]["details"] != "{}"


def test_registrierung_einrichten_schreibt_eine_zeile(welt):
    bw = welt
    _, admin_pw = _konto(bw, "admin@babu.local", "admin")
    verwaltung = _login(bw, "admin@babu.local", admin_pw)
    with bw._DB_LOCK, bw._db() as c:
        cur = c.execute(
            "INSERT INTO registrierungen (zeit, daten, status) VALUES (?,?,?)",
            ("2026-09-01T00:00:00Z",
             '{"email":"lead@salon.de","salon":"Lead Salon"}', "neu"))
        reg_id = cur.lastrowid

    r = verwaltung.post("/api/registrierung-einrichten", json={"id": reg_id})
    assert r.status_code == 200, r.text

    treffer = [z for z in _audit_zeilen(bw) if z["aktion"] == "registrierung_einrichten"]
    assert len(treffer) == 1
    assert treffer[0]["ziel_un"] == "lead@salon.de"


def test_export_schreibt_eine_zeile(welt):
    bw = welt
    _, kanzlei_pw = _konto(bw, "kanzlei@babu.local", "kanzlei")
    kanzlei = _login(bw, "kanzlei@babu.local", kanzlei_pw)

    r = kanzlei.get("/api/export/2026-08.csv")
    assert r.status_code == 200, r.text

    treffer = [z for z in _audit_zeilen(bw) if z["aktion"] == "export"]
    assert len(treffer) == 1
    assert treffer[0]["akteur_un"] == "kanzlei@babu.local"
    assert treffer[0]["ziel_un"] is None
    assert "2026-08" in treffer[0]["details"]


# ————— Keine Geheimnisse —————

# Die Label-Zeichenkette "startpasswort"/"link" im `weg`-Feld ist erlaubt
# (sie sagt nur, welcher Weg genommen wurde) — verboten sind die JSON-Schlüssel,
# unter denen ein echtes Geheimnis stünde.
_VERBOTEN = ('"pw"', '"passwort"', '"passwort2"', '"token"', '"schluessel"')


def test_details_enthalten_kein_startpasswort(welt):
    bw = welt
    _, admin_pw = _konto(bw, "admin@babu.local", "admin")
    _konto(bw, "ziel@salon.de", "salon")
    verwaltung = _login(bw, "admin@babu.local", admin_pw)
    startpasswort = verwaltung.post(
        "/api/nutzer-aktion",
        json={"email": "ziel@salon.de", "aktion": "passwort_neu"}
    ).json()["startpasswort"]

    for z in _audit_zeilen(bw):
        for verboten in _VERBOTEN:
            assert verboten not in z["details"], z
        assert startpasswort not in z["details"]


def test_details_enthalten_kein_geheimes_reset_token(welt):
    """Setzt eine Kanzlei das Passwort eines fremden Betriebs zurück, steht
    der Link (und damit der Token) NIRGENDS im Audit-Log — sonst wäre das
    Log selbst ein zweiter Weg zum Konto."""
    bw = welt
    _, kanzlei_pw = _konto(bw, "kanzlei@babu.local", "kanzlei")
    _konto(bw, "fremd@anderer-salon.de", "salon")
    verwaltung = _login(bw, "kanzlei@babu.local", kanzlei_pw)

    r = verwaltung.post("/api/nutzer-aktion",
                        json={"email": "fremd@anderer-salon.de", "aktion": "passwort_neu"})
    assert r.status_code == 200
    link = r.json()["link"]
    token = link.split("#reset/")[1]

    for z in _audit_zeilen(bw):
        assert token not in z["details"]
        assert link not in z["details"]


# ————— Lesen: nur admin —————

def test_audit_lesen_nur_admin(welt):
    bw = welt
    _, admin_pw = _konto(bw, "admin@babu.local", "admin")
    _, kanzlei_pw = _konto(bw, "kanzlei@babu.local", "kanzlei")
    _, salon_pw = _konto(bw, "salon@a.de", "salon")

    admin = _login(bw, "admin@babu.local", admin_pw)
    kanzlei = _login(bw, "kanzlei@babu.local", kanzlei_pw)
    salon = _login(bw, "salon@a.de", salon_pw)

    assert admin.get("/api/audit").status_code == 200
    assert kanzlei.get("/api/audit").status_code == 403
    assert salon.get("/api/audit").status_code == 403


def test_audit_neueste_zuerst_und_seitenweise(welt):
    bw = welt
    _, admin_pw = _konto(bw, "admin@babu.local", "admin")
    admin = _login(bw, "admin@babu.local", admin_pw)
    for i in range(5):
        _konto(bw, f"ziel{i}@salon.de", "salon")
        admin.post("/api/nutzer-aktion",
                   json={"email": f"ziel{i}@salon.de", "aktion": "deaktivieren"})

    erste = admin.get("/api/audit?limit=2").json()
    assert len(erste["eintraege"]) == 2
    # Neueste zuerst: die letzte Deaktivierung (ziel4) steht oben.
    assert erste["eintraege"][0]["ziel_un"] == "ziel4@salon.de"
    assert erste["weiter"] is not None

    zweite = admin.get(f"/api/audit?limit=2&vor={erste['weiter']}").json()
    assert len(zweite["eintraege"]) == 2
    assert zweite["eintraege"][0]["id"] < erste["eintraege"][-1]["id"]
