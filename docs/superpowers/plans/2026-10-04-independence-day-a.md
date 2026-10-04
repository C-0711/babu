# Independence Day Stufe A — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jede Inhaberin kann ihre Buchhaltung selbst prüfen, korrigieren, Kreditoren pflegen und den Monat abschließen — mit oder ohne Steuerbüro; ein Modus „Wer reicht beim Finanzamt ein?“ steuert nur letzten Schritt, Texte und Fristen.

**Architecture:** Ein reines Modul `arbeitsweise.py` deutet die Einstellung. Eine neue Wache `_buchhaltung_box_wache` (Kanzlei/Admin wie bisher, dazu die Inhaberin über `_box_wache`) ersetzt die Verwalter-Wache auf DATEV-Seite, Korrektur und Export. Texte und Knöpfe lesen den Modus; Fristen lesen ihn statt `steuerberater_status`.

**Tech Stack:** Python 3.12, FastAPI, pytest (Server `server/belegreview/`), Vanilla-JS in `portal.html`/`datev.html`.

**Spec:** `docs/superpowers/specs/2026-10-04-independence-day-a-design.md`

## Global Constraints

- Sprache in UI, Commits und Kommentaren: Deutsch. UI-Sprachregel: kein Technik-Vokabular; `tests/test_sprachregel.py` prüft `portal.html` inklusive `//`-Kommentaren (verbotene Wörter: Server, Token, Hash, Commit, Queue, Modell, KI, OCR, Lesung) — JS-Kommentare als `/* */`.
- Im Portal nie Namen in `onclick`-Attribute, nur Nummern oder `data-`-Attribute.
- Neue Routen immer über `_box_wache`/`box_mitglied`/`_verwalter_box_wache` absichern, nie über `ERLAUBT`. (A legt keine neue Route an.)
- Mitarbeiterinnen (Rolle `mitarbeit`) bekommen keine der Werkzeuge.
- Kanzleien mit `X-Mandant` verhalten sich exakt wie bisher.
- `/api/belege`, `/api/abgleich/{monat}` (Golden-Vergleich) und `tests/golden/routen.txt` bleiben unverändert.
- Suite: `cd server/belegreview && <venv>/bin/python -m pytest tests/<datei> -q -p no:cacheprovider` (venv: `/tmp/babu-venv` oder die Scratch-venv der Sitzung). Nie `pkill -f pytest`, nie `git stash`.
- Rechtstexte (`recht.py`, `avv.py`), Werbung und App-Store-Notiz bleiben in A unverändert.

## Review Focus

- Ein von einer Kanzlei angelegter Betrieb ohne jede Einstellung muss „steuerbuero“ bleiben (keine DATEV-Begriffe, keine Mein-ELSTER-Texte für Nina) — Test in Task 2.
- Eine Inhaberin darf über `X-Mandant` nicht in die DATEV-Seite eines fremden Betriebs (der Kopf verlangt Kanzlei-Mitgliedschaft) — Test in Task 4.
- Eine Mitarbeiterin mit „darf Belege“ erreicht weder die Seite `/datev` noch `/api/korrektur` noch den Export — Test in Task 4.
- Abo „nur lesen“: Vorschau geht, „Monat abschließen“ nicht — Test in Task 4.
- Einrichtungsantworten in Klartext („Vierteljährlich“, „Weiß nicht“, „Baden-Württemberg“) ergeben die richtigen Fristen — Test in Task 3.

---

### Task 1: `arbeitsweise.py` — eine Stelle, die den Modus deutet

**Files:**
- Create: `server/belegreview/arbeitsweise.py`
- Test: `server/belegreview/tests/test_arbeitsweise.py`

**Interfaces:**
- Produces: `arbeitsweise.STEUERBUERO = "steuerbuero"`, `arbeitsweise.SELBST = "selbst"`, `arbeitsweise.modus(einstellungen: dict | None, betreut: bool = False) -> str`.

- [ ] **Step 1: Write the failing test**

```python
"""Wer reicht beim Finanzamt ein? — die Deutung der Einstellung (Stufe A)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import arbeitsweise as aw  # noqa: E402


@pytest.mark.parametrize("wert, erwartet", [
    ("Mein Steuerbüro", aw.STEUERBUERO),
    ("Mein Steuerbüro bleibt", aw.STEUERBUERO),
    ("vorbereitend", aw.STEUERBUERO),
    ("Ich selbst (Independence Day)", aw.SELBST),
    ("Alles über babu", aw.SELBST),
])
def test_alle_werte_der_einstellung(wert, erwartet):
    assert aw.modus({"steuerberater_modus": wert}) == erwartet


def test_ohne_modus_entscheidet_die_frage_nach_dem_steuerberater():
    assert aw.modus({"steuerberater_status": "Ja"}) == aw.STEUERBUERO
    assert aw.modus({"steuerberater_status": "Nein"}, betreut=True) == aw.SELBST


def test_ohne_jede_angabe_entscheidet_die_betreuung():
    """Ein von einer Kanzlei angelegter Betrieb ohne Einstellungen bleibt beim
    Steuerbüro; ein Direktkunde ohne Angaben macht es selbst."""
    assert aw.modus({}, betreut=True) == aw.STEUERBUERO
    assert aw.modus(None, betreut=False) == aw.SELBST
    assert aw.modus({"steuerberater_modus": "  "}, betreut=True) == aw.STEUERBUERO
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/test_arbeitsweise.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'arbeitsweise'`

- [ ] **Step 3: Write minimal implementation**

