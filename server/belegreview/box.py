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

**Lesen seit dem GitChain-Standard (27.09.2026): aus dem eigenen Klon.**
babu liest nicht mehr im Speicher von GitChain (`~/gitchain/tresor`,
`/opt/gitchain-repos`), sondern aus einem eigenen Lesespiegel je Box
(`git clone --mirror` vom Remote, mit dem Token des Schreibwegs). Der Spiegel
liegt unter `BABU_LESE_WURZEL/<ref>.git` und ist für den Lesecode ein ganz
gewöhnlicher Bare-Store — `git -C <store> show HEAD:…` bleibt, wie es war.
Nachgezogen wird er per `lesestand_holen()`: vor jedem Index-Neubau (höchstens
alle `BABU_LESE_TTL` Sekunden) und sofort nach jedem eigenen Push.
`BABU_LESEN=store` schaltet auf den alten Direktzugriff zurück — nur als
Rückweg und für die Tests, die den Lesecode gegen einen Bare-Store prüfen.
"""
from __future__ import annotations

import os
import shutil
import subprocess
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
# Wo die Lesespiegel liegen (Modus `klon`, siehe Modul-Kopf).
LESE_WURZEL = Path(os.environ.get("BABU_LESE_WURZEL",
                                  str(Path.home() / "babu-web" / "lesen")))
# Wie oft der Lesespiegel höchstens beim Remote nachfragt. Ein eigener Push
# zieht ihn ohnehin sofort nach; die Frist gilt nur für fremde Commits
# (Hintergrundjobs, zweiter Server).
LESE_TTL = float(os.environ.get("BABU_LESE_TTL", os.environ.get("BABU_INDEX_TTL", "5")))


def lesen_modus() -> str:
    """`klon` (Standard: eigener Lesespiegel) oder `store` (alter Direktzugriff).

    Bei jedem Aufruf frisch gelesen, damit Tests und Rückweg ohne Neuimport
    umschalten können. Alles außer `store` heißt `klon`.
    """
    return "store" if os.environ.get("BABU_LESEN", "klon").strip().lower() == "store" \
        else "klon"

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
            "rechnungen": {}, "kennungen": {}}


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
    # Dasselbe für die Dokumente (Verträge, Post vom Amt). Eigener Stand
    # statt einer gemeinsamen Matrix: die beiden Bestände wachsen getrennt,
    # werden getrennt nachgetragen, und im Chat sollen sie getrennt zitiert
    # werden („passende Belege" gegen „passende Unterlagen").
    dokument_vektoren: dict = field(
        default_factory=lambda: {"kopf": None, "pfade": [], "matrix": None},
        repr=False)
    blob_stand: dict = field(default_factory=lambda: {"kopf": None, "pfade": {}},
                             repr=False)
    seiten_cache: dict = field(default_factory=dict, repr=False)
    # Lesespiegel (Modus `klon`): wann zuletzt nachgezogen, letzter Fehler.
    # Das Schloss dazu liegt je Pfad in `_SPIEGEL_SCHLOESSER`.
    lese_stand: dict = field(default_factory=lambda: {"geholt": 0.0, "fehler": ""},
                             repr=False)

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
    if lesen_modus() == "klon":
        store = lese_aus_ref(boxschreiber.REF)
    else:
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


def lese_aus_ref(ref: str) -> Path:
    """Konvention (Modus `klon`): der Lesespiegel einer Box.

    `babu/salon-2/belege` → `~/babu-web/lesen/babu/salon-2/belege.git`. Der
    volle Ref als Pfad, damit zwei Boxen nie denselben Spiegel teilen.
    """
    return LESE_WURZEL / (ref.strip("/") + ".git")


# Ein hängender Dienst (TCP-Blackhole, Pod im Stau) darf den Lesepfad nicht
# minutenlang festhalten: Fetch mit Low-Speed-Grenze und kurzer Gesamtfrist.
# Der erste Klon (hunderte MiB) läuft nur im Hintergrund und darf länger.
FETCH_FRIST = int(os.environ.get("BABU_LESE_FETCH_FRIST", "15"))
_LANGSAM = ["-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=10"]

# Ein Schloss je Spiegel-PFAD, nicht je Box-Objekt: nach einer LRU-Verdrängung
# kann es für dieselbe Box kurz zwei Objekte geben — beide dürfen dann nicht
# gleichzeitig in denselben Spiegel holen.
_SPIEGEL_SCHLOESSER: dict[str, threading.Lock] = {}
_SPIEGEL_SCHLOESSER_LOCK = threading.Lock()


def _spiegel_schloss(pfad: Path) -> threading.Lock:
    with _SPIEGEL_SCHLOESSER_LOCK:
        return _SPIEGEL_SCHLOESSER.setdefault(str(pfad), threading.Lock())


def _lese_git(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    import boxschreiber  # noqa: PLC0415 — Token und Auth-Kopf wie beim Schreiben
    return subprocess.run(["git", *_LANGSAM, *args], capture_output=True, text=True,
                          timeout=timeout, env=boxschreiber._pat_umgebung())  # noqa: SLF001


def spiegel_befund(box: "Box") -> str:
    """Für /healthz: `ok`, `fehlt` (noch kein Spiegel) oder der letzte Fehler."""
    if lesen_modus() != "klon":
        return "store"
    if box.lese_stand["fehler"]:
        return box.lese_stand["fehler"]
    return "ok" if (Path(box.store) / "HEAD").is_file() else "fehlt"


def lesestand_holen(box: "Box", sofort: bool = False, warten: bool = True,
                    erstklon: bool = True) -> bool:
    """Den Lesespiegel der Box beim Remote nachziehen (Modus `klon`).

    Gibt es ihn noch nicht, entsteht er per `git clone --mirror` — erst in
    einen Nachbarordner, dann umbenannt, damit ein abgebrochener Klon nie
    als halber Spiegel stehen bleibt. Sonst `fetch --prune` mit
    Low-Speed-Grenze und `FETCH_FRIST`. Ohne `sofort` höchstens alle
    `LESE_TTL` Sekunden. Ein Fehler (Netz, Token, hängender Dienst) wird
    gemeldet, bricht aber nichts: gelesen wird dann der letzte Stand.
    Im Modus `store` gibt es nichts nachzuziehen.

    `warten=False`: zieht gerade ein anderer Faden nach, wird nicht gewartet.
    Mit `sofort` wird dann nur vermerkt, dass der nächste Leser nachziehen
    soll (`geholt = 0`) — so wartet ein Upload nach seinem Push nie auf einen
    laufenden Fetch oder Erstklon.
    `erstklon=False` (Lesepfad): fehlt der Spiegel, startet der Erstklon im
    Hintergrund statt im Request.
    """
    if lesen_modus() != "klon" or not box.remote:
        return True
    schloss = _spiegel_schloss(Path(box.store))
    if not schloss.acquire(blocking=warten):
        if sofort:
            box.lese_stand["geholt"] = 0.0
        return not box.lese_stand["fehler"]
    try:
        if not erstklon and not (Path(box.store) / "HEAD").is_file():
            threading.Thread(target=lesestand_holen, args=(box, True),
                             name="lesespiegel-erstklon", daemon=True).start()
            return False
        return _lesestand_holen_gesperrt(box, sofort)
    finally:
        schloss.release()


def _lesestand_holen_gesperrt(box: "Box", sofort: bool) -> bool:
    """Der eigentliche Klon/Fetch — nur unter dem Spiegel-Schloss aufrufen."""
    jetzt = time.monotonic()
    if not sofort and jetzt - box.lese_stand["geholt"] < LESE_TTL:
        return not box.lese_stand["fehler"]
    box.lese_stand["geholt"] = jetzt
    spiegel = Path(box.store)
    try:
        if not (spiegel / "HEAD").is_file():
            spiegel.parent.mkdir(parents=True, exist_ok=True)
            neu = spiegel.with_name(spiegel.name + ".neu")
            if neu.exists():
                shutil.rmtree(neu)
            r = _lese_git(["clone", "--mirror", "-q", box.remote, str(neu)],
                          timeout=int(os.environ.get("BABU_LESE_KLON_FRIST", "900")))
            if r.returncode == 0:
                neu.rename(spiegel)
        else:
            url = _lese_git(["-C", str(spiegel), "remote", "get-url", "origin"],
                            timeout=10)
            if url.stdout.strip() != box.remote:
                # Umzug des Remotes (z. B. :7808 → neuer Dienst): der Spiegel
                # folgt der Konfiguration, nicht seiner Erinnerung.
                _lese_git(["-C", str(spiegel), "remote", "set-url", "origin",
                           box.remote], timeout=10)
            r = _lese_git(["-C", str(spiegel), "fetch", "-q", "--prune", "origin"],
                          timeout=FETCH_FRIST)
    except (OSError, subprocess.SubprocessError) as ex:
        box.lese_stand["fehler"] = ("Dienst antwortet nicht (Frist)"
                                    if isinstance(ex, subprocess.TimeoutExpired)
                                    else type(ex).__name__)
        print(f"[lesespiegel] {box.ref}: Lesespiegel nicht nachgezogen "
              f"({box.lese_stand['fehler']})", flush=True)
        return False
    if r.returncode != 0:
        import boxschreiber  # noqa: PLC0415
        box.lese_stand["fehler"] = boxschreiber.git_fehler_text(r.stderr)
        print(f"[lesespiegel] {box.ref}: Lesespiegel nicht nachgezogen: "
              f"{box.lese_stand['fehler']}", flush=True)
        return False
    box.lese_stand["fehler"] = ""
    return True


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
    """Box zu einem `mandant.box_ref` — über die Konventionen oben.

    Trägt die Mandantenzeile den Produktiv-Ref, ist das die Default-Box und
    keine zweite: sonst entstünde für denselben Store eine ZWEITE
    Arbeitskopie (`~/babu-web/boxen/ws-…` statt `~/babu-web/box`) mit
    eigenem Schreibschloss — zwei Schreiber auf einem Remote, genau der
    Fehler, gegen den die Registry oben gebaut ist.

    Das ist kein hypothetischer Fall: Ninas Mandantenzeile (id 2,
    SupremeStudio) trägt auf der H200V genau diesen Ref. Ohne diese drei
    Zeilen bekäme sie in dem Moment eine zweite Arbeitskopie, in dem der
    Server anfängt, ihren Mandanten aufzulösen.
    """
    import boxschreiber  # noqa: PLC0415 — nur für den Vergleich mit dem Produktiv-Ref
    if ref.strip("/") == boxschreiber.REF.strip("/"):
        return default_box()
    store = lese_aus_ref(ref) if lesen_modus() == "klon" else store_aus_ref(ref)
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
