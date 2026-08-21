"""Die Vertragskiste — was jeden Monat sicher abgeht, und wann zu handeln ist.

Reine Rechnung ohne I/O: die Verträge kommen als Liste aus `babu_web`
(gelesene `.vertrag.json`-Sidecars), damit alles ohne Server testbar ist.

Grundhaltung wie überall in babu: was sich nicht sicher lesen lässt, wird
NICHT geraten. Eine verpasste Kündigungsfrist kostet ein weiteres Jahr —
ein erfundenes Datum wäre schlimmer als ein ehrliches „steht im Vertrag".
"""
from __future__ import annotations

import datetime as dt
import re

# Wie weit voraus eine Frist als „steht an" gilt.
VORLAUF_TAGE = 90

_ZAHLWORT = {"ein": 1, "eine": 1, "einem": 1, "zwei": 2, "drei": 3, "vier": 4,
             "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9,
             "zehn": 10, "elf": 11, "zwölf": 12}


def frist_monate(text: str | None) -> int | None:
    """Kündigungsfrist in Monaten — oder None, wenn nicht sicher lesbar.

    Wochenfristen geben wir bewusst nicht zurück: „vier Wochen zum
    Monatsende" ist nicht dasselbe wie ein Monat, und falsch gerechnet
    kostet es Geld.
    """
    if not text:
        return None
    t = str(text).strip().lower()
    if "woche" in t:
        return None
    m = re.search(r"(\d{1,2})\s*monat", t)
    if m:
        monate = int(m.group(1))
        return monate if 1 <= monate <= 24 else None
    m = re.search(r"([a-zäöü]+)\s*monat", t)
    if m:
        return _ZAHLWORT.get(m.group(1))
    return None


def frist_ziel(text: str | None) -> str | None:
    """Zum Quartals-, Monats- oder Jahresende? None = kein Zielpunkt genannt."""
    if not text:
        return None
    t = str(text).strip().lower()
    if "quartal" in t:
        return "quartal"
    if "jahresende" in t or "jahres­ende" in t:
        return "jahr"
    if "monatsende" in t or "monatsschluss" in t:
        return "monat"
    return None


def _datum(wert: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(wert)[:10])
    except (TypeError, ValueError):
        return None


def _monatsende(jahr: int, monat: int) -> dt.date:
    return (dt.date(jahr + monat // 12, monat % 12 + 1, 1) - dt.timedelta(days=1))


def _monate_zurueck(datum: dt.date, monate: int) -> dt.date:
    """Datum minus n Monate, auf den Monatsletzten geklemmt."""
    gesamt = datum.year * 12 + (datum.month - 1) - monate
    jahr, monat = divmod(gesamt, 12)
    letzter = _monatsende(jahr, monat + 1).day
    return dt.date(jahr, monat + 1, min(datum.day, letzter))


def _auf_zielpunkt(datum: dt.date, ziel: str | None) -> dt.date:
    """Der letzte Tag, der noch vor dem Zielpunkt liegt."""
    if ziel == "monat":
        return _monatsende(datum.year, datum.month)
    if ziel == "quartal":
        quartalsmonat = ((datum.month - 1) // 3) * 3 + 3
        return _monatsende(datum.year, quartalsmonat)
    if ziel == "jahr":
        return dt.date(datum.year, 12, 31)
    return datum


def kuendigen_bis(vertrag: dict, heute: dt.date) -> dict:
    """Bis wann muss die Kündigung raus sein?

    Braucht beides: ein Laufzeitende und eine lesbare Frist. Fehlt eines,
    sagt babu das — und nennt kein Datum.
    """
    ende = _datum((vertrag or {}).get("laufzeit_bis"))
    monate = frist_monate((vertrag or {}).get("kuendigungsfrist"))
    if ende is None or monate is None:
        return {"datum": None, "sicher": False, "tage": None, "vorbei": False,
                "hinweis": "Die Frist steht in deinem Vertrag — babu konnte sie "
                           "nicht sicher lesen."}
    ziel = frist_ziel(vertrag.get("kuendigungsfrist"))
    spaetestens = _auf_zielpunkt(_monate_zurueck(ende, monate), ziel)
    # Der Zielpunkt darf die Frist nicht verkürzen: „3 Monate zum Quartalsende"
    # heißt mindestens 3 Monate, das Quartalsende davor.
    if spaetestens > _monate_zurueck(ende, monate):
        spaetestens = _auf_zielpunkt(
            _monate_zurueck(ende, monate) - dt.timedelta(days=1), ziel)
    return {"datum": spaetestens.isoformat(), "sicher": True,
            "tage": (spaetestens - heute).days,
            "vorbei": spaetestens < heute,
            "hinweis": ""}


def _laeuft_noch(vertrag: dict, heute: dt.date) -> bool:
    ende = _datum(vertrag.get("laufzeit_bis"))
    return ende is None or ende >= heute


def uebersicht(vertraege: list[dict], heute: dt.date | None = None) -> dict:
    """Die Kiste: Dauerkosten im Monat, und was demnächst zu tun ist."""
    heute = heute or dt.date.today()
    laufend = [v for v in (vertraege or []) if isinstance(v, dict)
               and _laeuft_noch(v, heute)]

    zeilen: list[dict] = []
    monatlich = 0.0
    ohne_betrag = 0
    for v in laufend:
        betrag = v.get("betrag_monat")
        if betrag is None:
            ohne_betrag += 1
        else:
            monatlich += float(betrag)
        frist = kuendigen_bis(v, heute)
        zeilen.append({
            "art": v.get("art"), "art_name": v.get("art_name"),
            "partner": v.get("partner"), "betrag_monat": betrag,
            "konto_skr04": v.get("konto_skr04"),
            "laufzeit_bis": v.get("laufzeit_bis"),
            "kuendigungsfrist": v.get("kuendigungsfrist"),
            "kuendigen_bis": frist,
        })
    zeilen.sort(key=lambda z: -(z["betrag_monat"] or 0.0))

    anstehend = [z for z in zeilen
                 if z["kuendigen_bis"]["sicher"]
                 and not z["kuendigen_bis"]["vorbei"]
                 and z["kuendigen_bis"]["tage"] is not None
                 and z["kuendigen_bis"]["tage"] <= VORLAUF_TAGE]
    anstehend = [dict(z, tage=z["kuendigen_bis"]["tage"],
                      datum=z["kuendigen_bis"]["datum"]) for z in anstehend]
    anstehend.sort(key=lambda z: z["tage"])

    return {"monatlich": round(monatlich, 2),
            "jaehrlich": round(monatlich * 12, 2),
            "anzahl": len(laufend), "ohne_betrag": ohne_betrag,
            "vertraege": zeilen, "anstehend": anstehend}
