#!/usr/bin/env python3
"""Die Gesetze des Werkstatt-Containers im amtlichen Wortlaut holen — Kopie der
Barber-Liste, angepasst: ohne Friseur-Verordnungen und Infektionsschutz, dazu
Kfz-Techniker-Meister- und Mechatroniker-Ausbildungsverordnung, StVZO und FZV
(Hauptuntersuchung, Zulassung), Altfahrzeug- und Altölverordnung,
Kreislaufwirtschaft, Betriebssicherheit (Hebebühnen, Druckluft), Batterie-
recht, Pflichtversicherung, das ganze BGB (darin Werkvertrag §§ 631 ff. und
Werkstattpfandrecht § 647) und das HGB — jede Norm, ohne Auswahl.

    python3 werkzeuge/kompendium/werkstatt/gesetze_holen.py ZIELORDNER
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "barber"))
from gesetze_holen import GESETZE as BARBER, holen  # noqa: E402

OHNE = {"friseur-mstrv", "friseurausbv_2008", "ifsg"}
GESETZE = {k: (v, None) for k, v in BARBER.items() if k not in OHNE}
GESETZE.update({
    "kfztechmstrv_2020": ("Kraftfahrzeugtechnikermeisterverordnung", None),
    "kfzmechaausbv_2013": ("Kfz-Mechatroniker-Ausbildungsverordnung", None),
    "stvzo_2012": ("Straßenverkehrs-Zulassungs-Ordnung", None),
    "fzv_2023": ("Fahrzeug-Zulassungsverordnung", None),
    "altautov": ("Altfahrzeug-Verordnung", None),
    "alt_lv": ("Altölverordnung", None),
    "krwg": ("Kreislaufwirtschaftsgesetz", None),
    "betrsichv_2015": ("Betriebssicherheitsverordnung", None),
    "battdg": ("Batterierecht-Durchführungsgesetz", None),
    "pflvg": ("Pflichtversicherungsgesetz", None),
    "bgb": ("Bürgerliches Gesetzbuch", None),
    "hgb": ("Handelsgesetzbuch", None),
})


def main() -> int:
    ziel = Path(sys.argv[1]).expanduser()
    ziel.mkdir(parents=True, exist_ok=True)
    heute = datetime.date.today().isoformat()
    summe = 0
    for abk, (name, nur) in GESETZE.items():
        try:
            n, groesse = holen(abk, name, ziel, heute, nur)
            summe += n
            print(f"{abk:22} {n:5} Normen  {groesse // 1024:6} KB  {name}")
        except Exception as e:  # noqa: BLE001
            print(f"{abk:22} FEHLER {type(e).__name__}: {e}")
    print(f"zusammen {summe} Normen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
