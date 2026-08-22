# Was babu noch braucht, um einen Salon zu führen

Stand 22.08.2026. babu managt heute das **Papier** eines Salons vollständig —
Belege, Kasse, Rechnungen, Verträge, Abschluss, Fristen, Ablage. Vom
**Betrieb** noch nichts: keine Termine, keine Kundinnen, keine Preisliste,
keine Arbeitszeit, kein Bestand.

Diese Liste ist nach Wirkung sortiert, nicht nach Aufwand. Jede Aufgabe sagt,
warum sie dran ist und was daran schiefgehen kann.

---

## 0. Zuerst: einmal echt benutzen

Vor jedem neuen Feature. Die App ist an einem Tag stark gewachsen, war aber
nie auf Ninas Gerät, und die Naht App→Server ist nie am echten Server
gelaufen.

- [ ] **App auf Ninas iPhone bringen** · klein
  `DEVELOPMENT_TEAM=8L87Z2GRSG`, `devicectl device install`. UDID steht in
  der Notiz `babu-app-auf-ninas-iphone`.
- [ ] **Die Naht App→Server einmal durchspielen** · klein
  Rechnung stellen, PDF landet in der Box, Beleg fotografieren, Einsortierung
  stimmt, Chat antwortet, Meldungen kommen an. Das ist der einzige Test, den
  es bisher nirgends gibt.
- [ ] **Einen echten Salontag begleiten** · klein
  Was sie tatsächlich öffnet, was sie sucht, wo sie hängenbleibt. Danach
  stimmt die Reihenfolge unten vielleicht nicht mehr — das wäre ein gutes
  Ergebnis.

---

## 1. Preise und Leistungen · klein, sofort nützlich

Gibt es nirgends, wird aber an drei Stellen gebraucht, die schon stehen.

- [x] **Leistungskatalog** (Name, Dauer, Preis, Steuersatz) · klein — 22.08.
      Im Hamburger unter „Deine Preise", auch aus dem Kalender erreichbar.
- [ ] **Rechnungspositionen aus dem Katalog wählen** statt tippen · klein
- [ ] **Preisaushang im Marketing aus echten Preisen** bauen · klein
      Heute tippt man den Text von Hand — die Preise liegen dann vor.
- [ ] **Auswertung je Leistung**: was verdient sie pro Stunde womit · mittel
      Braucht Dauer im Katalog. Die interessanteste Zahl im Laden.

---

## 2. Kundinnen mit Verlauf · mittel, der Kern des Handwerks

Farbformel, Länge, was letztes Mal schiefging, Allergiehinweise. Steht heute
im Karteikasten oder in Ninas Kopf.

- [x] **Kundinnen-Kartei** (Name, Kontakt, Notiz) · mittel — 22.08.
- [x] **Behandlungsverlauf** je Kundin, mit Farbformel · mittel — 22.08.
- [x] **Allergie- und Verträglichkeitshinweise** dokumentieren · mittel — 22.08.
      Stehen rot ganz oben, vor allem anderen.
- [x] **Datenschutz bewusst entwerfen, nicht nebenbei** · mittel — 22.08.
      Farbformeln und Allergiehinweise sind Gesundheitsdaten — andere
      DSGVO-Klasse als Belege. Sie liegen in SQLite, nicht in der Git-Box;
      Löschen nimmt den ganzen Verlauf mit. Zwei Tests wachen darüber:
      dass nach dem Löschen nichts übrig bleibt, und dass nie eine
      Farbformel in der Ablage auftaucht.

---

## 3. Arbeitszeit · mittel, teils Pflicht

babu kennt das Team und was es kostet, aber nicht, wann jemand da war.

- [ ] **Rechtsstand prüfen** · klein
      Der BAG-Beschluss von 2022 verpflichtet Arbeitgeber zur
      Zeiterfassung; die gesetzliche Ausgestaltung war zuletzt offen. Vor
      dem Bauen jemanden mit aktuellem Stand fragen.
