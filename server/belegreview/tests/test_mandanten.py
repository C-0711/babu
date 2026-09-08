"""Kanzlei, Mandant, Mitgliedschaft — die Tabellen hinter dem Pro-Zugang.

Geprüft wird gegen eine echte SQLite-Datei, nicht gegen Attrappen: das
Schema entsteht in `_db()` und muss dort auch anlegbar sein. Die drei
Dinge, an denen später die Mandantentrennung hängt, sind einzeln belegt —
der Anfangsstatus, die UNIQUE-Grenze und die Mitgliedschaftsfrage.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import babu_web  # noqa: E402
import box as bx  # noqa: E402
import mandanten  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    """Eine Portal-Datenbank mit `nutzer` und den drei neuen Tabellen."""
    c = sqlite3.connect(tmp_path / "portal.db")
    c.execute("""CREATE TABLE nutzer (email TEXT PRIMARY KEY, name TEXT,
                 rolle TEXT NOT NULL DEFAULT 'salon')""")
    for mail in ("kanzlei@0711.io", "sachbearbeiter@0711.io",
                 "nina@0711.io", "salon-b@0711.io"):
        c.execute("INSERT INTO nutzer (email, name) VALUES (?, ?)", (mail, mail))
    mandanten.schema(c)
    yield c
    c.close()


def test_das_schema_laesst_sich_zweimal_anlegen(db):
    """`_db()` ruft es bei JEDEM Verbindungsaufbau — es muss idempotent sein."""
    mandanten.schema(db)
    mandanten.schema(db)


def test_ein_neuer_mandant_wartet_auf_seine_box(db):
    kid = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=db)
    mid = mandanten.mandant_anlegen(kid, "Salon Nina", "nina@0711.io", c=db)

    m = mandanten.mandant_holen(mid, c=db)
    assert m["status"] == "box_ausstehend"
    assert m["box_ref"] is None
    assert m["kanzlei_id"] == kid
    assert m["besitzer_un"] == "nina@0711.io"


def test_die_box_zu_verknuepfen_macht_den_mandanten_aktiv(db):
    kid = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=db)
    mid = mandanten.mandant_anlegen(kid, "Salon Nina", "nina@0711.io", c=db)

    mandanten.box_verknuepfen(mid, "inspektor/ws-nina.de/babu", c=db)
    m = mandanten.mandant_holen(mid, c=db)
    assert m["status"] == "aktiv"
    assert m["box_ref"] == "inspektor/ws-nina.de/babu"


def test_stammdaten_des_mandanten_stehen_am_mandanten(db):
    """Kontenrahmen und DATEV-Nummern gehören zum Betrieb, nicht in die
    Umgebung des Servers — sonst hätten alle Mandanten dieselben."""
    kid = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=db)
    mid = mandanten.mandant_anlegen(kid, "Salon Nina", "nina@0711.io",
                                    kontenrahmen="SKR03", berater_nr="12345",
                                    mandant_nr="4711", c=db)
    m = mandanten.mandant_holen(mid, c=db)
    assert (m["kontenrahmen"], m["berater_nr"], m["mandant_nr"]) == \
        ("SKR03", "12345", "4711")


def test_ein_salon_haengt_nur_einmal_an_derselben_kanzlei(db):
    kid = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=db)
    mandanten.mandant_anlegen(kid, "Salon Nina", "nina@0711.io", c=db)
    with pytest.raises(sqlite3.IntegrityError):
        mandanten.mandant_anlegen(kid, "Salon Nina nochmal", "nina@0711.io", c=db)


def test_ein_erfundener_status_kommt_nicht_durch(db):
    kid = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=db)
    mid = mandanten.mandant_anlegen(kid, "Salon Nina", "nina@0711.io", c=db)
    with pytest.raises(ValueError):
        mandanten.status_setzen(mid, "irgendwas", c=db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE mandant SET status = 'erfunden' WHERE id = ?", (mid,))


def test_wer_die_kanzlei_anlegt_ist_ihr_erstes_mitglied(db):
    kid = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=db)
    mid = mandanten.mandant_anlegen(kid, "Salon Nina", "nina@0711.io", c=db)
    assert mandanten.kanzlei_mitglied("kanzlei@0711.io", mid, c=db) is True


def test_eine_fremde_kanzlei_sieht_den_mandanten_nicht(db):
    """Die Lücke, die Phase 3 schließt: nicht „ist das eine Kanzlei-Rolle",
    sondern „betreut DIESE Kanzlei DIESEN Mandanten"."""
    eine = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=db)
    andere = mandanten.kanzlei_anlegen("Kanzlei Nord", "sachbearbeiter@0711.io",
                                       c=db)
    meiner = mandanten.mandant_anlegen(eine, "Salon Nina", "nina@0711.io", c=db)
    mandanten.mandant_anlegen(andere, "Salon B", "salon-b@0711.io", c=db)

    assert mandanten.kanzlei_mitglied("kanzlei@0711.io", meiner, c=db) is True
    assert mandanten.kanzlei_mitglied("sachbearbeiter@0711.io", meiner, c=db) is False


