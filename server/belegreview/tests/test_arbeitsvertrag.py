"""Die Vertragsmaschine.

Ein falscher Arbeitsvertrag fällt nicht auf, bis es Streit gibt — und dann
kostet er Geld und Nerven. Deshalb prüfen die Tests hier weniger, ob Text
herauskommt, als ob babu die Fälle erkennt, in denen es KEINEN Vertrag
erzeugen darf: unter Mindestlohn, über der Minijob-Grenze, Probezeit zu
lang, Jugendliche zu viele Stunden.
"""
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import arbeitsvertrag as av  # noqa: E402


BETRIEB = {"name": "Salon Nina", "strasse": "Marktstr. 3",
           "ort": "70173 Stuttgart", "arbeitnehmerin": "Frau Holder"}


def eckdaten(**anders):
    grund = {"art": "teilzeit", "eintritt": "2026-09-01",
             "stunden_woche": 24, "tage_woche": 3, "entgelt": 1600,
             "taetigkeit": "Friseurin"}
    return {**grund, **anders}


# ————— Was babu ausrechnet, statt es abzufragen —————

@pytest.mark.parametrize("tage, erwartet", [
    (6, 24), (5, 20), (4, 16), (3, 12), (2, 8), (1, 4),
])
def test_urlaub_nach_arbeitstagen(tage, erwartet):
    """§ 3 BUrlG: vier Wochen bleiben vier Wochen, egal wie verteilt."""
    assert av.urlaub_mindestens(tage) == erwartet


def test_urlaub_wird_aufgerundet():
    """Abrunden hieße, unter das gesetzliche Minimum zu gehen."""
    assert av.urlaub_mindestens(2.5) == 10


@pytest.mark.parametrize("alter, erwartet", [
    (15, 25), (16, 23), (17, 21), (18, 20), (40, 20),
])
def test_jugendliche_bekommen_mehr_urlaub(alter, erwartet):
    """§ 19 JArbSchG, hier auf die Fünftagewoche gerechnet."""
    assert av.urlaub_mindestens(5, alter) == erwartet


def test_monatsentgelt_rechnet_mit_dreizehn_dritteln():
    """52 Wochen auf 12 Monate sind 4,333 — nicht 4. Wer mit 4 rechnet,
    landet unter dem Mindestlohn, sobald ein Monat fünf Zahltage hat."""
    assert av.monatsentgelt(13.90, 40) == pytest.approx(2409.33, abs=0.01)
    assert av.monatsentgelt(13.90, 40) > 13.90 * 40 * 4


def test_stundenlohn_ist_die_umkehrung():
    lohn = av.stundenlohn_aus(av.monatsentgelt(15.0, 24), 24)
    assert lohn == pytest.approx(15.0, abs=0.01)


def test_kuendigungsfrist_waechst_mit_der_zugehoerigkeit():
    assert "vier Wochen" in av.kuendigungsfrist_regulaer(0)
    assert "einen Monat" in av.kuendigungsfrist_regulaer(24)
    assert "zwei Monate" in av.kuendigungsfrist_regulaer(60)
    assert "sieben Monate" in av.kuendigungsfrist_regulaer(240)


def test_alter_am_stichtag():
    geboren = dt.date(2008, 9, 2)
    assert av.alter_am(geboren, dt.date(2026, 9, 1)) == 17   # Tag davor
    assert av.alter_am(geboren, dt.date(2026, 9, 2)) == 18


# ————— Was babu nicht erzeugt —————

def test_unter_mindestlohn_gibt_es_keinen_vertrag():
    with pytest.raises(av.VertragFehler) as e:
        av.vertrag_bauen(eckdaten(entgelt=1200), BETRIEB)
    assert "13,90" in str(e.value) or "13.90" in str(e.value)
    assert "Mindestlohn" in str(e.value)


def test_der_fehler_sagt_auch_was_reichen_wuerde():
    """Ein Nein ohne Zahl zwingt zum Raten."""
    with pytest.raises(av.VertragFehler) as e:
        av.vertrag_bauen(eckdaten(entgelt=1200), BETRIEB)
    assert "mindestens" in str(e.value)


def test_minijob_ueber_der_grenze_gibt_es_nicht():
    with pytest.raises(av.VertragFehler) as e:
        av.vertrag_bauen(eckdaten(art="minijob", stunden_woche=12,
                                  entgelt=800), BETRIEB)
    assert "603" in str(e.value)


