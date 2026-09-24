"""Portale: je Branche eine Kopie von babu — und Friseur bleibt, wie es war.

Seit dem 24.09.2026 stehen die Texte, die ans Modell gehen, nicht mehr im
Code der Dienste, sondern im Portal des Betriebs (`portale/`). Für Friseur
hat sich dabei kein Byte geändert. Die beiden Golden-Dateien sind VOR dem
Umzug aus dem damaligen Code aufgezeichnet worden; wer sie anfassen muss,
hat einen Text verändert statt verschoben.
"""
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import gemma_buchung  # noqa: E402
import kompendium  # noqa: E402
import portale  # noqa: E402

GOLDEN = HIER / "golden"


@pytest.fixture()
def festes_wissen(monkeypatch):
    """Das Kompendium liegt nur auf der H200V — für den Vergleich ein
    fester Platzhalter, derselbe wie bei der Aufzeichnung."""
    monkeypatch.setattr(kompendium, "kontierungswissen",
                        lambda: "KONTIERUNGSWISSEN-PLATZHALTER")
    monkeypatch.setattr(kompendium, "grundwissen",
                        lambda: "GRUNDWISSEN-PLATZHALTER")


def test_jedes_portal_ist_vollstaendig():
    assert portale.pruefen() == []


def test_ohne_angabe_und_bei_unsinn_ist_es_friseur():
    for s in (None, "", "  ", "xyz", "Friseur ", "FRISEUR"):
        assert portale.hole(s).SCHLUESSEL == "friseur"
    assert portale.kennt("friseur") and not portale.kennt("xyz")
    assert not portale.kennt(None)


def test_der_buchungs_vorspann_ist_byte_gleich_mit_dem_von_vor_dem_umzug(festes_wissen):
    e = {"betrieb_name": "Salon Nina", "kleinunternehmer": "Nein"}
    ist = gemma_buchung.system_text(gemma_buchung.profil_text(e), "SKR04")
    assert ist == (GOLDEN / "vorspann_friseur.txt").read_text(encoding="utf-8")


def test_ausdrueckliches_friseur_ist_dasselbe_wie_keine_angabe(festes_wissen):
    ohne = {"betrieb_name": "Salon Nina", "kleinunternehmer": "Nein"}
    mit = dict(ohne, portal="friseur")
    assert gemma_buchung.profil_text(mit) == gemma_buchung.profil_text(ohne)
    assert (gemma_buchung.system_text(gemma_buchung.profil_text(mit), "SKR04",
                                      portal="friseur")
            == gemma_buchung.system_text(gemma_buchung.profil_text(ohne), "SKR04"))


def test_ein_portal_hinweis_ersetzt_nur_den_text_nie_das_konto():
    """Der Katalog bleibt der des Kontenrahmens: Codes, Reihenfolge und die
    Kategorien, die ein Konto haben. Das Portal darf nur den Hinweis ändern."""
    normal = gemma_buchung.katalog_text("SKR04")
    anders = gemma_buchung.katalog_text("SKR04", hinweise={"werkzeug": "ANDERS"})
    zeilen_n, zeilen_a = normal.splitlines(), anders.splitlines()
    assert len(zeilen_n) == len(zeilen_a)
    assert [z.split(":")[0] for z in zeilen_n] == [z.split(":")[0] for z in zeilen_a]
    assert "  werkzeug: Werkzeug und Kleingeräte — ANDERS" in zeilen_a


def test_der_chat_vorspann_ist_byte_gleich_mit_dem_von_vor_dem_umzug(festes_wissen, tmp_path, monkeypatch):
    import babu_web
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".g")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "p.db")
    monkeypatch.setattr(babu_web, "wer_token",
                        lambda t: "christoph0711.io" if t == "test-pat" else None)
    gesagt = []

    class Antwort:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(babu_web.requests, "post",
                        lambda url, json=None, **kw: (gesagt.append(json), Antwort())[1])
    monkeypatch.setattr(babu_web, "_welt_fuer", lambda un: {
        "einstellungen": {"betrieb_name": "Salon Nina"}, "belege": [],
        "kassenblaetter": [], "vertraege": [], "rechnungen": [], "team": [],
        "fristen": [], "zahlen": {}, "dokumente": []})
    monkeypatch.setattr(babu_web, "_recherche", lambda frage: "")
    babu_web._LOGIN_VERSUCHE.clear()
    from fastapi.testclient import TestClient
    c = TestClient(babu_web.app, base_url="https://testserver")
    assert c.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    assert c.post("/chat", json={"frage": "Was ist eine Kleinunternehmerin?"}).status_code == 200
    system = gesagt[-1]["messages"][0]["content"]
    assert system == (GOLDEN / "chat_vorspann_friseur.txt").read_text(encoding="utf-8")


# ————— Barber: die erste Kopie —————

def test_barber_ist_eine_vollstaendige_kopie():
    b = portale.hole("barber")
    assert b.SCHLUESSEL == "barber" and portale.kennt("barber")
    assert b.KOMPENDIUM[0] == "kompendium"      # erbt das neutrale Wissen
    assert b.KOMPENDIUM[-1] == "kompendium-barber"
    # Jeder Hinweis betrifft eine Kategorie, die es im Katalog gibt.
    import kontierung
    assert set(b.KATEGORIE_HINWEISE) <= set(kontierung.KATEGORIEN)


def test_barber_bucht_mit_eigenem_vorspann_und_denselben_konten(festes_wissen):
    e = {"betrieb_name": "Moe's Barbershop", "kleinunternehmer": "Nein", "portal": "barber"}
    profil = gemma_buchung.profil_text(e)
    assert profil.startswith("Barbershop „Moe's Barbershop“")
    b = gemma_buchung.system_text(profil, "SKR04", portal="barber")
    f = gemma_buchung.system_text(gemma_buchung.profil_text(
        {"betrieb_name": "Salon Nina", "kleinunternehmer": "Nein"}), "SKR04")
    assert b != f                                   # zwei Portale, zwei Vorspänne
    assert b.startswith("Du bist die Buchhaltung eines Barbershops")
    assert "Rasiermesser" in b and "Extensions" not in b
    # Codes und Reihenfolge des Katalogs sind in beiden Portalen gleich.
    codes = lambda t: [z.split(":")[0].strip() for z in t.splitlines() if z.startswith("  ") and ":" in z]
    kat = lambda t: t.split("KATEGORIEN")[1].split("\n\n")[0]
    assert codes(kat(b)) == codes(kat(f))
    # Der Barber-Vorspann ist in sich stabil (Prefix-Cache).
    assert b == gemma_buchung.system_text(profil, "SKR04", portal="barber")


def test_portal_und_sprache_werden_geprueft_und_gespeichert(tmp_path, monkeypatch):
    import babu_web
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".g")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "p.db")
    monkeypatch.setattr(babu_web, "wer_token",
                        lambda t: "christoph0711.io" if t == "test-pat" else None)
    babu_web._LOGIN_VERSUCHE.clear()
    from fastapi.testclient import TestClient
    c = TestClient(babu_web.app, base_url="https://testserver")
    assert c.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    assert c.post("/api/einstellungen", json={"portal": "maler"}).status_code == 400
    assert c.post("/api/einstellungen", json={"sprache": "fr"}).status_code == 400
    r = c.post("/api/einstellungen", json={"portal": " Barber ", "sprache": "TR"})
    assert r.status_code == 200, r.text
    e = babu_web.db_einstellungen("christoph0711.io")
    assert e["portal"] == "barber" and e["sprache"] == "tr"
