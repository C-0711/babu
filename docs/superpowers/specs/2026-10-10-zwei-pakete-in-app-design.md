# Zwei Pakete, rein in der App — was sich an Landing und App ändern muss

> Entwurf 10.10.2026 nach dem Entscheid des Auftraggebers. Befund am heutigen
> Stand von mybabu.io (`server/babu-web/index.html`) und der App-Store-App
> (`ios/Beleg`, Ziel `Beleg`). Kein Code geändert — das ist die Liste.
>
> **Nachtrag 10.10.2026 abends: Preise und Zuschnitt neu entschieden.**
> Statt 39/59 € netto gelten **9,99 € und 19,99 € als Apple-Endpreise**, und
> der Schnitt zwischen den Stufen verläuft anders (Abschnitt 1). Alles, was
> unten noch 39/59 sagt, ist überholt; die Begründungen dahinter gelten weiter.

## 1. Das Modell (Stand 10.10.2026 abends, endgültig)

**Beide Stufen können dasselbe. Der Unterschied ist der Speicherplatz.**

| | **9,99 €** | **19,99 €** |
|---|---|---|
| Speicherplatz auf souveränen deutschen Servern | **1 GB** | **5 GB** |
| Belege und Rechnungen fotografieren, lesen, buchen, ablegen | ja | ja |
| Verträge, Post vom Finanzamt, Briefe, Kontoauszüge | ja | ja |
| Kassenbuch | ja | ja |
| Zum Monatsende: TXT-Datei und Belege per Mail ans Steuerbüro | ja | ja |
| Fragen an babu — der Chat kennt deine Dokumente | ja | ja |
| Auslagen abrechnen | ja | ja |
| Bezahlung | Apple In-App-Abo | Apple In-App-Abo |
| Start | App laden, 10 Belege frei, dann Abo | dito |

Die Preise sind **Endpreise im App Store** (inklusive Umsatzsteuer), nicht netto.

Warum das besser ist als ein Schnitt nach Funktionen: Ein Speicher-Abo ist ein
Modell, das jede Kundin kennt (iCloud, Dropbox) und das Apple seit Jahren
tausendfach freigegeben hat. Es gibt nichts zu erklären, nichts zu verhandeln,
und vor allem keine Diskussion darüber, ob hier an Verbraucher oder an
Unternehmen verkauft wird — genau der Punkt, an dem die Einreichung am
05.10. gescheitert ist.

**ERiC und die Anbindung an die Buchhaltung fallen aus dem Launch heraus.**
Sie waren als Stufe 2 gedacht; mit dem Speicher-Modell sind sie frei und
kommen, wann sie fertig werden, statt einen Starttermin zu blockieren.
Im Code existiert von ERiC heute nichts (die Kennzahlen der Voranmeldung
rechnet `monatsabschluss.py` bereits).

Portal, Kanzlei-Cockpit, Ambassador-Programm und Stripe bleiben draußen und
kommen mit babu Pro. Der **Monatsversand ans Steuerbüro gehört dagegen in
beide Stufen** — er ist am 10.10. gebaut worden
(`server/belegreview/uebergabepaket.py`, Commit b71f726).

### Was 1 GB und 5 GB wirklich heißen (gemessen 10.10. an der echten Box)

Ein Beleg kostet **rund 550 KB**: Foto 538 KB im Schnitt (iPhone, Qualität 0,6,
volle Auflösung; größtes gemessenes 713 KB) plus etwa 13 KB für Lesung und
Protokoll. Die Git-Historie der Belegbox fällt nicht ins Gewicht — die
gemessenen 397 MB sind 8.657 lose Objekte bei 12,7 MB gepackt, ein `git gc`
lässt sie zusammenfallen.

| Belege je Monat | 1 GB reicht | 5 GB reichen |
|---|---|---|
| 30 | 5,3 Jahre | mehr als 26 Jahre |
| 50 | 3,2 Jahre | 16 Jahre |
| 100 | 1,6 Jahre | 8 Jahre |

