"""Auszahlung an Ambassadorinnen (kern_auszahlung, gutschrift, sepa — seit 03.10.2026).

Profil (Konto, Anschrift, Steuerstatus, Zustimmung) → Vorschau → Lauf mit
Gutschrift je Ambassadorin und EINER Bankdatei → überwiesen bestätigt. Was
geprüft wird: Pflichtangaben auf der Gutschrift, lückenlose Nummern, USt
nur bei Umsatzsteuerpflicht, Summen in der Bankdatei, nichts doppelt, und
dass nur der Betreiber den Lauf sieht.
"""
import base64
import datetime as dt
import io
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import babu_web  # noqa: E402
import gutschrift  # noqa: E402
import kern_ambassador as ka  # noqa: E402
import sepa  # noqa: E402

PASSWORT = "ein-langes-passwort-hier"
D = dt.date
NS = {"p": sepa.NS}


def _login(email):
    c = TestClient(babu_web.app, base_url="https://testserver")
    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    assert c.post("/api/login", json={"email": email, "passwort": PASSWORT}).status_code == 200
    return c


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "ROLLEN", {})
    monkeypatch.setattr(ka, "_heute", lambda: D(2027, 1, 15))
    for name, wert in (("BABU_FIRMA_NAME", "0711 Intelligence GmbH"),
                       ("BABU_FIRMA_ANSCHRIFT", "Musterstraße 1|70173 Stuttgart"),
                       ("BABU_FIRMA_USTID", "DE123456789"),
                       ("BABU_AUSZAHLUNG_IBAN", "DE89370400440532013000")):
        monkeypatch.setenv(name, wert)
    monkeypatch.delenv("BABU_PROVISION_KARENZ_TAGE", raising=False)
    post = []
    import postfach
    monkeypatch.setattr(postfach, "senden", lambda an, betreff, text, *, stempel: (
        post.append((an, betreff, text)) or (True, "ok")))
    for email, rolle in (("chef@0711.io", "admin"), ("kanzlei@afflek.de", "kanzlei"),
                         ("babs@salon.de", "salon"), ("ute@salon.de", "salon")):
        babu_web.nutzer_anlegen(email, email.split("@")[0], "Salon", rolle,
                                passwort=PASSWORT, box=False)
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        for code, email, name in (("BABS-1", "babs@salon.de", "Babs"),
                                  ("UTE-1", "ute@salon.de", "Ute")):
            c.execute("INSERT INTO ambassador (code, email, name, erstellt, verdient) "
                      "VALUES (?,?,?,'2026-10-01', 0)", (code, email, name))

        def buchung(code, email, meilenstein, betrag, datum):
            c.execute("INSERT INTO ambassador_buchung (code, email, salon, meilenstein, "
                      "betrag, datum, quelle, paket) VALUES (?,?,?,?,?,?,'stripe','salon')",
                      (code, email, "Salon " + email[0].upper(), meilenstein, betrag, datum))
            c.execute("UPDATE ambassador SET verdient = verdient + ? WHERE code=?",
                      (betrag, code))
        buchung("BABS-1", "a@s.de", "gezeichnet", 237, "2026-11-02")
        buchung("BABS-1", "b@s.de", "gezeichnet", 117, "2026-12-20")
        buchung("BABS-1", "c@s.de", "gezeichnet", 447, "2027-01-03")   # nächstes Quartal
        buchung("UTE-1", "d@s.de", "gezeichnet", 60, "2026-10-10")    # unter 100 €
    return {"post": post, "chef": _login("chef@0711.io"), "babs": _login("babs@salon.de"),
            "ute": _login("ute@salon.de")}


PROFIL = {"kontoinhaber": "Bärbel Müßig", "iban": "DE02 1203 0000 0000 2020 51",
          "strasse": "Lindenweg 3", "plz": "71634", "ort": "Ludwigsburg",
          "steuerstatus": "ust", "steuernummer": "71/123/45678", "zustimmung": True}


