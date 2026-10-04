"""Kontoumsätze aus Bankdateien: CAMT.053 und CSV (B2, 04.10.2026)."""
import io
import sys
import zipfile
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import bank_anbindung as ba  # noqa: E402
import bank_camt as bc  # noqa: E402
import kontoauszug  # noqa: E402

IBAN = "DE89370400440532013000"

CAMT = f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
 <BkToCstmrStmt><GrpHdr><MsgId>1</MsgId></GrpHdr>
  <Stmt><Id>A1</Id>
   <Acct><Id><IBAN>{IBAN}</IBAN></Id></Acct>
   <Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">1234.56</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-09-30</Dt></Dt></Bal>
   <Ntry><Amt Ccy="EUR">141.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts>BOOK</Sts>
    <BookgDt><Dt>2026-09-03</Dt></BookgDt><ValDt><Dt>2026-09-03</Dt></ValDt>
    <AcctSvcrRef>REF-1</AcctSvcrRef><AddtlNtryInf>SEPA-Lastschrift</AddtlNtryInf>
    <NtryDtls><TxDtls><RltdPties><Cdtr><Nm>Friseur Grosshandel Wagner</Nm></Cdtr>
     <CdtrAcct><Id><IBAN>DE02120300000000202051</IBAN></Id></CdtrAcct></RltdPties>
     <RmtInf><Ustrd>Rechnung 4711</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
   <Ntry><Amt Ccy="EUR">1250.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
    <BookgDt><Dt>2026-09-15</Dt></BookgDt>
    <NtryDtls><TxDtls><RltdPties><Dbtr><Nm>Salonkee GmbH</Nm></Dbtr></RltdPties>
     <RmtInf><Ustrd>Auszahlung September</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>
   <Ntry><Amt Ccy="EUR">9.90</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts>BOOK</Sts>
    <BookgDt><Dt>2026-09-30</Dt></BookgDt>
    <BkTxCd><Domn><Cd>PMNT</Cd><Fmly><Cd>ACCB</Cd><SubFmlyCd>CHRG</SubFmlyCd></Fmly></Domn></BkTxCd>
    <AddtlNtryInf>Kontoführung</AddtlNtryInf></Ntry>
   <Ntry><Amt Ccy="EUR">50.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts>PDNG</Sts>
    <BookgDt><Dt>2026-09-30</Dt></BookgDt></Ntry>
  </Stmt></BkToCstmrStmt></Document>""".encode()


def test_camt_wird_gelesen():
    d = bc.lesen(CAMT, "auszug.xml")
    assert d["art"] == "camt"
    assert [(u["buchung"], u["betrag"]) for u in d["umsaetze"]] == [
        ("2026-09-03", -141.0), ("2026-09-15", 1250.0), ("2026-09-30", -9.9)]
    wagner = d["umsaetze"][0]
    assert (wagner["gegenpartei"], wagner["gegen_iban"], wagner["zweck"]) == (
        "Friseur Grosshandel Wagner", "DE02120300000000202051", "Rechnung 4711")
    assert d["umsaetze"][2]["art"] == "Entgelt"
    assert d["konten"] == [{"iban": IBAN, "von": "2026-09-03", "bis": "2026-09-30",
                            "saldo": {"betrag": 1234.56, "datum": "2026-09-30"}}]


def test_dieselbe_datei_gibt_dieselben_kennungen():
    a = [u["id"] for u in bc.lesen(CAMT)["umsaetze"]]
    assert a == [u["id"] for u in bc.lesen(CAMT)["umsaetze"]]
    assert len(set(a)) == 3


def test_camt_mit_doctype_wird_abgelehnt():
    boese = CAMT.replace(b'<?xml version="1.0" encoding="UTF-8"?>',
                         b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]>')
    with pytest.raises(bc.ImportFehler, match="DOCTYPE"):
        bc.lesen(boese)


def test_camt_im_zip():
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("2026-09-03.xml", CAMT)
        z.writestr("liesmich.txt", "x")
    assert len(bc.lesen(puffer.getvalue(), "auszuege.zip")["umsaetze"]) == 3


def test_sparkassen_csv():
    roh = ('"Auftragskonto";"Buchungstag";"Valutadatum";"Buchungstext";"Verwendungszweck";'
           '"Beguenstigter/Zahlungspflichtiger";"Kontonummer/IBAN";"Betrag";"Waehrung"\n'
           f'"{IBAN}";"03.09.26";"03.09.26";"FOLGELASTSCHRIFT";"Rechnung 4711";'
           '"Friseur Grosshandel Wagner";"DE02120300000000202051";"-141,00";"EUR"\n'
           f'"{IBAN}";"15.09.26";"15.09.26";"GUTSCHRIFT";"Auszahlung";"Salonkee GmbH";"";"1.250,00";"EUR"\n')
    d = bc.lesen(roh.encode("cp1252"), "umsaetze.csv")
    assert d["art"] == "csv"
    assert [(u["buchung"], u["betrag"], u["art"]) for u in d["umsaetze"]] == [
        ("2026-09-03", -141.0, "FOLGELASTSCHRIFT"), ("2026-09-15", 1250.0, "GUTSCHRIFT")]


def test_csv_mit_vorspann_und_soll_haben_braucht_die_iban():
    roh = ("Umsätze Girokonto\nZeitraum: 01.09.2026 - 30.09.2026\n\n"
           "Buchung;Valuta;Auftraggeber/Empfänger;Verwendungszweck;Soll;Haben\n"
           "03.09.2026;03.09.2026;Wagner;Rechnung 4711;141,00;\n"
           "15.09.2026;15.09.2026;Salonkee;Auszahlung;;1250,00\n")
    with pytest.raises(bc.ImportFehler, match="IBAN"):
        bc.lesen(roh.encode("utf-8"))
    d = bc.lesen(roh.encode("utf-8"), iban="de89 3704 0044 0532 0130 00")
    assert [u["betrag"] for u in d["umsaetze"]] == [-141.0, 1250.0]
    assert d["umsaetze"][0]["iban"] == IBAN


def test_unbekannte_spalten_lassen_sich_zuordnen():
    roh = "Tag;Wert;Wer\n03.09.2026;-141,00;Wagner\n".encode()
    with pytest.raises(bc.ImportFehler) as f:
        bc.lesen(roh, iban=IBAN)
    assert f.value.spalten == ["Tag", "Wert", "Wer"]
    d = bc.lesen(roh, iban=IBAN, spalten={"buchung": "Tag", "betrag": "Wert",
                                          "gegenpartei": "Wer"})
    assert d["umsaetze"][0]["gegenpartei"] == "Wagner"


# ————— Das Modell —————

def test_zusammenfuehren_legt_nichts_doppelt_an():
    u = bc.lesen(CAMT)["umsaetze"]
    alle, neu = ba.zusammenfuehren(u[:2], u)
    assert (len(alle), neu) == (3, 1)


def test_im_alten_format_versteht_der_abgleich_die_umsaetze():
    alt = [ba.als_alt(u) for u in bc.lesen(CAMT)["umsaetze"]]
    assert alt[0]["datum"] == "03.09.2026" and alt[0]["text"].startswith("Friseur")
    ab = kontoauszug.abgleich(alt, [{"brutto": 141.0, "datum": "2026-09-02", "stamm": "s1"}])
    status = [p["status"] for p in ab["positionen"]]
    assert status == ["gedeckt", "einnahme", "bank"]


def test_pdf_umsaetze_aus_derselben_zeit_fallen_weg():
    importiert = [ba.als_alt(u) for u in bc.lesen(CAMT)["umsaetze"]]
    pdf = [{"datum": "03.09.2026", "betrag": -141.0, "text": "Wagner"},
           {"datum": "01.08.2026", "betrag": -20.0, "text": "nur im PDF"}]
    assert ba.ohne_doppelte_pdf(importiert, pdf) == [pdf[1]]
