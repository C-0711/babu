"""Massenimport je Mandant — die Türen, der Lauf und die drei Ausgänge.

Was hier wirklich auf dem Spiel steht:

1. **Die Belege müssen in die richtige Box und mit den richtigen Konten.**
   Zwei echte bare-Stores; und der Faden bucht mit dem Profil und dem
   Kontenrahmen des SALONS, nicht denen der Kanzlei. Das ist die
   Verwechslung, die man einer Zahl nicht ansieht.
2. **Jeder Beleg bekommt ein Ergebnis.** Auch der, aus dem nichts wurde —
   sonst stünden zweihundert Belege auf „wird gelesen" und niemand merkte
   es.
3. **Nichts geht doppelt hinein und nichts von Hand Eingetragenes verloren.**
4. **Ein Abbruch, ein Fehler und ein Neustart müssen sichtbar sein** und
   sich fortsetzen lassen.

Der Worker wird SYNCHRON gerufen (`belegimport._import_lauf` direkt im
Mandanten-Kontext), nicht über den Faden, den die Route startet — aus
demselben Grund, aus dem `test_portal_upload_liest_serverseitig` die
Lesung direkt awaitet: ein Hintergrund-Faden hat keine verlässliche Chance,
vor dem Testende fertig zu werden, und ein Test, der auf eine Uhr wartet,
ist ein Test, der irgendwann von selbst kaputtgeht. Der Kontext wird dabei
in einem frischen `contextvars.Context` gesetzt, damit `_AKTIVE_BOX` nicht
in den nächsten Test hinüberleckt.
"""
import ast
import contextvars
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import babu_web  # noqa: E402
import belegimport as bi  # noqa: E402
import box as bx  # noqa: E402
import boxschreiber  # noqa: E402
import mandanten  # noqa: E402

KANZLEI = "kanzlei-a@0711.io"
SALON = "nina@0711.io"

GEBUCHT = {"status": "gebucht", "buchung": {
    "betrag_eur": 12.5, "datum": "2026-08-27", "lieferant": "Testladen",
    "ust_satz": 19, "konto": "6800", "kategorie": "buerobedarf",
    "kategorie_name": "Büromaterial", "dokumentklasse": "beleg"}}
FRAGEN = {"status": "fragen",
          "fragen": [{"frage": "Wofür war das?", "optionen": []}]}
AUFGEBEN = {"status": "aufgeben", "hinweis": "nichts zu erkennen"}

JPEG = b"\xff\xd8\xff\xe0"


