"""Impressum, Datenschutz, AGB — eine Quelle für Portal, Landing, App und die
drei eigenen Seiten (`/impressum`, `/datenschutz`, `/agb`).

Die Seiten braucht die Beta App Review bei Apple (eine Datenschutz-URL ist
Pflicht), die App verlinkt sie unter „Rechtliches", das Portal zeigt sie im
Blatt, die Landing-Seite in der Fußzeile. Bis 14.09.2026 lagen die Texte nur
im Portal — als Platzhalter.

**Seit 14.09.2026 stehen hier Erprobungsfassungen**, vom Auftraggeber für den
Pilot so bestimmt („ist eh nur Test"). Jeder Text sagt in seiner ersten Zeile,
dass er eine Erprobungsfassung ist; die Anwältin ersetzt ihn vor dem allgemeinen
Start, und zwar nur hier in `TEXTE`. Ein Text, der mit `PLATZHALTER` beginnt,
meldet `fertig()` False, die Seite sagt es selbst, und `ios/archiv.sh` warnt
vor jedem Upload — dieser Mechanismus bleibt für den Fall, dass ein Text wieder
herausgenommen wird.
"""
from __future__ import annotations

import html

PLATZHALTER = "Text folgt."

TEXTE: dict[str, tuple[str, str]] = {
    "impressum": ("Impressum",
        "Erprobungsfassung (Stand 14.09.2026). Die Angaben gelten für die Zeit des "
        "Pilotbetriebs; der verbindliche Wortlaut wird vor dem allgemeinen Start "
        "rechtlich geprüft.\n\n"
        "Anbieter dieser Seite und der App babu:\n\n"
        "0711 Intelligence, Christoph Bertsch, Stuttgart.\n\n"
        "Kontakt: nina@0711.io\n\n"
        "Verantwortlich für die Inhalte: Christoph Bertsch.\n\n"
        "babu ist ein Werkzeug zur Aufnahme und Ordnung von Belegen. babu erstellt "
        "keine Steuererklärungen und ersetzt keine Steuerberatung. Die steuerliche "
        "Beurteilung bleibt bei der Steuerkanzlei des jeweiligen Betriebs."),
    "datenschutz": ("Datenschutz",
        "Erprobungsfassung (Stand 03.10.2026). Diese Erklärung beschreibt, was "
        "mit deinen Angaben geschieht. Der verbindliche Wortlaut wird vor dem "
        "allgemeinen Start rechtlich geprüft.\n\n"
        "1. Wer verantwortlich ist. Verantwortlich ist der im Impressum genannte "
        "Anbieter. Fragen und Anliegen zum Datenschutz: nina@0711.io.\n\n"
        "2. Was babu verarbeitet. Beim Anlegen des Zugangs: E-Mail-Adresse, Name, "
        "Name des Betriebs und ein von dir gewähltes Passwort (nur als Prüfsumme "
        "gespeichert). Bei der Nutzung: die Belege, die du fotografierst oder als "
        "PDF einreichst, mit dem darauf gelesenen Text; Kontoauszüge, wenn du sie "
        "einreichst; Angaben zu Terminen, Kundinnen und Personal, sofern du diese "
        "Bereiche nutzt; Rückmeldungen, die du aus der App schickst. Technisch: "
        "Zeitpunkt und Art eines Zugriffs, die Adresse deines Geräts im Netz und "
        "eine Kennung je verbundenem Telefon.\n\n"
        "3. Wofür. Um Belege zu lesen, einzuordnen und für dich und deine "
        "Steuerkanzlei geordnet abzulegen; um den Zugang zu sichern; um Fehler zu "
        "finden und zu beheben. Rechtsgrundlage ist die Erfüllung der "
        "Nutzungsvereinbarung mit dir (Art. 6 Abs. 1 lit. b DSGVO) und unser "
        "berechtigtes Interesse an einem sicheren Betrieb (Art. 6 Abs. 1 lit. f).\n\n"
        "4. Wo. Alle Daten liegen auf einem eigenen Rechner des Anbieters in "
        "Deutschland. Das Lesen der Belege geschieht ebenfalls dort; kein Beleg wird "
        "an einen fremden Dienst zur Auswertung gegeben. E-Mails (Passwort "
        "zurücksetzen, Einladungen) werden über einen Versanddienst mit "
        "Verarbeitung in der EU verschickt.\n\n"
        "5. Wer sie sonst sieht. Deine Steuerkanzlei, wenn sie deinen Betrieb in "
        "babu betreut, für die Belege deines Betriebs. Rückmeldungen aus der App "
        "landen bei uns in einem geschützten Vorgangssystem und als Kopie im "
        "Support-Postfach. Sonst niemand.\n\n"
        "6. Wie lange. Belege und Kontoauszüge sind Buchführungsunterlagen und "
        "bleiben so lange gespeichert, wie du oder deine Kanzlei sie brauchen, "
        "längstens bis zum Ablauf der gesetzlichen Aufbewahrungsfrist. Zugangsdaten "
        "so lange, wie dein Zugang besteht. Technische Protokolle höchstens 30 "
        "Tage. Sicherungskopien werden nach 14 Tagen überschrieben.\n\n"
        "7. Deine Rechte. Du kannst Auskunft über deine Daten verlangen, sie "
        "berichtigen oder löschen lassen, ihre Verarbeitung einschränken, sie in "
        "einem gängigen Format erhalten und dich bei einer Aufsichtsbehörde "
        "beschweren. Schreib dafür an nina@0711.io; wir antworten innerhalb von 30 "
        "Tagen. Eine Löschung setzt voraus, dass die Belege nicht mehr der "
        "Aufbewahrungspflicht unterliegen; bis dahin werden sie gesperrt.\n\n"
        "8. Verbundene Telefone. Jedes Telefon, das du mit babu verbindest, erhält "
        "einen eigenen Schlüssel. Du siehst die Liste im Portal und kannst jedes "
        "Telefon dort trennen. Ein neues Passwort beendet alle Sitzungen.\n\n"
        "9. Bezahlen. Wenn du ein Abo abschließt, bezahlst du über den "
        "Zahlungsdienst Stripe (Stripe Payments Europe, Irland): per Karte. "
        "Stripe erhält dafür Name, Anschrift, E-Mail, gegebenenfalls deine "
        "Umsatzsteuer-Identifikationsnummer und die Zahlungsdaten; die "
        "Zahlungsdaten gibst du direkt bei Stripe ein. babu selbst "
        "sieht und speichert keine Kontonummer und keine Kartendaten, sondern nur, "
        "welches Paket du hast und ob die Zahlung angekommen ist. Rechnungen "
        "erstellt Stripe in unserem Auftrag; sie werden zehn Jahre aufbewahrt "
        "(Aufbewahrungspflicht). Rechtsgrundlage ist der Vertrag mit dir "
        "(Art. 6 Abs. 1 lit. b) und die gesetzliche Pflicht (lit. c).\n\n"
        "10. Empfehlung durch eine Ambassadorin. Kommst du über den Link einer "
        "Ambassadorin zu babu, sieht sie in ihrem Bereich, ob du babu nutzt: "
        "deinen Stand (testet, macht mit), wie viele Belege du hochgeladen hast "
        "und an welchem Tag zuletzt — nie die Belege, Beträge oder andere Inhalte. "
        "Das brauchen wir, um ihre Provision abzurechnen, und es ist unser "
        "berechtigtes Interesse (Art. 6 Abs. 1 lit. f), dass sie dir beim Start "
        "helfen kann. Du kannst dem jederzeit widersprechen (Art. 21 DSGVO); "
        "schreib uns dafür kurz.\n\n"
        "11. Wenn du Ambassadorin bist. Wir speichern deinen Namen, deine "
        "E-Mail-Adresse und für die Auszahlung deine Kontoverbindung, Anschrift "
        "und Steuerangaben. Gutschriften bewahren wir zehn Jahre auf. Die "
        "Vornamen und Handynummern, die du für eine Einladung einträgst, nutzt "
        "babu nur, um dir eine fertige Nachricht vorzuschlagen; verschickt wird "
        "sie von deinem eigenen Telefon. babu schreibt diese Menschen nicht von "
        "sich aus an. Trag nur Menschen ein, die dich kennen und mit einer "
        "Nachricht von dir rechnen.\n\n"
        "12. Weitere Dienste. Der Datenverkehr zu babu läuft über Cloudflare "
        "(Verbindung und Schutz vor Angriffen); die App verteilt Apple über den "
        "App Store."),
    "agb": ("Nutzungsbedingungen",
        "Erprobungsfassung (Stand 03.10.2026). Der verbindliche Wortlaut wird vor "
        "dem allgemeinen Start rechtlich geprüft.\n\n"
        "0. Für wen. babu richtet sich an Unternehmerinnen und Unternehmer "
        "(§ 14 BGB), die babu für ihren Betrieb nutzen.\n\n"
        "1. Was babu ist. babu nimmt Belege auf, liest sie, ordnet sie ein und legt "
        "sie geordnet ab, damit deine Steuerkanzlei damit arbeiten kann. babu gibt "
        "keine steuerliche oder rechtliche Beratung. Vorschläge zur Einordnung "
        "eines Belegs sind Hilfen, keine Entscheidungen; die Verantwortung für die "
        "Buchführung bleibt bei dir und deiner Kanzlei.\n\n"
        "2. Zugang. Den Zugang bekommst du auf Einladung. Du hältst dein Passwort "
        "geheim und meldest uns, wenn du einen Missbrauch vermutest. Du darfst nur "
        "Belege deines eigenen Betriebs einreichen.\n\n"
        "3. Kosten. Kommst du über einen Testmonat zu babu, nutzt du babu 30 Tage "
        "lang kostenlos und in vollem Umfang. Der Test endet von selbst; es "
        "entsteht kein Abo und keine Zahlungspflicht. Danach kannst du alles "
        "weiter ansehen und herunterladen, aber nichts Neues erfassen, bis du ein "
        "Abo abschließt. Ohne deine ausdrückliche Bestellung entstehen keine "
        "Kosten.\n\n"
        "3a. Abo. Es gibt drei Pakete: Solo 39 €, Salon 79 € und Salon Plus "
        "149 € im Monat, jeweils zuzüglich Umsatzsteuer. Das Abo läuft monatlich "
        "und ist jederzeit zum Ende des bezahlten Monats kündbar, im Portal unter "
        "„Weitermachen“. Bezahlt wird im Voraus per Karte über den "
        "Zahlungsdienst Stripe; die Rechnung kommt per E-Mail. Ein "
        "Paketwechsel nach oben gilt sofort und wird anteilig berechnet, nach "
        "unten zum Ende des Monats.\n\n"
        "3b. Wenn eine Zahlung nicht ankommt. Geht eine Abbuchung zurück, "
        "versucht Stripe es erneut, und wir sagen dir Bescheid. Kommt die Zahlung "
        "binnen 14 Tagen nicht an, kannst du babu bis dahin weiter ansehen und "
        "herunterladen, aber nichts Neues erfassen. Deine Belege bleiben "
        "vollständig erhalten.\n\n"
        "4. Verfügbarkeit. babu ist ein Erprobungsdienst. Wir bemühen uns um einen "
        "verlässlichen Betrieb, sichern die Daten täglich und beheben Fehler zügig, "
        "können aber keine bestimmte Verfügbarkeit zusagen. Bewahre Originalbelege "
        "so auf, wie es die Aufbewahrungspflicht verlangt.\n\n"
        "5. Haftung. Wir haften für Vorsatz und grobe Fahrlässigkeit sowie bei "
        "Verletzung von Leben, Körper und Gesundheit. Bei einfacher Fahrlässigkeit "
        "haften wir nur für die Verletzung wesentlicher Pflichten und beschränkt "
        "auf den vorhersehbaren, typischen Schaden. Für Ergebnisse der "
        "automatischen Belegerkennung übernehmen wir keine Gewähr; prüfe sie, "
        "bevor du dich darauf verlässt.\n\n"
        "6. Ende. Du kannst die Nutzung jederzeit beenden: ein Abo zum Ende des "
        "bezahlten Monats im Portal, sonst indem du uns schreibst. Wir können mit "
        "einer Frist von vier Wochen beenden. Nach dem Ende kannst du deine "
        "Ablage weiter ansehen und herunterladen; auf Wunsch bekommst du sie als "
        "geordnete Ablage ausgehändigt.\n\n"
        "7. Änderungen. Änderungen dieser Bedingungen teilen wir dir per E-Mail "
        "mit; sie gelten, wenn du danach weiter nutzt oder ausdrücklich zustimmst.\n\n"
        "Es gilt deutsches Recht."),
}

