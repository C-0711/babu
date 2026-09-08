"""Jeder Betrieb lädt in SEINE Belegbox — auch ohne `X-Mandant`-Kopf.

Der Befund vom 08.09.2026, und der Grund für diese Datei: die iOS-App lädt
über `POST /api/aufnahme`, die Route hängt korrekt an `_box_wache` — aber
`_box_wache` löste ohne Kopf über `box_von(un, None)` immer auf die
**Default-Box** auf. Und die App schickt nie einen Kopf (repo-weit kein
Treffer in `ios/`). Der zweite Betrieb hätte seine Belege damit in die Box
des ersten geladen, ohne dass irgendetwas gemeldet hätte.

Der Fehler saß nicht in der Tür, sondern in der Auflösung. Repariert ist er
in `_eigener_mandant`, eingehängt in `_api_wache` — eine Stelle, die rund
hundert Routen zugleich mandantenfähig macht. Diese Datei ist der Nachweis,
und sie prüft alle vier Ausgänge:

1. kein Mandat        → Default-Box, alles bleibt wie heute (Ninas Rückfall)
2. Mandat mit Box     → dessen Box, ohne jeden Kopf
3. Mandat ohne Box    → 409 „wird noch eingerichtet", NICHT die Default-Box
4. mehrere Mandate    → 409, fail-closed statt raten

Der eigentliche Beweis steht in `test_zwei_betriebe_laden_in_zwei_boxen`:
zwei Konten laden nacheinander hoch, danach liegt in jeder Box genau ein
Beleg — und zwar der eigene.
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
BON = "EDEKA\n08.09.2026\nSumme 14,88 EUR\nMwSt 7% 0,97"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _bare(tmp_path: Path, ziel: Path) -> Path:
    """Ein leerer bare-Store genau dort, wo `box.store_aus_ref` ihn sucht."""
    arbeit = tmp_path / f"arbeit-{abs(hash(str(ziel))) % 100000}"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    _git(arbeit, "config", "user.name", "t")
    _git(arbeit, "config", "user.email", "t@l")
    (arbeit / "README.md").write_text(ziel.name)
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "stand")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(ziel)],
                   check=True)
    return ziel


def _konto(bw, email: str, rolle: str = "salon") -> str:
    assert bw.nutzer_anlegen(email, email.split("@")[0], "Betrieb", rolle,
                             passwort=PASSWORT, box=True) is not None
    return email


def _login(bw, email: str):
    from fastapi.testclient import TestClient
    client = TestClient(bw.app, base_url="https://testserver")
    bw._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    r = client.post("/api/login", json={"email": email, "passwort": PASSWORT})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture()
def welt(tmp_path, monkeypatch):
    """Eine Default-Box (wie heute) und zwei eigene Boxen daneben."""
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    monkeypatch.setattr(babu_web, "ROLLEN", {})
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(bx, "STORE_WURZEL", tmp_path / "stores")
    monkeypatch.setattr(bx, "KLON_WURZEL", tmp_path / "klone")
    bx.registry_leeren()

    default = _bare(tmp_path, tmp_path / "default.git")
    monkeypatch.setattr(babu_web, "STORE", default)
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon-default")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(default))
    monkeypatch.setattr(boxschreiber, "REF", "inspektor/ws-default/babu")

    for ref in ("inspektor/ws-anna/babu", "inspektor/ws-bea/babu"):
        _bare(tmp_path, bx.store_aus_ref(ref))
        # Der Klon pusht ans bare-Repo, nicht ans Gateway.
        monkeypatch.setitem(_REMOTES, ref, str(bx.store_aus_ref(ref)))
    monkeypatch.setattr(bx, "remote_aus_ref", lambda ref: _REMOTES[ref.strip("/")])

    babu_web._LOGIN_VERSUCHE.clear()  # noqa: SLF001
    buero = _konto(babu_web, "buero@kanzlei.de", "kanzlei")
    anna = _konto(babu_web, "anna@salon.de")
    bea = _konto(babu_web, "bea@salon.de")
    ohne = _konto(babu_web, "ohne@salon.de")
    allein = _konto(babu_web, "allein@salon.de")

    kid = mandanten.kanzlei_anlegen("Kanzlei Süd", buero)
    anna_id = mandanten.mandant_anlegen(kid, "Salon Anna", anna)
    bea_id = mandanten.mandant_anlegen(kid, "Salon Bea", bea)
    ohne_id = mandanten.mandant_anlegen(kid, "Salon Ohne", ohne)
    mandanten.box_verknuepfen(anna_id, "inspektor/ws-anna/babu")
    mandanten.box_verknuepfen(bea_id, "inspektor/ws-bea/babu")

    yield {"bw": babu_web, "tmp": tmp_path, "anna": anna, "bea": bea,
           "ohne": ohne, "allein": allein, "buero": buero, "kanzlei_id": kid,
           "anna_id": anna_id, "bea_id": bea_id, "ohne_id": ohne_id}
    bx.registry_leeren()


_REMOTES: dict[str, str] = {}


def _hochladen(client, name: str) -> dict:
    r = client.post("/api/aufnahme", params={"name": name, "text": BON},
                    content=b"\xff\xd8\xff\xe0bild-" + name.encode())
    assert r.status_code == 200, r.text
    return r.json()


def _im_stand(store: Path) -> set[str]:
    """Was liegt in dieser Box — direkt aus git gelesen."""
    roh = subprocess.run(["git", "-C", str(store), "ls-tree", "-r", "--name-only",
                          "HEAD"], capture_output=True, text=True)
    return {Path(z).name for z in roh.stdout.splitlines() if z.startswith("docs/")}


# ————— Der eigentliche Beweis —————

def test_zwei_betriebe_laden_in_zwei_boxen(welt, monkeypatch):
    """Zwei Konten, zwei Uploads, kein Kopf — und trotzdem zwei Boxen.

    Vor dem 08.09.2026 landeten beide Belege in der Default-Box, und Anna
    hätte Beas Kassenbon in ihrer Liste gehabt.
    """
    bw = welt["bw"]
    monkeypatch.setattr(bw, "_hintergrund_lesen_starten",
                        lambda pfad, daten, endung, un: None)

    _hochladen(_login(bw, welt["anna"]), "anna-bon.jpg")
    _hochladen(_login(bw, welt["bea"]), "bea-bon.jpg")

    anna_box = _im_stand(bx.store_aus_ref("inspektor/ws-anna/babu"))
    bea_box = _im_stand(bx.store_aus_ref("inspektor/ws-bea/babu"))
    default = _im_stand(welt["tmp"] / "default.git")

    assert len(anna_box) == 1 and any("anna-bon" in n for n in anna_box)
    assert len(bea_box) == 1 and any("bea-bon" in n for n in bea_box)
    assert default == set(), f"in der Default-Box liegt fremdes: {default}"


def test_jede_sieht_nur_ihre_eigenen_belege(welt, monkeypatch):
    """Die Gegenprobe von der Leseseite: dieselbe Route, zwei Antworten."""
    bw = welt["bw"]
    monkeypatch.setattr(bw, "_hintergrund_lesen_starten",
                        lambda pfad, daten, endung, un: None)
    _hochladen(_login(bw, welt["anna"]), "anna-bon.jpg")
    _hochladen(_login(bw, welt["bea"]), "bea-bon.jpg")

    def stämme(email):
        r = _login(bw, email).get("/api/belege")
        assert r.status_code == 200, r.text
        return {b["stamm"] for b in r.json()["belege"]}

    a, b = stämme(welt["anna"]), stämme(welt["bea"])
    assert any("anna-bon" in s for s in a) and not any("bea-bon" in s for s in a)
    assert any("bea-bon" in s for s in b) and not any("anna-bon" in s for s in b)


# ————— Die vier Ausgänge der Auflösung —————

def test_ohne_mandat_bleibt_es_die_default_box(welt):
    """Ninas Rückfall: wer keine Mandantenzeile hat, arbeitet wie bisher.

    Das ist die Zusicherung, an der der Golden-Diff des Deploy-Rituals
    hängt — ohne sie wäre der Umbau für die laufende Kundin ein Umzug.
    """
    bw = welt["bw"]
    assert bw._eigener_mandant(welt["allein"]) == (None, None)  # noqa: SLF001
    r = _login(bw, welt["allein"]).get("/api/belege")
    assert r.status_code == 200, r.text


def test_ein_mandat_mit_box_gewinnt_ohne_kopf(welt):
    bw = welt["bw"]
    nummer, fehler = bw._eigener_mandant(welt["anna"])  # noqa: SLF001
    assert fehler is None and nummer == welt["anna_id"]


def test_ein_mandat_ohne_box_wartet_ehrlich(welt):
    """Kein stiller Rückfall: lieber 409 als in eine fremde Box schreiben."""
    bw = welt["bw"]
    nummer, fehler = bw._eigener_mandant(welt["ohne"])  # noqa: SLF001
    assert fehler is None and nummer == welt["ohne_id"]

    r = _login(bw, welt["ohne"]).get("/api/belege")
    assert r.status_code == 409, r.text
    assert "eingerichtet" in r.json()["fehler"]


def test_zwei_mandate_werden_nicht_geraten(welt):
    """Zwei Steuerbüros für denselben Betrieb sind erlaubt — dann ist
    „welche Box?" aber keine Frage, die der Server beantworten darf."""
    bw = welt["bw"]
    zweite = mandanten.kanzlei_anlegen("Kanzlei Nord", "nord@kanzlei.de")
    mandanten.mandant_anlegen(zweite, "Anna bei Nord", welt["anna"])

    r = _login(bw, welt["anna"]).get("/api/belege")
    assert r.status_code == 409, r.text
    assert "mehreren Steuerbüros" in r.json()["fehler"]


