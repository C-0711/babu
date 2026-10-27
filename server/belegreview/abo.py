"""Abo und Zugang — wer voll arbeitet und wer nur noch ansieht (seit 03.10.2026).

Go-live-Plan Phase 2: Salons schließen nach dem Testmonat selbst ein Abo
ab (Stripe, nur Karte — dasselbe Konto wie Camp45). Dieses Modul ist nur die REGEL — ohne Datenbank, ohne Netz, ohne Uhr. Die Wache in `babu_web._box_wache` holt
den Stand der Mandantenzeile und fragt `zugang()` und `sperrt()`.

Die Regel in einer Tabelle:

    Lage                                   Zugang
    kein Abo und kein Test                 voll   (Bestand, Kanzlei-Mandanten, Pilot)
    nur Test                               voll bis test_bis, dann nur lesen
    zahlung_laeuft / aktiv                 voll
    zahlung_offen                          voll bis 14 Tage nach dem ersten Fehler
    gekuendigt                             voll bis abo_ende, dann nur lesen
    beendet                                nur lesen

„Nur lesen" heißt wie beim Testmonat: ansehen und herunterladen ja,
erfassen und ändern nein. Rückmeldungen und der Weg zum Abo bleiben offen.

Ohne Abo-Spalten (abo_status NULL) ist das Ergebnis Zeile für Zeile das
des Testmonats vom 02.10.2026 — die Wache braucht deshalb keinen Schalter.
`BABU_ABO` steuert nur, ob die Abo-Wege (Seite, Knöpfe, Checkout) da sind.
"""
from __future__ import annotations

import datetime as dt
import os

#: Die Pakete — Nettopreise in Cent (verbindlich seit 03.10.2026).
PAKETE: dict[str, dict] = {
    "solo": {"name": "Solo", "netto_cent": 3900},
    "salon": {"name": "Salon", "netto_cent": 7900},
    "plus": {"name": "Salon Plus", "netto_cent": 14900},
}

UST_PROZENT = 19

#: Zahlungsfrist nach dem ersten fehlgeschlagenen Einzug.
FRIST_TAGE = 14

STATUS = ("zahlung_laeuft", "aktiv", "zahlung_offen", "gekuendigt", "beendet")

LESEND = frozenset({"GET", "HEAD", "OPTIONS"})

#: Was auch im Nur-Lesen-Zustand schreiben darf: Rückmeldungen (wer
#: feststeckt, muss es sagen können), der Weg zum Abo selbst — und seit
#: 10.10.2026 die E-Mail des Gerätekontos. Sie ist der einzige Weg zurück
#: zu den Belegen auf einem neuen Telefon, und wer am Freikontingent
#: hängt, ist genau der, der sie hinterlegen soll.
#: Seit 28.10.2026 auch die Messung der Kaufseite (`/api/platz/`): bei vollem
#: Platz steht die Nutzerin genau vor der Wand, die gemessen werden soll —
#: eine Sperre dort ließe die Quelle `voll` systematisch leer.
FREIE_PFADE = ("/api/rueckmeldung", "/api/abo/", "/api/konto/email", "/api/platz/")

#: Warum nur lesen — der Text, den Portal und App zeigen.
TEXTE = {
    "test_vorbei": ("Dein Testmonat ist vorbei — du kannst alles weiter ansehen "
                    "und herunterladen. Damit du wieder Belege erfassen kannst, "
                    "mach unter „Weitermachen“ mit babu weiter."),
    "zahlung_offen": ("Die letzte Zahlung ist nicht angekommen. Du kannst alles "
                      "ansehen und herunterladen; zum Erfassen bitte unter "
                      "„Weitermachen“ die Zahlungsdaten prüfen."),
    "gekuendigt": ("Dein Abo ist beendet. Du kannst alles weiter ansehen und "
                   "herunterladen. Unter „Weitermachen“ kannst du wieder "
                   "einsteigen."),
    "beendet": ("Dein Abo ist beendet. Du kannst alles weiter ansehen und "
                "herunterladen. Unter „Weitermachen“ kannst du wieder "
                "einsteigen."),
}


#: Dieselben Lagen für die iOS-App — ohne Aufforderung, außerhalb der App
#: abzuschließen (App-Store-Richtlinie 3.1.1/3.1.3): nur, was gilt.
TEXTE_APP = {
    "test_vorbei": ("Dein Testmonat ist vorbei. Du kannst alles weiter ansehen "
                    "und herunterladen."),
    "zahlung_offen": ("Die letzte Zahlung ist nicht angekommen. Du kannst alles "
                      "weiter ansehen und herunterladen."),
    "gekuendigt": "Dein Abo ist beendet. Du kannst alles weiter ansehen und herunterladen.",
    "beendet": "Dein Abo ist beendet. Du kannst alles weiter ansehen und herunterladen.",
}


def an() -> bool:
    """Sind die Abo-Wege eingeschaltet? (`BABU_ABO=1`, Standard aus.)"""
    return os.environ.get("BABU_ABO", "0").strip() == "1"


def brutto_cent(netto_cent: int) -> int:
    """Netto + 19 % USt, kaufmännisch gerundet (3900 → 4641)."""
    return (netto_cent * (100 + UST_PROZENT) + 50) // 100


def preise() -> list[dict]:
    """Die Pakete zum Anzeigen: Schlüssel, Name, netto und brutto in Cent."""
    return [{"paket": k, "name": p["name"], "netto_cent": p["netto_cent"],
             "brutto_cent": brutto_cent(p["netto_cent"])}
            for k, p in PAKETE.items()]


