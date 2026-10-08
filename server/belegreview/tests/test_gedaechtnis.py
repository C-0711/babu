"""Das Faktengedächtnis: was Nina babu über sich erzählt hat.

Der Gesprächsverlauf reicht nicht. „Ich habe zwei Minijobberinnen",
„montags ist zu", „die Kaffeemaschine war für den Salon" steht in keinem
Beleg und wäre mit dem Faden weg. Genau das unterscheidet einen Kumpel von
einer Auskunft.

Zwei Regeln, die hier festgenagelt sind:

1. **Gemerkt wird nur, was sie selbst gesagt hat.** Entweder ausdrücklich
   („merk dir, dass …") oder von Hand eingetragen. Was das Modell bloß
   vermutet, kommt nie hierher — eine Erfindung im Gedächtnis sieht danach
   in jeder Antwort wie ein Fakt aus.
2. **Sie kann es sehen und löschen** (Art. 15 und Art. 17 DSGVO), einzeln
   und in einem Griff. Deshalb liegt es in der Datenbank und nicht in der
   Belegbox, wo jede Fassung für immer stünde.
"""
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import gedaechtnis as gd  # noqa: E402


# ————— Die reine Rechnung: was ist ein Merksatz? —————

def test_die_bitte_sich_etwas_zu_merken_wird_erkannt():
    assert gd.merksatz_aus_frage("Merk dir, dass montags zu ist") == "montags zu ist"
    assert gd.merksatz_aus_frage("merke dir: ich habe zwei Minijobberinnen") \
        == "ich habe zwei Minijobberinnen"
    assert gd.merksatz_aus_frage("Ach, und denk dran: die Kaffeemaschine war "
                                 "für den Salon") == "die Kaffeemaschine war für den Salon"


def test_eine_normale_frage_wird_nicht_gemerkt():
    """Der wichtigste Fall: fast alles, was sie sagt, ist eine Frage und
    keine Ansage. Wer hier zu breit sammelt, füllt das Gedächtnis mit
    Fragen statt mit Wissen."""
    for frage in ("Was habe ich im Mai ausgegeben?",
                  "Ich habe zwei Minijobberinnen — muss ich die anmelden?",
                  "Wie läuft mein Salon?",
                  "Kann ich die Kaffeemaschine absetzen?",
                  ""):
        assert gd.merksatz_aus_frage(frage) is None, frage


def test_der_laengere_ausloeser_gewinnt():
    """Sonst bliebe „bitte" als erstes Wort im Merksatz stehen."""
    assert gd.merksatz_aus_frage("Merk dir bitte, dass ich Dienstag frei habe") \
        == "ich Dienstag frei habe"


def test_ein_leerer_rest_ist_kein_merksatz():
    assert gd.merksatz_aus_frage("Merk dir das") is None
    assert gd.merksatz_aus_frage("denk dran!") is None


def test_derselbe_satz_zweimal_ist_kein_zweites_wissen():
    assert gd.ist_neu("Montags ist zu", ["montags ist zu."]) is False
    assert gd.ist_neu("Dienstags ist zu", ["montags ist zu"]) is True


def test_ein_merksatz_bleibt_ein_satz():
    lang = "x" * 900
    assert len(gd.merksatz_aus_frage("merk dir: " + lang)) == gd.MAX_TEXT
    assert len(gd.saubern(lang)) == gd.MAX_TEXT
    assert gd.saubern("  ") is None and gd.saubern(None) is None


def test_der_block_sagt_woher_das_kommt():
    """Damit babu „du hast mir gesagt, dass …" schreibt und es nicht als
    eigene Erkenntnis ausgibt."""
    text = gd.block(["montags ist zu", "zwei Minijobberinnen"])
    assert "montags ist zu" in text and "zwei Minijobberinnen" in text
    assert "erzählt" in text.lower()
    assert gd.block([]) == "" and gd.block(None) == ""


def test_der_block_waechst_nicht_unbegrenzt():
    text = gd.block([f"Satz {i}" for i in range(200)])
    assert text.count("·") == gd.MAX_SAETZE


# ————— Am laufenden Server: merken, sehen, vergessen —————

@pytest.fixture()
def welt(tmp_path, monkeypatch):
    import babu_web

    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None
    babu_web._LOGIN_VERSUCHE.clear()
    babu_web._REG_ZULETZT.clear()

    gesagt: list[dict] = []

    class Antwort:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "Alles klar."}}]}

    monkeypatch.setattr(babu_web.requests, "post",
                        lambda url, json=None, **kw: (gesagt.append(json), Antwort())[1])
    monkeypatch.setattr(babu_web, "_welt_fuer", lambda un: {
        "einstellungen": {"betrieb_name": "Salon Nina"},
        "belege": [], "kassenblaetter": [], "vertraege": [], "rechnungen": [],
        "team": [], "fristen": [], "zahlen": {}, "dokumente": [],
    })

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    return client, babu_web, gesagt


