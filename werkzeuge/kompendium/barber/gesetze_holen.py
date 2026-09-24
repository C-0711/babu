#!/usr/bin/env python3
"""Die Gesetze des Barber-Containers im amtlichen Wortlaut holen.

Quelle ist gesetze-im-internet.de (Bundesministerium der Justiz, amtliche
Fassung als XML je Gesetz). Jede Norm wird ein Abschnitt `## <Abk.> <§> <Titel>`
in einer Markdown-Datei je Gesetz, mit Fundstelle, Stand und Abrufdatum im
Kopf — so trägt jedes Atom, das `container_bauen.py` daraus schneidet, seine
Quelle in sich. Amtliche Werke (§ 5 UrhG).

    python3 werkzeuge/kompendium/barber/gesetze_holen.py ZIELORDNER

Die Liste unten ist das Expertenwissen eines Barbershops: Steuer und Kasse,
Handwerk und Meister, Arbeit und Sozialversicherung, Hygiene und Gefahrstoffe,
Preisaushang, Aufenthalt für Selbständige, Doppelbesteuerung Türkei.
"""
from __future__ import annotations

import datetime
import io
import re
import sys
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

GESETZE = {
    # Steuer und Kasse
    "ao_1977": "Abgabenordnung", "ustg_1980": "Umsatzsteuergesetz",
    "ustdv_1980": "Umsatzsteuer-Durchführungsverordnung", "estg": "Einkommensteuergesetz",
    "estdv_1955": "Einkommensteuer-Durchführungsverordnung", "gewstg": "Gewerbesteuergesetz",
    "kassensichv": "Kassensicherungsverordnung",
    "dbabkg_tur": "Doppelbesteuerungsabkommen Deutschland–Türkei",
    # Handwerk, Meister, Ausbildung, Gewerbe
    "hwo": "Handwerksordnung", "gewo": "Gewerbeordnung", "gewanzv_2014": "Gewerbeanzeigeverordnung",
    "friseur-mstrv": "Friseurmeisterverordnung", "friseurausbv_2008": "Friseur-Ausbildungsverordnung",
    "hwreintrv": "Anerkennung von Prüfungen für die Handwerksrolle",
    "afbg": "Aufstiegsfortbildungsförderungsgesetz (Meister-BAföG)",
    "bbig_2005": "Berufsbildungsgesetz",
    "bbimindvergfbek_2026": "Mindestausbildungsvergütung 2026",
    # Arbeit und Sozialversicherung
    "sgb_4": "SGB IV", "sgb_6": "SGB VI", "milog": "Mindestlohngesetz",
    "milov5": "Fünfte Mindestlohnanpassungsverordnung", "milodokv_2015": "Mindestlohndokumentationspflichtenverordnung",
    "schwarzarbg_2004": "Schwarzarbeitsbekämpfungsgesetz", "arbzg": "Arbeitszeitgesetz",
    "jarbschg": "Jugendarbeitsschutzgesetz", "muschg_2018": "Mutterschutzgesetz",
    "burlg": "Bundesurlaubsgesetz", "entgfg": "Entgeltfortzahlungsgesetz",
    "kschg": "Kündigungsschutzgesetz", "nachwg": "Nachweisgesetz",
    "tzbfg": "Teilzeit- und Befristungsgesetz", "arbschg": "Arbeitsschutzgesetz",
    "arbmedvv": "Verordnung zur arbeitsmedizinischen Vorsorge",
    "gefstoffv_2010": "Gefahrstoffverordnung",
    # Hygiene, Preise, Aufenthalt, Datenschutz
    "ifsg": "Infektionsschutzgesetz", "pangv_2022": "Preisangabenverordnung",
    "preisangg": "Preisangabengesetz", "aufenthg_2004": "Aufenthaltsgesetz",
    "bdsg_2018": "Bundesdatenschutzgesetz",
}


def _text(el) -> str:
    if el is None:
        return ""
    teile = []
    for p in el.iter():
        if p.tag in ("P", "DT", "DD", "LA", "row"):
            t = " ".join("".join(p.itertext()).split())
            if t:
                teile.append(t)
    if not teile:
        teile = [" ".join("".join(el.itertext()).split())]
    # Doppelte aus verschachtelten Elementen entfernen, Reihenfolge behalten.
    gesehen, aus = set(), []
    for t in teile:
        if t not in gesehen:
            gesehen.add(t)
            aus.append(t)
    return "\n\n".join(aus)


def holen(abk: str, name: str, ziel: Path, heute: str) -> tuple[int, int]:
    url = f"https://www.gesetze-im-internet.de/{abk}/xml.zip"
    with urllib.request.urlopen(url, timeout=120) as r:
        daten = r.read()
    z = zipfile.ZipFile(io.BytesIO(daten))
    xml = z.read(next(n for n in z.namelist() if n.endswith(".xml")))
    wurzel = ET.fromstring(xml)
    normen = wurzel.findall("norm")
    kopf = normen[0].find("metadaten") if normen else None
    jurabk = (kopf.findtext("jurabk") or abk).strip() if kopf is not None else abk
    lang = " ".join((kopf.findtext("langue") or name).split()) if kopf is not None else name
    stand = "; ".join(" ".join(s.itertext()).strip()
                      for s in (kopf.findall("standangabe") if kopf is not None else []))
    zeilen = [f"# {name} ({jurabk})", "",
              f"Quelle: {url.replace('/xml.zip', '/')} — amtlicher Wortlaut ({lang}). "
              f"{('Stand: ' + stand + '. ') if stand else ''}Abgerufen {heute}.", ""]
    abschnitte = 0
    for n in normen:
        md = n.find("metadaten")
        enbez = " ".join((md.findtext("enbez") or "").split()) if md is not None else ""
        titel = " ".join("".join(md.find("titel").itertext()).split()) \
            if md is not None and md.find("titel") is not None else ""
        inhalt = _text(n.find("textdaten/text/Content"))
        if not inhalt or (not enbez and not titel):
            continue
        if re.fullmatch(r"\(?weggefallen\)?", inhalt.strip(), flags=re.I):
            continue
        zeilen += [f"## {jurabk} {enbez} {titel}".rstrip(), "", inhalt, ""]
        abschnitte += 1
    datei = ziel / f"{abk}.md"
    datei.write_text("\n".join(zeilen), encoding="utf-8")
    return abschnitte, datei.stat().st_size


def main() -> int:
    ziel = Path(sys.argv[1]).expanduser()
    ziel.mkdir(parents=True, exist_ok=True)
    heute = datetime.date.today().isoformat()
    summe = 0
    for abk, name in GESETZE.items():
        try:
            n, groesse = holen(abk, name, ziel, heute)
            summe += n
            print(f"{abk:22} {n:5} Normen  {groesse // 1024:6} KB  {name}")
        except Exception as e:  # noqa: BLE001
            print(f"{abk:22} FEHLER {type(e).__name__}: {e}")
    print(f"zusammen {summe} Normen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
