#!/usr/bin/env python3
"""Die Werkstatt-Seite (mybabu.io/werkstatt) als Kopie der Friseur-Startseite
bauen — Kopie von `werbung/barber/seite_bauen.py`, angepasst an Kfz-Werkstätten.

Kopierprinzip: `server/babu-web/index.html` bleibt unangetastet; hier steht,
was auf der Werkstatt-Seite ANDERS ist, und daraus entsteht
`server/babu-web/werkstatt.html`. Jede Ersetzung wird gezählt — ändert sich
die Friseur-Seite, bricht der Bau laut ab.

Anders als bei Friseur, mit Absicht:
- Ganz oben der gemeinsame Welten-Hero (werbung/welten.py): Mario breit mit
  Überschrift, Babs und Moe schauen herein und führen hinüber.
- Mario und seine Werkstatt in allen Szenenbildern (/bilder/ws-*.jpg).
- Kein Buhl, das Steuer-Backend bleibt. App per TestFlight auf Einladung.
- Impressum, Datenschutz, AGB als echte Links; kein Profi-Upload, keine
  Spot-Serie mit Babs und Olaf.
- Werkstatt-Fragen mit Fundstelle aus dem amtlichen Wortlaut: Meisterpflicht
  (HwO Anlage A Nr. 20), Werkstattpfandrecht (§ 647 BGB), Gewährleistung
  (§ 634a BGB), Gebrauchtwagen (§ 25a, § 14a Abs. 6 UStG), Altöl (§ 8 AltölV).

    python3 werbung/werkstatt/seite_bauen.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUELLE = REPO / "server" / "babu-web" / "index.html"
ZIEL = REPO / "server" / "babu-web" / "werkstatt.html"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import welten  # noqa: E402

t = QUELLE.read_text(encoding="utf-8")


def ers(alt: str, neu: str, n: int = 1) -> None:
    """Ersetzt `alt` (Leerraum egal) genau n-mal durch `neu`."""
    global t
    muster = r"\s+".join(re.escape(w) for w in alt.split())
    t, zahl = re.subn(muster, lambda _m: neu, t)
    if zahl != n:
        sys.exit(f"Ersetzung passt nicht ({zahl} statt {n}): {alt[:80]!r}")


def weg(anfang: str, ende: str) -> None:
    global t
    a = t.find(anfang)
    b = t.find(ende, a)
    if a < 0 or b < 0:
        sys.exit(f"Abschnitt nicht gefunden: {anfang[:60]!r}")
    t = t[:a] + t[b + len(ende):]


def bild_ersetzen(alt_text: str, neu_src: str) -> None:
    """Ein eingebettetes Friseur-Bild (data-URI) durch das Werkstatt-Bild ersetzen."""
    global t
    muster = r'src="data:[^"]+"(\s+alt="' + re.escape(alt_text) + '")'
    t, zahl = re.subn(muster, lambda m: f'src="{neu_src}" loading="lazy" width="692" height="859"{m.group(1)}', t)
    if zahl != 1:
        sys.exit(f"Bild nicht gefunden: {alt_text[:60]!r}")


HAKEN = ('<span class="hakenkreis"><svg viewBox="0 0 16 16" fill="none"><path d="M3.5 8.5l3 3 6-7" '
         'stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg></span>')

# ── Kopf, Farben, Welten-Hero ───────────────────────────────────────────────
ers("<title>babu — dein Papierkram macht sich von selbst</title>",
    "<title>babu Werkstatt — dein Papierkram macht sich von selbst</title>")
ers("mit oder ohne eigenes Steuerbüro. Gemacht für Friseursalons.",
    "mit oder ohne eigenes Steuerbüro. Gemacht für Kfz-Werkstätten.")
ers("--gc-accent:#857b61; --gc-accent-hover:#736950; --gc-accent-subtle:#f0ebe3;",
    "--gc-accent:#3d5a76; --gc-accent-hover:#2c4459; --gc-accent-subtle:#e7edf3;")
ers("--gc-gold:#c9b98d;", "--gc-gold:#c9953c;")
ers("</style>", """.faq-quelle{display:block;font-size:12.5px;color:var(--gc-muted);margin-top:8px}
</style>""")
t = welten.einsetzen(t, "werkstatt")

# ── 2 · Drei Schritte ───────────────────────────────────────────────────────
ers("Zwischen zwei Terminen, direkt an der Kasse, egal wo.",
    "Zwischen zwei Aufträgen, direkt an der Werkbank, egal wo.")

# ── So fängst du an ─────────────────────────────────────────────────────────
ers('src="/bilder/start-1-laden.jpg"', 'src="/bilder/ws-start-1-laden.jpg"')
ers('alt="Friseurin sitzt entspannt auf der Bank in ihrem Salon und richtet auf dem Telefon etwas ein"',
    'alt="Mario sitzt morgens auf einem Reifenstapel in seiner Werkstatt und richtet auf dem Telefon etwas ein"')
ers("<b>App laden.</b> Aus dem App Store, wie jede andere App auch. Dauert so lange wie ein Kaffee.",
    "<b>App laden.</b> Per Einladung aufs iPhone: Apple schickt dir eine Mail, du tippst auf „Testen“. Dauert so lange wie ein Kaffee.")
ers('src="/bilder/start-2-anmelden.jpg"', 'src="/bilder/ws-start-2-anmelden.jpg"')
ers('alt="Friseurin steht am Empfangstresen und tippt mit dem Daumen kurz etwas in ihr Telefon"',
    'alt="Mario steht an der Theke und tippt mit dem Daumen kurz etwas in sein Telefon"')
ers('src="/bilder/start-3-foto.jpg"', 'src="/bilder/ws-start-3-foto.jpg"')
ers('alt="Hände halten ein Telefon über einen Kassenbon auf dem Tresen und fotografieren ihn von oben"',
    'alt="Mario steht in seiner Werkstatt und fotografiert mit dem Telefon einen Beleg"')
ers('src="/bilder/start-4-fertig.jpg"', 'src="/bilder/ws-start-4-fertig.jpg"')
ers('alt="Friseurin lehnt am Feierabend entspannt an der Wand ihres leeren Salons, das Telefon liegt weggelegt auf ihrem Knie"',
    'alt="Mario steht nach Feierabend entspannt in seiner aufgeräumten Werkstatt, das Telefon liegt auf der Werkbank"')

# ── Und das kann babu dann alles ────────────────────────────────────────────
ers("Alles, was zwischen der ersten Kundin und dem Feierabend anfällt",
    "Alles, was zwischen dem ersten Auftrag und dem Feierabend anfällt")
ers('src="/bilder/kann-termine.jpg"', 'src="/bilder/ws-kann-termine.jpg"')
ers('alt="Friseurin schaut zwischen zwei Kundinnen kurz auf ihr Telefon, in der anderen Hand eine Bürste"',
    'alt="Mario schaut zwischen zwei Aufträgen kurz auf sein Telefon, in der anderen Hand einen Drehmomentschlüssel"')
ers("<b>Termine.</b> Schreib hin, wie du es sagen würdest: „Frau Meier Donnerstag Farbe“. babu sucht die freie Lücke.",
    "<b>Termine.</b> Schreib hin, wie du es sagen würdest: „Maier Donnerstag Inspektion und Bremsen“. babu sucht die freie Lücke.")
ers('src="/bilder/kann-nachricht.jpg"', 'src="/bilder/ws-kann-nachricht.jpg"')
ers('alt="Friseurin sitzt auf der Lehne der Wartebank und liest schmunzelnd eine Nachricht auf dem Telefon"',
    'alt="Mario sitzt auf der Kante der Werkbank und liest schmunzelnd eine Nachricht auf dem Telefon"')
ers("Deine Kundin schreibt, babu antwortet mit freien Zeiten und trägt den Termin ein.",
    "Dein Kunde schreibt, babu antwortet mit freien Zeiten und trägt den Termin ein.")
ers('src="/bilder/kann-belege.jpg"', 'src="/bilder/ws-kann-belege.jpg"')
ers('alt="Umgekippter Schuhkarton auf dem Tresen, aus dem ein Haufen Kassenbons quillt, daneben ein Telefon"',
    'alt="Umgekippter Schuhkarton auf der Theke, aus dem ein Haufen Belege quillt, Mario greift mit dem Telefon hinein"')
ers("<b>Der Schuhkarton.</b> Bon, Vertrag, Brief vom Amt, Kontoauszug",
    "<b>Der Schuhkarton.</b> Teilerechnung, Leasingvertrag, Brief vom Amt, Kontoauszug")
ers('src="/bilder/kann-kundin.jpg"', 'src="/bilder/ws-kann-kunde.jpg"')
ers('alt="Friseurin rührt Farbe in einer Schale an, das Telefon steht aufgestellt vor ihr"',
    'alt="Mario zeigt einem Kunden unter dem Auto auf der Hebebühne eine abgefahrene Bremsscheibe, das Telefon steht auf dem Werkzeugwagen"')
ers("<b>Deine Kundinnen.</b> Welche Formel beim letzten Mal stimmte, was sie nicht verträgt. Der Karteikasten hinterm Spiegel, nur auffindbar.",
    "<b>Deine Stammkunden.</b> Welches Auto, wann der letzte Ölwechsel war, was beim letzten Mal schon auffiel. Die Karteikarte an der Pinnwand, nur auffindbar.")
ers('src="/bilder/kann-rechnung.jpg"', 'src="/bilder/ws-kann-rechnung.jpg"')
ers('alt="Friseurin lehnt am Tresen und tippt konzentriert etwas in ihr Telefon, im Hintergrund zieht eine Kundin ihren Mantel an"',
    'alt="Mario lehnt an der Theke und tippt konzentriert etwas in sein Telefon, im Hintergrund holt ein Kunde seinen Autoschlüssel"')
ers("<b>Rechnungen.</b> Stuhlmiete, Hochzeit, Firmenkunde.",
    "<b>Rechnungen.</b> Inspektion, Reifenwechsel, Firmenflotte — Teile und Arbeitszeit getrennt.")
ers('src="/bilder/kann-kasse.jpg"', 'src="/bilder/ws-kann-kasse.jpg"')
ers('alt="Friseurin zählt abends bei Lampenlicht hinter dem Tresen Scheine und Münzen, das Telefon liegt daneben"',
    'alt="Mario zählt abends unter der Arbeitslampe an der Theke Scheine und Münzen, das Telefon liegt daneben"')
ers("<b>Abends kurz zählen.</b> Eine Zahl nach der anderen,",
    "<b>Abends kurz zählen.</b> Barzahler am Abholtag? Eine Zahl nach der anderen,")

# ── Salon-Check → Werkstatt-Check ───────────────────────────────────────────
ers('<div class="lbl">Neu · Der Salon-Check</div>', '<div class="lbl">Neu · Der Werkstatt-Check</div>')
ers("wo dein Salon steht. Mit Ampeln statt Steuer-Deutsch.", "wo deine Werkstatt steht. Mit Ampeln statt Steuer-Deutsch.")
ers('alt="Friseurin mit einem großen Stapel Ordner und Belegen vom letzten Jahr im Arm"',
    'alt="Mario trägt lachend einen riesigen Stapel Ordner und Belege vom letzten Jahr im Arm"')
bild_ersetzen("Mario trägt lachend einen riesigen Stapel Ordner und Belege vom letzten Jahr im Arm", "/bilder/ws-papierstapel.jpg")
ers("<h4>Dein Salon-Check</h4>", "<h4>Dein Werkstatt-Check</h4>")
ers("<span>Material</span>", "<span>Teile und Material</span>")
ers("✓ Fertig — dein Salon-Check steht.", "✓ Fertig — dein Werkstatt-Check steht.")
ers(">Salon-Check starten</a>", ">Werkstatt-Check starten</a>")

# ── Kostenvergleich: ohne den Babs-und-Olaf-Spot ────────────────────────────
weg('<div class="karte" style="margin-top:18px;max-width:340px', "</p>\n  </div>")

# ── Pakete ──────────────────────────────────────────────────────────────────
ers("<h2>Ein Preis, der zu deinem Salon passt.</h2>", "<h2>Ein Preis, der zu deiner Werkstatt passt.</h2>")
ers("Je nachdem, wie dein Salon aufgestellt ist,", "Je nachdem, wie deine Werkstatt aufgestellt ist,")
ers("<li>Kleinunternehmerin (§ 19 UStG) — keine Umsatzsteuer</li>", "<li>Kleinunternehmer (§ 19 UStG) — keine Umsatzsteuer</li>")
ers("<li>Belege, Kassenbuch, Salon-Check — alles drin</li>", "<li>Belege, Kassenbuch, Werkstatt-Check — alles drin</li>")
ers('<h3 class="gruen">Salon</h3>', '<h3 class="gruen">Werkstatt</h3>')
ers("<h3>Salon Plus</h3>", "<h3>Werkstatt Plus</h3>")
ers("<li>Alles aus Salon — plus getrennte Auswertungen</li>", "<li>Alles aus Werkstatt — plus getrennte Auswertungen</li>")
ers("""Dann wird es günstiger — sag uns kurz Bescheid.
  Machst du umsatzsteuerfreie medizinische Behandlungen (z. B. podologische
  Fußpflege, § 4 Nr. 14 UStG)? babu stellt das richtig ein.</p>""",
    "Dann wird es günstiger — sag uns kurz Bescheid.</p>")
ers("Sieben kurze Fragen — dann weißt du es.", "Sechs kurze Fragen — dann weißt du es.")
ers("""    {k:'medizinisch', f:'Machst du medizinische Behandlungen ohne Umsatzsteuer — zum Beispiel podologische Fußpflege?', a:['Ja','Nein']},
""", "")
ers("{k:'klein', f:'Bist du Kleinunternehmerin?", "{k:'klein', f:'Bist du Kleinunternehmer?")
ers("{k:'filialen', f:'Hat dein Salon mehr als einen Standort?'", "{k:'filialen', f:'Hat deine Werkstatt mehr als einen Standort?'")
ers("var paket=plus?['Salon Plus','149 €']:(solo?['Solo','39 €']:['Salon','79 €']);",
    "var paket=plus?['Werkstatt Plus','149 €']:(solo?['Solo','39 €']:['Werkstatt','79 €']);")
ers("""    if(antworten.medizinisch==='Ja')
      extra.push('Deine medizinischen Behandlungen bleiben ohne Umsatzsteuer — babu stellt das richtig ein.');
