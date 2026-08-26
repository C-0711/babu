"""Wem die Belegbox gehört — und wer nicht hineinsehen darf.

Es gibt genau EINE Belegbox pro Betrieb. Ein Konto allein ist deshalb noch
kein Zugang zu ihren Belegen: freigeschaltet ist, wer zum Betrieb gehört
(Inhaberin, ihr Team) oder ihn betreut (Kanzlei). Wer sich selbst
registriert, bekommt sein Konto — aber keine fremden Belege zu sehen.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
GOLDEN = HIER / "golden" / "review_weingaertle.json"
STAMM = "20260812-225200-c781d6-beleg_2026-07-21_weingaerty_22bf8b36"

# Die `welt`-Fixture ersetzt `babu_web.wer_token` dauerhaft durch einen
# Platzhalter, damit kein Test gitchain.de anruft. Wer die echte Funktion
# prüfen will, muss sie sich vorher merken — beim Einsammeln der Tests steht
# sie noch.
sys.path.insert(0, str(HIER.parent))
import babu_web as _babu_web_beim_einsammeln  # noqa: E402

ECHTES_WER_TOKEN = _babu_web_beim_einsammeln.wer_token


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    _git(arbeit, "config", "user.name", "t")
    _git(arbeit, "config", "user.email", "t@l")
    golden = json.loads(GOLDEN.read_text())
    gespeichert = {k: v for k, v in golden.items() if k not in ("audit", "buchungssatz")}
    (arbeit / "docs" / "2026-08").mkdir(parents=True)
    (arbeit / "docs" / "2026-08" / f"{STAMM}.jpg").write_bytes(b"\xff\xd8x")
    (arbeit / "review").mkdir()
    (arbeit / "review" / f"{STAMM}.json").write_text(
        json.dumps(gespeichert, ensure_ascii=False))
    (arbeit / "kassenbuch" / "2026-08").mkdir(parents=True)
    (arbeit / "kassenbuch" / "2026-08" / "2026-08-17.json").write_text(json.dumps(
        {"datum": "2026-08-17", "einnahmenBar": 412.5, "ecZahlungen": 388.0}))
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", f"aufnahme+review: {STAMM}")
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
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None
    babu_web._LOGIN_VERSUCHE.clear()
    babu_web._REG_ZULETZT.clear()
    return babu_web


def _neuer_client(bw):
    from fastapi.testclient import TestClient
    return TestClient(bw.app, base_url="https://testserver")


def _inhaberin(bw):
    """Der freigeschaltete Zugang (Allowlist) — ihr gehört die Box."""
    client = _neuer_client(bw)
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    return client


def _fremde(bw, email="fremd@woanders.de"):
    """Jemand, der sich einfach selbst registriert hat."""
    bw._REG_ZULETZT.clear()
    client = _neuer_client(bw)
    r = client.post("/api/signup", json={"salon": "Fremder Salon", "email": email,
                                         "passwort": "passwort-lang-genug"})
    assert r.status_code == 200
    return client


# ————— Die Belegbox ist nicht öffentlich —————

BOX_LESEN = [
    "/api/belege",
    f"/api/beleg/{STAMM}",
    f"/api/beleg/{STAMM}/bild",
    "/api/monat/2026-08",
    "/api/kpi/2026-08",
    "/api/dokumente",
    "/api/ablage",
    "/api/abgleich/2026-08",
    "/api/monatsabschluss/2026-08",
    "/api/salon-check?jahr=2025",
]


@pytest.mark.parametrize("pfad", BOX_LESEN)
def test_fremdes_konto_sieht_keine_belege(welt, pfad):
    client = _fremde(welt)
    r = client.get(pfad)
    assert r.status_code == 403, f"{pfad} gibt fremde Daten heraus"
    assert "freigeschaltet" in r.json()["fehler"]


@pytest.mark.parametrize("pfad", BOX_LESEN)
def test_inhaberin_kommt_ueberall_hin(welt, pfad):
    client = _inhaberin(welt)
    assert client.get(pfad).status_code == 200, f"{pfad} sperrt die Inhaberin aus"


BOX_SCHREIBEN = [
    ("post", "/api/hochladen?name=beleg.jpg", {"content": b"\xff\xd8bild"}),
    ("post", "/api/dokumente?name=brief.pdf", {"content": b"%PDF-1.4"}),
    ("post", f"/api/bewirtung/{STAMM}",
     {"json": {"anlass": "Essen", "teilnehmer": ["A"]}}),
    ("post", f"/api/angaben/{STAMM}", {"json": {"brutto": "12,00"}}),
    ("post", "/api/kassenbuch", {"json": {"datum": "2026-08-20", "einnahmenBar": 100}}),
    ("post", "/api/kontoauszug?name=auszug.pdf", {"content": b"%PDF-1.4"}),
    ("post", "/api/abschluss?jahr=2025&name=euer.pdf", {"content": b"%PDF-1.4"}),
    ("post", "/api/monatsabschluss/2026-08/freigeben", {}),
]


@pytest.mark.parametrize("methode,pfad,kwargs", BOX_SCHREIBEN)
def test_fremdes_konto_schreibt_nicht_in_die_box(welt, methode, pfad, kwargs):
    client = _fremde(welt)
    r = getattr(client, methode)(pfad, **kwargs)
    assert r.status_code == 403, f"{pfad} nimmt fremde Schreibzugriffe an"


def test_fremdes_konto_fragt_den_chat_nicht_ueber_fremde_belege(welt):
    client = _fremde(welt)
    assert client.post("/chat", json={"frage": "Was habe ich ausgegeben?"}
                       ).status_code == 403


def test_eigenes_konto_bleibt_nutzbar(welt):
    """Kein Rauswurf: Einstellungen, Team und Fristen sind seine eigenen Daten."""
    client = _fremde(welt)
    assert client.get("/api/ich").status_code == 200
    assert client.get("/api/einstellungen").status_code == 200
    assert client.post("/api/einstellungen", json={"telefon": "0711 123"}).status_code == 200
    assert client.get("/api/team").status_code == 200
    assert client.get("/api/fristen/2026").status_code == 200


def test_ich_sagt_ob_die_box_offen_ist(welt):
    """Die Oberfläche muss den Unterschied kennen, um ehrlich zu bleiben."""
    assert _inhaberin(welt).get("/api/ich").json()["box"] is True
    assert _fremde(welt).get("/api/ich").json()["box"] is False


def test_team_der_inhaberin_darf_in_die_box(welt):
    """Eine Mitarbeiterin arbeitet in DER Box ihres Salons — mit ihren Rechten."""
    bw = welt
    inhaberin = _inhaberin(bw)
    d = inhaberin.post("/api/team", json={"name": "Jana", "email": "jana@salon.de",
                                          "betrag": "2400", "darf_belege": True,
                                          "darf_kasse": False}).json()
    jana = next(p for p in d["team"] if p["name"] == "Jana")
    start = inhaberin.post("/api/team-zugang", json={"id": jana["id"]}).json()["startpasswort"]

    jana_client = _neuer_client(bw)
    bw._LOGIN_VERSUCHE.clear()
    assert jana_client.post("/api/login", json={"email": "jana@salon.de",
                                                "passwort": start}).status_code == 200
    # Sie sieht die Belege des Salons …
    assert jana_client.get("/api/belege").status_code == 200
    assert jana_client.get("/api/ich").json()["box"] is True
    # … darf einreichen (freigegeben) …
    assert jana_client.post("/api/hochladen?name=bon.jpg",
                            content=b"\xff\xd8bild").status_code == 200
    # … aber nicht an die Kasse und nicht an die Zahlen.
    assert jana_client.post("/api/kassenbuch",
                            json={"datum": "2026-08-20", "einnahmenBar": 100}
                            ).status_code == 403
    assert jana_client.get("/api/monatsabschluss/2026-08").status_code == 403


def test_abgeschaltetes_konto_kommt_nicht_mehr_rein(welt):
    """Wer geht, verliert den Zugang — auch mit gültigem Cookie."""
    bw = welt
    inhaberin = _inhaberin(bw)
    d = inhaberin.post("/api/team", json={"name": "Mira", "email": "mira@salon.de",
                                          "betrag": "1200", "darf_belege": True}).json()
    mira = next(p for p in d["team"] if p["name"] == "Mira")
    start = inhaberin.post("/api/team-zugang", json={"id": mira["id"]}).json()["startpasswort"]
    mira_client = _neuer_client(bw)
    bw._LOGIN_VERSUCHE.clear()
    mira_client.post("/api/login", json={"email": "mira@salon.de", "passwort": start})
    assert mira_client.get("/api/belege").status_code == 200

    inhaberin.post("/api/team-aktion", json={"id": mira["id"], "aktion": "beenden"})
    assert mira_client.get("/api/belege").status_code == 403


def test_bestehende_zugaenge_verlieren_die_box_nicht(welt):
    """Migration: wer schon eingerichtet war, arbeitet weiter — die neue
    Spalte steht für alte Zeilen auf 1."""
    bw = welt
    with bw._DB_LOCK, bw._db() as c:
        c.execute("""INSERT INTO nutzer (email, name, salon, rolle, pw, aktiv, angelegt)
                     VALUES ('alt@salon.de','Alt','Alter Salon','salon',?,1,'2026-01-01')""",
                  (bw.pw_hash("altes-passwort"),))
    assert bw.nutzer_holen("alt@salon.de")["box"] is True
    assert bw.box_mitglied("alt@salon.de") is True


def test_verwaltung_richtet_die_box_ein(welt):
    """Aus einer Registrierung wird ein echter Zugang — mit einem Schalter."""
    bw = welt
    fremde = _fremde(bw, "neu@salon.de")
    assert fremde.get("/api/belege").status_code == 403

    verwaltung = _inhaberin(bw)          # PAT-Zugang hat Rolle kanzlei
    r = verwaltung.post("/api/nutzer-aktion",
                        json={"email": "neu@salon.de", "aktion": "box_freigeben"})
    assert r.status_code == 200
    assert fremde.get("/api/belege").status_code == 200
    assert fremde.get("/api/ich").json()["box"] is True

    # Und wieder zu.
    verwaltung.post("/api/nutzer-aktion",
                    json={"email": "neu@salon.de", "aktion": "box_sperren"})
    assert fremde.get("/api/belege").status_code == 403


def test_der_pat_zwischenspeicher_schluesselt_auf_sha256(welt, monkeypatch):
    """`hash()` ist der falsche Schlüssel für einen Zugangsspeicher.

    Er ist je Prozessstart zufällig gesalzen und für Zeichenketten auf Tempo
    gebaut, nicht auf Kollisionsfreiheit — wer zwei Token mit demselben
    `hash()` findet, bekommt das Konto des anderen.
    """
    bw = welt

    class Antwort:
        status_code = 200

        @staticmethod
        def json():
            return {"un": "christoph0711.io"}

    monkeypatch.setattr(bw.requests, "get", lambda *a, **k: Antwort())
    bw._CACHE.clear()
    try:
        assert ECHTES_WER_TOKEN("ein-geheimes-token") == "christoph0711.io"
        assert list(bw._CACHE) == [hashlib.sha256(b"ein-geheimes-token").hexdigest()]
    finally:
        bw._CACHE.clear()


# ————— Die vier Meldungen-Routen sind ebenfalls belegbox-gebunden —————
#
# Vorher hingen sie an `_api_wache` (Allowlist ODER bloß aktives Konto) —
# ein frisches /api/signup-Konto ohne jede Belegbox kam durch. Diese Tests
# wären der fehlende Fall gewesen, der das damals hätte auffangen müssen:
# ein fremdes, aktives Konto OHNE Box muss hier draußen bleiben, genau wie
# bei /ablage und den übrigen box-gebundenen Routen oben.

MELDUNGEN_SCHREIBEN = [
    ("post", "/api/rueckmeldung", {"json": {"text": "Etwas stimmt nicht."}}),
    ("post", "/api/rueckmeldungen/1/freigeben", {}),
    ("post", "/api/rueckmeldungen/1/beanstanden", {"json": {"text": "Passt so nicht."}}),
]


@pytest.mark.parametrize("methode,pfad,kwargs", MELDUNGEN_SCHREIBEN)
def test_fremdes_konto_ohne_box_kommt_nicht_an_die_meldungen(welt, methode, pfad, kwargs):
    client = _fremde(welt)
    r = getattr(client, methode)(pfad, **kwargs)
    assert r.status_code in (401, 403), f"{pfad} lässt ein boxloses Konto durch"


def test_fremdes_konto_ohne_box_sieht_die_meldungsliste_nicht(welt):
    client = _fremde(welt)
    assert client.get("/api/rueckmeldungen").status_code in (401, 403)


def test_von_der_verwaltung_angelegte_konten_haben_die_box(welt):
    bw = welt
    verwaltung = _inhaberin(bw)
    r = verwaltung.post("/api/nutzer", json={"email": "kollegin@kanzlei.de",
                                             "name": "Kollegin", "rolle": "salon"})
    assert r.status_code == 200
    assert bw.box_mitglied("kollegin@kanzlei.de") is True
    assert any(n["email"] == "kollegin@kanzlei.de" and n["box"] is True
               for n in verwaltung.get("/api/nutzer").json()["nutzer"])
