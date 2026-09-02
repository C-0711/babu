"""Die Steuerberater-Sicht auf ihre Mandanten — Monatsspalte und Übersicht.

Was hier wirklich auf dem Spiel steht, sind vier Dinge:

1. **Die Zahlen müssen aus der richtigen Box kommen.** Zwei echte
   bare-Stores, zwei getrennte Indizes — käme zweimal dieselbe Zahl heraus,
   läse die Ansicht zweimal dieselbe Box.
2. **Leere Monate müssen dastehen.** Eine Liste, die nur die Monate mit
   Belegen zeigt, verschweigt genau den Fall, der Arbeit macht: den Monat,
   in dem nichts kam.
3. **Die Grenze zwischen zwei Kanzleien.** Wie in `test_kanzlei_routen`:
   404 und nicht 403, sonst ließe sich die Nachbarkanzlei abzählen.
4. **Eine hängende Box darf die Seite nicht anhalten** — sie wird ein 503
   mit einem Satz, und zwar innerhalb des Budgets.

Dazu der Acting-as-Test für die DATEV-Seite: sie hängt an einer
Verwaltungswache, die den `X-Mandant`-Kopf zwar prüfte, aber nie in eine
Belegbox übersetzte. Die Kanzlei bekam mit Kopf ihren EIGENEN Stapel —
leer, unauffällig, falsch.

`_heute` wird festgehalten. Ohne das hinge jede Erwartung an der Uhr des
Rechners und die Datei ginge irgendwann von selbst kaputt.
"""
import json
import subprocess
import sys
import time
from datetime import date
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

#: Der Tag, an dem diese Tests spielen. Mai 2026 hat 31 Tage und beginnt an
#: einem Freitag; bis zum 20. liegen darin 17 Öffnungstage (Mo–Sa).
HEUTE = date(2026, 5, 20)


def _review(monat: str, lieferant: str, brutto: float, offen: list) -> dict:
    review = json.loads(json.dumps(GOLDEN))
    review["felder"].update(lieferant=lieferant, brutto=brutto, offen=offen,
                            ust_satz=19, bewirtungssignal=False,
                            summenprobe_ok=None, steuertabelle=[])
    review["einschaetzung"] = {"konto": "6815", "konto_skr04": "6815",
                               "kontenrahmen": "SKR04", "steuerschluessel": "9"}
    review["vlm"] = {"buchungstext": f"Einkauf {lieferant}"}
    review["datei"] = f"docs/{monat}/x.jpg"
    return review


