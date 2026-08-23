"""Der Monatslauf: übergeben und nachrechnen.

babu rechnet die Abrechnung nicht selbst — das macht die zertifizierte
Schiene. Was babu macht, ist prüfen, was fehlt, die Bewegungsdaten liefern
und nachrechnen, was zurückkommt. Genau daran hängen diese Tests.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lohnlauf as ll  # noqa: E402


BETRIEB = {"name": "Salon Nina", "betriebsnummer": "12345678",
           "steuernummer": "99012/34567", "ort": "Stuttgart"}


def person(**anders):
    grund = {
        "vorname": "Jana", "name": "Holder", "geburtsdatum": "1994-03-02",
        "strasse": "Marktstr. 3", "plz": "70173", "ort": "Stuttgart",
        "staatsangehoerigkeit": "deutsch",
        "rentenvers_nr": "12030294H123", "steuer_idnr": "12345678911",
        "krankenkasse": "AOK Baden-Württemberg", "iban": "DE02120300000000202051",
        "eintritt": "2026-01-15", "art": "teilzeit", "entgelt": 160000,
        "stunden_woche": 24,
    }
    return {**grund, **anders}


# ————— Was fehlt noch? —————

def test_vollstaendige_person_ist_abrechenbar():
    assert ll.was_fehlt(person()) == []
    assert ll.abrechenbar(person()) is True


@pytest.mark.parametrize("feld", ["rentenvers_nr", "steuer_idnr", "iban",
                                  "krankenkasse", "geburtsdatum", "entgelt"])
def test_jedes_pflichtfeld_wird_vermisst(feld):
    fehlt = ll.was_fehlt(person(**{feld: ""}))
    assert [f["feld"] for f in fehlt] == [feld]


def test_der_hinweis_sagt_auch_wo_man_es_herbekommt():
    """„Steuer-IdNr. fehlt" hilft niemandem, der nicht weiß, was das ist."""
    [f] = ll.was_fehlt(person(steuer_idnr=""))
    assert "elfstellig" in f["text"] and "Steuerbescheid" in f["text"]


def test_minijob_braucht_die_aussage_zur_rentenversicherung():
    fehlt = ll.was_fehlt(person(art="minijob", entgelt=60300))
    assert any(f["feld"] == "rv_befreiung" for f in fehlt)
    # Ausdrücklich „kein Antrag" reicht — nur schweigen reicht nicht.
    assert ll.was_fehlt(person(art="minijob", entgelt=60300,
                               rv_befreiung=False)) == []


def test_auslaendischer_titel_wird_verlangt():
    """§ 4a Abs. 5 AufenthG — Kopie für die Dauer der Beschäftigung."""
    fehlt = ll.was_fehlt(person(titel_pflichtig=True))
    assert any("4a" in f["text"] for f in fehlt)


# ————— Die Stunden des Monats —————

def zeit(tag, minuten=480, pause=30, bestaetigt=True):
    return {"tag": tag, "minuten": minuten, "pause_min": pause,
            "bestaetigt": bestaetigt}


def test_nur_bestaetigte_zeiten_zaehlen():
    """Unbestätigte Zeiten in eine Abrechnung zu übernehmen hieße,
    ungeprüft Geld zu bewegen."""
    z = [zeit("2026-09-01"), zeit("2026-09-02"),
         zeit("2026-09-03", bestaetigt=False)]
    ergebnis = ll.monatsstunden(z, "2026-09")
    assert ergebnis["stunden"] == 15.0        # zweimal 7,5 Stunden
    assert ergebnis["tage"] == 2
    assert ergebnis["unbestaetigt"] == 1


def test_pausen_werden_abgezogen():
    assert ll.monatsstunden([zeit("2026-09-01", 480, 60)], "2026-09")["stunden"] == 7.0


def test_zeiten_anderer_monate_bleiben_draussen():
    z = [zeit("2026-08-31"), zeit("2026-09-01"), zeit("2026-10-01")]
    assert ll.monatsstunden(z, "2026-09")["tage"] == 1


def test_laengere_pause_als_arbeitstag_ist_ein_fehler():
    with pytest.raises(ll.LohnlaufFehler) as e:
        ll.monatsstunden([zeit("2026-09-01", 240, 300)], "2026-09")
    assert "2026-09-01" in str(e.value)


def test_kaputter_monat_wird_abgelehnt():
    for schlecht in ("2026-13", "September", "2026", ""):
        with pytest.raises(ll.LohnlaufFehler):
            ll.monatsstunden([], schlecht)


