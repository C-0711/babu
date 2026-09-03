"""P0-4/2a: Portal-Uploads bekommen jetzt eine Lesung.

Befund vom 02.09.2026: `POST /api/hochladen` und `POST /ablage` schrieben
nur die Datei nach `docs/<monat>/` — nie ein `review/<stamm>.json`. Nur
`/api/aufnahme` (die App, mit Vision-Lesung im Gepäck) tat das. Ohne App
davor blieb ein Portal-Beleg deshalb für immer auf „Wird gelesen" stehen.

`_beleg_serverseitig_lesen` holt das jetzt nach: ein PDF mit Textebene
liefert seine Zeilen, ein Foto/Scan geht als Bild direkt an Gemma
(multimodal) — derselbe Fallback-Weg, den `gemma_buchung.py` für das
Telefon ohne Vision-Text schon kennt.

Die Kernfunktion wird hier DIREKT aufgerufen (nicht über
`asyncio.create_task`/den Upload-Request selbst) — ein `TestClient`-Aufruf
öffnet für jede Anfrage nur kurz einen eigenen Event-Loop-Portal und
schließt ihn sofort wieder; ein per `create_task` gestarteter Hintergrund-
Task hat dann keine verlässliche Chance, vor Testende fertig zu werden.
Direkt awaiten ist deterministisch, nicht flaky.
"""
import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
UN = "nina@0711.io"


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
    import boxschreiber
    monkeypatch.setattr(babu_web, "STORE", bare)
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(bare))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    babu_web._BELEG_VEKTOREN = (None, [], None)
    return babu_web, bare


def _stand(bare: Path) -> str:
    return subprocess.run(["git", "-C", str(bare), "ls-tree", "-r", "--name-only", "HEAD"],
                          capture_output=True, text=True).stdout


def _ablegen(bare_egal, pfad: str, daten: bytes) -> None:
    """Wie `ablage`/`api_hochladen` es tun, bevor die Lesung überhaupt
    beginnt: die Datei ist schon committet."""
    import boxschreiber
    boxschreiber.schreiben(pfad, daten, f"aufnahme: {Path(pfad).name}", UN)


GEBUCHT = {"status": "gebucht", "buchung": {
    "betrag_eur": 12.5, "datum": "2026-08-27", "lieferant": "Testladen",
    "ust_satz": 19, "konto": "6800", "kategorie": "buerobedarf",
    "kategorie_name": "Büromaterial", "dokumentklasse": "beleg"}}


# ————— PDF mit Textebene → Zeilen —————

def test_pdf_mit_text_bekommt_ein_review(welt, monkeypatch):
    bw, bare = welt
    import gemma_buchung
    import abschluss_lesen

    gesehen = {}

    def falsche_runde(zeilen, *rest, **kw):
        gesehen["zeilen"] = zeilen
        gesehen["bild"] = rest[6] if len(rest) > 6 else kw.get("bild")
        return GEBUCHT
    monkeypatch.setattr(gemma_buchung, "runde", falsche_runde)
    monkeypatch.setattr(abschluss_lesen, "seiten_text",
                        lambda pfad: ["Testladen", "12,50 EUR"])

    stamm = "20260827-120000-abcdef-beleg"
    pfad = f"docs/2026-08/{stamm}.pdf"
    daten = b"%PDF-1.4 fake"
    _ablegen(bare, pfad, daten)

    asyncio.run(bw._beleg_serverseitig_lesen(pfad, daten, ".pdf", UN))

    assert gesehen["zeilen"] == ["Testladen", "12,50 EUR"]
    assert gesehen["bild"] is None
    stand = _stand(bare)
    assert f"review/{stamm}.json" in stand
    assert f"review/{stamm}.md" in stand
    eintrag = bw.index_aktuell()["belege"][stamm]
    assert eintrag["status"] == "geprüft"
    assert eintrag["brutto"] == 12.5


# ————— Bild/Scan → bild=(daten, mime), nicht Zeilen —————

