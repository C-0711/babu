"""Das Branchenwissen fürs Gespräch — geprüft gegen die Datei, nicht gegen
den Prompt.

Verbindliche Regel (CLAUDE.md): Fachwissen gehört in den Wissenscontainer,
die Quelle ins Repo, die Kopie auf die H200V. In `gemma_buchung.REGELN`
steht nur Verhalten. Für den Chat gilt dasselbe: die Zahlen stehen in der
Wissensdatei, im Prompt steht nur der Auftrag, sie zu benutzen.

Nachgesehen am 08.09.2026: `grundwissen.md` (34.304 Zeichen) lag NUR auf der
H200V unter ~/kompendium/ und in keinem Repo — der Chat trug also seit dem
27.08. ein Branchenwissen mit sich, das niemand versionieren, prüfen oder
zurücknehmen konnte. Es liegt jetzt hier, und diese Tests fassen es an.

Zwei Dateien mit zwei Aufgaben:

  grundwissen.md           wie die Branche aussieht (Statistik, Recht, Löhne)
  beratung-grundwissen.md  woran man EINEN Salon misst — die Messlatten

Getrennt vom Kontierungswissen, weil das Buchen anderes braucht als das
Reden: Nutzungsdauern und Konten dort, Vergleichswerte und Schwellen hier.
"""
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

CONTAINER = HIER.parents[2] / "werkzeuge" / "kompendium"
BERATUNG = CONTAINER / "beratung-grundwissen.md"
GRUND = CONTAINER / "grundwissen.md"


def test_das_branchenwissen_liegt_im_repo():
    """Vorher lag es nur auf dem Server — unversioniert und ungeprüft."""
    assert GRUND.exists(), "grundwissen.md fehlt im Wissenscontainer"
    assert BERATUNG.exists(), "beratung-grundwissen.md fehlt im Wissenscontainer"


def test_die_messlatten_stehen_drin():
    """Die Zahlen, gegen die „ist das viel?" gerechnet wird."""
    w = BERATUNG.read_text(encoding="utf-8")
    for wert in ("32 %", "36 %", "39,6 %", "9,1 %", "13,1 %", "7,2 %", "72,9 %"):
        assert wert in w, wert
    assert "Destatis" in w and "Richtsatzsammlung 2025" in w


def test_die_drei_lesefallen_stehen_drin():
    """Ohne sie führt jeder Vergleich in die Irre — und babu würde einer
    Inhaberin erzählen, sie mache 33 % Gewinn."""
    w = BERATUNG.read_text(encoding="utf-8")
    assert "ohne Arbeitgeberanteil" in w.replace("OHNE", "ohne")
    assert "enthält den Unternehmerlohn" in w
    assert "Material ist der kleinste Block" in w


def test_trinkgeld_ist_beantwortet():
    """Die Frage, die im Salon täglich vorkommt — und der Unterschied
    zwischen steuerfrei und aufzeichnungsfrei, den fast alle verwechseln."""
    w = BERATUNG.read_text(encoding="utf-8")
    assert "§ 3 Nr. 51 EStG" in w
    assert "ohne Höchstgrenze" in w
    assert "Betriebseinnahme" in w                 # Trinkgeld an die Inhaberin
    assert "Steuerfrei heißt nicht aufzeichnungsfrei" in w


def test_die_kassenpflichten_stehen_mit_datum_und_der_entwurf_als_entwurf():
    w = BERATUNG.read_text(encoding="utf-8")
    assert "§ 146a Abs. 2 AO" in w and "§ 146a Abs. 4 AO" in w
    assert "01.04.2021" in w and "01.01.2025" in w
    assert "offene Ladenkasse bleibt zulässig" in w
    # Was noch nicht gilt, darf nie wie geltendes Recht klingen.
    assert "noch nicht geltendes Recht" in w and "Entwurfsstand" in w


def test_die_schwellen_stehen_drin():
    w = BERATUNG.read_text(encoding="utf-8")
    assert "25.000 €" in w and "100.000 €" in w        # § 19 UStG ab 2025
    assert "603 €" in w and "13,90 €" in w             # Minijob, Mindestlohn 2026
    assert "Mehrzweckgutschein" in w


