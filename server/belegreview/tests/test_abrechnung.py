"""Aus dem Termin abrechnen — und wie das Geld ins Kassenbuch kommt.

babu kennt den Termin und (neu) den Preis. Nach der Behandlung ein Tipp:
bar oder Karte. Was babu daraus NICHT macht: das Kassenbuch selbst
schreiben. Die Tagessummen bleiben das, was die Inhaberin abends bestätigt
— babu legt sie nur fertig hin. Eine Kasse, die sich selbst bucht, ist
etwas anderes als ein Kassenbuch, und dieser Unterschied ist steuerlich
keine Kleinigkeit.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import abrechnung as ab  # noqa: E402


def leistung(name="Schnitt", preis=42.0, minuten=45, satz=19):
    return {"name": name, "preis": preis, "minuten": minuten, "ust_satz": satz}


def termin(preis=42.0, zahlart="bar", abgerechnet="2026-09-03",
           leistung_="Schnitt", id=1):
    return {"id": id, "start": "2026-09-03T10:00", "minuten": 45,
            "kundin": "Frau Holder", "leistung": leistung_, "preis": preis,
            "zahlart": zahlart, "abgerechnet": abgerechnet}


# ————— Was eine Leistung sein muss —————

def test_eine_leistung_braucht_namen_und_preis():
    with pytest.raises(ab.AbrechnungFehler):
        ab.leistung_pruefen({"name": "", "preis": 42})
    with pytest.raises(ab.AbrechnungFehler):
        ab.leistung_pruefen({"name": "Schnitt", "preis": 0})


def test_unsinniger_preis_wird_abgewiesen():
    for p in (-5, 100000, "viel"):
        with pytest.raises(ab.AbrechnungFehler):
            ab.leistung_pruefen({"name": "Schnitt", "preis": p})


def test_deutsche_schreibweise_geht():
    l = ab.leistung_pruefen({"name": "Farbe", "preis": "89,50", "minuten": "120"})
    assert l["preis"] == 89.5 and l["minuten"] == 120


def test_ohne_dauer_gilt_eine_stunde():
    assert ab.leistung_pruefen({"name": "Beratung", "preis": 30})["minuten"] == 60


def test_steuersatz_faellt_auf_neunzehn_zurueck():
    assert ab.leistung_pruefen({"name": "X", "preis": 10})["ust_satz"] == 19
    assert ab.leistung_pruefen({"name": "X", "preis": 10, "ust_satz": 7})["ust_satz"] == 7
    assert ab.leistung_pruefen({"name": "X", "preis": 10, "ust_satz": 5})["ust_satz"] == 19


# ————— Abrechnen —————

def test_abrechnen_braucht_eine_zahlart():
    with pytest.raises(ab.AbrechnungFehler):
        ab.zahlart_pruefen("bitcoin")
    assert ab.zahlart_pruefen("bar") == "bar"
    assert ab.zahlart_pruefen("karte") == "karte"


def test_mit_gutschein_bezahlt_ist_eine_zahlart():
    """Die Kasse kennt den Gutschein als Tagessumme, das Abrechnen bisher
    nicht — wer am Termin „Gutschein" tippte, bekam eine Absage."""
    assert ab.zahlart_pruefen("gutschein") == "gutschein"


# ————— Der Vorschlag fürs Kassenbuch —————

def test_die_tagessummen_werden_vorgeschlagen():
    tag = ab.tagesvorschlag("2026-09-03", [
        termin(preis=42.0, zahlart="bar"),
        termin(preis=89.5, zahlart="karte", id=2),
        termin(preis=25.0, zahlart="bar", id=3),
    ])
    assert tag["bar"] == 67.0
    assert tag["karte"] == 89.5
    assert tag["zusammen"] == 156.5
    assert tag["termine"] == 3


def test_nicht_abgerechnete_termine_zaehlen_nicht():
    tag = ab.tagesvorschlag("2026-09-03", [
        termin(preis=42.0), termin(preis=99.0, abgerechnet=None, id=2)])
    assert tag["bar"] == 42.0 and tag["termine"] == 1
    assert tag["offen"] == 1


