"""Das Anlagenverzeichnis im Portal: anlegen, ergänzen, ausgeben.

BABU-58. Es liegt in `portal.db`, nicht in der Belegbox — begründet im Commit:
die Liste ändert sich (Nutzungsdauer wird nachgetragen, ein Gut geht ab), und
sie ist abgeleitet. Der aufbewahrungspflichtige Teil, die Rechnung, liegt schon
versioniert in der Box; der Eintrag zeigt nur auf sie.

Geprüft wird der Weg von Ninas Seite aus: der Beleg schlägt sich als Vorschlag
vor, sie trägt die Nutzungsdauer nach, das Verzeichnis rechnet, und die Ausgabe
lässt sich dem Steuerberater geben.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


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
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient  # noqa: PLC0415
    client = TestClient(babu_web.app, base_url="https://testserver")
    client.post("/api/anmelden", json={"pat": "test-pat"})
    return client, arbeit, bare, babu_web


def _anlagebeleg(arbeit: Path, bare: Path, babu_web, stamm: str,
                 netto: float = 1500.0) -> None:
    """Ein Beleg, den kontierung.py als Anlagevermögen eingestuft hat."""
    (arbeit / "docs" / "2026-08").mkdir(parents=True, exist_ok=True)
    (arbeit / "docs" / "2026-08" / f"{stamm}.jpg").write_bytes(b"\xff\xd8jpeg")
    (arbeit / "review").mkdir(exist_ok=True)
    (arbeit / "review" / f"{stamm}.json").write_text(json.dumps({
        "datei": f"docs/2026-08/{stamm}.jpg", "engine": "test",
        "dokumentklasse": "Rechnung", "aehnlich": None, "ocr_text": "",
        "semantik": {"belegart": "Geräte und Einrichtung"},
        "vlm": {"lieferant": "Salontechnik Müller"},
        "felder": {"lieferant": "Salontechnik Müller", "beleg_nr": "R-77",
                   "datum": "12.08.2026", "netto": netto, "ust": netto * 0.19,
                   "brutto": netto * 1.19, "ust_satz": 19,
                   "summenprobe_ok": True, "bewirtungssignal": False,
                   "offen": []},
        "einschaetzung": {"belegart": "Rechnung", "kategorie": "anlagevermoegen",
                          "konto": "0650", "kontenrahmen": "SKR04",
                          "konto_skr04": "0650", "steuerschluessel": "9",
                          "hinweise": []},
    }, ensure_ascii=False))
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "review: test")
    _git(arbeit, "push", "-q", str(bare), "main")
    babu_web._INDEX.update(head=None, geprueft=0.0)


# ————— Anlegen —————

def test_ein_leeres_verzeichnis_ist_leer_aber_da(welt):
    client = welt[0]
    d = client.get("/api/anlagen").json()
    assert d["anlagen"] == []
    assert d["jahr"] == int(time.strftime("%Y"))
    assert any(a["code"] == "computer" for a in d["arten"])


def test_ein_anlagegut_laesst_sich_eintragen_und_rechnet_sofort(welt):
    client = welt[0]
    r = client.post("/api/anlagen", json={
        "bezeichnung": "Waschanlage", "angeschafft": "2026-04-01",
        "wert": "2400.00", "nutzungsdauer": 4})
    assert r.status_code == 200, r.text
    d = client.get("/api/anlagen", params={"jahr": 2026}).json()
    assert len(d["anlagen"]) == 1
    z = d["anlagen"][0]
    assert z["anschaffungswert"] == "2400.00"
    assert z["afa"] == "450.00"             # 600 € × 9/12
    assert z["restbuchwert"] == "1950.00"
    assert d["summe"]["afa"] == "450.00"


def test_unter_der_gwg_grenze_wird_abgelehnt_mit_grund(welt):
    client = welt[0]
    r = client.post("/api/anlagen", json={
        "bezeichnung": "Föhn", "angeschafft": "2026-04-01", "wert": "300.00"})
    assert r.status_code == 400
    assert "800" in r.json()["fehler"]


def test_ohne_bezeichnung_wird_gefragt_nicht_gespeichert(welt):
    client = welt[0]
    r = client.post("/api/anlagen", json={"angeschafft": "2026-04-01",
                                          "wert": "2400.00"})
    assert r.status_code == 400
    assert "heißt" in r.json()["fehler"] or "Name" in r.json()["fehler"]


def test_eine_bekannte_art_bringt_ihre_nutzungsdauer_mit(welt):
    client = welt[0]
    client.post("/api/anlagen", json={
        "bezeichnung": "iPad Kasse", "angeschafft": "2026-01-10",
        "wert": "1200.00", "art": "computer"})
    z = client.get("/api/anlagen", params={"jahr": 2026}).json()["anlagen"][0]
    assert z["nutzungsdauer"] == 1
    assert z["nutzungsdauer_geprueft"] is True
    assert "2022" in z["nutzungsdauer_quelle"]
    assert z["rueckfrage"] is None


def test_eine_unbekannte_art_kommt_als_rueckfrage_ins_verzeichnis(welt):
    """Nicht ablehnen: das Gut existiert. Aber es fehlt sichtbar etwas."""
    client = welt[0]
    client.post("/api/anlagen", json={
        "bezeichnung": "Frisierstuhl Nr. 3", "angeschafft": "2026-05-02",
        "wert": "1450.00", "art": "frisierstuhl"})
    d = client.get("/api/anlagen", params={"jahr": 2026}).json()
    z = d["anlagen"][0]
    assert z["nutzungsdauer"] is None
    assert "Jahre" in z["rueckfrage"]
    assert d["offen"] == 1


# ————— Ergänzen —————

def test_die_nutzungsdauer_laesst_sich_nachtragen(welt):
    client = welt[0]
    kennung = client.post("/api/anlagen", json={
        "bezeichnung": "Frisierstuhl", "angeschafft": "2026-01-01",
        "wert": "1200.00", "art": "frisierstuhl"}).json()["kennung"]
    r = client.post(f"/api/anlagen/{kennung}", json={"nutzungsdauer": 8})
    assert r.status_code == 200, r.text
    z = client.get("/api/anlagen", params={"jahr": 2026}).json()["anlagen"][0]
    assert z["nutzungsdauer"] == 8
    assert z["rueckfrage"] is None
    assert z["afa"] == "150.00"
    assert z["nutzungsdauer_geprueft"] is False   # von Hand, nicht amtlich


def test_ein_abgang_laesst_sich_vermerken(welt):
    client = welt[0]
    kennung = client.post("/api/anlagen", json={
        "bezeichnung": "Alter Stuhl", "angeschafft": "2026-01-01",
        "wert": "1200.00", "nutzungsdauer": 4}).json()["kennung"]
    client.post(f"/api/anlagen/{kennung}", json={"abgang": "2027-06-30"})
    assert len(client.get("/api/anlagen", params={"jahr": 2026}).json()["anlagen"]) == 1
    assert client.get("/api/anlagen", params={"jahr": 2029}).json()["anlagen"] == []


def test_ein_eintrag_laesst_sich_loeschen(welt):
    client = welt[0]
    kennung = client.post("/api/anlagen", json={
        "bezeichnung": "Versehen", "angeschafft": "2026-01-01",
        "wert": "1200.00", "nutzungsdauer": 4}).json()["kennung"]
    assert client.delete(f"/api/anlagen/{kennung}").status_code == 200
    assert client.get("/api/anlagen", params={"jahr": 2026}).json()["anlagen"] == []


def test_ein_fremder_eintrag_laesst_sich_nicht_aendern(welt):
    client = welt[0]
    assert client.post("/api/anlagen/9999", json={"nutzungsdauer": 5}).status_code == 404
    assert client.delete("/api/anlagen/9999").status_code == 404


# ————— Der Beleg schlägt sich selbst vor —————

def test_ein_anlagebeleg_wird_vorgeschlagen(welt):
    """Das war die Lücke: die App entschied „Anlagevermögen" — und dann nichts."""
    client, arbeit, bare, babu_web = welt
    _anlagebeleg(arbeit, bare, babu_web, "20260812-aaa-waschanlage")
    d = client.get("/api/anlagen", params={"jahr": 2026}).json()
    assert len(d["vorschlaege"]) == 1
    v = d["vorschlaege"][0]
    assert v["stamm"] == "20260812-aaa-waschanlage"
    assert v["wert"] == "1500.00"           # netto, nicht brutto
    assert v["angeschafft"] == "2026-08-12"
    assert v["bezeichnung"] == "Salontechnik Müller"


