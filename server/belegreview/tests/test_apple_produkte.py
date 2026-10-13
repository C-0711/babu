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


def test_mehr_platz_ist_die_niedrigere_ebene():
    """Apple stuft innerhalb einer Gruppe über `groupNumber`, und **1 ist die
    höchste Stufe**. Ein Wechsel auf eine niedrigere Zahl ist eine
    Höherstufung und greift sofort; eine höhere Zahl ist eine Herabstufung
    und greift erst zur nächsten Verlängerung.

    Mehr Platz muss also die NIEDRIGERE Zahl tragen. Dieser Test behauptete
    bis zum 14.10.2026 das Gegenteil — er verlangte „in derselben Richtung"
    und hielt damit 1 GB auf Ebene 1 fest. Wer von 1 GB auf 100 GB wechselte,
    hätte das als Herabstufung erlebt: bezahlt, aber erst zum Monatsende mehr
    Platz, obwohl die Ablage jetzt voll ist. In App Store Connect steht es
    seit dem 14.10.2026 richtig (1 = 100 GB, 2 = 5 GB, 3 = 1 GB).
    """
    nach_id = {s["productID"]: s for s in _storekit()}
    nach_platz = [nach_id[e["apple"]]["groupNumber"]
                  for e in sorted(paket.STUFEN.values(), key=lambda e: e["gb"])]
    assert nach_platz == sorted(nach_platz, reverse=True), \
        ("mehr Platz = kleinere Ebene, sonst ist das Hochstufen eine "
         f"Herabstufung: {nach_platz}")


def test_die_groesste_stufe_ist_ebene_eins():
    """Die Gegenprobe zum Test davor, ohne Sortierlogik: der größte Platz
    trägt die 1."""
    nach_id = {s["productID"]: s for s in _storekit()}
    groesste = max(paket.STUFEN.values(), key=lambda e: e["gb"])
    assert nach_id[groesste["apple"]]["groupNumber"] == 1, groesste["apple"]


def test_keine_doppelte_ebene():
    nummern = [s["groupNumber"] for s in _storekit()]
    assert len(set(nummern)) == len(nummern)


def test_familienfreigabe_aus():
    """Ein Betrieb teilt seine Buchhaltung nicht mit der Familie."""
    assert not any(s["familyShareable"] for s in _storekit())
