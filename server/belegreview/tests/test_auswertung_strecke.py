"""Die Strecke von der Startseite bis ins Profil.

    E-Mail eintragen → Unterlagen hochladen → lesen → Mail mit Link
                     → Passwort zweimal → Konto → Bericht → ins Profil

Sechs Übergänge, und an jedem kann etwas verloren gehen, ohne dass es
auffällt: ein Schlüssel, der zweimal gilt; eine Auskunft darüber, welche
Adressen ein Konto haben; eine Mail, die nirgends landet; ein Profil, das
ungefragt überschrieben wird.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent


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

    sys.path.insert(0, str(HIER.parent))
    import babu_web
    import postfach
    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "AUSWERTUNG_TMP", tmp_path / "auswertung-tmp")
    monkeypatch.setattr(babu_web, "BASIS_URL", "https://babu.test")
    monkeypatch.setattr(postfach, "POSTAUSGANG", tmp_path / "post")
    monkeypatch.setattr(postfach, "HOST", "")          # kein Versand eingerichtet
    babu_web._AUSWERTUNG_ZULETZT.clear()
    return babu_web, tmp_path


def kunde(bw):
    return TestClient(bw.app, base_url="https://testserver")


ZAHLEN = {"umsatz": 172807.49, "wareneinsatz": 63122.03, "personal": 27548.99,
          "raumkosten": 26276.89, "steuerberatung": 15518.40, "afa": 7777.51,
          "sonstige_kosten": 16122.19, "gewinn": 16441.48, "ust_zahllast": None,
          "est_vorauszahlungen": None}
STAMM = {"rechtsform": "Einzelunternehmen", "steuernummer": "71 015 73457",
         "finanzamt": "Ludwigsburg", "kleinunternehmer": None}


def lesen_faelschen(bw, monkeypatch):
    """Das Lesen selbst hat eigene Tests — hier zählt die Strecke drumherum."""
    import abschluss_lesen
    monkeypatch.setattr(abschluss_lesen, "dokument_lesen",
                        lambda pfad, **kw: {"datei": Path(pfad).name, "art": "euer",
                                            "seiten": 8, "lane": "text",
                                            "werte": dict(ZAHLEN, **STAMM),
                                            "afa_liste": []})


def durchlauf(bw, monkeypatch, mail="salon@example.de"):
    """Anfordern → hochladen → lesen. Gibt (client, Postausgangsdatei) zurück."""
    lesen_faelschen(bw, monkeypatch)
    c = kunde(bw)
    a = c.post("/api/auswertung/anfordern", json={"email": mail})
    assert a.status_code == 200, a.text
    korb = a.json()["korb"]
    u = c.post("/api/auswertung/unterlage?korb=" + korb + "&name=euer.pdf",
               content=b"%PDF-1.4 nur ein Platzhalter")
    assert u.status_code == 200, u.text
    l = c.post("/api/auswertung/lesen?korb=" + korb + "&jahr=2024")
    assert l.status_code == 200, l.text
    # Das Lesen läuft im Hintergrund — abwarten statt raten.
    for _ in range(200):
        stand = c.get("/api/auswertung/stand?korb=" + korb).json()["stand"]
        if stand != "liest":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("das Lesen wurde nicht fertig")
    assert stand in ("fertig", "wartet_auf_post"), stand
    return c, korb


def brief(tmp_path):
    posten = sorted((tmp_path / "post").glob("*.eml"))
    assert posten, "keine Nachricht im Postausgang"
    return posten[-1].read_text(encoding="utf-8", errors="replace")


def schluessel_aus(text):
    import re
    m = re.search(r"/auswertung/([A-Za-z0-9_-]{20,})", text.replace("=\n", ""))
    assert m, text[:800]
    return m.group(1)


# ————— Anfordern —————

def test_eine_adresse_bekommt_einen_korb(welt):
    bw, _ = welt
    a = kunde(bw).post("/api/auswertung/anfordern", json={"email": "s@example.de"})
    assert a.status_code == 200
    assert a.json()["korb"]
    assert "Postfach" in a.json()["hinweis"]


def test_eine_kaputte_adresse_wird_abgelehnt(welt):
    bw, _ = welt
    a = kunde(bw).post("/api/auswertung/anfordern", json={"email": "kein-mail"})
    assert a.status_code == 400


def test_die_antwort_verraet_nicht_ob_es_das_konto_gibt(welt):
    """Sonst ist das Formular ein Melder, welche Betriebe babu benutzen."""
    bw, _ = welt
    c = kunde(bw)
    c.post("/api/signup", json={"salon": "S", "email": "da@example.de",
                                "passwort": "passwort-lang"})
    bw._AUSWERTUNG_ZULETZT.clear()
    neu = kunde(bw).post("/api/auswertung/anfordern", json={"email": "neu@example.de"})
    bw._AUSWERTUNG_ZULETZT.clear()
    alt = kunde(bw).post("/api/auswertung/anfordern", json={"email": "da@example.de"})
    assert neu.status_code == alt.status_code == 200
    assert neu.json()["hinweis"] == alt.json()["hinweis"]
    assert bool(neu.json().get("korb")) == bool(alt.json().get("korb"))


def test_zu_schnell_hintereinander_wird_gebremst(welt):
    bw, _ = welt
    c = kunde(bw)
    assert c.post("/api/auswertung/anfordern", json={"email": "a@example.de"}).status_code == 200
    assert c.post("/api/auswertung/anfordern", json={"email": "b@example.de"}).status_code == 429


# ————— Hochladen —————

def test_ohne_gueltigen_korb_geht_nichts_hoch(welt):
    bw, _ = welt
    a = kunde(bw).post("/api/auswertung/unterlage?korb=erfunden&name=x.pdf",
                       content=b"x")
    assert a.status_code == 403


def test_ein_fremdes_format_wird_abgelehnt(welt):
    bw, _ = welt
    c = kunde(bw)
    korb = c.post("/api/auswertung/anfordern", json={"email": "s@example.de"}).json()["korb"]
    a = c.post(f"/api/auswertung/unterlage?korb={korb}&name=schad.exe", content=b"x")
    assert a.status_code == 400


def test_mehr_als_zwoelf_unterlagen_braucht_niemand(welt):
    bw, _ = welt
    c = kunde(bw)
    korb = c.post("/api/auswertung/anfordern", json={"email": "s@example.de"}).json()["korb"]
    for i in range(bw.AUSWERTUNG_DATEIEN_MAX):
        assert c.post(f"/api/auswertung/unterlage?korb={korb}&name=d{i}.pdf",
                      content=b"x").status_code == 200
    zuviel = c.post(f"/api/auswertung/unterlage?korb={korb}&name=zuviel.pdf",
                    content=b"x")
    assert zuviel.status_code == 400


def test_ohne_unterlage_gibt_es_nichts_zu_lesen(welt):
    bw, _ = welt
    c = kunde(bw)
    korb = c.post("/api/auswertung/anfordern", json={"email": "s@example.de"}).json()["korb"]
    assert c.post(f"/api/auswertung/lesen?korb={korb}").status_code == 400


# ————— Lesen und Mail —————

def test_der_ganze_weg_erzeugt_eine_mail_mit_link(welt, monkeypatch):
    bw, tmp = welt
    durchlauf(bw, monkeypatch)
    text = brief(tmp)
    assert "Auswertung" in text
    assert "https://babu.test/auswertung/" in text.replace("=\n", "")
    assert schluessel_aus(text)


def test_die_mail_traegt_den_anriss_nicht_den_ganzen_bericht(welt, monkeypatch):
    bw, tmp = welt
    durchlauf(bw, monkeypatch)
    text = brief(tmp).replace("=\n", "")
    assert "Steuerberatung" in text          # der Befund, der überzeugt
    assert "Die Gegenproben" not in text     # der Rest steht hinter dem Link


def test_ohne_eingerichteten_versand_liegt_die_mail_im_postausgang(welt, monkeypatch):
    """Der heutige Normalfall. Verloren gehen darf sie trotzdem nicht — im
    Schlüssel steckt der einzige Weg zu dieser Auswertung."""
    bw, tmp = welt
    durchlauf(bw, monkeypatch)
    assert list((tmp / "post").glob("*.eml"))


def test_die_unterlagen_werden_nach_dem_lesen_geloescht(welt, monkeypatch):
    """Sie gehören niemandem — ein Tempordner ist kein Aufbewahrungsort."""
    bw, tmp = welt
    durchlauf(bw, monkeypatch)
    reste = list((tmp / "auswertung-tmp").rglob("*.pdf"))
    assert not reste, reste


def test_der_stand_ist_abfragbar_der_bericht_nicht(welt, monkeypatch):
    """Wer die Adresse eingetippt hat, ist nicht, wem sie gehört."""
    bw, _ = welt
    c, korb = durchlauf(bw, monkeypatch)
    a = c.get("/api/auswertung/stand?korb=" + korb)
    assert a.status_code == 200
    assert set(a.json()) == {"stand"}


def test_ein_fehlschlag_schweigt_nicht(welt, monkeypatch):
    """Wer „der Link kommt per E-Mail" gelesen hat, wartet sonst ewig."""
    bw, tmp = welt
    import abschluss_lesen

    def kaputt(pfad, **kw):
        raise RuntimeError("das ist kein PDF")

    monkeypatch.setattr(abschluss_lesen, "dokument_lesen", kaputt)
    c = kunde(bw)
    korb = c.post("/api/auswertung/anfordern",
                  json={"email": "salon@example.de"}).json()["korb"]
    c.post(f"/api/auswertung/unterlage?korb={korb}&name=x.pdf", content=b"kaputt")
    c.post(f"/api/auswertung/lesen?korb={korb}")
    for _ in range(200):
        if c.get("/api/auswertung/stand?korb=" + korb).json()["stand"] != "liest":
            break
        time.sleep(0.02)
    assert c.get("/api/auswertung/stand?korb=" + korb).json()["stand"] == "fehler"
    text = brief(tmp)
    assert "nicht lesen" in text
    assert "noch einmal" in text
    # Und kein Anmeldelink: es gibt nichts, wozu er führen würde.
    assert "/auswertung/" not in text.replace("=\n", "")