# ————— reine Teile —————

def test_umschrift_auf_sepa_zeichen():
    assert sepa.umschrift("Bärbel Müßig & Co. „Salon“ — süß", 70) == \
        "Baerbel Muessig + Co. Salon - suess"
    assert len(sepa.umschrift("x" * 200, 140)) == 140


def test_bankdatei_summen_und_felder():
    xml = sepa.pain001(msg_id="BABU-1", erstellt=dt.datetime(2027, 1, 15, 9),
                       ausfuehrung=D(2027, 1, 15),
                       schuldner={"name": "0711", "iban": "DE89 3704 0044 0532 0130 00"},
                       zahlungen=[{"e2e": "GS-2027-0001", "betrag_cent": 42369, "name": "A",
                                   "iban": "DE02120300000000202051", "zweck": "x"},
                                  {"e2e": "GS-2027-0002", "betrag_cent": 11700, "name": "B",
                                   "iban": "DE02120300000000202051", "zweck": "y"}])
    w = ET.fromstring(xml)
    assert w.find("p:CstmrCdtTrfInitn/p:GrpHdr/p:CtrlSum", NS).text == "540.69"
    assert w.find("p:CstmrCdtTrfInitn/p:GrpHdr/p:NbOfTxs", NS).text == "2"
    block = w.find("p:CstmrCdtTrfInitn/p:PmtInf", NS)
    assert block.find("p:DbtrAcct/p:Id/p:IBAN", NS).text == "DE89370400440532013000"
    betraege = [e.text for e in block.findall("p:CdtTrfTxInf/p:Amt/p:InstdAmt", NS)]
    assert betraege == ["423.69", "117.00"]
    assert [e.text for e in block.findall("p:CdtTrfTxInf/p:PmtId/p:EndToEndId", NS)] == \
        ["GS-2027-0001", "GS-2027-0002"]


def test_bankdatei_ohne_oder_mit_negativem_betrag():
    with pytest.raises(ValueError):
        sepa.pain001(msg_id="x", erstellt=dt.datetime.now(), ausfuehrung=D(2027, 1, 15),
                     schuldner={"name": "x", "iban": "x"}, zahlungen=[])
    with pytest.raises(ValueError):
        sepa.pain001(msg_id="x", erstellt=dt.datetime.now(), ausfuehrung=D(2027, 1, 15),
                     schuldner={"name": "x", "iban": "x"},
                     zahlungen=[{"e2e": "a", "betrag_cent": -1, "name": "a",
                                 "iban": "a", "zweck": "a"}])


def _text(pdf: bytes) -> str:
    pdfium = pytest.importorskip("pypdfium2")
    dok = pdfium.PdfDocument(pdf)
    return "".join(dok[i].get_textpage().get_text_range() for i in range(len(dok)))


@pytest.mark.parametrize("status,titel,muss,darf_nicht", [
    ("ust", "Gutschrift", ["Umsatzsteuer 19 %", "45,03", "282,03", "§ 14 Abs. 2"], ["§ 19"]),
    ("klein", "Gutschrift", ["§ 19 UStG", "237,00", "§ 14 Abs. 2"], ["Umsatzsteuer 19 %"]),
    ("privat", "Provisionsabrechnung", ["Privatperson", "237,00"],
     ["Umsatzsteuer 19 %", "§ 14 Abs. 2"]),
])
def test_gutschrift_je_steuerstatus(status, titel, muss, darf_nicht):
    ust = 4503 if status == "ust" else 0
    beleg = {"nr": "GS-2027-0001", "datum": "2027-01-15", "von": "2026-10-01",
             "bis": "2026-12-31",
             "aussteller": {"name": "0711 Intelligence GmbH",
                            "anschrift": "Musterstraße 1\n70173 Stuttgart",
                            "ust_id": "DE123456789"},
             "empfaengerin": {"name": "Bärbel", "anschrift": "Weg 3\n71634 Lb",
                              "steuerstatus": status, "steuernummer": "71/1",
                              "ust_id": None, "iban": "DE02120300000000202051"},
             "posten": [{"datum": "2026-11-02", "salon": "Salon A",
                         "meilenstein": "gezeichnet", "paket": "salon",
                         "netto_cent": 23700}],
             "netto_cent": 23700, "ust_cent": ust, "brutto_cent": 23700 + ust,
             "zustimmung_am": "2026-10-05T10:00:00Z"}
    t = _text(gutschrift.pdf(beleg))
    assert f"{titel} GS-2027-0001" in t
    for wort in muss + ["0711 Intelligence GmbH", "DE123456789", "Leistungszeitraum",
                        "DE… 2051"]:
        assert wort in t, wort
    for wort in darf_nicht + ["ENTWURF", "DE02120300000000202051"]:
        assert wort not in t, wort


