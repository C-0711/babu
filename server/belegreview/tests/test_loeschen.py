"""Löschen: was falsch ist, muss weggehen — was bleiben muss, bleibt.

Gelöscht wird mit einem eigenen Commit. Der aktuelle Stand zeigt den Beleg
danach nicht mehr, die Historie behält ihn. Was aufbewahrungspflichtig ist
(Kassenbuch, Kontoauszüge, Stapel) lässt sich gar nicht erst löschen.
"""
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
GOLDEN = HIER / "golden" / "review_weingaertle.json"
STAMM = "20260812-225200-c781d6-beleg_2026-07-21_weingaerty_22bf8b36"
DOKUMENT = "dokumente/2026-08/mietvertrag.pdf"


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
    # Beleg mit vollem Gefolge: Lesung, Angaben, Bewirtung, Korrektur.
    (arbeit / "review" / f"{STAMM}.json").write_text(
        json.dumps(gespeichert, ensure_ascii=False))
    (arbeit / "review" / f"{STAMM}.md").write_text("# BelegReview\n")
    (arbeit / "review" / f"{STAMM}.embedding.json").write_text('{"dim":3}')
    (arbeit / "review" / f"{STAMM}.angaben.json").write_text('{"brutto":142.6}')
    (arbeit / "review" / f"{STAMM}.bewirtung.json").write_text('{"anlass":"Team"}')
    (arbeit / "review" / f"{STAMM}.korrektur.json").write_text('{"konto_skr04":"6640"}')

    # Dokument mit Sidecars
    (arbeit / "dokumente" / "2026-08").mkdir(parents=True)
    (arbeit / DOKUMENT).write_bytes(b"%PDF-1.4 vertrag")
    (arbeit / (DOKUMENT + ".meta.json")).write_text(
        json.dumps({"titel": "Mietvertrag", "art": "vertrag"}))
    (arbeit / (DOKUMENT + ".vertrag.json")).write_text(
        json.dumps({"art": "miete", "betrag_monat": 1250.0}))

    # Aufbewahrungspflichtiges
    (arbeit / "kassenbuch" / "2026-08").mkdir(parents=True)
    (arbeit / "kassenbuch" / "2026-08" / "2026-08-17.json").write_text(
        json.dumps({"datum": "2026-08-17", "einnahmenBar": 412.5}))
    (arbeit / "auszuege" / "2026-08").mkdir(parents=True)
    (arbeit / "auszuege" / "2026-08" / "auszug.pdf").write_bytes(b"%PDF auszug")
    (arbeit / "export" / "2026-08").mkdir(parents=True)
    (arbeit / "export" / "2026-08" / "EXTF_20260821.csv").write_bytes(b"EXTF;700")

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
    babu_web._LOGIN_VERSUCHE.clear()
    babu_web._REG_ZULETZT.clear()

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    return client, bare, babu_web


def _im_stand(bare: Path) -> list[str]:
    return subprocess.run(["git", "-C", str(bare), "ls-tree", "-r", "--name-only", "HEAD"],
                          capture_output=True, text=True).stdout.split()


# ————— Belege —————

def test_beleg_loeschen_nimmt_die_beiakten_mit(welt):
    client, bare, _ = welt
    assert any(z["stamm"] == STAMM for z in client.get("/api/belege").json()["belege"])

    r = client.post(f"/api/beleg/{STAMM}/loeschen", json={"grund": "doppelt fotografiert"})
    assert r.status_code == 200 and r.json()["ok"] is True

    stand = _im_stand(bare)
    assert f"docs/2026-08/{STAMM}.jpg" not in stand
    for anhang in (".json", ".md", ".embedding.json", ".angaben.json",
                   ".bewirtung.json", ".korrektur.json"):
        assert f"review/{STAMM}{anhang}" not in stand, f"{anhang} blieb liegen"

    assert not any(z["stamm"] == STAMM for z in client.get("/api/belege").json()["belege"])
    assert client.get(f"/api/beleg/{STAMM}").status_code == 404


def test_geloeschtes_bleibt_in_der_historie(welt):
    """Nichts verschwindet spurlos — der Commit trägt den Namen der Nutzerin."""
    client, bare, _ = welt
    client.post(f"/api/beleg/{STAMM}/loeschen", json={})
    log = subprocess.run(["git", "-C", str(bare), "log", "-1", "--format=%s|%an"],
                         capture_output=True, text=True).stdout.strip()
    assert log == f"geloescht: {STAMM}|christoph0711.io"
    # Der Beleg ist im vorherigen Stand noch vorhanden.
    frueher = subprocess.run(
        ["git", "-C", str(bare), "cat-file", "-e", f"HEAD~1:docs/2026-08/{STAMM}.jpg"],
        capture_output=True)
    assert frueher.returncode == 0


