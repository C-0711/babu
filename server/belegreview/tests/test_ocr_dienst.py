"""Der OCR-Dienst — und was passiert, wenn er wegfällt.

Die eingebaute Lane rechnete PP-OCRv5 auf der CPU: gemessen 2,75 s je
Beleg. Derselbe Zettel über den GPU-Dienst: 0,03 s. Das ist der Unterschied
zwischen „gleich fertig" und „warte mal".

Wichtiger als die Geschwindigkeit ist hier aber, dass ein weggefallener
Dienst keinen Beleg verschluckt. Deshalb prüfen diese Tests vor allem den
Rückfall.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def rw():
    import review_watcher
    return review_watcher


class Antwort:
    def __init__(self, nutzlast, status=200):
        self._n, self.status_code = nutzlast, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._n


def dienstantwort(texte, scores=None, ys=None):
    scores = scores or [0.97] * len(texte)
    ys = ys or list(range(0, 40 * len(texte), 40))
    return {"errorCode": 0, "errorMsg": "Success", "result": {
        "ms": 28, "ocrResults": [{"page": 0, "meta": {"doc_angle": 0},
            "prunedResult": {
                "rec_texts": texte, "rec_scores": scores,
                "rec_polys": [[[10, y], [200, y], [200, y + 14], [10, y + 14]]
                              for y in ys]}}]}}


def test_zeilen_kommen_in_lesereihenfolge(rw, tmp_path, monkeypatch):
    bild = tmp_path / "beleg.png"; bild.write_bytes(b"\x89PNG" + b"x" * 50)
    # Absichtlich verdreht geliefert — sortiert werden muss nach y.
    monkeypatch.setattr(rw.requests, "post", lambda *a, **k: Antwort(
        dienstantwort(["Gesamtbetrag 3,50", "GALERIA"], ys=[300, 20])))
    assert [t for t, _ in rw.ocr_zeilen(bild)] == ["GALERIA", "Gesamtbetrag 3,50"]


def test_die_konfidenz_kommt_mit(rw, tmp_path, monkeypatch):
    bild = tmp_path / "b.png"; bild.write_bytes(b"x")
    monkeypatch.setattr(rw.requests, "post", lambda *a, **k: Antwort(
        dienstantwort(["Zeile"], scores=[0.42])))
    assert rw.ocr_zeilen(bild) == [("Zeile", 0.42)]


def test_die_quelle_wird_festgehalten(rw, tmp_path, monkeypatch):
    """Im Review soll stehen, wer gelesen hat — nicht ein fester Text."""
    bild = tmp_path / "b.png"; bild.write_bytes(b"x")
    monkeypatch.setattr(rw.requests, "post", lambda *a, **k: Antwort(
        dienstantwort(["Zeile"])))
    rw.ocr_zeilen(bild)
    assert "GPU" in rw._OCR_QUELLE and "v6" in rw._OCR_QUELLE


def test_doc_ori_wird_angefordert_unwarp_nicht(rw, tmp_path, monkeypatch):
    """`unwarp` meldet der Dienst selbst als gemessen schädlich."""
    bild = tmp_path / "b.png"; bild.write_bytes(b"x")
    gerufen = {}

    def merken(url, **kw):
        gerufen["url"] = url
        return Antwort(dienstantwort(["Zeile"]))
    monkeypatch.setattr(rw.requests, "post", merken)
    rw.ocr_zeilen(bild)
    assert "doc_ori=1" in gerufen["url"]
    assert "unwarp" not in gerufen["url"]


# ————— Der Rückfall —————

def test_faellt_der_dienst_aus_liest_die_eingebaute_lane(rw, tmp_path, monkeypatch):
    """Ein Beleg, der nicht gelesen wird, weil ein Dienst weg ist, wäre der
    schlechtere Tausch."""
    bild = tmp_path / "b.png"; bild.write_bytes(b"x")

    def kaputt(*a, **k):
        raise ConnectionError("Dienst weg")
    monkeypatch.setattr(rw.requests, "post", kaputt)

    class Attrappe:
        def predict(self, _):
            return [{"rec_texts": ["Notlesung"], "rec_scores": [0.8],
                     "rec_polys": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}]
    monkeypatch.setattr(rw, "ocr_engine", lambda: Attrappe())
    assert rw.ocr_zeilen(bild) == [("Notlesung", 0.8)]
    assert "CPU" in rw._OCR_QUELLE


def test_ein_fehlercode_gilt_als_ausfall(rw, tmp_path, monkeypatch):
    bild = tmp_path / "b.png"; bild.write_bytes(b"x")
    monkeypatch.setattr(rw.requests, "post", lambda *a, **k: Antwort(
        {"errorCode": 7, "errorMsg": "Bild unlesbar"}))

    class Attrappe:
        def predict(self, _):
            return [{"rec_texts": ["Rückfall"], "rec_scores": [0.5],
                     "rec_polys": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}]
    monkeypatch.setattr(rw, "ocr_engine", lambda: Attrappe())
    assert rw.ocr_zeilen(bild)[0][0] == "Rückfall"


def test_eine_leere_antwort_gilt_als_ausfall(rw, tmp_path, monkeypatch):
    bild = tmp_path / "b.png"; bild.write_bytes(b"x")
    monkeypatch.setattr(rw.requests, "post", lambda *a, **k: Antwort(
        {"errorCode": 0, "result": {"ocrResults": []}}))

    class Attrappe:
        def predict(self, _):
            return [{"rec_texts": ["Rückfall"], "rec_scores": [0.5],
                     "rec_polys": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}]
    monkeypatch.setattr(rw, "ocr_engine", lambda: Attrappe())
    assert rw.ocr_zeilen(bild)[0][0] == "Rückfall"


def test_ohne_dienstadresse_gar_kein_versuch(rw, tmp_path, monkeypatch):
    """OCR_DIENST leeren schaltet den Dienst ab — für Notfälle."""
    bild = tmp_path / "b.png"; bild.write_bytes(b"x")
    monkeypatch.setattr(rw, "OCR_DIENST", "")

    def darf_nicht(*a, **k):
        raise AssertionError("es wurde doch gerufen")
    monkeypatch.setattr(rw.requests, "post", darf_nicht)

    class Attrappe:
        def predict(self, _):
            return [{"rec_texts": ["lokal"], "rec_scores": [0.9],
                     "rec_polys": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}]
    monkeypatch.setattr(rw, "ocr_engine", lambda: Attrappe())
    assert rw.ocr_zeilen(bild)[0][0] == "lokal"