def _bare(tmp_path: Path, name: str, belege: list[tuple],
          weitere: dict[str, dict] | None = None) -> Path:
    """Eine Wegwerf-Belegbox: Belege, Reviews und was sonst hinein soll.

    `weitere` nimmt fertige JSON-Dateien (Kassenblätter, ein abgelegter
    Export-Stapel) mit ihrem Pfad in der Box — genau so, wie `boxschreiber`
    sie im Betrieb ablegt.
    """
    arbeit = tmp_path / f"arbeit-{name}"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    for k, v in (("user.name", "t"), ("user.email", "t@l")):
        subprocess.run(["git", "-C", str(arbeit), "config", k, v], check=True)
    (arbeit / "review").mkdir(parents=True, exist_ok=True)
    for monat, stamm, lieferant, brutto, offen in belege:
        ordner = arbeit / "docs" / monat
        ordner.mkdir(parents=True, exist_ok=True)
        (ordner / f"{stamm}.jpg").write_bytes(b"\xff\xd8\xff\xe0" + stamm.encode())
        review = _review(monat, lieferant, brutto, offen)
        review["datei"] = f"docs/{monat}/{stamm}.jpg"
        (arbeit / "review" / f"{stamm}.json").write_text(
            json.dumps(review, ensure_ascii=False))
    for pfad, inhalt in (weitere or {}).items():
        ziel = arbeit / pfad
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(json.dumps(inhalt, ensure_ascii=False))
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
    """Zwei Kanzleien, drei Mandanten, zwei echte Boxen — wie in
    `test_kanzlei_routen`, aber mit Kassenbuch und abgelegtem Export.

    Kanzlei Süd (`kanzlei-a@0711.io`) betreut „Salon Nina" (Box `eins`) und
    „Salon Ohne" (noch keine Box). Kanzlei Nord betreut „Salon Fremd"
    (Box `zwei`).

    Box `eins` trägt:
      * 2026-05 — ein offener Beleg (Rückfrage) und ein geprüfter,
        dazu zwei Kassentage.
      * 2026-04 — ein geprüfter Beleg UND der abgelegte Stapel, der ihn zu
        „exportiert" macht.
    """
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    # Die eigene Box der Kanzlei gibt es nicht — genau so sieht das
    # Alt-Verhalten ohne `X-Mandant` aus: nichts drin.
    monkeypatch.setattr(babu_web, "STORE", tmp_path / "leer.git")
    monkeypatch.setattr(bx, "STORE_WURZEL", tmp_path)
    monkeypatch.setattr(bx, "KLON_WURZEL", tmp_path / "klone")
    monkeypatch.setattr(kr, "_heute", lambda: HEUTE)
    bx.registry_leeren()

    _bare(tmp_path, "eins",
          [("2026-05", "20260501-120000-aaa111-alpha", "Friseurbedarf Nord",
            120.00, ["Wofür war das?"]),
           ("2026-05", "20260502-120000-aaa112-beta", "Delila Hair GmbH",
            80.50, []),
           ("2026-04", "20260403-120000-aaa113-gamma", "Bürobedarf Müller",
            59.00, [])],
          {"kassenbuch/2026-05/2026-05-04.json":
               {"datum": "2026-05-04", "einnahmenBar": 100.0,
                "ecZahlungen": 250.0},
           "kassenbuch/2026-05/2026-05-05.json":
               {"datum": "2026-05-05", "einnahmenBar": 40.0,
                "ecZahlungen": 60.0},
           "export/2026-04/stapel.json":
               {"monat": "2026-04", "zeit": "20260510-090000",
                "staemme": ["20260403-120000-aaa113-gamma"],
                "kassentage": [], "von": "kanzlei-a@0711.io"}})
    _bare(tmp_path, "zwei",
          [("2026-05", "20260501-120000-bbb222-delta", "Salon Fremd Bedarf",
            33.00, [])])

    for mail, rolle in (("kanzlei-a@0711.io", "kanzlei"),
                        ("kanzlei-b@0711.io", "kanzlei"),
                        ("betreiber@0711.io", "admin"),
                        ("nina@0711.io", "salon"),
                        ("ohne@0711.io", "salon"),
                        ("fremd@0711.io", "salon")):
        babu_web.nutzer_anlegen(mail, mail.split("@")[0], "", rolle)

    with babu_web._DB_LOCK, babu_web._db() as c:
        a = mandanten.kanzlei_anlegen("Kanzlei Süd", "kanzlei-a@0711.io", c=c)
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


@pytest.fixture()
def k(welt):
    return TestClient(babu_web.app, base_url="https://testserver")


def _als(welt, un):
    welt["wer"]["un"] = un


def _monate(k, mandant_id, **frage):
    r = k.get(f"/api/kanzlei/mandanten/{mandant_id}/monate", params=frage)
    assert r.status_code == 200, r.text
    return {m["monat"]: m for m in r.json()["monate"]}


# ── Die Monatsspalte eines Mandanten ────────────────────────────────────

def test_die_monate_zaehlen_die_belege_je_stand(welt, k):
    monate = _monate(k, welt["nina"])
    mai = monate["2026-05"]
    assert mai["belege"] == {"gesamt": 2, "offen": 1, "geprueft": 1,
                             "exportiert": 0}
    assert mai["brutto_summe"] == 200.50
    # Der April ist heraus — der abgelegte Stapel macht den Beleg
    # „exportiert", nicht ein Feld, das jemand von Hand setzt.
    april = monate["2026-04"]
    assert april["belege"]["exportiert"] == 1
    assert april["belege"]["offen"] == 0


