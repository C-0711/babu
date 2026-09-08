# Umsetzung: zwei Apps, zwei Backends, ein Marktplatz

Arbeitsplan zum Produktplan vom 08.09.2026 (`~/.claude/plans/crispy-tumbling-ladybug.md`).
Der Produktplan sagt **was und warum**, dieser sagt **in welcher Reihenfolge, womit
nachgewiesen, und wer es tut**.

Stand beim Schreiben: main `1f69075`, Suite 2129 grün, ein Betrieb (Nina) und eine
Testkanzlei (Afflek) im Betrieb, GKM Neff Bonn übernimmt Ninas Mandat.

---

## Wie dieser Plan gelesen wird

**Drei Bahnen, die nebeneinander laufen.** Bahn 0 ist Papier und Post, Bahn 1 macht das
heutige Produkt marktfähig, Bahn 2 baut das Fundament für das zweite. Bahn 0 muss zuerst
angestoßen werden, weil sie am längsten wartet — nicht weil sie am meisten Arbeit ist.

| | Bahn | Wer |
|---|---|---|
| **0** | Anträge, Rechtstexte, Abnahmen | du und Dritte |
| **1** | babu Start live bekommen | ich |
| **2** | Schnitt und Pro | ich |

**Zwei Sorten Aufgaben, die nie vermischt werden dürfen:**

- **Was ich bauen kann** — Code, Tests, Deploy. Dauer schätzbar, Ergebnis beweisbar.
- **Was nur du oder ein Dritter kann** — ein Antrag bei der Steuerverwaltung, ein Text von
  einer Anwältin, ein Import in einer echten DATEV-Instanz, ein Preis. Dauer nicht in
  meiner Hand, und keine Zeile Code ersetzt sie.

Der häufigste Weg, einen Sechs-Monats-Plan zu verlieren, ist, die zweite Sorte für später
zu halten. Deshalb steht sie hier zuerst.

---

## Bahn 0 — Diese Woche, außerhalb des Codes

Fünf Dinge. Keines dauert lange, alle haben Vorlauf.

### 0.1 · ELSTER-Entwicklerregistrierung beantragen
**Wer:** du · **Blockiert:** C2 (UStVA selbst senden), C3 (ELStAM-Abruf)

ERiC ist die Bibliothek der Steuerverwaltung, kostenlos für Softwarehersteller nach
Registrierung. Unsere eigene Recherche (`docs/personal-onboarding.md:56`) hält fest: *„Ein
Anspruch auf einen Account besteht nicht."* Wenn die Registrierung sich zieht oder
abgelehnt wird, fällt C2 und mit ihm der ELStAM-Teil von C3 — dann bleibt der Marktplatz
der einzige Weg zum Finanzamt.

**Nächster Schritt:** Antrag über elster.de/eportal (Entwicklerbereich), Firmierung
0711 Intelligence, Verwendungszweck Umsatzsteuer-Voranmeldung. Antwortzeit unbekannt.

### 0.2 · Rechtstexte anfordern
**Wer:** du, über eine Anwältin · **Blockiert:** babu Start live

Impressum (§ 5 DDG), Datenschutzerklärung (Art. 13 DSGVO), AGB. Im Portal stehen heute
Platzhalter „Text folgt" — auf einer Seite, die Steuerdaten verarbeitet. Ich kann
Pflichtangaben nicht erfinden.

Für den Marktplatz kommt später ein zweites Vertragswerk dazu (siehe 0.5).

### 0.3 · DATEV-Import bei GKM Neff
**Wer:** du und die Kanzlei · **Blockiert:** die Aussage „babu liefert DATEV"

Export und Rundlauf sind geprüft: 274 Zeilen über zehn Monate, Formatversion 12, 124
Spalten, cp1252 und UTF-8, Rücklesen 274/274 identisch. Was nie stattgefunden hat, ist ein
Import in einer **echten** DATEV-Instanz. Solange das aussteht, ist die Schnittstelle
unbewiesen.

**Nächster Schritt:** GKM Neff einrichten (siehe 1.1), einen Monat exportieren, importieren
lassen, Protokoll festhalten — besonders Meldungen mit #REW-Nummer. Die übersetze ich
danach in den Prüfbefund.

