"""Gutschrift für die Provision einer Ambassadorin (seit 03.10.2026).

0711 rechnet die Provision ab, nicht die Ambassadorin: Gutschriftverfahren
nach § 14 Abs. 2 Satz 2 UStG, vereinbart in der Ambassador-Vereinbarung und
bei jedem Profil bestätigt. Je Auszahlungslauf und Ambassadorin genau eine
Gutschrift mit fortlaufender Nummer (GS-JJJJ-NNNN, nie wiederverwendet).

Drei Fälle (die Ambassadorin wählt selbst, Texte von der Kanzlei geprüft):

    ust      umsatzsteuerpflichtig — Netto + 19 % USt, Titel „Gutschrift"
    klein    Kleinunternehmerin § 19 UStG — keine USt, Hinweis auf § 19
    privat   gelegentliche Vermittlung als Privatperson — keine USt,
             Titel „Provisionsabrechnung" (keine Rechnung im Sinne des UStG)

Das PDF entsteht mit dem eingebauten Schreiber aus vordrucke.py (keine
Bibliothek im Container), aber mit eigenem Kopf: `vordrucke._kopf`
schreibt „ENTWURF" — eine Gutschrift ist kein Entwurf.
"""
from __future__ import annotations

import datetime as dt

from vordrucke import _BREITE, _Blatt, _eur

STEUERSTATUS = {
    "ust": "umsatzsteuerpflichtig",
    "klein": "Kleinunternehmerin nach § 19 UStG",
    "privat": "Privatperson (gelegentliche Vermittlung)",
}

_PAKET_NAME = {"solo": "Solo", "salon": "Salon", "plus": "Salon Plus"}
_MEILENSTEIN = {"gezeichnet": "Abschluss", "gehalten": "3 Monate dabei",
                "storno_gezeichnet": "Korrektur: Zahlung zurückgebucht",
                "storno_gehalten": "Korrektur: Zahlung zurückgebucht"}


def titel(steuerstatus: str) -> str:
    return "Provisionsabrechnung" if steuerstatus == "privat" else "Gutschrift"


def nummer(c, jahr: int) -> str:
    """Die nächste Nummer des Jahres. Im laufenden `with _DB_LOCK`-Block
    rufen; der eindeutige Index auf gutschrift_nr fängt jeden Wettlauf."""
    z = c.execute("SELECT gutschrift_nr FROM ambassador_auszahlung WHERE "
                  "gutschrift_nr LIKE ? ORDER BY gutschrift_nr DESC",
                  (f"GS-{jahr}-%",)).fetchone()
    letzte = int(z[0].rsplit("-", 1)[1]) if z and z[0] else 0
    return f"GS-{jahr}-{letzte + 1:04d}"


def iban_maskiert(iban: str) -> str:
    i = (iban or "").replace(" ", "")
    return f"{i[:2]}… {i[-4:]}" if len(i) > 6 else "—"


def _de(tag: str | dt.date) -> str:
    t = tag if isinstance(tag, dt.date) else dt.date.fromisoformat(str(tag)[:10])
    return t.strftime("%d.%m.%Y")


def pdf(beleg: dict) -> bytes:
    """Das Blatt aus dem Schnappschuss `beleg` (so, wie er gespeichert wird):

    nr, datum, von, bis, aussteller{name, anschrift, ust_id},
    empfaengerin{name, anschrift, steuerstatus, steuernummer, ust_id, iban},
    posten[{datum, salon, meilenstein, paket, netto_cent}],
    netto_cent, ust_cent, brutto_cent, zustimmung_am
    """
    a, e = beleg["aussteller"], beleg["empfaengerin"]
    status = e["steuerstatus"]
    b = _Blatt()
    b.zeile(a["name"], fett=True, size=10)
    for z in str(a.get("anschrift") or "").split("\n"):
        if z.strip():
            b.zeile(z.strip(), size=8.5)
    if a.get("ust_id"):
        b.zeile(f"USt-IdNr. {a['ust_id']}", size=8.5)
    b.frei(14)
    b.zeile("An", size=8)
    b.zeile(e["name"], size=10)
    for z in str(e.get("anschrift") or "").split("\n"):
        if z.strip():
            b.zeile(z.strip(), size=9.5)
    if e.get("ust_id"):
        b.zeile(f"USt-IdNr. {e['ust_id']}", size=8.5)
    elif e.get("steuernummer"):
        b.zeile(f"Steuernummer {e['steuernummer']}", size=8.5)
    b.frei(14)
    b.zeile(f"{titel(status)} {beleg['nr']}", fett=True, size=15, abstand=22)
    b.zeile(f"Datum {_de(beleg['datum'])} · Leistungszeitraum "
            f"{_de(beleg['von'])} bis {_de(beleg['bis'])}", size=8.5)
    b.linie(stark=True)
    b.zeile("Provision für vermittelte babu-Abos (Ambassador-Programm)", size=9.5)
    b.frei(6)
    b.zeile("Datum      Salon", "Betrag EUR", fett=True, size=8.5)
    b.linie()
    for p in beleg["posten"]:
        text = (f"{_de(p['datum'])}  {p.get('salon') or 'Salon'} — "
                f"{_MEILENSTEIN.get(p['meilenstein'], p['meilenstein'])}"
                + (f", Paket {_PAKET_NAME.get(p['paket'], p['paket'])}" if p.get("paket") else ""))
        b.zeile(text[:90], _eur(p["netto_cent"] / 100), size=9)
    b.linie()
    if status == "ust":
        b.zeile("Summe netto", _eur(beleg["netto_cent"] / 100), size=9.5)
        b.zeile("Umsatzsteuer 19 %", _eur(beleg["ust_cent"] / 100), size=9.5)
        b.zeile("Auszahlungsbetrag", _eur(beleg["brutto_cent"] / 100), fett=True,
                size=10.5)
    else:
        b.zeile("Auszahlungsbetrag", _eur(beleg["brutto_cent"] / 100), fett=True,
                size=10.5)
        b.frei(4)
        if status == "klein":
            b.zeile("Kein Ausweis von Umsatzsteuer: die Leistende ist "
                    "Kleinunternehmerin nach § 19 UStG.", size=8.5)
        else:
            b.zeile("Keine Umsatzsteuer: gelegentliche Vermittlung durch eine "
                    "Privatperson. Die Einkünfte versteuert die Empfängerin selbst.",
                    size=8.5)
    b.frei(10)
    b.zeile(f"Die Überweisung geht auf das Konto {iban_maskiert(e.get('iban', ''))}.",
            size=9)
    b.frei(16)
    b.linie()
    if status in ("ust", "klein"):
        b.zeile("Abrechnung im Gutschriftverfahren nach § 14 Abs. 2 Satz 2 UStG, "
                f"vereinbart am {_de(beleg['zustimmung_am'])}.", size=7.5, abstand=10)
        b.zeile("Widerspricht die Empfängerin dieser Gutschrift, verliert sie ihre "
                "Wirkung als Rechnung — bitte dann an den Aussteller wenden.",
                size=7.5, abstand=10)
    b.zeile(f"{a['name']} · erstellt mit babu", size=7.5, abstand=10,
            rechts_x=_BREITE - 52)
    return b.bytes()
