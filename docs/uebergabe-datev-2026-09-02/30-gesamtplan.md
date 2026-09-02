# Gesamtplan — Auftrag vom 02.09.2026, 18:15

Zusammenführung der drei Einzelpläne (`20`, `21`, `22`). Stand des Codes: `d163ac6`
auf main, deployt, Suite 1608 grün. Die Einzelpläne enthalten Datei, Funktion,
Zeile, Test und Risiko je Schritt — dieses Dokument ordnet nur die Reihenfolge
und benennt, was vor dem Bauen entschieden werden muss.

## Vier Arbeitsstränge

| Strang | Plan | Umfang | Abhängigkeiten |
|---|---|---|---|
| A · 26 Portal-Befunde | `22` | 7 Runden, P0 zuerst | keine |
| B · Wissensschicht (Konten + DATEV-Uploads) | `20` | 8 Phasen | keine, additiv |
| C · Pro-Zugang Kanzlei, Mandanten, Postgres | `21` | 5 Phasen, Wochen | größter Umbau, berührt Auth und Datenschicht |
| D · Sicherheits-Sofortmaßnahme | `21` Phase 0 | < 1 Tag | keine |

## Empfohlene Reihenfolge

1. **D sofort**: Rollen-Fallback bei leerer Konfiguration von „kanzlei" auf
   „salon" (fail-closed). Ein Commit, ein Test, Golden-Diff.
2. **A Runde 1** (P0-1, P0-2, P0-3): Zahlen stimmen überall überein, gedruckte
   Bon-Steuer gewinnt, Export-Summe repariert. Zwei Teilcommits, weil P0-2 einen
   iOS-Build braucht.
3. **B Phasen 2–6**: Upload-Route, Ablage-Fach „Wissen", Suche in Chat und
   Buchung. Rein additiv, geringes Risiko, sofort nützlich.
4. **A Runde 2** (P0-4 „Wird gelesen"): serverseitige Lesung für Portal-Uploads
   plus Timeout-Zustand. Neuer Codepfad mit Modellaufruf, hohes Risiko.
5. **B Phase 1 + 7**: SKR04-Atome auf dem Host bauen, Bulk-Import der lokalen
   DATEV-Quellen. Danach Container-Neustart.
6. **A Runden 3–4** (Kassenbuch und Rechnung am Rechner, Desktop-Layout).
7. **C Phasen 1–5**: Postgres, Mandantenmodell, Kanzlei arbeitet als Mandant,
   Provisionierung, Frontend. Erst wenn A und B ruhig laufen, weil C dieselben
   Dateien tief umbaut.
8. **A Runden 5–7** (P1-Rest, P2, P3) nach Gelegenheit; P3-21 (Login-Shell vom
   App-Bundle trennen) als eigener Auftrag.

## Entscheidungen, die beim Auftraggeber liegen

Aus Plan 21 (Pro-Zugang):

- **D1** Postgres für alle Tabellen (empfohlen) oder nur für Kanzlei/Mandanten?
- **D2** Netz: Postgres-Port nur auf localhost, babu-web bleibt im Host-Netz (empfohlen).
- **D3** Tests gegen echtes Wegwerf-Postgres, mit Fallback auf SQLite-Dialekt (empfohlen).
- **D4** Box-Anlage bleibt Handarbeit, weil das Gateway insp-app tabu ist.
  Reicht das für hunderte Mandanten, oder braucht es ein eigenes Onboarding-Werkzeug?
- **D5** Rollen-Fallback sofort auf „salon" (empfohlen, siehe Strang D).

Aus Plan 20 (Wissensschicht):

- Thema als Chip auf der Karte (empfohlen) oder als dritte Baum-Ebene in der Ablage?
- Quellen-Chips „Nachgeschlagen in …" im Chat sichtbar machen? Eigene, größere UI-Arbeit.
- Buchungsfilter: alle Wissens-Themen zulassen (empfohlen) oder nur Kontenrahmen und Steuerschlüssel?

Aus Plan 22 (Befunde):

- **P0-4** Schwelle, ab der ein Beleg als „konnte nicht gelesen werden" gilt: Vorschlag 20 Minuten.
- **3b Rechnung am Rechner**: vorher klären, ob der Server das Rechnungs-PDF selbst
  rendert oder nur das PDF der App ablegt. Entscheidet über den Umfang.
- **3d Salon-Check**: welche grauen Karten brauchen ein Korrekturfeld? Vorher alle
  Aufrufstellen sichten.
- **P2-18** Zwei Personal-Ansichten: nur Navigation zusammenlegen (empfohlen) oder
  auch die Datenmodelle verschmelzen?
- **P3-25** Impressum und Datenschutz: Texte müssen vom Auftraggeber kommen.

## Was in keinem Plan steht

- Der Import eines babu-Stapels in einer echten DATEV-Instanz. Braucht eine Kanzlei.
  Bleibt Schritt 1 der DATEV-Brücke und ist durch nichts hier ersetzbar.
- Anlagenverzeichnis, offene Posten, Saldenvorträge, Kontenbeschriftungen als
  DATEV-Export. Formate liegen nicht vor.
