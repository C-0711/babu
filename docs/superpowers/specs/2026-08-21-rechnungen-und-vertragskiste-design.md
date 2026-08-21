# Rechnungen stellen — und die Vertragskiste

Stand 21.08.2026. Zwei Ergänzungen an derselben Stelle: babu kennt bisher nur
Geld, das rausgeht (Belege) und Geld, das über die Ladenkasse reinkommt
(Kassenbuch). Was fehlt, ist die dritte Sorte — Geld, das der Salon jemandem
in Rechnung stellt — und ein Ort für die Verträge, die jeden Monat sicher
abgehen.

## A — Rechnungen

### Warum

Ein Salon schreibt Rechnungen: Stuhlmiete an die selbständige Kosmetikerin,
Hochzeit für einen Firmenkunden, Gutscheine für eine Firma. Heute passiert das
in Word, die Nummern verrutschen, und die Umsatzsteuer-Voranmeldung weiß
nichts davon. `review_watcher.py` kennt „Stuhlmiete" längst als Stichwort —
nur stellen konnte babu keine.

### Wo

In der iPhone-App, fünfter Tab **Rechnungen**. Oben die offenen, darunter die
bezahlten. „Neue Rechnung" führt in die Vorlage.

### Die Vorlage

Gespeicherte **Empfänger** (Name, Anschrift, optional USt-IdNr) und
gespeicherte **Positionen** (Text, Betrag, Steuersatz). Eine neue Rechnung ist
damit: Empfängerin antippen, Position übernehmen, Datum prüfen, fertig. Für
den Einzelfall lassen sich Positionen frei eintippen.

Der Kopf kommt aus `/api/einstellungen` — Betriebsname, Anschrift,
Steuernummer, Kleinunternehmer-Status. Nichts davon wird abgetippt, und der
§19-Hinweis erscheint automatisch, wenn er gilt.

### Pflichtangaben (§ 14 UStG)

Name und Anschrift beider Seiten, Steuernummer oder USt-IdNr, Rechnungsdatum,
fortlaufende Nummer, Menge und Art der Leistung, Zeitpunkt der Leistung,
Entgelt je Steuersatz, Steuersatz und Steuerbetrag. Bei Kleinunternehmerinnen
statt der Steuer der Satz „Kein Ausweis von Umsatzsteuer nach § 19 UStG".
Unter 250 € genügt die Kleinbetragsrechnung — babu prüft das, verlangt aber
nichts Zusätzliches.

### Nummer und Festschreiben

Die **Nummer vergibt der Server**, nicht das Telefon: eine lückenlose Folge auf
einem Gerät zu führen scheitert an der ersten Neuinstallation.

1. App schickt die Rechnungsdaten → Server vergibt die nächste Nummer und legt
   `rechnungen/<JJJJ-MM>/<nummer>.json` in der Belegbox ab.
2. App rendert das PDF **mit dieser Nummer** und lädt es nach
   (`rechnungen/<JJJJ-MM>/<nummer>.pdf`).

Reißt die Verbindung zwischen 1 und 2 ab, existiert die Rechnung mit ihrer
Nummer, das PDF lässt sich nachreichen — keine Lücke in der Folge. Ohne
Verbindung bleibt alles Entwurf, und die App sagt das, statt zu behaupten,
es sei gespeichert.

Format der Nummer: `JJJJ-NNNN`, je Jahr bei 1 beginnend, aus dem Stand der
Belegbox ermittelt (kein Zähler in SQLite, der beim Umzug verloren geht).

### Wann eine Rechnung zählt

Neue Einstellung `versteuerung` mit den Werten `ist` (Vorgabe) und `soll`.

- **Ist-Versteuerung** (§ 20 UStG, der Normalfall im kleinen Salon, und was
  die EÜR ohnehin verlangt): die Rechnung zählt in dem Monat, in dem sie
  **bezahlt** wird. Eine gestellte, unbezahlte Rechnung bleibt aus BWA und
  Voranmeldung draußen und steht als „offen" in der Liste.
- **Soll-Versteuerung**: sie zählt im Monat des Rechnungsdatums.

Jede Rechnung trägt dafür ein `bezahlt_am`. Das ist zugleich die Antwort auf
„wer schuldet mir noch was".

### Wo alles liegt

`rechnungen/<JJJJ-MM>/<nummer>.json` (die Zahlen, aus denen die Auswertung
rechnet) und `.pdf` (was die Kundin bekommt und was aufbewahrt wird). In der
Ablage als eigene Art **Rechnungen**. Festgeschriebene Rechnungen sind
aufbewahrungspflichtig und damit **nicht löschbar** — der Entwurf davor schon.
Eine falsche Rechnung wird nicht gelöscht, sondern storniert (eigene Rechnung
mit negativem Betrag und Verweis).