# ————— Profil —————

def test_profil_pruefen_und_maskiert_zeigen(welt):
    b = welt["babs"]
    assert b.get("/api/ambassador/profil").json()["fehlt"] == [
        "Kontodaten", "Anschrift", "Steuerangabe", "Zustimmung"]
    assert b.post("/api/ambassador/profil", json=dict(PROFIL, iban="DE00 1234")).status_code == 400
    assert b.post("/api/ambassador/profil", json=dict(PROFIL, plz="123")).status_code == 400
    assert b.post("/api/ambassador/profil", json=dict(PROFIL, zustimmung=False)).status_code == 400
    assert b.post("/api/ambassador/profil",
                  json=dict(PROFIL, steuernummer="", ust_id="")).status_code == 400
    r = b.post("/api/ambassador/profil", json=PROFIL)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["fehlt"] == [] and d["iban"] == "DE… 2051"
    assert "0000" not in str(b.get("/api/ambassador/profil").json())
    me = b.get("/api/ambassador/me").json()
    assert me["profil_vollstaendig"] is True and me["gutschriften"] == []


def test_privatperson_braucht_keine_steuernummer(welt):
    r = welt["ute"].post("/api/ambassador/profil",
                         json=dict(PROFIL, steuerstatus="privat", steuernummer=""))
    assert r.status_code == 200 and r.json()["fehlt"] == []


def test_neue_iban_meldet_sich_per_mail(welt):
    welt["babs"].post("/api/ambassador/profil", json=PROFIL)
    welt["babs"].post("/api/ambassador/profil",
                      json=dict(PROFIL, iban="DE89370400440532013000"))
    assert any("Kontoverbindung" in p[1] for p in welt["post"])


def test_profil_nur_fuer_ambassadorinnen(welt):
    assert welt["chef"].get("/api/ambassador/profil").status_code == 404


# ————— Lauf —————

def _lauf_vorbereiten(welt):
    welt["babs"].post("/api/ambassador/profil", json=PROFIL)
    welt["ute"].post("/api/ambassador/profil",
                     json=dict(PROFIL, kontoinhaber="Ute", steuerstatus="privat"))


def test_vorschau(welt):
    welt["babs"].post("/api/ambassador/profil", json=PROFIL)
    v = welt["chef"].get("/api/auszahlung/vorschau").json()
    assert (v["lauf"], v["stichtag"]) == ("2027-01-15", "2026-12-31")
    babs, ute = sorted(v["zeilen"], key=lambda z: z["code"])
    assert (babs["netto_cent"], babs["ust_cent"], babs["brutto_cent"]) == (35400, 6726, 42126)
    assert babs["zahlbar"] is True and babs["posten"] == 2      # 447 € kommt im April
    assert ute["zahlbar"] is False and ute["grund"] == "unter 100 €"


def test_lauf_nur_fuer_den_betreiber(welt):
    for pfad in ("/api/auszahlung/vorschau", "/api/auszahlung/laeufe"):
        assert welt["babs"].get(pfad).status_code == 403
        assert _login("kanzlei@afflek.de").get(pfad).status_code == 403
    assert _login("kanzlei@afflek.de").post("/api/auszahlung/lauf").status_code == 403


