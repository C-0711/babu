"""Das Werkzeug, das einen Betrieb aufnimmt — und danach nachsieht.

Fünf Dinge hängen hier wirklich:

1. **Der Trockenlauf schreibt nichts.** Ein „zeig mir erst mal“, das schon
   die Hälfte angelegt hat, ist schlimmer als gar keins.
2. **Die Reihenfolge.** `mandant.besitzer_un` zeigt per Fremdschlüssel auf
   `nutzer(email)`; unter Postgres ist ein Mandant vor seinem Konto ein
   500er. Der Test prüft nicht, dass beides existiert — er prüft, dass das
   Konto schon dastand, als der Mandant geschrieben wurde.
3. **Kein zweiter Lauf auf dieselbe Adresse.** `nutzer_anlegen` gäbe stumm
   `None` zurück; ohne Abbruch entstünde ein zweiter Mandant an einem
   fremden Konto.
4. **Die fehlende Belegbox wird benannt, nicht erzeugt.** Das Gateway ist
   ein fremdes Projekt; das Werkzeug darf nur den Pfad nennen, den es
   erwartet.
5. **Die Prüfungen melden.** Ein Anlegewerkzeug, dem man glauben soll,
   muss auf einen kaputten Zustand mit „NEIN“ antworten und nicht mit
   Schweigen.
"""
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER.parent.parent.parent / "werkzeuge"))

import babu_web  # noqa: E402
import betrieb_anlegen as ba  # noqa: E402
import box as bx  # noqa: E402
import mandanten  # noqa: E402


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    """Leere Portal-Datenbank, leere Store-Wurzel, eine Kanzlei."""
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(bx, "STORE_WURZEL", tmp_path / "stores")
    monkeypatch.setattr(bx, "KLON_WURZEL", tmp_path / "klone")
    bx.registry_leeren()
    with babu_web._db_sitzung() as c:  # noqa: SLF001
        kanzlei_id = mandanten.kanzlei_anlegen("Kanzlei Test",
                                               "kanzlei@0711.io", c=c)
    return {"tmp": tmp_path, "kanzlei_id": kanzlei_id}


def _plan(welt, **abweichend):
    grund = dict(email="nina@salon.test", name="Nina Muster",
                 betrieb="SupremeStudio", kanzlei_id=welt["kanzlei_id"],
                 berater_nr="16149", mandant_nr="19364",
                 kontenrahmen="SKR04")
    grund.update(abweichend)
    return ba.Plan(**grund)


def _bare_box(welt, ref: str) -> Path:
    """Eine Belegbox, wie insp-app sie hinterlässt — hier von Hand."""
    store = bx.store_aus_ref(ref)
    store.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "--bare", str(store)], check=True)
    return store


def _zaehlen(tabelle: str, **wo) -> int:
    bedingung = " AND ".join(f"{k}=?" for k in wo) or "1=1"
    with babu_web._db_sitzung() as c:  # noqa: SLF001
        return len(list(c.execute(
            f"SELECT 1 FROM {tabelle} WHERE {bedingung}", tuple(wo.values()))))


# ---------------------------------------------------------------------------
# 1. Trockenlauf
# ---------------------------------------------------------------------------

def test_trockenlauf_schreibt_nichts(welt):
    bericht, passwort = ba.anlegen(_plan(welt, trocken=True))

    assert passwort is None
    assert _zaehlen("nutzer", email="nina@salon.test") == 0
    assert _zaehlen("mandant", besitzer_un="nina@salon.test") == 0
    # Er zeigt trotzdem, was er täte — und zwar alle drei Schritte.
    assert [s.name for s in bericht.schritte] == ["konto", "mandant"]
    assert all(not s.getan for s in bericht.schritte)


def test_trockenlauf_sieht_schon_nach_der_box(welt):
    """Die Box ist der einzige Schritt, den ein Mensch vorher erledigt —
    deshalb steht ihr Befund auch im Trockenlauf."""
    bericht, _ = ba.anlegen(_plan(welt, trocken=True,
                                  box_ref="inspektor/ws-nina.test/babu"))
    (befund,) = bericht.pruefungen
    assert befund.name == "belegbox" and not befund.ok
    assert str(bx.store_aus_ref("inspektor/ws-nina.test/babu")) in befund.grund
    # Ein Trockenlauf hat nichts halb angelegt — er meldet nie einen Fehler.
    assert bericht.code() == 0
    text = "\n".join(ba.bericht_zeilen(bericht))
    assert "Vorbefund" in text and "Nichts geschrieben" in text


# ---------------------------------------------------------------------------
# 2. Der Lauf, und die Reihenfolge darin
# ---------------------------------------------------------------------------

