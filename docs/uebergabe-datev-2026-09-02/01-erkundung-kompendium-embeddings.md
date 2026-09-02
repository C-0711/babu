# Kompendium — wie es gebaut, gelesen und benutzt wird

All paths absolute; base = `/Users/christophbertsch/babu/.claude/worktrees/project-handover-context-7bfaa2`.

---

## 1. `server/belegreview/kompendium.py` (118 lines — the whole module)

**Location on disk:** `VERZEICHNIS = Path(os.environ.get("KOMPENDIUM_DIR", str(Path.home() / "kompendium")))` — line 22-23. In the container that resolves to `/data/kompendium` because `compose.yml:24` sets `HOME: /data` and `server/docker/compose.yml:36` mounts `~/kompendium:/data/kompendium:ro`.

**Module state** (lines 25-28): `_LOCK` (threading.Lock), `_VEKTOREN` (numpy memmap), `_OFFSETS: list[int]`, `_TEXTE: dict[str,str]`.

**On-disk format:**
| file | format |
|---|---|
| `vektoren.npy` | fp32 `.npy`, shape `(n, d)`, **already L2-normalised** (comment line 26), loaded `np.load(npy, mmap_mode="r")` (line 44) |
| `atome.jsonl` | one JSON object per line; keys used: `id`, `quelle`, `loc`, `text` (see fixture `server/belegreview/tests/test_kompendium.py:24-31`) |
| `grundwissen.md` | plain markdown digest, read once, capped at 60 000 chars |
| `kontierung-grundwissen.md` | plain markdown, capped at 30 000 chars |

**Public functions:**

- `_laden() -> bool` (line 31): builds the byte-offset index by iterating `atome.jsonl` in binary once per process; **hard invariant at line 51-52: `len(offsets) != vektoren.shape[0]` → returns False and the whole Kompendium stays silent.** This is the constraint any atom-adding plan must respect — JSONL line count and npy row count must match exactly, in the same order.
- `atom(nr: int) -> dict | None` (line 58): `f.seek(_OFFSETS[nr]); json.loads(f.readline())`.
- `suchen(frage_vektor: list[float], k: int = 5) -> list[dict]` (line 69): brute-force cosine. `q = np.asarray(v, np.float32)`, `scores = _VEKTOREN @ (q / norm)` (line 81), `np.argsort(-scores)[:k]` (line 83). Returns dicts `{"score": round(...,4), "quelle", "loc", "text"}`. **No threshold inside** — thresholds live in the callers. Docstring: 89 760 vectors ≈ 20 ms.
- `grundwissen() -> str` (line 101) → `_datei("grundwissen.md", 60000)`.
- `kontierungswissen() -> str` (line 109) → `_datei("kontierung-grundwissen.md", 30000)`.
- `_datei(name, grenze)` (line 92) — private, caches in `_TEXTE`, swallows `OSError` → `""`.

**Query embedding** — done *outside* kompendium.py, in `server/belegreview/babu_web.py`:
- `EMBED_API = os.environ.get("EMBED_API", "http://127.0.0.1:11436/v1/embeddings")` — line 248
- `EMBED_MODELL = os.environ.get("EMBED_MODELL", "embeddinggemma")` — line 249
- `embedding_rechnen(text: str, als_dokument: bool = True) -> dict | None` — line 2113. POSTs `{"model", "input", "truncate_prompt_tokens": 2040}`, timeout 15 s, returns `{"modell", "dim", "vektor"}` or `None` on any exception.
  - **document prefix**: `f"title: none | text: {text[:6000]}"` (line 2125)
  - **query prefix**: `f"task: search result | query: {text[:2000]}"` (line 2126)
  - Docstring (2119-2121): the service accepts max 2048 tokens and answers 400 instead of truncating unless `truncate_prompt_tokens` is sent.

---

## 2. Build script — **NOT in the repo**

There is **no** Kompendium build/ingest script anywhere in this repository. Verified by:
- full-repo grep for `atome.jsonl` / `vektoren.npy` / `kompendium` — only hits are `kompendium.py`, `gemma_buchung.py`, `babu_web.py`, `vordrucke.py`, `historie.py`, `tests/test_kompendium.py`, and `server/docker/compose.yml:36`.
- `werkzeuge/` contains only `fixlauf/` and `portal-vorschau/`; no ingest tooling.
- `git log --all -- '*kompendium*'` returns 4 commits, all of which only touch the consumer side (`e0f7ea7`, `35a2e7a`, `9b30622`, `bdf9a58`).
- `.gitignore` does not exclude a kompendium directory — it simply was never committed.

