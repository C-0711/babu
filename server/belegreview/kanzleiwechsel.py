"""Der Brief an die bisherige Kanzlei: Daten anfordern, Mandat beenden.

Die Landingpage verspricht seit Langem „Vorlage bekommst du von uns" —
hier ist sie. Wer wechselt, braucht zwei Dinge von der alten Kanzlei: die
Daten in einer Form, die das neue System lesen kann, und eine saubere
Beendigung des Mandats.

Die angeforderte Liste ist NICHT aus einem Musterbrief abgeschrieben,
sondern aus dem, was babu tatsächlich verarbeitet: den Buchungsstapel
liest `historie.py`, Kontenliste, Anlagenliste, Gewinnrechnung und
Bescheide liest `abschluss_lesen.py`, die Lohnkonten braucht `lohnlauf`.
Deshalb steht hinter jedem Punkt, WOZU er gebraucht wird — das macht die
Bitte für die Kanzlei nachvollziehbar und verhindert, dass etwas
angefordert wird, das nachher niemand öffnet.

Was hier bewusst FEHLT: Paragrafen. Ein Herausgabeanspruch besteht, und
jede Musterbrief-Sammlung im Netz zitiert dazu Vorschriften — belegen
kann babu sie nicht, und eine erfundene Fundstelle in einem Brief an eine
Kanzlei ist schlimmer als keine. Der Brief bittet klar und begründet
sachlich; die rechtliche Einordnung bleibt, wo sie hingehört.

Ebenso fehlt eine Kündigungsfrist: die steht im Mandatsvertrag, und den
kennt babu nicht. Der Brief kündigt „zum nächstmöglichen Zeitpunkt" und
bittet um Bestätigung, wann das ist.

Reine Rechnung ohne I/O.
"""
from __future__ import annotations

import time

# Was angefordert wird — und wozu babu es braucht. Die Reihenfolge ist die
# des Nutzens: ohne den Buchungsstapel fehlt die halbe Vergangenheit,
# ohne die Anlagenliste läuft keine Abschreibung weiter.
UNTERLAGEN = [
    ("Buchungsstapel im DATEV-Format (ASCII/EXTF), je Wirtschaftsjahr",
     "damit die Monate der Vergangenheit übernommen werden können"),
    ("Sachkonten-Beschriftungen des verwendeten Kontenrahmens",
     "damit die Kontonummern lesbare Namen behalten"),
    ("Summen- und Saldenlisten je Jahr",
     "als Gegenprobe zu den übernommenen Buchungen"),
    ("Anlagenverzeichnis mit Anschaffungsdatum, Anschaffungskosten, "
     "bisheriger Abschreibung und Restbuchwert",
     "damit die Abschreibungen ohne Bruch weiterlaufen"),
    ("Offene-Posten-Listen (Debitoren und Kreditoren) zum Stichtag",
     "damit offene Forderungen und Verbindlichkeiten nicht verloren gehen"),
    ("Jahresabschlüsse bzw. Einnahmen-Überschuss-Rechnungen und die "
     "zugehörigen Steuerbescheide der letzten Jahre",
     "für den Vergleich und die Nachweise"),
    ("Saldenvorträge zum Übergabestichtag (Kasse, Bank)",
     "damit das Kassenbuch nicht bei null beginnt"),
]

# Nur wenn dort auch Lohn gemacht wurde — sonst steht es nicht im Brief.
LOHN_UNTERLAGEN = [
    ("Lohnkonten und Lohnjournale der laufenden und der abgeschlossenen "
     "Jahre sowie die Meldebescheinigungen zur Sozialversicherung",
     "damit die Lohnabrechnung ohne Lücke fortgeführt werden kann"),
]

# Was zusätzlich zu klären ist, wenn das Mandat endet.
BEENDIGUNG = [
    "die mir überlassenen Originalunterlagen (Belegordner, Verträge, "
    "Bescheide) zurückzugeben",
    "die für mich erteilte Vollmacht gegenüber dem Finanzamt zu löschen "
    "und mir das zu bestätigen",
    "mir mitzuteilen, welche Arbeiten noch offen sind und bis wann sie "
    "abgeschlossen werden",
]

FRIST_TAGE = 14


def _datum(t: time.struct_time | None = None) -> str:
    return time.strftime("%d.%m.%Y", t or time.localtime())


