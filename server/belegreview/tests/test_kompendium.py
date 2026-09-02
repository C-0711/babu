"""Kompendium-Suche, Weltblock und Recherche — die drei Schichten des Chats.

Schicht 1: stehender Weltblock (byte-stabil → Prefix-Cache).
Schicht 2: Grundwissen-Digest aus dem Kompendium, ebenso stabil.
Schicht 3: Recherche je Frage — Vektorsuche über Kompendium-Atome und
Beleg-Beiakten. Ohne Kompendium-Verzeichnis und ohne Embedding-Dienst
bleibt alles still; der Chat läuft dann wie vorher.
"""
import json
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))


@pytest.fixture()
def mini_kompendium(tmp_path, monkeypatch):
    import numpy as np

    import kompendium
    atome = [
        {"id": 0, "quelle": "afa.pdf", "loc": "S1#0",
         "text": "Bedienungsstühle: Nutzungsdauer 10 Jahre"},
        {"id": 1, "quelle": "ustg.md", "loc": "txt#3",
         "text": "Kleinunternehmer nach § 19 UStG"},
        {"id": 2, "quelle": "statistik.md", "loc": "txt#0",
         "text": "Durchschnittsmiete je Quadratmeter Salonfläche"},
    ]
    with open(tmp_path / "atome.jsonl", "w") as f:
        for a in atome:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    vektoren = np.eye(3, 4, dtype=np.float32)  # Atom i zeigt in Richtung i
    np.save(tmp_path / "vektoren.npy", vektoren)
    (tmp_path / "grundwissen.md").write_text("# Grundwissen\n\nFriseurbranche.")
    monkeypatch.setattr(kompendium, "VERZEICHNIS", tmp_path)
    monkeypatch.setattr(kompendium, "_VEKTOREN", None)
    monkeypatch.setattr(kompendium, "_OFFSETS", [])
    monkeypatch.setattr(kompendium, "_TEXTE", {})
    return kompendium


def test_suche_findet_das_passendste_atom(mini_kompendium):
    treffer = mini_kompendium.suchen([0.1, 0.9, 0.0, 0.0], k=2)
    assert [t["quelle"] for t in treffer] == ["ustg.md", "afa.pdf"]
    assert treffer[0]["score"] > treffer[1]["score"]
    assert "Kleinunternehmer" in treffer[0]["text"]
    assert treffer[0]["loc"] == "txt#3"


def test_grundwissen_kommt_aus_der_datei(mini_kompendium):
    assert mini_kompendium.grundwissen().startswith("# Grundwissen")


def test_ohne_verzeichnis_bleibt_alles_still(tmp_path, monkeypatch):
    import kompendium
    monkeypatch.setattr(kompendium, "VERZEICHNIS", tmp_path / "gibtsnicht")
    monkeypatch.setattr(kompendium, "_VEKTOREN", None)
    monkeypatch.setattr(kompendium, "_OFFSETS", [])
    monkeypatch.setattr(kompendium, "_TEXTE", {})
    assert kompendium.suchen([1.0, 0.0], k=3) == []
    assert kompendium.grundwissen() == ""


def test_weltblock_ist_deterministisch_und_traegt_alles():
    import wissen
    welt = {
        "einstellungen": {"betrieb_name": "Salon Test"},
        "belege": [
            {"stamm": "b2", "lieferant": "Wagner", "brutto": 50.0,
             "monat": "2026-08", "datum": "05.08.2026", "belegart": "Ware"},
            {"stamm": "b1", "lieferant": "Anna", "brutto": 20.0,
             "monat": "2026-07", "datum": "01.07.2026", "belegart": "Ware"},
        ],
        "kassenblaetter": [], "vertraege": [], "rechnungen": [], "team": [],
        "fristen": [], "zahlen": {}, "dokumente": [],
    }
    a = wissen.weltblock(welt)
    assert a == wissen.weltblock(dict(welt))
    assert "BELEG-REGISTER (2" in a
    # Älteste zuerst: neue Belege verlängern den Block nur am Ende.
    assert a.index("Anna") < a.index("Wagner")