- [ ] **Kommen und Gehen erfassen** · mittel
- [ ] **Urlaub und Krankheit** · klein
- [ ] **Monatsmeldung ans Lohnbüro** aus erfassten Stunden · mittel
      Schließt die Lücke, die babu heute offen lässt („macht das Lohnbüro").

---

## 4. Der Kalender · gebaut, nicht angebunden

Ein Salontag besteht aus Terminen. Ohne sie öffnet Nina babu einmal abends
statt zwanzigmal am Tag.

- [x] **Entscheiden: anbinden oder bauen** · klein — 22.08.
      Entschieden wurde gegen die Empfehlung, die hier stand: souverän,
      ohne fremdes Buchungssystem. Der Grund ist der Punkt darunter — wer
      den Kalender anbindet, gibt genau die Verbindung aus der Hand, die
      babu von jedem Buchungsanbieter unterscheidet.
- [x] **Eigener Kalender** · groß — 22.08.
      Öffnungszeiten, Überschneidungsprüfung, Lücken über den Tag verteilt,
      ein Satz genügt („Frau Holder Donnerstag Farbe").
- [x] **Termin ↔ Geld verbinden** · mittel — 22.08.
      Am Termin abrechnen, bar oder Karte; daraus wird abends ein Vorschlag
      fürs Kassenbuch. Ausdrücklich ein Vorschlag: wer Umsätze selbst
      festschreibt, ist eine Kasse nach § 146a AO und braucht eine TSE.
- [ ] **Auslastung und Umsatzprognose** · mittel
      „Dieser Dienstag trägt sich nicht." Die Zahlen liegen jetzt vor.
- [x] **WhatsApp-Agent für die Terminplanung** · groß — 22.08.
      Gebaut und deployed. Die Kundin schreibt, babu schlägt drei Zeiten
      vor, sie antwortet mit einer Nummer, der Termin steht — als Anfrage,
      die im Salon bestätigt wird. Höchstens zwei offene Anfragen je
      Nummer, damit niemand den Tag zuschreibt.
- [ ] **Meta freischalten lassen** · klein, aber Papierkram
      Das Einzige, was noch fehlt: verifiziertes Business-Konto, geprüfte
      Nummer, Zugangstoken. Bis dahin läuft der Prüfstand im Portal — er
      spielt dasselbe Gespräch durch, schickt aber nichts nach draußen.

---

## 5. Warenbestand · klein, bewusst winzig

Kein Lagersystem. Nur: „Farbe 7/0 geht zur Neige."

- [ ] **Nachbestell-Hinweis aus den Einkaufsbelegen** · mittel
      babu sieht die Belege ohnehin und weiß, was wie oft gekauft wird.

---

## 6. Nicht bauen, bis es wirklich sein muss

- [ ] **Kasse am Tresen** · groß, mit Zertifizierung
      Vom Kassen*buch* zur echten Kasse greift § 146a AO: elektronische
      Aufzeichnungssysteme brauchen eine zertifizierte technische
      Sicherheitseinrichtung (TSE). Die heutige Lösung — abends
      Tagessummen, „offene Ladenkasse" — liegt bewusst darunter. Kein
      Feature, sondern ein Projekt.

---

## Nebenher: die offenen Baustellen

- [ ] **Backup außer Haus** · klein
      `~/babu-sichern.sh` läuft täglich, aber auf dieselbe Maschine. Gegen
      Plattenschaden hilft es, gegen Serververlust nicht.
- [ ] **Portal auf die helle Palette ziehen** · klein
      Die App hat kein Grau mehr, `portal.html` noch die alten Werte.
- [ ] **Die neuen Funktionen im Portal zeigen** · groß
      Rechnungen, Marketing, Briefkopf, Vertragskiste, Meldungen leben nur
      in der App. Die Routen stehen, die Oberfläche fehlt.
- [ ] **E-Rechnung (XRechnung)** · mittel
      Für B2B läuft die Übergangsfrist für kleine Betriebe Ende 2027 aus.
      Stuhlmiete an eine Selbständige ist B2B. Die JSON-Ablage der
      Rechnungen ist so gebaut, dass das XML daraus entsteht.
- [ ] **Punkt 5 aus dem Sorglos-Paket: geführter Jahreswechsel** · mittel