def test_ein_anderer_tag_zaehlt_nicht_mit():
    t = termin(preis=42.0)
    t["abgerechnet"] = "2026-09-04"
    assert ab.tagesvorschlag("2026-09-03", [t])["zusammen"] == 0.0


def test_sieben_prozent_wird_getrennt_ausgewiesen():
    """Pflegeprodukte laufen mit 7 % — das Kassenbuch fragt danach."""
    t = termin(preis=21.4, id=4)
    t["ust_satz"] = 7
    tag = ab.tagesvorschlag("2026-09-03", [termin(preis=42.0), t])
    assert tag["umsatz7"] == 21.4
    assert tag["zusammen"] == 63.4


def test_ein_eingeloester_gutschein_ist_kein_bargeld():
    """Sonst stünde Geld im Kassenbuch, das nicht in der Schublade liegt.

    Beim Einlösen kommt nichts herein — bezahlt wurde beim Verkauf des
    Gutscheins. Die Summe gehört deshalb auf `gutscheineEingeloest`, das
    weder in den Kassenbestand noch in den Tagesumsatz zählt.
    """
    tag = ab.tagesvorschlag("2026-09-03", [
        termin(preis=42.0, zahlart="bar"),
        termin(preis=40.0, zahlart="gutschein", id=2),
    ])
    assert tag["bar"] == 42.0
    assert tag["gutschein"] == 40.0
    assert tag["zusammen"] == 42.0        # der Gutschein bringt keinen Umsatz
    assert tag["termine"] == 2


def test_ein_gutschein_bringt_auch_keinen_umsatz_zu_sieben_prozent():
    """Die Aufteilung 7/19 beschreibt den Tagesumsatz. Wäre der eingelöste
    Gutschein darin, wären die 7 % größer als der Umsatz, aus dem sie
    stammen sollen."""
    t = termin(preis=21.4, zahlart="gutschein", id=4)
    t["ust_satz"] = 7
    tag = ab.tagesvorschlag("2026-09-03", [termin(preis=42.0), t])
    assert tag["umsatz7"] == 0.0
    assert tag["zusammen"] == 42.0


def test_der_satz_nennt_den_gutschein_eigens():
    """Ohne einen eigenen Halbsatz sähe es aus, als wäre die Behandlung
    unbezahlt geblieben."""
    tag = ab.tagesvorschlag("2026-09-03", [
        termin(preis=42.0), termin(preis=40.0, zahlart="gutschein", id=2)])
    assert "Gutschein" in tag["satz"]
    assert "40" in tag["satz"].replace(",", ".")


def test_der_satz_sagt_was_zu_tun_ist():
    leer = ab.tagesvorschlag("2026-09-03", [])
    voll = ab.tagesvorschlag("2026-09-03", [termin(preis=42.0)])
    assert "nichts" in leer["satz"].lower()
    assert "42" in voll["satz"].replace(",", ".")
    for s in (leer["satz"], voll["satz"]):
        assert s[0].isupper() or s[0].isdigit()


def test_babu_schreibt_das_kassenbuch_nicht_selbst():
    """Der Vorschlag ist ein Vorschlag — er trägt kein Datum der Buchung
    und keine Bestätigung. Das Kassenbuch bleibt die Bestätigung der
    Inhaberin."""
    tag = ab.tagesvorschlag("2026-09-03", [termin(preis=42.0)])
    assert "gebucht" not in tag and "commit" not in tag
    assert tag["vorschlag"] is True


# ————— Aus dem Termin eine Rechnung —————

def test_aus_dem_termin_wird_eine_rechnungsposition():
    p = ab.rechnungsposition(termin(preis=89.5, leistung_="Farbe"))
    assert p["text"] == "Farbe"
    assert p["einzelpreis"] == 89.5
    assert p["ust_satz"] == 19


