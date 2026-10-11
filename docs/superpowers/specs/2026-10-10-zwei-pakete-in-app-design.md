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

| | **Stufe 1 · 9,99 €** | **Stufe 2 · 19,99 €** | **Stufe 3 · 99 €** |
|---|---|---|---|
| Speicherplatz auf souveränen deutschen Servern | **1 GB** | **5 GB** | **100 GB** |
| Belege und Rechnungen fotografieren, lesen, buchen, ablegen | ja | ja | ja |
| Verträge, Post vom Finanzamt, Briefe, Kontoauszüge | ja | ja | ja |
| Kassenbuch | ja | ja | ja |
| Zum Monatsende: TXT-Datei und Belege per Mail ans Steuerbüro | ja | ja | ja |
| Fragen an babu — der Chat kennt deine Dokumente | ja | ja | ja |
| Auslagen abrechnen | ja | ja | ja |
| Bezahlung | Apple In-App-Abo | Apple In-App-Abo | Apple In-App-Abo |
| Start | App laden, 10 Belege frei, dann Abo | dito | dito |

Die Preise sind **Endpreise im App Store** (inklusive Umsatzsteuer), nicht netto.

Warum das besser ist als ein Schnitt nach Funktionen: Ein Speicher-Abo ist ein
Modell, das jede Kundin kennt (iCloud, Dropbox) und das Apple seit Jahren
tausendfach freigegeben hat. Es gibt nichts zu erklären, nichts zu verhandeln,
und vor allem keine Diskussion darüber, ob hier an Verbraucher oder an
Unternehmen verkauft wird — genau der Punkt, an dem die Einreichung am
05.10. gescheitert ist.

**ERiC und die Anbindung an die Buchhaltung fallen aus dem Launch heraus —
und kommen dann für alle dazu, ohne Aufpreis.** Sie waren als Stufe 2 gedacht;
mit dem Speicher-Modell sind sie frei und erscheinen, wann sie fertig werden,
statt einen Starttermin zu blockieren. Im Code existiert von ERiC heute nichts
(die Kennzahlen der Voranmeldung rechnet `monatsabschluss.py` bereits).

