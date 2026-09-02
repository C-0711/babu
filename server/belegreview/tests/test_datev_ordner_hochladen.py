"""Dateiauswahl, Themenzuordnung und PAT-Weg des DATEV-Import-Skripts.

Kein Netz: `requests` ist überall gemockt. Kein echter Keychain-Zugriff:
`subprocess.run` ist gemockt.
"""
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parents[2] / "werkzeuge" / "wissen-import"))

import datev_ordner_hochladen as di  # noqa: E402


@pytest.fixture()
def datev_ordner(tmp_path):
    ordner = tmp_path / "datev"
    (ordner / "hilfe-center").mkdir(parents=True)
    (ordner / "kontenrahmen_2026").mkdir()  # muss ignoriert werden

    (ordner / "SKR04_DATEV_Art-Nr_11175_2026.pdf").write_bytes(b"%PDF-1.4 fake")
    (ordner / "SKR04_Bau_und_Handwerk_2026.pdf").write_bytes(b"%PDF-1.4 fake")
    (ordner / "notiz.txt").write_text("keine PDF, wird ignoriert")

    (ordner / "hilfe-center" / "Dok-0907048_Steuerschluessel-Tabelle_2026.md").write_text("x")
    (ordner / "hilfe-center" / "Dok-0907108_Kontenrahmenaenderungen_2025-2026.md").write_text("x")
    (ordner / "hilfe-center" / "Dok-0907817_DATEV-Kontenrahmen-2026_PDF-Inventar.md").write_text("x")

    # Unterordner mit eigenen PDFs — darf NICHT rekursiv erfasst werden.
    (ordner / "kontenrahmen_2026" / "10136_HGB_SKR_04_McDonalds_2026.pdf").write_bytes(b"x")
    return ordner


# ── Dateiauswahl ───────────────────────────────────────────────────────────

def test_sammelt_nur_top_level_pdfs_und_hilfe_center_md(datev_ordner):
    dateien = di.dateien_sammeln(datev_ordner)
    namen = {p.name for p in dateien}
    assert namen == {
        "SKR04_DATEV_Art-Nr_11175_2026.pdf",
        "SKR04_Bau_und_Handwerk_2026.pdf",
        "Dok-0907048_Steuerschluessel-Tabelle_2026.md",
        "Dok-0907108_Kontenrahmenaenderungen_2025-2026.md",
        "Dok-0907817_DATEV-Kontenrahmen-2026_PDF-Inventar.md",
    }
    # Kein rekursiver Scan: das PDF im branchenspezifischen Unterordner fehlt.
    assert "10136_HGB_SKR_04_McDonalds_2026.pdf" not in namen
    assert "notiz.txt" not in namen


def test_leerer_ordner_liefert_leere_liste(tmp_path):
    assert di.dateien_sammeln(tmp_path) == []


# ── Themenzuordnung ────────────────────────────────────────────────────────

def test_bekannte_dateien_werden_fest_zugeordnet():
    assert di.thema_aus_dateiname("Dok-0907048_Steuerschluessel-Tabelle_2026.md") \
        == "steuerschluessel"
    assert di.thema_aus_dateiname("Dok-0907108_Kontenrahmenaenderungen_2025-2026.md") \
        == "kontenrahmen"
    assert di.thema_aus_dateiname("SKR04_Bau_und_Handwerk_2026.pdf") == "kontenrahmen"
    assert di.thema_aus_dateiname("SKR04_DATEV_Art-Nr_11175_2026.pdf") == "kontenrahmen"


def test_unbekannte_datei_bleibt_ohne_thema_fuer_die_server_erkennung():
    assert di.thema_aus_dateiname("Dok-0907817_DATEV-Kontenrahmen-2026_PDF-Inventar.md") is None
    assert di.thema_aus_dateiname("irgendwas.pdf") is None


def test_alle_bekannten_themen_sind_im_vertrag_der_route():
    for thema in di.BEKANNTE_DATEIEN.values():
        assert thema in di.THEMEN


# ── PAT: Umgebungsvariable vor Keychain, nie geloggt ───────────────────────

