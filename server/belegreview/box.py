#!/usr/bin/env python3
"""box — welche Belegbox ein Request gerade bedient.

Bis heute gab es genau EINE Box je Server. Ihre drei Angaben standen als
Modulkonstanten da: `babu_web.STORE` (der Bare-Store zum Lesen),
`boxschreiber.KLON`/`REF`/`REMOTE` (die Arbeitskopie zum Schreiben). Dazu
kam ein halbes Dutzend Modulglobals mit dem Zustand dieser einen Box —
Index, Blob-Stand, Seitenzahlen, Vektoren, die Schlösser.

Für eine Kanzlei mit vielen Mandanten muss dieser Zustand pro Box liegen,
sonst zeigt der Index von Mandant A die Belege von Mandant B. Diese Datei
bündelt beides in einem Objekt:

* `Box` hält Pfade UND Zustand. Das Objekt selbst ist eingefroren (die
  Pfade ändern sich nie), der Zustand darin ist es nicht — die Dicts und
  Schlösser bleiben dieselben Objekte, nur ihr Inhalt wandert.
* `_BOX_REGISTRY` gibt für dieselbe Box immer dasselbe Objekt zurück.
  Das ist keine Bequemlichkeit, sondern Pflicht: `Box.schloss` ist das
  Schreibschloss um den Klon, und zwei Objekte hieße zwei Schlösser hieße
  zwei Schreiber in derselben Arbeitskopie.
* `box_von(un, mandant_id)` löst auf. Ohne `mandant_id` — und das ist in
  Phase 2 IMMER der Fall — kommt die Default-Box heraus, gebaut aus genau
  den Modulkonstanten von oben. Der Alt-Pfad bleibt damit bit-identisch,
  und die Tests, die `babu_web.STORE` oder `boxschreiber.KLON` umbiegen,
  wirken weiter: die Werte werden bei jedem Aufruf frisch gelesen, nicht
  beim Import eingefroren.

Woher die Default-Box ihre Werte nimmt: `boxschreiber.REF/KLON/REMOTE`
liest sie selbst (später Import, damit diese Datei ein Blattmodul bleibt),
den Store meldet `babu_web` per `store_quelle()` an. Ohne Anmeldung greift
`STORE_STANDARD` — dieselbe Umgebungsvariable, derselbe Vorgabewert.
"""
from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Der Bare-Store der einen Box, wie er seit jeher aus BABU_STORE kommt.
# `babu_web.STORE` ist genau dieser Wert — eine Quelle, zwei Namen.
STORE_STANDARD = Path(os.environ.get(
    "BABU_STORE",
    str(Path.home() / "inspektor-store" / "inspektor" / "ws-christoph0711.io" / "babu.git")))

# Wo die Stores weiterer Mandanten liegen und wo ihre Arbeitskopien
# hinkommen. Beides greift erst, wenn es eine zweite echte Box gibt.
STORE_WURZEL = Path(os.environ.get("BABU_STORE_WURZEL",
                                   str(Path.home() / "inspektor-store")))
KLON_WURZEL = Path(os.environ.get("BABU_BOX_KLON_WURZEL",
                                  str(Path.home() / "babu-web" / "boxen")))

# Wie viele Boxen gleichzeitig im Speicher stehen dürfen und wie lange eine
# unbenutzte überlebt. Bei hunderten Mandanten arbeiten nur wenige
# gleichzeitig; ohne Deckel wüchse der Index-Zustand unbegrenzt.
BOX_MAX = int(os.environ.get("BABU_BOX_MAX", "50"))
BOX_TTL = float(os.environ.get("BABU_BOX_TTL", "3600"))


def _leerer_index() -> dict:
    """Derselbe Aufbau wie das frühere `babu_web._INDEX` — Feld für Feld."""
    return {"head": None, "geprueft": 0.0, "belege": {}, "reviews": {},
            "dokumente": [], "freigaben": {}, "umsaetze": {},
            "kassenblaetter": {}, "zeiten": {}, "oid_cache": {},
            "rechnungen": {}}


