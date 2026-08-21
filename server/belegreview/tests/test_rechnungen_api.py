"""Die ganze Strecke: Rechnung stellen, PDF nachreichen, bezahlt, Storno.

Geprüft wird, was am Server dranhängt — dass die Nummer vom Server kommt und
lückenlos bleibt, dass die Rechnung in der Belegbox landet und dass sie
erst als Erlös zählt, wenn das Geld da ist.
"""
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent

STAMMDATEN = {"betrieb_name": "Salon Nina", "anschrift": "Hauptstraße 5, Stuttgart",
              "steuernummer": "99012/34567", "kleinunternehmer": "Nein"}
EMPF = {"name": "Jana Allgaier", "anschrift": "Blumenweg 2, Stuttgart"}


def pos(text="Stuhlmiete August", betrag=450.0, satz=19):
    return {"text": text, "einzelpreis": betrag, "ust_satz": satz}


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "README.md").write_text("box")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "start"],
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
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={}, rechnungen={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None
    babu_web._LOGIN_VERSUCHE.clear()
    babu_web._REG_ZULETZT.clear()

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    for k, v in STAMMDATEN.items():
        babu_web.db_einstellung_setzen("christoph0711.io", k, v)
    return client, bare, babu_web


def _stellen(client, datum="2026-08-21", positionen=None, empfaenger=None):
    # `positionen=[]` muss durchkommen — nicht durch die Vorgabe ersetzt werden.
    return client.post("/api/rechnungen", json={
        "datum": datum, "empfaenger": empfaenger or EMPF,
        "positionen": [pos()] if positionen is None else positionen})


def _im_stand(bare: Path) -> list[str]:
    return subprocess.run(["git", "-C", str(bare), "ls-tree", "-r", "--name-only", "HEAD"],
                          capture_output=True, text=True).stdout.split()


# ————— Stellen —————

def test_rechnung_stellen_gibt_die_nummer_vom_server(welt):
    client, bare, _ = welt
    r = _stellen(client)
    assert r.status_code == 200
    d = r.json()
    assert d["nummer"] == "2026-0001"
    assert d["rechnung"]["brutto"] == 535.5
    assert d["rechnung"]["gestellt_von"] == "christoph0711.io"
    assert "rechnungen/2026-08/2026-0001.json" in _im_stand(bare)


def test_nummern_laufen_lueckenlos_durch(welt):
    client, _, _ = welt
    nummern = [_stellen(client).json()["nummer"] for _ in range(3)]
    assert nummern == ["2026-0001", "2026-0002", "2026-0003"]


def test_gleichzeitige_anfragen_bekommen_verschiedene_nummern(welt):
    """Zwei Rechnungen im selben Moment dürfen nie dieselbe Nummer tragen."""
    client, _, _ = welt
    ergebnisse: list[str] = []
    sperre = threading.Lock()

    def stellen():
        r = _stellen(client)
        if r.status_code == 200:
            with sperre:
                ergebnisse.append(r.json()["nummer"])

    threads = [threading.Thread(target=stellen) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ergebnisse) == 4
    assert len(set(ergebnisse)) == 4, f"doppelte Nummer: {ergebnisse}"


def test_stammdaten_landen_im_kopf(welt):
    client, _, _ = welt
    d = _stellen(client).json()["rechnung"]
    assert d["aussteller"]["betrieb_name"] == "Salon Nina"
    assert d["aussteller"]["steuernummer"] == "99012/34567"


def test_ohne_steuernummer_keine_rechnung(welt):
    client, _, bw = welt
    bw.db_einstellung_setzen("christoph0711.io", "steuernummer", "")
    r = _stellen(client)
    assert r.status_code == 400
    assert "Steuernummer" in r.json()["fehler"]


def test_ohne_position_keine_rechnung(welt):
    client, _, _ = welt
    assert _stellen(client, positionen=[]).status_code == 400


def test_mitarbeiterin_stellt_keine_rechnungen(welt):
    client, _, bw = welt
    d = client.post("/api/team", json={"name": "Jana", "email": "jana@salon.de",
                                       "betrag": "2400", "darf_belege": True}).json()
    jana = next(p for p in d["team"] if p["name"] == "Jana")
    start = client.post("/api/team-zugang", json={"id": jana["id"]}).json()["startpasswort"]
    from fastapi.testclient import TestClient
    jana_client = TestClient(bw.app, base_url="https://testserver")
    bw._LOGIN_VERSUCHE.clear()
    jana_client.post("/api/login", json={"email": "jana@salon.de", "passwort": start})
    r = jana_client.post("/api/rechnungen", json={"empfaenger": EMPF,
                                                  "positionen": [pos()]})
    assert r.status_code == 403


# ————— PDF, bezahlt, Storno —————

def test_pdf_nachreichen(welt):
    client, bare, _ = welt
    nummer = _stellen(client).json()["nummer"]
    r = client.post(f"/api/rechnung/{nummer}/pdf", content=b"%PDF-1.4 test")
    assert r.status_code == 200
    assert f"rechnungen/2026-08/{nummer}.pdf" in _im_stand(bare)
    assert client.post(f"/api/rechnung/{nummer}/pdf",
                       content=b"kein pdf").status_code == 400


def test_bezahlt_setzen_macht_sie_zum_umsatz(welt):
    client, _, _ = welt
    nummer = _stellen(client).json()["nummer"]
    liste = client.get("/api/rechnungen").json()
    assert liste["offen_anzahl"] == 1 and liste["offen_summe"] == 535.5

    r = client.post(f"/api/rechnung/{nummer}/bezahlt", json={"am": "2026-08-25"})
    assert r.status_code == 200
    liste = client.get("/api/rechnungen").json()
    assert liste["offen_anzahl"] == 0
    assert liste["rechnungen"][0]["stand"] == "bezahlt"


def test_storno_statt_loeschen(welt):
    client, bare, _ = welt
    nummer = _stellen(client).json()["nummer"]
    r = client.post(f"/api/rechnung/{nummer}/storno")
    assert r.status_code == 200
    gegen = r.json()["nummer"]
    assert gegen == "2026-0002"
    assert r.json()["rechnung"]["brutto"] == -535.5
    # Das Original bleibt liegen und ist als storniert markiert.
    assert f"rechnungen/2026-08/{nummer}.json" in _im_stand(bare)
    liste = {z["nummer"]: z for z in client.get("/api/rechnungen").json()["rechnungen"]}
    assert liste[nummer]["stand"] == "storniert"
    assert client.post(f"/api/rechnung/{nummer}/storno").status_code == 409


def test_rechnungen_sind_nicht_loeschbar(welt):
    """Aufbewahrungspflichtig — eine falsche Rechnung wird storniert."""
    client, _, _ = welt
    nummer = _stellen(client).json()["nummer"]
    client.post(f"/api/rechnung/{nummer}/pdf", content=b"%PDF-1.4 test")
    r = client.post("/api/dokument-loeschen",
                    json={"pfad": f"rechnungen/2026-08/{nummer}.pdf"})
    assert r.status_code == 400


def test_rechnung_steht_in_der_ablage(welt):
    client, _, _ = welt
    nummer = _stellen(client).json()["nummer"]
    client.post(f"/api/rechnung/{nummer}/pdf", content=b"%PDF-1.4 test")
    jahre = client.get("/api/ablage").json()["jahre"]
    stuecke = {s["pfad"]: s for j in jahre for a in j["arten"] for s in a["stuecke"]}
    pfad = f"rechnungen/2026-08/{nummer}.pdf"
    assert pfad in stuecke
    assert stuecke[pfad]["loeschbar"] is False
    assert client.get("/api/dokument/" + pfad).status_code == 200


# ————— Bis in die Auswertung —————

def test_erst_bezahlt_zaehlt_sie_im_monatsabschluss(welt):
    client, _, _ = welt
    nummer = _stellen(client).json()["nummer"]
    vorher = client.get("/api/monatsabschluss/2026-08").json()
    assert vorher["erloese"]["aus_rechnungen"] == 0.0

    client.post(f"/api/rechnung/{nummer}/bezahlt", json={"am": "2026-08-25"})
    nachher = client.get("/api/monatsabschluss/2026-08").json()
    assert nachher["erloese"]["aus_rechnungen"] == 535.5
    assert nachher["ustva"]["zahllast"] == 85.5


def test_soll_versteuerung_zaehlt_sofort(welt):
    client, _, bw = welt
    bw.db_einstellung_setzen("christoph0711.io", "versteuerung", "soll")
    _stellen(client)
    d = client.get("/api/monatsabschluss/2026-08").json()
    assert d["erloese"]["aus_rechnungen"] == 535.5


# ————— Vertragskiste —————

def test_vertragskiste_zeigt_dauerkosten(welt):
    client, bare, bw = welt
    import boxschreiber
    boxschreiber.schreiben(
        {"dokumente/2026-08/miete.pdf": b"%PDF",
         "dokumente/2026-08/miete.pdf.meta.json":
             json.dumps({"titel": "Miete", "art": "vertrag"}).encode(),
         "dokumente/2026-08/miete.pdf.vertrag.json":
             json.dumps({"art": "miete", "art_name": "Mietvertrag",
                         "partner": "Sonnenberg", "betrag_monat": 1250.0,
                         "laufzeit_bis": "2026-12-31",
                         "kuendigungsfrist": "3 Monate zum Quartalsende"}).encode()},
        None, "vertrag: miete", "christoph0711.io")
    bw._INDEX["geprueft"] = 0.0

    d = client.get("/api/vertraege").json()
    assert d["monatlich"] == 1250.0
    assert d["jaehrlich"] == 15000.0
    assert d["vertraege"][0]["partner"] == "Sonnenberg"
    assert d["vertraege"][0]["kuendigen_bis"]["datum"] == "2026-09-30"