def test_bild_geht_als_bild_an_gemma_nicht_als_zeilen(welt, monkeypatch):
    bw, bare = welt
    import gemma_buchung

    gesehen = {}

    def falsche_runde(zeilen, einstellungen, antworten, rahmen,
                      umsaetze=None, nachbarn=None, markdown=None, bild=None,
                      vertraege=None, personal=None, offene_abbuchungen=None):
        gesehen.update(zeilen=zeilen, bild=bild)
        return GEBUCHT
    monkeypatch.setattr(gemma_buchung, "runde", falsche_runde)

    stamm = "20260827-130000-abcdef-beleg"
    pfad = f"docs/2026-08/{stamm}.jpg"
    daten = b"\xff\xd8\xff\xe0" + b"x" * 300
    _ablegen(bare, pfad, daten)

    asyncio.run(bw._beleg_serverseitig_lesen(pfad, daten, ".jpg", UN))

    assert gesehen["zeilen"] == []
    assert gesehen["bild"] == (daten, "image/jpeg")
    stand = _stand(bare)
    assert f"review/{stamm}.json" in stand


def test_heic_bekommt_das_passende_mime(welt, monkeypatch):
    bw, bare = welt
    import gemma_buchung
    gesehen = {}

    def falsche_runde(zeilen, einstellungen, antworten, rahmen,
                      umsaetze=None, nachbarn=None, markdown=None, bild=None,
                      vertraege=None, personal=None, offene_abbuchungen=None):
        gesehen["bild"] = bild
        return GEBUCHT
    monkeypatch.setattr(gemma_buchung, "runde", falsche_runde)

    stamm = "20260827-140000-abcdef-beleg"
    pfad = f"docs/2026-08/{stamm}.heic"
    daten = b"heic-fake"
    _ablegen(bare, pfad, daten)
    asyncio.run(bw._beleg_serverseitig_lesen(pfad, daten, ".heic", UN))
    assert gesehen["bild"] == (daten, "image/heic")


def test_unbekanntes_format_wird_gar_nicht_erst_versucht(welt, monkeypatch):
    """.xml (DATEV-Export o. ä.) ist weder Text-PDF noch Foto — kein
    Leseversuch, kein Review, kein Absturz."""
    bw, bare = welt
    import gemma_buchung
    monkeypatch.setattr(gemma_buchung, "runde",
                        lambda *a, **k: pytest.fail("darf für .xml nicht aufgerufen werden"))
    stamm = "20260827-150000-abcdef-export"
    pfad = f"docs/2026-08/{stamm}.xml"
    daten = b"<xml/>"
    _ablegen(bare, pfad, daten)
    asyncio.run(bw._beleg_serverseitig_lesen(pfad, daten, ".xml", UN))
    assert f"review/{stamm}.json" not in _stand(bare)


# ————— "fragen"/"aufgeben": niemand am Portal antwortet — kein Review —————

@pytest.mark.parametrize("ergebnis", [
    {"status": "fragen", "fragen": [{"frage": "?", "optionen": []}]},
    {"status": "aufgeben", "hinweis": "zu viele Fragen"},
])
def test_fragen_und_aufgeben_schreiben_kein_review(welt, monkeypatch, ergebnis):
    bw, bare = welt
    import gemma_buchung
    monkeypatch.setattr(gemma_buchung, "runde", lambda *a, **k: ergebnis)
    stamm = "20260827-160000-abcdef-beleg"
    pfad = f"docs/2026-08/{stamm}.jpg"
    daten = b"\xff\xd8\xff\xe0" + b"x" * 300
    _ablegen(bare, pfad, daten)
    asyncio.run(bw._beleg_serverseitig_lesen(pfad, daten, ".jpg", UN))
    assert f"review/{stamm}.json" not in _stand(bare)
    eintrag = bw.index_aktuell()["belege"][stamm]
    assert eintrag["status"] == "erfasst"


# ————— Ein hängender/werfender Aufruf blockiert und crasht nicht —————

