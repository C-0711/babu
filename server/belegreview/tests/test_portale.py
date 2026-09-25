"""Portale: je Branche eine Kopie von babu — und Friseur bleibt, wie es war.

Seit dem 24.09.2026 stehen die Texte, die ans Modell gehen, nicht mehr im
Code der Dienste, sondern im Portal des Betriebs (`portale/`). Für Friseur
hat sich dabei kein Byte geändert. Die beiden Golden-Dateien sind VOR dem
Umzug aus dem damaligen Code aufgezeichnet worden; wer sie anfassen muss,
hat einen Text verändert statt verschoben.
"""
import json
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import gemma_buchung  # noqa: E402
import kompendium  # noqa: E402
import portale  # noqa: E402

GOLDEN = HIER / "golden"


@pytest.fixture()
def festes_wissen(monkeypatch):
    """Das Kompendium liegt nur auf der H200V — für den Vergleich ein
    fester Platzhalter, derselbe wie bei der Aufzeichnung."""
    monkeypatch.setattr(kompendium, "kontierungswissen",
                        lambda: "KONTIERUNGSWISSEN-PLATZHALTER")
    monkeypatch.setattr(kompendium, "grundwissen",
                        lambda: "GRUNDWISSEN-PLATZHALTER")
    # Seit 25.09.2026 liest Friseur aus seiner eigenen Kopie (kompendium-friseur),
    # deren Dateien Byte für Byte die alten sind — derselbe Platzhalter.
    monkeypatch.setattr(kompendium, "kontierungswissen_von",
                        lambda bestaende: "KONTIERUNGSWISSEN-PLATZHALTER")
    monkeypatch.setattr(kompendium, "grundwissen_von",
                        lambda bestaende: "GRUNDWISSEN-PLATZHALTER")


def test_jedes_portal_ist_vollstaendig():
    assert portale.pruefen() == []


def test_ohne_angabe_und_bei_unsinn_ist_es_friseur():
    for s in (None, "", "  ", "xyz", "Friseur ", "FRISEUR"):
        assert portale.hole(s).SCHLUESSEL == "friseur"
    assert portale.kennt("friseur") and not portale.kennt("xyz")
    assert not portale.kennt(None)


def test_der_buchungs_vorspann_ist_byte_gleich_mit_dem_von_vor_dem_umzug(festes_wissen):
    e = {"betrieb_name": "Salon Nina", "kleinunternehmer": "Nein"}
    ist = gemma_buchung.system_text(gemma_buchung.profil_text(e), "SKR04")
    assert ist == (GOLDEN / "vorspann_friseur.txt").read_text(encoding="utf-8")


def test_ausdrueckliches_friseur_ist_dasselbe_wie_keine_angabe(festes_wissen):
    ohne = {"betrieb_name": "Salon Nina", "kleinunternehmer": "Nein"}
    mit = dict(ohne, portal="friseur")
    assert gemma_buchung.profil_text(mit) == gemma_buchung.profil_text(ohne)
    assert (gemma_buchung.system_text(gemma_buchung.profil_text(mit), "SKR04",
                                      portal="friseur")
            == gemma_buchung.system_text(gemma_buchung.profil_text(ohne), "SKR04"))


def test_ein_portal_hinweis_ersetzt_nur_den_text_nie_das_konto():
    """Der Katalog bleibt der des Kontenrahmens: Codes, Reihenfolge und die
    Kategorien, die ein Konto haben. Das Portal darf nur den Hinweis ändern."""
    normal = gemma_buchung.katalog_text("SKR04")
    anders = gemma_buchung.katalog_text("SKR04", hinweise={"werkzeug": "ANDERS"})
    zeilen_n, zeilen_a = normal.splitlines(), anders.splitlines()
    assert len(zeilen_n) == len(zeilen_a)
    assert [z.split(":")[0] for z in zeilen_n] == [z.split(":")[0] for z in zeilen_a]
    assert "  werkzeug: Werkzeug und Kleingeräte — ANDERS" in zeilen_a