### 0.4 · TSE-Anbieter auswählen
**Wer:** du · **Blockiert:** C4 (Kasse), erst Monat 5

Cloud-TSE gibt es fertig (fiskaly, Deutsche Fiskal). Die Entscheidung „einkaufen oder
selbst" verändert C4 erheblich. Sie muss nicht diese Woche fallen, aber der Vertrag
braucht Vorlauf.

### 0.5 · Vertragswerk Marktplatz
**Wer:** du, über eine Anwältin · **Blockiert:** C1 scharf schalten (nicht bauen)

Wer haftet wofür zwischen Betrieb, Berater und Plattform. Der Marktplatz lässt sich ohne
das bauen und testen, aber kein echter Berater darf sich vorher registrieren.

---

## Bahn 1 — babu Start live

Ziel: 5 bis 20 Betriebe auf Einladung. Kein App-Store-Review, kein In-App-Kauf, kein
Selbstbedienungs-Onboarding.

### Erledigt (08.09.2026)

- **A1 Mandantentrennung** — der befürchtete Befund war keiner (die Ordner sind längst je
  Betrieb getrennt). Gefunden und behoben wurde eine echte Lücke: zwei Routen rechneten
  Personalkosten mit dem angemeldeten Konto statt dem aktiven Betrieb. Wächter-Test
  `test_betriebsfunktionen_kennen_den_mandanten.py`.
- **A2 Belege ohne Lesung** — `/api/aufnahme` schrieb ohne mitgeschicktes Ergebnis nie ein
  Review; der Beleg hieß nach 20 Minuten „unlesbar". Jetzt liest der Server nach. Dazu der
  Folgefund: eine Rückfrage von Gemma führte ebenfalls zu keinem Review — auch behoben.

### 1.1 · Onboarding-Werkzeug (2 Tage)
**Blockiert:** jeden weiteren Betrieb, auch GKM Neff

Heute ist die Aufnahme eines Betriebs verteiltes Wissen: Konto anlegen, Belegbox von Hand
erzeugen, Mandantenzeile schreiben, Kontenrahmen setzen, Kanzlei verknüpfen. Fünf Schritte,
von denen vier still schiefgehen können.

**Zu bauen:** `werkzeuge/betrieb_anlegen.py` — ein Lauf, der alles anlegt und danach prüft:
Konto da, Box erreichbar, Mandantenzeile vollständig, Kontenrahmen gesetzt, erste
Anmeldung möglich. Kein Eingriff in `insp-app` (tabu); die Box entsteht über denselben
Weg wie heute von Hand, nur skriptgesteuert und mit Prüfung danach.

**Nachweis:** einen Testbetrieb anlegen, prüfen, wieder entfernen. Danach GKM Neff damit
einrichten — das ist zugleich der erste echte Lauf.

### 1.2 · Posteingang (4 Tage)
**Blockiert:** das Versprechen „digitale Erfassung des ganzen Schriftverkehrs"

`postfach.py` sendet, ein Eingang existiert nicht. Ohne ihn ist die Hälfte des
Kernversprechens unerfüllt: Post kommt heute nur ins System, wenn Nina sie abfotografiert.

**Zu bauen:** `posteingang.py` — eine E-Mail-Adresse je Betrieb, eingehende Anhänge landen
im selben Leseweg wie ein Foto (`dokumente/<monat>/`, gleiche Sidecars). Absenderprüfung,
Größengrenze, Dubletten über den Hash.

**Erste Entscheidung, die ich brauche:** eigener Mailempfang oder ein Dienst (Postmark,
Mailgun) mit Webhook. Der Dienst ist in Tagen fertig, der eigene Empfang braucht DNS,
SPF/DKIM und einen laufenden Prozess mehr.

**Nachweis:** eine E-Mail mit PDF-Anhang an die Testadresse; das Dokument steht danach im
Fach „Post vom Amt" mit Erklärung.

### 1.3 · Zwei App-Ziele vorbereiten (3 Tage)
**Blockiert:** babu Pro als eigene App

