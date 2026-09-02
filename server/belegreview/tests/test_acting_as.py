"""Eine Kanzlei arbeitet „als" ein Mandant — und sieht dann DESSEN Daten.

Der Fehler, gegen den diese Datei anschreibt, ist nicht „die Kanzlei kommt
nicht rein", sondern ein leiserer: sie kommt rein, sieht die Belege des
Mandanten — und daneben ihr eigenes, leeres Team, ihre eigenen
Einstellungen, ihre eigene Berater-Nummer. Halb fremde, halb eigene Daten
in einer Ansicht, und keiner Zahl sieht man an, welche von beiden sie ist.

Geprüft wird deshalb an beiden Enden zugleich: die Belegbox (aus git) UND
der Portal-Zustand (aus SQLite) müssen zum selben Mandanten gehören.

Aufbau: eine Kanzlei Süd mit zwei Mandanten (Nina und Berta), jeder mit
eigener Box, eigenem Team und eigenen Betriebsangaben. Dazu die Kanzlei
selbst, die eine eigene — leere — Box hat: an ihr zeigt sich, was ohne
`X-Mandant`-Kopf herauskommt.
"""
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import babu_web  # noqa: E402
import box as bx  # noqa: E402
import boxschreiber  # noqa: E402
import mandanten  # noqa: E402

PASSWORT = "ein-langes-passwort-hier"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _bare(tmp_path: Path, ziel: Path, belege: tuple[str, ...] = ()) -> Path:
    """Ein bare-Store an genau der Stelle, an der `box.store_aus_ref` sucht."""
    arbeit = tmp_path / f"arbeit-{ziel.name}-{abs(hash(str(ziel))) % 10000}"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    _git(arbeit, "config", "user.name", "t")
    _git(arbeit, "config", "user.email", "t@l")
    (arbeit / "README.md").write_text(ziel.name)
    for beleg in belege:
        datei = arbeit / "docs" / "2026-05" / beleg
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_bytes(b"\xff\xd8\xff\xe0" + beleg.encode())
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "stand")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(ziel)],
                   check=True)
    return ziel


def _konto(bw, email: str, rolle: str = "salon") -> str:
    assert bw.nutzer_anlegen(email, email.split("@")[0], "Betrieb", rolle,
                             passwort=PASSWORT) is not None
    return email


def _neuer_client(bw):
    from fastapi.testclient import TestClient
    return TestClient(bw.app, base_url="https://testserver")


def _login(bw, email: str):
    client = _neuer_client(bw)
    bw._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    r = client.post("/api/login", json={"email": email, "passwort": PASSWORT})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture()
def welt2(tmp_path, monkeypatch):
    """Kanzlei Süd mit zwei Mandanten — Boxen, Konten, Portal-Zustand.

    Gibt ein Wörterbuch zurück statt eines Tupels: die Tests unten fragen
    sehr unterschiedliche Teile ab, und `welt["nina_id"]` liest sich
    besser als das siebte Element.
    """
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(babu_web, "ROLLEN", {})
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(bx, "STORE_WURZEL", tmp_path / "stores")
    monkeypatch.setattr(bx, "KLON_WURZEL", tmp_path / "klone")
    bx.registry_leeren()

    # Die eine Box von heute — sie gehört der Kanzlei und ist leer.
    eigene = _bare(tmp_path, tmp_path / "kanzlei.git")
    monkeypatch.setattr(babu_web, "STORE", eigene)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon-kanzlei")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(eigene))

    for ref, beleg in (("inspektor/ws-nina/babu", "20260501-120000-aaa111-alpha.jpg"),
                       ("inspektor/ws-berta/babu", "20260501-120000-bbb222-beta.jpg"),
                       ("inspektor/ws-carla/babu", "20260501-120000-ccc333-gamma.jpg")):
        _bare(tmp_path, bx.store_aus_ref(ref), (beleg,))

    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    kanzlei = _konto(babu_web, "sued@kanzlei.de", "kanzlei")
    sachbearbeiter = _konto(babu_web, "sachbearbeiter@kanzlei.de", "kanzlei")
    fremde = _konto(babu_web, "nord@kanzlei.de", "kanzlei")
    nina = _konto(babu_web, "nina@0711.io")
    berta = _konto(babu_web, "berta@0711.io")
    carla = _konto(babu_web, "carla@0711.io")

    sued = mandanten.kanzlei_anlegen("Kanzlei Süd", kanzlei)
    nord = mandanten.kanzlei_anlegen("Kanzlei Nord", fremde)
    nina_id = mandanten.mandant_anlegen(sued, "Salon Nina", nina,
                                        kontenrahmen="SKR03", berater_nr="12345",
                                        mandant_nr="4711")
    berta_id = mandanten.mandant_anlegen(sued, "Salon Berta", berta,
                                         berater_nr="12345", mandant_nr="4712")
    carla_id = mandanten.mandant_anlegen(nord, "Salon Carla", carla)
    ohne_box_id = mandanten.mandant_anlegen(sued, "Salon Ohne", "sued@kanzlei.de")
    mandanten.box_verknuepfen(nina_id, "inspektor/ws-nina/babu")
    mandanten.box_verknuepfen(berta_id, "inspektor/ws-berta/babu")
    mandanten.box_verknuepfen(carla_id, "inspektor/ws-carla/babu")

    yield {"bw": babu_web, "kanzlei": kanzlei, "sachbearbeiter": sachbearbeiter,
           "fremde": fremde, "nina": nina, "berta": berta, "carla": carla,
           "sued": sued, "nord": nord, "nina_id": nina_id, "berta_id": berta_id,
           "carla_id": carla_id, "ohne_box_id": ohne_box_id}
    bx.registry_leeren()


