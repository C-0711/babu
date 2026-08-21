"""Der Monat läuft von selbst an — statt auf einen Knopfdruck zu warten.

Bisher war der Monatsabschluss eine Aufgabe: hingehen, Monat wählen,
rechnen lassen, freigeben. Jetzt ist er eine Bestätigung: am 3. liegt der
Vormonat gerechnet da, und babu sagt, was ihm noch fehlt.

Der Unterschied klingt klein und ist der ganze Punkt: aus „ich muss noch"
wird „ich schau kurz drüber".
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import monatslauf as ml  # noqa: E402

HEUTE = dt.date(2026, 9, 3)


def beleg(monat="2026-08", status="geprüft"):
    return {"monat": monat, "status": status}


# ————— Welcher Monat ist dran —————

def test_am_dritten_ist_der_vormonat_dran():
    assert ml.faelliger_monat(HEUTE) == "2026-08"


def test_vor_dem_dritten_ist_noch_nichts_faellig():
    """Am 1. sind noch Belege vom Vormonat unterwegs."""
    assert ml.faelliger_monat(dt.date(2026, 9, 1)) is None


def test_spaeter_im_monat_bleibt_der_vormonat_dran():
    assert ml.faelliger_monat(dt.date(2026, 9, 20)) == "2026-08"


def test_der_jahreswechsel_stimmt():
    assert ml.faelliger_monat(dt.date(2027, 1, 5)) == "2026-12"


# ————— Was noch fehlt —————

def test_ein_sauberer_monat_ist_bereit():
    stand = ml.stand("2026-08", belege=[beleg(), beleg()], fehlende_belege=[],
                     freigegeben=False, heute=HEUTE)
    assert stand["bereit"] is True
    assert stand["offen"] == []
    assert "kann raus" in stand["satz"]


def test_unklare_belege_halten_ihn_auf():
    stand = ml.stand("2026-08",
                     belege=[beleg(status="nachfrage"), beleg()],
                     fehlende_belege=[], freigegeben=False, heute=HEUTE)
    assert stand["bereit"] is False
    assert any("Beleg" in o["text"] for o in stand["offen"])
    assert stand["offen"][0]["anzahl"] == 1


def test_abbuchungen_ohne_beleg_halten_ihn_auf():
    stand = ml.stand("2026-08", belege=[beleg()],
                     fehlende_belege=[{"betrag": 141.0}], freigegeben=False,
                     heute=HEUTE)
    assert stand["bereit"] is False
    assert any("141" in o["text"].replace(",", ".") for o in stand["offen"])


def test_beides_wird_einzeln_genannt():
    stand = ml.stand("2026-08", belege=[beleg(status="erfasst")],
                     fehlende_belege=[{"betrag": 90.0}], freigegeben=False,
                     heute=HEUTE)
    assert len(stand["offen"]) == 2


# ————— Schon erledigt —————

def test_ein_freigegebener_monat_ist_fertig():
    stand = ml.stand("2026-08", belege=[beleg()], fehlende_belege=[],
                     freigegeben=True, heute=HEUTE)
    assert stand["stand"] == "freigegeben"
    assert stand["bereit"] is False
    assert "übergeben" in stand["satz"]


def test_ein_noch_laufender_monat_wird_nicht_gedraengt():
    """Der laufende Monat ist nicht fällig — babu drängelt nicht."""
    stand = ml.stand("2026-09", belege=[beleg("2026-09", "erfasst")],
                     fehlende_belege=[], freigegeben=False, heute=HEUTE)
    assert stand["stand"] == "laeuft"
    assert stand["bereit"] is False


# ————— Der Satz, den die Nutzerin liest —————

def test_der_satz_kommt_ohne_technik_aus():
    for stand in (ml.stand("2026-08", [beleg()], [], False, HEUTE),
                  ml.stand("2026-08", [beleg("2026-08", "nachfrage")], [], False, HEUTE),
                  ml.stand("2026-08", [beleg()], [], True, HEUTE),
                  ml.stand("2026-09", [], [], False, HEUTE)):
        satz = stand["satz"]
        assert satz and satz[0].isupper()
        for wort in ("UStVA", "Status", "API", "JSON", "Commit"):
            assert wort not in satz


def test_der_monat_heisst_wie_im_kalender():
    assert "August" in ml.stand("2026-08", [beleg()], [], False, HEUTE)["monatsname"]
    assert "Dezember" in ml.stand("2026-12", [], [], False,
                                  dt.date(2027, 1, 5))["monatsname"]


# ————— Am Server —————

def test_der_faellige_monat_kommt_von_selbst(tmp_path, monkeypatch):
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
                           dokumente=[], zeiten={}, oid_cache={}, rechnungen={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200

    d = client.get("/api/monatslauf").json()
    assert "faellig" in d
    assert d["satz"] and d["satz"][0].isupper()
    if d["faellig"]:
        assert d["monatsname"] in ml.MONATE
        assert d["stand"] in ("bereit", "wartet", "freigegeben", "laeuft")
