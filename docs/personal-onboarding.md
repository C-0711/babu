# Mitarbeiter in babu — Onboarding, Zeiterfassung, Lohn

Stand 22.08.2026. Recherchiert, nicht geraten — die Belege stehen unten.

Das Ziel ist klar: Nina legt eine Mitarbeiterin an, die bekommt einen Link,
macht auf dem Telefon alles selbst, und Nina druckt nie etwas. Kein
Lohnbüro, kein DATEV.

Das ist zu **etwa achtzig Prozent erreichbar**. Die restlichen zwanzig sind
keine Programmierfrage, und es lohnt sich, sie zuerst zu benennen — sonst
bauen wir sechs Wochen und stehen dann vor einer Wand.

---

## 1. Was der Gesetzgeber erlaubt — und was nicht

### Digital geht, seit dem 1.1.2025

Das Vierte Bürokratieentlastungsgesetz hat das Nachweisgesetz geändert. Die
wesentlichen Arbeitsbedingungen dürfen seither in **Textform** (§ 126b BGB)
erteilt werden — E-Mail oder PDF genügen, keine Unterschrift nötig. Ein
unbefristeter Arbeitsvertrag lässt sich damit vollständig digital schließen.

Das ist das Fundament für „Nina druckt nie".

### Papier bleibt Pflicht — an drei Stellen

| Vorgang | Warum |
|---|---|
| **Befristeter Arbeitsvertrag** | § 14 Abs. 4 TzBfG verlangt Schriftform. Wird sie verletzt, ist nicht der Vertrag unwirksam, sondern **die Befristung** — es entsteht ein unbefristetes Arbeitsverhältnis. |
| **Kündigung** | § 623 BGB verlangt Schriftform und schließt die elektronische Form **ausdrücklich aus**. Keine E-Mail, keine Signatur. |
| **Aufhebungsvertrag** | Ebenfalls § 623 BGB. |

Dazu: Verlangt eine Mitarbeiterin ausdrücklich Schriftform, muss Nina sie
unverzüglich liefern.

> **Konsequenz für das Produkt.** Ninas jetziger Mustervertrag ist ein
> „befristetes Probearbeitsverhältnis" über sechs Monate. Genau diese
> Konstruktion zwingt sie aufs Papier. Ein **unbefristeter Vertrag mit
> sechsmonatiger Probezeit** (§ 622 Abs. 3 BGB, zwei Wochen Kündigungsfrist)
> erreicht arbeitsrechtlich fast dasselbe, ist sauberer — und geht rein
> digital. Das ist keine Kleinigkeit, sondern der Unterschied zwischen
> „papierlos" und „fast papierlos".

### Melden an die Ämter: hier liegt die eigentliche Wand