def test_haengender_aufruf_schreibt_kein_review_und_wirft_nicht(welt, monkeypatch):
    bw, bare = welt
    import gemma_buchung

    def wirft(*a, **k):
        raise RuntimeError("kein Netz zur Buchhaltung")
    monkeypatch.setattr(gemma_buchung, "runde", wirft)

    stamm = "20260827-170000-abcdef-beleg"
    pfad = f"docs/2026-08/{stamm}.jpg"
    daten = b"\xff\xd8\xff\xe0" + b"x" * 300
    _ablegen(bare, pfad, daten)

    # _hintergrund_lesen ist die Stelle, die den Fehler auffängt (die Route
    # selbst bekommt davon nichts mit — sie hat längst geantwortet).
    asyncio.run(bw._hintergrund_lesen(pfad, daten, ".jpg", UN))
    assert f"review/{stamm}.json" not in _stand(bare)
    eintrag = bw.index_aktuell()["belege"][stamm]
    assert eintrag["status"] == "erfasst"


def test_timeout_schreibt_kein_review_und_wirft_nicht(welt, monkeypatch):
    """Ein Aufruf, der nie zurückkommt, darf den Hintergrund-Task nicht für
    immer offen halten — `asyncio.timeout` fängt das ab."""
    bw, bare = welt
    import gemma_buchung
    import time as _time
    monkeypatch.setattr(bw, "BELEG_LESE_FRIST_SEK", 0.05)

    def langsam(*a, **k):
        _time.sleep(0.3)
        return GEBUCHT
    monkeypatch.setattr(gemma_buchung, "runde", langsam)

    stamm = "20260827-180000-abcdef-beleg"
    pfad = f"docs/2026-08/{stamm}.jpg"
    daten = b"\xff\xd8\xff\xe0" + b"x" * 300
    _ablegen(bare, pfad, daten)

    asyncio.run(bw._hintergrund_lesen(pfad, daten, ".jpg", UN))  # darf nicht werfen
    assert f"review/{stamm}.json" not in _stand(bare)


# ————— Idempotenz: eine manuelle Angabe (oder eine schnellere zweite
# Lesung) darf der Hintergrund-Task nie überschreiben —————

def test_hintergrund_lesung_ueberschreibt_keine_manuelle_angabe(welt, monkeypatch):
    bw, bare = welt
    import gemma_buchung
    import boxschreiber

    stamm = "20260827-190000-abcdef-beleg"
    pfad = f"docs/2026-08/{stamm}.jpg"
    daten = b"\xff\xd8\xff\xe0" + b"x" * 300
    _ablegen(bare, pfad, daten)

    # So sieht ein Review aus, das längst da ist — von einer manuellen
    # Angabe oder einer schon abgeschlossenen zweiten Lesung.
    vorhandenes_review = {"datei": pfad, "felder": {"brutto": 4.2, "offen": []},
                          "von_hand": True}
    boxschreiber.schreiben(
        {f"review/{stamm}.json": __import__("json").dumps(vorhandenes_review).encode()},
        None, f"angaben: {stamm}", UN)

    monkeypatch.setattr(gemma_buchung, "runde", lambda *a, **k: GEBUCHT)
    asyncio.run(bw._beleg_serverseitig_lesen(pfad, daten, ".jpg", UN))

    roh = bw.git_show(f"review/{stamm}.json")
    import json
    assert json.loads(roh) == vorhandenes_review, "der Hintergrund-Task hat überschrieben"


# ————— Die Routen stoßen die Lesung wirklich an —————

def test_hochladen_stoesst_die_hintergrund_lesung_an(welt, monkeypatch):
    bw, _ = welt
    monkeypatch.setattr(bw, "_box_wache", lambda request: (UN, None))
    monkeypatch.setattr(bw, "_mitarbeit_wache", lambda un, recht, was: None)
    gesehen = {}
    monkeypatch.setattr(bw, "_hintergrund_lesen_starten",
                        lambda pfad, daten, endung, un: gesehen.update(
                            pfad=pfad, daten=daten, endung=endung, un=un))
    from fastapi.testclient import TestClient
    c = TestClient(bw.app, base_url="https://testserver")
    r = c.post("/api/hochladen", params={"name": "kassenbon.jpg"},
              content=b"\xff\xd8\xff\xe0bild")
    assert r.status_code == 200, r.text
    assert gesehen["endung"] == ".jpg"
    assert gesehen["un"] == UN
    assert gesehen["pfad"] == r.json()["datei"]


