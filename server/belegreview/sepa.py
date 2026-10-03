"""SEPA-Sammelüberweisung als Datei für das Online-Banking (seit 03.10.2026).

Nina zahlt die Provisionen der Ambassadorinnen quartalsweise aus. babu
erzeugt dafür EINE Datei im Format pain.001.001.09 (DK-Anlage 3, Version
3.7 — das lesen die deutschen Banken seit November 2023); sie lädt sie in
das Online-Banking von 0711 hoch und gibt sie dort frei. babu selbst
überweist nichts.

Nur die Pflichtfelder, nichts Ausgefallenes:

    GrpHdr      MsgId, Zeitpunkt, Anzahl, Summe, Auftraggeber
    PmtInf      ein Zahlungsblock: Überweisung (TRF), SEPA, Ausführungstag,
                Konto von 0711, Entgelt geteilt (SLEV)
    CdtTrfTxInf je Ambassadorin: Gutschrift-Nr. als Ende-zu-Ende-Referenz,
                Betrag, Name, IBAN, Verwendungszweck

Texte gehen nur im SEPA-Zeichensatz hinaus (Umlaute umgeschrieben).
"""
from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET

NS = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"

_UMSCHRIFT = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
              "ß": "ss", "&": "+", "é": "e", "è": "e", "á": "a", "à": "a",
              "ó": "o", "ò": "o", "ç": "c", "ñ": "n", "„": "", "“": "", "”": "",
              "–": "-", "—": "-"}
_ERLAUBT = re.compile(r"[^A-Za-z0-9/\-?:().,'+ ]")


def umschrift(text: str, laenge: int) -> str:
    """Auf den SEPA-Zeichensatz bringen und kürzen."""
    t = "".join(_UMSCHRIFT.get(z, z) for z in str(text or ""))
    t = _ERLAUBT.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()[:laenge]


def _el(eltern, name: str, text: str | None = None, **attr) -> ET.Element:
    e = ET.SubElement(eltern, name, attr)
    if text is not None:
        e.text = text
    return e


def _betrag(cent: int) -> str:
    return f"{cent // 100}.{cent % 100:02d}"


def pain001(*, msg_id: str, erstellt: dt.datetime, ausfuehrung: dt.date,
            schuldner: dict, zahlungen: list[dict]) -> bytes:
    """Die Datei. `schuldner`: name, iban, bic (optional).
    `zahlungen`: je {e2e, betrag_cent, name, iban, zweck}."""
    if not zahlungen:
        raise ValueError("keine Zahlungen")
    if any(z["betrag_cent"] <= 0 for z in zahlungen):
        raise ValueError("nur positive Beträge")
    summe = sum(z["betrag_cent"] for z in zahlungen)
    doc = ET.Element("Document", {"xmlns": NS})
    wurzel = _el(doc, "CstmrCdtTrfInitn")
    kopf = _el(wurzel, "GrpHdr")
    _el(kopf, "MsgId", umschrift(msg_id, 35))
    _el(kopf, "CreDtTm", erstellt.strftime("%Y-%m-%dT%H:%M:%S"))
    _el(kopf, "NbOfTxs", str(len(zahlungen)))
    _el(kopf, "CtrlSum", _betrag(summe))
    _el(_el(kopf, "InitgPty"), "Nm", umschrift(schuldner["name"], 70))

    block = _el(wurzel, "PmtInf")
    _el(block, "PmtInfId", umschrift(msg_id, 35))
    _el(block, "PmtMtd", "TRF")
    _el(block, "BtchBookg", "false")
    _el(block, "NbOfTxs", str(len(zahlungen)))
    _el(block, "CtrlSum", _betrag(summe))
    _el(_el(_el(block, "PmtTpInf"), "SvcLvl"), "Cd", "SEPA")
    _el(_el(block, "ReqdExctnDt"), "Dt", ausfuehrung.isoformat())
    _el(_el(block, "Dbtr"), "Nm", umschrift(schuldner["name"], 70))
    _el(_el(_el(block, "DbtrAcct"), "Id"), "IBAN", schuldner["iban"].replace(" ", ""))
    institut = _el(_el(block, "DbtrAgt"), "FinInstnId")
    if schuldner.get("bic"):
        _el(institut, "BICFI", schuldner["bic"].replace(" ", ""))
    else:
        _el(_el(institut, "Othr"), "Id", "NOTPROVIDED")
    _el(block, "ChrgBr", "SLEV")
    for z in zahlungen:
        tx = _el(block, "CdtTrfTxInf")
        _el(_el(tx, "PmtId"), "EndToEndId", umschrift(z["e2e"], 35))
        _el(_el(tx, "Amt"), "InstdAmt", _betrag(z["betrag_cent"]), Ccy="EUR")
        _el(_el(tx, "Cdtr"), "Nm", umschrift(z["name"], 70))
        _el(_el(_el(tx, "CdtrAcct"), "Id"), "IBAN", z["iban"].replace(" ", ""))
        _el(_el(tx, "RmtInf"), "Ustrd", umschrift(z["zweck"], 140))
    ET.indent(doc)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(doc, encoding="utf-8")