# ————— Der Link —————

def test_der_link_zeigt_den_bericht(welt, monkeypatch):
    bw, tmp = welt
    c, _ = durchlauf(bw, monkeypatch)
    s = schluessel_aus(brief(tmp))
    a = c.get("/api/auswertung/bericht?schluessel=" + s)
    assert a.status_code == 200
    d = a.json()
    assert d["mail"] == "salon@example.de"
    assert "Steuerberatung" in d["bericht"]
    assert "Die Gegenproben" in d["bericht"]      # hier der ganze Bericht
    assert d["felder"]["steuernummer"] == "71 015 73457"


def test_ein_falscher_schluessel_sagt_dasselbe_wie_ein_unbekannter(welt, monkeypatch):
    bw, tmp = welt
    c, _ = durchlauf(bw, monkeypatch)
    a = c.get("/api/auswertung/bericht?schluessel=" + "x" * 40)
    b = c.get("/api/auswertung/bericht?schluessel=" + "y" * 40)
    assert a.status_code == b.status_code == 404
    assert a.json()["fehler"] == b.json()["fehler"]


# ————— Aus der Einladung wird ein Konto —————

def test_passwort_zweimal_ergibt_ein_konto(welt, monkeypatch):
    bw, tmp = welt
    c, _ = durchlauf(bw, monkeypatch)
    s = schluessel_aus(brief(tmp))
    a = c.post("/api/auswertung/konto", json={
        "schluessel": s, "passwort": "salon-am-markt", "passwort2": "salon-am-markt"})
    assert a.status_code == 200, a.text
    assert a.json()["un"] == "salon@example.de"
    assert bw.SESSION_COOKIE in a.cookies or bw.SESSION_COOKIE in c.cookies
    # Angemeldet: der eigene Bericht ist da.
    m = c.get("/api/auswertung")
    assert m.status_code == 200
    assert "Steuerberatung" in m.json()["bericht"]


