"""Ein Beleg ohne Ergebnis wird nachgelesen — statt still „unlesbar" zu werden.

Der Zielbild-Weg ist: die App liest mit Vision, holt sich Gemmas Buchung über
`/api/buchung/einschaetzung` und schickt sie mit dem Foto an `/api/aufnahme`.
Kommt dort KEIN Ergebnis an — der Nutzer bricht die Rückfragen ab, die
Einschätzung läuft in einen Fehler, oder die App ist älter als das Zielbild —
wurde das Foto bisher nur archiviert. Nach `BELEG_HAENGT_NACH_MIN` stempelte
der Index es als „unlesbar".

Gemessen am 08.09.2026 in Ninas Box: neun von 278 Belegen standen so da, für
keinen davon existierte je ein Review. Drei davon waren gestochen scharfe
Bons (EDEKA 14,88 €, eine Sixt-Aufstellung) — nicht unlesbar, sondern nie
gelesen.

Das Nachlesen ist KEINE zweite Lesung: die verbietet das Zielbild für Belege,
die schon eine haben. Hier gibt es keine. Es ist derselbe Weg, den der
Portal-Upload (`/api/hochladen`) seit jeher geht.
"""
import subprocess
import sys
from pathlib import Path

import pytest

BON = """Friseur Grosshandel Wagner GmbH
Rechnung Nr. 4711
Shampoo 5L                 45,00
Summe                     141,00
"""


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

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import babu_web
    import boxschreiber

    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(babu_web, "_vertrag_job", lambda *a, **k: None)
    monkeypatch.setattr(babu_web, "_brief_job", lambda *a, **k: None)
    monkeypatch.setattr(babu_web, "embedding_rechnen", lambda *a, **k: None)
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={}, rechnungen={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app)
    client.headers.update({"Authorization": "Bearer test-pat"})
    return client, bare, babu_web


def _nachgelesen(monkeypatch, babu_web) -> list:
    """Mitschreiben, für welche Pfade nachgelesen würde."""
    gesehen = []
    monkeypatch.setattr(babu_web, "_hintergrund_lesen_starten",
                        lambda pfad, daten, endung, un: gesehen.append(pfad))
    return gesehen


def test_ohne_ergebnis_liest_der_server_nach(welt, monkeypatch):
    client, _bare, babu_web = welt
    gesehen = _nachgelesen(monkeypatch, babu_web)
    r = client.post("/api/aufnahme", params={"name": "foto.jpg", "text": BON},
                    content=b"\xff\xd8\xff\xe0bild")
    assert r.status_code == 200 and r.json()["art"] == "beleg"
    assert len(gesehen) == 1 and gesehen[0].startswith("docs/")


def test_mit_ergebnis_bleibt_es_bei_der_einen_lesung(welt, monkeypatch):
    """Der Regelfall: die App hat gelesen und gebucht — der Server rührt das
    Bild nicht noch einmal an. Genau das ist das Zielbild."""
    import json
    client, _bare, babu_web = welt
    gesehen = _nachgelesen(monkeypatch, babu_web)
    ergebnis = {"buchung": {"dokumentklasse": "beleg", "konto": "5400",
                            "kategorie": "wareneinkauf", "betrag_eur": 141.0,
                            "datum": "2026-09-08", "lieferant": "Wagner GmbH",
                            "ust_satz": 19},
                "zeilen": BON.splitlines()}
    r = client.post("/api/aufnahme", params={"name": "foto.jpg"},
                    files={"file": ("foto.jpg", b"\xff\xd8\xff\xe0bild", "image/jpeg")},
                    data={"text": BON, "ergebnis": json.dumps(ergebnis)})
    assert r.status_code == 200
    assert gesehen == [], "Beleg mit Ergebnis darf nicht nachgelesen werden"


def test_ein_vertrag_wird_nicht_als_beleg_nachgelesen(welt, monkeypatch):
    """Verträge und Behördenpost haben ihren eigenen Leseweg (`_vertrag_job`,
    `_brief_job`) — der Beleg-Weg darf ihnen nicht dazwischenfunken."""
    client, _bare, babu_web = welt
    gesehen = _nachgelesen(monkeypatch, babu_web)
    vertrag = ("Mietvertrag\nzwischen Vermieter und Mieterin\n"
               "Monatliche Miete 905,00 EUR\nKuendigungsfrist drei Monate\n")
    r = client.post("/api/aufnahme", params={"name": "blatt.jpg", "text": vertrag},
                    content=b"\xff\xd8\xff\xe0bild")
    assert r.status_code == 200 and r.json()["art"] == "vertrag"
    assert gesehen == []