def test_das_bfh_urteil_steht_mit_seiner_grenze_drin():
    """Es ist das stärkste Argument gegen eine pauschale Hinzuschätzung —
    und entbindet trotzdem nicht von ordentlicher Kassenführung. Ohne den
    zweiten Halbsatz wäre es eine gefährliche Auskunft."""
    w = BERATUNG.read_text(encoding="utf-8")
    assert "X R 19/21" in w and "18.06.2025" in w
    assert "innere Betriebsvergleich hat Vorrang" in w
    assert "entbindet" in w and "Kassenführung" in w
    assert "keine Rechtsberatung" in w


def test_jede_zahl_hat_eine_quelle():
    w = BERATUNG.read_text(encoding="utf-8")
    assert "## Quellen" in w
    for quelle in ("Fachserie 2 Reihe 1.6.4", "ECLI:DE:BFH:2025", "KassenSichV",
                   "§ 7 Abs. 4 SGB IV"):
        assert quelle in w, quelle


def test_die_datei_bleibt_unter_der_lesegrenze():
    """`kompendium.beratungswissen()` kappt bei 30.000 Zeichen — was
    darüber steht, käme im Prompt nie an."""
    assert len(BERATUNG.read_text(encoding="utf-8")) < 30000


def test_das_beraten_und_das_buchen_bleiben_getrennt():
    """Sonst bekäme jeder Buchungsprompt Branchenstatistik und jedes
    Gespräch den Kontenplan."""
    beratung = BERATUNG.read_text(encoding="utf-8")
    kontierung = (CONTAINER / "kontierung-grundwissen.md").read_text(encoding="utf-8")
    assert "Nutzungsdauern" not in beratung
    assert "Messlatte" not in kontierung


# ————— Und kommt es auch im Prompt an? —————

def test_kompendium_liest_die_beratungsdatei(tmp_path, monkeypatch):
    import kompendium
    (tmp_path / "beratung-grundwissen.md").write_text("# Messlatten\n\nPersonal 32 %.")
    monkeypatch.setattr(kompendium, "VERZEICHNIS", tmp_path)
    monkeypatch.setattr(kompendium, "_TEXTE", {})
    assert kompendium.beratungswissen().startswith("# Messlatten")


def test_ohne_wissenscontainer_bleibt_es_still(tmp_path, monkeypatch):
    """Lokal und in Tests gibt es das Verzeichnis nicht — der Chat muss
    trotzdem laufen."""
    import kompendium
    monkeypatch.setattr(kompendium, "VERZEICHNIS", tmp_path / "gibtsnicht")
    monkeypatch.setattr(kompendium, "_TEXTE", {})
    assert kompendium.beratungswissen() == ""


def test_die_messlatten_stehen_im_chat_prompt(tmp_path, monkeypatch):
    import babu_web
    import kompendium

    (tmp_path / "beratung-grundwissen.md").write_text(
        "# Messlatten\n\nPersonal 32-36 % vom Umsatz.")
    monkeypatch.setattr(kompendium, "VERZEICHNIS", tmp_path)
    monkeypatch.setattr(kompendium, "_TEXTE", {})
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None
    babu_web._LOGIN_VERSUCHE.clear()
    babu_web._REG_ZULETZT.clear()
    monkeypatch.setattr(babu_web, "_welt_fuer", lambda un: {
        "einstellungen": {"betrieb_name": "Salon Nina"}, "belege": [],
        "kassenblaetter": [], "vertraege": [], "rechnungen": [], "team": [],
        "fristen": [], "zahlen": {}, "dokumente": []})

    gesagt: list[dict] = []

    class Antwort:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "Gut."}}]}

    monkeypatch.setattr(babu_web.requests, "post",
                        lambda url, json=None, **kw: (gesagt.append(json), Antwort())[1])

    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    client.post("/chat", json={"frage": "Zahle ich zu viel für mein Team?"})
    system = gesagt[-1]["messages"][0]["content"]
    assert "Personal 32-36 % vom Umsatz." in system
    # Und der Auftrag, sie auch zu benutzen — das ist Verhalten und steht
    # deshalb im Prompt, nicht in der Wissensdatei.
    assert "nenne den Vergleichswert und seine Quelle" in system