def _leere_bare(tmp_path: Path, name: str) -> Path:
    arbeit = tmp_path / f"arbeit-{name}"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "README.md").write_text("box")
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "start"],
                   check=True, capture_output=True)
    bare = tmp_path / f"{name}.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)],
                   check=True)
    return bare


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    """Zwei Kanzleien, vier Mandanten, zwei echte Boxen.

    Kanzlei Süd betreut „Salon Nina" (Box `eins`), „Salon Ohne" (noch keine
    Box) und „Salon Pause" (Box, aber pausiert). Kanzlei Nord betreut
    „Salon Fremd" (Box `zwei`).
    """
    _leere_bare(tmp_path, "eins")
    _leere_bare(tmp_path, "zwei")

    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(babu_web, "STORE", tmp_path / "leer.git")
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(bx, "STORE_WURZEL", tmp_path)
    monkeypatch.setattr(bx, "KLON_WURZEL", tmp_path / "klone")
    # Im Betrieb geht der Push über das Gateway; hier ist das Push-Ziel der
    # bare-Store selbst — sonst prüfte dieser Test nur, ob HTTP kaputt ist.
    monkeypatch.setattr(bx, "remote_aus_ref",
                        lambda ref: str(tmp_path / (ref.strip("/") + ".git")))
    bx.registry_leeren()

    monkeypatch.setattr(bi, "IMPORT_TMP", tmp_path / "import-tmp")
    monkeypatch.setattr(bi, "IMPORT_ATEMPAUSE_SEK", 0)
    bi._IMPORT_JOBS.clear()
    bi._IMPORT_SHAS.clear()
    bi._START_VERSUCHE.clear()
    # Der Embedding-Dienst gehört nicht in diesen Test — und ohne ihn
    # dauerte jeder Beleg 15 Sekunden Zeitüberschreitung.
    monkeypatch.setattr(babu_web, "embedding_rechnen", lambda *a, **k: None)

    for mail, rolle in ((KANZLEI, "kanzlei"), ("kanzlei-b@0711.io", "kanzlei"),
                        ("betreiber@0711.io", "admin"), (SALON, "salon"),
                        ("ohne@0711.io", "salon"), ("pause@0711.io", "salon"),
                        ("fremd@0711.io", "salon")):
        babu_web.nutzer_anlegen(mail, mail.split("@")[0], "", rolle)

    with babu_web._DB_LOCK, babu_web._db() as c:
        a = mandanten.kanzlei_anlegen("Kanzlei Süd", KANZLEI, c=c)
        b = mandanten.kanzlei_anlegen("Kanzlei Nord", "kanzlei-b@0711.io", c=c)
        m_nina = mandanten.mandant_anlegen(a, "Salon Nina", SALON,
                                           kontenrahmen="SKR03", c=c)
        mandanten.box_verknuepfen(m_nina, "eins", c=c)
        m_ohne = mandanten.mandant_anlegen(a, "Salon Ohne", "ohne@0711.io", c=c)
        m_pause = mandanten.mandant_anlegen(a, "Salon Pause", "pause@0711.io", c=c)
        mandanten.box_verknuepfen(m_pause, "zwei", c=c)
        mandanten.status_setzen(m_pause, "pausiert", c=c)
        m_fremd = mandanten.mandant_anlegen(b, "Salon Fremd", "fremd@0711.io", c=c)
        mandanten.box_verknuepfen(m_fremd, "zwei", c=c)

    # Zwei verschiedene Profile — daran zeigt sich, wessen der Faden nimmt.
    babu_web.db_einstellung_setzen(SALON, "salon_name", "Salon Nina")
    babu_web.db_einstellung_setzen(KANZLEI, "salon_name", "Kanzlei Süd")

    wer = {"un": KANZLEI}
    monkeypatch.setattr(babu_web, "angemeldet", lambda request: wer["un"])
    monkeypatch.setattr(babu_web, "_origin_ok", lambda request: True)
    yield {"wer": wer, "nina": m_nina, "ohne": m_ohne, "pause": m_pause,
           "fremd": m_fremd, "tmp": tmp_path}
    bi._IMPORT_JOBS.clear()
    bi._IMPORT_SHAS.clear()
    bx.registry_leeren()


@pytest.fixture()
def k(welt):
    return TestClient(babu_web.app, base_url="https://testserver")


def _als(welt, un):
    welt["wer"]["un"] = un


def _hoch(k, mandant_id, name, daten=JPEG + b"eins", monat="2026-08"):
    return k.post(f"/api/kanzlei/mandanten/{mandant_id}/import/dateien",
                  params={"name": name, "monat": monat}, content=daten)


def _register(mandant_id):
    return bi._IMPORT_JOBS[mandant_id]


def _lauf_jetzt(un, mandant_id):
    """Den Worker synchron fahren — im eigenen, frischen Kontext."""
    status = bi._IMPORT_JOBS[mandant_id]
    status["stand"] = "wartet"
    box = bx.box_von(un, mandant_id)
    ktx = contextvars.Context()
    ktx.run(babu_web._im_mandanten_kontext, box, mandant_id,
            bi._import_lauf, babu_web, un, mandant_id, status["lauf"])
    return status


def _in_box(box, ziel, *args):
    """Etwas in der Box eines Mandanten lesen — im eigenen Kontext.

    Ohne den frischen `Context` bliebe `_AKTIVE_BOX` im Hauptfaden von
    pytest stehen, und anyio reicht genau diesen Kontext in jeden
    TestClient-Aufruf weiter — auch in die der NÄCHSTEN Testdatei. Ein
    fremder Test läse dann still die Box von hier.
    """
    return contextvars.Context().run(babu_web._im_box_kontext, box, ziel, *args)


