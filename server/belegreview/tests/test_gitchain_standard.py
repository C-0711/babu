"""GitChain-Standard (27.09.2026): Schreibweg, Lesespiegel, Box-Anlage, Anmeldung.

Was diese Datei belegt — alles mit echten Git-Repos auf der Platte, ohne Netz:

1. Auth-Kopf: Basic `svc-babu:<token>` (heute), Bearer per Schalter; der Token
   steht nie in einer Fehlermeldung, vorhandene GIT_CONFIG_*-Einträge bleiben.
2. Lesen aus dem eigenen Lesespiegel (`BABU_LESEN=klon`): der Spiegel entsteht
   per `clone --mirror`, der eigene Push steht sofort darin, ein fremder Commit
   nach dem nächsten Nachziehen; ein umgezogenes Remote wird übernommen.
3. Box-Anlage per Push-to-create (`box_anlegen`): idempotent, nur Verweise der
   Form babu/<betrieb>/belege.
4. Token-Anmeldung eines Menschen über `GET /v1/user` — Dienstkonten und
   Nicht-gcpat-Werte werden abgewiesen, Fehler führen nie zum Absturz.

Der Lauf gegen den echten Dienst steht in `werkzeuge/gitchain_e2e.py`.
"""
import base64
import subprocess
import sys
import time
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

import babu_web  # noqa: E402
import box as bx  # noqa: E402
import boxschreiber  # noqa: E402

TOKEN = "gcpat-test0123456789abcdefghijklmnop"
# Andere Testdateien ersetzen `babu_web.wer_token` modulweit durch ein Lambda
# (ohne Rückbau) — geprüft wird hier deshalb die echte Funktion von damals.
ECHTES_WER_TOKEN = babu_web.wer_token


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _server_repo(tmp_path: Path, ziel: Path, dateien: dict[str, str]) -> Path:
    """Ein Bare-Repo mit einem Commit — steht für die Box beim Dienst."""
    arbeit = tmp_path / f"arbeit-{ziel.name}"
    subprocess.run(["git", "init", "-q", "-b", "main", str(arbeit)], check=True)
    _git(arbeit, "config", "user.name", "t")
    _git(arbeit, "config", "user.email", "t@l")
    for pfad, inhalt in dateien.items():
        (arbeit / pfad).parent.mkdir(parents=True, exist_ok=True)
        (arbeit / pfad).write_text(inhalt)
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", "stand")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--bare", str(arbeit), str(ziel)], check=True)
    return ziel


def _fremder_commit(tmp_path: Path, remote: Path, pfad: str, inhalt: str) -> str:
    """Ein Commit, den jemand anderes (Hintergrundjob, zweiter Server) pusht."""
    arbeit = tmp_path / "fremd"
    if not arbeit.exists():
        subprocess.run(["git", "clone", "-q", str(remote), str(arbeit)], check=True)
        _git(arbeit, "config", "user.name", "fremd")
        _git(arbeit, "config", "user.email", "f@l")
    _git(arbeit, "pull", "-q", "origin", "main")
    (arbeit / pfad).parent.mkdir(parents=True, exist_ok=True)
    (arbeit / pfad).write_text(inhalt)
    _git(arbeit, "add", "-A")
    _git(arbeit, "commit", "-q", "-m", f"fremd: {pfad}")
    _git(arbeit, "push", "-q", "origin", "main")
    return _git(arbeit, "rev-parse", "HEAD")


# ---------------------------------------------------------------------------
# 1. Auth-Kopf und Fehlermeldungen
# ---------------------------------------------------------------------------