def _belege(client, mandant_id=None) -> set[str]:
    kopf = {"X-Mandant": str(mandant_id)} if mandant_id else {}
    r = client.get("/api/belege", headers=kopf)
    assert r.status_code == 200, r.text
    return {b["stamm"] for b in r.json()["belege"]}


# ————— Die Belegbox folgt dem Kopf —————

def test_ohne_kopf_bleibt_es_die_eigene_box(welt2):
    """Das Alt-Verhalten, an dem der Golden-Diff des Deploys hängt."""
    client = _login(welt2["bw"], welt2["kanzlei"])
    assert _belege(client) == set()


def test_mit_kopf_kommen_die_belege_des_mandanten(welt2):
    client = _login(welt2["bw"], welt2["kanzlei"])
    assert any("alpha" in s for s in _belege(client, welt2["nina_id"]))
    assert not any("beta" in s for s in _belege(client, welt2["nina_id"]))


def test_derselbe_zugang_wechselt_zwischen_zwei_mandanten(welt2):
    """Kein Zustand bleibt hängen: zwei Anfragen, zwei Antworten."""
    client = _login(welt2["bw"], welt2["kanzlei"])
    assert any("alpha" in s for s in _belege(client, welt2["nina_id"]))
    assert any("beta" in s for s in _belege(client, welt2["berta_id"]))
    assert not any("alpha" in s for s in _belege(client, welt2["berta_id"]))
    # …und danach wieder die eigene, leere Box.
    assert _belege(client) == set()


def test_ein_sachbearbeiter_darf_erst_nach_dem_eintragen(welt2):
    client = _login(welt2["bw"], welt2["sachbearbeiter"])
    r = client.get("/api/belege", headers={"X-Mandant": str(welt2["nina_id"])})
    assert r.status_code == 403
    mandanten.mitglied_anlegen(welt2["sued"], welt2["sachbearbeiter"])
    assert any("alpha" in s for s in _belege(client, welt2["nina_id"]))


def test_ein_mandant_ohne_box_meldet_sich_als_solcher(welt2):
    """`box_ausstehend` ist kein Rechteproblem — 409, nicht 403."""
    client = _login(welt2["bw"], welt2["kanzlei"])
    r = client.get("/api/belege", headers={"X-Mandant": str(welt2["ohne_box_id"])})
    assert r.status_code == 409
    assert "eingerichtet" in r.json()["fehler"]


# ————— Der Portal-Zustand folgt mit —————

def test_acting_as_zeigt_das_team_des_mandanten(welt2):
    """`/api/team` hängt an `_api_wache` und fasst keine Box an — trotzdem
    muss es beim Acting-as das Team des Mandanten zeigen. Genau hier war
    die Gefahr, dass Belege und Portal-Zustand auseinanderlaufen."""
    bw = welt2["bw"]
    nina = _login(bw, welt2["nina"])
    assert nina.post("/api/team", json={"name": "Jana", "email": "jana@salon.de",
                                        "betrag": "2400"}).status_code == 200

    kanzlei = _login(bw, welt2["kanzlei"])
    eigenes = kanzlei.get("/api/team").json()["team"]
    assert [p["name"] for p in eigenes] == []

    fremdes = kanzlei.get("/api/team",
                          headers={"X-Mandant": str(welt2["nina_id"])}).json()["team"]
    assert [p["name"] for p in fremdes] == ["Jana"]

    # Und der zweite Mandant hat sein eigenes (leeres) Team.
    assert kanzlei.get("/api/team",
                       headers={"X-Mandant": str(welt2["berta_id"])}
                       ).json()["team"] == []


