"""Der eigene Terminkalender — souverän, ohne fremdes System.

Ein Salontag besteht aus Terminen. babu führt sie selbst: keine Anbindung,
keine Abhängigkeit, die Daten bleiben im Haus.

Der wichtigste Teil ist nicht das Eintragen, sondern das Verhindern: zwei
Kundinnen zur selben Zeit bei derselben Stylistin ist der Fehler, der einen
Tag ruiniert.
"""
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kalender as ka  # noqa: E402


def termin(start="2026-09-03T10:00", minuten=60, wer="Jana", id=1):
    return {"id": id, "start": start, "minuten": minuten, "wer": wer,
            "kundin": "Frau Holder", "leistung": "Schnitt"}


# ————— Zwei zur selben Zeit —————

def test_ueberschneidung_bei_derselben_stylistin():
    bestehend = [termin(start="2026-09-03T10:00", minuten=60)]
    neu = termin(start="2026-09-03T10:30", minuten=30, id=2)
    assert ka.stoert(neu, bestehend) is not None


def test_direkt_danach_ist_keine_ueberschneidung():
    bestehend = [termin(start="2026-09-03T10:00", minuten=60)]
    neu = termin(start="2026-09-03T11:00", minuten=30, id=2)
    assert ka.stoert(neu, bestehend) is None


def test_verschiedene_stylistinnen_stoeren_sich_nicht():
    bestehend = [termin(start="2026-09-03T10:00", wer="Jana")]
    neu = termin(start="2026-09-03T10:00", wer="Mira", id=2)
    assert ka.stoert(neu, bestehend) is None


def test_ein_termin_stoert_sich_nicht_selbst():
    """Beim Verschieben darf der eigene Termin nicht im Weg stehen."""
    bestehend = [termin(id=7, start="2026-09-03T10:00")]
    verschoben = termin(id=7, start="2026-09-03T10:15")
    assert ka.stoert(verschoben, bestehend) is None


def test_abgesagte_termine_blockieren_nicht():
    bestehend = [dict(termin(), abgesagt=True)]
    assert ka.stoert(termin(start="2026-09-03T10:15", id=2), bestehend) is None


def test_die_meldung_nennt_wen_es_trifft():
    bestehend = [termin(start="2026-09-03T10:00")]
    meldung = ka.stoert(termin(start="2026-09-03T10:30", id=2), bestehend)
    assert "Jana" in meldung and "10:00" in meldung


# ————— Was ein Termin haben muss —————

def test_ein_termin_braucht_eine_dauer():
    with pytest.raises(ka.KalenderFehler):
        ka.pruefen({"start": "2026-09-03T10:00", "minuten": 0, "wer": "Jana"})


def test_unsinnige_dauer_wird_abgewiesen():
    for minuten in (-30, 24 * 60 + 1):
        with pytest.raises(ka.KalenderFehler):
            ka.pruefen({"start": "2026-09-03T10:00", "minuten": minuten,
                        "wer": "Jana"})


def test_kaputte_zeit_wird_abgewiesen():
    with pytest.raises(ka.KalenderFehler):
        ka.pruefen({"start": "irgendwann", "minuten": 60, "wer": "Jana"})


def test_ein_geprueffter_termin_hat_ein_ende():
    t = ka.pruefen(termin(start="2026-09-03T10:00", minuten=45))
    assert t["ende"] == "2026-09-03T10:45"


# ————— Der Tag —————

def test_der_tag_zaehlt_termine_und_minuten():
    tag = ka.tag("2026-09-03", [termin(minuten=60), termin(minuten=30, id=2,
                                                           start="2026-09-03T12:00")])
    assert tag["termine"] == 2
    assert tag["minuten"] == 90
    assert "1 Std 30 min" == tag["dauer_text"]


def test_abgesagte_zaehlen_nicht_mit():
    tag = ka.tag("2026-09-03", [termin(), dict(termin(id=2), abgesagt=True)])
    assert tag["termine"] == 1


def test_ein_leerer_tag_ist_kein_fehler():
    tag = ka.tag("2026-09-03", [])
    assert tag["termine"] == 0 and tag["minuten"] == 0


# ————— Termin trifft Geld: das, was kein Buchungsanbieter kann —————

def test_was_eine_gebuchte_stunde_einbringt():
    tag = ka.tag("2026-09-03", [termin(minuten=120)], umsatz=240.0)
    assert tag["pro_stunde"] == 120.0


