"""Zwei Betriebe teilen nie eine Arbeitskopie — auch nicht im selben Namensraum.

Befund 27.09.2026 auf der H200V: Der Box-Anleger legte alle Boxen unter
`inspektor/ws-christoph0711.io/<betrieb>` an, `klon_aus_ref` nahm aber nur
den vorletzten Ordner als Namen. Alle Betriebe schrieben so durch EINE
Arbeitskopie `boxen/ws-christoph0711.io`, deren origin die Box des ersten
Betriebs war (Ninas `babu.git`): Belege der Kanzlei GKM (Mandant 3) standen
danach in Ninas Box, die eigene Box des Mandanten blieb leer.

Und: die erste Schreibung in eine leere Box scheiterte an
`reset --hard origin/main` — es gibt dort noch kein `origin/main`.
"""
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import box as bx  # noqa: E402
import boxschreiber  # noqa: E402


def _leer(pfad: Path) -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(pfad)], check=True)
    return pfad


def _mit_stand(pfad: Path) -> Path:
    arbeit = pfad.parent / (pfad.name + ".arbeit")
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    (arbeit / "README.md").write_text("stand")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(arbeit), "-c", "user.name=t", "-c", "user.email=t@l",
                    "commit", "-q", "-m", "stand"], check=True)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(pfad)], check=True)
    return pfad


def _dateien(bare: Path) -> list[str]:
    r = subprocess.run(["git", "--git-dir", str(bare), "ls-tree", "-r", "--name-only",
                        "refs/heads/main"], capture_output=True, text=True)
    return r.stdout.splitlines()


@pytest.fixture()
def dienst(tmp_path, monkeypatch):
    """Ein Remote-Verzeichnis nach dem Muster `<gateway>/git/<ref>.git`."""
    monkeypatch.setenv("BABU_LESEN", "store")
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(boxschreiber, "GATEWAY", f"file://{tmp_path}/dienst")
    monkeypatch.setattr(boxschreiber, "REF", "babu/babu/belege")
    monkeypatch.setattr(bx, "KLON_WURZEL", tmp_path / "boxen")
    monkeypatch.setattr(bx, "STORE_WURZEL", tmp_path / "store")
    bx.registry_leeren()
    yield lambda ref: tmp_path / "dienst" / "git" / f"{ref}.git"
    bx.registry_leeren()


@pytest.mark.parametrize("eins,zwei", [
    ("inspektor/ws-christoph0711.io/babu", "inspektor/ws-christoph0711.io/nullsiebenelf-gmbh-3"),
    ("babu/salon-a-5/belege", "babu/salon-b-6/belege"),
])
def test_zwei_boxen_zwei_arbeitskopien(dienst, eins, zwei):
    assert bx.klon_aus_ref(eins) != bx.klon_aus_ref(zwei)


def test_beleg_landet_in_der_box_des_betriebs(dienst):
    """Der Fall vom 16.–18.09.: zwei Betriebe im selben Workspace-Ordner."""
    nina = _mit_stand(dienst("inspektor/ws-christoph0711.io/babu"))
    kanzlei = _mit_stand(dienst("inspektor/ws-christoph0711.io/nullsiebenelf-gmbh-3"))
    a = bx.box_aus_ref(2, "inspektor/ws-christoph0711.io/babu")
    b = bx.box_aus_ref(3, "inspektor/ws-christoph0711.io/nullsiebenelf-gmbh-3")
    # Eigene Arbeitskopie je Betrieb — sonst räumen zwei Schreiber mit zwei
    # Schlössern einander den git-Index weg und pushen ins falsche Remote.
    assert a.klon != b.klon
    assert a.schloss is not b.schloss
    boxschreiber.schreiben(a, "docs/2026-09/nina.pdf", b"%PDF nina", "aufnahme: nina", "nina")
    boxschreiber.schreiben(b, "docs/2026-09/oculus.pdf", b"%PDF oculus", "aufnahme: oculus", "gkm")
    assert "docs/2026-09/oculus.pdf" not in _dateien(nina)
    assert "docs/2026-09/nina.pdf" not in _dateien(kanzlei)
    assert "docs/2026-09/oculus.pdf" in _dateien(kanzlei)
    assert "docs/2026-09/nina.pdf" in _dateien(nina)


def test_erster_beleg_in_leerer_box(dienst):
    """Eine Box ohne jeden Commit nimmt den ersten Beleg an."""
    leer = _leer(dienst("babu/salon-probe-4/belege"))
    b = bx.box_aus_ref(4, "babu/salon-probe-4/belege")
    boxschreiber.schreiben(b, "docs/2026-09/erster.pdf", b"%PDF 1", "aufnahme: erster", "probe")
    assert _dateien(leer) == ["docs/2026-09/erster.pdf"]
    # Und der zweite Beleg läuft wieder über den normalen Weg (origin/main da).
    boxschreiber.schreiben(b, "docs/2026-09/zweiter.pdf", b"%PDF 2", "aufnahme: zweiter", "probe")
    assert _dateien(leer) == ["docs/2026-09/erster.pdf", "docs/2026-09/zweiter.pdf"]
