# Was babu Belege noch vom App Store trennt

Stand **14.10.2026**, alles am selben Tag über die App-Store-Connect-API
abgelesen. Gemessen wird mit `werkzeuge/asc_pruefung.py` (`kurz` zeigt nur
die offenen Punkte); die Zahlen hier sind die Ausgabe dieses Laufs, keine
Erinnerung.

    ~/.venvs/babu/bin/python werkzeuge/asc_pruefung.py kurz

Ergebnis: **42 von 45 in Ordnung, 3 offen.** Alle drei liegen bei Apple,
keiner im Code.

---

## 1. Paid Applications Agreement — „Pending User Info"

Apples eigene Antwort auf `/v2/appAvailabilities/6811956687/territoryAvailabilities`:
**Deutschland** ist das einzige Gebiet mit `available: true` (so gewollt),
und es trägt `CANNOT_SELL`. Dasselbe steht in allen 175 Gebieten. `CANNOT_SELL`
ist genau das Zeichen für den fehlenden Vertrag — nicht für einen Fehler in
der App.

Zwei Aufgaben hängen daran, und nur der Kontoinhaber darf sie erledigen:

- **Bankkonto** — am 14.10. eingetragen (Qonto), Status *Processing*. Apples
  Banner nennt bis zu 24 Stunden. Nichts zu tun außer warten.
- **Steuerformular** — beide Zeilen stehen auf *Missing Tax Info*, ohne
  Einreichungsdatum. Der Weg: **Business → Agreements → Paid Apps → Tax Forms
  → U.S. Form W-8BEN**, und zwar bis zur Unterschrift durch. Ein Formular,
  das man abbricht, zählt nicht; deshalb bleibt „Add Tax Form" sichtbar.

**Welches Formular: W-8BEN, nicht W-8BEN-E.** Das ist gemessen, nicht
geraten. Der Entwicklerzugang ist ein **Einzelkonto auf eine natürliche
Person**:

| Quelle | Wert |
|---|---|
| Signiertes Archiv, `embedded.mobileprovision` → `TeamName` | Christoph Bertsch |
| `GET /v1/certificates` → `name` | „Apple Development: Christoph Bertsch" |
| `GET /v1/users` → `ACCOUNT_HOLDER` | Christoph Bertsch |

Ein Firmenkonto trüge an allen drei Stellen den Firmennamen samt Team-ID.
Daraus folgt für das Formular: wirtschaftlich Berechtigter ist die
**natürliche Person**, Wohnsitzstaat Deutschland, als ausländische
Steuernummer die persönliche Steuer-Identifikationsnummer. Die Angaben zum
Doppelbesteuerungsabkommen schlägt Apples Assistent vor, sobald Deutschland
als Wohnsitzstaat gewählt ist — prüfen, nicht selbst eintippen; im Zweifel
die Zeile vom Steuerbüro ansehen lassen.

> Die Zahlen selbst — IBAN, Steuer-ID — stehen absichtlich nicht in dieser
> Datei und in keiner anderen im Repo. Sie gehören in Apples Formular und
> sonst nirgendwohin.

## 2. Trader Status — „In Review"

`TRADER_STATUS_NOT_PROVIDED` steht in **27 EU-Gebieten**. Seit 24.09.2026
liegt die Angabe bei Apple in Prüfung; ohne sie fällt die App aus den
EU-Storefronts, Deutschland eingeschlossen. Auch hier: warten.

Was dabei veröffentlicht wird, ist Name und Anschrift des Verkäufers auf der
Produktseite. Verkäufer ist nach Punkt 1 die natürliche Person; Impressum,
Rechtstexte und Abrechnung von babu nennen die **nullsiebenelf GmbH**
(`BABU_FIRMA_NAME` auf der H200V). Welcher Name im Store steht, entscheidet
der Auftraggeber.

## 3. Ein alter Prüfvorgang liegt offen

`GET /v1/apps/6811956687/reviewSubmissions` gibt genau eine Einreichung:

    ea12ce78-131a-4ca4-bd94-360c72a6de17   IOS   UNRESOLVED_ISSUES
    eingereicht 2026-10-08T20:54:16Z, 1 Eintrag REJECTED

Das ist der rote Punkt neben „App Review". Solange er steht, nimmt Apple
keine neue Einreichung an — **unabhängig vom Vertrag**. Die Version 1.0
selbst sieht sauber aus (`PREPARE_FOR_SUBMISSION`), und
`/appStoreVersionSubmission` antwortet 404; genau deshalb fällt dieser
Punkt ohne eigene Prüfung nicht auf. `asc_pruefung.py` prüft ihn seit
14.10.2026 mit.

Den Grund gibt die API nicht her: `appStoreVersionForReview` und
`submittedByActor` antworten **403**. Die Nachricht steht nur in der
Weboberfläche unter **App Review** bzw. im Resolution Center. Dort lesen,
beantworten oder die Einreichung zurücknehmen.

---

## Was Stripe dazu beitragen kann — und was nicht

