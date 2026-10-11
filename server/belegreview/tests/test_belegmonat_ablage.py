"""Der Beleg liegt im Monat seines DATUMS — auch im Archiv (11.10.2026).

Gefunden beim Durchklicken der App vor der Wiedereinreichung: ein Beleg vom
5. August, am 11. Oktober fotografiert, landete unter `docs/2026-10/` und
hieß `beleg_0000-00-00_…`. Die Monatszahl der Buchhaltung stimmte zwar
(`_beleg_monat` zieht sie aus dem Belegdatum), aber der Ordner und der Name
im Archiv logen — und genau die gehen im Übergabepaket ans Steuerbüro.

Die Regel gab es im Haus längst: der Kontoauszug liegt seit jeher in SEINEM
Monat, nicht im Monat des Hochladens. Belege ziehen nach.
"""
import json
import os
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

from auslagen_hilfe import BUCHUNG, auslagen_welt  # noqa: F401,E402
from test_acting_as import _login, welt2  # noqa: F401,E402


def _aufnehmen(client, buchung):
    bild = b"\xff\xd8\xff\xe0" + os.urandom(12)   # jedes Foto anders: keine Dublette
    return client.post(
        "/api/aufnahme", params={"name": "bon.jpg"},
        files={"file": ("bon.jpg", bild, "image/jpeg")},
        data={"text": "Rossmann 23,40",
              "ergebnis": json.dumps({"buchung": buchung,
                                      "zeilen": ["Rossmann", "23,40"]})})


def test_beleg_liegt_im_monat_seines_datums(auslagen_welt):
    nina = _login(auslagen_welt["bw"], auslagen_welt["nina"])
    r = _aufnehmen(nina, dict(BUCHUNG, datum="2026-05-12"))
    assert r.status_code == 200, r.text
    assert r.json()["datei"].startswith("docs/2026-05/"), r.json()["datei"]


def test_ohne_gelesenes_datum_bleibt_der_hochlademonat(auslagen_welt):
    """Irgendwo muss der Beleg liegen — sonst fehlt er ganz."""
    import time  # noqa: PLC0415
    nina = _login(auslagen_welt["bw"], auslagen_welt["nina"])
    for datum in (None, "", "0000-00-00", "2026-13-01", "12.05.2026"):
        r = _aufnehmen(nina, dict(BUCHUNG, datum=datum))
        assert r.status_code == 200, r.text
        assert r.json()["datei"].startswith(f"docs/{time.strftime('%Y-%m')}/"), \
            f"{datum!r} → {r.json()['datei']}"


def test_die_buchhaltung_zaehlt_den_beleg_im_belegmonat(auslagen_welt):
    """Gegenprobe: Ordner und Monatszahl sagen dasselbe."""
    nina = _login(auslagen_welt["bw"], auslagen_welt["nina"])
    r = _aufnehmen(nina, dict(BUCHUNG, datum="2026-05-12"))
    stamm = r.json()["datei"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
    zeile = next(z for z in nina.get("/api/belege").json()["belege"]
                 if z["stamm"] == stamm)
    assert zeile["monat"] == "2026-05", zeile