def test_basic_kopf_mit_dienstkonto(tmp_path, monkeypatch):
    pat = tmp_path / ".pat_babu"
    pat.write_text(TOKEN + "\n")
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", pat)
    monkeypatch.setattr(boxschreiber, "GIT_AUTH", "basic")
    monkeypatch.setattr(boxschreiber, "GIT_NUTZER", "svc-babu")
    monkeypatch.delenv("GIT_CONFIG_COUNT", raising=False)
    env = boxschreiber._pat_umgebung()  # noqa: SLF001
    assert env["GIT_CONFIG_COUNT"] == "2"
    assert env["GIT_CONFIG_KEY_0"] == "http.extraHeader"
    kopf = env["GIT_CONFIG_VALUE_0"]
    assert kopf.startswith("Authorization: Basic ")
    assert base64.b64decode(kopf.split()[-1]).decode() == f"svc-babu:{TOKEN}"
    # Kein stiller zweiter Weg über einen Schlüsselbund, keine Rückfrage.
    assert env["GIT_CONFIG_KEY_1"] == "credential.helper"
    assert env["GIT_CONFIG_VALUE_1"] == ""
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_bearer_per_schalter(tmp_path, monkeypatch):
    pat = tmp_path / ".pat_babu"
    pat.write_text(TOKEN)
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", pat)
    monkeypatch.setattr(boxschreiber, "GIT_AUTH", "bearer")
    monkeypatch.delenv("GIT_CONFIG_COUNT", raising=False)
    env = boxschreiber._pat_umgebung()  # noqa: SLF001
    assert env["GIT_CONFIG_VALUE_0"] == f"Authorization: Bearer {TOKEN}"


def test_vorhandene_git_config_bleibt(tmp_path, monkeypatch):
    """compose setzt safe.directory über GIT_CONFIG_* — früher überschrieben."""
    pat = tmp_path / ".pat_babu"
    pat.write_text(TOKEN)
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", pat)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "safe.directory")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "*")
    env = boxschreiber._pat_umgebung()  # noqa: SLF001
    assert env["GIT_CONFIG_COUNT"] == "3"
    assert (env["GIT_CONFIG_KEY_0"], env["GIT_CONFIG_VALUE_0"]) == ("safe.directory", "*")
    assert env["GIT_CONFIG_KEY_1"] == "http.extraHeader"


def test_ohne_token_datei_kein_kopf(tmp_path, monkeypatch):
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "fehlt")
    monkeypatch.delenv("GIT_CONFIG_COUNT", raising=False)
    env = boxschreiber._pat_umgebung()  # noqa: SLF001
    assert "GIT_CONFIG_COUNT" not in env


@pytest.mark.parametrize("stderr, erwartet", [
    ("fatal: Authentication failed for 'http://127.0.0.1:3361/git/babu/x/belege.git/'", "401"),
    ("remote: {\"error\":\"Invalid or insufficient personal access token\"}\n"
     "fatal: unable to access '…': The requested URL returned error: 401", "401"),
    ("fatal: could not read Username for 'http://…': terminal prompts disabled", "401"),
    ("fatal: unable to access '…': The requested URL returned error: 403", "403"),
    ("fatal: repository 'http://…/belege.git/' not found", "404"),
])
def test_fehlertext_klar(stderr, erwartet):
    text = boxschreiber.git_fehler_text(stderr)
    assert erwartet in text


def test_fehlertext_schwaerzt_token():
    text = boxschreiber.git_fehler_text(f"irgendwas {TOKEN} kaputt")
    assert TOKEN not in text and "gcpat-***" in text


# ---------------------------------------------------------------------------
# 2. Lesespiegel
# ---------------------------------------------------------------------------

@pytest.fixture()
def klonwelt(tmp_path, monkeypatch):
    """Default-Box im Modus `klon`: Remote ist ein Bare-Repo auf der Platte."""
    monkeypatch.setenv("BABU_LESEN", "klon")
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")
    monkeypatch.setattr(bx, "LESE_WURZEL", tmp_path / "lesen")
    monkeypatch.setattr(bx, "LESE_TTL", 3600.0)
    monkeypatch.setattr(babu_web, "INDEX_TTL", 0.0)
    remote = _server_repo(tmp_path, tmp_path / "server" / "belege.git",
                          {"README.md": "box", "review/a.json": '{"x": 1}'})
    monkeypatch.setattr(boxschreiber, "REF", "babu/test-1/belege")
    monkeypatch.setattr(boxschreiber, "REMOTE", str(remote))
    monkeypatch.setattr(boxschreiber, "KLON", tmp_path / "klon")
    bx.registry_leeren()
    yield {"tmp": tmp_path, "remote": remote}
    bx.registry_leeren()


def test_klon_modus_liest_nicht_im_store(klonwelt):
    b = bx.default_box()
    assert b.store == klonwelt["tmp"] / "lesen" / "babu" / "test-1" / "belege.git"
    assert "inspektor-store" not in str(b.store)


