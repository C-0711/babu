#!/usr/bin/env python3
"""Von der E-Mail auf der Startseite bis zum fertigen Konto.

Der Weg, den der Auftrag beschreibt:

    Startseite → E-Mail eintragen, Unterlagen hochladen
              → Anriss der Auswertung + Anmeldelink per E-Mail
              → Link öffnen, Passwort zweimal eingeben
              → Konto steht, alles ist schon ausgefüllt
              → Bericht in der App, auf Knopfdruck ins Profil

Hier liegt nur der Zustand dazwischen — die Einladung. Kein Netz, keine
Datenbank, kein E-Mail-Versand: das gehört in die Route, damit es sich
prüfen lässt, ohne etwas zu verschicken.

Warum eine Einladung und kein Konto:

Wer auf einer Startseite eine E-Mail-Adresse eintippt, hat noch nichts
bestätigt. Ein Konto anzulegen hieße, jeder könne mit einer fremden Adresse
ein Konto erzeugen — und der Inhaber der Adresse bekäme Post über ein Konto,
das er nie wollte. Die Einladung dreht das um: erst kommt der Link an die
Adresse, und erst wer ihn öffnet, bekommt ein Konto. Damit ist die Adresse
nebenbei bestätigt, ohne einen zweiten Schritt.

Was hier bewusst NICHT passiert:

* **Kein Wort darüber, ob eine Adresse schon ein Konto hat.** Sonst wird das
  Formular zum Melder, welche Betriebe babu benutzen. Die Antwort nach außen
  ist immer dieselbe: „Wenn die Adresse stimmt, ist die Auswertung
  unterwegs."
* **Der Schlüssel wird nie gespeichert**, nur sein Hash — wie beim
  Geräteschlüssel in `app_schluessel`. Wer die Datenbank liest, kann sich
  damit nicht anmelden.
* **Kein Passwort in der E-Mail.** Es wird beim ersten Öffnen gesetzt, zweimal
  eingegeben, und der Link ist danach verbraucht.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# 192 Bit Zufall, wie beim Onboarding-Link. Der Schlüssel steht in einer
# E-Mail und damit in fremden Postfächern, Spamfiltern und Weiterleitungen —
# er muss auch dann nicht zu erraten sein, wenn jemand Millionen versucht.
SCHLUESSEL_BITS = 192

# Zwei Wochen. Lang genug, dass eine Mail im Urlaub liegen bleiben darf;
# kurz genug, dass ein vergessener Link nicht ein Jahr später noch ein Konto
# eröffnet.
FRIST = timedelta(days=14)

# Wie oft dieselbe Adresse eine Auswertung anfordern darf, bevor gebremst
# wird. Ohne Bremse ist das Formular ein Versandwerkzeug für fremde Postfächer.
VERSUCHE_MAX = 3
VERSUCHE_FENSTER = timedelta(hours=24)

MINDEST_PASSWORT = 10

# Absichtlich nachsichtig: eine Adresse mit einem @ und einem Punkt dahinter.
# Strengere Muster weisen echte Adressen ab, und die Bestätigung übernimmt
# ohnehin der Link — wer die Mail nicht bekommt, kommt nicht weiter.
_MAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def mail_gueltig(adresse: str) -> bool:
    return bool(_MAIL.match((adresse or "").strip()))


def schluessel_erzeugen() -> str:
    """Der Teil, der in die E-Mail geht. Genau einmal im Klartext sichtbar."""
    return secrets.token_urlsafe(SCHLUESSEL_BITS // 8)


def schluessel_hash(schluessel: str) -> str:
    """Was in der Datenbank steht. Aus ihm folgt kein Schlüssel."""
    return hashlib.sha256((schluessel or "").encode("utf-8")).hexdigest()


@dataclass
class Einladung:
    """Eine angeforderte Auswertung, die auf ihren Menschen wartet."""
    mail: str
    schluessel_hash: str
    erstellt: datetime
    frist: datetime
    verbraucht: datetime | None = None
    # Was aus den Unterlagen gelesen wurde — wird beim Anmelden ins Konto
    # übernommen. Bis dahin gehört es niemandem.
    gelesen: dict = field(default_factory=dict)
    bericht: str = ""

    @property
    def offen(self) -> bool:
        return self.verbraucht is None and _jetzt() <= self.frist


@dataclass
class Ergebnis:
    """Was die Route zurückgibt — und was sie dem Anfragenden sagen darf."""
    ok: bool
    grund: str = ""
    einladung: Einladung | None = None
    schluessel: str | None = None      # nur beim Anlegen, für die E-Mail


# ── Anfordern ────────────────────────────────────────────────────────────────

def anfordern(mail: str, *, frueher: list[datetime] | None = None,
              gelesen: dict | None = None, bericht: str = "") -> Ergebnis:
    """Eine Einladung erzeugen — oder begründet ablehnen.

    `frueher` sind die Zeitpunkte, zu denen dieselbe Adresse es schon
    versucht hat; die Route holt sie aus der Datenbank.
    """
    adresse = (mail or "").strip().lower()
    if not mail_gueltig(adresse):
        return Ergebnis(False, "Diese E-Mail-Adresse sieht nicht richtig aus.")

    grenze = _jetzt() - VERSUCHE_FENSTER
    jung = [t for t in (frueher or []) if t > grenze]
    if len(jung) >= VERSUCHE_MAX:
        # Nach außen bleibt es freundlich und ohne Auskunft darüber, wie oft
        # es jemand versucht hat — die Bremse ist keine Information für Dritte.
        return Ergebnis(False, "Wir haben dir gerade erst geschrieben — "
                               "sieh bitte in deinem Postfach nach.")

    schluessel = schluessel_erzeugen()
    jetzt = _jetzt()
    return Ergebnis(True, einladung=Einladung(
        mail=adresse, schluessel_hash=schluessel_hash(schluessel),
        erstellt=jetzt, frist=jetzt + FRIST,
        gelesen=dict(gelesen or {}), bericht=bericht),
        schluessel=schluessel)


# Was nach außen gesagt wird, egal was drinnen passiert ist. Wer hier
# unterscheidet, verrät, welche Adressen bereits ein Konto haben.
ANTWORT_NACH_AUSSEN = ("Wenn die Adresse stimmt, ist deine Auswertung "
                       "unterwegs — sieh in ein paar Minuten ins Postfach.")


# ── Einlösen ─────────────────────────────────────────────────────────────────

def pruefen(einladung: Einladung | None, schluessel: str) -> Ergebnis:
    """Gehört dieser Schlüssel zu dieser Einladung, und gilt sie noch?"""
    if einladung is None:
        return Ergebnis(False, "Dieser Link ist uns nicht bekannt.")
    if not secrets.compare_digest(einladung.schluessel_hash,
                                  schluessel_hash(schluessel)):
        return Ergebnis(False, "Dieser Link ist uns nicht bekannt.")
    if einladung.verbraucht is not None:
        return Ergebnis(False, "Dieser Link wurde schon benutzt — "
                               "melde dich mit E-Mail und Passwort an.")
    if _jetzt() > einladung.frist:
        return Ergebnis(False, "Dieser Link ist abgelaufen. Fordere die "
                               "Auswertung noch einmal an.")
    return Ergebnis(True, einladung=einladung)


def passwort_pruefen(erstes: str, zweites: str) -> Ergebnis:
    """Zweimal eingeben heißt: beide müssen gleich sein und etwas taugen."""
    if (erstes or "") != (zweites or ""):
        return Ergebnis(False, "Die beiden Passwörter sind nicht gleich.")
    if len(erstes or "") < MINDEST_PASSWORT:
        return Ergebnis(False, f"Bitte mindestens {MINDEST_PASSWORT} Zeichen — "
                               f"lieber ein Satz als ein kurzes Kunstwort.")
    return Ergebnis(True)


def einloesen(einladung: Einladung, schluessel: str,
              passwort: str, passwort_wiederholt: str) -> Ergebnis:
    """Der Schritt, aus dem ein Konto wird. Prüft alles, ändert nichts.

    Die Route legt das Konto an und setzt danach `verbraucht` — hier wird
    nur entschieden, ob sie das darf. So bleibt der Fall „Konto angelegt,
    aber Link noch offen" unmöglich: es gibt genau eine Stelle, die schreibt.
    """
    if not (geprueft := pruefen(einladung, schluessel)).ok:
        return geprueft
    if not (pw := passwort_pruefen(passwort, passwort_wiederholt)).ok:
        return pw
    return Ergebnis(True, einladung=einladung)


# ── Die E-Mail ───────────────────────────────────────────────────────────────

def mail_text(einladung: Einladung, schluessel: str, *, basis: str) -> tuple[str, str]:
    """Betreff und Text. Der Anriss steht drin, der Rest hinter dem Link.

    Bewusst reiner Text: eine Mail mit Bildern und Schriften landet öfter im
    Spam, und der Anriss soll auch dann lesbar sein, wenn nichts nachgeladen
    wird.
    """
    link = f"{basis.rstrip('/')}/auswertung/{schluessel}"
    betreff = "Deine Auswertung ist fertig"
    text = f"""Hallo,

wir haben deine Unterlagen gelesen. Hier ist der erste Teil:

{einladung.bericht.strip()}

Den vollständigen Bericht siehst du hier — beim ersten Öffnen legst du
dein Passwort fest:

    {link}

Der Link gilt {FRIST.days} Tage und nur einmal. Danach meldest du dich
ganz normal mit deiner E-Mail-Adresse und dem Passwort an.

Wenn du das nicht angefordert hast, ignoriere diese Nachricht einfach —
ohne den Link passiert nichts.
"""
    return betreff, text
