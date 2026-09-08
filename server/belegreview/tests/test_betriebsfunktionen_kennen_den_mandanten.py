"""Wer einen Betrieb erwartet, bekommt den AKTIVEN Betrieb — nicht das Konto.

`test_salon_von_aktiv_ueberall.py` bewacht, dass `salon_von` nicht mehr roh
in Routen steht. Das genügt nicht: eine Route kann `salon_von` sauber
meiden und trotzdem ihr rohes `un` an eine Funktion weiterreichen, die den
Betrieb meint. Genau das war am 08.09.2026 an zwei Stellen der Fall —
`api_monatsabschluss` und `api_bwa_erstellen` rechneten
`team_personalkosten(un)`. Arbeitet eine Kanzlei als Mandant, sind das die
Löhne der KANZLEI in der BWA des Mandanten. Sichtbar wird das erst, wenn
die Kanzlei ein eigenes Team pflegt — bis dahin liefert die Funktion None
und der Fallback verdeckt den Fehler.

Dieselbe Fehlerart wie dort: sie meldet sich nicht.

Bewacht werden Funktionen, deren erstes Argument der BETRIEB ist (nicht das
angemeldete Konto). Innerhalb einer Route muss dort `salon_von_aktiv(...)`
stehen oder eine Variable, die daraus stammt.
"""
import ast
from pathlib import Path

QUELLE = Path(__file__).resolve().parent.parent / "babu_web.py"
BAUM = ast.parse(QUELLE.read_text(encoding="utf-8"))

# Erstes Argument ist IMMER der Betrieb — es gibt keinen sinnvollen Aufruf
# mit einem fremden Konto.
BETRIEBSFUNKTIONEN = {
    "team_liste", "team_personalkosten",         # Personal des Betriebs
    "_logo_pfad", "_foto_pfad", "_stueck_pfad",  # Dateien des Betriebs
}
# `db_einstellungen` steht BEWUSST nicht hier. Es nimmt auch legitim etwas
# anderes als den aktiven Betrieb: ein fremdes Konto in der Verwaltungsliste,
# ein Konto aus einem Einladungslink ohne Anmeldung, eines aus einer
# WhatsApp-Nummer, oder dieselbe Zeile, in die gleich zurückgeschrieben wird.
# Alle sieben solchen Stellen tragen im Code ihre Begründung („Roh und
# absichtlich"). Ein Wächter, der auf sie anschlägt, verdirbt das Vertrauen
# in die übrigen Funde — siehe die 44 Fehlalarme der „kistsatz"-Prüfung.
# Was einen aufgelösten Betrieb liefert.
AUFGELOEST = {"salon_von_aktiv", "_box_besitzer"}


def _routen() -> list:
    """Jede Funktion mit @app.get/@app.post/… — dort kommt `un` vom Wächter."""
    aus = []
    for k in ast.walk(BAUM):
        if not isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in k.decorator_list:
            ziel = d.func if isinstance(d, ast.Call) else d
            if isinstance(ziel, ast.Attribute) and isinstance(ziel.value, ast.Name) \
                    and ziel.value.id == "app":
                aus.append(k)
                break
    return aus


def _herkunft(f) -> dict:
    """Variable -> Funktion, aus der sie stammt (auch aus `a, b = f(...)`)."""
    q = {}
    for k in ast.walk(f):
        if not isinstance(k, ast.Assign) or not isinstance(k.value, ast.Call):
            continue
        if not isinstance(k.value.func, ast.Name):
            continue
        ziel = k.targets[0]
        if isinstance(ziel, ast.Name):
            q[ziel.id] = k.value.func.id
        elif isinstance(ziel, ast.Tuple) and ziel.elts and isinstance(ziel.elts[0], ast.Name):
            q[ziel.elts[0].id] = k.value.func.id
    return q


def _verstoesse() -> list[str]:
    aus = []
    for f in _routen():
        q = _herkunft(f)
        for k in ast.walk(f):
            if not (isinstance(k, ast.Call) and isinstance(k.func, ast.Name)
                    and k.func.id in BETRIEBSFUNKTIONEN and k.args):
                continue
            a = k.args[0]
            if isinstance(a, ast.Call) and isinstance(a.func, ast.Name) \
                    and a.func.id in AUFGELOEST:
                continue
            if isinstance(a, ast.Name) and q.get(a.id) in AUFGELOEST:
                continue
            gezeigt = a.id if isinstance(a, ast.Name) else ast.dump(a)[:40]
            aus.append(f"{QUELLE.name}:{k.lineno} {f.name}: "
                       f"{k.func.id}({gezeigt}) — nicht über salon_von_aktiv")
    return aus


def test_jede_route_reicht_den_aktiven_betrieb_weiter():
    verstoesse = _verstoesse()
    assert not verstoesse, "\n".join(verstoesse)


def test_die_bewachten_funktionen_gibt_es_wirklich():
    """Ein Wächter über Namen, die es nicht mehr gibt, bewacht nichts."""
    namen = {k.name for k in ast.walk(BAUM)
             if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))}
    fehlen = sorted(BETRIEBSFUNKTIONEN - namen)
    assert not fehlen, f"bewacht, existiert aber nicht: {fehlen}"
    assert "salon_von_aktiv" in namen


def test_der_waechter_wuerde_eine_luecke_sehen():
    """Die Gegenprobe: der Wächter am 08.09.2026 gegen den Stand VOR dem Fix."""
    baum = ast.parse(
        "app = X()\n"
        "@app.get('/x')\n"
        "def route(request):\n"
        "    un, fehler = _box_wache(request)\n"
        "    return team_personalkosten(un)\n")
    global BAUM
    echt, BAUM = BAUM, baum
    try:
        assert len(_verstoesse()) == 1
    finally:
        BAUM = echt
