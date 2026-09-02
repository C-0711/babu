<!-- Planungsagent (Sonnet), 02.09.2026, Stand d163ac6 -->

# Umsetzungsplan — 26 Befunde, Stand Commit d163ac6 (unverändert bis HEAD)

Alle Zeilennummern gegen den aktuellen Checkout verifiziert (`git log d163ac6..HEAD -- babu_web.py portal.html monatsabschluss.py gemma_buchung.py FeldParser.swift Store.swift` liefert keine Treffer — Stand ist identisch). Zusätzlich habe ich die entscheidenden Codestellen selbst gelesen, um die Änderungen konkret angeben zu können, nicht nur die Fundstellen zu zitieren.

Zwei Prüfwerkzeuge gelten für **jede** portal.html-Änderung in diesem Plan:
- `server/belegreview/tests/test_sprachregel.py` — verbietet u. a. „Server/OCR/KI/Modell/Hash/Commit/Token/PAT/Lesung/Zweitlesung/Erstlesung" in sichtbarem Text.
- `server/belegreview/tests/test_portal_verdrahtung.py` — jede `id="a-…"`-Section muss in `ansichten{}` stehen und umgekehrt.

---

## Runde 1 — P0-1 + P0-2 + P0-3 („Zahlen stimmen überall überein, Bon-Steuer gewinnt")

Diese drei gehören in **einen** Commit, weil P0-1 und P0-3 dieselbe Route (`/api/monat/{monat}`) und denselben Konsumenten (`ladeZahlen`/`ladeExport`) anfassen, und P0-2 unabhängig, aber gleich riskant ist (DATEV-Export). Ich würde sie trotzdem in **zwei Teil-Commits** innerhalb der Runde trennen (1a: Zahlen/Export, 1b: Vorsteuer/iOS), weil P0-2 auch einen iOS-Build/Merge braucht und getrennt deploybar sein sollte.

### 1a — P0-1: Kategorie-Quelle vereinheitlichen

**Datei/Funktion/Zeile:** `server/belegreview/babu_web.py:791`
```python
"belegart": ((review.get("semantik") or {}).get("belegart")) if review else None,
```
**Änderung:** Kategorie NICHT mehr aus `semantik.belegart` lesen (bei jedem Zielbild-Beleg `None`, weil `_review_aus_einschaetzung` `"semantik": None` hart setzt, babu_web.py:2078). Stattdessen aus `konto_skr04` ableiten, mit derselben Zuordnung, die `monatsabschluss.bwa()` intern benutzt (babu_web.py:301-303 in `bwa()`: `zuordnung = {konto: (schluessel, name) for schluessel, name, konten in KOSTENGRUPPEN for konto in konten}`).

- In `monatsabschluss.py` diese Zuordnung aus `bwa()` in eine eigene Funktion ziehen:
  ```python
  def kostengruppe_von(konto: str | None) -> tuple[str, str]:
      zuordnung = {k: (s, n) for s, n, konten in KOSTENGRUPPEN for k in konten}
      return zuordnung.get(konto or "", ("sonstiges", "Sonstiges"))
  ```
  `bwa()` (Zeile 301-303, 319) ruft diese Funktion statt der lokalen Dict-Comprehension — reine Extraktion, kein Verhaltensunterschied.
