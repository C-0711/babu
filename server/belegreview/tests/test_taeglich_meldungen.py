"""Schritt `meldungen` im täglichen Lauf (seit 10.10.2026, V2 „Ein Knopf" §8.3).

Was babu von sich aus sagt (melden.py), geht morgens an die Inhaberin:
als Push auf ihre Telefone, ohne Telefon als eine Mail — je Meldung genau
einmal, die Probe sendet nichts. Die Rechnung selbst ist `/api/meldungen`
(`babu_web.meldungen_fuer`) und dort geprüft; hier wird sie ersetzt.
"""
import importlib.util
import sys
from pathlib import Path

import babu_web  # noqa: E402
from test_kern_abo import (_abo, _ev, _melden, _rechnung, _sitzung,  # noqa: E402,F401
                           welt)

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

_spec = importlib.util.spec_from_file_location(
    "taeglich", HIER.parents[2] / "werkzeuge" / "taeglich.py")
taeglich = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(taeglich)

MELDUNG = {"schluessel": "frist:ustva:2026-10-10", "art": "frist",
           "titel": "Umsatzsteuer September", "text": "Fällig in 7 Tagen — am 10.10.",
           "am": "2026-10-03", "dringend": False}


def _mit_box(welt, monkeypatch, meldungen):
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("UPDATE mandant SET box_ref=?, status='aktiv' WHERE id=?",
                  ("babu/salon-sonne-1/belege", welt["mid"]))
    monkeypatch.setattr(taeglich, "_meldungen_fuer_betrieb", lambda m, heute: list(meldungen))


def test_ohne_telefon_eine_mail_je_tag(welt, monkeypatch):
    _mit_box(welt, monkeypatch, [MELDUNG, dict(MELDUNG, schluessel="rechnung:7",
                                               titel="Frau Holder hat noch nicht bezahlt")])
    assert taeglich.main(["--nur", "meldungen"]) == 0
    taeglich.main(["--nur", "meldungen"])
    treffer = [p for p in welt["post"] if p[0] == "sonne@salon.de"]
    assert treffer == [("sonne@salon.de", "babu: Umsatzsteuer September und mehr")]
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert c.execute("SELECT COUNT(*) FROM tageslauf WHERE aufgabe LIKE 'meldung:%'"
                         ).fetchone()[0] == 2


def test_mit_telefon_push_statt_mail(welt, monkeypatch):
    import kern_auslagen
    import push
    _mit_box(welt, monkeypatch, [MELDUNG])
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        c.execute("INSERT INTO push_geraet (token, un, umgebung, thema, angelegt_am, "
                  "zuletzt_am) VALUES ('abc', 'sonne@salon.de', 'produktion', "
                  "'io.0711.beleg', '2026-10-01', '2026-10-01')")
    monkeypatch.setattr(push, "eingerichtet", lambda: True)
    gesendet = []
    monkeypatch.setattr(push, "senden_an",
                        lambda geraete, titel, text, loeschen, klang="default": (
                            gesendet.append((len(geraete), titel)) or 1))
    taeglich.main(["--nur", "meldungen"])
    assert gesendet == [(1, "Umsatzsteuer September")]
    assert not [p for p in welt["post"] if p[0] == "sonne@salon.de"]
    assert kern_auslagen._geraete(["sonne@salon.de"])  # noqa: SLF001 — nichts gelöscht


def test_probe_sendet_nichts(welt, monkeypatch):
    _mit_box(welt, monkeypatch, [MELDUNG])
    taeglich.main(["--probe", "--nur", "meldungen"])
    assert not [p for p in welt["post"] if p[0] == "sonne@salon.de"]
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        assert c.execute("SELECT COUNT(*) FROM tageslauf").fetchone()[0] == 0


def test_betrieb_ohne_box_bleibt_still(welt, monkeypatch):
    monkeypatch.setattr(taeglich, "_meldungen_fuer_betrieb", lambda m, heute: [MELDUNG])
    taeglich.main(["--nur", "meldungen"])
    assert not [p for p in welt["post"] if p[0] == "sonne@salon.de"]


def test_standard_ablage_geht_an_die_eingetragenen_konten(welt, monkeypatch):
    _mit_box(welt, monkeypatch, [MELDUNG])
    with babu_web._DB_LOCK, babu_web._db() as c:  # noqa: SLF001
        import box
        c.execute("UPDATE mandant SET box_ref=? WHERE id=?", (box.default_box().ref, welt["mid"]))
    monkeypatch.setenv("BABU_STANDARD_KONTEN", "nina@salon.de")
    taeglich.main(["--nur", "meldungen"])
    assert [p[0] for p in welt["post"] if "Umsatzsteuer" in p[1]] == ["nina@salon.de"]
