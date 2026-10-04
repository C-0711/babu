# babu Expenses, Stufe D1 — Auslagen mit Beleg

Stand 04.10.2026 · Entwurf im Gespräch mit dem Auftraggeber abgestimmt · Teil 1 von 4
(Reihenfolge D1 → D2 → D3 → D4: D1 Auslagen mit Beleg, D2 babu-Mastercard,
D3 Fahrten und Pauschalen, D4 Lohn und Vorschüsse).

## Ziel

Mitarbeiterinnen, die etwas für den Betrieb aus eigener Tasche bezahlt haben,
reichen den Beleg in der App ein. Die Inhaberin gibt frei, der Betrieb erstattet
per Bankdatei oder bar, und die Auslage steht richtig gebucht im DATEV-Stapel.

**Fertig ist D1**, wenn eine Auslage vom Foto über Freigabe und Erstattung bis in
den Stapel läuft, ohne dass jemand außerhalb von babu etwas von Hand nachträgt;
wenn Inhaberin und Mitarbeiterin an jeder Stufe eine Nachricht bekommen; wenn eine
Mitarbeiterin nur ihre eigenen Auslagen sieht; und wenn `/api/belege` und
`/api/abgleich` für bestehende Belege bytegleich bleiben.

## Entscheidungen

| Frage | Entscheidung |
|---|---|
| Wie kommt das Geld zurück? | Erstattung als SEPA-Bankdatei (die Inhaberin lädt sie bei ihrer Bank hoch und bestätigt „überwiesen“) oder bar aus der Kasse. babu bewegt selbst kein Geld. |
| Freigabe? | Jede Auslage einzeln durch die Inhaberin. |
| Buchung? | Jede Mitarbeiterin mit Auslagen ist ein eigener Kreditor aus der Kreditorenliste — auch wenn der Betrieb sonst über das Sammelkonto bucht. |
| Was gehört zu D1? | Auslagen mit Beleg, dazu Push-Nachrichten und Mails. |
| Die Karte? | Annahme des Auftraggebers: Es gibt eine babu-Mastercard für Unternehmen (Debit, digital), die jede Mitarbeiterin mit Auslagen automatisch bekommt. Sie kommt in D2; D1 trägt dafür `bezahlt_mit` am Beleg. |
| Preis? | Gleiche Pakete. Auslagen gibt es, wo es ein Team gibt (Salon, Salon Plus). |
| Wo liegen die Daten? | Auslage und Erstattung in der Belegbox des Betriebs (Archiv mit Geschichte). Neu in der Datenbank sind nur die Team-Spalten und die Push-Geräte. |

## 1. Die Auslage

- Eine Auslage ist ein normaler Beleg — eine Lesung, derselbe Weg (Vision auf dem
  iPhone → `/api/buchung/einschaetzung` → `/api/aufnahme`). Dazu kommt die Beiakte
  **`review/<stamm>.auslage.json`**:

      {"von": "<un der Mitarbeiterin>", "name": "Lea",
       "bezahlt_mit": "privat",            # D2: "karte"
       "status": "eingereicht",            # eingereicht | freigegeben | abgelehnt |
                                           # zurueckgezogen | erstattet
       "eingereicht_am": "…", "entschieden_von": null, "entschieden_am": null,
       "grund": null, "kreditor": null, "erstattung": null}

- Zustände:
  - eingereicht → freigegeben → erstattet
  - eingereicht → abgelehnt (mit Grund)
  - eingereicht → zurückgezogen (durch die Mitarbeiterin)
  - freigegeben → eingereicht (die Inhaberin nimmt die Freigabe zurück), solange
    die Auslage weder erstattet noch übergeben ist und in keiner offenen
    Erstattung steckt.
- Neues reines Modul **`auslagen.py`** (ohne Box und Netz): erlaubte Übergänge,
  Summen je Person, Verwendungszweck, Kennung der Erstattung, Deckung der
  Kassenlücke.
- Index: `.auslage.json` kommt in die Ausnahmen von `_index_bauen` und in
  `BELEG_BEIAKTEN`. Wie beim Kreditor wird `auslage` nur in die kopierten Reviews
  in `idx["reviews"]` gelegt. `idx["belege"]` bleibt der unveränderte Vertrag mit
  der App.
- Geschrieben wird nur über `boxschreiber`, unter einem Schloss je Box.

