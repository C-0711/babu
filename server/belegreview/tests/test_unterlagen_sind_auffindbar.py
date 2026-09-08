"""Verträge und Post vom Amt werden eingebettet — und der Chat findet sie.

Gemessen am 08.09.2026 in Ninas Belegbox: **276 von 276 Belegen** trugen
einen Vektor (`review/<stamm>.embedding.json`), **13 Dokumente keinen
einzigen**. Verträge und Behördenpost wurden also gelesen, erklärt und in
der Liste angezeigt — für die Suche des Chats existierten sie nicht. Wer
nach seiner Kündigungsfrist fragte, bekam eine Antwort aus Belegen und
Kompendium, während der Mietvertrag daneben lag.

Eingebettet wird mit demselben Modell und denselben Präfixen wie die
Belege (EmbeddingGemma über `embedding_rechnen`), und aus demselben Text,
der hinterher zitiert wird — `dokument_markdown`. Was die Suche findet,
ist genau das, was ein Mensch nachlesen kann.

Kontoauszüge bleiben bewusst draußen: eine Umsatzliste ist keine Prosa,
und sie steht dem Chat monatsweise ohnehin im Weltblock zur Verfügung.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import babu_web  # noqa: E402
import box as bx  # noqa: E402
import boxschreiber  # noqa: E402

PFAD = "dokumente/2026-09/20260901-100000-aaa111-Mietvertrag.pdf"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    """Eine Box mit einem gelesenen Vertrag und einem erklärten Amtsbrief."""
    arbeit = tmp_path / "arbeit"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    _git(arbeit, "config", "user.name", "t")
    _git(arbeit, "config", "user.email", "t@l")

    def leg(pfad: str, inhalt: bytes) -> None:
        p = arbeit / pfad
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(inhalt)

    leg(PFAD, b"%PDF-1.4")
    leg(PFAD + ".meta.json", json.dumps(
        {"titel": "Mietvertrag Salonräume", "art": "vertrag"}).encode())
    leg(PFAD + ".vertrag.json", json.dumps({
        "art": "miete", "partner": "Hausverwaltung Weber",
        "betrag_monat": 1450.0, "zahlweise": "monatlich",
        "kuendigungsfrist": "drei Monate zum Quartalsende",
        "laufzeit_bis": "2029-12-31",
        "einfach": "Du mietest die Räume in der Kirchstraße 4."}).encode())

    brief = "dokumente/2026-09/20260902-090000-bbb222-Finanzamt.pdf"
    leg(brief, b"%PDF-1.4")
    leg(brief + ".meta.json", json.dumps(
        {"titel": "Bescheid Umsatzsteuer", "art": "behoerde"}).encode())
    leg(brief + ".erklaerung.json", json.dumps({
        "absender": "Finanzamt Ludwigsburg", "datum": "2026-08-28",
        "einfach": "Das Finanzamt setzt deine Umsatzsteuer für Juli fest.",
        "was_tun": "Überweise 412,80 Euro.",
        "bis_wann": "bis zum 10. September"}).encode())

    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "stand")
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)],
                   check=True)

    bx.registry_leeren()
    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    yield babu_web, brief
    bx.registry_leeren()


# ————— Der Text, aus dem der Vektor entsteht —————

def test_der_vertrag_traegt_seine_frist_im_text(welt):
    bw, _ = welt
    text = bw._dokument_text(PFAD)  # noqa: SLF001
    assert "Mietvertrag Salonräume" in text
    assert "Hausverwaltung Weber" in text
    assert "drei Monate zum Quartalsende" in text
    assert "Kirchstraße 4" in text


def test_der_amtsbrief_traegt_was_zu_tun_ist(welt):
    bw, brief = welt
    text = bw._dokument_text(brief)  # noqa: SLF001
    assert "Finanzamt Ludwigsburg" in text
    assert "412,80" in text
    assert "bis zum 10. September" in text


def test_ohne_beiakten_gibt_es_keinen_text(welt):
    """Ein Dokument, das noch nicht gelesen wurde, wird nicht eingebettet —
    ein Vektor über einen leeren Kopf fände alles und nichts."""
    bw, _ = welt
    assert bw._dokument_text("dokumente/2026-09/gibt-es-nicht.pdf") is None  # noqa: SLF001


# ————— Der Vektor landet in der Box und in der Matrix —————

def test_der_vektor_wird_neben_das_dokument_gelegt(welt, monkeypatch):
    bw, _ = welt
    monkeypatch.setattr(bw, "embedding_rechnen",
                        lambda text, als_dokument=True: {
                            "modell": "test", "dim": 3, "vektor": [1.0, 0.0, 0.0]})
    assert bw.dokument_vektor_ablegen(PFAD, "nina@0711.io") is True
    beiakte = bw.git_show(PFAD + ".embedding.json")
    assert beiakte is not None
    assert json.loads(beiakte)["vektor"] == [1.0, 0.0, 0.0]


def test_ohne_embedding_dienst_geht_nichts_verloren(welt, monkeypatch):
    """Der Vertrag bleibt gelesen, auch wenn der Vektor gerade nicht geht —
    der Nachtrag holt ihn später."""
    bw, _ = welt
    monkeypatch.setattr(bw, "embedding_rechnen",
                        lambda text, als_dokument=True: None)
    assert bw.dokument_vektor_ablegen(PFAD, "nina@0711.io") is False
    assert bw.git_show(PFAD + ".vertrag.json") is not None


def test_die_matrix_kennt_die_eingebetteten_unterlagen(welt, monkeypatch):
    bw, brief = welt
    vektoren = {PFAD: [1.0, 0.0, 0.0], brief: [0.0, 1.0, 0.0]}
    monkeypatch.setattr(bw, "embedding_rechnen",
                        lambda text, als_dokument=True: {"vektor": [1.0, 0.0, 0.0]})
    for pfad, v in vektoren.items():
        monkeypatch.setattr(bw, "embedding_rechnen",
                            lambda text, als_dokument=True, _v=v: {"vektor": _v})
        bw.dokument_vektor_ablegen(pfad, "nina@0711.io")

    pfade, matrix = bw._dokument_vektoren()  # noqa: SLF001
    assert sorted(pfade) == sorted(vektoren)
    assert matrix is not None and matrix.shape == (2, 3)


def test_die_beiakte_taucht_nicht_als_eigenes_dokument_auf(welt, monkeypatch):
    """Sonst stünde in Ninas Unterlagen-Liste eine Datei namens
    `Mietvertrag.pdf.embedding.json`."""
    bw, _ = welt
    monkeypatch.setattr(bw, "embedding_rechnen",
                        lambda text, als_dokument=True: {"vektor": [1.0, 0.0, 0.0]})
    bw.dokument_vektor_ablegen(PFAD, "nina@0711.io")
    with bw._box().index_schloss:  # noqa: SLF001
        bw._box().invalidieren()  # noqa: SLF001
    namen = [d["pfad"] for d in bw.index_aktuell()["dokumente"]]
    assert PFAD in namen
    assert not any(n.endswith(".embedding.json") for n in namen), namen


# ————— Und der Chat findet sie —————

def test_die_recherche_zitiert_die_passende_unterlage(welt, monkeypatch):
    """Der eigentliche Punkt: nach der Kündigungsfrist gefragt, liegt der
    Mietvertrag im Prompt — vorher fand der Chat dort nichts."""
    bw, brief = welt
    monkeypatch.setattr(bw, "embedding_rechnen",
                        lambda text, als_dokument=True: {"vektor": [1.0, 0.0, 0.0]})
    bw.dokument_vektor_ablegen(PFAD, "nina@0711.io")
    monkeypatch.setattr(bw, "embedding_rechnen",
                        lambda text, als_dokument=True: {"vektor": [0.0, 1.0, 0.0]})
    bw.dokument_vektor_ablegen(brief, "nina@0711.io")

    import kompendium
    monkeypatch.setattr(kompendium, "suchen", lambda v, k=5: [])
    monkeypatch.setattr(bw, "_wissen_treffer", lambda v, k=5: [])
    # Die Frage zeigt in Richtung Mietvertrag.
    monkeypatch.setattr(bw, "embedding_rechnen",
                        lambda text, als_dokument=True: {"vektor": [1.0, 0.0, 0.0]})

    text = bw._recherche("Wie lange ist meine Kündigungsfrist?")  # noqa: SLF001
    assert "PASSENDE EIGENE UNTERLAGEN" in text
    assert "drei Monate zum Quartalsende" in text
    # Und der Amtsbrief, der nicht dazu passt, bleibt draußen.
    assert "Finanzamt Ludwigsburg" not in text
