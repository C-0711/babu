"""Das Konto löschen — und zwar ganz (14.10.2026).

Apple 5.1.1(v): Wer in der App ein Konto anlegen kann, muss es dort auch
löschen können. Dieser Test hält drei Dinge:

1. **Danach trägt nichts mehr.** Der Geräteschlüssel gilt nicht, der Betrieb
   ist weg, der Zugang ist weg — geprüft über die Routen, nicht nur über
   Zeilen.
2. **Es bleibt nichts Persönliches liegen.** Jede Tabelle, die `un` oder
   `mandant_id` trägt, wird nach Zeilen dieses Zugangs abgesucht. Das ist
   der Test, der bei einer NEUEN Tabelle anschlägt — und dann soll jemand
   entscheiden, ob ihre Zeilen mitgehen, statt es zu übersehen.
3. **Wer nicht darf, darf nicht.** Eine Mitarbeiterin, ein fremder Betrieb,
   ein Portal-Betrieb mit Kanzlei: jeder mit seinem eigenen Weg.

Die Belegbox wird in der Suite nicht angelegt (`_box_nachziehen` ist in der
Fixture ersetzt), also läuft das Leeren ins Leere — genau dieser Fall wird
eigens geprüft: der Zugang muss trotzdem weg sein.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import babu_web  # noqa: E402
import kern_konto  # noqa: E402
import mandanten  # noqa: E402

from test_geraet_und_apple import (  # noqa: E402,F401
    _anlegen, _client, _mit_schluessel, welt)


def _loeschen(client, **kw):
    return client.post("/api/konto/loeschen", json={"bestaetigt": True, **kw})


def _tabellen_mit(spalte: str) -> list[str]:
    """Jede Tabelle der Datenbank, die diese Spalte trägt."""
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        namen = [z[0] for z in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        passend = []
        for n in namen:
            spalten = [z[1] for z in c.execute(f"PRAGMA table_info({n})")]
            if spalte in spalten:
                passend.append(n)
    return passend


# ---------------------------------------------------------------------------
# Der Weg selbst
# ---------------------------------------------------------------------------

def test_nach_dem_loeschen_traegt_der_schluessel_nicht_mehr(welt):
    konto = _anlegen(_client())
    client = _mit_schluessel(konto)
    assert client.get("/api/ich").status_code == 200
    r = _loeschen(client)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert client.get("/api/ich").status_code in (401, 403)


def test_der_betrieb_und_der_zugang_sind_weg(welt):
    konto = _anlegen(_client())
    _loeschen(_mit_schluessel(konto))
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert c.execute("SELECT 1 FROM mandant WHERE id=?",
                         (konto["mandant"],)).fetchone() is None
        assert c.execute("SELECT 1 FROM nutzer WHERE email=?",
                         (konto["un"],)).fetchone() is None
        assert c.execute("SELECT 1 FROM app_schluessel WHERE un=?",
                         (konto["un"],)).fetchone() is None


def test_ohne_bestaetigung_wird_nichts_geloescht(welt):
    """Ein POST ohne Rumpf darf kein Konto kosten."""
    konto = _anlegen(_client())
    client = _mit_schluessel(konto)
    assert client.post("/api/konto/loeschen", json={}).status_code == 400
    assert client.post("/api/konto/loeschen",
                       json={"bestaetigt": "ja"}).status_code == 400
    assert client.get("/api/ich").status_code == 200


def test_ohne_zugang_geht_es_nicht(welt):
    _anlegen(_client())
    assert _client().post("/api/konto/loeschen",
                          json={"bestaetigt": True}).status_code == 401


def test_der_eine_betrieb_loescht_den_anderen_nicht(welt):
    a, b = _anlegen(_client()), _anlegen(_client())
    _loeschen(_mit_schluessel(a))
    assert _mit_schluessel(b).get("/api/ich").status_code == 200
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert c.execute("SELECT 1 FROM mandant WHERE id=?",
                         (b["mandant"],)).fetchone() is not None


# ---------------------------------------------------------------------------
# Was liegen bleibt — und was nicht
# ---------------------------------------------------------------------------

def test_in_keiner_tabelle_bleibt_eine_zeile_dieses_zugangs(welt):
    """Der Test, der bei einer neuen Tabelle anschlägt.

    Gefüllt wird vorher, was sich über die Routen füllen lässt; für die
    übrigen Tabellen zählt, dass sie durchsucht WERDEN. Bleibt irgendwo eine
    Zeile, nennt die Meldung die Tabelle.
    """
    konto = _anlegen(_client())
    un, mandant_id = konto["un"], konto["mandant"]
    client = _mit_schluessel(konto)
    client.post("/api/konto/email", json={"email": "nina@salon.de"})
    # Die Tabellennamen VOR dem Schloss holen: `_DB_LOCK` ist nicht
    # wiedereintrittsfähig (HANDOVER „Bekannte Fallen"), und ein zweiter
    # Zugriff daraus heraus bleibt für immer stehen.
    mit_un = _tabellen_mit("un")
    mit_mandant = [t for t in _tabellen_mit("mandant_id") if t != "geloescht"]
    # Eine Zeile in jede Tabelle legen, die `un` trägt — unabhängig davon,
    # ob es dafür heute eine Route gibt.
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        for tabelle in mit_un:
            spalten = [z[1] for z in c.execute(f"PRAGMA table_info({tabelle})")]
            werte = [un if s == "un" else 1 for s in spalten]
            platz = ",".join("?" * len(spalten))
            try:
                c.execute(f"INSERT INTO {tabelle} ({','.join(spalten)}) "
                          f"VALUES ({platz})", werte)
            except Exception:  # noqa: BLE001,S110
                pass            # Pflichtfelder/Fremdschlüssel — dann eben nicht
    _loeschen(client)
    uebrig = {}
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        for tabelle in mit_un:
            n = c.execute(f"SELECT COUNT(*) FROM {tabelle} WHERE un=?",
                          (un,)).fetchone()[0]
            if n:
                uebrig[tabelle] = n
        for tabelle in mit_mandant:
            n = c.execute(f"SELECT COUNT(*) FROM {tabelle} WHERE mandant_id=?",
                          (mandant_id,)).fetchone()[0]
            if n:
                uebrig[tabelle] = n
    assert not uebrig, (
        f"Zeilen dieses Zugangs sind liegen geblieben: {uebrig}. Gehört die "
        "Tabelle in kern_konto.NACH_UN / NACH_MANDANT?")


def test_die_liste_kennt_jede_tabelle_der_datenbank(welt):
    """Gegenprobe zum Test davor, ohne Daten: steht jede Tabelle mit `un`
    oder `mandant_id` in einer der beiden Listen?

    Ohne diesen Test fiele eine neue Tabelle erst auf, wenn jemand sie in
    derselben Suite auch füllt — und Pflichtfelder können das verhindern.
    """
    bekannt = set(kern_konto.NACH_UN) | set(kern_konto.NACH_MANDANT)
    # Diese wenigen tragen die Spalte, gehören aber nicht dem Zugang.
    ausnahmen = {
        "nutzer",        # per `email` gelöscht, nicht per `un`
        "mandant",       # per `id` gelöscht
        "audit_log",     # eigene Bedingung (akteur_un ODER ziel_un)
        "geloescht",     # das Protokoll, das bleiben soll
    }
    fehlt = (set(_tabellen_mit("un")) | set(_tabellen_mit("mandant_id"))) \
        - bekannt - ausnahmen
    assert not fehlt, (
        f"Diese Tabellen kennt das Löschen nicht: {sorted(fehlt)}. Entscheide, "
        "ob ihre Zeilen mitgehen, und trage sie in kern_konto ein.")


def test_das_protokoll_nennt_niemanden(welt):
    konto = _anlegen(_client())
    _loeschen(_mit_schluessel(konto))
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        zeile = c.execute("SELECT mandant_id, box_ref, dateien, box_leer, zeit "
                          "FROM geloescht WHERE mandant_id=?",
                          (konto["mandant"],)).fetchone()
    assert zeile is not None, "ohne Protokoll weiß niemand, was noch zu tun ist"
    assert zeile[0] == konto["mandant"]
    text = " ".join(str(w) for w in zeile)
    assert konto["un"] not in text
    assert "nina@salon.de" not in text


def test_die_chatnachrichten_gehen_mit(welt):
    """Sie hängen am Faden, nicht am Zugang — der Fall, den man vergisst."""
    konto = _anlegen(_client())
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("INSERT INTO gespraech (un, titel, begonnen, zuletzt, betrieb) "
                  "VALUES (?,?,?,?,?)",
                  (konto["un"], "Frage", "2026-10-14", "2026-10-14", konto["un"]))
        faden = c.execute("SELECT id FROM gespraech WHERE un=?",
                          (konto["un"],)).fetchone()[0]
        c.execute("INSERT INTO nachricht (gespraech, rolle, text, zeit) "
                  "VALUES (?,?,?,?)", (faden, "user", "Wie buche ich das?",
                                       "2026-10-14"))
    _loeschen(_mit_schluessel(konto))
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert c.execute("SELECT COUNT(*) FROM nachricht WHERE gespraech=?",
                         (faden,)).fetchone()[0] == 0


def test_das_gedaechtnis_geht_mit(welt):
    konto = _anlegen(_client())
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("INSERT INTO merksatz (betrieb, text, gelernt, quelle, "
                  "gespraech) VALUES (?,?,?,?,?)",
                  (konto["un"], "Sie zahlt bar", "2026-10-14", "chat", None))
    _loeschen(_mit_schluessel(konto))
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert c.execute("SELECT COUNT(*) FROM merksatz WHERE betrieb=?",
                         (konto["un"],)).fetchone()[0] == 0


def test_ohne_box_ist_der_zugang_trotzdem_weg(welt):
    """Die Box lässt sich in der Suite nicht leeren (es gibt sie nicht). Der
    Zugang muss trotzdem weg sein — sonst gilt ein Konto weiter, dessen
    Löschung bestätigt wurde."""
    konto = _anlegen(_client())
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET box_ref=? WHERE id=?",
                  ("babu/gibt-es-nicht/belege", konto["mandant"]))
    client = _mit_schluessel(konto)
    r = _loeschen(client)
    assert r.status_code == 200, r.text
    assert r.json()["box_leer"] is False
    assert "Belege" in r.json()["hinweis"]
    assert client.get("/api/ich").status_code in (401, 403)
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        zeile = c.execute("SELECT box_ref, box_leer FROM geloescht WHERE "
                          "mandant_id=?", (konto["mandant"],)).fetchone()
    assert zeile == ("babu/gibt-es-nicht/belege", 0), zeile


# ---------------------------------------------------------------------------
# Wer nicht darf
# ---------------------------------------------------------------------------

def test_ein_portal_betrieb_wird_abgewiesen(welt):
    """Er hängt an einer Kanzlei und ihren Stapeln. Ein Knopf in der App
    hätte Folgen für zwei Parteien."""
    konto = _anlegen(_client())
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET herkunft=NULL WHERE id=?",
                  (konto["mandant"],))
    client = _mit_schluessel(konto)
    r = _loeschen(client)
    assert r.status_code == 409, r.text
    assert "Steuerbüro" in r.json()["fehler"]
    assert client.get("/api/ich").status_code == 200


def test_eine_mitarbeiterin_kommt_an_die_route_nicht_heran(welt, monkeypatch):
    """Zwei Schlösser hintereinander, und das vordere greift zuerst.

    `_api_wache` lässt eine Mitarbeiterin nur an die Pfade der Positivliste
    (`mitarbeitrecht`, babu Expenses D1) — `/api/konto/loeschen` steht dort
    nicht, also kommt 403 mit `grund: freigabe`, bevor die Route überhaupt
    läuft. Das ist die Antwort, die gilt; gemessen, nicht angenommen.
    """
    konto = _anlegen(_client())
    monkeypatch.setattr(babu_web, "rolle", lambda un: "mitarbeit")
    r = _loeschen(_mit_schluessel(konto))
    assert r.status_code == 403, r.text
    assert r.json()["grund"] == "freigabe"
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert c.execute("SELECT 1 FROM mandant WHERE id=?",
                         (konto["mandant"],)).fetchone() is not None


def test_auch_das_hintere_schloss_haelt_die_mitarbeiterin(welt, monkeypatch):
    """Das zweite Schloss, direkt gefragt.

    Käme `/api/konto/loeschen` je in die Positivliste, entschiede allein
    `darf_loeschen`. Deshalb steht die Prüfung dort auch — und deshalb wird
    sie hier einzeln gemessen, nicht nur über die Route, die sie heute gar
    nicht erreicht.
    """
    konto = _anlegen(_client())
    monkeypatch.setattr(babu_web, "rolle", lambda un: "mitarbeit")
    mandant_id, grund = kern_konto.darf_loeschen(konto["un"])
    assert mandant_id is None
    assert "Team" in (grund or "")


def test_ein_betrieb_eines_anderen_wird_nicht_geloescht(welt):
    """Gemessen, nicht angenommen: wo greift die Eigentumsfrage?

    Nicht in `darf_loeschen`, sondern eine Stufe früher. Der Betrieb wird
    über `testmonat.direkt_mandant_von` gesucht, und das SELECT fragt nach
    `besitzer_un` — gehört er einem anderen, gibt es für diesen Zugang gar
    keinen Betrieb. Die Antwort heißt deshalb „kein Betrieb" und nicht
    „gehört einem anderen". Der Besitzer-Vergleich in `darf_loeschen` bleibt
    als zweites Schloss stehen (siehe Test darunter), aber die Route kommt
    hier nie an ihm an.
    """
    konto = _anlegen(_client())
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET besitzer_un=? WHERE id=?",
                  ("app-jemand-anderes", konto["mandant"]))
    r = _loeschen(_mit_schluessel(konto))
    assert r.status_code == 409, r.text
    assert "keinen Betrieb" in r.json()["fehler"]
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert c.execute("SELECT 1 FROM mandant WHERE id=?",
                         (konto["mandant"],)).fetchone() is not None


def test_der_besitzer_vergleich_haelt_auch_fuer_sich(welt, monkeypatch):
    """Das zweite Schloss am Eigentum, direkt gefragt.

    Fände `direkt_mandant_von` eines Tages einen Betrieb, der dem Zugang
    nicht gehört (eine andere Kanzlei, eine andere Abfrage), entschiede
    allein dieser Vergleich. Also wird er einzeln gemessen.
    """
    konto = _anlegen(_client())
    fremd = konto["mandant"]
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET besitzer_un=? WHERE id=?",
                  ("app-jemand-anderes", fremd))
    monkeypatch.setattr("testmonat.direkt_mandant_von",
                        lambda un, c: (fremd, None))
    mandant_id, grund = kern_konto.darf_loeschen(konto["un"])
    assert mandant_id is None
    assert "gehört" in (grund or "")


def test_zweimal_loeschen_ist_kein_absturz(welt):
    konto = _anlegen(_client())
    client = _mit_schluessel(konto)
    assert _loeschen(client).status_code == 200
    assert _loeschen(client).status_code in (401, 403)


# ---------------------------------------------------------------------------
# Dieselben Anweisungen gegen ECHTES Postgres
# ---------------------------------------------------------------------------
#
# Die Tests oben laufen alle gegen SQLite: die Fixture `welt` setzt
# `babu_web.PORTAL_DB` auf eine Datei, egal ob eine Postgres-Instanz da ist.
# SQLite hat keine festen Spaltentypen — dort ist
# `WHERE mandant_id = 14` auch auf einer TEXT-Spalte in Ordnung.
#
# Live ist es das nicht. Am 14.10.2026 gab die Route auf mybabu.io einen 500:
#
#     psycopg.errors.UndefinedFunction: operator does not exist: text = smallint
#     DELETE FROM import_status WHERE mandant_id=$1
#
# `import_status.mandant_id` und `audit_log.mandant_id` stehen als TEXT
# (absichtlich, ohne Fremdschlüssel), `abo_rechnung` und `post_adresse` als
# INTEGER. Kein SQLite-Test der Welt sieht das.
#
# Dieser Test fährt deshalb genau die Anweisungen, die `loeschen()` ausführt,
# gegen das echte Schema aus `migrations/` — ohne die App, weil es hier nur um
# die Typen geht.

import pytest  # noqa: E402

import db as dbmodul  # noqa: E402


@pytest.fixture()
def pg_verbindung(pg_url, pg_schema, monkeypatch):
    """Eine echte Postgres-Verbindung auf dem Schema aus `migrations/`.

    `db.DIALEKT` wird mitgesetzt: `db.upsert()` liest ohne Argument diese
    Modulvariable, und sie steht beim Start aus `BABU_DB_URL`. Im
    Container ist sie „postgres", in der Suite „sqlite" — ohne das
    Mitsetzen prüfte dieser Test SQLite-Syntax gegen Postgres und meldete
    einen Fehler, den es live nicht gibt.
    """
    import psycopg  # noqa: PLC0415
    monkeypatch.setattr(dbmodul, "DIALEKT", "postgres")
    conn = psycopg.connect(pg_url)
    conn.execute(f'SET search_path TO "{pg_schema}"')
    dbmodul.schema_anwenden(conn, "postgres")
    try:
        yield dbmodul.Verbindung(conn, "postgres")
    finally:
        conn.close()


@pytest.mark.pg
def test_pg_die_spalten_haben_wirklich_verschiedene_typen(pg_verbindung, pg_schema):
    """Die Voraussetzung des Tests darunter — gemessen, nicht behauptet."""
    typen = dict(pg_verbindung.execute(
        "SELECT table_name, data_type FROM information_schema.columns "
        "WHERE table_schema=? AND column_name='mandant_id'",
        (pg_schema,)).fetchall())
    assert typen.get("import_status") == "text"
    assert typen.get("audit_log") == "text"
    assert typen.get("post_adresse") == "integer"
    assert len({typen[t] for t in typen}) > 1, \
        "Wenn alle gleich wären, bräuchte es den CAST nicht mehr"


@pytest.mark.pg
def test_pg_jede_loeschanweisung_laeuft_durch(pg_verbindung):
    """Jede Anweisung aus `loeschen()`, gegen echte Spaltentypen.

    Es wird nicht geprüft, dass Zeilen verschwinden — das tun die Tests oben.
    Hier zählt, dass Postgres jede Anweisung ANNIMMT. Vor dem 14.10.2026 tat
    es das bei zwei von ihnen nicht, und das fiel erst auf mybabu.io auf.
    """
    un, mandant_id = "app-pruefzugang", 4711
    for tabelle in kern_konto.NACH_UN:
        pg_verbindung.execute(f"DELETE FROM {tabelle} WHERE un=?", (un,))  # noqa: S608
    for tabelle in kern_konto.NACH_MANDANT:
        pg_verbindung.execute(
            f"DELETE FROM {tabelle} WHERE CAST(mandant_id AS TEXT) = ?",  # noqa: S608
            (str(mandant_id),))
    pg_verbindung.execute("DELETE FROM nachricht WHERE gespraech=?", (1,))
    pg_verbindung.execute("DELETE FROM merksatz WHERE betrieb=?", (un,))
    pg_verbindung.execute(
        "DELETE FROM audit_log WHERE ziel_un=? OR akteur_un=? "
        "OR CAST(mandant_id AS TEXT) = ?", (un, un, str(mandant_id)))
    pg_verbindung.execute(kern_konto.db_upsert_geloescht(),
                          (mandant_id, "babu/pruefung/belege", 0, 1,
                           "2026-10-14T00:00:00+00:00"))
    pg_verbindung.execute("DELETE FROM mandant WHERE id=?", (mandant_id,))
    pg_verbindung.execute("DELETE FROM nutzer WHERE email=?", (un,))


@pytest.mark.pg
def test_pg_der_alte_vergleich_waere_aufgefallen(pg_verbindung):
    """Negativkontrolle: der Stand von vor dem 14.10.2026, auf TEXT-Spalten.

    Ohne sie misst der Test davor nur, dass irgendein SQL durchläuft."""
    import psycopg  # noqa: PLC0415
    for tabelle in ("import_status", "audit_log"):
        with pytest.raises(psycopg.errors.UndefinedFunction):
            pg_verbindung.execute(
                f"DELETE FROM {tabelle} WHERE mandant_id=?", (4711,))  # noqa: S608
        pg_verbindung._roh.rollback()  # noqa: SLF001