def test_recherche_bringt_kompendium_und_eigene_belege(mini_kompendium, monkeypatch):
    import babu_web as bw
    monkeypatch.setattr(
        bw, "embedding_rechnen",
        lambda text, als_dokument=True: {"modell": "embeddinggemma", "dim": 4,
                                         "vektor": [1.0, 0.0, 0.0, 0.0]})
    beiakte = {"modell": "embeddinggemma", "dim": 4, "vektor": [1, 0, 0, 0]}

    def falsches_show(pfad):
        if pfad.endswith(".embedding.json"):
            return json.dumps(beiakte).encode()
        if pfad.endswith(".md"):
            return "# Stuhl-Kauf\n\n- Betrag: 500,00 € brutto".encode()
        return None
    monkeypatch.setattr(bw, "git_show", falsches_show)
    monkeypatch.setattr(bw, "_BELEG_VEKTOREN", (None, [], None))

    import subprocess as sp

    class R:
        returncode = 0

        def __init__(self, out):
            self.stdout = out
    monkeypatch.setattr(bw.subprocess, "run", lambda cmd, **kw: R(
        "kopf123\n" if "rev-parse" in cmd else "stuhl.embedding.json\n"))

    text = bw._recherche("Wie lange schreibe ich einen Bedienungsstuhl ab?")
    assert "NACHGESCHLAGEN" in text
    assert "[afa.pdf · S1#0]" in text
    assert "ZUR FRAGE PASSENDE EIGENE BELEGE" in text
    assert "# Stuhl-Kauf" in text


def test_recherche_ohne_embedding_dienst_ist_leer(monkeypatch):
    import babu_web as bw
    monkeypatch.setattr(bw, "embedding_rechnen",
                        lambda text, als_dokument=True: None)
    assert bw._recherche("egal") == ""


def test_recherche_findet_wissen_atome(mini_kompendium, monkeypatch):
    """Kompendium- und Wissens-Treffer werden zusammengeführt und nach
    Score sortiert — beide Quellen rendern gleich, weil `_wissen_treffer`
    dieselbe Dict-Form wie `kompendium.suchen()` liefert."""
    import numpy as np

    import babu_web as bw
    monkeypatch.setattr(
        bw, "embedding_rechnen",
        lambda text, als_dokument=True: {"modell": "e", "dim": 4,
                                         "vektor": [1.0, 0.0, 0.0, 0.0]})
    monkeypatch.setattr(bw, "_beleg_vektoren", lambda: ([], None))
    wissen_meta = [{"quelle": "wissen:kontenrahmen", "loc": "S2#0",
                   "text": "SKR04-Kontenrahmen: Übersicht der Kontenklassen",
                   "thema": "kontenrahmen", "thema_name": "Kontenrahmen",
                   "titel": "SKR04-Handbuch", "pfad": "wissen/kontenrahmen/x.pdf"}]
    # Zeigt nicht exakt auf denselben Punkt wie afa.pdf — score liegt
    # niedriger, muss also NACH afa.pdf erscheinen.
    wissen_matrix = np.array([[0.5, 0.8660254, 0.0, 0.0]], dtype=np.float32)
    monkeypatch.setattr(bw, "_wissen_vektoren", lambda: (wissen_meta, wissen_matrix))

    text = bw._recherche("Welches Konto für was?")
    assert "NACHGESCHLAGEN" in text
    assert "[afa.pdf · S1#0]" in text
    assert "[wissen:kontenrahmen · S2#0]" in text
    assert text.index("afa.pdf") < text.index("wissen:kontenrahmen")


