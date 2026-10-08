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
        "    3. Ein paar kurze Fragen zu deinem Salon (zwei Minuten) — danach\n"
        "       weiß babu, wie es für dich bucht.\n"
        "    4. Ersten Beleg abfotografieren: Kamera auf den Beleg, grüner\n"
        "       Haken, fertig. babu übernimmt den Rest.\n"
    )


def app_link() -> str | None:
    """Wohin „App holen“ führt: App Store, sonst der öffentliche
    TestFlight-Link, sonst nirgends (dann bleibt nur der Weg über die
    Apple-ID aus `testflight_absatz`)."""
    import os  # noqa: PLC0415
    return (os.environ.get("BABU_APPSTORE_LINK", "").strip()
            or os.environ.get("BABU_TESTFLIGHT_LINK", "").strip() or None)


def app_absatz() -> str:
    """Wie die App aufs iPhone kommt — der EINE Absatz für jede Willkommensmail.

    Ist `BABU_APPSTORE_LINK` gesetzt (nach Apples Freigabe, Go-live-Plan
    Phase 6), führt er in den App Store. Bis dahin der öffentliche
    TestFlight-Link (`BABU_TESTFLIGHT_LINK`), und ohne den die Bitte um die
    Apple-ID wie seit 17.09.2026."""
    import os  # noqa: PLC0415
    store = os.environ.get("BABU_APPSTORE_LINK", "").strip()
    if store:
        return ("Die babu-App aufs iPhone: im App Store „babu Belege“ laden —\n\n"
                f"    {store}\n\n"
                "In der App meldest du dich mit dieser E-Mail-Adresse an.\n")
    test = os.environ.get("BABU_TESTFLIGHT_LINK", "").strip()
    if test:
        return ("Die babu-App aufs iPhone: diesen Link auf dem Telefon öffnen —\n\n"
                f"    {test}\n\n"
                "Er führt zu TestFlight, Apples offiziellem Weg für Test-Apps. Einmal\n"
                "„Testen“ antippen, dann installiert sich babu wie jede andere App.\n"
                "In der App meldest du dich mit dieser E-Mail-Adresse an.\n")
    return testflight_absatz()


def testflight_absatz() -> str:
    """Der App-Hinweis mit der Frage nach der Apple-ID-Adresse.

    Seit 17.09.2026 läuft die App-Verteilung über TestFlight — und eine
    TestFlight-Einladung geht an die Apple-ID, nicht an die babu-Adresse.
    Deshalb bittet jede Salon-Einladung um eine kurze Antwort mit genau
    dieser Adresse, inklusive dem Weg, wo man sie auf dem iPhone findet.
    Wer sie nicht schickt, kann trotzdem arbeiten: Portal und Papierkram
    laufen ohne App; die App-Einladung kommt dann später.
    """
    return (
        "Die babu-App auf dem iPhone kommt per TestFlight — Apples offizieller\n"
        "Weg für Test-Apps. Eine Einladung geht aber an deine Apple-ID-Adresse,\n"
        "und das kann eine ganz andere sein als deine babu-Adresse.\n\n"
        "    1. Auf dem iPhone: Einstellungen → dein Name ganz oben — dort steht\n"
        "       die Adresse unter deinem Namen.\n"
        "    2. Diese Adresse einfach per Antwort auf diese Mail schicken.\n"
        "    3. Du bekommst die Einladung von TestFlight, tippst auf „Testen“ —\n"
        "       die App installiert sich wie jede andere.\n"
        "\nIn der App meldest du dich danach ganz normal mit deiner babu-Adresse\n"
        "an. Die Apple-ID ist nur für die Installation da.\n"
    )
