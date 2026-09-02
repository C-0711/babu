"""Zwei Belegboxen im selben Prozess dürfen einander nicht sehen.

Bis Plan 21 standen Store, Klon und der ganze Index-Zustand als Modul-
globals in `babu_web` — für genau EINE Box. Ein zweiter Mandant hätte in
denselben Index geschrieben und in derselben Arbeitskopie committet: der
Beleg von Salon A wäre in der Liste von Salon B aufgetaucht, und zwei
Threads hätten sich im selben Klon den git-Index weggeräumt.

Diese Datei baut deshalb ZWEI synthetische Boxen (nach dem Muster der
`welt`-Fixture aus `test_mehrseiten_buendel.py`) und prüft dreierlei:

1. Was in Box A geschrieben wird, steht nur in Box A.
2. Der Index von Box A kennt nur die Belege von Box A.
3. `box_von(un)` ohne Mandanten liefert exakt den Stand von heute —
   `STORE`, `REF` und `KLON`, wie sie ohne diesen Umbau gälten. Das ist die
   Zusicherung, an der der Golden-Diff des Deploy-Rituals hängt.
"""
import contextlib
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import babu_web  # noqa: E402
import box as bx  # noqa: E402
import boxschreiber  # noqa: E402


def _bare(tmp_path: Path, name: str, belege: list[str]) -> Path:
    """Ein bare-Store mit ein paar Belegen darin — wie eine echte Box."""
    arbeit = tmp_path / f"arbeit-{name}"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "README.md").write_text(name)
    for beleg in belege:
        ziel = arbeit / "docs" / "2026-05" / beleg
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(b"\xff\xd8\xff\xe0" + beleg.encode())
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "stand"],
                   check=True, capture_output=True)
    bare = tmp_path / f"{name}.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)],
                   check=True)
    return bare


def _im_stand(bare: Path) -> list[str]:
    r = subprocess.run(["git", "--git-dir", str(bare), "ls-tree", "-r",
                        "--name-only", "HEAD"], capture_output=True, text=True)
    return r.stdout.splitlines()


@contextlib.contextmanager
def _in_box(box: bx.Box):
    """Für die Dauer des Blocks ist DAS die aktive Box.

    Mit `reset` und nicht mit einem zweiten `set`: eine ContextVar behält
    ihren Wert für den ganzen Thread, und ein vergessenes Zurücksetzen
    verschöbe die Box in den nächsten Test.
    """
    marke = babu_web._AKTIVE_BOX.set(box)
    try:
        yield box
    finally:
        babu_web._AKTIVE_BOX.reset(marke)


@pytest.fixture()
def welten(tmp_path, monkeypatch):
    """Zwei Boxen nebeneinander: eigener Store, eigener Klon, eigener Zustand."""
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    bx.registry_leeren()

    bare1 = _bare(tmp_path, "eins", ["20260501-120000-aaa111-alpha.jpg"])
    bare2 = _bare(tmp_path, "zwei", ["20260501-120000-bbb222-beta.jpg"])
    welt1 = bx.Box(mandant_id=None, store=bare1, ref="inspektor/ws-eins/babu",
                   klon=tmp_path / "klon-eins", remote=str(bare1))
    welt2 = bx.Box(mandant_id=2, store=bare2, ref="inspektor/ws-zwei/babu",
                   klon=tmp_path / "klon-zwei", remote=str(bare2))
    yield welt1, welt2, bare1, bare2
    bx.registry_leeren()


def test_geschriebenes_bleibt_in_seiner_box(welten):
    welt1, welt2, bare1, bare2 = welten
    boxschreiber.schreiben(welt1, "docs/2026-05/nur-in-eins.txt", b"1",
                           "aufnahme: eins", "nina@0711.io")
    boxschreiber.schreiben(welt2, "docs/2026-05/nur-in-zwei.txt", b"2",
                           "aufnahme: zwei", "nina@0711.io")

    eins, zwei = _im_stand(bare1), _im_stand(bare2)
    assert "docs/2026-05/nur-in-eins.txt" in eins
    assert "docs/2026-05/nur-in-zwei.txt" not in eins
    assert "docs/2026-05/nur-in-zwei.txt" in zwei
    assert "docs/2026-05/nur-in-eins.txt" not in zwei


def test_jede_box_hat_ihre_eigene_arbeitskopie(welten):
    """Ein gemeinsamer Klon wäre der stille Fehler: der `reset --hard` der
    einen Box räumt der anderen die Datei aus dem Index."""
    welt1, welt2, _, _ = welten
    boxschreiber.schreiben(welt1, "docs/2026-05/a.txt", b"a", "aufnahme: a", "n")
    boxschreiber.schreiben(welt2, "docs/2026-05/b.txt", b"b", "aufnahme: b", "n")
    assert welt1.klon != welt2.klon
    assert (welt1.klon / "docs/2026-05/a.txt").exists()
    assert not (welt1.klon / "docs/2026-05/b.txt").exists()
    assert (welt2.klon / "docs/2026-05/b.txt").exists()
    assert welt1.schloss is not welt2.schloss