def test_spiegel_entsteht_und_wird_gelesen(klonwelt):
    b = bx.default_box()
    assert not b.store.exists()
    assert bx.lesestand_holen(b, sofort=True) is True
    assert (b.store / "HEAD").is_file()
    assert babu_web.git_show("review/a.json") == b'{"x": 1}'
    # Kein halber Spiegel bleibt liegen.
    assert not b.store.with_name(b.store.name + ".neu").exists()


def test_eigener_push_steht_sofort_im_spiegel(klonwelt):
    b = bx.default_box()
    bx.lesestand_holen(b, sofort=True)
    boxschreiber.schreiben(b, "docs/2026-09/beleg.txt", b"neu", "aufnahme: beleg", "nina")
    # LESE_TTL ist eine Stunde — ohne den Nachzug nach dem Push stünde er nicht da.
    assert babu_web.git_show("docs/2026-09/beleg.txt") == b"neu"
    assert _git(b.store, "rev-parse", "HEAD") == _git(klonwelt["remote"], "rev-parse", "HEAD")


def test_fremder_commit_nach_nachziehen(klonwelt, monkeypatch):
    b = bx.default_box()
    bx.lesestand_holen(b, sofort=True)
    babu_web.index_aktuell()
    kopf = _fremder_commit(klonwelt["tmp"], klonwelt["remote"], "review/b.json", "{}")
    # Innerhalb der Frist bleibt der Spiegel, wo er war …
    babu_web.index_aktuell()
    assert _git(b.store, "rev-parse", "HEAD") != kopf
    # … nach der Frist zieht der Index-Neubau ihn nach.
    monkeypatch.setattr(bx, "LESE_TTL", 0.0)
    babu_web.index_aktuell()
    assert _git(b.store, "rev-parse", "HEAD") == kopf
    assert babu_web.git_show("review/b.json") == b"{}"


def test_remote_umzug_wird_uebernommen(klonwelt, monkeypatch):
    """Go-live: Spiegel und Arbeitskopie zeigen noch aufs alte Gateway."""
    tmp = klonwelt["tmp"]
    b = bx.default_box()
    bx.lesestand_holen(b, sofort=True)
    boxschreiber.schreiben(b, "x.txt", b"1", "eins", "nina")
    # Umzug: vollständiger Spiegel des alten Remotes an eine neue Adresse.
    neu = tmp / "neuer-dienst" / "belege.git"
    subprocess.run(["git", "clone", "-q", "--mirror", str(klonwelt["remote"]), str(neu)],
                   check=True)
    monkeypatch.setattr(boxschreiber, "REMOTE", str(neu))
    bx.registry_leeren()
    b2 = bx.default_box()
    assert b2.remote == str(neu)
    boxschreiber.schreiben(b2, "y.txt", b"2", "zwei", "nina")
    assert _git(b2.klon, "remote", "get-url", "origin") == str(neu)
    assert _git(b2.store, "remote", "get-url", "origin") == str(neu)
    assert _git(neu, "show", "HEAD:y.txt") == "2"
    # Das alte Remote bekam nichts mehr.
    assert subprocess.run(["git", "-C", str(klonwelt["remote"]), "show", "HEAD:y.txt"],
                          capture_output=True).returncode != 0


def test_spiegel_fehler_bricht_nichts(klonwelt, monkeypatch, capsys):
    b = bx.default_box()
    bx.lesestand_holen(b, sofort=True)
    monkeypatch.setattr(boxschreiber, "REMOTE", str(klonwelt["tmp"] / "gibt-es-nicht.git"))
    bx.registry_leeren()
    b2 = bx.default_box()
    assert bx.lesestand_holen(b2, sofort=True) is False
    assert b2.lese_stand["fehler"]
    # Gelesen wird der letzte Stand.
    assert babu_web.git_show("review/a.json") == b'{"x": 1}'
    assert "[lesespiegel]" in capsys.readouterr().out


def test_lesepfad_wartet_nicht_auf_laufenden_klon(klonwelt):
    b = bx.default_box()
    schloss = bx._spiegel_schloss(b.store)  # noqa: SLF001
    schloss.acquire()
    try:
        # Ein anderer Faden klont gerade — der Lesepfad liest, statt zu warten.
        b.lese_stand["geholt"] = 123.0
        assert bx.lesestand_holen(b, sofort=True, warten=False) is True
        assert not b.store.exists()
        # … und vermerkt, dass der nächste Leser nachziehen soll.
        assert b.lese_stand["geholt"] == 0.0
    finally:
        schloss.release()


