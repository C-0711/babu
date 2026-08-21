"""Der Schreibpfad in die Belegbox: gleichzeitig, ehrlich und eingehegt.

Die Belegbox ist Beweismittel. Ein Commit, der den falschen Inhalt unter dem
falschen Namen trägt, fällt niemandem auf — deshalb steht hier, was passiert,
wenn mehrere Threads zugleich schreiben.
"""
import subprocess
import sys
import threading
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
import boxschreiber  # noqa: E402


@pytest.fixture()
def box(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "README.md").write_text("box")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "start"],
                   check=True, capture_output=True)
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    return bare


def _log(bare: Path) -> list[str]:
    return subprocess.run(["git", "-C", str(bare), "log", "--format=%s|%an"],
                          capture_output=True, text=True).stdout.strip().split("\n")


def _inhalt(bare: Path, pfad: str) -> bytes:
    return subprocess.run(["git", "-C", str(bare), "show", f"HEAD:{pfad}"],
                          capture_output=True).stdout


def test_gleichzeitige_schreiber_verlieren_nichts(box):
    """Portal-Upload und Hintergrund-Job treffen sich auf EINER Arbeitskopie.

    Ohne Schloss räumt der `reset --hard` des einen dem anderen die Datei aus
    dem Index — der Commit trägt dann fremden Inhalt unter falschem Namen.
    """
    # Erst einmal allein schreiben: ab jetzt ist der Klon warm, und das Rennen
    # geht um Index und `reset --hard` — der Fall, der still schiefgeht.
    boxschreiber.schreiben("docs/2026-08/start.txt", b"start", "aufnahme: start", "nina")

    fehler: list[Exception] = []

    def schreibe(i: int) -> None:
        try:
            boxschreiber.schreiben(f"docs/2026-08/beleg-{i}.txt",
                                   f"Inhalt {i}".encode(),
                                   f"aufnahme: beleg-{i}", f"nutzerin-{i}")
        except Exception as e:  # noqa: BLE001
            fehler.append(e)

    threads = [threading.Thread(target=schreibe, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not fehler, f"Schreiber gescheitert: {fehler}"
    zeilen = _log(box)
    for i in range(6):
        assert f"aufnahme: beleg-{i}|nutzerin-{i}" in zeilen, \
            f"beleg-{i} fehlt oder trägt den falschen Namen"
        assert _inhalt(box, f"docs/2026-08/beleg-{i}.txt") == f"Inhalt {i}".encode()


def test_ein_commit_je_schreibvorgang(box):
    """Kein Fremdgepäck: ein Commit enthält genau seine eigenen Dateien."""
    boxschreiber.schreiben("docs/2026-08/a.txt", b"A", "aufnahme: a", "nina")
    boxschreiber.schreiben({"docs/2026-08/b.txt": b"B",
                            "docs/2026-08/b.txt.meta.json": b"{}"},
                           None, "aufnahme: b", "nina")
    geaendert = subprocess.run(
        ["git", "-C", str(box), "show", "--name-only", "--format=", "HEAD"],
        capture_output=True, text=True).stdout.split()
    assert sorted(geaendert) == ["docs/2026-08/b.txt", "docs/2026-08/b.txt.meta.json"]


@pytest.mark.parametrize("pfad", [
    "/etc/passwd",                       # absolut: `KLON / "/etc/x"` ist "/etc/x"
    "../ausserhalb.txt",
    "docs/../../weg.txt",
    "docs/2026-08/beleg;rm.txt",
])
def test_pfade_ausserhalb_der_box_werden_abgewiesen(box, pfad):
    with pytest.raises(boxschreiber.SchreibFehler):
        boxschreiber.schreiben(pfad, b"x", "test", "nina")


def test_kaputte_arbeitskopie_meldet_sich(box, monkeypatch):
    """Stiller Fehlschlag wäre das Schlimmste: dann steht ein Commit in der
    Historie, dessen Inhalt nie geschrieben wurde."""
    echt = boxschreiber._git

    def kaputt(*args, **kwargs):
        if args and args[0] == "add":
            class Fehlschlag:
                returncode = 1
                stderr = "index.lock existiert"
                stdout = ""
            return Fehlschlag()
        return echt(*args, **kwargs)

    monkeypatch.setattr(boxschreiber, "_git", kaputt)
    with pytest.raises(boxschreiber.SchreibFehler, match="Vormerken"):
        boxschreiber.schreiben("docs/2026-08/x.txt", b"x", "aufnahme: x", "nina")