def test_pat_aus_umgebungsvariable_hat_vorrang(monkeypatch):
    monkeypatch.setenv("BABU_PAT", "geheim-123")

    def keychain_darf_nicht_laufen(*a, **kw):
        raise AssertionError("Keychain haette nicht aufgerufen werden duerfen")
    monkeypatch.setattr(di.subprocess, "run", keychain_darf_nicht_laufen)
    assert di.pat_holen() == "geheim-123"


def test_pat_faellt_auf_keychain_zurueck(monkeypatch):
    monkeypatch.delenv("BABU_PAT", raising=False)

    class R:
        returncode = 0
        stdout = "aus-der-keychain\n"
    aufrufe = []

    def fake_run(cmd, **kw):
        aufrufe.append(cmd)
        return R()
    monkeypatch.setattr(di.subprocess, "run", fake_run)
    ergebnis = di.pat_holen(service="babu-pat", account="nina")
    assert ergebnis == "aus-der-keychain"
    assert aufrufe[0][:2] == ["security", "find-generic-password"]
    assert "-w" in aufrufe[0]


def test_pat_ohne_treffer_ist_none(monkeypatch):
    monkeypatch.delenv("BABU_PAT", raising=False)

    class R:
        returncode = 44
        stdout = ""
    monkeypatch.setattr(di.subprocess, "run", lambda cmd, **kw: R())
    assert di.pat_holen(account="niemand") is None


# ── Upload — requests gemockt, kein Netz ───────────────────────────────────

class _FakeResponse:
    def __init__(self, daten):
        self._daten = daten

    def raise_for_status(self):
        pass

    def json(self):
        return self._daten


class _FakeSession:
    def __init__(self):
        self.aufrufe = []

    def post(self, url, **kwargs):
        self.aufrufe.append((url, kwargs))
        return _FakeResponse({"ok": True, "pfad": "wissen/kontenrahmen/x.pdf",
                              "thema": kwargs["params"].get("thema", "sonstiges")})


def test_hochladen_setzt_name_titel_thema_und_bearer_header(tmp_path):
    datei = tmp_path / "SKR04_Bau_und_Handwerk_2026.pdf"
    datei.write_bytes(b"%PDF-1.4 fake")
    session = _FakeSession()
    antwort = di.hochladen(datei, origin="https://babu.0711.io", pat="mein-pat",
                           session=session)
    assert antwort["ok"] is True
    url, kwargs = session.aufrufe[0]
    assert url == "https://babu.0711.io/api/wissen"
    assert kwargs["params"]["name"] == "SKR04_Bau_und_Handwerk_2026.pdf"
    assert kwargs["params"]["thema"] == "kontenrahmen"
    assert kwargs["headers"]["Authorization"] == "Bearer mein-pat"
    assert kwargs["data"] == b"%PDF-1.4 fake"


def test_hochladen_laesst_thema_weg_wenn_unbekannt(tmp_path):
    datei = tmp_path / "irgendwas.pdf"
    datei.write_bytes(b"x")
    session = _FakeSession()
    di.hochladen(datei, origin="https://babu.0711.io", pat="p", session=session)
    _, kwargs = session.aufrufe[0]
    assert "thema" not in kwargs["params"]


# ── main(): --probe braucht keinen PAT und laedt nichts hoch ───────────────

def test_probe_laedt_nichts_hoch_und_braucht_keinen_pat(datev_ordner, monkeypatch, capsys):
    monkeypatch.delenv("BABU_PAT", raising=False)

    def kein_netz(*a, **kw):
        raise AssertionError("Probe haette nichts posten duerfen")
    monkeypatch.setattr(di.requests, "post", kein_netz)
    monkeypatch.setattr(di, "pat_holen", lambda **kw: (_ for _ in ()).throw(
        AssertionError("Probe haette den PAT nicht anfassen duerfen")))

    code = di.main(["--ordner", str(datev_ordner), "--probe"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Probe, nichts hochgeladen" in out


def test_main_ohne_pat_bricht_sauber_ab(datev_ordner, monkeypatch, capsys):
    monkeypatch.delenv("BABU_PAT", raising=False)
    monkeypatch.setattr(di, "pat_holen", lambda **kw: None)
    code = di.main(["--ordner", str(datev_ordner)])
    assert code == 1
    out = capsys.readouterr().out
    assert "Kein PAT gefunden" in out
