"""Bankdaten pflegt der Betrieb — die Kanzlei sieht sie nur an.

Auftraggeber-Entscheid 03.10.2026 (Plan Kanzleiansicht, Phase 0): Arbeitet
eine Kanzlei über `X-Mandant` in einem Betrieb, darf sie Kontoauszüge und
Zahlungen lesen, aber nichts daran ändern — kein Auszug hochladen oder
löschen, keine fehlende Zahlung „klären", keine Rechnung als bezahlt
übernehmen, keinen Auszug in der Ablage umbenennen oder verschieben.

Geprüft wird an beiden Enden: die Antwort ist 403 mit `nur_lesen_bank`, und
in der Box des Betriebs ist kein Commit dazugekommen. Ohne Kopf — der
Betrieb selbst — bleibt alles wie vorher.
"""
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import box as bx  # noqa: E402
import boxschreiber  # noqa: E402
from test_acting_as import _login, welt2  # noqa: F401,E402

NINA_REF = "inspektor/ws-nina/babu"
AUSZUG = "auszuege/2026-05/kontoauszug-mai.pdf"


@pytest.fixture(autouse=True)
def _boxen_schreibbar(monkeypatch):
    """Geschrieben wird sonst über das Gateway — hier direkt in die Stores."""
    monkeypatch.setattr(bx, "remote_aus_ref",
                        lambda ref: str(bx.store_aus_ref(ref)))


def _commits() -> int:
    r = subprocess.run(["git", "-C", str(bx.store_aus_ref(NINA_REF)),
                        "rev-list", "--count", "HEAD"],
                       check=True, capture_output=True, text=True)
    return int(r.stdout.strip())


def _auszug_ablegen(welt) -> None:
    """Ein Auszug in Ninas Box, so wie ihn ihr eigener Knopf ablegt."""
    box = bx.box_von(welt["nina"], welt["nina_id"])
    boxschreiber.schreiben(box, {AUSZUG: b"%PDF-1.4 auszug",
                                 AUSZUG + ".umsaetze.json": b'{"umsaetze": []}'},
                           None, "auszug: mai", welt["nina"])


def _als_kanzlei(welt):
    client = _login(welt["bw"], welt["kanzlei"])
    return client, {"X-Mandant": str(welt["nina_id"])}


def _gesperrt(r) -> None:
    assert r.status_code == 403, r.text
    assert r.json().get("nur_lesen_bank") is True
    assert "ansehen" in r.json()["fehler"]


# ————— Schreiben: gesperrt, und die Box bleibt, wie sie war —————

def test_kanzlei_kann_keinen_auszug_hochladen(welt2):
    client, kopf = _als_kanzlei(welt2)
    vorher = _commits()
    _gesperrt(client.post("/api/kontoauszug?name=auszug.pdf",
                          content=b"%PDF-1.4 x", headers=kopf))
    assert _commits() == vorher


def test_kanzlei_kann_keinen_auszug_loeschen(welt2):
    _auszug_ablegen(welt2)
    client, kopf = _als_kanzlei(welt2)
    vorher = _commits()
    _gesperrt(client.post("/api/auszug-loeschen", json={"pfad": AUSZUG},
                          headers=kopf))
    assert _commits() == vorher


def test_kanzlei_kann_keine_fehlende_zahlung_klaeren(welt2):
    client, kopf = _als_kanzlei(welt2)
    vorher = _commits()
    _gesperrt(client.post("/api/fehlende-belege/klaeren",
                          json={"schluessel": "0123456789abcdef", "grund": "privat"},
                          headers=kopf))
    assert _commits() == vorher


def test_kanzlei_kann_keine_zahlung_uebernehmen(welt2):
    client, kopf = _als_kanzlei(welt2)
    vorher = _commits()
    _gesperrt(client.post("/api/zahlungen/uebernehmen",
                          json={"nummer": "2026-0001", "am": "2026-05-03"},
                          headers=kopf))
    assert _commits() == vorher


def test_die_regel_deckt_auch_kuenftige_bankrouten():
    """`/api/bank/*` gibt es noch nicht — die Regel gilt trotzdem schon,
    damit eine neue Route nicht aus Versehen schreibbar startet."""
    import bankrecht  # noqa: PLC0415
    assert bankrecht.sperrt("POST", "/api/bank/import", als_kanzlei=True)
    assert not bankrecht.sperrt("GET", "/api/bank/umsaetze", als_kanzlei=True)
    assert not bankrecht.sperrt("POST", "/api/bank/import", als_kanzlei=False)
    assert not bankrecht.sperrt("POST", "/api/kundinnen", als_kanzlei=True)
    # Nur ganze Pfadteile: „/api/bankett" ist keine Bankroute.
    assert not bankrecht.sperrt("POST", "/api/bankett", als_kanzlei=True)


def test_kanzlei_kann_einen_auszug_nicht_ueber_die_aufnahme_ablegen(welt2):
    """Der zweite Weg ins Auszugsfach: ein PDF, das „Auszug" im Namen trägt."""
    client, kopf = _als_kanzlei(welt2)
    vorher = _commits()
    _gesperrt(client.post("/api/aufnahme?name=kontoauszug-mai.pdf",
                          content=b"%PDF-1.4 kein echter auszug", headers=kopf))
    assert _commits() == vorher


def test_kanzlei_kann_einen_auszug_in_der_ablage_nicht_umbenennen(welt2):
    _auszug_ablegen(welt2)
    client, kopf = _als_kanzlei(welt2)
    vorher = _commits()
    _gesperrt(client.post("/api/ablage/umbenennen",
                          json={"pfad": AUSZUG, "titel": "Mai"}, headers=kopf))
    _gesperrt(client.post("/api/ablage/verschieben",
                          json={"pfad": AUSZUG, "art": "vertrag"}, headers=kopf))
    assert _commits() == vorher


# ————— Lesen: weiter erlaubt —————

def test_kanzlei_sieht_abgleich_und_zahlungen(welt2):
    _auszug_ablegen(welt2)
    client, kopf = _als_kanzlei(welt2)
    for pfad in ("/api/abgleich/2026-05", "/api/fehlende-belege",
                 "/api/zahlungen"):
        r = client.get(pfad, headers=kopf)
        assert r.status_code == 200, (pfad, r.text)


# ————— Der Betrieb selbst: unverändert —————

def test_der_betrieb_klaert_weiter_selbst(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    vorher = _commits()
    r = nina.post("/api/fehlende-belege/klaeren",
                  json={"schluessel": "0123456789abcdef", "grund": "privat"})
    assert r.status_code == 200, r.text
    assert _commits() == vorher + 1


def test_der_betrieb_benennt_seinen_auszug_weiter_um(welt2):
    _auszug_ablegen(welt2)
    nina = _login(welt2["bw"], welt2["nina"])
    r = nina.post("/api/ablage/umbenennen", json={"pfad": AUSZUG, "titel": "Mai"})
    assert r.status_code == 200, r.text


def test_andere_schreibwege_der_kanzlei_bleiben_offen(welt2):
    """Die Sperre gilt nur der Bank — Belege und Kundinnen pflegt die
    Kanzlei weiter mit."""
    client, kopf = _als_kanzlei(welt2)
    r = client.post("/api/kundinnen", json={"name": "Frau Meier"}, headers=kopf)
    assert r.status_code == 200, r.text
