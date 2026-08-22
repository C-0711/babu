#!/usr/bin/env python3
"""Aus dem amtlichen XML-Pseudocode einen Python-Lohnsteuerrechner erzeugen.

Der Programmablaufplan zur Lohnsteuer ist ein Flussdiagramm über vierzig
Seiten. Ihn abzutippen wäre die naheliegende und die falsche Lösung: bei
gut zweihundert Rechenschritten schleicht sich ein Vorzeichen ein, und der
Fehler zeigt sich erst in der Lohnabrechnung von jemandem.

Das BMF veröffentlicht denselben Ablaufplan zusätzlich als XML-Pseudocode
— maschinenlesbar, Java-gefärbt, mit BigDecimal. Dieses Werkzeug übersetzt
ihn nach Python. Damit ist der Jahreswechsel kein Übertragungsprojekt mehr,
sondern ein Aufruf:

    python3 werkzeug/pap_uebersetzen.py Lohnsteuer2027.xml > lohnsteuer_pap.py

Der Ablaufplan ist ein amtliches Werk und damit gemeinfrei (§ 5 UrhG).

Was übersetzt wird — der Wortschatz ist klein und geschlossen:

    BigDecimal.valueOf(x)      → D("x")        Zeichenkette, nicht float:
                                                Java liest 0.07 exakt, ein
                                                Python-float täte das nicht
    a.add(b) / subtract / multiply             → (a + b) usw.
    a.divide(b)                                → exakte Division
    a.divide(b, n, ROUND_DOWN)                 → Division, dann abschneiden
    a.setScale(n, ROUND_UP)                    → auf n Stellen aufrunden
    a.compareTo(b)                             → -1 / 0 / 1 wie in Java
    a.longValue()                              → int(a)

Absichtlich NICHT gemacht: keine Vereinfachungen, keine „Verbesserungen",
keine zusammengefassten Zwischenschritte. Was hier herauskommt, soll Zeile
für Zeile dem amtlichen Ablauf entsprechen — nur so lässt es sich gegen den
Rechner des BMF prüfen.
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET


# ———————————————————————————————————————————————————————————————
# Ein kleiner Parser für die Java-Ausdrücke
# ———————————————————————————————————————————————————————————————

ZEICHEN = re.compile(r"""
    (?P<zahl>\d+\.\d+|\d+)
  | (?P<name>[A-Za-z_]\w*)
  | (?P<logik>&&|\|\|)
  | (?P<op><=|>=|==|!=|[<>])
  | (?P<rechnen>[+\-*/])
  | (?P<zeichen>[().,\[\]])