def test_upload_wartet_nicht_auf_spiegel(klonwelt):
    """Nach dem Push wartet der Upload nicht auf einen laufenden Fetch."""
    b = bx.default_box()
    bx.lesestand_holen(b, sofort=True)
    schloss = bx._spiegel_schloss(b.store)  # noqa: SLF001
    schloss.acquire()
    try:
        t0 = time.monotonic()
        boxschreiber.schreiben(b, "z.txt", b"z", "zett", "nina")
        assert time.monotonic() - t0 < 5
    finally:
        schloss.release()
    # Der nächste Leser holt den eigenen Commit.
    babu_web.index_aktuell()
    assert babu_web.git_show("z.txt") == b"z"


def test_lesepfad_klont_nicht_im_request(klonwelt):
    b = bx.default_box()
    assert bx.lesestand_holen(b, warten=False, erstklon=False) is False
    for _ in range(100):             # der Erstklon läuft im Hintergrund
        if (b.store / "HEAD").is_file():
            break
        time.sleep(0.05)
    assert (b.store / "HEAD").is_file()


def test_haengender_dienst_haelt_lesen_nicht_auf(klonwelt, monkeypatch):
    """TCP-Blackhole: der Dienst nimmt an und antwortet nie."""
    import socket
    import threading
    b = bx.default_box()
    bx.lesestand_holen(b, sofort=True)
    babu_web.index_aktuell()
    loch = socket.socket()
    loch.bind(("127.0.0.1", 0))
    loch.listen(8)
    offen = []
    stop = threading.Event()

    def annehmen():
        loch.settimeout(0.2)
        while not stop.is_set():
            try:
                offen.append(loch.accept()[0])
            except OSError:
                pass
    threading.Thread(target=annehmen, daemon=True).start()
    try:
        monkeypatch.setattr(bx, "FETCH_FRIST", 2)
        monkeypatch.setattr(bx, "LESE_TTL", 0.0)
        monkeypatch.setattr(boxschreiber, "REMOTE",
                            f"http://127.0.0.1:{loch.getsockname()[1]}/git/babu/test-1/belege.git")
        bx.registry_leeren()
        b2 = bx.default_box()
        t0 = time.monotonic()
        idx = babu_web.index_aktuell()
        assert time.monotonic() - t0 < 6
        assert idx["head"]                      # alter Stand wird weiter gelesen
        assert babu_web.git_show("review/a.json") == b'{"x": 1}'
        assert "Frist" in b2.lese_stand["fehler"]
        # /healthz meldet den Spiegel mit (ohne Netz). Box-Klon gibt es hier
        # keinen (nie geschrieben) — der Status selbst ist hier nicht Thema.
        hz = babu_web.healthz()
        assert b'"spiegel":"Dienst antwortet nicht (Frist)"' in hz.body
        assert b'"stand":"ok"' not in hz.body
    finally:
        stop.set()
        for k in offen:
            k.close()
        loch.close()


def test_store_modus_bleibt_rueckweg(tmp_path, monkeypatch):
    monkeypatch.setenv("BABU_LESEN", "store")
    store = _server_repo(tmp_path, tmp_path / "alt.git", {"a.txt": "alt"})
    monkeypatch.setattr(babu_web, "STORE", store)
    bx.registry_leeren()
    b = bx.default_box()
    assert b.store == store
    assert bx.lesestand_holen(b, sofort=True) is True  # nichts zu tun
    bx.registry_leeren()


def test_mandanten_box_liest_aus_eigenem_spiegel(klonwelt, monkeypatch):
    tmp = klonwelt["tmp"]
    monkeypatch.setattr(boxschreiber, "GATEWAY", str(tmp / "dienst"))
    ref = "babu/salon-anna-3/belege"
    _server_repo(tmp, tmp / "dienst" / "git" / f"{ref}.git", {"README.md": "anna"})
    b = bx.box_aus_ref(3, ref)
    assert b.store == tmp / "lesen" / "babu" / "salon-anna-3" / "belege.git"
    assert b.remote == f"{tmp / 'dienst'}/git/{ref}.git"
    assert b.klon.parts[-3:] == ("babu", "salon-anna-3", "belege")
    assert bx.lesestand_holen(b, sofort=True)
    assert _git(b.store, "show", "HEAD:README.md") == "anna"