def test_ohne_umsatz_keine_erfundene_zahl():
    assert ka.tag("2026-09-03", [termin()])["pro_stunde"] is None


def test_umsatz_ohne_termine_ergibt_keine_division():
    """Laufkundschaft: Geld kam rein, gebucht war nichts."""
    tag = ka.tag("2026-09-03", [], umsatz=180.0)
    assert tag["pro_stunde"] is None
    assert tag["umsatz"] == 180.0


def test_der_satz_zum_tag_kommt_ohne_technik_aus():
    for tag in (ka.tag("2026-09-03", []),
                ka.tag("2026-09-03", [termin()], umsatz=90.0),
                ka.tag("2026-09-03", [termin(), termin(id=2,
                                                       start="2026-09-03T14:00")])):
        satz = tag["satz"]
        # Ein Satz, kein Datenfeld: er darf mit einer Zahl anfangen
        # („2 Termine, …"), aber nicht mit Kleinbuchstaben oder Klammern.
        assert satz and (satz[0].isupper() or satz[0].isdigit())
        assert satz.endswith((".", "e", "d"))       # ganzer Satz, kein Fragment
        for technik in ("None", "null", "{", "[", "minuten="):
            assert technik not in satz


# ————— Am Server —————

@pytest.fixture()
def welt(tmp_path, monkeypatch):
    import subprocess
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
    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={}, rechnungen={},
                           kassenblaetter={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    return client, babu_web


def test_termin_eintragen_und_wiederfinden(welt):
    client, _ = welt
    r = client.post("/api/termine", json={
        "start": "2026-09-03T10:00", "minuten": 60, "wer": "Jana",
        "kundin": "Frau Holder", "leistung": "Schnitt und Farbe"})
    assert r.status_code == 200
    assert r.json()["ende"] == "2026-09-03T11:00"

    d = client.get("/api/termine", params={"von": "2026-09-03"}).json()
    assert d["tage"][0]["termine"] == 1
    assert d["tage"][0]["liste"][0]["kundin"] == "Frau Holder"


def test_der_server_laesst_keine_doppelbelegung_zu(welt):
    """Der Fehler, der einen Salontag ruiniert."""
    client, _ = welt
    client.post("/api/termine", json={"start": "2026-09-03T10:00", "minuten": 60,
                                      "wer": "Jana", "kundin": "Frau Holder"})
    r = client.post("/api/termine", json={"start": "2026-09-03T10:30",
                                          "minuten": 30, "wer": "Jana",
                                          "kundin": "Frau Betz"})
    assert r.status_code == 409
    assert "Frau Holder" in r.json()["fehler"]


def test_verschieben_geht_trotzdem(welt):
    client, _ = welt
    id_ = client.post("/api/termine", json={"start": "2026-09-03T10:00",
                                            "minuten": 60, "wer": "Jana"}).json()["id"]
    r = client.post("/api/termine", json={"id": id_, "start": "2026-09-03T10:15",
                                          "minuten": 60, "wer": "Jana"})
    assert r.status_code == 200, "der eigene Termin darf sich nicht selbst blockieren"


def test_absagen_laesst_die_luecke_sichtbar(welt):
    client, _ = welt
    id_ = client.post("/api/termine", json={"start": "2026-09-03T10:00",
                                            "minuten": 60, "wer": "Jana"}).json()["id"]
    assert client.post(f"/api/termin/{id_}/absagen").status_code == 200
    d = client.get("/api/termine", params={"von": "2026-09-03"}).json()
    assert d["tage"][0]["termine"] == 0
    # Der Platz ist wieder frei.
    assert client.post("/api/termine", json={"start": "2026-09-03T10:00",
                                             "minuten": 60,
                                             "wer": "Jana"}).status_code == 200


def test_loeschen_entfernt_die_kundendaten(welt):
    """Personenbezogenes muss wirklich weggehen (Art. 17 DSGVO)."""
    client, bw = welt
    id_ = client.post("/api/termine", json={"start": "2026-09-03T10:00",
                                            "minuten": 60, "wer": "Jana",
                                            "kundin": "Frau Holder"}).json()["id"]
    assert client.post(f"/api/termin/{id_}/loeschen").status_code == 200
    with bw._DB_LOCK, bw._db() as c:
        assert c.execute("SELECT COUNT(*) FROM termin").fetchone()[0] == 0


def test_termine_liegen_nicht_in_der_belegbox(welt):
    """In einem Termin steht ein Kundenname — in Git bliebe er für immer."""
    client, _ = welt
    client.post("/api/termine", json={"start": "2026-09-03T10:00", "minuten": 60,
                                      "wer": "Jana", "kundin": "Frau Holder"})
    jahre = client.get("/api/ablage").json()["jahre"]
    alles = " ".join(str(j) for j in jahre)
    assert "Holder" not in alles


def test_fremdes_konto_sieht_keine_termine(welt):
    client, bw = welt
    client.post("/api/termine", json={"start": "2026-09-03T10:00", "minuten": 60,
                                      "wer": "Jana", "kundin": "Frau Holder"})
    from fastapi.testclient import TestClient
    fremd = TestClient(bw.app, base_url="https://testserver")
    bw._REG_ZULETZT.clear()
    fremd.post("/api/signup", json={"salon": "Fremd", "email": "fremd@x.de",
                                    "passwort": "passwort-lang"})
    assert fremd.get("/api/termine", params={"von": "2026-09-03"}).status_code == 403


# ————— Freie Lücken: das rechnet babu, nicht das Modell —————

def test_ein_leerer_tag_ist_voller_luecken():
    frei = ka.freie_luecken("2026-09-03", [], dauer=60)
    assert frei[0] == "09:00"
    assert len(frei) == 6          # gedeckelt, nicht endlos


def test_belegte_zeit_faellt_raus():
    t = [termin(start="2026-09-03T09:00", minuten=120, wer="Jana")]
    frei = ka.freie_luecken("2026-09-03", t, dauer=60, wer="Jana")
    assert "09:00" not in frei and "10:00" not in frei
    assert "11:00" in frei


def test_die_luecke_muss_lang_genug_sein():
    t = [termin(start="2026-09-03T09:00", minuten=30, wer="Jana"),
         termin(start="2026-09-03T10:00", minuten=30, wer="Jana", id=2)]
    # Zwischen 09:30 und 10:00 ist nur eine halbe Stunde frei.
    assert "09:30" not in ka.freie_luecken("2026-09-03", t, dauer=60, wer="Jana")
    assert "09:30" in ka.freie_luecken("2026-09-03", t, dauer=30, wer="Jana")


def test_nach_ladenschluss_gibt_es_nichts():
    frei = ka.freie_luecken("2026-09-03", [], dauer=60)
    assert all(z < "17:01" for z in frei)


def test_eine_andere_stylistin_hat_eigene_luecken():
    t = [termin(start="2026-09-03T09:00", minuten=180, wer="Jana")]
    assert "09:00" in ka.freie_luecken("2026-09-03", t, dauer=60, wer="Mira")


# ————— Was die KI liefert, wird geprüft —————

HEUTE = dt.date(2026, 9, 1)


def test_ein_brauchbarer_wunsch_geht_durch():
    w = ka.wunsch_pruefen({"kundin": "Frau Holder", "leistung": "Farbe",
                           "datum": "2026-09-03", "uhrzeit": "14:00",
                           "minuten": 120}, HEUTE)
    assert w["datum"] == "2026-09-03" and w["minuten"] == 120
    assert w["sicher"] is True


def test_ein_datum_in_der_vergangenheit_ist_ein_lesefehler():
    w = ka.wunsch_pruefen({"kundin": "X", "datum": "2026-08-01"}, HEUTE)
    assert w["datum"] is None and w["sicher"] is False


def test_unsinnige_dauer_faellt_auf_den_normalfall_zurueck():
    for minuten in (0, -30, 99999, "viel"):
        assert ka.wunsch_pruefen({"minuten": minuten}, HEUTE)["minuten"] == 60


def test_ohne_kundin_ist_es_nicht_sicher():
    w = ka.wunsch_pruefen({"datum": "2026-09-03"}, HEUTE)
    assert w["sicher"] is False


def test_kaputte_uhrzeit_wird_verworfen_statt_geraten():
    assert ka.wunsch_pruefen({"uhrzeit": "nachmittags"}, HEUTE)["uhrzeit"] is None
    assert ka.wunsch_pruefen({"uhrzeit": "14:30"}, HEUTE)["uhrzeit"] == "14:30"


def test_der_auftrag_sagt_dem_modell_dass_es_nicht_raten_soll():
    frage = ka.frage_bauen("Frau Holder Donnerstag Farbe", HEUTE)
    assert "Rate nie" in frage and "2026-09-01" in frage
    assert "Frau Holder" in frage


# ————— Die KI schlägt vor, sie bucht nicht —————

def test_aus_einem_satz_werden_vorschlaege(welt, monkeypatch):
    client, bw = welt

    class Antwort:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content":
                '{"kundin":"Frau Holder","leistung":"Farbe","wer":"Jana",'
                '"datum":"2099-09-03","uhrzeit":"14:00","minuten":120}'}}]}

    monkeypatch.setattr(bw.requests, "post", lambda *a, **k: Antwort())
    r = client.post("/api/termine/vorschlag",
                    json={"text": "Frau Holder Donnerstag Farbe"})
    assert r.status_code == 200
    d = r.json()
    assert d["wunsch"]["kundin"] == "Frau Holder"
    assert d["wunsch"]["minuten"] == 120
    assert d["vorschlaege"][0] == "14:00", "der Wunschzeitpunkt steht zuerst"
    # Nichts wurde gebucht.
    assert client.get("/api/termine",
                      params={"von": "2099-09-03"}).json()["tage"][0]["termine"] == 0


