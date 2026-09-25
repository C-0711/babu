#!/usr/bin/env python3
"""Das ganze Bundesrecht im amtlichen Wortlaut holen — jedes Gesetz und jede
Verordnung aus gesetze-im-internet.de (Inhaltsverzeichnis gii-toc.xml), jede
Norm vollständig, ohne Auswahl. Daraus baut `container_bauen.py` den
gemeinsamen Container `~/kompendium-bundesrecht`, in dem jedes Portal
(Friseur, Barber, Werkstatt …) zusätzlich zu seinem Branchen-Container sucht.

Eine Datei je Gesetz (`<abk>.md`), Kopf mit Fundstelle, Stand, Abrufdatum —
dasselbe Format wie `barber/gesetze_holen.py`, dessen `holen()` hier benutzt
wird. Wiederaufnehmbar: vorhandene Dateien werden übersprungen. Amtliche
Werke (§ 5 UrhG).

    python3 werkzeuge/kompendium/bundesrecht_holen.py ZIELORDNER [--faeden 4]
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "barber"))
from gesetze_holen import holen  # noqa: E402

TOC = "https://www.gesetze-im-internet.de/gii-toc.xml"


def verzeichnis() -> list[tuple[str, str]]:
    with urllib.request.urlopen(TOC, timeout=120) as r:
        t = r.read().decode("utf-8")
    return [(link.split("/")[3], " ".join(titel.split()))
            for titel, link in re.findall(r"<title>([^<]*)</title>\s*<link>([^<]*)</link>", t)]


def main() -> int:
    ziel = Path(sys.argv[1]).expanduser()
    ziel.mkdir(parents=True, exist_ok=True)
    faeden = int(sys.argv[sys.argv.index("--faeden") + 1]) if "--faeden" in sys.argv else 4
    heute = datetime.date.today().isoformat()
    alle = verzeichnis()
    offen = [(a, n) for a, n in alle if not (ziel / f"{a}.md").exists()]
    print(f"{len(alle)} Gesetze und Verordnungen, {len(offen)} offen", flush=True)
    fertig = fehler = normen = 0
    t0 = time.time()

    def eins(eintrag):
        abk, name = eintrag
        for versuch in range(3):
            try:
                return holen(abk, name[:200], ziel, heute)
            except Exception as e:  # noqa: BLE001
                letzter = e
                time.sleep(2 * (versuch + 1))
        raise letzter

    with cf.ThreadPoolExecutor(faeden) as ex:
        for (abk, _), f in zip(offen, ex.map(lambda e: _sicher(eins, e), offen)):
            if isinstance(f, Exception):
                fehler += 1
                print(f"FEHLER {abk}: {type(f).__name__}", flush=True)
            else:
                fertig += 1
                normen += f[0]
            if (fertig + fehler) % 250 == 0:
                print(f"{fertig + fehler}/{len(offen)} · {normen} Normen · {fehler} Fehler · "
                      f"{time.time() - t0:.0f} s", flush=True)
    print(f"fertig: {fertig} Gesetze, {normen} Normen, {fehler} Fehler, {time.time() - t0:.0f} s", flush=True)
    return 0


def _sicher(f, e):
    try:
        return f(e)
    except Exception as ex:  # noqa: BLE001
        return ex


if __name__ == "__main__":
    sys.exit(main())