# ————— Der Schnitt in zwei Hälften (Teilscheibe I1) —————
#
# `_beleg_serverseitig_lesen` ist seit dem Massenimport nur noch die Hülle
# um `_beleg_einschaetzen` + `_beleg_review_ablegen`. Die Tests darüber
# prüfen die Hülle; hier steht, dass die Hälften einzeln dasselbe ergeben —
# sonst wäre der Schnitt eine Verhaltensänderung mit Tarnkappe.

def test_die_haelften_ergeben_dasselbe_review_wie_die_huelle(welt, monkeypatch):
    import json
    bw, bare = welt
    import gemma_buchung
    monkeypatch.setattr(gemma_buchung, "runde", lambda *a, **k: GEBUCHT)

    stamm = "20260827-200000-abcdef-beleg"
    pfad = f"docs/2026-08/{stamm}.jpg"
    daten = b"\xff\xd8\xff\xe0" + b"x" * 300
    _ablegen(bare, pfad, daten)
    asyncio.run(bw._beleg_serverseitig_lesen(pfad, daten, ".jpg", UN))
    ueber_huelle = json.loads(bw.git_show(f"review/{stamm}.json"))

    zwei = "20260827-201000-abcdef-beleg"
    zwei_pfad = f"docs/2026-08/{zwei}.jpg"
    _ablegen(bare, zwei_pfad, daten + b"anders")

    async def von_hand():
        ergebnis, zeilen = await bw._beleg_einschaetzen(
            daten, ".jpg", UN, "2026-08")
        assert ergebnis["status"] == "gebucht"
        review, md = bw._review_aus_einschaetzung(
            zwei_pfad, ergebnis["buchung"], zeilen, "beleg")
        hinweis = bw._doppelgaenger_hinweis(ergebnis["buchung"])
        if hinweis:
            review["felder"]["offen"].append(hinweis)
        assert await bw._beleg_review_ablegen(zwei_pfad, review, md, UN) is True
    asyncio.run(von_hand())
    ueber_haelften = json.loads(bw.git_show(f"review/{zwei}.json"))

    # Bis auf den Dateipfad und den Doppelgänger-Hinweis (der zweite Beleg
    # SIEHT den ersten, der erste sah niemanden) ist beides dasselbe.
    ueber_haelften["datei"] = ueber_huelle["datei"]
    assert ueber_haelften["felder"].pop("offen") != []      # der Hinweis kam an
    ueber_haelften["felder"]["offen"] = ueber_huelle["felder"]["offen"]
    assert ueber_haelften == ueber_huelle


def test_einschaetzen_meldet_ein_unlesbares_format_statt_zu_schweigen(welt, monkeypatch):
    """Die Hülle wirft `.xml` weg; der Import muss unterscheiden können,
    OB gelesen wurde — deshalb ein benannter Stand statt `None`."""
    bw, _ = welt
    import gemma_buchung
    monkeypatch.setattr(gemma_buchung, "runde",
                        lambda *a, **k: pytest.fail("darf nicht gerufen werden"))
    ergebnis, zeilen = asyncio.run(
        bw._beleg_einschaetzen(b"<xml/>", ".xml", UN, "2026-08"))
    assert ergebnis == {"status": "unlesbar_format"}
    assert zeilen == []


def test_ein_pdf_ohne_textebene_gilt_als_unlesbares_format(welt, monkeypatch):
    bw, _ = welt
    import abschluss_lesen
    import gemma_buchung
    monkeypatch.setattr(abschluss_lesen, "seiten_text", lambda pfad: [])
    monkeypatch.setattr(gemma_buchung, "runde",
                        lambda *a, **k: pytest.fail("darf nicht gerufen werden"))
    ergebnis, _ = asyncio.run(
        bw._beleg_einschaetzen(b"%PDF-1.4", ".pdf", UN, "2026-08"))
    assert ergebnis == {"status": "unlesbar_format"}


