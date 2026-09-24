"""Das Portal babu Barber — eine Kopie von babu Friseur, für Barbershops.

Entstanden am 24.09.2026 als Kopie von `friseur.py` und angepasst: Barbershop
statt Salon, Inhaber statt Inhaberin, Kunden statt Kundinnen, die Beispiele
im Katalog aus dem Alltag eines Barbers. Die Zielgruppe ist zuerst die
türkische Barber-Community: Bedienung und Erklärungen gibt es auch auf
Türkisch — verbucht wird aber immer DEUTSCH auf dem deutschen Kontenrahmen.
Darum steht hier alles, was ans Modell geht, auf Deutsch.

Fachlich ist ein Barbershop ein Friseurbetrieb: dieselbe AfA-Tabelle
(Nr. 94 „Friseurgewerbe und Schönheitssalons"), derselbe Kontenrahmen,
dieselbe Richtsatz-Gewerbekennzahl 96021. Anders sind Alltag und Fragen:
Laufkundschaft, viel Bargeld, Klingen und Rasur, Stuhlmiete, Meisterpflicht.
"""
from __future__ import annotations

SCHLUESSEL = "barber"
NAME = "babu Barber"

# Wissenscontainer: ein eigener, vollständiger — Kopie des Friseur-Containers
# (91.459 Atome: Kontenplan, SKR04, DATEV, BMF, GoBD, Richtsätze, AfA) plus
# 8.773 Atome aus 39 Gesetzen im amtlichen Wortlaut (AO, UStG, EStG, HwO,
# Friseurmeister- und Ausbildungsverordnung, SGB IV/VI, MiLoG, JArbSchG,
# PAngV, IfSG, AufenthG …) = 100.232 Atome, gebaut am 25.09.2026 mit
# `werkzeuge/kompendium/container_bauen.py` aus `werkzeuge/kompendium/barber/`.
KOMPENDIUM: tuple[str, ...] = ("kompendium-barber",)

# Wörter, die vor der Suche im Container aus der Frage fallen (Regex) — die
# Branche ist im eigenen Portal klar, und „Barber" in der Frage zieht die
# Suche zu den Friseur-Dokumenten. Genau dieses Muster ist am 25.09.2026
# gemessen (portale.suchfrage, ~/.beleglex/messungen/20260925-barber-container/).
SUCH_OHNE = (r"\b(als\s+)?(barber(shop)?s?|barbier|herrenfriseur|friseur(salon)?|salon)\b"
             r"|\b(im|in meinem|in meinen|meinem|meinen|mein)\s+(?=[?.!,]|$)")


# ── Buchung ──────────────────────────────────────────────────────────────────

def profil_text(e: dict) -> str:
    """Ladenprofil + Personenprofil aus den Einstellungen des Betriebs."""
    klein = (e.get("kleinunternehmer") or "Nein").strip().lower() == "ja"
    return (
        f"Barbershop „{e.get('betrieb_name') or 'unbenannt'}“, Herrenfriseur/Barbier. "
        f"Rechtsform: {e.get('rechtsform') or 'Einzelunternehmen'}. "
        f"Gewinnermittlung: {e.get('abschluss_art') or 'EÜR'}. "
        + ("Kleinunternehmer nach §19 UStG — kein Vorsteuerabzug. "
           if klein else
           "Kein Kleinunternehmer — Vorsteuerabzug, soweit ausgewiesen. ")
        + "Der Inhaber arbeitet selbst im Shop und führt ein tägliches "
          "Kassenbuch; Bareinnahmen sind dort bereits erfasst."
    )


# Der erste Satz des stehenden Buchungs-Vorspanns.
BUCHUNG_AUFTRAG = ("Du bist die Buchhaltung eines Barbershops und verbuchst genau "
                   "EINEN Beleg.\n\n")

# Vor die Sachwörter eines Belegs, wenn im Kompendium nachgeschlagen wird.
# „Friseurgewerbe" bleibt drin: so heißt die AfA-Tabelle, die auch hier gilt.
NACHSCHLAG_PRAEFIX = "Nutzungsdauer und Kontierung im Barbershop (Friseurgewerbe): "

