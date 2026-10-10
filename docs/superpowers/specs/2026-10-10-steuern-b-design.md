# Stufe B — Steuern berechnen (Entwurf)

> Stand 10.10.2026. Folgt auf Stufe A „Independence Day" (04.10.2026: mit oder ohne
> Steuerbüro arbeiten) und D „babu Expenses" (04.10.2026). Stufe C (ELSTER/ERiC) kommt
> danach und hängt an der Herstellerregistrierung (Bahn 0.1). Diese Spezifikation sagt,
> **was** B rechnet, **woraus**, und **was es nicht tut**. Der Umsetzungsplan folgt
> getrennt, wie bei A.

## 1. Worum es geht

Seit Stufe A kann eine Inhaberin ohne Steuerbüro arbeiten (`arbeitsweise.modus ==
"selbst"`). babu schreibt ihr heute den Monat fest und legt die Voranmeldung als Blatt
ab (`monatsabschluss.ustva_entwurf`, `POST /api/ustva/{monat}`). Was fehlt, ist alles
hinter dem Monat: das Quartal für die, die vierteljährlich melden, das Jahr für die
Umsatzsteuer, die Einnahmen-Überschuss-Rechnung als Grundlage der Einkommensteuer,
die Gewerbesteuer und die Anlagen der Einkommensteuererklärung. Ohne B hört
„Independence Day" nach der Voranmeldung auf und schickt die Inhaberin im Januar doch
wieder zu einem Büro.

B rechnet — B übermittelt nichts. Das ist C.

## 2. Die Regel

- **Eine Quelle je Zahl.** Jede Zahl in B kommt aus einer Funktion, die es schon gibt,
  oder aus einer neuen in `steuern.py`; nie aus einer zweiten Rechnung in der Oberfläche.
  Erlöse nur über `_erloese_fuer()` (CLAUDE.md, Umsatz und Kasse), Vorsteuer über
  `monatsabschluss.vorsteuer_monat`, Abschreibung über `anlagen.py`, Personalkosten
  über `team_personalkosten`.
- **Festgeschriebene Monate sind die Wahrheit.** B rechnet nur über Monate, die
  `POST /api/monatsabschluss/{monat}/freigeben` festgeschrieben hat. Ein offener Monat
  macht das Quartal „vorläufig" — die Zahl steht da, trägt aber den Vermerk und keinen
  grünen Haken.
- **Kein Steuerrat.** B zeigt Kennziffern und Beträge und nennt das Formular, in das sie
  gehören. B sagt nicht „wähle die Kleinunternehmerregelung ab". Fachwissen gehört in
  den Wissenscontainer (`werkzeuge/kompendium/`), nicht in den Code.
- **UI-Sprachregel bleibt:** keine Systemnamen, kein „ELSTER-Format", kein Hash. „Dein
  Quartal", „Dein Jahr", „Was du dem Finanzamt sagst".

## 3. Was B rechnet

| # | Stück | Woraus | Formular / Kennziffer | Vorhanden |
|---|---|---|---|---|
| B1 | **Voranmeldung je Quartal** | drei festgeschriebene Monate, summiert wie `ustva_entwurf` | UStVA Kz 81/86/48/66/83 | monatlich ja, Quartal nein (`fristen.termin_profil` kennt `ustva_rhythmus` schon) |
| B2 | **Jahres-Umsatzsteuer** | zwölf Monate; Differenz zu den Voranmeldungen = Nachzahlung/Erstattung | USt-Jahreserklärung Zeile Kz 177 ff. | nein; Vorjahr liest `abschluss_lesen.py` nur aus hochgeladenen Bescheiden |
| B3 | **EÜR** | Erlöse (Kasse gegen Konto), Belege nach `kostengruppe_von`, AfA aus `anlagen.py`, Personal, Auslagen (D1) als Betriebsausgabe der Erstattung | Anlage EÜR Zeilen 11–16 (Einnahmen), 23–66 (Ausgaben), 69 (Gewinn) | `monatsabschluss.bwa` liefert Ausgaben/Ergebnis je Monat, keine Zeilenzuordnung |
| B4 | **Gewerbesteuer** | Gewinn aus B3, Freibetrag 24.500 € (Einzelunternehmen/Personengesellschaft), Hebesatz der Gemeinde (Einstellung), Messzahl 3,5 % | GewSt-Erklärung, Anrechnung § 35 EStG als Hinweis | nein; Gemeinde/Hebesatz fehlt in `einstellungen` |
| B5 | **ESt-Anlagen** | Gewinn → Anlage G (Gewerbe) oder S (Freiberuf), Anlage EÜR aus B3; Vorsorge/Sonderausgaben NICHT | nur die betrieblichen Anlagen | nein |
| B6 | **Vorauszahlungen** | Bescheid-Werte aus `abschluss_lesen.py` (Vorjahr) gegen den laufenden Gewinn: „Dieses Jahr wird mehr/weniger" | Hinweis, kein Formular | Vorjahr ja (`_vorjahr_kennzahlen`), Vergleich nein |

