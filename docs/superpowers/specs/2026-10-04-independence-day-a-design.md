# Independence Day, Stufe A — mit oder ohne Steuerbüro arbeiten können

Stand 04.10.2026 · freigegeben im Gespräch mit dem Auftraggeber · Teil 1 von 4
(Reihenfolge A → D → B → C: A Version und Werkzeuge, D babu Expenses,
B Steuern berechnen, C ELSTER-Versand).

## Ziel

babu gibt es in zwei Arten zu arbeiten:

- **Mit Steuerbüro** (so läuft babu heute): Der Betrieb erfasst, das Steuerbüro
  bucht, prüft und bekommt den DATEV-Stapel.
- **Independence Day**: Die Unternehmerin macht die Buchhaltung selbst und
  reicht selbst beim Finanzamt ein (Versand per ELSTER folgt in Stufe C).

Entscheidend (Auftraggeber): **Beides muss gehen.** Menschen arbeiten mit oder
ohne Steuerberater, und auch mit Steuerbüro darf die Inhaberin selbst prüfen,
korrigieren und abschließen. Der Modus regelt deshalb **nicht den Zugriff**,
sondern **den letzten Schritt, die Texte und die Fristen**.

**Fertig ist A**, wenn eine Inhaberin ohne Kanzlei ihren Monat prüfen,
korrigieren, Kreditoren pflegen und abschließen kann, nirgends mehr „deine
Kanzlei“ oder „das Steuer-Backend übermittelt“ liest, und Betriebe mit
Steuerbüro genau so weiterarbeiten wie bisher.

## Entscheidungen

| Frage | Entscheidung |
|---|---|
| Wie wird Independence Day verkauft? | Gleiche Pakete (Solo/Salon/Salon Plus); der Modus ist eine Einstellung. |
| Betrieb mit Steuerbüro stellt um? | Beides gleichzeitig möglich; das Steuerbüro bleibt, beide können arbeiten. |
| Wer bekommt die Werkzeuge? | Jede Inhaberin (Rolle `salon`), unabhängig vom Modus; Mitarbeiterinnen nie. |

## 1. Der Modus

- Einstellung `steuerberater_modus` (gibt es schon, `EINSTELLUNG_SCHLUESSEL`).
  Neue Frage: **„Wer reicht beim Finanzamt ein?“** mit den Antworten
  **„Mein Steuerbüro“** und **„Ich selbst (Independence Day)“**.
- Alte Werte bleiben lesbar: „Mein Steuerbüro bleibt“/„vorbereitend“ → Steuerbüro,
  „Alles über babu“ → selbst. Leer → abgeleitet aus `steuerberater_status`
  („Ja“ → Steuerbüro, „Nein“ → selbst); ist auch das leer, entscheidet die
  Betreuung: wird der Betrieb von einem echten Steuerbüro betreut (Kanzlei ≠
  „babu direkt“), gilt Steuerbüro, sonst selbst. So bleibt z. B. ein von einer
  Kanzlei angelegter Betrieb ohne Einstellungen beim Steuerbüro.
- Ein neues reines Modul **`arbeitsweise.py`** mit `modus(einstellungen) ->
  "steuerbuero" | "selbst"` ist die einzige Stelle, die diese Werte deutet.
  `/api/ich` und `/api/einstellungen` liefern zusätzlich `arbeitsweise`.
- Wechsel jederzeit im Portal (Einstellungen) und in der Einrichtung.

## 2. Werkzeuge für jede Inhaberin

- Neue Wache **`_buchhaltung_box_wache`** in `babu_web.py`: lässt Kanzlei und
  Admin durch (wie `_verwalter_box_wache`, mit `X-Mandant`) **und** die Inhaberin
  in ihrer eigenen Box (Rolle `salon`, `box_mitglied`, eigener Mandant). Rolle
  `mitarbeit` → 403. Abo-Nur-Lesen gilt wie in `_box_wache` für Schreibwege.
- Umgestellt auf die neue Wache:
  - DATEV-Seite: `GET /datev` und **alle** Routen in `datev_seite.py`
    (`_wache`) — Übersicht, Vorschau mit Prüfbefund, Stapel, Konten,
    Kreditoren (alle), Lesen/Vergleich, Übergeben.
  - `POST /api/korrektur/{stamm}`.
  - `GET /api/export/{monat}.csv` (auch `festschreiben=1`).
- Unverändert bei der Verwaltung: `/api/audit`, `/api/nutzer*`, alles unter
  `/api/kanzlei/*`, Posteingang, Betreiber-Routen.