def test_ein_sachbearbeiter_darf_nach_dem_eintragen(db):
    kid = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=db)
    mid = mandanten.mandant_anlegen(kid, "Salon Nina", "nina@0711.io", c=db)
    assert mandanten.kanzlei_mitglied("sachbearbeiter@0711.io", mid, c=db) is False
    mandanten.mitglied_anlegen(kid, "sachbearbeiter@0711.io", c=db)
    assert mandanten.kanzlei_mitglied("sachbearbeiter@0711.io", mid, c=db) is True


def test_die_daten_gehoeren_dem_salon_nicht_der_kanzlei(db):
    kid = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=db)
    mid = mandanten.mandant_anlegen(kid, "Salon Nina", "nina@0711.io", c=db)
    assert mandanten.mandant_besitzer_un(mid, c=db) == "nina@0711.io"


def test_mandanten_einer_kanzlei_nach_status(db):
    kid = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=db)
    a = mandanten.mandant_anlegen(kid, "Alpha", "nina@0711.io", c=db)
    mandanten.mandant_anlegen(kid, "Beta", "salon-b@0711.io", c=db)
    mandanten.box_verknuepfen(a, "inspektor/ws-alpha/babu", c=db)

    alle = mandanten.mandanten_von_kanzlei(kid, c=db)
    assert [m["name"] for m in alle] == ["Alpha", "Beta"]
    offen = mandanten.mandanten_von_kanzlei(kid, status="box_ausstehend", c=db)
    assert [m["name"] for m in offen] == ["Beta"]


# ————— Die Gegenrichtung: aus dem Betrieb heraus gefragt —————
#
# `mandanten_fuer` fragt aus der Kanzlei heraus. Beim Hochladen ohne
# `X-Mandant`-Kopf braucht der Server die andere Richtung: zu welcher
# Mandantenzeile gehört DIESER Betrieb? Ohne sie landete jeder Beleg in
# der Default-Box — also in der des ersten Kunden.

def test_ohne_mandat_ist_die_liste_leer(db):
    assert mandanten.mandate_von_besitzer("nina@0711.io", c=db) == []


def test_das_eigene_mandat_wird_gefunden(db):
    kid = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=db)
    mid = mandanten.mandant_anlegen(kid, "Salon Nina", "nina@0711.io", c=db)
    mandanten.box_verknuepfen(mid, "inspektor/ws-nina/babu", c=db)

    meine = mandanten.mandate_von_besitzer("nina@0711.io", c=db)
    assert [m["id"] for m in meine] == [mid]
    assert meine[0]["box_ref"] == "inspektor/ws-nina/babu"
    # Und der Nachbarbetrieb bleibt draußen.
    assert mandanten.mandate_von_besitzer("salon-b@0711.io", c=db) == []


def test_ein_mandat_ohne_box_zaehlt_mit(db):
    """`box_ausstehend` ist eine Zuständigkeit — nur eben noch ohne Box.

    Das ist wichtig: der Aufrufer muss diesen Fall SEHEN, um ihn ehrlich
    als „wird noch eingerichtet" zu beantworten. Fiele die Zeile hier
    heraus, bekäme der Betrieb stillschweigend die Default-Box.
    """
    kid = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=db)
    mid = mandanten.mandant_anlegen(kid, "Salon Nina", "nina@0711.io", c=db)
    meine = mandanten.mandate_von_besitzer("nina@0711.io", c=db)
    assert [m["id"] for m in meine] == [mid]
    assert meine[0]["status"] == "box_ausstehend"
    assert not meine[0]["box_ref"]


