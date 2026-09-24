#!/usr/bin/env python3
"""Die Barber-Seite (mybabu.io/barber) als Kopie der Friseur-Startseite bauen.

Kopierprinzip: `server/babu-web/index.html` bleibt unangetastet; diese Datei
beschreibt, was auf der Barber-Seite ANDERS ist, und schreibt daraus
`server/babu-web/barber.html`. Jede Ersetzung wird gezählt — ändert sich die
Friseur-Seite, bricht der Bau laut ab, statt still eine halbe Seite zu bauen.

Anders als bei Friseur, mit Absicht:
- Moe und sein Shop in allen Szenenbildern (/bilder/ba-*.jpg, 17 Gegenstücke
  der Friseur-Motive, dazu ein Kopfbild); die App-Bildschirme bleiben die
  echten Aufnahmen.
- Kein Buhl (Auftraggeber 24.09.), das Steuer-Backend bleibt.
- App kommt per TestFlight auf Einladung, nicht „aus dem App Store".
- Impressum, Datenschutz und AGB als echte Links; kein Profi-Upload (401 für
  jeden Besucher) und keine Spot-Serie mit Babs und Olaf (eine Friseurin).
- Barber-Fragen: Meisterpflicht (HwO Anlage A Nr. 38, § 7b, § 8),
  Stuhlmiete, Kasse — aus dem Barber-Container belegt.
- Umschalter Deutsch/Türkisch; Deutsch ist immer die Vorgabe, `?sprache=tr`
  öffnet türkisch (Texte in `tr_texte.py`).

    python3 werbung/barber/seite_bauen.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUELLE = REPO / "server" / "babu-web" / "index.html"
ZIEL = REPO / "server" / "babu-web" / "barber.html"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tr_texte import TR  # noqa: E402

t = QUELLE.read_text(encoding="utf-8")


def ers(alt: str, neu: str, n: int = 1) -> None:
    """Ersetzt `alt` (Leerraum egal) genau n-mal durch `neu`."""
    global t
    muster = r"\s+".join(re.escape(w) for w in alt.split())
    t, zahl = re.subn(muster, lambda _m: neu, t)
    if zahl != n:
        sys.exit(f"Ersetzung passt nicht ({zahl} statt {n}): {alt[:80]!r}")


def weg(anfang: str, ende: str) -> None:
    """Entfernt alles von `anfang` bis einschließlich `ende` (einmal)."""
    global t
    a = t.find(anfang)
    b = t.find(ende, a)
    if a < 0 or b < 0:
        sys.exit(f"Abschnitt nicht gefunden: {anfang[:60]!r}")
    t = t[:a] + t[b + len(ende):]


HAKEN = ('<span class="hakenkreis"><svg viewBox="0 0 16 16" fill="none"><path d="M3.5 8.5l3 3 6-7" '
         'stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg></span>')

# ── Kopf, Farben, Umschalter ────────────────────────────────────────────────
ers("<title>babu — dein Papierkram macht sich von selbst</title>",
    "<title>babu Barber — dein Papierkram macht sich von selbst</title>")
ers("mit oder ohne eigenes Steuerbüro. Gemacht für Friseursalons.",
    "mit oder ohne eigenes Steuerbüro. Gemacht für Barbershops — auf Deutsch und Türkisch.")
ers("--gc-accent:#857b61; --gc-accent-hover:#736950; --gc-accent-subtle:#f0ebe3;",
    "--gc-accent:#8a6c3a; --gc-accent-hover:#6f5630; --gc-accent-subtle:#f3ecdf;")
ers("--gc-gold:#c9b98d;", "--gc-gold:#c7a15a;")
ers("</style>", """/* ── Barber: Kopfbild, Sprachumschalter ─────────────────────────────── */
.blatt{position:relative}
.held{margin:36px auto 0;max-width:980px}
.held img{width:100%;height:auto;display:block;border-radius:22px;border:1px solid var(--gc-border)}
.sprache{position:absolute;top:16px;right:18px;display:flex;gap:4px;z-index:5}
.sprache button{border:1px solid var(--gc-border);background:var(--gc-bg);border-radius:99px;
  padding:6px 12px;font:600 12px Inter,-apple-system,sans-serif;cursor:pointer;color:var(--gc-desc)}
