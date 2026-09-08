"""Vektorisiert den Bestand: alles ohne Embedding-Beiakte bekommt eine.

Zwei Bestände, beide über EmbeddingGemma (:11436) und dieselben Präfixe:

* **Belege** — `review/<stamm>.embedding.json` aus `beleg_markdown`.
* **Unterlagen** — `dokumente/<datei>.embedding.json` aus
  `dokument_markdown` (Verträge, Post vom Amt). Bis 08.09.2026 gab es die
  gar nicht: sie wurden gelesen und erklärt, aber der Chat konnte sie nicht
  finden. In Ninas Box gemessen: 276 von 276 Belegen mit Vektor, 13
  Dokumente mit null.

Kontoauszüge bleiben draußen — Begründung in `dokument_markdown`.

Läuft im Container (docker compose exec babu-web python backfill_embeddings.py)
oder lokal mit gesetzten BABU_*-Umgebungsvariablen. Nutzt exakt dieselben
Bausteine wie /api/aufnahme — beleg_markdown und embedding_rechnen aus
babu_web —, damit Bestand und Neuzugang denselben Text einbetten.

Ein historisches review/<stamm>.md (altes Leseprotokoll) bleibt unangetastet;
nur wo gar keins liegt, wird das kanonische Markdown mit abgelegt.
Mit --probe wird nichts geschrieben, nur gezählt.
"""
import json
import subprocess
import sys

import babu_web as bw
import boxschreiber

BEIAKTEN = (".embedding.json", ".angaben.json", ".umsaetze.json", ".meta.json")


def review_staemme() -> list[str]:
    r = subprocess.run(["git", "-C", str(bw.STORE), "ls-tree", "--name-only",
                        "HEAD:review"], capture_output=True, text=True,
                       timeout=30, check=True)
    return sorted(n[:-len(".json")] for n in r.stdout.splitlines()
                  if n.endswith(".json")
                  and not any(n.endswith(b) for b in BEIAKTEN))


def dokument_pfade() -> list[str]:
    """Jedes abgelegte Dokument — ohne seine Beiakten."""
    r = subprocess.run(["git", "-C", str(bw.STORE), "ls-tree", "-r",
                        "--name-only", "HEAD", "dokumente"],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return []
    return sorted(n for n in r.stdout.splitlines()
                  if n and not n.endswith(bw.DOKUMENT_BEIAKTEN))


def main() -> int:
    probe = "--probe" in sys.argv
    dateien: dict[str, bytes] = {}
    fertig = fehler = 0
    staemme = review_staemme()
    for stamm in staemme:
        if bw.git_show(f"review/{stamm}.embedding.json") is not None:
            fertig += 1
            continue
        roh = bw.git_show(f"review/{stamm}.json")
        try:
            review = json.loads(roh)
        except (TypeError, ValueError):
            fehler += 1
            continue
        md = bw.beleg_markdown(review)
        if probe:
            dateien[f"review/{stamm}.embedding.json"] = b""
            continue
        semantik = bw.embedding_rechnen(md)
        if semantik is None:
            fehler += 1
            print(f"  ohne Vektor (Dienst?): {stamm}")
            continue
        dateien[f"review/{stamm}.embedding.json"] = json.dumps(semantik).encode()
        if bw.git_show(f"review/{stamm}.md") is None:
            dateien[f"review/{stamm}.md"] = md.encode()
    belege_neu = len(dateien)
    print(f"{len(staemme)} Reviews · {fertig} hatten schon einen Vektor · "
          f"{belege_neu} {'wären' if probe else 'werden'} neu · {fehler} Fehler")

    # Dieselbe Runde für die Unterlagen.
    dok = dokument_pfade()
    dok_fertig = 0
    for pfad in dok:
        if bw.git_show(pfad + ".embedding.json") is not None:
            dok_fertig += 1
            continue
        text = bw._dokument_text(pfad)  # noqa: SLF001
        if not text:
            continue          # noch nicht gelesen — kein Fehler, nur zu früh
        if probe:
            dateien[pfad + ".embedding.json"] = b""
            continue
        semantik = bw.embedding_rechnen(text)
        if semantik is None:
            fehler += 1
            print(f"  ohne Vektor (Dienst?): {pfad}")
            continue
        dateien[pfad + ".embedding.json"] = json.dumps(semantik).encode()
    print(f"{len(dok)} Unterlagen · {dok_fertig} hatten schon einen Vektor · "
          f"{len(dateien) - belege_neu} {'wären' if probe else 'werden'} neu")
    if probe or not dateien:
        return 0 if not fehler else 1
    # Ausdrücklich die Box benennen: seit dem Mehrbetrieb gibt es mehr als
    # eine, und ein Nachtrag, der still in die Default-Box schriebe, wäre
    # genau der Fehler, gegen den die Auflösung in `_api_wache` gebaut ist.
    commit = boxschreiber.schreiben(bw._box(), dateien, None,  # noqa: SLF001
                                    f"semantik: {len(dateien)} Beiakten für den "
                                    "Bestand", "backfill")
    print(f"Commit {commit}")
    return 0 if not fehler else 1


if __name__ == "__main__":
    sys.exit(main())
