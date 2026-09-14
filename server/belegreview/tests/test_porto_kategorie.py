#!/usr/bin/env python3
"""Test für Issue #82: Versandgebühren als Software statt Porto."""
import pytest
import kontierung
import gemma_buchung


def test_porto_ist_geprueft():
    """Porto sollte als geprüfte Kategorie markiert sein."""
    k = kontierung.KATEGORIEN["porto"]
    assert k.geprueft is True, "porto muss als geprueft markiert sein"
    assert k.skr04 == "6800", "SKR04-Konto sollte 6800 sein"
    assert k.skr03 == "4910", "SKR03-Konto sollte 4910 sein"


def test_porto_im_katalog():
    """Porto muss im Katalog für Gemma erscheinen."""
    katalog_skr04 = gemma_buchung.katalog_text("SKR04")
    katalog_skr03 = gemma_buchung.katalog_text("SKR03")
    
    # Porto muss in beiden Rahmen erscheinen
    assert "porto:" in katalog_skr04.lower(), "porto muss im SKR04-Katalog stehen"
    assert "porto:" in katalog_skr03.lower(), "porto muss im SKR03-Katalog stehen"
    
    # Der Hinweis auf Versand sollte dabei sein
    assert "versand" in katalog_skr04.lower(), "Hinweis auf Versand sollte im Katalog sein"
    assert "paketversand" in katalog_skr04.lower(), "Paketversand sollte erwähnt werden"


def test_porto_verwendung_paketversand():
    """Paketversand sollte auf porto abgebildet werden können."""
    k = kontierung.KATEGORIEN["porto"]
    
    # Porto sollte Briefmarken, Frankierung, Paketversand abdecken
    assert "paketversand" in k.hinweis.lower(), "Paketversand sollte im Hinweis stehen"
    assert "briefmarken" in k.hinweis.lower(), "Briefmarken sollten im Hinweis stehen"


def test_kontonummer_porto():
    """Kontonummer für Porto sollte abrufbar sein."""
    konto_skr04 = kontierung.konto("porto", "SKR04")
    konto_skr03 = kontierung.konto("porto", "SKR03")
    
    assert konto_skr04 == "6800", "SKR04-Konto für Porto sollte 6800 sein"
    assert konto_skr03 == "4910", "SKR03-Konto für Porto sollte 4910 sein"


def test_porto_gehoert_zum_rahmen():
    """Konto 6800 sollte als SKR04 erkannt werden."""
    assert kontierung.gehoert_zum_rahmen("6800", "SKR04"), \
        "6800 sollte als SKR04-Konto erkannt werden"
    assert kontierung.gehoert_zum_rahmen("4910", "SKR03"), \
        "4910 sollte als SKR03-Konto erkannt werden"