.sprache button[aria-pressed="true"]{background:var(--gc-fg);border-color:var(--gc-fg);color:#fff}
.faq-quelle{display:block;font-size:12.5px;color:var(--gc-muted);margin-top:8px}
</style>""")
ers('<div class="blatt">', '''<div class="blatt">
<div class="sprache" role="group" aria-label="Sprache">
  <button type="button" data-sprache="de" aria-pressed="true">Deutsch</button>
  <button type="button" data-sprache="tr" aria-pressed="false">Türkçe</button>
</div>''')

# ── 1 · Hero ────────────────────────────────────────────────────────────────
ers('<div class="lbl">babu · für deinen Salon</div>', '<div class="lbl">babu · für deinen Barbershop</div>')
ers("eigenes Steuerbüro. Du schneidest weiter Haare.</p>",
    "eigenes Steuerbüro. Du kümmerst dich um Fades und Bärte.</p>")
ers("""    Grüner Haken = alles erledigt. Mehr musst du nicht wissen.
  </div>
</section>""", """    Grüner Haken = alles erledigt. Mehr musst du nicht wissen.
  </div>
  <figure class="held"><img src="/bilder/ba-held.jpg" width="1600" height="893" alt="Moe lacht in seinem Barbershop mit einem Stammkunden im Stuhl, der ein Glas Tee hält"></figure>
</section>""")

# ── 2 · Drei Schritte ───────────────────────────────────────────────────────
ers("Zwischen zwei Terminen, direkt an der Kasse, egal wo.",
    "Zwischen zwei Kunden, direkt an der Kasse, egal wo.")

# ── So fängst du an ─────────────────────────────────────────────────────────
ers('src="/bilder/start-1-laden.jpg"', 'src="/bilder/ba-start-1-laden.jpg"')
ers('alt="Friseurin sitzt entspannt auf der Bank in ihrem Salon und richtet auf dem Telefon etwas ein"',
    'alt="Moe sitzt morgens auf der Wartebank in seinem Shop und richtet auf dem Telefon etwas ein"')
ers("<b>App laden.</b> Aus dem App Store, wie jede andere App auch. Dauert so lange wie ein Kaffee.",
    "<b>App laden.</b> Per Einladung aufs iPhone: Apple schickt dir eine Mail, du tippst auf „Testen“. Dauert so lange wie ein Tee.")
ers('src="/bilder/start-2-anmelden.jpg"', 'src="/bilder/ba-start-2-anmelden.jpg"')
ers('alt="Friseurin steht am Empfangstresen und tippt mit dem Daumen kurz etwas in ihr Telefon"',
    'alt="Moe steht am Tresen und tippt mit dem Daumen kurz etwas in sein Telefon"')
ers('src="/bilder/start-3-foto.jpg"', 'src="/bilder/ba-start-3-foto.jpg"')
ers('src="/bilder/start-4-fertig.jpg"', 'src="/bilder/ba-start-4-fertig.jpg"')
ers('alt="Friseurin lehnt am Feierabend entspannt an der Wand ihres leeren Salons, das Telefon liegt weggelegt auf ihrem Knie"',
    'alt="Moe lehnt nach Feierabend entspannt an der Backsteinwand seines leeren Shops, das Telefon liegt weggelegt im Regal"')

# ── Und das kann babu dann alles ────────────────────────────────────────────
ers("Alles, was zwischen der ersten Kundin und dem Feierabend anfällt",
    "Alles, was zwischen dem ersten Kunden und dem Feierabend anfällt")
ers('src="/bilder/kann-termine.jpg"', 'src="/bilder/ba-kann-termine.jpg"')
ers('alt="Friseurin schaut zwischen zwei Kundinnen kurz auf ihr Telefon, in der anderen Hand eine Bürste"',
    'alt="Moe schaut zwischen zwei Kunden kurz auf sein Telefon, in der anderen Hand eine Haarschneidemaschine"')
ers("<b>Termine.</b> Schreib hin, wie du es sagen würdest: „Frau Meier Donnerstag Farbe“. babu sucht die freie Lücke.",
    "<b>Termine.</b> Schreib hin, wie du es sagen würdest: „Kerem Donnerstag Fade und Bart“. babu sucht die freie Lücke — und für Laufkundschaft bleibt Platz.")
ers('src="/bilder/kann-nachricht.jpg"', 'src="/bilder/ba-kann-nachricht.jpg"')
ers('alt="Friseurin sitzt auf der Lehne der Wartebank und liest schmunzelnd eine Nachricht auf dem Telefon"',
    'alt="Moe sitzt auf der Lehne der Wartebank und liest schmunzelnd eine Nachricht auf dem Telefon"')
ers("Deine Kundin schreibt, babu antwortet mit freien Zeiten und trägt den Termin ein.",
    "Dein Kunde schreibt, babu antwortet mit freien Zeiten und trägt den Termin ein.")
ers('src="/bilder/kann-belege.jpg"', 'src="/bilder/ba-kann-belege.jpg"')
ers('alt="Umgekippter Schuhkarton auf dem Tresen, aus dem ein Haufen Kassenbons quillt, daneben ein Telefon"',
    'alt="Umgekippter Schuhkarton auf dem Tresen, aus dem ein Haufen Kassenbons quillt, Moe greift mit dem Telefon hinein"')
ers('src="/bilder/kann-kundin.jpg"', 'src="/bilder/ba-kann-kundin.jpg"')
ers('alt="Friseurin rührt Farbe in einer Schale an, das Telefon steht aufgestellt vor ihr"',
    'alt="Moe bereitet ein heißes Tuch für die Rasur vor, das Telefon steht aufgestellt vor ihm"')
ers("<b>Deine Kundinnen.</b> Welche Formel beim letzten Mal stimmte, was sie nicht verträgt. Der Karteikasten hinterm Spiegel, nur auffindbar.",
    "<b>Deine Stammkunden.</b> Welcher Schnitt beim letzten Mal saß, welche Aufsatzlänge, was die Haut nicht verträgt. Der Karteikasten hinterm Spiegel, nur auffindbar.")
ers('src="/bilder/kann-rechnung.jpg"', 'src="/bilder/ba-kann-rechnung.jpg"')
ers('alt="Friseurin lehnt am Tresen und tippt konzentriert etwas in ihr Telefon, im Hintergrund zieht eine Kundin ihren Mantel an"',
    'alt="Moe lehnt am Tresen und tippt konzentriert etwas in sein Telefon, im Hintergrund zieht ein Kunde seine Jacke an"')
ers("<b>Rechnungen.</b> Stuhlmiete, Hochzeit, Firmenkunde.",
    "<b>Rechnungen.</b> Stuhlmiete, Bräutigam mit Trauzeugen, Firmenkunde.")
ers('src="/bilder/kann-kasse.jpg"', 'src="/bilder/ba-kann-kasse.jpg"')
ers('alt="Friseurin zählt abends bei Lampenlicht hinter dem Tresen Scheine und Münzen, das Telefon liegt daneben"',
    'alt="Moe zählt abends unter der Messinglampe hinter dem Tresen Scheine und Münzen, das Telefon liegt daneben"')
ers("<b>Abends kurz zählen.</b> Eine Zahl nach der anderen, wie auf deinem Papierzettel. Am Ende sagt babu: deine Kasse stimmt.",
    "<b>Abends kurz zählen.</b> Viel Bargeld? Genau dafür. Eine Zahl nach der anderen, wie auf deinem Papierzettel. Am Ende sagt babu: deine Kasse stimmt.")

# ── Salon-Check → Shop-Check ────────────────────────────────────────────────
ers('<div class="lbl">Neu · Der Salon-Check</div>', '<div class="lbl">Neu · Der Shop-Check</div>')
ers("wo dein Salon steht. Mit Ampeln statt Steuer-Deutsch.",
    "wo dein Shop steht. Mit Ampeln statt Steuer-Deutsch.")
ers('alt="Friseurin mit einem großen Stapel Ordner und Belegen vom letzten Jahr im Arm"',
    'alt="Moe trägt lachend einen riesigen Stapel Ordner und Belege vom letzten Jahr im Arm"')
ers("<h4>Dein Salon-Check</h4>", "<h4>Dein Shop-Check</h4>")
ers("✓ Fertig — dein Salon-Check steht.", "✓ Fertig — dein Shop-Check steht.")
ers(">Salon-Check starten</a>", ">Shop-Check starten</a>")

# ── Kostenvergleich: ohne den Babs-und-Olaf-Spot ────────────────────────────
weg('<div class="karte" style="margin-top:18px;max-width:340px', "</p>\n  </div>")

# ── Pakete ──────────────────────────────────────────────────────────────────
ers("<h2>Ein Preis, der zu deinem Salon passt.</h2>", "<h2>Ein Preis, der zu deinem Shop passt.</h2>")
ers("Je nachdem, wie dein Salon aufgestellt ist,", "Je nachdem, wie dein Shop aufgestellt ist,")
ers("<li>Kleinunternehmerin (§ 19 UStG) — keine Umsatzsteuer</li>",
    "<li>Kleinunternehmer (§ 19 UStG) — keine Umsatzsteuer</li>")
ers("<li>Belege, Kassenbuch, Salon-Check — alles drin</li>", "<li>Belege, Kassenbuch, Shop-Check — alles drin</li>")
ers('<h3 class="gruen">Salon</h3>', '<h3 class="gruen">Shop</h3>')
ers("<h3>Salon Plus</h3>", "<h3>Shop Plus</h3>")
ers("<li>Alles aus Salon — plus getrennte Auswertungen</li>", "<li>Alles aus Shop — plus getrennte Auswertungen</li>")
ers("""Dann wird es günstiger — sag uns kurz Bescheid.
  Machst du umsatzsteuerfreie medizinische Behandlungen (z. B. podologische
  Fußpflege, § 4 Nr. 14 UStG)? babu stellt das richtig ein.</p>""",
    "Dann wird es günstiger — sag uns kurz Bescheid.</p>")
ers("Sieben kurze Fragen — dann weißt du es.", "Sechs kurze Fragen — dann weißt du es.")
ers("""    {k:'medizinisch', f:'Machst du medizinische Behandlungen ohne Umsatzsteuer — zum Beispiel podologische Fußpflege?', a:['Ja','Nein']},
""", "")
ers("{k:'klein', f:'Bist du Kleinunternehmerin?", "{k:'klein', f:'Bist du Kleinunternehmer?")
ers("{k:'filialen', f:'Hat dein Salon mehr als einen Standort?'", "{k:'filialen', f:'Hat dein Shop mehr als einen Standort?'")
ers("var paket=plus?['Salon Plus','149 €']:(solo?['Solo','39 €']:['Salon','79 €']);",
    "var paket=plus?['Shop Plus','149 €']:(solo?['Solo','39 €']:['Shop','79 €']);")
ers("""    if(antworten.medizinisch==='Ja')
      extra.push('Deine medizinischen Behandlungen bleiben ohne Umsatzsteuer — babu stellt das richtig ein.');
""", "")
ers("der Salon-Check liest es einfach aus deinen Unterlagen heraus.", "der Shop-Check liest es einfach aus deinen Unterlagen heraus.")

# ── Spot-Serie (Babs und Olaf) entfällt ─────────────────────────────────────
weg("<!-- ── 4b2 · Serie: Kostenwahrheit", "</section>")

# ── Telefon kann alles ──────────────────────────────────────────────────────
ers("Dein Telefon verbindet dich mit allem, was zu deinem Salon gehört —",
    "Dein Telefon verbindet dich mit allem, was zu deinem Shop gehört —")


def bild_ersetzen(alt_text: str, neu_src: str) -> None:
    """Ein eingebettetes Friseur-Bild (data-URI) durch das Barber-Bild ersetzen;
    `alt_text` ist das (schon ersetzte) alt dieses Bildes."""
    global t
    muster = r'src="data:[^"]+"(\s+alt="' + re.escape(alt_text) + '")'
    t, zahl = re.subn(muster, lambda m: f'src="{neu_src}" loading="lazy" width="692" height="859"{m.group(1)}', t)
    if zahl != 1:
        sys.exit(f"Bild nicht gefunden: {alt_text[:60]!r}")


bild_ersetzen("Moe trägt lachend einen riesigen Stapel Ordner und Belege vom letzten Jahr im Arm",
              "/bilder/ba-papierstapel.jpg")
ers('alt="Friseurin fotografiert am Empfangstresen einen Beleg mit dem Telefon, im Hintergrund wartet eine Kundin mit Folien"',
    'alt="Moe fotografiert am Tresen einen Beleg mit dem Telefon, im Hintergrund warten zwei Kunden auf der Bank"')
bild_ersetzen("Moe fotografiert am Tresen einen Beleg mit dem Telefon, im Hintergrund warten zwei Kunden auf der Bank",
              "/bilder/ba-scanner.jpg")
ers("sicher abgelegt. Mitten zwischen zwei Terminen.</p>", "sicher abgelegt. Mitten zwischen zwei Kunden.</p>")
ers('alt="Friseurin lehnt nach Feierabend entspannt am Tresen und schaut zufrieden auf ihr Telefon, daneben ein Kaffee"',
    'alt="Moe lehnt nach Feierabend entspannt am Tresen und schaut zufrieden auf sein Telefon, daneben ein Glas Tee"')
bild_ersetzen("Moe lehnt nach Feierabend entspannt am Tresen und schaut zufrieden auf sein Telefon, daneben ein Glas Tee",
              "/bilder/ba-helfer.jpg")
ers("grüner Haken, Kaffee. Der Tag ist wirklich vorbei.</p>", "grüner Haken, ein Glas Tee. Der Tag ist wirklich vorbei.</p>")
ers('alt="Friseurin fotografiert amüsiert einen Brief vom Amt, der vor ihr auf dem Tisch liegt"',
    'alt="Moe fotografiert amüsiert einen Brief vom Amt, der vor ihm auf dem Tresen liegt"')
bild_ersetzen("Moe fotografiert amüsiert einen Brief vom Amt, der vor ihm auf dem Tresen liegt", "/bilder/ba-berater.jpg")

# ── Hosentasche ─────────────────────────────────────────────────────────────
ers('<div class="klein" style="margin-bottom:6px">3 Termine, 3 Std 45 min gebucht</div>',
    '<div class="klein" style="margin-bottom:6px">3 Termine gebucht, dazwischen Laufkundschaft</div>')
ers('<div class="zeile"><b>11:00</b><span>Frau Holder</span><span class="pille">Schnitt</span></div>',
    '<div class="zeile"><b>11:00</b><span>Kerem Y.</span><span class="pille">Fade</span></div>')
ers('<div class="zeile"><b>13:30</b><span>Frau Sommer</span><span class="pille">Farbe</span></div>',
    '<div class="zeile"><b>13:30</b><span>Murat A.</span><span class="pille">Bart</span></div>')
ers('<div class="zeile"><b>16:00</b><span>Herr Betz</span><span class="pille">Schnitt</span></div>',
    '<div class="zeile"><b>16:00</b><span>Jonas B.</span><span class="pille">Fade + Bart</span></div>')
ers("„Frau Meier Donnerstag Farbe\" — babu sucht die Lücke.", "„Kerem Donnerstag Fade\" — babu sucht die Lücke.")
ers('<div class="stark">Offen · 535,50 €</div>', '<div class="stark">Offen · 450,00 €</div>')
ers('<div class="zeile"><span>Jana Allgaier</span><b>535,50 €</b></div>',
    '<div class="zeile"><span>Deniz K.</span><b>450,00 €</b></div>')
ers("<span>Jana hat am 02.09. bezahlt</span>", "<span>Deniz hat am 02.09. bezahlt</span>")
ers('src="/bilder/termine-morgens.jpg"', 'src="/bilder/ba-termine-morgens.jpg"')
ers('alt="Friseurin steht morgens vor Ladenöffnung am Tresen, Kaffee in der einen Hand, Telefon in der anderen, und sieht entspannt ihre Termine durch"',
    'alt="Moe steht morgens vor Ladenöffnung am Tresen, ein Glas Tee in der einen Hand, das Telefon in der anderen"')
ers("wie voll ist der Tag. Bevor die erste Kundin da ist.</p>", "wie voll ist der Tag. Bevor der erste Kunde da ist.</p>")
ers('src="/bilder/rechnung-tresen.jpg"', 'src="/bilder/ba-rechnung-tresen.jpg"')
ers('alt="Friseurin reicht einer lächelnden Kundin ein Blatt Papier über den Empfangstresen, daneben ein Kartenlesegerät"',
    'alt="Moe reicht einem lächelnden Kunden ein Blatt Papier über den Tresen"')
ers("<p><strong>Zwischendurch.</strong> Rechnung schreiben, während sie noch",
    "<p><strong>Zwischendurch.</strong> Rechnung schreiben, während er noch")
ers('src="/bilder/feierabend-zahlen.jpg"', 'src="/bilder/ba-feierabend-zahlen.jpg"')
ers('alt="Friseurin sitzt nach Feierabend entspannt im Friseurstuhl im aufgeräumten Salon und schaut auf ihr Telefon"',
    'alt="Moe sitzt nach Feierabend entspannt im eigenen Barberstuhl im aufgeräumten Shop und schaut auf sein Telefon"')

# ── Für deinen Barbershop gebaut ────────────────────────────────────────────
ers('<div class="lbl">Für deinen Salon gebaut</div>', '<div class="lbl">Für deinen Barbershop gebaut</div>')
ers("<strong>Farbe, Bedarf, Handtücher</strong> — Einkäufe werden automatisch richtig einsortiert.",
    "<strong>Klingen, Nackenpapier, Pomade</strong> — Einkäufe werden automatisch richtig einsortiert.")
ers("<strong>Essen mit der Vertreterin?</strong> babu fragt kurz nach, mit wem du warst",
    "<strong>Essen mit dem Vertreter?</strong> babu fragt kurz nach, mit wem du warst")
ers("""      <span><strong>Kontoauszug abgeben</strong> — babu prüft, ob zu jeder Abbuchung ein Beleg da ist. Fehlt einer, sagt es dir welcher.</span></li>
  </ul>""", f"""      <span><strong>Kontoauszug abgeben</strong> — babu prüft, ob zu jeder Abbuchung ein Beleg da ist. Fehlt einer, sagt es dir welcher.</span></li>
    <li>{HAKEN}
      <span><strong>Meister, Stuhlmiete, Mindestlohn, Azubi?</strong> Frag babu — der Chat kennt die Gesetze im Wortlaut, von der Handwerksordnung bis zum Jugendarbeitsschutz, und nennt dir die Stelle.</span></li>
    <li>{HAKEN}
      <span><strong>Kassen-Nachschau</strong> — das Finanzamt darf unangemeldet kommen (§ 146b AO). Dein Kassenbuch in babu ist lückenlos, jede Änderung bleibt sichtbar.</span></li>
  </ul>""")

# ── Kassenbuch: Bargeld ─────────────────────────────────────────────────────
ers("babu ersetzt nur den Zettel, auf dem du abends alles zusammenrechnest.</p>",
    """babu ersetzt nur den Zettel, auf dem du abends alles zusammenrechnest.</p>
  <p class="sub" style="margin-top:14px">In Barbershops wird viel bar bezahlt —
  darum schaut das Finanzamt hier besonders genau hin. Bei der Kontrollaktion der
  Finanzverwaltung Baden-Württemberg im Frühjahr 2026 waren 65 Barbershops unter den
  geprüften Betrieben. Ein sauberes Kassenbuch ist deine beste Antwort.</p>""")

# ── Wechsel: ohne Buhl, das Steuer-Backend bleibt ───────────────────────────
ers("""Abschluss über babu. Dahinter arbeitet <strong>Buhl</strong> — einer der
      größten Steuer-Software-Anbieter Deutschlands. Dein Kram ist in
      Profi-Händen.""", """Abschluss über babu. Dahinter arbeitet ein Steuer-Backend. Dein Kram ist in
      Profi-Händen.""")

# ── App laden: TestFlight ───────────────────────────────────────────────────
ers("""fertig. In der Testphase läuft die App auf freigeschalteten iPhones.</p>""",
    """fertig. In der Testphase kommt die App per TestFlight auf Einladung — Apples offizieller Weg für Test-Apps.</p>""")
ers("die wichtigsten Angaben ab — Salon-Name, Steuernummer, Finanzamt.",
    "die wichtigsten Angaben ab — Shop-Name, Steuernummer, Finanzamt.")

# ── FAQ ─────────────────────────────────────────────────────────────────────
ers("""<div class="antwort">Hinter babu arbeitet Buhl — einer der größten
      Steuer-Software-Anbieter Deutschlands (bekannt durch WISO Steuer). babu
      sammelt und ordnet, das Steuer-Backend übernimmt den fachlichen Teil.
      Du hast einen Ansprechpartner: babu.</div>""", """<div class="antwort">babu sammelt und ordnet, das
      Steuer-Backend übernimmt den fachlichen Teil. Du hast einen Ansprechpartner: babu.</div>""")
ers("""  <div style="margin-top:26px">
    <details><summary>Ich bin schon bei einem Steuerberater.""", """  <div style="margin-top:26px">
    <details><summary>Brauche ich einen Meister für meinen Barbershop?</summary>
      <div class="antwort">Ein Barbershop, der schneidet und rasiert, ist Friseurhandwerk — und
      das ist zulassungspflichtig (Anlage A Nr. 38 der Handwerksordnung). Du brauchst die
      Eintragung in die Handwerksrolle. Dafür gibt es mehrere Wege: den eigenen Meisterbrief,
      einen Betriebsleiter mit Meisterbrief (§ 7 HwO), die Ausübungsberechtigung ohne Meister —
      Gesellenprüfung und sechs Jahre im Beruf, davon vier in leitender Stellung (§ 7b HwO) —
      oder eine Ausnahmebewilligung (§ 8 HwO). Welcher Weg für dich passt, entscheidet die
      Handwerkskammer; deren Beratung ist kostenlos.
      <span class="faq-quelle">Quelle: Handwerksordnung §§ 1, 7, 7b, 8 und Anlage A, gesetze-im-internet.de</span></div></details>
    <details><summary>Ist Stuhlmiete bei mir erlaubt?</summary>
      <div class="antwort">Ja, wenn der Stuhlmieter wirklich selbständig ist: eigene Kunden,
      eigene Preise, eigenes Material, eigene Kasse, keine Vorgaben zu Arbeitszeiten. Sonst
      kann es eine Beschäftigung sein (§ 7 SGB IV) — mit Nachzahlung von Beiträgen. Wer
      unsicher ist, lässt den Status bei der Deutschen Rentenversicherung feststellen
      (§ 7a SGB IV). Die Stuhlmiete schreibst du mit babu als Rechnung.
      <span class="faq-quelle">Quelle: SGB IV §§ 7, 7a, gesetze-im-internet.de</span></div></details>
    <details><summary>Gibt es babu auf Türkisch?</summary>
      <div class="antwort">Diese Seite schon — oben rechts umschalten. Die App und der Chat
      bekommen Türkisch als Nächstes. Gebucht wird immer auf Deutsch und auf dem deutschen
      Kontenrahmen: dein Steuerbüro und das Finanzamt lesen es so.</div></details>
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
    '<a href="/" style="color:var(--gc-desc)">babu für Friseursalons</a> · '
    "babu ersetzt keine individuelle Steuerberatung.")