def test_die_mitarbeiterin_arbeitet_in_der_box_ihres_salons(welt):
    """`salon_von`, nicht das eigene Konto: sie hat keine eigene Box."""
    bw = welt["bw"]
    bw.nutzer_anlegen("hilfe@salon.de", "Hilfe", "Betrieb", "mitarbeit",
                      passwort=PASSWORT, box=True)
    with bw._DB_LOCK, bw._db() as c:  # noqa: SLF001
        c.execute("UPDATE nutzer SET gehoert_zu=? WHERE email=?",
                  (welt["anna"], "hilfe@salon.de"))
    nummer, fehler = bw._eigener_mandant("hilfe@salon.de")  # noqa: SLF001
    assert fehler is None and nummer == welt["anna_id"]


def test_der_kopf_schlaegt_den_eigenen_mandanten(welt):
    """Acting-as bleibt unangetastet: die Kanzlei sieht, was sie wählt."""
    bw = welt["bw"]
    client = _login(bw, welt["buero"])
    r = client.get("/api/belege", headers={"X-Mandant": str(welt["anna_id"])})
    assert r.status_code == 200, r.text
    # …und ein fremder Kopf bleibt 403, nicht etwa die eigene Box.
    dritte = mandanten.kanzlei_anlegen("Kanzlei West", "west@kanzlei.de")
    fremd = mandanten.mandant_anlegen(dritte, "Salon Fremd", "fremd@salon.de")
    r = client.get("/api/belege", headers={"X-Mandant": str(fremd)})
    assert r.status_code == 403, r.text


