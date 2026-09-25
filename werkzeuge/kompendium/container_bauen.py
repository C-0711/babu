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


def _stapel_einbetten(texte: list[str], *, api: str | None = None,
                     modell: str | None = None) -> list[list[float] | None]:
    """Viele Texte in EINER Anfrage an den Embedding-Dienst — dieselbe
    Konvention wie `babu_web.embedding_rechnen(als_dokument=True)`
    (Präfix „title: none | text: …“, 6.000 Zeichen, truncate 2040). Für das
    ganze Bundesrecht (> 100.000 Normen) wäre Text für Text zu langsam."""
    import requests  # noqa: PLC0415
    api = api or os.environ.get("EMBED_API", "http://127.0.0.1:11436/v1/embeddings")
    modell = modell or os.environ.get("EMBED_MODELL", "embeddinggemma")
    for versuch in range(4):
        try:
            r = requests.post(api, json={"model": modell,
                                         "input": [f"title: none | text: {x[:6000]}" for x in texte],
                                         "truncate_prompt_tokens": 2040}, timeout=300)
            r.raise_for_status()
            daten = sorted(r.json()["data"], key=lambda d: d["index"])
            return [d["embedding"] for d in daten]
        except Exception:  # noqa: BLE001
            import time  # noqa: PLC0415
            time.sleep(5 * (versuch + 1))
    return [None] * len(texte)


def bauen(quellordner: Path | str, ziel: Path | str, *, probe: bool = False,
          embed=None, stapel: int = 0) -> dict:
    """`stapel` > 0: in Stapeln dieser Größe einbetten (ohne `embed`)."""
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

    fertig = []
    import numpy as np  # noqa: PLC0415
    if stapel and embed is None:
        for s in range(0, len(neu), stapel):
            teil = neu[s:s + stapel]
            for a, v in zip(teil, _stapel_einbetten([a["text"] for a in teil])):
                if v is None:
                    ergebnis["fehler"] += 1
                    continue
                vek = np.asarray(v, dtype=np.float32)
                fertig.append({**a, "_vektor": vek / (np.linalg.norm(vek) or 1.0)})
            if (s // stapel) % 200 == 0:
                print(f"  {s + len(teil)}/{len(neu)} eingebettet", flush=True)
    else:
        embed = embed or sab._standard_embedder()
        for a in neu:
            v = embed(a["text"])
            if not v or not v.get("vektor"):
                ergebnis["fehler"] += 1
                print(f"  ohne Vektor (Dienst?): {a['quelle']} · {a['loc']}")
                continue
            fertig.append({**a, "_vektor": sab._l2_normalisieren(v["vektor"])})
    if not fertig:
        return ergebnis

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


def grundstock(quelle: Path | str, ziel: Path | str, ohne: tuple[str, ...]) -> dict:
    """Einen neuen Container als KOPIE eines vorhandenen anlegen — ohne die Atome,
    deren Quelle mit einem der Präfixe in `ohne` beginnt. Vektoren und Atome
    werden Zeile für Zeile übernommen (kein neues Einbetten), die IDs neu
    gezählt. Grundwissen- und Kontierungsdateien werden NICHT kopiert — die
    bringt der Quellordner des neuen Portals mit.

    Beispiel Werkstatt: der Friseur-Container ohne Friseur-AfA-Tabelle,
    Salon-Statistik und Beauty-Kontenplan; GoBD, Kassenrecht, Richtsätze,
    AfA-Tabelle AV und SKR04 bleiben."""
    quelle, ziel = Path(quelle).expanduser(), Path(ziel).expanduser()
    if ziel.resolve() == (Path.home() / "kompendium").resolve():
        raise RuntimeError("Der Hauptbestand ~/kompendium wird hier nie beschrieben.")
    if (ziel / "atome.jsonl").exists():
        raise RuntimeError(f"{ziel} hat schon einen Bestand — der Grundstock wird nur einmal gelegt.")
    import numpy as np  # noqa: PLC0415
    atome = sab._atome_lesen(quelle / "atome.jsonl")
    matrix = np.load(quelle / "vektoren.npy", mmap_mode="r")
    if len(atome) != matrix.shape[0]:
        raise RuntimeError("Quelle kaputt: Atome und Vektoren passen nicht zusammen.")
    behalten = [i for i, a in enumerate(atome) if not (a.get("quelle") or "").startswith(tuple(ohne))]
    ziel.mkdir(parents=True, exist_ok=True)
    tmp_j, tmp_n = ziel / "atome.jsonl.tmp", ziel / "vektoren.npy.tmp"
    with open(tmp_j, "w", encoding="utf-8") as f:
        for neu_id, i in enumerate(behalten):
            f.write(json.dumps({**atome[i], "id": neu_id}, ensure_ascii=False) + "\n")
    with open(tmp_n, "wb") as f:
        np.save(f, np.asarray(matrix[behalten], dtype=np.float32))
    if sum(1 for _ in open(tmp_j, "rb")) != np.load(tmp_n, mmap_mode="r").shape[0]:
        tmp_j.unlink(missing_ok=True)
        tmp_n.unlink(missing_ok=True)
        raise RuntimeError("Nachprüfung fehlgeschlagen — nichts geschrieben.")
    os.replace(tmp_j, ziel / "atome.jsonl")
    os.replace(tmp_n, ziel / "vektoren.npy")
    return {"quelle_atome": len(atome), "behalten": len(behalten), "ohne": len(atome) - len(behalten)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("quellordner")
    p.add_argument("ziel")
    p.add_argument("--probe", action="store_true", help="nur zählen, nichts schreiben")
    p.add_argument("--grundstock", help="vorher als Kopie dieses Containers anlegen")
    p.add_argument("--ohne", nargs="*", default=[], help="Quellen-Präfixe, die der Grundstock weglässt")
    p.add_argument("--stapel", type=int, default=0, help="in Stapeln dieser Größe einbetten (z. B. 64)")
    a = p.parse_args(argv)
    if a.grundstock:
        print(json.dumps(grundstock(a.grundstock, a.ziel, tuple(a.ohne)), ensure_ascii=False))
    print(json.dumps(bauen(a.quellordner, a.ziel, probe=a.probe, stapel=a.stapel), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