# ————— Der Buchungs-Prompt: stehender Vorspann, variabler Beleg —————
#
# Der Chat kontiert erkennbar besser, seit sein Wissen byte-stabil im
# System-Teil liegt und vLLMs Prefix-Cache ihn nur einmal rechnet. Der
# Buchungsweg hat seit dem 28.08.2026 dieselbe Bauart.

def test_der_vorspann_ist_fuer_jeden_beleg_byte_gleich():
    import gemma_buchung as gb
    profil = gb.profil_text({"betrieb_name": "Salon Nina"})
    a = gb.system_text(profil)
    b = gb.system_text(profil)
    assert a == b
    # Zwei verschiedene Belege ändern am Vorspann nichts.
    gb.prompt_bauen(profil, ["Edeka 12,90"], [])
    gb.prompt_bauen(profil, ["Wella 340,00"], [{"frage": "?", "antwort": "ja"}])
    assert gb.system_text(profil) == a


def test_die_regeln_stehen_vor_dem_beleg_nicht_dahinter():
    """Der eigentliche Fund: bis zum 28.08. standen rund 1.400 Token
    Regeln HINTER dem Beleg und wurden bei jeder Buchung neu gerechnet."""
    import gemma_buchung as gb
    profil = gb.profil_text({})
    vorspann = gb.system_text(profil)
    beleg = gb.prompt_bauen(profil, ["Edeka 12,90"], [])
    assert "Regeln:" in vorspann and "Antworte NUR mit" in vorspann
    assert "Regeln:" not in beleg
    # Der Beleg-Teil ist ein Bruchteil des Ganzen.
    assert len(beleg) < len(vorspann) / 10


def test_das_kontierungswissen_steht_im_vorspann(mini_kompendium, monkeypatch):
    import gemma_buchung as gb
    (mini_kompendium.VERZEICHNIS / "kontierung-grundwissen.md").write_text(
        "# Kontierungswissen\n\n- Bedienungsstühle: 10 Jahre")
    monkeypatch.setattr(mini_kompendium, "_TEXTE", {})
    text = gb.system_text(gb.profil_text({}))
    assert "Bedienungsstühle: 10 Jahre" in text
    assert "NACHSCHLAGEWISSEN" in text


def test_ohne_kompendium_bucht_babu_trotzdem(tmp_path, monkeypatch):
    import gemma_buchung as gb
    import kompendium
    monkeypatch.setattr(kompendium, "VERZEICHNIS", tmp_path / "weg")
    monkeypatch.setattr(kompendium, "_TEXTE", {})
    text = gb.system_text(gb.profil_text({}))
    assert "NACHSCHLAGEWISSEN" not in text
    assert "KATEGORIEN" in text and "Regeln:" in text


def test_der_vorspann_geht_als_eigene_system_nachricht_raus(monkeypatch):
    import gemma_buchung as gb
    gesehen = {}

    class Antwort:
        def read(self): return b'{"choices":[{"message":{"content":"{}"}}]}'
        def __enter__(self): return self
        def __exit__(self, *_): return False

    def falsches_urlopen(req, timeout=None):
        gesehen.update(json.loads(req.data))
        import io
        return io.BytesIO(b'{"choices":[{"message":{"content":"{}"}}]}')

    monkeypatch.setattr(gb.urllib.request, "urlopen", falsches_urlopen)
    gb.runde(["Edeka 12,90"], {"betrieb_name": "Salon Nina"}, [])
    rollen = [m["role"] for m in gesehen["messages"]]
    assert rollen == ["system", "user"], rollen
    assert "Regeln:" in gesehen["messages"][0]["content"]
    assert "Edeka 12,90" in gesehen["messages"][1]["content"]


def test_nachschlagen_findet_zum_beleg_passende_stellen(mini_kompendium, monkeypatch):
    import babu_web as bw
    import gemma_buchung as gb
    monkeypatch.setattr(bw, "embedding_rechnen",
                        lambda text, als_dokument=True: {
                            "modell": "e", "dim": 4, "vektor": [1.0, 0, 0, 0]})
    text = gb.nachschlagen(["Moebel Mayer", "Bedienungsstuhl 750,00"])
    assert "NACHGESCHLAGEN" in text
    assert "[afa.pdf · S1#0]" in text
    assert "Nutzungsdauer 10 Jahre" in text


