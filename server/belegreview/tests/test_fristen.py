"""Steuerliche Termine — reine Rechnung, an echten Kalenderdaten geprüft.

Geprüft wird, was eine verpasste Frist kosten würde: die Verschiebung
über Wochenenden und Feiertage, die Dauerfristverlängerung und der
drittletzte Bankarbeitstag der Sozialversicherung.
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fristen as fr  # noqa: E402


def profil(**werte):
    grund = {"kleinunternehmer": False, "ustva_rhythmus": "monatlich",
             "dauerfristverlaengerung": False, "lohn": False,
             "lohnsteuer_rhythmus": "vierteljaehrlich", "bundesland": "",
             "steuerberater": False}
    grund.update(werte)
    return grund


def datum(termine, art, enthaelt):
    """Das Datum des einen Termins, dessen Titel `enthaelt` enthält."""
    treffer = [t for t in termine if t["art"] == art and enthaelt in t["titel"]]
    assert len(treffer) == 1, f"{art}/{enthaelt}: {len(treffer)} Treffer"
    return treffer[0]["datum"]


# ————— Feiertage —————

def test_ostern_stimmt_mit_dem_kalender():
    # Nachschlagbare Osterdaten — die Formel muss sie treffen.
    assert fr.ostersonntag(2026) == dt.date(2026, 4, 5)
    assert fr.ostersonntag(2027) == dt.date(2027, 3, 28)
    assert fr.ostersonntag(2024) == dt.date(2024, 3, 31)


def test_bundesweite_feiertage_sind_immer_dabei():
    tage = fr.feiertage(2026)
    assert tage[dt.date(2026, 1, 1)] == "Neujahr"
    assert tage[dt.date(2026, 10, 3)] == "Tag der Deutschen Einheit"
    assert tage[dt.date(2026, 4, 3)] == "Karfreitag"        # 2 Tage vor Ostern
    assert tage[dt.date(2026, 5, 14)] == "Christi Himmelfahrt"


def test_fronleichnam_nur_wo_er_gilt():
    fronleichnam = fr.ostersonntag(2026) + dt.timedelta(days=60)
    assert fronleichnam in fr.feiertage(2026, "BW")
    assert fronleichnam not in fr.feiertage(2026, "BE")
    assert fronleichnam not in fr.feiertage(2026)           # ohne Land: bundesweit


def test_ohne_bundesland_wird_nur_bundesweit_gerechnet():
    # Lieber eine Frist zu früh im Kalender als eine verpasste.
    assert dt.date(2026, 11, 1) not in fr.feiertage(2026)
    assert dt.date(2026, 11, 1) in fr.feiertage(2026, "BY")


# ————— Verschiebung nach § 108 Abs. 3 AO —————

def test_frist_am_samstag_rutscht_auf_montag():
    # 10.01.2026 ist ein Samstag.
    assert dt.date(2026, 1, 10).weekday() == 5
    termine = fr.fristen_jahr(2026, profil())
    assert datum(termine, "ustva", "Dezember 2025") == "2026-01-12"


def test_frist_am_werktag_bleibt_stehen():
    # 10.03.2026 ist ein Dienstag.
    termine = fr.fristen_jahr(2026, profil())
    assert datum(termine, "ustva", "Februar 2026") == "2026-03-10"


def test_feiertag_schiebt_die_frist_weiter():
    feier = {dt.date(2026, 3, 10): "Testfeiertag"}
    assert fr.werktag_ab(dt.date(2026, 3, 10), feier) == dt.date(2026, 3, 11)


# ————— Umsatzsteuer-Voranmeldung —————

def test_monatlich_ergibt_zwoelf_voranmeldungen():
    termine = fr.fristen_jahr(2026, profil())
    assert len([t for t in termine if t["art"] == "ustva"]) == 12


def test_vierteljaehrlich_ergibt_vier():
    termine = fr.fristen_jahr(2026, profil(ustva_rhythmus="vierteljaehrlich"))
    ustva = [t for t in termine if t["art"] == "ustva"]
    assert len(ustva) == 4
    # 1. Quartal endet im März, fällig am 10. April (Freitag).
    assert datum(termine, "ustva", "1. Quartal") == "2026-04-10"


def test_dauerfristverlaengerung_schiebt_um_einen_monat():
    ohne = fr.fristen_jahr(2026, profil())
    mit = fr.fristen_jahr(2026, profil(dauerfristverlaengerung=True))
    # Januar 2026: ohne Verlängerung am 10.02., mit am 10.03.
    assert datum(ohne, "ustva", "Januar 2026") == "2026-02-10"
    assert datum(mit, "ustva", "Januar 2026") == "2026-03-10"


def test_dezember_faellt_ins_folgejahr():
    # Die Dezember-Anmeldung steht im Kalender des Folgejahres, nicht mehr
    # in dem des Zeitraums — dort wäre sie im Januar unsichtbar.
    assert not [t for t in fr.fristen_jahr(2026, profil())
                if "Dezember 2026" in t["titel"]]
    termine = fr.fristen_jahr(2027, profil())
    assert datum(termine, "ustva", "Dezember 2026") == "2027-01-11"  # 10.01.27 = Sonntag


def test_sondervorauszahlung_nur_mit_verlaengerung():
    ohne = fr.fristen_jahr(2026, profil())
    mit = fr.fristen_jahr(2026, profil(dauerfristverlaengerung=True))
    assert not [t for t in ohne if t["art"] == "sondervorauszahlung"]
    assert datum(mit, "sondervorauszahlung", "Sondervorauszahlung") == "2026-02-10"


def test_kleinunternehmerin_bekommt_keine_voranmeldung():
    termine = fr.fristen_jahr(2026, profil(ustva_rhythmus="keine"))
    assert not [t for t in termine if t["art"] == "ustva"]
    # Die Jahreserklärung bleibt trotzdem.
    assert [t for t in termine if t["art"] == "jahreserklaerung"]


# ————— Lohn und Sozialversicherung —————

def test_ohne_team_keine_lohntermine():
    termine = fr.fristen_jahr(2026, profil())
    assert not [t for t in termine if t["art"] in ("lohnsteuer", "sozialversicherung")]


def test_sozialversicherung_am_drittletzten_bankarbeitstag():
    termine = fr.fristen_jahr(2026, profil(lohn=True))
    # August 2026 endet am Montag, 31.08. Drittletzter Bankarbeitstag:
    # 31. (Mo), 28. (Fr), 27. (Do) → der 27.08.
    assert datum(termine, "sozialversicherung", "August 2026") == "2026-08-27"


def test_dezember_beitrag_zaehlt_silvester_nicht_mit():
    termine = fr.fristen_jahr(2026, profil(lohn=True))
    # Dezember 2026: 31.12. (Do) ist Bankfeiertag, 30. (Mi), 29. (Di), 28. (Mo).
    # 25./26.12. sind Feiertage → drittletzter Bankarbeitstag ist der 28.12.
    assert datum(termine, "sozialversicherung", "Dezember 2026") == "2026-12-28"


def test_beitragsnachweis_liegt_vor_dem_beitrag():
    termine = fr.fristen_jahr(2026, profil(lohn=True))
    sv = [t for t in termine if t["art"] == "sozialversicherung"]
    assert len(sv) == 12
    for t in sv:
        assert t["nachweis"] < t["datum"]


def test_lohnsteuer_vierteljaehrlich_ist_der_standard():
    termine = fr.fristen_jahr(2026, profil(lohn=True))
    lohn = [t for t in termine if t["art"] == "lohnsteuer"]
    assert len(lohn) == 4
    assert datum(termine, "lohnsteuer", "1. Quartal") == "2026-04-10"


def test_lohnsteuer_monatlich_ergibt_zwoelf():
    termine = fr.fristen_jahr(2026, profil(lohn=True, lohnsteuer_rhythmus="monatlich"))
    assert len([t for t in termine if t["art"] == "lohnsteuer"]) == 12


# ————— Jahreserklärung —————

def test_ohne_berater_ende_juli():
    termine = fr.fristen_jahr(2026, profil())
    # 31.07.2026 ist ein Freitag.
    assert datum(termine, "jahreserklaerung", "2025") == "2026-07-31"


def test_mit_berater_ende_februar_des_uebernaechsten_jahres():
    # Mit Vertretung ist 2026 die Erklärung für 2024 fällig, nicht die für 2025.
    termine = fr.fristen_jahr(2026, profil(steuerberater=True))
    # 28.02.2026 ist ein Samstag → Montag, der 02.03.
    assert datum(termine, "jahreserklaerung", "2024") == "2026-03-02"


def test_jahreserklaerung_fehlt_nie_im_kalender():
    # Egal ob mit oder ohne Vertretung: in jedem Jahr steht genau eine drin.
    for p in (profil(), profil(steuerberater=True)):
        termine = fr.fristen_jahr(2026, p)
        assert len([t for t in termine if t["art"] == "jahreserklaerung"]) == 1


# ————— Profil aus den Stammdaten —————

def test_kleinunternehmerin_bekommt_rhythmus_keine():
    p = fr.termin_profil({"kleinunternehmer": "Ja"})
    assert p["ustva_rhythmus"] == "keine"


def test_ohne_angabe_wird_vorsichtig_monatlich_angenommen():
    p = fr.termin_profil({})
    assert p["ustva_rhythmus"] == "monatlich"


def test_team_schaltet_die_lohntermine_frei():
    assert fr.termin_profil({}, hat_team=True)["lohn"] is True
    assert fr.termin_profil({}, hat_team=False)["lohn"] is False


# ————— Was als Nächstes ansteht —————

def test_naechste_zaehlt_die_verbleibenden_tage():
    termine = fr.fristen_jahr(2026, profil())
    offen = fr.naechste(termine, dt.date(2026, 3, 1), anzahl=2)
    assert len(offen) == 2
    assert offen[0]["datum"] == "2026-03-10"
    assert offen[0]["in_tagen"] == 9


def test_naechste_laesst_vergangenes_weg():
    termine = fr.fristen_jahr(2026, profil())
    offen = fr.naechste(termine, dt.date(2026, 12, 31), anzahl=5)
    assert all(t["datum"] >= "2026-12-31" for t in offen)


def test_termine_sind_aufsteigend_sortiert():
    termine = fr.fristen_jahr(2026, profil(lohn=True, dauerfristverlaengerung=True))
    daten = [t["datum"] for t in termine]
    assert daten == sorted(daten)