def test_lauf_legt_konto_und_mandant_an(welt):
    bericht, passwort = ba.anlegen(_plan(welt))

    assert passwort and len(passwort) >= 8
    konto = babu_web.nutzer_holen("nina@salon.test")
    assert konto is not None
    assert (konto["rolle"], konto["aktiv"], konto["salon"]) == \
        ("salon", True, "SupremeStudio")
    m = mandanten.mandant_holen(bericht.mandant_id)
    assert m["besitzer_un"] == "nina@salon.test"
    assert (m["kontenrahmen"], m["berater_nr"], m["mandant_nr"]) == \
        ("SKR04", "16149", "19364")
    assert m["status"] == "box_ausstehend"


def test_konto_steht_vor_dem_mandanten(welt, monkeypatch):
    """Der Fremdschlüssel muss zum Zeitpunkt des INSERT erfüllbar sein.

    Nicht „am Ende ist beides da“ — Postgres prüft beim Schreiben.
    """
    gesehen = {}
    echt = mandanten.mandant_anlegen

    def mit_blick(kanzlei_id, name, besitzer_un, *a, c=None, **kw):
        # Über die MITGEGEBENE Verbindung fragen: `nutzer_holen` nähme
        # dasselbe einfache Schloss ein zweites Mal und hinge für immer.
        gesehen["konto_da"] = c.execute(
            "SELECT 1 FROM nutzer WHERE email=?", (besitzer_un,)).fetchone()
        return echt(kanzlei_id, name, besitzer_un, *a, c=c, **kw)

    monkeypatch.setattr(mandanten, "mandant_anlegen", mit_blick)
    ba.anlegen(_plan(welt))
    assert gesehen["konto_da"] is not None


def test_konto_sieht_nicht_in_die_fremde_box(welt):
    """`box=0`: ein neuer Betrieb bekommt seine eigene Box über die
    Mandantenzeile — nicht die Default-Box des Servers."""
    ba.anlegen(_plan(welt))
    assert babu_web.nutzer_holen("nina@salon.test")["box"] is False


def test_neue_kanzlei_bekommt_ihr_erstes_mitglied(welt):
    bericht, _ = ba.anlegen(_plan(welt, kanzlei_id=None,
                                  kanzlei_neu="Kanzlei Afflek",
                                  kanzlei_inhaber="afflek@0711.io"))
    assert bericht.kanzlei_id != welt["kanzlei_id"]
    assert mandanten.kanzlei_mitglied("afflek@0711.io", bericht.mandant_id)
    assert [p.ok for p in bericht.pruefungen if p.name == "kanzlei"] == [True]


# ---------------------------------------------------------------------------
# 3. Zweiter Lauf
# ---------------------------------------------------------------------------

def test_zweiter_lauf_bricht_sauber_ab(welt):
    ba.anlegen(_plan(welt))
    with pytest.raises(ba.Abbruch) as ex:
        ba.anlegen(_plan(welt, betrieb="Zweiter Versuch"))
    assert "nina@salon.test" in str(ex.value)
    # Kein zweiter Mandant, kein umbenannter erster.
    assert _zaehlen("mandant", besitzer_un="nina@salon.test") == 1
    assert _zaehlen("mandant", name="Zweiter Versuch") == 0


def test_abbruch_ueber_die_kommandozeile_ist_code_2(welt, capsys):
    ba.anlegen(_plan(welt))
    code = ba.main(["--email", "nina@salon.test", "--betrieb", "Noch einer",
                    "--kanzlei-id", str(welt["kanzlei_id"])])
    assert code == 2
    assert "Abgebrochen" in capsys.readouterr().err


@pytest.mark.parametrize("abweichend, wort", [
    ({"email": "keine-adresse"}, "E-Mail"),
    ({"betrieb": ""}, "Betriebsnamen"),
    ({"kontenrahmen": "SKR99"}, "Kontenrahmen"),
    ({"kanzlei_id": 999}, "Kanzlei"),
    ({"kanzlei_neu": "Zweite"}, "schließen sich aus"),
    ({"kanzlei_id": None, "box_ref": "irgendwas/babu"}, "Belegbox"),
])
def test_vorpruefung_bricht_vor_dem_schreiben_ab(welt, abweichend, wort):
    with pytest.raises(ba.Abbruch) as ex:
        ba.anlegen(_plan(welt, **abweichend))
    assert wort in str(ex.value)
    assert _zaehlen("nutzer") == 0


# ---------------------------------------------------------------------------
# 4. Die Belegbox — benennen, nicht erzeugen
# ---------------------------------------------------------------------------

