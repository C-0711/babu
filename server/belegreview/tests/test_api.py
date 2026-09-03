"""Portal-API-Tests gegen einen Fixture-Bare-Store (aus dem Golden-Review gebaut).

Läuft lokal ohne Server: BABU_STORE zeigt auf ein frisch gebautes Bare-Repo,
wer_token ist gemockt (kein gitchain.de-Kontakt). Die iOS-Verträge (/review,
/chat-Fehlerbilder) werden gegen die Golden-Fixtures geprüft.

    scratch-venv/bin/python -m pytest server/belegreview/tests/test_api.py -q
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
GOLDEN = HIER / "golden" / "review_weingaertle.json"
STAMM = "20260812-225200-c781d6-beleg_2026-07-21_weingaerty_22bf8b36"
LOKALER_NAME = "beleg_2026-07-21_weingaerty_22bf8b36"   # was die App kennt


def _git(repo: Path, *args: str, env=None) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, env=env)


@pytest.fixture(scope="session")
def store(tmp_path_factory) -> Path:
    """Arbeitsrepo mit aufnahme:- und review:-Commits → Bare-Clone wie im Betrieb."""
    arbeit = tmp_path_factory.mktemp("box")
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    _git(arbeit, "config", "user.name", "test")
    _git(arbeit, "config", "user.email", "test@local")

    golden = json.loads(GOLDEN.read_text())
    # audit/buchungssatz sind HTTP-Anreicherung — liegen NICHT im Store.
    gespeichert = {k: v for k, v in golden.items() if k not in ("audit", "buchungssatz")}

    (arbeit / "docs" / "2026-08").mkdir(parents=True)
    (arbeit / "docs" / "2026-08" / f"{STAMM}.jpg").write_bytes(b"\xff\xd8\xff\xe0testjpeg")
    (arbeit / "docs" / "2026-08" / "20260812-211943-99b8fb-beleg-test.pdf").write_bytes(b"%PDF-1.4 test")
    # Stub-Review wie vom Watcher bei unlesbaren Fotos: semantik/vlm sind null —
    # der Index darf daran nicht sterben (Regression 13.08.).
    (arbeit / "docs" / "2026-08" / "20260813-000000-abcdef-kaputt.jpg").write_bytes(b"\xff\xd8kaputt")
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", f"aufnahme: {STAMM}.jpg",
         "--author", "christoph0711.io <aufnahme@gitchain.local>")

    (arbeit / "review").mkdir()
    (arbeit / "review" / f"{STAMM}.json").write_text(
        json.dumps(gespeichert, ensure_ascii=False, indent=1))
    (arbeit / "review" / f"{STAMM}.md").write_text("# BelegReview\n")
    (arbeit / "review" / f"{STAMM}.embedding.json").write_text(
        json.dumps({"modell": "embeddinggemma", "dim": 3, "vektor": [0.1, 0.2, 0.3]}))
    (arbeit / "review" / "20260813-000000-abcdef-kaputt.json").write_text(json.dumps({
        "datei": "docs/2026-08/20260813-000000-abcdef-kaputt.jpg",
        "engine": "BelegReview-Stub", "dokumentklasse": "unlesbar",
        "semantik": None, "vlm": None, "aehnlich": None,
        "felder": {"lieferant": None, "beleg_nr": None, "datum": None,
                   "netto": None, "ust": None, "brutto": None, "ust_satz": 19,
                   "summenprobe_ok": False, "bewirtungssignal": False,
                   "offen": ["Das Foto war schwer zu lesen."]},
        "einschaetzung": {"belegart": "unlesbar", "konto_skr04": None,
                          "steuerschluessel": "9", "hinweise": []},
        "ocr_text": ""}, ensure_ascii=False))
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", f"review: {STAMM}.jpg",
         "--author", "belegreview <review@gitchain.local>")

    # Issue #67: Beleg mit Status „erfasst" (kein review.json), aber mit
    # nachgetragenen Angaben (.angaben.json) — sollte die Daten zeigen.
    (arbeit / "docs" / "2026-02").mkdir(parents=True)
    (arbeit / "docs" / "2026-02" / "20260824-092514-1142bc-beleg_2026-02-23_delil_b1fc4bf5.jpg").write_bytes(b"\xff\xd8\xff\xe0delil")
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "aufnahme: delil beleg",
         "--author", "christoph0711.io <aufnahme@gitchain.local>")
    # Nutzerin trägt Angaben nach — kein review.json, nur .angaben.json
    (arbeit / "review" / "20260824-092514-1142bc-beleg_2026-02-23_delil_b1fc4bf5.angaben.json").write_text(json.dumps({
        "von": "nina@0711.io",
        "am": "2026-08-26T18:25:46Z",
        "beantwortet": ["brutto", "lieferant", "datum"],
        "brutto": 667.32,
        "lieferant": "delilà GmbH",
        "datum": "2026-02-23",
        "kategorie": "verbrauchsmaterial"
    }, ensure_ascii=False))
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "angaben: delil beleg",
         "--author", "nina@0711.io <nina@0711.io>")

    bare = tmp_path_factory.mktemp("store") / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)
    return bare


@pytest.fixture(scope="session")
def client(store, tmp_path_factory):
    os.environ["BABU_STORE"] = str(store)
    os.environ["BABU_SEITE"] = str(GOLDEN)  # irgendeine existierende Datei
    os.environ["BABU_SESSION_GEHEIMNIS"] = str(tmp_path_factory.mktemp("s") / ".geheimnis")
    os.environ["BABU_INDEX_TTL"] = "0"      # Tests: immer frisch prüfen
    sys.path.insert(0, str(HIER.parent))
    import babu_web  # noqa: PLC0415

    # Die Umgebungsvariablen oben wirken nur, wenn babu_web hier zum ersten
    # Mal importiert wird — importiert eine andere Testdatei es früher, zeigt
    # STORE noch woanders hin. Deshalb nochmal ausdrücklich setzen: die Tests
    # dürfen nicht davon abhängen, in welcher Reihenfolge pytest sammelt.
    babu_web.STORE = store
    babu_web.INDEX_TTL = 0.0
    babu_web.GEHEIMNIS_PFAD = Path(os.environ["BABU_SESSION_GEHEIMNIS"])
    babu_web.PORTAL_DB = tmp_path_factory.mktemp("db") / "portal.db"
    babu_web._INDEX.update(head=None, geprueft=0.0)

    babu_web.wer_token = lambda token: {"test-pat": "christoph0711.io",
                                        "fremd-pat": "fremder.example"}.get(token)
    from fastapi.testclient import TestClient  # noqa: PLC0415
    return TestClient(babu_web.app, base_url="https://testserver")


def _anmelden(client):
    r = client.post("/api/anmelden", json={"pat": "test-pat"})
    assert r.status_code == 200 and r.json() == {"un": "christoph0711.io"}
    assert "babu_sitzung" in client.cookies


def test_anmelden_falscher_pat(client):
    assert client.post("/api/anmelden", json={"pat": "quatsch"}).status_code == 401


def test_anmelden_fremder_nutzer(client):
    assert client.post("/api/anmelden", json={"pat": "fremd-pat"}).status_code == 403


def test_api_ohne_anmeldung(client):
    assert client.get("/api/belege").status_code == 401
    assert client.get("/api/ich").status_code == 401


def test_ich_mit_cookie(client):
    _anmelden(client)
    r = client.get("/api/ich")
    assert r.status_code == 200 and r.json()["un"] == "christoph0711.io"


def test_belege_liste_und_etag(client):
    _anmelden(client)
    r = client.get("/api/belege")
    assert r.status_code == 200
    d = r.json()
    assert d["gesamt"] == 4                      # JPG (Review) + PDF (erfasst) + Stub + delil
    assert set(d["monate"]) == {"2026-08", "2026-02"}
    stati = {z["stamm"]: z["status"] for z in d["belege"]}
    assert stati[STAMM] == "nachfrage"           # offen: Trinkgeld-Differenz
    assert stati["20260812-211943-99b8fb-beleg-test"] == "erfasst"
    # Der Stub trägt `dokumentklasse: "unlesbar"` — seit Teilscheibe I1 ist
    # das der Status, und zwar unabhängig davon, was in `offen` steht. Ein
    # Beleg, aus dem nichts zu lesen war, ist keine Frage, die sich
    # beantworten ließe. Beide Stände zählen im Portal, in `_box_befund`
    # und in der Kanzlei-Monatsspalte als „offen" — es verschiebt sich das
    # Wort, nicht die Zahl.
    assert stati["20260813-000000-abcdef-kaputt"] == "unlesbar"
    weingaertle = next(z for z in d["belege"] if z["stamm"] == STAMM)
    assert weingaertle["lieferant"] == "Rotenberger Weingärtle"
    assert weingaertle["brutto"] == 142.6
    assert weingaertle["konto_skr04"] == "6640"
    assert "_review" not in weingaertle
    etag = r.headers["etag"]
    assert client.get("/api/belege",
                      headers={"If-None-Match": etag}).status_code == 304


def test_belege_filter(client):
    _anmelden(client)
    r = client.get("/api/belege", params={"status": "nachfrage"})
    assert {z["stamm"] for z in r.json()["belege"]} == {STAMM}
    # Der Stub steht seit I1 unter „unlesbar" (siehe oben) und ist damit
    # weiter auffindbar — nur unter dem Wort, das auf ihn passt.
    r = client.get("/api/belege", params={"status": "unlesbar"})
    assert {z["stamm"] for z in r.json()["belege"]} == {"20260813-000000-abcdef-kaputt"}
    r = client.get("/api/belege", params={"monat": "2026-07"})
    assert r.json()["gesamt"] == 0


def test_beleg_detail_superset_von_review(client):
    _anmelden(client)
    review = client.get(f"/review/{STAMM}",
                        headers={"Authorization": "Bearer test-pat"}).json()
    detail = client.get(f"/api/beleg/{STAMM}").json()
    for k in review:
        assert k in detail, f"Detail verliert Schlüssel {k}"
    assert detail["status"] == "nachfrage"
    assert detail["stamm"] == STAMM
    assert detail["monat"] == "2026-08"
    assert detail["bild_url"].startswith(f"/api/beleg/{STAMM}/bild?v=")
    # Buchungssatz identisch mit dem Golden-Fixture (iOS-Vertrag)
    golden = json.loads(GOLDEN.read_text())
    assert detail["buchungssatz"] == golden["buchungssatz"]
    assert review["buchungssatz"] == golden["buchungssatz"]


def test_beleg_detail_suffix_match(client):
    _anmelden(client)
    r = client.get(f"/api/beleg/{LOKALER_NAME}")
    assert r.status_code == 200 and r.json()["stamm"] == STAMM


def test_beleg_bild(client):
    _anmelden(client)
    r = client.get(f"/api/beleg/{STAMM}/bild")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/jpeg")
    assert "immutable" in r.headers["cache-control"]
    assert r.content.startswith(b"\xff\xd8")


def test_monat_aggregation(client):
    _anmelden(client)
    d = client.get("/api/monat/2026-08").json()
    assert d["anzahl"] == 3
    assert d["brutto"] == 142.6
    # P0-1: die Kategorie kommt jetzt aus konto_skr04 (6640 -> dieselbe
    # Kostengruppe wie im Monatsabschluss), nicht mehr aus dem semantischen
    # "Bewirtung (semantisch, 30%)"-Label — das war die Ursache dafür, dass
    # derselbe Beleg in Ausgaben und Monatsabschluss zwei Kategorien zeigte.
    assert d["belegarten"][0]["belegart"] == "Werbung, Bewirtung und Reisen"
    assert d["belegarten"][0]["lieferanten"] == ["Rotenberger Weingärtle"]
    assert d["konten"][0] == {"konto": "6640", "brutto": 142.6, "anzahl": 1}
    assert len(d["offene"]) == 3                 # nachfrage + erfasstes PDF + Stub
    assert d["groesste_position"]["lieferant"] == "Rotenberger Weingärtle"
    assert d["vormonat"]["anzahl"] == 0


def test_review_vertrag_unveraendert(client):
    """iOS-Vertrag: Felder des Golden-Fixtures byte-gleich (bis auf Audit-Hashes)."""
    golden = json.loads(GOLDEN.read_text())
    live = client.get(f"/review/{STAMM}",
                      headers={"Authorization": "Bearer test-pat"}).json()
    for k in golden:
        if k == "audit":
            assert set(live[k]) == {"aufnahme", "review"}
            assert live[k]["aufnahme"]["autor"] == "christoph0711.io"
        else:
            assert live[k] == golden[k], f"Schlüssel {k} weicht ab"


def test_chat_ohne_reviews_ok_mit_cookie(client):
    _anmelden(client)
    r = client.post("/chat", json={"frage": ""})
    assert r.status_code == 400            # Cookie-Auth greift, Validierung meldet sich
    assert r.json() == {"fehler": "frage fehlt oder zu lang"}


def test_chat_route_ist_sync():
    """chat muss sync bleiben: requests/subprocess würden async den Event-Loop
    blockieren (workers=1) — GET /review liefe dann in Timeouts."""
    import inspect
    sys.path.insert(0, str(HIER.parent))
    import babu_web
    assert not inspect.iscoroutinefunction(babu_web.chat)


def test_origin_check(client):
    _anmelden(client)
    r = client.post("/chat", json={"frage": "x"},
                    headers={"Origin": "https://boese.example"})
    assert r.status_code == 401            # Cookie verworfen, kein Bearer da



def test_kein_async_handler_blockiert_den_event_loop():
    """Ein Git-Push dauert Sekunden. Läuft er direkt in einer async-Route,
    steht der ganze Server still — auch für alle anderen (workers=1).

    In async-Routen gehören diese Aufrufe deshalb in den Threadpool; dort
    stehen sie als Referenz (`run_in_threadpool(f, …)`), nicht als Aufruf.
    """
    import ast
    baum = ast.parse((HIER.parent / "babu_web.py").read_text())
    BLOCKIEREND = {"boxschreiber.schreiben", "index_aktuell", "ka.parse_pdf",
                   "requests.post", "requests.get", "subprocess.run"}

    def name_von(knoten):
        if isinstance(knoten, ast.Name):
            return knoten.id
        if isinstance(knoten, ast.Attribute) and isinstance(knoten.value, ast.Name):
            return f"{knoten.value.id}.{knoten.attr}"
        return None

    suender = []
    for f in ast.walk(baum):
        if not isinstance(f, ast.AsyncFunctionDef):
            continue
        for anweisung in f.body:                       # ohne decorator_list
            for k in ast.walk(anweisung):
                if isinstance(k, ast.Call) and name_von(k.func) in BLOCKIEREND:
                    suender.append(f"{f.name}: {name_von(k.func)}")
    assert not suender, ("blockierende Aufrufe direkt in async-Routen: "
                         + ", ".join(sorted(set(suender))))


def test_nichts_steht_hinter_dem_startaufruf():
    """Produktiv läuft `python babu_web.py` — dann blockiert `uvicorn.run`
    für immer, und alles darunter wird NIE ausgeführt.

    Am 22.08.2026 standen 137 Zeilen dahinter: die Gespräche-Routen gab es
    im Betrieb nicht (404), und /chat starb mit `NameError`. In den Tests
    fiel es nicht auf, weil die importieren — da läuft die ganze Datei.
    """
    quelle = (Path(__file__).resolve().parent.parent / "babu_web.py").read_text()
    zeilen = quelle.splitlines()
    start = next(i for i, z in enumerate(zeilen) if z.startswith('if __name__'))
    dahinter = [z for z in zeilen[start:]
                if z.startswith("@app.") or z.startswith("def ")
                or z.startswith("class ")]
    assert dahinter == [], (
        "Hinter dem Startaufruf definiert und damit im Betrieb tot: "
        + ", ".join(dahinter))


# ————— Der CSRF-Schutz —————
#
# Am 22.08.2026 ließ sich am Entwicklungsserver niemand anmelden: die
# Erlaubnisliste kannte nur Port 7844, der Entwicklungsserver läuft aber auf
# 8791. Jeder Cookie-POST kam als „nicht erlaubt" zurück.

def test_produktiv_bleibt_streng(monkeypatch):
    import babu_web as bw
    monkeypatch.setattr(bw, "PORTAL_ORIGIN", "https://babu.0711.io")

    class R:
        def __init__(self, o): self.headers = {"origin": o} if o else {}

    assert bw._origin_ok(R("https://babu.0711.io")) is True
    assert bw._origin_ok(R(None)) is True
    assert bw._origin_ok(R("https://boese.example")) is False
    assert bw._origin_ok(R("http://localhost:8791")) is False


def test_am_entwicklungsserver_gilt_beide_schleifennamen(monkeypatch):
    import babu_web as bw
    monkeypatch.setattr(bw, "PORTAL_ORIGIN", "http://127.0.0.1:8791")

    class R:
        def __init__(self, o): self.headers = {"origin": o}

    assert bw._origin_ok(R("http://127.0.0.1:8791")) is True
    assert bw._origin_ok(R("http://localhost:8791")) is True
    # Ein anderer Port bleibt draußen, auch auf der Schleife.
    assert bw._origin_ok(R("http://localhost:9999")) is False
    assert bw._origin_ok(R("https://boese.example")) is False


def test_beleg_mit_angaben_zeigt_daten_nicht_erfasst(client):
    """Issue #67: Beleg ohne review.json, aber mit .angaben.json sollte
    Status „geprüft" haben und die Daten im Frontend zeigen.

    Vorher: Status blieb „erfasst", Frontend zeigte „wird gelesen".
    Nachher: API rechnet Status neu, wenn Nutzerin alles beantwortet hat.
    """
    _anmelden(client)
    stamm = "20260824-092514-1142bc-beleg_2026-02-23_delil_b1fc4bf5"

    # Index sollte ergaenzt=true haben
    liste = client.get("/api/belege").json()
    eintrag = next(z for z in liste["belege"] if z["stamm"] == stamm)
    assert eintrag["ergaenzt"] is True
    assert eintrag["status"] == "geprüft"   # Neu: nicht mehr „erfasst"

    # Detail-API
    detail = client.get(f"/api/beleg/{stamm}").json()
    assert detail["status"] == "geprüft"    # ← der eigentliche Fix
    assert detail["audit"]["review"] is None  # kein review.json
    assert detail["ergaenzt"] is True
    assert detail["felder"]["lieferant"] == "delilà GmbH"
    assert detail["felder"]["brutto"] == 667.32
    assert detail["felder"]["datum"] == "2026-02-23"
    # Frontend prüft: if (status !== "erfasst") → zeigt Felder.
    # Ohne den Fix wäre status="erfasst", und alles bliebe versteckt.
