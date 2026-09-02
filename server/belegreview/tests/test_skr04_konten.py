"""Jedes Konto, das babu vergibt, muss im SKR04 2026 stehen.

DATEV bereinigt die Kontenrahmen zwischen 2024 und 2027 (Dok.-Nr. 1029365:
Konten werden reserviert und gelöscht). Ein Konto, das es nicht mehr gibt,
fällt erst beim Import in der Kanzlei auf — hier fällt es vorher auf.
skr04_konten.py ist aus dem Kontenrahmen-PDF erzeugt; wenn DATEV ein neues
Jahr veröffentlicht, wird die Datei neu erzeugt und dieser Test sagt, ob
babu ein gestrichenes Konto benutzt.
"""
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import extf  # noqa: E402
import historie as hi  # noqa: E402
import kontierung as kt  # noqa: E402
import monatsabschluss as ma  # noqa: E402
import skr04_automatik  # noqa: E402
import skr04_konten  # noqa: E402
import vordrucke  # noqa: E402


def _babu_konten() -> dict[str, str]:
    aus = {}
    for code, k in kt.KATEGORIEN.items():
        if k.skr04:
            aus[str(k.skr04)] = f"kontierung:{code}"
    for name, (nr, _) in vordrucke.SUSA_KONTEN.items():
        aus[nr] = f"susa:{name}"
    for nr in (extf.KASSE, extf.GELDTRANSIT, extf.ERLOES_STEUERFREI,
               extf.ERLOES_KLEINUNTERNEHMER, *extf.ERLOESKONTO.values(),
               *[z for z in extf.GESCHWISTER.values()]):
        aus[nr] = "extf"
    for nr in ma.NEUTRALE_KONTEN:
        aus[str(nr)] = "neutral"
    return aus


def test_jedes_konto_das_babu_vergibt_steht_im_skr04_2026():
    fehlt = {nr: wo for nr, wo in _babu_konten().items()
             if nr not in skr04_konten.KONTEN}
    assert not fehlt, f"nicht im SKR04 2026: {fehlt}"


def test_die_liste_ist_der_ganze_kontenrahmen_nicht_ein_auszug():
    assert len(skr04_konten.KONTEN) > 1200
    assert skr04_konten.name("4400") == "Erlöse 19 % USt"
    assert skr04_konten.name("5400") == "Wareneingang 19 % Vorsteuer"
    assert skr04_konten.name("1600") == "Kasse"
    assert skr04_konten.name("4184").startswith("Steuerfreie Erlöse Kleinunternehmer")
    assert skr04_konten.name("9999") is None and skr04_konten.name(None) is None


def test_automatikkonten_sind_eine_teilmenge_der_konten():
    """Zwei Dateien aus demselben PDF — sie dürfen sich nicht widersprechen."""
    fehlt = [k for k in skr04_automatik.AUTOMATIK if k not in skr04_konten.KONTEN]
    assert not fehlt, fehlt


def test_die_saldenliste_nennt_auch_fremde_konten_beim_namen():
    """Eine Handkorrektur auf ein Konto, das babu nicht vergibt, stand in
    der SuSa bisher als „—“."""
    beleg = {"stamm": "x", "brutto": 119.0, "netto": 100.0, "ust": 19.0,
             "konto_skr04": "6300", "status": "geprüft", "summenprobe_ok": True}
    erloese = ma.erloese_monat([])
    s = vordrucke.susa("2026-08", erloese, [beleg])
    zeile = next(z for z in s["zeilen"] if z["konto"] == "6300")
    assert zeile["name"] == skr04_konten.name("6300")
    assert zeile["name"] != "—"


def test_die_historie_traegt_kontonamen():
    from test_historie import stapel, zeile
    d = hi.stapel_lesen(stapel(zeile("1190,00", "H", "4400", "1600", "1503")))
    k = d["monate"]["2025-03"]["konten"][0]
    assert (k["konto"], k["name"]) == ("4400", "Erlöse 19 % USt")
