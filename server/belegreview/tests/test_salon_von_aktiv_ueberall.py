"""Keine Route darf `salon_von` roh benutzen.

`salon_von(un)` kennt nur die Team-Zugehörigkeit, nicht den Mandanten, für
den ein Request gerade arbeitet. In einer Route stehengeblieben zeigte sie
der Kanzlei beim Acting-as ihre EIGENEN — leeren — Zahlen, während daneben
die Belege des Mandanten stehen. Halb fremde, halb eigene Daten in einer
Ansicht, und keiner Zahl sähe man an, welche von beiden sie ist. Das ist
die schlechteste Fehlerart: sie meldet sich nicht.

Der Plan benennt das ausdrücklich als das größte Risiko der Phase 3
(„60 Aufrufstellen … Gegenmaßnahme: Lint/Grep-Check"). Also ein Wächter
über den Quelltext, in der Tradition von
`test_jeder_schreibweg_kennt_seine_box.py`.

Erlaubt bleibt `salon_von` in genau drei Funktionen — jede mit einem Grund,
der nicht „historisch gewachsen" lautet:

* `salon_von_aktiv`   — der Rückfall, wenn keine Mandanten-Box aktiv ist.
* `box_mitglied`      — entscheidet, WELCHE Box gilt; müsste sich sonst
                        selbst aufrufen.
* `_betrieb_von`      — urteilt über FREMDE Zugänge („wem gehört dieses
                        Konto?"); der aktive Mandant wäre dort die falsche
                        Antwort für jeden von ihnen.
"""
import ast
from pathlib import Path

QUELLE = Path(__file__).resolve().parent.parent / "babu_web.py"
BAUM = ast.parse(QUELLE.read_text())

ERLAUBT = {"salon_von_aktiv", "box_mitglied", "_betrieb_von"}


def _rufe_gesamt(name: str) -> list[int]:
    return sorted({k.lineno for k in ast.walk(BAUM)
                   if isinstance(k, ast.Call) and isinstance(k.func, ast.Name)
                   and k.func.id == name})


def _erlaubte_zeilen(name: str) -> set[int]:
    zeilen: set[int] = set()
    for funktion in ast.walk(BAUM):
        if isinstance(funktion, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and funktion.name in ERLAUBT:
            zeilen |= {k.lineno for k in ast.walk(funktion)
                       if isinstance(k, ast.Call)
                       and isinstance(k.func, ast.Name) and k.func.id == name}
    return zeilen


def test_salon_von_steht_nur_noch_in_den_drei_ausnahmen():
    offen = set(_rufe_gesamt("salon_von")) - _erlaubte_zeilen("salon_von")
    assert not offen, (
        "roher salon_von-Aufruf außerhalb von " + ", ".join(sorted(ERLAUBT))
        + ":\n" + "\n".join(f"  babu_web.py:{z}" for z in sorted(offen)))


def test_die_umstellung_hat_wirklich_stattgefunden():
    """Ein Wächter, der über einer leeren Datei wacht, ist keiner."""
    assert len(_rufe_gesamt("salon_von_aktiv")) > 50, \
        "zu wenige salon_von_aktiv-Aufrufe — ist die Umstellung noch da?"


def test_die_drei_ausnahmen_gibt_es_auch_wirklich():
    """Ein Name in der Ausnahmeliste, den es nicht gibt, wäre ein Loch:
    er entschuldigte nichts und fiele trotzdem nie auf."""
    namen = {f.name for f in ast.walk(BAUM)
             if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert ERLAUBT <= namen


def test_der_waechter_wuerde_eine_luecke_sehen():
    """Gegenprobe am eigenen Werkzeug, nicht am Ergebnis."""
    baum = ast.parse("def api_irgendwas(un):\n    return salon_von(un)\n")
    treffer = [k.lineno for k in ast.walk(baum)
               if isinstance(k, ast.Call) and isinstance(k.func, ast.Name)
               and k.func.id == "salon_von"]
    assert len(treffer) == 1