def _lesen_mit(monkeypatch, antwort):
    """Gemmas Antwort festlegen und den echten Nachlese-Weg fahren lassen."""
    import gemma_buchung
    monkeypatch.setattr(gemma_buchung, "runde", lambda *a, **k: antwort)


def test_eine_rueckfrage_wird_sichtbar_statt_unlesbar(welt, monkeypatch):
    """Der Bon von Merz & Benzing (Blumen 58,99 €) ist gestochen scharf, und
    Gemma stellt dazu genau die Frage, die die Regeln verlangen: Dekoration
    oder Geschenk? Bis zum 08.09.2026 schrieb der Nachlese-Weg dafür GAR
    kein Review — der Beleg lief in den Timeout und hieß „unlesbar"."""
    import asyncio
    client, _bare, babu_web = welt
    _lesen_mit(monkeypatch, {"status": "fragen", "fragen": [
        {"frage": "Bleiben die Blumen im Salon oder bekommt sie jemand?",
         "optionen": ["Sie stehen im Salon", "Geschenk an eine Kundin"]}]})
    r = client.post("/api/aufnahme", params={"name": "blumen.jpg", "text": BON},
                    content=b"\xff\xd8\xff\xe0bild")
    assert r.status_code == 200
    pfad = r.json()["datei"]
    asyncio.run(babu_web._beleg_serverseitig_lesen(
        pfad, b"\xff\xd8\xff\xe0bild", ".jpg", "christoph0711.io"))

    stamm = pfad.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    eintrag = babu_web.index_aktuell()["belege"][stamm]
    assert eintrag["status"] == "nachfrage", eintrag["status"]
    assert any("Blumen" in o for o in eintrag["offen"]), eintrag["offen"]


def test_aufgeben_schreibt_weiterhin_kein_review(welt, monkeypatch):
    """Gegenprobe zum Fix: geändert wird NUR der Frage-Fall. „Das gehört auf
    den Schreibtisch" und ein Format ohne Text bleiben ohne Review — sonst
    entstünde für jede hochgeladene XML ein sichtbarer Beleg."""
    import asyncio
    client, _bare, babu_web = welt
    _lesen_mit(monkeypatch, {"status": "aufgeben",
                             "hinweis": "Das ist eine Lohnabrechnung."})
    r = client.post("/api/aufnahme", params={"name": "lohn.jpg", "text": BON},
                    content=b"\xff\xd8\xff\xe0bild")
    pfad = r.json()["datei"]
    asyncio.run(babu_web._beleg_serverseitig_lesen(
        pfad, b"\xff\xd8\xff\xe0bild", ".jpg", "christoph0711.io"))

    stamm = pfad.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    assert stamm not in babu_web.index_aktuell()["reviews"]


def test_gebucht_bleibt_gebucht(welt, monkeypatch):
    import asyncio
    client, _bare, babu_web = welt
    _lesen_mit(monkeypatch, {"status": "gebucht", "buchung": {
        "dokumentklasse": "beleg", "konto": "5400", "kategorie": "wareneinkauf",
        "kategorie_name": "Wareneinkauf", "betrag_eur": 141.0,
        "datum": "2026-09-08", "lieferant": "Wagner GmbH", "ust_satz": 19}})
    r = client.post("/api/aufnahme", params={"name": "bon.jpg", "text": BON},
                    content=b"\xff\xd8\xff\xe0bild")
    pfad = r.json()["datei"]
    asyncio.run(babu_web._beleg_serverseitig_lesen(
        pfad, b"\xff\xd8\xff\xe0bild", ".jpg", "christoph0711.io"))

    stamm = pfad.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    eintrag = babu_web.index_aktuell()["belege"][stamm]
    assert eintrag["status"] == "geprüft" and eintrag["brutto"] == 141.0