Das ist der Grund, warum die zwei Stufen zusammenpassen: Buchungsbelege sind
8 bis 10 Jahre aufzubewahren (§ 147 AO). Bei 50 Belegen im Monat läuft 1 GB
nach gut drei Jahren voll — und genau dann ist der Wechsel auf 5 GB kein
Verkaufstrick, sondern die richtige Antwort. Die Stufe ist der Aufbewahrungs-
pflicht nachgebaut, nicht einem Funktionsschnitt.

**Eine Stellschraube bleibt:** Die App lädt heute das volle iPhone-Foto hoch
(`CaptureTab.swift`, `compressionQuality: 0.6`). Für die Lesung braucht ein
Beleg keine zwölf Megapixel. Auf etwa 2.000 Pixel Längskante verkleinert, läge
er bei grob 150–200 KB — aus 1 GB würden rund 5.200 Belege. Vor einer
Änderung gegen die Lesequalität messen (kleine Schrift auf Thermobons ist der
kritische Fall); die Vorgabe „kein Hochskalieren" bleibt davon unberührt.

### Was die App kann und erklärt werden muss

Vier Dinge, die heute schon gebaut sind und in Beschreibung, Landing und
Store-Text gehören — sie sind der Grund, warum der Speicher überhaupt wertvoll ist:

1. **Der Chat kennt deine Dokumente.** Was hochgeladen ist, versteht babu im
   Gespräch: Verträge, Post vom Amt, Kontoauszüge, Belege
   (`klartext_der_unterlage`, Fragen-Reiter).
