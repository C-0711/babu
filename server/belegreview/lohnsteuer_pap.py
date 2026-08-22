"""Lohnsteuer nach dem amtlichen Programmablaufplan 2026.

ERZEUGT — NICHT VON HAND ÄNDERN.

Übersetzt aus dem XML-Pseudocode des BMF (Lohnsteuer2026) durch
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

    __slots__ = ("AJAHR", "ALTE", "ALTER1", "ALV", "ANP", "ANTEIL1", "AVSATZAN", "BBGKVPV", "BBGRVALV", "BK", "BKS", "BMG", "DIFF", "EFA", "FVB", "FVBSO", "FVBZ", "FVBZSO", "GFB", "HBALTE", "HFVB", "HFVBZ", "HFVBZSO", "HOCH", "J", "JBMG", "JFREIB", "JHINZU", "JLFREIB", "JLHINZU", "JRE4", "JRE4ENT", "JVBEZ", "JW", "K", "KFB", "KRV", "KVSATZAN", "KVZ", "KZTAB", "LSTJAHR", "LSTLZZ", "LSTOSO", "LSTSO", "LZZ", "LZZFREIB", "LZZHINZU", "MBV", "MIST", "PKPV", "PKPVAGZ", "PKPVAGZJ", "PKV", "PVA", "PVS", "PVSATZAN", "PVZ", "R", "RE4", "RVSATZAN", "RW", "SAP", "SOLZFREI", "SOLZJ", "SOLZLZZ", "SOLZMIN", "SOLZS", "SOLZSBMG", "SOLZSZVE", "SONSTB", "SONSTENT", "ST", "ST1", "ST2", "STERBE", "STKL", "STS", "VBEZ", "VBEZB", "VBEZBSO", "VBEZM", "VBEZS", "VBS", "VERGL", "VFRB", "VFRBS1", "VFRBS2", "VJAHR", "VSP", "VSPALV", "VSPHB", "VSPKVPV", "VSPN", "VSPR", "W1STKL5", "W2STKL5", "W3STKL5", "WVFRB", "WVFRBM", "WVFRBO", "X", "Y", "ZKF", "ZMVB", "ZRE4", "ZRE4J", "ZRE4VP", "ZRE4VPR", "ZTABFB", "ZVBEZ", "ZVBEZJ", "ZVE", "ZX", "ZZX", "af", "f")

    def __init__(self, **eingaben):
        self.AJAHR = 0
        self.ALTE = D("0")
        self.ALTER1 = 0
        self.ALV = 0
        self.ANP = D("0")
        self.ANTEIL1 = D("0")
        self.AVSATZAN = D("0")
        self.BBGKVPV = D("0")
        self.BBGRVALV = D("0")
        self.BK = D("0")
        self.BKS = D("0")
        self.BMG = D("0")
        self.DIFF = D("0")
        self.EFA = D("0")
        self.FVB = D("0")
        self.FVBSO = D("0")
        self.FVBZ = D("0")
        self.FVBZSO = D("0")
        self.GFB = D("0")
        self.HBALTE = D("0")
        self.HFVB = D("0")
        self.HFVBZ = D("0")
        self.HFVBZSO = D("0")
        self.HOCH = D("0")
        self.J = 0
        self.JBMG = D("0")
        self.JFREIB = D("0")
        self.JHINZU = D("0")
        self.JLFREIB = D("0")
        self.JLHINZU = D("0")
        self.JRE4 = D("0")
        self.JRE4ENT = D("0")
        self.JVBEZ = D("0")
        self.JW = D("0")
        self.K = 0
        self.KFB = D("0")
        self.KRV = 0
        self.KVSATZAN = D("0")
        self.KVZ = D("0")
        self.KZTAB = 0
        self.LSTJAHR = D("0")
        self.LSTLZZ = D("0")
        self.LSTOSO = D("0")
        self.LSTSO = D("0")
        self.LZZ = 1
        self.LZZFREIB = D("0")
        self.LZZHINZU = D("0")
        self.MBV = D("0")
        self.MIST = D("0")
        self.PKPV = D("0")
        self.PKPVAGZ = D("0")
        self.PKPVAGZJ = D("0")
        self.PKV = 0
        self.PVA = D("0")
        self.PVS = 0
        self.PVSATZAN = D("0")
        self.PVZ = 0
        self.R = 0
        self.RE4 = D("0")
        self.RVSATZAN = D("0")
        self.RW = D("0")
        self.SAP = D("0")
        self.SOLZFREI = D("0")
        self.SOLZJ = D("0")
        self.SOLZLZZ = D("0")
        self.SOLZMIN = D("0")
        self.SOLZS = D("0")
        self.SOLZSBMG = D("0")
        self.SOLZSZVE = D("0")
        self.SONSTB = D("0")
        self.SONSTENT = D("0")
        self.ST = D("0")
        self.ST1 = D("0")
        self.ST2 = D("0")
        self.STERBE = D("0")
        self.STKL = 1
        self.STS = D("0")
        self.VBEZ = D("0")
        self.VBEZB = D("0")
        self.VBEZBSO = D("0")
        self.VBEZM = D("0")
        self.VBEZS = D("0")
        self.VBS = D("0")
        self.VERGL = D("0")
        self.VFRB = D("0")
        self.VFRBS1 = D("0")
        self.VFRBS2 = D("0")
        self.VJAHR = 0
        self.VSP = D("0")
        self.VSPALV = D("0")
        self.VSPHB = D("0")
        self.VSPKVPV = D("0")
        self.VSPN = D("0")
        self.VSPR = D("0")
        self.W1STKL5 = D("0")
        self.W2STKL5 = D("0")
        self.W3STKL5 = D("0")
        self.WVFRB = D("0")
        self.WVFRBM = D("0")
        self.WVFRBO = D("0")
        self.X = D("0")
        self.Y = D("0")
        self.ZKF = D("0")
        self.ZMVB = 0
        self.ZRE4 = D("0")
        self.ZRE4J = D("0")
        self.ZRE4VP = D("0")
        self.ZRE4VPR = D("0")
        self.ZTABFB = D("0")
        self.ZVBEZ = D("0")
        self.ZVBEZJ = D("0")
        self.ZVE = D("0")
        self.ZX = D("0")
        self.ZZX = D("0")
        self.af = 1
        self.f = D("1.0")
        for name, wert in eingaben.items():
            if name not in self.__slots__:
                raise AttributeError(f"{name} kennt der Ablaufplan nicht")
            setattr(self, name, wert if isinstance(wert, (D, int)) else D(str(wert)))


# ————— Konstanten des Ablaufplans —————
TAB1 = [D("0"), D("0.4"), D("0.384"), D("0.368"), D("0.352"), D("0.336"), D("0.32"), D("0.304"), D("0.288"), D("0.272"), D("0.256"), D("0.24"), D("0.224"), D("0.208"), D("0.192"), D("0.176"), D("0.16"), D("0.152"), D("0.144"), D("0.14"), D("0.136"), D("0.132"), D("0.128"), D("0.124"), D("0.12"), D("0.116"), D("0.112"), D("0.108"), D("0.104"), D("0.1"), D("0.096"), D("0.092"), D("0.088"), D("0.084"), D("0.08"), D("0.076"), D("0.072"), D("0.068"), D("0.064"), D("0.06"), D("0.056"), D("0.052"), D("0.048"), D("0.044"), D("0.04"), D("0.036"), D("0.032"), D("0.028"), D("0.024"), D("0.02"), D("0.016"), D("0.012"), D("0.008"), D("0.004"), D("0")]
TAB2 = [D("0"), D("3000"), D("2880"), D("2760"), D("2640"), D("2520"), D("2400"), D("2280"), D("2160"), D("2040"), D("1920"), D("1800"), D("1680"), D("1560"), D("1440"), D("1320"), D("1200"), D("1140"), D("1080"), D("1050"), D("1020"), D("990"), D("960"), D("930"), D("900"), D("870"), D("840"), D("810"), D("780"), D("750"), D("720"), D("690"), D("660"), D("630"), D("600"), D("570"), D("540"), D("510"), D("480"), D("450"), D("420"), D("390"), D("360"), D("330"), D("300"), D("270"), D("240"), D("210"), D("180"), D("150"), D("120"), D("90"), D("60"), D("30"), D("0")]
TAB3 = [D("0"), D("900"), D("864"), D("828"), D("792"), D("756"), D("720"), D("684"), D("648"), D("612"), D("576"), D("540"), D("504"), D("468"), D("432"), D("396"), D("360"), D("342"), D("324"), D("315"), D("306"), D("297"), D("288"), D("279"), D("270"), D("261"), D("252"), D("243"), D("234"), D("225"), D("216"), D("207"), D("198"), D("189"), D("180"), D("171"), D("162"), D("153"), D("144"), D("135"), D("126"), D("117"), D("108"), D("99"), D("90"), D("81"), D("72"), D("63"), D("54"), D("45"), D("36"), D("27"), D("18"), D("9"), D("0")]
TAB4 = [D("0"), D("0.4"), D("0.384"), D("0.368"), D("0.352"), D("0.336"), D("0.32"), D("0.304"), D("0.288"), D("0.272"), D("0.256"), D("0.24"), D("0.224"), D("0.208"), D("0.192"), D("0.176"), D("0.16"), D("0.152"), D("0.144"), D("0.14"), D("0.136"), D("0.132"), D("0.128"), D("0.124"), D("0.12"), D("0.116"), D("0.112"), D("0.108"), D("0.104"), D("0.1"), D("0.096"), D("0.092"), D("0.088"), D("0.084"), D("0.08"), D("0.076"), D("0.072"), D("0.068"), D("0.064"), D("0.06"), D("0.056"), D("0.052"), D("0.048"), D("0.044"), D("0.04"), D("0.036"), D("0.032"), D("0.028"), D("0.024"), D("0.02"), D("0.016"), D("0.012"), D("0.008"), D("0.004"), D("0")]
TAB5 = [D("0"), D("1900"), D("1824"), D("1748"), D("1672"), D("1596"), D("1520"), D("1444"), D("1368"), D("1292"), D("1216"), D("1140"), D("1064"), D("988"), D("912"), D("836"), D("760"), D("722"), D("684"), D("665"), D("646"), D("627"), D("608"), D("589"), D("570"), D("551"), D("532"), D("513"), D("494"), D("475"), D("456"), D("437"), D("418"), D("399"), D("380"), D("361"), D("342"), D("323"), D("304"), D("285"), D("266"), D("247"), D("228"), D("209"), D("190"), D("171"), D("152"), D("133"), D("114"), D("95"), D("76"), D("57"), D("38"), D("19"), D("0")]
ZAHL1 = D("1")
ZAHL2 = D("2")
ZAHL5 = D("5")
ZAHL7 = D("7")
ZAHL12 = D("12")
ZAHL100 = D("100")
ZAHL360 = D("360")
ZAHL500 = D("500")
ZAHL700 = D("700")
ZAHL1000 = D("1000")
ZAHL10000 = D("10000")

def MPARA(z: Zustand) -> None:
    z.BBGRVALV = D("101400")
    z.AVSATZAN = D("0.013")
    z.RVSATZAN = D("0.093")
    z.BBGKVPV = D("69750")
    z.KVSATZAN = ((((z.KVZ / ZAHL2) / ZAHL100)) + D("0.07"))
    if (z.PVS == D("1")):
        z.PVSATZAN = D("0.023")
    else:
        z.PVSATZAN = D("0.018")
    if (z.PVZ == D("1")):
        z.PVSATZAN = (z.PVSATZAN + D("0.006"))
    else:
        z.PVSATZAN = (z.PVSATZAN - (z.PVA * D("0.0025")))
    z.W1STKL5 = D("14071")
    z.W2STKL5 = D("34939")
    z.W3STKL5 = D("222260")
    z.GFB = D("12348")
    z.SOLZFREI = D("20350")


def MRE4JL(z: Zustand) -> None:
    if (z.LZZ == D("1")):
        z.ZRE4J = teilen(z.RE4, ZAHL100, D("2"), 'ROUND_DOWN')
        z.ZVBEZJ = teilen(z.VBEZ, ZAHL100, D("2"), 'ROUND_DOWN')
        z.JLFREIB = teilen(z.LZZFREIB, ZAHL100, D("2"), 'ROUND_DOWN')
        z.JLHINZU = teilen(z.LZZHINZU, ZAHL100, D("2"), 'ROUND_DOWN')
    else:
        if (z.LZZ == D("2")):
            z.ZRE4J = teilen(((z.RE4 * ZAHL12)), ZAHL100, D("2"), 'ROUND_DOWN')
            z.ZVBEZJ = teilen(((z.VBEZ * ZAHL12)), ZAHL100, D("2"), 'ROUND_DOWN')
            z.JLFREIB = teilen(((z.LZZFREIB * ZAHL12)), ZAHL100, D("2"), 'ROUND_DOWN')
            z.JLHINZU = teilen(((z.LZZHINZU * ZAHL12)), ZAHL100, D("2"), 'ROUND_DOWN')
        else:
            if (z.LZZ == D("3")):
                z.ZRE4J = teilen(((z.RE4 * ZAHL360)), ZAHL700, D("2"), 'ROUND_DOWN')
                z.ZVBEZJ = teilen(((z.VBEZ * ZAHL360)), ZAHL700, D("2"), 'ROUND_DOWN')
                z.JLFREIB = teilen(((z.LZZFREIB * ZAHL360)), ZAHL700, D("2"), 'ROUND_DOWN')
                z.JLHINZU = teilen(((z.LZZHINZU * ZAHL360)), ZAHL700, D("2"), 'ROUND_DOWN')
            else:
                z.ZRE4J = teilen(((z.RE4 * ZAHL360)), ZAHL100, D("2"), 'ROUND_DOWN')
                z.ZVBEZJ = teilen(((z.VBEZ * ZAHL360)), ZAHL100, D("2"), 'ROUND_DOWN')
                z.JLFREIB = teilen(((z.LZZFREIB * ZAHL360)), ZAHL100, D("2"), 'ROUND_DOWN')
                z.JLHINZU = teilen(((z.LZZHINZU * ZAHL360)), ZAHL100, D("2"), 'ROUND_DOWN')
    if (z.af == D("0")):
        z.f = D("1")


def MRE4(z: Zustand) -> None:
    if (vergleiche(z.ZVBEZJ, D("0")) == D("0")):
        z.FVBZ = D("0")
        z.FVB = D("0")
        z.FVBZSO = D("0")
        z.FVBSO = D("0")
    else:
        if (z.VJAHR < D("2006")):
            z.J = D("1")
        else:
            if (z.VJAHR < D("2058")):
                z.J = (z.VJAHR - D("2004"))
            else:
                z.J = D("54")
        if (z.LZZ == D("1")):
            z.VBEZB = (((z.VBEZM * D(z.ZMVB))) + z.VBEZS)
            z.HFVB = stellen(((TAB2[int(z.J)] / ZAHL12) * D(z.ZMVB)), D("0"), 'ROUND_UP')
            z.FVBZ = stellen(((TAB3[int(z.J)] / ZAHL12) * D(z.ZMVB)), D("0"), 'ROUND_UP')
        else:
            z.VBEZB = stellen(((((z.VBEZM * ZAHL12)) + z.VBEZS)), D("2"), 'ROUND_DOWN')
            z.HFVB = TAB2[int(z.J)]
            z.FVBZ = TAB3[int(z.J)]
        z.FVB = stellen(((((z.VBEZB * TAB1[int(z.J)]))) / ZAHL100), D("2"), 'ROUND_UP')
        if (vergleiche(z.FVB, z.HFVB) == D("1")):
            z.FVB = z.HFVB
        if (vergleiche(z.FVB, z.ZVBEZJ) == D("1")):
            z.FVB = z.ZVBEZJ
        z.FVBSO = stellen(((z.FVB + (((z.VBEZBSO * TAB1[int(z.J)])) / ZAHL100))), D("2"), 'ROUND_UP')
        if (vergleiche(z.FVBSO, TAB2[int(z.J)]) == D("1")):
            z.FVBSO = TAB2[int(z.J)]
        z.HFVBZSO = stellen(((((((z.VBEZB + z.VBEZBSO)) / ZAHL100)) - z.FVBSO)), D("2"), 'ROUND_DOWN')
        z.FVBZSO = stellen(((z.FVBZ + ((z.VBEZBSO) / ZAHL100))), D("0"), 'ROUND_UP')
        if (vergleiche(z.FVBZSO, z.HFVBZSO) == D("1")):
            z.FVBZSO = stellen(z.HFVBZSO, D("0"), 'ROUND_UP')
        if (vergleiche(z.FVBZSO, TAB3[int(z.J)]) == D("1")):
            z.FVBZSO = TAB3[int(z.J)]
        z.HFVBZ = stellen(((((z.VBEZB / ZAHL100)) - z.FVB)), D("2"), 'ROUND_DOWN')
        if (vergleiche(z.FVBZ, z.HFVBZ) == D("1")):
            z.FVBZ = stellen(z.HFVBZ, D("0"), 'ROUND_UP')
    MRE4ALTE(z)


def MRE4ALTE(z: Zustand) -> None:
    if (z.ALTER1 == D("0")):
        z.ALTE = D("0")
    else:
        if (z.AJAHR < D("2006")):
            z.K = D("1")
        else:
            if (z.AJAHR < D("2058")):
                z.K = (z.AJAHR - D("2004"))
            else:
                z.K = D("54")
        z.BMG = (z.ZRE4J - z.ZVBEZJ)
        z.ALTE = stellen(((z.BMG * TAB4[int(z.K)])), D("0"), 'ROUND_UP')
        z.HBALTE = TAB5[int(z.K)]
        if (vergleiche(z.ALTE, z.HBALTE) == D("1")):
            z.ALTE = z.HBALTE


def MRE4ABZ(z: Zustand) -> None:
    z.ZRE4 = stellen((((((z.ZRE4J - z.FVB) - z.ALTE) - z.JLFREIB) + z.JLHINZU)), D("2"), 'ROUND_DOWN')
    if (vergleiche(z.ZRE4, D("0")) == (-D("1"))):
        z.ZRE4 = D("0")
    z.ZRE4VP = z.ZRE4J
    z.ZVBEZ = stellen((z.ZVBEZJ - z.FVB), D("2"), 'ROUND_DOWN')
    if (vergleiche(z.ZVBEZ, D("0")) == (-D("1"))):
        z.ZVBEZ = D("0")


def MBERECH(z: Zustand) -> None:
    MZTABFB(z)
    z.VFRB = stellen(((((z.ANP + (z.FVB + z.FVBZ))) * ZAHL100)), D("0"), 'ROUND_DOWN')
    MLSTJAHR(z)
    z.WVFRB = stellen(((((z.ZVE - z.GFB)) * ZAHL100)), D("0"), 'ROUND_DOWN')
    if (vergleiche(z.WVFRB, D("0")) == (-D("1"))):
        z.WVFRB = D("0")
    z.LSTJAHR = stellen(((z.ST * D(z.f))), D("0"), 'ROUND_DOWN')
    UPLSTLZZ(z)
    if (vergleiche(z.ZKF, D("0")) == D("1")):
        z.ZTABFB = (z.ZTABFB + z.KFB)
        MRE4ABZ(z)
        MLSTJAHR(z)
        z.JBMG = stellen(((z.ST * D(z.f))), D("0"), 'ROUND_DOWN')
    else:
        z.JBMG = z.LSTJAHR
    MSOLZ(z)


def MZTABFB(z: Zustand) -> None:
    z.ANP = D("0")
    if ((vergleiche(z.ZVBEZ, D("0")) >= D("0")) and (vergleiche(z.ZVBEZ, z.FVBZ) == (-D("1")))):
        z.FVBZ = D(int(z.ZVBEZ))
    if (z.STKL < D("6")):
        if (vergleiche(z.ZVBEZ, D("0")) == D("1")):
            if (vergleiche(((z.ZVBEZ - z.FVBZ)), D("102")) == (-D("1"))):
                z.ANP = stellen(((z.ZVBEZ - z.FVBZ)), D("0"), 'ROUND_UP')
            else:
                z.ANP = D("102")
    else:
        z.FVBZ = D("0")
        z.FVBZSO = D("0")
    if (z.STKL < D("6")):
        if (vergleiche(z.ZRE4, z.ZVBEZ) == D("1")):
            if (vergleiche((z.ZRE4 - z.ZVBEZ), D("1230")) == (-D("1"))):
                z.ANP = stellen(((z.ANP + z.ZRE4) - z.ZVBEZ), D("0"), 'ROUND_UP')
            else:
                z.ANP = (z.ANP + D("1230"))
    z.KZTAB = D("1")
    if (z.STKL == D("1")):
        z.SAP = D("36")
        z.KFB = stellen(((z.ZKF * D("9756"))), D("0"), 'ROUND_DOWN')
    else:
        if (z.STKL == D("2")):
            z.EFA = D("4260")
            z.SAP = D("36")
            z.KFB = stellen(((z.ZKF * D("9756"))), D("0"), 'ROUND_DOWN')
        else:
            if (z.STKL == D("3")):
                z.KZTAB = D("2")
                z.SAP = D("36")
                z.KFB = stellen(((z.ZKF * D("9756"))), D("0"), 'ROUND_DOWN')
            else:
                if (z.STKL == D("4")):
                    z.SAP = D("36")
                    z.KFB = stellen(((z.ZKF * D("4878"))), D("0"), 'ROUND_DOWN')
                else:
                    if (z.STKL == D("5")):
                        z.SAP = D("36")
                        z.KFB = D("0")
                    else:
                        z.KFB = D("0")
    z.ZTABFB = stellen(((((z.EFA + z.ANP) + z.SAP) + z.FVBZ)), D("2"), 'ROUND_DOWN')


def MLSTJAHR(z: Zustand) -> None:
    UPEVP(z)
    z.ZVE = ((z.ZRE4 - z.ZTABFB) - z.VSP)
    UPMLST(z)


def UPLSTLZZ(z: Zustand) -> None:
    z.JW = (z.LSTJAHR * ZAHL100)
    UPANTEIL(z)
    z.LSTLZZ = z.ANTEIL1


def UPMLST(z: Zustand) -> None:
    if (vergleiche(z.ZVE, ZAHL1) == (-D("1"))):
        z.ZVE = D("0")
        z.X = D("0")
    else:
        z.X = stellen(((z.ZVE / D(z.KZTAB))), D("0"), 'ROUND_DOWN')
    if (z.STKL < D("5")):
        UPTAB26(z)
    else:
        MST5_6(z)


def UPEVP(z: Zustand) -> None:
    if (z.KRV == D("1")):
        z.VSPR = D("0")
    else:
        if (vergleiche(z.ZRE4VP, z.BBGRVALV) == D("1")):
            z.ZRE4VPR = z.BBGRVALV
        else:
            z.ZRE4VPR = z.ZRE4VP
        z.VSPR = stellen(((z.ZRE4VPR * z.RVSATZAN)), D("2"), 'ROUND_DOWN')
    MVSPKVPV(z)
    if (z.ALV == D("1")):
        pass
    else:
        if (z.STKL == D("6")):
            pass
        else:
            MVSPHB(z)


def MVSPKVPV(z: Zustand) -> None:
    if (vergleiche(z.ZRE4VP, z.BBGKVPV) == D("1")):
        z.ZRE4VPR = z.BBGKVPV
    else:
        z.ZRE4VPR = z.ZRE4VP
    if (z.PKV > D("0")):
        if (z.STKL == D("6")):
            z.VSPKVPV = D("0")
        else:
            z.PKPVAGZJ = stellen(((z.PKPVAGZ * ZAHL12) / ZAHL100), D("2"), 'ROUND_DOWN')
            z.VSPKVPV = stellen(((z.PKPV * ZAHL12) / ZAHL100), D("2"), 'ROUND_DOWN')
            z.VSPKVPV = (z.VSPKVPV - z.PKPVAGZJ)
            if (vergleiche(z.VSPKVPV, D("0")) == (-D("1"))):
                z.VSPKVPV = D("0")
    else:
        z.VSPKVPV = stellen((z.ZRE4VPR * (z.KVSATZAN + z.PVSATZAN)), D("2"), 'ROUND_DOWN')
    z.VSP = stellen((z.VSPKVPV + z.VSPR), D("0"), 'ROUND_UP')


def MVSPHB(z: Zustand) -> None:
    if (vergleiche(z.ZRE4VP, z.BBGRVALV) == D("1")):
        z.ZRE4VPR = z.BBGRVALV
    else:
        z.ZRE4VPR = z.ZRE4VP
    z.VSPALV = stellen((z.AVSATZAN * z.ZRE4VPR), D("2"), 'ROUND_DOWN')
    z.VSPHB = stellen((z.VSPALV + z.VSPKVPV), D("2"), 'ROUND_DOWN')
    if (vergleiche(z.VSPHB, D("1900")) == D("1")):
        z.VSPHB = D("1900")
    z.VSPN = stellen((z.VSPR + z.VSPHB), D("0"), 'ROUND_UP')
    if (vergleiche(z.VSPN, z.VSP) == D("1")):
        z.VSP = z.VSPN


def MST5_6(z: Zustand) -> None:
    z.ZZX = z.X
    if (vergleiche(z.ZZX, z.W2STKL5) == D("1")):
        z.ZX = z.W2STKL5
        UP5_6(z)
        if (vergleiche(z.ZZX, z.W3STKL5) == D("1")):
            z.ST = stellen(((z.ST + (((z.W3STKL5 - z.W2STKL5)) * D("0.42")))), D("0"), 'ROUND_DOWN')
            z.ST = stellen(((z.ST + (((z.ZZX - z.W3STKL5)) * D("0.45")))), D("0"), 'ROUND_DOWN')
        else:
            z.ST = stellen(((z.ST + (((z.ZZX - z.W2STKL5)) * D("0.42")))), D("0"), 'ROUND_DOWN')
    else:
        z.ZX = z.ZZX
        UP5_6(z)
        if (vergleiche(z.ZZX, z.W1STKL5) == D("1")):
            z.VERGL = z.ST
            z.ZX = z.W1STKL5
            UP5_6(z)
            z.HOCH = stellen(((z.ST + (((z.ZZX - z.W1STKL5)) * D("0.42")))), D("0"), 'ROUND_DOWN')
            if (vergleiche(z.HOCH, z.VERGL) == (-D("1"))):
                z.ST = z.HOCH
            else:
                z.ST = z.VERGL


def UP5_6(z: Zustand) -> None:
    z.X = stellen(((z.ZX * D("1.25"))), D("0"), 'ROUND_DOWN')
    UPTAB26(z)
    z.ST1 = z.ST
    z.X = stellen(((z.ZX * D("0.75"))), D("0"), 'ROUND_DOWN')
    UPTAB26(z)
    z.ST2 = z.ST
    z.DIFF = (((z.ST1 - z.ST2)) * ZAHL2)
    z.MIST = stellen(((z.ZX * D("0.14"))), D("0"), 'ROUND_DOWN')
    if (vergleiche(z.MIST, z.DIFF) == D("1")):
        z.ST = z.MIST
    else:
        z.ST = z.DIFF


def MSOLZ(z: Zustand) -> None:
    z.SOLZFREI = ((z.SOLZFREI * D(z.KZTAB)))
    if (vergleiche(z.JBMG, z.SOLZFREI) == D("1")):
        z.SOLZJ = stellen((((z.JBMG * D("5.5"))) / ZAHL100), D("2"), 'ROUND_DOWN')
        z.SOLZMIN = stellen(((((z.JBMG - z.SOLZFREI)) * D("11.9")) / ZAHL100), D("2"), 'ROUND_DOWN')
        if (vergleiche(z.SOLZMIN, z.SOLZJ) == (-D("1"))):
            z.SOLZJ = z.SOLZMIN
        z.JW = stellen((z.SOLZJ * ZAHL100), D("0"), 'ROUND_DOWN')
        UPANTEIL(z)
        z.SOLZLZZ = z.ANTEIL1
    else:
        z.SOLZLZZ = D("0")
    if (z.R > D("0")):
        z.JW = (z.JBMG * ZAHL100)
        UPANTEIL(z)
        z.BK = z.ANTEIL1
    else:
        z.BK = D("0")


def UPANTEIL(z: Zustand) -> None:
    if (z.LZZ == D("1")):
        z.ANTEIL1 = z.JW
    else:
        if (z.LZZ == D("2")):
            z.ANTEIL1 = teilen(z.JW, ZAHL12, D("0"), 'ROUND_DOWN')
        else:
            if (z.LZZ == D("3")):
                z.ANTEIL1 = teilen(((z.JW * ZAHL7)), ZAHL360, D("0"), 'ROUND_DOWN')
            else:
                z.ANTEIL1 = teilen(z.JW, ZAHL360, D("0"), 'ROUND_DOWN')


def MSONST(z: Zustand) -> None:
    z.LZZ = D("1")
    if (z.ZMVB == D("0")):
        z.ZMVB = D("12")
    if ((vergleiche(z.SONSTB, D("0")) == D("0")) and (vergleiche(z.MBV, D("0")) == D("0"))):
        z.LSTSO = D("0")
        z.STS = D("0")
        z.SOLZS = D("0")
        z.BKS = D("0")
    else:
        MOSONST(z)
        z.ZRE4J = stellen(((((z.JRE4 + z.SONSTB)) / ZAHL100)), D("2"), 'ROUND_DOWN')
        z.ZVBEZJ = stellen(((((z.JVBEZ + z.VBS)) / ZAHL100)), D("2"), 'ROUND_DOWN')
        z.VBEZBSO = z.STERBE
        MRE4SONST(z)
        MLSTJAHR(z)
        z.WVFRBM = stellen((((z.ZVE - z.GFB)) * ZAHL100), D("2"), 'ROUND_DOWN')
        if (vergleiche(z.WVFRBM, D("0")) == (-D("1"))):
            z.WVFRBM = D("0")
        z.LSTSO = (z.ST * ZAHL100)
        z.STS = (teilen(((z.LSTSO - z.LSTOSO) * D(z.f)), ZAHL100, D("0"), 'ROUND_DOWN') * ZAHL100)
        STSMIN(z)


def STSMIN(z: Zustand) -> None:
    if (vergleiche(z.STS, D("0")) == (-D("1"))):
        if (vergleiche(z.MBV, D("0")) == D("0")):
            pass
        else:
            z.LSTLZZ = (z.LSTLZZ + z.STS)
            if (vergleiche(z.LSTLZZ, D("0")) == (-D("1"))):
                z.LSTLZZ = D("0")
            z.SOLZLZZ = stellen((z.SOLZLZZ + (z.STS * (D("5.5") / ZAHL100))), D("0"), 'ROUND_DOWN')
            if (vergleiche(z.SOLZLZZ, D("0")) == (-D("1"))):
                z.SOLZLZZ = D("0")
            z.BK = (z.BK + z.STS)
            if (vergleiche(z.BK, D("0")) == (-D("1"))):
                z.BK = D("0")
        z.STS = D("0")
        z.SOLZS = D("0")
    else:
        MSOLZSTS(z)
    if (z.R > D("0")):
        z.BKS = z.STS
    else:
        z.BKS = D("0")


def MSOLZSTS(z: Zustand) -> None:
    if (vergleiche(z.ZKF, D("0")) == D("1")):
        z.SOLZSZVE = (z.ZVE - z.KFB)
    else:
        z.SOLZSZVE = z.ZVE
    if (vergleiche(z.SOLZSZVE, D("1")) == (-D("1"))):
        z.SOLZSZVE = D("0")
        z.X = D("0")
    else:
        z.X = teilen(z.SOLZSZVE, D(z.KZTAB), D("0"), 'ROUND_DOWN')
    if (z.STKL < D("5")):
        UPTAB26(z)
    else:
        MST5_6(z)
    z.SOLZSBMG = stellen((z.ST * D(z.f)), D("0"), 'ROUND_DOWN')
    if (vergleiche(z.SOLZSBMG, z.SOLZFREI) == D("1")):
        z.SOLZS = teilen((z.STS * D("5.5")), ZAHL100, D("0"), 'ROUND_DOWN')
    else:
        z.SOLZS = D("0")


def MOSONST(z: Zustand) -> None:
    z.ZRE4J = stellen(((z.JRE4 / ZAHL100)), D("2"), 'ROUND_DOWN')
    z.ZVBEZJ = stellen(((z.JVBEZ / ZAHL100)), D("2"), 'ROUND_DOWN')
    z.JLFREIB = teilen(z.JFREIB, ZAHL100, D("2"), 'ROUND_DOWN')
    z.JLHINZU = teilen(z.JHINZU, ZAHL100, D("2"), 'ROUND_DOWN')
    MRE4(z)
    MRE4ABZ(z)
    z.ZRE4VP = (z.ZRE4VP - (z.JRE4ENT / ZAHL100))
    MZTABFB(z)
    z.VFRBS1 = stellen(((((z.ANP + (z.FVB + z.FVBZ))) * ZAHL100)), D("2"), 'ROUND_DOWN')
    MLSTJAHR(z)
    z.WVFRBO = stellen(((((z.ZVE - z.GFB)) * ZAHL100)), D("2"), 'ROUND_DOWN')
    if (vergleiche(z.WVFRBO, D("0")) == (-D("1"))):
        z.WVFRBO = D("0")
    z.LSTOSO = (z.ST * ZAHL100)


def MRE4SONST(z: Zustand) -> None:
    MRE4(z)
    z.FVB = z.FVBSO
    MRE4ABZ(z)
    z.ZRE4VP = (((z.ZRE4VP + (z.MBV / ZAHL100)) - (z.JRE4ENT / ZAHL100)) - (z.SONSTENT / ZAHL100))
    z.FVBZ = z.FVBZSO
    MZTABFB(z)
    z.VFRBS2 = ((((((((z.ANP + z.FVB) + z.FVBZ))) * ZAHL100))) - z.VFRBS1)


def UPTAB26(z: Zustand) -> None:
    if (vergleiche(z.X, (z.GFB + ZAHL1)) == (-D("1"))):
        z.ST = D("0")
    else:
        if (vergleiche(z.X, D("17800")) == (-D("1"))):
            z.Y = teilen(((z.X - z.GFB)), ZAHL10000, D("6"), 'ROUND_DOWN')
            z.RW = (z.Y * D("914.51"))
            z.RW = (z.RW + D("1400"))
            z.ST = stellen(((z.RW * z.Y)), D("0"), 'ROUND_DOWN')
        else:
            if (vergleiche(z.X, D("69879")) == (-D("1"))):
                z.Y = teilen(((z.X - D("17799"))), ZAHL10000, D("6"), 'ROUND_DOWN')
                z.RW = (z.Y * D("173.1"))
                z.RW = (z.RW + D("2397"))
                z.RW = (z.RW * z.Y)
                z.ST = stellen(((z.RW + D("1034.87"))), D("0"), 'ROUND_DOWN')
            else:
                if (vergleiche(z.X, D("277826")) == (-D("1"))):
                    z.ST = stellen(((((z.X * D("0.42"))) - D("11135.63"))), D("0"), 'ROUND_DOWN')
                else:
                    z.ST = stellen(((((z.X * D("0.45"))) - D("19470.38"))), D("0"), 'ROUND_DOWN')
    z.ST = (z.ST * D(z.KZTAB))


def berechnen(z: Zustand) -> Zustand:
    """Der Hauptlauf des Ablaufplans."""
    MPARA(z)
    MRE4JL(z)
    z.VBEZBSO = D("0")
    MRE4(z)
    MRE4ABZ(z)
    MBERECH(z)
    MSONST(z)
    return z
