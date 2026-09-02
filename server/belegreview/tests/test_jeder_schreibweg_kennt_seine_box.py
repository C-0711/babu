"""Jeder Schreibweg muss sagen, in WELCHE Box er schreibt.

`boxschreiber.schreiben()` nimmt seit Plan 21 die Box als erstes Argument.
Weil bis Phase 3 eine Übergangsschale fehlende Boxen durch die Default-Box
ersetzt (damit die vorhandenen Tests unverändert bleiben konnten), fiele
eine vergessene Aufrufstelle nicht auf — sie schriebe still in die falsche
Box, sobald es eine zweite gibt. Das ist die schlechteste aller Fehlerarten:
sie meldet sich nicht, und der Beleg landet beim falschen Salon.

Deshalb ein Wächter über den Quelltext, in der Tradition von
`test_kein_schloss_im_schloss.py`. Er kennt beide Formen, in denen der
Schreibweg gerufen wird: direkt und über `run_in_threadpool`.
"""
import ast
from pathlib import Path

QUELLE = Path(__file__).resolve().parent.parent / "babu_web.py"
BAUM = ast.parse(QUELLE.read_text())

SCHREIBWEGE = ("schreiben", "loeschen")


def _ist_schreibweg(knoten) -> bool:
    return (isinstance(knoten, ast.Attribute) and knoten.attr in SCHREIBWEGE
            and isinstance(knoten.value, ast.Name)
            and knoten.value.id == "boxschreiber")


def _ist_box_ruf(knoten) -> bool:
    return (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Name)
            and knoten.func.id == "_box")


def _aufrufstellen() -> tuple[int, list[str]]:
    mit, ohne = 0, []
    for k in ast.walk(BAUM):
        if not isinstance(k, ast.Call):
            continue
        if _ist_schreibweg(k.func):
            erstes = k.args[0] if k.args else None
        elif (isinstance(k.func, ast.Name) and k.func.id == "run_in_threadpool"
              and k.args and _ist_schreibweg(k.args[0])):
            erstes = k.args[1] if len(k.args) > 1 else None
        else:
            continue
        if _ist_box_ruf(erstes):
            mit += 1
        else:
            ohne.append(f"  babu_web.py:{k.lineno}")
    return mit, ohne


def test_jeder_aufruf_gibt_eine_box_mit():
    mit, ohne = _aufrufstellen()
    assert not ohne, ("Schreibweg ohne Box — landet still in der Default-Box:\n"
                      + "\n".join(ohne))
    assert mit > 30, f"nur {mit} Aufrufstellen gefunden — sucht der Wächter noch?"


def test_der_waechter_wuerde_eine_luecke_sehen():
    """Gegenprobe: ein Wächter, der nie etwas findet, ist keiner."""
    luecke = ast.parse("boxschreiber.schreiben('docs/x.txt', b'x', 'm', 'n')")
    treffer = [k for k in ast.walk(luecke)
               if isinstance(k, ast.Call) and _ist_schreibweg(k.func)
               and not _ist_box_ruf(k.args[0] if k.args else None)]
    assert len(treffer) == 1
