"""Die DATEV-Seite: Rollenschutz, Export, Vorschau, Hereinlesen, Abgleich.

Der Rollenschutz steht zuerst, weil er das Einzige ist, was hier wirklich
weh tun kann: die Seite zeigt den vollständigen Buchungsstapel eines
Betriebs. Der Rest prüft, dass Vorschau und Datei dieselben Zahlen tragen
(sie kommen aus derselben Quelle — genau deshalb muss man es einmal
belegen) und dass eine hereingelesene Datei rund läuft: was babu erzeugt,
muss babu wiedererkennen.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

GOLDEN = json.loads((HIER / "golden" / "review_weingaertle.json").read_text())

# Drei Belege in zwei Monaten — genug für einen Zeitraum-Export und für
# einen Abgleich, in dem sich eine Zeile entfernen und eine ändern lässt.
BELEGE = [
    ("2026-07", "20260714-101500-aaa001-friseurbedarf", "Friseurbedarf Nord",
     284.60, "14.07.2026", "R-1001"),
    ("2026-07", "20260722-183000-aaa002-delila", "Delila Hair GmbH",
     419.90, "22.07.2026", "R-1002"),
    ("2026-08", "20260812-093000-aaa003-buero", "Bürobedarf Müller",
     119.00, "12.08.2026", "R-2001"),
]


# Ein vierter Beleg für die Fälle, die eine Gutschrift brauchen: negativer
# Betrag, also im Stapel positiv im Haben. Er steht NICHT in `BELEGE` —
# sonst verschöbe er die Zählungen aller anderen Tests.
GUTSCHRIFT = ("2026-08", "20260818-140000-aaa004-erstattung",
              "Delila Hair GmbH", -40.00, "18.08.2026", "GS-7")


def _welt_bauen(tmp_path, monkeypatch, belege, rechnungen=()):
    """Eine Wegwerf-Belegbox mit den übergebenen Belegen, Rolle „admin"."""
    arbeit = tmp_path / "box"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    for monat, stamm, lieferant, brutto, datum, nummer in belege:
        ordner = arbeit / "docs" / monat
        ordner.mkdir(parents=True, exist_ok=True)
        (ordner / f"{stamm}.jpg").write_bytes(b"\xff\xd8\xff\xe0demo")
        review = json.loads(json.dumps(GOLDEN))
        review["datei"] = f"docs/{monat}/{stamm}.jpg"
        review["felder"].update(lieferant=lieferant, brutto=brutto, datum=datum,
                                beleg_nr=nummer, ust_satz=19, offen=[],
                                bewirtungssignal=False, steuertabelle=[])
        review["einschaetzung"] = {"konto": "6815", "konto_skr04": "6815",
                                   "kontenrahmen": "SKR04", "steuerschluessel": "9"}
        review["vlm"] = {"buchungstext": f"Einkauf {lieferant}"}
        (arbeit / "review").mkdir(exist_ok=True)
        (arbeit / "review" / f"{stamm}.json").write_text(
            json.dumps(review, ensure_ascii=False))
    # Gestellte Rechnungen liegen als rechnungen/<JJJJ-MM>/<nummer>.json in
    # der Box — genau so liest sie `_index_bauen`.
    for r in rechnungen:
        ordner = arbeit / "rechnungen" / r["datum"][:7]
        ordner.mkdir(parents=True, exist_ok=True)
        (ordner / f"{r['nummer']}.json").write_text(
            json.dumps(r, ensure_ascii=False))
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "demo"],
                   check=True, capture_output=True)
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)],
                   check=True)

    import babu_web
    import boxschreiber
    monkeypatch.setattr(babu_web, "STORE", bare)
    # Der Schreibweg in die Wegwerf-Box: ohne diese drei zeigt die
    # Default-Box auf das echte Gateway, und die Übergabe versuchte, aus
    # dem Test heraus in die Belegbox des Betriebs zu schreiben.
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(babu_web, "angemeldet", lambda request: "chef@0711.io")
    monkeypatch.setattr(babu_web, "zugelassen", lambda un: True)
    monkeypatch.setattr(babu_web, "rolle", lambda un: "admin")
    monkeypatch.setattr(babu_web, "nutzer_holen", lambda email: None)
    import datev_seite
    datev_seite._LESE_VERSUCHE.clear()
    return babu_web


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    return _welt_bauen(tmp_path, monkeypatch, BELEGE)


@pytest.fixture()
def welt_mit_gutschrift(tmp_path, monkeypatch):
    return _welt_bauen(tmp_path, monkeypatch, [*BELEGE, GUTSCHRIFT])


@pytest.fixture()
def c(welt):
    return TestClient(welt.app, base_url="https://testserver")


# ── Rollenschutz ────────────────────────────────────────────────────────

def test_salon_sieht_weder_seite_noch_zahlen(welt, monkeypatch):
    """Eine Inhaberin ohne Verwaltungsrolle bekommt nichts davon zu sehen —
    die SEITE ebenso wenig wie ihre Zahlen. Eine Seite, die erst hinterher
    „nicht erlaubt" sagt, hätte den Stapel schon ausgeliefert."""
    monkeypatch.setattr(welt, "rolle", lambda un: "salon")
    k = TestClient(welt.app, base_url="https://testserver")
    seite = k.get("/datev")
    assert seite.status_code == 403
    assert "Kein Zugang" in seite.text
    assert "EXTF" not in seite.text
    for pfad in ("/api/datev/uebersicht",
                 "/api/datev/vorschau?von=2026-07&bis=2026-07",
                 "/api/datev/stapel.csv?von=2026-07&bis=2026-07",
                 "/api/datev/konten.csv?von=2026-07&bis=2026-07",
                 "/api/datev/kreditoren.csv?von=2026-07&bis=2026-07"):
        assert k.get(pfad).status_code == 403, pfad
    assert k.post("/api/datev/lesen",
                  files={"datei": ("x.csv", b"egal", "text/csv")}).status_code == 403
    assert k.post("/api/datev/uebergeben?von=2026-07&bis=2026-07") \
        .status_code == 403


def test_verwaltung_bekommt_die_seite(c):
    r = c.get("/datev")
    assert r.status_code == 200
    assert "Buchungsstapel" in r.text
    assert "Zum Portal" in r.text


# ── Export ──────────────────────────────────────────────────────────────

def _kopf(rohtext: bytes) -> list[str]:
    return rohtext.decode("cp1252").split("\r\n")[0].split(";")


def test_export_monat_hat_gueltigen_extf_kopf(c):
    r = c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-07")
    assert r.status_code == 200
    kopf = _kopf(r.content)
    assert kopf[0] == '"EXTF"' and kopf[1] == "700"
    assert kopf[2] == "21" and kopf[3] == '"Buchungsstapel"'
    assert kopf[4] == "12"                 # Formatversion wie im Kanzlei-Export
    assert kopf[14] == "20260701" and kopf[15] == "20260731"
    assert "Buchungsstapel_2026-07.csv" in r.headers["content-disposition"]


def test_export_zeitraum_ist_eine_datei_mit_einem_kopf(c):
    """Zwei Monate, EIN Stapel: eine Kopfzeile, eine Spaltenzeile, und der
    Zeitraum im Kopf reicht vom ersten bis zum letzten Tag."""
    r = c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-08")
    assert r.status_code == 200
    zeilen = [z for z in r.content.decode("cp1252").split("\r\n") if z]
    assert sum(1 for z in zeilen if z.startswith('"EXTF"')) == 1
    assert sum(1 for z in zeilen if z.startswith("Umsatz (ohne")) == 1
    kopf = zeilen[0].split(";")
    assert kopf[14] == "20260701" and kopf[15] == "20260831"
    assert kopf[16] == '"babu 2026-07 bis 2026-08"'
    # Alle drei Belege stehen drin — zwei aus Juli, einer aus August.
    assert len(zeilen) == 2 + 3


def test_zeitraum_ueber_den_jahreswechsel_wird_abgelehnt(c):
    r = c.get("/api/datev/stapel.csv?von=2026-12&bis=2027-01")
    assert r.status_code == 400
    assert "Wirtschaftsjahr" in r.json()["fehler"]