## 2. Einreichen (Mitarbeiterin)

- Neues Team-Recht **`darf_auslagen`** (Spalte in `team`, Standard aus). Die
  Inhaberin schaltet es im Team ein. „darf Belege“ bleibt das Geld des Betriebs,
  „darf Auslagen“ ist das eigene Geld der Mitarbeiterin.
- `/api/aufnahme` bekommt das Feld `auslage=1`. Bei einer Mitarbeiterin verlangt
  es `darf_auslagen`, ohne das Feld wie heute `darf_belege`. Beleg und
  `.auslage.json` gehen in **einem** Commit in die Box.
- `/api/buchung/einschaetzung` verlangt für eine Mitarbeiterin künftig
  `darf_belege` oder `darf_auslagen`. Heute ist die Route für sie ungeprüft.
- Einreichen dürfen in D1 nur Mitarbeiterinnen. Die eigene Auslage der Inhaberin
  bleibt eine Privateinlage (Kassenbuch „Ich hatte ausgelegt“).
- **Konto für die Erstattung:** Die Mitarbeiterin trägt ihre IBAN einmal selbst
  ein: `POST /api/auslagen/konto {iban}`. Die IBAN wird mit Prüfziffer geprüft und
  in der neuen Spalte `team.iban` gespeichert. Gibt es in der Personalakte
  (`mitarbeiter`) eine IBAN zur selben E-Mail, schlägt die App sie gekürzt vor
  („Ist das dein Konto? DE89 •••• 3000“).
- **Eigene Sicht:** `GET /api/auslagen/meine` (Liste mit Stand, Betrag,
  Lieferant, Datum und Grund) und `GET /api/auslagen/meine/{stamm}` mit Bild —
  nur, wenn `von` die Anfragende ist.
- `POST /api/auslagen/{stamm}/zurueckziehen` geht nur bei eigenen und nur bei
  eingereichten Auslagen.
- Lücke schließen: `GET /api/belege` und `/api/beleg/{stamm}` verlangen für eine
  Mitarbeiterin künftig `darf_belege`. Eine Mitarbeiterin, die nur Auslagen
  einreicht, sieht so keine fremden Belege.

## 3. Freigabe (Inhaberin)

- Freigeben, Ablehnen, Zurücknehmen und Erstatten darf **nur die Inhaberin**
  (Rolle `salon`) in ihrer eigenen Box. Kanzlei und Admin sehen die Auslagen nur
  an.
- Routen:
  - `GET /api/auslagen?stand=offen|zu_erstatten|erstattet|alle` (Inhaberin;
    Kanzlei mit `X-Mandant` nur lesend)
  - `POST /api/auslagen/{stamm}/freigeben`
  - `POST /api/auslagen/{stamm}/ablehnen {grund}` (mindestens 3 Zeichen)
  - `POST /api/auslagen/{stamm}/zuruecknehmen`
- **Erste Freigabe einer Mitarbeiterin:** babu legt ihren Kreditor an
  (`kreditoren.anlegen`, nächste freie Nummer, `art: "mitarbeiterin"`,
  `zugang: <E-Mail>`, Name aus dem Team, IBAN aus `team.iban`). Die Nummer steht
  ab dann in jeder ihrer Auslagen (`kreditor`). Ändert sie ihre IBAN, wird sie beim
  Kreditor nachgetragen.
- Auf „Heute“ steht für die Inhaberin die Karte „N Auslagen warten auf dich“, im
  Portal und in der App.

## 4. Erstattung

- `POST /api/auslagen/erstattung {art: "ueberweisung" | "bar", staemme: [...], datum}`
  - Alle Auslagen müssen freigegeben sein und dürfen in keiner anderen Erstattung
    stecken. Gebündelt wird je Mitarbeiterin.
  - Die Kennung läuft je Jahr: `E-2026-001`.
  - Abgelegt wird **`auslagen/erstattungen/<kennung>.json`**:
    `{kennung, art, datum, status, posten: [{stamm, kreditor, name, betrag}],
    je_person: [{kreditor, name, summe}], von, am}`.
