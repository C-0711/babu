"""Bankdateien ablegen und lesen — Routen und Index (B2, 04.10.2026)."""
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import box as bx  # noqa: E402
from test_acting_as import _login, welt2  # noqa: F401,E402
from test_bank_camt import CAMT  # noqa: E402

NINA_REF = "inspektor/ws-nina/babu"


@pytest.fixture(autouse=True)
def _boxen_schreibbar(monkeypatch):
    monkeypatch.setattr(bx, "remote_aus_ref", lambda ref: str(bx.store_aus_ref(ref)))


def _commits() -> int:
    r = subprocess.run(["git", "-C", str(bx.store_aus_ref(NINA_REF)), "rev-list",
                        "--count", "HEAD"], check=True, capture_output=True, text=True)
    return int(r.stdout)


def _hochladen(client, roh=CAMT, name="auszug.xml", headers=None, **form):
    return client.post("/api/bank/import", files={"datei": (name, roh, "application/xml")},
                       data=form, headers=headers or {})


def test_der_betrieb_legt_eine_camt_datei_ab(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    vorher = _commits()
    r = _hochladen(nina)
    assert r.status_code == 200, r.text
    assert (r.json()["neu"], r.json()["monate"]) == (3, ["2026-09"])
    assert _commits() == vorher + 1
    # Dieselbe Datei noch einmal: nichts Neues, kein Commit.
    r = _hochladen(nina)
    assert (r.json()["neu"], r.json()["doppelt"]) == (0, 3)
    assert _commits() == vorher + 1
    konten = nina.get("/api/bank/konten").json()["konten"]
    assert konten[0]["iban"] == "DE89 •••• 3000"
    assert konten[0]["saldo"] == {"betrag": 1234.56, "datum": "2026-09-30"}
    umsaetze = nina.get("/api/bank/umsaetze", params={"monat": "2026-09"}).json()["umsaetze"]
    assert [u["betrag"] for u in umsaetze] == [-9.9, 1250.0, -141.0]


def test_der_abgleich_sieht_die_importierten_umsaetze(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    _hochladen(nina)
    ab = nina.get("/api/abgleich/2026-09").json()
    assert ab["auszug_da"] is True
    assert [p["status"] for p in ab["positionen"]] == ["fehlt", "einnahme", "bank"]
    fragen = nina.get("/api/fehlende-belege").json()["fragen"]
    assert [f["betrag"] for f in fragen] == [141.0]


def test_die_kanzlei_legt_nichts_ab_liest_aber(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    _hochladen(nina)
    kanzlei = _login(welt2["bw"], welt2["kanzlei"])
    kopf = {"X-Mandant": str(welt2["nina_id"])}
    r = _hochladen(kanzlei, headers=kopf)
    assert r.status_code == 403 and r.json()["nur_lesen_bank"] is True
    r = kanzlei.get("/api/bank/umsaetze", params={"monat": "2026-09"}, headers=kopf)
    assert r.status_code == 200 and len(r.json()["umsaetze"]) == 3


def test_eine_unlesbare_datei_sagt_warum(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    r = _hochladen(nina, roh="Tag;Wert\n03.09.2026;-1,00\n".encode(), name="x.csv",
                   iban="DE89370400440532013000")
    assert r.status_code == 400
    assert r.json()["spalten"] == ["Tag", "Wert"]


# ————— B3: Belege ohne Zahlung, Bezahlt am, Cockpit —————

def _zwei_belege(welt) -> tuple[str, str]:
    """Zwei geprüfte Belege im September: 141 € (auf dem Konto) und 77 € (nicht)."""
    import json as _json  # noqa: PLC0415
    import boxschreiber  # noqa: PLC0415
    golden = _json.loads((HIER / "golden" / "review_weingaertle.json").read_text())
    dateien = {}
    staemme = []
    for stamm, lieferant, brutto, datum in (
            ("20260902-100000-bbb001-wagner", "Friseur Grosshandel Wagner", 141.0, "02.09.2026"),
            ("20260910-100000-bbb002-kao", "Kao Germany", 77.0, "10.09.2026")):
        review = {k: v for k, v in golden.items() if k not in ("audit", "buchungssatz")}
        review["datei"] = f"docs/2026-09/{stamm}.jpg"
        review["felder"] = dict(review["felder"], lieferant=lieferant, brutto=brutto,
                                datum=datum, offen=[], bewirtungssignal=False,
                                steuertabelle=[], zahlungsart="ueberweisung")
        review["einschaetzung"] = {"konto": "5100", "konto_skr04": "5100",
                                   "kontenrahmen": "SKR04", "steuerschluessel": "9"}
        dateien[f"docs/2026-09/{stamm}.jpg"] = b"\xff\xd8\xff\xe0x"
        dateien[f"review/{stamm}.json"] = _json.dumps(review, ensure_ascii=False).encode()
        staemme.append(stamm)
    boxschreiber.schreiben(bx.box_von(welt["nina"], welt["nina_id"]), dateien, None,
                           "aufnahme: zwei", welt["nina"])
    return staemme[0], staemme[1]


def test_belege_ohne_zahlung_und_bezahlt_am(welt2):
    wagner, kao = _zwei_belege(welt2)
    nina = _login(welt2["bw"], welt2["nina"])
    _hochladen(nina)
    kanzlei = _login(welt2["bw"], welt2["kanzlei"])
    kopf = {"X-Mandant": str(welt2["nina_id"])}
    d = kanzlei.get("/api/bank/abgleich/2026-09", headers=kopf).json()
    assert d["auszug_da"] is True
    assert [b["stamm"] for b in d["belege_ohne_zahlung"]] == [kao]
    assert d["zaehler"]["mit_beleg"] == 1 and d["zaehler"]["belege_ohne_zahlung"] == 1
    assert nina.get(f"/api/beleg/{wagner}").json()["bezahlt"]["datum"] == "03.09.2026"
    assert "bezahlt" not in nina.get(f"/api/beleg/{kao}").json()


def test_das_cockpit_zeigt_die_bankzahlen_des_monats(welt2):
    import json as _json  # noqa: PLC0415
    _zwei_belege(welt2)
    _hochladen(_login(welt2["bw"], welt2["nina"]))
    kanzlei = _login(welt2["bw"], welt2["kanzlei"])
    d = kanzlei.get(f"/api/kanzlei/mandanten/{welt2['nina_id']}/monate",
                    params={"anzahl": 3}).json()
    september = [m for m in _json.loads(_json.dumps(d)).get("monate", [])
                 if m.get("monat") == "2026-09"]
    assert september and september[0]["bank"]["umsaetze"] == 3
    assert september[0]["bank"]["belege_ohne_zahlung"] == 1