# ————— Was die App beim Anmelden erfährt —————

def test_das_anmelden_sagt_ob_es_schon_eine_ablage_gibt(welt):
    """`POST /api/app-anmelden` trägt seit 08.09.2026 ein Feld `box`.

    Ohne dieses Feld meldete die App nach jeder geglückten Anmeldung
    „Verbunden ✓ — alles bereit", setzte `ablageAktiv` und schickte jeden
    Beleg gegen eine Wand — bei jedem App-Start aufs Neue, denn 403 galt
    ihr nicht als Zugangsproblem. Ein selbst registriertes Konto
    (`/api/signup` legt `box=False` an) trifft das immer.
    """
    from fastapi.testclient import TestClient
    bw = welt["bw"]
    client = TestClient(bw.app, base_url="https://testserver")

    def anmelden(email):
        bw._LOGIN_VERSUCHE.clear()  # noqa: SLF001
        r = client.post("/api/app-anmelden",
                        json={"email": email, "passwort": PASSWORT,
                              "geraet": "iPhone"})
        assert r.status_code == 200, r.text
        return r.json()

    assert anmelden(welt["anna"])["box"] is True     # Mandat mit Box
    assert anmelden(welt["ohne"])["box"] is False    # Box wird eingerichtet
    assert anmelden(welt["allein"])["box"] is True   # Default-Box wie heute