def test_nachschlagen_nimmt_nur_quellen_die_buchungsfragen_beantworten(
        mini_kompendium, monkeypatch):
    """Gemessen am 28.08.2026: die Frageform hebt ALLE Ähnlichkeiten auf
    rund 0,42, sodass jeder Beleg dieselbe Branchenstatistik trifft. Ein
    Schwellwert trennt das nicht — die Quelle schon."""
    import babu_web as bw
    import gemma_buchung as gb
    # Der Vektor zeigt auf Atom 2 (statistik.md) — kein Buchungswissen.
    monkeypatch.setattr(bw, "embedding_rechnen",
                        lambda text, als_dokument=True: {
                            "modell": "e", "dim": 4, "vektor": [0, 0, 1.0, 0]})
    assert gb.nachschlagen(["Wella", "Koleston Perfect"]) == ""


def test_die_suche_laesst_betraege_und_mengen_weg():
    import gemma_buchung as gb
    sache = gb._sachwoerter(["Moebel Mayer", "Bedienungsstuhl Hydraulik Holz",
                             "Netto 630,25", "Gesamt 750,00 EUR"], None)
    assert "Bedienungsstuhl Hydraulik Holz" in sache
    assert "630" not in sache and "750" not in sache


def test_nachschlagen_findet_wissen_quelle(mini_kompendium, monkeypatch):
    """`quelle="wissen:lohn"` passiert den NACHSCHLAG_QUELLEN-Filter, obwohl
    "lohn" selbst nicht in der Liste steht — der Filter prüft nur auf das
    Präfix "wissen", jedes Thema darunter ist für die Buchung zulässig."""
    import babu_web as bw
    import gemma_buchung as gb
    # Zeigt auf statistik.md (kein Buchungswissen) — das Kompendium darf
    # hier nichts beitragen, damit der Treffer eindeutig vom Wissen kommt.
    monkeypatch.setattr(bw, "embedding_rechnen",
                        lambda text, als_dokument=True: {
                            "modell": "e", "dim": 4, "vektor": [0, 0, 1.0, 0]})
    monkeypatch.setattr(bw, "_wissen_treffer", lambda vektor, k=6: [
        {"score": 0.55, "quelle": "wissen:lohn", "loc": "S3#1",
         "text": "Die Lohnsteuer richtet sich nach der Lohnsteuerklasse.",
         "thema": "lohn", "thema_name": "Lohn", "titel": "Lohnhandbuch",
         "pfad": "wissen/lohn/handbuch.pdf"}])
    text = gb.nachschlagen(["Frisör", "Team-Lohn Auszahlung"])
    assert "NACHGESCHLAGEN" in text
    assert "[wissen:lohn · S3#1]" in text


def test_nachschlagen_schweigt_ohne_dienst(monkeypatch):
    import babu_web as bw
    import gemma_buchung as gb
    monkeypatch.setattr(bw, "embedding_rechnen",
                        lambda text, als_dokument=True: None)
    assert gb.nachschlagen(["irgendwas"]) == ""


def test_das_nachgeschlagene_steht_beim_beleg_nicht_im_vorspann():
    """Es ändert sich mit jedem Beleg — im Vorspann würde es den
    Prefix-Cache für jede Buchung zerschneiden."""
    import gemma_buchung as gb
    profil = gb.profil_text({})
    beleg = gb.prompt_bauen(profil, ["x"], [], nachschlag="\nNACHGESCHLAGEN: A")
    assert "NACHGESCHLAGEN: A" in beleg
    assert "NACHGESCHLAGEN: A" not in gb.system_text(profil)