def test_der_chat_vorspann_ist_byte_gleich_mit_dem_von_vor_dem_umzug(festes_wissen, tmp_path, monkeypatch):
    import babu_web
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".g")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "p.db")
    monkeypatch.setattr(babu_web, "wer_token",
                        lambda t: "christoph0711.io" if t == "test-pat" else None)
    gesagt = []

    class Antwort:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(babu_web.requests, "post",
                        lambda url, json=None, **kw: (gesagt.append(json), Antwort())[1])
    monkeypatch.setattr(babu_web, "_welt_fuer", lambda un: {
        "einstellungen": {"betrieb_name": "Salon Nina"}, "belege": [],
        "kassenblaetter": [], "vertraege": [], "rechnungen": [], "team": [],
        "fristen": [], "zahlen": {}, "dokumente": []})
    monkeypatch.setattr(babu_web, "_recherche", lambda frage, **kw: "")
    babu_web._LOGIN_VERSUCHE.clear()
    from fastapi.testclient import TestClient
    c = TestClient(babu_web.app, base_url="https://testserver")
    assert c.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    assert c.post("/chat", json={"frage": "Was ist eine Kleinunternehmerin?"}).status_code == 200
    system = gesagt[-1]["messages"][0]["content"]
    assert system == (GOLDEN / "chat_vorspann_friseur.txt").read_text(encoding="utf-8")


# ————— Barber: die erste Kopie —————

def test_barber_ist_eine_vollstaendige_kopie():
    b = portale.hole("barber")
    assert b.SCHLUESSEL == "barber" and portale.kennt("barber")
    assert b.KOMPENDIUM == ("kompendium-barber",)   # eigener, vollständiger Container
    assert portale.eigener_container(b)
    assert not portale.eigener_container(portale.hole("friseur"))
    # Jeder Hinweis betrifft eine Kategorie, die es im Katalog gibt.
    import kontierung
    assert set(b.KATEGORIE_HINWEISE) <= set(kontierung.KATEGORIEN)


def test_barber_bucht_mit_eigenem_vorspann_und_denselben_konten(festes_wissen):
    e = {"betrieb_name": "Moe's Barbershop", "kleinunternehmer": "Nein", "portal": "barber"}
    profil = gemma_buchung.profil_text(e)
    assert profil.startswith("Barbershop „Moe's Barbershop“")
    b = gemma_buchung.system_text(profil, "SKR04", portal="barber")
    f = gemma_buchung.system_text(gemma_buchung.profil_text(
        {"betrieb_name": "Salon Nina", "kleinunternehmer": "Nein"}), "SKR04")
    assert b != f                                   # zwei Portale, zwei Vorspänne
    assert b.startswith("Du bist die Buchhaltung eines Barbershops")
    assert "Rasiermesser" in b and "Extensions" not in b
    # Codes und Reihenfolge des Katalogs sind in beiden Portalen gleich.
    codes = lambda t: [z.split(":")[0].strip() for z in t.splitlines() if z.startswith("  ") and ":" in z]
    kat = lambda t: t.split("KATEGORIEN")[1].split("\n\n")[0]
    assert codes(kat(b)) == codes(kat(f))
    # Der Barber-Vorspann ist in sich stabil (Prefix-Cache).
    assert b == gemma_buchung.system_text(profil, "SKR04", portal="barber")


def test_portal_und_sprache_werden_geprueft_und_gespeichert(tmp_path, monkeypatch):
    import babu_web
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".g")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "p.db")
    monkeypatch.setattr(babu_web, "wer_token",
                        lambda t: "christoph0711.io" if t == "test-pat" else None)
    babu_web._LOGIN_VERSUCHE.clear()
    from fastapi.testclient import TestClient
    c = TestClient(babu_web.app, base_url="https://testserver")
    assert c.post("/api/anmelden", json={"pat": "test-pat"}).status_code == 200
    assert c.post("/api/einstellungen", json={"portal": "maler"}).status_code == 400
    assert c.post("/api/einstellungen", json={"sprache": "fr"}).status_code == 400
    r = c.post("/api/einstellungen", json={"portal": " Barber ", "sprache": "TR"})
    assert r.status_code == 200, r.text
    e = babu_web.db_einstellungen("christoph0711.io")
    assert e["portal"] == "barber" and e["sprache"] == "tr"


# ————— Der Barber-Chat in der App: Wissenscontainer UND alle Belege —————