Damit gilt die Regel ohne Ausnahme und für immer: **Funktionen trennen die
Stufen nie, nur der Speicher.** Was babu lernt, lernen alle. Das hält die
Store-Beschreibung ehrlich (kein „in der größeren Stufe enthalten"), erspart
jede Abo-Logik im Code außer der Platzprüfung — und macht die Freigabe bei
Apple zur Formsache, weil zwei Speichergrößen nichts sind, worüber man
streiten kann.

Portal, Kanzlei-Cockpit, Ambassador-Programm und Stripe bleiben draußen und
kommen mit babu Pro. Der **Monatsversand ans Steuerbüro gehört dagegen in
beide Stufen** — er ist am 10.10. gebaut worden
(`server/belegreview/uebergabepaket.py`, Commit b71f726).

### Was die Stufen in Belegen heißen (gemessen 10.10. an der echten Box)

Ein Beleg kostet **rund 550 KB**: Foto 538 KB im Schnitt (iPhone, Qualität 0,6,
volle Auflösung; größtes gemessenes 713 KB) plus etwa 13 KB für Lesung und
Protokoll. Die Git-Historie der Belegbox fällt nicht ins Gewicht — die
gemessenen 397 MB sind 8.657 lose Objekte bei 12,7 MB gepackt, ein `git gc`
lässt sie zusammenfallen.

| Belege je Monat | 1 GB reicht | 5 GB reichen | 100 GB reichen |
|---|---|---|---|
| 30 | 5,3 Jahre | mehr als 26 Jahre | ~530 Jahre |
| 50 | 3,2 Jahre | 16 Jahre | ~318 Jahre |
| 100 | 1,6 Jahre | 8 Jahre | ~159 Jahre |

In Belegen: 1 GB trägt rund **1.900**, 5 GB rund **9.500**, 100 GB rund
**190.000**. Der Preis je Gigabyte fällt dabei von 9,99 € über 4,00 € auf
0,99 € — eine Staffel, wie man sie erwartet.

**Der Platz ist Sache des Auftraggebers** (Entscheid 10.10.2026): Er sorgt für
genug Speicher, **ausschließlich in Deutschland**. Die Staffel muss sich also
nicht an der heutigen Plattengröße eines einzelnen Servers ausrichten. Für die
App und den Server heißt das nur: Der Verbrauch je Mandant wird gezählt und
gegen das gebuchte Kontingent gehalten (Abschnitt 5) — wo die Bytes liegen,
ist eine Frage des Betriebs, nicht des Modells. Dass sie in Deutschland
liegen, bleibt Teil des Versprechens und gehört in Store-Text und Landing.

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

> **Gebaut am 10.10.2026** für `index.html`, `barber.html` und
> `werkstatt.html`, dazu die Rechtstexte in `recht.py`. Alles liegt im Repo,
> **nichts ist deployt**.
>
> * Hero: nur noch „App laden", „Anmelden" raus, darunter „Die ersten
>   10 Belege sind frei — ohne Anmeldung, ohne E-Mail."
> * Preise: die drei Stufen (1 GB 9,99 · 5 GB 19,99 · 100 GB 99,00) statt
>   Solo/Salon/Plus, Rechenbasis in „Rechne selbst" ist 19,99 €. Darunter
>   ein Kasten „In jeder Stufe dabei" mit den vier Sätzen des Auftraggebers
>   plus Belege/Kassenbuch und Monatsversand — **keine Tabelle mit Häkchen
>   je Stufe**, denn Funktionen trennen die Stufen nie.
> * Der Paket-Fragebogen („Welches Paket passt zu dir?") ist raus, samt
>   seinem JavaScript: es gibt nichts zu beraten, wenn alle Stufen alles
>   können.
> * „Konto anlegen" (→ `/testen`), „Zum Portal-Login", der Salon-/Shop-/
>   Werkstatt-Check-Knopf und der Profi-Direkt-Upload in der Fußzeile sind
>   raus. Auf keiner der drei Seiten steht noch ein Link auf `/portal` oder
>   `/testen` — **der Portal-Weg bleibt im Code und erreichbar, nur
>   unverlinkt** (Entscheid Auftraggeber 10.10.).
> * „Loslegen": aus „App laden, anmelden, einrichten" wird „App laden,
>   los geht's, fotografieren".
> * Der Wechsel-Abschnitt verspricht keine Kanzlei und kein Buhl-Backend
>   mehr, sondern: babu bereitet vor, abgegeben wird selbst oder vom
>   Steuerbüro. Dieselbe Linie in den FAQ und im Chat-Katalog.
> * **Türkisch (barber.html):** die Übersetzungstabelle fällt bei einem
>   unbekannten Schlüssel auf Deutsch zurück — die neuen Abschnitte wären
>   also stumm deutsch geblieben. 40 Einträge ergänzt; in der türkischen
>   Fassung steht jetzt kein deutscher Satz mehr (am laufenden Dokument
>   geprüft).
> * **Rechtstexte** (`recht.py`): Datenschutz §9 ist jetzt Apple, §9a das
>   bisherige Stripe. AGB §2 beschreibt beide Zugangswege samt der Folge,
>   dass ohne hinterlegte E-Mail der Zugang mit dem Telefon verloren ist;
>   §3 die zehn freien Belege; §3a die Stufen über Apple, §3b das
>   Portal-Abo (vorher 3a), §3c der Zahlungsausfall (vorher 3b). Hilfe:
>   Zugang, Preis, Kündigen und „Passwort vergessen" für beide Wege.
>   Die Fingerabdrücke ändern sich damit (`recht.fassung`) — das ist der
>   Zweck: eine Zustimmung trägt die Fassung, der sie galt.
>   **Das ist der neue Stand für die Anwältin.**



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

> **Gebaut am 10.10.2026**, beide Ziele bauen, alle Harnesse grün.
>
> * `Platz.swift` (Stand und Stufen, reine Rechnung), `Kasse.swift`
>   (StoreKit 2: Preise, Kauf, `currentEntitlements`, `Transaction.updates`),
>   `AblageService+Platz.swift` (Gerätekonto, E-Mail, Kauf melden),
>   `PlatzSheet.swift` (die Auswahl), `PlatzStreifen.swift` (der Hinweis).
> * `OnboardingView` legt bei „Los geht's" das Gerätekonto an; scheitert
>   das, kann sie „Erst mal ohne" weitermachen — die Belege bleiben dann
>   auf dem Telefon, wie bei jedem Konto ohne Ablage.
> * Der Streifen zeigt sich **nur, wenn es etwas zu sagen gibt** (letzte
>   drei freie Belege, über 90 %, voll). Ein Balken, der immer da ist,
>   erzieht zum Wegsehen.
> * Ein 403 mit `grund: speicher_voll|frei_aufgebraucht` ist in der App ein
>   eigener Fall (`AblageErgebnis.platzVoll`): der Beleg bleibt **wartend**
>   liegen statt als fehlgeschlagen abgestempelt zu werden, und die Auswahl
>   geht auf. Harness `ios/Tests/ablage` prüft das samt Negativkontrollen.
> * `ios/Beleg/Support/babu.storekit` + beide Schemata: die Auswahl lässt
>   sich im Simulator durchspielen (nur beim Start aus Xcode, siehe §8).
> * `BABU_ADRESSE=<url>` schickt einen DEBUG-Bau an einen anderen Server —
>   ohne das ginge jeder Probelauf des Gerätekontos gegen die Produktion.
>
> **Punkt 1 unten (Zuschnitt 39/59) ist mit dem Modell aus Abschnitt 1
> hinfällig** und wurde nicht gebaut: Funktionen trennen die Stufen nie.
> `Ausbaustufe` bleibt, wie sie war. Punkt 5 (Launch-Verstecke), Punkt 6
> (Ein Knopf) und Punkt 7 (Store-Eintrag) sind offen.

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

> **Gebaut am 10.10.2026** (Commit „Die Stufen serverseitig"). Was unten in
> der Liste steht, ist erledigt; wo der gebaute Stand von der Liste abweicht,
> steht es hier. Suite grün, 78 neue Tests.
>
> * `paket.py` rechnet die Stufen (ohne Datenbank, ohne Netz), `herkunft`
>   ist die Weiche: für Portal-Betriebe gibt `stand()` None zurück.
> * `POST /api/geraet/anlegen` legt Konto, Mandant und Geräteschlüssel an.
>   **Abweichung:** die Belegbox fordert die Route sofort in einem
>   Hintergrundfaden an, statt auf den Cron-Anleger zu warten — der läuft
>   nur jede Minute, und so lange kann ein Telefon nicht warten, das gerade
>   den ersten Beleg fotografiert. Der Cron bleibt als Rückfall.
> * Die Sperre läuft durch den vorhandenen Engpass `abo.zugang()`, der vier
>   Werte mehr nimmt und den Platz ZUERST prüft. **Abweichung:** der Grund
>   heißt `frei_aufgebraucht` bzw. `speicher_voll` (nicht `paket_noetig`),
>   und es sind **403** wie bei jeder anderen Sperre, nicht 402 — damit
>   bleibt die Form genau die von `testmonat_vorbei`. Die Anzahl der Belege
>   zählt `mandant.belege_gesamt` (nur aufwärts), nicht `/api/aufnahme`.
> * `POST /api/abo/apple` und `POST /api/abo/apple/meldung` prüfen die
>   signierten Belege gegen Apples Wurzelzertifikat (`apple_abo.py`,
>   `zertifikate/AppleRootCA-G3.cer`). `APPLE_TEST_WURZEL` lässt auf einem
>   Entwicklungsserver zusätzlich Xcodes StoreKit-Testwurzel zu; leer im Live-Stand.
> * Der tägliche Lauf zieht `speicher_bytes` gegen die Ablage nach
>   (`taeglich.py schritt_platz`, `box.inhalt_bytes`).
> * **Nicht gebaut, weil nicht nötig:** `abo_status` wird vom Apple-Weg
>   nicht angefasst — die Stufe steht in `mandant.paket`, und `abo.zugang()`
>   entscheidet über den Platz, bevor der Abo-Status überhaupt zur Sprache
>   kommt. Stripe bleibt daneben unverändert.



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
  **Korrektur 11.10.2026 (am Raster gemessen):** auch **99,00 € steht drin**
  — das Raster für DEU führt 800 Punkte von 0,29 € bis 1.199,99 €, darunter
  99,00 neben 99,90 und 99,99. Die Sorge um einen Sonderpreis war unbegründet;
  alle drei Preise sind genau so gesetzt, wie entschieden.
- Apple-Anteil: 15 % (Small Business Program bis 1 Mio. $/Jahr), sonst 30 %.
  Was bei babu ankommt, je Kundin und Monat:

      Stufe 1   9,99 € brutto  →  8,39 € netto  →   **7,14 €** nach 15 % Apple
      Stufe 2  19,99 € brutto  → 16,80 € netto  →  **14,28 €** nach 15 % Apple
      Stufe 3  99,00 € brutto  → 83,19 € netto  →  **70,71 €** nach 15 % Apple

  Zum Vergleich der alte Weg: 39 € netto über Stripe ergaben rund 38 €.
  Stufe 1 bringt also **etwa ein Fünftel davon** — das Modell trägt sich nur
  über Menge. Bei 30 % Apple-Anteil (über 1 Mio. $ Jahresumsatz) wären es
  5,88 € bzw. 11,76 €.
- „10 Belege frei, dann Abo" ist ein Freemium-Tor, kein Apple-Probeabo —
  erlaubt, ohne Intro-Angebot. Ein zusätzliches „erster Monat gratis" wäre
  ein Introductory Offer und braucht Apples Regeln (einmal je Apple-ID).
- Auf der Landing darf Apple genannt werden; Preise dort müssen den
  Store-Preisen entsprechen.

### App Store Connect, Stand 11.10.2026

Alles per API gesetzt, nichts eingereicht:

| | |
|---|---|
| Gruppe | „babu Speicher" (22463529), Anzeigename de-DE „Dein Platz bei babu", en-US „Your babu storage" |
| Abos | drei, monatlich, Ebene 1/2/3, Familienfreigabe aus, Markt nur App Store, Mehrplatz aus |
| Preise | 9,99 / 19,99 / 99,00 € in Deutschland, daraus abgeleitet in **allen 175 Gebieten** (Apples `equalizations`) — Pflicht zum Einreichen, auch wo nicht verkauft wird |
| Gebiete | **nur DEU.** Entscheid 11.10.2026: babu verkauft nur in Deutschland. (Camp45 geht in viele Länder — anderes Produkt, anderer Eintrag.) |
| Texte | de-DE und en-US, Name ≤ 30 und Beschreibung ≤ 55 Zeichen (Apples Grenzen; die erste Fassung war zu lang) |
| Prüfbild | der Auswahlbildschirm aus dem Simulator, 1170×2532, an allen drei Abos, Zustand COMPLETE |
| Prüfnotiz | englisch, an allen drei: dass die Stufen sich NUR im Speicher unterscheiden und wie man den Bildschirm erreicht |
| Erlös | 7,14 / 14,28 / 70,71 € je Monat (Apple nennt sie selbst — die Rechnung in Abschnitt 6 stimmt) |

**Warum `MISSING_METADATA` — die Ursache, gefunden am 11.10.2026 spät.**
Nicht der Vertrag, sondern fehlende Preise. `POST /subscriptionSubmissions`
(eine eigene Ressource — über `reviewSubmissionItems` lassen sich Abos NICHT
einreichen, dort gibt es keine Beziehung dafür) nennt den Grund beim Namen:

    IAP_SUBMISSION_NOT_ALLOWED_MISSING_PRICING_DATA
    Subscription (6821489409) is missing pricing for the following
    territories: (HUN, LUX, VEN, NPL, KGZ, MMR, LVA, JPN, …)

**Apple verlangt einen Preis in JEDEM der 175 Gebiete — auch in denen, in
denen gar nicht verkauft wird.** Verfügbarkeit und Preisliste sind zwei
verschiedene Dinge; das steht in keiner Fehlermeldung der Oberfläche.
Statt 175 Preise zu raten, fragt `asc_abos.py alle_preise` Apple selbst:
`GET /subscriptionPricePoints/<punkt>/equalizations` liefert zu einem
Preispunkt die Entsprechung in jedem anderen Gebiet, Kaufkraft und lokale
Steuer eingerechnet — dieselbe Rechnung, die die Weboberfläche beim „Preis
für alle Gebiete erzeugen" anstellt.

**Der Vertrag bleibt davon unberührt.** `CANNOT_SELL` steht weiter in allen
175 Gebieten; ohne den Paid Applications Agreement verkauft die App nichts.
Zwei getrennte Sperren, beide müssen weg.

**Überholt (der Absatz von vormittags):**
Nicht an den Produkten. `GET /v2/appAvailabilities/<app>/territoryAvailabilities`
sagt für babu Belege in **allen 175 Gebieten `CANNOT_SELL`**, dazu in 27
EU-Gebieten `TRADER_STATUS_NOT_PROVIDED`:

| Gebiet | verfügbar | Zustand |
|---|---|---|
| DEU | ja | `TRADER_STATUS_NOT_PROVIDED`, `CANNOT_SELL`, `AVAILABLE_FOR_SALE_UNRELEASED_APP` |
| AUT | **nein** | `TRADER_STATUS_NOT_PROVIDED`, `CANNOT_SELL` |
| CHE | **nein** | `CANNOT_SELL` |

Daraus folgen drei Dinge, und keines davon kann die API lösen:

1. **`CANNOT_SELL` überall** — die App darf nichts verkaufen. Das ist der
   **Paid Applications Agreement** samt Bank- und Steuerangaben. babu war
   bisher kostenlos ohne jeden Kauf; solange der Vertrag nicht steht, bleibt
   jedes Abo unvollständig, egal wie vollständig seine Felder sind.
   → App Store Connect → **Business → Agreements**, nur der Kontoinhaber.
2. **`TRADER_STATUS_NOT_PROVIDED`** — Apples Händlerstatus nach dem Digital
   Services Act fehlt. Ohne ihn fällt die App aus den EU-Storefronts, also
   auch aus dem einzigen Gebiet, in dem sie heute steht.
   → App Store Connect → **Business → Trader Status**. Die API kennt dafür
   kein Feld (geprüft).
3. **Die App steht nur in DEU**, nicht in AUT und CHE — anders als am
   24.09.2026 notiert. Die Abos sind für DEU/AUT/CHE eingerichtet; sobald
   die App wieder in AUT und CHE verkauft wird, passt das zusammen. Soll es
   bei Deutschland allein bleiben, gehören die beiden Gebiete auch bei den
   Abos heraus (`asc_abos.py`, `GEBIETE`).

Die Produkte selbst sind vollständig: Texte, Preise, Verfügbarkeit, Prüfbild
und Prüfnotiz stehen, und die API kennt kein offenes Feld mehr (Feldliste
abgefragt). Der Zustand sollte von selbst auf `READY_TO_SUBMIT` gehen, sobald
Punkt 1 erledigt ist.

## 7. Offene Entscheidungen

1. ~~Preis im Store~~ — **entschieden 10.10. abends: 9,99 € und 19,99 € brutto.**
2. ~~Zuschnitt~~ — **entschieden: beide Stufen können alles, der Unterschied
   ist der Speicher (1 GB / 5 GB).** ERiC und die Anbindung an die Buchhaltung
   sind aus dem Launch heraus.
2a. Verhalten bei vollem Speicher — Auftraggeber.
3. Wird „Ein Knopf" der Launch-Einstieg?
4. Was passiert mit den heutigen Pilotkonten (Nina, Testbetriebe,
   Ambassadorinnen)? Vorschlag: bleiben auf dem Portal-Weg, bis Pro kommt;
   die Launch-App erkennt ein bestehendes Konto am Schlüssel und zeigt
   dann kein Paket-Blatt.
5. Landing: eine Seite für alle oder weiter `/barber`, `/werkstatt`?

## 8. Reihenfolge und Aufwand (Schätzung)

1. Entscheidungen 1–3 — Auftraggeber.
2. ~~Server: Gerätekonto, Zähler, Apple-Abo-Stand~~ — **gebaut 10.10.2026**
   (Abschnitt 5). Noch nicht deployt.
3. ~~App: Gerätekonto im Onboarding, StoreKit-Blatt, Zähler~~ — **gebaut
   10.10.2026** (Abschnitt 4). Launch-Verstecke offen; TestFlight offen.
4. ~~Landing, Barber, Werkstatt, Rechtstexte, Chat-Katalog~~ — **gebaut
   10.10.2026** (Abschnitt 3). Im Repo, nicht deployt; die Rechtstexte
   gehen in dieser Fassung an die Anwältin.
5. App Store Connect: Abos, Screenshots, Review — Auftraggeber + 1 Tag.
   **Korrektur 11.10.2026: die API kann es doch.** Angelegt per
   `werkzeuge/asc_abos.py` — Gruppe „babu Speicher" (22463529) und die drei
   Abos `babu.speicher.1gb` (6821489409), `babu.speicher.5gb` (6821489462),
   `babu.speicher.100gb` (6821489521), monatlich, Ebenen 1–3. Zeichengleich
   mit `paket.STUFEN` und `ios/Beleg/Support/babu.storekit`;
   `tests/test_apple_produkte.py` hält die beiden Orte im Repo zusammen.

### Was am Kaufweg noch nicht gemessen ist (10.10.2026)

Geprüft ist die Signaturprüfung selbst (eigene Ketten, Negativkontrollen,
`tests/test_apple_abo.py`) und der ganze Weg über die Routen
(`tests/test_geraet_und_apple.py`). **Nicht gemessen ist `Product.purchase()`
gegen den Server**: StoreKit nimmt die Testdatei `babu.storekit` nur an, wenn
die App AUS XCODE startet — beim Start über `simctl` liefert
`Product.products(for:)` nichts, und die Auswahl zeigt die Ersatzpreise aus
`paket.STUFEN`. Für den Durchlauf: aus Xcode starten (Schema `Beleg`,
Simulator) und den Entwicklungsserver mit
`APPLE_TEST_WURZEL=/Applications/Xcode.app/Contents/PlugIns/IDEStoreKitEditor.ideplugin/Contents/Resources/StoreKitTestCertificate.cer`
laufen lassen — sonst weist er den Testbeleg zu Recht ab.