- **Monat abschließen**: dieselbe Übergabe wie heute (`_stapel_uebergeben`,
  Siegel, Läufe, Nachträge, festgehaltene Gegenkonten). Ob die Inhaberin oder das
  Steuerbüro drückt, steht im Lauf (`von`). Kein zweites Verfahren.

## 3. Oberfläche

- **Modus selbst**: Die Inhaberin sieht
  - im Beleg den Abschnitt „Das geht an DATEV“ mit Kreditor-Feld (heute nur
    `istKanzlei()`), die Korrektur von Konto, Steuer und Buchungstext,
  - im Menü „Buchhaltung“ den Weg zur DATEV-Seite,
  - auf der DATEV-Seite den Knopf „Monat abschließen“ statt „Stapel übergeben“.
- **Modus Steuerbüro**: Oberfläche der Inhaberin wie heute (schlicht, ohne
  Kontonummern); die DATEV-Seite ist erreichbar, aber nicht im Menü. Der Knopf
  heißt dort „An mein Steuerbüro geben“.
- Portal-Funktion `buchhaltungSelbst()` (Modus selbst und Rolle `salon`) neben
  `istKanzlei()`; Sprachregel und Nummern-in-onclick gelten.

## 4. Ehrliche Texte

Alle Stellen, die heute ein „Steuer-Backend“ oder „deine Kanzlei“ voraussetzen,
richten sich nach dem Modus:

- „Übermittlung durch das Steuer-Backend“: `monatsabschluss.py` (Kopf, 368f),
  `vordrucke.py` (PDF-Fuß 484–486), `babu_web.py` (Monatsabschluss/Freigabe,
  ~11855–11947), `portal.html` (1636, 5321–5324), `ios/.../AbschlussView.swift`.
  Selbst: „Die Voranmeldung als PDF — den Versand ans Finanzamt bereiten wir vor;
  bis dahin trägst du die Zahlen in Mein ELSTER ein.“ Steuerbüro: „Dein
  Steuerbüro übermittelt.“
- 403-Texte für Inhaberinnen („Diesen Stapel lädt deine Kanzlei herunter“,
  „übergeben wird er von deiner Kanzlei“, `portal.html` 3698/3711) entfallen,
  weil die Inhaberin jetzt darf.
- Rechtstexte (`recht.py` Impressum/AGB §1, `avv.py`), Werbung und App-Store-
  Notiz bleiben in A **unverändert**; sie werden mit Stufe C angepasst, wenn
  babu wirklich übermittelt (siehe „Außerhalb von A“).

## 5. Fehlende Einstellungen

In `EINSTELLUNG_SCHLUESSEL` aufnehmen und im Portal setzbar machen (Einstellungen,
Abschnitt Steuern): `ustva_rhythmus` (monatlich/vierteljährlich),
`dauerfristverlaengerung` (Ja/Nein), `bundesland`, `hat_personal` (Ja/Nein).
`fristen.termin_profil` liest sie schon; bisher waren sie nicht setzbar (immer
monatlich). Fristen für Jahreserklärungen richten sich nach `arbeitsweise`
statt nach `steuerberater_status` (selbst: 31.07. Folgejahr; Steuerbüro: Ende
Februar übernächstes Jahr).

## 6. Tests

- Neu `tests/test_arbeitsweise.py`: Deutung aller alten und neuen Werte.
- Neu `tests/test_buchhaltung_wache.py`: Inhaberin erreicht DATEV-Seite,
  Vorschau, Kreditoren, Korrektur, Export und Übergabe in ihrer Box;
  Mitarbeiterin bekommt 403; Kanzlei mit `X-Mandant` wie bisher; eine fremde
  Inhaberin kommt nicht in eine fremde Box; Abo „nur lesen“ sperrt die
  Schreibwege der Inhaberin.
- Bestehende Rollentests (`test_datev_seite.py` „Salon sieht nichts“) werden
  bewusst umgeschrieben: die Inhaberin sieht jetzt ihre eigene Seite.
- Fristen: `ustva_rhythmus` vierteljährlich und Arbeitsweise selbst ergeben die
  erwarteten Termine.
- Golden-Vergleich (`/api/belege`, `/api/abgleich`) und `tests/golden/routen.txt`
  bleiben unverändert (keine neue Route).

## Außerhalb von A

- Stufe B (Steuern berechnen: Voranmeldung je Quartal, Jahres-USt, EÜR, GewSt,
  ESt-Anlagen), Stufe C (ELSTER/ERiC, Rechtstexte, App-Store-Notiz) und D
  (babu Expenses) bekommen je eine eigene Spezifikation.
- Externer Schritt, jetzt anstoßen: ELSTER-Herstellerregistrierung
  (Hersteller-ID, ERiC, Test-Finanzamt).
