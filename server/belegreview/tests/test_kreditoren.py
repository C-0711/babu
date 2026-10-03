"""Die Kreditorenliste eines Betriebs — die reine Regel (K1).

Plan Kanzleiansicht, Schritt K1 (03.10.2026). Größere Betriebe brauchen je
Lieferant eine eigene Kreditorennummer, kleine Studios bleiben beim
Sammelkonto. Die Nummern kommen aus dem DATEV der Kanzlei; für neue
Lieferanten vergibt babu die nächste freie. Eine vergebene Nummer ändert
sich nie.

Hier nur das Modul ohne Netz und ohne Box. Die Routen prüft
`test_kreditoren_routen.py`.
"""
import json
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import kreditoren as kr  # noqa: E402

AM = "2026-10-03T12:00:00+0200"


def _mit(*paare) -> dict:
    stand = kr.leer()
    for nummer, name in paare:
        stand, _ = kr.zusammenfuehren(stand, [{"nummer": nummer, "name": name}],
                                      "datev", "kanzlei@k.de", AM)
    return stand


# ————— Grundstand —————

def test_ohne_liste_bleibt_es_beim_sammelkonto():
    stand = kr.laden(None)
    assert stand["modus"] == "sammel"
    assert stand["sammelkonto"] == "70099"
    assert stand["kreditoren"] == []


def test_kaputte_datei_ist_ein_leerer_stand():
    assert kr.laden(b"{kein json")["kreditoren"] == []
    assert kr.laden(b"[1, 2]")["modus"] == "sammel"


def test_speichern_und_laden_ergibt_denselben_stand():
    stand = _mit(("70123", "Friseurbedarf Nord GmbH"))
    assert kr.laden(kr.als_bytes(stand)) == stand


# ————— Namen —————

@pytest.mark.parametrize("roh, norm", [
    ("Friseurbedarf Nord GmbH", "friseurbedarf nord"),
    ("FRISEURBEDARF NORD G.m.b.H.", "friseurbedarf nord"),
    ("Müller & Söhne KG", "mueller soehne"),
    ("Großhandel Weiß e.K.", "grosshandel weiss"),
    ("  Wella   Deutschland GmbH & Co. KG ", "wella deutschland"),
])
def test_namen_werden_vergleichbar(roh, norm):
    assert kr.norm_name(roh) == norm


def test_der_anfangsbuchstabe_kommt_vom_vergleichbaren_namen():
    assert kr.buchstabe("Öko Haarpflege") == "O"
    assert kr.buchstabe("3M Deutschland") == "#"
    assert kr.buchstabe("delilà GmbH") == "D"


# ————— Nummern —————

def test_kreditornummern_haben_fuenf_stellen_ab_sieben():
    assert kr.ist_kreditornummer("70123")
    assert kr.ist_kreditornummer("99999")
    assert not kr.ist_kreditornummer("10001")      # Debitor
    assert not kr.ist_kreditornummer("6815")       # Sachkonto
    assert not kr.ist_kreditornummer("700123")     # andere Sachkontenlänge
    assert not kr.ist_kreditornummer("7012a")


def test_die_erste_nummer_ist_70001():
    assert kr.naechste_nummer(kr.leer()) == "70001"


def test_die_naechste_nummer_folgt_der_hoechsten():
    assert kr.naechste_nummer(_mit(("70001", "A"), ("70250", "B"))) == "70251"


def test_das_sammelkonto_wird_nie_vergeben():
    assert kr.naechste_nummer(_mit(("70098", "A"))) == "70100"


def test_anlegen_vergibt_die_naechste_nummer():
    stand, k = kr.anlegen(_mit(("70010", "Alt")), "Friseurbedarf Nord",
                          "kanzlei@k.de", AM)
    assert k["nummer"] == "70011"
    assert k["quelle"] == "babu"
    assert k["an_datev_am"] is None
    assert [x["nummer"] for x in stand["kreditoren"]] == ["70010", "70011"]


def test_anlegen_lehnt_einen_doppelten_lieferanten_ab():
    with pytest.raises(kr.KreditorFehler, match="70010"):
        kr.anlegen(_mit(("70010", "Friseurbedarf Nord GmbH")),
                   "friseurbedarf nord", "kanzlei@k.de", AM)