# `eq=False`: zwei Boxen sind gleich, wenn sie dasselbe Objekt sind. Alles
# andere wäre falsch — der Zustand darin unterscheidet sie nicht, das
# Schloss macht sie unvergleichbar, und die Registry gibt ohnehin für
# denselben Schlüssel immer dasselbe Objekt zurück.
@dataclass(frozen=True, eq=False)
class Box:
    """Eine Belegbox: wo sie liegt, und was der Server über sie weiß."""

    mandant_id: int | None      # None = die eine Box des Einzelbetriebs
    store: Path                 # Bare-Store, gelesen mit `git -C <store>`
    ref: str                    # z. B. "inspektor/ws-christoph0711.io/babu"
    klon: Path                  # Arbeitskopie des Schreibwegs
    # Ein Schreiber zur Zeit in dieser Arbeitskopie (früher
    # `boxschreiber._SCHLOSS`).
    schloss: threading.Lock = field(default_factory=threading.Lock, repr=False)
    remote: str = ""            # Push-Ziel; leer heißt "aus ref ableiten"

    # ---- Zustand, früher Modulglobals in babu_web ------------------------
    index: dict = field(default_factory=_leerer_index, repr=False)
    index_schloss: threading.Lock = field(default_factory=threading.Lock, repr=False)
    # Die Rechnungsnummer wird gelesen UND vergeben — dazwischen darf
    # niemand dieselbe Nummer bekommen.
    rechnung_schloss: threading.Lock = field(default_factory=threading.Lock, repr=False)
    # Termine: Überschneidung prüfen und eintragen gehören zusammen.
    termin_schloss: threading.Lock = field(default_factory=threading.Lock, repr=False)
    # (Kopf, Stämme, Matrix) der Beleg-Embeddings — je Box-Stand einmal gebaut.
    beleg_vektoren: dict = field(
        default_factory=lambda: {"kopf": None, "staemme": [], "matrix": None},
        repr=False)
    blob_stand: dict = field(default_factory=lambda: {"kopf": None, "pfade": {}},
                             repr=False)
    seiten_cache: dict = field(default_factory=dict, repr=False)

    def invalidieren(self) -> None:
        """Der nächste Lesezugriff baut den Index neu.

        Ersetzt die knapp drei Dutzend `_INDEX["geprueft"] = 0.0` von
        früher — als Methode, weil sonst jede Schreibroute wüsste, wie der
        Index innen aussieht.
        """
        self.index["geprueft"] = 0.0


# ---------------------------------------------------------------------------
# Registry: für dieselbe Box immer dasselbe Objekt.
# ---------------------------------------------------------------------------

# OrderedDict statt dict, weil `move_to_end`/`popitem(last=False)` die
# LRU-Ordnung ohne eigene Buchführung tragen. Wert ist (Box, zuletzt).
_BOX_REGISTRY: "OrderedDict[tuple, tuple[Box, float]]" = OrderedDict()
_BOX_REGISTRY_LOCK = threading.Lock()

_STORE_QUELLE: Callable[[], Path] | None = None


def store_quelle(fn: Callable[[], Path]) -> None:
    """`babu_web` meldet hier an, woher der Store der Default-Box kommt.

    Anmeldung statt Import: `box` bliebe sonst nicht das Blattmodul, das
    `boxschreiber` gefahrlos importieren kann. Die Funktion wird bei JEDEM
    Aufruf ausgewertet, damit ein `monkeypatch.setattr(babu_web, "STORE", …)`
    weiter wirkt.
    """
    global _STORE_QUELLE
    _STORE_QUELLE = fn


def _verdraengen(jetzt: float) -> None:
    """Alte und überzählige Boxen aus der Registry werfen.

    Eine Box, deren Schreibschloss gerade jemand hält, bleibt drin: sie
    wegzuwerfen hieße, der nächste Aufruf bekäme ein zweites Objekt mit
    einem zweiten Schloss — und damit zwei Schreiber in EINER Arbeitskopie,
    genau der Fehler, gegen den das Schloss überhaupt da ist.
    """
    for schluessel in [k for k, (b, wann) in _BOX_REGISTRY.items()
                       if jetzt - wann > BOX_TTL and not b.schloss.locked()]:
        del _BOX_REGISTRY[schluessel]
    while len(_BOX_REGISTRY) > BOX_MAX:
        entbehrlich = next((k for k, (b, _) in _BOX_REGISTRY.items()
                            if not b.schloss.locked()), None)
        if entbehrlich is None:      # alle in Arbeit — dann eben zu viele
            break
        del _BOX_REGISTRY[entbehrlich]


def _aus_registry(schluessel: tuple, bauen: Callable[[], Box]) -> Box:
    jetzt = time.monotonic()
    with _BOX_REGISTRY_LOCK:
        eintrag = _BOX_REGISTRY.get(schluessel)
        if eintrag is not None:
            _BOX_REGISTRY[schluessel] = (eintrag[0], jetzt)
            _BOX_REGISTRY.move_to_end(schluessel)
            return eintrag[0]
        neu = bauen()
        _BOX_REGISTRY[schluessel] = (neu, jetzt)
        _verdraengen(jetzt)
        return neu