""", "")
ers("der Salon-Check liest es einfach aus deinen Unterlagen heraus.", "der Werkstatt-Check liest es einfach aus deinen Unterlagen heraus.")

# ── Spot-Serie (Babs und Olaf) entfällt ─────────────────────────────────────
weg("<!-- ── 4b2 · Serie: Kostenwahrheit", "</section>")

# ── Telefon kann alles ──────────────────────────────────────────────────────
ers("Dein Telefon verbindet dich mit allem, was zu deinem Salon gehört —",
    "Dein Telefon verbindet dich mit allem, was zu deiner Werkstatt gehört —")
ers('alt="Friseurin fotografiert am Empfangstresen einen Beleg mit dem Telefon, im Hintergrund wartet eine Kundin mit Folien"',
    'alt="Mario fotografiert an der Theke einen Beleg mit dem Telefon, im Hintergrund warten zwei Kunden"')
bild_ersetzen("Mario fotografiert an der Theke einen Beleg mit dem Telefon, im Hintergrund warten zwei Kunden", "/bilder/ws-scanner.jpg")
ers("sicher abgelegt. Mitten zwischen zwei Terminen.</p>", "sicher abgelegt. Mitten zwischen zwei Aufträgen.</p>")
ers('alt="Friseurin lehnt nach Feierabend entspannt am Tresen und schaut zufrieden auf ihr Telefon, daneben ein Kaffee"',
    'alt="Mario lehnt nach Feierabend entspannt an der Werkbank und schaut zufrieden auf sein Telefon, daneben ein Tässchen Kaffee"')
bild_ersetzen("Mario lehnt nach Feierabend entspannt an der Werkbank und schaut zufrieden auf sein Telefon, daneben ein Tässchen Kaffee",
              "/bilder/ws-helfer.jpg")
ers('alt="Friseurin fotografiert amüsiert einen Brief vom Amt, der vor ihr auf dem Tisch liegt"',
    'alt="Mario fotografiert amüsiert einen Brief vom Amt, der vor ihm auf der Theke liegt"')
bild_ersetzen("Mario fotografiert amüsiert einen Brief vom Amt, der vor ihm auf der Theke liegt", "/bilder/ws-berater.jpg")

# ── Hosentasche ─────────────────────────────────────────────────────────────
ers('<div class="klein" style="margin-bottom:6px">3 Termine, 3 Std 45 min gebucht</div>',
    '<div class="klein" style="margin-bottom:6px">3 Aufträge, beide Bühnen belegt</div>')
ers('<div class="zeile"><b>11:00</b><span>Frau Holder</span><span class="pille">Schnitt</span></div>',
    '<div class="zeile"><b>08:00</b><span>Schmid</span><span class="pille">Inspektion</span></div>')
ers('<div class="zeile"><b>13:30</b><span>Frau Sommer</span><span class="pille">Farbe</span></div>',
    '<div class="zeile"><b>11:00</b><span>Yılmaz</span><span class="pille">Bremsen</span></div>')
ers('<div class="zeile"><b>16:00</b><span>Herr Betz</span><span class="pille">Schnitt</span></div>',
    '<div class="zeile"><b>15:30</b><span>Petrović</span><span class="pille">Reifen</span></div>')
ers("„Frau Meier Donnerstag Farbe\" — babu sucht die Lücke.", "„Maier Donnerstag Ölwechsel\" — babu sucht die Lücke.")
ers('<div class="stark">Offen · 535,50 €</div>', '<div class="stark">Offen · 486,00 €</div>')
ers('<div class="zeile"><span>Jana Allgaier</span><b>535,50 €</b></div>',
    '<div class="zeile"><span>Kowalski GmbH</span><b>486,00 €</b></div>')
ers('<div class="klein">Nr. 2026-0001 · Stuhlmiete</div>', '<div class="klein">Nr. 2026-0001 · Inspektion Firmenwagen</div>')
ers("<span>Jana hat am 02.09. bezahlt</span>", "<span>Kowalski hat am 02.09. bezahlt</span>")
ers('src="/bilder/termine-morgens.jpg"', 'src="/bilder/ws-termine-morgens.jpg"')
ers('alt="Friseurin steht morgens vor Ladenöffnung am Tresen, Kaffee in der einen Hand, Telefon in der anderen, und sieht entspannt ihre Termine durch"',
    'alt="Mario steht morgens vor dem Aufmachen an der Theke, ein Tässchen Kaffee in der einen Hand, das Telefon in der anderen"')
ers("wie voll ist der Tag. Bevor die erste Kundin da ist.</p>", "wie voll ist der Tag. Bevor der erste Kunde da ist.</p>")
ers('src="/bilder/rechnung-tresen.jpg"', 'src="/bilder/ws-rechnung-tresen.jpg"')
ers('alt="Friseurin reicht einer lächelnden Kundin ein Blatt Papier über den Empfangstresen, daneben ein Kartenlesegerät"',
    'alt="Mario reicht einer lächelnden Kundin die Rechnung und den Autoschlüssel über die Theke"')
ers('src="/bilder/feierabend-zahlen.jpg"', 'src="/bilder/ws-feierabend-zahlen.jpg"')
ers('alt="Friseurin sitzt nach Feierabend entspannt im Friseurstuhl im aufgeräumten Salon und schaut auf ihr Telefon"',
    'alt="Mario sitzt nach Feierabend entspannt auf dem Rollhocker in der aufgeräumten Werkstatt und schaut auf sein Telefon"')
ers("""Alles andere hat babu schon gemacht — zwischen zwei
  Terminen, während du geschnitten hast.</p>""", """Alles andere hat babu schon gemacht — zwischen zwei
  Aufträgen, während du geschraubt hast. Oder wie Mario sagt: <em>Schaffe, schaffe — aber net
  am Schreibtisch.</em></p>""")

# ── Für deine Werkstatt gebaut ──────────────────────────────────────────────
ers('<div class="lbl">Für deinen Salon gebaut</div>', '<div class="lbl">Für deine Werkstatt gebaut</div>')
ers("<strong>Farbe, Bedarf, Handtücher</strong> — Einkäufe werden automatisch richtig einsortiert.",
    "<strong>Ersatzteile, Reifen, Öl, Werkzeug</strong> — Einkäufe werden automatisch richtig einsortiert.")
ers("<strong>Essen mit der Vertreterin?</strong> babu fragt kurz nach, mit wem du warst",
    "<strong>Essen mit dem Teilehändler?</strong> babu fragt kurz nach, mit wem du warst")
ers("""      <span><strong>Kontoauszug abgeben</strong> — babu prüft, ob zu jeder Abbuchung ein Beleg da ist. Fehlt einer, sagt es dir welcher.</span></li>
  </ul>""", f"""      <span><strong>Kontoauszug abgeben</strong> — babu prüft, ob zu jeder Abbuchung ein Beleg da ist. Fehlt einer, sagt es dir welcher.</span></li>
    <li>{HAKEN}
      <span><strong>Werkstattpfandrecht, Gewährleistung, Altöl, Hebebühnen-Prüfung?</strong> Frag babu — der Chat kennt das ganze Bundesrecht im Wortlaut, vom BGB bis zur Betriebssicherheitsverordnung, und nennt dir die Stelle.</span></li>
    <li>{HAKEN}
      <span><strong>Kassen-Nachschau</strong> — das Finanzamt darf unangemeldet kommen (§ 146b AO). Dein Kassenbuch in babu ist lückenlos, jede Änderung bleibt sichtbar.</span></li>
  </ul>""")

# ── Wechsel: ohne Buhl, das Steuer-Backend bleibt ───────────────────────────
ers("""Abschluss über babu. Dahinter arbeitet <strong>Buhl</strong> — einer der
      größten Steuer-Software-Anbieter Deutschlands. Dein Kram ist in
      Profi-Händen.""", """Abschluss über babu. Dahinter arbeitet ein Steuer-Backend. Dein Kram ist in
      Profi-Händen.""")

# ── App laden: TestFlight ───────────────────────────────────────────────────
ers("fertig. In der Testphase läuft die App auf freigeschalteten iPhones.</p>",
    "fertig. In der Testphase kommt die App per TestFlight auf Einladung — Apples offizieller Weg für Test-Apps.</p>")
ers("die wichtigsten Angaben ab — Salon-Name, Steuernummer, Finanzamt.",
    "die wichtigsten Angaben ab — Werkstatt-Name, Steuernummer, Finanzamt.")

# ── FAQ ─────────────────────────────────────────────────────────────────────
ers("""<div class="antwort">Hinter babu arbeitet Buhl — einer der größten
      Steuer-Software-Anbieter Deutschlands (bekannt durch WISO Steuer). babu
      sammelt und ordnet, das Steuer-Backend übernimmt den fachlichen Teil.
      Du hast einen Ansprechpartner: babu.</div>""", """<div class="antwort">babu sammelt und ordnet, das
      Steuer-Backend übernimmt den fachlichen Teil. Du hast einen Ansprechpartner: babu.</div>""")
ers("""  <div style="margin-top:26px">
    <details><summary>Ich bin schon bei einem Steuerberater.""", """  <div style="margin-top:26px">
    <details><summary>Brauche ich einen Meister für meine Werkstatt?</summary>
      <div class="antwort">Kfz-Techniker ist ein zulassungspflichtiges Handwerk (Anlage A Nr. 20
      der Handwerksordnung). Du brauchst die Eintragung in die Handwerksrolle: mit eigenem
      Meisterbrief, mit einem Betriebsleiter, der ihn hat (§ 7 HwO), über die
      Ausübungsberechtigung ohne Meister — Gesellenprüfung und sechs Jahre im Beruf, davon vier
      in leitender Stellung (§ 7b HwO; die Kfz-Techniker sind davon nicht ausgenommen) — oder
      mit einer Ausnahmebewilligung (§ 8 HwO). Welcher Weg passt, entscheidet die
      Handwerkskammer; deren Beratung ist kostenlos.
      <span class="faq-quelle">Quelle: Handwerksordnung §§ 1, 7, 7b, 8 und Anlage A, gesetze-im-internet.de</span></div></details>
    <details><summary>Darf ich das Auto behalten, bis die Rechnung bezahlt ist?</summary>
      <div class="antwort">Grundsätzlich ja: Wer eine Sache ausbessert, hat für seine Forderung ein
      Pfandrecht an der Sache des Auftraggebers, wenn sie dafür in seinen Besitz gekommen ist
      (§ 647 BGB — das Werkstattpfandrecht). Fällig ist dein Geld bei der Abnahme (§ 641 BGB).
      Gehört das Auto nicht dem Auftraggeber — etwa ein Leasing- oder Firmenwagen —, kann es
      anders aussehen; dann frag vorher nach.
      <span class="faq-quelle">Quelle: BGB §§ 641, 647, gesetze-im-internet.de</span></div></details>
    <details><summary>Wie lange hafte ich für eine Reparatur?</summary>
      <div class="antwort">Mängelansprüche bei einem Werk, das in der Wartung oder Veränderung
      einer Sache besteht — also jede Reparatur und jede Inspektion —, verjähren in zwei Jahren
      (§ 634a Abs. 1 Nr. 1 BGB).
      <span class="faq-quelle">Quelle: BGB § 634a, gesetze-im-internet.de</span></div></details>
    <details><summary>Ich verkaufe auch Gebrauchtwagen. Was ist mit der Umsatzsteuer?</summary>
      <div class="antwort">Kaufst du als Händler einen Wagen von privat (ohne Umsatzsteuer) und
      verkaufst ihn weiter, kann die Differenzbesteuerung gelten (§ 25a UStG): versteuert wird
      nur deine Marge, also der Verkaufspreis abzüglich Einkaufspreis. Auf der Rechnung steht
      dann „Gebrauchtgegenstände/Sonderregelung“, und die Umsatzsteuer wird nicht gesondert
      ausgewiesen (§ 14a Abs. 6 UStG).
      <span class="faq-quelle">Quelle: UStG §§ 14a, 25a, gesetze-im-internet.de</span></div></details>
    <details><summary>Muss ich Altöl zurücknehmen?</summary>
      <div class="antwort">Wenn du Motor- oder Getriebeöl an Endverbraucher verkaufst, ja: Du
      brauchst eine Annahmestelle, die gebrauchtes Öl bis zur verkauften Menge kostenlos
      annimmt, und beim Verkauf an Privatleute ein gut lesbares Schild, das darauf hinweist
      (§ 8 AltölV).
      <span class="faq-quelle">Quelle: Altölverordnung § 8, gesetze-im-internet.de</span></div></details>
    <details><summary>Ich bin schon bei einem Steuerberater.""")
ers("""Es kassiert
      nicht und speichert keine einzelnen Verkäufe — darum entsteht auch keine
      TSE-Pflicht.</div>""", """Es kassiert
      nicht und speichert keine einzelnen Verkäufe — darum entsteht auch keine
      TSE-Pflicht. Hast du eine elektronische Kasse, braucht sie eine TSE und muss beim
      Finanzamt gemeldet sein (§ 146a AO).</div>""")

# ── Fußzeile: echte Rechtslinks, kein Profi-Upload ──────────────────────────
weg('<details style="margin-top:34px;border:0">', "</details>")
ers("""  <div style="font-size:12.5px;margin-top:26px">
    <a href="/einkauf" style="color:var(--gc-desc);text-decoration:none">babu Einkauf (bald)</a>
  </div>
