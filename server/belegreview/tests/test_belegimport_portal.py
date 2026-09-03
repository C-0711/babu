"""Der Massenimport im Portal: ein Ordner Belege je Mandant.

Die Serverseite steht in `belegimport.py` und ist mit
`test_belegimport_lauf.py` abgedeckt. Hier geht es um das andere Ende: das
Portal ist eine einzige HTML-Datei ohne Baukasten, falsche Verdrahtung
fällt dort still aus — ein Knopf, der nichts tut, ist kein Fehler, nur ein
Knopf. Geprüft wird deshalb an der Datei, dieselbe Art Prüfung wie in
`test_portal_verdrahtung.py` und `test_hochladen_fortschritt.py`.

Vier Dinge, die beim Bauen fast schiefgegangen wären und die deshalb hier
festgehalten sind:

* Der Weg geht durch `hochladenMitBalken`, nicht durch `hochladen()`.
  `hochladen()` ist der Weg für den eigenen Schreibtisch und weist Fotos
  ausdrücklich ab — beim Massenimport sind Fotos aber der Normalfall.
* Die Balken landen in `#md-import-liste`, nicht in `#belege-liste`. Sonst
  schriebe die Kanzlei ihren Import in die Belegliste des eigenen Betriebs.
* Der Block hängt an `kann` (Belegbox da und Mandat aktiv). Ohne Box
  antwortete jede Datei mit 409, und niemand wüsste warum.
* Der Wortlaut je Beleg kommt aus `statusSatz`/`statusMarke`. Ein Beleg
  heißt nicht anders, nur weil er über den Massenweg hereinkam.
"""
import re
from pathlib import Path

PORTAL = (Path(__file__).resolve().parent.parent / "portal.html").read_text()


def _rumpf(name: str) -> str:
    """Der Körper einer Funktion, über die geschweiften Klammern gezählt."""
    start = PORTAL.index(f"function {name}(")
    auf = PORTAL.index("{", start)
    tiefe, i = 0, auf
    while i < len(PORTAL):
        if PORTAL[i] == "{":
            tiefe += 1
        elif PORTAL[i] == "}":
            tiefe -= 1
            if tiefe == 0:
                return PORTAL[auf:i + 1]
        i += 1
    raise AssertionError(f"{name} hört nie auf")


# ————— Die Auswahl —————

def test_beide_wege_in_die_auswahl_gibt_es():
    """Einzelne Dateien und ein ganzer Ordner — je ein Knopf."""
    assert "function mdImportWaehlen(" in PORTAL
    assert "mdImportWaehlen(${m.id},false)" in PORTAL, "kein Weg für Dateien"
    assert "mdImportWaehlen(${m.id},true)" in PORTAL, "kein Weg für einen Ordner"


def test_der_ordner_weg_kann_wirklich_ordner():
    """Ohne `webkitdirectory` öffnet sich derselbe Dateidialog wie daneben."""
    assert re.search(r'id="md-import-ordner"[^>]*webkitdirectory', PORTAL, re.S), \
        "der Ordner-Knopf wählt gar keinen Ordner"
    assert re.search(r'id="md-import-dateien"[^>]*\bmultiple', PORTAL, re.S), \
        "die Dateiauswahl nimmt nur eine Datei"


def test_die_auswahl_nimmt_nur_belege_an():
    """Fotos und PDF — kein Tabellenblatt, keine Buchungsdatei."""
    for feld in ("md-import-dateien", "md-import-ordner"):
        m = re.search(rf'id="{feld}"[^>]*accept="([^"]*)"', PORTAL, re.S)
        assert m, f"{feld} sagt nicht, was es annimmt"
        for endung in (".jpg", ".png", ".pdf", ".heic"):
            assert endung in m.group(1), f"{feld} nimmt kein {endung}"
    assert "MD_IMPORT_ENDUNGEN" in PORTAL, "nichts sortiert den Ordner-Unrat aus"


# ————— Der Sendeweg —————

def test_der_import_geht_durch_den_balken_und_an_seine_tuer():
    """Ein Balken je Datei, und er zeigt auf `…/import/dateien`."""
    rumpf = _rumpf("mdImportAblegen")
    assert "hochladenMitBalken(" in rumpf, "kein Balken je Datei"
    assert "/import/dateien?name=" in rumpf, "der Balken zeigt auf die falsche Tür"
    assert "encodeURIComponent(datei.name)" in rumpf, "Dateiname ungeschützt in der Adresse"


def test_der_import_geht_nicht_durch_den_schreibtisch_weg():
    """`hochladen()` weist Fotos ab — beim Massenimport sind sie der Normalfall."""
    rumpf = _rumpf("mdImportAblegen")
    assert not re.search(r"(?<![\w])hochladen\(", rumpf), \
        "der Massenimport benutzt den Schreibtisch-Weg"


def test_die_balken_landen_in_der_import_liste():
    rumpf = _rumpf("mdImportAblegen")
    assert '$("#md-import-liste")' in rumpf or "md-import-liste" in rumpf
    assert "#belege-liste" not in rumpf, \
        "der Import schreibt in die Belegliste des eigenen Betriebs"


def test_nach_dem_ablegen_wird_gestartet_und_zugeschaut():
    rumpf = _rumpf("mdImportAblegen")
    assert "/import/start" in rumpf, "nichts startet den Lauf"
    assert "mdImportZuschauen(" in rumpf, "niemand schaut dem Lauf zu"


# ————— Zusehen —————