- `babu_web.py:791` wird zu:
  ```python
  "belegart": (monatsabschluss.kostengruppe_von(e.get("konto_skr04"))[1]
               if e.get("konto_skr04") else
               (review.get("semantik") or {}).get("belegart")) if review else None,
  ```
  (Fallback auf `semantik.belegart` nur für alte Reviews vor dem 27.08., die noch keine `konto_skr04` tragen — sonst würde dieser Fix historische Belege auf „Sonstiges" zurückwerfen.)
- `import monatsabschluss` steht am Dateikopf vermutlich schon (wird an mehreren Stellen importiert) — prüfen, sonst als lokalen Import in der Funktion, die `791` enthält, ergänzen (Konsistenz mit dem Rest der Datei, die lokale Imports bevorzugt, `# noqa: PLC0415`).

**Test:** `server/belegreview/tests/test_monatsabschluss.py` — neuer Test `test_kostengruppe_von_ist_eine_eigene_funktion` (ruft `kostengruppe_von("6640")` → `("werbung", "Werbung, Bewirtung und Reisen")`, `kostengruppe_von(None)` → `("sonstiges","Sonstiges")`). In `server/belegreview/tests/test_zahlen_lesen.py` (oder wo `_beleg_liste`/Index getestet wird) einen Test `test_belegart_kommt_aus_konto_skr04_nicht_aus_semantik`: einen Zielbild-Review mit `einschaetzung.konto_skr04="6640"` und `semantik=None` bauen, `index_aktuell()["belege"][stamm]["belegart"]` muss `"Werbung, Bewirtung und Reisen"` sein, nicht `"Sonstiges"`.

**Risiko:** gering — additive Fallback-Logik, kein bestehendes Feld wird entfernt. Einziges Risiko: alte Reviews ohne `konto_skr04` UND ohne `semantik.belegart` fallen weiterhin auf `None`/„Sonstiges" — unverändertes Verhalten, kein Rückschritt.

### 1a — P0-1 Fortsetzung: Ausgaben-Ansicht auf Monatsabschluss-Zahlen umstellen

**Datei/Funktion/Zeile:** `server/belegreview/portal.html`, Funktion `ladeZahlen` (Zeile 2399-2470).

`ladeZahlen` holt bereits `/api/monatsabschluss/{monat}` (Zeile 2409) für `lauf`/`erloese`/`ergebnis` — ich erweitere das um `bwa`, statt eine zweite, abweichende Rechnung (`/api/monat/{monat}` → `_monat_summen`, Brutto aller Belege) daneben zu zeigen.

**Änderung:**
- Zeile 2407-2416: zusätzlich `bwa = ab.bwa` einsammeln.
- Zeile 2434-2444 (der „Eingenommen/Ausgegeben"-Block): `d.brutto` (Brutto aller Belege, inkl. privater/neutraler Buchungen) ersetzen durch `bwa.kosten_netto` — dieselbe Zahl, die auf der Monatsabschluss-Seite unter „Ausgegeben (ohne Steuer)" steht (portal.html:3612-3613). Label ebenfalls auf „Ausgegeben (ohne Steuer)" ändern, damit gleicher Text = gleiche Zahl an beiden Stellen sofort erkennbar ist. Anzahl-Text darunter bleibt die reine Belegzahl (`d.anzahl`, weiterhin aus `_monat_summen` — unproblematisch, das ist nur ein Zähler, keine Summe).
- Zeile 2446-2470 (Loop über `d.belegarten`): ersetzen durch Loop über `bwa.gruppen` (dieselbe Struktur, die `ladeAbschluss` bei Zeile 3627-3633 rendert — netto statt brutto, Kostengruppen statt beliebiger `belegart`-Strings). Dafür eine gemeinsame JS-Funktion `kostengruppenZeile(g)` extrahieren, die beide Views (`ladeZahlen` und `ladeAbschluss`) nutzen — das behebt gleichzeitig die daneben gefundene **„0 Belege"-Anzeige bei Vertragskosten**: statt `${g.anzahl} Beleg/Belege` prüft die neue Funktion `g.aus_vertrag` und zeigt in dem Fall `"aus Vertrag: " + g.aus_vertrag` an (Datenfeld existiert bereits, `monatsabschluss.py:344`, wird nur nie gelesen).
- Explizite Differenz-Zeile ergänzen (Auftrag: „davon 905 € Miete aus Vertrag, noch ohne Beleg"): direkt unter der „Ausgegeben"-Zahl `<div>` mit `sum(g.netto for g in bwa.gruppen if g.aus_vertrag)` einfügen, nur wenn > 0: „davon {euro} € aus Verträgen ohne eigenen Beleg".

**Datei/Funktion/Zeile (Monatsabschluss-Seite, derselbe Fix, gleicher Commit):** `portal.html:3628-3631` (`ladeAbschluss`, Gruppen-Renderer) — dieselbe `kostengruppenZeile(g)`-Funktion statt der Inline-Zeile benutzen, damit die „0 Belege"-Korrektur nicht nur in Ausgaben, sondern auch im Monatsabschluss selbst greift (dort tritt der Bug ja zuerst auf, laut Befund #1: „Raum 905,00 € (0 Belege)").

**„Bleibt dir" auf Heute erklären (Teil von P0-1):** `portal.html:1660-1674` (`ladeBleibtDir`) — Zeile 1671 `$("#heute-bleibt-satz").textContent = "vor Steuern — der Monat läuft noch";` um einen zweiten Satz ergänzen, sobald `bwa.kosten_netto` bekannt ist: z. B. „Eingenommen {erloese} € · Ausgegeben {kosten_netto} € — vor Steuern, der Monat läuft noch". Dazu `ladeBleibtDir` um `erloese: d.erloese.brutto_gesamt` und `kosten: d.bwa.kosten_netto` erweitern (beide stehen in derselben Antwort, die schon geladen wird — keine neue Route).

**Test:** `server/belegreview/tests/test_portal_verdrahtung.py` läuft automatisch mit (keine neue Section/kein neuer Menüpunkt). Neuer Snapshot-artiger Test wäre in JS nicht sinnvoll (keine JS-Testinfra im Repo) — stattdessen serverseitig absichern, dass `bwa.gruppen[].aus_vertrag` bei Vertragskosten ohne Beleg gesetzt bleibt (`test_monatsabschluss.py::test_vertrag_liefert_die_monatskosten` existiert schon, Zeile 197 — dort zusätzlich `assert g["aus_vertrag"]` und `assert g["anzahl"] == 0` prüfen, als Dokumentation dafür, dass die UI genau das abfragen muss).

**Risiko:** mittel — größte reine UI-Änderung dieser Runde, betrifft die meistgenutzte Seite. Manuelles Durchklicken im `portal-vorschau` Pflicht (siehe Verifikation unten). Kein Route-Contract-Bruch, da `/api/monatsabschluss` unverändert bleibt und `/api/monat` nur einen neuen Nutzen bekommt (siehe P0-3 unten), aber nichts Bestehendes entfernt wird — andere Konsumenten von `d.brutto`/`d.belegarten` aus `/api/monat` bleiben lauffähig.

### 1a — P0-3: Export-Summe reparieren + Filter erklären

**Datei/Funktion/Zeile:** `server/belegreview/babu_web.py:1522-1557` (`_monat_summen`) und `:3469-3480` (`api_monat`).

**Änderung:** `_monat_summen` bleibt wie es ist (liefert `brutto`, nicht `summe` — das ist für den Rest korrekt benannt). Stattdessen `api_monat` um einen zweiten, export-genauen Block erweitern, der exakt denselben Filter wie `/api/export/{monat}.csv` (babu_web.py:3339-3340: `status in ("geprüft", "exportiert")`) anwendet:
```python
@app.get("/api/monat/{monat}")
def api_monat(monat: str, request: Request) -> Response:
    ...
    daten = _monat_summen(monat)
    daten["vormonat"] = _monat_summen(vor)
    idx = index_aktuell()
    export_zeilen = [z for z in idx["belege"].values()
                     if z["monat"] == monat and z["status"] in ("geprüft", "exportiert")]
    daten["export"] = {
        "anzahl": len(export_zeilen),
        "brutto": round(sum(z["brutto"] or 0 for z in export_zeilen), 2),
    }
    return JSONResponse(daten)
```
**Datei/Funktion/Zeile:** `portal.html:3871-3891` (`ladeExport`) — Zeile 3882-3885 umbauen:
```js
ziel.innerHTML = `<div class="mrow"><span class="art">Belege im Monat</span>
    <span class="summe">${d.anzahl}</span></div>
  <div class="mrow"><span class="art">Davon geprüft und bereit für den Stapel</span>
    <span class="summe">${d.export.anzahl}</span></div>
  <div class="mrow"><span class="art">Summe im Stapel</span>
    <span class="summe">${euro(d.export.brutto)}</span></div>
  ${d.export.anzahl < d.anzahl ? `<p style="color:var(--gc-desc);font-size:13px;margin-top:6px">
    ${d.anzahl - d.export.anzahl} Beleg${d.anzahl - d.export.anzahl===1?"":"e"}
    ${d.anzahl - d.export.anzahl===1?"ist":"sind"} noch nicht geprüft und fehlt${d.anzahl - d.export.anzahl===1?"":"en"} im Stapel.</p>` : ""}
  <button class="chip" style="margin-top:12px" id="export-knopf">Stapel herunterladen</button>
  <span id="export-status" style="font-size:12px;color:var(--gc-muted);margin-left:8px"></span>`;
```
(Das reine Zahlwort-Gefrickel mit Singular/Plural ist optional — notfalls „X Beleg(e)" nehmen, wichtig ist der erklärende Satz, nicht die Grammatik.)

**Test:** `server/belegreview/tests/test_zahlen_lesen.py` (oder passendste bestehende Test-Datei für `_monat_summen`/`api_monat`) — neuer Test `test_monat_route_liefert_export_teilmenge`: zwei Belege im Monat anlegen, einen „geprüft", einen „erfasst" — `GET /api/monat/{monat}` muss `export.anzahl == 1` und `export.brutto == <brutto des geprüften>` liefern, während `anzahl == 2`.

**Risiko:** sehr gering — rein additiv (`daten["export"]` ist ein neues Feld, nichts Bestehendes ändert sich), und die einzige bisherige Fehlerquelle (`d.summe` existierte nie) verschwindet.

---

### 1b — P0-2: Vorsteuer — gedruckte Steuerzeilen gewinnen

**Server, Datei/Funktion/Zeile:** `server/belegreview/babu_web.py:2025-2082` (`_review_aus_einschaetzung`), konkret Zeile 2030-2039.

**Änderung:**
```python
brutto = buchung.get("betrag_eur")
try:
    satz = int(buchung.get("ust_satz") or 0)
except (TypeError, ValueError):
    satz = 0
steuersaetze = buchung.get("steuersaetze") or []
netto = ust = None
summenprobe_ok = None
if steuersaetze and isinstance(brutto, (int, float)):
    tabellen_brutto = round(sum(float(s.get("brutto") or 0) for s in steuersaetze), 2)
    if abs(tabellen_brutto - float(brutto)) < 0.02:
        # Die Steuertabelle aus Gemmas gelesenen Positionen deckt den
        # Betrag — sie trägt Pfand/Mischsätze korrekt, der einzelne Satz
        # auf den Gesamtbetrag würde das ignorieren (Ninas Anmerkung P0-2).
        netto = round(sum(float(s.get("netto") or 0) for s in steuersaetze), 2)
        ust = round(sum(float(s.get("ust") or 0) for s in steuersaetze), 2)
        summenprobe_ok = abs(netto + ust - float(brutto)) < 0.02
if netto is None and isinstance(brutto, (int, float)) and satz in (7, 19):
    netto = round(brutto / (1 + satz / 100), 2)
    ust = round(brutto - netto, 2)
elif netto is None and isinstance(brutto, (int, float)):
    netto, ust = round(float(brutto), 2), 0.0
```
`"summenprobe_ok": None,` in der `felder`-Dict (Zeile 2059) durch `"summenprobe_ok": summenprobe_ok,` ersetzen. Das setzt `_status_ableiten` (babu_web.py:645-660) endlich echt: eine gerissene Probe (Tabelle vorhanden, Summe passt nicht zu `brutto`) landet weiterhin über `summenprobe_ok is False` in „nachfrage" — bisher unmöglich, weil immer `None`.

**Prompt-Ergänzung, Datei/Funktion/Zeile:** `server/belegreview/gemma_buchung.py`, REGELN-Konstante (Zeile ~90-143). Neue Regel direkt nach der Reverse-Charge-Regel (Zeile 112-117) einfügen:
```
- Pfand (Flaschen, Kästen, Mehrweg) ist eine durchlaufende Kaution, KEINE
  Ware und KEIN Umsatz des Verkäufers: es trägt 0 % Umsatzsteuer. Steht auf
  dem Bon eine eigene Pfand-Zeile, gib sie als eigene Position mit
  ust_satz 0 aus — rechne sie NIE in die Bemessungsgrundlage der 19 %/7 %
  Positionen hinein. Weist der Bon Netto und Steuer bereits fertig
  aus, übernimm genau diese Werte, statt sie aus dem Bruttobetrag
  zurückzurechnen.
```
Im `SCHEMA`-Block (Zeile 167-183) das `positionen`-Beispiel um eine Mischsatz-Zeile mit Pfand erweitern (Kommentar, kein Pflichtteil des JSON-Schemas, aber als Beispiel im Prompt-Text daneben in `voller_prompt`/Doku bzw. als Testfall in `test_gemma_buchung.py`, siehe unten — SCHEMA selbst bleibt strukturell gleich, da `positionen` schon `ust_satz` pro Position trägt).

**iOS, Datei/Funktion/Zeile:** `ios/Beleg/Beleg/Store.swift:447-480` (`gemmaBuchungAnwenden`).

**Änderung:** Reihenfolge umkehren — erst prüfen, ob eine Tabelle (Gemmas `steuersaetze` ODER die schon auf dem Beleg liegende, von `FeldParser` gelesene `b.steuerPositionen`) den Brutto deckt, NUR wenn keine Tabelle passt, die blinde `brutto/(1+satz)`-Rechnung als letzten Fallback nehmen:
```swift
if betragEur > 0 {
    b.brutto = betragEur
    b.ustSatz = ustSatz
}
if !begruendung.isEmpty { b.begruendung = begruendung }
var gedeckt = false
if !steuersaetze.isEmpty {
    steuertabelleAnwenden(&b, steuersaetze)          // Gemmas gelesene Tabelle
    gedeckt = b.summenprobeOK
}
if !gedeckt, let ocr = b.steuerPositionen, !ocr.isEmpty {
    steuertabelleAnwenden(&b, ocr)                    // gedruckte Zeilen vom Gerät
    gedeckt = b.summenprobeOK
}
if !gedeckt, betragEur > 0 {
    b.netto = (betragEur / (1 + Double(ustSatz) / 100) * 100).rounded() / 100
    b.ust = ((b.brutto - b.netto) * 100).rounded() / 100
    b.summenprobeOK = false   // ehrlich markieren: geschätzt, nicht geprüft
}
```
`steuertabelleAnwenden` (Store.swift:485-495) bleibt unverändert (prüft schon `abs(summe - b.brutto) < 0.02`). Wichtig: `b.steuerPositionen` (das OCR-Ergebnis aus `FeldParser.swift:133-141`) darf NICHT vor diesem Aufruf überschrieben werden — aktuell passiert das nicht, aber die neue Reihenfolge macht das Vertrauensverhältnis explizit (Kommentar im Code ergänzen: „Gedruckte Zeilen gewinnen vor der Rückrechnung — Pfand ist sonst jeden Monat falsch, Ninas Anmerkung P0-2").

**Test (Server):** `server/belegreview/tests/test_gemma_buchung.py` — neuer Test `test_pfand_bleibt_steuerfrei_in_der_positionsliste` (prüft `_steuertabelle` mit einer Position `ust_satz=19` und einer `ust_satz=0` (Pfand), erwartet zwei Einträge, keinen gemeinsamen falschen 19%-Wert). Neuer Test in `server/belegreview/tests/test_beleg_bearbeiten.py` oder einer neuen Datei `test_review_steuertabelle.py`: `_review_aus_einschaetzung` mit `buchung["steuersaetze"] = [{"satz":19,"brutto":59.06,"netto":49.63,"ust":9.43},{"satz":0,"brutto":6.67,"netto":6.67,"ust":0.0}]`, `betrag_eur=65.73` → erwartet `netto=56.30`, `ust=9.43`, `summenprobe_ok=True` (nicht `55.24/10.49`). Zweiter Fall: `steuersaetze` fehlt/leer → alter Pfad, `summenprobe_ok=None` bleibt Fallback-Verhalten.

**Test (iOS):** `ios/Tests/karte/main.swift` (oder neue Datei im selben Verzeichnis) — Fixture mit `betragEur=65.73`, `ustSatz=19`, leeres `steuersaetze`, aber `b.steuerPositionen` vorbelegt mit dem gedruckten Netto/USt (57,06/8,67) — erwartet `b.netto == 57.06`, `b.ust == 8.67` nach `gemmaBuchungAnwenden`, nicht die zurückgerechneten 55,24/10,49. `ios/Tests/run.sh` ausführen.

**Risiko:** hoch — betrifft direkt die DATEV-Vorsteuer-Zeile (Steuerschlüssel 9), also Zahlen, die an die Kanzlei gehen. Vor dem Deploy: Golden-Diff nach CLAUDE.md-Ritual zwingend, und den konkreten Beleg aus dem Befund (Getränkemarkt, 04.08., 65,73 €) nach dem iOS-Merge im Simulator nachstellen, falls die Rohdaten/ein Fixture dafür verfügbar sind (Testdaten liegen laut CLAUDE.md nur lokal in `~/Downloads`, nicht committen — als manueller Rauchtest, nicht als Repo-Fixture).

---

## Runde 2 — P0-4: „Wird gelesen" darf nicht ewig stehen bleiben

Zwei Teile: (a) Portal-Uploads bekommen überhaupt eine Lesung, (b) ein Timeout-Zustand für alles, was trotzdem hängen bleibt. Beide request-getriggert, kein Watcher (verbindliche Vorgabe CLAUDE.md/HANDOVER.md).

### 2a — Server-seitige Lesung für Portal-Uploads

**Befund:** `POST /api/hochladen` (babu_web.py:1720-1751) und `POST /ablage` (babu_web.py:1629-1707) schreiben nur `docs/<monat>/<datei>` und schreiben NIE `review/<stamm>.json` — nur `/api/aufnahme` mit App-`ergebnis` tut das (babu_web.py:1939-1968).

**Änderung — geteilte Lese-Funktion zuerst extrahieren**, Datei `babu_web.py`, aus `api_buchung_einschaetzung` (Zeile 3483-3580): den Kontext-Aufbau (Verträge, Personal, Umsätze, Nachbarn, offene Abbuchungen, Profil) in eine Hilfsfunktion `_einschaetzungs_kontext(un, monat) -> dict` ziehen (reine Extraktion der Zeilen 3512-3568), die sowohl die bestehende Route als auch der neue Hintergrund-Lesepfad aufrufen.

**Neue Funktion** `_beleg_serverseitig_lesen(pfad: str, daten: bytes, endung: str, un: str) -> None`, aufgerufen als `asyncio.create_task` (fire-and-forget, mit Timeout) direkt nach dem `boxschreiber.schreiben`-Commit in `api_hochladen` (Zeile 1745-1751) und in `ablage` (Zeile 1698-1707):
```python
async def _hintergrund_lesen(pfad, daten, endung, un):
    try:
        async with asyncio.timeout(BELEG_LESE_FRIST_SEK):  # z.B. 90s
            await _beleg_serverseitig_lesen(pfad, daten, endung, un)
    except (TimeoutError, Exception) as ex:  # noqa: BLE001
        print(f"[lesen] {pfad}: {ex!r}", flush=True)
        # Kein Review geschrieben — der Beleg bleibt "erfasst", bis ihn
        # die Timeout-Anzeige (2b) auffängt oder Nina "Nochmal versuchen" tippt.
```
`_beleg_serverseitig_lesen` selbst:
- Für `.pdf` ohne mitgeschickten Text: `abschluss_lesen.seiten_text` (bereits genutztes Muster, babu_web.py:1856-1864) → `zeilen`, kein Bild.
- Für Bilder (`.jpg/.jpeg/.png/.heic`): kein Vision-Text vorhanden (kommt nur vom iPhone) → `bild=(daten, mime)` an `gemma_buchung.runde` geben — das ist exakt der in HANDOVER.md beschriebene Fallback-Weg „Gemma 4 Vision liest den Beleg SELBST … falls einmal kein Bild vorliegt" (gemma_buchung.py Docstring Zeile 4-8), hier umgekehrt: kein Vision-Text, dafür das Bild direkt.
- `run_in_threadpool(gemma_buchung.runde, zeilen, profil, [], rahmen, umsaetze, nachbarn, None, bild, vertraege_ktx, personal_ktx, offene_abbuchungen)` — `antworten=[]`, da niemand am Portal Rückfragen beantwortet; bei `status == "fragen"` oder `"aufgeben"` wird **kein** Review geschrieben (Beleg bleibt „erfasst" bis Timeout/„Nochmal versuchen"/manuelles Nachtragen — kein Blockieren, kein Fehlerzustand).
- Bei `status == "gebucht"`: `_review_aus_einschaetzung(pfad, ergebnis["buchung"], zeilen, ergebnis["buchung"]["dokumentklasse"])` genau wie in `/api/aufnahme` (Zeile 1941-1943), Doppelgänger-Check aus Zeile 1946-1960 mit übernehmen, dann `boxschreiber.schreiben({f"review/{stamm}.json": ..., f"review/{stamm}.md": ...}, ..., f"lesen: {stamm}", un)` als **zweiten** Commit (der erste, der die Datei ablegt, ist schon durch — sauberer als beides in einer Transaktion zu zwingen, und konsistent mit dem bestehenden Doppel-Commit-Muster nirgends anders im Code, aber hier nötig, weil die Lesung erst NACH dem Ablegen beginnt).
- `run_in_threadpool` + `asyncio.timeout` sorgt dafür, dass ein hängender vLLM-Aufruf (`VLM_FRIST=120s` in `gemma_buchung.py`) den Request-Handler nicht blockiert — der Upload-Request selbst kehrt sofort zurück, die Lesung läuft im Hintergrund des Serverprozesses (kein separater Prozess/Dienst, kein Watcher-Neubau — läuft nur, wenn ein Request sie ausgelöst hat).

**Explizit NICHT tun:** keine Datei `review_watcher.py` neu anlegen, keine Endlosschleife, kein pm2-Eintrag — CLAUDE.md verbietet das ausdrücklich. Der `asyncio.create_task` lebt nur für die Dauer dieses einen Requests/Prozesses und verschwindet mit ihm; das ist erlaubt, weil er von einem Request ausgelöst wird, nicht selbstständig pollt.

**Test:** neue Datei `server/belegreview/tests/test_portal_upload_liest_serverseitig.py`:
- `POST /api/hochladen` mit einem PDF, das lesbaren Text enthält, `monkeypatch` auf `gemma_buchung.runde` (liefert festes `{"status":"gebucht","buchung":{...}}`) → nach `await`/kurzer Wartezeit im Test (`await asyncio.sleep(0)`-Schleife oder die Hintergrundfunktion synchron im Test aufrufen statt über `create_task`, um Flakiness zu vermeiden) muss `review/<stamm>.json` existieren und `index_aktuell()["belege"][stamm]["status"] == "geprüft"` sein.
- Timeout-Fall: `gemma_buchung.runde` wirft/hängt → kein Review, Beleg bleibt „erfasst", kein 500 auf der Upload-Route selbst.
- Bild-Fall: `.jpg`-Upload → `_beleg_serverseitig_lesen` ruft `gemma_buchung.runde` mit `bild=(...)`, nicht mit `zeilen`.

**Risiko:** hoch — neuer Codepfad mit externem Modellaufruf im Hintergrund eines Web-Requests. Sorgfältig gegen Doppel-Lesung absichern (z. B. wenn zwei fast gleichzeitige Requests denselben Stamm treffen — unwahrscheinlich, da `beleg_dateiname` einen Zufalls-Hex trägt, aber die Funktion sollte idempotent sein: vor dem Schreiben prüfen, ob `review/<stamm>.json` inzwischen schon existiert, sonst überschreibt der Hintergrund-Task eine zwischenzeitliche manuelle Eintragung über `/api/angaben`). Diese Race explizit im Code kommentieren und in einem Test abdecken (`test_hintergrund_lesung_ueberschreibt_keine_manuelle_angabe`).

### 2b — Timeout-Status, wenn auch die Hintergrund-Lesung nicht durchkommt

**Datei/Funktion/Zeile:** `server/belegreview/babu_web.py:645-660` (`_status_ableiten`).

**Änderung:**
```python
BELEG_HAENGT_NACH_MIN = 20

def _status_ableiten(review: dict | None, bewirtung_da: bool,
                      hochgeladen: str | None = None) -> str:
    if review is None:
        if hochgeladen and _minuten_seit(hochgeladen) > BELEG_HAENGT_NACH_MIN:
            return "unlesbar"
        return "erfasst"
    ...
```
`_minuten_seit` als kleiner Helfer (ISO-8601-Parsing von `%cI`, `datetime.fromisoformat`, Zeitzonen-sicher). Aufrufer bei babu_web.py:778 (`"status": _status_ableiten(review, bewirtung_da)`) um `eintrag["hochgeladen"]` ergänzen — das Feld existiert im selben Dict bereits zwei Zeilen darüber (Zeile 777).

**Portal, Datei/Funktion/Zeile:**
- `portal.html:1498-1505` (`statusSatz`) — neuer Zweig ganz oben: `if (z.status === "unlesbar") return ["Konnte nicht gelesen werden — magst du drauf schauen?","frage"];`
- `portal.html:1804-1809` (`statusMarke`) — fällt automatisch auf `["frage offen","warn"]`, kein Zusatzcode nötig.
- `portal.html:1989-2012` (Detailansicht) — Zeile 1990 `inArbeit` bleibt für „erfasst"; neuer Zweig `const haengt = d.status === "unlesbar";` und bei `haengt` zwei Buttons unter der bestehenden `aenderungsFormular`-Karte (die für `!f.brutto` ohnehin schon sichtbar ist, Zeile 2066 — „Selbst eintragen" ist damit für „unlesbar" bereits abgedeckt, da `f.brutto` bei fehlendem Review immer `null` ist): einen Button „Nochmal versuchen", der eine neue Route aufruft.

**Neue Route** (Name bewusst NICHT `neu-lesen`, um jede Verwechslung mit der am 27.08. gelöschten `review_watcher`-Route `/review/<stamm>/neu-lesen` zu vermeiden — anderer Mechanismus, anderer Name):
```python
@app.post("/api/beleg/{stamm}/erneut-lesen")
async def api_beleg_erneut_lesen(stamm: str, request: Request) -> Response:
    un, fehler = _box_wache(request)
    if fehler: return fehler
    eintrag = (await run_in_threadpool(index_aktuell))["belege"].get(stamm)
    if eintrag is None or eintrag["status"] not in ("erfasst", "unlesbar"):
        return JSONResponse({"fehler": "Für diesen Beleg gibt es nichts erneut zu lesen."}, status_code=409)
    daten = await run_in_threadpool(_beleg_datei_laden, eintrag["datei"])  # Blob aus dem aktuellen Stand
    asyncio.create_task(_hintergrund_lesen(eintrag["datei"], daten,
                                           Path(eintrag["datei"]).suffix.lower(), un))
    return JSONResponse({"ok": True, "hinweis": "Wir schauen nochmal drauf."})
```
(`_beleg_datei_laden` als kleiner Helfer über `git_show`/`_blobs_lesen`, analog zu bestehenden Blob-Lesefunktionen in der Datei.)

Portal-Button ruft diese Route auf, zeigt danach `setTimeout(() => ladeDetail(stamm), 1500)` (gleiche Reload-Geste wie `angabenSenden`, Zeile 1974).

**Test:** `server/belegreview/tests/test_belegmonat.py` oder neue Datei `test_status_haengt.py`:
- `_status_ableiten(None, False, hochgeladen="<vor 25 Min>")` → `"unlesbar"`.
- `_status_ableiten(None, False, hochgeladen="<vor 5 Min>")` → `"erfasst"` (unverändert).
- Route-Test: `POST /api/beleg/{stamm}/erneut-lesen` auf einem `unlesbar`-Beleg → `200`, auf einem `geprüft`-Beleg → `409`.

**Sprachregel-Check:** „Konnte nicht gelesen werden" enthält kein verbotenes Wort (`[Ll]esung` matcht nicht auf „gelesen"), „Nochmal versuchen" ebenfalls unauffällig — trotzdem `test_sprachregel.py` laufen lassen, da der Linter auf reinen Substring-Matches arbeitet und keine Wortgrenzen-Rücksicht auf Komposita nimmt (sicherheitshalber prüfen, kein manuelles Vertrauen).

**Risiko:** mittel. `BELEG_HAENGT_NACH_MIN = 20` ist eine Annahme — mit Nina/Produktverantwortlicher abstimmen, ob 20 Minuten sinnvoll sind (der Befund nennt „seit 5 Tagen", jede vernünftige Schwelle behebt das). Die neue Route teilt sich den `_box_wache`-Zugriffsschutz mit allen anderen Belegrouten (Sicherheitsregel aus CLAUDE.md: „Neue Routen immer über `_box_wache`/`box_mitglied` absichern" — hier erfüllt).

---

## Runde 3 — P1-6: Kassenbuch + Rechnung am Rechner

Drei nahezu unabhängige Unterpunkte (Kassenbuch, Rechnung, Termine-Woche) + der Salon-Check-Korrekturpfad. Alle vier passen in einen Commit, weil sie alle „App-only" Texte durch echte Formulare ersetzen, aber ich würde sie in 3 Teilcommits liefern (Kassenbuch+Rechnung sind am dringendsten laut Auftrag-Reihenfolge „6").

### 3a — Kassenbuch-Formular im Portal

**Datei/Funktion/Zeile:** `portal.html:3603-3605` (in `ladeAbschluss`) — der Textblock „Trag sie in der App im Kassenbuch ein" wird durch ein echtes Formular ersetzt, das nur erscheint, wenn `!e.tage` (kein Kassenblatt für den Monat) UND es sich um den aktuellen oder einen noch nicht festgeschriebenen Monat handelt.

**Änderung:**
- Neue JS-Funktion `kassenbuchFormular(profil)` — rendert ein Datumsfeld (Default: heute) + je Frage aus `profil.fragen` (Struktur `{feld, frage, hilfe}`, `monatsabschluss.umsatz_profil`, Zeile 71-94) ein Eingabefeld, plus die fixen Pflichtfelder aus `KASSENBUCH_ZAHLEN` (babu_web.py:5483-5490): mindestens `einnahmenBar`, `ecZahlungen`, `bestandVortag`, `gezaehltSchluss` — nicht alle 17 Felder auf einmal zeigen (das wäre wieder Buchhalter-Overkill), sondern die aus dem `profil.fragen` plus die vier genannten Kernzahlen; alles andere bleibt optional/eingeklappt unter „Mehr Angaben" (Trinkgeld, Auslagen, Vorschuss).
- POST-Body exakt wie App: `{datum, ...KASSENBUCH_ZAHLEN-Felder, grund}` an `POST /api/kassenbuch` (babu_web.py:9337).
- 409-Antwort (`kassenfest.darf_schreiben`, babu_web.py:9389-9393) im Formular auffangen: wenn `abgeschlossen: true` im Fehlerkörper, ein Grund-Textfeld einblenden und den Request mit `grund` wiederholen (dasselbe Muster wie die App laut Warnung im Auftrag „409 message" — konkret: erster Versuch ohne `grund`, bei 409 erscheint „Dieser Tag ist schon eingetragen — kurz sagen, warum du änderst" + Textfeld + „Trotzdem speichern").
- GET-Vorbelegung über `GET /api/kassenbuch/{datum}` (babu_web.py:9317-9334) beim Öffnen des Formulars, damit ein bereits erfasster Tag nicht leer wirkt.

**Test:** neue Datei `server/belegreview/tests/test_kassenbuch_im_portal.py` — reiner Backend-Test, der die Route mit Portal-typischem Body (Cookie-Session statt PAT) durchspielt: Normalfall (kein Vorher-Stand) → 200; zweiter Schreibversuch ohne `grund` auf denselben Tag → 400 mit erwartetem Fehlertext; mit `grund` → 200. (Die Route selbst ist unverändert, dieser Test dokumentiert nur, dass der Portal-Weg denselben Vertrag erfüllt — `test_kassenbuch_blatt.py`/`test_kassenfest.py` decken die Route selbst schon ab.)

**Risiko:** mittel — GoBD-relevant (Kassenbuch). Die Route selbst bleibt unverändert, nur ein neuer Client. Wichtig: das Portal-Formular darf **keine** eigene Rundungs-/Berechnungslogik einführen, die von der App abweicht — alle Zahlen 1:1 als eingegeben an den Server, Rundung macht `api_kassenbuch` selbst (Zeile 9354).

### 3b — Rechnung-Formular im Portal

**Datei/Funktion/Zeile:** `portal.html:4259-4260` (`ladeRechnungen`).

**Änderung:** Formular mit Kundin/Position(en)/Betrag/Datum → `POST /api/rechnungen` (babu_web.py:6035, vergibt die Nummer serverseitig). Nach Erfolg: `POST /api/rechnung/{nummer}/pdf` (babu_web.py:6107) aufrufen, um das PDF serverseitig erzeugen zu lassen — das bedeutet: die iOS-seitige `RechnungPDF.swift`-Logik (Layout) muss **serverseitig nachgebaut oder aus der Portal-Sicht nicht nötig sein**, wenn `/api/rechnung/{nummer}/pdf` bereits ein PDF zurückgibt/erzeugt. Das muss vor der Umsetzung geklärt werden: **prüfen, ob `/api/rechnung/{nummer}/pdf` das PDF selbst rendert oder nur ein von der App mitgeschicktes PDF ablegt** — falls Letzteres, fehlt für den Portal-Weg noch ein serverseitiger PDF-Renderer (das wäre dann ein zusätzlicher Arbeitsschritt, den ich hier nicht unterschätzen will; ich habe die Route nicht bis in die PDF-Erzeugung gelesen). **Empfehlung:** vor Umsetzungsbeginn `rechnungen.py`/die Route bei `babu_web.py:6107` genau lesen, ob ein serverseitiger PDF-Weg (z. B. via `weasyprint`/`reportlab`, falls vorhanden) existiert oder ob RechnungPDF.swift wirklich der einzige Renderer ist — das entscheidet, ob dies ein UI-Task oder ein UI+Backend-Task ist.
- Bis dahin minimal-invasiv: Formular erzeugt die Rechnung (Nummer, Pflichtangaben-Prüfung über `fehlende_pflichtangaben`), zeigt „Rechnung Nr. X angelegt — das PDF folgt in der App" als Zwischenlösung, falls sich herausstellt, dass PDF-Rendering wirklich nur in Swift existiert.
- Bezahlt/Storno (`/bezahlt` :6137, `/storno` :6171) sind reine Status-Buttons — unkompliziert im Portal nachzubauen, keine Unklarheit.

**Test:** `server/belegreview/tests/test_rechnungen_api.py` erweitern um einen Portal-Session-Test (Cookie statt PAT) für `POST /api/rechnungen` — falls dort noch nicht abgedeckt.

**Risiko:** mittel-hoch, abhängig von der oben offenen PDF-Frage. Das ist der einzige Punkt in diesem Plan, den ich nicht zu Ende verifizieren konnte, ohne `rechnungen.py` und `RechnungPDF.swift` vollständig zu lesen — als Rechercheauftrag vor Runde 3b klar benennen.

### 3c — Termine-Wochenansicht

**Datei/Funktion/Zeile:** `portal.html:4422-4427` (`ladeTermine`) und `:4909-4911` (Tages-Stepping).

**Änderung:** Die Route braucht **keine** Änderung (`GET /api/termine?von&bis`, babu_web.py:6453, unterstützt bereits Bereiche, Zeile 6470-6478 loopt schon tageweise). Nur `ladeTermine` umbauen: `von`/`bis` auf Wochenanfang/-ende (Mo-So) statt `tTag`/`tTag` setzen, Rendering von einer Tagesliste auf 7 Spalten/Abschnitte (ein `<div class="lbl">` pro Wochentag, analog zum bestehenden Listenmuster). Stepping-Buttons (Zeile 4909-4911) von Tag- auf Wochenschritte umstellen (`setDate(d.getDate()+7)` statt `+1`).

**Test:** kein neuer Backend-Test nötig (Route unverändert). `test_portal_verdrahtung.py` deckt ab, dass die Ansicht registriert bleibt, falls IDs sich ändern.

**Risiko:** gering — reine Client-Änderung, Server-Vertrag bereits vorhanden und stabil.

### 3d — Salon-Check: Korrekturfeld für graue Karten

**Datei/Funktion/Zeile:** `server/belegreview/saloncheck.py:53-58` (`_grau`), `portal.html:3269-3282` (`scReport`), `babu_web.py:4205-4222` (`db_abschluss_snapshot`/`db_abschluss_lesen`).

**Änderung:**
- Neue Route `POST /api/abschluss/karte-korrektur` — Body `{jahr, karte_id, wert}`, lädt `db_abschluss_lesen(un)`, sucht in `status["karten"]` den Eintrag mit `id == karte_id`, setzt `wert` (und optional `ampel` von `"grau"` auf `"gruen"` mit einem Zusatzfeld `"von_nutzerin_bestaetigt": True`), schreibt über `db_abschluss_snapshot(un, jahr, status)` zurück.
- `portal.html:3269-3282` (`scReport`): wenn `k.ampel === "grau"`, statt nur `k.satz` als Text ein `<input>` + „Speichern"-Button einblenden, das die neue Route aufruft und danach den Report neu lädt.

**Wichtiger Vorbehalt:** Ich konnte nicht abschließend prüfen, **welches konkrete Zahlenfeld** hinter jeder `_grau(...)`-Karte steckt (verschiedene Aufrufer in `abschluss_lesen.py`/`saloncheck.py` erzeugen vermutlich unterschiedliche graue Karten für unterschiedliche Unsicherheiten — Umsatzsteuer-Voranmeldung, AfA, Kassendifferenz o. ä.). **Vor der Umsetzung**: alle Aufrufstellen von `_grau(` in `saloncheck.py` und `abschluss_lesen.py` auflisten und für jede einzeln festlegen, ob eine einzelne Zahl reicht oder ob (wie bei den anderen Formularen) mehrere Felder nötig sind. Das ist der am wenigsten scharf spezifizierte Punkt dieser Runde — als eigener kleiner Rechercheschritt vor der Implementierung einplanen, nicht blind umsetzen.

**Test:** `server/belegreview/tests/test_saloncheck_api.py` erweitern um `test_graue_karte_laesst_sich_korrigieren` (Route setzt `wert`, Ampel wechselt, `db_abschluss_lesen` liefert den neuen Stand).

**Risiko:** mittel, mit der oben genannten Unschärfe als Hauptrisiko.

---

## Runde 4 — P1-5: Desktop-Layout

**Datei/Funktion/Zeile:** `portal.html:99-117` (`.spalten`-Klasse, bereits vorhanden, aber nirgends benutzt — 0 Treffer für `class="spalten"`).

**Änderung, minimal-invasiv (keine neue CSS nötig, nur Anwendung):**
- `ladeHeute` (ab Zeile 1676): den `#heute-inhalt`-Container-Innenhalt in eine `<div class="spalten">`-Hülle packen, Überschriften/breite Elemente (z. B. der „Bleibt dir"-Block) mit `class="voll"` markieren, damit sie über beide Spalten gehen (CSS-Regel dafür existiert schon: `.spalten > .lbl, .spalten > h2, .spalten > .voll{grid-column:1/-1}`, Zeile 116).
- `ladeZahlen`/`ladeAbschluss`: ebenso — die Kacheln/Karten in `.spalten` einhüllen, damit bei ≥1180px zwei Karten nebeneinander stehen statt eine 760px-breite Säule in einem 1440px-Fenster (Zeile 2446 hat aktuell `max-width:760px` inline — das kann bleiben oder auf `.voll` reduziert werden, je nachdem wie breit die Balkengrafik wirken soll).
- **Belege als Tabelle ab 1180px:** `belegZeile` (portal.html:1810-1821) ist aktuell eine Kachel/Listenzeile. Neue Variante `belegTabellenzeile(z)` mit `<tr><td>Datum</td><td>Laden</td><td>Betrag</td><td>Kategorie</td><td>Status</td></tr>`, per `@media (min-width:1180px)` per CSS umgeschaltet (zwei Renderpfade in `ladeBelege`, ausgewählt über `window.matchMedia('(min-width:1180px)').matches`, oder beide DOM-Varianten rendern und per CSS ein-/ausblenden — letzteres ist robuster gegen Resize ohne Reload, aber verdoppelt den DOM; angesichts von max. ~200 Belegen pro Monat vertretbar). Sortierbarkeit: Klick auf Spaltenkopf sortiert das bereits geladene Array clientseitig neu (`Array.prototype.sort` auf `d.belege`), keine neue Route nötig.
- **Belegliste links + Detail rechts** (echtes Master-Detail wie bei `#detail-grid`, Zeile 472-473, das bereits das einzige Zwei-Spalten-Muster im Haus ist): bei ≥1180px in der `a-belege`-Ansicht ein zweispaltiges Layout, linke Spalte = Tabelle, rechte Spalte = Inline-Detail (per `location.hash`-Änderung ohne vollen Seitenwechsel — technisch aufwendiger, da `ladeDetail` aktuell eine eigene Ansicht `a-detail` befüllt, keine Teilansicht). **Empfehlung:** das Master-Detail-Layout als eigenen, späteren Feinschliff nach der Tabellenansicht behandeln (höherer Aufwand, geringerer Grenznutzen gegenüber der Tabelle allein) — in der Kommunikation mit dem Nutzer als „Tabelle zuerst, Splitscreen als Nachtrag" vorschlagen, falls Zeit knapp wird.

**Test:** `test_portal_verdrahtung.py` läuft mit (keine neuen Views). Kein automatisierter Breite-Test vorhanden — manuelle Prüfung bei 1440px im `portal-vorschau` (siehe Verifikation) ist hier der einzig praktikable „Test".

**Risiko:** gering bis mittel — reine CSS/Layout-Änderung ohne Server-Kontakt, aber mit Reichweite über viele Views. Regressionsgefahr: bestehende Inline-`max-width`-Werte (760px, 46ch, 880px, 560px — Zeile 953/1412/2446/3039) nicht versehentlich doppelt begrenzen, wenn sie jetzt in einem `.spalten`-Grid-Item liegen (Grid-Item + `max-width` können zu ungewolltem Leerraum in der Spalte führen — bei jeder Anwendung einzeln im Browser prüfen).

---

## Runde 5 — restliche P1: Ablage-Namen (7) und Löschen (8)

### 5a — P1-7: Kontoauszug-Titel synthetisieren

**Datei/Funktion/Zeile:** `server/belegreview/kontoauszug.py:20-68` (`parse_text`), `server/belegreview/babu_web.py:5592-5616` (`_abschluss_beiakten`) und `:5676-5684` (`_ablage_eintraege`, Titel-Zuweisung für `auszuege/`).

**Kernbefund (selbst verifiziert, geht über die Erkundung hinaus):** `_abschluss_beiakten()` indiziert **nur** `.meta.json`-Dateien (Zeile 5606-5609) — für Kontoauszüge wird aber nie eine `.meta.json` geschrieben, sondern nur `.umsaetze.json` (babu_web.py:2534-2538, :1925-1927). `beiakten.get(pfad)` ist für jeden Auszug also **immer** `{}`, und `titel = beiakte.get("titel") or name` (Zeile 5684) fällt deshalb strukturell **immer** auf den Rohdateinamen zurück — das ist kein Zufall, sondern der eigentliche Grund für den Befund.

**Änderung:**
1. `kontoauszug.py:parse_text` um eine einfache Banknamen-Erkennung erweitern: eine kleine Stichwortliste (`("Kreissparkasse", "Sparkasse", "Volksbank", "Commerzbank", "Deutsche Bank", "Postbank", "ING", "DKB", "comdirect", "GLS Bank")`) über die ersten ~15 Zeilen des Texts laufen lassen, ersten Treffer als `bank` zurückgeben; Rückgabe-Dict um `"bank": bank` erweitern (Default `None`).
2. `_abschluss_beiakten()` (oder eine parallele neue Funktion `_auszug_umsaetze()`, um die bestehende Funktion nicht mit einer zweiten Zuständigkeit zu überladen) zusätzlich `.umsaetze.json`-Blobs für `auszuege/`-Pfade einsammeln (dieselbe `_git ls-tree`/`_blobs_lesen`-Technik, nur mit `.endswith(".umsaetze.json")` statt `.meta.json`).
3. `_ablage_eintraege`, Zeile 5676-5684: wenn keine `.meta.json`-Titel vorhanden ist, aber `.umsaetze.json`-Daten mit `monat`/`bank`:
   ```python
   if not titel_aus_meta:
       um = auszug_umsaetze.get(pfad) or {}
       if um.get("monat"):
           monatname = monatslauf.monatsname(um["monat"])
           jahr = um["monat"][:4]
           titel = f"Kontoauszug {monatname} {jahr}" + (f" · {um['bank']}" if um.get("bank") else "")
   ```
   (`import monatslauf` ergänzen, falls noch nicht importiert.)

**Test:** `server/belegreview/tests/test_kontoauszug.py` — neuer Test `test_parse_text_erkennt_die_bank` (Text mit „Kreissparkasse …" → `bank == "Kreissparkasse"`; Text ohne Bankname → `bank is None`, kein Crash). `server/belegreview/tests/test_ablage_ordner.py` — neuer Test `test_auszug_titel_wird_synthetisiert` (einen Auszug mit `.umsaetze.json{monat:"2026-07", bank:"Kreissparkasse"}` ablegen, `_ablage_eintraege()` muss `titel == "Kontoauszug Juli 2026 · Kreissparkasse"` liefern statt des Rohdateinamens).

**Risiko:** gering — additiv, alter Fallback (`.meta.json`-Titel, dann Rohname) bleibt vollständig erhalten für Fälle ohne erkannten Monat/Bank (z. B. Fotos statt PDF, andere Bank-Formate).

### 5b — P1-8: Löschen aus der Kachel-/Zeilenebene entfernen

**Datei/Funktion/Zeile:** `portal.html:2707-2717` (`ablageWerkzeug`), aufgerufen aus `ablageKachel` (Zeile 2691) und `ablageZeile` (Zeile 2700) UND aus der Detailansicht `ladeUnterlage` (Zeile 2869).

**Änderung:** `ablageWerkzeug(s)` in zwei Varianten aufteilen:
```js
function ablageWerkzeugKurz(s){   // für Kachel/Zeile — kein Löschen
  const ordnerbar = /^(dokumente|abschluss)\//.test(s.pfad) && meineRolle !== "mitarbeit";
  const wie = esc(s.titel).replace(/'/g, "");
  return ordnerbar ? `<div class="stueck-werkzeug">
    <button onclick="ablageUmbenennen('${s.pfad}','${wie}')">Umbenennen</button>
    <button onclick="ablageVerschieben('${s.pfad}')">Verschieben</button>
  </div>` : "";
}
function ablageWerkzeugVoll(s){ /* bisheriger Inhalt von ablageWerkzeug, unverändert */ }
```
`ablageKachel`/`ablageZeile` (Zeile 2691/2700) rufen `ablageWerkzeugKurz(s)`; `ladeUnterlage` (Zeile 2869) ruft `ablageWerkzeugVoll(s)`. Der bestehende Löschen-Fluss (`loeschFragen`-Bestätigungsdialog, Zeile 3907; Routen `/api/dokument-loeschen`/`/api/auszug-loeschen`, unverändert) bleibt vollständig erhalten — nur der Auslöser-Button wandert aus der Kachel/Zeile in die Detailansicht. Belege selbst (`/api/beleg/{stamm}/loeschen`) hängen nicht an `ablageWerkzeug` (eigener Handler `belegLoeschen`, Zeile 3950 laut Erkundung) — dort separat prüfen, ob ein vergleichbarer Kachel-Button existiert und ggf. gleich behandeln (nicht explizit im Befund #8 genannt, aber dieselbe Logik gilt).

**Test:** kein Backend-Test nötig (Routen unverändert). `test_loeschen.py::test_die_ablage_zeigt_was_geloescht_werden_darf` (Zeile 250) bleibt unverändert gültig, da es die Server-Antwort (`loeschbar`-Feld) prüft, nicht die Portal-Darstellung.

**Risiko:** gering — reine UI-Verschiebung, kein Rechte-/Datenmodell-Eingriff.

---

## Runde 6 — P2 (Inkonsistenzen)

Alle folgenden sind unabhängig voneinander, kein Grund sie in einem Commit zu bündeln — ich würde je nach Umfang 3-4 kleine Commits daraus machen. Aufwand pro Punkt ist klein genug, um sie kompakt zu halten.

1. **Wochenlabels (9):** `portal.html:1823-1833` (`wochenGruppe`). Ursache: die Funktion vergleicht wahrscheinlich gegen „heute minus 7 Tage" statt gegen den Anfang der aktuellen Kalenderwoche, unabhängig vom angezeigten Monat. **Änderung:** `wochenGruppe(iso)` muss die Wochengrenzen aus `new Date()` (echtes Heute) berechnen — das ist vermutlich schon so, das eigentliche Problem laut Befund ist, dass die Funktion in `ladeBelege` (Zeile 1851) **unabhängig vom gerade betrachteten Monat `aktMonat`** immer gegen das echte Heute rechnet. Das ist fachlich sogar korrekt (August-Belege sind nie „diese Woche", wenn heute September ist) — der Befund zeigt aber einen Fall, wo genau das NICHT passiert (27.08. steht unter „Diese Woche"). **Konkret zu prüfen vor dem Fix:** das Datum, gegen das `wochenGruppe` vergleicht (`z.datum` = Belegdatum vs. `z.hochgeladen` = Upload-Zeit) — vermutlich vergleicht die Funktion versehentlich das Beleg-**Datum** eines am 27.08. fotografierten, aber erst am 01.09. hochgeladenen Belegs gegen das Hochlade-Datum eines anderen. **Test:** `wochenGruppe("2026-08-27")` am 02.09. aufgerufen muss für ALLE Belege mit demselben Datum denselben Gruppennamen liefern — als Unit-Test (falls JS-Testinfra fehlt, als Doku-Test in Python nachbilden, der die Logik der Funktion als Pseudocode gegenprüft, oder als manueller Rauchtest im Portal-Vorschau mit fingierten Daten).
2. **„Deine letzten Belege" unsortiert (10):** `babu_web.py:1034` (`_beleg_liste`, sortiert nach `hochgeladen`) + `portal.html:1770` (`/api/belege?limit=3`). Befund zeigt Daten 22.07./01.09./22.08. — das sind Beleg**daten**, nicht Hochlade-Zeiten; die Sortierung nach `hochgeladen` ist vermutlich beabsichtigt (jüngst hochgeladen zuerst), aber die Überschrift „Deine letzten Belege" suggeriert Sortierung nach Beleg**datum**. **Änderung:** entweder (a) Überschrift präzisieren („Zuletzt hochgeladen" statt „Deine letzten Belege"), oder (b) `limit=3` mit `order=datum` als neuer optionaler Query-Parameter in `/api/belege` (babu_web.py:1329-1347), Sortierschlüssel in `_beleg_liste` konfigurierbar machen. **Ich empfehle (a)**, da es der zutreffenden Semantik entspricht und keinen Server-Umbau braucht — „zuletzt hochgeladen" ist genau das, was Nina in dem Moment wissen will (was ist neu in ihrer Box), nicht das älteste/neueste Kaufdatum.
3. **Duplikat-Dialog ohne Antwort (11):** `babu_web.py:1953-1958` (`hinweis` landet in `felder.offen`), kein Resolve. **Änderung:** zwei Buttons „Ja, doppelt — löschen" (ruft `/api/beleg/{stamm}/loeschen` mit `grund` „Doppelgänger") und „Nein, zwei Einkäufe" (ruft `/api/angaben/{stamm}` mit einem Marker, der laut `_offen_nach_angaben` (Zeile 663-687) bereits ausreicht, um `offen` zu leeren — jedes gespeicherte Feld erledigt die Frage). Im Detail-View (`portal.html`, dort wo `f.offen` gerendert wird — Fundstelle in Erkundung nicht explizit genannt, bei der Umsetzung neben `aenderungsFormular` suchen) diese zwei Buttons zusätzlich zum bestehenden Formular einblenden, wenn der offene Punkt den Text „Doppelgänger" enthält (`o.includes("Doppelgänger")`).
4. **ISO-Datum bei Post-Fristen (12a):** `portal.html:2940` (`ladePost`) — `datumDeutsch`-Helfer existiert bereits (Zeile 3857-3864), nur nicht hier verwendet. **Änderung:** `${esc(e.bis_wann)}` → `${datumDeutsch(e.bis_wann)}`. Zusätzlich rote Markierung für überfällige Fristen: `new Date(e.bis_wann) < new Date()` → CSS-Klasse `frist-ueberfaellig` mit `color:var(--gc-danger)`. Trivial, kein Backend-Kontakt.
5. **Verträge „Frist steht im Vertrag" (12b):** `portal.html:4311-4314` (`ladeVertraege`). Prüfen, ob `vertraege.uebersicht()`/`vertraege_aktuell()` (babu_web.py:8549, `vertraege.py`) die `kuendigungsfrist` bereits liest (laut `ladeUnterlage`-Rendering, Zeile 2854, gibt es das Feld `v.kuendigungsfrist` durchaus!) — dann ist der Fix rein im Rendering von `ladeVertraege`: `v.kuendigungsfrist` statt des Platzhaltertexts anzeigen, falls vorhanden, sonst den Platzhalter als expliziten Fallback behalten.
6. **Post-Semantik (13):** `portal.html:1108` Überschrift. Einfachste Änderung: Überschrift „Was deine Kanzlei für dich bereitlegt" → „Post" (neutral), da laut Befund sowohl Finanzamt- als auch GEZ-Post darunterfällt und nichts davon originär „von der Kanzlei" kommt. Kein Backend-Eingriff.
7. **E-Mail ohne @ (14):** siehe eigene Analyse oben — **Server:** `babu_web.py:1313-1326` (`api_ich`) um `"hat_passwort": bool(nutzer_holen(un))` erweitern (`nutzer_holen` bereits in `api_passwort`, Zeile 1292, verwendet — reine Wiederverwendung). **Portal:** `portal.html:3358` `const eigenesKonto = (ich.un || "").includes("@");` → `const eigenesKonto = !!ich.hat_passwort;`, ebenso den `/api/ich`-Aufruf im Menü (Zeile 3412-3416) falls dort dieselbe Prüfung dupliziert wird. Zusätzlich Label „E-Mail" (falls irgendwo so beschriftet) auf „Angemeldet als" ändern, da `un` bei GitChain-Konten kein E-Mail-Format hat und das kein babu-Bug ist (das @ wird nicht serverseitig entfernt — es kommt von GitChains `whoami` schon ohne @, `wer_token`, Zeile 290-313 — das ist Fremdsystem, außerhalb dieses Repos zu klären, wenn ein echtes @ gewünscht ist). **Test:** `server/belegreview/tests/test_nutzer.py` — `test_api_ich_meldet_ob_ein_passwort_existiert` (Konto mit `nutzer`-Eintrag → `hat_passwort: true`; PAT-only-Konto → `false`).
8. **Team-Formular (15):** `portal.html:3487-3505` — bei „Fester Lohn" gewählt müssen die Stundenlohn-Felder (Zeile 3494/3501) per JS ein-/ausgeblendet werden (`change`-Listener auf dem Lohnart-Feld, `.hidden` auf dem jeweils anderen Feldblock). „Speichern"-Button: siehe Punkt 15 der Erkundung — CSS-Fix unten (Punkt „Speichern"-Styling) behebt das Knopf-Aussehen mit.
9. **CSS `.hin`-Styling (Teil von 15):** `portal.html:426` `.nachfrage .hin{...}` → in ein eigenständiges `.hin{...}` umwandeln (Ankerklasse ohne `.nachfrage`-Voraussetzung), damit alle 8 Fundstellen (Zeilen 1701, 1936, 2059, 2928-2929, 3507, 4995, 5035) einheitlich als Knopf erscheinen, unabhängig davon, ob die umgebende Karte `.nachfrage` trägt. Ein-Zeilen-CSS-Änderung, betrifft aber sichtbar 8 Stellen — vor dem Merge alle 8 im Portal-Vorschau ansehen, da mindestens eine (Zeile 2929) bereits ein eigenes `style="background:..."` mitbringt, das mit der neuen Basis nicht kollidieren darf.
10. **Kündigung vorangekreuzt (16):** `portal.html:3715` `<input type="checkbox" id="kw-kuendigen" checked>` → `checked` entfernen. Ein-Wort-Änderung, aber sicherheitsrelevant genug (Mandatskündigung als Default), um einzeln zu testen: `portal.html`-Grep nach `checked` an dieser Stelle nach dem Fix muss leer sein.
11. **Salon-Check unter „Belege" (17):** Sub-Tab-Bars `portal.html:968-973`/`1034-1039`/`1047-1052`. Das ist eine Navigations-Umstrukturierung (Salon-Check von einem Beleg-Subtab zu einem eigenständigen Auswertungs-Menüpunkt neben Ausgaben/Monatsabschluss) — **berührt `ansichten{}` und Menüführung**, `test_portal_verdrahtung.py` läuft danach zwingend mit vollem Ergebnis durch (neue/verschobene `a-`-Section + Menüeintrag müssen synchron bleiben). Größerer Umbau als die anderen P2-Punkte — als eigener kleiner Commit, nicht mit den Ein-Zeilen-Fixes vermischen.
12. **Zwei Personal-Views (18):** `a-personal` (Zeile 1338, `/api/mitarbeiter`, babu_web.py:6694) vs. `a-team` (Zeile 1124, `/api/team`, babu_web.py:8590) — laut Erkundung zwei **getrennte** Datenquellen für „dieselben Menschen", nur `team` fließt in die BWA (`team_personalkosten`, babu_web.py:8584). Das ist kein reiner UI-Fix, sondern eine mögliche **Datenzusammenführung** (zwei Tabellen `mitarbeiter`/`team` vs. eine Ansicht) — das würde ich NICHT blind in dieser Runde umsetzen, sondern zuerst klären, ob `mitarbeiter` und `team` fachlich wirklich identische Personen sind oder unterschiedliche Zwecke haben (z. B. Terminplanung vs. Lohnkosten). **Vorschlag für diese Runde:** nur die Navigation zusammenlegen (ein Menüpunkt „Dein Team", der beide Datensätze in Tabs zeigt), ohne die Datenmodelle zu verschmelzen — das ist risikoarm und behebt die Verwirrung, ohne BWA-Berechnungen anzufassen.
13. **„0 Sek."-Kacheln (19):** `portal.html:2365-2397` (`kennzahlKacheln`), Datenquelle `kennzahlen_monat` (babu_web.py:3400-3409). **Änderung:** vor dem Rendern prüfen `if (anzahl_belege < 5) return "";` (Kachel-Sektion ganz weglassen statt „0 Sek." zu zeigen). Serverseitig unverändert (die Rohzahl ist korrekt, nur die Darstellung bei wenig Daten ist irreführend).
14. **Fragen-Seite Weißraum (20):** `portal.html:1422-1437` (Markup), CSS `#chatlog`/`#chatform`/`#chatfrage`/`.beispiele` (Zeile 599-609). Reine CSS-Umsortierung (Eingabe + Beispiel-Chips nebeneinander, `#chatlog` mit `min-height` statt `flex:1`, das den Weißraum erzwingt). Kein Server-Kontakt.

**Übergreifender Test für Runde 6:** nach jedem Teil-Commit `test_portal_verdrahtung.py` und `test_sprachregel.py` laufen lassen (schnelle, harte Regressionswächter für genau diese Art von HTML-Umbauten).

---

## Runde 7 — P3 (Technik)

1. **Unauthentifiziertes `GET /portal` (21):** `babu_web.py:1048-1050`. **Vorschlag (Skizze, wie im Auftrag verlangt):** `portal.html` in zwei Dateien trennen — `portal-login.html` (nur Login-Maske + minimales JS für `POST /api/anmelden`, keine der ~80 API-Routen im DOM referenziert) wird bei `GET /portal` unauthentifiziert ausgeliefert; nach erfolgreichem Login liefert eine neue Route `GET /portal/app` (geschützt durch denselben `_api_wache`/Cookie-Check wie die Daten-Routen) das bisherige große Bundle (`portal-app.html`, Rest des heutigen Inhalts) aus. Der Login-Flow (`zeigeLogin`, aktuell portal.html:1516) bleibt clientseitig funktional identisch, holt aber nach erfolgreichem `/api/anmelden` das App-Bundle per `fetch` + `document.write`/dynamischem Import nach, statt dass es die ganze Zeit im DOM lag. **Umfang:** groß, echter Strukturbruch der Ein-Datei-Architektur — eigener, isolierter Umsetzungsauftrag, nicht nebenbei. `test_portal_verdrahtung.py` müsste auf beide Dateien erweitert werden.
2. **Caching (22):** `babu_web.py:1040/1045/1050/...` (`HTML_FRISCH`). Content-Hash-basiertes ETag auf `/portal` ergänzen (`hashlib.sha256(datei_bytes).hexdigest()[:16]` als `ETag`-Header, `If-None-Match` prüfen → 304), analog zum bereits vorhandenen Muster bei `/api/belege` (Zeile 1336-1338). Erst sinnvoll umsetzbar, NACHDEM Punkt 1 (Login/App-Split) entschieden ist, da sich sonst der Cache-Schlüssel für sicherheitsrelevanten Inhalt cached — Reihenfolge beachten.
3. **Fehlende `<label>` (23):** die 13 Stellen ohne `for=`-Zuordnung (Team-Formular 3490-3504, Personal 4627ff, Einstellungen, Chat 1434) bekommen `<label for="…">`+`id` am Input statt reinem Wrapping — mechanische, aber flächige Änderung; am besten zusammen mit den ohnehin in Runde 3/6 angefassten Formularen (Kassenbuch-Neubau, Team-Formular-Fix) miterledigen statt separat.
4. **Fünf Breakpoints (24):** Konsolidierung von 640/700/820/900/1180 auf weniger Stufen — reine CSS-Aufräumarbeit ohne fachliche Dringlichkeit; nur anfassen, wenn ohnehin an den betroffenen Stellen aus Runde 4 gearbeitet wird, sonst eigenes Nice-to-have-Ticket.
5. **Impressum/Datenschutz (25):** Footer-Komponente mit Platzhaltertext + Kommentar `<!-- TODO: rechtssichere Texte durch Nina/Kanzlei einsetzen -->`. **Ausdrücklich als Nutzereingabe markieren** — ich kann keine rechtsverbindlichen Pflichtangaben (§ 5 DDG, Art. 13 DSGVO) erfinden; das Formular/den Platz dafür schaffen ist Aufgabe dieses Repos, der Inhalt nicht.
6. **Zugänge-Rollenschutz (26):** laut Erkundung bereits serverseitig korrekt (`_verwalter_wache`, babu_web.py:3180-3186 → `darf_verwalten`, :3176). **Kein Code-Fix, nur Verifikation:** ein Test `server/belegreview/tests/test_zugriff.py` (falls nicht schon vorhanden) explizit gegen alle vier genannten Routen (`/api/nutzer`, `POST /api/nutzer`, `/api/nutzer-aktion`, `/api/registrierungen`) mit einer `mitarbeit`-Rolle → 403 erwarten, damit dieser Befund als abgeschlossen dokumentiert ist, nicht nur behauptet.

---

## Verifikations-Abschnitt (nach jeder Runde)

1. **Server-Suite:** `cd server/belegreview && /tmp/babu-venv/bin/python -m pytest tests/` — muss vollständig grün bleiben (aktuell 1608 Tests), plus die neuen Tests aus der jeweiligen Runde.
2. **Sprach-/Verdrahtungs-Linter gezielt:** `pytest tests/test_sprachregel.py tests/test_portal_verdrahtung.py -v` nach jeder portal.html-Änderung.
3. **iOS-Harness** (nur Runde 1b betroffen): `ios/Tests/run.sh`.
4. **iOS-Simulator-Smoke** (nur Runde 1b): `xcodebuild -project ios/Beleg/Beleg.xcodeproj -scheme Beleg -destination 'platform=iOS Simulator,name=iPhone 16e' -derivedDataPath /tmp/bsim build`.
5. **Portal-Vorschau (manuell, jede Runde mit UI-Änderung):**
   ```
   BABU_ORIGIN=http://localhost:7899 /tmp/babu-venv/bin/python werkzeuge/portal-vorschau/portal_vorschau.py
   ```
   dann im Browser `fetch("/api/anmelden",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({pat:"test-pat"})})` (oder das dort dokumentierte Login-Verfahren) und die betroffene Ansicht bei 1440px und 375px Breite ansehen.
6. **Golden-Diff vor jedem echten H200V-Deploy** (nicht vor dieser lokalen Vorschau, aber verbindlich laut CLAUDE.md, sobald eine Runde live geht): `/api/belege` und `/api/abgleich/<monat>` als `python3 -m json.tool --sort-keys` vor und nach `docker compose build && up -d` byte-diffen, dann die geänderten Routen live durchrufen.
7. **Für Runde 1b speziell:** vor dem Deploy den realen Beleg aus dem Befund (Getränkemarkt, 04.08., 65,73 €) — sofern als Testdatensatz verfügbar, sonst mit einem äquivalenten selbst gebauten Pfand-Beleg — einmal durch den vollen Weg (Foto → Einschätzung → Aufnahme) schicken und die DATEV-Zeile (Steuerschlüssel 9, Betrag) von Hand nachrechnen.

---

### Kritische Dateien für die Umsetzung
- server/belegreview/babu_web.py
- server/belegreview/portal.html
- server/belegreview/monatsabschluss.py
- server/belegreview/gemma_buchung.py
- ios/Beleg/Beleg/Store.swift
- server/belegreview/kontoauszug.py