**The corpus lives only on H200V under `~/kompendium/`.** The only embedding-producing code in the repo is `embedding_rechnen` (above) and `backfill_embeddings.py`. The chunking / prefix / truncation conventions used to build the 89 760 atoms are only *documented* in prose:
- `kompendium.py:4-9` — "89.760 Text-Atome aus 182 Quelldateien (AfA-Tabellen, BMF, Kontenpläne, Branchenstatistik, juris), eingebettet mit EmbeddingGemma-300M — demselben Modell und denselben Präfixen, mit denen babu seit dem 27.08. jeden Beleg vektorisiert."
- `babu_web.py:2114-2117` — "Beide Seiten (Beleg-Beiakten UND das Branchen-Kompendium) sind mit genau dieser Konvention eingebettet."

So: to add SKR04 atoms you must reproduce `title: none | text: …` + `truncate_prompt_tokens: 2040` against `:11436`, append to `atome.jsonl` and `np.concatenate` onto `vektoren.npy` keeping the row/line order identical, and (important) **L2-normalise** the new rows since `suchen` does not normalise the matrix side.

---

## 3. Consumers of Kompendium results

### 3a. Chat — `server/belegreview/babu_web.py`

- `_recherche(frage: str) -> str` — **line 2172**. This is the RAG block for the chat.
  - `emb = embedding_rechnen(frage, als_dokument=False)` (line 2180) — query prefix.
  - `kompendium.suchen(emb["vektor"], k=5)` filtered by **`score >= 0.30`** (lines 2185-2186). **No source filter here** — every `quelle` is eligible.
  - Header line: `"NACHGESCHLAGEN im Branchen- und Rechtswissen (mit Quelle):"`, each hit rendered as `f"  [{t['quelle']} · {t['loc']}] " + " ".join(t["text"].split())[:600]` (lines 2188-2191).
  - Then own-Beleg hits (see §4), joined with `"\n\n"`.
- `chat(body: dict, request: Request) -> Response` — `@app.post("/chat")` **line 3907**. (There is no `/api/chat`; `portal.html:2327` posts to `/chat` with `{frage, stream:true}`.)
  - **Prefix-cache layout** (lines 3931-3935 comment): ONE byte-stable system message for all questions.
  - `weltblock = wissen.weltblock(_welt_fuer(un))` (3936), `grund = kompendium.grundwissen()` (3937), `recherche = _recherche(frage)` (3938), `glossar = begriffe_erklaeren(frage)` (3939).
  - System message (lines 3962-4003) = fixed persona/rules **+** `"\n\nGRUNDWISSEN ZUR BRANCHE (Friseur und Beauty — destilliert, erste Einordnung):\n\n" + grund` **+** `"\n\nWAS BABU ÜBER DIESEN SALON WEISS:\n\n" + weltblock`.
  - Everything variable (`auftrag` + `recherche` + `glossar` + `FRAGE:`) goes into the **user** message (line 4005) so the prefix stays intact.
  - `verlauf_aus_anfrage(roh, zuege=None)` — line 3883, `VERLAUF_ZUEGE = 6` (line 9448), each turn clipped to 2000 chars.
  - SSE streaming path lines 4010-4044; non-stream 4046-4052.

### 3b. Booking prompt — `server/belegreview/gemma_buchung.py`

