"""PDFium ist nicht threadsicher — ohne Schloss stürzt der Prozess ab.

Am 02.09.2026 lief der Wissen-Hintergrund-Job (`_wissen_job`) für zwei
Uploads gleichzeitig, beide lasen ein PDF über `abschluss_lesen.seiten_text`
— der Produktivcontainer riss mit `AssertionError` in
`pypdfium2/internal/bases.py` ab, Docker startete ihn neu. `PDFIUM_LOCK`
serialisiert jeden Zugriff; dieser Test belegt das, statt es nur zu
behaupten, indem er ohne das Schloss zuverlässig denselben Absturz auslöst.
"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import abschluss_lesen as al  # noqa: E402

from test_abschluss import _text_pdf  # noqa: E402


def _viele_seiten_pdf(n: int) -> bytes:
    """Ein PDF mit `n` Seiten — mehr Seiten heißt mehr pdfium-Objekte
    gleichzeitig offen, was den Wettlauf zuverlässiger auslöst."""
    return _text_pdf([f"Zeile {i}" for i in range(n)])


def test_seiten_text_ist_unter_parallelen_aufrufen_stabil(tmp_path):
    pfade = []
    for i in range(6):
        p = tmp_path / f"parallel-{i}.pdf"
        p.write_bytes(_viele_seiten_pdf(30))
        pfade.append(p)

    fehler: list[BaseException] = []

    def _lesen(pfad):
        try:
            for _ in range(4):
                seiten = al.seiten_text(pfad)
                assert seiten and seiten[0].startswith("Zeile 0")
        except BaseException as ex:  # noqa: BLE001 — auch harte Abstürze fangen
            fehler.append(ex)

    faeden = [threading.Thread(target=_lesen, args=(p,)) for p in pfade for _ in range(3)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()

    assert not fehler, f"pdfium ist unter paralleler Nutzung abgestürzt: {fehler!r}"


def test_seiten_bilder_ist_unter_parallelen_aufrufen_stabil(tmp_path):
    pfade = []
    for i in range(4):
        p = tmp_path / f"parallel-bild-{i}.pdf"
        p.write_bytes(_viele_seiten_pdf(15))
        pfade.append(p)

    fehler: list[BaseException] = []

    def _rendern(pfad):
        try:
            for _ in range(3):
                bilder = al.seiten_bilder(pfad)
                assert bilder
        except BaseException as ex:  # noqa: BLE001
            fehler.append(ex)

    faeden = [threading.Thread(target=_rendern, args=(p,)) for p in pfade for _ in range(3)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()

    assert not fehler, f"pdfium ist unter paralleler Nutzung abgestürzt: {fehler!r}"


def test_gemischter_text_und_bild_zugriff_teilt_sich_ein_schloss(tmp_path):
    """`seiten_text` und `seiten_bilder` benutzen dasselbe `PDFIUM_LOCK` —
    dieser Test läuft nur durch, wenn beide wirklich serialisiert sind."""
    pfad = tmp_path / "gemischt.pdf"
    pfad.write_bytes(_viele_seiten_pdf(20))

    fehler: list[BaseException] = []

    def _text():
        try:
            for _ in range(4):
                al.seiten_text(pfad)
        except BaseException as ex:  # noqa: BLE001
            fehler.append(ex)

    def _bild():
        try:
            for _ in range(4):
                al.seiten_bilder(pfad)
        except BaseException as ex:  # noqa: BLE001
            fehler.append(ex)

    faeden = [threading.Thread(target=_text) for _ in range(3)] + \
             [threading.Thread(target=_bild) for _ in range(3)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()

    assert not fehler, f"pdfium ist unter paralleler Nutzung abgestürzt: {fehler!r}"


def test_kontoauszug_teilt_sich_dasselbe_schloss(tmp_path):
    import kontoauszug as ka  # noqa: PLC0415

    assert ka is not None  # nur der Import-Pfad zählt hier
    pfad = tmp_path / "auszug.pdf"
    pfad.write_bytes(_viele_seiten_pdf(10))

    fehler: list[BaseException] = []

    def _auszug():
        try:
            for _ in range(3):
                ka.parse_pdf(str(pfad))
        except BaseException as ex:  # noqa: BLE001
            fehler.append(ex)

    def _text():
        try:
            for _ in range(3):
                al.seiten_text(pfad)
        except BaseException as ex:  # noqa: BLE001
            fehler.append(ex)

    faeden = [threading.Thread(target=_auszug) for _ in range(3)] + \
             [threading.Thread(target=_text) for _ in range(3)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()

    assert not fehler, f"pdfium ist unter paralleler Nutzung abgestürzt: {fehler!r}"
