"""Die Salonprüfung im Lauf: Ernte setzt Felder, Bericht landet in der Box.

Das reine Rechnen prüft `test_salonpruefung.py`. Hier geht es um die
Verdrahtung, und die hat genau zwei Zusagen, die nicht brechen dürfen:

Ein Feld, das schon ausgefüllt ist, wird **nie** überschrieben — sonst
ersetzt eine alte Unterlage stillschweigend etwas, das jemand von Hand
eingetragen hat. Und der Bericht liegt in der Belegbox, nicht nur im
Arbeitsspeicher, damit er einen Neustart übersteht.
"""
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "README.md").write_text("box")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "s"],
                   check=True, capture_output=True)
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

    sys.path.insert(0, str(HIER.parent))
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
    monkeypatch.setattr(babu_web, "ERLAUBT", set())
    babu_web._REG_ZULETZT.clear()
    return babu_web, bare


def konto(bw, email="nina@0711.io"):
    c = TestClient(bw.app, base_url="https://testserver")
    bw._REG_ZULETZT.clear()
    c.post("/api/signup", json={"salon": "Salon Nina", "email": email,
                                "passwort": "passwort-lang"})
    with bw._DB_LOCK, bw._db() as v:
        v.execute("UPDATE nutzer SET box=1 WHERE email=?", (email,))
    return c


BESCHEID = """
Finanzamt Stuttgart-Mitte
Bescheid für 2025 über Einkommensteuer
Steuernummer 93815/12345
Salon SupremeBeauty
Hauptstraße 3
70173 Stuttgart
IBAN DE02 1203 0000 0000 2020 51
"""

DOKUMENTE = [{"datei": "bescheid.pdf", "art": "bescheid", "text": BESCHEID}]


def status_leer():
    return {"stand": "liest", "dokumente": [], "felder": [], "vorschlaege": []}


# ————— Die Ernte setzt Felder —————

def test_leere_felder_werden_gesetzt(welt):
    bw, _ = welt
    konto(bw)
    st = status_leer()
    bw._stammdaten_ernten("nina@0711.io", st, DOKUMENTE, 2025, {})
    e = bw.db_einstellungen("nina@0711.io")
    assert e["steuernummer"] == "93815/12345"
    # Anschrift und IBAN kommen NICHT aus einem Bescheid — dort stehen die
    # der Behörde. Siehe die Positivliste je Art.
    assert "betrieb_plz" not in e
    assert "iban" not in e


def test_ein_gesetztes_feld_wird_nie_ueberschrieben(welt):
    """Die wichtigste Zusage: was jemand eingetragen hat, bleibt stehen."""
    bw, _ = welt
    konto(bw)
    bw.db_einstellung_setzen("nina@0711.io", "steuernummer", "11/111/11111")
    st = status_leer()
    bw._stammdaten_ernten("nina@0711.io", st,
                          DOKUMENTE, 2025, bw.db_einstellungen("nina@0711.io"))
    assert bw.db_einstellungen("nina@0711.io")["steuernummer"] == "11/111/11111"


def test_stattdessen_wird_vorgeschlagen(welt):
    bw, _ = welt
    konto(bw)
    bw.db_einstellung_setzen("nina@0711.io", "steuernummer", "11/111/11111")
    st = status_leer()
    bw._stammdaten_ernten("nina@0711.io", st,
                          DOKUMENTE, 2025, bw.db_einstellungen("nina@0711.io"))
    vor = [v for v in st["vorschlaege"] if v["schluessel"] == "steuernummer"]
    assert vor and vor[0]["neu"] == "93815/12345"
    assert vor[0]["quelle"] == "bescheid.pdf"


def test_unsichere_funde_werden_nur_vorgeschlagen(welt):
    """Widersprechen sich zwei Unterlagen, wird nichts still gesetzt."""
    bw, _ = welt
    konto(bw)
    st = status_leer()
    bw._stammdaten_ernten("nina@0711.io", st, [
        {"datei": "a.pdf", "art": "bescheid", "text": "Steuernummer 93815/12345"},
        {"datei": "b.pdf", "art": "euer", "text": "Steuernummer 11/111/11111"},
    ], 2025, {})
    assert "steuernummer" not in bw.db_einstellungen("nina@0711.io")
    assert any(v["schluessel"] == "steuernummer" for v in st["vorschlaege"])


def test_jedes_geerntete_feld_steht_im_status(welt):
    bw, _ = welt
    konto(bw)
    st = status_leer()
    bw._stammdaten_ernten("nina@0711.io", st, DOKUMENTE, 2025, {})
    schluessel = {f["schluessel"] for f in st["felder"]}
    assert "steuernummer" in schluessel and "finanzamt" in schluessel
    for f in st["felder"]:
        assert f["quelle"] == "bescheid.pdf"
        assert f["regel"]


def test_ohne_unterlagen_passiert_nichts(welt):
    bw, _ = welt
    konto(bw)
    st = status_leer()
    vorher = bw.db_einstellungen("nina@0711.io")   # Signup legt schon welche an
    bw._stammdaten_ernten("nina@0711.io", st, [], 2025, {})
    assert st["felder"] == []
    assert bw.db_einstellungen("nina@0711.io") == vorher


