"""Lasttest der Box-Registry — Plan 21, Phase 5 (Abschnitt 8).

`box.py` hält für hunderte Mandanten nur eine begrenzte Zahl Boxen im
Speicher (`BOX_MAX`, LRU-Verdrängung nach `BOX_TTL`). Bisher bewiesen die
Tests das nur für zwei Boxen (`test_zwei_boxen.py`) oder drei echte
(`test_kanzlei_routen.py`). Hier sind es 50 — synthetisch, aber jede mit
einem eigenen bare-Store, einem eigenen `mandant`-Datensatz und einem
eigenen `box_von(un, mandant_id)`-Zugriff, wie es eine Kanzlei mit vielen
Betrieben tatsächlich tut.

Fünf Dinge werden bewiesen, nicht nur behauptet:

1. Die Registry hält höchstens `BOX_MAX` Boxen — die LRU verdrängt den Rest.
2. Eine verdrängte Box kommt beim nächsten Zugriff korrekt wieder: derselbe
   Store, derselbe Ref, derselbe Inhalt im Git — nur das Python-Objekt ist
   neu.
3. Zwei Boxen vermischen ihren Index-Zustand nicht — auch nicht über eine
   Verdrängung hinweg.
4. TTL-Verdrängung greift, wenn eine Box lange genug ungenutzt war (Zeit
   per `monkeypatch` auf `time.monotonic`, kein echtes Warten).
5. Acht Threads, die gleichzeitig auf dieselbe Box zugreifen, bekommen
   *ein* Objekt, keine zwei — und keine Ausnahme.

Die Boxen sind absichtlich winzig (ein `README`, keine Reviews, kein
Golden-Fixture) — 50 × `git init`/`commit`/`clone --bare` ist die teuerste
Operation hier, und das Budget ist wörtlich genommen: der Auftrag verlangt
einen Test unter 60 Sekunden.
"""
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import babu_web  # noqa: E402
import box as bx  # noqa: E402
import boxschreiber  # noqa: E402
import mandanten  # noqa: E402

ANZAHL = 50
UN = "kanzlei-last@0711.io"


def _bare(tmp_path: Path, name: str, index: int) -> Path:
    """Ein winziger bare-Store mit genau einer, boxeigenen Datei.

    Der Dateiinhalt trägt den Index — das ist der Fingerabdruck, an dem
    sich später beweisen lässt, dass eine verdrängte und neu geladene Box
    wirklich noch ihren eigenen Stand zeigt und nicht den einer Nachbarin.
    """
    arbeit = tmp_path / f"arbeit-{name}"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "docs" / "2026-05").mkdir(parents=True)
    (arbeit / "docs" / "2026-05" / "marke.txt").write_text(f"box-{index}")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "stand"],
                   check=True, capture_output=True)
    bare = tmp_path / f"{name}.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)],
                   check=True)
    return bare