# ---------------------------------------------------------------------------
# 3. Box-Anlage per Push-to-create
# ---------------------------------------------------------------------------

@pytest.fixture()
def dienst(tmp_path, monkeypatch):
    """Ein „Dienst" auf der Platte: GATEWAY/git/<ref>.git.

    Echtes Push-to-create kann nur der Dienst; eine Datei-Gegenstelle braucht
    ein leeres Bare-Repo, das der Test vorher anlegt (so, wie der Dienst es
    bei der Push-Discovery tut). Der Lauf gegen den echten Dienst steht im
    E2E-Skript.
    """
    monkeypatch.setattr(boxschreiber, "GATEWAY", str(tmp_path / "dienst"))
    monkeypatch.setattr(boxschreiber, "PAT_PFAD", tmp_path / "kein-pat")

    def leer(ref: str) -> Path:
        ziel = tmp_path / "dienst" / "git" / f"{ref}.git"
        ziel.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(ziel)], check=True)
        return ziel
    return leer


def test_box_anlegen_schreibt_manifest(dienst):
    ziel = dienst("babu/salon-probe-4/belege")
    kurz = boxschreiber.box_anlegen("babu/salon-probe-4/belege", anzeige="Salon Probe")
    assert kurz and len(kurz) >= 7
    manifest = _git(ziel, "show", "HEAD:.0711/container.json")
    assert '"type": "babu"' in manifest and '"namespace": "salon-probe-4"' in manifest
    assert '"identifier": "belege"' in manifest and "Salon Probe" in manifest
    assert _git(ziel, "log", "-1", "--format=%an") == "babu-portal"


def test_box_anlegen_ist_idempotent(dienst):
    ziel = dienst("babu/zwei-5/belege")
    erst = boxschreiber.box_anlegen("babu/zwei-5/belege")
    kopf = _git(ziel, "rev-parse", "HEAD")
    zweit = boxschreiber.box_anlegen("babu/zwei-5/belege")
    assert _git(ziel, "rev-parse", "HEAD") == kopf
    assert erst[:7] == zweit[:7]


@pytest.mark.parametrize("ref", [
    "inspektor/ws-christoph0711.io/babu",   # alter Namensraum — nie mehr
    "babu/../belege", "babu/x/andere", "ctax/x/belege", "babu/X-Gross/belege", "",
])
def test_box_anlegen_nur_im_eigenen_namensraum(dienst, ref):
    with pytest.raises(boxschreiber.SchreibFehler):
        boxschreiber.box_anlegen(ref)


def test_box_da_meldet_fehlende_box(dienst):
    da, grund = boxschreiber.box_da("babu/fehlt-9/belege")
    assert da is False and grund


def test_box_da_leer_und_gefuellt(dienst):
    dienst("babu/leer-6/belege")
    assert boxschreiber.box_da("babu/leer-6/belege") == (True, "noch ohne Belege")
    boxschreiber.box_anlegen("babu/leer-6/belege")
    da, stand = boxschreiber.box_da("babu/leer-6/belege")
    assert da and len(stand) == 12


# ---------------------------------------------------------------------------
# 4. Token-Anmeldung über GET /v1/user
# ---------------------------------------------------------------------------

class _Antwort:
    def __init__(self, status: int, daten: dict | None = None):
        self.status_code = status
        self._daten = daten or {}

    def json(self):
        return self._daten


@pytest.fixture()
def anfragen(monkeypatch):
    gesehen: list[tuple[str, dict]] = []
    antworten: dict[str, _Antwort] = {}

    def get(url, headers=None, timeout=None):  # noqa: ARG001
        gesehen.append((url, headers or {}))
        tok = (headers or {}).get("Authorization", "")[7:]
        a = antworten.get(tok)
        if isinstance(a, Exception):
            raise a
        return a or _Antwort(401, {"error": "invalid_token"})

    monkeypatch.setattr(babu_web.requests, "get", get)
    monkeypatch.setattr(babu_web, "GITCHAIN_ID", "http://127.0.0.1:3361")
    babu_web._CACHE.clear()  # noqa: SLF001
    yield gesehen, antworten
    babu_web._CACHE.clear()  # noqa: SLF001