- `system_text(profil: str, rahmen: str = "SKR04") -> str` — **line 198**. The standing block: auftrag + `PROFIL:` + `NACHSCHLAGEWISSEN (gilt für jeden Beleg dieses Salons):\n\n{wissen}` where `wissen = kompendium.kontierungswissen()` (lines 216-218, 225-226) + `KATEGORIEN` (`katalog_text(rahmen)`, line 59) + `REGELN` (line 77) + `SCHEMA` (line 166).
- `NACHSCHLAG_QUELLEN = ("afa", "kontenplan", "skr04", "skr03", "bmf", "ustg", "estg", "kontenrahmen", "steuerschluessel")` — **lines 239-240**. `NACHSCHLAG_SCHWELLE = 0.40` — line 241. The comment (233-238) explains why: the question form lifts *all* similarities to ~0.42, so a threshold alone can't separate signal from noise — the source name can.
- `_sachwoerter(zeilen: list[str], markdown: str | None) -> str` — **line 244**. Strips numbers/units via `re.sub(r"[0-9][0-9.,]*\s*(EUR|€|%|ml|l|St(ü|ue)ck|St|x)?\b", " ", z)` and stopwords `netto|brutto|gesamt|summe|ust|mwst|rechnung|beleg|datum|nr|betrag|zahlung`; returns max 200 chars.
- `nachschlagen(zeilen: list[str], markdown: str | None = None, k: int = 6) -> str` — **line 260**. Query text = `"Nutzungsdauer und Kontierung im Friseursalon: " + sache`, `als_dokument=False`. Filter: `score >= 0.40` **AND** `any(q in (t["quelle"] or "").lower() for q in NACHSCHLAG_QUELLEN)`, then **`[:2]`** — at most **two** atoms injected, each text clipped to 400 chars (line 298). Header `"\nNACHGESCHLAGEN zu diesem Beleg (Quelle in Klammern — nutze es nur, wenn es wirklich passt):\n"`.
- `runde(...)` — line 559 — wires it: `prompt_bauen(..., nachschlag=nachschlagen(zeilen, markdown))` and `system=system_text(profil, rahmen)` (lines 575-580).
- `prompt_bauen(profil, zeilen, antworten, rahmen="SKR04", umsaetze=None, nachbarn=None, markdown=None, mit_bild=False, vertraege=None, personal=None, offene_abbuchungen=None, nachschlag="") -> str` — **line 301**; `nachschlag` is placed in the *variable* part, right before `beantwortet` (line 365).
- `_gemma(prompt, bild=None, system=None) -> dict` — line 525: system as its own message, image second so it doesn't cut the shared prefix.
- `voller_prompt(*args, **kw)` — line 185, test/debug convenience.

**Naming note for the SKR04-atom plan:** `NACHSCHLAG_QUELLEN` already contains `"skr04"` and `"kontenplan"` as substring matches against `quelle`. If new atoms are given `quelle` like `skr04-konten` / `skr04-automatik`, they pass the booking filter with **zero code change**.

---

## 4. Per-Beleg embeddings (the pattern to reuse)

- `beleg_markdown(review: dict) -> str` — `babu_web.py:2085`. Canonical text of a Beleg: `# {lieferant}` header + `- Datum/Betrag/Kategorie/Dokumentklasse` bullets + summary + `## Jede erkannte Zeile` with every OCR line indented by two spaces. Docstring 2089-2091: **one text for two readers** — it is stored as `review/<stamm>.md` *and* is the text the embedding is computed from.
- `embedding_rechnen(text, als_dokument=True)` — line 2113 (see §1).
- **Sidecar format** `review/<stamm>.embedding.json`: exactly `json.dumps({"modell": "embeddinggemma", "dim": <int>, "vektor": [float, ...]})`. Written at `babu_web.py:1967-1970` (inside `/api/aufnahme`) and `backfill_embeddings.py:55`. Golden example: `server/belegreview/tests/golden/review_weingaertle.json:98`.
- **Where stored:** in the GitChain Belegbox next to the review, same commit as the document.
- `_BELEG_VEKTOREN: tuple[str | None, list[str], object]` — line 2139; atomically swapped 3-tuple `(HEAD, staemme, matrix)`.
- `_beleg_vektoren() -> tuple[list[str], object]` — **line 2142**. `git rev-parse HEAD` → cache check → `git ls-tree --name-only HEAD:review` → for every `*.embedding.json` load `["vektor"]`, **normalise per row** (`v / norm`, line 2166), `np.vstack`. Rebuilt once per box HEAD.
- Search in `_recherche` (lines 2193-2211): `scores = matrix @ q` with `q` normalised, `np.argsort(-scores)[:3]`, **early `break` at `scores[i] < 0.35`**, then `git_show(f"review/{staemme[i]}.md")` clipped to 900 chars, under header `"ZUR FRAGE PASSENDE EIGENE BELEGE (im Wortlaut):"`.
- `server/belegreview/backfill_embeddings.py` (71 lines): `BEIAKTEN = (".embedding.json", ".angaben.json", ".umsaetze.json", ".meta.json")` (line 19); `review_staemme() -> list[str]` (line 22) via `git ls-tree --name-only HEAD:review`; `main() -> int` (line 31) with `--probe`; writes all sidecars in one `boxschreiber.schreiben(dateien, None, msg, "backfill")` commit (line 62).

