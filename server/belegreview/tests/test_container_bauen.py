"""Ein Wissenscontainer für ein Portal (`werkzeuge/kompendium/container_bauen.py`).

Ein Portal mit eigenem Container (portale/barber.py) sucht in einem Verzeichnis
neben dem Hauptbestand. Der Container muss dasselbe Format haben, das
`kompendium.py` liest — und das Werkzeug darf den Hauptbestand nie anfassen.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER.parents[2] / "werkzeuge" / "kompendium"))

import container_bauen as cb  # noqa: E402
import kompendium  # noqa: E402


def _quellen(ordner: Path) -> Path:
    ordner.mkdir()
    (ordner / "hwo.md").write_text(
        "# HwO § 7b\nQuelle: gesetze-im-internet.de, abgerufen 24.09.2026\n\n"
        "## Absatz 1\nEine Ausübungsberechtigung erhält, wer sechs Jahre tätig war.\n\n"
        "## Absatz 2\nDavon vier Jahre in leitender Stellung, im Handwerk selbst.\n")
    (ordner / "grundwissen.md").write_text("# Grundwissen Barber\nstehend")
    return ordner


def _embed(text):
    rng = np.random.default_rng(sum(map(ord, text)))
    return {"vektor": list(rng.normal(size=8))}


def test_der_container_hat_das_format_das_kompendium_liest(tmp_path, monkeypatch):
    q = _quellen(tmp_path / "quellen")
    haupt = tmp_path / "kompendium"
    haupt.mkdir()
    r = cb.bauen(q, tmp_path / "kompendium-barber", embed=_embed)
    assert r["geschrieben"] and r["gesamt_atome"] == 3
    monkeypatch.setattr(kompendium, "VERZEICHNIS", haupt)
    monkeypatch.setattr(kompendium, "_WEITERE", {})
    monkeypatch.setattr(kompendium, "_WEITERE_TEXTE", {})
    zeilen = [json.loads(z) for z in open(tmp_path / "kompendium-barber" / "atome.jsonl")]
    v = np.load(tmp_path / "kompendium-barber" / "vektoren.npy")
    assert len(zeilen) == v.shape[0] and np.allclose(np.linalg.norm(v, axis=1), 1)
    assert all(z["quelle"] == "hwo.md" and z["text"] for z in zeilen)
    # Das Kompendium findet das Atom über denselben Vektor wieder.
    t = kompendium.suchen_in(_embed(zeilen[1]["text"])["vektor"], ("kompendium-barber",), k=1)
    assert t and t[0]["loc"] == zeilen[1]["loc"]
    assert kompendium.grundwissen_von(("kompendium", "kompendium-barber")).startswith("# Grundwissen Barber")


def test_ein_zweiter_lauf_fuegt_nichts_doppelt_an(tmp_path):
    q = _quellen(tmp_path / "quellen")
    cb.bauen(q, tmp_path / "k", embed=_embed)
    r = cb.bauen(q, tmp_path / "k", embed=_embed)
    assert r["neu"] == 0 and not r["geschrieben"]


def test_der_hauptbestand_wird_nie_beschrieben(tmp_path, monkeypatch):
    q = _quellen(tmp_path / "quellen")
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(RuntimeError):
        cb.bauen(q, tmp_path / "kompendium", embed=_embed)


def test_fehlt_der_eigene_container_schweigt_das_portal(tmp_path, monkeypatch):
    monkeypatch.setattr(kompendium, "VERZEICHNIS", tmp_path / "kompendium")
    monkeypatch.setattr(kompendium, "_WEITERE", {})
    monkeypatch.setattr(kompendium, "_WEITERE_TEXTE", {})
    assert kompendium.suchen_in([1.0, 0.0], ("kompendium-barber",), k=3) == []
    assert kompendium.grundwissen_von(("kompendium", "kompendium-barber")) == ""