# ————— Abwesenheiten —————

def test_abwesenheit_wird_in_kalendertagen_gezaehlt():
    a = [{"art": "urlaub", "von": "2026-09-07", "bis": "2026-09-11"},
         {"art": "krank", "von": "2026-09-21", "bis": "2026-09-21"}]
    z = ll.abwesenheiten_zaehlen(a, "2026-09")
    assert z["urlaub"] == 5 and z["krank"] == 1


def test_abwesenheit_ueber_den_monatswechsel_wird_geteilt():
    a = [{"art": "urlaub", "von": "2026-08-28", "bis": "2026-09-04"}]
    assert ll.abwesenheiten_zaehlen(a, "2026-08")["urlaub"] == 4
    assert ll.abwesenheiten_zaehlen(a, "2026-09")["urlaub"] == 4


def test_rueckwaerts_laufende_abwesenheit():
    with pytest.raises(ll.LohnlaufFehler):
        ll.abwesenheiten_zaehlen(
            [{"art": "urlaub", "von": "2026-09-10", "bis": "2026-09-01"}], "2026-09")


# ————— Sozialversicherung überschlagen —————

def test_die_beitraege_teilen_sich_ungefaehr_haelftig():
    b = ll.sv_beitraege(300000, kv_zusatz=0.029)
    # Der Arbeitgeber trägt zusätzlich die Insolvenzgeldumlage.
    assert abs(b["arbeitnehmer"] - b["arbeitgeber"]) < 1500
    assert b["gesamtkosten"] == 300000 + b["arbeitgeber"]


def test_kinderlose_zahlen_den_zuschlag_allein():
    ohne = ll.sv_beitraege(300000)
    mit = ll.sv_beitraege(300000, kinderlos=True)
    assert mit["arbeitnehmer"] > ohne["arbeitnehmer"]
    assert mit["arbeitgeber"] == ohne["arbeitgeber"]


def test_kinder_senken_den_pflegebeitrag():
    ohne = ll.sv_beitraege(300000)
    mit_drei = ll.sv_beitraege(300000, kinder_abschlaege=3)
    assert mit_drei["teile"]["pv"] < ohne["teile"]["pv"]


def test_hoechstens_vier_abschlaege():
    """Ab dem sechsten Kind ändert sich nichts mehr."""
    assert (ll.sv_beitraege(300000, kinder_abschlaege=4)["teile"]["pv"]
            == ll.sv_beitraege(300000, kinder_abschlaege=9)["teile"]["pv"])


def test_ueber_der_bemessungsgrenze_steigt_es_nicht_weiter():
    hoch = ll.sv_beitraege(1_500_000)
    noch_hoeher = ll.sv_beitraege(3_000_000)
    assert hoch["teile"]["kv"] == noch_hoeher["teile"]["kv"]
    assert hoch["teile"]["rv"] == noch_hoeher["teile"]["rv"]


def test_negatives_brutto_gibt_es_nicht():
    with pytest.raises(ll.LohnlaufFehler):
        ll.sv_beitraege(-1)


def test_der_halbe_cent_geht_auf():
    """§ 23 SGB IV verlangt kaufmännische Rundung, nicht die zur geraden Zahl.

    1.002,50 € Brutto ergeben rechnerisch 186,465 € Rentenversicherung und
    26,065 € Arbeitslosenversicherung. Pythons `round()` machte daraus
    186,46 € und 26,06 €, weil es auf die gerade Ziffer abrundet — ein
    falsch gemeldeter Beitrag, kein Schönheitsfehler.
    """
    b = ll.sv_beitraege(100250)
    assert b["teile"]["rv"] == 18647      # nicht 18646
    assert b["teile"]["alv"] == 2607      # nicht 2606


def test_der_halbe_cent_geht_auch_dann_auf_wenn_float_daneben_liegt():
    """1.001,25 € × 3,6 % sind exakt 36,045 € — als `float` aber 36,04499…

    Deshalb wird der Anteil in `Decimal` multipliziert: sonst liefe die
    Rundungsregel ins Leere, bevor sie überhaupt greifen könnte.
    """
    assert ll.sv_beitraege(100125)["teile"]["pv"] == 3605      # nicht 3604


def test_bekannte_beitraege_verschieben_sich_nicht():
    """Was schon richtig gerundet war, muss auf den Cent gleich bleiben."""
    b = ll.sv_beitraege(300000, kv_zusatz=0.029)
    assert b["teile"] == {"kv": 52500, "pv": 10800, "rv": 55800,
                          "alv": 7800, "insolvenzgeld": 450}