def test_ganzer_lauf(welt):
    _lauf_vorbereiten(welt)
    r = welt["chef"].post("/api/auszahlung/lauf")
    assert r.status_code == 200, r.text
    lauf = r.json()
    assert lauf["anzahl"] == 1 and lauf["summe_cent"] == 42126
    # Zweimal geht nicht.
    assert welt["chef"].post("/api/auszahlung/lauf").status_code == 409
    # Vor „überwiesen" sieht die Ambassadorin nichts, das Geld ist nicht ausgezahlt.
    me = welt["babs"].get("/api/ambassador/me").json()
    assert me["gutschriften"] == [] and me["gezahlt"] == 0
    assert welt["babs"].get("/api/ambassador/gutschrift/GS-2027-0001.pdf").status_code == 404

    xml = welt["chef"].get(f"/api/auszahlung/lauf/{lauf['id']}/sepa.xml")
    assert xml.status_code == 200
    w = ET.fromstring(xml.content)
    tx = w.find("p:CstmrCdtTrfInitn/p:PmtInf/p:CdtTrfTxInf", NS)
    assert tx.find("p:Amt/p:InstdAmt", NS).text == "421.26"
    assert tx.find("p:Cdtr/p:Nm", NS).text == "Baerbel Muessig"
    assert tx.find("p:PmtId/p:EndToEndId", NS).text == "GS-2027-0001"

    z = zipfile.ZipFile(io.BytesIO(
        welt["chef"].get(f"/api/auszahlung/lauf/{lauf['id']}/gutschriften.zip").content))
    assert z.namelist() == ["GS-2027-0001.pdf"]
    t = _text(z.read("GS-2027-0001.pdf"))
    assert "Gutschrift GS-2027-0001" in t and "421,26" in t and "Salon A" in t

    assert welt["chef"].post(f"/api/auszahlung/lauf/{lauf['id']}/ueberwiesen").status_code == 200
    me = welt["babs"].get("/api/ambassador/me").json()
    assert me["gezahlt"] == 354 and me["gutschriften"][0]["nr"] == "GS-2027-0001"
    assert welt["babs"].get("/api/ambassador/gutschrift/GS-2027-0001.pdf").status_code == 200
    # Andere sehen fremde Gutschriften nicht.
    assert welt["ute"].get("/api/ambassador/gutschrift/GS-2027-0001.pdf").status_code == 404
    assert any("Provision ist unterwegs" in p[1] and p[0] == "babs@salon.de"
               for p in welt["post"])
    # Die 447 € aus Januar bleiben offen für den April-Lauf.
    assert me["geld"]["offen"] == 447
    assert welt["chef"].post(f"/api/auszahlung/lauf/{lauf['id']}/verwerfen").status_code == 409


def test_verwerfen_gibt_die_provision_frei_und_die_nummer_bleibt(welt):
    _lauf_vorbereiten(welt)
    erster = welt["chef"].post("/api/auszahlung/lauf").json()
    assert welt["chef"].post(f"/api/auszahlung/lauf/{erster['id']}/verwerfen").status_code == 200
    zweiter = welt["chef"].post("/api/auszahlung/lauf").json()
    assert zweiter["anzahl"] == 1
    laeufe = welt["chef"].get("/api/auszahlung/laeufe").json()["laeufe"]
    nummern = {(g["nr"], g["status"]) for l in laeufe for g in l["gutschriften"]}
    assert nummern == {("GS-2027-0001", "storniert"), ("GS-2027-0002", "erstellt")}