def test_zweimal_loeschen_ist_harmlos(welt):
    client, _, _ = welt
    assert client.post(f"/api/beleg/{STAMM}/loeschen", json={}).status_code == 200
    assert client.post(f"/api/beleg/{STAMM}/loeschen", json={}).status_code == 404


def test_exportierter_beleg_bleibt(welt):
    """Was im Stapel bei der Kanzlei liegt, holt man nicht mehr zurück."""
    client, bare, _ = welt
    client.post(f"/api/bewirtung/{STAMM}",
                json={"anlass": "Team-Essen", "teilnehmer": ["Nicole"]})
    assert client.get("/api/export/2026-08.csv",
                      params={"festschreiben": 1}).status_code == 200
    assert client.get(f"/api/beleg/{STAMM}").json()["status"] == "exportiert"

    r = client.post(f"/api/beleg/{STAMM}/loeschen", json={})
    assert r.status_code == 409
    assert "Kanzlei" in r.json()["fehler"]
    assert f"docs/2026-08/{STAMM}.jpg" in _im_stand(bare)


def test_mitarbeiterin_darf_nicht_loeschen(welt):
    """Einreichen ja, wegwerfen nein."""
    client, bare, bw = welt
    d = client.post("/api/team", json={"name": "Jana", "email": "jana@salon.de",
                                       "betrag": "2400", "darf_belege": True}).json()
    jana = next(p for p in d["team"] if p["name"] == "Jana")
    start = client.post("/api/team-zugang", json={"id": jana["id"]}).json()["startpasswort"]

    from fastapi.testclient import TestClient
    jana_client = TestClient(bw.app, base_url="https://testserver")
    bw._LOGIN_VERSUCHE.clear()
    assert jana_client.post("/api/login", json={"email": "jana@salon.de",
                                                "passwort": start}).status_code == 200
    r = jana_client.post(f"/api/beleg/{STAMM}/loeschen", json={})
    assert r.status_code == 403
    assert "Inhaberin" in r.json()["fehler"]
    assert f"docs/2026-08/{STAMM}.jpg" in _im_stand(bare)


def test_fremdes_konto_loescht_nichts(welt):
    client, bare, bw = welt
    from fastapi.testclient import TestClient
    fremd = TestClient(bw.app, base_url="https://testserver")
    bw._REG_ZULETZT.clear()
    assert fremd.post("/api/signup", json={"salon": "Fremd", "email": "fremd@x.de",
                                           "passwort": "passwort-lang"}).status_code == 200
    assert fremd.post(f"/api/beleg/{STAMM}/loeschen", json={}).status_code == 403
    assert f"docs/2026-08/{STAMM}.jpg" in _im_stand(bare)


# ————— Dokumente —————

def test_dokument_loeschen_nimmt_sidecars_mit(welt):
    client, bare, _ = welt
    assert any(d["pfad"] == DOKUMENT for d in client.get("/api/dokumente").json()["dokumente"])

    r = client.post("/api/dokument-loeschen", json={"pfad": DOKUMENT})
    assert r.status_code == 200

    stand = _im_stand(bare)
    assert DOKUMENT not in stand
    assert DOKUMENT + ".meta.json" not in stand
    assert DOKUMENT + ".vertrag.json" not in stand
    assert not any(d["pfad"] == DOKUMENT
                   for d in client.get("/api/dokumente").json()["dokumente"])


@pytest.mark.parametrize("pfad", [
    "kassenbuch/2026-08/2026-08-17.json",
    "auszuege/2026-08/auszug.pdf",          # Auszüge gehen über ihre eigene Route
    "export/2026-08/EXTF_20260821.csv",
    "abschluss/2025/kennzahlen.json",
    "docs/2026-08/" + STAMM + ".jpg",       # Belege gehen über die Beleg-Route
    "../ausserhalb.txt",
])
def test_aufbewahrungspflichtiges_laesst_sich_nicht_loeschen(welt, pfad):
    client, bare, _ = welt
    vorher = _im_stand(bare)
    r = client.post("/api/dokument-loeschen", json={"pfad": pfad})
    assert r.status_code == 400
    assert _im_stand(bare) == vorher


# ————— Kontoauszüge: eigener Löschweg (Ninas Wunsch vom 26.08.) —————