""", "")
ers("Impressum &amp; Datenschutz folgen · babu ersetzt keine individuelle Steuerberatung.",
    '<a href="/impressum" style="color:var(--gc-desc)">Impressum</a> · '
    '<a href="/datenschutz" style="color:var(--gc-desc)">Datenschutz</a> · '
    '<a href="/agb" style="color:var(--gc-desc)">AGB</a> · '
    "babu ersetzt keine individuelle Steuerberatung.")
weg("/* ── Profi-Upload (Funktion der bisherigen Startseite, kompakt)", "})();\n")

# ── Chat-Widget ─────────────────────────────────────────────────────────────
ers("'Typisch im Salon: Material und Werkzeug (Scheren, Farben, Föhn), Miete,",
    "'Typisch in der Werkstatt: Ersatzteile, Werkzeug, Diagnosegeräte, Hebebühne (über die Jahre abgeschrieben), Miete,")
ers("Ob das zu dir passt, findet babu im Salon-Check mit heraus.'", "Ob das zu dir passt, findet babu im Werkstatt-Check mit heraus.'")
ers("Kleinunternehmerin (§ 19 UStG) heißt:", "Kleinunternehmer (§ 19 UStG) heißt:")
ers("Solo 39 €, Salon 79 €, Salon Plus 149 € im Monat", "Solo 39 €, Werkstatt 79 €, Werkstatt Plus 149 € im Monat")
ers("In der Testphase läuft die App auf freigeschalteten iPhones; deine Zugangsdaten bekommst du bei der Einrichtung.'",
    "In der Testphase kommt die App per TestFlight auf Einladung; deine Zugangsdaten bekommst du bei der Einrichtung.'")
ers("""    ['buhl|wiso|backend','Hinter babu arbeitet Buhl — einer der größten Steuer-Software-Anbieter Deutschlands (WISO Steuer). babu sammelt und ordnet, das Steuer-Backend macht den fachlichen Teil.']""",
    """    ['backend|wer macht','babu sammelt und ordnet, das Steuer-Backend macht den fachlichen Teil.'],
    ['meister|handwerksrolle|7b','Kfz-Techniker ist Anlage A Nr. 20 der Handwerksordnung. Du brauchst die Eintragung in die Handwerksrolle: mit Meister, mit Betriebsleiter, über die Ausübungsberechtigung nach § 7b (Gesellenprüfung, sechs Jahre, davon vier leitend) oder eine Ausnahme nach § 8. Frag deine Handwerkskammer — die Beratung ist kostenlos.'],
    ['behalten|pfand|nicht bezahlt','Werkstattpfandrecht: Für deine Forderung hast du ein Pfandrecht am Auto des Auftraggebers, das zur Reparatur in deinen Besitz kam (§ 647 BGB). Gehört es jemand anderem (Leasing, Firmenwagen), frag vorher nach.'],
    ['gewährleist|haft|mangel','Mängelansprüche bei Reparatur und Wartung verjähren in zwei Jahren (§ 634a Abs. 1 Nr. 1 BGB).'],
    ['gebraucht|differenz|25a','Gebrauchtwagen von privat angekauft: Differenzbesteuerung nach § 25a UStG — versteuert wird nur die Marge; auf die Rechnung gehört „Gebrauchtgegenstände/Sonderregelung“, ohne gesonderten Steuerausweis (§ 14a Abs. 6 UStG).'],
    ['altöl|altoel|öl zurück','Wer Motor- oder Getriebeöl an Endverbraucher verkauft, braucht eine Annahmestelle für Altöl — kostenlos bis zur verkauften Menge — und ein Hinweisschild (§ 8 AltölV).']""")
ers("['Was kann ich als Friseurin absetzen?','Was ist die Kleinunternehmer-Regel?',",
    "['Was kann ich in der Werkstatt absetzen?','Darf ich das Auto behalten?',")

# ── Probe: kein Salon-Wort mehr im sichtbaren Text (außer im Welten-Hero) ───
from html.parser import HTMLParser  # noqa: E402

_rest: list[str] = []


class _Pruefer(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stapel: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.stapel.append(tag)
        for k, v in attrs:
            if k == "alt" and v and re.search(r"Friseurin|Salon", v) and "Babs" not in v:
                _rest.append(v)

    def handle_endtag(self, tag):
        if self.stapel and self.stapel[-1] == tag:
            self.stapel.pop()

    def handle_data(self, d):
        if any(x in ("script", "style") for x in self.stapel):
            return
        s = " ".join(d.split())
        if re.search(r"\b(Friseurin|Salon|Haare|Babs|Olaf|Stuhlmiete)\b", s) and s not in ("Friseursalons", "← mit Babs"):
            _rest.append(s)


welthero = t[t.index("<!-- welten:start"):t.index("<!-- welten:ende -->")]
_Pruefer().feed(re.sub(r'data:[^"]+', "", t.replace(welthero, "")))
if _rest:
    sys.exit("Noch Salon-Text auf der Werkstatt-Seite:\n  " + "\n  ".join(dict.fromkeys(_rest)))

ZIEL.write_text(t, encoding="utf-8")
print(f"{ZIEL.relative_to(REPO)}: {len(t) // 1024} KB, {t.count('/bilder/ws-')} Werkstatt-Bilder")