def _runde(monkeypatch, antwort):
    """`gemma_buchung.runde` austauschen und mitschreiben, was sie sah."""
    import gemma_buchung
    gesehen = []

    def falsche_runde(zeilen, einstellungen, antworten, rahmen,
                      umsaetze=None, nachbarn=None, markdown=None, bild=None,
                      vertraege=None, personal=None, offene_abbuchungen=None):
        gesehen.append({"zeilen": zeilen, "einstellungen": einstellungen,
                        "rahmen": rahmen, "bild": bild})
        return antwort(len(gesehen)) if callable(antwort) else antwort
    monkeypatch.setattr(gemma_buchung, "runde", falsche_runde)
    return gesehen


def _commits(bare: Path) -> list[str]:
    return subprocess.run(["git", "-C", str(bare), "log", "--format=%s"],
                          capture_output=True, text=True).stdout.splitlines()


def _dateien(bare: Path) -> list[str]:
    return subprocess.run(["git", "-C", str(bare), "ls-tree", "-r",
                           "--name-only", "HEAD"],
                          capture_output=True, text=True).stdout.splitlines()


# ---------------------------------------------------------------------------
# Die Tür: wer darf, was geht hinein
# ---------------------------------------------------------------------------

def test_drei_dateien_landen_im_zwischenspeicher(welt, k):
    for i in range(3):
        r = _hoch(k, welt["nina"], f"bon{i}.jpg", JPEG + str(i).encode())
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
    status = _register(welt["nina"])
    assert status["stand"] == "sammelt"
    assert status["gesamt"] == 3
    ordner = bi._lauf_ordner(welt["nina"], status["lauf"])
    assert len(list(ordner.iterdir())) == 3
    # Noch ist nichts in der Belegbox — Start ist Start.
    assert _dateien(welt["tmp"] / "eins.git") == ["README.md"]


@pytest.mark.parametrize("name", ["stapel.xml", "liste.csv", "notiz.txt"])
def test_was_kein_beleg_ist_kommt_nicht_hinein(welt, k, name):
    assert _hoch(k, welt["nina"], name).status_code == 400


def test_eine_leere_datei_wird_abgewiesen(welt, k):
    assert _hoch(k, welt["nina"], "leer.jpg", b"").status_code == 400


def test_zu_gross_wird_schon_am_kopf_abgewiesen(welt, k):
    """Die Grenze greift VOR dem Lesen — `koerper_lesen` sieht den
    Content-Length-Kopf und bricht ab, statt 41 MB in den Speicher zu
    nehmen."""
    r = k.post(f"/api/kanzlei/mandanten/{welt['nina']}/import/dateien",
               params={"name": "riesig.jpg"}, content=JPEG,
               headers={"Content-Length": str(41 * 1024 * 1024)})
    assert r.status_code == 413


def test_ein_fremder_mandant_gibt_404_und_nicht_403(welt, k):
    """404 und nicht 403 — sonst ließe sich die Nachbarkanzlei abzählen."""
    assert _hoch(k, welt["fremd"], "bon.jpg").status_code == 404
    assert k.get(f"/api/kanzlei/mandanten/{welt['fremd']}/import").status_code == 404


def test_ein_salon_kommt_hier_gar_nicht_hinein(welt, k):
    _als(welt, SALON)
    assert _hoch(k, welt["nina"], "bon.jpg").status_code == 403


def test_ohne_belegbox_und_pausiert_gibt_409(welt, k):
    r = _hoch(k, welt["ohne"], "bon.jpg")
    assert r.status_code == 409 and "Belegbox" in r.json()["fehler"]
    r = _hoch(k, welt["pause"], "bon.jpg")
    assert r.status_code == 409 and "pausiert" in r.json()["fehler"]


def test_ohne_passenden_absender_wird_nicht_geschrieben(welt, k, monkeypatch):
    monkeypatch.setattr(babu_web, "_origin_ok", lambda request: False)
    assert _hoch(k, welt["nina"], "bon.jpg").status_code == 403
    assert k.post(f"/api/kanzlei/mandanten/{welt['nina']}/import/start"
                  ).status_code == 403
    # Lesen darf man weiter — ein GET ändert nichts.
    assert k.get(f"/api/kanzlei/mandanten/{welt['nina']}/import"
                 ).status_code == 200


def test_mehr_als_die_obergrenze_wird_abgelehnt(welt, k, monkeypatch):
    monkeypatch.setattr(bi, "IMPORT_MAX_DATEIEN", 2)
    for i in range(2):
        assert _hoch(k, welt["nina"], f"bon{i}.jpg", JPEG + str(i).encode()
                     ).status_code == 200
    r = _hoch(k, welt["nina"], "bon2.jpg", JPEG + b"2")
    assert r.status_code == 400 and "zwei Portionen" in r.json()["fehler"]


