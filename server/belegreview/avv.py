#!/usr/bin/env python3
"""Der Auftragsverarbeitungsvertrag (AVV) als Text und PDF.

Art. 28 DSGVO verlangt den Vertrag in Textform zwischen der verantwortlichen
Stelle (der Betrieb, der Belege einreicht) und dem Auftragsverarbeiter
(babu, Anbieter siehe Impressum). Die Pflichtangaben stehen alle drin —
in derselben Sprache wie die anderen Rechtstexte (recht.py): klares
Deutsch, Erprobungsfassung, keine anwaltliche Endprüfung (Klammer wie
überall: geprüft vor dem allgemeinen Start).

Der Text ist EINE Quelle (TEXTE hier), das PDF wird daraus erzeugt und
unter /app/avv.pdf ausgeliefert; der Betriebsteil ist bewusst austauschbar
(PARTEI_BETRIEB), damit der nächste Betrieb nur diesen Block tauscht.
"""
from __future__ import annotations

ANBIETER = ("0711 Intelligence, Christoph Bertsch, Stuttgart — "
            "Kontakt: nina@0711.io")

PARTEI_BETRIEB = {
    "name": "SupremeStudio (Nina Baic, Einzelunternehmen)",
    "anschrift": "Lindenstraße 2, 71634 Ludwigsburg",
    "vertretung": "Nina Baic (Inhaberin)",
    "kontakt": "nina@0711.io",
    "steuernummer": "71015/73457 (Finanzamt Ludwigsburg)",
    "beginn": "mit der Einladung des Betriebs zu babu (Pilotbetrieb seit August 2026)",
}