def _datum(wert: str | None) -> dt.date | None:
    if not wert:
        return None
    try:
        return dt.date.fromisoformat(str(wert)[:10])
    except ValueError:
        return None


def zugang(test_bis: str | None, abo_status: str | None, abo_ende: str | None,
           zahlungsfehler_seit: str | None, heute: dt.date,
           herkunft: str | None = None, paket: str | None = None,
           speicher_bytes: int | None = None,
           belege_gesamt: int | None = None) -> dict:
    """Wie darf dieser Betrieb heute arbeiten?

    Rückgabe `{stufe, grund, bis}`: `stufe` ist "voll" oder "nur_lesen";
    `grund` sagt warum (None = ohne Einschränkung), `bis` den letzten Tag mit
    vollem Zugang, wenn einer feststeht (ISO-Datum).

    Seit 10.10.2026 entscheidet bei Betrieben aus dem App Store zuerst der
    Platz (`paket.py`): Wer sein Kontingent aufgebraucht hat, sieht seine
    Belege weiter, legt aber nichts Neues mehr ab — auch wenn das Abo läuft.
    Für Betriebe aus dem Portal (`herkunft` nicht "app") bleibt die Antwort
    Byte für Byte, wie sie war."""
    import paket as pak  # noqa: PLC0415 — nur Rechnung, kein Modulzustand
    platz = pak.stand(herkunft=herkunft, stufe=paket,
                      verbraucht=speicher_bytes, belege=belege_gesamt)
    if platz and platz["voll"]:
        # Der volle Platz schlägt alles andere: Ein laufendes Abo gibt keinen
        # Platz, den es nicht gibt, und ein gekündigtes nimmt keinen weg.
        return {"stufe": "nur_lesen",
                "grund": "speicher_voll" if platz["stufe"] else "frei_aufgebraucht",
                "bis": None}
    if abo_status in ("zahlung_laeuft", "aktiv"):
        return {"stufe": "voll", "grund": None, "bis": None}
    if abo_status == "zahlung_offen":
        seit = _datum(zahlungsfehler_seit) or heute
        letzter = seit + dt.timedelta(days=FRIST_TAGE)
        if heute <= letzter:
            return {"stufe": "voll", "grund": "frist", "bis": letzter.isoformat()}
        return {"stufe": "nur_lesen", "grund": "zahlung_offen", "bis": None}
    if abo_status == "gekuendigt":
        ende = _datum(abo_ende)
        if ende is None or heute <= ende:
            return {"stufe": "voll", "grund": "gekuendigt",
                    "bis": ende.isoformat() if ende else None}
        return {"stufe": "nur_lesen", "grund": "gekuendigt", "bis": None}
    if abo_status == "beendet":
        return {"stufe": "nur_lesen", "grund": "beendet", "bis": None}
    # Kein Abo: der Testmonat entscheidet — oder es gibt keinen (Bestand).
    ende = _datum(test_bis)
    if ende is None:
        return {"stufe": "voll", "grund": None, "bis": None}
    if heute <= ende:
        return {"stufe": "voll", "grund": "test", "bis": ende.isoformat()}
    return {"stufe": "nur_lesen", "grund": "test_vorbei", "bis": None}


def sperrt(methode: str, pfad: str, z: dict | None) -> bool:
    """Darf diese Anfrage im Nur-Lesen-Zustand nicht durch?"""
    if not z or z.get("stufe") != "nur_lesen":
        return False
    if methode.upper() in LESEND:
        return False
    return not any(pfad.startswith(frei) for frei in FREIE_PFADE)


#: Was bei vollem Platz gesagt wird. Beide Wege dieselbe Botschaft: die
#: Belege bleiben liegen, es geht nur ums Weitermachen.
TEXTE_PLATZ = {
    "frei_aufgebraucht": "Deine zehn freien Belege sind abgelegt. Such dir "
                         "einen Platz aus, dann geht es weiter — deine "
                         "Belege bleiben, wo sie sind.",
    "speicher_voll": "Deine Ablage ist voll. Mit der nächsten Stufe hast du "
                     "sofort wieder Luft — alles Abgelegte bleibt, wo es ist.",
}


def text(z: dict, app: bool = False) -> str:
    """Der Satz zur Sperre. `app=True`: die Fassung für die iOS-App."""
    grund = z.get("grund") or ""
    # Platz ist kein Abo-Problem: derselbe Satz in App und Portal, und er
    # sagt zuerst, dass nichts verloren geht.
    if grund in TEXTE_PLATZ:
        return TEXTE_PLATZ[grund]
    quelle = TEXTE_APP if app else TEXTE
    return quelle.get(grund, quelle["test_vorbei"])


# ---------------------------------------------------------------------------
# Stripe → babu
# ---------------------------------------------------------------------------

def status_aus_stripe(status: str | None, cancel_at_period_end: bool = False) -> str:
    """Stripe-Abo-Status → `mandant.abo_status`.

    `incomplete` heißt bei SEPA: das Mandat ist erteilt, der erste Einzug
    läuft (dauert Tage) — der Salon arbeitet in der Zeit voll."""
    s = (status or "").lower()
    if s in ("active", "trialing"):
        return "gekuendigt" if cancel_at_period_end else "aktiv"
    if s == "incomplete":
        return "zahlung_laeuft"
    if s in ("past_due", "unpaid"):
        return "zahlung_offen"
    return "beendet"           # canceled, incomplete_expired, paused, unbekannt