ARTEN = tuple(TEXTE)

#: Die Vereinbarung mit den Ambassadorinnen (seit 03.10.2026) — eigene Seite
#: unter /ambassador/vereinbarung, NICHT in ARTEN: sie gilt nur für sie und
#: gehört nicht in die Rechtliches-Leiste von App und Portal.
AMBASSADOR: tuple[str, str] = ("Ambassador-Vereinbarung",
    "Erprobungsfassung (Stand 03.10.2026). Der verbindliche Wortlaut wird vor "
    "dem allgemeinen Start rechtlich und steuerlich geprüft.\n\n"
    "Zwischen 0711 Intelligence (siehe Impressum, „babu“) und dir als "
    "Ambassadorin.\n\n"
    "1. Worum es geht. Du empfiehlst babu an Betriebe, die du kennst. Du bist "
    "dabei frei: keine Weisungen, keine Mindestzahlen, kein Arbeitsverhältnis. "
    "Du handelst in eigenem Namen und darfst keine Verträge für babu "
    "schließen.\n\n"
    "2. Provision. Schließt ein Betrieb, der über deinen Link gekommen ist, ein "
    "bezahltes Abo ab, bekommst du 25 % von zwölf Netto-Monatspreisen seines "
    "Pakets, sobald die erste Monatsrechnung bezahlt ist, und noch einmal 25 %, "
    "sobald die dritte bezahlt ist. Beispiel Paket Salon (79 € netto): zweimal "
    "237 €. Für den eigenen Betrieb gibt es keine Provision. Anteilige "
    "Rechnungen bei einem Paketwechsel zählen nicht als Monat.\n\n"
    "3. Rückbuchung. Wird eine Zahlung zurückgebucht oder erstattet, für die "
    "eine Provision gebucht wurde, entfällt diese Provision. Sie wird mit "
    "späteren Provisionen verrechnet; ist schon ausgezahlt und folgt nichts "
    "mehr nach, melden wir uns.\n\n"
    "4. Auszahlung. Wir zahlen vierteljährlich am 15. Januar, April, Juli und "
    "Oktober aus, was bis zum Ende des Vorquartals verdient ist, sobald es "
    "mindestens 100 € sind; darunter kommt es mit dem nächsten Mal. "
    "Voraussetzung sind deine vollständigen Angaben zu Konto, Anschrift und "
    "Steuerstatus in babu.\n\n"
    "5. Abrechnung per Gutschrift. Du bist einverstanden, dass babu deine "
    "Provision per Gutschrift abrechnet (§ 14 Abs. 2 Satz 2 UStG); du stellst "
    "keine eigene Rechnung. Bist du umsatzsteuerpflichtig, kommt die "
    "Umsatzsteuer dazu; als Kleinunternehmerin (§ 19 UStG) oder als "
    "Privatperson ohne Umsatzsteuer. Du kannst der Gutschrift widersprechen; "
    "dann stellst du selbst eine Rechnung. Änderungen deines Steuerstatus "
    "trägst du in babu ein. Für deine eigenen Steuern bist du selbst "
    "verantwortlich.\n\n"
    "6. Empfehlen mit Anstand. Schreib nur Menschen an, die dich kennen und mit "
    "einer Nachricht von dir rechnen. Keine Massennachrichten, keine Werbung in "
    "fremden Gruppen, keine Versprechen, die babu nicht hält (babu ersetzt "
    "zum Beispiel keine Steuerberatung). babu schreibt deine Kontakte nicht von "
    "sich aus an; die vorbereiteten Nachrichten verschickst du selbst.\n\n"
    "7. Was du siehst. Für die Betriebe, die du eingeladen hast, siehst du den "
    "Stand und wie aktiv sie sind (Anzahl der Belege, letzter Tag) — nie ihre "
    "Belege, Beträge oder Zahlen. Diese Angaben behältst du für dich.\n\n"
    "8. Ende. Du und wir können jederzeit beenden, per E-Mail. Was bis dahin "
    "verdient ist, zahlen wir mit dem nächsten Lauf aus.\n\n"
    "9. Änderungen. Änderungen dieser Vereinbarung teilen wir dir vier Wochen "
    "vorher per E-Mail mit; du kannst bis dahin beenden.\n\n"
    "Es gilt deutsches Recht.")