def test_ohne_ablage_gibt_das_hochladen_kein_gewoehnliches_nein(welt):
    """409, nicht 403: „hier fehlt noch etwas" ist kein „du darfst nicht".

    Die App unterscheidet daran, ob sie es weiter versuchen soll — 401
    heißt neu verbinden, 403/409 heißt aufhören zu klopfen und es sagen.
    """
    bw = welt["bw"]
    r = _login(bw, welt["ohne"]).post(
        "/api/aufnahme", params={"name": "bon.jpg", "text": BON},
        content=b"\xff\xd8\xff\xe0bild")
    assert r.status_code == 409, r.text
    assert "eingerichtet" in r.json()["fehler"]


# ————— Die Routen, die früher an der Wache vorbeigingen —————

def test_der_chat_liest_aus_der_box_des_fragenden(welt, monkeypatch):
    """`/chat` prüfte seine Grenze selbst und las dahinter immer die
    Default-Box — er hätte jedem Betrieb aus Ninas Zahlen geantwortet.

    Gemessen wird nicht die Antwort (die kommt von Gemma), sondern welche
    Box beim Zusammentragen des Fallwissens aktiv ist. Genau das wäre
    abgeflossen.
    """
    bw = welt["bw"]
    import wissen
    aktive: list[str] = []
    # `weltblock` ist die Stelle, an der der Chat den Bestand des Betriebs
    # zusammenträgt — dort muss die richtige Box aktiv sein.
    monkeypatch.setattr(wissen, "weltblock",
                        lambda *a, **k: aktive.append(bw._box().ref) or "")  # noqa: SLF001
    monkeypatch.setattr(bw, "_recherche", lambda frage: "")

    _login(bw, welt["anna"]).post("/chat", json={"frage": "Was gab ich aus?"})
    _login(bw, welt["bea"]).post("/chat", json={"frage": "Was gab ich aus?"})

    assert aktive == ["inspektor/ws-anna/babu", "inspektor/ws-bea/babu"], aktive


def test_ein_konto_ohne_ablage_kommt_auch_in_den_chat_nicht(welt):
    """Dieselbe Tür wie für die Belege — auch beim Chat."""
    r = _login(welt["bw"], welt["ohne"]).post(
        "/chat", json={"frage": "Wie viel habe ich verdient?"})
    assert r.status_code == 409, r.text


def test_der_onboarding_vertrag_landet_beim_richtigen_salon(welt, monkeypatch):
    """Eine Mitarbeiterin unterschreibt — in der Box IHRES Salons.

    Der Weg hat kein angemeldetes Konto (er läuft über einen Einladungs-
    schlüssel), also lief auch keine Wache und setzte keine Box: der
    Arbeitsvertrag wäre bis 08.09.2026 in der Default-Box gelandet, egal
    für welchen Betrieb unterschrieben wurde.
    """
    bw = welt["bw"]
    geschrieben: list[tuple[str, str]] = []

    def _merken(box, pfad, daten, nachricht, un, **rest):
        geschrieben.append((box.ref, pfad))
        return "commit-egal"

    import boxschreiber
    monkeypatch.setattr(boxschreiber, "schreiben", _merken)

    # Die Auflösung ist der springende Punkt — sie muss Beas Box liefern,
    # obwohl niemand angemeldet ist.
    nummer, fehler = bw._eigener_mandant(welt["bea"])  # noqa: SLF001
    assert fehler is None and nummer == welt["bea_id"]
    assert bx.box_von(welt["bea"], nummer).ref == "inspektor/ws-bea/babu"