- **Überweisung:**
  - Nötig sind die IBAN und der Name des Betriebs (Einstellungen) und die IBAN
    jeder Mitarbeiterin. Fehlt eine, kommt 409 mit Klartext, z. B. „Für Lea fehlt
    die IBAN — sie trägt sie in der App ein.“
  - babu baut eine Bankdatei mit `sepa.pain001`, je Person eine Zahlung, und
    legt sie als `<kennung>.xml` ab. Der Verwendungszweck lautet
    „Auslagen <Name> <Kennung>“.
  - Status `erstellt`. Die Auslagen bleiben freigegeben und tragen
    `erstattung: <kennung>`.
  - `GET /api/auslagen/erstattung/{kennung}/bankdatei.xml` liefert die Datei, nur
    an die Inhaberin.
  - `POST …/{kennung}/ueberwiesen {am}` setzt den Status `ueberwiesen`; die
    Auslagen werden `erstattet`.
  - `POST …/{kennung}/verwerfen` geht, solange der Status `erstellt` ist. Die
    Auslagen werden wieder frei.
- **Bar:**
  - Status sofort `ausgezahlt`, die Auslagen werden `erstattet`.
  - babu legt einen **Erstattungsbeleg** als PDF ab (`<kennung>.pdf`, neu in
    `vordrucke.py`): wer, wann, welche Auslagen, Summe, ein Feld für die
    Unterschrift. Er ist der Beleg für den Kassenabgang.
- Jede Erstattung wird mit `audit.audit` festgehalten.

## 5. Buchung und DATEV

- **`extf.gegenkonto`**: neue Regel direkt nach `gegenkonto_fest`. Eine Auslage
  mit Status freigegeben oder erstattet und mit `kreditor` bucht gegen diesen
  Kreditor — **vor** „bar → Kasse“, denn ihr „bar“ war ihr eigenes Geld.
- **Im Stapel:**
  - **Eingereicht** wird zurückgehalten. Prüfbefund gelb: „N Auslagen warten auf
    Freigabe“.
  - **Abgelehnt** oder **zurückgezogen** kommt nie in den Stapel. Der Beleg bleibt
    im Archiv.
  - **Freigegeben** oder **erstattet** wird normal gebucht: Aufwand an Kreditor.
- **Bar-Erstattung:**
  - Eine eigene Buchungszeile im Monat des Erstattungsdatums: Kreditor der
    Mitarbeiterin an Kasse 1600, Belegfeld = Kennung, Text
    „Auslagenerstattung <Name>“.
  - Neue Funktion `extf.erstattungszeilen(erstattungen, monat)`.
  - Jeder Lauf von `_stapel_uebergeben` merkt sich auch die Kennungen, damit
    Nachträge eine Bar-Erstattung weder vergessen noch doppelt liefern.
- **Kassenlücke:** Bar-Erstattungen eines Monats decken die Kassenbuchzeile
  „Auslagen erstattet“. Sind sie höher als diese Zeile, ist das ein gelber Befund
  („Bar-Erstattung ohne Kassenzeile“).
- **Überweisung:** babu bucht keine Bankzeile, so wie bei jeder anderen
  Lieferantenzahlung — die Bank bucht das Steuerbüro (bzw. Stufe B für Betriebe
  ohne Steuerbüro).
- **Bankabgleich** (`kontoauszug.abgleich`, B2/B3): Eine Abbuchung gilt als
  gedeckt, wenn sie zu einer überwiesenen Erstattung passt — die Kennung steht im
  Verwendungszweck, oder Betrag je Person und Tag (bis zu 10 Tage nach
  `ueberwiesen_am`) stimmen. So kommt keine Bitte „Beleg fehlt“ für eine
  Erstattung.
- **Vorsteuer:** wie gelesen. Gelber Befund bei einer Auslage über 250 € brutto
  mit Vorsteuer: „Rechnung über 250 € muss auf den Betrieb lauten“.
- In der Kreditorenliste trägt der Kreditor der Mitarbeiterin den Vermerk
  „Mitarbeiterin“. Als DATEV-Stammdaten geht er mit K3.

## 6. Nachrichten: Push und Mails

| Ereignis | an | Inhalt (Beispiel) |
|---|---|---|
| eingereicht | Inhaberin | „Lea hat eine Auslage eingereicht: Rossmann, 23,40 €.“ |
| freigegeben | Mitarbeiterin | „Deine Auslage Rossmann (23,40 €) ist freigegeben.“ |
| abgelehnt | Mitarbeiterin | „… wurde abgelehnt: <Grund>.“ |
| überwiesen / bar ausgezahlt | Mitarbeiterin | „Deine Erstattung über 48,10 € ist unterwegs.“ / „… bar ausgezahlt.“ |