def test_ohne_preis_keine_position():
    with pytest.raises(ab.AbrechnungFehler):
        ab.rechnungsposition(termin(preis=None))


# ————— Der Punkt ist zweideutig (derselbe Fehler wie in der App) —————

@pytest.mark.parametrize("eingabe, erwartet", [
    (89.5, 89.5),            # echte Zahl — darf nie durch den Text-Parser
    (42, 42.0),
    ("89,50", 89.5),         # deutsch getippt
    ("1.250,00", 1250.0),    # mit Tausenderpunkt
    ("89.50", 89.5),         # englisch getippt
    ("1250", 1250.0),
])
def test_preise_werden_richtig_gelesen(eingabe, erwartet):
    assert ab.leistung_pruefen({"name": "X", "preis": eingabe})["preis"] == erwartet


# ————— Die Strecke am Server: Preis, Abrechnen, Kartei —————

import subprocess  # noqa: E402


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


def test_leistung_anlegen_und_wiederfinden(welt):
    client, _ = welt
    r = client.post("/api/leistungen", json={"name": "Farbe", "preis": "89,50",
                                             "minuten": 120})
    assert r.status_code == 200 and r.json()["preis"] == 89.5
    liste = client.get("/api/leistungen").json()["leistungen"]
    assert liste[0]["name"] == "Farbe" and liste[0]["minuten"] == 120


def test_termin_abrechnen_und_kassenvorschlag(welt):
    client, _ = welt
    import datetime as dt
    heute = dt.date.today().isoformat()
    t = client.post("/api/termine", json={"start": f"{heute}T10:00", "minuten": 60,
                                          "wer": "Jana", "kundin": "Frau Holder",
                                          "leistung": "Schnitt"}).json()
    assert client.post(f"/api/termin/{t['id']}/abrechnen",
                       json={"zahlart": "bar", "preis": "42,00"}).status_code == 200

    v = client.get("/api/kasse/vorschlag").json()
    assert v["bar"] == 42.0 and v["karte"] == 0.0
    assert v["vorschlag"] is True
    assert "42" in v["satz"].replace(",", ".")


def test_mit_gutschein_abrechnen_geht_und_bleibt_aus_der_kasse(welt):
    """Vorher lief „gutschein" in einen Fehler; ginge er als „bar" durch,
    stünde am Abend Bargeld im Vorschlag, das niemand gezählt hat."""
    client, _ = welt
    import datetime as dt
    heute = dt.date.today().isoformat()
    t = client.post("/api/termine", json={"start": f"{heute}T12:00", "minuten": 60,
                                          "wer": "Jana", "kundin": "Frau Sommer",
                                          "leistung": "Schnitt"}).json()
    r = client.post(f"/api/termin/{t['id']}/abrechnen",
                    json={"zahlart": "gutschein", "preis": "40,00"})
    assert r.status_code == 200 and r.json()["zahlart"] == "gutschein"

    v = client.get("/api/kasse/vorschlag").json()
    assert v["gutschein"] == 40.0
    assert v["bar"] == 0.0 and v["karte"] == 0.0
    assert v["zusammen"] == 0.0


def test_ohne_preis_kein_abrechnen(welt):
    client, _ = welt
    import datetime as dt
    heute = dt.date.today().isoformat()
    t = client.post("/api/termine", json={"start": f"{heute}T11:00", "minuten": 60,
                                          "wer": "Jana"}).json()
    r = client.post(f"/api/termin/{t['id']}/abrechnen", json={"zahlart": "bar"})
    assert r.status_code == 400 and "gekostet" in r.json()["fehler"]


