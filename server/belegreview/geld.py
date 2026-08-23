"""Geldbeträge kaufmännisch runden — der halbe Cent geht immer auf.

Pythons eingebautes `round()` rundet zur GERADEN Ziffer („banker's
rounding"): `round(0.125, 2)` ist `0.12`, nicht `0.13`. Für Statistik ist
das gut, für Geld ist es falsch.

Warum das zählt:

* **Umsatzsteuer.** Eine Rechnung weist Netto, Steuer und Brutto getrennt
  aus. Wer den halben Cent mal ab-, mal aufrundet, weist auf zwei
  Rechnungen mit demselben Netto verschiedene Steuer aus — und die
  Gegenprobe Netto + Steuer = Brutto stimmt nicht mehr.
* **Sozialversicherung.** § 23 SGB IV und die Beitragsverfahrensverordnung
  verlangen ausdrücklich kaufmännische Rundung auf den vollen Cent. Ein
  zur geraden Zahl gerundeter Beitrag ist nicht „einen Cent daneben",
  sondern ein falsch gemeldeter Beitrag.

Deshalb hier `Decimal` mit `ROUND_HALF_UP`.

Der Umweg über `str(wert)` ist Absicht: aus einem `float` wird das, was
Python selbst als kürzeste Darstellung druckt — also `0.475` und nicht
`0.474999999999999977795539507496869191527366638183593750`. Damit rundet
`_rund(0.475)` auf `0.48`, wie eine Kaufmannsfrau es erwartet. Ohne den
Umweg entschiede die Binärdarstellung, und die liegt bei halben Cent
willkürlich mal knapp darüber, mal knapp darunter.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def dez(wert) -> Decimal:
    """Ein Betrag als `Decimal` — aus float über seine gedruckte Form."""
    if isinstance(wert, Decimal):
        return wert
    if isinstance(wert, int) and not isinstance(wert, bool):
        return Decimal(wert)
    return Decimal(str(wert))


def rund(wert, stellen: int = 2) -> float:
    """Kaufmännisch gerundet, als `float` — so bleibt die JSON-Ausgabe eine Zahl.

    Das `+ 0.0` am Ende macht aus einem `-0.0` eine `0.0`: sonst stünde in
    der Rechnung „-0,00 €".
    """
    quant = Decimal(1).scaleb(-stellen) if stellen else Decimal(1)
    return float(dez(wert).quantize(quant, rounding=ROUND_HALF_UP)) + 0.0


def rund_cent(wert) -> int:
    """Auf ganze Cent, kaufmännisch — für alles, was in Cent gerechnet wird."""
    return int(dez(wert).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def anteil_cent(basis_cent: int, satz: float) -> int:
    """Ein Prozentanteil eines Cent-Betrags, kaufmännisch auf den Cent.

    Multipliziert wird in `Decimal`, nicht in `float`: sonst landete ein
    Produkt, das exakt auf einem halben Cent liegt, je nach Bitmuster mal
    knapp darüber und mal knapp darunter — und die Rundungsregel liefe ins
    Leere, bevor sie greifen könnte.
    """
    return rund_cent(dez(int(basis_cent)) * dez(satz))
