"""Jede Gemma-Adresse steht in compose.yml — und alle sind dieselbe.

Anlass 22.11.2026: Der k3s-Pod `gemma4-mm` auf :11435 fiel ab dem 04.11.
immer wieder aus und lief seit dem 19.11. abends gar nicht mehr. babu fragte
weiter dort, weil die Adresse nur als Voreinstellung
im Code stand und compose.yml nichts setzte — gebucht wurde nichts.
`/healthz` prüft nur GEMMA_API. Stünde VLM_API (die Buchung) oder
BABU_LLM_API (Scan-Blätter) noch auf einer anderen Adresse, wäre die Ampel
grün und die Buchung trotzdem tot.

Darum: jede Variable, über die ein Modul eine chat/completions-Adresse liest,
ist beim Dienst babu-web in compose.yml gesetzt, und alle zeigen auf dieselbe.
Kommt eine vierte dazu, schlägt dieser Test an, bis sie dort auch steht.
"""
import re
from pathlib import Path

HIER = Path(__file__).resolve().parent.parent          # server/belegreview
COMPOSE = HIER.parent / "docker" / "compose.yml"

_ADRESSE = re.compile(
    r'os\.environ\.get\(\s*"([A-Z_][A-Z0-9_]*)"\s*,\s*"(https?://[^"]*/chat/completions)"')


def _adress_variablen() -> dict[str, str]:
    """{Variable: Voreinstellung im Code} über alle Module von belegreview."""
    gefunden: dict[str, str] = {}
    for datei in sorted(HIER.glob("*.py")):
        for name, vorgabe in _ADRESSE.findall(datei.read_text(encoding="utf-8")):
            gefunden[name] = vorgabe
    return gefunden


def _babu_web_umgebung() -> dict[str, str]:
    """environment des Dienstes babu-web, ohne YAML-Bibliothek gelesen."""
    text = COMPOSE.read_text(encoding="utf-8")
    m = re.search(r"^  babu-web:\n(.*?)(?=^ {0,2}[a-z][\w-]*:|\Z)", text, re.M | re.S)
    assert m, "Dienst babu-web nicht in compose.yml gefunden"
    return dict(re.findall(r'^ {6}([A-Z_][A-Z0-9_]*):\s*"([^"]*)"', m.group(1), re.M))


def test_suche_findet_die_bekannten_adressen():
    # Gegenprobe zum Muster: findet es nichts, wären die anderen Tests leer wahr.
    assert {"GEMMA_API", "VLM_API", "BABU_LLM_API"} <= set(_adress_variablen())


def test_umgebung_wird_gelesen():
    # Gegenprobe zum Lesen von compose.yml: bekannte Zeilen müssen auftauchen.
    umgebung = _babu_web_umgebung()
    assert umgebung.get("BABU_GATEWAY") == "http://127.0.0.1:3361"
    assert "BABU_POSTEINGANG_PAT" not in umgebung      # gehört dem Posteingang


def test_jede_adresse_ist_in_compose_gesetzt():
    umgebung = _babu_web_umgebung()
    fehlt = sorted(set(_adress_variablen()) - set(umgebung))
    assert not fehlt, f"in compose.yml (babu-web) nicht gesetzt: {fehlt}"


def test_alle_adressen_sind_dieselbe():
    umgebung = _babu_web_umgebung()
    werte = {name: umgebung.get(name) for name in _adress_variablen()}
    assert len(set(werte.values())) == 1, f"verschiedene Gemma-Adressen: {werte}"
    (adresse,) = set(werte.values())
    assert adresse.endswith("/v1/chat/completions")
