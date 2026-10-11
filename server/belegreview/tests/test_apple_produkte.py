"""Die Produkt-Kennungen stehen an drei Orten — zwei davon prüft dieser Test.

`paket.STUFEN` (Server), `ios/Beleg/Support/babu.storekit` (Simulator) und
App Store Connect müssen zeichengleich dieselben Kennungen führen. Läuft
eines auseinander, ist der Fehler stumm: StoreKit liefert dann einfach kein
Produkt, die Auswahl zeigt die Ersatzpreise, und niemand kann kaufen — auf
dem Telefon einer Kundin, nicht hier.

App Store Connect lässt sich ohne Netz und ohne Schlüssel nicht prüfen; der
Stand dort wurde am 11.10.2026 von Hand abgeglichen (Gruppe „babu Speicher“,
22463529). Was dieser Test hält, sind die beiden Orte im Repo — und das ist
genau die Stelle, an der jemand etwas ändert.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import paket  # noqa: E402

STOREKIT = (Path(__file__).resolve().parents[3]
            / "ios" / "Beleg" / "Support" / "babu.storekit")


def _storekit() -> list[dict]:
    if not STOREKIT.is_file():
        pytest.skip(f"{STOREKIT} liegt hier nicht")
    daten = json.loads(STOREKIT.read_text())
    gruppen = daten["subscriptionGroups"]
    assert len(gruppen) == 1, "eine Gruppe — Apple stuft innerhalb der Gruppe"
    return gruppen[0]["subscriptions"]


def test_dieselben_kennungen():
    """Der eine Fehler, der niemandem auffällt, bis jemand kaufen will."""
    assert ({s["productID"] for s in _storekit()}
            == {e["apple"] for e in paket.STUFEN.values()})


def test_dieselben_preise():
    """Die Testdatei zeigt im Simulator Preise — die müssen stimmen, sonst
    prüft man die Auswahl gegen Zahlen, die es nicht gibt."""
    nach_id = {s["productID"]: s for s in _storekit()}
    for eintrag in paket.STUFEN.values():
        s = nach_id[eintrag["apple"]]
        assert float(s["displayPrice"]) * 100 == pytest.approx(eintrag["cent"]), \
            eintrag["apple"]


def test_alle_monatlich():
    assert {s["recurringSubscriptionPeriod"] for s in _storekit()} == {"P1M"}


def test_stufenreihenfolge_passt_zum_platz():
    """Apple stuft innerhalb einer Gruppe über `groupNumber`: 1 ist die
    höchste Stufe. Wer wechselt, soll den größeren Platz als Höherstufung
    erleben — deshalb muss die Reihenfolge der Zahlen zum Platz passen."""
    nach_id = {s["productID"]: s for s in _storekit()}
    paare = [(e["gb"], nach_id[e["apple"]]["groupNumber"])
             for e in paket.STUFEN.values()]
    nach_platz = [n for _gb, n in sorted(paare)]
    assert nach_platz == sorted(nach_platz), \
        "mehr Platz muss eine andere Ebene sein, in derselben Richtung"


def test_keine_doppelte_ebene():
    nummern = [s["groupNumber"] for s in _storekit()]
    assert len(set(nummern)) == len(nummern)


def test_familienfreigabe_aus():
    """Ein Betrieb teilt seine Buchhaltung nicht mit der Familie."""
    assert not any(s["familyShareable"] for s in _storekit())
