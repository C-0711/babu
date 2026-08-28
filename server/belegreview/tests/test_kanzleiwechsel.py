"""Der Brief an die bisherige Kanzlei — Daten anfordern, Mandat beenden.

Die Landingpage verspricht die Vorlage seit Langem („Vorlage bekommst du
von uns"); hier wird sie eingelöst. Geprüft wird vor allem, was der Brief
NICHT tut: keine Paragrafen behaupten, keine Frist erfinden, und nicht von
selbst losschicken.
"""
import io
import subprocess
import sys
import time
from pathlib import Path

import kanzleiwechsel as kw
import pytest
import vordrucke

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

from test_mehrseiten_buendel import _im_stand, welt  # noqa: F401,E402

BETRIEB = {"betrieb_name": "Salon Nina", "anschrift": "Hauptstraße 5, Stuttgart",
           "steuernummer": "93815/28461", "inhaberin": "Nina Weber"}
KANZLEI = {"name": "Kanzlei Sommer & Partner", "anschrift": "Marktplatz 1",
           "mandantennummer": "44821", "email": "post@sommer-partner.de"}
JETZT = time.strptime("2026-08-28", "%Y-%m-%d")


# ————— Was im Brief steht —————

def test_der_brief_nennt_beide_seiten_und_die_kennungen():
    b = kw.brief(BETRIEB, KANZLEI, jetzt=JETZT)
    t = b["text"]
    assert "Salon Nina" in t and "Kanzlei Sommer & Partner" in t
    assert "Steuernummer 93815/28461" in t
    assert "Mandantennummer 44821" in t
    assert t.rstrip().endswith("Nina Weber")
    assert "28.08.2026" in t


def test_die_liste_ist_die_der_daten_die_babu_lesen_kann():
    b = kw.brief(BETRIEB, KANZLEI, jetzt=JETZT)
    t = b["text"]
    for pflicht in ("Buchungsstapel im DATEV-Format", "Sachkonten-Beschriftungen",
                    "Summen- und Saldenlisten", "Anlagenverzeichnis",
                    "Offene-Posten-Listen", "Saldenvorträge"):
        assert pflicht in t, pflicht
    # Und jeder Punkt sagt, wozu — das macht die Bitte nachvollziehbar.
    assert "damit die Abschreibungen ohne Bruch weiterlaufen" in t


def test_lohn_wird_nur_angefordert_wo_lohn_lief():
    ohne = kw.brief(BETRIEB, KANZLEI, mit_lohn=False, jetzt=JETZT)["text"]
    mit = kw.brief(BETRIEB, KANZLEI, mit_lohn=True, jetzt=JETZT)["text"]
    assert "Lohnkonten" not in ohne
    assert "Lohnkonten" in mit


def test_kuendigung_bittet_um_bestaetigung_statt_eine_frist_zu_erfinden():
    """Die Kündigungsfrist steht im Mandatsvertrag — den kennt babu nicht."""
    b = kw.brief(BETRIEB, KANZLEI, kuendigen=True, jetzt=JETZT)
    t = b["text"]
    assert "zum nächstmöglichen Zeitpunkt" in t
    assert "wann das Mandat endet" in t
    assert "Kündigungsfrist" not in t, "keine Frist behaupten"
    assert b["kuendigt"] is True


def test_ohne_kuendigung_werden_nur_daten_erbeten():
    b = kw.brief(BETRIEB, KANZLEI, kuendigen=False, jetzt=JETZT)
    assert b["kuendigt"] is False
    assert "kündige" not in b["text"]
    assert "Buchungsstapel" in b["text"]
    assert b["betreff"] == "Herausgabe meiner Buchführungsdaten"


def test_der_brief_behauptet_keine_paragrafen():
    """babus eigene Regel: nie Zahlen, Paragrafen oder Fristen erfinden.
    Im Kompendium steht nichts zum Herausgabeanspruch — also steht auch
    im Brief nichts davon."""
    t = kw.brief(BETRIEB, KANZLEI, jetzt=JETZT)["text"]
    assert "§" not in t
    for wort in ("StBerG", "BGB", "DSGVO", "Abs."):
        assert wort not in t, wort


