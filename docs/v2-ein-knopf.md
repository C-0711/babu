# V2-Konzept: Ein Knopf

> Stand 03.09.2026 · Klick-Prototyp in der iOS-App, erreichbar über
> Einstellungen → Testphase → „Konzept „Ein Knopf" ausprobieren". Die
> gewohnte Ansicht (rund 40 Bildschirme) bleibt über das kleine „Konzept"
> oben rechts erreichbar — derselbe Bestand, derselbe Speicher.

## 1. Die Regel

- **Ein Knopf, ein Satz, eine Zahl.** Jede Seite sagt genau eines: was gerade
  zu tun ist (Satz), was es wert ist (Zahl), und wie man es tut (Knopf).
- **Kein Menü, keine Reiter, keine Liste.** Was nicht auf die Seite passt,
  gehört nicht auf die Seite — es liegt eine Ebene tiefer in der gewohnten
  Ansicht.
- **Die App entscheidet, was dran ist.** Nina entscheidet nur „jetzt" oder
  „später". Sie wirft alles rein — Bons, Rechnungen, Post vom Amt,
  Kontoauszüge — und babu sortiert, bucht, erinnert, rechnet.

## 2. Regie — welche Seite ist dran?

Reine Logik (`ios/Beleg/Beleg/EinKnopf/Regie.swift`, Harness
`ios/Tests/einknopf`). Oberste passende Zeile gewinnt. Was in dieser
Sitzung weggewischt wurde, kommt erst beim nächsten Start wieder — das ist
das Ermahnen.

| # | Seite | Wann | Zahl | Label | Satz | Knopf | Farbe |
|---|---|---|---|---|---|---|---|
| 1 | Frist naht | Umsatzsteuer-Termin in 0–7 Tagen und es ist noch etwas offen | „6 Tage" · „1 Tag" · „Heute" | — | „Bis zum 10. muss die Umsatzsteuer raus. 3 Belege fehlen noch." | Loslegen | Amber, ab 3 Tagen Rot |
| 2 | Frage | Ein Beleg wartet auf eine Antwort, die nur Nina weiß | Belegbetrag | Lieferant | die Frage, in ihrer Sprache | Antworten | Bronze |
| 3 | Beleg fehlt | Vom Konto ging Geld ab, ohne Beleg | Abbuchung | „vom Konto abgegangen" | „Am 12.08. gingen 84,90 € an Slavic Hair Company vom Konto. Dazu fehlt der Beleg." | Beleg reinwerfen | Bronze |
| 4 | Monat fertig | Der Monat ist gerechnet und kann raus | Zahllast ohne Vorzeichen | „bekommst du zurück" · „zahlst du" | „Dein August ist gerechnet." | Ans Finanzamt schicken | Grün, mit dem einen Haken |
| 5a | Heim, tagsüber | Nichts wartet | Zähler | „zurückgeholt im September" | „Wirf alles rein — Bons, Rechnungen, Post vom Amt. babu sortiert." | Reinwerfen | Bronze |
| 5b | Heim, ab 18 Uhr | Nichts wartet | Was vom Monat bleibt | „Bleibt dir" | „Heute 3 Belege reingeworfen, 48,00 € zurückgeholt. Im September bleiben dir bisher 2.318,00 €." | Reinwerfen | Bronze |

Kleinunternehmerin: keine Vorsteuer, deshalb heißt der Zähler „erfasst",
die Monatsseite zeigt „bleibt dir" und der Knopf „Monat abschließen".

## 3. Gestenregel

- **Knopf = tun. Wischen nach unten = später.** Nichts anderes.
- Auf „Beleg fehlt" fragt der Wisch nach: „Später" oder „Dazu gibt es
  keinen Beleg" (dann der Grund — kommt noch, Vertrag, privat, keiner).
- Auf der Heimseite gibt es nichts aufzuschieben; sie federt zurück.
- Kein Löschen, kein Ablehnen auf der Seite. Wer etwas wirklich nicht will,
  geht in die gewohnte Ansicht.
- Bei einer Frage öffnet „Antworten" ein Halbblatt mit zwei bis vier
  Antworten (verbunden: die Fragen der Buchhaltung, wie heute). Das
  Halbblatt gehört zur Seite, es ist keine neue.

## 4. Momente

- **Katsching.** Ist ein Beleg gebucht und seine Vorsteuer kommt zurück,
  klingt eine Münze (0,35 s, zwei Töne eine Quarte hoch, auf dem Gerät
  gerechnet — keine Datei im Repo), das iPhone tippt einmal, „+13,56 €"
  steht groß in Grün, darunter tickt der Monatszähler von alt auf neu.
  1,8 s, dann entscheidet die Regie neu.
- **Fanfare.** Einmal im Monat, nach „Ans Finanzamt schicken": vier Münzen
  aufwärts, der eine grüne Haken, „Unterwegs".
- **Warum das zum Design-Brief passt** („Kein Fintech-Look, kein
  Verspieltes — ein schönes Werkzeug"): ein Ton, eine Bewegung, an echtes
  Geld gebunden — die Zahl ist Kennziffer 66, kein Punktestand. Abschaltbar
  im Konzept-Dialog, gehorcht dem Stummschalter, verschwindet mit „Bewegung
  reduzieren" in ein Überblenden. Kein Konfetti (die Entscheidung in
  `AufraeumenView.swift` bleibt), keine Abzeichen, keine Serien, kein Streak.