# ————— Die Übergabe —————

def test_die_uebergabe_enthaelt_stammdaten_und_bewegungsdaten():
    leute = [person(zeiten=[zeit("2026-09-01"), zeit("2026-09-02")],
                    abwesenheiten=[{"art": "urlaub", "von": "2026-09-07",
                                    "bis": "2026-09-08"}])]
    u = ll.uebergabe_bauen(BETRIEB, leute, "2026-09")
    assert u["bereit"] is True
    [m] = u["mitarbeiter"]
    assert m["person"]["steuer_idnr"] == "12345678911"
    assert m["monat"]["stunden"] == 15.0 and m["monat"]["urlaub"] == 2


def test_ohne_betriebsnummer_geht_nichts():
    with pytest.raises(ll.LohnlaufFehler) as e:
        ll.uebergabe_bauen({"name": "Salon"}, [person()], "2026-09")
    assert "Betriebsnummer" in str(e.value)


def test_unvollstaendige_person_blockiert_nicht_die_anderen():
    """Wer fertig ist, wird abgerechnet; wer fehlt, wird benannt."""
    u = ll.uebergabe_bauen(BETRIEB, [person(), person(vorname="Mia",
                                             steuer_idnr="")], "2026-09")
    assert len(u["mitarbeiter"]) == 1
    assert u["unvollstaendig"][0]["name"] == "Mia Holder"
    assert u["bereit"] is False


def test_die_hindernisse_stehen_auf_deutsch_da():
    u = ll.uebergabe_bauen(BETRIEB, [person(), person(vorname="Mia", iban="")],
                           "2026-09")
    hindernisse = ll.uebergabe_pruefen(u)
    assert any("Mia Holder" in h and "IBAN" in h for h in hindernisse)


def test_unbestaetigte_zeiten_werden_als_hindernis_gemeldet():
    leute = [person(zeiten=[zeit("2026-09-01", bestaetigt=False)])]
    u = ll.uebergabe_bauen(BETRIEB, leute, "2026-09")
    hindernisse = ll.uebergabe_pruefen(u)
    assert any("nicht bestätigt" in h for h in hindernisse)


def test_leerer_monat_wird_gemeldet():
    u = ll.uebergabe_bauen(BETRIEB, [], "2026-09")
    assert u["bereit"] is False
    assert any("niemand abzurechnen" in h for h in ll.uebergabe_pruefen(u))


def test_die_fassung_wird_mitgefuehrt():
    u = ll.uebergabe_bauen(BETRIEB, [person()], "2026-09")
    assert u["fassung"] == ll.UEBERGABE_FASSUNG and u["monat"] == "2026-09"


# ————— Die Gegenprobe —————

def _zeile(entgelt=300000, **sv):
    return {"beschaeftigung": {"entgelt": entgelt},
            "sozialversicherung": {"kv_zusatzbeitrag": "2.90", **sv}}


def test_gleiche_zahlen_gehen_durch():
    """Beide Seiten folgen demselben Ablaufplan — 3.000 € StKl I ergeben
    293,08 €, gegen den BMF-Rechner geprüft."""
    probe = ll.gegenprobe(_zeile(kinderlos=True), {"lohnsteuer": 29308, "soli": 0},
                          steuerklasse=1)
    assert probe["stimmt"] is True
    assert "stimmt überein" in probe["satz"]


def test_abweichung_wird_beziffert_und_erklaert():
    probe = ll.gegenprobe(_zeile(kinderlos=True), {"lohnsteuer": 30000, "soli": 0},
                          steuerklasse=1)
    assert probe["stimmt"] is False
    [a] = probe["abweichungen"]
    assert a["feld"] == "lohnsteuer" and a["differenz"] == 692
    assert "+6,92 €" in probe["satz"], "Beträge gehören auf Deutsch"
    assert "Lohnsteuer" in probe["satz"]
    assert "vor dem auszahlen" in probe["satz"].lower()


def test_die_gegenprobe_merkt_eine_falsche_steuerklasse():
    """Der häufigste Zahlendreher: die Klasse verrutscht."""
    richtig = ll.gegenprobe(_zeile(kinderlos=True),
                            {"lohnsteuer": 29308, "soli": 0}, steuerklasse=1)
    falsch = ll.gegenprobe(_zeile(kinderlos=True),
                           {"lohnsteuer": 29308, "soli": 0}, steuerklasse=5)
    assert richtig["stimmt"] and not falsch["stimmt"]
