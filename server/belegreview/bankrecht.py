"""Bankdaten und Kanzlei — wer liest, wer pflegt (seit 03.10.2026).

Plan Kanzleiansicht, Phase 0: Arbeitet eine Kanzlei über `X-Mandant` in
einem Betrieb, sieht sie Kontoauszüge, Abgleich und Zahlungen — ändern
darf sie daran nichts. Kontoauszüge und Zahlungen pflegt der Betrieb
selbst. Später kommt die Freigabe des Betriebs dazu (B1); bis dahin gilt:
lesen ja, schreiben nein.

Dieses Modul ist nur die REGEL — ohne Datenbank, ohne Netz. Die Wache in
`babu_web._box_wache` fragt `sperrt()`; die beiden Wege, die nicht an
einer Route erkennbar sind (die Aufnahme eines Auszug-PDFs und die Ablage
unter `auszuege/`), fragen `pfad_gesperrt()` selbst.
"""
from __future__ import annotations

LESEND = frozenset({"GET", "HEAD", "OPTIONS"})

#: Routen, die Bankdaten ändern. `/api/bank/` deckt auch die künftigen
#: Bankrouten (Import, Live-Abruf) — eine neue Route startet nie schreibbar.
SCHREIBEND = ("/api/kontoauszug", "/api/auszug-loeschen",
              "/api/fehlende-belege/klaeren", "/api/zahlungen/uebernehmen")
BEREICHE = ("/api/bank/",)

#: Wo Kontoauszüge in der Belegbox liegen.
BOX_ORDNER = "auszuege/"

TEXT = "Kontoauszüge und Zahlungen pflegt der Betrieb selbst. Du kannst sie ansehen."


def antwort() -> dict:
    """Der Körper der 403-Antwort — gleich für jeden gesperrten Weg."""
    return {"fehler": TEXT, "nur_lesen_bank": True}


def sperrt(methode: str, pfad: str, als_kanzlei: bool) -> bool:
    """Darf diese Anfrage für eine Kanzlei nicht durch?"""
    if not als_kanzlei or methode.upper() in LESEND:
        return False
    pfad = pfad.rstrip("/") or "/"
    if pfad in SCHREIBEND:
        return True
    return any(pfad.startswith(b) or pfad == b.rstrip("/") for b in BEREICHE)


def pfad_gesperrt(box_pfad: str, als_kanzlei: bool) -> bool:
    """Ändert ein Schreibweg etwas unter `auszuege/`?"""
    return als_kanzlei and box_pfad.startswith(BOX_ORDNER)