def test_der_barber_chat_der_app_sieht_container_und_belege_zusammen(tmp_path, monkeypatch):
    """Die App fragt über `POST /chat` mit Bearer — dieselbe Route wie das
    Portal. Für einen Barber-Betrieb müssen in EINER Anfrage ankommen: die
    Rolle und das Grundwissen des Barber-Containers (stehend), das ganze
    Belegregister (Weltblock, stehend), die Treffer aus `kompendium-barber`
    UND die passenden eigenen Belege im Wortlaut (variabel)."""
    import numpy as np
    import babu_web
    haupt, barber = tmp_path / "kompendium", tmp_path / "kompendium-barber"
    haupt.mkdir(); barber.mkdir()
    atome = [{"id": 0, "quelle": "pangv_2022.md", "loc": "txt#12",
              "text": "PAngV § 12 Preisangaben für Leistungen: Preisverzeichnis im Schaufenster."},
             {"id": 1, "quelle": "arbzg.md", "loc": "txt#3", "text": "ArbZG § 3 Arbeitszeit."}]
    (barber / "atome.jsonl").write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in atome))
    np.save(barber / "vektoren.npy", np.eye(2, 4, dtype=np.float32))
    (barber / "grundwissen.md").write_text("# Grundwissen Barbershop TESTMARKE")
    monkeypatch.setattr(kompendium, "VERZEICHNIS", haupt)
    monkeypatch.setattr(kompendium, "_VEKTOREN", None)
    monkeypatch.setattr(kompendium, "_OFFSETS", [])
    monkeypatch.setattr(kompendium, "_TEXTE", {})
    monkeypatch.setattr(kompendium, "_WEITERE", {})
    monkeypatch.setattr(kompendium, "_WEITERE_TEXTE", {})

    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".g")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "p.db")
    monkeypatch.setattr(babu_web, "wer_token",
                        lambda t: "christoph0711.io" if t == "test-pat" else None)
    monkeypatch.setattr(babu_web, "embedding_rechnen",
                        lambda text, als_dokument=True: {"vektor": [1.0, 0.0, 0.0, 0.0]})
    monkeypatch.setattr(babu_web, "_wissen_treffer", lambda v, k=5: [])
    monkeypatch.setattr(babu_web, "_beleg_vektoren",
                        lambda: (["s1"], np.asarray([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)))
    monkeypatch.setattr(babu_web, "_dokument_vektoren", lambda: ([], None))
    monkeypatch.setattr(babu_web, "git_show",
                        lambda pfad: b"BELEG Friseurbedarf Yilmaz: Pomade 12,90 EUR" if pfad == "review/s1.md" else None)
    monkeypatch.setattr(babu_web, "_welt_fuer", lambda un: {
        "einstellungen": {"betrieb_name": "Moes Barbershop"},
        "belege": [{"stamm": "s1", "lieferant": "Friseurbedarf Yilmaz", "brutto": 12.9,
                    "monat": "2026-09", "datum": "20.09.2026", "belegart": "Wareneinkauf", "offen": []}],
        "kassenblaetter": [], "vertraege": [], "rechnungen": [], "team": [],
        "fristen": [], "zahlen": {}, "dokumente": []})
    gesagt = []

    class Antwort:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(babu_web.requests, "post",
                        lambda url, json=None, **kw: (gesagt.append(json), Antwort())[1])
    babu_web._LOGIN_VERSUCHE.clear()
    babu_web.db_einstellung_setzen("christoph0711.io", "portal", "barber")

    from fastapi.testclient import TestClient
    app = TestClient(babu_web.app, base_url="https://testserver")
    r = app.post("/chat", json={"frage": "Muss ich meine Preise aushängen?"},
                 headers={"Authorization": "Bearer test-pat"})
    assert r.status_code == 200, r.text
    system = gesagt[-1]["messages"][0]["content"]
    frage = gesagt[-1]["messages"][-1]["content"]
    assert "für Barbershops" in system                         # Rolle des Portals
    assert "# Grundwissen Barbershop TESTMARKE" in system      # Grundwissen aus kompendium-barber
    assert "Moes Barbershop" in system and "Yilmaz" in system  # Belegregister (Weltblock)
    assert "PAngV § 12" in frage                               # Treffer aus kompendium-barber
    assert "EIGENE BELEGE" in frage and "Pomade 12,90" in frage  # eigener Beleg im Wortlaut

    # Gegenprobe: derselbe Betrieb als Friseur sieht den Barber-Container nicht.
    babu_web.db_einstellung_setzen("christoph0711.io", "portal", "friseur")
    app.post("/chat", json={"frage": "Muss ich meine Preise aushängen?"},
             headers={"Authorization": "Bearer test-pat"})
    assert "TESTMARKE" not in gesagt[-1]["messages"][0]["content"]
    assert "PAngV" not in gesagt[-1]["messages"][-1]["content"]
    assert "Pomade 12,90" in gesagt[-1]["messages"][-1]["content"]  # die Belege bleiben


def test_die_suchfrage_verliert_im_barber_portal_das_branchenwort():
    b, f = portale.hole("barber"), portale.hole("friseur")
    assert portale.suchfrage(b, "Muss ich als Barber meine Preise aushängen?") \
        == "Muss ich meine Preise aushängen?"
    assert portale.suchfrage(b, "Welche Gewerbesteuer zahlt mein Barbershop?") \
        == "Welche Gewerbesteuer zahlt mein ?"   # so gemessen (Platz 1)
    assert portale.suchfrage(b, "Barber") == "Barber"            # nie leer
    frage = "Muss ich als Friseurin im Salon meine Preise aushängen?"
    assert portale.suchfrage(f, frage) == frage                  # Friseur unverändert


def test_der_buchungsweg_laesst_die_gesetzestexte_aus(tmp_path, monkeypatch):
    """Die Gesetze sind für den Chat da. Ihr Dateiname enthält „ustg" und käme
    sonst durch den Quellenfilter in den Buchungs-Nachschlag."""
    import numpy as np
    import babu_web
    d = tmp_path / "kompendium"
    d.mkdir()
    atome = [{"id": 0, "quelle": "gesetze/ustg_1980.md", "loc": "txt#1", "text": "UStG § 12 Steuersätze"},
             {"id": 1, "quelle": "branche/afa/AfA-Tabelle_94.xlsx", "loc": "S1", "text": "Bedienungsstühle 10 Jahre"}]
    (d / "atome.jsonl").write_text("".join(json.dumps(a) + "\n" for a in atome))
    np.save(d / "vektoren.npy", np.asarray([[1, 0, 0, 0], [0.9, 0.44, 0, 0]], dtype=np.float32))
    monkeypatch.setattr(kompendium, "VERZEICHNIS", d)
    monkeypatch.setattr(kompendium, "_VEKTOREN", None)
    monkeypatch.setattr(kompendium, "_OFFSETS", [])
    monkeypatch.setattr(kompendium, "_WEITERE", {})
    # Ohne Ausschluss stünde das Gesetz vorn …
    assert kompendium.suchen([1, 0, 0, 0], k=1)[0]["quelle"].startswith("gesetze/")
    # … mit Ausschluss kommt der nächste echte Treffer nach, nicht weniger.
    t = kompendium.suchen_in([1, 0, 0, 0], ("kompendium",), k=1, ohne=gemma_buchung.GESETZES_QUELLEN)
    assert [x["quelle"] for x in t] == ["branche/afa/AfA-Tabelle_94.xlsx"]
    monkeypatch.setattr(babu_web, "embedding_rechnen", lambda text, als_dokument=True: {"vektor": [1, 0, 0, 0]})
    monkeypatch.setattr(babu_web, "_wissen_treffer", lambda v, k=5: [])
    text = gemma_buchung.nachschlagen(["Friseurstuhl Hydraulik"], portal="friseur")
    assert "AfA-Tabelle_94" in text and "gesetze/" not in text


def test_die_barber_seite_wird_ausgeliefert(tmp_path, monkeypatch):
    import babu_web
    monkeypatch.setattr(babu_web, "SEITE", tmp_path / "index.html")
    from fastapi.testclient import TestClient
    c = TestClient(babu_web.app, base_url="https://testserver")
    assert c.get("/barber").status_code == 404                 # ohne Datei: kommt bald
    (tmp_path / "barber.html").write_text("<html>babu Barber</html>", encoding="utf-8")
    r = c.get("/barber")
    assert r.status_code == 200 and "babu Barber" in r.text
    assert r.headers["content-type"].startswith("text/html")


def test_die_gebaute_barber_seite_ist_vollstaendig():
    """Die Seite im Repo ist mit `werbung/barber/seite_bauen.py` gebaut: jedes
    Barber-Bild, echte Rechtslinks, kein Buhl, und jeder Satz hat Türkisch."""
    seite = (HIER.parents[1] / "babu-web" / "barber.html").read_text(encoding="utf-8")
    assert seite.count("/bilder/ba-") >= 18
    for pfad in ("/impressum", "/datenschutz", "/agb"):
        assert f'href="{pfad}"' in seite
    assert "Buhl" not in seite and "Steuer-Backend" in seite
    assert 'data-sprache="tr"' in seite and '"Dein Papierkram": "Evrak işlerin"' in seite
    assert "/ablage" not in seite                               # kein öffentlicher Upload


def test_alle_seiten_wechseln_ueber_den_welten_hero():
    """Ganz oben auf jeder Startseite EIN Hero: die eigene Welt breit mit der
    Überschrift, die anderen Welten als Weg hinüber — und von dort zurück."""
    import re
    ordner = HIER.parents[1] / "babu-web"
    welten = {"/": "fr-held.jpg", "/barber": "ba-held.jpg", "/werkstatt": "ws-held.jpg"}
    for datei, hier in (("index.html", "/"), ("barber.html", "/barber"), ("werkstatt.html", "/werkstatt")):
        seite = (ordner / datei).read_text(encoding="utf-8")
        hero = seite[seite.index("<!-- welten:start"):seite.index("<!-- welten:ende -->")]
        assert seite.index("<!-- welten:start") < seite.index("So geht's")
        aktiv = hero[hero.index('<div class="welt aktiv">'):hero.index("</h1>")]
        assert welten[hier] in aktiv and "Dein Papierkram" in aktiv, datei
        for pfad, bild in welten.items():
            if pfad != hier:
                assert re.search(rf'<a class="welt" href="{re.escape(pfad)}">\s*<img src="/bilder/{bild}"', hero), (datei, pfad)
        assert hero.count("<h1>") == 1 and seite.count("<h1>") == 1, datei


# ————— Werkstatt: die zweite Kopie —————

def test_werkstatt_ist_eine_vollstaendige_kopie(festes_wissen):
    w = portale.hole("werkstatt")
    assert w.SCHLUESSEL == "werkstatt" and w.KOMPENDIUM == ("kompendium-werkstatt",)
    import kontierung
    assert set(w.KATEGORIE_HINWEISE) <= set(kontierung.KATEGORIEN)
    e = {"betrieb_name": "Kfz-Service Mario", "kleinunternehmer": "Nein", "portal": "werkstatt"}
    v = gemma_buchung.system_text(gemma_buchung.profil_text(e), "SKR04", portal="werkstatt")
    assert v.startswith("Du bist die Buchhaltung einer Kfz-Werkstatt")
    assert "Achsvermessung" in v and "Extensions" not in v and "Rasiermesser" not in v
    assert portale.suchfrage(w, "Muss ich als Kfz-Werkstatt Altöl zurücknehmen?") \
        == "Muss ich Altöl zurücknehmen?"


def test_die_werkstatt_seite_wird_ausgeliefert(tmp_path, monkeypatch):
    import babu_web
    monkeypatch.setattr(babu_web, "SEITE", tmp_path / "index.html")
    from fastapi.testclient import TestClient
    c = TestClient(babu_web.app, base_url="https://testserver")
    assert c.get("/werkstatt").status_code == 404
    (tmp_path / "werkstatt.html").write_text("<html>babu Werkstatt</html>", encoding="utf-8")
    assert c.get("/werkstatt").status_code == 200


def test_der_chat_sucht_im_eigenen_container_das_bundesrecht_nur_bei_genannter_vorschrift():
    """Gemessen: das ganze Bundesrecht in der Vektorsuche verschlechtert die
    Antworten. Es kommt nur über den Wortlaut einer genannten Vorschrift."""
    assert portale.chat_bestaende(portale.hole("friseur")) == ("kompendium",)
    assert portale.chat_bestaende(portale.hole("werkstatt")) == ("kompendium-werkstatt",)


def test_eine_genannte_vorschrift_kommt_im_wortlaut(tmp_path, monkeypatch):
    d = tmp_path / "kompendium-bundesrecht"
    d.mkdir()
    atome = [
        {"id": 0, "quelle": "gesetze/bgb.md", "loc": "txt#1", "text": "BGB § 647 Unternehmerpfandrecht\nDer Unternehmer hat ein Pfandrecht."},
        {"id": 1, "quelle": "gesetze/sgb_4.md", "loc": "txt#2", "text": "SGB 4 § 7 Beschäftigung\n(1) Beschäftigung ist nichtselbständige Arbeit."},
        {"id": 2, "quelle": "gesetze/sgb_6.md", "loc": "txt#3", "text": "SGB 6 § 7 Freiwillige Versicherung\n(1) Freiwillig versichern können sich …"},
        {"id": 3, "quelle": "gesetze/ao_1977.md", "loc": "txt#4", "text": "AO 1977 § 146b Kassen-Nachschau\n(1) Zur Prüfung …"},
    ]
    (d / "atome.jsonl").write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in atome), encoding="utf-8")
    monkeypatch.setattr(kompendium, "VERZEICHNIS", tmp_path / "kompendium")
    monkeypatch.setattr(kompendium, "_NORMEN", {})
    assert [w["kopf"] for w in kompendium.wortlaut("Was sagt § 647 BGB?")] == ["BGB § 647 Unternehmerpfandrecht"]
    assert [w["quelle"] for w in kompendium.wortlaut("Gilt § 7 SGB IV für Stuhlmieter?")] == ["gesetze/sgb_4.md"]
    assert kompendium.wortlaut("Gilt § 7 SGB für mich?") == []            # mehrdeutig: nicht raten
    assert [w["kopf"] for w in kompendium.wortlaut("AO § 146b")] == ["AO 1977 § 146b Kassen-Nachschau"]
    assert kompendium.wortlaut("Wie viel Urlaub steht mir zu?") == []