**Sozialversicherung (DEÜV).** An-, Ab- und Jahresmeldungen, Beitrags­nachweise:
§ 95b SGB IV schreibt vor, dass diese Meldungen aus **systemgeprüften
Programmen** übermittelt werden. Die Systemprüfung macht die ITSG im Auftrag
des GKV-Spitzenverbands (das „GKV-Zertifikat"), sie wird jährlich erneuert.
babu kann diese Meldungen **nicht einfach senden** — auch nicht mit
perfektem XML. Die Alternative ohne Zertifikat ist das **SV-Meldeportal**
der Sozialversicherungsträger: eine Ausfüllhilfe im Browser, in die man von
Hand einträgt.

**Lohnsteuer-Anmeldung (Finanzamt).** Deutlich zugänglicher. Die
Steuerverwaltung gibt **ERiC** (ELSTER Rich Client) als C-Bibliothek
kostenlos an Softwarehersteller heraus; nötig ist eine Entwickler­registrierung.
Ein Anspruch auf einen Account besteht nicht, aber der Weg ist offen. Über
denselben Weg läuft der **ELStAM-Abruf** — ohne den kann man gar nicht
abrechnen, weil die Lohnsteuerabzugsmerkmale vom Finanzamt kommen.

**Weitere Meldewege**, die dazugehören und oft vergessen werden:
Betriebsnummer bei der Agentur für Arbeit, Lohnnachweis an die
Berufsgenossenschaft (für Friseure die **BGW**), elektronische
Arbeitsunfähigkeitsbescheinigung (eAU — der Arbeitgeber *ruft ab*, die
Mitarbeiterin reicht nichts mehr ein), A1-Bescheinigung bei Auslandseinsatz.

### Zeiterfassung

Die Pflicht besteht bereits — EuGH 2019, BAG 13.09.2022 (1 ABR 22/21): der
Arbeitgeber muss ein System zur Erfassung der Arbeitszeit einführen. Die
Novelle des Arbeitszeitgesetzes mit **elektronischer** Aufzeichnungspflicht
steckt weiter im Verfahren, soll aber im Lauf des Jahres 2026 kommen.
Bußgelder bis 30.000 €.

Für babu heißt das: nicht abwarten. Wer die Zeiterfassung jetzt sauber baut,
ist bei Inkrafttreten fertig.

### Ausländische Mitarbeiterinnen

§ 4a Abs. 5 AufenthG: Nina muss den Aufenthaltstitel bzw. die Arbeitserlaubnis
prüfen und **für die Dauer der Beschäftigung eine Kopie aufbewahren** —
ausdrücklich auch **in elektronischer Form**. Das passt exakt zu babus
Scanner. Neu ist eine Mitteilungspflicht: endet die Beschäftigung vorzeitig,
muss die Ausländerbehörde **binnen vier Wochen** informiert werden. Eine
Frist, die babu selbst überwachen kann.

---

## 2. Was das für den Bauplan heißt

Drei Stufen. Die erste bringt sofort Nutzen und braucht **keine**
Zertifizierung.

### Stufe 1 · Die digitale Personalakte (jetzt baubar)

Alles, was heute auf Papier durch den Salon wandert, entsteht und lebt in
babu. Am Ende steht ein **strukturierter Export** — genau die Daten, die der
Personalfragebogen abfragt, maschinenlesbar. Wer heute die Abrechnung macht,
bekommt sie fix und fertig, statt handschriftliche Bögen abzutippen.

Damit ist Nina den Papierkram los, auch ohne dass babu selbst abrechnet.

### Stufe 2 · Selbst abrechnen (baubar, hohe Verantwortung)

Lohnsteuer nach dem amtlichen Programmablaufplan des BMF, SV-Beiträge,
ELStAM-Abruf und Lohnsteuer-Anmeldung über ERiC. Lohnzettel landen im
Postfach der Mitarbeiterin in der App.

Das ist rechnerisch machbar und rechtlich zulässig. Es ist aber der Punkt, an
dem babu Verantwortung für fremdes Geld übernimmt — mit allem, was an
Haftung daran hängt. Vor dieser Stufe braucht es eine Entscheidung, keine
Zeile Code.

### Stufe 3 · SV-Meldungen selbst senden (gesperrt)

Erst mit ITSG-Systemprüfung und GKV-Zertifikat. Bis dahin zwei ehrliche
Zwischenwege:

1. **SV-Meldeportal**: babu bereitet jede Meldung vollständig auf und zeigt
   sie feldweise an; Nina überträgt sie einmal pro Vorgang. Unschön, aber
   dauert Minuten statt Stunden — und ist heute schon möglich.
2. **Zertifizierter Partner** als Übertragungsschiene. babu bleibt das
   System, in dem die Daten leben.

---

## 3. Der Ablauf, wie er sich anfühlen soll

### Nina legt an — zwei Minuten

Name, Handynummer, **Beschäftigungsart**. Die Art entscheidet über alles
Weitere:

| Art | Was daran hängt (2026) |
|---|---|
| Festanstellung Voll-/Teilzeit | volle SV-Pflicht, Krankenkasse frei wählbar |
| Geringfügig (Minijob) | **603 €/Monat**, 7.236 €/Jahr; Meldung an die **Minijob-Zentrale**, nicht an die Krankenkasse; RV-Befreiung möglich |
| Kurzfristige Beschäftigung | 3 Monate/70 Arbeitstage, keine Berufsmäßigkeit |
| Auszubildende | Vertrag über die **Handwerkskammer** (Lehrlingsrolle), Jugendarbeitsschutz bei unter 18 |
| Freie Mitarbeit / Stuhlmiete | **kein** Arbeitsvertrag — Scheinselbständigkeit ist das größte Risiko im Friseurhandwerk. babu muss hier warnen, nicht bequem machen. |

Nina wählt die Vorlage, trägt Stunden und Gehalt ein — babu prüft sofort
gegen den **Mindestlohn 13,90 €** (2026; ab 1.1.2027: 14,60 €) und gegen die
Minijob-Grenze. Ein Vertrag, der unter Mindestlohn liegt, wird gar nicht
erst erzeugt.

### Die Mitarbeiterin bekommt einen Link

Eine SMS, ein Tippen, sie ist drin. Kein Konto anlegen, kein Passwort
erfinden — derselbe Weg, den babu für Ninas Team schon kennt.

### Der Wizard — eine Frage pro Bildschirm

So wie das Kassenbuch schon funktioniert:

1. **Wer bist du** — die Felder des Personalfragebogens, aber einzeln und in
   Alltagssprache statt als DIN-A4-Formular
2. **Ausweis fotografieren** — Personalausweis oder Aufenthaltstitel; der
   Scanner liest ab, was er lesen kann, sie bestätigt
3. **Sozialversicherungsnummer** — abfotografieren oder eintippen
4. **Krankenkasse** — Auswahl aus einer Liste
5. **Steuer-IdNr.** — Grundlage für den ELStAM-Abruf
6. **Bankverbindung** — IBAN abfotografieren
7. **Vertrag lesen und annehmen** — vollständiger Text, scrollen bis unten,
   dann annehmen. Textform genügt (siehe oben), die Annahme wird mit
   Zeitstempel protokolliert
8. **Belehrungen** — Arbeitsschutz, **Hautschutz nach TRGS 530** (das ist die
   Friseur-Vorschrift, an die niemand denkt), Datenschutz, Verschwiegenheit;
   jede einzeln bestätigt
9. **Fertig** — sie sieht ihren ersten Arbeitstag im Kalender

Jedes Dokument geht durch die vorhandene `einsortieren`-Strecke. Nina muss
nichts prüfen, nichts abheften, nichts drucken.

### Danach: der Alltag auf dem Telefon

**Zeiterfassung — hier liegt babus eigentlicher Vorteil.** Andere Systeme
brauchen eine Stempeluhr. babu kennt den Tag bereits: die Termine stehen im
Kalender, und es weiß, wer sie gemacht hat. Vorschlag:

> Abends fragt babu: *„Du hattest heute Termine von 9:15 bis 17:40, dazu
> 40 Minuten Pause. Stimmt das?"* — Ein Tipp, fertig.

Das ist keine Spielerei. Es ist der Unterschied zwischen einer Pflicht, die
täglich vergessen wird, und einer, die sich von selbst erledigt. Wer will,
kann trotzdem manuell stempeln — per NFC-Aufkleber am Tresen oder Knopf in
der App.

Dazu, alles im selben Muster wie die schon gebauten Meldungen:

- **Urlaubsantrag** — sie beantragt, Nina sieht es in „Das steht an", tippt zu
- **Krankmeldung** — sie meldet sich in der App; die AU holt babu später über
  das eAU-Verfahren ab, sie muss nichts einreichen
- **Lohnzettel** — landet im Postfach in ihrer App, nicht in einem Umschlag
- **Fristen** — Probezeitende, Befristungsende, Ablauf des Aufenthaltstitels,
  Vertragsjubiläum: babu meldet sich, bevor es eng wird

### Ninas Dashboard

Unter *Konto → Dein Team*, ausgebaut:

- Wer ist heute da, wer im Urlaub, wer krank
- Offene Stunden, Überstunden, Resturlaub je Person
- Personalkosten des Monats gegen den Umsatz — die Zahl, die im Salon zählt
- **Was fehlt noch**: nicht angenommene Verträge, fehlende Ausweiskopien,
  ablaufende Titel, nicht bestätigte Stundenzettel
- Ein Knopf: **Monatsübergabe** — alles, was die Abrechnung braucht, als
  strukturierter Export

---

## 4. Die Daten

Aus dem Personalfragebogen ergibt sich die Struktur unmittelbar. Sie gehört
— wie Kundinnen und Termine — in **SQLite, nicht in die Belegbox**: das sind
personenbezogene Daten, und sie müssen löschbar bleiben.

Die gescannten **Dokumente** dagegen gehören in die Belegbox: Verträge,
Ausweiskopien, Bescheinigungen sind aufbewahrungspflichtig, und dort ist
jede Fassung nachweisbar.

```
mitarbeiter    person   : vorname, name, geburtsname, geburtsdatum,
                          geburtsort, geburtsland, geschlecht,
                          staatsangehoerigkeit
               kontakt  : strasse, plz, ort, telefon, email
               steuer   : steuer_idnr, rentenvers_nr, kinderfreibetrag
               bank     : iban, bic, bankname
               beschaef : art, eintritt, austritt, befristet_bis,
                          stunden_woche, tage_woche, entgelt, entgeltform,
                          urlaubstage, probezeit_bis
               sv       : krankenkasse, kv_status, rv_pflicht,
                          elterneigenschaft, kinder_unter_25
               status   : schwerbehindert, grad, weitere_beschaeftigung,
                          hauptbeschaeftigung
               ausland  : titel_art, titel_bis, arbeitserlaubnis_bis
               stand    : eingeladen | im_wizard | vollstaendig | aktiv |
                          ausgeschieden

dokument       art (vertrag, ausweis, titel, sv_nachweis, au, sonstiges),
               belegbox_pfad, gueltig_bis, erfasst_am

zeit           tag, beginn, ende, pause_min, quelle (kalender|manuell|nfc),
               bestaetigt_von_mitarbeiter, bestaetigt_von_inhaberin

abwesenheit    art (urlaub, krank, unbezahlt), von, bis, stand, beleg

lohnlauf       monat, brutto, netto, ag_kosten, stand, zettel_pfad
```

Der Personalfragebogen der Lohnprogramme ist damit **vollständig aus der
Datenbank erzeugbar** — inklusive der Felder, die Nina heute per Hand
ausfüllt.

---

## 5. Die Verträge

Ninas Muster ist als Ausgangspunkt brauchbar, aber es ist erkennbar ein
umgebautes Formular aus einer Arztpraxis — in § 11 steht „Patienten". Für
ein Produkt, das viele Salons benutzen, reicht das nicht. Was mir beim Lesen
aufgefallen ist, in der Reihenfolge des Risikos:

| Stelle | Befund |
|---|---|
| § 13 Verfallfristen | Nennt keine Ausnahme für den Mindestlohn. Nach der Rechtsprechung des BAG kann eine Ausschlussklausel dadurch **insgesamt unwirksam** werden. |
| § 1 Abs. 2 | „Befristetes Probearbeitsverhältnis", das danach „als unbefristet gilt" — vermischt Befristung (§ 14 TzBfG) und Probezeit (§ 622 BGB). Zwingt außerdem aufs Papier. |
| § 15 | Doppelte Schriftformklausel; in AGB regelmäßig unwirksam. |
| § 5 Abs. 3 | Rückzahlung von Fortbildungskosten ohne zeitliche Staffelung — regelmäßig unwirksam. |
| § 7 Abs. 5 | „Bleibt der **Arbeitgeber** … der Arbeit fern" — Schreibfehler, gemeint ist der Arbeitnehmer. |
| § 11 | „Patienten" statt Kundinnen. |
| § 3 Abs. 3 | Mehrarbeitspflicht ohne Vergütungsregelung. |
| fehlend | Mehrere Pflichtangaben nach § 2 NachwG: Zusammensetzung des Entgelts, Ruhepausen, Kündigungsverfahren samt **Klagefrist nach § 4 KSchG**, Hinweis auf Tarifverträge, Fortbildungsanspruch. |
| § 9 | 12 Urlaubstage bei 3-Tage-Woche ist exakt das gesetzliche Minimum — korrekt gerechnet, aber ohne Puffer. |

Was babu mitbringen sollte, zugeschnitten aufs Friseurhandwerk:

**Verträge**
1. Arbeitsvertrag Voll-/Teilzeit, unbefristet mit Probezeit *(digital)*
2. Arbeitsvertrag geringfügig beschäftigt, mit RV-Befreiungsantrag *(digital)*
3. Arbeitsvertrag kurzfristige Beschäftigung *(befristet → Papier)*
4. Aushilfs-/Werkstudentenvertrag
5. Hinweis- und Prüfbogen freie Mitarbeit / Stuhlmiete — **mit Warnung vor
   Scheinselbständigkeit**, nicht als bequeme Vorlage

**Anlagen, die zu jedem Vertrag gehören**
6. Nachweis der wesentlichen Arbeitsbedingungen (§ 2 NachwG) — die
   Vollständigkeitsliste
7. Verpflichtung auf Datengeheimnis (Art. 88 DSGVO, § 26 BDSG) —
   Kundendaten, Farbformeln, Fotos
8. Verschwiegenheit und Abwerbeverbot während des Arbeitsverhältnisses
9. Fortbildungskosten-Rückzahlung, **gestaffelt**
10. Arbeitsmittel und Werkzeug, Trinkgeldregelung

**Belehrungen und Unterweisungen**
11. Arbeitsschutzunterweisung (§ 12 ArbSchG)
12. **Hautschutz nach TRGS 530 Friseurhandwerk** — Hautschutzplan,
    Handschuhe, Feuchtarbeit. Die branchentypische Pflicht.
13. Jugendarbeitsschutz (bei unter 18), Mutterschutz
14. Zuständige Berufsgenossenschaft: **BGW**

> **Klar gesagt:** Ich kann diese Vorlagen sauber und vollständig
> ausformulieren, mit den Pflichtangaben und ohne die oben genannten Fehler.
> Bevor sie in einem Produkt an fremde Salons ausgeliefert werden, gehören
> sie einmal durch eine Fachanwältin für Arbeitsrecht — nicht weil der
> Entwurf schlecht wäre, sondern weil ein Fehler dann nicht einen Vertrag
> betrifft, sondern alle. Der Aufwand dafür ist einmalig und klein gegen das
> Risiko. Im System werden die Vorlagen versioniert, damit jederzeit
> nachvollziehbar ist, welche Fassung wer angenommen hat.

---

## 6. Vorschlag zur Reihenfolge

1. **Personalakte und Wizard** — Nina legt an, Mitarbeiterin macht den Rest
   selbst, alles gescannt. Danach ist der Papierkram weg.
2. **Zeiterfassung aus dem Kalender** — der Teil, den sonst niemand so bauen
   kann, weil niemand sonst die Termine hat.
3. **Verträge und Belehrungen** — Vorlagen, Annahme mit Protokoll,
   Versionierung.
4. **Dashboard, Fristen, Monatsübergabe** — der strukturierte Export.
5. **Danach entscheiden**: selbst abrechnen (Stufe 2) oder erst einmal
   sauber übergeben.

Punkt 1 bis 4 sind ohne Zertifizierung und ohne fremde Zulassung baubar. Sie
nehmen Nina den größten Teil der Arbeit ab — und sie sind die Voraussetzung
für alles, was danach kommt.

---

## Quellen

- [BMAS: Mindestlohn steigt zum 1. Januar 2026 auf 13,90 Euro](https://www.bmas.de/DE/Service/Presse/Pressemitteilungen/2025/mindestlohn-steigt-zum-ersten-januar-2026.html)
- [DGB: Gesetzlicher Mindestlohn 2026](https://www.dgb.de/service/ratgeber/mindestlohn/)
- [§ 95b SGB IV / DEÜV: systemgeprüfte Programme, GKV-Zertifikat (ITSG)](https://www.hamburger-software.de/blog/gkv-zertifikat-warum-arbeitgeber-auf-itsg-gepruefte-lohnsoftware-setzen-sollten/)
- [SV-Meldeportal der Sozialversicherungsträger](https://info.sv-meldeportal.de/)
- [Techniker Krankenkasse: Welches Entgeltabrechnungsprogramm ist für DEÜV-Meldungen geeignet?](https://www.tk.de/firmenkunden/versicherung/meldeverfahren-faq/maschinelle-datenuebermittlung/entgeltabrechnungsprogramme-pruefen-2030474)
- [ELSTER: Informationen für Entwickler (ERiC)](https://www.elster.de/eportal/infoseite/entwickler)
- [ELSTER: Lohnsteuer-Anmeldung](https://www.elster.de/eportal/formulare-leistungen/alleformulare/lsta)
- [Menold Bezler: Digitale Arbeitsverträge ab 2025 – mit Ausnahmen](https://www.menoldbezler.de/blog/digitale-arbeitsvertraege-ab-2025-mit-ausnahmen)
- [Haufe: Änderungen im Nachweisgesetz – digitaler Arbeitsvertrag](https://www.haufe.de/personal/arbeitsrecht/weitreichende-aenderungen-am-nachweisgesetz_76_569140.html)
- [IHK Rhein-Neckar: Arbeitszeiterfassung 2026 – Pflicht, Gesetzesstand & Urteile](https://www.ihk.de/rhein-neckar/recht/arbeitsrecht/arbeitszeiterfassung-5631422)
- [§ 4a AufenthG – Zugang zur Erwerbstätigkeit](https://www.gesetze-im-internet.de/aufenthg_2004/__4a.html)
- [Pusch Wahlig: Die neue Mitteilungspflicht im Ausländerbeschäftigungsrecht](https://pwwl.de/die-neue-mitteilungspflicht-im-auslaenderbeschaeftigungsrecht/)
