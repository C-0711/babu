<!-- Planungsagent (Sonnet), 02.09.2026, Stand d163ac6 -->

# Implementierungsplan: SKR04-Konten + DATEV-Wissen im Kontext

Alle Pfade absolut ab `/Users/christophbertsch/babu/.claude/worktrees/project-handover-context-7bfaa2`. Zeilennummern Stand `d163ac6` (aus dem Kompendium), zusätzlich selbst verifiziert. Nur Lesen — es wurde nichts verändert.

## 0. Architekturentscheidung (Design-Frage 1+2 aus dem Planauftrag)

**Zwei getrennte, additive Bausteine, keine Vermischung:**

1. **SKR04-Konten → das bestehende, read-only Host-Kompendium** (`~/kompendium` auf H200V, im Container `:ro` gemountet, `server/docker/compose.yml:36`). Ein neues Build-Skript läuft **auf dem Host**, hängt Atome an `atome.jsonl`/`vektoren.npy` an. Kein Container-Code ändert sich für die Konten selbst — nur `quelle`-Werte wählen, die `gemma_buchung.NACHSCHLAG_QUELLEN` (Zeilen 239-240) bereits per Substring matcht.
2. **Hochgeladene DATEV-Dokumente → ein neues, schreibbares Ablage-Fach** `wissen/` in der GitChain-Belegbox, nach demselben Sidecar-Muster wie Beleg-Embeddings (`review/<stamm>.embedding.json`) und Salon-Check-Klartexte (`*.text.json`). Rührt den `:ro`-Mount nicht an.

Beide Quellen werden in **einer** neuen Suchfunktion `babu_web._wissen_treffer()` zusammengeführt und zusätzlich zu `kompendium.suchen()` sowohl in `_recherche()` (Chat) als auch in `gemma_buchung.nachschlagen()` (Buchung) abgefragt — dieselbe Ergebnisform (`score, quelle, loc, text`) wie `kompendium.suchen()`, damit beide Aufrufer sie unverändert weiterverarbeiten können.

---

## Phase 1 — SKR04-Konten als Kompendium-Atome (Host-Build-Skript)

**Neue Datei (Repo, aber nur auf dem Host ausgeführt):** `werkzeuge/kompendium/skr04_atome_bauen.py`

Läuft **außerhalb** des Containers direkt auf der H200V (`python3 werkzeuge/kompendium/skr04_atome_bauen.py`), weil `~/kompendium` im Container `:ro` gemountet ist (`compose.yml:36`) — ein Container-Prozess kann dort nicht schreiben. Das Skript braucht Zugriff auf `EMBED_API` (Standard `http://127.0.0.1:11436/v1/embeddings`, auf dem Host direkt erreichbar da `network_mode: host`) und auf die Repo-Module `skr04_konten.py`, `skr04_automatik.py`, `kontierung.py` (liegen unter `server/belegreview/`, also `sys.path.insert(0, "server/belegreview")`).

**Ablauf:**

1. `import babu_web as bw` **nur** um `bw.embedding_rechnen` wiederzuverwenden (exakt das Muster aus `backfill_embeddings.py:16`) — identische Präfix-Konvention (`"title: none | text: …"`, `truncate_prompt_tokens: 2040`).
2. Für jedes Konto in `skr04_konten.KONTEN` (1516 Einträge, `{nr: name}`) und jedes Automatik-Konto in `skr04_automatik.AUTOMATIK` (`{nr: (art, satz, name)}`) einen Atom-Text bauen. Zwei `quelle`-Werte, beide bestehen `NACHSCHLAG_QUELLEN` per Substring ohne Code-Änderung:
   - `quelle="skr04-konten"` für jedes der 1516 Konten.
   - `quelle="skr04-automatik"` für die 183 Automatik-Konten (zusätzlich zum normalen Atom, da hier die Steuerautomatik das eigentliche Wissen ist).
   - `loc` = die Kontonummer selbst, z. B. `"Konto 6640"` — erscheint als Zitat `[skr04-konten · Konto 6640]` in Chat/Buchungs-Prompt.
3. **Atom-Text-Schema** (löst die im Planauftrag genannte Doppelanforderung „Welches Konto für Bewirtung?" **und** „Was ist Konto 6640?"): pro Konto ein Text mit zwei Sätzen — Aussage- und Frageform, denn EmbeddingGemma sucht am besten gegen ähnlich geformten Text:
   ```
   Konto 6640 im SKR04-Kontenrahmen: Bewirtung. Kontenklasse 6 (Betriebliche Aufwendungen).
   {AUTOMATIK-Zeile falls vorhanden: "Automatik Vorsteuer (AV) 19 %." bzw. "Automatik Umsatzsteuer (AM)."}
   {Babu-Kategorie-Zeile falls in kontierung._K per skr04-Feld == "6640" gefunden: "In babu die Kategorie „Bewirtung" — Bewirtungsbelege mit Kundinnen und Geschäftspartnern; 70 % abzugsfähig nach § 4 Abs. 5 Nr. 2 EStG." plus SKR03-Gegenstück "SKR03-Pendant: Konto 4650."}
   Frage: Welches Konto für Bewirtung? Antwort: Konto 6640 (Bewirtung).
   Frage: Was ist Konto 6640? Antwort: Bewirtung.
   ```
   Für die 1516−37 „reinen" DATEV-Konten (keine babu-Kategorie) entfällt der Kategorie-Absatz; Frage-Form bleibt (`"Frage: Was ist Konto {nr}? Antwort: {name}."`).
