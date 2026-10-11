"""Das Impressum — die Angaben, die niemand erfinden darf.

Der Rechtsträger heißt **nullsiebenelf GmbH** (Amtsgericht Stuttgart,
HRB 801171, Geschäftsführer Christoph Bertsch). „0711 Intelligence" ist die
Marke; bis zum 11.10.2026 stand sie allein im Impressum, ohne Rechtsform und
ohne Register. Das ist kein Impressum, sondern eine Visitenkarte.

Die nullsiebenelf GmbH hat **keine USt-IdNr** (Entscheid des Auftraggebers,
11.10.2026). § 27a UStG verlangt sie nur, sofern vorhanden — also steht die
Zeile gar nicht erst da. Eine Zeile mit Platzhalter wäre schlechter als
keine, und die Nummer der Schwestergesellschaft Bertsch Innovation GmbH
(DE205928452, HRB 214310) wäre schlicht falsch: zwei Registernummern sind
zwei juristische Personen.

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


def test_die_ladungsfaehige_anschrift_steht_da():
    """Straße, Hausnummer, PLZ, Ort — „Stuttgart" allein ist keine."""
    assert "Kronenstraße 25" in TEXT
    assert "70174 Stuttgart" in TEXT


def test_ohne_ust_idnr_steht_die_zeile_gar_nicht_da():
    """§ 27a UStG verlangt sie nur, sofern vorhanden. Ein Platzhalter im
    Impressum wäre schlechter als die weggelassene Zeile."""
    if recht.UST_IDNR is None:
        assert "Umsatzsteuer-Identifikation" not in TEXT
    else:
        assert recht.UST_IDNR in TEXT


def test_die_nummer_der_schwester_taucht_nirgends_auf():
    """DE205928452 gehört der Bertsch Innovation GmbH (HRB 214310). Im
    Impressum eines anderen Rechtsträgers wäre sie eine falsche Erklärung."""
    for _titel, text in recht.TEXTE.values():
        assert recht.BERTSCH_INNOVATION["ust_idnr"] not in text


def test_fehlende_anschrift_haelt_das_impressum_auf():
    """Der Riegel: ohne ladungsfähige Anschrift ist es ein Entwurf."""
    echt = recht.ANSCHRIFT
    try:
        recht.ANSCHRIFT = "FEHLT — Straße, Hausnummer, PLZ, Ort"
        assert recht.impressum_vollstaendig() is False
    finally:
        recht.ANSCHRIFT = echt
    assert recht.impressum_vollstaendig() is True


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
