#!/usr/bin/env python3
"""
doc_classify — EIN harmonisierter Dokument-Klassifikator für alle Fälle
======================================================================
Erkennt Belegtypen aus dem (PaddleOCR-)Text. Wird von profile.py und den Mappern
gemeinsam genutzt, damit alle Fälle dieselbe Typ-Logik verwenden.
Reihenfolge: spezifischste Muster zuerst.
"""


VAST_TYPES = ("lohnsteuerbescheinigung", "religionszugehörigkeit", "kapitalerträge",
              "rentenbezugsmitteilung", "beitragsbescheinigung kranken")


def classify_doc(text, name="", pages=1):
    t = (name + "\n" + text).lower()

    # === Kombinierter VAST-Belegabruf zuerst ===
    # Mehrere Bescheinigungen in EINEM PDF (nummerierte Lohnsteuerzeilen) -> extract_vast.
    # Erkennung: "Transferticket" + >=2 verschiedene Bescheinigungstypen. Muss VOR dem
    # Seitenzahl-Gate stehen (kombinierte VAST hat oft >=4 Seiten, ist aber KEINE ESt).
    if "transferticket" in t and sum(1 for k in VAST_TYPES if k in t) >= 2:
        return "VAST/Belegabruf"

    # === Zusammengesetzte Mehrseiten-Dokumente ===
    # (Vollständige Erklärungen/Berechnungen/Bescheide bündeln oft die Einzelbelege
    #  und enthalten daher ALLE Stichworte. Seitenzahl >=4 oder starke Titelmarker
    #  unterscheiden sie zuverlässig von 1-2-seitigen Einzelbelegen.)
    composite = pages >= 4 or "nur für ihre unterlagen" in t or "steuerberechnung" in t
    if composite:
        if "einkommensteuerbescheid" in t or "steuerbescheid" in t or "bescheid für 20" in t:
            return "Steuerbescheid"
        if "steuerberechnung" in t or "festgesetzt werden" in t or "nur für ihre unterlagen" in t:
            return "ESt-Berechnung"
        if "hauptvordruck est" in t or "einkommensteuererklärung" in t:
            return "Einkommensteuererklärung"

    # === VAST/Belegabruf-Einzelbelege (kurz): "Transferticket"-Kopf ===
    if "transferticket" in t and pages <= 3:
        if "rentenbezugsmitteilung" in t:
            return "Rentenbezugsmitteilung"
        if "beitragsbescheinigung kranken" in t:
            return "Kranken-/Pflegeversicherung"
        if "religionszugehörigkeit" in t:
            return "Religionszugehörigkeit"
        if "kapitalerträge mit freistellungsauftrag" in t or "freigestellte kapitalerträge" in t:
            return "Kapitalerträge (freigestellt)"
        if "stammdaten" in t and ("steuerkontoinhaber" in t or "persönliche angaben" in t):
            return "Stammdaten"
        if "lohnsteuerbescheinigung" in t:
            return "Lohnsteuerbescheinigung"
        return "VAST/Belegabruf (sonstig)"

    # === Spenden / Zuwendungen (formale Bestätigungstitel) ===
    if ("zuwendungsbestätigung" in t or "zuwendungsbestaetigung" in t
            or "spendenbescheinigung" in t or "geldzuwendung" in t
            or "bestätigung über die zuwendung" in t or "bestätigung über geldzuwendung" in t):
        return "Spendenbescheinigung"

    # === Beitragsbescheinigung Kranken-/Pflegeversicherung (privat, ohne VaSt-Header) ===
    # (Debeka & Co. schicken eigene Beitragsbescheinigungen ohne Transferticket/VaSt-Kopf.)
    if "beitragsbescheinigung" in t and ("krankenversicherung" in t or "pflegeversicherung" in t
                                          or "pflegepflichtversicherung" in t):
        return "Kranken-/Pflegeversicherung"

    # === Kapitalerträge ohne Steuerabzug (Zinsen aus Privat-/Wohndarlehen, Anlage KAP) ===
    if ("wohndarlehen" in t or "verzinsung des wohndarlehens" in t
            or ("zinsertrag" in t and "darlehen" in t)):
        return "Kapitalerträge ohne Steuerabzug"

    # === Haushaltsnahe Aufwendungen / § 35a (Dienstleistungen, Pflege/Betreuung, Handwerker) ===
    if (("haushaltsnah" in t or "35a" in t)
            and ("dienstleistung" in t or "handwerker" in t or "betreuung" in t
                 or "pflege" in t or "aufwendungen" in t)):
        return "Haushaltsnahe Dienstleistungen"

    # === ELSTER-XML ===
    if "<elster" in t and "finkonsens" in t:
        return "ELSTER-XML"

    # === Standalone / Anlage-N Lohnsteuerbescheinigung ===
    # (VOR der Bank-Regel, da "steuerbescheinigung" ein Teilstring von
    #  "Lohnsteuerbescheinigung" ist — sonst Fehlklassifikation als Bank.)
    if "lohnsteuerbescheinigung" in t:
        return "Lohnsteuerbescheinigung"

    # === Bescheid / Berechnung / Erklärung ===
    if "einkommensteuerbescheid" in t or "steuerbescheid" in t or "bescheid für 20" in t:
        return "Steuerbescheid"
    if "steuerberechnung" in t or "festgesetzt werden" in t:
        return "ESt-Berechnung"
    # Bank-Steuerbescheinigung NUR wenn nicht Lohn-/keine andere Steuerbescheinigung
    if ("erträgnisaufstellung" in t
            or ("steuerbescheinigung" in t and "lohnsteuerbescheinigung" not in t)):
        return "Steuerbescheinigung (Bank)"
    if "hauptvordruck est" in t:   # nur starker Erklärungs-Marker, nicht greedy
        return "Einkommensteuererklärung"

    # === Werbungskosten (Anlage N) — SPÄT + Bescheid-Guard (sonst fangen Bescheid-Fotos hier an) ===
    if not any(k in t for k in ["bescheid","festgesetzt","festsetzung","steuerberechnung",
                                "zu versteuerndes einkommen","erstattung","nachzahlung"]):
        if ("werbungskosten" in t or "entfernungspauschale" in t
                or ("arbeitsstelle" in t and ("km" in t or "fahrt" in t))
                or ("erste tätigkeitsstätte" in t and "entfernung" in t)):
            return "Werbungskosten"

    return "Sonstiges"


if __name__ == "__main__":
    import glob, json, sys
    ocr_dir = sys.argv[1] if len(sys.argv) > 1 else "ocr_hh"
    for f in sorted(glob.glob(f"{ocr_dir}/*.ocr.json")):
        d = json.loads(open(f, encoding="utf-8").read())
        text = "\n".join(l["text"] for pg in d["pages"] for l in pg["lines"])
        print(f"  {classify_doc(text, d['file'], len(d['pages'])):28} {d['file'][:50]}")
