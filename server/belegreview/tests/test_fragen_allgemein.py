"""Fragen, die mit keinem einzelnen Beleg zu tun haben.

Nina hat kein Steuerbüro mehr, das sie kurz anrufen kann. Sie fragt babu
deshalb auch „Muss ich die Rechnung aufheben?" und „Was ist eine
Umsatzsteuervoranmeldung?" — und sie fotografiert Briefe vom Amt.

Bisher bekam das Modell zu JEDER Frage die Belege des Salons und dazu die
Anweisung, ausschließlich daraus zu antworten. Auf eine allgemeine Frage kam
damit „steht nicht in deinen Unterlagen". Hier wird geprüft, dass die Frage
vorher einsortiert wird — mit Stichwörtern, nicht mit einem Modell: die
Unterscheidung muss auch dann greifen, wenn vLLM gerade nicht antwortet.
"""
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    sys.path.insert(0, str(HIER.parent))
    import babu_web

    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None
    babu_web._LOGIN_VERSUCHE.clear()
    babu_web._REG_ZULETZT.clear()

    # Kein vLLM in Tests: die Antwort kommt aus einer Attrappe, deren Text
    # der Test selbst setzen kann.
    gesagt: list[dict] = []
    gesagt_antwort = ["Kurz gesagt: ja."]

    class Antwort:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": gesagt_antwort[0]}}]}

        def iter_lines(self, decode_unicode=False):
            import json as _json
            yield "data: " + _json.dumps(
                {"choices": [{"delta": {"content": gesagt_antwort[0]}}]})
            yield "data: [DONE]"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def falsches_post(url, json=None, **kw):
        gesagt.append(json)
        return Antwort()

    monkeypatch.setattr(babu_web.requests, "post", falsches_post)
    monkeypatch.setattr(babu_web, "_welt_fuer", lambda un: {
        "einstellungen": {"betrieb_name": "Salon Nina", "kleinunternehmer": "Nein"},
        "belege": [{"stamm": f"s{i}", "lieferant": "Friseur Großhandel Wagner",
                    "brutto": 141.0 + i, "monat": "2026-08", "datum": "03.08.2026",
                    "belegart": "Wareneinkauf", "offen": []} for i in range(60)],
        "kassenblaetter": [], "vertraege": [], "rechnungen": [], "team": [],
        "fristen": [], "zahlen": {}, "dokumente": [],
    })

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    return client, babu_web, gesagt, gesagt_antwort


# ————— Welche Art Frage ist das? (reine Rechnung, kein Server nötig) —————

@pytest.mark.parametrize("frage", [
    "Muss ich die Rechnung aufheben?",
    "Was ist eine Umsatzsteuervoranmeldung?",
    "Was kann ich als Friseurin absetzen?",
    "Brauche ich eine Kasse mit TSE?",
    "Wie lange muss ich Kassenbons aufbewahren?",
    "Was bedeutet Kleinunternehmerregelung?",
])
def test_allgemeine_fragen_werden_als_allgemein_erkannt(welt, frage):
    _, bw, _, _ = welt
    assert bw.frage_art(frage) == "allgemein", frage


@pytest.mark.parametrize("frage", [
    "Wie viel habe ich im Juli für Bewirtung ausgegeben?",
    "Welche Belege brauchen mich noch?",
    "Was habe ich diesen Monat für Ware ausgegeben?",
    "Wie läuft mein Salon gerade?",
])
def test_fragen_nach_dem_eigenen_bestand_bleiben_bestandsfragen(welt, frage):
    _, bw, _, _ = welt
    assert bw.frage_art(frage) == "bestand", frage


# ————— Was beim Modell ankommt —————

def test_allgemeine_frage_bekommt_den_auftrag_zu_antworten(welt):
    """Der Kern von BABU-40: die Frage darf nicht am Bestand abprallen."""
    client, _, gesagt, _ = welt
    client.post("/chat", json={"frage": "Was ist eine Umsatzsteuervoranmeldung?"})
    inhalt = gesagt[-1]["messages"][-1]["content"]
    assert "ALLGEMEINE FRAGE" in inhalt
    assert "nicht in ihren Unterlagen" in inhalt, \
        "dem Modell muss verboten werden, auf die Unterlagen auszuweichen"


def test_der_prompt_anfang_ist_fuer_jede_frage_derselbe(welt):
    """Seit dem KV-Cache-Umbau wird nichts mehr nach der Frage ausgewählt:
    der Weltblock steht byte-stabil im System-Teil, damit vLLMs
    Prefix-Cache ihn nur einmal rechnet. Sechzig Belege sind kein Ballast
    mehr — sie kosten nach der ersten Frage nichts."""
    client, _, gesagt, _ = welt
    client.post("/chat", json={"frage": "Was ist eine Umsatzsteuervoranmeldung?"})
    system_a = gesagt[-1]["messages"][0]["content"]
    nutzer_a = gesagt[-1]["messages"][-1]["content"]
    client.post("/chat", json={"frage": "Wie viel habe ich diesen Monat ausgegeben?"})
    assert gesagt[-1]["messages"][0]["content"] == system_a
    assert "BELEG-REGISTER (60" in system_a
    # Die Nutzer-Nachricht trägt das Register nicht mehr je Frage mit.
    assert "Friseur Großhandel Wagner" not in nutzer_a