- **Mails** gehen über `postfach.senden` (von `post@mybabu.io`) und verlinken auf
  mybabu.io. Jede Person kann sie in den Einstellungen abschalten („Mails zu
  Auslagen“, Standard an).
- **Push** über Apple (APNs, Anmeldung per Schlüssel):
  - Die App meldet ihr Gerät nach dem Anmelden: `POST /api/push/geraet {token, umgebung}`.
  - Gespeichert wird in der neuen Tabelle **`push_geraet`**: `un`, `token`,
    `umgebung`, `angelegt_am`, `zuletzt_am`. Kein Fremdschlüssel auf
    `nutzer(email)`, weil PAT-Konten keine nutzer-Zeile haben.
  - Neues Modul **`push.py`**: HTTP/2 an APNs, Signatur ES256 mit dem Schlüssel
    aus `docker/.env` (`APNS_KEY_ID`, `APNS_TEAM_ID`, Pfad zum `.p8`), Thema
    `io.0711.beleg` bzw. `io.0711.beleg.pro`.
  - Antwortet APNs mit 410, wird das Gerät gelöscht.
  - Ohne Schlüssel ist Push still aus; Mails gehen trotzdem. Schalter
    `BABU_PUSH=0` schaltet Push ab.
- Gesendet wird **nach** dem Commit in einem Hintergrund-Thread. Eine Nachricht,
  die nicht rausgeht, blockiert nie die Anfrage; sie wird geloggt.
- Alle Texte folgen der Sprachregel.

## 7. App (iOS)

- **Reiter nach Rolle:** In `Ausbaustufe.swift` zeigt die App einer Mitarbeiterin
  nur, was sie darf:
  - „Auslagen“ mit `darf_auslagen`
  - den Scanner für Betriebsbelege mit `darf_belege`
  - die Kasse mit `darf_kasse`
  - dazu ein verkürztes Menü (Meine Meldungen, Konto, Abmelden).
- Das gilt für beide Ziele (Beleg und BelegPro). `ios/Tests/zuschnitt` prüft es
  zusätzlich mit der Rolle Mitarbeiterin.
- `/api/ich` liefert für Mitarbeiterinnen
  `rechte: {belege, kasse, auslagen}`.
- **Reiter „Auslagen“ der Mitarbeiterin:**
  - der Knopf „Auslage fotografieren“ (derselbe Scanner, mit `auslage=1`)
  - „Meine Auslagen“ nach Stand mit der offenen Summe
  - die Einzelansicht mit Grund und „Zurückziehen“
  - beim ersten Mal die Karte „Konto für Erstattungen“.
- **Inhaberin:** Auslagen-Liste mit „Freigeben“ und „Ablehnen“. Erstattungen
  macht sie im Portal, weil die Bankdatei dort hingehört.
- Neue Felder im gespeicherten Zustand sind optional; alte `zustand.json` müssen
  laden.

## 8. Portal

- **Inhaberin:** Menü Buchhaltung → „Auslagen“ (neue Ansicht `auslagen`) mit drei
  Reitern:
  - **Offen:** freigeben oder ablehnen.
  - **Zu erstatten:** auswählen → „Erstattung erstellen“ (Überweisung oder bar),
    Bankdatei laden, „überwiesen“ bestätigen, Erstattungsbeleg ansehen.
  - **Erstattet:** die Historie.
- Dazu die Karte auf „Heute“. Im Team gibt es den Schalter „darf Auslagen
  einreichen“, die IBAN steht dort gekürzt.
- **Mitarbeiterin:** „Meine Auslagen“, nur lesen. Eingereicht wird in der App.
- **Kanzlei** (mit `X-Mandant`): die Auslagen-Liste nur lesend. Im Beleg steht
  „Auslage von Lea · freigegeben am …“.
- Es gelten die Sprachregel und: im `onclick` nur Nummern, nie Namen.

## 9. Rechte auf einen Blick

| Was | Mitarbeiterin | Inhaberin | Kanzlei / Admin |
|---|---|---|---|
| Auslage einreichen | mit `darf_auslagen` | – | – |
| Auslagen sehen | nur eigene | alle | alle, nur lesen |
| Freigeben, ablehnen, zurücknehmen | – | ja | – |
| Erstattung, Bankdatei, „überwiesen“ | – | ja | – |
| IBAN für Erstattungen | eigene eintragen | gekürzt sehen | – |

