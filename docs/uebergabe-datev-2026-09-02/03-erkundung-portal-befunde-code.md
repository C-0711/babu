I have everything. Here are the findings.

## P0-1 — Three different expense sums for one month

Four independent computations, each with its own definition:

| View | id | JS | Route | What it sums |
|---|---|---|---|---|
| Auswertung › Ausgaben | `a-zahlen` (portal.html:1016) | `ladeZahlen` **portal.html:2399** | `GET /api/monat/{monat}` (babu_web.py:3469) | **brutto** of *all* Belege, grouped by `belegart` |
| Auswertung › Monatsabschluss | `a-abschluss` (portal.html:996) | `ladeAbschluss` **portal.html:3592** | `GET /api/monatsabschluss/{monat}` (babu_web.py:8784) | **netto** by `konto_skr04` → `KOSTENGRUPPEN` + Vertragskosten + Personal |
| Export | `a-export` (portal.html:1133) | `ladeExport` **portal.html:3871** | same `/api/monat/{monat}` | reads a key that does not exist (see P0-3) |
| Heute | `a-heute` (portal.html:952) | `ladeBleibtDir` **portal.html:1665** | `/api/monatsabschluss/{monat}` | `bwa.ergebnis` (same as Monatsabschluss) |

- **Ausgaben 79,50 € brutto** — `_monat_summen` **babu_web.py:1522-1557**; `brutto_summe += z["brutto"]` (l. 1531), no netto, no contracts, no personnel, no `NEUTRALE_KONTEN` exclusion. Rendered at **portal.html:2441** (`euro(d.brutto)`).
- **Ausgegeben (ohne Steuer) 979,30 €** — `monatsabschluss.bwa` **monatsabschluss.py:294-399**. Netto per Beleg (l. 318), plus **Vertragskosten** at **monatsabschluss.py:328-345** (`vertraege_fuer_monat`, l. 253), fed by `vertraege_aktuell()` (**babu_web.py:8549**, i.e. the `vertrag` blocks of `index["dokumente"]`), plus `personal_monat` from `team_personalkosten` (**babu_web.py:8584**) at l. 365-371.
- **"Raum 905,00 € (0 Belege)"** — the contract bucket gets `netto += betrag` but `anzahl` stays 0 (**monatsabschluss.py:341-345**); it sets `e["aus_vertrag"]`, but the renderer at **portal.html:3634-3637** only prints `${g.anzahl} Beleg/Belege` and never looks at `aus_vertrag`. So a contract-derived line always reads "0 Belege".
- **"Sonstiges" vs "Werbung, Bewirtung und Reisen" — the actual category bug.** `_review_aus_einschaetzung` writes the category into `einschaetzung.belegart` and hard-codes `"semantik": None` (**babu_web.py:2070 and 2078**). But the index reads the display category only from `review["semantik"]["belegart"]` (**babu_web.py:791**). For every app-path (Zielbild) receipt that field is therefore `None`, and `_monat_summen` falls back with `art = z["belegart"] or "Sonstiges"` (**babu_web.py:1532**). The Monatsabschluss is unaffected because it groups by `konto_skr04` (set at babu_web.py:793 from `einschaetzung.konto_skr04`), which maps to `("werbung", "Werbung, Bewirtung und Reisen")` for 6640/6643 (**monatsabschluss.py:35-36**). Same receipt, two names, two grouping keys.
- Note: `/api/auswertung` (babu_web.py:4993) is *not* involved — it serves the Kanzlei-BWA report text; the "Auswertung" tab in the portal is `#zahlen`.

## P0-2 — Wrong Vorsteuer (19 % applied to the deposit/Pfand)

- **Server, the decisive place: `_review_aus_einschaetzung`, babu_web.py:2025, lines 2030-2039.**
  ```python
  netto = round(brutto / (1 + satz / 100), 2)
  ust   = round(brutto - netto, 2)
  ```
  It uses only `betrag_eur` + the single `ust_satz` and **discards `buchung["steuersaetze"]`**, the per-rate table that `gemma_buchung._steuertabelle` (**gemma_buchung.py:492-509**) built from the positions. 65,73 / 1,19 = 55,24 → USt 10,49. It also writes `"summenprobe_ok": None` (**babu_web.py:2059**), so nothing ever cross-checks against the printed 57,06 / 8,67.
