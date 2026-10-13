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


def test_der_grundstock_ist_eine_kopie_ohne_die_genannten_quellen(tmp_path):
    q = _quellen(tmp_path / "quellen")
    cb.bauen(q, tmp_path / "friseur", embed=_embed)
    (tmp_path / "friseur" / "hwo.md").write_text("x")
    # Ein zweites Atom mit anderer Quelle dazu, damit etwas übrig bleibt.
    zeilen = [json.loads(z) for z in open(tmp_path / "friseur" / "atome.jsonl")]
    r = cb.grundstock(tmp_path / "friseur", tmp_path / "werkstatt", ohne=("hwo",))
    assert r == {"quelle_atome": len(zeilen), "behalten": 0, "ohne": len(zeilen)}
    r = cb.grundstock(tmp_path / "friseur", tmp_path / "werkstatt2", ohne=("anderes",))
    assert r["behalten"] == len(zeilen)
    v_alt = np.load(tmp_path / "friseur" / "vektoren.npy")
    v_neu = np.load(tmp_path / "werkstatt2" / "vektoren.npy")
    assert np.array_equal(v_alt, v_neu)                     # Zeile für Zeile, kein Neu-Einbetten
    with pytest.raises(RuntimeError):
        cb.grundstock(tmp_path / "friseur", tmp_path / "werkstatt2", ohne=())   # nur einmal


def test_eine_korrigierte_quelle_ersetzt_ihre_atome(tmp_path):
    """Ein Container SPIEGELT seine Quelle — er sammelt sie nicht an.

    Bis zum 14.10.2026 fügte der Bau nur Atome mit neuem SHA hinzu. Wer einen
    Satz korrigierte, bekam beide Fassungen nebeneinander in den Index; die
    Suche konnte die alte zitieren. Aufgefallen an einer Rechtsaussage: das
    Zählprotokoll bei der offenen Ladenkasse ist gesetzlich nicht gefordert
    (BFH X B 41/16) — im Index stand weiter, es sei gefordert.
    """
    q = tmp_path / "quellen"
    q.mkdir()
    datei = q / "kasse.md"
    datei.write_text("# Offene Ladenkasse\nQuelle: AO, abgerufen 14.10.2026\n\n"
                     "## Pflichten\nSie verlangt Kassenbericht und Zählprotokoll.\n")
    ziel = tmp_path / "kompendium-barber"
    erst = cb.bauen(q, ziel, embed=_embed)
    assert erst["geschrieben"]
    vorher = erst["gesamt_atome"]

    datei.write_text("# Offene Ladenkasse\nQuelle: AO, abgerufen 14.10.2026\n\n"
                     "## Pflichten\nSie verlangt einen Kassenbericht. Ein "
                     "Zählprotokoll ist gesetzlich nicht gefordert.\n")
    zweit = cb.bauen(q, ziel, embed=_embed)

    atome = [json.loads(z) for z in (ziel / "atome.jsonl").read_text().splitlines()]
    text = "\n".join(a["text"] for a in atome)
    assert "nicht gefordert" in text, "die Korrektur fehlt"
    assert "Kassenbericht und Zählprotokoll" not in text, "die alte Fassung steht noch da"
    assert len(atome) == vorher, f"angesammelt statt ersetzt: {vorher} → {len(atome)}"
    assert zweit["ersetzt"] == 1

    # Die Invariante, an der alles hängt: Zeile i ist Vektor i.
    vek = np.load(ziel / "vektoren.npy")
    assert vek.shape[0] == len(atome)


def test_eine_quelle_die_es_nicht_mehr_gibt_bleibt_stehen(tmp_path):
    """Gespiegelt wird je Datei. Was nicht mehr im Quellordner liegt, wird
    nicht angefasst — ein Container kann aus mehreren Läufen bestehen."""
    q = tmp_path / "quellen"
    q.mkdir()
    (q / "alt.md").write_text(
        "# Alt\nQuelle: gesetze-im-internet.de, abgerufen 14.10.2026\n\n"
        "## Abschnitt A\nDieser Satz bleibt stehen, auch wenn seine Datei "
        "spaeter nicht mehr im Quellordner liegt.\n")
    ziel = tmp_path / "kompendium-barber"
    assert cb.bauen(q, ziel, embed=_embed)["geschrieben"]
    (q / "alt.md").unlink()
    (q / "neu.md").write_text(
        "# Neu\nQuelle: gesetze-im-internet.de, abgerufen 14.10.2026\n\n"
        "## Abschnitt B\nDieser Satz kommt in einem zweiten Lauf dazu und "
        "verdraengt den ersten nicht.\n")
    r = cb.bauen(q, ziel, embed=_embed)
    text = (ziel / "atome.jsonl").read_text()
    assert "bleibt stehen" in text and "kommt in einem zweiten Lauf dazu" in text
    assert r["ersetzt"] == 0
