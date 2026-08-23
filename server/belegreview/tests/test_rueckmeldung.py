"""Aus Ninas Worten wird ein Vorgang.

Zwei Dinge müssen hier stimmen. Die Überschrift muss IHRE Worte tragen —
ein zusammengefasster Titel klingt glatter und verliert genau das, woran
sie ihre Meldung wiedererkennt. Und der Zusammenhang muss vollständig
mitkommen, sonst fragt jemand zurück, was Nina längst vergessen hat.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rueckmeldung import Meldung, als_vorgang, koerper_aus, titel_aus  # noqa: E402


# ————— Die Überschrift —————

@pytest.mark.parametrize("text, soll", [
    ("Der Beleg vom Bäcker zeigt 19 % statt 7 %.",
     "Der Beleg vom Bäcker zeigt 19 % statt 7 %"),
    # Das Ausrufezeichen bleibt: es trägt ihren Ton, ein Schlusspunkt nicht.
    ("Ich kann Kontoauszüge nicht hochladen! Das nervt.",
     "Ich kann Kontoauszüge nicht hochladen!"),
    ("Warum steht da der falsche Monat? Der Beleg ist vom März.",
     "Warum steht da der falsche Monat?"),
    ("Kurz", "Kurz"),
    ("  viel   Weißraum   dazwischen  ", "viel Weißraum dazwischen"),
])
def test_der_titel_sind_ihre_worte(text, soll):
    assert titel_aus(text) == soll


def test_ein_langer_text_bricht_am_wortende():
    text = ("Wenn ich einen Beleg fotografiere und dann sofort weiterwische "
            "dann bleibt manchmal das alte Bild stehen und ich sehe nicht ob "
            "es geklappt hat")
    t = titel_aus(text)
    assert len(t) <= 76
    assert t.endswith("…")
    assert not t[:-2].endswith(" ")          # kein abgeschnittenes Wort
    assert text.startswith(t[:-2].rstrip())  # es sind ihre Worte, unverändert


def test_ein_leerer_text_ergibt_keinen_leeren_titel():
    assert titel_aus("   ") == "Rückmeldung ohne Text"


def test_der_erste_satz_gewinnt_auch_wenn_mehr_kommt():
    t = titel_aus("Das Datum ist falsch. Es steht der Tag vom Hochladen drin, "
                  "nicht der vom Beleg.")
    assert t == "Das Datum ist falsch"


# ————— Der Zusammenhang —————

def test_alles_bekannte_steht_im_koerper():
    k = koerper_aus(Meldung(
        text="Der Betrag stimmt nicht.", quelle="app", ansicht="Dokumente",
        beleg="RE-2026-4711", von="nina@0711.io",
        geraet="iPhone 15 Pro Max, iOS 26.6", fassung="34c4a20"))
    for erwartet in ("Der Betrag stimmt nicht.", "der App", "Dokumente",
                     "RE-2026-4711", "nina@0711.io", "iPhone 15 Pro Max",
                     "34c4a20"):
        assert erwartet in k, erwartet


def test_was_unbekannt_ist_steht_nicht_als_leere_zeile_da():
    k = koerper_aus(Meldung(text="Fehlt was.", quelle="portal"))
    assert "Ansicht" not in k and "Gerät" not in k and "Beleg " not in k
    assert "dem Portal" in k


def test_der_koerper_sagt_woher_die_meldung_kommt():
    """Wer das liest, soll nicht raten, ob Nina es getippt hat."""
    k = koerper_aus(Meldung(text="x"))
    assert "Rückmeldeknopf" in k and "eigenen Worten" in k


# ————— Der Vorgang —————

def test_ein_fehler_wird_ein_bug():
    v = als_vorgang(Meldung(text="Kaputt.", art="fehler", quelle="app"))
    assert v["type"] == "bug" and v["component"] == "App"


def test_ein_wunsch_wird_eine_aufgabe():
    v = als_vorgang(Meldung(text="Wäre schön.", art="wunsch", quelle="portal"))
    assert v["type"] == "task" and v["component"] == "Web"


def test_eine_meldung_geht_in_die_triage_nicht_an_einen_agenten():
    """Fixits Formular setzt von sich aus einen Agenten und „in Arbeit".
    Ninas Meldung ist noch nicht entschieden — erst liest ein Mensch."""
    v = als_vorgang(Meldung(text="Etwas stimmt nicht."))
    assert v["status"] == "todo"
    assert "assignee" not in v and "assignee_kind" not in v


def test_der_autor_ist_nina():
    v = als_vorgang(Meldung(text="x"), autor="nina")
    assert v["actor"] == "nina" and v["author"] == "nina"


def test_ihr_text_steht_vollstaendig_im_vorgang():
    lang = "Erste Zeile.\nZweite Zeile mit Umlauten: äöüß.\nDritte."
    v = als_vorgang(Meldung(text=lang))
    for zeile in lang.split("\n"):
        assert zeile in v["body"]


@pytest.mark.parametrize("art", ["", "bug", "Fehler", None, "sonstiges"])
def test_eine_unbekannte_art_faellt_sofort_auf(art):
    with pytest.raises(ValueError):
        als_vorgang(Meldung(text="x", art=art))


def test_eine_leere_meldung_wird_gar_nicht_erst_zum_vorgang():
    with pytest.raises(ValueError):
        als_vorgang(Meldung(text="   \n  "))


def test_die_nutzlast_hat_genau_die_felder_die_fixit_kennt():
    """Abgeschaut am echten Aufruf des Fixit-Formulars (23.08.2026)."""
    v = als_vorgang(Meldung(text="x"))
    assert set(v) == {"actor", "author", "type", "title", "body",
                      "priority", "component", "status"}
