"""Befunde der Gesamtprüfung babu Expenses D1 (04.10.2026) — jeder mit seinem Test."""
import ast
import inspect
import json
import re
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

from auslagen_hilfe import BUCHUNG, auslagen_welt, einreichen, lea  # noqa: F401,E402
from test_acting_as import _login, welt2  # noqa: F401,E402

GOLDEN = HIER / "golden" / "routen.txt"
IBAN_LEA = "DE89370400440532013000"
IBAN_SALON = "DE02120300000000202051"
NUR_AUSLAGEN = {
    "GET /api/ich", "POST /api/abmelden", "POST /api/passwort",
    "GET /api/rueckmeldungen", "POST /api/rueckmeldung",
    "POST /api/rueckmeldungen/{iid}/beanstanden", "POST /api/rueckmeldungen/{iid}/freigeben",
    "GET /api/auslagen/meine", "GET /api/auslagen/meine/{stamm}",
    "GET /api/auslagen/meine/{stamm}/bild", "POST /api/auslagen/{stamm}/zurueckziehen",
    "POST /api/auslagen/konto", "POST /api/auslagen/nachrichten", "POST /api/push/geraet",
    "POST /api/aufnahme", "POST /api/buchung/einschaetzung"}


def _freigeben(chefin):
    s = chefin.get("/api/auslagen", params={"stand": "offen"}).json()["auslagen"][0]["stamm"]
    return s, chefin.post(f"/api/auslagen/{s}/freigeben")


def _salon(chefin):
    chefin.post("/api/einstellungen", json={"betrieb_name": "Salon Nina", "iban": IBAN_SALON})


# ————— C1: Mitarbeiterinnen nur über eine Positivliste —————

def test_c1_nur_auslagen_oeffnet_genau_diese_adressen():
    import mitarbeitrecht as mr  # noqa: PLC0415
    erlaubt = set()
    for zeile in GOLDEN.read_text().splitlines():
        if zeile.strip():
            methode, pfad = zeile.split(" ", 1)
            if mr.erlaubt(methode, re.sub(r"\{[^}]+\}", "x1", pfad), {"auslagen": True}):
                erlaubt.add(zeile)
    assert erlaubt == NUR_AUSLAGEN


def test_c1_rechte_oeffnen_nur_ihren_bereich():
    import mitarbeitrecht as mr  # noqa: PLC0415
    assert mr.erlaubt("GET", "/api/belege", {"belege": True})
    assert not mr.erlaubt("GET", "/api/belege", {"auslagen": True})
    assert mr.erlaubt("GET", "/api/kassenbuch/2026-05-12", {"kasse": True})
    alle = {"belege": True, "kasse": True, "auslagen": True}
    for pfad in ("/api/kundinnen", "/api/monat/2026-05", "/api/dokumente", "/api/angaben/x1"):
        assert not mr.erlaubt("GET", pfad, alle) and not mr.erlaubt("POST", pfad, alle), pfad


def test_c1_lea_sieht_den_betrieb_nicht(auslagen_welt):
    lea_c, _, _ = lea(auslagen_welt)
    for pfad in ("/api/monat/2026-05", "/api/kpi/2026-05", "/api/dokumente", "/api/ablage",
                 "/api/kassenbuch/2026-05-12", "/api/kundinnen", "/api/abgleich/2026-05",
                 "/api/rechnungen", "/api/termine", "/review/20260501-120000-aaa111-alpha"):
        assert lea_c.get(pfad).status_code in (401, 403), pfad
    assert lea_c.post("/chat", json={"frage": "Wie hoch war der Umsatz?"}).status_code in (401, 403)
    assert lea_c.get("/api/auslagen/meine").status_code == 200
    assert lea_c.get("/api/ich").status_code == 200
    assert einreichen(lea_c).status_code == 200


# ————— C2: bezahlt wird, was freigegeben wurde —————

def test_c2_der_freigegebene_betrag_gilt(auslagen_welt):
    lea_c, nina, _ = lea(auslagen_welt, belege=True)
    lea_c.post("/api/auslagen/konto", json={"iban": IBAN_LEA})
    einreichen(lea_c)
    s, r = _freigeben(nina)
    assert r.status_code == 200
    assert lea_c.post(f"/api/angaben/{s}", json={"brutto": "999,00"}).status_code == 403
    _salon(nina)
    k = nina.post("/api/auslagen/erstattung", json={"art": "ueberweisung", "staemme": [s],
                                                     "datum": "2026-05-20"}).json()["kennung"]
    assert '<InstdAmt Ccy="EUR">23.40</InstdAmt>' in nina.get(
        f"/api/auslagen/erstattung/{k}/bankdatei.xml").text


def test_c2_eine_aenderung_nach_der_freigabe_braucht_eine_neue(auslagen_welt):
    lea_c, nina, _ = lea(auslagen_welt)
    einreichen(lea_c)
    s, _ = _freigeben(nina)
    assert nina.post(f"/api/angaben/{s}", json={"brutto": "50,00"}).status_code == 200
    r = nina.post("/api/auslagen/erstattung", json={"art": "bar", "staemme": [s],
                                                     "datum": "2026-05-20"})
    assert r.status_code == 409 and "Freigabe" in r.json()["fehler"]


# ————— I1: ohne Betrag keine Freigabe —————

