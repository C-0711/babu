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


# ---------------------------------------------------------------------------
# Ninas Befund vom 14.10.2026: „7 % von 19 %"
# ---------------------------------------------------------------------------

def _hochland() -> dict:
    """Ihr Bon, mit den Werten aus ihrer Belegbox (28.09.2026).

    4,40 € zu 7 % (Kaffee) und 1,00 € zu 19 % (Tassenmaß), zusammen 5,40 €.
    `ust_satz` trägt den überwiegenden Satz — das ist so gewollt und für
    einen Beleg mit EINEM Satz richtig. Als Beschriftung des ganzen Belegs
    ist es falsch.
    """
    return {
        "felder": {"lieferant": "Hochland Kaffee", "datum": "2026-01-24",
                   "brutto": 5.40, "netto": 4.95, "ust": 0.45, "ust_satz": 7,
                   "steuertabelle": [
                       {"satz": 7, "brutto": 4.4, "netto": 4.11, "ust": 0.29},
                       {"satz": 19, "brutto": 1.0, "netto": 0.84, "ust": 0.16}]},
        "buchung": {"buchung": {"kategorie_name": "Kundenaufmerksamkeiten"}},
        "zeilen": ["Hochland", "Rechnung"], "dokumentklasse": "beleg"}


def _betragszeile(review: dict) -> str:
    """`beleg_markdown` ist eine reine Funktion — ohne die `welt`-Fixture,
    die der Rest dieser Datei für den Schreibweg braucht."""
    from pathlib import Path as _P  # noqa: PLC0415
    sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    import babu_web  # noqa: PLC0415
    return next(z for z in babu_web.beleg_markdown(review).splitlines()
                if z.startswith("- Betrag:"))


def test_ein_beleg_mit_zwei_saetzen_nennt_beide():
    """Hinter dem ⓘ stand „5,40 € brutto (7 % USt)" — auf einem Bon, der zu
    einem Fünftel 19 % trägt. Nina hat genau das gemeldet."""
    zeile = _betragszeile(_hochland())
    assert "7 %" in zeile and "19 %" in zeile, zeile


def test_der_groessere_anteil_steht_vorne():
    """Die Steuertabelle ist nach Bruttoanteil sortiert; der Text folgt ihr,
    damit „überwiegend 7 %" lesbar bleibt."""
    assert _betragszeile(_hochland()).index("7 %") \
        < _betragszeile(_hochland()).index("19 %")


def test_ein_satz_bleibt_ein_satz():
    """Negativkontrolle. Der Normalfall darf sich NICHT ändern — sonst stünde
    auf jedem gewöhnlichen Beleg plötzlich eine Aufzählung."""
    einer = dict(_hochland())
    einer["felder"] = dict(einer["felder"], ust_satz=19, brutto=11.90,
                           netto=10.0, ust=1.90,
                           steuertabelle=[{"satz": 19, "brutto": 11.9,
                                           "netto": 10.0, "ust": 1.9}])
    assert _betragszeile(einer) == "- Betrag: 11,90 € brutto (19 % USt)"


def test_ohne_steuersatz_steht_kein_satz():
    ohne = dict(_hochland())
    ohne["felder"] = {"lieferant": "Amt", "brutto": 30.0, "ust_satz": 0}
    assert _betragszeile(ohne) == "- Betrag: 30,00 € brutto"
