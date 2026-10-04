"""Wer reicht beim Finanzamt ein — das Steuerbüro oder die Unternehmerin selbst?

Independence Day, Stufe A (04.10.2026). babu gibt es mit und ohne Steuerbüro;
beides muss gehen. Der Modus regelt NICHT den Zugriff (jede Inhaberin darf
prüfen, korrigieren, abschließen), sondern den letzten Schritt im Monat, die
Texte und die Fristen. Diese Datei ist die einzige Stelle, die die Einstellung
`steuerberater_modus` deutet — alte und neue Antworten.

Reine Rechnung ohne Datenbank.
"""
from __future__ import annotations

STEUERBUERO = "steuerbuero"
SELBST = "selbst"

_STEUERBUERO = {"mein steuerbüro", "mein steuerbüro bleibt", "vorbereitend",
                "steuerbuero"}
_SELBST = {"ich selbst (independence day)", "ich selbst", "alles über babu",
           "selbst"}


def modus(einstellungen: dict | None, betreut: bool = False) -> str:
    """`steuerbuero` oder `selbst`.

    Reihenfolge: die ausdrückliche Antwort; sonst „Hast du einen Steuerberater?“;
    sonst die Betreuung — ein Betrieb, den ein echtes Steuerbüro betreut
    (`betreut`), bleibt beim Steuerbüro.
    """
    e = einstellungen or {}
    m = str(e.get("steuerberater_modus") or "").strip().lower()
    if m in _STEUERBUERO:
        return STEUERBUERO
    if m in _SELBST:
        return SELBST
    s = str(e.get("steuerberater_status") or "").strip().lower()
    if s in ("ja", "vorhanden"):
        return STEUERBUERO
    if s == "nein":
        return SELBST
    return STEUERBUERO if betreut else SELBST