def test_kundenkartei_mit_verlauf(welt):
    client, _ = welt
    k = client.post("/api/kundinnen", json={"name": "Frau Holder",
                                            "telefon": "0711 123",
                                            "allergie": "PPD-Unverträglichkeit"})
    assert k.status_code == 200
    kid = k.json()["id"]
    assert client.post(f"/api/kundin/{kid}/behandlung", json={
        "leistung": "Farbe", "formel": "7/0 + 8/3, 30 min",
        "notiz": "Ansatz nachgedunkelt"}).status_code == 200

    d = client.get(f"/api/kundin/{kid}").json()
    assert d["allergie"] == "PPD-Unverträglichkeit"
    assert d["verlauf"][0]["formel"] == "7/0 + 8/3, 30 min"


def test_kundin_suchen(welt):
    client, _ = welt
    for n in ("Frau Holder", "Frau Sommer", "Herr Betz"):
        client.post("/api/kundinnen", json={"name": n})
    assert len(client.get("/api/kundinnen", params={"suche": "Frau"}).json()["kundinnen"]) == 2


def test_loeschen_nimmt_den_ganzen_verlauf_mit(welt):
    """Farbformeln und Allergiehinweise müssen wirklich weggehen."""
    client, bw = welt
    kid = client.post("/api/kundinnen", json={"name": "Frau Holder",
                                              "allergie": "PPD"}).json()["id"]
    client.post(f"/api/kundin/{kid}/behandlung", json={"formel": "7/0"})
    assert client.post(f"/api/kundin/{kid}/loeschen").status_code == 200
    assert client.get(f"/api/kundin/{kid}").status_code == 404
    with bw._DB_LOCK, bw._db() as c:
        assert c.execute("SELECT COUNT(*) FROM behandlung").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM kundin").fetchone()[0] == 0


def test_kundendaten_landen_nicht_in_der_belegbox(welt):
    """In Git bliebe eine Farbformel für immer stehen."""
    client, _ = welt
    kid = client.post("/api/kundinnen", json={"name": "Frau Holder"}).json()["id"]
    client.post(f"/api/kundin/{kid}/behandlung", json={"formel": "7/0 + 8/3"})
    jahre = client.get("/api/ablage").json()["jahre"]
    assert "7/0" not in str(jahre) and "Holder" not in str(jahre)


def test_fremdes_konto_sieht_die_kartei_nicht(welt):
    client, bw = welt
    client.post("/api/kundinnen", json={"name": "Frau Holder"})
    from fastapi.testclient import TestClient
    fremd = TestClient(bw.app, base_url="https://testserver")
    bw._REG_ZULETZT.clear()
    fremd.post("/api/signup", json={"salon": "Fremd", "email": "fremd@x.de",
                                    "passwort": "passwort-lang"})
    assert fremd.get("/api/kundinnen").status_code == 403


def test_die_kartennummer_wird_mitgeschrieben(welt):
    """Ohne die Referenz beim Anbieter ist eine Kartenzahlung später nicht
    auffindbar — Kassenbuch und Kontoauszug hängen daran zusammen."""
    client, _ = welt
    import datetime as dt
    heute = dt.date.today().isoformat()
    t = client.post("/api/termine", json={"start": f"{heute}T14:00",
                                          "minuten": 45, "kundin": "Frau Holder"}).json()
    r = client.post(f"/api/termin/{t['id']}/abrechnen",
                    json={"zahlart": "karte", "preis": "42,00",
                          "referenz": "pi_3Qabc123"})
    assert r.status_code == 200

    liste = client.get(f"/api/termine?von={heute}&bis={heute}").json()["tage"][0]["liste"]
    assert liste[0]["zahlung_ref"] == "pi_3Qabc123"


def test_barzahlung_braucht_keine_referenz(welt):
    client, _ = welt
    import datetime as dt
    heute = dt.date.today().isoformat()
    t = client.post("/api/termine", json={"start": f"{heute}T15:00",
                                          "minuten": 45, "kundin": "Frau Sommer"}).json()
    assert client.post(f"/api/termin/{t['id']}/abrechnen",
                       json={"zahlart": "bar", "preis": "20,00"}).status_code == 200
    liste = client.get(f"/api/termine?von={heute}&bis={heute}").json()["tage"][0]["liste"]
    assert liste[0]["zahlung_ref"] is None