# ---------------------------------------------------------------------------
# Das Ablegen: Bündel, richtige Box
# ---------------------------------------------------------------------------

def test_25_dateien_werden_genau_zwei_commits(welt, k, monkeypatch):
    _runde(monkeypatch, GEBUCHT)
    for i in range(25):
        assert _hoch(k, welt["nina"], f"bon{i:02d}.jpg",
                     JPEG + str(i).encode()).status_code == 200
    status = _lauf_jetzt(KANZLEI, welt["nina"])
    lauf = status["lauf"]
    betreffs = _commits(welt["tmp"] / "eins.git")
    import_commits = [b for b in betreffs if b.startswith(f"import {lauf}")]
    assert len(import_commits) == 2, betreffs
    assert import_commits[0].endswith("5 Belege")
    assert import_commits[1].endswith("20 Belege")
    assert status["abgelegt"] == 25
    # Und die Nachbarbox hat davon nichts gesehen.
    assert _dateien(welt["tmp"] / "zwei.git") == ["README.md"]


def test_der_zwischenspeicher_ist_nach_dem_ablegen_leer(welt, k, monkeypatch):
    _runde(monkeypatch, GEBUCHT)
    _hoch(k, welt["nina"], "bon.jpg")
    status = _lauf_jetzt(KANZLEI, welt["nina"])
    ordner = bi._lauf_ordner(welt["nina"], status["lauf"])
    assert not ordner.exists() or not list(ordner.iterdir())


# ---------------------------------------------------------------------------
# Der Kontext: wessen Profil, wessen Kontenrahmen
# ---------------------------------------------------------------------------

def test_der_faden_bucht_mit_profil_und_rahmen_des_salons(welt, k, monkeypatch):
    """Die Verwechslung, die man einer Zahl nicht ansieht: die Belege lägen
    in der richtigen Box, die Konten kämen aus der Kanzlei."""
    gesehen = _runde(monkeypatch, GEBUCHT)
    _hoch(k, welt["nina"], "bon.jpg")
    _lauf_jetzt(KANZLEI, welt["nina"])
    assert len(gesehen) == 1
    assert gesehen[0]["einstellungen"].get("salon_name") == "Salon Nina"
    assert gesehen[0]["rahmen"] == "SKR03"       # am Mandanten, nicht am Server
    assert gesehen[0]["bild"] == (JPEG + b"eins", "image/jpeg")


# ---------------------------------------------------------------------------
# Die drei Ausgänge: gebucht, Rückfrage, unlesbar
# ---------------------------------------------------------------------------

def test_gebucht_fragen_aufgeben_ergeben_drei_sichtbare_stände(welt, k, monkeypatch):
    antworten = {1: GEBUCHT, 2: FRAGEN, 3: AUFGEBEN}
    _runde(monkeypatch, lambda n: antworten[n])
    for i, name in enumerate(["a.jpg", "b.jpg", "c.jpg"]):
        _hoch(k, welt["nina"], name, JPEG + str(i).encode())
    status = _lauf_jetzt(KANZLEI, welt["nina"])

    assert status["stand"] == "fertig"
    assert (status["gebucht"], status["rueckfrage"], status["unlesbar"]) == (1, 1, 1)
    staende = {d["name"]: d["stand"] for d in status["dateien"]}
    assert staende == {"a.jpg": "gebucht", "b.jpg": "rueckfrage",
                       "c.jpg": "unlesbar"}
    grund = {d["name"]: d["grund"] for d in status["dateien"]}
    assert grund["b.jpg"] == "Wofür war das?"

    # Und so sieht der Index das:
    box = bx.box_von(KANZLEI, welt["nina"])
    idx = _in_box(box, babu_web.index_aktuell)
    nach_datei = {z["datei"].rsplit("-", 1)[-1]: z for z in idx["belege"].values()}
    assert nach_datei["a.jpg"]["status"] == "geprüft"
    assert nach_datei["b.jpg"]["status"] == "nachfrage"
    assert nach_datei["b.jpg"]["offen"] == ["Wofür war das?"]
    assert nach_datei["c.jpg"]["status"] == "unlesbar"