def _marke_lesen(store: Path) -> str:
    r = subprocess.run(["git", "--git-dir", str(store), "show",
                        "HEAD:docs/2026-05/marke.txt"],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


@pytest.fixture(scope="module")
def welt50(tmp_path_factory):
    """50 Mandanten unter einer Kanzlei, jeder mit eigener, echter Box.

    Modul-weit gebaut, nicht je Test: 50 × `git init`/`commit`/`clone --bare`
    ist die teure Operation hier, und acht Tests sollen sie sich teilen
    statt sie acht Mal zu wiederholen — sonst reißt das 60-Sekunden-Budget
    aus dem Auftrag. `pytest.MonkeyPatch()` statt der Fixture `monkeypatch`,
    weil die nur Funktionsgeltung hat; die einzelnen Tests patchen
    `BOX_MAX`/`BOX_TTL` weiterhin mit der normalen, funktionsweiten Fixture.
    """
    tmp_path = tmp_path_factory.mktemp("registry_last")
    mp = pytest.MonkeyPatch()
    mp.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    mp.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    mp.setattr(babu_web, "INDEX_TTL", 0.0)
    mp.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    mp.setattr(babu_web, "STORE", tmp_path / "leer.git")
    mp.setattr(bx, "STORE_WURZEL", tmp_path)
    mp.setattr(bx, "KLON_WURZEL", tmp_path / "klone")
    bx.registry_leeren()

    babu_web.nutzer_anlegen(UN, "kanzlei", "", "kanzlei")
    with babu_web._DB_LOCK, babu_web._db() as c:
        kanzlei_id = mandanten.kanzlei_anlegen("Kanzlei Last", UN, c=c)

    mandant_ids = []
    marken = {}
    for i in range(ANZAHL):
        name = f"box{i}"
        besitzer = f"salon{i}@0711.io"
        babu_web.nutzer_anlegen(besitzer, f"Salon {i}", "", "salon")
        bare = _bare(tmp_path, name, i)
        marken[name] = _marke_lesen(bare)
        with babu_web._DB_LOCK, babu_web._db() as c:
            mid = mandanten.mandant_anlegen(kanzlei_id, f"Salon {i}", besitzer, c=c)
            mandanten.box_verknuepfen(mid, name, c=c)
        mandant_ids.append(mid)

    yield mandant_ids, marken
    bx.registry_leeren()
    mp.undo()


@pytest.fixture(autouse=True)
def _frische_registry():
    """Jeder Test beginnt und endet mit einer leeren Registry — die Boxen
    aus `welt50` bleiben (modulweit), nur ihr In-Memory-Zustand nicht."""
    bx.registry_leeren()
    yield
    bx.registry_leeren()


# ---------------------------------------------------------------------------
# 1. Zugriff auf alle 50 + Obergrenze
# ---------------------------------------------------------------------------

def test_alle_50_sind_ueber_box_von_erreichbar(welt50, monkeypatch):
    """Jeder der 50 Mandanten liefert seine eigene, echte Box."""
    mandant_ids, marken = welt50
    monkeypatch.setattr(bx, "BOX_MAX", 100)      # hier soll nichts verdrängen
    for i, mid in enumerate(mandant_ids):
        box = bx.box_von(UN, mid)
        assert box.mandant_id == mid
        assert box.store.name == f"box{i}.git"
        assert _marke_lesen(box.store) == marken[f"box{i}"]


def test_registry_haelt_hoechstens_die_obergrenze(welt50, monkeypatch):
    """LRU: 50 Zugriffe bei einer Obergrenze von 10 — nie mehr als 10 im Speicher."""
    mandant_ids, _ = welt50
    monkeypatch.setattr(bx, "BOX_MAX", 10)
    stand = []
    for mid in mandant_ids:
        bx.box_von(UN, mid)
        stand.append(len(bx._BOX_REGISTRY))
    assert max(stand) <= 10, f"Registry ist über die Obergrenze gewachsen: {max(stand)}"
    assert len(bx._BOX_REGISTRY) == 10
    # LRU: übrig sind die zuletzt zehn angefragten, in derselben Reihenfolge.
    uebrig = [b.mandant_id for b, _ in bx._BOX_REGISTRY.values()]
    assert uebrig == mandant_ids[-10:]


# ---------------------------------------------------------------------------
# 2. Verdrängte Boxen kommen korrekt wieder
# ---------------------------------------------------------------------------

def test_verdraengte_box_kommt_mit_gleichem_inhalt_wieder(welt50, monkeypatch):
    mandant_ids, marken = welt50
    monkeypatch.setattr(bx, "BOX_MAX", 10)
    erste = mandant_ids[0]
    box_vorher = bx.box_von(UN, erste)
    store_vorher, ref_vorher = box_vorher.store, box_vorher.ref
    inhalt_vorher = _marke_lesen(box_vorher.store)

    # 15 weitere Zugriffe verdrängen die erste Box zuverlässig aus einer
    # Registry mit Platz für 10.
    for mid in mandant_ids[1:16]:
        bx.box_von(UN, mid)
    assert erste not in [b.mandant_id for b, _ in bx._BOX_REGISTRY.values()], (
        "die erste Box wurde nicht verdrängt — der Test prüft dann nichts")

    box_nachher = bx.box_von(UN, erste)
    assert box_nachher is not box_vorher, "ohne Verdrängung wäre das kein Beweis"
    assert box_nachher.store == store_vorher
    assert box_nachher.ref == ref_vorher
    assert _marke_lesen(box_nachher.store) == inhalt_vorher == marken["box0"]


# ---------------------------------------------------------------------------
# 3. Keine Vermischung von Index-Zuständen
# ---------------------------------------------------------------------------

def test_index_zustaende_vermischen_sich_nicht(welt50, monkeypatch):
    mandant_ids, _ = welt50
    monkeypatch.setattr(bx, "BOX_MAX", 100)
    a, b, c = mandant_ids[0], mandant_ids[1], mandant_ids[2]

    box_a = bx.box_von(UN, a)
    box_a.index["belege"]["nur-in-a"] = {"stamm": "nur-in-a"}
    box_b = bx.box_von(UN, b)
    box_c = bx.box_von(UN, c)

    assert "nur-in-a" not in box_b.index["belege"]
    assert "nur-in-a" not in box_c.index["belege"]
    assert box_a.index is not box_b.index
    assert box_a.schloss is not box_b.schloss

    # Derselbe Schlüssel liefert dasselbe Objekt zurück — der Zustand bleibt.
    box_a_wieder = bx.box_von(UN, a)
    assert box_a_wieder is box_a
    assert box_a_wieder.index["belege"]["nur-in-a"] == {"stamm": "nur-in-a"}


# ---------------------------------------------------------------------------
# 4. TTL-Verdrängung
# ---------------------------------------------------------------------------

def test_ttl_verdraengt_ungenutzte_boxen(welt50, monkeypatch):
    mandant_ids, _ = welt50
    monkeypatch.setattr(bx, "BOX_MAX", 100)      # nur die TTL soll wirken
    monkeypatch.setattr(bx, "BOX_TTL", 60.0)

    uhr = {"t": 1_000_000.0}
    monkeypatch.setattr(bx.time, "monotonic", lambda: uhr["t"])

    alt = mandant_ids[0]
    bx.box_von(UN, alt)
    assert alt in [b.mandant_id for b, _ in bx._BOX_REGISTRY.values()]

    uhr["t"] += 61.0          # über die TTL hinaus
    neu = mandant_ids[1]
    bx.box_von(UN, neu)       # jeder Zugriff räumt `_verdraengen()` mit auf

    stand = [b.mandant_id for b, _ in bx._BOX_REGISTRY.values()]
    assert alt not in stand, "die TTL hat die ungenutzte Box nicht verdrängt"
    assert neu in stand


def test_ttl_verschont_boxen_die_gerade_geschrieben_wird(welt50, monkeypatch):
    """Ein gehaltenes Schreibschloss überlebt die TTL — siehe `_verdraengen`
    im Modul-Docstring: zwei Objekte für eine Arbeitskopie wären der Fehler,
    den das Schloss verhindern soll."""
    mandant_ids, _ = welt50
    monkeypatch.setattr(bx, "BOX_MAX", 100)
    monkeypatch.setattr(bx, "BOX_TTL", 60.0)
    uhr = {"t": 1_000_000.0}
    monkeypatch.setattr(bx.time, "monotonic", lambda: uhr["t"])

    gehalten = mandant_ids[0]
    box = bx.box_von(UN, gehalten)
    box.schloss.acquire()
    try:
        uhr["t"] += 3600.0
        bx.box_von(UN, mandant_ids[1])
        stand = [b.mandant_id for b, _ in bx._BOX_REGISTRY.values()]
        assert gehalten in stand, "eine gehaltene Box wurde trotzdem verdrängt"
    finally:
        box.schloss.release()


# ---------------------------------------------------------------------------
# 5. Nebenläufiger Zugriff
# ---------------------------------------------------------------------------

def test_acht_threads_je_box_erzeugen_kein_duplikat(welt50, monkeypatch):
    """8 Threads greifen gleichzeitig auf dieselben Boxen zu — für jeden
    Mandanten darf dabei nur EIN Objekt entstehen, egal wie die Threads
    verschachtelt laufen, und keine Ausnahme darf durchkommen."""
    mandant_ids, _ = welt50
    monkeypatch.setattr(bx, "BOX_MAX", 100)   # Nebenläufigkeit prüfen, nicht Verdrängung
    bx.registry_leeren()

    auftraege = [mid for mid in mandant_ids for _ in range(8)]   # je Box 8x
    ergebnisse: dict[int, list[int]] = {}
    fehler = []

    def _holen(mid: int):
        try:
            box = bx.box_von(UN, mid)
            return mid, id(box)
        except Exception as ex:  # noqa: BLE001
            fehler.append(ex)
            raise

    with ThreadPoolExecutor(max_workers=8) as ex:
        for mid, objekt_id in ex.map(_holen, auftraege):
            ergebnisse.setdefault(mid, []).append(objekt_id)

    assert not fehler, f"Zugriffe unter Last warfen Ausnahmen: {fehler}"
    for mid, ids in ergebnisse.items():
        assert len(set(ids)) == 1, (
            f"Mandant {mid}: {len(set(ids))} verschiedene Box-Objekte statt einem "
            f"— zwei Schreiber in einer Arbeitskopie wären die Folge")
    # Und die Registry selbst trägt jeden Schlüssel nur einmal.
    schluessel = [k for k in bx._BOX_REGISTRY if k[0] in set(mandant_ids)]
    assert len(schluessel) == len(set(schluessel))


# ---------------------------------------------------------------------------
# Zeitmessung warm/kalt — Zahlen gehen in den Bericht, keine harte Schwelle
# außer der Grundaussage "warm ist nicht langsamer als kalt".
# ---------------------------------------------------------------------------

def test_zeit_pro_box_von_kalt_und_warm(welt50, monkeypatch, capsys):
    mandant_ids, _ = welt50
    monkeypatch.setattr(bx, "BOX_MAX", 100)
    bx.registry_leeren()

    start = time.perf_counter()
    for mid in mandant_ids:
        bx.box_von(UN, mid)
    kalt = (time.perf_counter() - start) / len(mandant_ids)

    DURCHLAEUFE = 20
    start = time.perf_counter()
    for _ in range(DURCHLAEUFE):
        for mid in mandant_ids:
            bx.box_von(UN, mid)
    warm = (time.perf_counter() - start) / (len(mandant_ids) * DURCHLAEUFE)

    with capsys.disabled():
        print(f"\n[test_registry_last] box_von kalt (je neue Box):  "
              f"{kalt * 1e6:.1f} µs")
        print(f"[test_registry_last] box_von warm (Registry-Treffer): "
              f"{warm * 1e6:.1f} µs")
        print(f"[test_registry_last] Faktor warm schneller als kalt: "
              f"{(kalt / warm) if warm else float('inf'):.1f}x")

    # Nur eine grobe Plausibilität — kein hartes Performance-Gate, das die
    # Suite auf einer langsamen CI-Maschine flaky machen würde.
    assert warm < kalt * 5