#: Hilfe (seit 03.10.2026) — die Support-Adresse der App im App Store. Kurz,
#: in Alltagssprache, und immer mit dem Weg zu einem Menschen.
HILFE: tuple[str, str] = ("Hilfe",
    "Hier stehen die häufigsten Fragen. Wenn deine nicht dabei ist: schreib uns "
    "an hallo@0711.io — wir antworten an Werktagen innerhalb eines Tages.\n\n"
    "Wie komme ich zu babu? Über die Einladung deines Steuerbüros, über den Link "
    "einer Ambassadorin (30 Tage kostenlos testen) oder über die Warteliste auf "
    "mybabu.io. Du bekommst eine E-Mail mit einem Link, mit dem du dein Passwort "
    "festlegst.\n\n"
    "Ich habe mein Passwort vergessen. Auf der Anmeldeseite auf „Passwort "
    "vergessen?“ tippen — du bekommst einen Link per E-Mail.\n\n"
    "Wie kommen Belege zu babu? In der App den Beleg fotografieren — fertig. Im "
    "Portal auf mybabu.io kannst du PDFs hochladen.\n\n"
    "Was kostet babu? Der Testmonat ist kostenlos und endet von selbst. Danach "
    "gibt es drei Pakete: Solo 39 €, Salon 79 € und Salon Plus 149 € im Monat, "
    "jeweils zuzüglich Umsatzsteuer, monatlich kündbar.\n\n"
    "Wie kündige ich? Im Portal unter „Weitermachen“ → „Abo verwalten“, jederzeit "
    "zum Ende des bezahlten Monats. Deine Belege kannst du danach weiter ansehen "
    "und herunterladen.\n\n"
    "Sieht mein Steuerbüro meine Belege? Ja, wenn es deinen Betrieb in babu "
    "betreut. Sonst niemand.\n\n"
    "Ich bin Ambassadorin — wann kommt mein Geld? Vierteljährlich am 15. Januar, "
    "April, Juli und Oktober, ab 100 €. Trag dafür in deinem Bereich unter „Wohin "
    "soll dein Geld?“ deine Kontodaten ein.\n\n"
    "Etwas funktioniert nicht. In der App eine Rückmeldung schicken — mit einem "
    "Satz, was du gemacht hast. Oder schreib an "
    "hallo@0711.io.")