def test_anlegen_braucht_einen_namen_den_datev_nimmt():
    with pytest.raises(kr.KreditorFehler):
        kr.anlegen(kr.leer(), "   ", "k", AM)
    with pytest.raises(kr.KreditorFehler, match="50"):
        kr.anlegen(kr.leer(), "x" * 51, "k", AM)


def test_aendern_laesst_die_nummer_stehen():
    stand, k = kr.aendern(_mit(("70010", "Alt GmbH")), "70010",
                          {"name": "Neu GmbH", "nummer": "79999", "aktiv": False},
                          "kanzlei@k.de", AM)
    assert k["nummer"] == "70010"
    assert k["name"] == "Neu GmbH"
    assert k["aktiv"] is False
    assert "Alt GmbH" in k["aliase"]


def test_aendern_einer_unbekannten_nummer():
    with pytest.raises(kr.KreditorFehler):
        kr.aendern(kr.leer(), "70010", {"name": "X"}, "k", AM)


def test_iban_wird_ohne_leerzeichen_gefuehrt():
    _, k = kr.anlegen(kr.leer(), "Wella", "k", AM, iban="de89 3704 0044 0532 0130 00")
    assert k["iban"] == ["DE89370400440532013000"]


# ————— Einstellung —————

def test_einzeln_einschalten_und_sammelkonto_setzen():
    stand = kr.einstellen(kr.leer(), modus="einzeln", sammelkonto="70000")
    assert stand["modus"] == "einzeln"
    assert stand["sammelkonto"] == "70000"


def test_einstellung_prueft_ihre_werte():
    with pytest.raises(kr.KreditorFehler):
        kr.einstellen(kr.leer(), modus="alle")
    with pytest.raises(kr.KreditorFehler):
        kr.einstellen(kr.leer(), sammelkonto="1600")


# ————— Liste: Suche, Buchstabe, Seiten —————

def test_liste_ist_alphabetisch_nach_dem_vergleichbaren_namen():
    stand = _mit(("70003", "Zebra Haar"), ("70001", "Öko Pflege"), ("70002", "alpha AG"))
    namen = [k["name"] for k in kr.liste(stand)["eintraege"]]
    assert namen == ["alpha AG", "Öko Pflege", "Zebra Haar"]


def test_liste_filtert_nach_anfangsbuchstabe():
    stand = _mit(("70001", "Wella"), ("70002", "Welle Bau"), ("70003", "Kao"))
    l = kr.liste(stand, buchstabe="W")
    assert [k["nummer"] for k in l["eintraege"]] == ["70001", "70002"]
    assert l["buchstaben"] == {"K": 1, "W": 2}


def test_liste_sucht_in_name_alias_und_nummer():
    stand = _mit(("70001", "Wella Deutschland GmbH"), ("70002", "Kao"))
    stand, _ = kr.aendern(stand, "70002", {"aliase": ["Goldwell"]}, "k", AM)
    assert [k["nummer"] for k in kr.liste(stand, q="wella")["eintraege"]] == ["70001"]
    assert [k["nummer"] for k in kr.liste(stand, q="goldwell")["eintraege"]] == ["70002"]
    # Auch die Suche nach Nummern bleibt alphabetisch: Kao vor Wella.
    assert [k["nummer"] for k in kr.liste(stand, q="7000")["eintraege"]] == ["70002", "70001"]


def test_liste_teilt_in_seiten():
    stand = _mit(*[(str(70101 + i), f"Lieferant {i:03d}") for i in range(120)])
    l = kr.liste(stand, seite=3, pro_seite=50)
    assert l["gesamt"] == 120 and l["seiten"] == 3
    assert len(l["eintraege"]) == 20


# ————— Datei lesen —————

def _datev16(zeilen, laenge="4", kategorie="16"):
    kopf = ['"EXTF"', "700", kategorie, '"Debitoren/Kreditoren"', "5",
            "20261003120000000", "", '"RE"', '"Kanzlei"', "", "16149", "19364",
            "20260101", laenge, "", "", '""', '""']
    spalten = ['"Konto"', '"Name (Adressattyp Unternehmen)"', '"Unternehmensgegenstand"',
               '"Name (Adressattyp natürl. Person)"', '"Vorname (Adressattyp natürl. Person)"',
               '"Name (Adressattyp keine Angabe)"', '"Adressattyp"', '"Kurzbezeichnung"',
               '"IBAN-Nr. 1"']
    text = "\r\n".join([";".join(kopf), ";".join(spalten), *zeilen]) + "\r\n"
    return text.encode("cp1252")


