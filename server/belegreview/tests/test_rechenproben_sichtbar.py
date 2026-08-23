"""Die Rechenproben müssen zu sehen sein — im Protokoll und im Portal.

Seit dem 23.08.2026 rechnet sich jeder Beleg selbst nach (Einzelposten,
Netto + Steuer, Steuersatz, Bargeld). Das war der eigentliche Fund: die alte
Summenprobe bestätigte sich selbst — war nur ein Betrag lesbar, rechnete die
Deutung Netto und Steuer aus dem Brutto zurück und verglich das Ergebnis
danach mit seiner eigenen Eingabe. Ein verlesenes 90,00 statt 40,00 lief mit
grünem Haken durch.

Die Proben stimmen jetzt. Sehen konnte Nina sie trotzdem kaum: im Protokoll
liefen sie zwischen den Notizen mit, und über die Schnittstelle kam nur das
anonyme „Summenprobe nicht bestanden" — ohne zu sagen, WELCHE Probe nicht
aufging und mit welchen Zahlen.

Hier steht, was dagegen hilft.
"""
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

from belegdeutung import Kasten, deuten  # noqa: E402
from leseprotokoll import protokoll  # noqa: E402

GOLDEN = HIER / "golden" / "review_weingaertle.json"
PORTAL = (HIER.parent / "portal.html").read_text()
STAMM = "20260812-225200-c781d6-beleg_2026-07-21_friseurbedarf_22bf8b36"


def k(text, x0, y0, breite=None, hoehe=20, konf=0.97):
    breite = breite if breite is not None else len(text) * hoehe * 0.55
    return Kasten(text, konf, x0, y0, x0 + breite, y0 + hoehe)


def rechts(text, kante, y, hoehe=20, konf=0.97):
    breite = len(text) * hoehe * 0.55
    return Kasten(text, konf, kante - breite, y, kante, y + hoehe)


@pytest.fixture
def verlesener_bon():
    """Posten über 33,61 € netto, als Endbetrag steht 90,00 € — genau der
    Fall, den nur die Einzelpostenprobe fängt."""
    return [
        k("FRISEURBEDARF SÜDWEST GMBH", 60, 30, hoehe=30),
        k("1 Coloration 60 ml", 60, 386, hoehe=15), rechts("21,85", 520, 386, hoehe=15),
        k("2 Entwickler 1 L", 60, 408, hoehe=15), rechts("11,76", 520, 408, hoehe=15),
        k("Nettosumme", 60, 448, hoehe=15), rechts("33,61", 520, 448, hoehe=15),
        k("zzgl. USt 19 %", 60, 470, hoehe=15), rechts("6,39", 520, 470, hoehe=15),
        k("Rechnungsbetrag", 60, 496, hoehe=18), rechts("90,00", 520, 496, hoehe=18),
    ]


@pytest.fixture
def sauberer_bon():
    return [
        k("Bäckerei Probe GmbH", 40, 20, hoehe=22),
        k("1 x Brötchen", 40, 140, hoehe=14), rechts("1,30", 300, 140, hoehe=14),
        k("SUMME", 40, 176, hoehe=18), rechts("1,30", 300, 176, hoehe=18),
        k("Netto", 40, 206, hoehe=13), rechts("1,21", 300, 206, hoehe=13),
        k("MwSt 7,00 %", 40, 224, hoehe=13), rechts("0,09", 300, 224, hoehe=13),
    ]


def _abschnitt(text: str, ueberschrift: str) -> str:
    assert f"## {ueberschrift}" in text, f"Abschnitt „{ueberschrift}“ fehlt"
    return text.split(f"## {ueberschrift}")[1].split("\n## ")[0]


# ————— Das Leseprotokoll —————

def test_die_rechenproben_haben_einen_eigenen_abschnitt(sauberer_bon):
    text = protokoll(deuten(sauberer_bon, heute=date(2026, 8, 22)),
                     datei="bon.jpg", engine="x", dauer_s=0.1)
    assert "## Die Rechenproben" in text


