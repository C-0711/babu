# Golden Case „Salon Schwabo" — der vollständige Testfall

Vollsynthetischer Testkorpus nach dem Vorbild von Ninas echtem Case
(`~/Downloads/Steuer App`, bleibt lokal). **Alle Daten hier sind erfunden**
— Personen, Firmen, IBANs, Steuernummern — und dürfen im Repo liegen.
Foto-Belege: Gemini Nano Banana 2 (`gemini-3-pro-image`); PDFs: gebaut
(`reportlab`/PIL). Jede Besonderheit des Systems kommt genau einmal vor,
und **alle Summen gehen rechnerisch auf** (die arithmetische Gegenprobe
ist der stärkste Nachweis).

## Stammdaten

| | |
|---|---|
| Salon | **Salon Schwabo**, Schwabstr. 112, 70193 Stuttgart |
| Inhaberin | **Jenny Block** |
| Rechtsform | Einzelunternehmen, Regelbesteuerung (kein § 19) |
| Kontenrahmen | SKR04 |
| Steuernummer | 99015/28371 (Finanzamt Stuttgart III) |
| Bank | Kreissparkasse Stuttgart, GiroBusiness **40088123** |
| Monat des Falls | **August 2026** |

## Belege (Fotos, `belege/`)

| Datei | Testet | Erwartung (Golden) |
|---|---|---|
| `01-bon-southside-mehrsatz.jpg` | Thermobon, **19 % + 7 % gemischt**, Barzahlung mit Gegeben/Rückgeld | Brutto **88,68 €** (A: 62,00 + 11,78 · B: 13,93 + 0,97); Gegeben 100,00/Rückgeld 11,32 verwirren die Summe nicht; Kategorie Ware; vom Konto gedeckt (03.08.) |
| `02-bewirtung-bellavista.jpg` | **Bewirtung** mit handschriftlichem Trinkgeld | Brutto **51,80 €** (Netto 43,53 + 19 % 8,27); Bewirtungssignal → Frage „Mit wem warst du essen?"; Zahlbetrag 55,00 = Trinkgeld 3,20, keine offene Differenz-Frage |
| `03-ausland-chicago-usd.jpg` | **Fremdwährung/Ausland** (USD, englisch, ohne USt) | USD 285,00 erkannt; **betrag_eur 265,31** aus der Kontobewegung vom 05.08.; keine USt erfunden (Export) |
| `04-schief-baecker.jpg` | **Schlechtes Foto** (schief, dunkel, klein) | Import-Entzerrung richtet es; liest Vision < 12 Zeichen → „bitte neu fotografieren"-Fall; sonst 6,40 € (7 %) |
| `05-gutschrift-southside.jpg` | **Gutschrift/Retoure** (negativer Betrag) | −27,80 € als Gutschrift, nicht als Ausgabe; passt zur Konto-Gutschrift vom 17.08. |
| `06a/06b-kosmetikzentrale-*.jpg` | **Mehrseitige Rechnung** (#69): Übertrag S. 1, Endsumme S. 2 | Mehrseiten-Modus: EIN Beleg, **312,60 €** (Netto 262,69 + 19 % 49,91); Übertrag 214,50 wird NICHT doppelt gezählt; Konto-Deckung 21.08. |
| `07-parkhaus.jpg` | Kleinbetrag | 4,50 € (19 % = 0,72); Kategorie Kfz/Reise |
| `08-kleinunternehmer-fusspflege.jpg` | **§ 19-Lieferant** (kein USt-Ausweis) | 85,00 €, **0 % — keine USt erfinden**; bar, daher keine Konto-Deckung nötig |
| `09-dublette-bytegleich.jpg` | **Dublettenwache** (byte-identisch) | Kopie von 01 — zweiter Upload wird abgewiesen („war schon da") |
| `10-ibanfalle-laserline.jpg` | **Einsortier-Falle**: dicker IBAN/BIC-Block | Bleibt BELEG (238,00 € = 200,00 + 19 %), landet NICHT im Kontoauszugsfach; Konto-Deckung 18.08. |

Zusätzlicher Doppelgänger-Test ohne eigene Datei: `01` ein zweites Mal
**neu fotografieren** (gleiches Datum + Betrag, andere Bytes) → Doppelgänger-Hinweis.

## Verträge (`vertraege/`)

| Datei | Testet | Erwartung |
|---|---|---|
| `mietvertrag-schwabstr-112.pdf` | Vertrag **mit Textlayer**, 3 Seiten | Fach Verträge; Dauerkosten **1.180,00 €/Monat** (980 + 200 NK) landen im Vertrags-Kontext der Einschätzung; erklärt die UNGEDECKTE Miet-Abbuchung |
| `wartungsvertrag-laserline-scan.pdf` | Vertrag als **Scan OHNE Textlayer** | Gemma liest das Blatt (multimodale Lese-Strecke); 200,00 €/Termin, Laufzeit 24 Monate ab 01.02.2026 |

## Kontoauszug (`kontoauszuege/`)

`Konto_0040088123-Auszug_2026_0008.pdf` — Text-PDF im KSK-Zeilenformat
(**parsebar verifiziert**: Monat 2026-08, Konto 40088123, 10 Umsätze).

| Datum | Position | Betrag | Golden-Erwartung im Abgleich |
|---|---|---|---|
| 03.08. | Southside Lastschrift | −88,68 | ✓ gedeckt durch Beleg 01 |
| 05.08. | Chicago Hair (USD 285,00) | −265,31 | ✓ gedeckt durch Beleg 03 (Fremdwährungs-Brücke!) |
| 07.08. | Miete Immobilien Weiss | −1.180,00 | **ohne Beleg** → Checkliste/Hinweis (der Mietvertrag erklärt sie) |
| 12.08. | Telekom | −49,99 | **ohne Beleg** → Checkliste/Hinweis |
| 15.08. | SumUp Auszahlung | +1.842,30 | Einnahme, kein Beleg nötig |
| 17.08. | Southside Gutschrift | +27,80 | passt zu Beleg 05 |
| 18.08. | Laserline | −238,00 | ✓ gedeckt durch Beleg 10 |
| 21.08. | Kosmetik Zentrale | −312,60 | ✓ gedeckt durch Bündel 06 |
| 28.08. | SumUp Auszahlung | +1.573,90 | Einnahme |
| 29.08. | KSK Entgeltabschluss | −12,90 | Bankentgelt — der Auszug ist der Beleg |

## Behörde (`behoerde/`)

`finanzamt-ust-vorauszahlung-scan.pdf` — Bescheid als **Scan ohne
Textlayer**: USt-Vorauszahlung Juni 2026, **612,40 €**, fällig 10.09.2026.
Erwartung: Fach Behörde; Frist erscheint; Gemma liest den Scan.

## Testablauf (empfohlene Reihenfolge)

1. Frisches Testkonto (`jenny@0711.io` o. ä.) oder lokaler Vorschau-Server
   (`werkzeuge/portal-vorschau/`) — **nie** in Ninas echte Box.
2. Kontoauszug übers Portal ablegen → Bank-Ansicht zeigt 10 Positionen.
3. Belege 01, 03, 07, 08, 10 einzeln über die App (oder Foto-Import —
   testet die Entzerrung) → Fragen beantworten, grüner Haken.
4. 06a+06b über den **Mehrseiten-Modus** (⧉ im Sucher) → ein Beleg, 312,60 €.
5. 02 aufnehmen → Bewirtungsfrage beantworten (Anlass + 2 Teilnehmer).
6. 04 importieren → Entzerrungs-/Unlesbar-Verhalten prüfen.
7. 05 aufnehmen → Gutschrift.
8. 09 hochladen → Dublette abgewiesen; danach 01 neu fotografieren →
   Doppelgänger-Hinweis.
9. Verträge + Bescheid übers Portal ablegen → Fächer, Scan-Lesung, Fristen.
10. Bank-Checkliste: genau **Miete + Telekom** stehen als „ohne Beleg";
    Auswertung: Ausgaben ≈ 1.011,68 € aus Belegen; Monatslauf am 3. des
    Folgemonats.

## Grenzen

- Die Foto-Belege sind KI-generiert: Layout/Beträge stimmen, einzelne
  Zeichen können vom Prompt abweichen — die MANIFEST-Beträge sind die
  Referenz. Wo Vision anderes liest als hier steht, erst das Bild ansehen.
- `04` ist absichtlich grenzwertig — beide Ausgänge (gelesen oder „neu
  fotografieren") sind akzeptabel, nur ein stiller Fehlschlag nicht.
