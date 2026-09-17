"""Ein Server, zwei Namen: babu.0711.io und mybabu.io (seit 17.09.2026).

Am 17.09. kam jeder Formular-POST unter mybabu.io als „nicht erlaubt"
zurück — Warteliste, Login, Passwort vergessen —, weil die Herkunftsprüfung
nur den einen konfigurierten Namen kannte. Die Prüfung fragt jetzt das,
worum es beim CSRF-Schutz geht: passt der Origin zum Host, unter dem die
Seite geladen wurde? Dann ist es dieselbe Seite, egal wie sie heißt.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import babu_web  # noqa: E402


class _Anfrage:
    def __init__(self, **kopf):
        self.headers = {k.replace("_", "-"): v for k, v in kopf.items()}


def test_der_konfigurierte_name_gilt_weiter(monkeypatch):
    monkeypatch.setattr(babu_web, "PORTAL_ORIGIN", "https://babu.0711.io")
    assert babu_web._origin_ok(_Anfrage(origin="https://babu.0711.io", host="babu.0711.io"))  # noqa: SLF001
    assert babu_web._origin_ok(_Anfrage())  # ohne Origin: kein Browser-Formular  # noqa: SLF001


def test_ein_zweiter_name_gilt_wenn_origin_und_host_zusammenpassen(monkeypatch):
    monkeypatch.setattr(babu_web, "PORTAL_ORIGIN", "https://babu.0711.io")
    assert babu_web._origin_ok(_Anfrage(origin="https://mybabu.io", host="mybabu.io"))  # noqa: SLF001
    assert babu_web._origin_ok(_Anfrage(origin="https://www.mybabu.io", host="www.mybabu.io"))  # noqa: SLF001
    # Hinter einem Proxy zählt der weitergereichte Host.
    assert babu_web._origin_ok(_Anfrage(origin="https://mybabu.io", host="127.0.0.1:7844",  # noqa: SLF001
                                        x_forwarded_host="mybabu.io"))


def test_eine_fremde_seite_bleibt_draussen(monkeypatch):
    monkeypatch.setattr(babu_web, "PORTAL_ORIGIN", "https://babu.0711.io")
    # Cross-Site: der Browser schickt den Origin der fremden Seite, der Host
    # ist unserer — das passt nicht zusammen.
    assert not babu_web._origin_ok(_Anfrage(origin="https://boese.example", host="mybabu.io"))  # noqa: SLF001
    assert not babu_web._origin_ok(_Anfrage(origin="https://boese.example", host="babu.0711.io"))  # noqa: SLF001
    # Ein Origin, der dem Host nur ähnelt, reicht nicht.
    assert not babu_web._origin_ok(_Anfrage(origin="https://mybabu.io.boese.example", host="mybabu.io"))  # noqa: SLF001


def test_die_zusatzliste_aus_der_umgebung(monkeypatch):
    monkeypatch.setattr(babu_web, "PORTAL_ORIGIN", "https://babu.0711.io")
    monkeypatch.setattr(babu_web, "WEITERE_ORIGINS", ["https://alt.example", " https://zwei.example/ "])
    assert babu_web._origin_ok(_Anfrage(origin="https://zwei.example", host="irgendwas"))  # noqa: SLF001
