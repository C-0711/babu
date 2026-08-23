"""Der Weg von der E-Mail auf der Startseite zum fertigen Konto.

Was hier schiefgehen kann, geht nicht laut schief: ein Link, der zweimal
gilt; eine Auskunft darüber, welche Adressen schon ein Konto haben; ein
Schlüssel, der im Klartext in der Datenbank steht. Nichts davon fällt im
Betrieb auf — deshalb steht es hier.
"""
import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import einladung as ei  # noqa: E402


def frisch(mail="salon@example.de", **kw):
    e = ei.anfordern(mail, **kw)
    assert e.ok, e.grund
    return e.einladung, e.schluessel


# ————— Anfordern —————

def test_eine_gueltige_adresse_bekommt_eine_einladung():
    e, s = frisch()
    assert e.mail == "salon@example.de"
    assert e.offen
    assert s and len(s) >= 30


def test_die_adresse_wird_vereinheitlicht():
    e, _ = frisch("  Salon@Example.DE  ")
    assert e.mail == "salon@example.de"


@pytest.mark.parametrize("kaputt", ["", "   ", "keine-mail", "a@b", "@example.de",
                                    "zwei@@example.de", "leer@.de"])
def test_eine_kaputte_adresse_wird_freundlich_abgelehnt(kaputt):
    e = ei.anfordern(kaputt)
    assert not e.ok and "nicht richtig" in e.grund


def test_der_schluessel_steht_nirgends_im_klartext():
    """Wer die Datenbank liest, darf sich damit nicht anmelden können."""
    e, s = frisch()
    assert s not in e.schluessel_hash
    assert e.schluessel_hash == ei.schluessel_hash(s)
    assert len(e.schluessel_hash) == 64


def test_zwei_anfragen_ergeben_zwei_verschiedene_schluessel():
    _, a = frisch()
    _, b = frisch()
    assert a != b


def test_nach_drei_versuchen_wird_gebremst():
    """Sonst ist das Formular ein Versandwerkzeug für fremde Postfächer."""
    from einladung import _jetzt  # noqa: PLC0415
    jetzt = _jetzt()
    frueher = [jetzt - timedelta(minutes=m) for m in (5, 30, 120)]
    e = ei.anfordern("salon@example.de", frueher=frueher)
    assert not e.ok
    assert "Postfach" in e.grund


def test_alte_versuche_zaehlen_nicht_mehr_mit():
    from einladung import _jetzt  # noqa: PLC0415
    alt = [_jetzt() - timedelta(days=2) for _ in range(5)]
    assert ei.anfordern("salon@example.de", frueher=alt).ok


def test_die_bremse_verraet_nichts_ueber_das_konto():
    """Der Text darf nicht sagen, ob es die Adresse schon gibt."""
    from einladung import _jetzt  # noqa: PLC0415
    e = ei.anfordern("salon@example.de",
                     frueher=[_jetzt()] * ei.VERSUCHE_MAX)
    for verraeterisch in ("Konto", "registriert", "bekannt", "existiert"):
        assert verraeterisch not in e.grund


def test_die_antwort_nach_aussen_ist_immer_dieselbe():
    assert "Wenn die Adresse stimmt" in ei.ANTWORT_NACH_AUSSEN
    for verraeterisch in ("Konto", "bereits", "neu"):
        assert verraeterisch not in ei.ANTWORT_NACH_AUSSEN


# ————— Prüfen —————

def test_der_richtige_schluessel_geht_durch():
    e, s = frisch()
    assert ei.pruefen(e, s).ok


def test_ein_falscher_schluessel_faellt_durch():
    e, _ = frisch()
    p = ei.pruefen(e, "irgendwas-anderes")
    assert not p.ok and "nicht bekannt" in p.grund


def test_eine_unbekannte_einladung_verraet_nichts_anderes():
    """Falscher Schlüssel und unbekannte Einladung müssen gleich klingen —
    sonst lässt sich erraten, welche Links es gibt."""
    e, _ = frisch()
    assert ei.pruefen(None, "x").grund == ei.pruefen(e, "falsch").grund