def test_minijob_knapp_unter_der_grenze_geht():
    v = av.vertrag_bauen(eckdaten(art="minijob", stunden_woche=10,
                                  tage_woche=2, entgelt=603), BETRIEB)
    assert v["art"] == "minijob"
    assert v["melden_an"].startswith("Minijob-Zentrale")


def test_probezeit_ueber_sechs_monaten_ist_unzulaessig():
    with pytest.raises(av.VertragFehler) as e:
        av.vertrag_bauen(eckdaten(probezeit_monate=9), BETRIEB)
    assert "622" in str(e.value)


def test_zu_wenig_urlaub_wird_abgelehnt():
    with pytest.raises(av.VertragFehler) as e:
        av.vertrag_bauen(eckdaten(urlaubstage=8), BETRIEB)
    assert "12" in str(e.value)


def test_mehr_urlaub_als_noetig_ist_erlaubt():
    v = av.vertrag_bauen(eckdaten(urlaubstage=20), BETRIEB)
    assert v["angaben"]["urlaubstage"] == 20


def test_ueber_achtundvierzig_stunden_geht_nicht():
    with pytest.raises(av.VertragFehler) as e:
        av.vertrag_bauen(eckdaten(stunden_woche=50, entgelt=4000), BETRIEB)
    assert "ArbZG" in str(e.value)


def test_befristungsende_vor_dem_eintritt():
    with pytest.raises(av.VertragFehler):
        av.vertrag_bauen(eckdaten(befristet_bis="2026-08-01"), BETRIEB)


def test_freie_mitarbeit_bekommt_keinen_vertrag_sondern_eine_warnung():
    """Scheinselbständigkeit ist im Friseurhandwerk der teure Klassiker.
    babu darf das nicht bequem machen."""
    with pytest.raises(av.VertragFehler) as e:
        av.vertrag_bauen(eckdaten(art="freie_mitarbeit"), BETRIEB)
    assert "Scheinselbständigkeit" in str(e.value)
    assert "Statusfeststellung" in str(e.value)


def test_unbekannte_art_zaehlt_die_moeglichen_auf():
    with pytest.raises(av.VertragFehler) as e:
        av.vertrag_bauen(eckdaten(art="irgendwas"), BETRIEB)
    assert "minijob" in str(e.value) and "vollzeit" in str(e.value)


# ————— Jugendliche —————

def test_jugendliche_hoechstens_vierzig_stunden():
    with pytest.raises(av.VertragFehler) as e:
        av.vertrag_bauen(eckdaten(geburtsdatum="2009-05-01", stunden_woche=45,
                                  entgelt=3000), BETRIEB)
    assert "JArbSchG" in str(e.value)


def test_jugendliche_hoechstens_fuenf_tage():
    with pytest.raises(av.VertragFehler) as e:
        av.vertrag_bauen(eckdaten(geburtsdatum="2009-05-01", tage_woche=6,
                                  stunden_woche=30, entgelt=2000), BETRIEB)
    assert "fünf Tagen" in str(e.value)


def test_jugendliche_bekommen_eigene_klausel_und_anlagen():
    v = av.vertrag_bauen(eckdaten(geburtsdatum="2009-05-01", stunden_woche=30,
                                  tage_woche=5, entgelt=2000), BETRIEB)
    assert any(p["id"] == "arbeitszeit_jugend" for p in v["paragraphen"])
    anlagen = {x["id"] for x in v["anlagen"]}
    assert "erstuntersuchung" in anlagen and "jarbschg" in anlagen


def test_volljaehrige_bekommen_die_jugendklausel_nicht():
    v = av.vertrag_bauen(eckdaten(geburtsdatum="1990-05-01"), BETRIEB)
    assert not any(p["id"] == "arbeitszeit_jugend" for p in v["paragraphen"])


# ————— Papier oder nicht —————

def test_unbefristet_geht_digital():
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    assert v["form"]["form"] == "textform"
    assert "126b" in v["form"]["grund"]


def test_befristet_muss_auf_papier():
    """§ 14 Abs. 4 TzBfG — und das Produkt muss den Ausweg zeigen."""
    v = av.vertrag_bauen(eckdaten(befristet_bis="2027-08-31"), BETRIEB)
    assert v["form"]["form"] == "schriftform"
    assert "TzBfG" in v["form"]["grund"]
    assert "Probezeit" in (v["form"]["ausweg"] or "")