- Keine Momente für Fotografieren, Antworten, Wischen. Belohnt wird nur
  Geld, das da ist.

## 5. Machbarkeit — Versprechen gegen Wirklichkeit

| Versprechen | Heute vorhanden | Lücke | Stufe |
|---|---|---|---|
| Foto → gebucht | `POST /api/buchung/einschaetzung` (Gemma, strenges JSON, Dokumentklasse beleg/vertrag/behoerde/kontoauszug), `POST /api/aufnahme` legt ab | keine | 1 |
| Alles reinwerfen | Fotos in der App; PDFs und Bilder über „Teilen → In babu öffnen"; Kontoauszug als Text-PDF über `POST /api/kontoauszug` | kein Mail-Eingang; gescannte Kontoauszüge nicht; im Prototyp landen PDFs in der gewohnten Ansicht | 2: Postfach je Salon |
| „Du bekommst X zurück" | `monatsabschluss.ustva_entwurf` (Kennziffern 81/86/48/66/83), Satz fertig formuliert | keine | 1 |
| „Ans Finanzamt schicken" | `POST /api/monatsabschluss/{monat}/freigeben` schreibt den Monat fest, `POST /api/ustva/{monat}` legt die Voranmeldung als PDF ab | **Es wird nichts übermittelt** — keine ELSTER-/ERiC-Anbindung. Der Prototyp behält den Knopftext; der Moment sagt ehrlich „liegt in deiner Ablage" | 2: ERiC-Bibliothek auf der H200V, Zertifikat, Übermittlungsprotokoll |
| Erinnern und ermahnen | Regeln in `melden.py` (7 und 1 Tag vor Fristen, 30 und 7 Tage vor Vertragsenden, höchstens drei), `GET /api/meldungen`; Fristen aus `fristen.py` über `GET /api/fristen/{jahr}` | **Kein Push** — nur lokale Mitteilungen um 9 Uhr, geplant beim Öffnen der App. **Ein Fehler:** `melden.py` liest `faellig`/`name`, `fristen.py` liefert `datum`/`titel`, darum entsteht nie eine Fristmeldung; die Fixture in `tests/test_melden.py` baut die falschen Felder nach und verdeckt es | sofort: Feldnamen angleichen · 2: Push mit Zeitplaner auf der H200V |
| Zahlen heute Abend | `GET /api/monatslauf` (Stand läuft/wartet/bereit/freigegeben, Erlöse, Zahllast, Ergebnis), `GET /api/monatsabschluss/{monat}` (Erlöse, Ergebnis, Vorsteuer) | Monatsstand bis heute, keine Tagesrechnung — der Satz sagt „im September", nicht „heute" | 1 |
| „Zurückgeholt" | kein Begriff im Backend | V2 definiert: **zurückgeholt = Vorsteuer (Kennziffer 66) der gebuchten Belege.** Exakt, prüfbar, kein Schätzwert. Eine Einkommensteuer-Ersparnis wird nicht gezeigt — sie hinge von Steuersatz und Jahresergebnis ab | 1 (Definition) |
| Katsching | keine Spielmechanik; Haptik an fünf Stellen, ein ✨ bei „Alles aufgeräumt" | Ton auf dem Gerät gerechnet (`Tonsynthese.swift`), kein Asset | 1 |

## 6. Was der Prototyp nicht tut

- Keine Kanzlei-Seite, kein Kassenbuch-Eintrag, keine Termine, keine
  Rechnungen, kein Team, kein Marketing.
- Kein echter Versand ans Finanzamt, kein Push.
- Ohne Belegbox-Zugang (und im Simulator) läuft ein **Rundgang** mit
  Beispieldaten durch alle Seiten: Frist → Slavic Hair Company → delilà
  Hair Extensions → Stadtwerke Stuttgart → Rotenberger Weingärtle → August
  fertig → Heim. Rundgang-Buchungen sind als Demo markiert und gehen nie in
  einen Stapel.

## 7. Werbung, wörtlich eingelöst

- „Ich sortier nichts mehr. Foto — fertig." → der Heim-Knopf. Erfüllt.
- „Ich seh meine Zahlen heute Abend." → Heim ab 18 Uhr, Stand bis heute.
  Erfüllt mit der Einschränkung aus Abschnitt 5.
- „Meine Fristen stehen in meinem Kalender." → Frist-Seite plus lokale
  Mitteilung. Erfüllt, sobald der Feldnamen-Fehler behoben ist; ohne Push
  gilt es nur, wenn die App geöffnet wird.

## 8. Nächste Schritte

1. Feldnamen `melden.py` ↔ `fristen.py` angleichen, Fixture aus der echten
   Fristenrechnung speisen (klein, sofort).
2. Knopftext „Ans Finanzamt schicken" nur behalten, wenn Stufe 2 (ERiC)
   beschlossen ist — sonst „Festschreiben".
3. Push: Zertifikat, Geräteschlüssel-Ablage, Zeitplaner um 9 Uhr auf der
   H200V.
4. Mail-Eingang je Salon, damit „alles reinwerfen" auch für Post gilt, die
   nie ein Foto war.
5. Mit Nina einen Salontag lang nur die eine Seite benutzen — und zählen,
   wie oft sie in die gewohnte Ansicht musste.