def test_unsinniger_monat_wird_abgelehnt(c):
    assert c.get("/api/datev/vorschau?von=Juli").status_code == 400
    assert c.get("/api/datev/vorschau?von=2026-08&bis=2026-07").status_code == 400


# ── Vorschau ────────────────────────────────────────────────────────────

def test_vorschau_zahlen_stimmen_mit_extf_ueberein(c):
    """Die Vorschau darf nicht ihre eigene Rechnung aufmachen: jede Zeile,
    die sie zeigt, muss so auch in der Datei stehen."""
    import extf
    d = c.get("/api/datev/vorschau?von=2026-07&bis=2026-08").json()
    zeilen = d["zeilen"]
    assert len(zeilen) == 3
    assert d["befund"]["buchungen"] == 3
    assert d["befund"]["belege"] == 3
    assert {z["konto"] for z in zeilen} == {"6815"}
    assert {z["sh"] for z in zeilen} == {"S"}
    aus_datei = [z.split(";") for z in
                 c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-08")
                 .content.decode("cp1252").split("\r\n")[2:] if z]
    assert [z["umsatz"] for z in zeilen] == [d_[0] for d_ in aus_datei]
    assert [z["belegfeld"] for z in zeilen] == \
        [d_[10].strip('"') for d_ in aus_datei]
    # Und dieselben Beträge wie extf sie für den einzelnen Beleg rechnet.
    summe = sum(float(z["umsatz"].replace(",", ".")) for z in zeilen)
    assert round(summe, 2) == round(284.60 + 419.90 + 119.00, 2)
    assert extf.SPALTEN[13] == "Buchungstext"


def test_vorschau_summiert_je_konto(c):
    d = c.get("/api/datev/vorschau?von=2026-07&bis=2026-07").json()
    je = {e["konto"]: e for e in d["je_konto"]}
    assert je["6815"]["anzahl"] == 2
    assert je["6815"]["summe"] == round(284.60 + 419.90, 2)


def test_vorschau_meldet_belege_ohne_konto(welt, c, tmp_path):
    """Ein Beleg ohne Kontierung fehlt im Stapel — das muss VOR dem
    Herunterladen dastehen, nicht hinterher bei der Kanzlei auffallen."""
    import datev_seite
    idx = welt.index_aktuell()
    stamm = BELEGE[0][1]
    kaputt = json.loads(json.dumps(idx["reviews"][stamm]))
    kaputt["einschaetzung"] = {}
    daten = {"monate": ["2026-07"], "rahmen": "SKR04", "kleinunternehmerin": False,
             "je_monat": {"2026-07": {"reviews": [kaputt], "staemme": [stamm],
                                      "ohne_konto": [stamm], "blaetter": []}}}
    befund = datev_seite._befund(daten, datev_seite._zeilen(daten))
    assert befund["ohne_kontierung"] == [stamm]
    assert befund["sauber"] is False


def test_vorschau_liest_iso_datum_und_meldet_nur_unlesbare(welt):
    """Befund vom 02.09.2026: die Belege des Zielbild-Wegs tragen ihr Datum
    als `JJJJ-MM-TT`, `extf.buchungszeilen` las nur `TT.MM.JJJJ`. Seit dem
    extf-Fix (2b281ed) kommen beide Formate durch — der Befund meldet nur
    noch, was wirklich unlesbar ist."""
    import datev_seite
    review = json.loads(json.dumps(welt.index_aktuell()["reviews"][BELEGE[0][1]]))
    review["felder"]["datum"] = "2026-07-14"          # so schreibt es die App
    daten = {"monate": ["2026-07"], "rahmen": "SKR04", "kleinunternehmerin": False,
             "je_monat": {"2026-07": {"reviews": [review], "staemme": ["x"],
                                      "ohne_konto": [], "blaetter": []}}}
    zeilen = datev_seite._zeilen(daten)
    assert zeilen and all(z["belegdatum"] == "1407" for z in zeilen)
    befund = datev_seite._befund(daten, zeilen)
    assert befund["ohne_belegdatum"] == 0
    assert befund["ohne_belegdatum_belege"] == []

    kaputt = json.loads(json.dumps(review))
    kaputt["felder"]["datum"] = "irgendwann"
    daten["je_monat"]["2026-07"]["reviews"] = [kaputt]
    zeilen = datev_seite._zeilen(daten)
    assert zeilen and all(not z["belegdatum"] for z in zeilen)
    befund = datev_seite._befund(daten, zeilen)
    assert befund["ohne_belegdatum"] == len(zeilen)
    assert befund["ohne_belegdatum_belege"] == ["x"]
    assert befund["sauber"] is False


def test_uebersicht_nennt_monate_und_rahmen(c):
    d = c.get("/api/datev/uebersicht").json()
    assert d["monate"] == ["2026-08", "2026-07"]
    assert d["rahmen"] == "SKR04"
    assert d["je_monat"]["2026-07"]["fertig"] == 2


# ── Stammdaten ──────────────────────────────────────────────────────────

def test_kontenbeschriftungen_tragen_die_benutzten_konten(c):
    r = c.get("/api/datev/konten.csv?von=2026-07&bis=2026-08")
    assert r.status_code == 200
    zeilen = r.content.decode("cp1252").split("\r\n")
    kopf = zeilen[0].split(";")
    assert kopf[0] == '"EXTF"' and kopf[2] == "20"
    assert kopf[3] == '"Kontenbeschriftungen"'
    assert zeilen[1].startswith('"Konto";"Kontenbeschriftung"')
    konten = {z.split(";")[0] for z in zeilen[2:] if z}
    assert "6815" in konten and "70099" in konten
    assert '"de-DE"' in zeilen[2]


def test_kreditoren_listen_die_lieferanten(c):
    r = c.get("/api/datev/kreditoren.csv?von=2026-07&bis=2026-08")
    assert r.status_code == 200
    text = r.content.decode("cp1252")
    assert '"Konto (Vorschlag)"' in text.split("\r\n")[0]
    for _, _, lieferant, _, _, _ in BELEGE:
        assert lieferant in text
    # Fortlaufend ab 70001, alphabetisch — „Bürobedarf" steht vorn.
    erste = text.split("\r\n")[1].split(";")
    assert erste[0] == "70001" and "Bürobedarf" in erste[1]


# ── Hereinlesen ─────────────────────────────────────────────────────────