def test_die_rueckfrage_steht_im_cockpit_und_laesst_sich_beantworten(
        welt, k, monkeypatch):
    _runde(monkeypatch, FRAGEN)
    _hoch(k, welt["nina"], "bon.jpg")
    _lauf_jetzt(KANZLEI, welt["nina"])

    # Ohne gelesenes Belegdatum entscheidet der Zeitstempel im Dateinamen
    # über den Monat (`_beleg_monat` → `_monat_aus_name`) — das ist heute,
    # nicht der Monat aus dem Ablagepfad.
    jetzt = time.strftime("%Y-%m")
    r = k.get(f"/api/kanzlei/mandanten/{welt['nina']}/monate",
              params={"anzahl": 24})
    assert r.status_code == 200, r.text
    monate = {m["monat"]: m for m in r.json()["monate"]}
    fragen = monate[jetzt]["rueckfragen"]
    assert len(fragen) == 1 and fragen[0]["frage"] == "Wofür war das?"
    stamm = fragen[0]["stamm"]

    # Die Kanzlei beantwortet sie im Namen des Mandanten (Acting-as).
    r = k.post(f"/api/angaben/{stamm}", json={"brutto": "12,50"},
               headers={"X-Mandant": str(welt["nina"])})
    assert r.status_code == 200, r.text
    monate = {m["monat"]: m for m in k.get(
        f"/api/kanzlei/mandanten/{welt['nina']}/monate",
        params={"anzahl": 24}).json()["monate"]}
    assert monate[jetzt]["rueckfragen"] == []
    assert monate[jetzt]["belege"]["geprueft"] == 1


def test_eine_ausnahme_in_der_buchhaltung_macht_den_beleg_unlesbar(
        welt, k, monkeypatch):
    """Ein Dienst, der gerade weg ist, darf den Lauf nicht anhalten."""
    import gemma_buchung

    def wirft(*a, **kw):
        raise RuntimeError("kein Netz zur Buchhaltung")
    monkeypatch.setattr(gemma_buchung, "runde", wirft)
    _hoch(k, welt["nina"], "bon.jpg")
    status = _lauf_jetzt(KANZLEI, welt["nina"])
    assert status["stand"] == "fertig"
    assert status["unlesbar"] == 1
    assert status["dateien"][0]["stand"] == "unlesbar"


# ---------------------------------------------------------------------------
# Nichts doppelt
# ---------------------------------------------------------------------------

def test_dieselbe_datei_zweimal_im_lauf_ist_doppelt(welt, k, monkeypatch):
    gesehen = _runde(monkeypatch, GEBUCHT)
    assert _hoch(k, welt["nina"], "bon.jpg").json().get("doppelt") is None
    zweite = _hoch(k, welt["nina"], "nochmal.jpg").json()
    assert zweite["doppelt"] is True
    status = _lauf_jetzt(KANZLEI, welt["nina"])
    assert status["doppelt"] == 1
    assert status["abgelegt"] == 1
    assert len(gesehen) == 1


def test_derselbe_ordner_ein_zweites_mal_ist_ganz_doppelt(welt, k, monkeypatch):
    gesehen = _runde(monkeypatch, GEBUCHT)
    for i in range(3):
        _hoch(k, welt["nina"], f"bon{i}.jpg", JPEG + str(i).encode())
    _lauf_jetzt(KANZLEI, welt["nina"])
    assert len(gesehen) == 3
    vorher = _commits(welt["tmp"] / "eins.git")

    for i in range(3):
        antwort = _hoch(k, welt["nina"], f"bon{i}.jpg", JPEG + str(i).encode())
        assert antwort.json()["doppelt"] is True
    status = _register(welt["nina"])
    assert status["doppelt"] == 3 and status["gesamt"] == 3
    assert _commits(welt["tmp"] / "eins.git") == vorher
    assert len(gesehen) == 3, "kein zweiter Aufruf an die Buchhaltung"