Kleinunternehmerin (`profil["kleinunternehmer"]`): B1/B2 entfallen (Kz 66 gibt es nicht,
Umsatzgrenze 25.000 €/100.000 € wird als Zähler gezeigt, Überschreiten als Meldung in
`melden.py`), B3–B5 bleiben.

## 4. Woraus — was heute fehlt

Vor B1 ist nichts zu bauen. Davor und für B3 bis B5 fehlen Angaben in `einstellungen`,
die die Einrichtung (Stufe A, A7) abfragen muss, in Alltagssprache:

- Rechtsform (Einzelunternehmen · GbR · UG/GmbH — bei UG/GmbH endet B bei B2 mit dem Hinweis
  „Körperschaft, bitte Steuerbüro"; babu rechnet keine KSt)
- Gewerbe oder freier Beruf (Friseur/Barber/Werkstatt = Gewerbe; die Portale wissen es)
- Gemeinde (für den Hebesatz; Tabelle im Kompendium, einmal jährlich gepflegt)
- Ist-/Soll-Versteuerung (heute stillschweigend Ist — das ist für Salons der Regelfall
  und bleibt Vorgabe, wird aber benannt)

Belege ohne Kostengruppe oder mit `status in (nachfrage, erfasst)` machen jede Zahl
„vorläufig" — dieselbe Regel wie `abschluss_meldung`.

## 5. Oberfläche

- **Portal, Buchhaltung → „Prüfen und abschließen"** (A6/A7) bekommt unter dem Monat
  zwei Karten: „Dein Quartal" (B1, nur bei vierteljährlichem Rhythmus) und „Dein Jahr"
  (B2–B5). Jede Karte: Zahl, ein Satz, Knopf „Blatt ablegen" → PDF in
  `abschluss/<jahr>/` der Belegbox wie heute die Voranmeldung.
- **App, Ein Knopf** (`docs/v2-ein-knopf.md`): Seite 4 „Monat fertig" bleibt. Neu, nur im
  Januar: Seite „Jahr fertig" — Zahl = Gewinn, Satz „Dein 2026 ist gerechnet.", Knopf
  „Jahr abschließen". Kein neuer Reiter.
- **Kanzlei-Modus** (`arbeitsweise == steuerbuero`): B rechnet dasselbe, zeigt es aber
  als „Vorschau für dein Steuerbüro" und legt nichts ab — das Büro übermittelt.

## 6. Was B nicht tut

- Nichts übermitteln (C). Der Knopf heißt „Blatt ablegen" / „Jahr abschließen", nie
  „ans Finanzamt schicken" — dieselbe Regel wie beim Monat seit 10.10.2026.
- Keine private Einkommensteuer: keine Vorsorge, keine Kinder, kein Ehegattensplitting.
  babu rechnet den Betrieb, nicht den Menschen.
- Keine Körperschaftsteuer, keine Bilanz. UG/GmbH bekommen B1/B2 und den Hinweis.
- Keine Lohnsteuer-Jahresmeldung — das ist Lohn (2.6 im Umsetzungsplan).

## 7. Nachweis

- `tests/test_steuern.py`: je Stück eine Fixture mit bekanntem Ergebnis — ein Quartal
  aus drei Golden-Monaten (Weingärtle-Vertrag in `test_api.py`), ein Jahr aus zwölf,
  Kleinunternehmerin ohne Kz 66, UG mit Abbruch nach B2, Gewinn unter und über 24.500 €.
- Golden-Vergleich: `/api/belege` und `/api/abgleich` bleiben byte-gleich (B liest nur).
- Ein echtes Jahr: Ninas 2025 (Salonkee-Auszahlungen, Bescheid liegt als Upload vor)
  gegen den Bescheid aus `abschluss_lesen.py` — Abweichung je Zeile erklärt oder als
  Befund festgehalten. Das ist die Abnahme, nicht die Suite.

## 8. Reihenfolge und Aufwand

1. Angaben in der Einrichtung (A7 erweitern) — 1 Tag.
2. B1 Quartal + B2 Jahr in `steuern.py`, Karten im Portal — 2 Tage.
3. B3 EÜR mit Zeilenzuordnung, PDF — 3 Tage; die Zuordnung Kostengruppe → EÜR-Zeile
   kommt als Tabelle ins Kompendium, nicht in den Code.
4. B4 Gewerbesteuer, B6 Vorauszahlungen — 1 Tag.
5. B5 Anlagen G/S — 1 Tag.
6. Abnahme mit Ninas 2025 — Auftraggeber.

Blockiert durch nichts Externes. C (ELSTER) wartet auf die Herstellerregistrierung;
B ist der Teil von „Independence Day", der ohne sie geht.
