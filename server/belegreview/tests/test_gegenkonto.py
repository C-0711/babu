"""Eine Regel fürs Gegenkonto — und Korrekturen, die überall ankommen (K0).

Plan Kanzleiansicht, Schritt K0 (03.10.2026). Die Regel, gegen welches
Konto ein Beleg läuft, stand zweimal im Haus: in `extf.buchungszeilen`
(die Stapeldatei) und in `babu_web.datev_buchungssatz` (die Anzeige). Die
Anzeige kannte den Debitor-Zweig für Ausgangsrechnungen nicht und zeigte
70099, wo im Stapel 1200 steht. Jetzt gibt es `extf.gegenkonto`, und beide
fragen dort.

Dazu zwei Lücken bei Kanzlei-Korrekturen: ein korrigierter Buchungstext
ging verloren, wenn das Review `vlm: null` trägt, und die Einzelansicht
zeigte die Korrektur gar nicht.
"""
import json
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import extf  # noqa: E402
from test_schreiben import GOLDEN, STAMM, welt  # noqa: F401,E402


def _review(**felder) -> dict:
    r = json.loads(GOLDEN.read_text())
    r["felder"] = dict(r["felder"], **felder)
    return r


def _ausgang(**felder) -> dict:
    r = _review(**felder)
    r["felder"]["dokumentklasse"] = "ausgangsrechnung"
    r["einschaetzung"] = dict(r["einschaetzung"], konto_skr04="4400",
                              konto="4400", kontenrahmen="SKR04")
    return r


# ————— Die Regel —————

def test_unbar_bezahlt_laeuft_ueber_das_sammelkonto():
    assert extf.gegenkonto(_review(zahlungsart="karte")) == extf.GEGENKONTO


def test_bar_bezahlt_laeuft_gegen_die_kasse():
    assert extf.gegenkonto(_review(zahlungsart="bar")) == extf.KASSE


def test_ausgangsrechnung_laeuft_gegen_den_debitor():
    assert extf.gegenkonto(_ausgang(zahlungsart="ueberweisung")) == extf.DEBITOR["SKR04"]


def test_bar_bezahlte_ausgangsrechnung_laeuft_gegen_die_kasse():
    assert extf.gegenkonto(_ausgang(zahlungsart="bar")) == extf.KASSE


def test_ein_kreditor_ersetzt_das_sammelkonto():
    assert extf.gegenkonto(_review(zahlungsart="karte"), kreditor="70123") == "70123"


def test_bar_schlaegt_den_kreditor():
    """Bar bezahlt ist bezahlt — die Kasse hat das Geld gegeben, nicht der
    offene Posten beim Lieferanten (Plan, offener Punkt 4)."""
    assert extf.gegenkonto(_review(zahlungsart="bar"), kreditor="70123") == extf.KASSE


def test_eine_ausgangsrechnung_kennt_keinen_kreditor():
    assert extf.gegenkonto(_ausgang(zahlungsart="ueberweisung"),
                           kreditor="70123") == extf.DEBITOR["SKR04"]


def test_das_sammelkonto_ist_einstellbar():
    assert extf.gegenkonto(_review(zahlungsart="karte"), sammelkonto="70000") == "70000"


def test_stapel_und_anzeige_nennen_dasselbe_gegenkonto():
    """Der Fehler, gegen den K0 anschreibt: die Anzeige sagte 70099, die
    Stapeldatei 1200."""
    import babu_web  # noqa: PLC0415
    r = _ausgang(zahlungsart="ueberweisung")
    satz = babu_web.datev_buchungssatz(r)
    zeilen = extf.buchungszeilen(r)
    assert zeilen, "Ausgangsrechnung ohne Stapelzeile"
    assert {z["gegenkonto"] for z in zeilen} == {satz["gegenkonto"]}
    assert satz["gegenkonto"] == extf.DEBITOR["SKR04"]


def test_ohne_alles_bleibt_der_weingaertle_satz_wie_er_war():
    """Golden-Vertrag mit der App: der Weingärtle-Bon (Karte) bleibt bei 70099."""
    import babu_web  # noqa: PLC0415
    assert babu_web.datev_buchungssatz(_review())["gegenkonto"] == extf.GEGENKONTO


# ————— Korrekturen kommen an —————

def _bewirtung_beantworten(client) -> None:
    r = client.post(f"/api/bewirtung/{STAMM}",
                    json={"anlass": "Team-Essen", "teilnehmer": ["Nicole"]})
    assert r.status_code == 200, r.text


def test_korrigierter_buchungstext_kommt_auch_ohne_vlm_in_den_stapel(welt):
    client, _ = welt
    import boxschreiber  # noqa: PLC0415
    r = json.loads(GOLDEN.read_text())
    r = {k: v for k, v in r.items() if k not in ("audit", "buchungssatz")}
    r["vlm"] = None
    boxschreiber.schreiben(f"review/{STAMM}.json",
                           json.dumps(r, ensure_ascii=False).encode(),
                           "review: ohne vlm", "t")
    _bewirtung_beantworten(client)
    assert client.post(f"/api/korrektur/{STAMM}",
                       json={"buchungstext": "Team-Essen Weingaertle"}).status_code == 200
    stapel = client.get("/api/export/2026-08.csv").content.decode("cp1252")
    assert "Team-Essen Weingaertle" in stapel


def test_die_einzelansicht_zeigt_die_korrektur(welt):
    client, _ = welt
    assert client.post(f"/api/korrektur/{STAMM}",
                       json={"konto_skr04": "6643", "steuerschluessel": "9",
                             "buchungstext": "Aufmerksamkeit Team"}).status_code == 200
    d = client.get(f"/api/beleg/{STAMM}").json()
    assert d["einschaetzung"]["konto_skr04"] == "6643"
    assert d["einschaetzung"]["steuerschluessel"] == "9"
    assert d["buchungssatz"]["konto"] == "6643"
    assert d["buchungssatz"]["buchungstext"] == "Aufmerksamkeit Team"
    assert d["korrigiert"] is True