weg("/* ── Profi-Upload (Funktion der bisherigen Startseite, kompakt)", "})();\n")

# ── Chat-Widget ─────────────────────────────────────────────────────────────
ers("'Typisch im Salon: Material und Werkzeug (Scheren, Farben, Föhn), Miete,",
    "'Typisch im Barbershop: Material und Werkzeug (Klingen, Trimmer, Scheren, Pomade), Miete,")
ers("Ob das zu dir passt, findet babu im Salon-Check mit heraus.'",
    "Ob das zu dir passt, findet babu im Shop-Check mit heraus.'")
ers("Solo 39 €, Salon 79 €, Salon Plus 149 € im Monat", "Solo 39 €, Shop 79 €, Shop Plus 149 € im Monat")
ers("In der Testphase läuft die App auf freigeschalteten iPhones; deine Zugangsdaten bekommst du bei der Einrichtung.'",
    "In der Testphase kommt die App per TestFlight auf Einladung; deine Zugangsdaten bekommst du bei der Einrichtung.'")
ers("""    ['buhl|wiso|backend','Hinter babu arbeitet Buhl — einer der größten Steuer-Software-Anbieter Deutschlands (WISO Steuer). babu sammelt und ordnet, das Steuer-Backend macht den fachlichen Teil.']""",
    """    ['backend|wer macht','babu sammelt und ordnet, das Steuer-Backend macht den fachlichen Teil.'],
    ['meister|handwerksrolle|7b','Barbershops sind Friseurhandwerk, Anlage A Nr. 38 der Handwerksordnung. Du brauchst die Eintragung in die Handwerksrolle: mit Meister, mit Betriebsleiter, über die Ausübungsberechtigung nach § 7b (Gesellenprüfung, sechs Jahre, davon vier leitend) oder eine Ausnahme nach § 8. Frag deine Handwerkskammer — die Beratung ist kostenlos.'],
    ['stuhlmiete|scheinselbst','Stuhlmiete geht, wenn der Mieter wirklich selbständig ist: eigene Kunden, Preise, Material, Kasse, keine Arbeitszeit-Vorgaben. Sonst droht eine Beschäftigung nach § 7 SGB IV. Im Zweifel Statusfeststellung bei der Rentenversicherung (§ 7a SGB IV).'],
    ['türk|turk','Diese Seite gibt es auf Türkisch (oben rechts). App und Chat folgen. Gebucht wird immer auf Deutsch.']""")