2. **Das Profil legt sich von selbst an.** Aus den hochgeladenen Unterlagen
   füllt babu die Angaben zum Betrieb (`auswertung.py`, Salon-Check →
   „Angaben auf Knopfdruck ins Profil").
3. **Mit jedem Dokument wird babu klüger.** Jede Buchung sieht inzwischen das
   Profil, die laufenden Verträge, das Personal, die Kontobewegungen des
   Monats und die Nachbar-Belege — der Kontext wächst mit der Ablage.
4. **Auslagen lassen sich abrechnen** (`auslagen.py`, `AuslagenTab.swift`,
   seit 04.10. live).

## 2. Was „kein Backend" wirklich heißt

Die App braucht auch im 39-€-Paket den Server — nur nicht das Portal:

- **Lesen und Buchen** laufen auf dem Server (`/api/buchung/einschaetzung`,
  Gemma). Ohne Zugang bleibt ein Beleg „ungelesen".
- **„Sicher bei uns verwahrt"** ist die Belegbox (`/api/aufnahme`). Das ist
  der Server.
- Beides hängt heute an einem **Konto** (Einladung, Testmonat-Code,
  Passwort, Kanzlei). Genau das fällt weg.

Nötig ist deshalb ein **Gerätekonto ohne Anmeldung**: die App legt beim
ersten Start selbst ein Konto an (Apple App Attest oder ein Geräteschlüssel,
Route neu: `POST /api/geraet/anlegen` → Konto + Mandant „babu direkt" + Box
über den Box-Anleger, Antwort = Geräteschlüssel wie heute aus der
Anmeldung). Kein Passwort, keine Mail. Die E-Mail fragt die App später in
der Einrichtung, freiwillig — für Wiederherstellung auf einem neuen Telefon
und für die Rechnung. Was dieser Schritt an Server braucht, ist klein:
eine Route, ein Zähler, der Apple-Abo-Stand (Abschnitt 5).

## 3. Landing (mybabu.io) — Änderungen je Abschnitt

Stand heute: drei Pakete Solo 39 / Salon 79 / Salon Plus 149 netto, überall
„Anmelden → Portal", „Konto anlegen → /testen", Steuerbüro, Kanzlei,
Ambassador, Kassenbuch als Standard.

| Abschnitt | Heute | Neu |
|---|---|---|
| Hero „App laden" / „Anmelden" | Anmelden → `/portal` | Nur **„App laden"** (App Store). „Anmelden" weg — es gibt keine Anmeldung. |
| „Drei Schritte" | fotografieren · lesen · fertig in babu | bleibt, plus Satz: „Die ersten 10 Belege sind frei." |
| „So fängst du an" (Screenshots) | Portal-Login, Einladung | Screenshots aus der App: laden, 10 Belege, Paket wählen (Apple-Blatt). |
| „Rechne selbst" (Tabelle) | „Mit babu (79 €)", Spalte „Steuerberater" | **39 €** als Rechenbasis; Spalte „Steuerberater" bleibt, aber „Abschluss — macht die Kanzlei" raus (keine Kanzlei im Launch). |
| „Ein Preis, der zu deinem Salon passt" | Solo 39 / Salon 79 / Salon Plus 149, netto zzgl. USt | **Zwei Karten: 39 € und 59 €**, Preis so, wie Apple ihn zeigt (brutto, s. Abschnitt 6). 59 € = „alles aus 39 + dein ganzer Schriftverkehr + Kassenbuch". Knopf „Welches Paket passt?" raus oder als zwei Sätze. |
| „Konto anlegen" (→ `/testen`) | Testmonat per Formular | weg. Der Weg ist der App Store. `/testen` bleibt erreichbar für den Pro-Pilot, aber unverlinkt. |
| „Abends kurz zählen" (Kassenbuch) | Standard | Als **59-€-Merkmal** kennzeichnen. |
| „Der Wechsel ist leichter, als du denkst" (Steuerberater-Wechsel) | Kanzlei-Wechsel, DATEV | Umschreiben: „Dein Steuerbüro bekommt den fertigen Stapel — bald" oder raus. Beim Launch gibt es keine Übergabe. |
| „App laden, anmelden, ersten Beleg fotografieren" | 3 Schritte mit Portal-Login | **„App laden, Beleg fotografieren, fertig."** Schritt 2 „Anmelden → Portal-Login" weg. |
| „Konto und Finanzamt-Post — auch erledigt" | „Dein Konto ✓ schon da", „Post vom Finanzamt kommt als Nächstes" | Finanzamt-Post = **59 €**. Bankkonto beim Launch nicht versprechen (Bankanbindung hängt am Portal). |
| FAQ „Wer macht denn dann meine Steuer?" / „Kann ich einfach wechseln?" | Kanzlei, Buhl als Backend | Ehrlich: „babu bereitet alles vor, abgeben tust du oder dein Steuerbüro." Kein Kanzlei-Versprechen. |
| FAQ „Was kostet babu?" | „Ab 39 € zzgl. USt" | „39 € oder 59 € im Monat, über den App Store, monatlich kündbar in deinen Apple-Einstellungen. Die ersten 10 Belege kostenlos." |
| FAQ „Kann ich mein Bankkonto anbinden?" | ja | „Kommt mit babu Pro." |
| FAQ „Wo liegen meine Daten?" | eigener Rechner in Deutschland | bleibt — das ist das Verkaufsargument für „sicher bei uns verwahrt". |
| Fußzeile „Beleg-Eingang für Profis (Direkt-Upload)" | Profi-Upload | raus (Portal). |
| Babu-Chat-Widget | Fragen-Katalog | Katalog auf das neue Modell umschreiben (Preise, 10 Belege, Apple, keine Anmeldung). |
| `/barber`, `/werkstatt` | eigene Portale mit denselben Paketen | dieselben Änderungen; sonst sagt die Barber-Seite 79 € und die Startseite 39 €. |

Rechtstexte: AGB §2 „Zugang auf Einladung" → „über den App Store"; §3/3a
Preise und Zahlweg (Apple statt Stripe); Datenschutz §9 Bezahlen (Apple statt
Stripe, babu sieht keine Zahlungsdaten); Hilfe („Wie komme ich zu babu?",
„Wie kündige ich?" → Apple-Abo). Nach der Abnahme vom 10.10. ist das ein
neuer Stand für die Anwältin.

## 4. App (`Beleg`, App Store) — Änderungen

Heute: ein Zuschnitt `Beleg` (Erfassen, Dokumente, Fragen; Kasse/Termine
nur in `BelegPro`), Anmeldung per Passwort/Link/Code gegen das Portal,
kein StoreKit, Testmonat vom Server.

1. **Zuschnitt 39/59 statt Beleg/Pro.** `Ausbaustufe` bekommt eine dritte
   Größe neben `voll`: das **Paket** (`.belege` = 39, `.schriftverkehr` =
   59), zur Laufzeit aus dem Apple-Abo, nicht aus dem Build-Flag. Reiter
   und Menü filtern nach beidem:
   - 39: Erfassen, Fragen; Dokumente **nur Belegfach**; Menü ohne
     Kassenbuch, Verträge, Kontoauszug.
   - 59: dazu Dokumente mit allen Fächern (Verträge, Behörde, Briefe,
     Kontoauszüge), **Kassenbuch** als Reiter (heute `nurVoll` → wird
     `nurSchriftverkehr`), Verträge und Kontoauszug im Menü.
   - `BelegPro` bleibt der Bau für den Jahreswechsel (Termine, Kundinnen,
     Team …), unverändert.
   Harness `ios/Tests/zuschnitt` prüft dann vier Fassungen statt zwei.
2. **Gerätekonto statt Anmeldung.** `OnboardingView` („Los geht's") legt
   im Hintergrund das Gerätekonto an (Abschnitt 2) und speichert den
   Schlüssel in der Keychain — derselbe Weg wie heute nach
   `anmeldungUebernehmen`. Die Anmeldeseite (Passwort, Link, Code) kommt
   aus dem Launch-Bau raus; `KontoMenu` → „Konto" zeigt stattdessen:
   Paket, Belege-Zähler, E-Mail für Wiederherstellung, Apple-Abo verwalten.
3. **Zähler 10 Belege.** Der Server zählt je Konto (`/api/ich` liefert
   `belege_frei: 10, belege_genutzt: n`), die App zeigt ihn ab Beleg 7
   („Noch 3 frei") und sperrt die Aufnahme ab 11 mit dem Paket-Blatt. Nur
   serverseitig zählen — ein lokaler Zähler fällt mit dem Neuinstallieren.
   Ansehen bleibt immer frei (dieselbe Regel wie beim Testmonat: nur
   ansehen, nichts Neues).
4. **StoreKit 2.** Zwei Auto-Renewable Subscriptions in einer Gruppe
   (`babu.belege.monat`, `babu.schriftverkehr.monat`), Paket-Blatt mit
   `SubscriptionStoreView`, Upgrade 39 → 59 sofort (Apple rechnet anteilig),
   „Abo verwalten" → `manageSubscriptionsSheet`. Der Stand des Abos
   (`Transaction.currentEntitlements`) geht an den Server
   (`POST /api/abo/apple` mit der signierten Transaktion) — der Server
   verifiziert gegen Apple und schaltet frei; dazu App Store Server
   Notifications V2 für Kündigung und Zahlungsausfall, damit der Server
   auch ohne die App Bescheid weiß. Ohne Netz gilt der letzte bekannte
   Stand aus der Keychain.
5. **Was aus dem Launch-Bau rausfällt** (nur verstecken, Code bleibt für
   Pro): Reiter „Empfehlen" und alles Ambassador, Auslagen/Team, „An mein
   Steuerbüro geben", DATEV-Büchlein, Monatsabschluss-Freigabe mit
   Kanzlei-Texten. `arbeitsweise` steht im Launch fest auf „selbst".
6. **Ein Knopf (V2)** passt zum Modell: Heim-Seite mit „Noch 3 frei" als
   Zahl, nach dem zehnten Beleg das Paket-Blatt. Entscheidung, ob V2 der
   Launch-Einstieg wird, steht aus (`docs/v2-ein-knopf.md` §8.5).
7. **App-Store-Eintrag** (Branch `claude/app-store-connect-distribution`
   auf GitHub: Datenschutz-Manifest, Build 7/8): Beschreibung, Screenshots
   und Preis-Hinweis auf 39/59 und „10 Belege frei"; In-App-Käufe in App
   Store Connect anlegen, Review-Notizen (Testkonto entfällt — Apple
   testet mit dem Gerätekonto).

## 5. Server — das Minimum für den Launch

- `POST /api/geraet/anlegen` (Gerätekonto, Box per Box-Anleger, Mandant
  in „babu direkt", `test_bis` leer, `belege_frei = 10`).
- Zähler in `/api/ich`; Sperre in `/api/aufnahme` ab 11 ohne Abo
  (403 `paket_noetig`, dieselbe Form wie `testmonat_vorbei`).
- `POST /api/abo/apple` + Server Notifications V2 → `mandant.abo_status`
  (`abo.py` kennt die Stände schon; Stripe bleibt daneben für Pro).
- E-Mail nachreichen (`POST /api/konto/email`) für Wiederherstellung;
  Wiederherstellung auf neuem Telefon = Link per Mail, wie heute
  `/anmelden/<token>`.
- `BABU_SIGNUP`, Testmonat-Code, Warteliste, Ambassador, Kanzlei bleiben
  im Code, sind aber im Launch nicht erreichbar (Landing verlinkt nichts).

## 6. Apple-Regeln und Zahlen

- Digitale Abos **müssen** über In-App-Kauf laufen (App Store Review 3.1.1);
  ein Link zu Stripe wäre ein Ablehnungsgrund. Richtig so wie entschieden.
- Apple-Preise sind **Endpreise inkl. USt**. 9,99 € und 19,99 € stehen in
  Apples Preisraster, es braucht keinen Sonderpreis. **Entschieden 10.10.**
- Apple-Anteil: 15 % (Small Business Program bis 1 Mio. $/Jahr), sonst 30 %.
  Was bei babu ankommt, je Kundin und Monat:

      Stufe 1   9,99 € brutto  →  8,39 € netto  →  **7,14 €** nach 15 % Apple
      Stufe 2  19,99 € brutto  → 16,80 € netto  →  **14,28 €** nach 15 % Apple

  Zum Vergleich der alte Weg: 39 € netto über Stripe ergaben rund 38 €.
  Stufe 1 bringt also **etwa ein Fünftel davon** — das Modell trägt sich nur
  über Menge. Bei 30 % Apple-Anteil (über 1 Mio. $ Jahresumsatz) wären es
  5,88 € bzw. 11,76 €.
- „10 Belege frei, dann Abo" ist ein Freemium-Tor, kein Apple-Probeabo —
  erlaubt, ohne Intro-Angebot. Ein zusätzliches „erster Monat gratis" wäre
  ein Introductory Offer und braucht Apples Regeln (einmal je Apple-ID).
- Auf der Landing darf Apple genannt werden; Preise dort müssen den
  Store-Preisen entsprechen.

## 7. Offene Entscheidungen

1. ~~Preis im Store~~ — **entschieden 10.10. abends: 9,99 € und 19,99 € brutto.**
2. ~~Zuschnitt~~ — **entschieden: beide Stufen können alles, der Unterschied
   ist der Speicher (1 GB / 5 GB).** ERiC und die Anbindung an die Buchhaltung
   sind aus dem Launch heraus.
2a. **Neu offen: Was passiert, wenn der Speicher voll ist?** Vorschlag: ab
   90 % ein Hinweis in der App, bei 100 % keine neuen Belege mehr annehmen
   (ansehen und herunterladen bleibt immer frei, wie bei der Testmonat-Sperre),
   dazu der Wechsel auf 5 GB als ein Tippen über Apple. **Niemals von selbst
   löschen** — die Belege sind aufbewahrungspflichtig, und das Versprechen
   lautet „sicher bei uns verwahrt". Dafür muss der Server den Verbrauch je
   Mandant kennen und in `/api/ich` liefern (Abschnitt 5).
2b. Soll das Foto vor dem Hochladen verkleinert werden? Erst messen.
3. Wird „Ein Knopf" der Launch-Einstieg?
4. Was passiert mit den heutigen Pilotkonten (Nina, Testbetriebe,
   Ambassadorinnen)? Vorschlag: bleiben auf dem Portal-Weg, bis Pro kommt;
   die Launch-App erkennt ein bestehendes Konto am Schlüssel und zeigt
   dann kein Paket-Blatt.
5. Landing: eine Seite für alle oder weiter `/barber`, `/werkstatt`?

## 8. Reihenfolge und Aufwand (Schätzung)

1. Entscheidungen 1–3 — Auftraggeber.
2. Server: Gerätekonto, Zähler, Apple-Abo-Stand — 3 Tage.
3. App: Zuschnitt 39/59, Gerätekonto im Onboarding, StoreKit-Blatt,
   Zähler, Launch-Verstecke — 5 Tage, Build auf dem Mac, TestFlight.
4. Landing, Barber, Werkstatt, Rechtstexte, Chat-Katalog — 1 Tag, dann
   Anwältin.
5. App Store Connect: Abos, Screenshots, Review — Auftraggeber + 1 Tag.
