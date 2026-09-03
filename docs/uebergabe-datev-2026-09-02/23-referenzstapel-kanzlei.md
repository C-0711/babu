# Der Referenzstapel der Kanzlei — was babus Format davon lernt

Aufgenommen am 03.09.2026. Vergleichsstück ist `historie/2026/stapel.csv` aus
Ninas Belegbox: ein Buchungsstapel, den **die Kanzlei selbst** aus DATEV
exportiert hat. Bis dahin hatte babu sein Format aus der DATEV-Dokumentation
gebaut und nie gegen eine echte Datei gehalten. Das ist der Unterschied
zwischen „müsste passen" und „passt".

Der Mandantenname und die Nummern des Betriebs stehen hier bewusst nicht.
Was hier steht, ist Format, nicht Inhalt.

## Die Kopfzeile

    "EXTF";700;21;"Buchungsstapel";12;20260413115454136;;"";"";"";16149;19364;
    20260101;4;20260301;20260331;"von 20260301 bis 20260331";"";1;0;1;"EUR";;
    "";;;"";;;"";""

(im Original eine einzige Zeile, hier nur der Lesbarkeit halber umbrochen)

31 Felder — genau so viele wie babu schreibt. Feld für Feld:

| Feld | Kanzlei | babu vorher | Befund |
|---|---|---|---|
| 1 Kennung | `"EXTF"` | `"EXTF"` | gleich |
| 2 Versionsnummer | `700` | `700` | gleich |
| 3 Formatkategorie | `21` | `21` | gleich (Buchungsstapel) |
| 4 Formatname | `"Buchungsstapel"` | dito | gleich |
| **5 Formatversion** | **`12`** | **`13`** | **abweichend — babu zieht nach** |
| 6 Erzeugt am | `20260413115454136` | dito, 17 Stellen | gleich |
| 11 Berater | `16149` | `0` bzw. aus der Einstellung | Form bestätigt: nackte Zahl |
| 12 Mandant | `19364` | dito | Form bestätigt |
| 13 Wirtschaftsjahresbeginn | `20260101` | dito | gleich |
| 14 Sachkontenlänge | `4` | `4` | gleich |
| 15/16 von / bis | `20260301` / `20260331` | dito | gleich |
| 17 Bezeichnung | `"von 20260301 bis 20260331"` | `"babu 2026-03"` | frei wählbar, bleibt |
| 19 Diktatkürzel … 21 | `1;0;1` | `1;0;1` bzw. `0` | Feld 21 ist die Festschreibung |
| 22 Währung | `"EUR"` | `"EUR"` | gleich |
| **27 Kontenrahmen (SKR)** | **leer (`""`)** | **leer** | **gleich — bleibt leer** |

Zwei Dinge sind damit entschieden:

**Formatversion 12, nicht 13.** babu lief der Software voraus. Ältere
DATEV-Fassungen nehmen eine höhere Versionsnummer zwar an, behandeln die Datei
aber als neueres Format — und melden dann Spalten, die sie nicht erwarten. Der
Kanzlei-Export ist die verlässlichere Auskunft darüber, womit dort gearbeitet
wird, als jede Dokumentation.

**Feld 27 bleibt leer.** Die Versuchung war, dort `SKR04` einzutragen — babu
weiß ja, welchen Rahmen der Betrieb fährt. Die Referenz lässt das Feld leer,
und das ist auch richtig: der Kontenrahmen ist eine Einstellung des Mandanten
in der Kanzlei-Software, nicht eine Behauptung der abgebenden Seite.

## Die Spaltenzeile

**124 Spalten.** babu schrieb 120. Die ersten 120 sind Wort für Wort und
Stelle für Stelle dieselben — kein Versatz, keine Umbenennung, keine
Lücke. Dazu kommen am Ende vier:

    … ;Steuersatz;Land;Abrechnungsreferenz;BVV-Position;
      EU-Land u. UStID (Ursprung);EU-Steuersatz (Ursprung)

