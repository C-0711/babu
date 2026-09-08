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

**Seit dem 08.09.2026 über MEHRERE Dateien.** `babu_web.py` wird Gruppe für
Gruppe in eigene Router zerlegt (Paket 2.1); die erste ausgegliederte Gruppe
ist `marke_routen.py` mit `_logo_pfad` und `_stueck_pfad`. Ein Wächter, der
nur `babu_web.py` liest, hätte die beiden ab dem Umzug schlicht nicht mehr
gesehen — und `test_die_bewachten_funktionen_gibt_es_wirklich` hätte das
zwar gemeldet, aber wer den Namen dann aus der Liste streicht, hat den
blinden Fleck. Deshalb steht hier eine LISTE von Quellen; jede weitere
Ausgliederung wird eine Zeile in `QUELLEN`.

Zwei Formen kommen dadurch dazu, beide werden erkannt:
* der Decorator heißt in einem ausgegliederten Blatt `@router.get`, nicht
  `@app.get`;
* der Betrieb kommt dort als `bw.salon_von_aktiv(un)` (Attribut am lazy
  importierten `babu_web`), nicht als blanker Name.
"""
import ast
from pathlib import Path

BLATT = Path(__file__).resolve().parent.parent

# Jede Datei, die Routen trägt. Wächst mit jeder Ausgliederung mit.
QUELLEN = [BLATT / "babu_web.py", BLATT / "marke_routen.py"]
BAEUME = {q.name: ast.parse(q.read_text(encoding="utf-8")) for q in QUELLEN}

# Wie die Routensammlung heißt — `app` im Monolithen, `router` im
# ausgegliederten Blatt.
SAMMLER = {"app", "router"}

# Erstes Argument ist IMMER der Betrieb — es gibt keinen sinnvollen Aufruf
# mit einem fremden Konto.
BETRIEBSFUNKTIONEN = {
    "team_liste", "team_personalkosten",         # Personal des Betriebs
    "_logo_pfad", "_foto_pfad", "_stueck_pfad",  # Dateien des Betriebs
    "_vorschlag_pfad",                           # dito, Logo-Entwürfe
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


def _gerufen(k) -> str | None:
    """Der Name der gerufenen Funktion — `f(...)` wie `bw.f(...)`."""
    if not isinstance(k, ast.Call):
        return None
    if isinstance(k.func, ast.Name):
        return k.func.id
    if isinstance(k.func, ast.Attribute):
        return k.func.attr
    return None


def _routen(baum) -> list:
    """Jede Funktion mit @app.get/@router.post/… — dort kommt `un` vom Wächter."""
    aus = []
    for k in ast.walk(baum):
        if not isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in k.decorator_list:
            ziel = d.func if isinstance(d, ast.Call) else d
            if isinstance(ziel, ast.Attribute) and isinstance(ziel.value, ast.Name) \
                    and ziel.value.id in SAMMLER:
                aus.append(k)
                break
    return aus


def _herkunft(f) -> dict:
    """Variable -> Funktion, aus der sie stammt (auch aus `a, b = f(...)`)."""
    q = {}
    for k in ast.walk(f):
        if not isinstance(k, ast.Assign) or not isinstance(k.value, ast.Call):
            continue
        name = _gerufen(k.value)
        if name is None:
            continue
        ziel = k.targets[0]
        if isinstance(ziel, ast.Name):
            q[ziel.id] = name
        elif isinstance(ziel, ast.Tuple) and ziel.elts and isinstance(ziel.elts[0], ast.Name):
            q[ziel.elts[0].id] = name
    return q


def _verstoesse() -> list[str]:
    aus = []
    for datei, baum in BAEUME.items():
        for f in _routen(baum):
            q = _herkunft(f)
            for k in ast.walk(f):
                name = _gerufen(k)
                if name not in BETRIEBSFUNKTIONEN or not k.args:
                    continue
                a = k.args[0]
                if _gerufen(a) in AUFGELOEST:
                    continue
                if isinstance(a, ast.Name) and q.get(a.id) in AUFGELOEST:
                    continue
                gezeigt = a.id if isinstance(a, ast.Name) else ast.dump(a)[:40]
                aus.append(f"{datei}:{k.lineno} {f.name}: "
                           f"{name}({gezeigt}) — nicht über salon_von_aktiv")
    return aus


def test_jede_route_reicht_den_aktiven_betrieb_weiter():
    verstoesse = _verstoesse()
    assert not verstoesse, "\n".join(verstoesse)


def test_die_bewachten_funktionen_gibt_es_wirklich():
    """Ein Wächter über Namen, die es nicht mehr gibt, bewacht nichts."""
    namen = set()
    for baum in BAEUME.values():
        namen |= {k.name for k in ast.walk(baum)
                  if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))}
    fehlen = sorted(BETRIEBSFUNKTIONEN - namen)
    assert not fehlen, f"bewacht, existiert aber nicht: {fehlen}"
    assert "salon_von_aktiv" in namen


def test_jede_quelle_traegt_wirklich_routen():
    """Eine Quelle ohne Routen ist entweder falsch eingetragen oder leer —
    beides führt dazu, dass hier nichts geprüft wird, ohne dass es auffällt."""
    for datei, baum in BAEUME.items():
        assert _routen(baum), f"{datei} trägt keine einzige Route"


def test_der_waechter_wuerde_eine_luecke_sehen():
    """Die Gegenprobe: der Wächter am 08.09.2026 gegen den Stand VOR dem Fix.

    Zweimal, weil es seit der Ausgliederung zwei Schreibweisen gibt: die des
    Monolithen (`@app.get`, blanker Name) und die eines eigenen Blatts
    (`@router.get`, `bw.`-Attribut). Ein Wächter, der nur die erste sieht,
    ließe jede ausgegliederte Gruppe ungeprüft durch.
    """
    proben = (
        "app = X()\n"
        "@app.get('/x')\n"
        "def route(request):\n"
        "    un, fehler = _box_wache(request)\n"
        "    return team_personalkosten(un)\n",
        "router = X()\n"
        "@router.get('/x')\n"
        "def route(request):\n"
        "    bw = _bw()\n"
        "    un, fehler = bw._box_wache(request)\n"
        "    return _logo_pfad(un)\n",
    )
    echt = dict(BAEUME)
    try:
        for quelltext in proben:
            BAEUME.clear()
            BAEUME["probe.py"] = ast.parse(quelltext)
            assert len(_verstoesse()) == 1, quelltext
    finally:
        BAEUME.clear()
        BAEUME.update(echt)


def test_der_waechter_nimmt_den_aufgeloesten_betrieb_an():
    """Die Gegen-Gegenprobe: die richtige Form darf NICHT anschlagen.

    Auch als Attribut am lazy importierten `babu_web` — sonst meldete jede
    ausgegliederte Datei lauter Fehlalarme, und das ist schlimmer als gar
    keine Prüfung.
    """
    echt = dict(BAEUME)
    try:
        BAEUME.clear()
        BAEUME["probe.py"] = ast.parse(
            "router = X()\n"
            "@router.get('/x')\n"
            "def route(request):\n"
            "    bw = _bw()\n"
            "    un, fehler = bw._box_wache(request)\n"
            "    inhaber = bw.salon_von_aktiv(un)\n"
            "    _logo_pfad(inhaber)\n"
            "    return _stueck_pfad(bw.salon_von_aktiv(un), 'aushang')\n")
        assert _verstoesse() == []
    finally:
        BAEUME.clear()
        BAEUME.update(echt)
