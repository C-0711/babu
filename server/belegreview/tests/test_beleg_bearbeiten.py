"""Am Schreibtisch aufräumen: einen Beleg im Browser ändern und abschließen.

Ninas Fall vom 22.08.2026: ein Parkbeleg über 4,20 €, bei dem etwas nicht
stimmt. In der App kann sie ihn ändern, im Portal fand sie keinen Weg.

Serverseitig fehlten drei Dinge. Die Kategorie — das „wofür", aus dem erst
das Konto wird. Ein Abschluss: wer alles beantwortet hat, dessen Beleg ist
fertig und nicht „wird noch gelesen". Und die Verrechnung selbst: die
offenen Punkte sind ganze Sätze („Der Rechnungsbetrag ist nicht sicher zu
lesen."), abgeglichen wurde aber gegen Feldnamen („brutto") — das konnte nie
zusammenpassen, also blieb die Frage stehen, obwohl sie beantwortet war.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
GOLDEN = HIER / "golden" / "review_weingaertle.json"
STAMM = "20260812-225200-c781d6-beleg_2026-07-21_apcoa_22bf8b36"
STAMM_B = "20260812-225300-c781d7-beleg_2026-07-21_bewirtung_22bf8b37"
BETRAG_OFFEN = "Der Rechnungsbetrag ist nicht sicher zu lesen."


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _review(**felder) -> str:
    golden = json.loads(GOLDEN.read_text())
    review = {k: v for k, v in golden.items() if k not in ("audit", "buchungssatz")}
    review["felder"] = dict(review["felder"], **felder)
    return json.dumps(review, ensure_ascii=False)


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    _git(arbeit, "config", "user.name", "t")
    _git(arbeit, "config", "user.email", "t@l")

    (arbeit / "docs" / "2026-08").mkdir(parents=True)
    (arbeit / "review").mkdir()
    for stamm, bewirtung in ((STAMM, False), (STAMM_B, True)):
        (arbeit / "docs" / "2026-08" / f"{stamm}.jpg").write_bytes(b"\xff\xd8x")
        (arbeit / "review" / f"{stamm}.json").write_text(_review(
            brutto=None, lieferant=None, offen=[BETRAG_OFFEN],
            bewirtungssignal=bewirtung, summenprobe_ok=True))

    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "aufnahme+review")
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

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    return client, bare, babu_web


def _beleg(client, stamm=STAMM) -> dict:
    return client.get(f"/api/beleg/{stamm}").json()


def _in_liste(client, stamm=STAMM) -> dict:
    return next(z for z in client.get("/api/belege").json()["belege"]
                if z["stamm"] == stamm)


# ————— Die Kategorien, aus denen die Nutzerin wählt —————

def test_die_kategorien_sind_abrufbar(welt):
    """Ohne Liste kein Auswahlfeld — und geraten wird nicht."""
    client, _, _ = welt
    d = client.get("/api/kategorien").json()
    codes = {k["code"] for k in d["kategorien"]}
    assert {"kfz", "bewirtung", "miete", "werbung"} <= codes
    kfz = next(k for k in d["kategorien"] if k["code"] == "kfz")
    assert kfz["name"] == "Kfz-Kosten"
    # Ninas Sprache: der Name trägt, die Kontonummer steht daneben.
    assert kfz["konto"] == "6530"


# ————— Ändern —————

def test_kategorie_setzen_macht_ein_konto_daraus(welt):
    client, _, _ = welt
    r = client.post(f"/api/angaben/{STAMM}", json={"kategorie": "kfz"})
    assert r.status_code == 200, r.text
    assert r.json()["angaben"]["kategorie"] == "kfz"

    d = _beleg(client)
    assert d["einschaetzung"]["kategorie"] == "kfz"
    # SKR04 ist der Rahmen dieses Betriebs — Kfz-Kosten sind dort 6530.
    assert d["einschaetzung"]["konto"] == "6530"
    assert d["einschaetzung"]["konto_skr04"] == "6530"
    assert _in_liste(client)["kategorie"] == "kfz"


def test_erfundene_kategorie_wird_abgewiesen(welt):
    """Lieber keine Kategorie als eine, die kein Konto kennt."""
    client, _, _ = welt
    r = client.post(f"/api/angaben/{STAMM}", json={"kategorie": "schoenes-wetter"})
    assert r.status_code == 400
    assert "Kategorie" in r.json()["fehler"]


def test_betrag_datum_und_laden_lassen_sich_am_schreibtisch_aendern(welt):
    client, _, _ = welt
    r = client.post(f"/api/angaben/{STAMM}",
                    json={"brutto": "4,20", "lieferant": "APCOA Parking",
                          "datum": "2026-07-21", "kategorie": "fahrt"})
    assert r.status_code == 200, r.text
    d = _beleg(client)
    assert d["felder"]["brutto"] == 4.20
    assert d["felder"]["lieferant"] == "APCOA Parking"
    assert d["felder"]["datum"] == "2026-07-21"
    assert d["einschaetzung"]["kategorie"] == "fahrt"


# ————— Abschließen —————

def test_wer_alles_beantwortet_hat_schliesst_den_beleg_ab(welt):
    """Vorher „nachfrage", danach fertig — nicht „wird noch gelesen"."""
    client, _, _ = welt
    assert _beleg(client)["status"] == "nachfrage"

    client.post(f"/api/angaben/{STAMM}", json={"brutto": "4,20"})
    d = _beleg(client)
    assert d["felder"]["offen"] == [], "die Frage nach dem Betrag ist beantwortet"
    assert d["status"] == "geprüft", "die Antwort schließt den Beleg ab"
    assert _in_liste(client)["status"] == "geprüft"


def test_eine_offene_bewirtungsfrage_bleibt_offen(welt):
    """Der Betrag ist nachgetragen — die Frage nach den Gästen bleibt trotzdem.

    § 4 Abs. 5 EStG verlangt Anlass und Teilnehmer; ein Betrag beantwortet
    das nicht. Wer hier durchwinkt, exportiert einen unvollständigen Beleg.
    """
    client, _, _ = welt
    client.post(f"/api/angaben/{STAMM_B}", json={"brutto": "4,20"})
    assert _beleg(client, STAMM_B)["status"] == "nachfrage"


def test_der_pauschale_gegenprobe_satz_verschwindet_mit_jeder_angabe(welt):
    """Alt-Reviews tragen „Die Gegenprobe weicht ab — kurz prüfen." ohne
    Feldbezug. Der Satz war mit keiner Angabe zu beantworten — Nina hat am
    26.08.2026 sechsmal gespeichert und die Frage blieb stehen. Wer etwas
    nachträgt, hat geprüft: der Satz ist damit erledigt."""
    client, bw, _ = welt
    import boxschreiber
    boxschreiber.schreiben(
        {f"review/{STAMM}.json": _review(
            brutto=None, lieferant=None,
            offen=["Die Gegenprobe weicht ab — kurz prüfen."],
            bewirtungssignal=False, summenprobe_ok=True).encode()},
        None, "review mit pauschalsatz", "t@l")
    client.post(f"/api/angaben/{STAMM}", json={"brutto": "4,20"})
    d = _beleg(client)
    assert d["felder"]["offen"] == []
    assert d["status"] == "geprüft"


def test_speichern_beantwortet_alle_lesefragen(welt):
    """Seit 27.08.2026: Das Formular steht da, um die offenen Fragen zu
    klären — wer etwas nachträgt und speichert, hat ALLE angesehen. Vorher
    beantwortete eine Angabe nur die per Stichwort passende Frage, und jede
    frei formulierte („Der Steuersatz ist nicht sicher zu lesen.") blieb
    für immer stehen, egal wie oft Nina speicherte."""
    client, bw, _ = welt
    import boxschreiber
    offen = ["Lieferant: die Gegenprobe liest „delilà Hair Extensions“, "
             "gelesen wurde „service@delila.de“ — bitte kurz prüfen.",
             "Der Steuersatz ist nicht sicher zu lesen."]
    boxschreiber.schreiben(
        {f"review/{STAMM}.json": _review(
            brutto=None, lieferant=None, offen=offen,
            bewirtungssignal=False, summenprobe_ok=True).encode()},
        None, "review mit widerspruechen", "t@l")
    client.post(f"/api/angaben/{STAMM}", json={"lieferant": "delilà GmbH"})
    d = _beleg(client)
    assert d["felder"]["offen"] == []
    assert d["status"] == "geprüft"


# ————— Das Portal muss die Wege auch anbieten —————

PORTAL = (HIER.parent / "portal.html").read_text()


def test_das_portal_bietet_das_aendern_immer_an():
    """Nina sah den Beleg, aber keinen Knopf — das war der ganze Vorgang."""
    assert "function aenderungsFormular(" in PORTAL, "kein Änderungsformular im Portal"
    assert "Beleg ändern" in PORTAL


def test_das_portal_kennt_die_kategorien_route():
    assert "/api/kategorien" in PORTAL
