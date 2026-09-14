"""Messen statt raten: Schlösser, Gemma-Zähler, Zugriffszeile, Login-Bremse.

Vier Dinge aus Woche 5 des Go-Live-Plans, die vor einer Entscheidung über
`_DB_LOCK` und die Gemma-Plätze stehen:

1. `_MessSchloss` zählt Warte- und Haltezeit, bleibt aber ein Schloss.
2. `/api/kpi` gibt die Zahlen aus.
3. `_metrik_mw` schreibt eine Zugriffszeile für Fehler und langsame Antworten —
   mit Konto und Betrieb.
4. Die Login-Bremse gilt je Konto (streng) und je IP (großzügig).
"""
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASSWORT = "ein-langes-passwort-hier"


def test_messschloss_ist_ein_schloss_und_misst():
    import babu_web as bw
    s = bw._MessSchloss("probe", threading.Lock())  # noqa: SLF001
    with s:
        assert s.locked()
        time.sleep(0.05)
    assert not s.locked()
    assert s.anzahl == 1 and s.halte_max_s >= 0.04

    # Ein zweiter Faden wartet — die Wartezeit landet im Maximum.
    s.acquire()
    gewartet = []

    def warter():
        t0 = time.perf_counter()
        with s:
            gewartet.append(time.perf_counter() - t0)
    t = threading.Thread(target=warter)
    t.start()
    time.sleep(0.15)
    s.release()
    t.join(2)
    assert gewartet and gewartet[0] >= 0.1
    assert s.warte_max_s >= 0.1
    assert s.acquire(timeout=0.01) and (s.release() is None)
    w = s.werte()
    assert set(w) == {"anzahl", "warte_mittel_ms", "warte_max_ms", "halte_max_ms"}


def test_semaphore_huelle_mit_mehreren_plaetzen():
    import babu_web as bw
    s = bw._MessSchloss("llm", threading.Semaphore(2))  # noqa: SLF001
    assert s.acquire(timeout=0.01) and s.acquire(timeout=0.01)
    assert not s.acquire(timeout=0.01)   # dritter Platz gibt es nicht
    s.release(); s.release()
    assert s.anzahl == 2


def test_die_echten_schloesser_tragen_die_huelle():
    import babu_web as bw
    assert isinstance(bw._DB_LOCK, bw._MessSchloss)  # noqa: SLF001
    assert isinstance(bw._LLM_SEMAPHORE, bw._MessSchloss)  # noqa: SLF001
    assert bw.LLM_PLAETZE == 1   # Standard bleibt EIN Platz


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    import babu_web
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    assert babu_web.nutzer_anlegen("nina@salon.de", "Nina", "Salon", "salon",
                                   passwort=PASSWORT, box=True) is not None
    return TestClient(babu_web.app, base_url="https://testserver"), babu_web


def test_kpi_zeigt_schloesser_und_zaehler(welt, monkeypatch):
    client, bw = welt
    monkeypatch.setattr(bw, "_box_wache", lambda request: ("nina@salon.de", None))
    monkeypatch.setattr(bw, "kennzahlen_monat", lambda monat: {"monat": monat})
    d = client.get("/api/kpi/2026-09").json()["betrieb"]
    assert set(d["schloesser"]) == {"db", "llm"}
    assert d["schloesser"]["db"]["anzahl"] > 0
    for k in ("llm_plaetze", "gemma_fehler", "gemma_timeout", "login_429", "arbeit_offen"):
        assert k in d


def test_zugriffszeile_fuer_fehler_mit_konto(welt, capsys):
    client, bw = welt
    # Ohne Anmeldung: 401 — Zeile mit Status, Pfad und Konto „-".
    client.get("/api/belege")
    aus = capsys.readouterr().out
    assert "[http] 401 GET /api/belege" in aus and "un=-" in aus
    # Angemeldet, aber ein Fehler: die Zeile trägt das Konto.
    bw._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    assert client.post("/api/login", json={"email": "nina@salon.de", "passwort": PASSWORT}).status_code == 200
    capsys.readouterr()
    client.delete("/api/geraete/gibt-es-nicht")   # 404 hinter der Wache
    aus = capsys.readouterr().out
    assert "[http] 404" in aus and "un=nina@salon.de" in aus
    # Eine glatte, schnelle Antwort schreibt keine Zeile.
    capsys.readouterr()
    assert client.get("/api/ich").status_code == 200
    assert "[http]" not in capsys.readouterr().out


def test_login_bremse_je_konto_und_je_ip(welt):
    client, bw = welt
    falsch = {"email": "nina@salon.de", "passwort": "falsch-falsch"}
    for _ in range(bw.LOGIN_JE_KONTO):
        assert client.post("/api/login", json=falsch).status_code == 401
    # Das Konto ist zu — auch mit dem richtigen Passwort, bis das Fenster verstreicht.
    assert client.post("/api/login", json=falsch).status_code == 429
    assert client.post("/api/login", json={"email": "nina@salon.de", "passwort": PASSWORT}).status_code == 429
    assert bw._METRIK["login_429"] >= 1  # noqa: SLF001
    # Ein ANDERES Konto von derselben Adresse (der Salon hinter der NAT) darf weiter.
    assert client.post("/api/login", json={"email": "bea@salon.de", "passwort": "x"}).status_code == 401
    # Dieselbe Bremse an der App-Anmeldung.
    bw._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    for _ in range(bw.LOGIN_JE_KONTO):
        assert client.post("/api/app-anmelden", json={**falsch, "geraet": "x"}).status_code == 401
    assert client.post("/api/app-anmelden", json={**falsch, "geraet": "x"}).status_code == 429
    # Erfolg räumt das Kontingent des Kontos.
    bw._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    for _ in range(bw.LOGIN_JE_KONTO - 1):
        client.post("/api/login", json=falsch)
    assert client.post("/api/login", json={"email": "nina@salon.de", "passwort": PASSWORT}).status_code == 200
    assert client.post("/api/login", json=falsch).status_code == 401