```python
"""Wer reicht beim Finanzamt ein — das Steuerbüro oder die Unternehmerin selbst?

Independence Day, Stufe A (04.10.2026). babu gibt es mit und ohne Steuerbüro;
beides muss gehen. Der Modus regelt NICHT den Zugriff (jede Inhaberin darf
prüfen, korrigieren, abschließen), sondern den letzten Schritt im Monat, die
Texte und die Fristen. Diese Datei ist die einzige Stelle, die die Einstellung
`steuerberater_modus` deutet — alte und neue Antworten.

Reine Rechnung ohne Datenbank.
"""
from __future__ import annotations

STEUERBUERO = "steuerbuero"
SELBST = "selbst"

_STEUERBUERO = {"mein steuerbüro", "mein steuerbüro bleibt", "vorbereitend",
                "steuerbuero"}
_SELBST = {"ich selbst (independence day)", "ich selbst", "alles über babu",
           "selbst"}


def modus(einstellungen: dict | None, betreut: bool = False) -> str:
    """`steuerbuero` oder `selbst`.

    Reihenfolge: die ausdrückliche Antwort; sonst „Hast du einen Steuerberater?“;
    sonst die Betreuung — ein Betrieb, den ein echtes Steuerbüro betreut
    (`betreut`), bleibt beim Steuerbüro.
    """
    e = einstellungen or {}
    m = str(e.get("steuerberater_modus") or "").strip().lower()
    if m in _STEUERBUERO:
        return STEUERBUERO
    if m in _SELBST:
        return SELBST
    s = str(e.get("steuerberater_status") or "").strip().lower()
    if s in ("ja", "vorhanden"):
        return STEUERBUERO
    if s == "nein":
        return SELBST
    return STEUERBUERO if betreut else SELBST
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/test_arbeitsweise.py -q -p no:cacheprovider`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add server/belegreview/arbeitsweise.py server/belegreview/tests/test_arbeitsweise.py
git commit -m "Independence Day A: arbeitsweise.modus deutet „Wer reicht ein?“"
```

---

### Task 2: Arbeitsweise am Betrieb — `/api/ich`, `/api/einstellungen`, neue Einstellungen

**Files:**
- Modify: `server/belegreview/mandanten.py` (neue Funktion `kanzlei_name`)
- Modify: `server/belegreview/babu_web.py` — `EINSTELLUNG_SCHLUESSEL` (~4765), `_einstellungen_mit_paket` (~4796), `/api/ich` (`daten = {"un": …}` ~2433), neue Funktion `_arbeitsweise(un)` direkt über `_einstellungen_mit_paket`
- Test: `server/belegreview/tests/test_arbeitsweise.py` (Integrationsteil anhängen)

**Interfaces:**
- Consumes: `arbeitsweise.modus(e, betreut)` (Task 1), `testmonat.DIREKT_NAME == "babu direkt"`.
- Produces: `mandanten.kanzlei_name(mandant_id: int, c=None) -> str | None`; `babu_web._arbeitsweise(un: str) -> str`; Feld `arbeitsweise` in `/api/ich` und `/api/einstellungen`.

- [ ] **Step 1: Write the failing test** (anhängen an `tests/test_arbeitsweise.py`)

```python
from test_acting_as import _login, welt2  # noqa: E402,F401