- Neue Routen hängen an `_box_wache` mit Rollen- und Rechteprüfung, nie an
  `ERLAUBT`.
- Abo „nur lesen“ sperrt Einreichen, Freigeben und Erstatten wie jeden
  Schreibweg.

## 10. Datenbank

Jede Änderung zweimal: inline im Schema **und** als Migration `0016_auslagen.sql`.

- `team`: `darf_auslagen` (0/1, Standard 0), `iban` (Text, leer).
- `push_geraet`: wie in Abschnitt 6.
- Abschalten der Mails: als Einstellung `mail_auslagen` in `einstellungen`
  (keine Schemaänderung).

## 11. Tests

- `tests/test_auslagen.py` (rein): erlaubte und verbotene Übergänge, Summen je
  Person, Verwendungszweck, Kennungen je Jahr, Deckung der Kassenlücke.
- `tests/test_auslagen_routen.py`:
  - Einreichen mit und ohne `darf_auslagen`.
  - Die Mitarbeiterin sieht nur Eigenes; eine zweite sieht die Auslagen der
    ersten nicht.
  - Zurückziehen geht nur bei eingereichten Auslagen.
  - Die erste Freigabe legt den Kreditor an.
  - Ablehnen braucht einen Grund.
  - Die Kanzlei darf nur lesen.
  - Abo „nur lesen“ sperrt.
  - `/api/belege` verlangt `darf_belege`.
- `tests/test_auslagen_erstattung.py`:
  - Die Bankdatei hat je Person die richtige Summe, IBAN und den
    Verwendungszweck.
  - Eine fehlende IBAN gibt 409.
  - „überwiesen“ macht die Auslagen erstattet; „verwerfen“ gibt sie frei.
  - Bar ergibt PDF und Kassenzeile.
  - Doppelt erstatten geht nicht.
- `tests/test_auslagen_stapel.py`:
  - Das Gegenkonto ist der Kreditor der Mitarbeiterin, auch wenn der Bon „bar“
    sagt.
  - Eingereicht wird zurückgehalten, Abgelehntes fehlt.
  - Die Bar-Erstattung bucht Kreditor an Kasse.
  - Ein Nachtrag liefert die Bar-Erstattung genau einmal.
  - Die Kassenlücke ist gedeckt; der Bankabgleich zählt die Erstattung als
    gedeckt.
- `tests/test_push.py`:
  - Die APNs-Anfrage wird richtig gebaut.
  - Ohne Schlüssel ist Push aus, Mails gehen trotzdem.
  - 410 löscht das Gerät.
  - Nachrichten kommen nach dem Commit.
  - Ein PAT-Konto kann ein Gerät melden.
- Unverändert:
  - Golden `/api/belege` und `/api/abgleich`.
  - Der Golden-Vertrag `tests/test_api.py`.
  - Ohne Auslagen bleibt jeder Stapel bytegleich.
- `tests/golden/routen.txt` bekommt die neuen Routen.
  `test_jeder_schreibweg_kennt_seine_box.py` prüft die neuen Module mit.
- iOS: `ios/Tests/zuschnitt` mit der Rolle Mitarbeiterin; Fixtures für
  „Meine Auslagen“ in `ios/Tests/run.sh`.

## Außerhalb von D1

- **D2 babu-Mastercard:** digitale Debitkarte je Mitarbeiterin, nur für Ausgaben
  des Betriebs. Jede Zahlung verlangt ein Belegfoto. Grenzen setzt die
  Inhaberin. Gebucht wird über ein Kartenkonto, eine Erstattung entfällt.
- **D3:** Kilometergeld und Verpflegungsmehraufwand.
- **D4:** Erstattung mit dem Lohn, Vorschüsse ans Team.
- Ebenfalls nicht in D1: Auslagen der Inhaberin selbst, Erfassen einer Auslage
  durch die Inhaberin für eine Mitarbeiterin, fremde Währungen.

## Externe Schritte

- APNs-Schlüssel im Apple-Developer-Konto anlegen (Team 8L87Z2GRSG) und
  Push-Fähigkeit (`aps-environment`) für beide App-IDs einschalten — Christoph.
- Hinweis an App Review: Mitarbeiterinnen melden sich mit ihrem eigenen Zugang
  an und sehen nur ihre Auslagen.
