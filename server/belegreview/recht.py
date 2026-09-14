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
        "Erprobungsfassung (Stand 14.09.2026). Diese Erklärung beschreibt, was "
        "während des Pilotbetriebs mit deinen Angaben geschieht.\n\n"
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
        "Telefon dort trennen. Ein neues Passwort beendet alle Sitzungen."),
    "agb": ("Nutzungsbedingungen",
        "Erprobungsfassung (Stand 14.09.2026). Diese Bedingungen gelten für den "
        "Pilotbetrieb von babu.\n\n"
        "1. Was babu ist. babu nimmt Belege auf, liest sie, ordnet sie ein und legt "
        "sie geordnet ab, damit deine Steuerkanzlei damit arbeiten kann. babu gibt "
        "keine steuerliche oder rechtliche Beratung. Vorschläge zur Einordnung "
        "eines Belegs sind Hilfen, keine Entscheidungen; die Verantwortung für die "
        "Buchführung bleibt bei dir und deiner Kanzlei.\n\n"
        "2. Zugang. Den Zugang bekommst du auf Einladung. Du hältst dein Passwort "
        "geheim und meldest uns, wenn du einen Missbrauch vermutest. Du darfst nur "
        "Belege deines eigenen Betriebs einreichen.\n\n"
        "3. Kosten. Die Nutzung ist während der Erprobung kostenlos. Vor einem "
        "Wechsel in einen bezahlten Betrieb informieren wir dich mit mindestens "
        "vier Wochen Vorlauf; ohne deine Zustimmung entstehen keine Kosten.\n\n"
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
        "6. Ende. Du kannst die Nutzung jederzeit beenden, indem du uns schreibst. "
        "Wir können die Erprobung mit einer Frist von vier Wochen beenden. Deine "
        "Belege bekommst du auf Wunsch als geordnete Ablage ausgehändigt.\n\n"
        "7. Änderungen. Änderungen dieser Bedingungen teilen wir dir per E-Mail "
        "mit; sie gelten, wenn du danach weiter nutzt oder ausdrücklich zustimmst.\n\n"
        "Es gilt deutsches Recht."),
}

ARTEN = tuple(TEXTE)


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
    absaetze = "".join(f"<p>{html.escape(a.strip())}</p>"
                       for a in text.split("\n\n") if a.strip())
    hinweis = ("" if fertig(art) else
               '<p class="hinweis">Dieser Text ist noch ein Platzhalter. '
               'Der verbindliche Wortlaut folgt vor dem Start.</p>')
    links = " · ".join(f'<a href="/{a}">{html.escape(TEXTE[a][0])}</a>' for a in ARTEN)
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