def test_zwei_verschiedene_passwoerter_legen_kein_konto_an(welt, monkeypatch):
    bw, tmp = welt
    c, _ = durchlauf(bw, monkeypatch)
    s = schluessel_aus(brief(tmp))
    a = c.post("/api/auswertung/konto", json={
        "schluessel": s, "passwort": "salon-am-markt", "passwort2": "anderes-wort"})
    assert a.status_code == 400 and "nicht gleich" in a.json()["fehler"]
    assert bw.nutzer_holen("salon@example.de") is None


def test_ein_kurzes_passwort_wird_abgelehnt(welt, monkeypatch):
    bw, tmp = welt
    c, _ = durchlauf(bw, monkeypatch)
    s = schluessel_aus(brief(tmp))
    a = c.post("/api/auswertung/konto", json={"schluessel": s,
                                              "passwort": "kurz", "passwort2": "kurz"})
    assert a.status_code == 400


def test_der_link_gilt_genau_einmal(welt, monkeypatch):
    bw, tmp = welt
    c, _ = durchlauf(bw, monkeypatch)
    s = schluessel_aus(brief(tmp))
    erst = c.post("/api/auswertung/konto", json={
        "schluessel": s, "passwort": "salon-am-markt", "passwort2": "salon-am-markt"})
    assert erst.status_code == 200
    nochmal = kunde(bw).post("/api/auswertung/konto", json={
        "schluessel": s, "passwort": "ganz-anderes-wort",
        "passwort2": "ganz-anderes-wort"})
    assert nochmal.status_code == 400
    assert "schon benutzt" in nochmal.json()["fehler"]