def test_jede_probe_steht_mit_namen_und_erklaerung_in_der_tabelle(sauberer_bon):
    lesung = deuten(sauberer_bon, heute=date(2026, 8, 22))
    assert lesung.proben, "ohne Proben prüft der Test nichts"
    abschnitt = _abschnitt(
        protokoll(lesung, datei="bon.jpg", engine="x", dauer_s=0.1),
        "Die Rechenproben")
    for p in lesung.proben:
        zeile = [z for z in abschnitt.splitlines() if z.startswith(f"| {p.name} |")]
        assert zeile, f"Probe „{p.name}“ fehlt in der Tabelle"
        assert p.erklaerung in zeile[0], f"Probe „{p.name}“ steht ohne Erklärung da"


def test_eine_bestandene_probe_ist_als_solche_zu_erkennen(sauberer_bon):
    abschnitt = _abschnitt(
        protokoll(deuten(sauberer_bon, heute=date(2026, 8, 22)),
                  datei="bon.jpg", engine="x", dauer_s=0.1),
        "Die Rechenproben")
    assert "geht auf" in abschnitt


def test_die_gescheiterte_probe_nennt_die_zeile(verlesener_bon):
    """Ohne Zeilenverweis muss Nina den Beleg selbst absuchen."""
    lesung = deuten(verlesener_bon, heute=date(2026, 8, 22))
    probe = next(p for p in lesung.proben if not p.bestanden)
    assert probe.zeile_nr is not None
    abschnitt = _abschnitt(
        protokoll(lesung, datei="x.jpg", engine="x", dauer_s=0.1),
        "Die Rechenproben")
    zeile = [z for z in abschnitt.splitlines() if z.startswith(f"| {probe.name} |")][0]
    assert f"Zeile {probe.zeile_nr + 1}" in zeile
    assert "geht nicht auf" in zeile


def test_die_gescheiterte_probe_steht_mit_ihren_zahlen_da(verlesener_bon):
    abschnitt = _abschnitt(
        protokoll(deuten(verlesener_bon, heute=date(2026, 8, 22)),
                  datei="x.jpg", engine="x", dauer_s=0.1),
        "Die Rechenproben")
    assert "33,61 €" in abschnitt and "90,00 €" in abschnitt


def test_die_proben_stehen_nicht_zusaetzlich_als_notiz(verlesener_bon):
    """Doppelt hilft nicht — die Notizen bleiben für das, was sonst nirgends
    steht (Spaltenlage, Trinkgeld)."""
    text = protokoll(deuten(verlesener_bon, heute=date(2026, 8, 22)),
                     datei="x.jpg", engine="x", dauer_s=0.1)
    notizen = _abschnitt(text, "Wie babu den Beleg gelesen hat")
    assert "Probe Einzelposten:" not in notizen
    assert "Spalte" in notizen, "die übrigen Notizen müssen bleiben"


def test_ohne_betrag_sagt_der_abschnitt_dass_nichts_nachzurechnen_war():
    lesung = deuten([k("Ein Zettel ohne Zahlen", 40, 20, hoehe=22)],
                    heute=date(2026, 8, 22))
    assert not lesung.proben
    abschnitt = _abschnitt(
        protokoll(lesung, datei="x.jpg", engine="x", dauer_s=0.1),
        "Die Rechenproben")
    assert "nachrechnen" in abschnitt


def test_ein_strich_in_der_erklaerung_zerlegt_die_probentabelle_nicht():
    """Die Texterkennung liest senkrechte Linien gern als „|" — ungeschützt
    zerfällt die Tabelle beim Anzeigen."""
    from belegdeutung import Probe  # noqa: PLC0415
    lesung = deuten([k("Laden GmbH", 40, 20, hoehe=22),
                     k("Summe", 40, 100), rechts("10,00", 300, 100)],
                    heute=date(2026, 8, 22))
    lesung.proben = [Probe("Bar | geld", False, "Gegeben 20 | zurück 10", 1)]
    text = protokoll(lesung, datei="x.jpg", engine="x", dauer_s=0.1)
    zeile = [z for z in text.splitlines() if z.startswith("| Bar")][0]
    assert len(re.split(r"(?<!\\)\|", zeile)) == 6      # | a | b | c | d |


# ————— Was über die Schnittstelle geht —————

