"""Gemma-Grenzen, gemessen am 04.09.2026: Token-Limit, Abbruchgrund,
JSON-Zaun, Bild-Ausschnitte. Alles ohne Netz."""
import io
import json

import pytest


def _antwort(inhalt, finish="stop"):
    return io.BytesIO(json.dumps({"choices": [{"finish_reason": finish,
                                               "message": {"content": inhalt}}]}).encode())


def test_json_aus_nimmt_zaun_und_freitext():
    import gemma_buchung as gb
    assert gb.json_aus('```json\n{"status": "gebucht"}\n```') == {"status": "gebucht"}
    assert gb.json_aus('Hier: {"a": 1} fertig.') == {"a": 1}
    assert gb.json_aus("kein json") == {}
    assert gb.json_aus("") == {}
    assert gb.json_aus("[1, 2]") == {}


def test_gemma_schickt_json_modus_und_genug_token(monkeypatch):
    import gemma_buchung as gb
    gesehen = {}

    def urlopen(req, timeout=None):
        gesehen.update(json.loads(req.data))
        return _antwort('{"status": "gebucht"}')
    monkeypatch.setattr(gb.urllib.request, "urlopen", urlopen)
    assert gb._gemma("Bon", None, "System") == {"status": "gebucht"}
    assert gesehen["response_format"] == {"type": "json_object"}
    # 20 Positionen brauchen ~1.500 Token; 1.200 kappten mitten im JSON.
    assert gesehen["max_tokens"] >= 2500


def test_abgeschnittene_antwort_wird_zur_klaren_rueckfrage(monkeypatch):
    """finish_reason "length" ist kein Verständnisproblem — und darf nicht
    als „worum geht es?" beim Telefon ankommen."""
    import gemma_buchung as gb
    monkeypatch.setattr(gb.urllib.request, "urlopen",
                        lambda req, timeout=None: _antwort('{"status": "gebucht", "kat', "length"))
    roh = gb._gemma("Bon", None, "System")
    assert roh == {"status": "abgeschnitten"}
    e = gb.buchung_pruefen(roh)
    assert e["status"] == "fragen"
    assert "sehr lang" in e["fragen"][0]["frage"]


def test_leerer_inhalt_faellt_nicht_um(monkeypatch):
    import gemma_buchung as gb
    monkeypatch.setattr(gb.urllib.request, "urlopen",
                        lambda req, timeout=None: _antwort(None))
    assert gb._gemma("Bon") == {}


def _png(breite, hoehe):
    from PIL import Image
    im = Image.new("RGB", (breite, hoehe), (250, 250, 250))
    puffer = io.BytesIO(); im.save(puffer, "PNG"); return puffer.getvalue()


def _jpg(breite, hoehe):
    from PIL import Image
    im = Image.new("RGB", (breite, hoehe), (250, 250, 250))
    puffer = io.BytesIO(); im.save(puffer, "JPEG"); return puffer.getvalue()


def test_langer_bon_geht_ganz_und_in_streifen():
    from PIL import Image
    import gemma_buchung as gb
    teile = gb.bild_kacheln(_png(200, 900), "image/png")
    n = gb.BILD_KACHELN_MAX
    assert 2 <= n <= 3, "vLLM erlaubt 4 Bilder; 4 hat den Dienst am 04.09. umgeworfen"
    assert len(teile) == 1 + n
    assert all(m == "image/jpeg" for _, m in teile)
    hoehen = [Image.open(io.BytesIO(d)).size[1] for d, _ in teile]
    assert hoehen[0] == 900
    assert all(900 / n < h < 900 / n * 1.2 for h in hoehen[1:]), hoehen


def test_ausschnitte_lassen_sich_abschalten(monkeypatch):
    import gemma_buchung as gb
    monkeypatch.setattr(gb, "BILD_KACHELN_MAX", 0)
    roh = _png(200, 900)
    teile = gb.bild_kacheln(roh, "image/png")
    assert len(teile) == 1 and teile[0][1] == "image/jpeg"


def test_ein_querformat_bleibt_ein_bild():
    import gemma_buchung as gb
    roh = _jpg(600, 400)
    assert gb.bild_kacheln(roh, "image/jpeg") == [(roh, "image/jpeg")]


def test_unlesbare_bytes_gehen_unveraendert_durch():
    import gemma_buchung as gb
    assert gb.bild_kacheln(b"kein bild", "image/heic") == [(b"kein bild", "image/heic")]


def test_gemma_reicht_alle_ausschnitte_vor_dem_text(monkeypatch):
    import gemma_buchung as gb
    gesehen = {}

    def urlopen(req, timeout=None):
        gesehen.update(json.loads(req.data)); return _antwort("{}")
    monkeypatch.setattr(gb.urllib.request, "urlopen", urlopen)
    gb._gemma("Bon", (_png(200, 900), "image/png"), "System")
    inhalt = gesehen["messages"][1]["content"]
    assert [t["type"] for t in inhalt] == ["image_url"] * (1 + gb.BILD_KACHELN_MAX) + ["text"]
    assert len(inhalt) - 1 <= 3, "nie 4 Bilder — siehe BILD_KACHELN_MAX"
    assert all(t["image_url"]["url"].startswith("data:image/jpeg;base64,")
               for t in inhalt[:-1])


def test_llm_json_meldet_abgeschnittene_antwort(monkeypatch):
    import abschluss_lesen as al
    import requests

    class Antwort:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"finish_reason": "length",
                                 "message": {"content": '{"art": "eu'}}]}
    gesehen = {}
    monkeypatch.setattr(requests, "post", lambda url, timeout=None, json=None: gesehen.update(json) or Antwort())
    with pytest.raises(ValueError, match="Token-Grenze"):
        al.llm_json([{"role": "user", "content": "x"}])
    assert gesehen["response_format"] == {"type": "json_object"}
    assert gesehen["max_tokens"] >= 2500


def test_llm_json_nimmt_zaun(monkeypatch):
    import abschluss_lesen as al
    import requests

    class Antwort:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"finish_reason": "stop",
                                 "message": {"content": '```json\n{"art": "euer"}\n```'}}]}
    monkeypatch.setattr(requests, "post", lambda *a, **k: Antwort())
    assert al.llm_json([{"role": "user", "content": "x"}]) == {"art": "euer"}


def test_die_bremse_hat_mehr_als_einen_platz():
    import babu_web as bw
    n = 0
    while bw._LLM_SEMAPHORE.acquire(blocking=False):
        n += 1
    for _ in range(n):
        bw._LLM_SEMAPHORE.release()
    assert 2 <= n <= 8, n
