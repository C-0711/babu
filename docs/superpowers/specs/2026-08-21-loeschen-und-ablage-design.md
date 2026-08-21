# Löschen — und die Ablage wird wieder Übersicht

Stand 21.08.2026. Zwei Dinge, die zusammengehören: man muss einen falschen
Beleg wieder loswerden können, und die Ablage soll zeigen, was da ist, statt
zum vierten Upload-Ort zu werden.

## Warum

Heute kann man in babu nichts löschen. Ein doppelt fotografierter Beleg, ein
Foto vom Küchentisch statt vom Kassenbon, ein Brief, der versehentlich zweimal
drin liegt — alles bleibt für immer stehen. Der Assistent behauptet sogar
bereits, man könne „falsche Belege löschen" (`babu_web.py`, System-Text des
Chats): babu verspricht etwas, das es nicht kann.

Gleichzeitig ist die Ablage zum Sammelbecken für Upload-Knöpfe geworden.
„Kontoauszug ablegen" gibt es dort **und** unter Konto **und** unter Post,
„Brief vom Amt ablegen" dort **und** unter Post. Vier Wege für dieselbe Sache
sind kein Komfort, sondern die Frage „habe ich das jetzt schon hochgeladen?".

## A — Die Ablage zeigt, sie sammelt nicht

Aus der Ablage verschwinden „Kontoauszug ablegen" und „Brief vom Amt ablegen".
Beide bleiben dort, wo sie hingehören: der Auszug unter Konto (und in der Post,
wo die Kanzlei ihn erwartet), der Brief unter Post.

„Vertrag ablegen" bleibt in der Ablage — es ist der einzige Ort dafür, und
Verträge sind das, was die Ablage ohnehin zeigt (Dauerkosten).

## B — Löschen

### Was beim Löschen passiert

Gelöscht wird mit einem eigenen Commit, der die Datei entfernt. Der aktuelle
Stand zeigt den Beleg danach nicht mehr; die Historie behält ihn. Das ist die
einzige Form, die zu Beweismaterial passt: nichts verschwindet spurlos, aber
was falsch ist, steht nicht mehr in der Buchhaltung.

Ein Beleg wird nie allein gelöscht. Seine Beiakten gehen mit — die
Zweitprüfung, nachgetragene Angaben, die Bewirtungsantwort, eine
Kanzlei-Korrektur. Sonst bliebe eine Prüfung ohne Beleg zurück.

### Was nicht gelöscht werden kann

| Bleibt | Warum |
|---|---|
| Belege im Status „exportiert" | liegen im Stapel bei der Kanzlei |
| Kassenbuch-Blätter | aufbewahrungspflichtig |
| Kontoauszüge | aufbewahrungspflichtig |
| Buchungsstapel (EXTF) | der Nachweis der Übergabe |
| Jahresabschluss-Unterlagen | aufbewahrungspflichtig |

Die API weist das ab; die Oberfläche zeigt dort erst gar keinen Knopf. Ein
Knopf, der beim Drücken „geht nicht" sagt, ist eine Falle.

### Wer darf

Die Inhaberin und die Kanzlei. Eine Mitarbeiterin mit `darf_belege` darf
Belege einreichen, aber nicht löschen — wegwerfen ist mehr als einreichen, und
die Rechte des Teams vergibt die Inhaberin bewusst.

### Routen

- `POST /api/beleg/{stamm}/loeschen` — Beleg samt Beiakten.
  409, wenn der Beleg exportiert ist. 403 für `mitarbeit`.
- `POST /api/dokument-loeschen` mit `{"pfad": "dokumente/…"}` — Dokument samt
  Sidecars (`.meta.json`, `.erklaerung.json`, `.vertrag.json`).
  400 für alles außerhalb von `dokumente/`.

Beide hinter `_box_wache`, beide über `boxschreiber.loeschen()`.

### boxschreiber.loeschen()

Neue Funktion neben `schreiben()`, mit demselben Schloss, demselben
fetch/reset und demselben einen Push-Retry. Beide teilen sich den inneren
Ablauf, damit es nicht zwei Wahrheiten über den Schreibpfad gibt. Pfade, die
es nicht mehr gibt, sind kein Fehler — zweimal Löschen ist harmlos.

### Wortlaut (Sprachregel: keine Technik, keine Systemnamen)

- Knopf: **Beleg löschen** · **Löschen**
- Rückfrage: *„Diesen Beleg löschen? Er verschwindet aus deiner Ablage —
  nachvollziehbar bleibt, dass es ihn gab."*
- Exportiert: *„Dieser Beleg liegt schon im Stapel bei deiner Kanzlei. Zum
  Löschen sprich kurz mit ihr."*
- Mitarbeiterin: *„Belege löschen darf die Inhaberin."*
- Aufbewahrungspflicht: *„Kassenbuch, Kontoauszüge und Stapel musst du
  aufbewahren — die bleiben."*

## C — Nebenbei: tote Links in der Ablage

Alle Zeilen der Ablage zeigen auf `/api/dokument/<pfad>`. Diese Route nimmt
aber nur Pfade unter `dokumente/` an — Kassenbuch, Kontoauszüge und Stapel
antworten mit „ungültiger Pfad". Diese Zeilen sind heute nicht anklickbar,
ohne es zu sagen. Die Route bekommt die übrigen Ablage-Ordner dazu (lesend),
damit ein Eintrag, der dasteht, sich auch öffnen lässt.

## Tests

`tests/test_loeschen.py`:

- Beleg löschen — weg aus der Liste, weg aus dem Stand, Commit auf den Namen
  der Nutzerin; die Beiakten sind mit weg.
- Exportierter Beleg — 409, und er ist danach noch da.
- Mitarbeiterin — 403, und er ist danach noch da.
- Fremdes Konto — 403 (die Grenze aus `_box_wache` gilt auch hier).
- Dokument löschen — weg samt Sidecars.
- Kassenbuch, Kontoauszug, Stapel — nicht löschbar.
- Zweimal löschen — beim zweiten Mal 404, kein Absturz.
- `boxschreiber.loeschen()` unter gleichzeitigen Schreibern.

## Nicht dabei

- Kein Papierkorb, kein Wiederherstellen. Wer sich vertut, lädt neu hoch; der
  alte Stand steht in der Historie.
- Kein Sammel-Löschen. Löschen ist eine einzelne, bewusste Handlung.
- Kein Löschen aufbewahrungspflichtiger Unterlagen, auch nicht „mit Warnung".
