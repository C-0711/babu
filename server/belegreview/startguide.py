#!/usr/bin/env python3
"""Der Start-up-Guide — die Schritte nach dem Zugang, in den Worten des Produkts.

Drei Mails schicken einen Zugangs-Link (Einladung Salon, Mitarbeiterin
Kanzlei, Passwort zurücksetzen). Alle sagen bisher nur, WO der Link ist —
aber nicht, was danach kommt. Das steht hier, in derselben Sprache wie
Portal und Startseite: keine Systemnamen, kein Technik-Vokabular (die
Sprachregel aus HANDOVER §1 gilt auch für Mailtexte).
"""
from __future__ import annotations


def schritte(portal: str, art: str = "salon") -> str:
    """Der Guide als eingerückter nummerierter Block für den Mailtext.

    `portal` ist die Anmeldeadresse (PORTAL_ORIGIN der Umgebung). `art`
    entscheidet, was nach dem Anmelden kommt: Salon füllen die Einrichtung
    aus, Kanzlei-Mitarbeiter sehen sofort die Betriebe.
    """
    portal = portal.rstrip("/")
    if art == "kanzlei":
        return (
            "    1. Knopf antippen — Passwort zweimal eingeben, fertig ist der Zugang.\n"
            "    2. Anmelden unter " + portal + "/portal mit dieser E-Mail-Adresse —\n"
            "       genau der, an die diese Mail ging. Sie muss nicht deine Apple-ID\n"
            "       sein; jede Adresse funktioniert.\n"
            "    3. Du siehst die Betriebe deiner Kanzlei — Belege, Fragen,\n"
            "       Übergaben an euer Steuerprogramm, alles an einem Ort.\n"
        )
    return (
        "    1. Knopf antippen — Passwort zweimal eingeben, fertig ist der Zugang.\n"
        "    2. Anmelden unter " + portal + "/portal mit dieser E-Mail-Adresse —\n"
        "       genau der, an die diese Mail ging. Sie muss nicht deine Apple-ID\n"
        "       sein; jede Adresse funktioniert.\n"
        "    3. App aufs iPhone: in Safari " + portal + "/app öffnen und\n"
        "       „babu installieren“ tippen. Dein iPhone wird dafür von uns\n"
        "       freigeschaltet — kurz Bescheid geben, wenn es noch nicht klappt.\n"
        "    4. In der App meldest du dich mit derselben E-Mail-Adresse an wie hier.\n"
        "    5. Ein paar kurze Fragen zu deinem Salon (zwei Minuten) — danach\n"
        "       weiß babu, wie es für dich bucht.\n"
        "    6. Ersten Beleg abfotografieren: Kamera auf den Beleg, grüner\n"
        "       Haken, fertig. babu übernimmt den Rest.\n"
    )