- **Printed tax lines are read but then thrown away.** `ios/Beleg/Beleg/FeldParser.swift:133-141` parses the printed Netto/USt/Brutto table into `f.steuerPositionen` and sets `summenprobeOK = true`. `Store.gemmaBuchungAnwenden` (**ios/Beleg/Beleg/Store.swift:447, esp. 467-472**) then overwrites `netto`/`ust` with `brutto/(1+satz)` and only restores the table in `steuertabelleAnwenden` (**Store.swift:483-490**) if Gemma itself returned a `steuersaetze` array summing to brutto (tolerance 0.02). The OCR-read table is not used as a fallback.
- **`buchung_pruefen`** (**gemma_buchung.py:373**, esp. 441-448) picks the *leading* rate (`steuersaetze[0]["satz"]`, largest gross share) as the single `ust_satz` — correct on the Beleg level, but only if the consumer then uses the table. Nobody on the server does.
- **Prompt rules ("Summenschema"):** `gemma_buchung.py:139-143` — "Prüfe die Summen als ZUSAMMENHÄNGENDES Schema …". The related no-invention rule is at **gemma_buchung.py:113-117** ("Rechne NIE 19 % aus einem Bruttobetrag heraus, die nicht auf dem Beleg stehen"), and the zero-rate rules at 118-125. There is **no rule about Pfand/deposit** anywhere in the prompt, and no `positionen` example with mixed rates in `SCHEMA` (gemma_buchung.py:167-183) beyond the generic field.
- Downstream: `monatsabschluss.vorsteuer_monat` (**monatsabschluss.py:163-196**) trusts `b["ust"]` verbatim; since `summenprobe_ok is None` it never lands in the Prüfliste (l. 179).

## P0-3 — Export "Summe 0,00 € bei 1 Beleg"

**portal.html:3884-3885** in `ladeExport`:
```js
<span class="summe">${euro(d.summe || 0)}</span>
```
`d` comes from `/api/monat/{monat}` → `_monat_summen`, which returns the key **`brutto`**, never `summe` (**babu_web.py:1554**). `d.summe` is `undefined` → `|| 0` → always "0,00 €", while `d.anzahl` (line 3882) is correct. Purely a key-name mismatch; no status filter is involved here. (The status filter `("geprüft", "exportiert")` does exist, but only in `/api/export/{monat}.csv`, **babu_web.py:3339-3340** — that is what the download contains, and it can legitimately be empty while the view says "1 Beleg".)

## P0-4 — Status "Wird gelesen" stuck

- **Lifecycle:** `_status_ableiten` **babu_web.py:645-660**. `review is None → "erfasst"`; with a review → `"geprüft"` unless `offen` remains / Bewirtung unanswered / `summenprobe_ok is False` → `"nachfrage"`. `"exportiert"` is set elsewhere (via the export-stapel bookkeeping). There are only these four states.
- **Portal text:** `statusSatz` **portal.html:1501** (`"wird noch gelesen …"`) and `statusMarke` **portal.html:1807** (`"wird gelesen"`); detail view `inArbeit = d.status === "erfasst"` **portal.html:1990** with hint "wird gerade gelesen — dauert einen Moment …" at **portal.html:2011**.
- **What advances it:** *only* the write of `review/<stamm>.json`. That happens in exactly one place: `/api/aufnahme` **babu_web.py:1805**, and only inside `if isinstance(ergebnis, dict) and isinstance(ergebnis.get("buchung"), dict)` (**babu_web.py:1939-1968**) — i.e. only when the iOS app posts multipart with Vision lines + Gemma's booking.
- **Therefore stuck forever for:** portal upload `POST /api/hochladen` (**babu_web.py:1720**, writes only `docs/<monat>/<datei>`, l. 1744-1746), `POST /ablage` (**babu_web.py:1629**, l. 1699-1702), and `/api/aufnahme` when the app sends no `ergebnis`.
- **No watcher exists any more.** `server/belegreview/README.md:22-27`: "Es gibt keine zweite Lesung mehr … Der frühere Watcher (`review_watcher.py`, pm2 `belegreview`) ist gelöscht — nicht neu starten, nicht neu erfinden." Nothing else polls `docs/`.
- **No timeout, no error state, no retry route.** The only escape hatches: `POST /api/angaben/{stamm}` (**babu_web.py:8480**) — saving anything flips the entry to "geprüft" via **babu_web.py:831-833** + `_beleg_abgeschlossen` (l. 690) — or `POST /api/beleg/{stamm}/loeschen` (**babu_web.py:1760**). `POST /api/buchung/einschaetzung` (**babu_web.py:3483**) is the booking endpoint, but it is app-only text-JSON and does not write a review for an already-archived Beleg.

## P1-5 — Desktop layout

Widths and breakpoints, all in portal.html:

- `main{padding:34px clamp(18px,4.7vw,56px) 60px}` **l. 92** — no max-width on `main`; the page is full-viewport-wide.
- `main p, .leer, .karte > p{max-width:78ch}` **l. 96** — the only global text constraint.
- Inline widths: `880px` (Gesperrt view, **l. 953**), `560px` (Einrichtung, **l. 1412**, deliberate), `760px` ("Wohin dein Geld geht" bars, **l. 2446**), `46ch` (**l. 3039**), `min(860px,100%)` (Aufräumen-Stapel, **l. 722**), sheets `min(520px,100%)` **l. 592** and `min(560px,100%)` **l. 681/695**.
- **`.spalten` (l. 105-117) — the multi-column grid, active only `@media (min-width:1180px)` — is defined but never applied anywhere in the file** (`grep 'class="spalten'` → 0 hits). Dead CSS; that is why wide screens stack.
- Breakpoints: **900px** (`#stand`, l. 79; `#unterlage-grid`, l. 260), **820px** (header/upload button, l. 83-88; `.ablage-flaeche`, l. 172; `.ablage-baum`, l. 175; `#detail-grid`, l. 473), **700px** (mobile tab bar, l. 746), **640px** (header/main padding, l. 737), **1180px** (`.spalten` l. 111, `#a-aufraeumen` l. 723).
- **Two-column views (the only ones):** `#detail-grid` — `minmax(0,5fr) minmax(0,6fr)`, **l. 472**, used by view `a-detail` (l. 990, built in `ladeDetail`, portal.html:2015); `#unterlage-grid` — `minmax(0,7fr) minmax(0,5fr)`, **l. 258**, view `a-unterlage` (l. 1097); plus `.ablage-flaeche` `250px minmax(0,1fr)` (**l. 170**, view `a-ablage`, l. 1069). All 24 other views are single-column.

## P1-6 — App-only functions on the desktop

- **"Gestellt wird in der App — hier siehst du, was offen ist."** — `ladeRechnungen`, **portal.html:4259-4260**. The APIs already exist and are not app-gated: `POST /api/rechnungen` (**babu_web.py:6035**, server assigns the number, `rechnungen.aufbauen` + `fehlende_pflichtangaben`), `POST /api/rechnung/{nummer}/pdf` (**6107**), `/bezahlt` (**6137**), `/storno` (**6171**), `GET /api/rechnungen` (**6015**). Only the PDF rendering is app-side (`ios/Beleg/Beleg/RechnungPDF.swift`); the portal already has a Briefkopf view (`a-briefkopf`, l. 1243). Guard is `rolle(un) == "mitarbeit"` only (babu_web.py:6047).
- **"Trag sie in der App im Kassenbuch ein — eine Zahl pro Frage."** — `ladeAbschluss`, **portal.html:3603-3605**. Route is **`POST /api/kassenbuch`** (**babu_web.py:9337**) — note: `datum` goes in the **JSON body**, not the path (`/api/kassenbuch/{datum}` is the GET, **babu_web.py:9317**). Body fields: `datum`, `KASSENBUCH_ZAHLEN`, `KASSENBUCH_NOTIZEN`, `trinkgeldVerteilt`, `korrekturen`, `grund`; GoBD guard `kassenfest.darf_schreiben` (babu_web.py:9394) requires `grund` on re-write and 409s once the month is festgeschrieben. The question set the portal would need is `monatsabschluss.umsatz_profil(...)["fragen"]` (**monatsabschluss.py:71-94**), already returned by `/api/monatsabschluss/{monat}` as `profil`.
- **Termine:** `GET /api/termine` (**babu_web.py:6453**) **already takes `von`/`bis`** and loops day by day (l. 6470-6478) — a week route is not needed and does not exist separately. The portal only ever requests a single day: `ladeTermine` **portal.html:4422**, call at **4427** (`?von=tTag&bis=tTag`), day stepping at **4909-4911**. No week rendering exists.
- **Salon-Check "Das konnten wir nicht sicher lesen — magst du kurz draufschauen?"** — `saloncheck._grau`, **saloncheck.py:53-58** (triggered from `unsicher`, produced by `abschluss_lesen._summenproben`, **abschluss_lesen.py:291-312**). Rendered read-only in `scReport` **portal.html:3269-3282** — `k.satz` is plain text, **no input field, no correction route**. The only write-back path in that view is `scVorschlaege` → `POST /api/abschluss/uebernehmen` (**babu_web.py:4957**), which fills *Stammdaten*, not the grey card's number.

## P1-7 — Ablage display names