ers("['Was kann ich als Friseurin absetzen?','Was ist die Kleinunternehmer-Regel?',",
    "['Was kann ich im Barbershop absetzen?','Brauche ich einen Meister?',")

ers("'Kleinunternehmerin (§ 19 UStG) heißt:", "'Kleinunternehmer (§ 19 UStG) heißt:")

# ── Türkisch: Umschalter und Wörterbuch ─────────────────────────────────────
UMSCHALTER = """
/* ── Sprache: Deutsch ist die Vorgabe, Türkisch der Umschalter. ─────────
   Ausgetauscht wird nur, was angezeigt wird — Texte, Bildbeschreibungen,
   Knöpfe, und was Fragebogen und Chat später einblenden. Gebucht wird in
   babu immer deutsch; das hier ist nur die Seite. ?sprache=tr öffnet sie
   türkisch (für Links, die man verschickt). */
(function(){
  var TR=__TR__, sprache='de',
      norm=function(s){return String(s).replace(/\\s+/g,' ').trim();},
      urText=new WeakMap(), urAttr=new WeakMap(), ATTR=['alt','aria-label','placeholder'],
      titelDe=document.title;
  function text(n){
    if(!urText.has(n)) urText.set(n,n.nodeValue);
    var o=urText.get(n), k=norm(o);
    if(!k) return;
    var neu=(sprache==='tr'&&TR[k])?(o.match(/^\\s*/)[0]+TR[k]+o.match(/\\s*$/)[0]):o;
    if(n.nodeValue!==neu) n.nodeValue=neu;
  }
  function element(el){
    var m=urAttr.get(el)||{};
    ATTR.forEach(function(a){
      if(!el.hasAttribute(a)) return;
      if(!(a in m)) m[a]=el.getAttribute(a);
      var k=norm(m[a]); el.setAttribute(a,(sprache==='tr'&&TR[k])?TR[k]:m[a]);
    });
    urAttr.set(el,m);
  }
  function lauf(wurzel){
    if(wurzel.nodeType===3){ text(wurzel); return; }
    if(wurzel.nodeType!==1||/^(SCRIPT|STYLE)$/.test(wurzel.nodeName)) return;
    element(wurzel);
    var w=document.createTreeWalker(wurzel,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT,
      {acceptNode:function(n){return n.parentNode&&/^(SCRIPT|STYLE)$/.test(n.parentNode.nodeName)?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT;}});
    while(w.nextNode()){ var n=w.currentNode; if(n.nodeType===3) text(n); else element(n); }
  }
  function setze(s){
    sprache=s; document.documentElement.lang=s;
    document.title=(s==='tr'&&TR[norm(titelDe)])?TR[norm(titelDe)]:titelDe;
    document.querySelectorAll('[data-sprache]').forEach(function(b){
      b.setAttribute('aria-pressed',b.getAttribute('data-sprache')===s?'true':'false');});
    lauf(document.body);
  }
  new MutationObserver(function(liste){
    if(sprache!=='tr') return;
    liste.forEach(function(m){ m.addedNodes.forEach(lauf); });
  }).observe(document.body,{childList:true,subtree:true});
  document.querySelectorAll('[data-sprache]').forEach(function(b){
    b.addEventListener('click',function(){ setze(b.getAttribute('data-sprache')); });
  });
  if(/[?&]sprache=tr\\b/.test(location.search)) setze('tr');
})();
"""
ers("</script>\n</body>", UMSCHALTER.replace("__TR__", json.dumps(TR, ensure_ascii=False)) + "</script>\n</body>")