def test_eine_kaputte_ernte_kippt_den_lauf_nicht(welt, monkeypatch):
    """Ein Fehler in der Ernte darf die Kennzahlen nicht mitreißen."""
    import salonpruefung
    bw, _ = welt
    konto(bw)
    monkeypatch.setattr(salonpruefung, "felder_ernten",
                        lambda d: (_ for _ in ()).throw(RuntimeError("kaputt")))
    st = status_leer()
    bw._stammdaten_ernten("nina@0711.io", st, DOKUMENTE, 2025, {})
    assert st["felder"] == []


# ————— Der Bericht —————

def in_der_box(bare):
    r = subprocess.run(["git", "-C", str(bare), "ls-tree", "-r", "--name-only", "HEAD"],
                       capture_output=True, text=True, check=True)
    return set(r.stdout.split())


def test_der_bericht_landet_in_der_box(welt):
    bw, bare = welt
    konto(bw)
    st = status_leer()
    bw._bericht_schreiben("nina@0711.io", 2025, st, DOKUMENTE,
                          [{"datei": "bescheid.pdf", "art": "bescheid"}],
                          {"zahlen": {"umsatz": 128000.0}, "unsicher": []})
    assert "abschluss/2025/bericht.md" in in_der_box(bare)
    text = bw.git_show("abschluss/2025/bericht.md").decode()
    assert "93815/12345" in text and "bescheid.pdf" in text


def test_der_bericht_ist_abrufbar(welt):
    bw, bare = welt
    c = konto(bw)
    bw._bericht_schreiben("nina@0711.io", 2025, status_leer(), DOKUMENTE,
                          [{"datei": "bescheid.pdf", "art": "bescheid"}],
                          {"zahlen": {}, "unsicher": []})
    r = c.get("/api/salon-check/bericht?jahr=2025")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/markdown")
    assert "Steuernummer" in r.text


def test_ohne_bericht_sagt_die_route_was_zu_tun_ist(welt):
    bw, _ = welt
    c = konto(bw)
    r = c.get("/api/salon-check/bericht?jahr=2025")
    assert r.status_code == 404
    assert "Unterlagen hoch" in r.json()["fehler"]


def test_der_bericht_braucht_eine_freischaltung(welt):
    bw, _ = welt
    bw._bericht_schreiben("nina@0711.io", 2025, status_leer(), DOKUMENTE,
                          [{"datei": "bescheid.pdf", "art": "bescheid"}],
                          {"zahlen": {}, "unsicher": []})
    c = konto(bw, "fremd@x.de")
    with bw._DB_LOCK, bw._db() as v:
        v.execute("UPDATE nutzer SET box=0 WHERE email=?", ("fremd@x.de",))
    assert c.get("/api/salon-check/bericht?jahr=2025").status_code == 403


def test_unsichere_kennzahlen_stehen_unter_offen(welt):
    bw, _ = welt
    konto(bw)
    bw._bericht_schreiben("nina@0711.io", 2025, status_leer(), DOKUMENTE,
                          [{"datei": "bescheid.pdf", "art": "bescheid"}],
                          {"zahlen": {}, "unsicher": ["gewinn"]})
    text = bw.git_show("abschluss/2025/bericht.md").decode()
    assert "Was noch fehlt" in text and "gewinn" in text


def test_ein_kaputter_bericht_kippt_den_lauf_nicht(welt, monkeypatch):
    import salonpruefung
    bw, _ = welt
    konto(bw)
    monkeypatch.setattr(salonpruefung, "bericht",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("kaputt")))
    st = status_leer()
    bw._bericht_schreiben("nina@0711.io", 2025, st, DOKUMENTE, [], {})
    assert st.get("bericht") is None


def test_der_bericht_nennt_die_art_in_klartext(welt):
    """„Erkannt als: behoerde" ist Vokabular. Beide Vokabulare müssen im
    Bericht als Klartext ankommen."""
    bw, _ = welt
    konto(bw)
    bw._bericht_schreiben("nina@0711.io", 2025, status_leer(), DOKUMENTE, [
        {"datei": "a.pdf", "art": "behoerde"},
        {"datei": "b.pdf", "art": "kontoauszug"},
        {"datei": "c.pdf", "art": "euer"},
    ], {"zahlen": {}, "unsicher": []})
    text = bw.git_show("abschluss/2025/bericht.md").decode()
    assert "Post vom Amt" in text
    assert "Kontoauszug" in text
    assert "Gewinnrechnung" in text
    assert "behoerde" not in text


def test_ein_bekannter_ablageort_wird_uebernommen(welt):
    """Unterlagen, die schon einsortiert sind, liegen nicht unter
    abschluss/<jahr> — dann darf der Bericht das nicht behaupten."""
    bw, _ = welt
    konto(bw)
    bw._bericht_schreiben("nina@0711.io", 2025, status_leer(), DOKUMENTE,
                          [{"datei": "a.pdf", "art": "kontoauszug",
                            "ablage": "auszuege/2026-01"}],
                          {"zahlen": {}, "unsicher": []})
    text = bw.git_show("abschluss/2025/bericht.md").decode()
    assert "auszuege/2026-01" in text