""", re.X)


def zerlegen(text: str) -> list[tuple[str, str]]:
    marken, i = [], 0
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        m = ZEICHEN.match(text, i)
        if not m:
            raise SyntaxError(f"unbekanntes Zeichen bei {text[i:][:30]!r}")
        marken.append((m.lastgroup, m.group()))
        i = m.end()
    return marken


RUNDUNG = {"ROUND_DOWN": "ROUND_DOWN", "ROUND_UP": "ROUND_UP"}


class Uebersetzer:
    """Rekursiver Abstieg über den Java-Ausdruck."""

    def __init__(self, marken: list[tuple[str, str]]):
        self.m, self.i = marken, 0

    def schau(self) -> tuple[str, str] | None:
        return self.m[self.i] if self.i < len(self.m) else None

    def nimm(self, erwartet: str | None = None) -> str:
        art, wert = self.m[self.i]
        if erwartet and wert != erwartet:
            raise SyntaxError(f"{erwartet!r} erwartet, {wert!r} gefunden")
        self.i += 1
        return wert

    # ————— Ebenen —————

    def vergleich(self) -> str:
        """Verknüpfungen ganz oben, damit `a == 1 && b < 2` richtig klammert."""
        wert = self.einzelvergleich()
        while (z := self.schau()) and z[0] == "logik":
            op = "and" if self.nimm() == "&&" else "or"
            wert = f"({wert} {op} {self.einzelvergleich()})"
        return wert

    def einzelvergleich(self) -> str:
        links = self.summe()
        z = self.schau()
        if z and z[0] == "op":
            op = self.nimm()
            return f"({links} {op} {self.summe()})"
        return links

    def summe(self) -> str:
        """Auch der Ablaufplan rechnet stellenweise ganz gewöhnlich —
        etwa `J = AJAHR - 2004` auf ganzen Zahlen."""
        wert = self.produkt()
        while (z := self.schau()) and z[0] == "rechnen" and z[1] in "+-":
            op = self.nimm()
            wert = f"({wert} {op} {self.produkt()})"
        return wert

    def produkt(self) -> str:
        wert = self.ausdruck()
        while (z := self.schau()) and z[0] == "rechnen" and z[1] in "*/":
            op = self.nimm()
            wert = f"({wert} {op} {self.ausdruck()})"
        return wert

    def ausdruck(self) -> str:
        """Ein Grundwert, gefolgt von beliebig vielen .methode(...)."""
        wert = self.grundwert()
        while (z := self.schau()) and z[1] == "." :
            self.nimm(".")
            name = self.nimm()
            self.nimm("(")
            args = []
            if (z := self.schau()) and z[1] != ")":
                args.append(self.vergleich())
                while (z := self.schau()) and z[1] == ",":
                    self.nimm(",")
                    args.append(self.vergleich())
            self.nimm(")")
            wert = self.anwenden(wert, name, args)
        return wert

    def grundwert(self) -> str:
        art, wert = self.m[self.i]
        if wert == "-":                 # Vorzeichen, etwa valueOf(-1)
            self.nimm("-")
            return f"(-{self.ausdruck()})"
        if wert == "(":
            self.nimm("(")
            innen = self.vergleich()
            self.nimm(")")
            return f"({innen})"
        if art == "zahl":
            self.nimm()
            return f'D("{wert}")'
        if art == "name":
            self.nimm()
            # BigDecimal.ZERO / .ONE / .valueOf(...) / .ROUND_*
            if wert == "BigDecimal":
                self.nimm(".")
                was = self.nimm()
                if was == "ZERO":
                    return 'D("0")'
                if was == "ONE":
                    return 'D("1")'
                if was in RUNDUNG:
                    return repr(RUNDUNG[was])
                if was == "valueOf":
                    self.nimm("(")
                    innen = self.vergleich()
                    self.nimm(")")
                    # valueOf(1234) auf eine schon fertige Zahl ist ein
                    # No-op; auf einen int-Wert macht es einen Betrag.
                    return f"D({innen})" if not innen.startswith('D("') else innen
                raise SyntaxError(f"BigDecimal.{was} kennen wir nicht")
            # Feldzugriff TAB1[...]
            if (z := self.schau()) and z[1] == "[":
                self.nimm("[")
                index = self.vergleich()
                self.nimm("]")
                return f"{wert}[int({index})]"
            return wert
        raise SyntaxError(f"unerwartet: {wert!r}")

    def anwenden(self, ziel: str, name: str, args: list[str]) -> str:
        if name == "add":
            return f"({ziel} + {args[0]})"
        if name == "subtract":
            return f"({ziel} - {args[0]})"
        if name == "multiply":
            return f"({ziel} * {args[0]})"
        if name == "divide":
            if len(args) == 1:
                return f"({ziel} / {args[0]})"
            if len(args) == 3:
                return f"teilen({ziel}, {args[0]}, {args[1]}, {args[2]})"
            raise SyntaxError(f"divide mit {len(args)} Argumenten")
        if name == "setScale":
            if len(args) != 2:
                raise SyntaxError("setScale braucht Stellen und Rundung")
            return f"stellen({ziel}, {args[0]}, {args[1]})"
        if name == "compareTo":
            return f"vergleiche({ziel}, {args[0]})"
        if name == "longValue":
            return f"int({ziel})"
        raise SyntaxError(f"Methode {name} kennen wir nicht")


def uebersetze(java: str) -> str:
    return Uebersetzer(zerlegen(java)).vergleich()


def zuweisung(java: str) -> str:
    """`A = ausdruck` → `z.A = ausdruck` (Zuweisung, kein Vergleich)."""
    links, rechts = java.split("=", 1)
    ziel = links.strip()
    if not re.fullmatch(r"[A-Za-z_]\w*", ziel):
        raise SyntaxError(f"seltsames Zuweisungsziel: {ziel!r}")
    return f"z.{ziel} = {uebersetze(rechts.strip())}"


# ———————————————————————————————————————————————————————————————
# Aus dem Baum Python machen
# ———————————————————————————————————————————————————————————————

def feldnamen(wurzel) -> set[str]:
    namen = set()
    for grp in wurzel.find("VARIABLES"):
        for v in grp:
            namen.add(v.get("name"))
    return namen


def mit_z(code: str, felder: set[str], konstanten: set[str]) -> str:
    """Feldnamen auf den Zustand `z` umschreiben; Konstanten bleiben global."""
    def ersetze(m):
        name = m.group(0)
        if name in felder and name not in konstanten:
            return f"z.{name}"
        return name
    # Nur freistehende Namen. Was hinter einem Punkt steht, ist schon
    # umgeschrieben (`z.FELD`) oder ein Attribut — beides bleibt.
    return re.sub(r"(?<![.\w\"])[A-Za-z_]\w*\b", ersetze, code)


def rumpf(knoten, felder, konstanten, tiefe=2) -> list[str]:
    ein = "    " * tiefe
    zeilen = []
    for k in knoten:
        if k.tag == "EVAL":
            zeilen.append(ein + mit_z(zuweisung(k.get("exec")), felder, konstanten))
        elif k.tag == "EXECUTE":
            zeilen.append(f"{ein}{k.get('method')}(z)")
        elif k.tag == "IF":
            bedingung = mit_z(uebersetze(k.get("expr")), felder, konstanten)
            zeilen.append(f"{ein}if {bedingung}:")
            dann = k.find("THEN")
            innen = rumpf(dann, felder, konstanten, tiefe + 1) if dann is not None else []
            zeilen += innen or [ein + "    pass"]
            sonst = k.find("ELSE")
            if sonst is not None:
                zeilen.append(f"{ein}else:")
                innen = rumpf(sonst, felder, konstanten, tiefe + 1)
                zeilen += innen or [ein + "    pass"]
        else:
            raise SyntaxError(f"unbekannter Knoten {k.tag}")
    return zeilen or [ein + "pass"]


KOPF = '''"""Lohnsteuer nach dem amtlichen Programmablaufplan {jahr}.