**This is the reusable pattern for uploaded documents:** canonical `.md` next to the binary + a `.embedding.json` sidecar in the same commit + a HEAD-keyed in-process matrix + brute-force cosine with a threshold. It would let uploaded DATEV docs be searched *without* touching the read-only `~/kompendium` mount at all.

---

## 5. Existing document-upload routes and the Ablage

### Routes (all in `babu_web.py`)
| line | route | notes |
|---|---|---|
| 1629 | `@app.post("/ablage")` — `async def ablage(request)` | legacy device-token ingress (:7843 path), not the portal Ablage |
| 1720 | `@app.post("/api/hochladen")` — `api_hochladen(request, name="beleg.jpg")` | raw body → `docs/{monat}/{dateiname}` |
| 1805 | `@app.post("/api/aufnahme")` — `api_aufnahme(request, name="foto.jpg", text="")` | the rich path, see below |
| 2236 | `@app.get("/api/dokumente")` | list |
| 2248 | `@app.get("/api/vorschau/{pfad:path}")` | first-page JPEG via pypdfium2 |
| 2287 | `@app.get("/api/dokument/{pfad:path}")` | download/inline |
| 2310 | `@app.post("/api/dokument-loeschen")` | only `dokumente/` |
| 2390 | `@app.post("/api/dokumente")` — `api_dokument_hochladen(request, name="dokument.pdf", titel="", art="dokument")` | **the generic Ablage upload** |
| 2437 | `@app.post("/api/dokument-gelesen")` | |
| 2496 | `@app.post("/api/kontoauszug")` — `api_kontoauszug(request, name="auszug.pdf")` | PDF only, parses Umsätze |
| 4471 | `@app.post("/api/abschluss")` — `api_abschluss_hochladen(request, jahr=0, name="unterlage.pdf")` | Salon-Check upload |
| 4512 | `@app.post("/api/abschluss/start")` | starts `_abschluss_job` thread |
| 5269 / 5286 | `@app.get("/api/salon-check/bericht")` / `("/api/salon-check")` | |
| 5782 | `@app.get("/api/ablage")` | tree Jahr → Art → Stücke |
| 5879 | `@app.get("/api/ablage/suche")` — `api_ablage_suche(request, q="")` | **keyword** search, deliberately not semantic (comment 5811-5819) |
| 5953 / 5972 | `@app.post("/api/ablage/umbenennen")` / `("/api/ablage/verschieben")` | edit the `.meta.json` sidecar |
| 8940 / 8958 | `@app.get("/api/historie")` / `@app.post("/api/historie")` — `api_historie_hochladen(request)` | DATEV EXTF Buchungsstapel |

Limits: `HOCHLADEN_ENDUNGEN = {".jpg",".jpeg",".png",".pdf",".heic",".xml"}` (1595), `HOCHLADEN_MAX = 40 MB` (1596), `DOKUMENT_ENDUNGEN = {".pdf",".jpg",".jpeg",".png"}` (2224), `ABSCHLUSS_MAX = 80 MB` (4061), `HISTORIE_MAX = 20 MB` (8893).

