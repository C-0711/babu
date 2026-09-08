"""Keine Adresse darf beim Ausgliedern verschwinden.

`babu_web.py` wird Gruppe für Gruppe in eigene Router zerlegt (Paket 2.1,
`docs/umsetzung-zwei-produkte.md`). Ein Umzug, der eine Route unterwegs
verliert, meldet sich nicht: der Server startet, die Suite läuft, und erst
die iOS-App oder das Portal bekommen irgendwann einen 404 auf eine Adresse,
die es gestern noch gab. Das ist dieselbe stille Fehlerart wie in
`test_betriebsfunktionen_kennen_den_mandanten.py`.

Deshalb steht die vollständige Liste aller Adressen als Fixture in
`golden/routen.txt` — je Zeile ein Verfahren und ein Pfad, alphabetisch.
Wer eine Route ABSICHTLICH hinzufügt oder entfernt, ändert die Fixture
bewusst mit (wie beim Golden-Vertrag in `test_api.py`). Wer sie nur
verschiebt, fasst sie nicht an.

**Included Router müssen mitgezählt werden.** Seit FastAPI 0.141 steht in
`app.routes` für jeden `include_router` KEIN aufgeklappter Satz Routen mehr,
sondern ein einzelnes `_IncludedRouter`-Objekt ohne `path`. Ein Sammler, der
nur `r.path` liest, übersieht damit still jede ausgegliederte Gruppe — also
genau das, was hier bewacht werden soll. `_pfade` steigt deshalb in
`original_router.routes` hinab; `test_der_sammler_sieht_auch_ausgegliederte_routen`
ist die Gegenprobe darauf.
"""
import sys
from pathlib import Path

from fastapi import APIRouter, FastAPI

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

GOLDEN = HIER / "golden" / "routen.txt"

import babu_web  # noqa: E402


def _pfade(routen, praefix: str = "") -> set[str]:
    """Alle „VERFAHREN /pfad" einer Routenliste — Router eingeschlossen."""
    aus: set[str] = set()
    for r in routen:
        innen = getattr(r, "original_router", None)
        if innen is not None:
            # Das Präfix des Routers steckt bereits in `r.path` der inneren
            # Routen (`APIRouter(prefix=…)` schreibt es beim Anlegen hinein).
            # Dazu kommt nur, was beim `include_router` selbst mitgegeben
            # wurde — bei uns nichts, aber ein Sammler, der es unterschlägt,
            # zeigte später die falschen Adressen an.
            kontext = getattr(r, "include_context", None)
            aus |= _pfade(innen.routes, praefix + getattr(kontext, "prefix", ""))
            continue
        pfad = getattr(r, "path", None)
        if pfad is None:
            continue
        for verfahren in sorted(getattr(r, "methods", None) or ["-"]):
            aus.add(f"{verfahren} {praefix}{pfad}")
    return aus


def _erwartet() -> set[str]:
    return {z.strip() for z in GOLDEN.read_text().splitlines() if z.strip()}


def test_alle_adressen_sind_noch_da():
    ist = _pfade(babu_web.app.routes)
    soll = _erwartet()
    fehlen = sorted(soll - ist)
    neu = sorted(ist - soll)
    assert not fehlen and not neu, (
        "Die Adressen weichen von golden/routen.txt ab.\n"
        + "".join(f"  FEHLT   {z}\n" for z in fehlen)
        + "".join(f"  NEU     {z}\n" for z in neu)
        + "Verschoben? Dann ist etwas verloren gegangen. Absichtlich neu "
          "oder entfernt? Dann die Fixture bewusst mitändern.")


def test_die_ausgegliederten_gruppen_sind_eingehaengt():
    """Die drei bisherigen Ausgliederungen, je an einer ihrer Adressen.

    Ein Wächter über einer Liste, die niemand mehr füttert, ist keiner:
    stünde `include_router` nicht mehr da, wäre `golden/routen.txt` zwar
    verletzt — aber dieser Test sagt in einem Satz, WELCHE Gruppe fehlt.
    """
    ist = _pfade(babu_web.app.routes)
    for adresse in ("GET /api/datev/uebersicht",      # datev_seite
                    "GET /api/kanzlei/mandanten",     # kanzlei_routen
                    "GET /api/marke",                 # marke_routen
                    "GET /api/marketing"):            # marke_routen
        assert adresse in ist, f"nicht eingehängt: {adresse}"


def test_briefkopf_und_marketing_liegen_in_marke_routen():
    """Der Umzug vom 08.09.2026: die Routen sind aus `babu_web` heraus.

    Geprüft wird die Herkunft, nicht nur die Existenz — sonst wäre ein
    versehentlich in `babu_web` zurückgelassener Zwilling unsichtbar.
    """
    import marke_routen  # noqa: PLC0415

    eigen = _pfade(marke_routen.router.routes)
    assert len(eigen) == 14, sorted(eigen)
    assert {"GET /api/marke", "POST /api/marke/waehlen",
            "GET /api/marketing/{schluessel}"} <= eigen

    quelle = babu_web.__file__
    for r in babu_web.app.routes:
        pfad = getattr(r, "path", None)
        if pfad and (pfad.startswith("/api/marke")
                     or pfad.startswith("/api/marketing")):
            assert r.endpoint.__code__.co_filename != quelle, \
                f"{pfad} steht immer noch in babu_web.py"


def test_die_reihenfolge_der_marketing_routen_bleibt():
    """`/api/marketing/entwerfen` muss VOR `/api/marketing/{schluessel}`
    stehen — sonst verschluckt der Platzhalter den Entwurf."""
    import marke_routen  # noqa: PLC0415

    pfade = [r.path for r in marke_routen.router.routes]
    assert pfade.index("/api/marketing/entwerfen") \
        < pfade.index("/api/marketing/{schluessel}")


def test_der_sammler_sieht_auch_ausgegliederte_routen():
    """Gegenprobe am eigenen Werkzeug, nicht am Ergebnis."""
    unter = APIRouter(prefix="/api/probe")

    @unter.get("/ding")
    def _ding():  # pragma: no cover — wird nie gerufen
        return {}

    probe = FastAPI()
    probe.include_router(unter)
    assert "GET /api/probe/ding" in _pfade(probe.routes)