def test_belegter_wunsch_bekommt_alternativen(welt, monkeypatch):
    client, bw = welt
    client.post("/api/termine", json={"start": "2099-09-03T14:00", "minuten": 120,
                                      "wer": "Jana", "kundin": "Frau Betz"})

    class Antwort:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content":
                '{"kundin":"Frau Holder","wer":"Jana","datum":"2099-09-03",'
                '"uhrzeit":"14:00","minuten":120}'}}]}

    monkeypatch.setattr(bw.requests, "post", lambda *a, **k: Antwort())
    d = client.post("/api/termine/vorschlag", json={"text": "egal"}).json()
    assert "14:00" not in d["vorschlaege"]
    assert d["vorschlaege"], "es muss Alternativen geben"
    assert "schon etwas" in d["hinweis"]


def test_ohne_modell_bleibt_der_kalender_bedienbar(welt, monkeypatch):
    """Fällt vLLM aus, sagt babu das — und man trägt von Hand ein."""
    client, bw = welt

    def kaputt(*a, **k):
        raise RuntimeError("weg")

    monkeypatch.setattr(bw.requests, "post", kaputt)
    r = client.post("/api/termine/vorschlag", json={"text": "Frau Holder morgen"})
    assert r.status_code == 503
    assert "von Hand" in r.json()["fehler"]
    # Der normale Weg geht weiter.
    assert client.post("/api/termine", json={"start": "2099-09-03T10:00",
                                             "minuten": 60,
                                             "wer": "Jana"}).status_code == 200