def test_datev_debitoren_kreditoren_wird_gelesen():
    roh = _datev16([
        '70001;"Friseurbedarf Nord GmbH";;;;;"2";"FBN";"DE89370400440532013000"',
        '70002;;;"Meier";"Anna";;"1";;""',
        '10001;"Kundin Debitor";;;;;"2";;""',
    ])
    d = kr.datei_lesen(roh)
    assert d["art"] == "datev"
    assert d["eintraege"] == [
        {"nummer": "70001", "name": "Friseurbedarf Nord GmbH",
         "iban": ["DE89370400440532013000"]},
        {"nummer": "70002", "name": "Anna Meier", "iban": []},
    ]
    assert d["uebersprungen"] == 1


def test_eine_andere_datev_datei_wird_abgelehnt():
    with pytest.raises(kr.KreditorFehler, match="Buchungsstapel"):
        kr.datei_lesen(_datev16([], kategorie="21").replace(
            b"Debitoren/Kreditoren", b"Buchungsstapel"))


def test_eine_andere_sachkontenlaenge_wird_abgelehnt():
    with pytest.raises(kr.KreditorFehler, match="Sachkontenlänge"):
        kr.datei_lesen(_datev16(['700001;"X";;;;;"2";;""'], laenge="5"))


def test_eine_einfache_liste_wird_gelesen():
    roh = "Kontonummer;Name;IBAN\n70005;Wella Deutschland;\n70006;Kao GmbH;DE02120300000000202051\n"
    d = kr.datei_lesen(roh.encode("utf-8"))
    assert d["art"] == "csv"
    assert [e["nummer"] for e in d["eintraege"]] == ["70005", "70006"]
    assert d["eintraege"][1]["iban"] == ["DE02120300000000202051"]


def test_eine_liste_mit_komma_und_utf8_bom():
    roh = "﻿Konto,Bezeichnung\n70007,Löwen Haar\n".encode("utf-8")
    assert kr.datei_lesen(roh)["eintraege"][0]["name"] == "Löwen Haar"


def test_eine_liste_ohne_nummernspalte_sagt_es():
    with pytest.raises(kr.KreditorFehler, match="Kontonummer"):
        kr.datei_lesen(b"Name;Ort\nWella;Darmstadt\n")


# ————— Vorschau und Zusammenführen —————

def test_vorschau_zeigt_neu_geaendert_gleich_und_doppelt():
    stand = _mit(("70001", "Wella"), ("70002", "Kao"))
    v = kr.vorschau(stand, [
        {"nummer": "70001", "name": "Wella"},                 # gleich
        {"nummer": "70002", "name": "Kao Germany GmbH"},      # geändert
        {"nummer": "70003", "name": "Goldwell"},              # neu
        {"nummer": "70004", "name": "WELLA GmbH"},            # neu, aber doppelt
    ], "datev")
    assert v["gleich"] == 1
    assert [g["nummer"] for g in v["geaendert"]] == ["70002"]
    assert [n["nummer"] for n in v["neu"]] == ["70003", "70004"]
    assert v["doppelt"] == [{"nummer": "70004", "name": "WELLA GmbH",
                             "schon": "70001"}]


def test_datev_gewinnt_beim_namen_und_merkt_den_alten():
    stand, _ = kr.anlegen(kr.leer(), "Wella", "k", AM)
    stand, z = kr.zusammenfuehren(stand, [{"nummer": "70001",
                                           "name": "Wella Deutschland GmbH"}],
                                  "datev", "k", AM)
    k = stand["kreditoren"][0]
    assert (k["name"], k["quelle"]) == ("Wella Deutschland GmbH", "datev")
    assert k["aliase"] == ["Wella"]
    assert k["an_datev_am"] == AM
    assert z == {"neu": 0, "geaendert": 1}


def test_die_historie_aendert_nichts_was_schon_da_ist():
    stand = _mit(("70001", "Wella Deutschland GmbH"))
    stand, z = kr.zusammenfuehren(stand, [{"nummer": "70001", "name": "Wella 03/26"},
                                          {"nummer": "70002", "name": "Kao"}],
                                  "historie", "k", AM)
    assert stand["kreditoren"][0]["name"] == "Wella Deutschland GmbH"
    assert stand["kreditoren"][1]["quelle"] == "historie"
    assert z == {"neu": 1, "geaendert": 0}