def test_ein_kanzleibetrieb_ohne_einstellungen_bleibt_beim_steuerbuero(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    assert nina.get("/api/ich").json()["arbeitsweise"] == "steuerbuero"
    assert nina.get("/api/einstellungen").json()["arbeitsweise"] == "steuerbuero"


def test_die_inhaberin_stellt_auf_selbst_um(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    r = nina.post("/api/einstellungen",
                  json={"steuerberater_modus": "Ich selbst (Independence Day)",
                        "ustva_rhythmus": "Vierteljährlich",
                        "dauerfristverlaengerung": "Ja",
                        "bundesland": "Baden-Württemberg", "hat_personal": "Nein"})
    assert r.status_code == 200, r.text
    e = nina.get("/api/einstellungen").json()
    assert e["arbeitsweise"] == "selbst"
    assert (e["ustva_rhythmus"], e["bundesland"]) == ("Vierteljährlich", "Baden-Württemberg")
    assert nina.get("/api/ich").json()["arbeitsweise"] == "selbst"
```

Am Dateikopf zusätzlich `sys.path.insert(0, str(Path(__file__).resolve().parent))` ergänzen, damit `test_acting_as` importierbar ist.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/test_arbeitsweise.py -q -p no:cacheprovider`
Expected: FAIL — `KeyError: 'arbeitsweise'` bzw. neue Schlüssel werden nicht gespeichert.

- [ ] **Step 3: Write minimal implementation**

In `mandanten.py` (unter `bank_stand`):

```python
def kanzlei_name(mandant_id: int, c=None) -> str | None:
    """Wie heißt die Kanzlei, die diesen Betrieb betreut?"""
    with _sitzung(c) as cc:
        z = cc.execute("SELECT k.name FROM mandant m JOIN kanzlei k "
                       "ON k.id = m.kanzlei_id WHERE m.id=?", (mandant_id,)).fetchone()
    return z[0] if z else None
```

In `babu_web.py`, `EINSTELLUNG_SCHLUESSEL` um eine Zeile erweitern (nach `"personal_monat",`):

```python
                          # Fristen (Independence Day A, 04.10.2026): fristen.py
                          # las sie schon, setzen ließen sie sich nie.
                          "ustva_rhythmus", "dauerfristverlaengerung",
                          "bundesland", "hat_personal",
```

Direkt über `_einstellungen_mit_paket`:

```python
def _arbeitsweise(un: str) -> str:
    """Steuerbüro oder selbst — für diesen Zugang, beim Acting-as für den Mandanten."""
    import arbeitsweise  # noqa: PLC0415
    import testmonat  # noqa: PLC0415
    mandant_id = _AKTIVER_MANDANT.get(None)
    betreut = False
    if mandant_id is not None:
        name = mandanten.kanzlei_name(mandant_id)
        betreut = bool(name) and name != testmonat.DIREKT_NAME
    return arbeitsweise.modus(db_einstellungen(salon_von_aktiv(un)), betreut)
```

In `_einstellungen_mit_paket`, nach `e["paket_empfehlung"] = …`:

```python
    e["arbeitsweise"] = _arbeitsweise(un)
```

In `/api/ich`, `daten = {...}` um `"arbeitsweise": _arbeitsweise(un),` erweitern.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/test_arbeitsweise.py tests/test_api.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/belegreview/mandanten.py server/belegreview/babu_web.py server/belegreview/tests/test_arbeitsweise.py
git commit -m "Independence Day A: Arbeitsweise in /api/ich und Einstellungen, Fristen-Einstellungen setzbar"
```

---

### Task 3: Fristen folgen der Arbeitsweise, Klartext-Antworten werden verstanden

**Files:**
- Modify: `server/belegreview/fristen.py` — `termin_profil` (~144–167), neues `LAND_KUERZEL`
- Test: `server/belegreview/tests/test_fristen.py` (anhängen; falls die Datei anders heißt: `grep -l termin_profil tests/*.py`)

**Interfaces:**
- Consumes: `arbeitsweise.modus` (Task 1).
- Produces: `fristen.termin_profil(einstellungen, hat_team=False, betreut=False) -> dict` mit unverändertem Schlüssel `steuerberater: bool`.

- [ ] **Step 1: Write the failing test**

```python
def test_klartext_aus_der_einrichtung_wird_verstanden():
    import fristen  # noqa: PLC0415
    p = fristen.termin_profil({"ustva_rhythmus": "Vierteljährlich",
                               "bundesland": "Baden-Württemberg",
                               "dauerfristverlaengerung": "Ja"})
    assert (p["ustva_rhythmus"], p["bundesland"], p["dauerfristverlaengerung"]) == (
        "vierteljaehrlich", "BW", True)
    assert fristen.termin_profil({"ustva_rhythmus": "Weiß nicht"})["ustva_rhythmus"] == "monatlich"


def test_jahresfrist_folgt_der_arbeitsweise():
    import fristen  # noqa: PLC0415
    assert fristen.termin_profil({"steuerberater_modus": "Mein Steuerbüro"})["steuerberater"] is True
    assert fristen.termin_profil({"steuerberater_modus": "Ich selbst (Independence Day)",
                                  "steuerberater_status": "Ja"})["steuerberater"] is False
    assert fristen.termin_profil({}, betreut=True)["steuerberater"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/test_fristen.py -q -p no:cacheprovider -k "klartext or arbeitsweise"`
Expected: FAIL — `vierteljährlich` wird nicht erkannt bzw. `betreut` unbekannt.

- [ ] **Step 3: Write minimal implementation**

In `fristen.py` unter `BUNDESLAENDER`:

```python
#: Die Einrichtung fragt das Land im Klartext (04.10.2026); intern gelten Kürzel.
LAND_KUERZEL = {
    "baden-württemberg": "BW", "bayern": "BY", "berlin": "BE", "brandenburg": "BB",
    "bremen": "HB", "hamburg": "HH", "hessen": "HE", "mecklenburg-vorpommern": "MV",
    "niedersachsen": "NI", "nordrhein-westfalen": "NW", "rheinland-pfalz": "RP",
    "saarland": "SL", "sachsen": "SN", "sachsen-anhalt": "ST",
    "schleswig-holstein": "SH", "thüringen": "TH",
}
```

`termin_profil` ersetzen durch:

```python
def termin_profil(einstellungen: dict, hat_team: bool = False,
                  betreut: bool = False) -> dict:
    """Welche Fristen gelten für diesen Salon?

    Der Rhythmus der Voranmeldung hängt an der Steuer des Vorjahres
    (§ 18 Abs. 2 UStG). Ist er nicht hinterlegt, gilt die vorsichtige
    Annahme „monatlich" — lieber ein Termin zu viel im Kalender. Ob ein
    Steuerbüro einreicht, sagt seit 04.10.2026 `arbeitsweise` (Stufe A).
    """
    import arbeitsweise  # noqa: PLC0415
    e = {k: (v or "").strip() for k, v in (einstellungen or {}).items()}
    klein = e.get("kleinunternehmer") == "Ja"
    rhythmus = e.get("ustva_rhythmus", "").lower().replace("ä", "ae")
    if rhythmus not in ("monatlich", "vierteljaehrlich", "keine"):
        rhythmus = "keine" if klein else "monatlich"
    land = e.get("bundesland", "").strip()
    return {
        "kleinunternehmer": klein,
        "ustva_rhythmus": rhythmus,
        "dauerfristverlaengerung": e.get("dauerfristverlaengerung") == "Ja",
        "lohn": bool(hat_team) or e.get("hat_personal") == "Ja",
        "lohnsteuer_rhythmus": (e.get("lohnsteuer_rhythmus", "").lower()
                                or "vierteljaehrlich"),
        "bundesland": LAND_KUERZEL.get(land.lower(), land.upper()),
        "steuerberater": arbeitsweise.modus(e, betreut) == arbeitsweise.STEUERBUERO,
    }
```

Aufrufer von `termin_profil` in `babu_web.py` (`grep -n "termin_profil(" babu_web.py`): wo `_AKTIVER_MANDANT` gesetzt ist, `betreut=` wie in `_arbeitsweise` mitgeben. Kleine Hilfsfunktion neben `_arbeitsweise`:

```python
def _betreut() -> bool:
    import testmonat  # noqa: PLC0415
    mandant_id = _AKTIVER_MANDANT.get(None)
    if mandant_id is None:
        return False
    name = mandanten.kanzlei_name(mandant_id)
    return bool(name) and name != testmonat.DIREKT_NAME
```

und `_arbeitsweise` darauf umstellen (`betreut = _betreut()`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/test_fristen.py tests/test_arbeitsweise.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/belegreview/fristen.py server/belegreview/babu_web.py server/belegreview/tests/test_fristen.py
git commit -m "Independence Day A: Fristen folgen der Arbeitsweise, Klartext aus der Einrichtung"
```

---

### Task 4: Die Wache „Buchhaltung“ — Inhaberin darf DATEV-Seite, Korrektur, Export, Abschluss

**Files:**
- Modify: `server/belegreview/babu_web.py` — neue `darf_buchhaltung`, `_buchhaltung_box_wache` direkt unter `_verwalter_box_wache` (~5397); `GET /datev` (~1975); `api_korrektur` (~4617); `api_export` (~6151)
- Modify: `server/belegreview/datev_seite.py` — `_wache` (~83)
- Modify: `server/belegreview/tests/test_datev_seite.py` — `test_salon_sieht_weder_seite_noch_zahlen` wird `test_mitarbeiterin_sieht_weder_seite_noch_zahlen`
- Create: `server/belegreview/tests/test_buchhaltung_wache.py`

**Interfaces:**
- Produces: `babu_web.darf_buchhaltung(un: str) -> bool`; `babu_web._buchhaltung_box_wache(request) -> tuple[str, None] | tuple[None, JSONResponse]`.

- [ ] **Step 1: Write the failing test** (`tests/test_buchhaltung_wache.py`)

```python
"""Jede Inhaberin darf ihre Buchhaltung selbst machen (Independence Day A).

DATEV-Seite mit Prüfbefund, Kreditoren, Korrektur, Export und „Monat
abschließen“ — in ihrer eigenen Box. Mitarbeiterinnen nie, fremde Boxen nie,
Kanzleien wie bisher.
"""
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))
sys.path.insert(0, str(HIER))

import box as bx  # noqa: E402
from test_acting_as import _login, welt2  # noqa: F401,E402

ALPHA = "20260501-120000-aaa111-alpha"


@pytest.fixture(autouse=True)
def _boxen_schreibbar(monkeypatch):
    monkeypatch.setattr(bx, "remote_aus_ref", lambda ref: str(bx.store_aus_ref(ref)))


def test_die_inhaberin_erreicht_ihre_datev_seite(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    assert nina.get("/datev").status_code == 200
    assert nina.get("/api/datev/uebersicht").status_code == 200
    assert nina.get("/api/datev/vorschau", params={"von": "2026-05", "bis": "2026-05"}).status_code == 200
    assert nina.get("/api/datev/kreditoren").status_code == 200
    assert nina.post("/api/datev/kreditoren", json={"name": "Wella"}).status_code == 200
    assert nina.get("/api/export/2026-05.csv").status_code == 200


def test_die_inhaberin_korrigiert_selbst(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    r = nina.post(f"/api/korrektur/{ALPHA}", json={"buchungstext": "Einkauf"})
    assert r.status_code in (200, 404), r.text     # 404: Beleg ohne Lesung — aber nicht 403
    assert r.status_code != 403


def test_eine_inhaberin_kommt_nicht_in_eine_fremde_box(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    kopf = {"X-Mandant": str(welt2["berta_id"])}
    assert nina.get("/api/datev/uebersicht", headers=kopf).status_code == 403
    assert nina.get("/datev", params={"mandant": welt2["berta_id"]}).status_code == 403


def test_mitarbeiterin_bekommt_nichts(welt2, monkeypatch):
    monkeypatch.setattr(welt2["bw"], "rolle", lambda un: "mitarbeit")
    nina = _login(welt2["bw"], welt2["nina"])
    assert nina.get("/datev").status_code == 403
    assert nina.get("/api/datev/uebersicht").status_code == 403
    assert nina.post(f"/api/korrektur/{ALPHA}", json={"buchungstext": "x"}).status_code == 403
    assert nina.get("/api/export/2026-05.csv").status_code == 403


def test_die_kanzlei_bleibt_wie_sie_war(welt2):
    kanzlei = _login(welt2["bw"], welt2["kanzlei"])
    kopf = {"X-Mandant": str(welt2["nina_id"])}
    assert kanzlei.get("/api/datev/uebersicht", headers=kopf).status_code == 200


def test_nur_lesen_sperrt_den_abschluss_der_inhaberin(welt2, monkeypatch):
    import abo  # noqa: PLC0415
    monkeypatch.setattr(abo, "zugang", lambda **kw: {"stufe": "nur_lesen", "grund": "test_vorbei"})
    nina = _login(welt2["bw"], welt2["nina"])
    assert nina.get("/api/datev/vorschau", params={"von": "2026-05", "bis": "2026-05"}).status_code == 200
    assert nina.post("/api/datev/uebergeben", params={"von": "2026-05", "bis": "2026-05"}).status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/test_buchhaltung_wache.py -q -p no:cacheprovider`
Expected: FAIL — Inhaberin bekommt 403 auf `/datev` und `/api/datev/*`.

- [ ] **Step 3: Write minimal implementation**

In `babu_web.py` direkt unter `_verwalter_box_wache`:

```python
def darf_buchhaltung(un: str) -> bool:
    """Prüfen, korrigieren, abschließen: Verwaltung — und jede Inhaberin
    (Independence Day A, 04.10.2026). Mitarbeiterinnen nie."""
    return darf_verwalten(un) or rolle(un) == "salon"


def _buchhaltung_box_wache(request: Request):
    """Die Wache der Buchhaltungswerkzeuge (DATEV-Seite, Korrektur, Export).

    Kanzlei und Admin gehen den Weg von `_verwalter_box_wache` (mit
    `X-Mandant`, unverändert). Die Inhaberin geht über `_box_wache`: ihre
    eigene Box, und das Abo „nur lesen“ sperrt ihre Schreibwege.
    """
    un, fehler = _api_wache(request)
    if fehler:
        return None, fehler
    if darf_verwalten(un):
        return _verwalter_box_wache(request)
    if rolle(un) != "salon":
        return None, JSONResponse({"fehler": "Das macht die Inhaberin."},
                                  status_code=403)
    return _box_wache(request)
```

`GET /datev`: `_verwalter_box_wache(request)` → `_buchhaltung_box_wache(request)`.

`api_korrektur` und `api_export`: die Zeilen

```python
    if not darf_verwalten(un):
        return JSONResponse({"fehler": "nur für die Kanzlei"}, status_code=403)
```

ersetzen durch

```python
    if not darf_buchhaltung(un):
        return JSONResponse({"fehler": "Das macht die Inhaberin."}, status_code=403)
```

(`_box_wache` davor bleibt — so ändert sich für Kanzleien nichts.)

`datev_seite._wache`: `return _bw()._verwalter_box_wache(request)` → `return _bw()._buchhaltung_box_wache(request)`; Docstring um einen Satz ergänzen: „Seit 04.10.2026 (Independence Day A) auch die Inhaberin in ihrer eigenen Box.“

In `tests/test_datev_seite.py` den Test umbenennen und `lambda un: "salon"` durch `lambda un: "mitarbeit"` ersetzen; Docstring: „Eine Mitarbeiterin bekommt nichts davon zu sehen …“.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/test_buchhaltung_wache.py tests/test_datev_seite.py tests/test_kreditoren_routen.py tests/test_schreiben.py tests/test_routen_vollstaendig.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/belegreview/babu_web.py server/belegreview/datev_seite.py server/belegreview/tests/test_buchhaltung_wache.py server/belegreview/tests/test_datev_seite.py
git commit -m "Independence Day A: Inhaberin darf DATEV-Seite, Korrektur, Export und Abschluss"
```

---

### Task 5: Ehrliche Texte auf dem Server

**Files:**
- Modify: `server/belegreview/monatsabschluss.py` — Modulkopf (Zeile ~6–8), `ustva_entwurf` (~335, `hinweis` ~368)
- Modify: `server/belegreview/vordrucke.py` — `ustva_pdf` (~432, Fuß ~484)
- Modify: `server/belegreview/babu_web.py` — Aufrufe `ma.ustva_entwurf(...)` (~11929, ~12236), `vordrucke.ustva_pdf(...)` (~12237), Freigabe-`hinweis` (~11966) und Docstrings (~11876, ~11940)
- Test: `server/belegreview/tests/test_arbeitsweise.py` (anhängen)

**Interfaces:**
- Consumes: `babu_web._arbeitsweise(un)` (Task 2).
- Produces: `monatsabschluss.ustva_entwurf(monat, erloese, vorsteuer, profil, arbeitsweise="steuerbuero")`; `monatsabschluss.uebermittlung_text(arbeitsweise: str) -> str`; `vordrucke.ustva_pdf(entwurf, betrieb, befunde, arbeitsweise="steuerbuero")`.

- [ ] **Step 1: Write the failing test**

```python
def test_kein_steuer_backend_mehr_in_den_texten():
    import monatsabschluss as ma  # noqa: PLC0415
    selbst = ma.uebermittlung_text("selbst")
    buero = ma.uebermittlung_text("steuerbuero")
    assert "Mein ELSTER" in selbst and "Steuer-Backend" not in selbst
    assert "Steuerbüro" in buero and "Steuer-Backend" not in buero


def test_der_entwurf_und_das_pdf_sagen_wer_uebermittelt(welt2, monkeypatch):
    nina = _login(welt2["bw"], welt2["nina"])
    nina.post("/api/einstellungen", json={"steuerberater_modus": "Ich selbst (Independence Day)",
                                          "kleinunternehmer": "Nein"})
    d = nina.get("/api/monatsabschluss/2026-05").json()
    assert "Mein ELSTER" in d["ustva"]["hinweis"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/test_arbeitsweise.py -q -p no:cacheprovider -k "texten or uebermittelt"`
Expected: FAIL — `AttributeError: module 'monatsabschluss' has no attribute 'uebermittlung_text'`

- [ ] **Step 3: Write minimal implementation**

In `monatsabschluss.py` über `ustva_entwurf`:

```python
def uebermittlung_text(arbeitsweise: str) -> str:
    """Wer die Voranmeldung ans Finanzamt schickt — ehrlich (Stufe A, 04.10.2026).

    Bis dahin stand hier „geschickt wird er von deinem Steuer-Backend“ — ein
    Dienst, den es nicht gibt. Den Versand per ELSTER bringt Stufe C.
    """
    if arbeitsweise == "selbst":
        return ("Entwurf aus deinen Zahlen. Den Versand ans Finanzamt bereiten wir "
                "vor — bis dahin trägst du die Zahlen in Mein ELSTER ein.")
    return "Entwurf aus deinen Zahlen. Geprüft und übermittelt wird er von deinem Steuerbüro."
```

`ustva_entwurf` bekommt den Parameter `arbeitsweise: str = "steuerbuero"` und `"hinweis": uebermittlung_text(arbeitsweise),`. Modulkopf-Satz zum „steuerlichen Backend“ ersetzen durch „Wer übermittelt, steht in `uebermittlung_text`.“

In `vordrucke.ustva_pdf(entwurf, betrieb, befunde, arbeitsweise="steuerbuero")` die erste Fußzeile ersetzen durch:

```python
    import monatsabschluss as ma  # noqa: PLC0415
    _fuss(b, [ma.uebermittlung_text(arbeitsweise) + " (§ 18 Abs. 1 UStG)",
              "Grundlage: Kassenbuch, gestellte Rechnungen und die Belege "
              "des Monats; Kennziffern nach Vordruckmuster USt 1 A 2026."])
```

In `babu_web.py` beide `ma.ustva_entwurf(monat, erloese, vorsteuer, profil)` um `, _arbeitsweise(un)` ergänzen, `vordrucke.ustva_pdf(entwurf, einstellungen, befunde)` um `, _arbeitsweise(un)`. Freigabe-`hinweis`: `"Entwurf aus babu — " + ma.uebermittlung_text(_arbeitsweise(un))`. Die Docstrings (~11876, ~11940) „steuerlichen Backend“ → „dem Steuerbüro oder der Unternehmerin selbst (siehe arbeitsweise)“.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/test_arbeitsweise.py tests/test_monatsabschluss*.py tests/test_vordrucke*.py -q -p no:cacheprovider`
Expected: PASS (bestehende Tests, die den alten Satz prüfen, bewusst auf den neuen umstellen)

- [ ] **Step 5: Commit**

```bash
git add server/belegreview/monatsabschluss.py server/belegreview/vordrucke.py server/belegreview/babu_web.py server/belegreview/tests/
git commit -m "Independence Day A: ehrliche Texte — Steuerbüro oder Mein ELSTER statt Steuer-Backend"
```

---

### Task 6: DATEV-Seite — „Monat abschließen“ oder „An mein Steuerbüro geben“

**Files:**
- Modify: `server/belegreview/datev_seite.py` — `api_uebersicht` (Antwort um `wer` erweitern)
- Modify: `server/belegreview/datev.html` — Knopf-Beschriftung, Rückfrage, Zurück-Link
- Test: `server/belegreview/tests/test_buchhaltung_wache.py` (anhängen)

**Interfaces:**
- Consumes: `babu_web._arbeitsweise(un)`, `babu_web.darf_verwalten(un)`.
- Produces: `/api/datev/uebersicht` liefert `wer ∈ {"kanzlei", "selbst", "steuerbuero"}`.

- [ ] **Step 1: Write the failing test**

```python
def test_die_seite_weiss_wer_den_monat_abschliesst(welt2):
    nina = _login(welt2["bw"], welt2["nina"])
    assert nina.get("/api/datev/uebersicht").json()["wer"] == "steuerbuero"
    nina.post("/api/einstellungen", json={"steuerberater_modus": "Ich selbst (Independence Day)"})
    assert nina.get("/api/datev/uebersicht").json()["wer"] == "selbst"
    kanzlei = _login(welt2["bw"], welt2["kanzlei"])
    assert kanzlei.get("/api/datev/uebersicht",
                       headers={"X-Mandant": str(welt2["nina_id"])}).json()["wer"] == "kanzlei"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/test_buchhaltung_wache.py -q -p no:cacheprovider -k abschliesst`
Expected: FAIL — `KeyError: 'wer'`

- [ ] **Step 3: Write minimal implementation**

In `api_uebersicht` in die Antwort:

```python
        # Wer hier den Monat abschließt (Independence Day A): die Kanzlei, die
        # Inhaberin für sich selbst oder die Inhaberin für ihr Steuerbüro.
        "wer": ("kanzlei" if bw.darf_verwalten(un) else bw._arbeitsweise(un)),
```

In `datev.html`:
- globale Variable `let WER = "kanzlei";`, in `starten()` nach `const d = …`: `WER = d.wer || "kanzlei";`; Zurück-Link für Inhaberinnen: `if (WER !== "kanzlei"){ document.getElementById("zurueck").href = "/portal"; }`.
- in `vorschau()` den Knopftext ersetzen:

```javascript
const UEBERGABE = {kanzlei: ["Stapel übergeben", "Nachtrag übergeben"],
                   selbst: ["Monat abschließen", "Nachtrag abschließen"],
                   steuerbuero: ["An mein Steuerbüro geben", "Nachtrag ans Steuerbüro geben"]};
```

und im Knopf `${(UEBERGABE[WER] || UEBERGABE.kanzlei)[b.uebergeben_text ? 1 : 0]}`.
- in `uebergeben()` die Rückfrage:

```javascript
  const frage = WER === "selbst"
    ? "Diesen Monat jetzt abschließen?\n\nDanach ist er festgeschrieben; was später kommt, geht als Nachtrag."
    : "Diesen Stapel jetzt an die Kanzlei übergeben?\n\nDanach gilt der Monat als bei der Kanzlei; was später kommt, geht als Nachtrag.";
  if (!confirm(frage)) return;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/test_buchhaltung_wache.py tests/test_datev_seite.py -q -p no:cacheprovider` und JS-Syntax: `python3 -c "import re,pathlib;pathlib.Path('/tmp/d.js').write_text('\n'.join(re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', pathlib.Path('server/belegreview/datev.html').read_text(), re.S)))" && node --check /tmp/d.js`
Expected: PASS, `node --check` ohne Ausgabe

- [ ] **Step 5: Commit**

```bash
git add server/belegreview/datev_seite.py server/belegreview/datev.html server/belegreview/tests/test_buchhaltung_wache.py
git commit -m "Independence Day A: DATEV-Seite sagt Monat abschließen oder An mein Steuerbüro geben"
```

---

### Task 7: Portal — Modus, Werkzeuge im Beleg, Menü, Texte, Einrichtung

**Files:**
- Modify: `server/belegreview/portal.html`
- Modify: `server/belegreview/saloncheck.py:229` (neuer Wert „Mein Steuerbüro“)
- Modify: `ios/Beleg/Beleg/AbschlussView.swift:3-4` (nur Kommentar)
- Test: `server/belegreview/tests/test_sprachregel.py` (bestehend), Node-Syntaxprüfung

**Interfaces:**
- Consumes: `/api/ich.arbeitsweise` (Task 2), `/api/korrektur/{stamm}` (Task 4, Inhaberin darf).
- Produces: JS `meineArbeitsweise`, `buchhaltungSelbst()`, `korrekturFormular(d)`.

- [ ] **Step 1: Sitzung kennt die Arbeitsweise**

Neben `let meineBox = true;`:

```javascript
let meineArbeitsweise = "steuerbuero";
/* Independence Day A: die Inhaberin macht ihre Buchhaltung selbst — dann
   sieht sie die Werkzeuge, die sonst nur das Steuerbüro sieht. Erlaubt sind
   sie ihr in beiden Arbeitsweisen; hier geht es nur um die Oberfläche. */
function buchhaltungSelbst(){ return meineRolle === "salon" && meineArbeitsweise === "selbst"; }
```

In `sitzungUebernehmen(d)`: `meineArbeitsweise = d.arbeitsweise || "steuerbuero";`. In `ladeEinstellungen()` nach `meineBox = …`: `meineArbeitsweise = ich.arbeitsweise || meineArbeitsweise;`.

- [ ] **Step 2: Beleg — DATEV-Abschnitt und Korrektur auch für Independence Day**

Bedingung `if ((zeilen.length || b) && istKanzlei()){` → `if ((zeilen.length || b) && (istKanzlei() || buchhaltungSelbst())){`, und hinter `${kreditorFeld(d)}` `${korrekturFormular(d)}` einsetzen. Neue Funktion neben `kreditorFeld`:

```javascript
/* Konto, Steuer und Buchungstext von Hand — dieselbe Korrektur wie in der
   Werkbank des Steuerbüros. */
function korrekturFormular(d){
  const e = d.einschaetzung || {}, v = d.vlm || {};
  const bu = String(e.steuerschluessel || "");
  return `<div class="kred-feld" id="korr-feld"><span class="lbl">Korrektur</span>
    <div class="eingabe-gitter" style="margin-top:8px">
      <label for="korr-konto">Konto<input id="korr-konto" inputmode="numeric" maxlength="8" value="${esc(e.konto_skr04 || "")}"></label>
      <label for="korr-bu">Steuer<select id="korr-bu">
        <option value="9"${bu === "9" ? " selected" : ""}>19 %</option>
        <option value="8"${bu === "8" ? " selected" : ""}>7 %</option>
        <option value=""${bu === "" || bu === "0" ? " selected" : ""}>ohne Steuer</option></select></label>
      <label class="breit" for="korr-text">Buchungstext<input id="korr-text" maxlength="60" value="${esc(v.buchungstext || "")}"></label>
    </div>
    <button class="chip" style="margin-top:10px" data-korr="${esc(d.stamm)}">Korrektur speichern</button>
    <span id="korr-status" style="font-size:12px;color:var(--gc-muted)"></span></div>`;
}
document.addEventListener("click", async ev => {
  const knopf = ev.target.closest("#korr-feld [data-korr]");
  if (!knopf) return;
  const status = $("#korr-status");
  status.textContent = "wird gespeichert …";
  try{
    const r = await api("/api/korrektur/" + knopf.dataset.korr, {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({konto_skr04: $("#korr-konto").value.trim(),
                            steuerschluessel: $("#korr-bu").value,
                            buchungstext: $("#korr-text").value.trim()})});
    const d = await r.json().catch(() => ({}));
    status.textContent = r.ok ? "Gespeichert ✓" : (d.fehler || "Ging gerade nicht.");
    if (r.ok) setTimeout(() => ladeDetail(knopf.dataset.korr), 500);
  }catch{ status.textContent = "Gerade keine Verbindung."; }
});
```

(`data-korr` trägt den Stamm, keinen Namen — der Stamm ist eine Kennung.)

- [ ] **Step 3: Menü und Export-Abschnitt**

`$("#nav-datev").hidden = $("#nav-verwaltung").hidden;` → `$("#nav-datev").hidden = $("#nav-verwaltung").hidden && !buchhaltungSelbst();`.

Im Export-Abschnitt (`html += \`<div class="sektion lbl">Für die Kanzlei</div>…`):

```javascript
  const selbst = buchhaltungSelbst();
  html += `<div class="sektion lbl">${selbst ? "Für DATEV" : "Für die Kanzlei"}</div><div class="karte">
    <p style="color:var(--gc-desc);font-size:13px">Der fertige Buchungsstapel dieses Monats —
    im Format, das DATEV versteht.</p>
    <p style="color:var(--gc-desc);font-size:13px;margin-top:4px">${uebergeben
      ? (selbst ? "Abgeschlossen seit " : "Bei der Kanzlei seit ") + esc(zeitKurz(uebergeben)) + "."
      : (selbst ? "Dieser Stapel ist eine Vorschau — abschließen kannst du den Monat auf der DATEV-Seite."
                : "Dieser Stapel ist eine Vorschau — übergeben wird er von deinem Steuerbüro oder von dir auf der DATEV-Seite.")}</p>`
```

In `stapelLaden`: `"Diesen Stapel lädt deine Kanzlei herunter."` → `"Den Stapel lädt die Inhaberin herunter."` (trifft nur noch Mitarbeiterinnen).

- [ ] **Step 4: Abschluss-Texte**

Zeile ~1636 (`ein Entwurf, den dein Steuer-Backend prüft.`) → `ein Entwurf.` und den Rest per JS beim Laden der Ansicht setzen: dem `<p>` die id `ab-satz` geben, in der Ladefunktion des Monatsabschlusses

```javascript
  $("#ab-satz").textContent = "Aus deinen Belegen und deinem Kassenbuch gerechnet — "
    + (meineArbeitsweise === "selbst" ? "ein Entwurf, den du selbst einreichst." : "ein Entwurf für dein Steuerbüro.");
```

Freigabe-Karte (~5321): Text und Knopf nach Modus:

```javascript
      <b>${meineArbeitsweise === "selbst" ? "Fertig?" : "Fertig für die Prüfung?"}</b>
      <p style="color:var(--gc-desc);font-size:13px;margin:4px 0 10px">${meineArbeitsweise === "selbst"
        ? "Die Zahlen werden festgehalten und bleiben als Nachweis in deiner Belegbox. Den Versand ans Finanzamt bereiten wir vor — bis dahin trägst du sie in Mein ELSTER ein."
        : "Dein Steuerbüro bekommt die Zahlen zur Prüfung und übermittelt sie ans Finanzamt. Was hier steht, bleibt als Nachweis in deiner Belegbox."}</p>
      <button class="chip" id="freigabe-knopf">${meineArbeitsweise === "selbst" ? "Zahlen festhalten" : "Zahlen zur Prüfung geben"}</button>
```

- [ ] **Step 5: Einrichtung**

In `EINRICHTUNG_SCHRITTE` die Frage zu `steuerberater_modus` ersetzen und vier Schritte anhängen:

```javascript
  {f:"Wer reicht beim Finanzamt ein?", k:"steuerberater_modus",
   wahl:["Mein Steuerbüro","Ich selbst (Independence Day)"],
   hilfe:"Beides geht — und du kannst es jederzeit ändern."},
  {f:"Wie oft gibst du die Umsatzsteuer-Voranmeldung ab?", k:"ustva_rhythmus",
   wahl:["Monatlich","Vierteljährlich","Weiß nicht"],
   hilfe:"Steht im Brief vom Finanzamt. Nicht sicher? Dann rechnen wir vorsichtig mit monatlich."},
  {f:"Hast du Dauerfristverlängerung?", k:"dauerfristverlaengerung", wahl:["Ja","Nein","Weiß nicht"]},
  {f:"In welchem Bundesland ist dein Betrieb?", k:"bundesland",
   wahl:["Baden-Württemberg","Bayern","Berlin","Brandenburg","Bremen","Hamburg","Hessen",
         "Mecklenburg-Vorpommern","Niedersachsen","Nordrhein-Westfalen","Rheinland-Pfalz",
         "Saarland","Sachsen","Sachsen-Anhalt","Schleswig-Holstein","Thüringen"]},
  {f:"Beschäftigst du Personal?", k:"hat_personal", wahl:["Ja","Nein"]},
```

Umstellen jederzeit: in der Ansicht Einstellungen unter der Karte `#einst-paket`
einen Knopf ergänzen (Markup neben `id="einst-paket"`):

```html
    <button class="chip" style="margin:8px 0 14px" onclick="location.hash='#einrichtung'">Arbeitsweise und Fristen ändern</button>
```

`saloncheck.py:229`: `("vorbereitend", "Mein Steuerbüro bleibt")` → `("vorbereitend", "Mein Steuerbüro bleibt", "Mein Steuerbüro")`.

`ios/Beleg/Beleg/AbschlussView.swift:4`: Kommentar „geprüft wird er vom Steuer-Backend.“ → „wer übermittelt, sagt die Arbeitsweise des Betriebs.“

- [ ] **Step 6: Prüfen**

Run: `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/test_sprachregel.py tests/test_saloncheck*.py -q -p no:cacheprovider`
Run (JS-Syntax): `python3 -c "import re,pathlib;pathlib.Path('/tmp/p.js').write_text('\n'.join(re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', pathlib.Path('server/belegreview/portal.html').read_text(), re.S)))" && node --check /tmp/p.js`
Expected: PASS, keine Ausgabe von `node --check`

- [ ] **Step 7: Commit**

```bash
git add server/belegreview/portal.html server/belegreview/saloncheck.py ios/Beleg/Beleg/AbschlussView.swift
git commit -m "Independence Day A: Portal zeigt die Werkzeuge im Modus selbst, ehrliche Texte, Einrichtung fragt die Fristen"
```

---

### Task 8: Ausliefern

**Files:** keine Codeänderung.

- [ ] **Step 1: Betroffene Tests gesammelt**

Run: `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/test_arbeitsweise.py tests/test_buchhaltung_wache.py tests/test_datev_seite.py tests/test_kreditoren_routen.py tests/test_fristen.py tests/test_api.py tests/test_schreiben.py tests/test_sprachregel.py tests/test_routen_vollstaendig.py tests/test_acting_as.py -q -p no:cacheprovider`
Expected: alle grün.

- [ ] **Step 2: Deploy-Ritual (CLAUDE.md)**

Sicherung (tgz ohne `.env*`, `pg_dump`), Rückweg-Image taggen, Golden vorher (`werkzeuge/golden.py`), `rsync -rc --delete --exclude='.env*' --exclude=werkzeuge --exclude=__pycache__ --exclude=.pytest_cache server/ h200v:~/babu-docker/`, `docker compose build babu-web && docker compose up -d babu-web`, `/healthz` muss `stand: ok` liefern, Golden nachher, `diff` muss gleich sein.

- [ ] **Step 3: Live lesend prüfen**

`/api/ich` eines Kanzlei-Mandanten liefert `arbeitsweise: "steuerbuero"`; `/api/datev/uebersicht` für die Kanzlei mit `X-Mandant` liefert `wer: "kanzlei"`.

- [ ] **Step 4: Push**

```bash
git push gitlab HEAD:main
```