ERZEUGT — NICHT VON HAND ÄNDERN.

Übersetzt aus dem XML-Pseudocode des BMF ({quelle}) durch
`werkzeug/pap_uebersetzen.py`. Wer hier etwas ändert, verliert es beim
nächsten Jahreswechsel und weicht außerdem vom amtlichen Ablauf ab.

Der Programmablaufplan ist ein amtliches Werk (§ 5 UrhG). Die Namen der
Felder und Methoden sind seine, nicht unsere — deshalb stehen sie hier
groß und unübersetzt: nur so lässt sich Zeile für Zeile mit dem Original
vergleichen.

Gerechnet wird mit `Decimal`, weil Java `BigDecimal` verwendet. Mit
Fließkomma käme man auf Centbeträge, die um einen Cent danebenliegen — und
in einer Lohnabrechnung fällt genau das auf.
"""
from __future__ import annotations

from decimal import Decimal as D, ROUND_DOWN, ROUND_UP, getcontext

# Java rechnet Divisionen ohne Skalenangabe exakt. Genug Stellen, damit
# Python dasselbe tut.
getcontext().prec = 60


def stellen(wert: D, n: int, rundung: str) -> D:
    """Java: setScale(n, rundung)."""
    return wert.quantize(D(1).scaleb(-n), rounding=rundung)


def teilen(a: D, b: D, n: int, rundung: str) -> D:
    """Java: divide(b, n, rundung)."""
    return stellen(a / b, n, rundung)


def vergleiche(a: D, b: D) -> int:
    """Java: compareTo — minus eins, null oder eins."""
    return (a > b) - (a < b)


class Zustand:
    """Alle Felder des Ablaufplans an einer Stelle.

    Ein Objekt statt vieler Parameter: der Ablaufplan schreibt quer durch
    seine Unterprogramme in gemeinsame Felder, und das soll die Übersetzung
    nicht verstecken.
    """

    __slots__ = ({felder})

    def __init__(self, **eingaben):
{vorgaben}
        for name, wert in eingaben.items():
            if name not in self.__slots__:
                raise AttributeError(f"{{name}} kennt der Ablaufplan nicht")
            setattr(self, name, wert if isinstance(wert, (D, int)) else D(str(wert)))


'''


def erzeugen(pfad: str) -> str:
    wurzel = ET.parse(pfad).getroot()
    name = wurzel.get("name", "Lohnsteuer")
    jahr = re.sub(r"\D", "", name) or "?"

    felder = feldnamen(wurzel)
    konstanten = {c.get("name") for c in wurzel.find("CONSTANTS")}

    # Vorgabewerte: Zahlen als Decimal, ints als int.
    vorgaben = []
    for grp in wurzel.find("VARIABLES"):
        for v in grp:
            n, typ, vor = v.get("name"), v.get("type"), v.get("default")
            if typ == "int":
                vorgaben.append(f"        self.{n} = {int(vor or 0)}")
            elif vor and not re.fullmatch(r"-?[\d.]+", vor.strip()):
                # Manche Vorgaben sind selbst Java, etwa BigDecimal.ZERO.
                vorgaben.append(f"        self.{n} = {uebersetze(vor)}")
            else:
                vorgaben.append(f'        self.{n} = D("{vor or 0}")')

    teile = [KOPF.format(
        jahr=jahr, quelle=name,
        felder=", ".join(f'"{f}"' for f in sorted(felder)),
        vorgaben="\n".join(sorted(set(vorgaben))))]

    # Konstanten
    teile.append("# ————— Konstanten des Ablaufplans —————\n")
    for c in wurzel.find("CONSTANTS"):
        roh = c.get("value").strip()
        if roh.startswith("{"):
            werte = [uebersetze(x.strip())
                     for x in roh.strip("{}").split(",") if x.strip()]
            teile.append(f"{c.get('name')} = [{', '.join(werte)}]\n")
        else:
            teile.append(f"{c.get('name')} = {uebersetze(roh)}\n")
    teile.append("\n")

    # Methoden
    for m in wurzel.find("METHODS"):
        mname = m.get("name")
        if mname is None:
            continue
        teile.append(f"def {mname}(z: Zustand) -> None:\n")
        teile.append("\n".join(rumpf(m, felder, konstanten, 1)) + "\n\n\n")

    # Hauptlauf
    haupt = [m for m in wurzel.find("METHODS") if m.get("name") is None]
    if not haupt:
        haupt = [wurzel.find("METHODS/MAIN")]
    teile.append("def berechnen(z: Zustand) -> Zustand:\n"
                 '    """Der Hauptlauf des Ablaufplans."""\n')
    teile.append("\n".join(rumpf(haupt[0], felder, konstanten, 1)) + "\n")
    teile.append("    return z\n")
    return "".join(teile)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Aufruf: pap_uebersetzen.py <Lohnsteuer20XX.xml>")
    sys.stdout.write(erzeugen(sys.argv[1]))