Gemessen am 14.10.2026 über `/v1/account` mit dem Live-Schlüssel der H200V:

- Konto `acct_1RbavUG1IQEnqe6L`, Deutschland, EUR, Zahlungen und
  Auszahlungen aktiv, Anzeigename „0711.io".
- `business_type: individual`, als Person **Christoph Bertsch**. Stripe und
  Apple stimmen also überein; es ist babus eigenes Impressum, das die GmbH
  nennt.
- **Die Bankverbindung ist über diesen Schlüssel nicht lesbar:**
  `/v1/accounts/<id>/external_accounts` antwortet
  `more_permissions_required`. Die IBAN für Apples Formular kommt daher
  nicht aus Stripe, sondern aus dem Online-Banking.
- Auch `BABU_AUSZAHLUNG_IBAN` auf der H200V hilft nicht: dort stehen 16
  Ziffern (Bankleitzahl + Konto), keine IBAN. Das ist bekannt und gewollt
  abgefangen — `kern_auszahlung.schuldner()` liefert ohne gültige IBAN keine
  Bankdatei, sondern eine Überweisungsliste (Test
  `tests/test_auszahlung.py::test_ohne_gueltiges_konto_gibt_es_die_ueberweisungsliste`).

## Was fertig ist

Aus demselben Lauf, damit klar ist, was nicht mehr ansteht: Build 12 hängt
an Version 1.0 und ist `VALID`, Export-Compliance beantwortet, je 6
Screenshots in beiden Größen, Beschreibung mit allen drei Preisen, Laufzeit
und Kündigungsweg, Prüfkonto und Prüfnotiz hinterlegt, alle drei Abos
`READY_TO_SUBMIT` mit Preisen in 175 Gebieten.

---

## Nachtrag 14.10.2026 — die Punkte aus dem Brief an die Entwicklung

### 1 · Konto löschen in der App (5.1.1(v)) — **gebaut**

`POST /api/konto/loeschen` (`server/belegreview/kern_konto.py`), in der App
unter **Einstellungen → Aufhören → Konto löschen**, mit Rückfrage. Gelöscht
wird alles, was babu in seiner Datenbank über den Zugang führt — jede Tabelle
mit `un` oder `mandant_id`, die Chatnachrichten an ihren Fäden und das
Gedächtnis — und der Inhalt der Belegbox in einem Commit
(`boxschreiber.alles_loeschen`).

Was bleibt, ist eine Zeile in `geloescht`: Mandantennummer, Box-Verweis,
Zeitpunkt, Zahl der entfernten Dateien, und ob das Leeren geklappt hat. Kein
Name, keine Adresse, keine E-Mail.

**Zwei Dinge, die babu nicht kann, und die die App auch so sagt:**

- Das Repo der Belegbox samt Historie löscht nur der Betreiber — der
  GitChain-Dienst kennt dafür keinen Weg (`box.py` spricht ausschließlich Git
  über HTTP). Die Tabelle `geloescht` IST deshalb die Arbeitsliste dafür.
