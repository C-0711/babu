#!/usr/bin/env python3
"""E-Mail verschicken — und sie nicht verlieren, wenn das nicht geht.

Bis heute verschickte babu keine einzige Mail. Der Trichter von der
Startseite braucht aber genau eine: den Anmeldelink zur Auswertung. Ohne
sie ist die Auswertung fertig und niemand kommt an sie heran.

Die Regel ist dieselbe wie beim Rückmeldeknopf: **erst ablegen, dann
versuchen.** Eine Nachricht, die nicht rausgeht, liegt danach als Datei im
Postausgang und lässt sich von Hand versenden. Was nicht passieren darf,
ist eine Auswertung, die erzeugt wurde und deren Link niemand mehr kennt —
der Schlüssel steht nur in dieser einen Nachricht.

Ohne eingerichteten Versand ist das kein Fehlerfall, sondern der heutige
Normalfall: die Datei landet im Postausgang, der Aufrufer bekommt gesagt,
dass sie wartet, und der Ablauf geht weiter.
"""
from __future__ import annotations

import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

HOST = os.environ.get("BABU_SMTP_HOST", "").strip()
PORT = int(os.environ.get("BABU_SMTP_PORT", "587") or 587)
NUTZER = os.environ.get("BABU_SMTP_NUTZER", "").strip()
PASSWORT = os.environ.get("BABU_SMTP_PASSWORT", "")
ABSENDER = os.environ.get("BABU_ABSENDER", "babu <post@babu.0711.io>").strip()
POSTAUSGANG = Path(os.environ.get(
    "BABU_POSTAUSGANG", str(Path.home() / "babu-web" / "postausgang")))
TIMEOUT = 20

# Für den Dateinamen im Postausgang: alles, was kein Buchstabe, keine Ziffer
# und kein Bindestrich ist, fliegt raus. Sonst legt eine Adresse mit „/“
# darin eine Datei irgendwo anders ab.
_UNSAUBER = re.compile(r"[^A-Za-z0-9._@-]+")


def eingerichtet() -> bool:
    return bool(HOST)


def _nachricht(an: str, betreff: str, text: str) -> EmailMessage:
    m = EmailMessage()
    m["From"] = ABSENDER
    m["To"] = an
    m["Subject"] = betreff
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain="babu.0711.io")
    # Reiner Text. Eine Mail mit Bildern und Schriften landet öfter im Spam,
    # und der Anriss soll auch dann lesbar sein, wenn nichts nachgeladen wird.
    m.set_content(text)
    return m


def _ablegen(m: EmailMessage, an: str, stempel: str) -> Path:
    """Die Nachricht als .eml in den Postausgang. Immer, vor jedem Versuch."""
    POSTAUSGANG.mkdir(parents=True, exist_ok=True)
    name = f"{stempel}-{_UNSAUBER.sub('_', an)}.eml"
    pfad = POSTAUSGANG / name
    pfad.write_bytes(bytes(m))
    try:
        pfad.chmod(0o600)   # in einer Mail steht ein Anmeldeschlüssel
    except OSError:
        pass
    return pfad


def senden(an: str, betreff: str, text: str, *, stempel: str) -> tuple[bool, str]:
    """Ablegen, dann versuchen. Gibt (verschickt, Hinweis) zurück.

    `stempel` geht in den Dateinamen — die aufrufende Stelle kennt einen
    sortierbaren Zeitpunkt, dieses Modul soll keine Uhr brauchen (das macht
    es prüfbar).
    """
    m = _nachricht(an, betreff, text)
    try:
        pfad = _ablegen(m, an, stempel)
    except OSError as ex:
        # Wenn nicht einmal das Ablegen geht, darf der Versand NICHT
        # stattfinden: sonst ist der Schlüssel unterwegs und nirgends notiert.
        return False, f"Postausgang nicht schreibbar: {ex!r}"[:160]

    if not eingerichtet():
        return False, f"kein Versand eingerichtet — liegt in {pfad.name}"

    try:
        if PORT == 465:
            with smtplib.SMTP_SSL(HOST, PORT, timeout=TIMEOUT,
                                  context=ssl.create_default_context()) as s:
                if NUTZER:
                    s.login(NUTZER, PASSWORT)
                s.send_message(m)
        else:
            with smtplib.SMTP(HOST, PORT, timeout=TIMEOUT) as s:
                s.starttls(context=ssl.create_default_context())
                if NUTZER:
                    s.login(NUTZER, PASSWORT)
                s.send_message(m)
    except Exception as ex:  # noqa: BLE001
        return False, f"Versand fehlgeschlagen ({ex!r}) — liegt in {pfad.name}"[:200]

    # Verschickt: die Kopie bleibt trotzdem liegen. Wer nachvollziehen muss,
    # welcher Link an welche Adresse ging, findet es hier — und niemand sonst
    # (0600, und der Ordner liegt außerhalb des Web-Wurzelverzeichnisses).
    return True, f"verschickt an {an}"
