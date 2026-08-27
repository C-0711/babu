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
    monkeypatch.setattr(kompendium, "_GRUNDWISSEN", None)
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
    monkeypatch.setattr(kompendium, "_GRUNDWISSEN", None)
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