def test_ausbildung_muss_auf_papier():
    v = av.vertrag_bauen(eckdaten(art="ausbildung", stunden_woche=40,
                                  tage_woche=5, entgelt=800), BETRIEB)
    assert v["form"]["form"] == "schriftform"
    assert "Handwerkskammer" in v["form"]["grund"]


def test_wer_papier_verlangt_bekommt_papier():
    v = av.vertrag_bauen(eckdaten(schriftform_gewuenscht=True), BETRIEB)
    assert v["form"]["form"] == "schriftform"


# ————— Vollständigkeit nach dem Nachweisgesetz —————

def test_der_vertrag_ist_nachweisrechtlich_vollstaendig():
    """Fehlt eine Pflichtangabe, droht ein Bußgeld nach § 4 NachwG — und im
    Streit gilt im Zweifel die Darstellung der Arbeitnehmerin."""
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    assert v["pflichtangaben_fehlen"] == []


@pytest.mark.parametrize("art, extra", [
    ("vollzeit", {"stunden_woche": 40, "tage_woche": 5, "entgelt": 2500}),
    ("teilzeit", {}),
    ("minijob", {"stunden_woche": 10, "tage_woche": 2, "entgelt": 603}),
    ("kurzfristig", {"stunden_woche": 20, "tage_woche": 4, "entgelt": 1400}),
    ("werkstudent", {"stunden_woche": 18, "tage_woche": 3, "entgelt": 1200}),
])
def test_jede_art_ergibt_einen_vollstaendigen_vertrag(art, extra):
    v = av.vertrag_bauen(eckdaten(art=art, **extra), BETRIEB)
    assert v["pflichtangaben_fehlen"] == []
    assert len(v["paragraphen"]) >= 15


def test_der_waechter_wuerde_eine_luecke_merken():
    """Gegenprobe: sonst wäre die Vollständigkeitsprüfung blind."""
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    v["paragraphen"] = [p for p in v["paragraphen"] if p["id"] != "urlaub"]
    assert any("Erholungsurlaub" in x for x in av.pflichtangaben_fehlen(v))


# ————— Die Klauseln, an denen Ninas Muster gescheitert wäre —————

def test_ausschlussfrist_nimmt_den_mindestlohn_aus():
    """Ohne diese Ausnahme kann die ganze Klausel unwirksam sein."""
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    [k] = [p for p in v["paragraphen"] if p["id"] == "ausschlussfrist"]
    assert "Mindestlohn" in k["text"]
    assert "nicht verzichtet werden kann" in k["text"]


def test_kuendigungsklausel_nennt_die_klagefrist():
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    [k] = [p for p in v["paragraphen"] if p["id"] == "kuendigung"]
    assert "drei Wochen" in k["text"] and "§ 4 KSchG" in k["text"]
    assert "elektronische Form ist" in k["text"]      # § 623 BGB


def test_keine_doppelte_schriftformklausel():
    """In AGB regelmäßig unwirksam — und sie widerspricht der Textform."""
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    [k] = [p for p in v["paragraphen"] if p["id"] == "nebenabreden"]
    assert "Textform" in k["text"]
    assert "Individuell ausgehandelte Abreden" in k["text"]


def test_rueckzahlung_von_fortbildung_nur_gestaffelt():
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    [k] = [p for p in v["paragraphen"] if p["id"] == "fortbildung"]
    assert "zeitanteilig abstufen" in k["text"]


def test_nebentaetigkeit_ohne_zustimmungsvorbehalt():
    """Ein genereller Zustimmungsvorbehalt greift in Art. 12 GG ein."""
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    [k] = [p for p in v["paragraphen"] if p["id"] == "nebentaetigkeit"]
    assert "anzuzeigen" in k["text"]
    assert "Zustimmungsvorbehalt besteht nicht" in k["text"]


def test_mehrarbeit_ist_nicht_pauschal_abgegolten():
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    [k] = [p for p in v["paragraphen"] if p["id"] == "mehrarbeit"]
    assert "pauschale Abgeltung" in k["text"] and "nicht vereinbart" in k["text"]


def test_arbeitszeit_nennt_pausen_und_erfassung():
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    [k] = [p for p in v["paragraphen"] if p["id"] == "arbeitszeit"]
    assert "Ruhepausen" in k["text"] and "§ 4 ArbZG" in k["text"]
    assert "aufgezeichnet" in k["text"]