# ————— `_review_ueberschreibbar`: die drei Fälle —————

def test_ohne_review_darf_geschrieben_werden(welt):
    bw, _ = welt
    assert bw._review_ueberschreibbar("gibt-es-nicht") is True


def test_ein_echtes_review_bleibt_stehen(welt, monkeypatch):
    import json
    bw, _ = welt
    echt = {"buchung": {"status": "gebucht", "buchung": {}}}
    monkeypatch.setattr(bw, "git_show",
                        lambda pfad: json.dumps(echt).encode())
    assert bw._review_ueberschreibbar("stamm") is False


@pytest.mark.parametrize("stand", ["fragen", "aufgeben"])
def test_ein_platzhalter_darf_ersetzt_werden_solange_niemand_geantwortet_hat(
        welt, monkeypatch, stand):
    import json
    bw, _ = welt
    platzhalter = {"buchung": {"status": stand}}
    monkeypatch.setattr(bw, "git_show", lambda pfad: (
        json.dumps(platzhalter).encode() if pfad.endswith(f"stamm.json") else None))
    assert bw._review_ueberschreibbar("stamm") is True

    # Sobald ein Mensch etwas eingetragen hat, ist Schluss.
    monkeypatch.setattr(bw, "git_show", lambda pfad: (
        json.dumps(platzhalter).encode() if pfad.endswith("stamm.json")
        else b'{"brutto": 4.2}'))
    assert bw._review_ueberschreibbar("stamm") is False


def test_ein_kaputtes_review_wird_nicht_angefasst(welt, monkeypatch):
    """Was sich nicht lesen lässt, wird nicht überschrieben — im Zweifel
    steht dort etwas, das jemand braucht."""
    bw, _ = welt
    monkeypatch.setattr(bw, "git_show", lambda pfad: b"{kein json")
    assert bw._review_ueberschreibbar("stamm") is False


def test_ablegen_meldet_wenn_es_nicht_geschrieben_hat(welt, monkeypatch):
    import json
    bw, bare = welt
    stamm = "20260827-210000-abcdef-beleg"
    pfad = f"docs/2026-08/{stamm}.jpg"
    _ablegen(bare, pfad, b"\xff\xd8\xff\xe0" + b"x" * 300)
    echt = {"buchung": {"status": "gebucht", "buchung": {}}}
    import boxschreiber
    boxschreiber.schreiben({f"review/{stamm}.json": json.dumps(echt).encode()},
                           None, f"review: {stamm}", UN)
    review, md = bw._review_aus_einschaetzung(pfad, GEBUCHT["buchung"], [], "beleg")
    assert asyncio.run(bw._beleg_review_ablegen(pfad, review, md, UN)) is False
    assert json.loads(bw.git_show(f"review/{stamm}.json")) == echt


def test_ablage_stoesst_die_hintergrund_lesung_an(welt, monkeypatch):
    bw, _ = welt
    monkeypatch.setattr(bw, "angemeldet", lambda request: UN)
    monkeypatch.setattr(bw, "box_mitglied", lambda un: True)
    gesehen = {}
    monkeypatch.setattr(bw, "_hintergrund_lesen_starten",
                        lambda pfad, daten, endung, un: gesehen.update(
                            pfad=pfad, daten=daten, endung=endung, un=un))
    from fastapi.testclient import TestClient
    c = TestClient(bw.app, base_url="https://testserver")
    r = c.post("/ablage", files={"file": ("beleg.jpg",
              b"\xff\xd8\xff\xe0" + b"x" * 300, "image/jpeg")})
    assert r.status_code == 200, r.text
    assert gesehen["endung"] == ".jpg"
    assert gesehen["un"] == UN
    assert gesehen["pfad"] == r.json()["datei"]
