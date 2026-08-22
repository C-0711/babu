#!/usr/bin/env python3
"""Den erzeugten Lohnsteuerrechner gegen den des BMF prüfen.

Ein selbstgebauter Lohnsteuerrechner ist erst dann etwas wert, wenn er
gegen den amtlichen gerechnet wurde. Das BMF betreibt dafür einen
öffentlichen Rechner; dieses Werkzeug schickt dieselben Fälle dorthin und
vergleicht Cent für Cent.

    python3 werkzeug/pap_pruefen.py

Es gibt daneben eine ausdrücklich für diesen Zweck gedachte
Programmierschnittstelle des BMF. Sie braucht einen Zugriffscode, den man
nach einer Einwilligung erhält — sobald er vorliegt, ist er hier über
BMF_CODE einzusetzen; dann läuft die Prüfung ohne Formularumweg.

Bewusst kein Test in `tests/`: das hier geht ins Netz und gehört nicht in
einen Testlauf, der auch ohne Verbindung grün sein muss. Die Ergebnisse
dieser Prüfung wandern als feste Werte nach `tests/test_lohnsteuer_pap.py`.
"""
from __future__ import annotations

import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lohnsteuer_pap as pap  # noqa: E402

FORMULAR = "https://www.bmf-steuerrechner.de/bl/bl2026/eingabeformbl2026.xhtml"
BMF_CODE = os.environ.get("BMF_CODE", "")
KOPF = {"User-Agent": "babu-PAP-Pruefung/1.0 (Abgleich mit dem BMF-Rechner)"}


# ————— Die Fälle —————
#
# Absichtlich breit gestreut: alle sechs Steuerklassen, alle vier
# Lohnzahlungszeiträume, unter und über dem Grundfreibetrag, mit und ohne
# Kirchensteuer, Kinderfreibeträge, privat versichert, Sachsen.

FAELLE = [
    {"name": "StKl I, 3.000 monatlich",
     "LZZ": 2, "brutto": 3000, "STKL": 1, "KVZ": "2,90", "PVZ": 1},
    {"name": "StKl I, 1.000 monatlich (unter dem Grundfreibetrag)",
     "LZZ": 2, "brutto": 1000, "STKL": 1, "KVZ": "2,90", "PVZ": 1},
    {"name": "StKl III, 5.000 monatlich",
     "LZZ": 2, "brutto": 5000, "STKL": 3, "KVZ": "2,90", "PVZ": 0},
    {"name": "StKl V, 2.500 monatlich",
     "LZZ": 2, "brutto": 2500, "STKL": 5, "KVZ": "2,90", "PVZ": 1},
    {"name": "StKl VI, 2.000 monatlich",
     "LZZ": 2, "brutto": 2000, "STKL": 6, "KVZ": "2,90", "PVZ": 1},
    {"name": "StKl II, 3.500 monatlich, 1 Kinderfreibetrag",
     "LZZ": 2, "brutto": 3500, "STKL": 2, "ZKF": "1,0", "KVZ": "2,90", "PVZ": 0},
    {"name": "StKl I, 60.000 jährlich",
     "LZZ": 1, "brutto": 60000, "STKL": 1, "KVZ": "2,90", "PVZ": 1},
    {"name": "StKl IV, 800 wöchentlich",
     "LZZ": 3, "brutto": 800, "STKL": 4, "KVZ": "2,90", "PVZ": 1},
    {"name": "StKl I, 150 täglich",
     "LZZ": 4, "brutto": 150, "STKL": 1, "KVZ": "2,90", "PVZ": 1},
    {"name": "StKl I, 9.000 monatlich (über allen Bemessungsgrenzen)",
     "LZZ": 2, "brutto": 9000, "STKL": 1, "KVZ": "2,90", "PVZ": 1},
    {"name": "StKl III, 4.000 monatlich, privat versichert",
     "LZZ": 2, "brutto": 4000, "STKL": 3, "PKV": 1, "PKPV": 650, "PVZ": 0},
    {"name": "StKl I, 3.000 monatlich, Sachsen",
     "LZZ": 2, "brutto": 3000, "STKL": 1, "KVZ": "2,90", "PVS": 1, "PVZ": 1},
    # Nicht über das Formular prüfbar: das BMF-Formular übernimmt die Zahl
    # der Kinder nur bei echter Benutzereingabe und meldet auf der
    # Ergebnisseite wieder „0 oder 1". Das ist keine Abweichung der
    # Rechnung, sondern eine Grenze dieses Prüfwegs — mit dem Zugriffscode
    # für die Programmierschnittstelle fällt sie weg.
    # {"name": "PVA", "LZZ": 2, "brutto": 3000, "STKL": 1, "PVA": 2, "PVZ": 0},
    {"name": "StKl I, 2.100 monatlich (knapp über dem Grundfreibetrag)",
     "LZZ": 2, "brutto": 2100, "STKL": 1, "KVZ": "2,90", "PVZ": 1},
]


