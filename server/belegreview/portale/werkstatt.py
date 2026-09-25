"""Das Portal babu Werkstatt — eine Kopie von babu Barber, für Kfz-Werkstätten.

Entstanden am 25.09.2026 als Kopie von `barber.py` und angepasst: Werkstatt
statt Shop, Aufträge statt Termine, die Beispiele im Katalog aus dem Alltag
eines Kfz-Meisters. Held der Seite ist Mario, Kfz-Meister aus dem
Schwäbischen. Verbucht wird wie überall deutsch auf dem deutschen
Kontenrahmen.

Fachlich anders als der Salon: Teile werden beim Kunden eingebaut und
weiterberechnet, Fremdarbeiten (Lackierer, Achsvermessung), Werkzeug und
Hebebühnen (AfA-Tabelle AV), Gebrauchtwagen mit Differenzbesteuerung (§ 25a
UStG), Werkstattpfandrecht (§ 647 BGB), Altöl-Rücknahme (§ 8 AltölV),
Meisterpflicht (HwO Anlage A Nr. 20).
"""
from __future__ import annotations

SCHLUESSEL = "werkstatt"
NAME = "babu Werkstatt"

# Wissenscontainer: ein eigener, vollständiger — Grundstock aus dem
# Friseur-Container ohne dessen Salon-Quellen (91.248 Atome: Kontenplan,
# SKR04, DATEV, BMF, GoBD, Richtsätze, AfA-Tabelle AV, Handwerksstatistik
# Stuttgart) plus 51 Gesetze im amtlichen Wortlaut (ganzes BGB und HGB, AO,
# UStG, EStG, HwO, KfzTechMstrV, StVZO, FZV, AltölV, AltfahrzeugV, KrWG,
# BetrSichV …), gebaut am 25.09.2026 aus `werkzeuge/kompendium/werkstatt/`.
KOMPENDIUM: tuple[str, ...] = ("kompendium-werkstatt",)

# Wörter, die vor der Suche im Container aus der Frage fallen (Regex) — die
# Branche ist im eigenen Portal klar (Befund Barber, 25.09.2026).
SUCH_OHNE = (r"\b(als\s+)?(kfz-?werkstatt|autowerkstatt|kfz-?mechaniker|mechaniker|kfz-?meister|kfz-?betrieb)\b"
             r"|\b(im|in meinem|in meinen|in meiner|meinem|meinen|meiner|mein)\s+(?=[?.!,]|$)")


# ── Buchung ──────────────────────────────────────────────────────────────────

def profil_text(e: dict) -> str:
    """Betriebsprofil + Personenprofil aus den Einstellungen des Betriebs."""
    klein = (e.get("kleinunternehmer") or "Nein").strip().lower() == "ja"
    return (
        f"Werkstatt „{e.get('betrieb_name') or 'unbenannt'}“, Kfz-Werkstatt (Reparatur und Wartung). "
        f"Rechtsform: {e.get('rechtsform') or 'Einzelunternehmen'}. "
        f"Gewinnermittlung: {e.get('abschluss_art') or 'EÜR'}. "
        + ("Kleinunternehmer nach §19 UStG — kein Vorsteuerabzug. "
           if klein else
           "Kein Kleinunternehmer — Vorsteuerabzug, soweit ausgewiesen. ")
        + "Der Inhaber arbeitet selbst in der Werkstatt und führt ein tägliches "
          "Kassenbuch; Bareinnahmen sind dort bereits erfasst."
    )


# Der erste Satz des stehenden Buchungs-Vorspanns.
BUCHUNG_AUFTRAG = ("Du bist die Buchhaltung einer Kfz-Werkstatt und verbuchst genau "
                   "EINEN Beleg.\n\n")

# Vor die Sachwörter eines Belegs, wenn im Kompendium nachgeschlagen wird.
NACHSCHLAG_PRAEFIX = "Nutzungsdauer und Kontierung in der Kfz-Werkstatt: "

# Kategorie-Code → Hinweis im Katalog des Vorspanns. Die buchhalterische
# Aussage bleibt die des Katalogs, nur die Beispiele sind die einer Werkstatt.
# Nie eine Kontonummer.
KATEGORIE_HINWEISE: dict[str, str] = {
    "wareneinkauf": "Teile, die beim Kunden eingebaut oder an ihn verkauft werden: Ersatzteile, "
                    "Reifen, Motoröl, Batterien, Wischerblätter.",
    "verbrauchsmaterial": "Wird in der Werkstatt aufgebraucht und nicht einzeln weiterberechnet: "
                          "Bremsenreiniger, Putzlappen, Handschuhe, Ölbindemittel, Kleinteile.",
    "materialeinsatz": "Wird im Kundenauftrag verarbeitet und geht mit dem Auto mit: Kältemittel, "
                       "Schrauben und Schellen, Kleber, Lack für Ausbesserungen. Wareneinsatz.",
    "fremdleistung": "Fremdarbeiten für Kundenaufträge: Lackierer, Achsvermessung, Getriebe- oder "
                     "Motorinstandsetzung, Abschleppdienst, Glaser.",
    "reinigung": "Werkstattreinigung, Arbeitskleidung-Service, Ölabscheider-Leerung laufen bei "
                 "manchen Betrieben über Fremdleistung — einmal festlegen.",
    "dekoration": "Pflanzen, Bilder, Ausstattung für Kundenwarteraum und Theke — sie bleiben in der "
                  "Werkstatt. Was ein Kunde mitbekommt, ist geschenk; was er dort verzehrt, ist aufmerksamkeit.",
    "bewirtung": "Echte Bewirtung außer Haus oder mit Anlass und Teilnehmern (70 % abziehbar). "
                 "Kaffee und Wasser für wartende Kunden in der Werkstatt sind KEINE Bewirtung — das ist aufmerksamkeit.",
    "aufmerksamkeit": "Kaffee, Wasser, Süßes für wartende Kunden in der Werkstatt, dort verzehrt — "
                      "voll abziehbar, kein 70/30. Was der Kunde mitnimmt, ist geschenk.",
    "werkzeug": "Schraubenschlüssel, Drehmomentschlüssel, Druckluftwerkzeug, Messzeug — unter der "
                "GWG-Grenze sofort Aufwand, darüber Anlagevermögen (Hebebühne, Kompressor, Diagnosegerät).",
}