# Kategorie-Code → Hinweis, der im Katalog des Vorspanns den Hinweis aus
# `kontierung.py` ersetzt. Die buchhalterische Aussage bleibt dieselbe, nur
# die Beispiele sind die eines Barbers. Nie eine Kontonummer.
KATEGORIE_HINWEISE: dict[str, str] = {
    "wareneinkauf": "Ware, die der Kunde mitnimmt: Pomade, Bartöl, Aftershave, Haarwachs.",
    "verbrauchsmaterial": "Wird im Shop aufgebraucht: Klingen, Nackenpapier, "
                          "Rasierschaum, Desinfektion, Handschuhe.",
    "materialeinsatz": "Wird in der Dienstleistung verarbeitet und geht mit dem "
                       "Kunden mit: Haarfarbe, Bartfarbe, Haarsysteme. Wareneinsatz.",
    "fremdleistung": "Stuhlmiete, freier Barber, Subunternehmer.",
    "reinigung": "Handtuchservice und Mietwäsche laufen bei manchen Betrieben über "
                 "Fremdleistung — einmal festlegen.",
    "dekoration": "Pflanzen, Bilder, Spiegel-Deko, Saisonschmuck für den Shop — sie "
                  "bleiben im Shop. Was ein Kunde mitbekommt, ist geschenk; was er im "
                  "Shop verzehrt, ist aufmerksamkeit.",
    "bewirtung": "Echte Bewirtung außer Haus oder mit Anlass und Teilnehmern (70 % "
                 "abziehbar). Tee, Kaffee und Wasser für Kunden im Shop sind KEINE "
                 "Bewirtung — das ist aufmerksamkeit.",
    "aufmerksamkeit": "Tee, Kaffee, Wasser, Süßes für Kunden im Shop, dort verzehrt — "
                      "voll abziehbar, kein 70/30. Was der Kunde mitnimmt, ist geschenk.",
    "werkzeug": "Scheren, Clipper, Trimmer, Rasiermesser, Föhn — unter der GWG-Grenze "
                "sofort Aufwand, darüber Anlagevermögen.",
}


# ── Expertenchat ─────────────────────────────────────────────────────────────

CHAT_ROLLE = (
    "Du bist der Assistent von babu (0711 Intelligence) für "
    "Barbershops. Du sprichst mit dem Inhaber. Antworte auf "
    "Deutsch, knapp, konkret und in ganzen Sätzen. Keine "
    "Sie-Anrede — neutrale Formen oder Du. Kein Technik-Vokabular, "
    "keine Systemnamen.\n\n"
    "DU BIST FÜR ALLES DA, was seinen Betrieb angeht — nicht nur "
    "für Steuern:\n"
    "· Seine eigenen Zahlen und Unterlagen: Belege, Kasse, "
    "Verträge, gestellte Rechnungen, Termine, Team, Post vom Amt. "
    "Das beantwortest du AUSSCHLIESSLICH aus den mitgelieferten "
    "Daten und nennst, worauf du dich stützt. Steht etwas nicht "
    "darin, sagst du das offen und rätst nicht.\n"
    "· Steuer und Recht im Shop-Alltag: Kleinunternehmer-Regel, "
    "Kassenpflicht und Kassennachschau, Bargeld, Meisterpflicht, "
    "Stuhlmiete, was absetzbar ist, Aufbewahrung, Fristen. "
    "Einfach erklärt, mit dem Hinweis, dass es eine erste "
    "Einordnung ist.\n"
    "· Führen und Organisieren: Preise und Kalkulation, "
    "Laufkundschaft und Termine, Auslastung, Personal und Ausbildung, "
    "Einkauf und Lieferanten, Kundenbindung, Reklamationen, "
    "schwierige Gespräche, Werbung, Hygiene und Arbeitsschutz.\n"
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

# Zusatzauftrag, wenn die Frage allgemein ist und nicht den eigenen Bestand
# betrifft.
CHAT_AUFTRAG_ALLGEMEIN = (
    "ALLGEMEINE FRAGE — beantworte sie aus deinem Wissen, nicht aus seinen "
    "Unterlagen. Er hat kein Steuerbüro mehr, das er kurz anrufen kann; "
    "erklär jedes Fachwort in einem Nebensatz. Schreib NICHT, dass die "
    "Antwort nicht in seinen Unterlagen steht — danach ist nicht gefragt. "
    "Die Shop-Angaben oben sind nur Hintergrund.\n\n"
)

# Überschriften der beiden stehenden Blöcke im Chat.
CHAT_WISSENSTITEL = ("GRUNDWISSEN ZUR BRANCHE (Barbershop und Herrenfriseur — "
                     "destilliert, erste Einordnung):")
CHAT_WELTTITEL = "WAS BABU ÜBER DIESEN SHOP WEISS:"
