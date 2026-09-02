ich will das die konten auch komplett ausgelesen werden und auch im context durch embeddings verfuegbar sind und dann auch alle datev themen im Frontend und backen hochgeladen sortiert und in den kontext kommen ich brauche auch einen Pro zugang fuer stuerberate die Im Backend 100te Mandanten verwalten koennen P0 — Zahlen, die sich widersprechen

1. Drei Ausgaben-Summen für September. Auswertung › Ausgaben: „Ausgegeben 79,50 € · 1 Beleg", Kategorie „Sonstiges". Auswertung › Monatsabschluss: „Ausgegeben (ohne Steuer) 979,30 €", Kategorien „Raum 905,00 € (0 Belege)" + „Werbung, Bewirtung und Reisen 74,30 €". Export: „Belege im Monat 1 · Summe 0,00 €". Heute-Seite: „Bleibt dir −979,30 €" ohne Erklärung, direkt unter „Eingenommen 0,00 / Ausgegeben 79,50" auf der Nachbarseite. Ursache ist klar (Bruttosicht Belege vs. Nettosicht inkl. Vertragskosten), aber das Portal erklärt es nirgends. Der Pizzeria-Beleg ist auf einer Seite „Sonstiges", auf der anderen „Bewirtung". Eine Zahl, eine Kategorie, überall dieselbe — oder die Differenz („davon 905 € Miete aus Vertrag, noch ohne Beleg") explizit hinschreiben.

2. Falsche Vorsteuer auf einem „geprüften" Beleg. Getränkemarkt am Gaskessel, 04.08., 65,73 €. Der Bon druckt: Netto 57,06 · Steuer 19 % 8,67 (Pfand ist steuerfrei). babu zeigt: 55,24 ohne Steuer · 10,49 Steuer — hat also 19 % auf den Gesamtbetrag gerechnet und die gedruckten Steuerzeilen ignoriert. 1,82 € zu viel Vorsteuer, DATEV-Zeile mit Steuerschlüssel 9 auf den vollen Betrag. Bei Getränke-Einkäufen mit Pfand passiert das jeden Monat. Wenn der Bon Netto/Steuer ausweist, müssen diese Werte gewinnen.

3. Export summiert auf 0,00 € bei 1 Beleg im Monat. Entweder ein Rechenfehler oder „nur geprüfte + freigegebene Belege" — dann fehlt der Hinweis.

4. „Wird gelesen" seit 5 Tagen. Fünf Belege vom 27.08. und einer vom 31.08. stehen am 02.09. noch auf „Wird gelesen". Kein Fehlerzustand, kein „Nochmal versuchen", kein Hinweis. Nach x Minuten muss der Status kippen: „Konnte nicht gelesen werden — magst du drauf schauen?"

P1 — Desktop, der nichts Desktop-spezifisches kann

5. Layout. Alle Views sind eine Spalte mit max. ~880–1330 px, darunter Handy-Karten. Bei 1440 px ist die rechte Hälfte der Heute-Seite leer. Der Belege-Detail ist der einzige Zwei-Spalten-Screen. Ein Desktop-Cockpit hätte: Belegliste links + Detail rechts, Wochenansicht bei Terminen, Tabelle statt Kacheln bei Belegen (Datum / Laden / Betrag / Kategorie / Status, sortierbar).

6. Fehlende Funktionen am Rechner. Rechnungen: „Gestellt wird in der App — hier siehst du, was offen ist." Die Landingpage verspricht „Rechnung schreiben, während sie noch da ist" — am Rechner geht es nicht. Kassenbuch: „Trag sie in der App im Kassenbuch ein." Am Rechner nicht möglich, obwohl das Abend-Zählen ein klassischer Rechner-Job ist. Termine: nur Tagesansicht, keine Woche. Salon-Check: „Das konnten wir nicht sicher lesen — magst du kurz draufschauen?" — aber es gibt nichts zum Draufschauen und kein Feld zum Nachtragen.

7. Ablage-Suche findet nichts wieder. Kontoauszüge heißen 20260822-180616-bfcd90-Konto_0030217038-Auszug_2026_0007.PDF. babu hat die Datei gelesen (Monat, Bank, Seiten bekannt) und könnte sie „Kontoauszug Juli 2026 · Kreissparkasse" nennen. Rohnamen sind für die Zielgruppe Rauschen.

8. „Löschen" auf jeder Kachel in der Ablage, gleichwertig neben dem Dateinamen. GoBD-relevante Belege sollten nicht mit einem Klick auf Kachelebene löschbar sein — mindestens ins Kontextmenü oder in die Detailansicht.

P2 — Inkonsistenzen und Kleinkram

9. Relative Wochenlabels in vergangenen Monaten. August zeigt „Diese Woche" / „Letzte Woche" — im September. Aldi 27.08. steht unter „Diese Woche", vier andere Belege vom 27.08. unter „Letzte Woche".

10. „Deine letzten Belege" auf Heute ist nicht sortiert: 22.07., 01.09., 22.08.

11. Duplikat-Dialog ohne Antwortmöglichkeit. Die Frage lautet „Sieht aus wie ein Doppelgänger — bitte prüfen". Das Formular darunter heißt „Trag nach, was fehlt" mit Betrag/Datum/Laden und „Speichern und abschließen". Es fehlen die zwei Buttons, die die Frage beantworten: „Ja, doppelt — löschen" / „Nein, zwei Einkäufe".

12. Fristen. Post vom Amt zeigt „Bis 2026-06-01" (ISO-Format, überall sonst DD.MM.) — die Frist ist drei Monate vorbei, ohne rote Markierung. Verträge: „Frist steht im Vertrag" — babu hat den Vertrag gelesen, die Frist sollte drin stehen.

13. Post-Semantik. Überschrift „Was deine Kanzlei für dich bereitlegt", Inhalt sind Briefe vom Finanzamt und GEZ. Entweder „Post" allgemein oder zwei Bereiche.

14. E-Mail ohne @. Menü und Einstellungen zeigen „christoph0711.io". API liefert "un":"christoph0711.io" — das @ wird schon serverseitig verloren.

15. Team-Formular. „Fester Lohn" gewählt, trotzdem stehen Monatslohn und Stundenlohn/Stunden gleichzeitig da. „Speichern" ist unformatierter Text, kein Button.

16. „Mandat gleich kündigen" im Kanzlei-Brief ist vorangekreuzt. Kündigung als Default ist heikel — leer lassen.

17. Salon-Check unter „Belege". Die Tabs Belege / Bank / Salon-Check hängen unter dem Nav-Punkt „Belege". Salon-Check ist eine Auswertung und gehört neben Ausgaben / Monatsabschluss.

18. Zwei Personal-Views. „Einstellen & Personal" und „Dein Team" sind zwei Menüpunkte für dieselben Menschen.

19. „Wie der Monat gelaufen ist": „0 Sek. bis ein Beleg fertig war · gut so" bei einem Beleg. Die Kacheln sind bei wenig Daten Füllmaterial; ab n < 5 ausblenden.

20. Fragen-Seite ist bei leerem Verlauf zu 80 % Weißraum mit Eingabe in der Mitte. Eingabe nach oben oder unten, Beispiel-Chips direkt daneben.

P3 — Technik

21. Alles unauthentifiziert ausgeliefert. 270 KB HTML, 182 KB Inline-JS, alle 27 Views und ~80 API-Routen im DOM vor dem Login — inklusive WhatsApp-Token-Felder, Testwerkzeuge, Einrichtung-Reset. Kein Datenleck, aber Angriffsfläche und Einblick für jeden. Login-Shell und App-Bundle trennen.

22. Kein Caching. Ein Inline-Script, ein Inline-Style, jeder Aufruf lädt 270 KB frisch.

23. Formulare ohne <label>. Fast alle Inputs nur mit Placeholder. autocomplete ist korrekt gesetzt.

24. Fünf Breakpoints (640/700/820/900/1180), zwei Paare eng beieinander — gewachsenes CSS.

25. Impressum & Datenschutz „folgen" — auf einer Seite mit Login, Kontoanlage und Verarbeitung von Steuerdaten (§ 5 DDG, Art. 13 DSGVO).

26. Zugänge-View: Kanzlei-Rolle sieht alle Mandanten (Namen, E-Mails, Startpasswort-Reset). Bitte prüfen, dass die Route serverseitig auf rolle === "kanzlei" gesperrt ist, nicht nur per ausgeblendetem Menüpunkt.

Was gut ist

Bank-Abgleich Juni: „46 mit Beleg · 15 ohne · fehlt 7.228,23 €" — das ist die beste Seite im Portal. Klar, konkret, handlungsleitend. Fragen-Assistent antwortet richtig und mit Begründung (Miete Petra Bechtle 905 €, GoBD). Duplikaterkennung greift (Getränkemarkt 2×, trotz OCR-Tippfehler „Getrinkenarkt"). Beleg-Weg (Foto › Gelesen › Geprüft › DATEV › Kanzlei) und „Das geht an DATEV" mit Konto/Gegenkonto/Steuerschlüssel — Transparenz ohne Fachchinesisch. Ton und Copy sind durchgängig, keine einzige Stelle fällt in Steuerdeutsch.

Reihenfolge, wenn ich entscheiden müsste

Erst 1 + 2 + 3 (Zahlen stimmen überall überein, Bon-Steuer gewinnt), dann 4 (Stuck-State), dann 6 (Kassenbuch + Rechnung am Rechner), dann 5 (Desktop-Layout). Alles andere danach.