def test_was_sie_zu_merken_gibt_steht_beim_naechsten_mal_im_prompt(welt):
    client, _, gesagt = welt
    client.post("/chat", json={"frage": "Merk dir, dass montags zu ist"})
    client.post("/chat", json={"frage": "Wann soll ich Inventur machen?"})
    system = gesagt[-1]["messages"][0]["content"]
    assert "montags zu ist" in system


def test_es_wirkt_schon_in_derselben_antwort(welt):
    """Sonst antwortet babu auf „merk dir X" ohne X zu kennen — und das
    liest sich, als hätte es nicht zugehört."""
    client, _, gesagt = welt
    client.post("/chat", json={"frage": "Merk dir: ich habe zwei Minijobberinnen"})
    assert "zwei Minijobberinnen" in gesagt[-1]["messages"][0]["content"]


def test_eine_normale_frage_landet_nicht_im_gedaechtnis(welt):
    client, _, _ = welt
    client.post("/chat", json={"frage": "Habe ich zwei Minijobberinnen?"})
    assert client.get("/api/gedaechtnis").json()["merksaetze"] == []


def test_sie_kann_selbst_etwas_eintragen_und_es_sehen(welt):
    """Art. 15: was babu über sie weiß, muss sie sehen können."""
    client, _, _ = welt
    r = client.post("/api/gedaechtnis", json={"text": "Bitte kurze Antworten"})
    assert r.status_code == 200 and r.json()["id"]
    saetze = client.get("/api/gedaechtnis").json()["merksaetze"]
    assert [s["text"] for s in saetze] == ["Bitte kurze Antworten"]
    assert saetze[0]["quelle"] == "eingetragen" and saetze[0]["gelernt"]


def test_derselbe_satz_wird_nicht_zweimal_gemerkt(welt):
    client, _, _ = welt
    client.post("/api/gedaechtnis", json={"text": "Montags ist zu"})
    zweit = client.post("/api/gedaechtnis", json={"text": "montags ist zu."})
    assert zweit.json()["doppelt"] is True
    assert len(client.get("/api/gedaechtnis").json()["merksaetze"]) == 1


def test_leerer_text_wird_abgewiesen(welt):
    client, _, _ = welt
    assert client.post("/api/gedaechtnis", json={"text": " "}).status_code == 400
    assert client.post("/api/gedaechtnis", json={}).status_code == 400


def test_einzeln_vergessen(welt):
    """Art. 17, der genaue Schnitt: ein Satz weg, die anderen bleiben."""
    client, _, _ = welt
    eins = client.post("/api/gedaechtnis", json={"text": "Montags ist zu"}).json()["id"]
    client.post("/api/gedaechtnis", json={"text": "Zwei Minijobberinnen"})
    assert client.post(f"/api/gedaechtnis/{eins}/vergessen").status_code == 200
    uebrig = [s["text"] for s in client.get("/api/gedaechtnis").json()["merksaetze"]]
    assert uebrig == ["Zwei Minijobberinnen"]
    assert client.post(f"/api/gedaechtnis/{eins}/vergessen").status_code == 404


def test_alles_vergessen_in_einem_griff(welt):
    client, _, gesagt = welt
    for text in ("Montags ist zu", "Zwei Minijobberinnen", "Kurze Antworten"):
        client.post("/api/gedaechtnis", json={"text": text})
    r = client.post("/api/gedaechtnis/vergessen")
    assert r.status_code == 200 and r.json()["vergessen"] == 3
    assert client.get("/api/gedaechtnis").json()["merksaetze"] == []
    # Und es ist auch aus dem Prompt raus, nicht nur aus der Liste.
    client.post("/chat", json={"frage": "Und jetzt?"})
    assert "Montags ist zu" not in gesagt[-1]["messages"][0]["content"]


def test_ein_betrieb_sieht_nie_das_gedaechtnis_eines_anderen(welt):
    """Der Satz beschreibt den Salon. Ein anderer Salon hat damit nichts
    zu tun — auch nicht beim Löschen."""
    client, bw, _ = welt
    client.post("/api/gedaechtnis", json={"text": "Montags ist zu"})

    from fastapi.testclient import TestClient
    fremd = TestClient(bw.app, base_url="https://testserver")
    bw._REG_ZULETZT.clear()
    fremd.post("/api/signup", json={"salon": "Fremd", "email": "fremd@x.de",
                                    "passwort": "passwort-lang"})
    assert fremd.get("/api/gedaechtnis").json()["merksaetze"] == []
    assert fremd.post("/api/gedaechtnis/vergessen").json()["vergessen"] == 0
    assert client.get("/api/gedaechtnis").json()["merksaetze"], "fremd hat mitgelöscht"


def test_ohne_anmeldung_kein_gedaechtnis(welt):
    _, bw, _ = welt
    from fastapi.testclient import TestClient
    anonym = TestClient(bw.app, base_url="https://testserver")
    assert anonym.get("/api/gedaechtnis").status_code == 401
    assert anonym.post("/api/gedaechtnis", json={"text": "x y z"}).status_code == 401
    assert anonym.post("/api/gedaechtnis/vergessen").status_code == 401
