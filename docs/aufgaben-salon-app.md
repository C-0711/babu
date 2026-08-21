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

- [ ] **Leistungskatalog** (Name, Dauer, Preis, Steuersatz) · klein
- [ ] **Rechnungspositionen aus dem Katalog wählen** statt tippen · klein
- [ ] **Preisaushang im Marketing aus echten Preisen** bauen · klein
      Heute tippt man den Text von Hand — die Preise liegen dann vor.
- [ ] **Auswertung je Leistung**: was verdient sie pro Stunde womit · mittel
      Braucht Dauer im Katalog. Die interessanteste Zahl im Laden.

---

## 2. Kundinnen mit Verlauf · mittel, der Kern des Handwerks

Farbformel, Länge, was letztes Mal schiefging, Allergiehinweise. Steht heute
im Karteikasten oder in Ninas Kopf.

- [ ] **Kundinnen-Kartei** (Name, Kontakt, Notiz) · mittel
- [ ] **Behandlungsverlauf** je Kundin, mit Farbformel · mittel
- [ ] **Allergie- und Verträglichkeitshinweise** dokumentieren · mittel
- [ ] **Datenschutz bewusst entwerfen, nicht nebenbei** · mittel
      Farbformeln und Allergiehinweise sind Gesundheitsdaten — andere
      DSGVO-Klasse als Belege. Löschbarkeit von Anfang an: Kundendaten
      gehören NICHT in die Git-Box (dort bleibt alles für immer), sondern
      dahin, wo Team-Fotos und Logos schon liegen.

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

## 4. Der Kalender · groß — anbinden, nicht nachbauen

Ein Salontag besteht aus Terminen. Ohne sie öffnet Nina babu einmal abends
statt zwanzigmal am Tag.

- [ ] **Entscheiden: anbinden oder bauen** · klein
      Empfehlung: anbinden. Terminbuchung ist gelöst, und ein halbgarer
      Eigenbau kostet echte Termine.
- [ ] **An einen bestehenden Kalender andocken** · groß
- [ ] **Termin ↔ Geld verbinden** · mittel
      Das kann babu besser als jeder Buchungsanbieter: Auslastung,
      Umsatzprognose, „dieser Dienstag trägt sich nicht".

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