def test_kontoauszug_loeschen_nimmt_die_beiakte_mit(welt):
    client, bare, _ = welt
    r = client.post("/api/auszug-loeschen",
                    json={"pfad": "auszuege/2026-08/auszug.pdf"})
    assert r.status_code == 200, r.text
    dateien = _im_stand(bare)
    assert "auszuege/2026-08/auszug.pdf" not in dateien
    assert "auszuege/2026-08/auszug.pdf.umsaetze.json" not in dateien


def test_kontoauszug_loeschen_nur_fuer_die_inhaberin(welt):
    client, bare, bw = welt
    import babu_web
    echte = babu_web.rolle
    bw.rolle = lambda un: "mitarbeit"
    try:
        r = client.post("/api/auszug-loeschen",
                        json={"pfad": "auszuege/2026-08/auszug.pdf"})
    finally:
        bw.rolle = echte
    assert r.status_code == 403
    assert "auszuege/2026-08/auszug.pdf" in _im_stand(bare)


@pytest.mark.parametrize("pfad", ["dokumente/2026-08/brief.pdf",
                                  "kassenbuch/2026-08/2026-08-17.json",
                                  "../ausserhalb.txt", ""])
def test_auszug_route_nimmt_nur_auszuege(welt, pfad):
    client, bare, _ = welt
    vorher = _im_stand(bare)
    r = client.post("/api/auszug-loeschen", json={"pfad": pfad})
    assert r.status_code in (400, 404)
    assert _im_stand(bare) == vorher


def test_die_ablage_zeigt_was_geloescht_werden_darf(welt):
    """Ein Knopf, der beim Drücken „geht nicht" sagt, ist eine Falle —
    deshalb sagt der Server je Zeile, ob sie gelöscht werden darf."""
    client, _, _ = welt
    jahre = client.get("/api/ablage").json()["jahre"]
    stuecke = {s["pfad"]: s for j in jahre for a in j["arten"] for s in a["stuecke"]}
    assert stuecke[DOKUMENT]["loeschbar"] is True
    assert stuecke["kassenbuch/2026-08/2026-08-17.json"]["loeschbar"] is False
    # Seit 27.08.2026: Auszüge dürfen weg (falsch/doppelt) — Historie bleibt.
    assert stuecke["auszuege/2026-08/auszug.pdf"]["loeschbar"] is True
    assert stuecke["export/2026-08/EXTF_20260821.csv"]["loeschbar"] is False


def test_ablage_eintraege_lassen_sich_oeffnen(welt):
    """Was in der Ablage steht, muss sich auch ansehen lassen."""
    client, _, _ = welt
    jahre = client.get("/api/ablage").json()["jahre"]
    pfade = [s["pfad"] for j in jahre for a in j["arten"] for s in a["stuecke"]]
    assert "kassenbuch/2026-08/2026-08-17.json" in pfade
    for pfad in pfade:
        r = client.get("/api/dokument/" + pfad)
        assert r.status_code == 200, f"{pfad} lässt sich nicht öffnen ({r.status_code})"


# ————— Der Schreibpfad selbst —————

def test_loeschen_haelt_sich_an_dasselbe_schloss(welt):
    """Löschen und Schreiben teilen sich die Arbeitskopie."""
    import boxschreiber
    _, bare, _ = welt
    for i in range(3):                       # erst anlegen, dann gleichzeitig ran
        boxschreiber.schreiben(f"docs/2026-08/alt{i}.txt", b"A",
                               f"aufnahme: alt{i}", "nina")
    fehler: list[Exception] = []

    def loesche(i: int) -> None:
        try:
            boxschreiber.loeschen([f"docs/2026-08/alt{i}.txt"],
                                  f"geloescht: alt{i}", "nina")
        except Exception as e:  # noqa: BLE001
            fehler.append(e)

    def schreibe(i: int) -> None:
        try:
            boxschreiber.schreiben(f"docs/2026-08/neu{i}.txt", b"x",
                                   f"aufnahme: neu{i}", "nina")
        except Exception as e:  # noqa: BLE001
            fehler.append(e)

    threads = ([threading.Thread(target=loesche, args=(i,)) for i in range(3)]
               + [threading.Thread(target=schreibe, args=(i,)) for i in range(3)])
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not fehler, f"gescheitert: {fehler}"
    stand = _im_stand(bare)
    for i in range(3):
        assert f"docs/2026-08/alt{i}.txt" not in stand
        assert f"docs/2026-08/neu{i}.txt" in stand


def test_loeschen_was_es_nicht_gibt(welt):
    import boxschreiber
    _, _, _ = welt
    with pytest.raises(boxschreiber.NichtsZuLoeschen):
        boxschreiber.loeschen(["docs/2026-08/gibtsnicht.txt"], "geloescht: nix", "nina")