def test_hautschutz_steht_drin():
    """Die branchentypische Pflicht, an die keine allgemeine Vorlage denkt."""
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    [k] = [p for p in v["paragraphen"] if p["id"] == "arbeitsschutz"]
    assert "TRGS 530" in k["text"] and "BGW" in k["text"]


def test_kundendaten_duerfen_nicht_mitgenommen_werden():
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    [k] = [p for p in v["paragraphen"] if p["id"] == "verschwiegenheit"]
    assert "Farbformeln" in k["text"]
    assert "eigener Listen" in k["text"]


# ————— Was je Art dazukommt —————

def test_minijob_erklaert_die_rentenversicherung():
    v = av.vertrag_bauen(eckdaten(art="minijob", stunden_woche=10,
                                  tage_woche=2, entgelt=603), BETRIEB)
    [k] = [p for p in v["paragraphen"] if p["id"] == "minijob_rv"]
    assert "befreien" in k["text"] and "603" in k["text"]
    assert "rv_befreiung" in {x["id"] for x in v["anlagen"]}


def test_kurzfristig_nennt_die_zeitgrenzen():
    v = av.vertrag_bauen(eckdaten(art="kurzfristig", stunden_woche=20,
                                  tage_woche=4, entgelt=1400), BETRIEB)
    [k] = [p for p in v["paragraphen"] if p["id"] == "kurzfristig_grenzen"]
    assert "70 Arbeitstage" in k["text"]
    assert "vorbeschaeftigung" in {x["id"] for x in v["anlagen"]}


def test_werkstudent_ueber_zwanzig_stunden_wird_gewarnt():
    v = av.vertrag_bauen(eckdaten(art="werkstudent", stunden_woche=25,
                                  tage_woche=4, entgelt=1700), BETRIEB)
    assert any("Werkstudentenprivileg" in x["text"] for x in v["befunde"])


def test_teilzeit_bekommt_die_minijob_klausel_nicht():
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    assert not any(p["id"] == "minijob_rv" for p in v["paragraphen"])


def test_jede_art_bekommt_die_pflichtanlagen():
    for art, extra in (("vollzeit", {"stunden_woche": 40, "tage_woche": 5,
                                     "entgelt": 2500}),
                       ("minijob", {"stunden_woche": 10, "tage_woche": 2,
                                    "entgelt": 603})):
        v = av.vertrag_bauen(eckdaten(art=art, **extra), BETRIEB)
        ids = {x["id"] for x in v["anlagen"]}
        assert {"datengeheimnis", "arbeitsschutz", "hautschutz"} <= ids


# ————— Die Werte, die sich jährlich ändern —————

def test_die_werte_haengen_am_eintrittsdatum():
    assert av.werte_fuer(dt.date(2025, 6, 1))["mindestlohn"] == 12.82
    assert av.werte_fuer(dt.date(2026, 6, 1))["mindestlohn"] == 13.90
    assert av.werte_fuer(dt.date(2027, 6, 1))["mindestlohn"] == 14.60


def test_unbekanntes_jahr_wird_gekennzeichnet():
    """Stillschweigend mit veralteten Zahlen zu rechnen wäre schlimmer."""
    w = av.werte_fuer(dt.date(2030, 1, 1))
    assert w["geschaetzt"] is True and w["mindestlohn"] == 14.60


def test_der_hinweis_steht_im_vertrag():
    v = av.vertrag_bauen(eckdaten(eintritt="2030-01-01", entgelt=2000,
                                  stunden_woche=24), BETRIEB)
    assert any("noch nicht hinterlegt" in x["text"] for x in v["befunde"])


def test_die_minijob_grenze_passt_zum_mindestlohn():
    """Die Grenze ist gesetzlich an den Mindestlohn gekoppelt:
    Mindestlohn × 130 ÷ 3. Wenn beide Zahlen auseinanderlaufen, ist eine
    davon beim Jahreswechsel vergessen worden."""
    for jahr, w in av.WERTE.items():
        erwartet = w["mindestlohn"] * 130 / 3
        assert abs(w["minijob"] - erwartet) < 1.5, (
            f"{jahr}: Grenze {w['minijob']} passt nicht zu "
            f"{w['mindestlohn']} €/h (erwartet ~{erwartet:.0f})")


# ————— Der fertige Text —————

def test_der_text_enthaelt_beide_parteien_und_alle_paragraphen():
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    text = av.als_text(v)
    assert "Salon Nina" in text and "Frau Holder" in text
    assert text.count("§ ") >= len(v["paragraphen"])
    assert "Anlagen zu diesem Vertrag" in text