def test_ein_doppelgaenger_wird_zur_rueckfrage(welt, k, monkeypatch):
    """Gleicher Tag, gleicher Betrag — fragen, nicht blocken."""
    _runde(monkeypatch, GEBUCHT)
    _hoch(k, welt["nina"], "a.jpg", JPEG + b"a")
    _hoch(k, welt["nina"], "b.jpg", JPEG + b"b")
    status = _lauf_jetzt(KANZLEI, welt["nina"])
    staende = [d["stand"] for d in sorted(status["dateien"],
                                          key=lambda d: d["name"])]
    assert staende == ["gebucht", "rueckfrage"]
    zweite = sorted(status["dateien"], key=lambda d: d["name"])[1]
    assert "Doppelgänger" in zweite["grund"]


# ---------------------------------------------------------------------------
# Was von Hand kam, bleibt
# ---------------------------------------------------------------------------

def test_ein_review_von_hand_wird_nie_ueberschrieben(welt, k, monkeypatch):
    _runde(monkeypatch, GEBUCHT)
    _hoch(k, welt["nina"], "bon.jpg")
    status = _register(welt["nina"])
    datei = status["dateien"][0]["datei"]
    stamm = Path(datei).name.rsplit(".", 1)[0]
    box = bx.box_von(KANZLEI, welt["nina"])
    von_hand = {"datei": datei, "von_hand": True,
                "felder": {"brutto": 4.2, "offen": []}}
    boxschreiber.schreiben(box, {f"review/{stamm}.json":
                                 json.dumps(von_hand).encode()},
                           None, f"angaben: {stamm}", KANZLEI)
    _lauf_jetzt(KANZLEI, welt["nina"])

    roh = _in_box(box, babu_web.git_show, f"review/{stamm}.json")
    assert json.loads(roh) == von_hand
    assert status["dateien"][0]["stand"] == "uebersprungen"


def test_ein_platzhalter_wird_beim_fortsetzen_ersetzt(welt, k, monkeypatch):
    """Erst kommt nichts heraus, dann doch — der Platzhalter darf weichen,
    solange niemand von Hand geantwortet hat."""
    _runde(monkeypatch, AUFGEBEN)
    _hoch(k, welt["nina"], "bon.jpg")
    status = _lauf_jetzt(KANZLEI, welt["nina"])
    assert status["unlesbar"] == 1
    stamm = Path(status["dateien"][0]["datei"]).name.rsplit(".", 1)[0]

    _runde(monkeypatch, GEBUCHT)
    r = k.post(f"/api/kanzlei/mandanten/{welt['nina']}/import/fortsetzen",
               params={"nur": "unlesbar"})
    assert r.status_code == 200, r.text
    assert r.json()["dateien"] == 1
    neu = _lauf_jetzt(KANZLEI, welt["nina"])
    assert neu["gebucht"] == 1

    box = bx.box_von(KANZLEI, welt["nina"])
    review = json.loads(_in_box(box, babu_web.git_show,
                                f"review/{stamm}.json"))
    assert review["felder"]["brutto"] == 12.5
    assert review["dokumentklasse"] == "beleg"


# ---------------------------------------------------------------------------
# Abbrechen, fortsetzen, Neustart
# ---------------------------------------------------------------------------

def test_abbruch_nach_dem_zweiten_beleg(welt, k, monkeypatch):
    """Die gepatchte Buchhaltung drückt selbst auf Abbrechen — so liegt der
    Zeitpunkt fest und nicht in der Hand einer Uhr."""
    zaehler = {"n": 0}

    def antwort(n):
        zaehler["n"] = n
        if n == 2:
            k.post(f"/api/kanzlei/mandanten/{welt['nina']}/import/abbrechen")
        return GEBUCHT
    _runde(monkeypatch, antwort)
    for i in range(5):
        _hoch(k, welt["nina"], f"bon{i}.jpg", JPEG + str(i).encode())
    status = _lauf_jetzt(KANZLEI, welt["nina"])

    assert status["stand"] == "abgebrochen"
    assert zaehler["n"] == 2
    staende = [d["stand"] for d in sorted(status["dateien"],
                                          key=lambda d: d["name"])]
    assert staende[:2] == ["gebucht", "rueckfrage"]   # 2. ist Doppelgänger
    assert staende[2:] == ["abgelegt", "abgelegt", "abgelegt"]