def test_die_rueckfragen_stehen_im_klartext_darunter(welt, k):
    mai = _monate(k, welt["nina"])["2026-05"]
    assert len(mai["rueckfragen"]) == 1
    frage = mai["rueckfragen"][0]
    assert frage["frage"] == "Wofür war das?"
    assert frage["lieferant"] == "Friseurbedarf Nord"
    assert frage["brutto"] == 120.00
    assert frage["stamm"] == "20260501-120000-aaa111-alpha"
    # Ein Monat ohne offene Belege nennt keine.
    assert _monate(k, welt["nina"])["2026-04"]["rueckfragen"] == []


def test_leere_monate_stehen_mit_drin(welt, k):
    """Der Monat, in dem nichts kam, ist der, der Arbeit macht."""
    monate = _monate(k, welt["nina"], anzahl=6)
    assert list(monate) == ["2026-05", "2026-04", "2026-03", "2026-02",
                            "2026-01", "2025-12"]
    leer = monate["2026-03"]
    assert leer["belege"]["gesamt"] == 0
    assert leer["abschluss"]["stand"] == "leer"
    assert leer["umsatz"] is None
    assert leer["kassenbuch"]["letzter_tag"] is None


def test_der_stand_eines_monats_in_einem_wort(welt, k):
    monate = _monate(k, welt["nina"])
    assert monate["2026-05"]["abschluss"]["stand"] == "offen"
    assert monate["2026-04"]["abschluss"]["stand"] == "exportiert"
    assert monate["2026-04"]["abschluss"]["export_am"], \
        "der abgelegte Stapel muss einen Zeitpunkt tragen"
    assert monate["2026-03"]["abschluss"]["stand"] == "leer"
    # Nichts mehr offen, aber nichts heraus: pruefbereit.
    _als(welt, "betreiber@0711.io")
    assert _monate(k, welt["fremd"])["2026-05"]["abschluss"]["stand"] \
        == "pruefbereit"


def test_das_kassenbuch_zaehlt_tage_und_summiert_die_kasse(welt, k):
    mai = _monate(k, welt["nina"])["2026-05"]
    assert mai["kassenbuch"]["tage_eingetragen"] == 2
    # Mo–Sa bis zum 20. Mai 2026 = 17 Tage. Im laufenden Monat wird nur bis
    # heute gezählt — sonst läse sich jeder normale Stand wie ein Rückstand.
    assert mai["kassenbuch"]["tage_erwartet"] == 17
    assert mai["kassenbuch"]["letzter_tag"] == "2026-05-05"
    assert mai["umsatz"] == 450.0


def test_die_oeffnungstage_des_mandanten_entscheiden(welt, k):
    """Und zwar die des MANDANTEN, nicht die der Kanzlei."""
    babu_web.db_einstellung_setzen("nina@0711.io", "oeffnungstage", "di,mi,do")
    mai = _monate(k, welt["nina"])["2026-05"]
    # Di/Mi/Do bis zum 20. Mai 2026: 5., 6., 7., 12., 13., 14., 19., 20.
    assert mai["kassenbuch"]["tage_erwartet"] == 8


def test_ein_kuenftiger_monat_erwartet_keine_kassentage(welt, k, monkeypatch):
    monkeypatch.setattr(kr, "_heute", lambda: date(2026, 3, 15))
    monate = _monate(k, welt["nina"], anzahl=1)
    assert list(monate) == ["2026-03"]
    assert monate["2026-03"]["kassenbuch"]["tage_erwartet"] == 12


# ── Wer sie sehen darf ──────────────────────────────────────────────────

def test_die_nachbarkanzlei_bekommt_einen_404(welt, k):
    _als(welt, "kanzlei-b@0711.io")
    r = k.get(f"/api/kanzlei/mandanten/{welt['nina']}/monate")
    assert r.status_code == 404
    assert "gibt es hier nicht" in r.json()["fehler"]


def test_ein_salon_kommt_gar_nicht_erst_hinein(welt, k):
    _als(welt, "nina@0711.io")
    assert k.get(f"/api/kanzlei/mandanten/{welt['nina']}/monate"
                 ).status_code == 403
    assert k.get("/api/kanzlei/uebersicht").status_code == 403