TEXTE: dict[str, tuple[str, str]] = {
    "avv": ("Auftragsverarbeitungsvertrag",
        "Erprobungsfassung (Stand 17.09.2026). Die Angaben gelten für die Zeit "
        "des Pilotbetriebs; der verbindliche Wortlaut wird vor dem allgemeinen "
        "Start rechtlich geprüft.\n\n"
        "Zwischen\n\n"
        f"    {PARTEI_BETRIEB['name']}\n"
        f"    {PARTEI_BETRIEB['anschrift']}\n"
        f"    Vertretung: {PARTEI_BETRIEB['vertretung']}\n"
        f"    Kontakt: {PARTEI_BETRIEB['kontakt']}\n"
        f"    Steuernummer: {PARTEI_BETRIEB['steuernummer']}\n\n"
        "— der verantwortlichen Stelle, nachfolgend „der Betrieb“ —\n\n"
        "und\n\n"
        f"    {ANBIETER}\n\n"
        "— dem Auftragsverarbeiter, nachfolgend „babu“ —\n\n"
        f"gilt folgender Vertrag. Beginn der Verarbeitung: {PARTEI_BETRIEB['beginn']}.\n\n"
        "1. Gegenstand und Umfang. Der Betrieb reicht Belege (Fotos, PDFs), "
        "Kontoauszüge und Betriebsangaben über die babu-App und das babu-Portal "
        "ein. babu liest die Belege, ordnet sie ein, legt sie in der Ablage des "
        "Betriebs ab und stellt sie der Steuerkanzlei des Betriebs zur "
        "Verfügung, wenn der Betrieb das eingerichtet hat. babu verarbeitet die "
        "Daten ausschließlich im Auftrag und nach den Weisungen des Betriebs.\n\n"
        "2. Zweck. Ordnungsgemäße Aufnahme, Lesung, Einordnung und Ablage der "
        "Buchführungsunterlagen des Betriebs sowie Bereitstellung für dessen "
        "Steuerkanzlei. Eine Verarbeitung für eigene Zwecke von babu findet "
        "nicht statt; besonders keine Weitergabe an Dritte, kein Verkauf, "
        "keine Werbung.\n\n"
        "3. Kategorien und Personen. Verarbeitet werden Belege und deren "
        "gelesener Inhalt, Kontoauszüge, Termin- und Kundenangaben (sofern "
        "genutzt) sowie Zugangsdaten (E-Mail, Name, Passwort-Prüfsumme, "
        "Gerätekennungen). Betroffen sein können Kundinnen und Mitarbeiter des "
        "Betriebs, soweit deren Angaben auf Belegen stehen.\n\n"
        "4. Ort. Alle Daten liegen auf einem eigenen Rechner des Anbieters in "
        "Deutschland. Das Lesen der Belege geschieht ebenfalls dort; kein Beleg "
        "wird an einen fremden Dienst zur Auswertung gegeben. E-Mails "
        "(Passwort zurücksetzen, Einladungen) gehen über einen Versanddienst "
        "mit Verarbeitung in der EU (§ 9).\n\n"
        "5. Weisungsrecht. Der Betrieb kann Art, Umfang und Zweck der "
        "Verarbeitung jederzeit einsehen und ändern — durch E-Mail an "
        "nina@0711.io oder direkt im Portal (Löschen, Export, Trennen von "
        "Geräten). Babu setzt Weisungen unverzüglich um; hält babu eine "
        "Weisung für rechtswidrig, weist es den Betrieb schriftlich darauf "
        "hin, führt sie aber nicht eigenmächtig fort.\n\n"
        "6. Vertraulichkeit. Nur Personen, die den Betrieb betreuen, sehen "
        "dessen Belege. Jede Person ist zur Verschwiegenheit verpflichtet. "
        "Die Steuerkanzlei des Betriebs sieht die Belege des Betriebs, wenn "
        "der Betrieb sie in babu betreut.\n\n"
        "7. Sicherheit. Babu sichert die Daten täglich, hält Zugänge mit "
        "Passwörtern und Geräteschlüsseln getrennt, beendet Sitzungen bei "
        "neuen Passwörtern und speichert Passwörter nur als Prüfsumme. "
        "Technische Protokolle werden nach 30 Tagen, Sicherungskopien nach "
        "14 Tagen überschrieben.\n\n"
        "8. Mitteilungspflichten. Babu teilt dem Betrieb Verstöße gegen "
        "Schutz der Daten unverzüglich mit. Ein Datenpannen-Verdacht wird "
        "dem Betrieb innerhalb von 24 Stunden gemeldet, mit dem Stand und "
        "den Maßnahmen.\n\n"
        "9. Unterbeauftragte. Der E-Mail-Versanddienst (Verarbeitung in der "
        "EU) ist der einzige Unterbeauftragte. Der Betrieb wird über neue "
        "Unterbeauftragte vorab informiert und kann widersprechen.\n\n"
        "10. Kontrollrechte. Der Betrieb kann die Einhaltung dieser "
        "Vereinbarung prüfen — nach Terminabsprache und ohne Betriebssperrung. "
        "Babu dokumentiert auf Anfrage, welche Daten des Betriebs wo liegen.\n\n"
        "11. Löschung und Rückgabe. Nach Ende des Auftrags übergibt babu dem "
        "Betrieb dessen Ablage als geordnete Daten und löscht die Kopien, "
        "soweit keine gesetzliche Aufbewahrungspflicht entgegensteht; bis "
        "dahin werden Daten gesperrt. Kontoauszüge und Belege sind "
        "Buchführungsunterlagen und bleiben so lange, wie es das Recht "
        "verlangt.\n\n"
        "12. Haftung. Wie in den Nutzungsbedingungen: volle Haftung für "
        "Vorsatz und grobe Fahrlässigkeit sowie Verletzung von Leben, Körper "
        "und Gesundheit; bei einfacher Fahrlässigkeit nur für wesentliche "
        "Pflichten, beschränkt auf den typischen Schaden.\n\n"
        "13. Laufzeit. Für die Zeit des Pilotbetriebs und darüber hinaus bis "
        "die Löschung nach § 11 vollständig durchgeführt ist. Jede Seite kann "
        "mit vier Wochen Frist kündigen; die Löschung und Rückgabe bleibt "
        "hiervon unberührt.\n\n"
        "Es gilt deutsches Recht."),
}

ARTEN = tuple(TEXTE)


def fertig(art: str | None = None) -> bool:
    """Rechtstexte lückenlos? (PLATZHALTER-Konvention wie recht.py)."""
    arten = (art,) if art else ARTEN
    return all(not TEXTE[a][1].startswith("Text folgt.") for a in arten)
