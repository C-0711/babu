# Nachtprotokoll 03./04.10.2026

Alle Zeiten deutsche Zeit (MESZ). Quellen: Git-Commits (Mac läuft auf BST, +1 h umgerechnet),
Sicherungen und Golden-Dateien auf der H200V (`~/golden/`, `~/sicherung/`, Rückweg-Images), GitLab.
„live“ = Deploy mit Sicherung, Rückweg-Image, Golden-Vergleich vorher/nachher (jedes Mal GLEICH)
und Push auf gitlab main.

## Samstag, 03.10.

| Zeit  | Was | Commit | Stand |
|-------|-----|--------|-------|
| 20:52 | **Phase 0:** Kanzlei sieht Bankdaten nur noch an (Hochladen, Löschen, Klären, Übernehmen gesperrt); Portal als Mandant wieder nutzbar | 2bddc7d | live 20:52 |

## Sonntag, 04.10.

| Zeit  | Was | Commit | Stand |
|-------|-----|--------|-------|
| 00:08 | **K0+K1 Kreditoren:** eine Gegenkonto-Regel für Stapel und Einzelansicht; Kreditorenliste je Betrieb, Reiter „Kreditoren“ auf der DATEV-Seite, Übernahme aus DATEV-Datei und alten Stapeln | 4ff9e6f | live 00:09 |
| 01:40 | **K2:** Kreditor am Beleg wählbar, im Stapel statt 70099, im Prüfbefund; Übergabe hält die Gegenkonten fest | 17c19a6 | live 01:40, Stapel-Fingerabdrücke vor 01:34 / nach 01:41 gleich |
| 03:33 | **Punkt 2 (Ninas #80–#82, #86):** Pfand eigenes Konto 5820, Versand immer Porto, Abos/Lizenzen → IT/Software | ee3d109 | live 03:33 |
| 03:49 | **B1:** Freigabe der Kontoumsätze durch den Betrieb (Migration 0015, Fassung im Rechtstext, Anfrage per Mail, Karte auf „Heute“) | ca6ce2c | live 04:05 |
| 04:37 | **B2+B3:** Import von CAMT- und CSV-Dateien jeder Bank, ein Umsatzmodell, Bankabgleich und „Belege ohne Zahlung“ für die Kanzlei, Bank-Spalte im Cockpit | a548665 | live 04:37 |
| 04:45 | **GitLab:** #81, #82, #86 auf „zur-abnahme“, #67 geschlossen | – | erledigt |
| 05:09 | **Sicherheitsfix:** Mitarbeiterinnen ändern das Team nicht mehr; Upload aus der App prüft „darf Belege“ | ce27107 | live 05:09 |
| 05:15 | Spezifikation **Independence Day Stufe A** (mit oder ohne Steuerbüro arbeiten) | d39dc24 | Doku |
| 05:19 | Nachtrag: leere Arbeitsweise folgt der Betreuung durch ein Steuerbüro | 75ab8af | Doku |
| 05:22 | Umsetzungsplan Stufe A | 407a1a0 | Doku |
| 05:29 | A1: `arbeitsweise.modus` deutet „Wer reicht beim Finanzamt ein?“ | 4c658be | lokal |
| 05:30 | A2: Arbeitsweise in `/api/ich` und Einstellungen; Rhythmus, Dauerfrist, Bundesland, Personal setzbar | 9eddf92 | lokal |
| 05:31 | A3: Fristen folgen der Arbeitsweise, Klartext aus der Einrichtung | 408e4cb | lokal |
| 05:33 | A4: Inhaberin darf DATEV-Seite, Korrektur, Export und Abschluss (Mitarbeiterin nie) | 315c321 | lokal |
| 05:35 | A5: ehrliche Texte: „Dein Steuerbüro übermittelt“ bzw. „Mein ELSTER“ statt „Steuer-Backend“ | 36568e6 | lokal |
| 05:37 | A6: DATEV-Seite: Knopf „Monat abschließen“ / „An mein Steuerbüro geben“ | 11208c1 | lokal |
| 05:39 | A7: Portal zeigt die Werkzeuge im Modus „selbst“; Einrichtung fragt Arbeitsweise und Fristen | 6037b11 | lokal |
| 05:58 | Sammel-Testlauf A: 357 grün, 1 Test auf den neuen Hinweistext umgestellt | 63abcc3 | erledigt |
| 06:00 | Gesamtprüfung A durch frischen Prüfer: 1 kritisch, 5 wichtig, 6 klein | – | erledigt |
| 06:06 | Abnahme-Anleitung für Nina als PDF (Fassung 1) | – | verschickt |
| 06:08 | **Kritisch behoben:** Festschreiben per Link umging die Abo-Sperre und ließ sich von fremden Seiten auslösen | 7469a05 | live 06:24 |
| 06:09 | Kanzlei/Admin lesen immer die Steuerbüro-Texte; Kleinunternehmerin ohne Voranmeldungs-Fristen | b5bc5ef, a99bb0f | live 06:24 |
| 06:12 | Korrektur: Konto des Stapels, nur Geändertes, früheres Konto bleibt; Steuer-Feld entfernt | 21c5ef3 | live 06:24 |
| 06:18 | Texte „bei der Kanzlei“ / „bei deinem Steuerbüro“ / „abgeschlossen“ statt „deine Kanzlei“ | df0b7b8 | live 06:24 |
| 06:19 | Menü Buchhaltung: „Prüfen und abschließen“ im Modus selbst | 902cf03 | live 06:24 |
| 06:21 | Kein Kündigungsrat bei „Mein Steuerbüro“ | 5e34094 | live 06:24 |
| 06:23 | **Deploy Stufe A:** Sicherung, Rückweg-Image, Golden vorher; Testlauf 488 grün; Neustart 06:24, healthz ok, Golden gleich; Live-Prüfung; Push gitlab main | 5e34094 | live |
| 06:30 | Abnahme-Anleitung für Nina, Fassung 2 | – | fertig |

**Stufe A ist live (06:24) und auf gitlab main (5e34094).** Rückweg: Image `babu-web:rueckweg-vor-ida-20261004-062341`.

## Offen bei dir (Punkt 1)

- IBAN (DE + 20 Ziffern) und USt-ID (DE + 9 Ziffern) in `docker/.env` korrigieren
- SEPA-Lastschrift in Stripe einschalten
- Stripe-Konto von Einzelperson auf Firma umstellen und Steuernummer hinterlegen
- Rechtstexte prüfen lassen, Impressum

## Danach

D (babu Expenses), dann B (Steuern berechnen), dann C (ELSTER). Externer Schritt jetzt
anstoßen: ELSTER-Herstellerregistrierung.