def test_ohne_belegbox_ist_es_ein_409_und_kein_fehler(welt, k):
    """`box_ausstehend` ist der Wartezustand, kein Rechteproblem."""
    r = k.get(f"/api/kanzlei/mandanten/{welt['ohne']}/monate")
    assert r.status_code == 409
    assert r.json()["fehler"] == "Belegbox wird eingerichtet"


def test_eine_haengende_box_wird_ein_503_im_budget(welt, k, monkeypatch):
    monkeypatch.setattr(kr, "BUDGET_DETAIL", 0.5)

    def zaeh(*args, **kwargs):
        time.sleep(5)

    monkeypatch.setattr(kr, "_monats_befund", zaeh)
    angefangen = time.monotonic()
    r = k.get(f"/api/kanzlei/mandanten/{welt['nina']}/monate")
    gebraucht = time.monotonic() - angefangen
    assert r.status_code == 503
    assert r.json()["fehler"] == "Belegbox gerade nicht erreichbar"
    assert gebraucht < 2.0, f"{gebraucht:.2f}s gebraucht"


# ── Die Matrix über alle Mandanten ──────────────────────────────────────

def test_die_uebersicht_stellt_mandanten_und_monate_gegenueber(welt, k):
    d = k.get("/api/kanzlei/uebersicht", params={"monate": 3}).json()
    assert d["monate"] == ["2026-05", "2026-04", "2026-03"]
    nach_name = {z["name"]: z for z in d["mandanten"]}
    nina = nach_name["Salon Nina"]
    staende = {z["monat"]: z for z in nina["zellen"]}
    assert staende["2026-05"] == {"monat": "2026-05", "stand": "offen",
                                  "offen": 1, "gesamt": 2}
    assert staende["2026-04"]["stand"] == "exportiert"
    assert staende["2026-03"]["stand"] == "leer"
    assert nina["rueckfragen"] == 1
    assert nina["offen_gesamt"] == 1
    assert nina["letzte_aktivitaet"]


def test_die_uebersicht_sortiert_nach_offenen_punkten(welt, k):
    """Wer am meisten offen hat, steht oben."""
    _als(welt, "betreiber@0711.io")
    d = k.get("/api/kanzlei/uebersicht").json()
    assert [z["name"] for z in d["mandanten"]][0] == "Salon Nina"
    assert d["zaehler"]["offen"] == 1
    assert d["zaehler"]["rueckfragen"] == 1
    assert d["zaehler"]["warten_auf_belegbox"] == 1
    # Zwei echte Boxen, zwei getrennte Indizes.
    nach_name = {z["name"]: z for z in d["mandanten"]}
    assert nach_name["Salon Fremd"]["offen_gesamt"] == 0
    assert {z["monat"]: z["stand"] for z in nach_name["Salon Fremd"]["zellen"]
            }["2026-05"] == "pruefbereit"


def test_eine_kanzlei_sieht_in_der_uebersicht_nur_ihre_eigenen(welt, k):
    d = k.get("/api/kanzlei/uebersicht").json()
    assert {z["name"] for z in d["mandanten"]} == {"Salon Nina", "Salon Ohne"}


def test_ein_mandant_ohne_box_wartet_und_stuerzt_nicht(welt, k):
    d = k.get("/api/kanzlei/uebersicht").json()
    ohne = [z for z in d["mandanten"] if z["name"] == "Salon Ohne"][0]
    assert ohne["belegbox_da"] is False
    assert ohne["hinweis"] == "Belegbox wird eingerichtet"
    assert ohne["rueckfragen"] is None
    assert all(z["stand"] == "leer" for z in ohne["zellen"])