- Display name = `s.titel`, rendered in `ablageKachel` **portal.html:2686** and `ablageZeile` **portal.html:2697**.
- `titel` is built in `_ablage_eintraege` **babu_web.py:5627-5722**. For `auszuege/` (**l. 5680-5686**): `titel = beiakte.get("titel") or name` — i.e. **the raw filename** unless someone renamed it via `POST /api/ablage/umbenennen` (**babu_web.py:5953**). Other paths do get synthetic names (`kassenbuch/` l. 5613, `rechnungen/` l. 5615, `ustva/` l. 5617, `historie/` l. 5622, `bwa/` l. 5624).
- The filename shape comes from `boxschreiber.beleg_dateiname` **boxschreiber.py:188-192** (`JJJJMMTT-HHMMSS-<hex>-<sanitised original>`).
- **Metadata that already exists but is not used for the title:** `kontoauszug.parse_text` returns `{"konto", "monat", "umsaetze"}` (**kontoauszug.py:20-68**), stored as `<pfad>.umsaetze.json` by `POST /api/kontoauszug` (**babu_web.py:2534-2538**) and by `/api/aufnahme` (**babu_web.py:1925-1927**); the month is also the folder (`auszuege/<monat>/`). Page count is already computed: `e["seiten"] = _pdf_seiten(...)` **babu_web.py:5668**, shown as "N Seiten" (portal.html:2684). Bank name is **not** extracted anywhere — `parse_text` reads only the account number.

## P1-8 — "Löschen" on Ablage cards

- Button: `ablageWerkzeug` **portal.html:2707-2717**, condition `s.loeschbar && meineRolle !== "mitarbeit"` (**l. 2714**).
- `loeschbar` is set server-side: `True` for `index["dokumente"]` (**babu_web.py:5640**), `False` for Belege (**5652**), and `pfad.startswith("auszuege/")` for the tree-derived entries (**babu_web.py:5719**) — Kassenbuch/Export/Abschluss/BWA are deliberately not deletable.
- Handlers: `dokumentLoeschen` **portal.html:3960**, which routes `auszuege/` to `auszugLoeschen` **portal.html:3970**; both go through the confirm sheet `loeschFragen` **portal.html:3907** → the POST at **portal.html:3937-3947**.
- Routes and guards: `POST /api/dokument-loeschen` **babu_web.py:2310** — `_box_wache`, `rolle(un) == "mitarbeit"` → 403 (l. 2320), path must match `DOKUMENT_PFAD_RE` and contain no `..` (l. 2327), deletes `pfad` + `DOKUMENT_BEIAKTEN`. `POST /api/auszug-loeschen` **babu_web.py:2351** — same guards, `AUSZUG_PFAD_RE = ^auszuege/[A-Za-z0-9._/ -]{1,200}$` (**l. 2347**), deletes `pfad` + `.umsaetze.json`. Beleg deletion is separate: `POST /api/beleg/{stamm}/loeschen` **babu_web.py:1760** (`belegLoeschen`, portal.html:3950). No undo route; GitChain history keeps the versions.

## P2 — quick locations

