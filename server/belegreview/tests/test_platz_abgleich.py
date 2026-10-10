"""Der tägliche Abgleich des Platzes (box.inhalt_bytes, taeglich.schritt_platz).

Gemessen wird gegen einen WIRKLICHEN Bare-Store, den der Test selbst anlegt
und mit Dateien bekannter Größe füllt — nicht gegen eine ersetzte Zählung.
Nur die Zuordnung Verweis → Store ist ersetzt; die gehört nicht hierher.

Die beiden Zusagen, die zählen:
  * gezählt wird der INHALT des Standes, nicht das Git-Verzeichnis (lose
    Objekte blähen `.git` vorübergehend um das Dreißigfache auf),
  * ist nichts messbar, bleibt der alte Wert stehen — ein Messfehler darf
    kein Kontingent verändern.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import babu_web  # noqa: E402
import box as bx  # noqa: E402
import mandanten  # noqa: E402
import paket  # noqa: E402

from test_kern_abo import welt  # noqa: E402,F401

_spec = importlib.util.spec_from_file_location(
    "taeglich", HIER.parents[2] / "werkzeuge" / "taeglich.py")
taeglich = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(taeglich)


def _git(store: Path, *args: str, **kw):
    r = subprocess.run(["git", "-C", str(store), *args], capture_output=True,
                       text=True, **kw)
    assert r.returncode == 0, r.stderr
    return r.stdout


def _store_mit(tmp_path: Path, dateien: dict[str, bytes]) -> Path:
    """Ein echter Bare-Store mit genau diesen Dateien im Stand `main`."""
    arbeit, store = tmp_path / "arbeit", tmp_path / "store.git"
    arbeit.mkdir(parents=True)
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(store))
    _git(tmp_path, "init", "-q", "-b", "main", str(arbeit))
    for name, inhalt in dateien.items():
        ziel = arbeit / name
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(inhalt)
    _git(arbeit, "add", "-A")
    _git(arbeit, "-c", "user.name=suite", "-c", "user.email=suite@test",
         "commit", "-q", "-m", "stand")
    _git(arbeit, "push", "-q", str(store), "HEAD:refs/heads/main")
    _git(store, "symbolic-ref", "HEAD", "refs/heads/main")
    return store


def _box(store: Path, mandant_id: int = 1) -> bx.Box:
    return bx.Box(mandant_id=mandant_id, store=store, ref="babu/suite/belege",
                  klon=store.parent / "klon")


# ---------------------------------------------------------------------------
# Die Messung selbst
# ---------------------------------------------------------------------------

def test_zaehlt_den_inhalt_des_standes(tmp_path):
    dateien = {"belege/a.jpg": b"x" * 500_000,
               "belege/b.jpg": b"y" * 123_456,
               "review/a.json": b"{}" * 7}
    store = _store_mit(tmp_path, dateien)
    assert bx.inhalt_bytes(_box(store)) == sum(len(v) for v in dateien.values())


def test_die_geschichte_zaehlt_nicht_mit(tmp_path):
    """Wer einen Beleg ersetzt, zahlt nicht für beide Fassungen."""
    store = _store_mit(tmp_path, {"belege/a.jpg": b"x" * 400_000})
    arbeit = tmp_path / "arbeit"
    (arbeit / "belege" / "a.jpg").write_bytes(b"z" * 10_000)
    _git(arbeit, "add", "-A")
    _git(arbeit, "-c", "user.name=suite", "-c", "user.email=suite@test",
         "commit", "-q", "-m", "ersetzt")
    _git(arbeit, "push", "-q", str(store), "HEAD:refs/heads/main")
    assert bx.inhalt_bytes(_box(store)) == 10_000


def test_leerer_stand_ist_null_nicht_unmessbar(tmp_path):
    store = _store_mit(tmp_path, {".0711/container.json": b"{}"})
    assert bx.inhalt_bytes(_box(store)) == 2


def test_store_ohne_stand_ist_nicht_messbar(tmp_path):
    store = tmp_path / "leer.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(store))
    assert bx.inhalt_bytes(_box(store)) is None


def test_store_weg_ist_nicht_messbar(tmp_path):
    assert bx.inhalt_bytes(_box(tmp_path / "gibtsnicht.git")) is None


# ---------------------------------------------------------------------------
# Der Schritt im täglichen Lauf
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_betrieb(welt, monkeypatch, tmp_path):
    """Der Salon aus `test_kern_abo.welt`, aber als Betrieb aus dem App Store."""
    store = _store_mit(tmp_path / "box", {"belege/a.jpg": b"x" * 777_000})
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET herkunft=?, box_ref=?, status='aktiv', "
                  "speicher_bytes=?, belege_gesamt=? WHERE id=?",
                  (paket.HERKUNFT_APP, "babu/salon-sonne-1/belege", 10, 4,
                   welt["mid"]))
    monkeypatch.setattr(taeglich, "_meldungen_fuer_betrieb", lambda m, h: [])
    monkeypatch.setattr(bx, "box_aus_ref", lambda mid, ref: _box(store, mid))
    return {**welt, "store": store}


def _stand(mid):
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        return mandanten.abo_stand(mid, c=c)


def test_der_lauf_zieht_die_bytes_nach(app_betrieb):
    assert taeglich.main(["--nur", "platz"]) == 0
    stand = _stand(app_betrieb["mid"])
    assert stand["speicher_bytes"] == 777_000
    # Die Belegzahl bleibt: sie zählt Ereignisse, nicht Bytes.
    assert stand["belege_gesamt"] == 4


def test_die_probe_misst_aber_schreibt_nicht(app_betrieb):
    assert taeglich.main(["--probe", "--nur", "platz"]) == 0
    assert _stand(app_betrieb["mid"])["speicher_bytes"] == 10


def test_unmessbare_box_laesst_den_alten_wert_stehen(app_betrieb, monkeypatch):
    monkeypatch.setattr(bx, "inhalt_bytes", lambda box, timeout=120: None)
    assert taeglich.main(["--nur", "platz"]) == 0
    assert _stand(app_betrieb["mid"])["speicher_bytes"] == 10


def test_ein_fehler_an_einer_box_kippt_den_lauf_nicht(app_betrieb, monkeypatch):
    def kaputt(box, timeout=120):
        raise OSError("Store weg")
    monkeypatch.setattr(bx, "inhalt_bytes", kaputt)
    assert taeglich.main(["--nur", "platz"]) == 0
    assert _stand(app_betrieb["mid"])["speicher_bytes"] == 10


def test_portal_betriebe_werden_nicht_angefasst(welt, monkeypatch, tmp_path):
    """Die Zusage an jeden Betrieb, der schon da ist."""
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET box_ref=?, status='aktiv', speicher_bytes=? "
                  "WHERE id=?", ("babu/salon-sonne-1/belege", 42, welt["mid"]))
    gemessen = []
    monkeypatch.setattr(bx, "inhalt_bytes",
                        lambda box, timeout=120: gemessen.append(1) or 999)
    assert taeglich.main(["--nur", "platz"]) == 0
    assert gemessen == []
    assert _stand(welt["mid"])["speicher_bytes"] == 42


def test_platz_ist_teil_des_ganzen_laufs():
    assert "platz" in taeglich.SCHRITTE
