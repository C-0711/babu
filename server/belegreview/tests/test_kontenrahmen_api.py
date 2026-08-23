"""Der Kontenrahmen im Portal: lesen, wählen, wechseln — und der Export.

BABU-57. Bis 23.08.2026 gab es dafür nur `BABU_KONTENRAHMEN` in der Umgebung
des Dienstes. Hier wird geprüft, dass Nina ihn selbst setzen kann, dass ein
Wechsel nicht als Schalter durchgeht, und dass eine Vermischung spätestens
beim Buchungsstapel auffällt — dort, wo die Konten das Haus verlassen.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _beleg(arbeit: Path, stamm: str, konto: str, rahmen: str, datum: str) -> None:
    (arbeit / "docs" / "2026-08").mkdir(parents=True, exist_ok=True)
    (arbeit / "docs" / "2026-08" / f"{stamm}.jpg").write_bytes(b"\xff\xd8jpeg")
    (arbeit / "review").mkdir(exist_ok=True)
    (arbeit / "review" / f"{stamm}.json").write_text(json.dumps({
        "datei": f"docs/2026-08/{stamm}.jpg", "engine": "test",
        "dokumentklasse": "Rechnung", "semantik": {"belegart": "Wareneinkauf"},
        "vlm": {"lieferant": "Großhandel", "buchungstext": "Einkauf"},
        "aehnlich": None, "ocr_text": "",
        "felder": {"lieferant": "Großhandel", "beleg_nr": "R-1", "datum": datum,
                   "netto": 100.0, "ust": 19.0, "brutto": 119.0, "ust_satz": 19,
                   "summenprobe_ok": True, "bewirtungssignal": False, "offen": []},
        "einschaetzung": {"belegart": "Rechnung", "konto": konto,
                          "kontenrahmen": rahmen,
                          "konto_skr04": konto if rahmen == "SKR04" else None,
                          "steuerschluessel": "9", "hinweise": []},
    }, ensure_ascii=False))


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        _git(arbeit, "config", k, v)
    (arbeit / "README.md").write_text("box")
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "start")
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

    sys.path.insert(0, str(HIER.parent))
    import babu_web  # noqa: PLC0415

    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.delenv("BABU_KONTENRAHMEN", raising=False)
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient  # noqa: PLC0415
    client = TestClient(babu_web.app, base_url="https://testserver")
    client.post("/api/anmelden", json={"pat": "test-pat"})
    return client, arbeit, bare, babu_web


def _neu_veroeffentlichen(arbeit: Path, bare: Path, babu_web) -> None:
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "review: test")
    _git(arbeit, "push", "-q", str(bare), "main")
    babu_web._INDEX.update(head=None, geprueft=0.0)


# ————— Lesen —————

def test_ohne_wahl_gilt_die_vorgabe_und_sie_sagt_es(welt):
    client = welt[0]
    d = client.get("/api/kontenrahmen").json()
    assert d["rahmen"] == "SKR04"
    assert d["gewaehlt"] is False          # noch nichts entschieden
    assert d["rahmen_liste"] == ["SKR03", "SKR04"]


def test_die_einstellungen_zeigen_den_geltenden_rahmen_mit(welt):
    """Damit App und Portal ihn in einem Zug bekommen."""
    client = welt[0]
    e = client.get("/api/einstellungen").json()
    assert e["kontenrahmen_gilt"] == "SKR04"


# ————— Wählen —————

def test_die_erste_wahl_geht_ohne_rueckfrage(welt):
    client, *_ = welt
    r = client.post("/api/kontenrahmen", json={"rahmen": "SKR03"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["rahmen"] == "SKR03" and d["gewaehlt"] is True
    assert client.get("/api/einstellungen").json()["kontenrahmen"] == "SKR03"


def test_ein_unbekannter_rahmen_wird_abgelehnt(welt):
    client, *_ = welt
    r = client.post("/api/kontenrahmen", json={"rahmen": "SKR49"})
    assert r.status_code == 400
    assert "SKR03" in r.json()["fehler"]        # sie sagt, was es gibt


def test_der_kontenrahmen_geht_nicht_ueber_die_sammelroute(welt):
    """Sonst wäre der Wechsel doch wieder ein Schalter — ohne Jahresfrage."""
    client, *_ = welt
    r = client.post("/api/einstellungen", json={"kontenrahmen": "SKR03"})
    assert r.status_code == 409
    assert "kontenrahmen" in r.json()["fehler"].lower()
    assert client.get("/api/kontenrahmen").json()["rahmen"] == "SKR04"


# ————— Wechseln ist ein Jahreswechsel —————

def test_ein_wechsel_verlangt_eine_bestaetigung(welt):
    client, *_ = welt
    client.post("/api/kontenrahmen", json={"rahmen": "SKR04"})
    r = client.post("/api/kontenrahmen", json={"rahmen": "SKR03"})
    assert r.status_code == 409
    assert "Wirklich umstellen?" in r.json()["rueckfrage"]
    assert client.get("/api/kontenrahmen").json()["rahmen"] == "SKR04"


def test_ein_bestaetigter_wechsel_wird_vorgemerkt_nicht_geschaltet(welt):
    """Das laufende Jahr behält seinen Rahmen — sonst zwei in einem Stapel.

    Der Wechsel ist damit kein Schalter, sondern eine Vormerkung: er tritt am
    1. Januar von selbst in Kraft, ohne dass jemand daran denken muss."""
    import time  # noqa: PLC0415
    client, arbeit, bare, babu_web = welt
    heute = int(time.strftime("%Y"))
    client.post("/api/kontenrahmen", json={"rahmen": "SKR04"})
    _beleg(arbeit, "20260812-aaa-einkauf", "5400", "SKR04", "12.08.2026")
    _neu_veroeffentlichen(arbeit, bare, babu_web)

    r = client.post("/api/kontenrahmen",
                    json={"rahmen": "SKR03", "bestaetigt": True})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["rahmen"] == "SKR04"                       # noch nicht
    assert d["wechsel_geplant"] == {"jahr": heute + 1, "rahmen": "SKR03"}
    # und die Belege dieses Jahres bleiben exportierbar
    assert client.get("/api/export/2026-08.csv").status_code == 200


def test_ein_vorgemerkter_wechsel_tritt_im_zieljahr_von_selbst_ein(welt):
    """Am 1. Januar schaltet niemand etwas — die Vormerkung wirkt einfach."""
    import kontenrahmen as kr  # noqa: PLC0415
    e = {"kontenrahmen": "SKR04", "kontenrahmen_kommt": "2027:SKR03"}
    assert kr.aus_einstellungen(e, jahr=2026) == "SKR04"
    assert kr.aus_einstellungen(e, jahr=2027) == "SKR03"
    assert kr.aus_einstellungen(e, jahr=2031) == "SKR03"


def test_mitten_im_jahr_bei_gebuchten_belegen_geht_es_nicht(welt):
    client, arbeit, bare, babu_web = welt
    client.post("/api/kontenrahmen", json={"rahmen": "SKR04"})
    _beleg(arbeit, "20260812-aaa-einkauf", "5400", "SKR04", "12.08.2026")
    _neu_veroeffentlichen(arbeit, bare, babu_web)

    r = client.post("/api/kontenrahmen",
                    json={"rahmen": "SKR03", "ab_jahr": 2026, "bestaetigt": True})
    assert r.status_code == 409
    assert "2026" in r.json()["begruendung"]
    assert client.get("/api/kontenrahmen").json()["rahmen"] == "SKR04"


def test_die_gebuchten_jahre_stehen_in_der_auskunft(welt):
    """Damit die Oberfläche sagen kann, warum es nicht sofort geht."""
    client, arbeit, bare, babu_web = welt
    _beleg(arbeit, "20260812-aaa-einkauf", "5400", "SKR04", "12.08.2026")
    _neu_veroeffentlichen(arbeit, bare, babu_web)
    assert client.get("/api/kontenrahmen").json()["gebuchte_jahre"] == [2026]


# ————— Der Export ist die letzte Kontrolle —————

def test_ein_gemischter_stapel_wird_nicht_ausgeliefert(welt):
    """Zwei Rahmen in einem Buchungsstapel — hier oder beim Steuerberater."""
    client, arbeit, bare, babu_web = welt
    client.post("/api/kontenrahmen", json={"rahmen": "SKR03"})
    _beleg(arbeit, "20260812-aaa-einkauf", "3400", "SKR03", "12.08.2026")
    _beleg(arbeit, "20260812-bbb-schere", "5400", "SKR04", "13.08.2026")
    _neu_veroeffentlichen(arbeit, bare, babu_web)

    r = client.get("/api/export/2026-08.csv")
    assert r.status_code == 409, r.text
    d = r.json()
    assert "5400" in d["fehler"]
    assert "schere" in d["fehler"]


def test_ein_sauberer_stapel_geht_raus(welt):
    client, arbeit, bare, babu_web = welt
    client.post("/api/kontenrahmen", json={"rahmen": "SKR03"})
    _beleg(arbeit, "20260812-aaa-einkauf", "3400", "SKR03", "12.08.2026")
    _neu_veroeffentlichen(arbeit, bare, babu_web)

    r = client.get("/api/export/2026-08.csv")
    assert r.status_code == 200
    zeilen = r.content.decode("cp1252").split("\r\n")
    assert zeilen[2].split(";")[6] == "3400"