def test_fortsetzen_liest_die_abgelegten_aus_der_box(welt, k, monkeypatch):
    """Nach dem Abbruch ist der Zwischenspeicher leer — was noch fehlt,
    holt sich der zweite Lauf aus der Belegbox."""
    def antwort(n):
        if n == 1:
            k.post(f"/api/kanzlei/mandanten/{welt['nina']}/import/abbrechen")
        return GEBUCHT
    _runde(monkeypatch, antwort)
    for i in range(3):
        _hoch(k, welt["nina"], f"bon{i}.jpg", JPEG + str(i).encode())
    erster = _lauf_jetzt(KANZLEI, welt["nina"])
    assert erster["stand"] == "abgebrochen"

    gesehen = _runde(monkeypatch, GEBUCHT)
    r = k.post(f"/api/kanzlei/mandanten/{welt['nina']}/import/fortsetzen")
    assert r.status_code == 200, r.text
    assert r.json()["dateien"] == 2
    zweiter = _lauf_jetzt(KANZLEI, welt["nina"])
    assert zweiter["stand"] == "fertig"
    assert len(gesehen) == 2
    # Kein neuer Ablage-Commit — die Dateien lagen längst in der Box.
    lauf = zweiter["lauf"]
    assert not [b for b in _commits(welt["tmp"] / "eins.git")
                if b.startswith(f"import {lauf}")]


def test_nach_einem_neustart_heisst_der_lauf_unterbrochen(welt, k, monkeypatch):
    _runde(monkeypatch, GEBUCHT)
    _hoch(k, welt["nina"], "bon.jpg")
    status = _register(welt["nina"])
    status["stand"] = "liest"
    babu_web.db_import_snapshot(welt["nina"], status)
    bi._IMPORT_JOBS.clear()          # so sieht ein frischer Prozess aus

    r = k.get(f"/api/kanzlei/mandanten/{welt['nina']}/import")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    d = r.json()
    assert d["stand"] == "unterbrochen"
    assert "Fortsetzen" in d["hinweis"]


def test_ohne_jeden_lauf_steht_da_leer(welt, k):
    r = k.get(f"/api/kanzlei/mandanten/{welt['nina']}/import")
    assert r.status_code == 200 and r.json() == {"stand": "leer"}


def test_eine_datei_die_nur_im_zwischenspeicher_lag_muss_neu_ausgewaehlt_werden(
        welt, k, monkeypatch):
    _runde(monkeypatch, GEBUCHT)
    _hoch(k, welt["nina"], "bon.jpg")
    status = _register(welt["nina"])
    status["stand"] = "liest"
    babu_web.db_import_snapshot(welt["nina"], status)
    bi._IMPORT_JOBS.clear()
    # Der Zwischenspeicher ist nach dem Neustart weg (tmpfs, Aufräumen).
    import shutil
    shutil.rmtree(bi.IMPORT_TMP, ignore_errors=True)

    r = k.post(f"/api/kanzlei/mandanten/{welt['nina']}/import/fortsetzen")
    assert r.status_code == 409, r.text
    assert "nichts mehr offen" in r.json()["fehler"]
    neu = bi.fortsetzung_bauen(babu_web.db_import_lesen(welt["nina"]))
    assert neu["dateien"][0]["stand"] == "uebersprungen"
    assert neu["dateien"][0]["grund"] == bi.GRUND_NOCHMAL


# ---------------------------------------------------------------------------
# Bremse, Audit, Warteschlange
# ---------------------------------------------------------------------------

def test_die_sechste_startanforderung_wird_gebremst(welt, k, monkeypatch):
    _runde(monkeypatch, GEBUCHT)
    codes = []
    for i in range(6):
        _hoch(k, welt["nina"], f"bon{i}.jpg", JPEG + str(i).encode())
        # Der Faden der Route findet nichts mehr vor (der Lauf steht auf
        # „wartet") — geprüft wird hier die Bremse, nicht der Lauf.
        codes.append(k.post(
            f"/api/kanzlei/mandanten/{welt['nina']}/import/start").status_code)
        bi._IMPORT_JOBS.clear()
        bi._IMPORT_SHAS.clear()
    assert codes[:5] == [200] * 5
    assert codes[5] == 429