def test_dieselbe_norm_aus_zwei_bestaenden_zaehlt_einmal(tmp_path, monkeypatch):
    import numpy as np
    for name in ("kompendium-werkstatt", "kompendium-bundesrecht"):
        d = tmp_path / name
        d.mkdir()
        (d / "atome.jsonl").write_text(json.dumps(
            {"id": 0, "quelle": "gesetze/bgb.md", "loc": "txt#1", "text": "BGB § 647 Pfandrecht"}) + "\n"
            + json.dumps({"id": 1, "quelle": f"{name}.md", "loc": "txt#2", "text": f"anders {name}"}) + "\n")
        np.save(d / "vektoren.npy", np.asarray([[1, 0, 0, 0], [0.6, 0.8, 0, 0]], dtype=np.float32))
    monkeypatch.setattr(kompendium, "VERZEICHNIS", tmp_path / "kompendium")
    monkeypatch.setattr(kompendium, "_WEITERE", {})
    t = kompendium.suchen_in([1, 0, 0, 0], ("kompendium-werkstatt", "kompendium-bundesrecht"), k=3)
    assert [x["text"] for x in t].count("BGB § 647 Pfandrecht") == 1 and len(t) == 3


def test_nennt_die_frage_eine_nummer_beginnt_der_wortlaut_dort(tmp_path, monkeypatch):
    d = tmp_path / "kompendium-bundesrecht"
    d.mkdir()
    lang = "\n".join(f"{i}.\nText der Nummer {i}." for i in range(1, 60))
    (d / "atome.jsonl").write_text(json.dumps({"id": 0, "quelle": "gesetze/estg.md", "loc": "txt#1",
                                               "text": "EStG § 3\n" + lang}) + "\n", encoding="utf-8")
    monkeypatch.setattr(kompendium, "VERZEICHNIS", tmp_path / "kompendium")
    monkeypatch.setattr(kompendium, "_NORMEN", {})
    w = kompendium.wortlaut("Was steht in § 3 Nr. 51 EStG?", grenze=200)
    assert "Text der Nummer 51." in w[0]["text"] and "Text der Nummer 2." not in w[0]["text"]