Heute ein Xcode-Target (`io.0711.beleg`). Vor dem zweiten muss
`ios/Beleg/Beleg/AblageService.swift` (1615 Zeilen, ~55 Routen in einem Enum) in Sparten
zerfallen — Belege, Betrieb, Geld, Pro. Sonst wächst die Datei mit jedem Pro-Modul weiter
und trägt beide Produkte gleichzeitig.

**Nachweis:** `ios/Tests/run.sh` grün, Simulator-Build beider Ziele, App unverändert
bedienbar.

### 1.4 · Zwei offene Befunde vom 08.09. (1–2 Tage)
**Betrifft den Lesepfad — nur auf ausdrücklichen Auftrag**

- **Gescannte PDFs werden nie gelesen.** Ein abfotografiertes PDF ohne Textlayer läuft in
  `unlesbar_format`; den Bildweg, den JPGs gehen, gibt es für PDFs nicht. Das trifft jedes
  eingescannte Dokument — unter anderem Ninas Minijob-Beitragskontoauszug.
- **Buchung über 0,00 €.** Ein DHL-Beleg wurde mit Betrag null auf Wareneingang gebucht.
  Eine Buchung über null ist keine Buchung; das gehört zur Rückfrage.

### 1.5 · Support statt Meldeschleife (1 Tag)
Der Rückmeldeknopf auf jedem Bildschirm legt heute ein GitLab-Issue an — gebaut für einen
Kunden. Bei zwanzig Betrieben braucht es einen Weg, der nicht in unserem Issue-Tracker
endet. Kleinste Lösung: dieselbe Meldung geht an eine Support-Adresse, die Issue-Anlage
bleibt intern.

---

## Bahn 2 — Der Schnitt und babu Pro

### 2.1 · Kern aufteilen (6–8 Tage)
**Blockiert:** alles Weitere. `babu_web.py` hat 11.649 Zeilen und 168 Routen.

Vorgehen: eine Gruppe nach der anderen in einen eigenen Router, dem Muster von
`datev_seite.py` und `kanzlei_routen.py` folgend. Reihenfolge nach Risiko, das kleinste
zuerst:

1. `marke_routen.py` (14 Routen, keine Buchungslogik) — der Probelauf
2. `dokumente_routen.py` (14)
3. `betrieb_routen.py` (Kundinnen, Termine, Team — 39)
4. `geld_routen.py` (Kasse, Rechnungen — 11)
5. `belege_routen.py` (18) — zuletzt, weil der Buchungsweg daran hängt

**Nachweis je Schritt:** Suite grün UND Golden-Diff byte-gleich (`/api/belege`,
`/api/abgleich/<monat>`). Eine Verschiebung, die den Golden ändert, ist keine Verschiebung
— dann ist etwas anderes passiert als Umziehen.

**Zwei Engpässe dabei mitnehmen:** `_DB_LOCK` auf SQLite beschränken (unter Postgres
unnötig, serialisiert heute ~86 Stellen), und `_LLM_SEMAPHORE` von 1 auf 4 heben. Der
Semaphore-Teil liegt fertig samt Tests in den zurückgenommenen Commits `d8b3445` und
`8ac993d` — **ohne** den JSON-Modus, der am 04.09. den geteilten Gemma-Dienst zweimal
umgeworfen hat.

### 2.2 · Fiskal-Dienst aufsetzen (4 Tage)
Neuer Container, eigene Sicherheitszone, eigener Update-Zyklus. Zunächst leer bis auf das
Gerüst und den API-Vertrag zum Kern: er liest über HTTP, schreibt nie in die Belegbox.

**Nachweis:** der Dienst läuft, holt sich einen Monatsabschluss aus dem Kern, und ein
Absturz in ihm lässt die Belegannahme unberührt.

### 2.3 · Marktplatz (10–12 Tage)
**Kein externer Blocker fürs Bauen** — nur fürs Scharfschalten (0.5).

In vier Scheiben, jede für sich nutzbar:

1. **Selbstregistrierung für Berater** mit Freischaltung durch dich (3 Tage)
2. **Mandat anbieten und übernehmen** — Tabellen `mandat_angebot`, `mandat_uebernahme`;
   Betrieb stellt ein, Berater übernimmt, beide sehen einander (4 Tage)