#: Freigabe der Kontoumsätze für die Kanzlei (seit 04.10.2026, Plan
#: Kanzleiansicht B1). Erprobungsfassung — der Wortlaut wird vor dem
#: Einschalten (`BABU_BANK_FREIGABE=1`) rechtlich geprüft.
BANK_FREIGABE: tuple[str, str] = ("Kontoumsätze für dein Steuerbüro",
    "Erprobungsfassung (Stand 04.10.2026).\n\n"
    "Mit dieser Freigabe darf dein Steuerbüro in babu die Umsätze der Konten "
    "ansehen, die du in babu ablegst oder verbindest — um Belege und Zahlungen "
    "abzugleichen, fehlende Belege zu finden und offene Rechnungen zu sehen.\n\n"
    "Dein Steuerbüro kann damit nur lesen. Es kann keine Zahlung auslösen, "
    "nichts an deinen Kontoauszügen ändern und nichts löschen.\n\n"
    "Die Freigabe gilt nur für dein Steuerbüro in babu, niemanden sonst. Du "
    "kannst sie jederzeit widerrufen; danach sieht es die Umsätze nicht mehr.")


def fassung(art: str) -> str:
    """Kurzer Fingerabdruck eines Rechtstexts — gespeichert bei jeder
    Zustimmung, damit sich später sagen lässt, WELCHER Fassung zugestimmt
    wurde. `art`: ein Schlüssel aus TEXTE, "ambassador" oder "bank_freigabe"."""
    import hashlib  # noqa: PLC0415
    titel, text = (AMBASSADOR if art == "ambassador"
                   else BANK_FREIGABE if art == "bank_freigabe" else TEXTE[art])
    return hashlib.sha256((titel + text).encode("utf-8")).hexdigest()[:12]