def test_ein_uebernommener_beleg_wird_nicht_zweimal_vorgeschlagen(welt):
    client, arbeit, bare, babu_web = welt
    _anlagebeleg(arbeit, bare, babu_web, "20260812-aaa-waschanlage")
    client.post("/api/anlagen", json={
        "bezeichnung": "Waschanlage", "angeschafft": "2026-08-12",
        "wert": "1500.00", "nutzungsdauer": 8,
        "beleg": "20260812-aaa-waschanlage"})
    d = client.get("/api/anlagen", params={"jahr": 2026}).json()
    assert d["vorschlaege"] == []
    assert d["anlagen"][0]["beleg"] == "20260812-aaa-waschanlage"


# ————— Ausgeben —————

def test_das_verzeichnis_laesst_sich_ausgeben(welt):
    client = welt[0]
    client.post("/api/anlagen", json={
        "bezeichnung": "Waschanlage", "angeschafft": "2026-04-01",
        "wert": "2400.00", "nutzungsdauer": 4})
    r = client.get("/api/anlagen/2026.csv")
    assert r.status_code == 200
    text = r.content.decode("cp1252")
    assert text.startswith("Bezeichnung;")
    assert "2400,00" in text and "450,00" in text
    assert "Anlagenverzeichnis" in r.headers["content-disposition"]


def test_ohne_anmeldung_geht_gar_nichts(welt):
    client = welt[0]
    client.cookies.clear()
    assert client.get("/api/anlagen").status_code == 401
    assert client.post("/api/anlagen", json={}).status_code == 401