def test_wer_token_fragt_v1_user(anfragen):
    gesehen, antworten = anfragen
    antworten[TOKEN] = _Antwort(200, {"username": "Christoph0711.io", "scopes": ["read_repository"]})
    assert ECHTES_WER_TOKEN(TOKEN) == "christoph0711.io"
    url, kopf = gesehen[0]
    assert url == "http://127.0.0.1:3361/v1/user"
    assert kopf["Authorization"] == f"Bearer {TOKEN}"
    assert "/auth/whoami" not in url


def test_wer_token_cache(anfragen):
    gesehen, antworten = anfragen
    antworten[TOKEN] = _Antwort(200, {"username": "nina0711.io"})
    ECHTES_WER_TOKEN(TOKEN)
    ECHTES_WER_TOKEN(TOKEN)
    assert len(gesehen) == 1


@pytest.mark.parametrize("ident", [
    {"username": "svc-babu"},
    {"username": "babu-dienst", "art": "dienst"},
])
def test_dienstkonto_ist_kein_mensch(anfragen, ident):
    _, antworten = anfragen
    antworten[TOKEN] = _Antwort(200, ident)
    assert ECHTES_WER_TOKEN(TOKEN) is None


def test_falsches_token_401_ohne_absturz(anfragen):
    assert ECHTES_WER_TOKEN("gcpat-falsch0000000000000000") is None


def test_dienst_weg_ohne_absturz(anfragen, capsys):
    import requests
    _, antworten = anfragen
    antworten[TOKEN] = requests.ConnectionError("weg")
    assert ECHTES_WER_TOKEN(TOKEN) is None
    assert TOKEN not in capsys.readouterr().out


@pytest.mark.parametrize("wert", ["", "abc", "Bearer x", "test-pat"])
def test_nicht_gcpat_geht_nicht_ans_netz(anfragen, wert):
    gesehen, _ = anfragen
    assert ECHTES_WER_TOKEN(wert) is None
    assert gesehen == []


def test_anmelden_mit_zugangscode(anfragen, tmp_path, monkeypatch):
    """/api/anmelden: gültig → Sitzung, falsch → 401, Dienstkonto → 401."""
    from fastapi.testclient import TestClient
    _, antworten = anfragen
    monkeypatch.setattr(babu_web, "GEHEIMNIS_PFAD", tmp_path / ".geheimnis")
    monkeypatch.setattr(babu_web, "PORTAL_DB", tmp_path / "portal.db")
    monkeypatch.setattr(babu_web, "ERLAUBT", {"christoph0711.io"})
    monkeypatch.setattr(babu_web, "wer_token", ECHTES_WER_TOKEN)
    antworten[TOKEN] = _Antwort(200, {"username": "christoph0711.io"})
    dienst = "gcpat-dienst000000000000000000000"
    antworten[dienst] = _Antwort(200, {"username": "svc-babu"})
    c = TestClient(babu_web.app, base_url="https://testserver")
    r = c.post("/api/anmelden", json={"pat": TOKEN})
    assert r.status_code == 200 and r.json() == {"un": "christoph0711.io"}
    assert c.post("/api/anmelden", json={"pat": "gcpat-falsch00000000000000"}).status_code == 401
    assert c.post("/api/anmelden", json={"pat": dienst}).status_code == 401


# ---------------------------------------------------------------------------
# 5. betrieb_anlegen fragt im Modus `klon` den Dienst, nicht dessen Platte
# ---------------------------------------------------------------------------

def test_box_befund_fragt_den_dienst(dienst, monkeypatch):
    monkeypatch.setenv("BABU_LESEN", "klon")
    sys.path.insert(0, str(HIER.parent.parent.parent / "werkzeuge"))
    import betrieb_anlegen  # noqa: PLC0415
    fehlt = betrieb_anlegen.box_befund("babu/fehlt-11/belege")
    assert not fehlt.ok and fehlt.handarbeit and "--box-anlegen" in fehlt.grund
    dienst("babu/da-12/belege")
    boxschreiber.box_anlegen("babu/da-12/belege")
    da = betrieb_anlegen.box_befund("babu/da-12/belege")
    assert da.ok and "/git/babu/da-12/belege.git" in da.grund