4. **`kontierung._K` als Brücke**: für jede `Kategorie` mit `geprueft=True` (Zeilen 70ff., z. B. `wareneinkauf→"5400"`, `bewirtung→"6640"`) das SKR04-Konto nachschlagen und den obigen Zusatzabsatz anhängen — das ist der Teil, der `"Welches Konto für Bewirtung?"` beantwortbar macht, nicht nur `"Was ist Konto 6640?"`.
5. **Reihenfolge/Invariante wahren** (`kompendium.py:51-52`): neue Atome nur **anhängen**, niemals bestehende Zeilen/Zeilen-Reihenfolge verändern. Skript liest zuerst die aktuelle Zeilenzahl von `atome.jsonl`, vergibt fortlaufende `id`, embettet, und schreibt:
   - `atome.jsonl` → `open(..., "a")`, eine Zeile je neues Atom.
   - `vektoren.npy` → `np.load(alt, mmap_mode=None)` (voll laden, nicht memmap, da wir schreiben), `np.concatenate([alt, neu])`, dann **atomar** speichern: erst `vektoren.npy.tmp` schreiben, dann `os.replace()` — ebenso `atome.jsonl.tmp` → `os.replace()`. Beide Ersetzungen möglichst dicht hintereinander (kein Lock zwischen Prozessen nötig, da nur ein Build-Lauf gleichzeitig läuft).
   - **L2-Normalisierung nicht vergessen** — `suchen()` normalisiert nur den Query-Vektor, nicht die Matrix (`kompendium.py:81`); jede neue Zeile muss vor dem Speichern durch ihre eigene Norm geteilt werden.
6. **Idempotenz**: Skript prüft vor dem Embedden, ob eine Zeile mit `quelle in ("skr04-konten","skr04-automatik")` und passendem `loc` schon existiert (einmal die komplette `atome.jsonl` einlesen) — sonst würde jeder Re-Lauf 1516 Atome duplizieren. Flag `--neu-bauen` erzwingt kompletten Ersatz (alte skr04-Atome per `id` herausfiltern, Rest neu anhängen — dann eine echte Neuschreibung beider Dateien, nicht nur Append).
7. `--probe`-Flag wie in `backfill_embeddings.py` — zählt nur, schreibt nichts.

**Grundwissen-Ergänzung** (Design-Frage 1, zweiter Teil): eine kompakte „Kontenübersicht" der ~37 babu-Kategorien (aus `kontierung._K`, nur `geprueft=True`) als neuer Abschnitt in `kontierung-grundwissen.md` (Host-Datei, `kompendium.kontierungswissen()` liest sie gecappt bei 30 000 Zeichen, `kompendium.py:109-117`). **Format:** eine Zeile je Kategorie, `"{name}: SKR04 {skr04} / SKR03 {skr03}"`, ca. 37 Zeilen × ~50 Zeichen ≈ 1900 Zeichen — unkritisch für den 30 000-Zeichen-Deckel und für den Prefix-Cache (dieser Block ist ohnehin schon byte-stabil, siehe `gemma_buchung.system_text` Docstring). **Nicht** die 1516 SKR04-Konten dort hineinschreiben — das würde den Deckel sprengen und ist genau der Fall, für den die Vektorsuche existiert. Diese Datei liegt ebenfalls nur auf dem Host; Änderung erfolgt manuell oder durch eine kleine Erweiterung desselben Build-Skripts (`--grundwissen-anhaengen`).