def test_leerer_satz_wird_abgewiesen(welt):
    client, _ = welt
    assert client.post("/api/termine/vorschlag", json={"text": ""}).status_code == 400


def test_alternativen_sind_ueber_den_tag_verteilt():
    """Vier Viertelstunden am Stück sind dieselbe Antwort viermal."""
    frei = ka.freie_luecken("2026-09-03", [], dauer=60, hoechstens=4)
    assert frei[0] == "09:00"
    assert frei[-1] >= "16:00", f"letzter Vorschlag zu früh: {frei}"
    # Kein Vorschlag klebt am nächsten.
    abstaende = [int(b[:2]) - int(a[:2]) for a, b in zip(frei, frei[1:])]
    assert all(x >= 2 for x in abstaende), f"zu dicht beieinander: {frei}"


def test_frei_ist_eine_eigene_frage_nicht_die_vorschlagsliste():
    """14:00 kann frei sein, ohne in der Auswahl vorzukommen."""
    assert "14:00" not in ka.freie_luecken("2026-09-03", [], dauer=120)
    assert ka.ist_frei("2026-09-03", [], "14:00", 120) is True


def test_belegtes_ist_nicht_frei():
    t = [termin(start="2026-09-03T14:00", minuten=60, wer="Jana")]
    assert ka.ist_frei("2026-09-03", t, "14:30", 60, "Jana") is False
    assert ka.ist_frei("2026-09-03", t, "15:00", 60, "Jana") is True


def test_nach_ladenschluss_ist_nichts_frei():
    assert ka.ist_frei("2026-09-03", [], "17:30", 60) is False
    assert ka.ist_frei("2026-09-03", [], "08:00", 60) is False