def test_als_bytes_ist_lesbares_json():
    d = json.loads(kr.als_bytes(_mit(("70001", "Löwen"))))
    assert d["kreditoren"][0]["name"] == "Löwen"


# ————— Aus den alten Buchungsstapeln der Kanzlei —————

def _alter_stapel(buchungen) -> bytes:
    """Ein Kanzlei-Stapel (Kategorie 21) mit Konto, Gegenkonto und Text."""
    import extf  # noqa: PLC0415
    kopf = ['"EXTF"', "700", "21", '"Buchungsstapel"', "12", "20260110120000000",
            "", '"RE"', '"Kanzlei"', "", "16149", "19364", "20260101", "4",
            "20260101", "20260131", '"Januar"']
    zeilen = []
    for konto, gegen, text in buchungen:
        f = [""] * len(extf.SPALTEN)
        f[0], f[1], f[6], f[7], f[9], f[13] = "10,00", "S", konto, gegen, "0501", f'"{text}"'
        zeilen.append(";".join(f))
    spalten = ";".join(f'"{n}"' for n in extf.SPALTEN)
    return ("\r\n".join([";".join(kopf), spalten, *zeilen]) + "\r\n").encode("cp1252")


def test_die_alten_stapel_nennen_die_kreditoren():
    import historie  # noqa: PLC0415
    stapel = _alter_stapel([
        ("6815", "70001", "Friseurbedarf Nord RE 4711"),
        ("6815", "70001", "Friseurbedarf Nord 4712"),
        ("70001", "1800", "Friseurbedarf Nord"),          # Zahlung: Kreditor im Konto
        ("6815", "10001", "Kundin"),                      # Debitor — nicht gefragt
        *[("6815", "70099", f"Lieferant {n}") for n in "ABCDEF"],
    ])
    konten = historie.personenkonten([stapel, b"kein stapel"])
    assert [k["nummer"] for k in konten] == ["70001", "70099"]
    nord, sammel = konten
    assert nord["name"] == "Friseurbedarf Nord"
    assert nord["buchungen"] == 3
    assert nord["sammel"] is False
    assert sammel["sammel"] is True       # sechs verschiedene Namen auf einem Konto


@pytest.mark.parametrize("text, name", [
    ("3M Deutschland 03/25", "3M Deutschland"),
    ("Wella RE4711 vom 12.03.", "Wella vom"),
    ("Friseurbedarf Nord Nr.4711", "Friseurbedarf Nord"),
    ("R-A687-2026-00071 Weingärtle", "Weingärtle"),
])
def test_rechnungsnummern_fallen_aus_dem_namen_marken_nicht(text, name):
    import historie  # noqa: PLC0415
    assert historie._name_aus_text(text) == name


def test_datev_gewinnt_auch_bei_gleichem_vergleichsnamen():
    """„Friseurbedarf Nord“ aus den alten Buchungen, „Friseurbedarf Nord GmbH“
    aus DATEV: die Schreibweise der Kanzlei gilt."""
    stand = kr.zusammenfuehren(kr.leer(), [{"nummer": "70001", "name": "Friseurbedarf Nord"}],
                               "historie", "k", AM)[0]
    neu = [{"nummer": "70001", "name": "Friseurbedarf Nord GmbH", "iban": []}]
    v = kr.vorschau(stand, neu, "datev")
    assert v["geaendert"] == [{"nummer": "70001", "alt": "Friseurbedarf Nord",
                               "neu": "Friseurbedarf Nord GmbH", "iban_neu": []}]
    stand, z = kr.zusammenfuehren(stand, neu, "datev", "k", AM)
    assert stand["kreditoren"][0]["name"] == "Friseurbedarf Nord GmbH"
    assert stand["kreditoren"][0]["aliase"] == []     # derselbe Name, kein Nebenname
    assert z["geaendert"] == 1


def test_eine_neue_iban_ist_eine_aenderung_aber_kein_neuer_name():
    stand = _mit(("70001", "Wella"))
    v = kr.vorschau(stand, [{"nummer": "70001", "name": "Wella",
                             "iban": ["DE89370400440532013000"]}], "datev")
    assert v["geaendert"] == [{"nummer": "70001", "alt": "Wella", "neu": "Wella",
                               "iban_neu": ["DE89370400440532013000"]}]