def test_es_gibt_einen_takt_und_er_hoert_auch_wieder_auf():
    assert "function mdImportPoll(" in PORTAL, "niemand fragt nach dem Stand"
    assert "function mdImportStop(" in PORTAL
    zuschauen = _rumpf("mdImportZuschauen")
    assert "setInterval" in zuschauen and "_mdImportTimer" in zuschauen
    poll = _rumpf("mdImportPoll")
    for ende in ("fertig", "abgebrochen", "fehler", "unterbrochen"):
        assert f'"{ende}"' in poll, f"der Takt laeuft ueber den Stand {ende} hinaus weiter"
    assert "mdMonate(" in poll, "nach dem Lauf werden die Monate nicht frisch"


def test_wer_die_karte_verlaesst_hoert_auf_zu_fragen():
    """Sonst fragt das Portal im Sekundentakt weiter, während niemand hinsieht."""
    assert "mdImportStop()" in _rumpf("routen"), "der Router hält den Takt nicht an"
    assert "mdImportStop()" in _rumpf("mdReiter"), "der Reiterwechsel lässt ihn laufen"
    assert "mdImportStop()" in _rumpf("mdZeigen"), \
        "ein anderer Mandant erbt den Takt des vorigen"


def test_der_wiedereinstieg_nach_dem_neuladen():
    """Beim Öffnen der Karte einmal nachsehen — sonst ist der Lauf weg."""
    rumpf = _rumpf("mdImportWiedereinstieg")
    assert "/import" in rumpf
    assert "beendet_um" in rumpf, "ein gerade beendeter Lauf verschwindet spurlos"
    assert "mdImportZuschauen(" in rumpf


def test_der_zaehler_zaehlt_in_worten():
    rumpf = _rumpf("mdImportStandZeigen")
    for wort in ("angesehen", "geprüft", "mit Frage", "nicht lesbar", "waren schon da"):
        assert wort in rumpf, f"das Wort {wort} fehlt im Zähler"
    assert "md-import-zaehler" in rumpf


def test_die_liste_wird_nicht_bei_jedem_takt_neu_gebaut():
    """Muster wie `scBlaetter`: nur anfassen, wo sich etwas geändert hat."""
    rumpf = _rumpf("mdImportZeilen")
    assert "dataset.schluessel" in rumpf, "kein Schlüssel je Zeile"
    assert "dataset.stand" in rumpf, "die Liste zuckt im Sekundentakt"


def test_der_wortlaut_kommt_aus_der_belegliste():
    """Ein Beleg heißt nicht anders, nur weil er über den Massenweg kam."""
    rumpf = _rumpf("mdImportWortlaut")
    assert "statusSatz(" in rumpf, "eigener Wortlaut statt des gemeinsamen"
    assert "statusMarke(" in rumpf
    for stand in ("gebucht", "rueckfrage", "unlesbar", "doppelt", "uebersprungen"):
        assert f'"{stand}"' in rumpf, f"der Ausgang {stand} hat keinen Satz"
    assert "mandantOeffnen(" in rumpf, "eine Rückfrage lässt sich nicht ansehen"


def test_dateinamen_von_fremder_platte_werden_als_text_gesetzt():
    """Ein Dateiname ist Text, kein Bauplan."""
    rumpf = _rumpf("mdImportZeilen")
    assert ".upname\").textContent" in rumpf, "der Dateiname geht als Auszeichnung hinein"


# ————— Anhalten und weitermachen —————

def test_anhalten_ist_verdrahtet():
    assert "function mdImportAbbrechen(" in PORTAL
    rumpf = _rumpf("mdImportAbbrechen")
    assert "/import/abbrechen" in rumpf
    assert "wird angehalten" in rumpf, "der Knopf sagt nicht, dass er gedrückt wurde"
    assert 'onclick="mdImportAbbrechen(${m.id})"' in PORTAL, "kein Knopf dafür"


def test_der_anhalten_knopf_zeigt_sich_nur_waehrend_es_laeuft():
    assert 'id="md-import-anhalten" hidden' in PORTAL, "der Knopf steht immer da"
    rumpf = _rumpf("mdImportStandZeigen")
    assert "md-import-anhalten" in rumpf and "hidden = !laeuft" in rumpf


def test_weitermachen_ist_verdrahtet():
    assert "function mdImportFortsetzen(" in PORTAL
    rumpf = _rumpf("mdImportFortsetzen")
    assert "/import/fortsetzen" in rumpf
    assert "nur=unlesbar" in rumpf
    schluss = _rumpf("mdImportStandZeigen")
    assert "Unlesbare nochmal versuchen" in schluss, \
        "unlesbare Belege bleiben unlesbar"
    assert "Weitermachen" in schluss, "ein unterbrochener Lauf hat keinen Weg zurück"


# ————— Wo der Block steht —————

def test_der_block_steht_nur_wo_es_eine_belegbox_gibt():
    """Ohne Box antwortete jede Datei mit 409 — und niemand wüsste warum."""
    assert re.search(r"if \(kann\)\{\s*html \+= `<div[^`]*"
                     r"Belege für diesen Betrieb ablegen", PORTAL, re.S), \
        "der Import-Block hängt nicht an `kann`"
    assert "if (kann) mdImportWiedereinstieg(m.id);" in PORTAL


def test_der_block_erklaert_sich_ohne_technik():
    """Sprachregel: was passiert, nicht womit."""
    for satz in ("Einen ganzen Ordner", "Wir sehen uns jeden Beleg an",
                 "eine halbe Minute je Beleg", "etwas langsamer"):
        assert satz in PORTAL, f"dieser Satz fehlt: {satz}"


def test_die_teile_des_blocks_gibt_es():
    for teil in ("md-import-zaehler", "md-import-liste", "md-import-monat",
                 "md-import-notiz", "md-import-schluss"):
        assert f'id="{teil}"' in PORTAL, f"{teil} fehlt"