def test_fachwort_wird_in_ninas_sprache_mitgeliefert(welt):
    """„Umsatzsteuervoranmeldung" darf vorkommen — erklärt werden muss es."""
    client, _, gesagt, _ = welt
    client.post("/chat", json={"frage": "Was ist eine Umsatzsteuervoranmeldung?"})
    inhalt = gesagt[-1]["messages"][-1]["content"]
    assert "Zwischenmeldung" in inhalt, "die Klartext-Erklärung fehlt im Prompt"


def test_fachwort_kommt_auch_bei_einer_bestandsfrage_mit(welt):
    client, _, gesagt, _ = welt
    client.post("/chat", json={"frage": "Wie viel Vorsteuer habe ich diesen Monat?"})
    inhalt = gesagt[-1]["messages"][-1]["content"]
    assert "beim Einkauf bezahlt" in inhalt, "die Klartext-Erklärung fehlt im Prompt"


# ————— Beratung: benennen, nicht abweisen —————

@pytest.mark.parametrize("frage", [
    "Das Finanzamt hat eine Betriebsprüfung angekündigt, was mache ich?",
    "Soll ich gegen den Bescheid Einspruch einlegen?",
    "Wie kündige ich meiner Auszubildenden?",
    "Kann ich eine Stundung beantragen?",
])
def test_beratungsfragen_werden_erkannt(welt, frage):
    _, bw, _, _ = welt
    assert bw.beratungsfall(frage), frage


def test_beratungsfrage_wird_beantwortet_und_die_grenze_benannt(welt):
    """Nicht abweisen — aber sagen, wo die Auskunft aufhört."""
    client, _, _, antwort = welt
    antwort[0] = "Sammle die Unterlagen der letzten drei Jahre."
    r = client.post("/chat", json={
        "frage": "Das Finanzamt hat eine Betriebsprüfung angekündigt, was mache ich?"})
    assert r.status_code == 200
    text = r.json()["antwort"]
    assert "Sammle die Unterlagen" in text, "die Frage wurde abgewiesen"
    assert "Beratung" in text and "Steuerberaterin" in text


def test_die_grenze_steht_nicht_zweimal_da(welt):
    client, _, _, antwort = welt
    antwort[0] = ("Sammle die Unterlagen. Das ist keine Steuerberatung — "
                  "sprich mit deiner Steuerberaterin.")
    text = client.post("/chat", json={
        "frage": "Soll ich Einspruch einlegen?"}).json()["antwort"]
    assert text.count("Steuerberaterin") == 1


def test_eine_harmlose_frage_bekommt_keinen_warnhinweis(welt):
    client, _, _, antwort = welt
    antwort[0] = "Ja, den Bon hebst du auf."
    text = client.post("/chat", json={
        "frage": "Muss ich die Rechnung aufheben?"}).json()["antwort"]
    assert text == "Ja, den Bon hebst du auf."


def test_die_grenze_kommt_auch_im_stream_hinterher(welt):
    """Die App streamt — sonst fehlte der Hinweis genau dort, wo Nina liest."""
    client, _, _, antwort = welt
    antwort[0] = "Sammle die Unterlagen."
    r = client.post("/chat", json={"frage": "Soll ich Einspruch einlegen?",
                                   "stream": True})
    assert r.status_code == 200
    assert "Steuerberaterin" in r.text


# ————— Der Brief vom Amt —————

def test_brief_mit_einspruchsfrist_nennt_die_grenze(welt, monkeypatch):
    _, bw, _, _ = welt
    import abschluss_lesen
    monkeypatch.setattr(abschluss_lesen, "seiten_text",
                        lambda pfad: ["Gegen diesen Bescheid können Sie Einspruch "
                                      "einlegen. " * 20])
    erklaerung = bw.brief_erklaerung_bauen(
        b"%PDF-1.4", "brief.pdf",
        llm=lambda n: {"einfach": "Das Finanzamt hat deinen Gewinn geschätzt.",
                       "was_tun": "Einspruch einlegen, wenn die Zahl nicht stimmt.",
                       "bis_wann": "2026-09-15"})
    assert erklaerung["hinweis"], "ein Einspruch ist Beratung — das muss dastehen"
    assert "Steuerberaterin" in erklaerung["hinweis"]


def test_ein_harmloser_brief_bekommt_keinen_hinweis(welt, monkeypatch):
    _, bw, _, _ = welt
    import abschluss_lesen
    monkeypatch.setattr(abschluss_lesen, "seiten_text",
                        lambda pfad: ["Ihre Steuernummer lautet neu 12/345. " * 20])
    erklaerung = bw.brief_erklaerung_bauen(
        b"%PDF-1.4", "brief.pdf",
        llm=lambda n: {"einfach": "Du hast eine neue Steuernummer.",
                       "was_tun": "Trag sie in deine Rechnungen ein.",
                       "bis_wann": None})
    assert erklaerung["hinweis"] is None