def test_der_index_zeigt_nur_die_eigenen_belege(welten):
    welt1, welt2, _, _ = welten
    with _in_box(welt1):
        belege1 = set(babu_web.index_aktuell()["belege"])
    with _in_box(welt2):
        belege2 = set(babu_web.index_aktuell()["belege"])

    assert any("alpha" in b for b in belege1)
    assert not any("beta" in b for b in belege1)
    assert any("beta" in b for b in belege2)
    assert not any("alpha" in b for b in belege2)
    assert welt1.index is not welt2.index


def test_invalidieren_trifft_nur_die_eigene_box(welten):
    welt1, welt2, _, _ = welten
    with _in_box(welt1):
        babu_web.index_aktuell()
    with _in_box(welt2):
        babu_web.index_aktuell()
    assert welt1.index["geprueft"] > 0 and welt2.index["geprueft"] > 0

    welt1.invalidieren()
    assert welt1.index["geprueft"] == 0.0
    assert welt2.index["geprueft"] > 0.0


def test_git_liest_aus_der_aktiven_box(welten):
    welt1, welt2, _, _ = welten
    with _in_box(welt1):
        assert babu_web.git_show("README.md") == b"eins"
    with _in_box(welt2):
        assert babu_web.git_show("README.md") == b"zwei"


# ---------------------------------------------------------------------------
# Der Alt-Pfad: eine Box, und zwar genau die von heute.
# ---------------------------------------------------------------------------

def test_default_box_ist_der_stand_von_heute(tmp_path, monkeypatch):
    """Ohne Mandanten kommt exakt heraus, was ohne den Umbau gälte."""
    bx.registry_leeren()
    monkeypatch.setattr(babu_web, "STORE", tmp_path / "babu.git")
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REF", "inspektor/ws-christoph0711.io/babu")
    monkeypatch.setattr(boxschreiber, "REMOTE", "http://127.0.0.1:7808/git/x.git")

    b = bx.box_von("nina@0711.io")
    assert b.mandant_id is None
    assert b.store == babu_web.STORE
    assert b.klon == boxschreiber.KLON
    assert b.ref == boxschreiber.REF
    assert b.remote == boxschreiber.REMOTE
    bx.registry_leeren()


def test_default_box_folgt_umgebogenem_store(tmp_path, monkeypatch):
    """Die Werte werden bei jedem Aufruf gelesen, nicht beim Import
    eingefroren — sonst zeigte ein Test auf den echten Produktiv-Store."""
    bx.registry_leeren()
    monkeypatch.setattr(babu_web, "STORE", tmp_path / "eins.git")
    erste = bx.box_von("nina@0711.io")
    monkeypatch.setattr(babu_web, "STORE", tmp_path / "zwei.git")
    zweite = bx.box_von("nina@0711.io")
    assert erste is not zweite
    assert zweite.store == tmp_path / "zwei.git"
    bx.registry_leeren()


def test_dieselbe_box_ist_dasselbe_objekt(tmp_path, monkeypatch):
    """Zwei Objekte hießen zwei Schlösser hieße zwei Schreiber im Klon."""
    bx.registry_leeren()
    monkeypatch.setattr(babu_web, "STORE", tmp_path / "babu.git")
    assert bx.box_von("nina@0711.io") is bx.box_von("nina@0711.io")
    bx.registry_leeren()


def test_registry_waechst_nicht_ueber_die_grenze(tmp_path, monkeypatch):
    bx.registry_leeren()
    monkeypatch.setattr(bx, "BOX_MAX", 5)
    for i in range(20):
        bx.box_aus_ref(i, f"inspektor/ws-{i}/babu")
    assert len(bx._BOX_REGISTRY) <= 5
    bx.registry_leeren()


def test_eine_box_in_arbeit_wird_nicht_verdraengt(tmp_path, monkeypatch):
    """Wer gerade schreibt, darf nicht unter der Hand ein zweites Objekt
    mit einem zweiten Schloss bekommen."""
    bx.registry_leeren()
    monkeypatch.setattr(bx, "BOX_MAX", 2)
    fest = bx.box_aus_ref(1, "inspektor/ws-fest/babu")
    with fest.schloss:
        for i in range(10):
            bx.box_aus_ref(100 + i, f"inspektor/ws-{i}/babu")
        assert bx.box_aus_ref(1, "inspektor/ws-fest/babu") is fest
    bx.registry_leeren()


def test_die_ref_konvention_trifft_den_produktivpfad(monkeypatch):
    """`inspektor/ws-<x>/babu` → `<wurzel>/inspektor/ws-<x>/babu.git`.

    Für den Produktiv-Ref muss dabei exakt der heutige `BABU_STORE`
    herauskommen — sonst ist die Konvention geraten und nicht beschrieben.
    """
    monkeypatch.setattr(bx, "STORE_WURZEL", Path("/srv/inspektor-store"))
    assert bx.store_aus_ref("inspektor/ws-christoph0711.io/babu") == Path(
        "/srv/inspektor-store/inspektor/ws-christoph0711.io/babu.git")
    monkeypatch.setattr(bx, "KLON_WURZEL", Path("/srv/boxen"))
    assert bx.klon_aus_ref("inspektor/ws-nina.de/babu") == Path("/srv/boxen/ws-nina.de")

