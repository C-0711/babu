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