def registry_leeren() -> None:
    """Nur für Tests: die Registry zurücksetzen."""
    with _BOX_REGISTRY_LOCK:
        _BOX_REGISTRY.clear()


def _default_werte() -> tuple[Path, str, Path, str]:
    """Store, Ref, Klon, Remote der einen Box — bei jedem Aufruf frisch.

    Später Import von `boxschreiber`: diese Datei soll ein Blattmodul
    bleiben, damit `boxschreiber` sie seinerseits importieren darf.
    """
    import boxschreiber  # noqa: PLC0415
    store = _STORE_QUELLE() if _STORE_QUELLE is not None else STORE_STANDARD
    return Path(store), boxschreiber.REF, Path(boxschreiber.KLON), boxschreiber.REMOTE


def default_box() -> Box:
    """Die Box des Einzelbetriebs — aus den bestehenden Umgebungswerten.

    Bewusst NICHT aus der `mandant`-Tabelle: der Alt-Pfad darf sich durch
    die neuen Tabellen um kein Byte ändern (Plan 21, Abschnitt 3.3). Die
    Tabelle greift erst für zusätzliche Mandanten.
    """
    store, ref, klon, remote = _default_werte()
    schluessel = (None, str(store), ref, str(klon), remote)
    return _aus_registry(
        schluessel,
        lambda: Box(mandant_id=None, store=store, ref=ref, klon=klon, remote=remote))


def store_aus_ref(ref: str) -> Path:
    """Konvention: der Store einer Box liegt unter der Store-Wurzel.

    `inspektor/ws-nina.de/babu` → `~/inspektor-store/inspektor/ws-nina.de/babu.git`.
    Für den Produktiv-Ref kommt damit exakt der heutige `BABU_STORE`
    heraus — die Konvention ist keine Erfindung, sondern die Beschreibung
    dessen, was insp-app ohnehin anlegt.
    """
    return STORE_WURZEL / (ref.strip("/") + ".git")


def klon_aus_ref(ref: str) -> Path:
    """Konvention: je Box eine eigene Arbeitskopie unter der Klon-Wurzel.

    Der Name ist der letzte Ordner vor dem Repo-Namen (`ws-nina.de`), weil
    der die Box eindeutig macht. Die Default-Box liegt weiter unter
    `~/babu-web/box` und geht diesen Weg nie.
    """
    teile = [t for t in ref.strip("/").split("/") if t]
    name = teile[-2] if len(teile) >= 2 else (teile[-1] if teile else "box")
    return KLON_WURZEL / name


def remote_aus_ref(ref: str) -> str:
    """Push-Ziel über das Gateway — dieselbe Form wie `boxschreiber.REMOTE`."""
    import boxschreiber  # noqa: PLC0415
    return f"{boxschreiber.GATEWAY}/git/{ref}.git"


def box_aus_ref(mandant_id: int | None, ref: str) -> Box:
    """Box zu einem `mandant.box_ref` — über die Konventionen oben."""
    store = store_aus_ref(ref)
    klon = klon_aus_ref(ref)
    remote = remote_aus_ref(ref)
    schluessel = (mandant_id, str(store), ref, str(klon), remote)
    return _aus_registry(
        schluessel,
        lambda: Box(mandant_id=mandant_id, store=store, ref=ref, klon=klon,
                    remote=remote))


class KeineBox(RuntimeError):
    """Der Mandant hat (noch) keine Belegbox — `status = box_ausstehend`."""


def box_von(un: str, mandant_id: int | None = None) -> Box:
    """Welche Box bedient dieser Zugang gerade?

    Ohne `mandant_id` die eine Box von heute — das ist in Phase 2 jeder
    Aufruf, denn `_mandant_aus_kontext` in `babu_web` liefert bis Phase 3
    immer None. Mit `mandant_id` die Box dieses Mandanten, aufgelöst über
    `mandant.box_ref`.

    `un` bleibt im Vertrag, obwohl der Alt-Pfad ihn nicht braucht: ab
    Phase 3 entscheidet er mit, welcher Mandant überhaupt erlaubt ist.
    """
    if mandant_id is None:
        return default_box()
    import mandanten  # noqa: PLC0415 — nur der Mehr-Box-Weg braucht die Tabelle
    zeile = mandanten.mandant_holen(mandant_id)
    if zeile is None:
        raise KeineBox(f"Mandant {mandant_id} gibt es nicht")
    if not zeile.get("box_ref"):
        raise KeineBox(f"Mandant {mandant_id}: Belegbox wird noch eingerichtet")
    return box_aus_ref(mandant_id, str(zeile["box_ref"]))
