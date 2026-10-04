"""Ein Umsatzmodell für alle Wege aufs Konto (seit 04.10.2026).

Plan Kanzleiansicht, B2. Kontoumsätze kommen auf drei Wegen: als PDF-Auszug
(`kontoauszug.py`, nur Kreissparkasse), als Datei der Bank (CAMT.053 oder
CSV, `bank_camt.py`) und später live über einen Kontoinformationsdienst
(B4). Alle drei münden hier in dieselbe Form.

Ablage in der Belegbox des Betriebs:

    bank/konten.json                       die Konten mit Abdeckung und Saldo
    bank/umsaetze/<konto_id>/<JJJJ-MM>.json die Umsätze eines Monats
    bank/importe/<stempel>-<name>          die Originaldatei

`konto_id` ist ein Hash der IBAN — im Pfad steht keine Kontonummer.

Die bisherigen Leser (Abgleich, fehlende Belege, Zahlungen, Monatsabschluss)
lesen weiter `idx["umsaetze"]` im alten Format; `als_alt()` übersetzt.

Reine Rechnung ohne Box und Netz.
"""
from __future__ import annotations

import hashlib
import re


def iban_normal(iban: str | None) -> str:
    return re.sub(r"\s+", "", str(iban or "")).upper()


def konto_id(iban: str) -> str:
    return hashlib.sha256(iban_normal(iban).encode()).hexdigest()[:12]


def iban_kurz(iban: str | None) -> str:
    """„DE89 •••• 3000“ — für Anzeigen, in denen die ganze Nummer nichts hilft."""
    i = iban_normal(iban)
    return f"{i[:4]} •••• {i[-4:]}" if len(i) > 8 else i


def umsatz_id(konto: str, buchung: str, betrag: float, gegenpartei: str,
              zweck: str, referenz: str | None, n: int) -> str:
    """Stabile Kennung: mit Bankreferenz aus ihr, sonst aus dem Inhalt.

    `n` zählt gleiche Umsätze desselben Tages in derselben Datei (zweimal
    derselbe Kaffee) — dieselbe Datei ergibt so immer dieselben Kennungen,
    und ein zweiter Import legt nichts doppelt an.
    """
    if referenz:
        roh = f"{konto}|ref|{referenz}"
    else:
        roh = f"{konto}|{buchung}|{betrag:.2f}|{gegenpartei}|{zweck}|{n}"
    return hashlib.sha256(roh.encode()).hexdigest()[:20]


def kennungen_vergeben(umsaetze: list[dict]) -> list[dict]:
    """Jedem Umsatz seine Kennung — gleiche Inhalte werden durchgezählt."""
    gesehen: dict[tuple, int] = {}
    for u in umsaetze:
        schluessel = (u["konto"], u["buchung"], round(u["betrag"], 2),
                      u.get("gegenpartei") or "", u.get("zweck") or "")
        n = gesehen.get(schluessel, 0)
        gesehen[schluessel] = n + 1
        u["id"] = umsatz_id(u["konto"], u["buchung"], u["betrag"],
                            u.get("gegenpartei") or "", u.get("zweck") or "",
                            u.get("referenz"), n)
    return umsaetze


def zusammenfuehren(bestand: list[dict], neu: list[dict]) -> tuple[list[dict], int]:
    """Neue Umsätze dazu, über die Kennung — Vorhandenes bleibt, wie es ist."""
    da = {u["id"] for u in bestand}
    dazu = [u for u in neu if u["id"] not in da]
    alle = sorted(bestand + dazu, key=lambda u: (u["buchung"], u["id"]))
    return alle, len(dazu)


def je_monat(umsaetze: list[dict]) -> dict[str, list[dict]]:
    aus: dict[str, list[dict]] = {}
    for u in umsaetze:
        aus.setdefault(u["buchung"][:7], []).append(u)
    return aus


def als_alt(u: dict) -> dict:
    """Ein Umsatz in der Form, die `kontoauszug.parse_text` liefert."""
    j, m, t = u["buchung"][:10].split("-")
    typ = u.get("art") or ("Gutschrift" if u["betrag"] >= 0 else "Lastschrift")
    gegen = (u.get("gegenpartei") or "").strip()
    text = " ".join(x for x in (gegen, (u.get("zweck") or "").strip()) if x)
    return {"datum": f"{t}.{m}.{j}", "typ": typ, "betrag": round(u["betrag"], 2),
            "text": text[:300], "gegenpartei": (gegen or typ)[:80],
            "id": u["id"], "quelle": u.get("quelle"), "gegen_iban": u.get("gegen_iban")}


def ohne_doppelte_pdf(importiert: list[dict], pdf: list[dict]) -> list[dict]:
    """PDF-Umsätze, die schon aus einer Bankdatei da sind, fallen weg.

    Gleich heißt: gleicher Tag und gleicher Betrag, eins zu eins. So bleibt
    ein PDF-Monat, den keine Datei abdeckt, wie er ist — und eine Datei, die
    nur einen Teil des Monats abdeckt, verdoppelt nichts.
    """
    frei: dict[tuple, int] = {}
    for u in importiert:
        k = (u["datum"], round(u["betrag"], 2))
        frei[k] = frei.get(k, 0) + 1
    rest = []
    for u in pdf:
        k = (u.get("datum"), round(float(u.get("betrag") or 0), 2))
        if frei.get(k):
            frei[k] -= 1
            continue
        rest.append(u)
    return rest


def konto_dazu(konten: list[dict], iban: str, von: str | None, bis: str | None,
               quelle: str, datei: str | None, saldo: dict | None) -> list[dict]:
    """Ein Konto anlegen oder seine Abdeckung und seinen Saldo fortschreiben."""
    kid = konto_id(iban)
    neu = [dict(k) for k in konten]
    k = next((x for x in neu if x["id"] == kid), None)
    if k is None:
        k = {"id": kid, "iban": iban_normal(iban), "abdeckung": [], "saldo": None}
        neu.append(k)
    if von and bis:
        k["abdeckung"] = sorted([*k.get("abdeckung", []),
                                 {"von": von, "bis": bis, "quelle": quelle, "datei": datei}],
                                key=lambda a: (a["von"], a["bis"]))
    if saldo and (not k.get("saldo") or saldo["datum"] >= k["saldo"]["datum"]):
        k["saldo"] = saldo
    return neu