**Nach dem Host-Rebuild zwingend:** `kompendium._VEKTOREN` ist ein Prozess-globaler Zustand, der nur einmal pro Prozess geladen wird (`_laden()`, Zeile 34-35 „danach kostenlos"). Ein laufender `babu-web`-Container merkt einen Kompendium-Rebuild **nicht**, bis er neu startet. Deploy-Ritual-Zusatz: nach jedem Kompendium-Rebuild `docker compose restart babu-web` (oder ein regulärer Redeploy) einplanen — sonst bleiben die neuen Atome bis zum nächsten ohnehin fälligen Deploy unsichtbar.

---

## Phase 2 — Datenformat und Backend-Modul für hochgeladene DATEV-Dokumente

**Neue Datei:** `server/belegreview/datev_wissen.py` (reine Logik + Text-Chunking, kein Flask/FastAPI-Zustand — Modulname bewusst *nicht* `wissen.py`, das ist bereits das Fallwissen-Modul für den Chat, `wissen.py:1-13`, unrelated).

### 2.1 Themen

```python
THEMEN: dict[str, tuple[str, tuple[str, ...]]] = {
    "kontenrahmen":   ("Kontenrahmen", ("kontenrahmen", "skr04", "skr03",
                        "kontenplan", "sachkonto", "kontenklasse")),
    "steuerschluessel": ("Steuerschlüssel", ("steuerschlüssel", "steuerschluessel",
                        "automatikkonto", "vorsteuerschlüssel", "buchungsschlüssel")),
    "buchungsstapel": ("Buchungsstapel und Schnittstelle", ("buchungsstapel", "extf",
                        "schnittstelle", "datev-format", "stapelbeschreibung")),
    "afa":            ("Anlagen und AfA", ("afa", "absetzung für abnutzung",
                        "nutzungsdauer", "anlagevermögen", "abschreibung", "gwg")),
    "umsatzsteuer":   ("Umsatzsteuer", ("umsatzsteuer", "vorsteuer", "ustva",
                        "reverse charge", "innergemeinschaftlich")),
    "lohn":           ("Lohn", ("lohnsteuer", "lohnabrechnung", "sozialversicherung",
                        "minijob", "lohnkonto")),
    "jahresabschluss": ("Jahresabschluss und EÜR", ("jahresabschluss", "eür", "euer",
                        "bilanz", "gewinnermittlung", "susa", "bwa")),
    "sonstiges":      ("Sonstiges", ()),
}
```

`thema_erkennen(text: str) -> str` — gewichtete Substring-Suche wie `einsortieren._punkte` (Zeilen 92-105), aber ohne Gewichte (ein Treffer zählt), Rückgabe des Themas mit den meisten Treffern in `text[:4000].lower()`; `"sonstiges"` bei Gleichstand 0.

### 2.2 Text-Extraktion mit Seitenbezug

`seiten_lesen(pfad: str | Path) -> list[str]` — anders als `babu_web.klartext_der_unterlage` (Zeile 4118), das **eine** Gesamtzeichenkette liefert, braucht die Wissensschicht den **Seitenbezug** für Zitate. Neue Funktion, dieselben Bausteine wiederverwendend:

- `.pdf`: `abschluss_lesen.seiten_text(pfad)` (Seite-für-Seite, Cap `SEITEN_CAP=40` in `abschluss_lesen.py:19`, hier zusätzlich `WISSEN_SEITEN_MAX = 120` als eigener Deckel für sehr lange DATEV-Handbücher). Für jede Seite mit `len(text.strip()) < TEXTEBENE_SCHWELLE` (120, wie `babu_web.py:4086`) und solange nicht mehr als `WISSEN_OCR_MAX = 20` Seiten bereits per OCR gelesen wurden: einzelne Seite rendern (`abschluss_lesen.seiten_bilder(pfad)[i]`) und über `babu_web._ocr_seite(jpeg, name)` (Zeile 4093, per Gemma multimodal abschreiben) lesen — **lazy import** `import babu_web as bw` innerhalb der Funktion, exakt das in `gemma_buchung.py` etablierte Muster gegen Zirkelimporte.
- `.md` / `.txt`: Datei komplett als eine „Seite" lesen (kein PDF-Rendering nötig) — deckt den Bulk-Import aus `~/JennyfromtheBlock/datev/hilfe-center/*.md` ab (siehe Phase 7).
- `.jpg`/`.jpeg`/`.png`: eine Seite, direkt über `_ocr_seite`.
- Jede LLM-Lese-Operation (OCR-Aufruf) läuft unter `babu_web._LLM_SEMAPHORE` — das ist Sache des **Aufrufers** (`_wissen_job`, Phase 3), nicht dieser reinen Funktion, damit `datev_wissen.py` ohne Server-Zustand testbar bleibt.

### 2.3 Chunking

`atome_bauen(seiten: list[str]) -> list[dict]` — reine Funktion, keine I/O:

```python
WISSEN_CHUNK_ZEICHEN = 3200   # ~800 Token bei ~4 Zeichen/Token
WISSEN_CHUNK_MIN = 200        # kürzere Rest-Absätze nicht als eigenes Atom
WISSEN_ATOME_MAX = 400        # Deckel je Dokument
```

Je Seite: Text an Leerzeilen in Absätze splitten (`re.split(r"\n\s*\n", seite)`), Absätze greedy zu Blöcken von bis zu `WISSEN_CHUNK_ZEICHEN` zusammenfassen; jeder Block wird ein Atom `{"loc": f"S{seitennr}#{index_in_seite}", "text": block}` — dieselbe `"S{n}#{i}"`-Konvention wie im Kompendium-Test-Fixture (`tests/test_kompendium.py:24-28`, `"loc":"S1#0"`). Abbruch bei `WISSEN_ATOME_MAX` mit Log-Hinweis (Rest des Dokuments bleibt unindiziert, aber die Datei selbst bleibt vollständig einsehbar).

### 2.4 Speicherformat (git, im `wissen/`-Baum der Belegbox)

Für einen Upload `wissen/<thema>/<dateiname>` (Dateiname via `boxschreiber.beleg_dateiname(name)`, gleiches Schema wie überall):

| Datei | Inhalt |
|---|---|
| `wissen/<thema>/<dateiname>` | Originalbytes (pdf/jpg/png/md/txt) |
| `wissen/<thema>/<dateiname>.meta.json` | `{"titel","thema","von","hochgeladen_am","seiten","absaetze","status": "wird eingelesen"\|"eingelesen"\|"fehler","hinweis"}` |
| `wissen/<thema>/<dateiname>.text.json` | `{"text": "<gesamter Klartext>"}` — **exakt** dieselbe Sidecar-Konvention wie `_abschluss_klartexte()` (`babu_web.py:5859-5875`) erwartet |
| `wissen/<thema>/<dateiname>.atome.json` | `[{"loc","text","vektor","modell","dim"}, …]` |

**Wichtiger Fund (spart Code):** `_abschluss_klartexte()` filtert nur auf `pfad.endswith(".text.json")` — **ohne** Präfix-Einschränkung (`babu_web.py:5865-5875`). Ein `wissen/<thema>/<datei>.text.json` wird also **ohne jede Code-Änderung** von der bestehenden Ablage-Stichwortsuche (`api_ablage_suche`/`_durchsuchbarer_text`, Zeilen 5872-5900) mit erfasst. Nur `.meta.json` ist ohnehin schon global ausgeschlossen; **einzig `.atome.json` muss neu zur Sidecar-Ausschlussliste** in `_ablage_eintraege()` (Zeile 5671-5673, aktuell `(".umsaetze.json", ".meta.json", ".erklaerung.json", ".text.json", ".aenderungen.json")`) hinzugefügt werden — sonst erscheint es fälschlich als eigener Ablage-Eintrag.

---

## Phase 3 — Route, Hintergrund-Job, Ablage-Integration (alles in `server/belegreview/babu_web.py`)

### 3.1 Konstanten (neben den bestehenden Analoga platzieren)

```python
WISSEN_ENDUNGEN = DOKUMENT_ENDUNGEN | {".md", ".txt"}          # neben Zeile 2224
WISSEN_MAX = 80 * 1024 * 1024                                   # neben ABSCHLUSS_MAX, Zeile 4061
WISSEN_TMP = Path(os.environ.get("BABU_WISSEN_TMP",
                  str(Path.home() / "babu-web" / "wissen-tmp"))) # neben ABSCHLUSS_TMP, Zeile 4062
```

`ABLAGE_ARTEN` (Zeile 5551-5570) neuer Eintrag:
```python
"wissen": ("Wissen", "Nachschlagewerk zu Kontenrahmen, Steuer und DATEV"),
```
`ABLAGE_PFAD_RE` (Zeile 2231-2233) — `"wissen"` in die Alternation aufnehmen, sonst schlägt `/api/dokument/{pfad}` und `/api/vorschau/{pfad}` für jede hochgeladene Datei fehl.

### 3.2 Route `POST /api/wissen`

```python
@app.post("/api/wissen")
async def api_wissen_hochladen(request: Request, name: str = "dokument.pdf",
                               titel: str = "", thema: str = "") -> Response:
```
Ablauf (Muster aus `api_dokument_hochladen`, Zeile 2390-2434, und `api_abschluss_hochladen`, Zeile 4470-4505):
1. `_box_wache`.
2. Endung gegen `WISSEN_ENDUNGEN` prüfen.
3. `daten = await koerper_lesen(request, WISSEN_MAX)`.
4. `_blob_schon_da(daten)` — **Ausschlussliste dort (Zeile 5746-5747) um `".atome.json"` erweitern**, sonst könnte ein zufällig namensgleicher Vektor-Sidecar fälschlich als „schon hochgeladen" erkannt werden.
5. Thema bestimmen: wenn `thema not in datev_wissen.THEMEN`, synchron die ersten 3 Seiten lesen (`abschluss_lesen.seiten_text` über eine `NamedTemporaryFile`, exakt das Muster aus `/api/aufnahme`, Zeilen 1855-1864) und `datev_wissen.thema_erkennen(text)` aufrufen — **kein** LLM-Aufruf in der Request-Handler-Zeit, nur PDF-Textlage (schnell). Bei reinem Scan ohne Textlage: Fallback `"sonstiges"`.
6. `dateiname = boxschreiber.beleg_dateiname(name)`; `pfad = f"wissen/{thema}/{dateiname}"`.
7. Erst-Commit: `{pfad: daten, pfad+".meta.json": json.dumps({"titel": (titel or name)[:120], "thema": thema, "von": un, "hochgeladen_am": _jetzt_iso(), "status": "wird eingelesen"}, ensure_ascii=False, indent=1).encode()}` via `boxschreiber.schreiben` (ein Commit, wie überall).
8. `_INDEX["geprueft"] = 0.0` invalidieren.
9. `threading.Thread(target=_wissen_job, args=(pfad, daten, thema, un), daemon=True).start()`.
10. Antwort `{"ok": True, "commit", "pfad", "thema": thema}`.

### 3.3 Hintergrund-Job `_wissen_job(pfad: str, daten: bytes, thema: str, un: str) -> None`

Platzierung neben `_abschluss_job` (Zeile 4389), gleiches Fehler-Idiom (`try/except Exception`, nie den Prozess mitreißen):

```python
_WISSEN_LOCK = threading.Lock()
_WISSEN_JOBS: dict[str, dict] = {}   # pfad -> {"stand","eingelesen","gesamt","hinweis"}
```

1. `_WISSEN_JOBS[pfad] = {"stand": "liest", "eingelesen": 0, "gesamt": 0}`.
2. Bytes nach `WISSEN_TMP / _un_ordner(un) / Path(pfad).name` schreiben (Ordner anlegen), Datei am Ende löschen (`finally`).
3. `seiten = datev_wissen.seiten_lesen(tmp_pfad)` — OCR-Aufrufe darin laufen unter `with _LLM_SEMAPHORE:` (Semaphore wird als Parameter oder per lazy `import babu_web` in `datev_wissen._ocr_seite`-Aufruf gehalten — sauberer: `datev_wissen.seiten_lesen` bekommt einen optionalen `ocr: Callable[[bytes,str],str]`-Parameter, den `_wissen_job` als `lambda j,n: (_LLM_SEMAPHORE, babu_web._ocr_seite(j,n))`-Wrapper übergibt, damit das Semaphore nicht ins reine Modul einziehen muss).
4. `atome_roh = datev_wissen.atome_bauen(seiten)`; `_WISSEN_JOBS[pfad]["gesamt"] = len(atome_roh)`.
5. Für jedes Atom: `with _LLM_SEMAPHORE: v = embedding_rechnen(atom["text"], als_dokument=True)`; bei `None` überspringen und loggen (Dienst kurz weg darf den Rest nicht kippen — Muster aus `backfill_embeddings.py:50-53`); sonst `atome.append({**atom, **v})`; nach jedem Atom `_WISSEN_JOBS[pfad]["eingelesen"] += 1` (billiger In-Memory-Zähler, kein DB-Write nötig — Job ist kurzlebig, anders als der Salon-Check).
6. Abschluss-Commit (ein `boxschreiber.schreiben`-Aufruf, drei Dateien):
   ```python
   {pfad+".text.json": json.dumps({"text": "\n\n".join(seiten)}, ensure_ascii=False).encode(),
    pfad+".atome.json": json.dumps(atome, ensure_ascii=False).encode(),
    pfad+".meta.json": json.dumps({**alt_meta, "status": "eingelesen",
                                    "seiten": len(seiten), "absaetze": len(atome)},
                                   ensure_ascii=False, indent=1).encode()}
   ```
   `alt_meta` vorher per `git_show(pfad+".meta.json")` lesen (Titel/Thema/von nicht verlieren) — Muster aus `_beiakte_aendern`, Zeile 5910-5921.
7. `_INDEX["geprueft"] = 0.0`; `_WISSEN_JOBS[pfad]["stand"] = "fertig"`.
8. Bei Exception: Meta-Commit mit `"status": "fehler", "hinweis": "Das hat gerade nicht geklappt — versuch es später nochmal."` (gleicher Wortlaut wie `_abschluss_job`, Zeile 4460-4461), damit die UI-Sprache konsistent bleibt.

### 3.4 Fortschritts-Route

```python
@app.get("/api/wissen/status")
def api_wissen_status(request: Request, pfad: str = "") -> Response:
```
`_box_wache`, Pfad gegen `^wissen/[A-Za-z0-9._/ -]{1,200}$` prüfen, dann `_WISSEN_JOBS.get(pfad) or {"stand": "unbekannt"}` zurückgeben — reiner In-Memory-Read, kein Git-Zugriff, für das Polling aus der Karte („wird eingelesen … n/m").

### 3.5 Suchindex `_wissen_vektoren()` / `_wissen_treffer()`

Direkt neben `_beleg_vektoren()` (Zeile 2136-2169), gleiches HEAD-Keying-Muster:

```python
_WISSEN_VEKTOREN: tuple[str | None, list[dict], object] = (None, [], None)

def _wissen_vektoren() -> tuple[list[dict], object]:
    """Alle Vektoren aus wissen/*/*.atome.json — je Box-Stand einmal gebaut."""
    global _WISSEN_VEKTOREN
    ...  # git ls-tree -r HEAD, Filter auf "wissen/" + ".atome.json"
    # je Atom: meta.append({"score" wird erst in _wissen_treffer gesetzt,
    #   "quelle": f"wissen:{thema}", "loc": a["loc"], "text": a["text"],
    #   "thema": thema, "titel": <aus .meta.json>, "pfad": pfad})


def _wissen_treffer(frage_vektor: list[float], k: int = 5) -> list[dict]:
    """Gleiche Rückgabeform wie kompendium.suchen(): score, quelle, loc, text
    (+ thema, titel, pfad für spätere UI-Zitate)."""
```

`quelle` bekommt bewusst das Präfix `"wissen:"` (technisch, nicht UI-sichtbar — die Zitate `[quelle · loc]` landen nur im LLM-Prompt, portal.html rendert sie nirgends, geprüft: kein `"NACHGESCHLAGEN"`-Treffer in `portal.html`). Das erlaubt in `gemma_buchung.py` **eine** Ein-Zeilen-Änderung:

```python
NACHSCHLAG_QUELLEN = ("afa", "kontenplan", "skr04", "skr03", "bmf",
                      "ustg", "estg", "kontenrahmen", "steuerschluessel", "wissen")
```

### 3.6 Ablage-Integration

`_wissen_beiakten() -> dict[str, dict]` — exakte Kopie des Musters `_abschluss_beiakten()` (Zeile 5592-5616), nur mit Filter `pfad.startswith("wissen/") and pfad.endswith(".meta.json")`.

In `_ablage_eintraege()` (Zeile 5627-5721):
- Skip-Tuple (Zeile 5671-5672) um `".atome.json"` erweitern.
- Neuer `elif`-Zweig vor dem abschließenden `else: continue` (nach der `bwa/`-Verzweigung, Zeile 5703-5710):
  ```python
  elif pfad.startswith("wissen/"):
      beiakte = _wissen_beiakten().get(pfad) or {}
      art = "wissen"
      titel = beiakte.get("titel") or name
  ```
  Danach beim finalen `eintraege.append(...)` (Zeile 5716-5720) zusätzlich `thema=pfad.split("/")[1]` und `status=beiakte.get("status")` mitgeben, damit die Karte „wird eingelesen" anzeigen kann.

**Offene Design-Frage (im Planauftrag als solche markiert):** Soll „Thema" eine echte dritte Baum-Ebene in `/api/ablage` werden (Jahr → Fach → Thema → Stücke), oder reicht ein flaches Fach „Wissen" mit Thema als Chip/Filter auf der Karte? **Empfehlung:** flach + Chip (Punkt 3.6 oben) für Version 1 — verändert die API-Form von `/api/ablage` nicht (`arten: [{art,name,hinweis,anzahl,stuecke}]` bleibt stabil), Thema-Filter läuft rein clientseitig über `stuecke.filter(s => s.thema === x)`. Eine echte dritte Ebene ist mit vertretbarem Aufwand nachrüstbar, aber nicht für die erste Iteration nötig.

**Löschen (optional, niedrige Priorität):** DATEV-Referenzdokumente sind keine GoBD-Belege der Nutzerin — `loeschbar: True` ist vertretbar. Neue Route `POST /api/wissen-loeschen` nach dem Muster von `/api/kontoauszug`-Löschen (Zeile ~2360-2387): `boxschreiber.loeschen([pfad, pfad+".meta.json", pfad+".text.json", pfad+".atome.json"], ...)`. Kann in einer Folge-Iteration nachgezogen werden, ist für „hochladen, sortiert, im Kontext" nicht Voraussetzung.

---

## Phase 4 — Suchzusammenführung (Chat + Buchung)

### 4.1 Chat — `_recherche()` (`babu_web.py:2172-2212`)

Zeile 2185-2186 ändern von
```python
treffer = [t for t in kompendium.suchen(emb["vektor"], k=5) if t["score"] >= 0.30]
```
zu
```python
treffer = sorted(
    (t for t in kompendium.suchen(emb["vektor"], k=5) + _wissen_treffer(emb["vektor"], k=5)
     if t["score"] >= 0.30),
    key=lambda t: -t["score"])[:5]
```
Rest der Funktion (Rendering `f"[{t['quelle']} · {t['loc']}] " + …[:600]`, Zeilen 2188-2191) bleibt **unverändert** — funktioniert automatisch für beide Quellen, weil `_wissen_treffer` dieselbe Dict-Form liefert.

### 4.2 Buchung — `gemma_buchung.nachschlagen()` (`gemma_buchung.py:260-299`)

Zeile 292-295 ändern von
```python
treffer = [t for t in kompendium.suchen(emb["vektor"], k=k)
           if t["score"] >= NACHSCHLAG_SCHWELLE
           and any(q in (t["quelle"] or "").lower() for q in NACHSCHLAG_QUELLEN)][:2]
```
zu
```python
treffer = [t for t in kompendium.suchen(emb["vektor"], k=k) + bw._wissen_treffer(emb["vektor"], k=k)
           if t["score"] >= NACHSCHLAG_SCHWELLE
           and any(q in (t["quelle"] or "").lower() for q in NACHSCHLAG_QUELLEN)][:2]
```
`bw` ist bereits als `import babu_web as bw` innerhalb der Funktion vorhanden (Zeile ~266). Plus die Ein-Zeilen-Erweiterung von `NACHSCHLAG_QUELLEN` um `"wissen"` (Abschnitt 3.5).

### 4.3 Zitat-Anzeige im Chat (Design-Frage 3, „Nachgeschlagen in: …"-Chips)

Aktuell rendert `portal.html` keine strukturierten Quellen-Chips — die `[quelle · loc]`-Klammern sind reiner Prompt-Text fürs Modell, Nina sieht nur die (paraphrasierte) Antwort. Um „Nachgeschlagen in: …"-Chips **sichtbar** zu machen, müsste `/chat` zusätzlich zur Textantwort eine strukturierte Quellenliste mitschicken (SSE-Event oder Antwortfeld) und `portal.html` müsste sie rendern. Das ist eine **separate, größere UI-Änderung** (SSE-Protokoll, Chat-Rendering) und nicht Voraussetzung für „kommt in den Kontext" — **als optionale Folgearbeit markiert**, nicht Teil dieser Phasen 1-4.

---

## Phase 5 — Frontend (`server/belegreview/portal.html`)

1. **`ABLAGE_SYMBOL`** (Icon-Map, referenziert in `ablageBaumZeichnen`, Zeile 2635-2646) — neuer Eintrag `wissen: "buch"` o. ä. vorhandenes Icon.
2. **`ABLAGE_NAME`** (Zeile 2593-2595, für „Verschieben"-Dialog) — `wissen: "Wissen"` ergänzen.
3. **Upload-Chip** neben „Vertrag ablegen" (Zeile 1081): `<button class="chip" id="ablage-wissen">DATEV-Dokument ablegen</button>` + verstecktes `<input type="file" id="wissen-datei" accept=".pdf,.jpg,.jpeg,.png,.md,.txt,application/pdf,image/*" hidden>`. Vor dem Senden ein **Thema-Auswahlfeld** (einfaches `<select>` mit den 8 `THEMEN`-Labels, Default „wird erkannt") — analog zum bestehenden `prompt()`-Dialog in `ablageVerschieben` (Zeile 2790-2799), aber als kleines Inline-`<select>` statt `prompt()`, damit die Nutzerin vor dem Hochladen wählen kann; bei „wird erkannt" bleibt `thema`-Parameter leer und der Server klassifiziert automatisch (Abschnitt 3.2 Schritt 5).
4. **Wiring** (Muster aus Zeile 2894-2904, Vertrag-Upload):
   ```js
   $("#ablage-wissen").addEventListener("click", () => $("#wissen-datei").click());
   $("#wissen-datei").addEventListener("change", async ev => {
     const datei = ev.target.files[0]; ev.target.value = "";
     if (!datei) return;
     const thema = $("#wissen-thema").value;  // "" oder ein THEMEN-Key
     const a = await hochladenMitBalken(datei,
       "/api/wissen?name=" + encodeURIComponent(datei.name)
         + (thema ? "&thema=" + encodeURIComponent(thema) : "")
         + "&titel=" + encodeURIComponent(datei.name),
       $("#ablage-hochladen"), {fertigSatz: "abgelegt, wird eingelesen"});
     if (a.ok){ setTimeout(ladeAblage, 1500); setTimeout(ladeAblage, 20000); }
   });
   ```
   Identisches Nachlade-Muster wie beim Vertrag (Zeile 2905) — **keine** neue Status-Route zwingend nötig fürs UI, `ladeAblage()` holt den aktuellen `.meta.json`-Status über `_ablage_eintraege()` mit. Die `/api/wissen/status`-Route aus Abschnitt 3.4 ist die Grundlage für einen **optionalen** Live-Zähler „n/m Absätze" während des Laufs, z. B. per `setInterval` alle 3 s solange `status !== "fertig"/"fehler"` — Zusatz, kein Blocker.
5. **Karte** (`ablageKachel`, Zeile 2676-2694): `marke`-Zeile erweitern um den Fall `s.status === "wird eingelesen"` → `<span class="marke">wird eingelesen</span>`; Thema als zusätzliche Zeile `<div class="wann">${esc(THEMA_NAME[s.thema] || "")}</div>` neben dem Datum.
6. **UI-Sprachregel beachten** (CLAUDE.md): kein „Embedding", kein „Vektor", kein „Atom" in sichtbaren Texten — durchgängig „Nachschlagewerk" / „eingelesen" / „Absätze" verwenden, wie im Planauftrag vorgegeben.

---

## Phase 6 — Tests

Alle mit `/tmp/babu-venv/bin/python -m pytest tests/` aus `server/belegreview/` ausführbar; bestehende Suite bleibt grün (1608 Tests, Stand Erkundung).

**Neue Dateien:**

- `tests/test_skr04_atome.py` — Unit-Tests für `werkzeuge/kompendium/skr04_atome_bauen.py`: Atom-Text enthält Frage- und Aussageform; `quelle` ist `"skr04-konten"`/`"skr04-automatik"`; Idempotenz (zweiter Lauf ohne `--neu-bauen` fügt nichts doppelt hinzu); Invariante `len(jsonl) == vektoren.shape[0]` nach dem Lauf; L2-Norm jeder neuen Zeile ≈ 1.0.
- `tests/test_datev_wissen.py` — reine Logik aus `datev_wissen.py`: `thema_erkennen()` für typische Titelzeilen jedes Themas; `atome_bauen()` — Chunk-Grenzen (`WISSEN_CHUNK_ZEICHEN`), `loc`-Format `"S{n}#{i}"`, Deckel `WISSEN_ATOME_MAX` greift; `seiten_lesen()` für `.md`/`.txt` liefert eine „Seite" mit dem vollen Text.
- `tests/test_wissen_upload.py` — Routen-Test mit dem `welt`-Fixture-Muster aus `tests/test_dokumente.py:14-40` (echtes bare Git-Repo in `tmp_path`, `TestClient`): `POST /api/wissen` legt Datei + `.meta.json` in einem Commit ab; Thema-Autoerkennung ohne `thema`-Parameter; `_blob_schon_da`-Dublettenschutz greift auch hier; nach synchronem Aufruf von `_wissen_job` (Embedding-Aufruf gemonkeypatcht wie in `test_kompendium.py:96-100`) liegen `.text.json` und `.atome.json` im Store; `GET /api/ablage` zeigt den Eintrag im Fach `"wissen"`; `GET /api/ablage/suche?q=<Wort aus dem Text>` findet ihn (Beweis für die `.text.json`-Wiederverwendung ohne Codeänderung in `_abschluss_klartexte`).
- `tests/test_kompendium.py` erweitern: neuer Test `test_recherche_findet_wissen_atome` (gemonkeypatchte `_wissen_vektoren`, analog zu `test_recherche_bringt_kompendium_und_eigene_belege`, Zeile 90-113) — beweist, dass `_recherche()` Kompendium- und Wissen-Treffer zusammenführt und nach Score sortiert.
- `tests/test_kompendium.py` (dieselbe Datei, dort liegen bereits die `nachschlagen`-Tests, Zeilen 195-231) erweitern: `test_nachschlagen_findet_wissen_quelle` — `quelle="wissen:kontenrahmen"` passiert den `NACHSCHLAG_QUELLEN`-Filter.

**Bestehende Tests, die den Vertrag der geänderten Funktionen prüfen und weiter grün bleiben müssen:** `tests/test_kompendium.py` (alle bisherigen), `tests/test_gemma_buchung.py`, `tests/test_ablage_ordner.py`, `tests/test_dokumente.py`.

---

## Phase 7 — Bulk-Import für `~/JennyfromtheBlock/datev`

**Neues Skript:** `werkzeuge/wissen-import/datev_ordner_hochladen.py` — Mac-seitig, iteriert `~/JennyfromtheBlock/datev/*.pdf` und `~/JennyfromtheBlock/datev/hilfe-center/*.md`, postet jede Datei per `requests.post("https://babu.0711.io/api/wissen", ..., headers={"Authorization": f"Bearer {pat}"})` — nutzt exakt denselben Auth-Weg wie die App (`babu_web.angemeldet`, Zeile 417-426: „Cookie ODER Bearer"), **kein neuer Code am Server nötig** für den CLI/rsync-freien Zugang, der im Planauftrag gefordert ist. PAT-Beschaffung wie in `HANDOVER.md` Abschnitt 5 beschrieben (`pat_minten.py --zeigen --geraet`), **niemals** den PAT-Wert ausgeben oder ins Skript hart codieren (Sicherheitsregel aus `CLAUDE.md`) — Skript liest ihn aus der Keychain oder fragt ihn interaktiv ab, ohne ihn zu loggen.

`thema` wird beim Bulk-Import leer gelassen (Server-Autoerkennung) außer bei eindeutig benannten Dateien (`0907048*` → „Steuerschlüssel", `0907108*` → „Kontenrahmenänderungen" laut Erkundung) — dort kann das Skript das Thema direkt mitgeben, um Fehlklassifikation zu vermeiden. Testdaten-Regel aus `CLAUDE.md` „Bekannte Fallen" beachten: **echte Salon-/Bankdaten aus `~/Downloads` niemals hochladen** — das betrifft dieses Skript nicht (DATEV-Referenzdokumente sind keine Salon-Daten), aber es sollte hart auf `~/JennyfromtheBlock/datev/` beschränkt bleiben (kein rekursiver Home-Scan).

---

## Phase 8 — Rollout, Betrieb, Verifikation

**Reihenfolge:**
1. Phase 2-6 (Wissen-Upload, Suche, Tests) zuerst deployen — reine Zusatzfunktion, keine Migration bestehender Daten, geringes Risiko.
2. Phase 1 (SKR04-Atome) danach auf dem Host bauen, **außerhalb** des normalen Deploy-Rituals, da das Skript nicht im Container läuft.
3. Nach dem Kompendium-Rebuild: `docker compose restart babu-web` (Phase 1, letzter Absatz).

**Deploy-Ritual für Phase 2-6 (verbindlich laut CLAUDE.md, vollständig, kein Verkürzen):**
1. Golden vorher: `GET /api/belege` + `GET /api/abgleich/<aktueller Monat>` als `python3 -m json.tool --sort-keys` sichern.
2. `rsync server/ h200v:~/babu-docker/`.
3. `ssh h200v 'cd ~/babu-docker/docker && docker compose build && docker compose up -d'`.
4. Golden nachher byte-diffen — muss identisch sein, da Phase 2-6 additiv sind (neue Route, neues Fach, keine bestehenden Antwortformen geändert außer der internen `_recherche`/`nachschlagen`-Quellenliste, die nicht in `/api/belege` oder `/api/abgleich` auftaucht).
5. Live-Rauchtest der geänderten/neuen Routen:
   - `POST /api/wissen` mit einer kleinen Test-PDF (Testkonto, nicht Ninas Box) → Commit sichtbar, `GET /api/ablage` zeigt Fach „Wissen".
   - `GET /api/wissen/status?pfad=...` liefert `"stand":"fertig"` nach Abschluss.
   - `GET /api/ablage/suche?q=<Stichwort aus der Test-PDF>` findet den Eintrag.
   - `POST /chat` mit einer Frage, deren Antwort nur im hochgeladenen Dokument steht → Antwort muss den Inhalt sinngemäß wiedergeben (Beweis, dass `_wissen_treffer` in `_recherche` ankommt).
6. Für Phase 1 zusätzlich: eine reale Buchung mit einem Beleg, dessen Kategorie ein „reines" SKR04-Konto ohne babu-Kategorie betrifft (z. B. ein seltenes Konto), gegen das gebucht wird, und prüfen, dass `NACHSCHLAG_QUELLEN`-Treffer aus `skr04-konten` im Buchungs-Prompt auftauchen (Server-Log oder `gemma_buchung.voller_prompt`-Debug-Ausgabe, nicht live an Nina).

**Sicherheits-/Betriebsregeln, die die neue Route erben muss:**
- `_box_wache` sichert `/api/wissen` und `/api/wissen/status` (nicht `ERLAUBT`-Liste direkt) — verbindlich laut CLAUDE.md „Neue Routen immer über `_box_wache`/`box_mitglied` absichern".
- Kein Passwort-/Token-Handling in den neuen Skripten (Phase 1, Phase 7) — nur Länge/Status, PAT bleibt Keychain-only.
- `docker compose down`/`pm2 start babu-web` bleibt Rückweg — von den neuen Routen unberührt, da sie Teil desselben `babu-web`-Prozesses sind.

---

## Risiken

1. **Kompendium-Invariante verletzt** (`kompendium.py:51-52`): ein fehlerhafter Host-Lauf (z. B. Abbruch zwischen `atome.jsonl`- und `vektoren.npy`-Ersetzung) macht das **gesamte** Kompendium stumm, nicht nur die SKR04-Atome — betrifft dann auch Chat und Buchung komplett. Gegenmaßnahme: Skript prüft nach dem Schreiben beide Dateien erneut ein (`_laden()`-Logik nachbilden) und bricht mit klarer Fehlermeldung ab, **bevor** es den alten Stand überschreibt (Backup der alten `atome.jsonl`/`vektoren.npy` vor dem `os.replace()`).
2. **Kosten/Dauer des Wissen-Jobs**: ein 100+-seitiges DATEV-Handbuch kann 100-300 Embedding-Aufrufe auslösen, jeder seriell unter `_LLM_SEMAPHORE` — mehrere Minuten Laufzeit, während der andere `_LLM_SEMAPHORE`-Nutzer (Buchung, Chat-OCR, Salon-Check) warten. `WISSEN_ATOME_MAX=400` und `WISSEN_SEITEN_MAX=120` begrenzen den Worst Case; bei Bedarf könnte man den Job künftig auf Zeiten geringer Last beschränken (nicht Teil dieses Plans).
3. **Fehlklassifikation des Themas**: die Stichwortliste in Abschnitt 2.1 ist ein erster Entwurf, keine geprüfte Taxonomie — falsch einsortierte Dokumente sind über „Verschieben" korrigierbar, sobald Phase 3.6/5 auch für `wissen/` freigeschaltet ist (aktuell ist `ablageWerkzeug`, Zeile 2707, nur für `^(dokumente|abschluss)/` aktiv — **muss um `wissen` erweitert werden**, sonst gibt es keinen manuellen Korrekturweg, was Design-Frage 2 explizit fordert). Ergänzend: `ABLAGE_BEIAKTE_RE` (Zeile 5908-5909) und `api_ablage_verschieben`s `ABLAGE_ARTEN`-Prüfung (Zeile 5972 ff.) müssen `"wissen"` als gültiges Ziel zulassen (aktuell nur `art != "beleg"` ausgeschlossen — `"wissen"` würde also schon durchgehen, sobald es in `ABLAGE_ARTEN` steht; nur `ablageWerkzeug`s Pfad-Regex im Frontend blockiert noch).
4. **Große Wissensbasis verwässert die Buchungssuche**: `nachschlagen()`s Kommentar (Zeilen 233-238) beschreibt bereits, dass die Frageform alle Kompendium-Treffer auf ~0,42 hebt — mit zusätzlichen `wissen:`-Atomen wächst die Kandidatenmenge; der bestehende Quellenfilter (`NACHSCHLAG_QUELLEN`) bleibt die einzige Trennlinie und muss bei jedem neuen Thema-Slug reflektiert werden (z. B. würde `"lohn"` oder `"jahresabschluss"` NICHT automatisch in `NACHSCHLAG_QUELLEN` passen, da nur `"wissen"` als Substring geprüft wird — das ist beabsichtigt: **alle** Themen unter `wissen:` sind für die Buchung zulässig, nicht nur steuerliche; falls das zu unspezifisch wird, ist eine Verfeinerung auf `NACHSCHLAG_QUELLEN` mit `"wissen:kontenrahmen"`, `"wissen:steuerschluessel"` etc. statt nur `"wissen"` eine spätere Stellschraube — als offene Entscheidung markiert).

---

### Kritische Dateien für die Umsetzung

- `server/belegreview/babu_web.py` (neue Route `/api/wissen`, `/api/wissen/status`, `_wissen_job`, `_wissen_vektoren`/`_wissen_treffer`, Erweiterungen an `_recherche`, `ABLAGE_ARTEN`, `ABLAGE_PFAD_RE`, `_ablage_eintraege`, `_blob_schon_da`)
- `server/belegreview/gemma_buchung.py` (Erweiterung `NACHSCHLAG_QUELLEN`, `nachschlagen()`)
- `server/belegreview/kompendium.py` (Referenz für die Invariante, selbst unverändert)
- `server/belegreview/datev_wissen.py` (neu: Themen, Chunking, Seiten-Extraktion)
- `werkzeuge/kompendium/skr04_atome_bauen.py` (neu, Host-Build-Skript für SKR04-Atome)
- `server/belegreview/portal.html` (Ablage-Fach „Wissen", Upload-Chip, Thema-Auswahl, Kachel-Status)
- `server/belegreview/tests/test_kompendium.py`, neue `tests/test_datev_wissen.py`, `tests/test_wissen_upload.py`, `tests/test_skr04_atome.py`