babu füllt sie nicht; für einen Salon gibt es dort nichts einzutragen. Sie
stehen trotzdem in der Zeile, weil eine kürzere Spaltenzeile beim Import als
Abweichung auffällt und dann jedes Mal eine Rückfrage erzeugt.

Der Test `test_spalten_entsprechen_der_kanzlei_referenz` friert die ganze
Zeile ein. Wer künftig eine Spalte einschiebt, verschiebt sonst stillschweigend
jede Zahl in jeder Datei — die Buchungszeile zählt ihre Felder an dieser Liste
ab.

## Der Zeichensatz

Die Referenzdatei ist **UTF-8 mit vorangestelltem Erkennungszeichen**. babu
schreibt Windows-1252, und das bleibt der Standard: es ist der Zeichensatz,
den jede DATEV-Fassung annimmt, und der Bestand an babu-Dateien ist so
geschrieben.

Neu ist der Schalter. `als_bytes(text, utf8_bom=True)` und an der Seite
`?zeichensatz=utf8` liefern dieselbe Datei in UTF-8. Das ist kein Schönheits-
thema: in Windows-1252 fehlen Buchstaben, die in Lieferantennamen vorkommen
(türkische, polnische), und babu machte daraus bisher stumm ein Fragezeichen.
Wer den Namen braucht, wie er geschrieben wird, nimmt UTF-8.

## Eine Buchungszeile aus der Referenz

    10;"S";"EUR";;;;1461;4830;"";0203;"375";"";;"Trinkgeldeinnahme";…

Drei Beobachtungen, alle mit Folgen für babu:

1. **Belegfeld 1 ist gefüllt** (`"375"`) — die Kanzlei vergibt fortlaufende
   eigene Belegnummern. babu schreibt dort seine eigene Belegnummer. Beides ist
   richtig; der Abgleich der DATEV-Seite weiß das bereits und vergleicht in
   drei Wellen, davon eine ohne Belegfeld.
2. **Der BU-Schlüssel ist leer**, obwohl es eine Einnahme mit Steuer ist —
   das Konto `4830` rechnet die Steuer selbst. Genau das macht babu seit dem
   02.09. auch (Automatikkonten tragen keinen Schlüssel).
3. **Die Beleginfo-Paare werden genutzt.** babu lässt sie leer. Das ist
   vorerst kein Handlungsbedarf, aber es ist der Ort, an dem später einmal
   die Herkunft eines Belegs stehen könnte.

## Was daraus wurde

- `extf.SPALTEN`: 124 Spalten, die vier neuen am Ende.
- `extf.stapel`: Kopf-Feld 5 auf `12`, Feld 27 bleibt leer.
- `extf.als_bytes(text, utf8_bom=False)`: Windows-1252 wie bisher, UTF-8 auf
  Wunsch.
- DATEV-Seite: `stapel.csv?zeichensatz=utf8` und `konten.csv?zeichensatz=utf8`.
- `historie.kopf_lesen` gibt zusätzlich `felder_roh`, `spalten` und
  `formatversion` heraus — ungedeutet, damit ein Vergleich überhaupt möglich ist.
- Beim Hereinlesen meldet die Seite eine abweichende Spaltenzeile (Anzahl und
  erste Abweichung). Gelesen wird trotzdem: die Spalten werden über ihren
  Namen gesucht, nicht über ihre Stelle.

## Was offen bleibt

- Die Bezeichnung im Kopf (Feld 17) heißt bei babu `"babu 2026-03"`, bei der
  Kanzlei `"von 20260301 bis 20260331"`. Frei wählbar, kein Streitpunkt —
  babus Fassung sagt mehr.
- Die Beleginfo-Paare sind ungenutzt.
- Der letzte Beweis bleibt ein Import in einer echten DATEV-Instanz. Alles
  hier ist an einer exportierten Datei gemessen, nicht an einem gelaufenen
  Import.
