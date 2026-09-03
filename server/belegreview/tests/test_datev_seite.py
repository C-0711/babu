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


def _welt_bauen(tmp_path, monkeypatch, belege):
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
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "demo"],
                   check=True, capture_output=True)
    bare = tmp_path / "babu.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)],
                   check=True)

    import babu_web
    monkeypatch.setattr(babu_web, "STORE", bare)
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

def _daten(reviews, staemme, hinweise=None, monat="2026-08"):
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