# ————— K2: welcher Kreditor gehört zu einem Beleg? —————

def _einzeln(*paare) -> dict:
    return kr.einstellen(_mit(*paare), modus="einzeln")


def test_im_sammelmodus_gibt_es_keinen_kreditor():
    stand = _mit(("70001", "Wella"))
    assert kr.aufloesen(stand, "Wella", {"nummer": "70001"}) is None


def test_eine_ausdrueckliche_zuordnung_gilt():
    k = kr.aufloesen(_einzeln(("70001", "Wella")), "irgendwer", {"nummer": "70001"})
    assert k == {"nummer": "70001", "name": "Wella", "quelle": "zuordnung"}


def test_ausdruecklich_sammelkonto_ist_eine_antwort():
    """„Kein eigener Kreditor“ ist eine Entscheidung — kein offener Beleg."""
    k = kr.aufloesen(_einzeln(("70001", "Wella")), "Wella", {"nummer": None})
    assert k == {"nummer": None, "name": None, "quelle": "zuordnung"}


def test_der_lieferantenname_findet_seinen_kreditor():
    stand, _ = kr.aendern(_einzeln(("70001", "Wella Deutschland GmbH")), "70001",
                          {"aliase": ["Wella Kosmetik"]}, "k", AM)
    assert kr.aufloesen(stand, "WELLA DEUTSCHLAND", None)["nummer"] == "70001"
    assert kr.aufloesen(stand, "Wella Kosmetik GmbH", None)["quelle"] == "name"
    assert kr.aufloesen(stand, "Wella", None) is None          # nur genau
    assert kr.aufloesen(stand, "", None) is None


def test_ein_uebergebener_beleg_bekommt_keinen_neuen_kreditor_ueber_den_namen():
    stand = _einzeln(("70001", "Wella"))
    assert kr.aufloesen(stand, "Wella", None, exportiert=True) is None


def test_ein_nicht_mehr_verwendeter_kreditor_wird_nicht_gefunden():
    stand, _ = kr.aendern(_einzeln(("70001", "Wella")), "70001", {"aktiv": False},
                          "k", AM)
    assert kr.aufloesen(stand, "Wella", None) is None


def test_vorschlaege_nach_aehnlichkeit():
    stand = _einzeln(("70001", "Friseurbedarf Nord GmbH"), ("70002", "Friseurbedarf Süd"),
                     ("70003", "Wella"))
    v = kr.vorschlaege(stand, "Friseurbedarf Nord Hamburg")
    assert [x["nummer"] for x in v][:2] == ["70001", "70002"]
    assert "70003" not in [x["nummer"] for x in v]


def test_merken_legt_den_lieferanten_als_nebennamen_ab():
    stand = kr.merken(_einzeln(("70001", "Wella")), "70001", "Wella Deutschland GmbH")
    assert stand["kreditoren"][0]["aliase"] == ["Wella Deutschland GmbH"]
    # Schon derselbe Name: nichts zu merken.
    assert kr.merken(stand, "70001", "WELLA") == stand


def test_merken_lehnt_einen_fremden_namen_ab():
    stand = _einzeln(("70001", "Wella"), ("70002", "Kao"))
    with pytest.raises(kr.KreditorFehler, match="70002"):
        kr.merken(stand, "70001", "Kao GmbH")


# ————— K2: das Gegenkonto im Stapel —————

def test_das_uebergebene_gegenkonto_bleibt():
    import extf  # noqa: PLC0415
    r = {"felder": {"zahlungsart": "karte"}, "einschaetzung": {"konto": "6815"},
         "kreditor": {"nummer": "70002"}, "gegenkonto_fest": "70001"}
    assert extf.gegenkonto(r) == "70001"


def test_der_kreditor_aus_dem_index_ersetzt_das_sammelkonto():
    import extf  # noqa: PLC0415
    r = {"felder": {"zahlungsart": "karte"}, "einschaetzung": {"konto": "6815"},
         "kreditor": {"nummer": "70002"}, "sammelkonto": "70000"}
    assert extf.gegenkonto(r) == "70002"
    del r["kreditor"]
    assert extf.gegenkonto(r) == "70000"