def test_acting_as_zeigt_die_kundinnen_des_mandanten(welt2):
    """Dasselbe für eine Route hinter `_box_wache`."""
    bw = welt2["bw"]
    nina = _login(bw, welt2["nina"])
    assert nina.post("/api/kundinnen", json={"name": "Frau Meier"}).status_code == 200

    kanzlei = _login(bw, welt2["kanzlei"])
    assert kanzlei.get("/api/kundinnen").json()["kundinnen"] == []
    mit = kanzlei.get("/api/kundinnen",
                      headers={"X-Mandant": str(welt2["nina_id"])}).json()
    assert [k["name"] for k in mit["kundinnen"]] == ["Frau Meier"]


def test_acting_as_rechnet_mit_den_einstellungen_des_mandanten(welt2):
    """Betriebsangaben sind finanziell — der Monatsabschluss hängt daran."""
    bw = welt2["bw"]
    bw.db_einstellung_setzen(welt2["berta"], "kleinunternehmer", "Ja")

    kanzlei = _login(bw, welt2["kanzlei"])
    fuer = {}
    for name in ("nina_id", "berta_id"):
        r = kanzlei.get("/api/monatsabschluss/2026-05",
                        headers={"X-Mandant": str(welt2[name])})
        assert r.status_code == 200, r.text
        fuer[name] = r.json()["profil"]["braucht_ustva"]
    assert fuer["nina_id"] is True and fuer["berta_id"] is False, \
        "beide Mandanten wurden mit demselben Umsatzprofil gerechnet"
    # Und ohne Kopf das eigene Profil der Kanzlei, unverändert.
    assert kanzlei.get("/api/monatsabschluss/2026-05"
                       ).json()["profil"]["braucht_ustva"] is True


# ————— Der Export-Kopf —————

def _kopffelder(client, monat: str, mandant_id=None) -> list[str]:
    """Die erste Zeile des EXTF-Stapels, in Felder zerlegt.

    Feld 10 ist die Berater-, Feld 11 die Mandantennummer (EXTF v13,
    `extf.stapel`). Auf Positionen prüfen und nicht auf Teilzeichenketten:
    eine `1` steht im Kopf an mehreren Stellen.
    """
    kopf = {"X-Mandant": str(mandant_id)} if mandant_id else {}
    r = client.get(f"/api/export/{monat}.csv", headers=kopf)
    assert r.status_code == 200, r.text
    return r.content.decode("cp1252").split("\r\n")[0].split(";")


def test_der_export_traegt_die_nummern_des_mandanten(welt2, monkeypatch):
    """Berater- und Mandantennummer sagen der Kanzlei-Software, WESSEN
    Buchhaltung sie importiert. Aus der Serverumgebung kämen für zwei
    Mandanten dieselben — im DATEV-Import liefen sie ineinander."""
    monkeypatch.setenv("BABU_BERATER", "99999")
    monkeypatch.setenv("BABU_MANDANT", "1")
    kanzlei = _login(welt2["bw"], welt2["kanzlei"])

    ohne = _kopffelder(kanzlei, "2026-05")
    assert (ohne[10], ohne[11]) == ("99999", "1")

    fuer_nina = _kopffelder(kanzlei, "2026-05", welt2["nina_id"])
    assert (fuer_nina[10], fuer_nina[11]) == ("12345", "4711")
    fuer_berta = _kopffelder(kanzlei, "2026-05", welt2["berta_id"])
    assert (fuer_berta[10], fuer_berta[11]) == ("12345", "4712")