# Jeder sichtbare deutsche Satz braucht eine türkische Fassung — sonst stünde
# er im Umschalter plötzlich allein auf Deutsch da.
from html.parser import HTMLParser  # noqa: E402
_norm = lambda s: " ".join(s.split())  # noqa: E731
_fehlt: list[str] = []
_BLEIBT = re.compile(r"^(Kerem Y\.|Murat A\.|Jonas B\.|Deniz K\.|Ludwigsburg|Fade|Bart|Fade \+ Bart|Kamera|"
                     r"Deutsch|Türkçe|babu|Solo|Shop|Shop Plus|[\d\s.,:€/*+–—%()-]+.*€.*|[\d.,\s€*]+)$")


class _Pruefer(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stapel: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.stapel.append(tag)
        for k, v in attrs:
            if k in ("alt", "aria-label", "placeholder") and v and not v.startswith("data:") and _norm(v) not in TR:
                _fehlt.append(_norm(v))

    def handle_endtag(self, tag):
        if self.stapel and self.stapel[-1] == tag:
            self.stapel.pop()

    def handle_data(self, d):
        if any(x in ("script", "style") for x in self.stapel):
            return
        s = _norm(d)
        if re.search(r"[A-Za-zÄÖÜäöüß]{3}", s) and s not in TR and not _BLEIBT.match(s):
            _fehlt.append(s)


_Pruefer().feed(re.sub(r'data:[^"]+', "", t))
if _fehlt:
    sys.exit("Ohne türkische Fassung:\n  " + "\n  ".join(dict.fromkeys(_fehlt)))

ZIEL.write_text(t, encoding="utf-8")
print(f"{ZIEL.relative_to(REPO)}: {len(t) // 1024} KB, {t.count('/bilder/ba-')} Barber-Bilder")
