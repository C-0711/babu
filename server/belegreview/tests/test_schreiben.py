"""Stufe-2-Tests: boxschreiber + POST /api/bewirtung + POST /api/hochladen.

Eigenes Modul mit frischem Store (Schreibtests mutieren den Zustand).
Remote = lokales Bare-Repo ohne Auth; der PAT-Header bleibt aus, weil die
PAT-Datei im Test nicht existiert.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
GOLDEN = HIER / "golden" / "review_weingaertle.json"
STAMM = "20260812-225200-c781d6-beleg_2026-07-21_weingaerty_22bf8b36"


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
    (arbeit / "review" / f"{STAMM}.json").write_text(json.dumps(gespeichert, ensure_ascii=False))
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", f"aufnahme+review: {STAMM}")
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

    sys.path.insert(0, str(HIER.parent))
    import babu_web
    import boxschreiber

    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           zeiten={}, oid_cache={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    client.post("/api/anmelden", json={"pat": "test-pat"})
    return client, bare


def test_bewirtung_antwort_macht_geprueft(welt):
    client, bare = welt
    vorher = client.get(f"/api/beleg/{STAMM}").json()
    assert vorher["status"] == "nachfrage"

    r = client.post(f"/api/bewirtung/{STAMM}",
                    json={"anlass": "Team-Essen nach der Schulung",
                          "teilnehmer": ["Nicole Baic", "Jana Allgaier"]})
    assert r.status_code == 200 and r.json()["ok"] is True

    log = subprocess.run(["git", "-C", str(bare), "log", "-1", "--format=%s|%an"],
                         capture_output=True, text=True).stdout.strip()
    assert log == f"bewirtung: {STAMM}|christoph0711.io"

    nachher = client.get(f"/api/beleg/{STAMM}").json()
    assert nachher["status"] == "geprüft"          # Trinkgeld-Offen ist nur Info
    assert nachher["bewirtung_beantwortet"] is True
    assert nachher["bewirtung"]["anlass"] == "Team-Essen nach der Schulung"
    assert nachher["bewirtung"]["teilnehmer"] == ["Nicole Baic", "Jana Allgaier"]


def test_bewirtung_validierung(welt):
    client, _ = welt
    r = client.post(f"/api/bewirtung/{STAMM}", json={"anlass": "", "teilnehmer": []})
    assert r.status_code == 400


def test_hochladen(welt):
    client, bare = welt
    r = client.post("/api/hochladen", params={"name": "kassenbon.jpg"},
                    content=b"\xff\xd8\xff\xe0bild")
    assert r.status_code == 200
    datei = r.json()["datei"]
    assert datei.startswith("docs/") and datei.endswith("-kassenbon.jpg")
    log = subprocess.run(["git", "-C", str(bare), "log", "-1", "--format=%s|%an"],
                         capture_output=True, text=True).stdout.strip()
    assert log.startswith("aufnahme: ") and log.endswith("|christoph0711.io")
    d = client.get("/api/belege").json()
    assert any(z["datei"] == datei and z["status"] == "erfasst" for z in d["belege"])


def test_export_nach_bewirtung(welt):
    """EXTF-Export: erst nach dem grünen Haken landet der Beleg im Stapel;
    festschreiben=1 markiert ihn als exportiert (Beleg-Weg „Bei der Kanzlei")."""
    client, bare = welt
    leer = client.get("/api/export/2026-08.csv")
    assert leer.status_code == 200
    assert len(leer.content.split(b"\r\n")) == 3          # Kopf + Spalten + Abschluss

    client.post(f"/api/bewirtung/{STAMM}",
                json={"anlass": "Team-Essen", "teilnehmer": ["Nicole"]})
    voll = client.get("/api/export/2026-08.csv")
    zeilen = voll.content.decode("cp1252").split("\r\n")
    assert len(zeilen) == 5                                # + 2 Buchungen (Mehrsatz!)
    assert zeilen[2].startswith("85,40;S;EUR")             # 7 % Speisen
    assert zeilen[3].startswith("57,20;S;EUR")             # 19 % Getränke
    assert "EXTF" in zeilen[0]

    fest = client.get("/api/export/2026-08.csv", params={"festschreiben": 1})
    assert fest.status_code == 200
    log = subprocess.run(["git", "-C", str(bare), "log", "-1", "--format=%s"],
                         capture_output=True, text=True).stdout.strip()
    assert log == "export: 2026-08"
    d = client.get(f"/api/beleg/{STAMM}").json()
    assert d["status"] == "exportiert"


def test_korrektur_fliesst_in_liste_und_export(welt):
    client, bare = welt
    r = client.post(f"/api/korrektur/{STAMM}",
                    json={"konto_skr04": "6640", "steuerschluessel": "8",
                          "buchungstext": "Bewirtung Weingärtle Team-Essen"})
    assert r.status_code == 200
    log = subprocess.run(["git", "-C", str(bare), "log", "-1", "--format=%s|%an"],
                         capture_output=True, text=True).stdout.strip()
    assert log == f"korrektur: {STAMM}|christoph0711.io"
    z = next(x for x in client.get("/api/belege").json()["belege"] if x["stamm"] == STAMM)
    assert z["korrigiert"] is True
    assert z["buchungstext"] == "Bewirtung Weingärtle Team-Essen"
    assert client.post(f"/api/korrektur/{STAMM}",
                       json={"konto_skr04": "abc"}).status_code == 400


def test_kpi(welt):
    client, _ = welt
    d = client.get("/api/kpi/2026-08").json()
    assert d["belege"] >= 1
    assert d["auto_geprueft_quote"]["ziel"] == 0.8
    assert d["offen_zur_frist"]["wert"] >= 0
    assert d["betrieb"]["requests"] > 0


def test_die_kennzahlen_haengen_auch_in_der_auswertung(welt):
    """Eine Quote, die niemand abruft, ist keine Kennzahl.

    `/api/kpi/{monat}` hatte keinen Aufrufer — weder App noch Portal. Die
    fachlichen Zahlen stehen deshalb jetzt auch in der Monatsauswertung,
    die das Portal ohnehin holt. Die Betriebswerte bleiben draußen: die
    gehören dem Betrieb, nicht der Inhaberin.
    """
    client, _ = welt
    kpi = client.get("/api/kpi/2026-08").json()
    auswertung = client.get("/api/monatsabschluss/2026-08").json()
    assert auswertung["kennzahlen"] == {k: v for k, v in kpi.items() if k != "betrieb"}
    assert "betrieb" not in auswertung["kennzahlen"]


def test_ablage_vertragsgleich(welt):
    """POST /ablage wie der alte Eingang: multipart file, {ok,ref,commit,datei};
    txt → 400 (Verbindungstest), Bearer-Auth."""
    client, bare = welt
    # Verbindungstest-Semantik: txt wird mit 400 abgelehnt = Token gültig
    r = client.post("/ablage", files={"file": ("verbindungstest.txt", b"x", "text/plain")},
                    headers={"Authorization": "Bearer test-pat"})
    assert r.status_code == 400
    # Echter Beleg
    r = client.post("/ablage",
                    files={"file": ("beleg_neu.jpg", b"\xff\xd8\xff\xe0bild", "image/jpeg")},
                    data={"notiz": "Team-Abend"},
                    headers={"Authorization": "Bearer test-pat"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True and d["ref"].endswith("/babu")
    assert d["datei"].endswith("-beleg_neu.jpg")
    log = subprocess.run(["git", "-C", str(bare), "log", "-1", "--format=%s|%b|%an"],
                         capture_output=True, text=True).stdout.strip()
    assert log.startswith("aufnahme: ") and "Team-Abend" in log
    assert log.endswith("|christoph0711.io")
    # Ohne gültigen Token und ohne Cookie → 401 (App-Mapping tokenFehler)
    client.cookies.clear()
    assert client.post("/ablage", files={"file": ("x.jpg", b"x", "image/jpeg")},
                       headers={"Authorization": "Bearer quatsch"}).status_code == 401


def test_hochladen_grenzen(welt):
    client, _ = welt
    assert client.post("/api/hochladen", params={"name": "boese.exe"},
                       content=b"x").status_code == 400
    assert client.post("/api/hochladen", params={"name": "leer.jpg"},
                       content=b"").status_code == 400


def test_angaben_nachtragen(welt):
    """Was babu nicht lesen konnte, trägt die Nutzerin selbst nach —
    ohne Verwaltungsrecht, als eigener Commit, sichtbar im Beleg."""
    client, bare = welt
    r = client.post(f"/api/angaben/{STAMM}",
                    json={"brutto": "4,20", "lieferant": "APCOA Parking",
                          "notiz": "Parken beim Großhandel"})
    assert r.status_code == 200
    assert r.json()["angaben"]["brutto"] == 4.20
    assert set(r.json()["angaben"]["beantwortet"]) == {"brutto", "lieferant"}

    log = subprocess.run(["git", "-C", str(bare), "log", "-1", "--format=%s|%an"],
                         capture_output=True, text=True).stdout.strip()
    assert log == f"angaben: {STAMM}|christoph0711.io"

    d = client.get(f"/api/beleg/{STAMM}").json()
    assert d["felder"]["brutto"] == 4.20
    assert d["felder"]["lieferant"] == "APCOA Parking"
    assert d.get("ergaenzt") is True
    assert client.get("/api/belege").json()["belege"][0].get("stamm")

    # Unlesbarer Betrag und leere Eingabe werden abgewiesen.
    assert client.post(f"/api/angaben/{STAMM}", json={"brutto": "vier euro"}).status_code == 400
    assert client.post(f"/api/angaben/{STAMM}", json={}).status_code == 400