def test_fehlende_box_wird_benannt_und_nicht_verknuepft(welt):
    ref = "inspektor/ws-nina.test/babu"
    bericht, _ = ba.anlegen(_plan(welt, box_ref=ref))

    (befund,) = [p for p in bericht.pruefungen if p.name == "belegbox"]
    assert not befund.ok and befund.handarbeit
    assert str(bx.store_aus_ref(ref)) in befund.grund
    assert "insp-app" in befund.grund
    # Und nichts angelegt: kein Store, kein `aktiv`.
    assert not bx.store_aus_ref(ref).exists()
    assert mandanten.mandant_holen(bericht.mandant_id)["status"] == \
        "box_ausstehend"
    # Kein Fehler, aber auch kein Freibrief: eigener Rückgabewert.
    assert bericht.code() == 3


def test_vorhandene_box_wird_verknuepft(welt):
    ref = "inspektor/ws-nina.test/babu"
    _bare_box(welt, ref)
    bericht, _ = ba.anlegen(_plan(welt, box_ref=ref))

    m = mandanten.mandant_holen(bericht.mandant_id)
    assert (m["box_ref"], m["status"]) == (ref, "aktiv")
    assert bericht.code() == 0
    assert all(p.ok for p in bericht.pruefungen)
    # Eine frische Box hat noch keinen Stand — und sagt das auch. `git
    # rev-parse HEAD` gibt dort das Wort „HEAD“ auf stdout zurück.
    (box,) = [p for p in bericht.pruefungen if p.name == "belegbox"]
    assert "noch ohne Belege" in box.grund


def test_box_die_kein_git_speicher_ist_ist_ein_fehler(welt):
    ref = "inspektor/ws-kaputt/babu"
    store = bx.store_aus_ref(ref)
    store.mkdir(parents=True)          # Ordner da, aber kein Repo darin
    bericht, _ = ba.anlegen(_plan(welt, box_ref=ref))

    (befund,) = [p for p in bericht.pruefungen if p.name == "belegbox"]
    assert not befund.ok and not befund.handarbeit
    assert "kein Git-Speicher" in befund.grund
    assert bericht.code() == 1


def test_ohne_kanzlei_bleibt_die_mandantenzeile_offen(welt):
    bericht, _ = ba.anlegen(_plan(welt, kanzlei_id=None))
    assert bericht.mandant_id is None
    namen = {p.name: p for p in bericht.pruefungen}
    assert namen["konto"].ok
    assert not namen["mandantenzeile"].ok and namen["mandantenzeile"].handarbeit
    assert bericht.code() == 3


def test_box_wird_nachgetragen_wenn_sie_spaeter_kommt(welt):
    """Der Weg, auf den der Befund verweist — er muss auch gehen.

    Die Box entsteht am Gateway, immer später. Ein voller zweiter Lauf
    bricht auf dem vorhandenen Konto ab (und das zu Recht), also braucht
    der Nachtrag einen eigenen Weg.
    """
    ref = "inspektor/ws-nina.test/babu"
    erst, _ = ba.anlegen(_plan(welt, box_ref=ref))
    assert erst.code() == 3

    _bare_box(welt, ref)                       # jetzt legt sie ein Mensch an
    spaeter = ba.box_nachtragen(ba.Plan(email="nina@salon.test", box_ref=ref))

    assert spaeter.mandant_id == erst.mandant_id
    m = mandanten.mandant_holen(erst.mandant_id)
    assert (m["box_ref"], m["status"]) == (ref, "aktiv")
    # Das Startpasswort ist hier nicht mehr bekannt — geprüft wird dann
    # die schwächere, aber wahre Frage: liegt ein scrypt-Hash da?
    (a,) = [p for p in spaeter.pruefungen if p.name == "anmeldung"]
    assert a.ok and "hier nicht nachrechenbar" in a.grund
    assert spaeter.code() == 0


def test_nachtrag_ohne_box_verknuepft_nichts(welt):
    ref = "inspektor/ws-nina.test/babu"
    erst, _ = ba.anlegen(_plan(welt))
    spaeter = ba.box_nachtragen(ba.Plan(email="nina@salon.test", box_ref=ref))
    assert mandanten.mandant_holen(erst.mandant_id)["box_ref"] is None
    assert mandanten.mandant_holen(erst.mandant_id)["status"] == "box_ausstehend"
    assert spaeter.code() == 3


def test_nachtrag_trocken_schreibt_nichts(welt):
    ref = "inspektor/ws-nina.test/babu"
    erst, _ = ba.anlegen(_plan(welt))
    _bare_box(welt, ref)
    ba.box_nachtragen(ba.Plan(email="nina@salon.test", box_ref=ref,
                              trocken=True))
    assert mandanten.mandant_holen(erst.mandant_id)["box_ref"] is None