def test_start_und_ende_stehen_im_audit(welt, k, monkeypatch):
    _runde(monkeypatch, GEBUCHT)
    _hoch(k, welt["nina"], "bon.jpg")
    assert k.post(f"/api/kanzlei/mandanten/{welt['nina']}/import/start"
                  ).status_code == 200
    _lauf_jetzt(KANZLEI, welt["nina"])
    with babu_web._DB_LOCK, babu_web._db() as c:
        zeilen = c.execute(
            "SELECT aktion, akteur_un, ziel_un, mandant_id, details "
            "FROM audit_log WHERE aktion LIKE 'kanzlei_import%'").fetchall()
    aktionen = {z[0]: z for z in zeilen}
    assert set(aktionen) == {"kanzlei_import_start", "kanzlei_import_ende"}
    for name, zeile in aktionen.items():
        assert zeile[1] == KANZLEI, name
        assert zeile[2] == SALON, name
        assert zeile[3] == str(welt["nina"]), name
    details = json.loads(aktionen["kanzlei_import_ende"][4])
    assert details["gebucht"] == 1 and details["gesamt"] == 1
    assert details["stand"] == "fertig"


def test_ein_zweiter_mandant_wartet_statt_zu_draengeln(welt, k, monkeypatch):
    """Ein Lauf zur Zeit im Prozess. Der zweite steht sichtbar auf „wartet"
    und macht weiter, sobald der erste durch ist."""
    _runde(monkeypatch, GEBUCHT)
    _als(welt, "betreiber@0711.io")
    _hoch(k, welt["fremd"], "bon.jpg")
    status = bi._IMPORT_JOBS[welt["fremd"]]
    status["stand"] = "wartet"

    bi._IMPORT_WORKER_LOCK.acquire()
    faden = threading.Thread(
        target=lambda: contextvars.Context().run(
            babu_web._im_mandanten_kontext,
            bx.box_von("betreiber@0711.io", welt["fremd"]), welt["fremd"],
            bi._import_lauf, babu_web, "betreiber@0711.io", welt["fremd"],
            status["lauf"]),
        daemon=True)
    faden.start()
    try:
        # Solange das Schloss liegt, passiert nichts — und das steht dran.
        frist = time.monotonic() + 2.0
        while status["hinweis"] != bi.HINWEIS_WARTET and time.monotonic() < frist:
            time.sleep(0.01)
        assert status["hinweis"] == bi.HINWEIS_WARTET
        assert status["stand"] == "wartet"
        assert status["abgelegt"] == 0
    finally:
        bi._IMPORT_WORKER_LOCK.release()
    faden.join(timeout=20)
    assert not faden.is_alive()
    assert status["stand"] == "fertig"
    assert status["gebucht"] == 1


# ---------------------------------------------------------------------------
# Zwei Wächter über den Quelltext
# ---------------------------------------------------------------------------

def test_jeder_schreibweg_in_belegimport_kennt_seine_box():
    """Wie `test_jeder_schreibweg_kennt_seine_box.py` für `babu_web`.

    `boxschreiber.schreiben()` nimmt seit Plan 21 die Box als erstes
    Argument, und eine Übergangsschale ersetzt eine fehlende durch die
    Default-Box. Ein vergessenes Argument fiele also nicht auf — es
    schriebe still in die Box der Kanzlei statt in die des Mandanten.
    """
    baum = ast.parse((HIER.parent / "belegimport.py").read_text())
    treffer, ohne = 0, []
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        f = knoten.func
        if not (isinstance(f, ast.Attribute)
                and f.attr in ("schreiben", "loeschen")
                and isinstance(f.value, ast.Name)
                and f.value.id == "boxschreiber"):
            continue
        erstes = knoten.args[0] if knoten.args else None
        if isinstance(erstes, ast.Name) and erstes.id == "box":
            treffer += 1
        else:
            ohne.append(f"  belegimport.py:{knoten.lineno}")
    assert not ohne, ("Schreibweg ohne Box — landet still in der falschen "
                      "Box:\n" + "\n".join(ohne))
    assert treffer >= 1, "sucht der Wächter noch?"


def test_die_import_endungen_sind_die_upload_endungen_ohne_xml():
    """Die Liste steht doppelt (Import-Kreis, siehe `belegimport`) — hier
    wird sie zusammengehalten."""
    assert set(bi.IMPORT_ENDUNGEN) == set(babu_web.HOCHLADEN_ENDUNGEN) - {".xml"}
