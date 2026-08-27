"""Die Beiakte zum Suchen: kanonisches Markdown + Embedding je Beleg.

Ein Beleg wird beim Archivieren als Markdown (Kopf + jede Zeile) abgelegt
und darüber vektorisiert — im selben Commit. Der Embedding-Dienst darf
dabei ausfallen, ohne die Aufnahme zu stören; backfill_embeddings holt
fehlende Vektoren später nach.
"""
import json
import subprocess
import sys

# Dieselbe Welt wie die Bündel-Tests: Bare-Box, gestubbte Wachen.
from test_mehrseiten_buendel import (ERGEBNIS, _hochladen, _im_stand,  # noqa: F401
                                     welt)

VEKTOR = {"modell": "embeddinggemma", "dim": 3, "vektor": [0.1, 0.2, 0.3]}


def test_markdown_traegt_kopf_und_jede_zeile(welt):
    bw, _ = welt
    review, md = bw._review_aus_einschaetzung(
        "docs/x.pdf", ERGEBNIS["buchung"], ERGEBNIS["zeilen"], "beleg")
    assert md == bw.beleg_markdown(review)
    assert md.startswith("# Henkel\n")
    assert "- Datum: 2026-02-24" in md
    assert "- Betrag: 189,61 € brutto (19 % USt)" in md
    assert "- Dokumentklasse: beleg" in md
    assert "## Jede erkannte Zeile" in md
    assert "  Zahlungsbetrag EUR 189,61" in md


def test_aufnahme_schreibt_embedding_beiakte(welt, monkeypatch):
    bw, bare = welt
    monkeypatch.setattr(bw, "embedding_rechnen", lambda text: dict(VEKTOR))
    r = _hochladen(bw)
    assert r.status_code == 200, r.text
    beiakten = [d for d in _im_stand(bare) if d.endswith(".embedding.json")]
    assert len(beiakten) == 1, _im_stand(bare)
    roh = subprocess.run(["git", "--git-dir", str(bare), "show",
                          f"HEAD:{beiakten[0]}"], capture_output=True).stdout
    assert json.loads(roh) == VEKTOR
    md_pfad = beiakten[0].replace(".embedding.json", ".md")
    md = subprocess.run(["git", "--git-dir", str(bare), "show",
                         f"HEAD:{md_pfad}"], capture_output=True).stdout
    assert md.decode().startswith("# Henkel")


def test_aufnahme_uebersteht_toten_embedding_dienst(welt, monkeypatch):
    bw, bare = welt
    monkeypatch.setattr(bw, "embedding_rechnen", lambda text: None)
    r = _hochladen(bw)
    assert r.status_code == 200, r.text
    dateien = _im_stand(bare)
    assert not any(d.endswith(".embedding.json") for d in dateien)
    # Das Markdown liegt trotzdem — der Backfill braucht nur noch den Vektor.
    assert any(d.startswith("review/") and d.endswith(".md") for d in dateien)


def test_backfill_holt_fehlende_vektoren_nach(welt, monkeypatch):
    bw, bare = welt
    monkeypatch.setattr(bw, "embedding_rechnen", lambda text: None)
    assert _hochladen(bw).status_code == 200

    import backfill_embeddings
    monkeypatch.setattr(bw, "embedding_rechnen", lambda text: dict(VEKTOR))
    monkeypatch.setattr(sys, "argv", ["backfill_embeddings.py"])
    assert backfill_embeddings.main() == 0
    beiakten = [d for d in _im_stand(bare) if d.endswith(".embedding.json")]
    assert len(beiakten) == 1, _im_stand(bare)
    # Ein zweiter Lauf findet nichts mehr zu tun und bleibt still.
    assert backfill_embeddings.main() == 0
    assert len([d for d in _im_stand(bare)
                if d.endswith(".embedding.json")]) == 1
