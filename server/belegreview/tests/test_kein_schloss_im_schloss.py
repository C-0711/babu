"""_DB_LOCK ist ein einfaches Schloss — zweimal zusperren hängt für immer.

Beim Bauen der Kundenkartei stand `salon_von(un)` als Argument mitten in
einem `with _DB_LOCK`-Block. `salon_von` geht über `nutzer_holen` selbst an
die Datenbank und nimmt dafür dasselbe Schloss: der Aufruf kam nie zurück.
Kein Fehler, kein Log, nur ein Request, der ewig hängt — die schlechteste
aller Fehlerarten, weil nichts davon irgendwo auftaucht.

Deshalb ein Wächter über den Quelltext. Er muss über die Aufrufkette gehen,
nicht nur eine Ebene tief: die erste Fassung dieses Tests sah nur
`nutzer_holen` und ließ genau den Fehler durch, den sie verhindern sollte.
"""
import ast
from pathlib import Path

QUELLE = Path(__file__).resolve().parent.parent / "babu_web.py"
BAUM = ast.parse(QUELLE.read_text())


def _funktionen() -> dict[str, ast.AST]:
    return {k.name: k for k in ast.walk(BAUM)
            if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _gerufene(knoten) -> set[str]:
    return {a.func.id for a in ast.walk(knoten)
            if isinstance(a, ast.Call) and isinstance(a.func, ast.Name)}


def schlossnehmer() -> set[str]:
    """Alle Funktionen, die das Schloss nehmen — direkt oder über andere."""
    funktionen = _funktionen()
    nehmer = {name for name, k in funktionen.items()
              if any(isinstance(n, ast.Name) and n.id == "_DB_LOCK"
                     for n in ast.walk(k))}
    gewachsen = True
    while gewachsen:                     # bis sich nichts mehr ändert
        gewachsen = False
        for name, knoten in funktionen.items():
            if name not in nehmer and _gerufene(knoten) & nehmer:
                nehmer.add(name)
                gewachsen = True
    return nehmer


def _im_schloss() -> list[str]:
    """Aufrufe innerhalb eines with-_DB_LOCK-Blocks, die selbst zusperren."""
    nehmer = schlossnehmer()
    treffer = []
    for knoten in ast.walk(BAUM):
        if not isinstance(knoten, (ast.With, ast.AsyncWith)):
            continue
        if not any(isinstance(n, ast.Name) and n.id == "_DB_LOCK"
                   for p in knoten.items for n in ast.walk(p.context_expr)):
            continue
        for rumpf in knoten.body:        # nur der Block, nicht die with-Zeile
            for a in ast.walk(rumpf):
                if isinstance(a, ast.Call) and isinstance(a.func, ast.Name) \
                        and a.func.id in nehmer:
                    treffer.append(f"  babu_web.py:{a.lineno}  {a.func.id}()")
    return treffer


def test_das_schloss_nimmt_sich_selbst_nicht_zweimal():
    treffer = _im_schloss()
    assert not treffer, ("Im _DB_LOCK-Block steht ein Aufruf, der das Schloss "
                         "selbst braucht — das hängt:\n" + "\n".join(treffer))


def test_der_waechter_sieht_die_ganze_kette():
    """Gegenprobe: salon_von nimmt das Schloss nur mittelbar, über
    nutzer_holen. Sieht der Wächter das nicht, ist er nutzlos."""
    nehmer = schlossnehmer()
    assert "nutzer_holen" in nehmer, "die direkte Ebene fehlt"
    assert "salon_von" in nehmer, "die Kette wird nicht verfolgt"