def test_konto_ohne_brauchbares_passwort_ist_ein_fehler(welt):
    """Die schwächere Anmeldeprüfung ist trotzdem eine Prüfung."""
    ref = "inspektor/ws-nina.test/babu"
    ba.anlegen(_plan(welt, box_ref=ref))
    _bare_box(welt, ref)
    with babu_web._db_sitzung() as c:  # noqa: SLF001
        c.execute("UPDATE nutzer SET pw='' WHERE email=?", ("nina@salon.test",))
    spaeter = ba.box_nachtragen(ba.Plan(email="nina@salon.test", box_ref=ref))
    (a,) = [p for p in spaeter.pruefungen if p.name == "anmeldung"]
    assert not a.ok and not a.handarbeit
    assert spaeter.code() == 1


def test_nachtrag_auf_unbekanntem_betrieb_bricht_ab(welt):
    with pytest.raises(ba.Abbruch) as ex:
        ba.box_nachtragen(ba.Plan(email="niemand@salon.test",
                                  box_ref="a/b"))
    assert "kein Konto" in str(ex.value)


# ---------------------------------------------------------------------------
# 5. Die Prüfungen melden wirklich
# ---------------------------------------------------------------------------

def test_fehlende_datev_nummern_fallen_auf(welt):
    bericht, _ = ba.anlegen(_plan(welt, berater_nr="", mandant_nr=""))
    (p,) = [p for p in bericht.pruefungen if p.name == "mandantenzeile"]
    assert not p.ok and not p.handarbeit
    assert "berater_nr" in p.grund and "mandant_nr" in p.grund
    assert bericht.code() == 1


def test_verbogener_kontenrahmen_wird_gemeldet(welt):
    """Die Prüfung liest nach, statt zu glauben, was sie geschrieben hat."""
    bericht, passwort = ba.anlegen(_plan(welt))
    with babu_web._db_sitzung() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET kontenrahmen='SKR99' WHERE id=?",
                  (bericht.mandant_id,))
    erneut = ba.pruefen(ba._geputzt(_plan(welt)), bericht, passwort)  # noqa: SLF001
    (p,) = [p for p in erneut if p.name == "kontenrahmen"]
    assert not p.ok and "SKR99" in p.grund


def test_geloeschtes_konto_wird_gemeldet(welt):
    bericht, passwort = ba.anlegen(_plan(welt))
    with babu_web._db_sitzung() as c:  # noqa: SLF001
        c.execute("UPDATE nutzer SET aktiv=0 WHERE email=?",
                  ("nina@salon.test",))
    erneut = ba.pruefen(ba._geputzt(_plan(welt)), bericht, passwort)  # noqa: SLF001
    (p,) = [p for p in erneut if p.name == "konto"]
    assert not p.ok and "gesperrt" in p.grund


def test_anmeldung_wird_wirklich_durchgerechnet(welt):
    """Nicht „ein Hash steht da“, sondern „dieses Passwort passt dazu“."""
    bericht, passwort = ba.anlegen(_plan(welt))
    (p,) = [p for p in bericht.pruefungen if p.name == "anmeldung"]
    assert p.ok
    falsch = ba.pruefen(ba._geputzt(_plan(welt)), bericht,  # noqa: SLF001
                        passwort + "x")
    assert not [q for q in falsch if q.name == "anmeldung"][0].ok
    assert babu_web.pw_pruefen(passwort,
                               babu_web.nutzer_holen("nina@salon.test")["pw"])


# ---------------------------------------------------------------------------
# 6. Das Startpasswort bleibt auf der Konsole
# ---------------------------------------------------------------------------

def test_startpasswort_steht_in_keiner_zeile_der_datenbank(welt):
    bericht, passwort = ba.anlegen(_plan(welt))
    with babu_web._db_sitzung() as c:  # noqa: SLF001
        felder = [str(z) for z in c.execute("SELECT email, name, salon, pw "
                                            "FROM nutzer")]
        felder += [str(z) for z in c.execute("SELECT details FROM audit_log")]
    assert passwort not in " ".join(felder)


def test_bericht_traegt_das_passwort_nur_wenn_es_uebergeben_wird(welt, capsys):
    bericht, passwort = ba.anlegen(_plan(welt))
    ohne = "\n".join(ba.bericht_zeilen(bericht))
    mit = "\n".join(ba.bericht_zeilen(bericht, passwort))
    assert passwort not in ohne
    assert passwort in mit
    # Und der Weg über die Kommandozeile gibt es genau einmal aus.
    code = ba.main(["--email", "zweite@salon.test", "--betrieb", "Zweiter",
                    "--kanzlei-id", str(welt["kanzlei_id"]),
                    "--berater-nr", "1", "--mandant-nr", "2"])
    ausgabe = capsys.readouterr().out
    assert code == 3                      # steht, nur die Box fehlt noch
    assert ausgabe.count("Startpasswort für zweite@salon.test") == 1