def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def welt(tmp_path, monkeypatch, verlesener_bon):
    """Eine Belegbox mit genau einem Beleg — dem verlesenen."""
    import review_watcher as rw  # noqa: PLC0415

    felder = rw.felder_aus_lesung(deuten(verlesener_bon, heute=date(2026, 8, 22)))
    golden = json.loads(GOLDEN.read_text())
    review = {kk: v for kk, v in golden.items() if kk not in ("audit", "buchungssatz")}
    review["felder"] = felder
    review["datei"] = f"docs/2026-08/{STAMM}.jpg"

    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    _git(arbeit, "config", "user.name", "t")
    _git(arbeit, "config", "user.email", "t@l")
    (arbeit / "docs" / "2026-08").mkdir(parents=True)
    (arbeit / "review").mkdir()
    (arbeit / "docs" / "2026-08" / f"{STAMM}.jpg").write_bytes(b"\xff\xd8x")
    (arbeit / "review" / f"{STAMM}.json").write_text(
        json.dumps(review, ensure_ascii=False))
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "aufnahme+review")
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

    import babu_web  # noqa: PLC0415
    import boxschreiber  # noqa: PLC0415
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    babu_web._INDEX.update(head=None, geprueft=0.0, belege={}, reviews={},
                           dokumente=[], zeiten={}, oid_cache={})
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None

    from fastapi.testclient import TestClient  # noqa: PLC0415
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    return client


def test_die_deutung_liefert_die_proben_ueberhaupt(verlesener_bon):
    """Gegenprobe zu allem Folgenden: was nicht in den Feldern steht, kann
    auch keine Schnittstelle weitergeben."""
    import review_watcher as rw  # noqa: PLC0415
    f = rw.felder_aus_lesung(deuten(verlesener_bon, heute=date(2026, 8, 22)))
    assert f["summenprobe_ok"] is False
    gescheitert = [p for p in f["proben"] if not p["bestanden"]]
    assert [p["name"] for p in gescheitert] == ["Einzelposten"]


def test_die_belegliste_nennt_die_gescheiterte_probe(welt):
    """Bisher stand in der Liste nur `summenprobe_ok: false` — das schickt
    Nina auf die Suche, ohne ihr zu sagen wonach."""
    zeile = next(z for z in welt.get("/api/belege").json()["belege"]
                 if z["stamm"] == STAMM)
    assert zeile["summenprobe_ok"] is False
    namen = [p["name"] for p in zeile["proben"]]
    assert "Einzelposten" in namen


def test_der_einzelne_beleg_liefert_die_proben_mit_zeile(welt):
    proben = welt.get(f"/api/beleg/{STAMM}").json()["felder"]["proben"]
    einzel = next(p for p in proben if p["name"] == "Einzelposten")
    assert einzel["bestanden"] is False
    assert "33,61 €" in einzel["erklaerung"] and "90,00 €" in einzel["erklaerung"]
    assert einzel["zeile"] is not None


def test_ein_selbst_eingetragener_betrag_raeumt_die_alten_proben_weg(welt):
    """Die Probe rechnete gegen den gelesenen Betrag. Trägt Nina ihn selbst
    ein, gilt ihre Angabe — die alte Rechnung daneben stehen zu lassen wäre
    eine Behauptung über eine Zahl, die es nicht mehr gibt."""
    r = welt.post(f"/api/angaben/{STAMM}", json={"brutto": 40.0})
    assert r.status_code == 200, r.text
    assert welt.get(f"/api/beleg/{STAMM}").json()["felder"]["proben"] == []
    zeile = next(z for z in welt.get("/api/belege").json()["belege"]
                 if z["stamm"] == STAMM)
    assert zeile["proben"] == []


# ————— Und was das Portal daraus macht —————

def test_das_portal_zeigt_einen_abschnitt_rechenproben():
    assert "Die Rechenproben" in PORTAL, \
        "das Portal nennt die Proben nirgends beim Namen"


def test_das_portal_liest_das_feld_proben():
    assert re.search(r"\bf\.proben\b", PORTAL), \
        "das Portal wertet das Feld gar nicht aus"


def test_das_portal_zeigt_die_erklaerung_und_nicht_nur_den_namen():
    """„Summenprobe nicht bestanden" sagt niemandem, wo er hinsehen soll."""
    assert re.search(r"p\.erklaerung", PORTAL)