def test_gibt_es_das_konto_schon_wird_der_link_trotzdem_verbraucht(welt, monkeypatch):
    """Sonst bliebe er als zweiter Weg zu einem fremden Konto offen."""
    bw, tmp = welt
    c, _ = durchlauf(bw, monkeypatch)
    s = schluessel_aus(brief(tmp))
    bw.nutzer_anlegen("salon@example.de", "", "S", "salon",
                      passwort="schon-vorhanden", box=False)
    a = c.post("/api/auswertung/konto", json={
        "schluessel": s, "passwort": "salon-am-markt", "passwort2": "salon-am-markt"})
    assert a.status_code == 409
    zweiter = kunde(bw).post("/api/auswertung/konto", json={
        "schluessel": s, "passwort": "salon-am-markt", "passwort2": "salon-am-markt"})
    assert "schon benutzt" in zweiter.json()["fehler"]


# ————— Auf Knopfdruck ins Profil —————

def angemeldet(bw, monkeypatch):
    c, _ = durchlauf(bw, monkeypatch)
    return c


def test_die_angaben_stehen_bereit_aber_noch_nicht_im_profil(welt, monkeypatch):
    """„Auf Knopfdruck ins Profil" heißt: es gibt einen Knopf — nicht, dass
    es schon passiert ist."""
    bw, tmp = welt
    c = angemeldet(bw, monkeypatch)
    s = schluessel_aus(brief(tmp))
    c.post("/api/auswertung/konto", json={"schluessel": s,
                                          "passwort": "salon-am-markt",
                                          "passwort2": "salon-am-markt"})
    d = c.get("/api/auswertung").json()
    assert d["offen"]["steuernummer"] == "71 015 73457"
    assert not (bw.db_einstellungen("salon@example.de").get("steuernummer") or "")


def test_der_knopfdruck_setzt_sie(welt, monkeypatch):
    bw, tmp = welt
    c = angemeldet(bw, monkeypatch)
    s = schluessel_aus(brief(tmp))
    c.post("/api/auswertung/konto", json={"schluessel": s,
                                          "passwort": "salon-am-markt",
                                          "passwort2": "salon-am-markt"})
    a = c.post("/api/auswertung/uebernehmen")
    assert a.status_code == 200
    assert a.json()["gesetzt"]["finanzamt"] == "Ludwigsburg"
    e = bw.db_einstellungen("salon@example.de")
    assert e["steuernummer"] == "71 015 73457"
    assert e["rechtsform"] == "Einzelunternehmen"


def test_was_schon_dasteht_wird_nicht_ueberschrieben(welt, monkeypatch):
    bw, tmp = welt
    c = angemeldet(bw, monkeypatch)
    s = schluessel_aus(brief(tmp))
    c.post("/api/auswertung/konto", json={"schluessel": s,
                                          "passwort": "salon-am-markt",
                                          "passwort2": "salon-am-markt"})
    bw.db_einstellung_setzen("salon@example.de", "finanzamt", "Von Hand")
    c.post("/api/auswertung/uebernehmen")
    assert bw.db_einstellungen("salon@example.de")["finanzamt"] == "Von Hand"


def test_nach_dem_uebernehmen_ist_nichts_mehr_offen(welt, monkeypatch):
    bw, tmp = welt
    c = angemeldet(bw, monkeypatch)
    s = schluessel_aus(brief(tmp))
    c.post("/api/auswertung/konto", json={"schluessel": s,
                                          "passwort": "salon-am-markt",
                                          "passwort2": "salon-am-markt"})
    c.post("/api/auswertung/uebernehmen")
    assert not c.get("/api/auswertung").json()["offen"]


def test_ohne_anmeldung_gibt_es_weder_bericht_noch_uebernahme(welt):
    bw, _ = welt
    c = kunde(bw)
    assert c.get("/api/auswertung").status_code == 401
    assert c.post("/api/auswertung/uebernehmen").status_code == 401


def test_die_seite_hinter_dem_link_wird_ausgeliefert(welt):
    bw, _ = welt
    a = kunde(bw).get("/auswertung/irgendein-schluessel")
    assert a.status_code == 200
    assert "Konto anlegen" in a.text
