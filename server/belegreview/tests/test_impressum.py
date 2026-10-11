"""Das Impressum — die Angaben, die niemand erfinden darf.

Der Rechtsträger heißt **nullsiebenelf GmbH** (Amtsgericht Stuttgart,
HRB 801171, Geschäftsführer Christoph Bertsch). „0711 Intelligence" ist die
Marke; bis zum 11.10.2026 stand sie allein im Impressum, ohne Rechtsform und
ohne Register. Das ist kein Impressum, sondern eine Visitenkarte.

Zwei Pflichtangaben fehlen noch und kennt nur die Geschäftsführung: die
ladungsfähige Anschrift (§ 5 DDG) und die Umsatzsteuer-Identifikationsnummer
(§ 27a UStG). Solange sie fehlen, hält `recht.impressum_vollstaendig()`
dagegen — und dieser Test hält dagegen, dass jemand sie mit einem Platzhalter
füllt, der live wie eine Angabe aussieht.

Was hier NICHT steht und nie hier stehen wird: Bankverbindung und
Steuernummer. Beide gehören in kein Impressum. Sie gehören in die Formulare
bei Apple und Stripe, und die füllt die Geschäftsführung selbst aus.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import recht  # noqa: E402

TEXT = recht.TEXTE["impressum"][1]


def test_der_rechtstraeger_steht_mit_rechtsform_da():
    assert "nullsiebenelf GmbH" in TEXT


def test_register_und_gericht_stehen_da():
    assert "HRB 801171" in TEXT
    assert "Amtsgericht Stuttgart" in TEXT


def test_der_geschaeftsfuehrer_ist_als_solcher_benannt():
    """„Christoph Bertsch, Stuttgart" sagt nicht, wer vertritt."""
    assert "Geschäftsführer: Christoph Bertsch" in TEXT


def test_die_marke_steht_nicht_mehr_als_anbieter():
    """0711 Intelligence ist nicht im Register — als Anbieter wäre es falsch."""
    anbieter = TEXT.split("Kontakt:")[0]
    assert "0711 Intelligence" not in anbieter


@pytest.mark.parametrize("was", ["Anschrift", "Umsatzsteuer-Identifikationsnummer"])
def test_die_pflichtangabe_ist_wenigstens_erwaehnt(was):
    assert was in TEXT or was.split("-")[0] in TEXT


def test_solange_etwas_fehlt_sagt_der_server_es_auch():
    """Der Riegel: fehlt eine Pflichtangabe, meldet es die Funktion — und
    niemand kann sie mit einem stillen Platzhalter umgehen."""
    fehlt = recht.ANSCHRIFT.startswith("FEHLT") or recht.UST_IDNR.startswith("FEHLT")
    assert recht.impressum_vollstaendig() is not fehlt


def test_keine_bankverbindung_im_impressum():
    """Eine IBAN im Impressum ist eine Einladung an Lastschriftbetrüger."""
    assert not re.search(r"\bDE\d{2}[\s\d]{18,}", TEXT)
    assert "IBAN" not in TEXT and "BIC" not in TEXT


def test_keine_steuernummer_im_impressum():
    """Die Steuernummer (99030/09781) ist NICHT die USt-IdNr und gehört
    nirgends hin, wo sie jemand lesen kann."""
    assert not re.search(r"\b\d{5}/\d{5}\b", TEXT)


def test_keine_steuernummer_irgendwo_in_den_rechtstexten():
    for art, (_titel, text) in recht.TEXTE.items():
        assert not re.search(r"\b\d{5}/\d{5}\b", text), art
        assert not re.search(r"\bDE\d{2}[\s\d]{18,}", text), art


def test_die_fassung_haengt_am_wortlaut():
    """Ändert sich das Impressum, ändert sich sein Fingerabdruck — sonst
    trüge eine alte Zustimmung den neuen Text."""
    vorher = recht.fassung("impressum")
    titel, text = recht.TEXTE["impressum"]
    recht.TEXTE["impressum"] = (titel, text + " ")
    try:
        assert recht.fassung("impressum") != vorher
    finally:
        recht.TEXTE["impressum"] = (titel, text)