def test_eine_haengende_box_wird_zum_fragezeichen(welt, k, monkeypatch):
    """Ein Fragezeichen und keine Null: eine Null behauptet, es sei nichts
    offen — und das ist die gefährlichere Lüge."""
    def zaeh(bw, un, mandant_id, monate):
        time.sleep(5)

    monkeypatch.setattr(kr, "_uebersicht_befund", zaeh)
    angefangen = time.monotonic()
    d = k.get("/api/kanzlei/uebersicht").json()
    gebraucht = time.monotonic() - angefangen
    nina = [z for z in d["mandanten"] if z["name"] == "Salon Nina"][0]
    assert nina["erreichbar"] is False
    assert nina["hinweis"] == "Belegbox gerade nicht erreichbar"
    assert all(z["stand"] == "?" and z["offen"] is None for z in nina["zellen"])
    assert d["zaehler"]["nicht_erreichbar"] == 1
    assert gebraucht < kr.BUDGET_GESAMT + 1.5, f"{gebraucht:.2f}s gebraucht"


def test_ein_beendeter_mandant_faellt_aus_der_uebersicht(welt, k):
    k.post(f"/api/kanzlei/mandanten/{welt['ohne']}/status",
           json={"status": "beendet"})
    d = k.get("/api/kanzlei/uebersicht").json()
    assert "Salon Ohne" not in {z["name"] for z in d["mandanten"]}


# ── Acting-as auf der DATEV-Seite ───────────────────────────────────────

def test_die_datev_seite_liest_mit_kopf_die_box_des_mandanten(welt, k):
    """Der leise Fehler: `_verwalter_wache` prüfte den `X-Mandant`-Kopf,
    übersetzte ihn aber nie in eine Belegbox. Die Kanzlei bekam mit Kopf
    ihren eigenen — leeren — Stapel, und man sah es der Antwort nicht an."""
    kopf = {"X-Mandant": str(welt["nina"])}
    mit = k.get("/api/datev/uebersicht", headers=kopf).json()
    assert set(mit["monate"]) == {"2026-05", "2026-04"}
    assert mit["je_monat"]["2026-05"]["belege"] == 2
    assert mit["je_monat"]["2026-05"]["kassentage"] == 2

    # Ohne Kopf das Alt-Verhalten: die eigene Box der Kanzlei, und die ist leer.
    ohne = k.get("/api/datev/uebersicht").json()
    assert ohne["monate"] == []


def test_der_stapel_traegt_die_buchungen_des_mandanten(welt, k):
    kopf = {"X-Mandant": str(welt["nina"])}
    r = k.get("/api/datev/stapel.csv", params={"von": "2026-05"}, headers=kopf)
    assert r.status_code == 200, r.text
    text = r.content.decode("cp1252")
    assert "Delila Hair GmbH" in text

    ohne = k.get("/api/datev/stapel.csv", params={"von": "2026-05"})
    assert ohne.status_code == 200
    assert "Delila Hair GmbH" not in ohne.content.decode("cp1252")


def test_der_stapel_schreibt_den_mandanten_ins_audit(welt, k):
    """Hier verlassen Steuerdaten das Haus. Ohne die Nummer sagte die
    Audit-Zeile nicht, WESSEN Stapel jemand mitgenommen hat."""
    k.get("/api/datev/stapel.csv", params={"von": "2026-05"},
          headers={"X-Mandant": str(welt["nina"])})
    with babu_web._DB_LOCK, babu_web._db() as c:
        zeilen = c.execute(
            "SELECT akteur_un, mandant_id FROM audit_log WHERE aktion=?",
            ("datev_stapel",)).fetchall()
    assert zeilen, "kein Audit-Eintrag für den Stapel-Download"
    assert zeilen[-1][0] == "kanzlei-a@0711.io"
    assert zeilen[-1][1] == str(welt["nina"])


def test_eine_fremde_kanzlei_kommt_auch_ueber_datev_nicht_hinein(welt, k):
    """Die Wache hebt den Kopf in die Box — sie darf ihn dabei nicht
    weicher prüfen als `_box_wache` es tut."""
    _als(welt, "kanzlei-b@0711.io")
    r = k.get("/api/datev/uebersicht", headers={"X-Mandant": str(welt["nina"])})
    assert r.status_code == 403


def test_die_datev_seite_selbst_haengt_an_derselben_wache(welt, k):
    """Eine Seite, die eine andere Frage stellt als ihre Daten, ist keine
    Wache."""
    assert k.get("/datev").status_code == 200
    _als(welt, "nina@0711.io")
    assert k.get("/datev").status_code == 403