def test_ein_beendetes_mandat_zaehlt_nicht_mehr(db):
    """Ein gekündigtes Mandat ist keine Zuständigkeit, und die Box daran
    ist Geschichte."""
    kid = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=db)
    mid = mandanten.mandant_anlegen(kid, "Salon Nina", "nina@0711.io", c=db)
    mandanten.status_setzen(mid, "beendet", c=db)
    assert mandanten.mandate_von_besitzer("nina@0711.io", c=db) == []


def test_zwei_kanzleien_ergeben_zwei_mandate(db):
    """Die UNIQUE-Grenze verhindert nur Doppel INNERHALB einer Kanzlei.

    Zwei Kanzleien können denselben Betrieb führen — dann ist die Frage
    „welche Box?" nicht mehr eindeutig, und der Aufrufer muss das merken
    können, statt sich eine auszusuchen.
    """
    a = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=db)
    b = mandanten.kanzlei_anlegen("Kanzlei Nord", "sachbearbeiter@0711.io", c=db)
    mandanten.mandant_anlegen(a, "Nina bei Süd", "nina@0711.io", c=db)
    mandanten.mandant_anlegen(b, "Nina bei Nord", "nina@0711.io", c=db)
    assert len(mandanten.mandate_von_besitzer("nina@0711.io", c=db)) == 2


def test_ohne_verbindung_und_ohne_c_gibt_es_eine_klare_meldung(monkeypatch):
    monkeypatch.setattr(mandanten, "_VERBINDUNG", None)
    with pytest.raises(RuntimeError, match="keine Datenbank"):
        mandanten.mandant_holen(1)


# ---------------------------------------------------------------------------
# Zusammenspiel: die Tabellen entstehen in `_db()`, und `box_von` liest sie.
# ---------------------------------------------------------------------------

def test_db_legt_die_tenancy_tabellen_mit_an(tmp_path, monkeypatch):
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    with babu_web._db() as c:
        if c.dialekt == "sqlite":
            frage = "SELECT name FROM sqlite_master WHERE type = 'table'"
        else:   # Postgres kennt kein sqlite_master — dort über den Katalog
            frage = ("SELECT table_name FROM information_schema.tables "
                     "WHERE table_schema = current_schema()")
        namen = {z[0] for z in c.execute(frage)}
    assert {"kanzlei", "mandant", "kanzlei_mitglied"} <= namen


def test_box_von_loest_ueber_die_mandantentabelle_auf(tmp_path, monkeypatch):
    """Der Weg, den Phase 3 gehen wird — hier einmal ganz durchgespielt."""
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(bx, "STORE_WURZEL", tmp_path / "stores")
    monkeypatch.setattr(bx, "KLON_WURZEL", tmp_path / "klone")
    bx.registry_leeren()

    with babu_web._db() as c:
        c.execute("INSERT INTO nutzer (email, name, salon, rolle, pw) "
                  "VALUES (?, ?, ?, ?, ?)",
                  ("nina@0711.io", "Nina", "Salon", "salon", "x"))
        c.execute("INSERT INTO nutzer (email, name, salon, rolle, pw) "
                  "VALUES (?, ?, ?, ?, ?)",
                  ("kanzlei@0711.io", "K", "K", "kanzlei", "x"))
        kid = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei@0711.io", c=c)
        mid = mandanten.mandant_anlegen(kid, "Salon Nina", "nina@0711.io", c=c)
        c.commit()

    # Solange keine Box eingerichtet ist, gibt es auch keine.
    with pytest.raises(bx.KeineBox):
        bx.box_von("kanzlei@0711.io", mid)

    mandanten.box_verknuepfen(mid, "inspektor/ws-nina.de/babu")
    b = bx.box_von("kanzlei@0711.io", mid)
    assert b.mandant_id == mid
    assert b.store == tmp_path / "stores/inspektor/ws-nina.de/babu.git"
    assert b.klon == tmp_path / "klone/ws-nina.de"
    # …und sie ist NICHT die Box des Einzelbetriebs.
    assert b is not bx.default_box()
    bx.registry_leeren()