3. **Vollmacht und Übergabe in babu** — heute nur als Brief (`kanzleiwechsel.py`); fehlt
   die Übernahme mit Zeitpunkt, Zustimmung und Audit-Eintrag (2 Tage)
4. **Team und Vertretung in der Kanzlei** — heute trage ich Sachbearbeiter von Hand in die
   Datenbank ein (2 Tage)

Die Abrechnung der Vermittlung kommt danach und braucht erst das Vertragswerk.

### 2.4 · E-Rechnung (5 Tage)
Empfang ist seit 2025 Pflicht, Versand ab 2027/2028. Keine Zulassung nötig.
- **Empfangen:** eingehende ZUGFeRD/XRechnung direkt in den Buchungsweg, ohne Lesung — die
  Daten stehen schon strukturiert drin.
- **Senden:** dasselbe Rechnungs-PDF mit eingebettetem XML.

Sinnvoll direkt nach dem Posteingang (1.2), weil beide am selben Eingang hängen.

### 2.5 · ELSTER (10–15 Tage, erst nach 0.1)
`amtsweg.py` im Fiskal-Dienst: ERiC einbinden, Zertifikatsverwaltung je Betrieb (das
Zertifikat gehört dem Unternehmer), Steuernummer nach Bundesfinanzamtsnummer, Transferticket
und Protokoll ablegen, Testfälle der Steuerverwaltung.

**Nachweis:** die amtlichen Testfälle, danach **eine** echte UStVA für einen realen Monat
mit Transferticket. Vorher nichts scharf schalten.

### 2.6 · Lohn (10 Tage, nach 2.5)
Der schwerste Teil steht: `lohnsteuer_pap.py` ist der amtliche Programmablaufplan 2026,
gegen den BMF-Rechner geprüft. Es fehlen Routen (heute reine Bibliothek), Lohnkonto nach
§ 4 LStDV, die Abrechnung als Dokument, ELStAM-Abruf (läuft über ERiC).

**Gesperrt bleibt** der SV-Meldeversand: § 95b SGB IV verlangt ein systemgeprüftes Programm
mit GKV-Zertifikat der ITSG. Zwischenweg: babu bereitet feldweise auf, die Inhaberin
überträgt im SV-Meldeportal.

### 2.7 · Kasse mit TSE (15–20 Tage, nach 0.4)
Heute ein sauberes Kassenbuch mit Tagessummen, bewusst unterhalb von § 146a AO. Eine echte
Kasse braucht Einzelaufzeichnung, TSE, DSFinV-K-Export, Belegausgabe, Kassenmeldung und
Verfahrensdokumentation. Das ist ein Neubau neben dem Kassenbuch, kein Umbau daran — das
Kassenbuch muss weiterlaufen für alle, die keine Kasse brauchen.

---

## Was blockiert was

```
0.1 ELSTER-Antrag ──────────────► 2.5 ELSTER ──► 2.6 Lohn (ELStAM)
0.2 Rechtstexte ────────────────► Start live
0.3 DATEV-Import ◄── 1.1 Onboarding-Werkzeug (GKM Neff einrichten)
0.4 TSE-Anbieter ───────────────► 2.7 Kasse
0.5 Vertragswerk ───────────────► 2.3 Marktplatz scharf schalten

1.1 ──► weitere Betriebe
1.2 Posteingang ──► 2.4 E-Rechnung (gemeinsamer Eingang)
1.3 App-Ziele ────► babu Pro als eigene App
2.1 Kern aufteilen ─► 2.2 Fiskal ─► 2.5, 2.6, 2.7
```

**Der kritische Pfad läuft über 0.1.** Fällt die ELSTER-Registrierung aus, entfallen 2.5
und der ELStAM-Teil von 2.6 — babu Pro wäre dann Marktplatz plus Lohnvorbereitung plus
Kasse, ohne eigenen Weg zum Finanzamt. Das ist ein Produkt, aber ein anderes.

---

## Reihenfolge