### Erlöse

`monatsabschluss.erloese_monat()` bekommt die Rechnungen dazu und weist sie
getrennt aus (`aus_kasse` / `aus_rechnungen`), damit sichtbar bleibt, woher
der Umsatz kam. UStVA und BWA rechnen unverändert mit den Summen — nur
gefüttert werden sie jetzt aus zwei Quellen.

## B — Die Vertragskiste

### Warum

Verträge liest babu serverseitig schon (`.vertrag.json`: Monatsbetrag,
Laufzeit, Kündigungsfrist) und rechnet sie in die BWA. Aber es gibt keinen
Ort, an dem die Inhaberin ihre Dauerkosten *sieht* — und keine Warnung, bevor
eine Kündigungsfrist abläuft. Genau das ist die Kiste: was jeden Monat sicher
abgeht, und wann man etwas tun muss.

### Was sie zeigt

In der App unter Rechnungen erreichbar (gleiche Ecke: was regelmäßig Geld
bewegt), als eigene Ansicht **Verträge**:

- **Was monatlich abgeht** — Summe über alle laufenden Verträge, darunter
  jeder einzeln mit Art, Partner und Betrag.
- **Was ansteht** — Verträge, deren Kündigungsfrist in den nächsten 90 Tagen
  abläuft, mit dem Datum, bis zu dem gekündigt sein muss. Das ist der
  eigentliche Wert: eine Frist, die man verpasst, kostet ein weiteres Jahr.
- **Vertrag fotografieren** — führt auf den bestehenden Weg
  (`POST /api/dokumente?art=vertrag`), babu liest ihn im Hintergrund.

### Die Frist rechnen

Neue Funktion `vertraege.kuendigen_bis(vertrag, heute)` in einem eigenen
Modul. Aus `laufzeit_bis` und der Kündigungsfrist im Klartext („3 Monate zum
Quartalsende") wird das späteste Datum, an dem die Kündigung raus sein muss.
Was sich nicht sicher lesen lässt, wird **nicht geraten**: dann steht dort
„Frist steht im Vertrag" statt eines erfundenen Datums.

## Routen

| Route | Zweck |
|---|---|
| `GET /api/rechnungen` | Liste mit Stand (offen/bezahlt), Summen |
| `POST /api/rechnungen` | Rechnung festschreiben, Server vergibt die Nummer |
| `POST /api/rechnung/{nummer}/pdf` | PDF nachreichen |
| `POST /api/rechnung/{nummer}/bezahlt` | „bezahlt am" setzen |
| `GET /api/empfaenger` · `POST /api/empfaenger` | gespeicherte Empfänger |
| `GET /api/vertraege` | Dauerkosten, Summe, anstehende Fristen |

Alle hinter `_box_wache`. Rechnungen stellen darf die Inhaberin und die
Kanzlei, nicht die Rolle `mitarbeit`.

## Tests

- `tests/test_rechnungen.py` — Nummernfolge (lückenlos, je Jahr neu, auch bei
  gleichzeitigen Anfragen), Pflichtangaben, Kleinunternehmer-Hinweis,
  Storno, PDF-Nachreichen, `bezahlt_am`, nicht löschbar.
- `tests/test_erloese_rechnungen.py` — Ist vs. Soll: dieselbe Rechnung landet
  je nach Einstellung in einem anderen Monat; Kasse und Rechnungen werden
  getrennt ausgewiesen, aber gemeinsam summiert.
- `tests/test_vertraege.py` — Fristberechnung inkl. „zum Quartalsende", und
  dass Unlesbares nicht geraten wird.
- `ios/Tests/` — Harness für den Rechnungs-Aufbau (Summen je Steuersatz,
  Kleinbetragsgrenze, §19-Fall) nach dem Muster des EXTF-Harness.

## Nicht dabei

- Keine Serie und keine Automatik — jede Rechnung wird von Hand ausgelöst.
- Kein Mahnwesen, kein Abgleich mit dem Kontoauszug.
- **Keine E-Rechnung (XRechnung/ZUGFeRD).** Für B2B läuft die Übergangsfrist
  für kleine Betriebe Ende 2027 aus; Stuhlmiete an eine Selbständige ist B2B.
  Das PDF trägt bis dahin. Die JSON-Ablage ist so gebaut, dass das XML später
  daraus entsteht, ohne die Daten neu zu erheben.
