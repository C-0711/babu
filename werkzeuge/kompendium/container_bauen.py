#!/usr/bin/env python3
"""Einen Wissenscontainer für ein Portal bauen — läuft auf dem HOST.

Ein Portal (`server/belegreview/portale/`) nennt seine Container als
Verzeichnisse unter $HOME, das eigene zuletzt; Barber etwa
`~/kompendium-barber`. Ein Container hat dasselbe Format wie der
Hauptbestand `~/kompendium`:

    atome.jsonl                 ein Atom je Zeile {id, sha, quelle, typ, loc, text}
    vektoren.npy                float32, L2-normalisiert, Zeile i = Atom i
    grundwissen.md              stehender Block des Expertenchats
    kontierung-grundwissen.md   stehender Block des Buchungswegs

Eingabe ist ein Quellordner mit Markdown/Text-Dateien. Jede Datei wird an
Überschriften und Leerzeilen in Atome von höchstens ~1.200 Zeichen geteilt;
`grundwissen.md` und `kontierung-grundwissen.md` im Quellordner werden
zusätzlich unverändert in den Container kopiert. Jede Quelldatei soll ihre
Herkunft im Kopf nennen (Gesetz, Paragraf, Fundstelle, Abrufdatum) — ein
Atom ohne Quelle gehört nicht in einen Container, aus dem ein Chat zitiert.

    python3 werkzeuge/kompendium/container_bauen.py QUELLORDNER ~/kompendium-barber --probe
    python3 werkzeuge/kompendium/container_bauen.py QUELLORDNER ~/kompendium-barber
    docker compose -f ~/babu-docker/docker/compose.yml restart babu-web

Eigenschaften wie `skr04_atome_bauen.py`, dessen Bausteine hier benutzt
werden: nur anhängen; idempotent über (quelle, sha des Textes); jede Zeile
L2-normalisiert; atomar über `.tmp` + `os.replace()` mit Sicherungskopie;
die Invariante Zeilen == Vektoren wird VOR dem Ersetzen geprüft. Eingebettet
wird über den Dienst auf :11436 mit dem Dokument-Präfix, genau wie
`babu_web.embedding_rechnen(als_dokument=True)`.

Der Hauptbestand `~/kompendium` wird von diesem Werkzeug nie beschrieben.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))

import skr04_atome_bauen as sab  # noqa: E402

STEHEND = ("grundwissen.md", "kontierung-grundwissen.md")
GRENZE = 1200


def atome_aus_text(quelle: str, text: str) -> list[dict]:
    """Teilt einen Text an Überschriften in Abschnitte und jeden Abschnitt
    an Absätzen in Atome von höchstens ~GRENZE Zeichen. Die Überschrift reist
    mit jedem Teil, damit ein Atom allein verständlich bleibt."""
    abschnitte: list[tuple[str, list[str]]] = [("", [])]
    for zeile in text.splitlines():
        if re.match(r"^#{1,4}\s", zeile):
            abschnitte.append((zeile.lstrip("#").strip(), []))
        else:
            abschnitte[-1][1].append(zeile)
    teile: list[str] = []
    for titel, zeilen in abschnitte:
        stueck = ""
        for absatz in re.split(r"\n\s*\n", "\n".join(zeilen).strip()):
            absatz = absatz.strip()
            if not absatz:
                continue
            if stueck and len(stueck) + len(absatz) > GRENZE:
                teile.append(f"{titel}\n{stueck}".strip())
                stueck = ""
            stueck = f"{stueck}\n\n{absatz}".strip()
        if stueck:
            teile.append(f"{titel}\n{stueck}".strip())
    return [{"sha": hashlib.sha256(t.encode()).hexdigest()[:16], "quelle": quelle,
             "typ": "md", "loc": f"txt#{i}", "text": t}
            for i, t in enumerate(teile) if len(t) > 40]


def quellen_lesen(ordner: Path) -> list[dict]:
    atome = []
    for datei in sorted(ordner.rglob("*")):
        if datei.suffix.lower() not in (".md", ".txt") or datei.name in STEHEND:
            continue
        atome.extend(atome_aus_text(str(datei.relative_to(ordner)),
                                    datei.read_text(encoding="utf-8")))
    return atome


def bauen(quellordner: Path | str, ziel: Path | str, *, probe: bool = False,
          embed=None) -> dict:
    quellordner, ziel = Path(quellordner).expanduser(), Path(ziel).expanduser()
    if ziel.resolve() == (Path.home() / "kompendium").resolve():
        raise RuntimeError("Der Hauptbestand ~/kompendium wird hier nie beschrieben.")
    jsonl, npy = ziel / "atome.jsonl", ziel / "vektoren.npy"
    alt = sab._atome_lesen(jsonl)
    vorhanden = {(a.get("quelle"), a.get("sha")) for a in alt}
    kandidaten = quellen_lesen(quellordner)
    neu = [a for a in kandidaten if (a["quelle"], a["sha"]) not in vorhanden]
    stehend = [n for n in STEHEND if (quellordner / n).exists()]
    ergebnis = {"vorhandene_atome": len(alt), "kandidaten": len(kandidaten),
                "neu": len(neu), "stehend": stehend, "fehler": 0, "geschrieben": False}
    if probe:
        return ergebnis

    ziel.mkdir(parents=True, exist_ok=True)
    for n in stehend:
        if (ziel / n).exists():
            sab._backup(ziel / n)
        shutil.copy2(quellordner / n, ziel / n)
    if not neu:
        return ergebnis

    embed = embed or sab._standard_embedder()
    fertig = []
    for a in neu:
        v = embed(a["text"])
        if not v or not v.get("vektor"):
            ergebnis["fehler"] += 1
            print(f"  ohne Vektor (Dienst?): {a['quelle']} · {a['loc']}")
            continue
        fertig.append({**a, "_vektor": sab._l2_normalisieren(v["vektor"])})
    if not fertig:
        return ergebnis

    import numpy as np  # noqa: PLC0415
    neue = np.asarray([a["_vektor"] for a in fertig], dtype=np.float32)
    if npy.exists():
        alte = np.asarray(np.load(npy), dtype=np.float32)
        if alte.shape[0] and alte.shape[1] != neue.shape[1]:
            raise RuntimeError(f"Dimension passt nicht: {alte.shape[1]} gegen "
                               f"{neue.shape[1]} — nichts geschrieben.")
        matrix = np.concatenate([alte, neue]) if alte.shape[0] else neue
    else:
        matrix = neue
    start = max((a.get("id", -1) for a in alt), default=-1) + 1
    zeilen = alt + [{"id": start + i, **{k: a[k] for k in ("sha", "quelle", "typ", "loc", "text")}}
                    for i, a in enumerate(fertig)]
    if len(zeilen) != matrix.shape[0]:
        raise RuntimeError(f"Invariante verletzt: {len(zeilen)} Atome, "
                           f"{matrix.shape[0]} Vektoren — nichts geschrieben.")
    sab._backup(jsonl)
    sab._backup(npy)
    tmp_j, tmp_n = jsonl.with_name("atome.jsonl.tmp"), npy.with_name("vektoren.npy.tmp")
    with open(tmp_j, "w", encoding="utf-8") as f:
        for z in zeilen:
            f.write(json.dumps(z, ensure_ascii=False) + "\n")
    with open(tmp_n, "wb") as f:
        np.save(f, matrix)
    if sum(1 for _ in open(tmp_j, "rb")) != np.load(tmp_n, mmap_mode="r").shape[0]:
        tmp_j.unlink(missing_ok=True)
        tmp_n.unlink(missing_ok=True)
        raise RuntimeError("Nachprüfung fehlgeschlagen — alter Stand bleibt.")
    os.replace(tmp_j, jsonl)
    os.replace(tmp_n, npy)
    ergebnis.update(geschrieben=True, gesamt_atome=len(zeilen))
    return ergebnis


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("quellordner")
    p.add_argument("ziel")
    p.add_argument("--probe", action="store_true", help="nur zählen, nichts schreiben")
    a = p.parse_args(argv)
    print(json.dumps(bauen(a.quellordner, a.ziel, probe=a.probe), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
