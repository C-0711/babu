"""Der Briefkopf der Rechnung — und was passiert, wenn die KI Unsinn sagt.

Eine Rechnung wird gedruckt und Kundinnen in die Hand gegeben. Ein Vorschlag
des Sprachmodells darf sie nie unleserlich machen: was nicht taugt, fällt
auf die Vorgabe zurück.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import marke  # noqa: E402


def test_ein_brauchbarer_vorschlag_wird_uebernommen():
    stil = marke.stil_pruefen({"farbe": "#7A3B2E", "schrift": "serif",
                               "ausrichtung": "mitte", "linie": False,
                               "begruendung": "Warmes Kupfer passt zu Haarfarbe."})
    assert stil["farbe"] == "#7A3B2E"
    assert stil["schrift"] == "serif"
    assert stil["ausrichtung"] == "mitte"
    assert stil["linie"] is False
    assert "Kupfer" in stil["begruendung"]


def test_gar_kein_vorschlag_ist_kein_fehler():
    for roh in (None, {}, "Quatsch", []):
        assert marke.stil_pruefen(roh) == marke.VORGABE


@pytest.mark.parametrize("farbe", ["rot", "#GGGGGG", "#12345", "", "#fff",
                                   "rgb(1,2,3)", None])
def test_unbrauchbare_farben_fallen_zurueck(farbe):
    assert marke.stil_pruefen({"farbe": farbe})["farbe"] == marke.VORGABE["farbe"]


def test_zu_helle_farbe_wird_abgelehnt():
    """Hellgelb auf Weiß ist auf Papier nicht lesbar."""
    assert marke.stil_pruefen({"farbe": "#FFF7A0"})["farbe"] == marke.VORGABE["farbe"]
    assert marke.stil_pruefen({"farbe": "#F2F2F2"})["farbe"] == marke.VORGABE["farbe"]


def test_dunkle_farbe_geht_durch():
    for farbe in ("#7A3B2E", "#1B3A2F", "#2E2A5C"):
        assert marke.stil_pruefen({"farbe": farbe})["farbe"] == farbe


def test_erfundene_schrift_faellt_zurueck():
    assert marke.stil_pruefen({"schrift": "Comic Sans"})["schrift"] == "serif"
    assert marke.stil_pruefen({"ausrichtung": "diagonal"})["ausrichtung"] == "links"


def test_kleinschreibung_ist_egal():
    stil = marke.stil_pruefen({"farbe": "#7a3b2e", "schrift": "SANS",
                               "ausrichtung": "Mitte"})
    assert stil["farbe"] == "#7A3B2E"
    assert stil["schrift"] == "sans"
    assert stil["ausrichtung"] == "mitte"


def test_die_frage_nennt_den_salon():
    frage = marke.frage_bauen({"betrieb_name": "Salon Nina",
                               "rechtsform": "Einzelunternehmen",
                               "anschrift": "Hauptstraße 5, Stuttgart"})
    assert "Salon Nina" in frage
    assert "Stuttgart" in frage
    assert "JSON" in frage


def test_die_frage_geht_auch_ohne_daten():
    frage = marke.frage_bauen({})
    assert "Friseursalon" in frage


def test_der_stil_laesst_sich_erklaeren():
    """Die Nutzerin soll lesen können, was gewählt wurde — ohne Hex-Codes."""
    text = marke.als_text({"schrift": "serif", "ausrichtung": "links", "linie": True})
    assert "Klassisch" in text and "linksbündig" in text and "Linie" in text
    assert "#" not in text


# ————— Logo von der KI —————

def test_der_logo_auftrag_nennt_den_salon_genau():
    """Ein Logo mit falsch geschriebenem Namen ist wertlos."""
    auftrag = marke.logo_auftrag({"betrieb_name": "Salon Nina"})
    assert auftrag.count("Salon Nina") >= 2
    assert "korrekt geschrieben" in auftrag


def test_der_auftrag_verbietet_was_kein_logo_ist():
    auftrag = marke.logo_auftrag({"betrieb_name": "Salon Nina"})
    for verboten in ("keine Fotografie", "kein 3D", "keine Verläufe"):
        assert verboten in auftrag


def test_der_stil_geht_in_den_auftrag_ein():
    schlicht = marke.logo_auftrag({"betrieb_name": "X"}, "schlicht")
    edel = marke.logo_auftrag({"betrieb_name": "X"}, "edel")
    assert schlicht != edel
    assert "zeitlose" in schlicht and "edle" in edel


def test_unbekannter_stil_faellt_auf_schlicht_zurueck():
    assert marke.logo_auftrag({"betrieb_name": "X"}, "knallbunt") == \
        marke.logo_auftrag({"betrieb_name": "X"}, "schlicht")


def test_die_farbe_wird_geprueft_bevor_sie_in_den_auftrag_geht():
    assert "#7A3B2E" in marke.logo_auftrag({"betrieb_name": "X"}, farbe="#7A3B2E")
    # Unsinn fällt auf die Vorgabe zurück, statt im Auftrag zu landen.
    assert marke.VORGABE["farbe"] in marke.logo_auftrag({"betrieb_name": "X"},
                                                        farbe="knallrot")


def test_ohne_namen_kein_absturz():
    assert "Salon" in marke.logo_auftrag({})


# ————— Der Farbkatalog: vier Schritte zum Logo —————

def test_jede_katalogfarbe_ist_druckbar():
    """Eine Farbe, die auf Papier verschwindet, gehört nicht in den Katalog."""
    assert marke.katalog_pruefen() == []


def test_der_katalog_kommt_ohne_hexcodes_aus():
    """Die Nutzerin wählt „Kupfer", nicht „#8A4B2A"."""
    for eintrag in marke.KATALOG:
        assert eintrag["name"] and not eintrag["name"].startswith("#")
        assert eintrag["dazu"], f"{eintrag['name']} hat keine Erklärung"


def test_farbe_nachschlagen():
    assert marke.farbe_aus_katalog("kupfer")["hex"] == "#8A4B2A"
    assert marke.farbe_aus_katalog("KUPFER")["name"] == "Kupfer"
    assert marke.farbe_aus_katalog("lila") is None
    assert marke.farbe_aus_katalog(None) is None


def test_es_sind_genau_vier_schritte():
    assert [s["nummer"] for s in marke.SCHRITTE] == [1, 2, 3, 4]
    for schritt in marke.SCHRITTE:
        assert schritt["titel"] and schritt["frage"].endswith(("?", "."))


def test_katalogfarben_ueberstehen_die_pruefung():
    """Was im Katalog steht, muss auch als Stil durchgehen."""
    for eintrag in marke.KATALOG:
        stil = marke.stil_pruefen({"farbe": eintrag["hex"]})
        assert stil["farbe"] == eintrag["hex"].upper()


# ————— Ein Knopf, zehn Vorschläge —————

def test_zehn_vorschlaege_sind_verschieden():
    saetze = marke.vorschlag_saetze({"betrieb_name": "Salon Nina"})
    assert len(saetze) == 10
    kombis = {(s["stil"], s["farbe"]) for s in saetze}
    assert len(kombis) == 10, "doppelte Vorschläge verschwenden einen Platz"


def test_jeder_stil_kommt_vor():
    saetze = marke.vorschlag_saetze({"betrieb_name": "X"})
    assert set(s["stil"] for s in saetze) == set(marke.LOGO_STILE)


def test_ein_zweiter_versuch_zeigt_anderes():
    erste = marke.vorschlag_saetze({"betrieb_name": "X"}, saat=0)
    zweite = marke.vorschlag_saetze({"betrieb_name": "X"}, saat=1)
    assert [s["farbe"] for s in erste] != [s["farbe"] for s in zweite]


def test_jeder_vorschlag_traegt_seinen_auftrag():
    for s in marke.vorschlag_saetze({"betrieb_name": "Salon Nina"}):
        assert "Salon Nina" in s["auftrag"]
        assert s["farbe"] in s["auftrag"]
        assert s["farbe_name"]


def test_die_anzahl_bleibt_im_rahmen():
    assert len(marke.vorschlag_saetze({}, anzahl=0)) == 1
    assert len(marke.vorschlag_saetze({}, anzahl=99)) == 12


def test_aus_dem_zeichen_wird_der_ganze_auftritt():
    """Ein Tipp auf ein Logo — und Farbe, Schrift und Linie stehen."""
    vorschlag = {"stil": "edel", "farbe": "#1F3A5F", "farbe_name": "Nachtblau"}
    auftritt = marke.auftritt_aus(vorschlag)
    assert auftritt["farbe"] == "#1F3A5F"
    assert auftritt["schrift"] == "serif"
    assert auftritt["ausrichtung"] == "mitte"
    assert "Nachtblau" in auftritt["begruendung"]


def test_verspielt_bekommt_die_moderne_schrift():
    assert marke.auftritt_aus({"stil": "verspielt", "farbe": "#8A4B2A"})["schrift"] == "sans"
    assert marke.auftritt_aus({"stil": "schlicht", "farbe": "#8A4B2A"})["schrift"] == "serif"


def test_ein_kaputter_vorschlag_ergibt_trotzdem_einen_auftritt():
    assert marke.auftritt_aus({})["farbe"] == marke.VORGABE["farbe"]
    assert marke.auftritt_aus(None)["schrift"] in marke.SCHRIFTEN