def test_betraege_stehen_deutsch_im_text():
    v = av.vertrag_bauen(eckdaten(entgelt=1600), BETRIEB)
    [k] = [p for p in v["paragraphen"] if p["id"] == "verguetung"]
    assert "1.600,00 €" in k["text"]


def test_die_fassung_wird_mitgefuehrt():
    """Ohne Fassung lässt sich später nicht sagen, was jemand angenommen hat."""
    v = av.vertrag_bauen(eckdaten(), BETRIEB)
    assert v["fassung"] == av.VORLAGE_FASSUNG


# ————— Wo der Mindestlohn nicht gilt (§ 22 MiLoG) —————
#
# Beide Ausnahmen sind beim ersten Lauf aufgefallen: der Code hat
# Auszubildende am Mindestlohn gemessen und damit zulässige Verträge
# abgelehnt.

def test_auszubildende_fallen_nicht_unter_den_mindestlohn():
    """800 € bei 40 Stunden wären 4,62 €/h — für Azubis trotzdem zulässig."""
    v = av.vertrag_bauen(eckdaten(art="ausbildung", stunden_woche=40,
                                  tage_woche=5, entgelt=800), BETRIEB)
    assert v["angaben"]["stundenlohn"] < 13.90
    assert any("22 Abs. 3" in x["text"] for x in v["befunde"])


def test_unter_der_mindestausbildungsverguetung_geht_nicht():
    with pytest.raises(av.VertragFehler) as e:
        av.vertrag_bauen(eckdaten(art="ausbildung", stunden_woche=40,
                                  tage_woche=5, entgelt=600), BETRIEB)
    assert "724" in str(e.value) and "BBiG" in str(e.value)


@pytest.mark.parametrize("jahr, mindestens", [
    (1, 724), (2, 854), (3, 977), (4, 1014),
])
def test_die_ausbildungsverguetung_steigt_mit_dem_lehrjahr(jahr, mindestens):
    """§ 17 Abs. 2 BBiG: +18 %, +35 %, +40 % auf das erste Jahr."""
    with pytest.raises(av.VertragFehler) as e:
        av.vertrag_bauen(eckdaten(art="ausbildung", ausbildungsjahr=jahr,
                                  stunden_woche=40, tage_woche=5,
                                  entgelt=500), BETRIEB)
    assert str(mindestens) in str(e.value)

    av.vertrag_bauen(eckdaten(art="ausbildung", ausbildungsjahr=jahr,
                              stunden_woche=40, tage_woche=5,
                              entgelt=mindestens), BETRIEB)   # genau reicht


def test_fuenftes_lehrjahr_gibt_es_nicht():
    with pytest.raises(av.VertragFehler):
        av.vertrag_bauen(eckdaten(art="ausbildung", ausbildungsjahr=5,
                                  stunden_woche=40, tage_woche=5,
                                  entgelt=2000), BETRIEB)


def test_jugendliche_ohne_ausbildung_sind_ausgenommen():
    """§ 22 Abs. 2 MiLoG — eine Ausnahme zugunsten der Ausbildung."""
    v = av.vertrag_bauen(eckdaten(geburtsdatum="2009-05-01", stunden_woche=20,
                                  tage_woche=4, entgelt=900), BETRIEB)
    assert v["angaben"]["stundenlohn"] < 13.90
    assert any("22 Abs. 2" in x["text"] for x in v["befunde"])


def test_jugendliche_mit_abgeschlossener_ausbildung_nicht():
    with pytest.raises(av.VertragFehler) as e:
        av.vertrag_bauen(eckdaten(geburtsdatum="2009-05-01", stunden_woche=20,
                                  tage_woche=4, entgelt=900,
                                  berufsausbildung_abgeschlossen=True), BETRIEB)
    assert "Mindestlohn" in str(e.value)


def test_ein_minijob_hat_kaum_noch_zehn_stunden_platz():
    """Die stille Folge aus Mindestlohn und Minijob-Grenze: 603 € geteilt
    durch 13,90 € sind 43,4 Stunden im Monat — also gut zehn je Woche. Mehr
    passt 2026 nicht in einen Minijob, egal wie man rechnet."""
    grenze = av.WERTE[2026]["minijob"] / (av.WERTE[2026]["mindestlohn"] * 13 / 3)
    assert 10.0 < grenze < 10.1

    with pytest.raises(av.VertragFehler):
        av.vertrag_bauen(eckdaten(art="minijob", stunden_woche=12,
                                  tage_woche=3, entgelt=603), BETRIEB)