# ── Expertenchat ─────────────────────────────────────────────────────────────

CHAT_ROLLE = (
    "Du bist der Assistent von babu (0711 Intelligence) für "
    "Kfz-Werkstätten. Du sprichst mit dem Inhaber. Antworte auf "
    "Deutsch, knapp, konkret und in ganzen Sätzen. Keine "
    "Sie-Anrede — neutrale Formen oder Du. Kein Technik-Vokabular, "
    "keine Systemnamen.\n\n"
    "DU BIST FÜR ALLES DA, was seinen Betrieb angeht — nicht nur "
    "für Steuern:\n"
    "· Seine eigenen Zahlen und Unterlagen: Belege, Kasse, "
    "Verträge, gestellte Rechnungen, Aufträge, Team, Post vom Amt. "
    "Das beantwortest du AUSSCHLIESSLICH aus den mitgelieferten "
    "Daten und nennst, worauf du dich stützt. Steht etwas nicht "
    "darin, sagst du das offen und rätst nicht.\n"
    "· Steuer und Recht im Werkstatt-Alltag: Kleinunternehmer-Regel, "
    "Kassenpflicht und Kassen-Nachschau, Gebrauchtwagen und "
    "Differenzbesteuerung, Werkstattpfandrecht, Gewährleistung, "
    "Meisterpflicht, Altöl und Altfahrzeuge, Prüfung von Hebebühnen, "
    "was absetzbar ist, Aufbewahrung, Fristen. Einfach erklärt, mit dem "
    "Hinweis, dass es eine erste Einordnung ist.\n"
    "· Führen und Organisieren: Stundenverrechnungssatz und "
    "Kalkulation, Auftragsplanung, Auslastung der Bühnen, Personal "
    "und Ausbildung, Teileeinkauf und Lieferanten, Kundenbindung, "
    "Reklamationen, schwierige Gespräche, Werbung, Arbeitsschutz "
    "und Umgang mit Gefahrstoffen.\n"
    "· Und wenn ihm der Kopf raucht: hör zu, ordne, und mach "
    "einen ersten Schritt daraus. Er führt einen Betrieb oft allein "
    "— oft ist die Frage hinter der Frage die wichtigere.\n\n"
    "SO ANTWORTEST DU: Erst die Antwort, dann die Begründung. "
    "Beträge deutsch (1.234,56 €). Wenn du rechnest, zeig die "
    "Rechnung. Bei mehreren Möglichkeiten nenne eine Empfehlung, "
    "keine Liste von Optionen.\n\n"
    "DEINE GRENZEN, und du benennst sie: Du bist keine "
    "Steuerberatung, keine Rechtsberatung und keine ärztliche "
    "Auskunft. Bei Kündigungen, Verträgen mit Folgen, "
    "Betriebsprüfungen, Streit mit dem Finanzamt und allem, wo "
    "Fristen laufen, verweist du auf seine Ansprechperson — und "
    "sagst trotzdem, was du zur Sache weißt, damit er "
    "vorbereitet ins Gespräch geht. Erfinde nie Zahlen, Paragrafen "
    "oder Fristen. Was du nicht weißt, sagst du.\n\n"
    "Wenn bei der Frage etwas NACHGESCHLAGEN mitkommt, stützt du "
    "dich darauf und nennst die Quelle in Klammern."
)

CHAT_AUFTRAG_ALLGEMEIN = (
    "ALLGEMEINE FRAGE — beantworte sie aus deinem Wissen, nicht aus seinen "
    "Unterlagen. Er hat kein Steuerbüro mehr, das er kurz anrufen kann; "
    "erklär jedes Fachwort in einem Nebensatz. Schreib NICHT, dass die "
    "Antwort nicht in seinen Unterlagen steht — danach ist nicht gefragt. "
    "Die Werkstatt-Angaben oben sind nur Hintergrund.\n\n"
)

CHAT_WISSENSTITEL = ("GRUNDWISSEN ZUR BRANCHE (Kfz-Werkstatt — "
                     "destilliert, erste Einordnung):")
CHAT_WELTTITEL = "WAS BABU ÜBER DIESE WERKSTATT WEISS:"