def test_ein_abgelaufener_link_wird_abgelehnt():
    from einladung import _jetzt  # noqa: PLC0415
    e, s = frisch()
    e.frist = _jetzt() - timedelta(seconds=1)
    p = ei.pruefen(e, s)
    assert not p.ok and "abgelaufen" in p.grund


def test_ein_verbrauchter_link_gilt_nicht_noch_einmal():
    from einladung import _jetzt  # noqa: PLC0415
    e, s = frisch()
    e.verbraucht = _jetzt()
    p = ei.pruefen(e, s)
    assert not p.ok and "schon benutzt" in p.grund
    assert "E-Mail und Passwort" in p.grund     # und sagt, wie es weitergeht


# ————— Das Passwort, zweimal —————

def test_zwei_gleiche_gute_passwoerter_gehen_durch():
    assert ei.passwort_pruefen("salon-am-markt-2026", "salon-am-markt-2026").ok


def test_zwei_verschiedene_werden_abgelehnt():
    p = ei.passwort_pruefen("salon-am-markt-2026", "salon-am-markt-2025")
    assert not p.ok and "nicht gleich" in p.grund


def test_zu_kurz_wird_abgelehnt_mit_einem_rat():
    p = ei.passwort_pruefen("kurz", "kurz")
    assert not p.ok and "Satz" in p.grund


def test_einloesen_prueft_beides():
    e, s = frisch()
    assert ei.einloesen(e, s, "salon-am-markt-2026", "salon-am-markt-2026").ok
    assert not ei.einloesen(e, "falsch", "salon-am-markt-2026",
                            "salon-am-markt-2026").ok
    assert not ei.einloesen(e, s, "kurz", "kurz").ok


def test_einloesen_veraendert_die_einladung_nicht():
    """Es gibt genau eine Stelle, die schreibt — sonst entsteht der Fall
    „Konto angelegt, Link noch offen"."""
    e, s = frisch()
    ei.einloesen(e, s, "salon-am-markt-2026", "salon-am-markt-2026")
    assert e.verbraucht is None


# ————— Was mitgetragen wird —————

def test_das_gelesene_wartet_bis_zur_anmeldung():
    e, _ = frisch(gelesen={"steuernummer": "71 015 73457"},
                  bericht="# Deine Auswertung")
    assert e.gelesen["steuernummer"] == "71 015 73457"
    assert e.bericht.startswith("# Deine Auswertung")


def test_das_gelesene_wird_kopiert_nicht_verlinkt():
    quelle = {"a": 1}
    e, _ = frisch(gelesen=quelle)
    quelle["b"] = 2
    assert "b" not in e.gelesen


# ————— Die E-Mail —————

def test_die_mail_traegt_anriss_und_link():
    e, s = frisch(bericht="Die Steuerberatung kostet 94 % deines Gewinns.")
    betreff, text = ei.mail_text(e, s, basis="https://babu.0711.io/")
    assert "Auswertung" in betreff
    assert "94 %" in text
    assert f"https://babu.0711.io/auswertung/{s}" in text


def test_die_mail_sagt_wie_lange_der_link_gilt():
    e, s = frisch()
    _, text = ei.mail_text(e, s, basis="https://babu.0711.io")
    assert f"{ei.FRIST.days} Tage" in text
    assert "nur einmal" in text


def test_die_mail_enthaelt_kein_passwort():
    e, s = frisch()
    _, text = ei.mail_text(e, s, basis="https://babu.0711.io")
    assert "Passwort" in text          # es wird erwähnt …
    assert "Dein Passwort:" not in text  # … aber keines mitgeschickt


def test_die_mail_sagt_was_bei_irrtum_zu_tun_ist():
    """Wer sie ungefragt bekommt, muss wissen, dass Nichtstun genügt."""
    e, s = frisch()
    _, text = ei.mail_text(e, s, basis="https://babu.0711.io")
    assert "nicht angefordert" in text and "ignorier" in text.lower()
