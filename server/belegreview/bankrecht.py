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

#: Die Freigabe selbst: anfragen darf die Kanzlei, freigeben nur der Betrieb
#: (das prüft die Route). Sie ist deshalb weder Schreib- noch Lesesperre.
FREIGABE = "/api/bank/freigabe"

#: B1 (seit 04.10.2026): mit `BABU_BANK_FREIGABE=1` braucht die Kanzlei zum
#: LESEN die Freigabe des Betriebs. Diese Wege zeigen Bankdaten.
LESEND_BANK = ("/api/abgleich/", "/api/fehlende-belege", "/api/zahlungen",
               "/api/bank/", "/api/vorschau/auszuege/", "/api/dokument/auszuege/")

TEXT_FREIGABE = ("Die Kontoumsätze hat der Betrieb noch nicht für dich freigegeben. "
                 "Du kannst die Freigabe anfragen.")


def freigabe_pflicht() -> bool:
    """Ist die Freigabe eingeschaltet? Ohne Schalter liest die Kanzlei wie bisher."""
    import os  # noqa: PLC0415
    return os.environ.get("BABU_BANK_FREIGABE", "").strip() == "1"


def braucht_freigabe(methode: str, pfad: str, als_kanzlei: bool) -> bool:
    """Liest diese Anfrage einer Kanzlei Bankdaten?"""
    if not als_kanzlei or methode.upper() not in LESEND:
        return False
    if pfad.startswith(FREIGABE):
        return False
    return any(pfad.startswith(p) or pfad == p.rstrip("/") for p in LESEND_BANK)


def antwort_freigabe() -> dict:
    return {"fehler": TEXT_FREIGABE, "bank_freigabe_fehlt": True}


def antwort() -> dict:
    """Der Körper der 403-Antwort — gleich für jeden gesperrten Weg."""
    return {"fehler": TEXT, "nur_lesen_bank": True}


def sperrt(methode: str, pfad: str, als_kanzlei: bool) -> bool:
    """Darf diese Anfrage für eine Kanzlei nicht durch?"""
    if not als_kanzlei or methode.upper() in LESEND:
        return False
    pfad = pfad.rstrip("/") or "/"
    if pfad.startswith(FREIGABE):
        return False
    if pfad in SCHREIBEND:
        return True
    return any(pfad.startswith(b) or pfad == b.rstrip("/") for b in BEREICHE)


def pfad_gesperrt(box_pfad: str, als_kanzlei: bool) -> bool:
    """Ändert ein Schreibweg etwas unter `auszuege/`?"""
    return als_kanzlei and box_pfad.startswith(BOX_ORDNER)