def test_i1_ohne_betrag_keine_freigabe(auslagen_welt):
    lea_c, nina, _ = lea(auslagen_welt)
    einreichen(lea_c, buchung=dict(BUCHUNG, betrag_eur=None))
    s = lea_c.get("/api/auslagen/meine").json()["auslagen"][0]["stamm"]
    r = nina.post(f"/api/auslagen/{s}/freigeben")
    assert r.status_code == 409 and "Betrag" in r.json()["fehler"]
    assert [k for k in nina.get("/api/datev/kreditoren").json()["eintraege"] if k["name"] == "Lea"] == []


def test_i1_eine_auslage_ohne_lesung_bleibt_fuer_die_nachlese_sichtbar(auslagen_welt, monkeypatch):
    bw = auslagen_welt["bw"]
    monkeypatch.setattr(bw, "_hintergrund_lesen_starten", lambda *a, **k: None)
    lea_c, nina, _ = lea(auslagen_welt)
    r = lea_c.post("/api/aufnahme", params={"name": "bon.jpg"},
                   files={"file": ("bon.jpg", b"\xff\xd8\xff\xe0ohne-lesung", "image/jpeg")},
                   data={"text": "Rossmann", "auslage": "1"})
    assert r.status_code == 200, r.text
    stati = {z["stamm"]: z["status"] for z in nina.get("/api/belege").json()["belege"]}
    assert "wartet" not in stati.values()


# ————— I2: nichts Schweres auf dem Ereignis-Loop —————

def test_i2_async_routen_schreiben_nicht_auf_dem_loop():
    import kern_auslagen  # noqa: PLC0415
    baum = ast.parse(inspect.getsource(kern_auslagen))
    schwer = {"_schreiben", "_aendern", "_lesen", "_erstattung_lesen", "_schloss", "_betrag"}
    for fn in ast.walk(baum):
        if isinstance(fn, ast.AsyncFunctionDef) or (
                isinstance(fn, ast.FunctionDef) and fn.name == "eingereicht_melden"):
            namen = {k.func.id for k in ast.walk(fn)
                     if isinstance(k, ast.Call) and isinstance(k.func, ast.Name)}
            assert not namen & schwer, (fn.name, namen & schwer)


# ————— I3: Detail und Kreditor-Zuordnung kennen die Auslage —————

def test_i3_detail_und_zuordnung_kennen_die_auslage(auslagen_welt):
    lea_c, nina, _ = lea(auslagen_welt)
    einreichen(lea_c)
    s, r = _freigeben(nina)
    kreditor = r.json()["kreditor"]
    assert nina.get(f"/api/beleg/{s}").json()["buchungssatz"]["gegenkonto"] == kreditor
    nina.post("/api/datev/kreditoren/einstellung", json={"modus": "einzeln"})
    assert nina.post("/api/datev/kreditoren/zuordnen",
                     json={"stamm": s, "nummer": kreditor}).status_code == 409
    belege = nina.get("/api/datev/kreditoren/belege").json()["belege"]
    assert s not in [b.get("stamm") for b in belege]


# ————— I4: der Erstattungsbeleg bleibt erreichbar —————

def test_i4_der_erstattungsbeleg_bleibt_erreichbar(auslagen_welt):
    lea_c, nina, _ = lea(auslagen_welt)
    einreichen(lea_c)
    s, _ = _freigeben(nina)
    k = nina.post("/api/auslagen/erstattung", json={"art": "bar", "staemme": [s],
                                                     "datum": "2026-05-20"}).json()["kennung"]
    liste = nina.get("/api/auslagen", params={"stand": "erstattet"}).json()["erstattungen"]
    assert [(e["kennung"], e["art"]) for e in liste] == [(k, "bar")]
    portal = (HIER.parent / "portal.html").read_text()
    assert re.search(r'href="\$\{mitMandant\([^\n]*/beleg\.pdf"\)\}"', portal)


# ————— I5: eine Kennung wird nie überschrieben —————

def test_i5_eine_kennung_wird_nie_ueberschrieben(auslagen_welt, monkeypatch):
    import auslagen as al  # noqa: PLC0415
    lea_c, nina, _ = lea(auslagen_welt)
    einreichen(lea_c)
    einreichen(lea_c)
    staemme = [z["stamm"] for z in nina.get("/api/auslagen", params={"stand": "offen"}).json()["auslagen"]]
    for s in staemme:
        nina.post(f"/api/auslagen/{s}/freigeben")
    monkeypatch.setattr(al, "naechste_kennung", lambda vorhandene, jahr: "E-2026-001")
    k1 = nina.post("/api/auslagen/erstattung", json={"art": "bar", "staemme": [staemme[0]],
                                                      "datum": "2026-05-20"}).json()["kennung"]
    k2 = nina.post("/api/auslagen/erstattung", json={"art": "bar", "staemme": [staemme[1]],
                                                      "datum": "2026-05-20"}).json()["kennung"]
    assert (k1, k2) == ("E-2026-001", "E-2026-002")


# ————— Dublette: ehrlich statt still —————

def test_dublette_einer_auslage_sagt_es_ehrlich(auslagen_welt):
    lea_c, _, _ = lea(auslagen_welt)
    daten = {"text": "Rossmann", "auslage": "1",
             "ergebnis": json.dumps({"buchung": BUCHUNG, "zeilen": []})}
    datei = {"file": ("bon.jpg", b"\xff\xd8\xff\xe0gleiches-foto", "image/jpeg")}
    assert lea_c.post("/api/aufnahme", params={"name": "bon.jpg"}, files=datei, data=daten).status_code == 200
    r = lea_c.post("/api/aufnahme", params={"name": "bon.jpg"}, files=datei, data=daten)
    assert r.status_code == 409 and "datei" not in r.json()