### The write pattern — `server/belegreview/boxschreiber.py`
- `schreiben(rel_pfad: str | dict[str, bytes], inhalt: bytes | None, nachricht: str, autor_un: str) -> str` — **line 113**. Accepts a **dict of many files → ONE commit** (that's how document + `.meta.json` + `.md` + `.embedding.json` land atomically).
- `loeschen(pfade: list[str], nachricht, autor_un) -> str` — line 136; raises `NichtsZuLoeschen`.
- `beleg_dateiname(original: str) -> str` — **line 188**, scheme `JJJJMMTT-HHMMSS-<hex6>-<name>`, name middle-truncated at `NAME_MAX = 80` by `_mitte_kuerzen` (line 164).
- Mechanics: single global `_SCHLOSS` lock (39), `_bereit()` = fetch + `reset --hard origin/main` (62), `_commit_und_push` with exactly one retry (88), PAT via `http.extraHeader` (42). Path guard `_pfad_pruefen` (80): `^[A-Za-z0-9._/ -]{1,200}$`, no `..`, not absolute.
- Every route calls `boxschreiber.schreiben` through `run_in_threadpool(...)` and then invalidates the index: `with _INDEX_LOCK: _INDEX["geprueft"] = 0.0`.

### `/api/aufnahme` in detail (`babu_web.py:1805-1990`) — the fullest example
multipart (`file`, `text`, `ergebnis`) or raw body → PDF text fallback via `abschluss_lesen.seiten_text` first 3 pages (1855-1864) → `_blob_schon_da(daten)` dedup (1865) → `einsortieren.entscheiden(gelesen)` (1881) → `einsortieren.pfad_fuer(art, dateiname, monat)` (1922) → builds a `dateien: dict[str, bytes]` containing the binary, optional `.umsaetze.json`, optional `.meta.json`, `review/<stamm>.json`, `review/<stamm>.md`, and **`review/<stamm>.embedding.json` from `embedding_rechnen(md)`** (1961-1970) → one `boxschreiber.schreiben` call (1973) → background threads `_vertrag_job` / `_brief_job`.

`server/belegreview/einsortieren.py`: `MERKMALE` (line 21) weighted keyword table, `ZIELE = {"beleg":"docs","vertrag":"dokumente","behoerde":"dokumente","kontoauszug":"auszuege"}` (102), `SICHER_AB = 6` (105), `entscheiden(text) -> dict` (150), `pfad_fuer(art, dateiname, monat) -> str` (169).

### The Ablage index — `_ablage_eintraege()`
- `ABLAGE_ARTEN: dict[str, tuple[str,str]]` — **`babu_web.py:5551-5570`**, 12 fächer: `beleg, behoerde, kanzlei, vertrag, abschluss, kontoauszug, export, kassenbuch, rechnung, historie, ustva, bwa`. **A new "Wissen"/"Nachschlagewerk" fach for uploaded DATEV docs would be added here.**
- `ABLAGE_FACH` (5579), `ABLAGE_PFAD_RE` (**2231-2233**): `^(dokumente|auszuege|abschluss|export|kassenbuch|rechnungen|docs|ustva|bwa|historie)/[A-Za-z0-9._/ -]{1,200}$` — **a new top-level prefix must be added here or the file cannot be opened/previewed.** `DOKUMENT_PFAD_RE` (2225) restricts deletion to `dokumente/`.
- `_ablage_eintraege() -> list[dict]` — **5627**. Sources: `index_aktuell()["dokumente"]`, `index_aktuell()["belege"]`, then a `git ls-tree -r HEAD` walk with a prefix→art if/elif chain (5670-5711) for `auszuege/`, `abschluss/`, `export/*.csv`, `kassenbuch/`, `rechnungen/*.pdf`, `ustva/*.pdf`, `historie/`, `bwa/*.pdf`. `_abschluss_beiakten()` (5592) reads `.meta.json` sidecars for `fach`/`titel` overrides. `_jahr_aus(pfad, zeit)` (5585). `_beleg_titel(z)` (5619). `_pdf_seiten(oid, pfad)` for page count.
- `index_aktuell() -> dict` — **1014**; `_index_bauen(head)` — **721**; `INDEX_TTL` 5 s (555); `_INDEX` dict at 563 with keys `head, geprueft, belege, reviews, dokumente, umsaetze, kassenblaetter, rechnungen, freigaben, zeiten, oid_cache`.
- Search side: `_durchsuchbarer_text(e, reviews, klartexte)` (5836), `_abschluss_klartexte()` (5866) reading `*.text.json` sidecars, `_fundstelle(text, suche)` (5825), `SUCHE_TREFFER_MAX = 60`, `SUCHE_UMFELD = 60` (5821-5822).

### `portal.html` (Ablage view)
Markup `server/belegreview/portal.html:1079-1092`: `#ablage-suche`, `#ablage-vertrag` (chip "Vertrag ablegen"), `#ablage-ansicht-schalter`, `#ablage-post-hinweis`, `#ablage-hochladen` (progress-bar host), `#ablage-baum` (aside), `#ablage-mappe`.

JS:
- state `ablageDaten, ablageJahr, ablageFach, ablageAnsicht, ablageSuche, ablageTreffer, ablageSuchTakt` — line 2600-2602
- `ladeAblage()` — **2604**
- `ablageBaumZeichnen()` — **2635** (uses `ABLAGE_SYMBOL[a.art]` icon map)
- `ablageVorschau(s)` — **2658** (jpg/png → `/api/dokument/…`, pdf → `/api/vorschau/…` with `onerror` fallback icon)
- `ablageZiel(s)` — **2672** (`#detail/<stamm>` for Belege, else `#unterlage/<pfad>`)
- `ablageKachel(s)` — **2676** (card: `.kachel > .blatt[.stapel] > img`, `.marke`, `.name`, `.wann`, `.fundstelle`)
- `ablageZeile(s)` — **2695**
- `ablageWerkzeug(s)` — **2707** (Umbenennen/Verschieben only for `^(dokumente|abschluss)/`)
- `ablageMappeZeichnen()` — **2719**
- `ablageSuchen(wort)` — **2764** (260 ms debounce, min 2 chars)
- `ablageUmbenennen(pfad, jetzt)` — 2779; `ablageVerschieben(pfad)` — 2791
- `ladeUnterlage(pfad)` — 2812 (detail view; PDF in `<iframe>`)
- Upload helpers: `hochladenMitBalken(datei, url, elternteil, {fertigSatz, vorne})` — **4105**; `hochladen(dateien)` — 4127 (routes `.csv/.txt` → `/api/historie`, rejects images at the desk, else `/api/hochladen`); `fuersNetzVerkleinern`, `sendenMitFortschritt`, `fortschrittZeile`.
- Concrete upload wirings: Vertrag 2894-2904 (`/api/dokumente?art=vertrag&name=…&titel=…` → `#ablage-hochladen`), Brief vom Amt 2977-2986 (`art=behoerde` → `#post-hochladen`), Kontoauszug 2988-3000, Salon-Check 3050-3060 (`/api/abschluss?jahr=…&name=…`), Historie 4140.

**→ The cheapest path for "user uploads DATEV docs sorted by topic" is a new `art=` value on the existing `POST /api/dokumente` (line 2390) plus a new `ABLAGE_ARTEN` entry — that route already accepts `titel` and `art`, writes `dokumente/{YYYY-MM}/{name}` + `.meta.json` in one commit, and dispatches a background thread by `art` (2424-2432). The "topic" would live in the `.meta.json` and/or a subfolder.**

---

## 6. PDF text extraction

- `server/belegreview/abschluss_lesen.py:79` — `seiten_text(pfad) -> list[str]`: `pypdfium2.PdfDocument(str(pfad))`, `seite.get_textpage().get_text_range()` for the first `SEITEN_CAP` pages. **This is the general text extractor.**
- `server/belegreview/abschluss_lesen.py:89` — `seiten_bilder(pfad, max_kante=BILD_MAX_KANTE) -> list[bytes]`: renders pages (or opens an image) as JPEG bytes for the multimodal path.
- `server/belegreview/abschluss_lesen.py:117` — `llm_json(nachrichten, timeout=LLM_TIMEOUT) -> dict`; `_bild_nachricht(prompt, jpeg)` at 132 builds the `image_url` data-URI message. Used by `_abschluss_job` / `salonpruefung.felder_ernten` and by `brief_erklaerung_bauen` (`babu_web.py:5315`).
- `server/belegreview/kontoauszug.py:72` — its own `pypdfium2` reader for statements (`parse_pdf`).
- Thumbnails: `babu_web.py:2271-2279` (`/api/vorschau`), `babu_web.py:4590-4598` (`/api/abschluss/{jahr}/{datei}/vorschau`), `babu_web.py:5770-5776` (`_pdf_seiten`, page count).
- Scan/multimodal booking: `gemma_buchung.py:525` `_gemma(prompt, bild=(bytes, mime), system=...)` → base64 `image_url` first, text second, against `VLM_API` (`:11435`, model `gemma4-mm`, `GEMMA_API`/`GEMMA_MODELL` at `babu_web.py:246-247`).
- PDF fallback inside `/api/aufnahme`: `babu_web.py:1855-1864` writes to a `NamedTemporaryFile` and calls `abschluss_lesen.seiten_text(tf.name)[:3]`.

---

## Two constraints worth carrying into the plan

1. **`babu_web.py:4201`** — `# vLLM (:11435/:11436) teilt sich mit dem Review-Watcher — nie parallel fluten.` and `_LLM_SEMAPHORE = threading.Semaphore(1)` (4202). Embedding 1516 SKR04 accounts or a batch of uploaded documents must be throttled / run offline, not from a request handler.
2. **`kompendium.py:51-52`** — the length invariant. Since `/data/kompendium` is mounted `:ro` (`compose.yml:36`), the container cannot append to `atome.jsonl` / `vektoren.npy` at all. New atoms either (a) get built on the host and the mount stays read-only, or (b) go into a **second, writable** store using the Beleg-sidecar pattern from §4.