def test_storno_wird_verrechnet(welt):
    _lauf_vorbereiten(welt)
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("INSERT INTO ambassador_buchung (code, email, salon, meilenstein, betrag, "
                  "datum, quelle) VALUES ('BABS-1', 'b@s.de', 'Salon B', "
                  "'storno_gezeichnet', -117, '2026-12-28', 'stripe')")
    v = welt["chef"].get("/api/auszahlung/vorschau").json()
    babs = next(z for z in v["zeilen"] if z["code"] == "BABS-1")
    assert babs["netto_cent"] == 23700 and babs["posten"] == 3


def test_karenz_haelt_junge_provision_zurueck(welt, monkeypatch):
    _lauf_vorbereiten(welt)
    monkeypatch.setenv("BABU_PROVISION_KARENZ_TAGE", "20")
    v = welt["chef"].get("/api/auszahlung/vorschau").json()
    babs = next(z for z in v["zeilen"] if z["code"] == "BABS-1")
    assert babs["netto_cent"] == 23700        # die 117 € vom 20.12. warten


def test_ohne_gueltiges_konto_gibt_es_die_ueberweisungsliste(welt, monkeypatch):
    """Wie bei Camp45 ohne hinterlegtes Konto (09.10.2026): live standen 16
    Ziffern als IBAN und 8 als USt-IdNr. in der .env. Dann entstehen die
    Gutschriften trotzdem — ohne die falsche USt-IdNr. —, statt der
    Bankdatei gibt es eine Überweisungsliste."""
    _lauf_vorbereiten(welt)
    monkeypatch.setenv("BABU_AUSZAHLUNG_IBAN", "1234567890123456")
    monkeypatch.setenv("BABU_FIRMA_USTID", "12345678")
    v = welt["chef"].get("/api/auszahlung/vorschau").json()
    assert v["konto_fehlt"] is False and v["bankdatei"] is False
    r = welt["chef"].post("/api/auszahlung/lauf")
    assert r.status_code == 200, r.text
    lauf = r.json()["id"]
    l = welt["chef"].get("/api/auszahlung/laeufe").json()["laeufe"][0]
    assert l["id"] == lauf and l["bankdatei"] is False
    assert welt["chef"].get(f"/api/auszahlung/lauf/{lauf}/sepa.xml").status_code == 404
    liste = welt["chef"].get(f"/api/auszahlung/lauf/{lauf}/ueberweisungen.csv")
    assert liste.status_code == 200
    zeilen = liste.content.decode("utf-8-sig").splitlines()
    assert zeilen[0].startswith("Empfängerin;IBAN;BIC;Betrag")
    assert len(zeilen) >= 2 and "GS-" in zeilen[1] and ";" in zeilen[1]
    import kern_auszahlung
    assert kern_auszahlung.firma()["ust_id"] == ""      # 8 Ziffern druckt babu nicht


def test_ohne_firmennamen_kein_lauf(welt, monkeypatch):
    _lauf_vorbereiten(welt)
    monkeypatch.delenv("BABU_FIRMA_NAME")
    r = welt["chef"].post("/api/auszahlung/lauf")
    assert r.status_code == 409 and "Firmenname" in r.json()["fehler"]


def test_nummern_laufen_je_jahr(welt):
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert gutschrift.nummer(c, 2027) == "GS-2027-0001"
        c.execute("INSERT INTO ambassador_auszahlung (code, betrag, datum, stichtag, von, "
                  "gutschrift_nr) VALUES ('BABS-1', 1, '2027-01-15', '2026-12-31', 'x', "
                  "'GS-2027-0009')")
        assert gutschrift.nummer(c, 2027) == "GS-2027-0010"
        assert gutschrift.nummer(c, 2028) == "GS-2028-0001"


def test_pdf_ist_gespeichert_wie_ausgestellt(welt):
    _lauf_vorbereiten(welt)
    welt["chef"].post("/api/auszahlung/lauf")
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        pdf, beleg = c.execute("SELECT pdf, beleg FROM ambassador_auszahlung").fetchone()
    assert base64.b64decode(pdf)[:5] == b"%PDF-"
    assert '"iban": "DE02120300000000202051"' in beleg
