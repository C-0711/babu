"""Vektorisiert den Bestand: jedes Review ohne Embedding-Beiakte bekommt sie.

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
    print(f"{len(staemme)} Reviews · {fertig} hatten schon einen Vektor · "
          f"{len(dateien)} {'wären' if probe else 'werden'} neu · {fehler} Fehler")
    if probe or not dateien:
        return 0 if not fehler else 1
    commit = boxschreiber.schreiben(dateien, None,
                                    f"semantik: {len(dateien)} Beiakten für den "
                                    "Bestand", "backfill")
    print(f"Commit {commit}")
    return 0 if not fehler else 1


if __name__ == "__main__":
    sys.exit(main())