| Woche | Bahn 0 (du) | Bahn 1 und 2 (ich) |
|---|---|---|
| 1 | 0.1 ELSTER · 0.2 Rechtstexte | 1.1 Onboarding-Werkzeug |
| 2 | 0.3 GKM Neff einrichten | 1.2 Posteingang |
| 3 | DATEV-Import fahren | 1.2 fertig · 1.5 Support |
| 4 | 0.5 Vertragswerk anstoßen | 1.3 App-Ziele |
| 5–6 | | 2.1 Kern aufteilen |
| **→ babu Start live** | sobald 0.2 da ist | |
| 7 | | 2.2 Fiskal-Gerüst |
| 8–10 | | 2.3 Marktplatz |
| 11–12 | | 2.4 E-Rechnung |
| 13–16 | 0.4 TSE entscheiden | 2.5 ELSTER (wenn 0.1 durch) |
| 17–20 | | 2.6 Lohn |
| 21–26 | | 2.7 Kasse mit TSE |
| **→ babu Pro live** | | |

Rund 70 bis 90 Arbeitstage Code. Das passt in sechs Monate, solange Bahn 0 nicht wartet.

---

## Arbeitsweise

**Je Änderung:** eigener Worktree, Commit auf dem Branch, `cd server/belegreview &&
/tmp/babu-venv/bin/python -m pytest tests/ -q -p no:cacheprovider` (Timeout 600 s), dann
ff-Merge auf main und Deploy per vollständigem `rsync server/`.

**Golden-Diff** bleibt Pflicht bei allem, was den Buchungsweg berührt — besonders beim
Aufteilen des Kerns. Bei reinen Anbauten entfällt er auf Ansage.

**Der Lesepfad** (`gemma_buchung.py`, `abschluss_lesen.py`, `_ocr_seite`) wird nur auf
ausdrücklichen, konkreten Auftrag angefasst. Am 04.09. hat eine Änderung dort den geteilten
Gemma-Dienst zweimal umgeworfen; der Stand wurde zurückgenommen. Nie `response_format`
zusammen mit Bildern.

**Vor jedem neuen Wächter-Test** gegen den Bestand messen. Eine Prüfung, die auf korrekten
Stellen anschlägt, ist schlechter als keine — sie verdirbt das Vertrauen in die übrigen
Funde. Am 08.09. schlug ein neuer Wächter bei sieben korrekten Stellen an und musste
verkleinert werden.

**Befunde selbst nachprüfen**, bevor sie in einen Plan wandern. Zwei der drei Befunde aus
der Erkundung zum Produktplan waren falsch; der Code trug an beiden Stellen die Begründung,
warum er richtig ist.

---

## Was schiefgehen kann

| Risiko | Woran man es merkt | Was dann |
|---|---|---|
| ELSTER-Registrierung kommt nicht | keine Antwort nach 6 Wochen | Pro ohne Selbstübermittlung ausliefern; der Marktplatz trägt das Produkt |
| DATEV-Import scheitert an #REW-Meldungen | Protokoll bei GKM Neff | Meldungen in den Prüfbefund übersetzen, neuer Stapel — Format ist einstellbar |
| Kern-Aufteilung bricht den Golden | Diff nach einem Schritt | Schritt zurücknehmen, kleiner schneiden. Nie zwei Gruppen in einem Commit |
| Gemma-Dienst fällt aus | Belege bleiben auf „wird gelesen" | Der Dienst ist geteilt und startet selbst neu; Belege werden nachgelesen, seit 08.09. auch ohne Ergebnis |
| Zu viele Betriebe zu früh | Index-Neubau je Box, ein Modell-Slot | Deckel bei 20 Betrieben halten, bis 2.1 durch ist |
| Marktplatz ohne Vertragswerk | ein Berater registriert sich | Registrierung bleibt bis 0.5 hinter Freischaltung durch dich |

---

## Offene Entscheidungen

1. **Posteingang:** eigener Mailempfang oder Dienst mit Webhook (blockiert 1.2)
2. **Vierter Tarif für babu Pro** und Höhe der Vermittlungsgebühr
3. **Berater-Prüfung** bei der Registrierung: Berufsträgereintrag automatisch prüfen oder
   von Hand freischalten
4. **TSE:** einkaufen oder selbst bauen
5. **Die zwei Lesepfad-Befunde** aus 1.4 — angehen oder liegen lassen