def test_der_brief_bleibt_hoeflich_und_klaert_offene_rechnungen():
    t = kw.brief(BETRIEB, KANZLEI, jetzt=JETZT)["text"]
    assert "Offene Rechnungen begleiche ich" in t
    assert "bedanke ich mich" in t
    # Kein Ton, der eine Zusammenarbeit unnötig verbrennt.
    for wort in ("unverzüglich", "andernfalls", "Rechtsanwalt", "Frist setze"):
        assert wort not in t, wort


def test_die_frist_ist_ein_vorschlag_kein_ultimatum():
    b = kw.brief(BETRIEB, KANZLEI, frist_tage=14, jetzt=JETZT)
    assert b["frist"] == "11.09.2026"
    assert "schlage ich den 11.09.2026 vor" in b["text"]
    assert "richte mich danach" in b["text"]


def test_der_hinweis_sagt_dass_es_eine_vorlage_ist():
    b = kw.brief(BETRIEB, KANZLEI, jetzt=JETZT)
    assert "kein Rechtsrat" in b["hinweis"]
    assert "Vertrag" in b["hinweis"]


def test_ohne_kanzleinamen_bleibt_ein_platzhalter_stehen():
    b = kw.brief(BETRIEB, {}, jetzt=JETZT)
    assert "Ihre Kanzlei" in b["text"]


# ————— Als Blatt —————

def _pdf_text(daten: bytes) -> str:
    import pypdfium2 as pdfium
    d = pdfium.PdfDocument(io.BytesIO(daten))
    text = "\n".join(d[i].get_textpage().get_text_bounded() for i in range(len(d)))
    d.close()
    return text


def test_der_brief_wird_ein_lesbares_blatt():
    b = kw.brief(BETRIEB, KANZLEI, jetzt=JETZT)
    pdf = vordrucke.brief_pdf(b, BETRIEB)
    assert pdf.startswith(b"%PDF")
    t = " ".join(_pdf_text(pdf).split())
    assert "Kanzlei Sommer & Partner" in t
    assert "Buchungsstapel im DATEV-Format" in t
    assert "Nina Weber" in t
    assert "kein Rechtsrat" in t


# ————— Die Strecke über den Server —————

@pytest.fixture()
def wechselwelt(welt, monkeypatch):
    bw, bare = welt
    monkeypatch.setattr(bw, "rolle", lambda un: "inhaberin")
    monkeypatch.setattr(bw, "db_einstellungen", lambda un: dict(BETRIEB, name="Nina Weber"))
    monkeypatch.setattr(bw, "team_liste", lambda un, nur_aktive=True: [])
    from fastapi.testclient import TestClient
    return bw, bare, TestClient(bw.app, base_url="https://testserver")


def test_die_route_legt_brief_und_text_ab(wechselwelt):
    _, bare, c = wechselwelt
    r = c.post("/api/kanzleiwechsel", json={"kanzlei": KANZLEI})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["betreff"].startswith("Beendigung des Mandats")
    assert "Buchungsstapel" in d["text"]
    dateien = _im_stand(bare)
    assert any(p.startswith("dokumente/kanzleiwechsel/") and p.endswith(".pdf")
               for p in dateien), dateien
    assert any(p.endswith(".txt") for p in dateien)


def test_babu_verschickt_den_brief_nicht_von_selbst(wechselwelt):
    """Eine Kündigung geht an einen Dritten und hat Folgen — sie gehört
    gelesen, bevor sie rausgeht."""
    _, _, c = wechselwelt
    d = c.post("/api/kanzleiwechsel", json={"kanzlei": KANZLEI}).json()
    assert d["versendet"] is False


def test_ohne_kanzleinamen_fragt_die_route_nach(wechselwelt):
    _, bare, c = wechselwelt
    r = c.post("/api/kanzleiwechsel", json={"kanzlei": {}})
    assert r.status_code == 400
    assert "Wie heißt die Kanzlei" in r.json()["fehler"]
    assert not any("kanzleiwechsel" in p for p in _im_stand(bare))


def test_mit_team_wird_auch_der_lohn_angefordert(wechselwelt, monkeypatch):
    bw, _, c = wechselwelt
    monkeypatch.setattr(bw, "team_liste",
                        lambda un, nur_aktive=True: [{"name": "Meier"}])
    d = c.post("/api/kanzleiwechsel", json={"kanzlei": KANZLEI}).json()
    assert "Lohnkonten" in d["text"]
