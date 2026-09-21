# babu_web.py zerlegen — der Plan

Stand 21.09.2026. Ausgangslage gemessen: **12.419 Zeilen, 173 Routen,
61 Module daneben, 130 Tests.** Die Datei funktioniert — das Ziel ist
nicht „schöner", sondern: Änderungen wieder auffindbar, Deploy-Risiko
klein, Review diffs lesbar.

## Die gute Nachricht zuerst

Die Messung zeigt: **babu_web.py ist KEIN Chaos.** Die thematischen
Blöcke stehen überwiegend zusammenhängend im File (warteliste 4424–4598,
whatsapp 10723–10881, auswertung 7480–7819 …). Nur vier Familien sind
zerstreut: `beleg`, `ablage`, `abschluss`, `termin`. Die Zerlegung kann
also entlang EXISTIERENDER Schnittlinien laufen — kein Redesign, sondern
Ausschneiden entlang der Naht.

## Regeln (unverhandelbar, aus CLAUDE.md abgeleitet)

1. **Ein Schritt = eine Familie.** Ausschneiden, umbenennen `from X import`,
   Suite grün, Deploy, ein Tag warten. Nie zwei Familien in einem Schritt.
2. **Kein Verhalten ändern.** Reine Moves + `import`. Jede Funktion behält
   ihren Namen, jede Route ihren Pfad, jeder Test sein Erwartungsbild.
3. **`babu_web.py` bleibt Einstiegspunkt.** Die App-Instanz, `_db()`,
   `_DB_LOCK`, Wächter (`_api_wache`, `_verwalter_wache`, Mandanten-Kontext)
   bleiben dort oder wandern in `kern.py` — die Module importieren die
   App, nicht umgekehrt (keine Zirkel-Importe).
4. **Suite ist das Gate.** 130 Tests, 2371 passing. Grüner Schritt oder
   Rückbau (`*.bak-vor-<familie>-<datum>`). Kein Schritt ohne grüne Suite.
5. **Schemaänderungen zweimal** (inline + migrations) — betrifft diesen
   Plan nicht, aber bleibt bestehen.

## Zielbild (8 Module + Kern)

```
belegreview/
  babu_web.py        ← App-Instanz, DB, Wächter, Kontext, healthz (~2.500 Z.)
  kern_auth.py       ← Login, Passwort, Geräte, Sitzungen (~700)
  kern_warteliste.py ← Warteliste, Apple-ID, Signup, Audit (~900)
  kern_belege.py     ← aufnahme, beleg, ablage, dokumente, hochladen (~3.500)
  kern_buchung.py    ← einschaetzung, gemma-Anbindung, review, kategorien (~1.500)
  kern_abschluss.py  ← abschluss, monatsabschluss, auswertung, bwa, ustva (~2.000)
  kern_betrieb.py    ← kundinnen, termine, mitarbeiter, leistungen, vertraege,
                       whatsapp, team (~2.000)
  kern_kanzlei.py    ← datev, export, kanzleiwechsel, nutzer-Verwaltung (~800)
  portal.html        ← bleibt (7.705 Z., eigenes Thema, später)
```

`babu_web.py` endet bei ~2.500 Zeilen: App, Schema, Wächter, dann
`from kern_belege import *`-artige Registrierung der Router (FastAPI
`APIRouter` pro Modul, app.include_router in der Kern-Datei).

## Die Schritte (Reihenfolge nach Risiko, kleinste first)

| # | Schritt | Zeilen | Risiko | Beweis danach |
|---|---|---|---|---|
| 1 | **kern_warteliste** (4424–4598 + signup/registrierung) | ~900 | klein | Warteliste-Tests + live: Nina sieht Liste |
| 2 | **kern_kanzlei** (datev 1642, export, kanzleiwechsel) | ~800 | klein | datev-Seite lädt, Prüfbefund unverändert |
| 3 | **kern_abschluss** (auswertung-Block 7480–7819, abschluss, bwa, ustva) | ~2.000 | mittel | Monatsabschluss-Durchlauf golden-diff-gleich |
| 4 | **kern_buchung** (einschaetzung 6230, gemma_buchung-Verdrahtung, review) | ~1.500 | mittel | Ninas Beleg durchläuft mit gleicher Buchung (Live-Beweis) |
| 5 | **kern_betrieb** (termine, kundinnen, mitarbeiter, whatsapp, leistungen) | ~2.000 | mittel | WhatsApp-Webhook antwortet, Kalender lädt |
| 6 | **kern_auth** (login, passwort, geräte, sitzungen) | ~700 | mittel-hoch | Login-Flow live, TestFlight-App meldet sich an |
| 7 | **kern_belege** (aufnahme, beleg, ablage, dokumente) | ~3.500 | HOCH | Zerstreute Familien zuerst innen sortieren, dann move. Aufnahme-Route live mit echtem Foto |
| 8 | portal.html splitten (separater Plan) | — | später | — |

Schritt 7 zuletzt, weil dort die drei zerstreuten Familien liegen
(`beleg` 2170–3015, `ablage` 2837–9122, `abschluss` 7259–8164) — der
einzige Schritt, der vorher Aufräum-Moves braucht (Helfer, die zwischen
den Familien geteilt sind, erst in kern_Hilfen sammeln).

## Was NICHT angefasst wird

- `portal.html` (eigene Welt, Sprachregel-Tests)
- DB-Schema, Box-Format, Gemma-Prompts
- Die Deploy-Rituale (rsync komplett, healthz, arbeit_offen)
- insp-app, posteingang, alles auf der H200V außerhalb von /app

## Aufwand & Einwands-Vorbeugung

- **Aufwand:** 7 Schritte à 1–3 h Arbeit + je 1 Beobachtungstag. Über
  zwei Wochen verteilt, ohne Pilot-Betrieb zu blockieren.
- **„Warum überhaupt?"** Jeder Bugfix in babu_web startet heute mit
  „wo war das noch?" über 12k Zeilen. Nach Schritt 3 kennt jeder
  Dateiname das Thema — LLM-Kontext, Review-Diffs und Deploy-Risiko
  werden kleiner. Das ist der ganze Nutzen, aber er kommt jeden Tag.
- **„Brich es nicht!"** Deshalb: Suite-Gate, ein Schritt pro Deploy,
  Golden-Diff bei jedem. Der Plan ist umkehrbar (bak-Dateien) und
  jeder Schritt steht allein.

## Erster konkreter Zug (wenn du sagst „mach")

Schritt 1 (warteliste, kleinster Risiko, heute schon im Fokus): Block
4424–4598 + signup/registrierung/Audit nach `kern_warteliste.py`
ziehen, `APIRouter` registrieren, Suite, Deploy, live durchrufen
(„Apple-ID eintragen → Status prüfen"). Dann Schritt 2 einen Tag später.