# ————— Die Strecke am Server —————

import subprocess  # noqa: E402


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "README.md").write_text("box")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "s"],
                   check=True, capture_output=True)
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)], check=True)

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import babu_web
    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    babu_web.wer_token = lambda t: "christoph0711.io" if t == "test-pat" else None
    babu_web._REG_ZULETZT.clear()
    from fastapi.testclient import TestClient
    client = TestClient(babu_web.app, base_url="https://testserver")
    assert client.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    client.post("/api/einstellungen", json={"betrieb_name": "Salon Nina",
                                            "betrieb_ort": "Stuttgart"})
    return client, babu_web


def test_die_arten_kommen_mit_den_geltenden_grenzen(welt):
    client, _ = welt
    d = client.get("/api/arbeitsvertrag/arten").json()
    assert {a["id"] for a in d["arten"]} >= {"vollzeit", "minijob", "ausbildung"}
    assert d["werte"]["mindestlohn"] == 13.90
    assert d["werte"]["minijob_grenze"] == 603
    # Die Warnung zur Scheinselbständigkeit muss die Oberfläche zeigen können.
    assert any("Scheinselbständigkeit" in x["warnung"]
               for x in d["nicht_anstellung"])


def test_entwurf_aus_eckdaten(welt):
    client, _ = welt
    r = client.post("/api/arbeitsvertrag/entwurf", json={
        "art": "teilzeit", "eintritt": "2026-09-01", "stunden_woche": 24,
        "tage_woche": 3, "entgelt": 1600, "taetigkeit": "Friseurin",
        "arbeitnehmerin": "Frau Holder"})
    assert r.status_code == 200
    d = r.json()
    assert d["pflichtangaben_fehlen"] == []
    assert d["form"]["form"] == "textform"
    assert d["angaben"]["urlaubstage"] == 12
    assert "Salon Nina" in d["text"] and "Frau Holder" in d["text"]


def test_der_betrieb_kommt_aus_den_einstellungen(welt):
    """Nina soll ihren Salonnamen nicht in jeden Vertrag tippen."""
    client, _ = welt
    d = client.post("/api/arbeitsvertrag/entwurf", json={
        "art": "vollzeit", "eintritt": "2026-09-01", "stunden_woche": 40,
        "tage_woche": 5, "entgelt": 2500}).json()
    assert d["betrieb"]["name"] == "Salon Nina"


def test_unzulaessiger_entwurf_wird_abgelehnt(welt):
    """400 mit Klartext, nicht 200 mit Warnhinweis im Vertrag."""
    client, _ = welt
    r = client.post("/api/arbeitsvertrag/entwurf", json={
        "art": "teilzeit", "eintritt": "2026-09-01", "stunden_woche": 24,
        "tage_woche": 3, "entgelt": 1000})
    assert r.status_code == 400
    assert "Mindestlohn" in r.json()["fehler"]


def test_freie_mitarbeit_wird_am_server_abgewiesen(welt):
    client, _ = welt
    r = client.post("/api/arbeitsvertrag/entwurf", json={
        "art": "freie_mitarbeit", "eintritt": "2026-09-01",
        "stunden_woche": 20, "entgelt": 2000})
    assert r.status_code == 400
    assert "Scheinselbständigkeit" in r.json()["fehler"]


def test_der_entwurf_wird_nicht_abgelegt(welt):
    """Ein Entwurf ist ein Entwurf — in der Belegbox hat er nichts verloren,
    bevor ihn jemand angenommen hat."""
    client, _ = welt
    vorher = client.get("/api/ablage").json()
    client.post("/api/arbeitsvertrag/entwurf", json={
        "art": "teilzeit", "eintritt": "2026-09-01", "stunden_woche": 24,
        "tage_woche": 3, "entgelt": 1600})
    assert client.get("/api/ablage").json() == vorher


def test_mitarbeiterinnen_machen_keine_vertraege(welt):
    client, bw = welt
    from fastapi.testclient import TestClient
    fremd = TestClient(bw.app, base_url="https://testserver")
    bw._REG_ZULETZT.clear()
    fremd.post("/api/signup", json={"salon": "Fremd", "email": "f@x.de",
                                    "passwort": "passwort-lang"})
    assert fremd.post("/api/arbeitsvertrag/entwurf",
                      json={"art": "teilzeit"}).status_code == 403
