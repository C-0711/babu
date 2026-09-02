"""Die Mandantenseite der Kanzlei — wer was sehen darf, und was ansteht.

Vier Dinge, an denen hier wirklich etwas hängt:

1. **Rollenschutz.** Ein Salon-Zugang darf die Mandantenliste nicht einmal
   sehen — sie nennt Namen und E-Mail-Adressen fremder Betriebe.
2. **Die Grenze zwischen zwei Kanzleien.** Kanzlei A darf die Mandanten von
   Kanzlei B weder auflisten noch einzeln aufrufen. Das ist die Lücke, die
   das Erkundungsdokument benannt hat: bis Plan 21 sah jede Kanzlei-Rolle
   jede Box.
3. **Kein Klartext.** Anlegen erzeugt ein Konto, aber nirgends in der
   Datenbank steht ein Passwort oder ein Einladungsschlüssel im Klartext.
4. **Das Zeitbudget.** Eine hängende Box darf die Übersicht nicht anhalten —
   sie steht als „nicht erreichbar" darin, und zwar rechtzeitig.

Die Boxen sind echt (zwei bare-Stores nach dem Muster aus
`test_zwei_boxen.py`), damit die Aggregation wirklich zwei getrennte Indizes
liest und nicht zweimal denselben.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import babu_web  # noqa: E402
import box as bx  # noqa: E402
import boxschreiber  # noqa: E402
import kanzlei_routen as kr  # noqa: E402
import mandanten  # noqa: E402

GOLDEN = json.loads((HIER / "golden" / "review_weingaertle.json").read_text())


# ---------------------------------------------------------------------------
# Eine Wegwerf-Belegbox mit Belegen in genau den Ständen, die die Übersicht
# zählt: eine offene Rückfrage, ein geprüfter Beleg.
# ---------------------------------------------------------------------------

def _bare(tmp_path: Path, name: str, belege: list[tuple[str, str, list]]) -> Path:
    arbeit = tmp_path / f"arbeit-{name}"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "review").mkdir(parents=True, exist_ok=True)
    for monat, stamm, offen in belege:
        ordner = arbeit / "docs" / monat
        ordner.mkdir(parents=True, exist_ok=True)
        (ordner / f"{stamm}.jpg").write_bytes(b"\xff\xd8\xff\xe0" + stamm.encode())
        review = json.loads(json.dumps(GOLDEN))
        review["datei"] = f"docs/{monat}/{stamm}.jpg"
        review["felder"].update(offen=offen, bewirtungssignal=False,
                                summenprobe_ok=None)
        (arbeit / "review" / f"{stamm}.json").write_text(
            json.dumps(review, ensure_ascii=False))
    subprocess.run(["git", "-C", str(arbeit), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(arbeit), "commit", "-q", "-m", "stand"],
                   check=True, capture_output=True)
    bare = tmp_path / f"{name}.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(bare)],
                   check=True)
    return bare


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    """Zwei Kanzleien, drei Mandanten, zwei echte Boxen.

    Kanzlei Süd (Inhaberin `kanzlei-a@0711.io`) betreut „Salon Nina" (Box
    `eins`, eine offene Rückfrage) und „Salon Ohne" (noch keine Box).
    Kanzlei Nord betreut „Salon Fremd" (Box `zwei`, nichts offen).
    """
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(babu_web, "STORE", tmp_path / "leer.git")
    # Die Boxen der Mandanten werden über `mandant.box_ref` aufgelöst —
    # `store_aus_ref` hängt sie unter diese Wurzel.
    monkeypatch.setattr(bx, "STORE_WURZEL", tmp_path)
    monkeypatch.setattr(bx, "KLON_WURZEL", tmp_path / "klone")
    bx.registry_leeren()

    _bare(tmp_path, "eins", [
        ("2026-05", "20260501-120000-aaa111-alpha", ["Wofür war das?"]),
        ("2026-05", "20260502-120000-aaa112-beta", []),
    ])
    _bare(tmp_path, "zwei", [("2026-05", "20260501-120000-bbb222-gamma", [])])

    # Konten: zwei Kanzleien, eine Vertretung, drei Salons.
    for mail, rolle in (("kanzlei-a@0711.io", "kanzlei"),
                        ("vertretung-a@0711.io", "kanzlei"),
                        ("kanzlei-b@0711.io", "kanzlei"),
                        ("betreiber@0711.io", "admin"),
                        ("nina@0711.io", "salon"),
                        # Postgres prüft den Fremdschlüssel mandant.besitzer_un
                        # → nutzer.email wirklich; SQLite ließ es durchgehen.
                        ("ohne@0711.io", "salon"),
                        ("fremd@0711.io", "salon")):
        babu_web.nutzer_anlegen(mail, mail.split("@")[0], "", rolle)

    with babu_web._DB_LOCK, babu_web._db() as c:
        a = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei-a@0711.io", c=c)
        mandanten.mitglied_anlegen(a, "vertretung-a@0711.io", c=c)
        b = mandanten.kanzlei_anlegen("Kanzlei Nord", "kanzlei-b@0711.io", c=c)
        m_nina = mandanten.mandant_anlegen(a, "Salon Nina", "nina@0711.io", c=c)
        mandanten.box_verknuepfen(m_nina, "eins", c=c)
        m_ohne = mandanten.mandant_anlegen(a, "Salon Ohne", "ohne@0711.io", c=c)
        m_fremd = mandanten.mandant_anlegen(b, "Salon Fremd", "fremd@0711.io", c=c)
        mandanten.box_verknuepfen(m_fremd, "zwei", c=c)

    wer = {"un": "kanzlei-a@0711.io"}
    monkeypatch.setattr(babu_web, "angemeldet", lambda request: wer["un"])
    monkeypatch.setattr(babu_web, "_origin_ok", lambda request: True)
    yield {"wer": wer, "kanzlei_a": a, "kanzlei_b": b, "nina": m_nina,
           "ohne": m_ohne, "fremd": m_fremd, "tmp": tmp_path}
    bx.registry_leeren()
    kr._ANLAGE_VERSUCHE.clear()
    kr._VERKNUEPFEN_VERSUCHE.clear()


@pytest.fixture()
def k(welt):
    return TestClient(babu_web.app, base_url="https://testserver")


def _als(welt, un):
    welt["wer"]["un"] = un


# ── Rollenschutz ────────────────────────────────────────────────────────

def test_ein_salon_sieht_die_mandantenliste_nicht(welt, k):
    """Die Liste nennt Namen und Adressen fremder Betriebe — ein
    Salon-Zugang hat darin nichts zu suchen."""
    _als(welt, "nina@0711.io")
    for pfad in ("/api/kanzlei/mandanten", "/api/kanzlei/warteschlange",
                 f"/api/kanzlei/mandanten/{welt['nina']}"):
        assert k.get(pfad).status_code == 403, pfad
    assert k.post("/api/kanzlei/mandanten",
                  json={"name": "X", "email": "x@y.de"}).status_code == 403


def test_ohne_anmeldung_gibt_es_gar_nichts(welt, k, monkeypatch):
    monkeypatch.setattr(babu_web, "angemeldet", lambda request: None)
    assert k.get("/api/kanzlei/mandanten").status_code == 401


# ── Die Grenze zwischen zwei Kanzleien ──────────────────────────────────

def test_kanzlei_a_sieht_die_mandanten_von_kanzlei_b_nicht(welt, k):
    d = k.get("/api/kanzlei/mandanten").json()
    namen = {m["name"] for m in d["mandanten"]}
    assert namen == {"Salon Nina", "Salon Ohne"}
    assert "Salon Fremd" not in namen


def test_der_einzelaufruf_eines_fremden_mandanten_ist_ein_404(welt, k):
    """404 und nicht 403: ein „darfst du nicht" verriete, dass es ihn gibt —
    damit ließe sich die Mandantenzahl der Nachbarkanzlei abzählen."""
    r = k.get(f"/api/kanzlei/mandanten/{welt['fremd']}")
    assert r.status_code == 404
    assert "gibt es hier nicht" in r.json()["fehler"]


def test_die_vertretung_sieht_dieselben_mandanten_wie_die_inhaberin(welt, k):
    _als(welt, "vertretung-a@0711.io")
    namen = {m["name"] for m in k.get("/api/kanzlei/mandanten").json()["mandanten"]}
    assert namen == {"Salon Nina", "Salon Ohne"}


def test_der_betreiber_sieht_alle_kanzleien(welt, k):
    _als(welt, "betreiber@0711.io")
    d = k.get("/api/kanzlei/mandanten").json()
    assert {m["name"] for m in d["mandanten"]} == {"Salon Nina", "Salon Ohne",
                                                  "Salon Fremd"}
    assert d["darf_verknuepfen"] is True


def test_die_kanzlei_bekommt_den_ablageort_der_box_nicht_zu_sehen(welt, k):
    """`box_ref` ist ein Pfad im fremden Gateway — er sagt der Kanzlei
    nichts und gehört nicht auf ihren Bildschirm."""
    d = k.get("/api/kanzlei/mandanten").json()
    assert all("box_ref" not in m for m in d["mandanten"])
    assert [m for m in d["mandanten"] if m["name"] == "Salon Nina"][0]["belegbox_da"]
    _als(welt, "betreiber@0711.io")
    d = k.get("/api/kanzlei/mandanten").json()
    assert any(m.get("box_ref") == "eins" for m in d["mandanten"])


# ── Suche und Blättern ──────────────────────────────────────────────────

def test_die_suche_greift_auf_namen_und_adresse(welt, k):
    assert {m["name"] for m in
            k.get("/api/kanzlei/mandanten?q=nina").json()["mandanten"]} == {"Salon Nina"}
    assert {m["name"] for m in
            k.get("/api/kanzlei/mandanten?q=ohne@").json()["mandanten"]} == {"Salon Ohne"}
    assert k.get("/api/kanzlei/mandanten?q=gibtsnicht").json()["gesamt"] == 0


def test_geblaettert_wird_zu_fuenfundzwanzig(welt, k):
    d = k.get("/api/kanzlei/mandanten").json()
    assert d["je_seite"] == 25 and d["seite"] == 1 and d["seiten"] == 1
    d = k.get("/api/kanzlei/mandanten?je_seite=1&seite=2").json()
    assert d["seiten"] == 2 and len(d["mandanten"]) == 1


def test_nach_status_laesst_sich_filtern(welt, k):
    d = k.get("/api/kanzlei/mandanten?status=box_ausstehend").json()
    assert {m["name"] for m in d["mandanten"]} == {"Salon Ohne"}


# ── Anlegen ─────────────────────────────────────────────────────────────

def _alle_werte(pfad: Path) -> str:
    """Jede Textzelle der Datenbank am Stück — für die Klartext-Probe.

    Über `babu_web._db()`, damit die Probe in beiden Dialekten dieselbe
    Datenbank liest, gegen die die Route geschrieben hat (unter Postgres
    liegt in `pfad` gar nichts)."""
    stuecke = []
    with babu_web._DB_LOCK, babu_web._db() as c:
        if c.dialekt == "sqlite":
            frage = "SELECT name FROM sqlite_master WHERE type='table'"
        else:
            frage = ("SELECT table_name FROM information_schema.tables "
                     "WHERE table_schema = current_schema()")
        tabellen = [z[0] for z in c.execute(frage).fetchall()]
        for t in tabellen:
            for zeile in c.execute(f"SELECT * FROM {t}").fetchall():
                stuecke.extend(str(w) for w in zeile)
    return "\n".join(stuecke)


def test_anlegen_erzeugt_kanzlei_mandant_konto_und_einladung(welt, k, monkeypatch):
    """Der ganze Weg in einem Aufruf — und danach steht das Konto, der
    Mandant wartet auf seine Box, und ein Link ist unterwegs."""
    gesendet = []
    import postfach
    monkeypatch.setattr(postfach, "senden",
                        lambda an, betreff, text, *, stempel: (
                            gesendet.append((an, betreff, text)) or (True, "ok")))
    # Ein Zugang ohne eigene Kanzlei — die Kanzlei-Zeile muss mit entstehen.
    babu_web.nutzer_anlegen("neu-kanzlei@0711.io", "Neu", "", "kanzlei")
    babu_web.db_einstellung_setzen("neu-kanzlei@0711.io", "kanzlei_name",
                                   "Kanzlei Neu")
    _als(welt, "neu-kanzlei@0711.io")

    r = k.post("/api/kanzlei/mandanten",
               json={"name": "Salon Frisch", "email": "Frisch@Salon.de",
                     "kontenrahmen": "SKR03", "berater_nr": "12345",
                     "mandant_nr": "77"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "box_ausstehend"
    assert d["hinweis"] == "Belegbox wird eingerichtet"
    assert d["konto_neu"] is True

    # Konto steht, gehört noch zu keiner Box.
    n = babu_web.nutzer_holen("frisch@salon.de")
    assert n and n["rolle"] == "salon" and n["box"] is False

    # Kanzlei-Zeile ist entstanden, mit dem Namen aus den Einstellungen.
    with babu_web._DB_LOCK, babu_web._db() as c:
        kid = kr._eigene_kanzlei("neu-kanzlei@0711.io", c)
        assert kid is not None
        assert mandanten.kanzlei_holen(kid, c=c)["name"] == "Kanzlei Neu"
        m = mandanten.mandant_holen(d["id"], c=c)
    assert m["kanzlei_id"] == kid
    assert m["kontenrahmen"] == "SKR03" and m["berater_nr"] == "12345"

    # Einladung: ein Link ist raus, und er steht nirgends in der Datenbank.
    assert gesendet and gesendet[0][0] == "frisch@salon.de"
    assert d["einladung_link"] in gesendet[0][2]
    schluessel = d["einladung_link"].split("#reset/")[1]
    assert len(schluessel) > 20
    assert schluessel not in _alle_werte(babu_web.PORTAL_DB)


def test_in_der_datenbank_steht_kein_passwort_im_klartext(welt, k, monkeypatch):
    import postfach
    monkeypatch.setattr(postfach, "senden",
                        lambda *a, **kw: (False, "kein Versand eingerichtet"))
    k.post("/api/kanzlei/mandanten",
           json={"name": "Salon Zwei", "email": "zwei@salon.de"})
    werte = _alle_werte(babu_web.PORTAL_DB)
    # Ein scrypt-Hash steht drin, ein lesbares Startpasswort nicht: die
    # erzeugten Passwörter haben die Form „abcd-efgh".
    assert "scrypt$" in werte
    import re
    assert not re.search(r"\b[a-z2-9]{4}-[a-z2-9]{4}\b", werte)


def test_dieselbe_adresse_zweimal_wird_abgelehnt(welt, k, monkeypatch):
    import postfach
    monkeypatch.setattr(postfach, "senden", lambda *a, **kw: (True, "ok"))
    k.post("/api/kanzlei/mandanten", json={"name": "A", "email": "doppelt@salon.de"})
    r = k.post("/api/kanzlei/mandanten", json={"name": "B", "email": "doppelt@salon.de"})
    assert r.status_code == 409


def test_krumme_eingaben_kommen_nicht_durch(welt, k):
    for koerper, wort in (({"name": "", "email": "a@b.de"}, "Namen"),
                          ({"name": "X", "email": "keine-adresse"}, "E-Mail"),
                          ({"name": "X", "email": "a@b.de",
                            "kontenrahmen": "SKR99"}, "Kontenrahmen")):
        r = k.post("/api/kanzlei/mandanten", json=koerper)
        assert r.status_code == 400 and wort in r.json()["fehler"], koerper


def test_das_anlegen_ist_gebremst(welt, k, monkeypatch):
    import postfach
    monkeypatch.setattr(postfach, "senden", lambda *a, **kw: (True, "ok"))
    letzte = None
    for i in range(kr.ANLAGE_MAX + 1):
        letzte = k.post("/api/kanzlei/mandanten",
                        json={"name": f"S{i}", "email": f"s{i}@salon.de"})
    assert letzte.status_code == 429


def test_das_anlegen_hinterlaesst_eine_zeile_im_protokoll(welt, k, monkeypatch):
    import postfach
    monkeypatch.setattr(postfach, "senden", lambda *a, **kw: (True, "ok"))
    k.post("/api/kanzlei/mandanten", json={"name": "Salon Log", "email": "log@salon.de"})
    with babu_web._DB_LOCK, babu_web._db() as c:
        zeilen = c.execute("SELECT akteur_un, aktion, ziel_un, details "
                           "FROM audit_log ORDER BY id DESC").fetchall()
    assert zeilen and zeilen[0][1] == "kanzlei_mandant_anlegen"
    assert zeilen[0][0] == "kanzlei-a@0711.io" and zeilen[0][2] == "log@salon.de"
    # Kein Geheimnis im Protokoll.
    assert "reset/" not in zeilen[0][3]


# ── Box verknüpfen ──────────────────────────────────────────────────────

def test_box_verknuepfen_darf_nur_der_betreiber(welt, k):
    r = k.post(f"/api/kanzlei/mandanten/{welt['ohne']}/box-verknuepfen",
               json={"box_ref": "drei"})
    assert r.status_code == 403
    with babu_web._DB_LOCK, babu_web._db() as c:
        assert mandanten.mandant_holen(welt["ohne"], c=c)["box_ref"] is None


def test_box_verknuepfen_macht_den_mandanten_aktiv(welt, k):
    _als(welt, "betreiber@0711.io")
    r = k.post(f"/api/kanzlei/mandanten/{welt['ohne']}/box-verknuepfen",
               json={"box_ref": "inspektor/ws-ohne/babu"})
    assert r.status_code == 200 and r.json()["status"] == "aktiv"
    with babu_web._DB_LOCK, babu_web._db() as c:
        m = mandanten.mandant_holen(welt["ohne"], c=c)
    assert m["box_ref"] == "inspektor/ws-ohne/babu" and m["status"] == "aktiv"


def test_ein_krummer_verweis_wird_abgelehnt(welt, k):
    _als(welt, "betreiber@0711.io")
    for ref in ("", "../../etc", "-x"):
        r = k.post(f"/api/kanzlei/mandanten/{welt['ohne']}/box-verknuepfen",
                   json={"box_ref": ref})
        assert r.status_code == 400, ref


def test_box_verknuepfen_ist_gebremst(welt, k):
    """Nach `VERKNUEPFEN_MAX` Versuchen im Fenster kommt 429 — derselbe
    Riegel wie beim Anlegen, nur für den Betreiber-Weg."""
    _als(welt, "betreiber@0711.io")
    for _ in range(kr.VERKNUEPFEN_MAX):
        r = k.post(f"/api/kanzlei/mandanten/{welt['ohne']}/box-verknuepfen",
                   json={"box_ref": "inspektor/ws-ohne/babu"})
        assert r.status_code == 200, r.text
    r = k.post(f"/api/kanzlei/mandanten/{welt['ohne']}/box-verknuepfen",
              json={"box_ref": "inspektor/ws-ohne/babu"})
    assert r.status_code == 429
    assert "warten" in r.json()["fehler"]


# ── Status ──────────────────────────────────────────────────────────────

def test_die_inhaberin_darf_pausieren_die_vertretung_nicht(welt, k):
    r = k.post(f"/api/kanzlei/mandanten/{welt['nina']}/status",
               json={"status": "pausiert"})
    assert r.status_code == 200 and r.json()["status_text"] == "pausiert"

    _als(welt, "vertretung-a@0711.io")
    r = k.post(f"/api/kanzlei/mandanten/{welt['nina']}/status",
               json={"status": "aktiv"})
    assert r.status_code == 403


def test_ohne_belegbox_laesst_sich_nichts_anschalten(welt, k):
    r = k.post(f"/api/kanzlei/mandanten/{welt['ohne']}/status",
               json={"status": "aktiv"})
    assert r.status_code == 400
    assert "Belegbox" in r.json()["fehler"]


def test_ein_fremder_mandant_laesst_sich_nicht_umstellen(welt, k):
    r = k.post(f"/api/kanzlei/mandanten/{welt['fremd']}/status",
               json={"status": "beendet"})
    assert r.status_code == 404


# ── Was ansteht: über zwei Boxen, mit Zeitbudget ────────────────────────

def test_die_uebersicht_zaehlt_die_rueckfragen_je_box(welt, k):
    d = k.get("/api/kanzlei/mandanten").json()
    nach_name = {m["name"]: m for m in d["mandanten"]}
    assert nach_name["Salon Nina"]["rueckfragen"] == 1
    assert nach_name["Salon Nina"]["erreichbar"] is True
    # Ohne Box gibt es nichts zu zählen — das ist kein Fehler.
    assert nach_name["Salon Ohne"]["rueckfragen"] is None
    assert nach_name["Salon Ohne"]["belegbox_da"] is False


def test_die_warteschlange_fasst_zwei_boxen_zusammen(welt, k):
    """Der Betreiber sieht beide Kanzleien — und damit zwei echte Boxen mit
    getrennten Indizes. Käme zweimal dieselbe Zahl heraus, läse die
    Aggregation zweimal dieselbe Box."""
    _als(welt, "betreiber@0711.io")
    d = k.get("/api/kanzlei/warteschlange").json()
    nach_name = {e["name"]: e for e in d["eintraege"]}
    assert nach_name["Salon Nina"]["rueckfragen"] == 1
    assert nach_name["Salon Fremd"]["rueckfragen"] == 0
    assert nach_name["Salon Nina"]["monate_ohne_freigabe"] == ["2026-05"]
    assert nach_name["Salon Fremd"]["export_faellig"] == ["2026-05"]
    assert d["zaehler"]["rueckfragen"] == 1
    assert d["zaehler"]["warten_auf_belegbox"] == 1
    assert nach_name["Salon Ohne"]["hinweis"] == "Belegbox wird eingerichtet"
    # Wer am lautesten ruft, steht oben.
    assert d["eintraege"][0]["name"] == "Salon Nina"


def test_ein_beendeter_mandant_steht_nicht_mehr_in_der_uebersicht(welt, k):
    k.post(f"/api/kanzlei/mandanten/{welt['ohne']}/status", json={"status": "beendet"})
    d = k.get("/api/kanzlei/warteschlange").json()
    assert "Salon Ohne" not in {e["name"] for e in d["eintraege"]}


def test_eine_haengende_box_blockiert_die_uebersicht_nicht(welt, k, monkeypatch):
    """Der eine Fall, der die Seite sonst anhielte: eine Box, die nicht
    antwortet. Sie steht als „nicht erreichbar" darin — und die Antwort
    kommt innerhalb des Budgets, nicht wenn die Box mag."""
    echt = kr._box_befund

    def zaeh(bw, un, mandant_id):
        if mandant_id == welt["nina"]:
            time.sleep(5)
        return echt(bw, un, mandant_id)

    monkeypatch.setattr(kr, "_box_befund", zaeh)
    _als(welt, "betreiber@0711.io")
    angefangen = time.monotonic()
    d = k.get("/api/kanzlei/warteschlange").json()
    gebraucht = time.monotonic() - angefangen

    nach_name = {e["name"]: e for e in d["eintraege"]}
    assert nach_name["Salon Nina"]["erreichbar"] is False
    assert nach_name["Salon Nina"]["hinweis"] == "nicht erreichbar"
    assert nach_name["Salon Nina"]["rueckfragen"] is None
    # Die gesunde Box antwortet trotzdem.
    assert nach_name["Salon Fremd"]["erreichbar"] is True
    assert d["zaehler"]["nicht_erreichbar"] == 1
    assert gebraucht < kr.BUDGET_GESAMT + 1.5, f"{gebraucht:.2f}s gebraucht"


def test_eine_kaputte_box_meldet_sich_als_nicht_erreichbar(welt, k, monkeypatch):
    """Nicht nur Langsamkeit — auch ein Fehler beim Lesen darf die Liste
    nicht mit einem 500 beenden."""
    def kaputt(bw, un, mandant_id):
        raise RuntimeError("Store weg")

    monkeypatch.setattr(kr, "_box_befund", kaputt)
    d = k.get("/api/kanzlei/warteschlange").json()
    assert {e["name"] for e in d["eintraege"]} == {"Salon Nina", "Salon Ohne"}
    assert d["zaehler"]["nicht_erreichbar"] == 1


def test_der_detailaufruf_nennt_den_wartezustand(welt, k):
    d = k.get(f"/api/kanzlei/mandanten/{welt['ohne']}").json()
    assert d["hinweis"] == "Belegbox wird eingerichtet"
    assert d["status_text"] == "Belegbox wird eingerichtet"
    d = k.get(f"/api/kanzlei/mandanten/{welt['nina']}").json()
    assert "hinweis" not in d and d["status_text"] == "aktiv"