def test_roundtrip_eigener_stapel_wird_wiedererkannt(c):
    """Was babu erzeugt, muss babu lesen können — und der Abgleich gegen
    dieselben Belege darf dann keinen einzigen Unterschied finden."""
    stapel = c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-08").content
    r = c.post("/api/datev/lesen",
               files={"datei": ("EXTF.csv", stapel, "text/csv")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["summen"]["anzahl"] == 3
    assert d["summen"]["soll"] == round(284.60 + 419.90 + 119.00, 2)
    assert d["kopf"]["monate"] == ["2026-07", "2026-08"]
    g = d["abgleich"]
    assert g["zaehler"] == {"gleich": 3, "nur_datev": 0, "nur_babu": 0,
                            "abweichend": 0}
    assert "nichts geändert" in d["hinweis"]


def test_abgleich_findet_entfernte_und_veraenderte_buchung(c):
    """Eine Zeile aus dem Stapel gelöscht, eine im Betrag verändert: der
    Abgleich muss beides finden — und die veränderte NICHT als „fehlt hier,
    fehlt dort" doppelt melden."""
    text = c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-08") \
            .content.decode("cp1252")
    zeilen = [z for z in text.split("\r\n") if z]
    # Zeile 3 (der erste Beleg) fliegt raus, Zeile 4 bekommt einen anderen
    # Betrag — dieselbe Belegnummer, derselbe Tag.
    geaendert = zeilen[3].split(";")
    original = geaendert[0]
    geaendert[0] = "400,00"
    neu = "\r\n".join([zeilen[0], zeilen[1], ";".join(geaendert), zeilen[4]]) + "\r\n"
    r = c.post("/api/datev/lesen",
               files={"datei": ("EXTF.csv", neu.encode("cp1252"), "text/csv")})
    assert r.status_code == 200, r.text
    g = r.json()["abgleich"]
    assert g["zaehler"]["nur_babu"] == 1
    assert g["zaehler"]["abweichend"] == 1
    assert g["zaehler"]["nur_datev"] == 0
    assert g["nur_babu"][0]["belegfeld"] == "R-1001"
    ab = g["abweichend"][0]
    assert ab["belegfeld"] == "R-1002"
    assert ab["betrag_text"] == original.replace(",", ",")
    assert ab["betrag_datev"] == 400.0
    assert ab["differenz"] == round(400.0 - 419.90, 2)


def test_abgleich_findet_buchung_die_nur_datev_hat(c):
    text = c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-07") \
            .content.decode("cp1252")
    zeilen = [z for z in text.split("\r\n") if z]
    zusatz = zeilen[2].split(";")
    zusatz[0] = "99,00"
    zusatz[10] = '"R-9999"'
    neu = "\r\n".join(zeilen + [";".join(zusatz)]) + "\r\n"
    g = c.post("/api/datev/lesen",
               files={"datei": ("EXTF.csv", neu.encode("cp1252"), "text/csv")}
               ).json()["abgleich"]
    assert g["zaehler"]["nur_datev"] == 1
    assert g["nur_datev"][0]["belegfeld"] == "R-9999"


def test_utf8_datei_wird_auch_gelesen(c):
    text = c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-07") \
            .content.decode("cp1252")
    r = c.post("/api/datev/lesen",
               files={"datei": ("EXTF.csv", text.encode("utf-8"), "text/csv")})
    assert r.status_code == 200
    assert r.json()["summen"]["anzahl"] == 2


# ── Fehlerfälle: eine Meldung, nie eine Innenansicht ────────────────────

@pytest.mark.parametrize("name,inhalt,stueck", [
    ("leer.csv", b"", "leer"),
    ("leer.csv", b"   \r\n", "leer"),
    ("fremd.csv", "Name;Betrag\r\nMüller;12,00\r\n".encode("cp1252"), "EXTF"),
    ("falsch.csv",
     '"EXTF";700;16;"Debitoren/Kreditoren";5;20260101000000000\r\nx;y\r\n'
     .encode("cp1252"), "Buchungsstapel"),
    ("nurkopf.csv",
     '"EXTF";700;21;"Buchungsstapel";13;20260101000000000\r\n'.encode("cp1252"),
     "keine Buchungen"),
])
def test_kaputte_datei_gibt_400_mit_meldung(c, name, inhalt, stueck):
    r = c.post("/api/datev/lesen", files={"datei": (name, inhalt, "text/csv")})
    assert r.status_code == 400
    meldung = r.json()["fehler"]
    assert stueck in meldung
    assert "Traceback" not in meldung


def test_falsche_endung_wird_abgelehnt(c):
    r = c.post("/api/datev/lesen",
               files={"datei": ("stapel.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 400
    assert ".csv" in r.json()["fehler"]


def test_zu_grosse_datei_wird_abgelehnt(c):
    import datev_seite
    gross = b"x" * (datev_seite.UPLOAD_MAX + 10)
    r = c.post("/api/datev/lesen", files={"datei": ("gross.csv", gross, "text/csv")})
    assert r.status_code == 400
    assert "MB" in r.json()["fehler"]


def test_hereinlesen_ist_gebremst(c):
    """Nach `LESE_MAX` Versuchen im Fenster kommt 429 statt einer weiteren
    Antwort — unabhängig davon, ob die Datei gültig ist. Der Riegel greift
    VOR der Endungsprüfung, deshalb reicht eine abgelehnte Datei je Versuch."""
    import datev_seite
    for _ in range(datev_seite.LESE_MAX):
        r = c.post("/api/datev/lesen",
                   files={"datei": ("stapel.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 400, r.text
    r = c.post("/api/datev/lesen",
               files={"datei": ("stapel.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 429
    assert "warten" in r.json()["fehler"]


def test_kaputter_zeichensatz_meldet_das(c):
    """Bytes, die weder UTF-8 noch Windows-1252 sind — 0x81 hat in cp1252
    keine Bedeutung, in UTF-8 auch nicht als Anfang."""
    roh = b'"EXTF";700;21;"Buchungsstapel"\r\n\x81\x8d\x8f\x90\r\n'
    r = c.post("/api/datev/lesen", files={"datei": ("krumm.csv", roh, "text/csv")})
    assert r.status_code == 400
    assert "Zeichensatz" in r.json()["fehler"]


# ── Der Lese-Kern für sich, ohne Server ─────────────────────────────────

def test_stapel_lesen_findet_spalten_ueber_den_namen():
    """Die Spalten werden über ihren NAMEN gesucht, nicht über die Position
    — eine DATEV-Version, die eine Spalte einschiebt, darf den Vergleich
    nicht verschieben."""
    import datev_seite
    kopf = '"EXTF";700;21;"Buchungsstapel";13;20260101000000000;;"BA";"babu";;' \
           '0;0;20260101;4;20260701;20260731'
    spalten = 'Zusatzspalte;Umsatz (ohne Soll/Haben-Kz);Soll/Haben-Kennzeichen;' \
              'Konto;Gegenkonto (ohne BU-Schlüssel);BU-Schlüssel;Belegdatum;' \
              'Belegfeld 1;Buchungstext'
    daten = 'egal;142,60;S;6640;70099;8;2107;"R-1";"Bewirtung"'
    d = datev_seite.stapel_lesen(
        "\r\n".join([kopf, spalten, daten]).encode("cp1252"))
    b = d["buchungen"][0]
    assert (b["umsatz"], b["konto"], b["gegenkonto"]) == (142.60, "6640", "70099")
    assert (b["bu"], b["belegdatum"], b["belegfeld"]) == ("8", "2107", "R-1")
    assert b["text"] == "Bewirtung" and b["datum"] == "21.07.2026"
    assert d["monate"] == ["2026-07"]


def test_haben_zeilen_zaehlen_nicht_zum_soll():
    import datev_seite
    kopf = '"EXTF";700;21;"Buchungsstapel";13;20260101000000000;;"BA";"babu";;' \
           '0;0;20260101;4;20260701;20260731'
    spalten = ";".join(__import__("extf").SPALTEN)
    zeile = lambda betrag, sh: ";".join(  # noqa: E731
        [betrag, sh, "EUR", "", "", "", "6815", "70099", "9", "0107", '"R-1"',
         "", "", '"x"'] + [""] * (len(__import__("extf").SPALTEN) - 14))
    d = datev_seite.stapel_lesen("\r\n".join(
        [kopf, spalten, zeile("10,00", "S"), zeile("4,00", "H")]).encode("cp1252"))
    assert d["summen"]["soll"] == 10.0 and d["summen"]["haben"] == 4.0


# ── Zeichensatz und Spaltenzeile (03.09.2026) ───────────────────────────

def test_stapel_kommt_standardmaessig_in_windows_1252(c):
    r = c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-07")
    assert not r.content.startswith(b"\xef\xbb\xbf")
    assert "windows-1252" in r.headers["content-type"]
    assert r.content.decode("cp1252").startswith('"EXTF"')


def test_stapel_auf_wunsch_in_utf8(c):
    """Der echte Kanzlei-Export ist UTF-8 mit Erkennungszeichen am Anfang.
    Wer beide Dateien nebeneinanderlegt, will denselben Zeichensatz."""
    r = c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-07&zeichensatz=utf8")
    assert r.status_code == 200
    assert r.content.startswith(b"\xef\xbb\xbf")
    assert "utf-8" in r.headers["content-type"]
    text = r.content.decode("utf-8-sig")
    assert text.startswith('"EXTF"')
    # Inhaltlich dieselbe Datei — nur anders geschrieben. Verglichen wird
    # ab der Spaltenzeile: der Kopf trägt den Zeitpunkt der Erzeugung, und
    # zwischen zwei Aufrufen kann eine Sekunde liegen.
    andere = c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-07")
    assert text.split("\r\n")[1:] == \
        andere.content.decode("cp1252").split("\r\n")[1:]


def test_konten_auch_in_utf8(c):
    r = c.get("/api/datev/konten.csv?von=2026-07&bis=2026-07&zeichensatz=utf8")
    assert r.status_code == 200
    assert r.content.startswith(b"\xef\xbb\xbf")
    assert r.content.decode("utf-8-sig").split("\r\n")[0].startswith('"EXTF"')


def test_lesen_meldet_abweichende_spalten(c):
    """Eine Datei mit einer anderen Spaltenzeile wird gelesen — aber es
    steht dabei, dass sie anders aussieht als babus eigene."""
    kopf = '"EXTF";700;21;"Buchungsstapel";12;20260101000000000;;"BA";"babu";;' \
           '0;0;20260101;4;20260701;20260731'
    spalten = 'Zusatzspalte;Umsatz (ohne Soll/Haben-Kz);Soll/Haben-Kennzeichen;' \
              'Konto;Gegenkonto (ohne BU-Schlüssel);BU-Schlüssel;Belegdatum;' \
              'Belegfeld 1;Buchungstext'
    daten = 'egal;142,60;S;6640;70099;8;2107;"R-1";"Bewirtung"'
    roh = "\r\n".join([kopf, spalten, daten]).encode("cp1252")
    d = c.post("/api/datev/lesen",
               files={"datei": ("fremd.csv", roh, "text/csv")}).json()
    hinweis = d["spalten_hinweis"]
    assert hinweis
    assert "9 Spalten" in hinweis and "124" in hinweis
    assert "Stelle 1" in hinweis and "Zusatzspalte" in hinweis
    # Gelesen wurde trotzdem — die Spalten werden über den Namen gesucht.
    assert d["summen"]["anzahl"] == 1
    assert d["kopf"]["formatversion"] == "12"


def test_eigener_stapel_meldet_keine_spaltenabweichung(c):
    stapel = c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-07").content
    d = c.post("/api/datev/lesen",
               files={"datei": ("EXTF.csv", stapel, "text/csv")}).json()
    assert d["spalten_hinweis"] is None


def test_spaltenabweichung_ist_reine_rechnung():
    """Ohne Server: dieselbe Liste ist keine Abweichung, eine kürzere schon."""
    import datev_seite
    import extf
    assert datev_seite.spalten_abweichung(list(extf.SPALTEN)) is None
    kurz = datev_seite.spalten_abweichung(list(extf.SPALTEN)[:120])
    assert kurz and "120 Spalten" in kurz and "Abrechnungsreferenz" in kurz


# ── Gutschriften (03.09.2026) ───────────────────────────────────────────

def test_vorschau_zeigt_die_gutschrift_im_haben(welt_mit_gutschrift):
    """Vier Belege, einer davon eine Erstattung: sie steht positiv in der
    Umsatzspalte und im Haben — und sie MINDERT die Summe."""
    k = TestClient(welt_mit_gutschrift.app, base_url="https://testserver")
    d = k.get("/api/datev/vorschau?von=2026-07&bis=2026-08").json()
    zeilen = d["zeilen"]
    assert len(zeilen) == 4
    haben = [z for z in zeilen if z["sh"] == "H"]
    assert len(haben) == 1
    assert haben[0]["umsatz"] == "40,00"
    assert haben[0]["belegfeld"] == "GS-7"
    assert d["befund"]["gutschriften"] == 1
    assert d["befund"]["summe"] == round(284.60 + 419.90 + 119.00 - 40.00, 2)


def test_die_datei_traegt_die_gutschrift_als_haben_zeile(welt_mit_gutschrift):
    k = TestClient(welt_mit_gutschrift.app, base_url="https://testserver")
    zeilen = [z.split(";") for z in
              k.get("/api/datev/stapel.csv?von=2026-07&bis=2026-08")
              .content.decode("cp1252").split("\r\n")[2:] if z]
    gs = [z for z in zeilen if z[1] == "H"]
    assert len(gs) == 1
    assert gs[0][0] == "40,00"          # kein Minus in der Umsatzspalte
    assert all("-" not in z[0] for z in zeilen)


def test_roundtrip_mit_gutschrift_wird_wiedererkannt(welt_mit_gutschrift):
    """Was babu erzeugt, muss babu lesen — auch mit einer Gutschrift darin.
    Der Abgleich gegen dieselben Belege darf keinen Unterschied finden."""
    k = TestClient(welt_mit_gutschrift.app, base_url="https://testserver")
    stapel = k.get("/api/datev/stapel.csv?von=2026-07&bis=2026-08").content
    d = k.post("/api/datev/lesen",
               files={"datei": ("EXTF.csv", stapel, "text/csv")}).json()
    assert d["summen"]["anzahl"] == 4
    assert d["summen"]["soll"] == round(284.60 + 419.90 + 119.00, 2)
    assert d["summen"]["haben"] == 40.00
    assert d["abgleich"]["zaehler"] == {"gleich": 4, "nur_datev": 0,
                                        "nur_babu": 0, "abweichend": 0}


def test_befund_summe_ist_soll_minus_haben():
    """Ohne Server: die Zahl unter der Tabelle soll sagen, was der Monat
    gekostet hat — nicht, was durchgelaufen ist."""
    import datev_seite
    zeilen = [{"umsatz": "100,00", "sh": "S", "konto": "5100",
               "gegenkonto": "70099", "quelle": "a", "belegdatum": "0108"},
              {"umsatz": "40,00", "sh": "H", "konto": "5100",
               "gegenkonto": "70099", "quelle": "b", "belegdatum": "0208"}]
    daten = {"monate": ["2026-08"], "rahmen": "SKR04",
             "kleinunternehmerin": False,
             "je_monat": {"2026-08": {"reviews": [], "staemme": [],
                                      "ohne_konto": [], "blaetter": []}}}
    befund = datev_seite._befund(daten, zeilen)
    assert befund["summe"] == 60.00
    assert befund["summe_text"] == "60,00"
    assert befund["gutschriften"] == 1
    # Und dieselbe Rechnung je Konto.
    assert datev_seite._je_konto(zeilen)[0]["summe"] == 60.00


# ── Steuersatz-Befund auf der Seite (03.09.2026) ────────────────────────

def _daten(reviews, staemme, hinweise=None, monat="2026-07"):
    """`monat` ist der Monat des STAPELS — er muss zum Belegdatum passen,
    sonst meldet der Befund zu Recht „außerhalb des Zeitraums"."""
    return {"monate": [monat], "rahmen": "SKR04", "kleinunternehmerin": False,
            "je_monat": {monat: {"reviews": reviews, "staemme": staemme,
                                 "ohne_konto": [], "blaetter": [],
                                 "hinweise": hinweise or []}}}


def test_befund_meldet_belege_ohne_steuersatz_gelb(welt):
    import datev_seite
    import extf
    review = json.loads(json.dumps(welt.index_aktuell()["reviews"][BELEGE[0][1]]))
    review["felder"]["ust_satz"] = None
    hinweise = [dict(h, beleg="ein-beleg")
                for h in extf.pruefen(review)]
    daten = _daten([review], ["ein-beleg"], hinweise)
    befund = datev_seite._befund(daten, datev_seite._zeilen(daten))
    assert befund["ohne_steuersatz"] == ["ein-beleg"]
    assert befund["zurueckgehalten"] == []
    # Gelb heißt: die Buchung geht mit. Der Stapel bleibt sauber.
    assert befund["sauber"] is True
    assert befund["buchungen"] == 1


def test_befund_haelt_einen_ungueltigen_satz_rot_zurueck(welt):
    import datev_seite
    import extf
    review = json.loads(json.dumps(welt.index_aktuell()["reviews"][BELEGE[0][1]]))
    review["felder"]["ust_satz"] = 12
    hinweise = [dict(h, beleg="ein-beleg") for h in extf.pruefen(review)]
    daten = _daten([review], ["ein-beleg"], hinweise)
    befund = datev_seite._befund(daten, datev_seite._zeilen(daten))
    assert [z["grund"] for z in befund["zurueckgehalten"]] == \
        ["steuersatz_ungueltig"]
    assert befund["zurueckgehalten"][0]["beleg"] == "ein-beleg"
    assert "12 %" in befund["zurueckgehalten_text"]
    assert "ein-beleg" in befund["zurueckgehalten_text"]
    assert befund["sauber"] is False
    # Und die Zeile ist wirklich nicht im Stapel.
    assert befund["buchungen"] == 0


def test_derselbe_grund_an_vielen_belegen_steht_einmal_da():
    import datev_seite
    hinweise = [{"grund": "steuersatz_ungueltig", "hart": True,
                 "text": "12 % ist kein Steuersatz, den DATEV kennt.",
                 "beleg": f"beleg-{i}"} for i in range(6)]
    text = datev_seite._hinweistext(hinweise)
    assert text.count("12 %") == 1
    assert "beleg-0, beleg-1, beleg-2 und 3 weitere" in text


def test_ein_sauberer_monat_meldet_nichts_dazu(c):
    d = c.get("/api/datev/vorschau?von=2026-07&bis=2026-08").json()
    assert d["befund"]["ohne_steuersatz"] == []
    assert d["befund"]["zurueckgehalten"] == []
    assert d["befund"]["sauber"] is True


# ── Ohne Umsatzsteuer: die ganze Seite rechnet mit (03.09.2026) ─────────

@pytest.fixture()
def welt_ohne_umsatzsteuer(tmp_path, monkeypatch):
    """Derselbe Betrieb, aber mit der Kleinunternehmer-Regelung.

    Gesetzt wird die Einstellung, nicht die Antwort: `_kleinunternehmerin`
    liest sie über `monatsabschluss.umsatz_profil` aus den Stammdaten
    (Schlüssel `kleinunternehmer`), und genau dieser Weg soll geprüft sein.
    """
    bw = _welt_bauen(tmp_path, monkeypatch, BELEGE)
    bw.db_einstellung_setzen(bw.salon_von_aktiv("chef@0711.io"),
                             "kleinunternehmer", "Ja")
    return bw


def test_uebersicht_kennt_die_regelung(welt_ohne_umsatzsteuer):
    k = TestClient(welt_ohne_umsatzsteuer.app, base_url="https://testserver")
    assert k.get("/api/datev/uebersicht").json()["kleinunternehmerin"] is True


def test_stapel_der_kleinunternehmerin_zieht_keine_vorsteuer(
        welt_ohne_umsatzsteuer):
    """Die Belege stehen auf 6815 mit Schlüssel 9. Ohne Umsatzsteuer darf
    dort nichts mehr stehen — sonst zöge der Import Vorsteuer, die dieser
    Betrieb gar nicht ziehen darf."""
    k = TestClient(welt_ohne_umsatzsteuer.app, base_url="https://testserver")
    zeilen = [z.split(";") for z in
              k.get("/api/datev/stapel.csv?von=2026-07&bis=2026-08")
              .content.decode("cp1252").split("\r\n")[2:] if z]
    assert len(zeilen) == 3
    assert all(z[8] == "" for z in zeilen), "kein Steuerschlüssel im Stapel"
    # Die Vorschau zeigt dasselbe — sie darf keine eigene Rechnung aufmachen.
    d = k.get("/api/datev/vorschau?von=2026-07&bis=2026-08").json()
    assert all(z["bu"] == "" for z in d["zeilen"])
    assert d["befund"]["buchungen"] == 3


def test_mit_umsatzsteuer_steht_der_schluessel_weiter_da(c):
    zeilen = [z.split(";") for z in
              c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-08")
              .content.decode("cp1252").split("\r\n")[2:] if z]
    assert all(z[8] == "9" for z in zeilen)


# ── Berater und Mandant (03.09.2026) ────────────────────────────────────
#
# Die beiden Zahlen im Stapelkopf sagen der Kanzlei-Software, wessen
# Buchhaltung sie importiert. Sie kamen aus der Serverumgebung — richtig,
# solange ein Betrieb je Server läuft, falsch, sobald eine Kanzlei mehrere
# betreut.

def test_uebersicht_nennt_berater_und_mandant(c):
    d = c.get("/api/datev/uebersicht").json()
    assert "berater" in d and "mandant" in d
    # Ohne gesetzte Nummern steht dort die Vorbelegung „0" — und die Seite
    # sagt, dass sie fehlt.
    assert d["stammdaten_fehlen"] == ["Beraternummer", "Mandantennummer"]


def test_befund_meldet_fehlende_nummern_haelt_aber_nichts_auf(c):
    d = c.get("/api/datev/vorschau?von=2026-07&bis=2026-07").json()
    b = d["befund"]
    assert b["stammdaten_fehlen"] == ["Beraternummer", "Mandantennummer"]
    assert "von Hand" in b["stammdaten_text"]
    # Der Download bleibt erlaubt: die Buchungen sind richtig, nur der
    # Umschlag trägt keine Adresse.
    assert b["sauber"] is True
    assert c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-07") \
        .status_code == 200


def test_die_nummern_aus_babu_web_schlagen_die_umgebung(welt, monkeypatch):
    """Sobald babu_web die Nummern am Mandanten führt, gelten sie — die
    Umgebung ist nur noch der Rückweg."""
    monkeypatch.setattr(welt, "_berater_mandant", lambda: ("16149", "19364"),
                        raising=False)
    k = TestClient(welt.app, base_url="https://testserver")
    d = k.get("/api/datev/uebersicht").json()
    assert (d["berater"], d["mandant"]) == ("16149", "19364")
    assert d["stammdaten_fehlen"] == []
    kopf = k.get("/api/datev/stapel.csv?von=2026-07&bis=2026-07") \
        .content.decode("cp1252").split("\r\n")[0].split(";")
    assert kopf[10] == "16149" and kopf[11] == "19364"
    # Die Kontenbeschriftungen tragen dieselben Nummern.
    konten = k.get("/api/datev/konten.csv?von=2026-07&bis=2026-07") \
        .content.decode("cp1252").split("\r\n")[0].split(";")
    assert konten[10] == "16149" and konten[11] == "19364"
    assert k.get("/api/datev/vorschau?von=2026-07&bis=2026-07") \
        .json()["befund"]["stammdaten_fehlen"] == []


def test_ohne_babu_web_nummern_bleibt_die_umgebung(welt, monkeypatch):
    import datev_seite
    monkeypatch.setenv("BABU_BERATER", "77777")
    monkeypatch.setenv("BABU_MANDANT", "88888")
    assert datev_seite._berater_mandant(welt) == ("77777", "88888")


def test_eine_kaputte_nummernquelle_wirft_die_seite_nicht(welt, monkeypatch):
    """Die Seite soll laufen, egal in welcher Reihenfolge die Hälften
    ankommen — und auch, wenn die andere Hälfte stolpert."""
    import datev_seite

    def kaputt():
        raise RuntimeError("noch nicht da")

    monkeypatch.setattr(welt, "_berater_mandant", kaputt, raising=False)
    monkeypatch.setenv("BABU_BERATER", "12345")
    monkeypatch.setenv("BABU_MANDANT", "67890")
    assert datev_seite._berater_mandant(welt) == ("12345", "67890")


def test_was_als_nummer_durchgeht():
    import datev_seite
    for schlecht in ("", "   ", "0", "00", "keine", "1a", None):
        assert datev_seite._nummer_fehlt(schlecht) is True, schlecht
    for gut in ("1", "16149", " 19364 "):
        assert datev_seite._nummer_fehlt(gut) is False, gut


def test_die_seite_zeigt_berater_und_mandant_im_kopf(c):
    seite = c.get("/datev").text
    assert 'id="berater"' in seite and 'id="mandant"' in seite
    assert "Berater" in seite and "Mandant" in seite


# ── Der vollständige Prüfbefund (03.09.2026) ────────────────────────────

def test_befund_meldet_belegdatum_ausserhalb_des_zeitraums(welt):
    """Der Kopf der Datei nennt von und bis. Eine Buchung mit einem Datum
    davor oder danach landet im falschen Monat."""
    import datev_seite
    review = json.loads(json.dumps(welt.index_aktuell()["reviews"][BELEGE[0][1]]))
    review["felder"]["datum"] = "2026-05-14"          # Mai in einem Juli-Stapel
    daten = _daten([review], ["ein-beleg"])
    befund = datev_seite._befund(daten, datev_seite._zeilen(daten))
    assert befund["ausserhalb_zeitraum"] == 1
    assert befund["ausserhalb_zeitraum_belege"] == ["ein-beleg"]
    assert befund["sauber"] is False


def test_ein_datum_im_zeitraum_faellt_nicht_auf(welt):
    import datev_seite
    review = json.loads(json.dumps(welt.index_aktuell()["reviews"][BELEGE[0][1]]))
    daten = _daten([review], ["ein-beleg"])
    befund = datev_seite._befund(daten, datev_seite._zeilen(daten))
    assert befund["ausserhalb_zeitraum"] == 0
    assert befund["sauber"] is True


def test_befund_zaehlt_zeichen_die_ersetzt_wuerden(welt):
    import datev_seite
    review = json.loads(json.dumps(welt.index_aktuell()["reviews"][BELEGE[0][1]]))
    review["vlm"] = {"buchungstext": "Einkauf Doğan"}
    daten = _daten([review], ["ein-beleg"])
    befund = datev_seite._befund(daten, datev_seite._zeilen(daten))
    assert befund["zeichen_ersetzt"] == 1
    # Gelb: die Datei geht trotzdem, sie schreibt nur ein Fragezeichen.
    assert befund["sauber"] is True


def test_ein_sauberer_monat_zaehlt_keine_ersetzten_zeichen(c):
    assert c.get("/api/datev/vorschau?von=2026-07&bis=2026-07") \
        .json()["befund"]["zeichen_ersetzt"] == 0


def test_die_siebener_ausnahme_gilt_nur_dem_sammelkonto(welt):
    """Bis 03.09.2026 war JEDES Konto ab 70000 von der Namensprüfung
    befreit — auch ein handkorrigiertes, das dort nichts zu suchen hat."""
    import datev_seite
    import extf
    review = json.loads(json.dumps(welt.index_aktuell()["reviews"][BELEGE[0][1]]))
    review["einschaetzung"]["konto"] = "70123"
    review["einschaetzung"]["konto_skr04"] = "70123"
    daten = _daten([review], ["ein-beleg"])
    befund = datev_seite._befund(daten, datev_seite._zeilen(daten))
    assert befund["unbenannte_konten"] == ["70123"]
    # Das Sammelkonto selbst steht in jeder Zeile und wird nie gemeldet.
    assert extf.GEGENKONTO not in befund["unbenannte_konten"]


def test_befund_nennt_konten_die_die_kanzlei_noch_nicht_bestaetigt_hat(welt):
    import datev_seite
    import kontierung as kt
    offen = next(k for k in kt.ungepruefte_konten() if k.konto("SKR04"))
    review = json.loads(json.dumps(welt.index_aktuell()["reviews"][BELEGE[0][1]]))
    review["einschaetzung"]["konto"] = offen.konto("SKR04")
    review["einschaetzung"]["konto_skr04"] = offen.konto("SKR04")
    daten = _daten([review], ["ein-beleg"])
    befund = datev_seite._befund(daten, datev_seite._zeilen(daten))
    assert befund["unbestaetigte_konten"] == [offen.konto("SKR04")]
    # Gelb: sie gehen mit, es sind die besten, die babu hat.
    assert befund["sauber"] is True


def test_bestaetigte_konten_stehen_nicht_in_der_liste(c):
    d = c.get("/api/datev/vorschau?von=2026-07&bis=2026-07").json()
    assert d["befund"]["unbestaetigte_konten"] == []


def test_befund_traegt_die_kassentage_mit(welt):
    import datev_seite
    daten = _daten([], [])
    daten["je_monat"]["2026-07"]["blaetter"] = [
        {"datum": "2026-07-03", "einnahmenBar": 100, "umsatzFrei": 500},
        {"datum": "2026-07-04", "einnahmenBar": 50, "bestandVortag": 100,
         "gezaehltSchluss": 140, "differenzGrund": "verzählt"},
    ]
    befund = datev_seite._befund(daten, datev_seite._zeilen(daten))
    assert [z["grund"] for z in befund["kassen_hart"]] == \
        ["saetze_ueber_tagesumsatz"]
    assert [z["grund"] for z in befund["kassen_weich"]] == \
        ["kassenschluss_weicht_ab"]
    assert "03.07.2026" in befund["kassen_hart_text"]
    assert "verzählt" in befund["kassen_weich_text"]
    assert befund["sauber"] is False        # der harte Tag hält ihn auf


def test_die_seite_zeigt_rot_vor_gelb(c):
    """Wer die Datei gleich weitergeben will, liest die ersten Zeilen —
    dort muss stehen, was ihn davon abhalten sollte."""
    seite = c.get("/datev").text
    assert "const rot = [], gelb = []" in seite
    assert "...rot.map" in seite
    stelle_rot = seite.index("...rot.map")
    stelle_gelb = seite.index("...gelb.map")
    assert stelle_rot < stelle_gelb
    assert "Konten, die deine Kanzlei noch nicht bestätigt hat" in seite


# ── Festschreibung (03.09.2026) ─────────────────────────────────────────

def test_die_vorschaudatei_traegt_kein_festschreibungskennzeichen(c):
    """`GET stapel.csv` ist die Vorschau: sie legt nichts ab, also darf
    sie sich auch nicht als endgültig ausgeben."""
    kopf = c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-07") \
        .content.decode("cp1252").split("\r\n")[0].split(";")
    assert kopf[20] == "0"


def test_ein_freigegebener_monatsabschluss_schreibt_nicht_mehr_fest(
        welt, monkeypatch):
    """Die Freigabe der Zahlen ist ein Ereignis im Salon. Sie sagt nichts
    darüber, ob dieser Stapel schon bei der Kanzlei liegt."""
    monkeypatch.setattr(welt, "_monat_festgeschrieben", lambda m: True)
    k = TestClient(welt.app, base_url="https://testserver")
    kopf = k.get("/api/datev/stapel.csv?von=2026-07&bis=2026-07") \
        .content.decode("cp1252").split("\r\n")[0].split(";")
    assert kopf[20] == "0"


# ── Das Stapel-Siegel: übergeben, nachtragen, nicht zweimal ─────────────
#
# Vorher gab es nur „Datei erzeugt". Ob ein Monat wirklich bei der Kanzlei
# lag, stand nirgends — wer zweimal drückte, gab zweimal denselben Stapel
# ab, und die Kanzlei hatte jede Buchung doppelt.

def _box_datei(welt, pfad):
    import subprocess
    r = subprocess.run(["git", "-C", str(welt.STORE), "show", f"HEAD:{pfad}"],
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


def _box_ordner(welt, pfad):
    import subprocess
    r = subprocess.run(["git", "-C", str(welt.STORE), "ls-tree", "--name-only",
                        f"HEAD:{pfad}"], capture_output=True, text=True)
    return sorted(z for z in r.stdout.splitlines() if z) if r.returncode == 0 else []


def test_uebergabe_legt_den_stapel_ab_und_schreibt_fest(welt, c):
    r = c.post("/api/datev/uebergeben?von=2026-07&bis=2026-07")
    assert r.status_code == 200, r.text
    kopf = r.content.decode("cp1252").split("\r\n")[0].split(";")
    assert kopf[20] == "1"                     # Festschreibung
    assert kopf[16] == '"babu 2026-07"'
    assert "Buchungsstapel_2026-07.csv" in r.headers["content-disposition"]

    stand = json.loads(_box_datei(welt, "export/2026-07/stapel.json"))
    assert sorted(stand["staemme"]) == sorted(b[1] for b in BELEGE
                                              if b[0] == "2026-07")
    assert len(stand["laeufe"]) == 1
    lauf = stand["laeufe"][0]
    assert lauf["buchungen"] == 2 and lauf["von"] == "chef@0711.io"
    assert lauf["datei"].startswith("EXTF_") and lauf["datei"].endswith(".csv")
    assert lauf["datei"] in _box_ordner(welt, "export/2026-07")


def test_zweiter_uebergabe_aufruf_ist_409(c):
    """Eine Kanzlei, die denselben Stapel zweimal importiert, hat jede
    Buchung doppelt."""
    assert c.post("/api/datev/uebergeben?von=2026-07&bis=2026-07") \
        .status_code == 200
    r = c.post("/api/datev/uebergeben?von=2026-07&bis=2026-07")
    assert r.status_code == 409
    meldung = r.json()["fehler"]
    assert "Für Juli liegt alles bei der Kanzlei" in meldung
    assert "Nachtrag" in meldung


def test_neuer_beleg_nach_uebergabe_wird_nachtrag(welt, c, tmp_path):
    """Was seither dazukam, geht allein — den Rest hat die Kanzlei schon."""
    assert c.post("/api/datev/uebergeben?von=2026-07&bis=2026-07") \
        .status_code == 200

    # Ein weiterer Juli-Beleg landet in der Box.
    stamm = "20260728-120000-aaa009-nachzuegler"
    review = json.loads(json.dumps(welt.index_aktuell()["reviews"][BELEGE[0][1]]))
    review["datei"] = f"docs/2026-07/{stamm}.jpg"
    review["felder"].update(brutto=55.0, datum="28.07.2026", beleg_nr="R-1099",
                            lieferant="Nachzügler GmbH")
    review["vlm"] = {"buchungstext": "Einkauf Nachzügler"}
    import boxschreiber
    boxschreiber.schreiben(welt._box(), {
        f"docs/2026-07/{stamm}.jpg": b"\xff\xd8\xff\xe0demo",
        f"review/{stamm}.json": json.dumps(review, ensure_ascii=False).encode(),
    }, None, "nachzügler", "chef@0711.io")
    with welt._box().index_schloss:
        welt._box().invalidieren()

    r = c.post("/api/datev/uebergeben?von=2026-07&bis=2026-07")
    assert r.status_code == 200, r.text
    zeilen = [z for z in r.content.decode("cp1252").split("\r\n") if z]
    kopf = zeilen[0].split(";")
    assert kopf[16] == '"babu 2026-07 Nachtrag 2"'
    assert kopf[20] == "1"
    # NUR der neue Beleg, nicht die beiden von vorher.
    daten = [z.split(";") for z in zeilen[2:]]
    assert len(daten) == 1
    assert daten[0][10] == '"R-1099"'

    stand = json.loads(_box_datei(welt, "export/2026-07/stapel.json"))
    assert len(stand["laeufe"]) == 2
    assert stand["laeufe"][1]["staemme"] == [stamm]
    # `staemme` bleibt die Vereinigung — der Index liest nur die.
    assert stamm in stand["staemme"] and len(stand["staemme"]) == 3
    # Und im Ordner liegen jetzt zwei Dateien.
    csvs = [d for d in _box_ordner(welt, "export/2026-07") if d.endswith(".csv")]
    assert len(csvs) == 2


def test_vorschau_legt_nichts_ab(welt, c):
    """`GET stapel.csv` ist zum Ansehen. Wer ansieht, gibt nicht ab."""
    assert c.get("/api/datev/stapel.csv?von=2026-07&bis=2026-07") \
        .status_code == 200
    assert c.get("/api/datev/vorschau?von=2026-07&bis=2026-07") \
        .status_code == 200
    assert _box_datei(welt, "export/2026-07/stapel.json") is None
    assert _box_ordner(welt, "export/2026-07") == []
    # Und danach ist die Übergabe noch möglich.
    assert c.post("/api/datev/uebergeben?von=2026-07&bis=2026-07") \
        .status_code == 200


def test_uebergabe_auditiert_mit_mandant(welt, c, monkeypatch):
    gesehen = []
    import audit
    monkeypatch.setattr(audit, "audit",
                        lambda un, was, **rest: gesehen.append((un, was, rest)))
    monkeypatch.setattr(welt, "_mandant_fuers_log", lambda: "42")
    assert c.post("/api/datev/uebergeben?von=2026-07&bis=2026-07") \
        .status_code == 200
    eintrag = next(e for e in gesehen if e[1] == "datev_uebergabe")
    assert eintrag[0] == "chef@0711.io"
    assert eintrag[2]["mandant_id"] == "42"
    assert eintrag[2]["von"] == "2026-07" and eintrag[2]["bis"] == "2026-07"
    assert eintrag[2]["belege"] == 2 and eintrag[2]["buchungen"] == 2
    assert eintrag[2]["nachtrag"] == 0


def test_uebersicht_nennt_uebergabe_und_offenen_nachtrag(c):
    d = c.get("/api/datev/uebersicht").json()
    assert d["je_monat"]["2026-07"]["uebergeben_am"] is None
    assert d["je_monat"]["2026-07"]["nachtrag_offen"] == 0
    assert c.post("/api/datev/uebergeben?von=2026-07&bis=2026-07") \
        .status_code == 200
    d = c.get("/api/datev/uebersicht").json()
    tag = d["je_monat"]["2026-07"]["uebergeben_am"]
    assert tag and len(tag) == 10 and tag[2] == "." and tag[5] == "."
    assert d["je_monat"]["2026-07"]["nachtrag_offen"] == 0
    assert d["je_monat"]["2026-08"]["uebergeben_am"] is None


def test_befund_sagt_was_schon_bei_der_kanzlei_liegt(c):
    assert c.post("/api/datev/uebergeben?von=2026-07&bis=2026-07") \
        .status_code == 200
    b = c.get("/api/datev/vorschau?von=2026-07&bis=2026-07").json()["befund"]
    assert len(b["uebergeben"]) == 1
    assert b["uebergeben"][0]["buchungen"] == 2
    assert "Für Juli liegt ein Stapel vom" in b["uebergeben_text"]
    assert "(2 Buchungen)" in b["uebergeben_text"]
    assert b["nachtrag_offen"] == 0


def test_ein_monat_ohne_uebergabe_sagt_nichts_dazu(c):
    b = c.get("/api/datev/vorschau?von=2026-08&bis=2026-08").json()["befund"]
    assert b["uebergeben"] == [] and b["uebergeben_text"] is None


def test_festschreiben_ueber_den_alten_weg_ist_dieselbe_uebergabe(
        welt, c, monkeypatch):
    """`/api/export/<monat>.csv?festschreiben=1` und die DATEV-Seite dürfen
    nicht zwei Wahrheiten darüber haben, was die Kanzlei schon hat."""
    # Der alte Weg hängt an `_box_wache` (Belegweg des Salons), die
    # DATEV-Seite an `_verwalter_box_wache`. Beide führen zum selben Siegel.
    monkeypatch.setattr(welt, "box_mitglied", lambda un, mandant_id=None: True)
    r = c.get("/api/export/2026-07.csv?festschreiben=1")
    assert r.status_code == 200, r.text
    assert r.content.decode("cp1252").split("\r\n")[0].split(";")[20] == "1"
    stand = json.loads(_box_datei(welt, "export/2026-07/stapel.json"))
    assert len(stand["laeufe"]) == 1
    # Der zweite Aufruf findet nichts Neues — auf beiden Wegen.
    assert c.get("/api/export/2026-07.csv?festschreiben=1").status_code == 409
    assert c.post("/api/datev/uebergeben?von=2026-07&bis=2026-07") \
        .status_code == 409


def test_export_ohne_festschreiben_bleibt_die_vorschau(welt, c, monkeypatch):
    monkeypatch.setattr(welt, "box_mitglied", lambda un, mandant_id=None: True)
    r = c.get("/api/export/2026-07.csv")
    assert r.status_code == 200
    assert r.content.decode("cp1252").split("\r\n")[0].split(";")[20] == "0"
    assert _box_datei(welt, "export/2026-07/stapel.json") is None


def test_eine_alte_ablage_ohne_laeufe_zaehlt_als_erster_lauf(welt):
    """Vor dem Siegel schrieb babu `stapel.json` ohne `laeufe`. Das WAR ein
    Lauf — sonst zählte der nächste als erster und schickte alles noch
    einmal."""
    import boxschreiber
    alt = {"monat": "2026-07", "zeit": "20260801-101500", "von": "chef@0711.io",
           "staemme": [b[1] for b in BELEGE if b[0] == "2026-07"],
           "kassentage": []}
    boxschreiber.schreiben(welt._box(),
                           {"export/2026-07/stapel.json":
                            json.dumps(alt).encode()},
                           None, "alter stand", "chef@0711.io")
    with welt._box().index_schloss:
        welt._box().invalidieren()
    k = TestClient(welt.app, base_url="https://testserver")
    r = k.post("/api/datev/uebergeben?von=2026-07&bis=2026-07")
    assert r.status_code == 409
    assert "Juli" in r.json()["fehler"]
    d = k.get("/api/datev/uebersicht").json()
    assert d["je_monat"]["2026-07"]["uebergeben_am"] == "01.08.2026"


def test_stempeltag_liest_den_zeitpunkt():
    import datev_seite
    assert datev_seite._stempeltag("20260903-141500") == "03.09.2026"
    assert datev_seite._stempeltag("") is None
    assert datev_seite._stempeltag(None) is None
    assert datev_seite._stempeltag("krumm") is None


def test_die_seite_hat_einen_uebergabeknopf_mit_bestaetigung(c):
    """Übergeben ist etwas anderes als Herunterladen — deshalb wird
    gefragt, und deshalb steht dort, was danach gilt."""
    seite = c.get("/datev").text
    assert 'id="uebergeben"' in seite
    assert "Stapel übergeben" in seite and "Nachtrag übergeben" in seite
    assert "Danach gilt der Monat als bei der Kanzlei" in seite
    assert "was später kommt" in seite
    assert "/api/datev/uebergeben?" in seite


# ── Belegfeld 1 aus dem Stamm (03.09.2026) ─────────────────────────────
#
# Belege ohne gelesene Rechnungsnummer gingen ohne Belegfeld in den Stapel.
# Der Abgleich vergleicht dann nur noch Datum und Betrag — und ein
# geänderter Cent sieht aus wie zwei verschiedene Buchungen statt wie eine
# mit einem anderen Betrag. Jetzt trägt jeder Beleg babus eigene Nummer.

OHNE_NUMMER = [(m, s, l, b, d, "") for (m, s, l, b, d, _n) in BELEGE]


@pytest.fixture()
def welt_ohne_belegnummer(tmp_path, monkeypatch):
    return _welt_bauen(tmp_path, monkeypatch, OHNE_NUMMER)


def test_ohne_rechnungsnummer_traegt_der_stapel_die_kennung(
        welt_ohne_belegnummer):
    k = TestClient(welt_ohne_belegnummer.app, base_url="https://testserver")
    zeilen = [z.split(";") for z in
              k.get("/api/datev/stapel.csv?von=2026-07&bis=2026-08")
              .content.decode("cp1252").split("\r\n")[2:] if z]
    assert [z[10] for z in zeilen] == ['"20260714-101500-aaa001"',
                                       '"20260722-183000-aaa002"',
                                       '"20260812-093000-aaa003"']


def test_abgleich_findet_ueber_die_kennung(welt_ohne_belegnummer):
    """Der Beweis, wofür die Kennung da ist: eine im Betrag veränderte
    Zeile muss als „abweichend" herauskommen, nicht als „fehlt hier, fehlt
    dort". Genau das kann Welle 3 nur mit einem Belegfeld."""
    k = TestClient(welt_ohne_belegnummer.app, base_url="https://testserver")
    text = k.get("/api/datev/stapel.csv?von=2026-07&bis=2026-08") \
        .content.decode("cp1252")
    zeilen = [z for z in text.split("\r\n") if z]
    geaendert = zeilen[3].split(";")
    geaendert[0] = "400,00"
    neu = "\r\n".join([zeilen[0], zeilen[1], zeilen[2], ";".join(geaendert),
                       zeilen[4]]) + "\r\n"
    g = k.post("/api/datev/lesen",
               files={"datei": ("EXTF.csv", neu.encode("cp1252"), "text/csv")}
               ).json()["abgleich"]
    assert g["zaehler"] == {"gleich": 2, "nur_datev": 0, "nur_babu": 0,
                            "abweichend": 1}
    assert g["abweichend"][0]["belegfeld"] == "20260722-183000-aaa002"


def test_der_eigene_stapel_ohne_nummern_wird_wiedererkannt(
        welt_ohne_belegnummer):
    k = TestClient(welt_ohne_belegnummer.app, base_url="https://testserver")
    stapel = k.get("/api/datev/stapel.csv?von=2026-07&bis=2026-08").content
    g = k.post("/api/datev/lesen",
               files={"datei": ("EXTF.csv", stapel, "text/csv")}) \
        .json()["abgleich"]
    assert g["zaehler"] == {"gleich": 3, "nur_datev": 0, "nur_babu": 0,
                            "abweichend": 0}


# ── Rechnungserlöse: nicht im Stapel, aber im Befund (03.09.2026) ───────
#
# Eine gestellte Rechnung zählt im Monat der Zahlung als Erlös. Im Stapel
# steht sie trotzdem nicht: babu weiß, dass sie bezahlt wurde, aber nicht
# auf welchem Weg — und ein Erlös ohne Gegenkonto ist keine Buchung. Die
# Kanzlei bucht sie mit dem Kontoauszug. Der Befund sagt es, damit die
# Summe unter der Tabelle niemanden in die Irre führt.

def _rechnung(nummer="2026-0001", datum="2026-07-10", bezahlt="2026-07-20",
              netto=200.0, ust=38.0):
    return {"nummer": nummer, "datum": datum, "bezahlt_am": bezahlt,
            "netto": netto, "ust": ust, "brutto": round(netto + ust, 2),
            "saetze": [{"satz": 19, "netto": netto, "ust": ust}],
            "storniert": None, "storniert_durch": None,
            "empfaenger": {"name": "Jana Allgaier"}}


@pytest.fixture()
def welt_mit_rechnung(tmp_path, monkeypatch):
    return _welt_bauen(tmp_path, monkeypatch, BELEGE, [_rechnung()])


def test_befund_zaehlt_bezahlte_rechnungen(welt_mit_rechnung):
    k = TestClient(welt_mit_rechnung.app, base_url="https://testserver")
    b = k.get("/api/datev/vorschau?von=2026-07&bis=2026-07").json()["befund"]
    assert b["rechnungen_nicht_im_stapel"] == {"anzahl": 1, "summe": 238.0}
    assert "238,00 €" in b["rechnungen_text"]
    assert "Kontoauszug" in b["rechnungen_text"]
    # Und die Buchungen selbst bleiben, wie sie waren: die Rechnung geht
    # NICHT in den Stapel.
    assert b["buchungen"] == 2
    # Gelb, kein Mangel — der Stapel ist deshalb nicht schlechter.
    assert b["sauber"] is True


def test_eine_unbezahlte_rechnung_zaehlt_noch_nicht(tmp_path, monkeypatch):
    """Ist-Versteuerung: erst das Geld macht den Erlös. Eine gestellte,
    unbezahlte Rechnung gehört in keinen Monat."""
    bw = _welt_bauen(tmp_path, monkeypatch, BELEGE, [_rechnung(bezahlt=None)])
    k = TestClient(bw.app, base_url="https://testserver")
    b = k.get("/api/datev/vorschau?von=2026-07&bis=2026-07").json()["befund"]
    assert b["rechnungen_nicht_im_stapel"] == {"anzahl": 0, "summe": 0.0}
    assert b["rechnungen_text"] is None


def test_ein_monat_ohne_rechnungen_sagt_nichts_dazu(c):
    b = c.get("/api/datev/vorschau?von=2026-07&bis=2026-07").json()["befund"]
    assert b["rechnungen_nicht_im_stapel"]["anzahl"] == 0
    assert b["rechnungen_text"] is None


def test_die_seite_zeigt_die_rechnungen_im_befund(c):
    seite = c.get("/datev").text
    assert "rechnungen_nicht_im_stapel" in seite
    assert "stehen nicht im Stapel" in seite