def _frist(tage: int = FRIST_TAGE, t: time.struct_time | None = None) -> str:
    return time.strftime("%d.%m.%Y",
                         time.localtime(time.mktime(t or time.localtime())
                                        + tage * 86400))


def unterlagenliste(mit_lohn: bool = False) -> list[tuple[str, str]]:
    return list(UNTERLAGEN) + (list(LOHN_UNTERLAGEN) if mit_lohn else [])


def brief(betrieb: dict, kanzlei: dict, *, kuendigen: bool = True,
          mit_lohn: bool = False, frist_tage: int = FRIST_TAGE,
          jetzt: time.struct_time | None = None) -> dict:
    """Der Brief als Text — Absender, Anrede, Bitte, Liste, Frist.

    `kuendigen=False` fordert nur die Daten an; das ist der Fall, in dem
    jemand die Kanzlei behalten und babu parallel nutzen will.
    """
    name = (betrieb.get("betrieb_name") or "").strip() or "Mein Betrieb"
    anschrift = (betrieb.get("anschrift") or "").strip()
    stnr = (betrieb.get("steuernummer") or "").strip()
    inhaberin = (betrieb.get("inhaberin") or "").strip()
    kanzlei_name = (kanzlei.get("name") or "").strip() or "Ihre Kanzlei"
    mandant_nr = (kanzlei.get("mandantennummer") or "").strip()

    kopf = [name]
    if anschrift:
        kopf.append(anschrift)
    kopf += ["", kanzlei_name]
    if (kanzlei.get("anschrift") or "").strip():
        kopf.append(kanzlei["anschrift"].strip())
    kopf += ["", _datum(jetzt), ""]

    betreff = ("Beendigung des Mandats und Herausgabe meiner Daten"
               if kuendigen else "Herausgabe meiner Buchführungsdaten")
    kennung = []
    if stnr:
        kennung.append(f"Steuernummer {stnr}")
    if mandant_nr:
        kennung.append(f"Mandantennummer {mandant_nr}")

    text = list(kopf)
    text.append(betreff)
    if kennung:
        text.append(" · ".join(kennung))
    text += ["", "Sehr geehrte Damen und Herren,", ""]

    if kuendigen:
        text += [
            "hiermit kündige ich das bestehende Mandat zum nächstmöglichen "
            "Zeitpunkt. Bitte bestätigen Sie mir kurz, wann das Mandat "
            "endet.", "",
            "Ich führe meine Buchhaltung künftig selbst und bitte Sie "
            "deshalb, mir meine Daten in einer Form zu überlassen, die ich "
            "einlesen kann:", ""]
    else:
        text += [
            "ich führe meine Buchhaltung künftig mit einem eigenen System "
            "und bitte Sie, mir meine Daten in einer Form zu überlassen, "
            "die ich einlesen kann:", ""]

    for i, (was, wozu) in enumerate(unterlagenliste(mit_lohn), 1):
        text.append(f"{i}. {was}")
        text.append(f"   ({wozu})")
    text.append("")

    if kuendigen:
        text.append("Darüber hinaus bitte ich Sie,")
        for punkt in BEENDIGUNG:
            text.append(f"— {punkt},")
        text[-1] = text[-1][:-1] + "."
        text.append("")

    text += [
        f"Für die Übergabe schlage ich den {_frist(frist_tage, jetzt)} vor. "
        "Falls Ihnen etwas davon in einem anderen Format leichter fällt, "
        "sagen Sie mir gern Bescheid — ich richte mich danach.", "",
        "Offene Rechnungen begleiche ich selbstverständlich; sagen Sie mir "
        "bitte, ob noch etwas aussteht.", "",
        "Für die Zusammenarbeit bedanke ich mich.", "",
        "Mit freundlichen Grüßen", "",
        inhaberin or name,
    ]
    return {
        "betreff": betreff,
        "text": "\n".join(text),
        "empfaenger": kanzlei.get("email") or None,
        "frist": _frist(frist_tage, jetzt),
        "punkte": len(unterlagenliste(mit_lohn)),
        "kuendigt": bool(kuendigen),
        "hinweis": ("Das ist eine Vorlage, kein Rechtsrat. Lies sie durch "
                    "und ändere, was nicht stimmt — und schau in deinen "
                    "Vertrag, ob dort eine Kündigungsfrist steht."),
    }