def test_kontenrahmen_von_liest_die_mandantenzeile(welt2, monkeypatch):
    """Ohne HTTP, damit die Regel selbst sichtbar wird: die `mandant`-Zeile
    tritt an die Stelle der Umgebungsvorgabe, die Angabe des Betriebs
    schlägt weiterhin beides."""
    monkeypatch.setenv("BABU_KONTENRAHMEN", "SKR04")
    bw = welt2["bw"]
    marke = bw._AKTIVER_MANDANT.set(welt2["nina_id"])  # noqa: SLF001
    try:
        assert bw.kontenrahmen_von(welt2["kanzlei"]) == "SKR03"
        # Die eigene Wahl des Betriebs geht vor.
        bw.db_einstellung_setzen(welt2["nina"], "kontenrahmen", "SKR04")
        assert bw.kontenrahmen_von(welt2["kanzlei"]) == "SKR04"
    finally:
        bw._AKTIVER_MANDANT.reset(marke)  # noqa: SLF001
    # Ohne Mandant bleibt es bei der Umgebung.
    assert bw.kontenrahmen_von(welt2["kanzlei"]) == "SKR04"


# ————— Wer den Kopf nicht führen darf —————

def test_eine_fremde_kanzlei_kommt_nicht_an_den_mandanten(welt2):
    """Der Cross-Tenant-Fall: Kanzlei Nord fragt nach einem Mandanten der
    Kanzlei Süd. Nicht „ist das eine Kanzlei-Rolle", sondern „betreut DIESE
    Kanzlei DIESEN Mandanten"."""
    client = _login(welt2["bw"], welt2["fremde"])
    r = client.get("/api/belege", headers={"X-Mandant": str(welt2["nina_id"])})
    assert r.status_code == 403
    # Ihren eigenen Mandanten sieht sie sehr wohl.
    assert any("gamma" in s for s in _belege(client, welt2["carla_id"]))


def test_ein_salon_mit_kopf_wird_abgewiesen(welt2):
    """Eine Salon-Rolle ist in keiner Kanzlei Mitglied — auch nicht in der,
    die sie betreut. Der Kopf wird nicht übergangen, sondern abgelehnt."""
    client = _login(welt2["bw"], welt2["nina"])
    r = client.get("/api/belege", headers={"X-Mandant": str(welt2["berta_id"])})
    assert r.status_code == 403
    # Auch auf den eigenen Mandanten nicht: der Kopf ist ein Werkzeug der
    # Kanzlei, nicht des Betriebs.
    assert client.get("/api/belege",
                      headers={"X-Mandant": str(welt2["nina_id"])}).status_code == 403
    # Ohne Kopf ist alles wie immer.
    assert client.get("/api/belege").status_code == 200


def test_eine_erfundene_nummer_kommt_nicht_durch(welt2):
    client = _login(welt2["bw"], welt2["kanzlei"])
    for wert in ("999999", "0", "-1", "abc", "1; DROP TABLE mandant"):
        r = client.get("/api/belege", headers={"X-Mandant": wert})
        assert r.status_code == 403, f"{wert!r} kam durch"


def test_ein_leerer_kopf_ist_wie_kein_kopf(welt2):
    """Sonst brächte ein Frontend, das die Variable noch nicht gefüllt hat,
    jeden Aufruf zum Scheitern."""
    client = _login(welt2["bw"], welt2["kanzlei"])
    assert client.get("/api/belege", headers={"X-Mandant": "  "}).status_code == 200


def test_box_mitglied_ohne_nummer_ist_die_regel_von_heute(welt2):
    """Die Zusicherung für den Ein-Betrieb: ohne `mandant_id` entscheidet
    weiter die Rolle, mit `mandant_id` nur noch die Mitgliedschaft."""
    bw = welt2["bw"]
    assert bw.box_mitglied(welt2["kanzlei"]) is True
    assert bw.box_mitglied(welt2["fremde"]) is True
    assert bw.box_mitglied(welt2["kanzlei"], welt2["nina_id"]) is True
    assert bw.box_mitglied(welt2["fremde"], welt2["nina_id"]) is False
    assert bw.box_mitglied(welt2["nina"], welt2["nina_id"]) is False


# ————— salon_von_aktiv selbst —————

def test_salon_von_aktiv_ist_ohne_mandant_das_alte_verhalten(welt2):
    bw = welt2["bw"]
    assert bw.salon_von_aktiv(welt2["kanzlei"]) == welt2["kanzlei"]
    assert bw.salon_von_aktiv(welt2["nina"]) == welt2["nina"]


def test_salon_von_aktiv_zeigt_beim_acting_as_auf_den_mandanten(welt2):
    bw = welt2["bw"]
    marke = bw._AKTIVER_MANDANT.set(welt2["berta_id"])  # noqa: SLF001
    try:
        assert bw.salon_von_aktiv(welt2["kanzlei"]) == welt2["berta"]
    finally:
        bw._AKTIVER_MANDANT.reset(marke)  # noqa: SLF001