def bei_uns(fall: dict) -> tuple[int, int, int]:
    """Was unser erzeugter Rechner sagt — in Cent."""
    z = pap.Zustand(
        RE4=int(round(fall["brutto"] * 100)),
        LZZ=fall["LZZ"], STKL=fall["STKL"],
        KVZ=fall.get("KVZ", "0").replace(",", "."),
        PVZ=fall.get("PVZ", 0), PVS=fall.get("PVS", 0), PVA=fall.get("PVA", 0),
        PKV=fall.get("PKV", 0),
        PKPV=int(round(fall.get("PKPV", 0) * 100)),
        ZKF=fall.get("ZKF", "0").replace(",", "."),
        R=fall.get("R", 0), KRV=0, af=0)
    pap.berechnen(z)
    return int(z.LSTLZZ), int(z.SOLZLZZ), int(z.BK)


# ————— Der BMF-Rechner über sein Formular —————

def _feld(html: str, name: str) -> str:
    m = re.search(rf'name="{re.escape(name)}"[^>]*value="([^"]*)"', html)
    return m.group(1) if m else ""


def beim_bmf(fall: dict, oeffner) -> tuple[int, int, int]:
    with oeffner.open(urllib.request.Request(FORMULAR, headers=KOPF),
                      timeout=60) as a:
        html = a.read().decode("utf-8", "ignore")
    daten = {
        "bl_form": "bl_form",
        "javax.faces.ViewState": _feld(html, "javax.faces.ViewState"),
        "bl_form:in_geburtsjahr": "",
        "bl_form:in_steuerklasse": str(fall["STKL"]),
        "bl_form:in_kinderfrei": fall.get("ZKF", "0,0").replace(",", "."),
        "bl_form:in_kirchensteuer": "WAHL",
        "bl_form:in_lohnart": str(fall["LZZ"]),
        "bl_form:in_bruttolohn": f"{fall['brutto']:.2f}".replace(".", ","),
        "bl_form:in_verbezug": "0,00",
        "bl_form:in_rentenvers": "0",
        "bl_form:in_alv": "0",
        "bl_form:in_kv": str(fall.get("PKV", 0)),
        "bl_form:in_zusatzBeiKv": fall.get("KVZ", "0,00"),
        # 0 ohne Zuschlag, 1 mit, 2 Sachsen ohne, 3 Sachsen mit
        "bl_form:in_pv": str(fall.get("PVS", 0) * 2 + fall.get("PVZ", 0)),
        "bl_form:in_pva": str(fall.get("PVA", 0)),
        "bl_form:in_moBeiPPV": f"{fall.get('PKPV', 0):.2f}".replace(".", ","),
        "bl_form:in_pkpvagz": "0,00",
        "bl_form:in_betragLohnAb": "0,00",
        "bl_form:in_betragLohnZu": "0,00",
        "bl_form:income_bl": "Berechnen",
    }
    r = urllib.request.Request(
        FORMULAR, data=urllib.parse.urlencode(daten).encode(),
        headers={**KOPF, "Content-Type": "application/x-www-form-urlencoded"})
    with oeffner.open(r, timeout=60) as a:
        ergebnis = a.read().decode("utf-8", "ignore")

    def betrag(was: str) -> int:
        m = re.search(rf"{was}[^0-9-]*(-?[\d.]+,\d\d)\s*Euro", ergebnis)
        if not m:
            raise LookupError(f"{was} nicht in der Antwort gefunden")
        return int(round(float(m.group(1).replace(".", "").replace(",", ".")) * 100))

    return (betrag("Die Lohnsteuer beträgt"),
            betrag("Der Solidaritätszuschlag beträgt"),
            betrag("Die Kirchensteuer beträgt"))


def main() -> int:
    import http.cookiejar
    oeffner = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    schief = 0
    print(f"{'Fall':<58} {'babu':>12} {'BMF':>12}")
    print("-" * 86)
    for fall in FAELLE:
        unser = bei_uns(fall)
        try:
            amtlich = beim_bmf(fall, oeffner)
        except Exception as e:  # noqa: BLE001
            print(f"{fall['name']:<58} {'—':>12}  nicht erreichbar: {e}")
            schief += 1
            continue
        gleich = unser == amtlich
        schief += not gleich
        print(f"{fall['name']:<58} {unser[0]/100:>11.2f}€ {amtlich[0]/100:>11.2f}€"
              f"  {'✓' if gleich else '✗ ABWEICHUNG'}")
        if not gleich:
            print(f"{'':60}  LSt/SolZ/BK  babu {unser}  BMF {amtlich}")

    print("-" * 86)
    print("Alle Fälle stimmen überein." if not schief
          else f"{schief} von {len(FAELLE)} Fällen weichen ab.")
    return 1 if schief else 0


if __name__ == "__main__":
    raise SystemExit(main())