- Relative week labels: `wochenGruppe` **portal.html:1823-1833**, applied in `ladeBelege` **portal.html:1851**.
- "Deine letzten Belege" ordering: `ladeHeute` calls `/api/belege?limit=3` at **portal.html:1770**; sorting in `_beleg_liste` **babu_web.py:1034** — `hochgeladen` desc (upload time, not receipt date), *then* paginated, so the limit is applied after the global sort.
- Duplicate dialog: text built in `/api/aufnahme` **babu_web.py:1953-1957**, appended to `review["felder"]["offen"]` (l. 1958). No resolve route exists; it is cleared only by `POST /api/angaben/{stamm}` (**babu_web.py:8480**, via `_offen_nach_angaben`, **babu_web.py:663-687**) or by deleting the Beleg.
- Post-vom-Amt Frist: `ladePost` **portal.html:2940** — `<b>Bis ${esc(e.bis_wann)}</b>`, raw ISO; the helper `datumDeutsch` exists at **portal.html:3857** but is not used here.
- Verträge "Frist steht im Vertrag": `ladeVertraege` **portal.html:4311-4314**.
- Heading "Was deine Kanzlei für dich bereitlegt": **portal.html:1108** (view `a-post`, l. 1102).
- "un" without "@": `un` comes from GitChain `/auth/whoami` in `wer_token` **babu_web.py:290-312** (`ident["un"]`, GitChain usernames have no @) and from `ERLAUBT` default `"christoph0711.io"` **babu_web.py:250**. Printed raw at **portal.html:3354** (`#einst-un`) and **portal.html:3414** (`#menu-un`); **portal.html:3358** uses `ich.un.includes("@")` to decide whether to show the password field, so PAT accounts silently lose it. Nothing strips an "@" — the value never had one.
- Team form: view `a-team` **portal.html:1124**, form built in `ladeTeam` **portal.html:3431**, fields at **3487-3505** ("Fester Lohn" **3493**, "Nach Stunden" **3494**, `t-stundenlohn` **3501**). "Speichern" at **portal.html:3507** uses `class="hin"` — but `.hin` is styled only as `.nachfrage .hin` (**portal.html:424-425**), and this button sits in a plain `.karte`, so it renders unstyled, like text. Same issue at **portal.html:4995** and **5035**.
- `kw-kuendigen` default checked: **portal.html:3715** (`<input type="checkbox" id="kw-kuendigen" checked>`), read at **portal.html:3747**, posted to `POST /api/kanzleiwechsel` (**babu_web.py:9033**).
- Salon-Check as a tab under Belege: sub-tab bars at **portal.html:968-973** (`a-belege`), **1034-1039** (`a-saloncheck`), **1047-1052** (`a-bank`).
- Two personal views: menu entries **portal.html:910-913**; `a-personal` **portal.html:1338** (`ladePersonal` **portal.html:4627**, `/api/mitarbeiter` babu_web.py:6694) vs `a-team` **portal.html:1124** (`ladeTeam` **portal.html:3431**, `/api/team` babu_web.py:8590). Two separate stores; only the `team` table feeds `team_personalkosten` → BWA.
- "Wie der Monat gelaufen ist" tiles: `kennzahlKacheln` **portal.html:2365-2397**, heading at **2386**; "0 Sek." from **portal.html:2370** (`Math.round(s.median) + " Sek."`) with `zeit_bis_haken_s.median` computed in `kennzahlen_monat` **babu_web.py:3400-3409** — for app-path receipts photo and review land in the same commit, so the latency is ~0.
- Fragen view: markup **portal.html:1422-1437**; CSS `#chatlog` **599**, `#chatform` (sticky) **605**, `#chatfrage` **606**, `.beispiele` **609**, `.msg{max-width:82%}` **600**. No width cap on the log; it spans the whole `main`.

## P3 — quick locations

- **portal.html is served as one file, unauthenticated:** `GET /portal` **babu_web.py:1048-1050** — `FileResponse(WURZEL / "portal.html")`, no auth check; the gate is client-side (`zeigeLogin`, portal.html:1516) plus `_api_wache`/`_box_wache` on every `/api/*` call. **5292 lines / ~250 KB**, all HTML+CSS+JS inline, no bundling, no split.
- **Caching:** `HTML_FRISCH = {"Cache-Control": "no-cache"}` **babu_web.py:1040**, applied at 1045, 1050, 1101, 1109, 4888, 6691. No ETag/Last-Modified beyond what Starlette's `FileResponse` adds. Icons get `public, max-age=86400` (**1067**); `portal.manifest.json` (**1053**) and `portal.sw.js` (**1058**) get no cache header at all. Data ETags exist only for `/api/belege` (**babu_web.py:1336-1338**).
- **Label elements: 16 total** — portal.html lines **1172, 1174, 1176, 1190, 1232, 1458, 1460, 1924, 1926, 1928, 1930, 1932, 3455, 3459, 3698, 3714**. Only three use `for=` (1232, 1458, 1460); the rest wrap their input. Every other input in the file (Team form 3490-3504, Personal 4627ff, Einstellungen, chat 1434) relies on `placeholder` alone — no accessible name.
- **Impressum/Datenschutz: no placeholder anywhere in portal.html** (0 hits). The only "Datenschutz" string in the tree is an onboarding *Belehrung* checkbox in `start.html:153`. No footer, no legal links in the portal.
- **Zugänge server-side role guard:** view `a-verwaltung` **portal.html:1397**, button shown by `meineRolle === "admin" || "kanzlei"` (**portal.html:3357**, also 3416). Server side is enforced properly: `_verwalter_wache` **babu_web.py:3180-3186** → `darf_verwalten` **babu_web.py:3176** (`rolle(un) in ("admin","kanzlei")`), used by `/api/nutzer` (3193), `POST /api/nutzer` (3211), `/api/nutzer-aktion` (3231), `/api/registrierungen` (2714), `/api/registrierung-einrichten` (3275). `/api/export/{monat}.csv` uses `darf_verwalten` directly (**babu_web.py:3335**).