- Ein Apple-Abo endet nicht mit dem Konto. Die Rückfrage sagt das wörtlich
  („Dein Platz bei babu endet damit NICHT von selbst … Solange du das nicht
  tust, bucht Apple weiter ab"), und daneben steht **Abo verwalten** →
  `apps.apple.com/account/subscriptions`, sichtbar nur, wenn eine Stufe läuft.

Wer darf: die Inhaberin ihres eigenen Betriebs, und nur bei einem Betrieb aus
der App (`herkunft = "app"`). Ein Portal-Betrieb hängt an einer Kanzlei und
ihren Stapeln — dort ist Löschen ein Vorgang zwischen zwei Parteien und wird
mit dem Weg dorthin abgewiesen. Eine Mitarbeiterin kommt an die Route gar
nicht heran (Positivliste `mitarbeitrecht`, 403).

17 Tests in `tests/test_konto_loeschen.py`. Einer von ihnen schlägt an, wenn
eine NEUE Tabelle mit `un` oder `mandant_id` entsteht, die das Löschen nicht
kennt — damit das nicht still liegen bleibt.

### 2 · Demo-Beleg nur im Simulator — **war schon so**

`ios/Beleg/Beleg/CaptureTab.swift:359` steht seit je in
`#if targetEnvironment(simulator)`. Auf einem Gerät gibt es den Knopf nicht,
auch nicht im Release-Build.

### 3 · Kaufbildschirm — **ergänzt**

- „Käufe wiederherstellen" läuft jetzt über `StoreKit.AppStore.sync()` und
  danach `Transaction.currentEntitlements` (`Kasse.wiederherstellen`). Vorher
  nur die Entitlements — das trägt nach einer Neuinstallation ohne Backup
  nicht.
- Nutzungsbedingungen und Datenschutz stehen auf dem Kaufbildschirm selbst.
  Sie standen nur in den Einstellungen; Apple verlangt sie dort, wo
  abgeschlossen wird.
- Je Stufe: Name (`1 GB`), Preis von Apple (`displayPrice`) und `/ Monat`,
  dazu ein eigener Satz über die Verlängerung.

### 4 · Abo-Ebenen umgedreht — **gefunden und behoben**

App Store Connect führt 1 = 100 GB, 2 = 5 GB, 3 = 1 GB (abgelesen).
`babu.storekit` trug die umgekehrte Reihenfolge, und ein Test hielt sie fest:
sein Docstring sagte „1 ist die höchste Stufe", seine Behauptung verlangte das
Gegenteil. Beides steht jetzt richtig, mit Negativkontrolle.

`groupLevel` liest der Code nirgends; die Reihenfolge im Kaufbildschirm kommt
aus `paket.STUFEN` (aufsteigend nach Platz) und ist von Apples Ebenen
unabhängig.

### 5 · Neues iPhone, Neuinstallation — **gemessen, eine Lücke geschlossen**

- **Belege** kommen zurück, sobald sich jemand anmeldet: die Liste kommt aus
  der Belegbox (`AppStore.vomServerLaden`), nicht vom Telefon.
- **Das Abo** kommt zurück: `Transaction.currentEntitlements` beim Start
  (`BelegApp.swift:35`) meldet es dem Server, der es dem Betrieb des
  angemeldeten Zugangs zuschreibt.
- **Der Geräteschlüssel** liegt in der Keychain als
  `kSecAttrAccessibleAfterFirstUnlock` **ohne** `kSecAttrSynchronizable`. Er
  ist damit in einem verschlüsselten Backup, aber nicht im
  iCloud-Schlüsselbund: ein frisches iPhone ohne Backup braucht eine neue
  Anmeldung per E-Mail-Link. Ihn zu synchronisieren wäre eine Entscheidung
  über einen Zugang in der iCloud und über den Begriff „Geräteschlüssel" —
  nicht gemacht.
- **Geschlossen:** `appAccountToken` geht jetzt beim Kauf mit
  (`paket.kauf_kennung`, UUIDv5 aus der Mandantennummer). Damit findet Apples
  Server Notification den Betrieb auch ohne dieses Telefon, und ein Kauf
  landet nie beim falschen Betrieb, wenn auf einem iPhone zwei Zugänge
  benutzt werden.

### 6 · `Transaction.updates` — **war schon so**

`Kasse.horchen()` läuft ab dem Start (`BelegApp.swift:30`) und nimmt
Verlängerung, nachgereichte Freigabe und Kauf auf einem anderen Gerät auf.
Rückerstattung ebenfalls: `apple_abo.stufe_aus_beleg` gibt bei
`revocationDate` keine Stufe zurück, der Platz endet sofort.

### 7 · Server Notifications — **die Routen gibt es, die URLs sind:**

    Produktion: https://mybabu.io/api/abo/apple/meldung
    Sandbox:    https://mybabu.io/api/abo/apple/meldung

Beide dieselbe: die Route unterscheidet nicht nach Umgebung, sie prüft die
Signaturkette gegen babus eigene Kopie der Apple-Wurzel
(`zertifikate/AppleRootCA-G3.cer`) und nimmt nur Belege auf das eigene Bündel.
Version **2** der Notifications. Sie antwortet 200 auch auf Meldungen zu einem
unbekannten Abo (eine Wiederholung würde daran nichts ändern), 400 nur bei
falscher Signatur.

**Ja, das Backend braucht den Status:** die Speichergrenze hängt daran
(`paket.stand`, Spalten `mandant.paket`/`apple_abo`/`apple_produkt`).

**Gespeichert werden zum Betrieb:** `originalTransactionId`, die
Produkt-Kennung und die daraus abgeleitete Stufe — keine Zahlungsdaten, kein
Preis, kein Apple-Konto. Für „App Privacy" heißt das: Käufe, verknüpft mit der
Nutzerin, zur Funktion der App (nicht für Werbung, nicht für Tracking).

### Die Prüfnotiz in App Store Connect — zwei Korrekturen (14.10.2026)

Beim Vergleich der Notiz mit dem Code fiel auf, dass sie den Prüfer in die
Irre schickt:

- Schritt 2 hieß „tap *Demo-Beleg einlesen (Simulator)*". Diesen Knopf gibt es
  auf **keinem Gerät** — er steht in `#if targetEnvironment(simulator)`, und
  Apple prüft auf Hardware (zuletzt auf einem iPad Air). Jetzt steht dort,
  dass die Kamera auf einen beliebigen Beleg gerichtet wird, und daneben der
  Hinweis, dass der Beispiel-Knopf nur im Simulator existiert.
- Die Notiz nannte das Löschen des Kontos nicht. Jetzt steht der Weg darin
  (Menü → Einstellungen → Aufhören → Konto löschen), samt dem Satz, dass das
  Abo davon nicht endet.

Was in der Notiz **stimmt** und geprüft wurde: „Abo verwalten" gibt es
wirklich in „Deine Ablage" (`PlatzView.swift:130`) — die zweite Stelle neben
dem Löschen-Abschnitt ist zusätzlich, kein Widerspruch.