def fertig(art: str | None = None) -> bool:
    """Ist der Text kein Platzhalter mehr? Ohne Art: alle drei."""
    arten = [art] if art else list(ARTEN)
    return all(not TEXTE[a][1].startswith(PLATZHALTER) for a in arten)


def als_json() -> dict:
    return {a: {"titel": t, "text": x, "fertig": fertig(a)} for a, (t, x) in TEXTE.items()}


def seite(art: str) -> str:
    """Eine eigenständige Seite im Ton der Landing-Seite — ohne Skript, ohne
    Anmeldung, damit Apple und jede Nutzerin sie ohne Konto lesen können."""
    titel, text = TEXTE[art]
    return seite_aus(titel, text, [(a, TEXTE[a][0]) for a in ARTEN])


def seite_aus(titel: str, text: str, nav: list[tuple[str, str]]) -> str:
    """Dasselbe Blatt für einen Text aus einer ANDEREN Quelle (avv.py).

    `nav` sind die (art, titel)-Paare der Nav-Zeile: die Seiten von avv.py
    verlinken ihre eigenen Geschwister, nicht die von recht.py."""
    absaetze = "".join(f"<p>{html.escape(a.strip())}</p>"
                       for a in text.split("\n\n") if a.strip())
    hinweis = ("" if not text.startswith(PLATZHALTER) else
               '<p class="hinweis">Dieser Text ist noch ein Platzhalter. '
               'Der verbindliche Wortlaut folgt vor dem Start.</p>')
    links = " · ".join(f'<a href="/{a}">{html.escape(t)}</a>' for a, t in nav)
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(titel)} · babu</title>
<style>
  body{{margin:0;background:#faf8f3;color:#2b2a26;font:16px/1.55 -apple-system,system-ui,Georgia,serif}}
  main{{max-width:680px;margin:0 auto;padding:40px 22px 60px}}
  h1{{font:600 30px/1.2 Georgia,'Times New Roman',serif;margin:0 0 18px}}
  p{{margin:0 0 14px}} .hinweis{{padding:12px 14px;background:#f1ebdc;border-radius:10px;font-size:14px}}
  nav{{font-size:13px;color:#736950;margin-bottom:26px}} nav a,footer a{{color:#736950}}
  footer{{margin-top:40px;font-size:13px;color:#8a8273}}
</style></head><body><main>
<nav><a href="/">babu</a> · {links}</nav>
<h1>{html.escape(titel)}</h1>
{hinweis}
{absaetze}
<footer>babu · 0711 Intelligence · Stuttgart · babu ersetzt keine individuelle Steuerberatung.</footer>
</main></body></html>
"""
