"""Die Kreditorenliste auf der DATEV-Seite — Routen, Box, Rechte (K1).

Gelesen und geschrieben wird `stammdaten/kreditoren.json` in der Box des
Betriebs. Hereinlesen zeigt erst eine Vorschau und schreibt nichts;
Übernehmen schreibt einen Commit. Die Regel selbst prüft
`test_kreditoren.py`.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import box as bx  # noqa: E402
from test_acting_as import _login, welt2  # noqa: F401,E402
from test_datev_seite import c, welt  # noqa: F401,E402
from test_kreditoren import _alter_stapel, _datev16  # noqa: E402


def _commits(welt) -> int:
    r = subprocess.run(["git", "-C", str(welt.STORE), "rev-list", "--count", "HEAD"],
                       check=True, capture_output=True, text=True)
    return int(r.stdout)


def _datei(welt, pfad) -> dict | None:
    r = subprocess.run(["git", "-C", str(welt.STORE), "show", f"HEAD:{pfad}"],
                       capture_output=True)
    return json.loads(r.stdout) if r.returncode == 0 else None


def _letzte_nachricht(welt) -> str:
    return subprocess.run(["git", "-C", str(welt.STORE), "log", "-1", "--format=%s"],
                          capture_output=True, text=True).stdout.strip()


DATEV_DATEI = _datev16([
    '70001;"Friseurbedarf Nord GmbH";;;;;"2";;"DE89370400440532013000"',
    '70002;"Wella Deutschland GmbH";;;;;"2";;""',
    '10001;"Kundin";;;;;"2";;""',
])


def _hochladen(c, pfad, roh=DATEV_DATEI, name="kreditoren.csv"):
    return c.post(pfad, files={"datei": (name, roh, "text/csv")})


# ————— Rechte —————

def test_ein_salon_sieht_die_kreditoren_nicht(welt, c, monkeypatch):
    monkeypatch.setattr(welt, "rolle", lambda un: "salon")
    assert c.get("/api/datev/kreditoren").status_code == 403
    assert c.post("/api/datev/kreditoren", json={"name": "X"}).status_code == 403


# ————— Liste, Anlegen, Ändern, Einstellung —————

def test_ohne_liste_gilt_das_sammelkonto(c):
    d = c.get("/api/datev/kreditoren").json()
    assert (d["modus"], d["sammelkonto"], d["naechste"]) == ("sammel", "70099", "70001")
    assert d["eintraege"] == [] and d["gesamt"] == 0


def test_anlegen_schreibt_einen_commit_in_die_box(welt, c):
    vorher = _commits(welt)
    r = c.post("/api/datev/kreditoren", json={"name": "Friseurbedarf Nord"})
    assert r.status_code == 200, r.text
    assert r.json()["kreditor"]["nummer"] == "70001"
    assert _commits(welt) == vorher + 1
    assert _letzte_nachricht(welt) == "kreditoren: 70001 Friseurbedarf Nord angelegt"
    gespeichert = _datei(welt, "stammdaten/kreditoren.json")
    assert gespeichert["kreditoren"][0]["angelegt_von"] == "chef@0711.io"
    d = c.get("/api/datev/kreditoren", params={"buchstabe": "F"}).json()
    assert [k["nummer"] for k in d["eintraege"]] == ["70001"]
    assert d["naechste"] == "70002"


def test_ein_doppelter_lieferant_wird_abgelehnt(welt, c):
    c.post("/api/datev/kreditoren", json={"name": "Friseurbedarf Nord GmbH"})
    vorher = _commits(welt)
    r = c.post("/api/datev/kreditoren", json={"name": "FRISEURBEDARF NORD"})
    assert r.status_code == 400
    assert "70001" in r.json()["fehler"]
    assert _commits(welt) == vorher


def test_aendern_behaelt_die_nummer(c):
    c.post("/api/datev/kreditoren", json={"name": "Wella"})
    r = c.post("/api/datev/kreditoren/70001",
               json={"name": "Wella Deutschland GmbH", "nummer": "79999"})
    assert r.status_code == 200, r.text
    k = r.json()["kreditor"]
    assert (k["nummer"], k["name"], k["aliase"]) == ("70001", "Wella Deutschland GmbH",
                                                     ["Wella"])
    assert c.post("/api/datev/kreditoren/70777", json={"name": "X"}).status_code == 404


def test_einstellung_schaltet_auf_einzeln(c):
    r = c.post("/api/datev/kreditoren/einstellung",
               json={"modus": "einzeln", "sammelkonto": "70000"})
    assert r.status_code == 200, r.text
    d = c.get("/api/datev/kreditoren").json()
    assert (d["modus"], d["sammelkonto"]) == ("einzeln", "70000")
    assert c.post("/api/datev/kreditoren/einstellung",
                  json={"modus": "alles"}).status_code == 400


# ————— Aus DATEV übernehmen: erst ansehen, dann übernehmen —————

def test_hereinlesen_zeigt_nur_und_schreibt_nichts(welt, c):
    vorher = _commits(welt)
    r = _hochladen(c, "/api/datev/kreditoren/lesen")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["art"] == "datev"
    assert [n["nummer"] for n in d["neu"]] == ["70001", "70002"]
    assert d["uebersprungen"] == 1
    assert _commits(welt) == vorher


def test_uebernehmen_traegt_die_liste_ein(welt, c):
    r = _hochladen(c, "/api/datev/kreditoren/uebernehmen")
    assert r.status_code == 200, r.text
    assert (r.json()["neu"], r.json()["geaendert"]) == (2, 0)
    d = c.get("/api/datev/kreditoren").json()
    assert [(k["nummer"], k["quelle"]) for k in d["eintraege"]] == [
        ("70001", "datev"), ("70002", "datev")]
    # Ein zweites Mal dieselbe Datei: nichts Neues, kein leerer Commit.
    vorher = _commits(welt)
    nochmal = _hochladen(c, "/api/datev/kreditoren/uebernehmen").json()
    assert (nochmal["neu"], nochmal["geaendert"]) == (0, 0)
    assert _commits(welt) == vorher


def test_eine_falsche_datei_sagt_warum(c):
    r = _hochladen(c, "/api/datev/kreditoren/lesen", b"Name;Ort\nWella;Darmstadt\n")
    assert r.status_code == 400
    assert "Kontonummer" in r.json()["fehler"]
    assert _hochladen(c, "/api/datev/kreditoren/lesen", b"x",
                      name="liste.pdf").status_code == 400


# ————— Aus den bisherigen Buchungen —————

@pytest.fixture()
def mit_historie(welt):
    import boxschreiber  # noqa: PLC0415
    boxschreiber.schreiben("historie/2025/stapel.csv", _alter_stapel([
        ("6815", "70001", "Friseurbedarf Nord RE 4711"),
        ("6815", "70001", "Friseurbedarf Nord"),
        *[("6815", "70099", f"Lieferant {n}") for n in "ABCDEF"],
    ]), "historie: 2025", "t")
    return welt


def test_bisherige_buchungen_schlagen_kreditoren_vor(mit_historie, c):
    d = c.get("/api/datev/kreditoren/aus-historie").json()
    assert [(v["nummer"], v["name"]) for v in d["vorschlaege"]] == [
        ("70001", "Friseurbedarf Nord")]
    assert [s["nummer"] for s in d["sammel"]] == ["70099"]
    r = c.post("/api/datev/kreditoren/aus-historie", json={})
    assert r.status_code == 200, r.text
    assert r.json()["neu"] == 1
    k = c.get("/api/datev/kreditoren").json()["eintraege"]
    assert [(x["nummer"], x["quelle"]) for x in k] == [("70001", "historie")]


# ————— Jeder Betrieb hat seine eigene Liste —————

def test_die_kanzlei_schreibt_in_die_box_des_mandanten(welt2, monkeypatch):
    monkeypatch.setattr(bx, "remote_aus_ref", lambda ref: str(bx.store_aus_ref(ref)))
    client = _login(welt2["bw"], welt2["kanzlei"])
    kopf = {"X-Mandant": str(welt2["nina_id"])}
    r = client.post("/api/datev/kreditoren", json={"name": "Salon-Lieferant"},
                    headers=kopf)
    assert r.status_code == 200, r.text
    nina = bx.store_aus_ref("inspektor/ws-nina/babu")
    berta = bx.store_aus_ref("inspektor/ws-berta/babu")
    pfad = "HEAD:stammdaten/kreditoren.json"
    assert subprocess.run(["git", "-C", str(nina), "show", pfad],
                          capture_output=True).returncode == 0
    assert subprocess.run(["git", "-C", str(berta), "show", pfad],
                          capture_output=True).returncode != 0
    assert client.get("/api/datev/kreditoren",
                      headers={"X-Mandant": str(welt2["berta_id"])}
                      ).json()["eintraege"] == []


# ————— K2: Kreditor am Beleg, im Stapel, im Befund —————

NORD = "20260714-101500-aaa001-friseurbedarf"
DELILA = "20260722-183000-aaa002-delila"
BUERO = "20260812-093000-aaa003-buero"


def _gegenkonten(c, monat="2026-07") -> dict:
    d = c.get("/api/datev/vorschau", params={"von": monat, "bis": monat}).json()
    return {z["quelle"]: z["gegenkonto"] for z in d["zeilen"] if z["art"] == "beleg"}


def _befund(c, monat="2026-07") -> dict:
    return c.get("/api/datev/vorschau", params={"von": monat, "bis": monat}).json()["befund"]


@pytest.fixture()
def einzeln(c):
    """Ein Betrieb mit „Ein Konto je Lieferant“ und zwei Kreditoren."""
    assert c.post("/api/datev/kreditoren", json={"name": "Friseurbedarf Nord"}).status_code == 200
    assert c.post("/api/datev/kreditoren", json={"name": "Delila"}).status_code == 200
    assert c.post("/api/datev/kreditoren/einstellung",
                  json={"modus": "einzeln"}).status_code == 200
    return c


def test_ohne_einzeln_bleibt_jeder_beleg_beim_sammelkonto(c):
    c.post("/api/datev/kreditoren", json={"name": "Friseurbedarf Nord"})
    assert set(_gegenkonten(c).values()) == {"70099"}
    assert _befund(c).get("sammelkonto_belege", []) == []


def test_der_lieferantenname_bringt_den_kreditor_in_den_stapel(einzeln):
    assert _gegenkonten(einzeln) == {NORD: "70001", DELILA: "70099"}


def test_zuordnen_mit_merken(welt, einzeln):
    r = einzeln.post("/api/datev/kreditoren/zuordnen",
                     json={"stamm": DELILA, "nummer": "70002", "merken": True})
    assert r.status_code == 200, r.text
    assert _gegenkonten(einzeln)[DELILA] == "70002"
    assert _letzte_nachricht(welt) == "kreditoren: Delila Hair GmbH → 70002"
    k = next(x for x in einzeln.get("/api/datev/kreditoren").json()["eintraege"]
             if x["nummer"] == "70002")
    assert k["aliase"] == ["Delila Hair GmbH"]
    datei = _datei(welt, f"review/{DELILA}.kreditor.json")
    assert (datei["nummer"], datei["von"]) == ("70002", "chef@0711.io")


def test_ausdruecklich_sammelkonto(einzeln):
    r = einzeln.post("/api/datev/kreditoren/zuordnen", json={"stamm": NORD, "nummer": None})
    assert r.status_code == 200, r.text
    assert _gegenkonten(einzeln)[NORD] == "70099"
    offen = einzeln.get("/api/datev/kreditoren/belege", params={"ohne": 1}).json()["belege"]
    assert NORD not in [b["stamm"] for b in offen]


def test_zuordnen_prueft_was_es_bekommt(einzeln):
    assert einzeln.post("/api/datev/kreditoren/zuordnen",
                        json={"stamm": NORD, "nummer": "70777"}).status_code == 400
    assert einzeln.post("/api/datev/kreditoren/zuordnen",
                        json={"stamm": "gibt-es-nicht", "nummer": "70001"}).status_code == 404
    einzeln.post("/api/datev/kreditoren/einstellung", json={"modus": "sammel"})
    r = einzeln.post("/api/datev/kreditoren/zuordnen", json={"stamm": NORD, "nummer": "70001"})
    assert r.status_code == 409


def test_offene_belege_mit_vorschlaegen(einzeln):
    d = einzeln.get("/api/datev/kreditoren/belege", params={"ohne": 1}).json()
    offen = {b["stamm"]: b for b in d["belege"]}
    assert set(offen) == {DELILA, BUERO}
    assert offen[DELILA]["vorschlaege"][0]["nummer"] == "70002"
    alle = einzeln.get("/api/datev/kreditoren/belege").json()["belege"]
    nord = next(b for b in alle if b["stamm"] == NORD)
    assert (nord["nummer"], nord["quelle"]) == ("70001", "name")


def test_der_befund_nennt_sammelkonto_und_neue_kreditoren(einzeln):
    b = _befund(einzeln)
    assert b["sammelkonto_belege"] == [DELILA]
    assert [k["nummer"] for k in b["kreditoren_neu"]] == ["70001"]
    assert "70001" not in b["unbenannte_konten"]


def test_uebergeben_haelt_das_gegenkonto_fest(welt, einzeln):
    r = einzeln.post("/api/datev/uebergeben", params={"von": "2026-07", "bis": "2026-07"})
    assert r.status_code == 200, r.text
    lauf = _datei(welt, "export/2026-07/stapel.json")["laeufe"][-1]
    assert lauf["gegenkonten"] == {NORD: "70001", DELILA: "70099"}
    # Danach ändert sich am übergebenen Beleg nichts mehr — weder durch
    # eine Zuordnung noch durch den Wechsel zurück aufs Sammelkonto.
    r = einzeln.post("/api/datev/kreditoren/zuordnen", json={"stamm": DELILA, "nummer": "70002"})
    assert r.status_code == 409
    einzeln.post("/api/datev/kreditoren/einstellung", json={"modus": "sammel"})
    assert _gegenkonten(einzeln) == {NORD: "70001", DELILA: "70099"}


def test_die_einzelansicht_zeigt_den_kreditor(welt, einzeln, monkeypatch):
    # Die DATEV-Testwelt kennt nur die Verwaltung; die Belegrouten brauchen
    # zusätzlich die Mitgliedschaft in der Box.
    monkeypatch.setattr(welt, "box_mitglied", lambda un, mandant_id=None: True)
    d = einzeln.get(f"/api/beleg/{NORD}").json()
    assert d["buchungssatz"]["gegenkonto"] == "70001"
    assert d["kreditor_wahl"]["nummer"] == "70001"
    assert d["kreditor_wahl"]["aenderbar"] is True
    assert {z["gegenkonto"] for z in d["stapelzeilen"]} == {"70001"}


def test_die_belegliste_der_app_bleibt_unberuehrt(welt, c, monkeypatch):
    monkeypatch.setattr(welt, "box_mitglied", lambda un, mandant_id=None: True)
    vorher = c.get("/api/belege").json()["belege"]
    c.post("/api/datev/kreditoren", json={"name": "Friseurbedarf Nord"})
    c.post("/api/datev/kreditoren/einstellung", json={"modus": "einzeln"})
    c.post("/api/datev/kreditoren/zuordnen", json={"stamm": DELILA, "nummer": "70001"})
    assert c.get("/api/belege").json()["belege"] == vorher


def test_die_zuordnung_geht_beim_loeschen_mit(welt):
    assert ".kreditor.json" in welt.BELEG_BEIAKTEN
